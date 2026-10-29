/** Continuous rule sessions: ONE world, MANY player commands. The rule
 * controller composition (createRuleController) is bound to a single command
 * — its memory is frozen at construction. This runtime owns the same driver
 * mechanics but rotates the per-command identity plan between rounds, so the
 * SAME world accepts 「走到门厅」 then 「完成压力试验」 without being recreated.
 * Each submit() prepares a FRESH allocation plan (advance/input/round/point
 * and group slots) and clears the stale ids, exactly what advanceDecision
 * needs to allocate and start a new advance after the previous handback (the
 * server refuses only an ACTIVE advance/work; a concluded round starts clean).
 *
 * The WorldSession wrapper supplies the dual heartbeat (the lease stays
 * renewed while the player reads or types), uniform isolation and the H2
 * recovery entry: createRecovered() replays verified server facts into a
 * fresh driver — mid-round recovery resumes the open point from the saved
 * plan, a handback-boundary recovery simply waits for the next submit.
 *
 * Narration stays committed-template by default; an optional polisher (the
 * page's model experiment) may rephrase, and its output is accepted only if
 * checkFactNarration admits every clause — any failure keeps the template.
 *
 * G5 identity chain: the session registers the program round-identity sink and
 * runs its driver with the automatic-round identity gate. A confirmed continue
 * allocates the next round's point plus a group slot per served frozen order
 * member under a per-round stable allocation key (server-idempotent replays),
 * an incomplete/failed allocation stops the round entry with a recognizable
 * reason, and a refresh that lands between continue and the first point
 * re-provisions through the recovery entry. Continuation itself stays
 * handback until the model continuation batch opens (G4). */
import { ControllerDriver, initialMemory, type DriverStatus, type WorldModelPort } from '../controller';
import type { AllocationPlan, ControllerMemory, ModelTask, UpdatesCall } from '../schedule';
import type { WorldTransport } from '../transport';
import type { RecoveryLease } from '../recovery';
import type { HeartbeatClock } from './heartbeat';
import { WorldSession } from './session';
import type { RuntimePortLike } from './model-port';
import type { CommittedNarration, CommittedRead } from './committed-narration';
import { projectCommittedNarration, renderCommittedNarration, selectFactNarration } from './committed-narration';
import { RuleAuthority, decodeRuleAction, describeRuleDecision, encodeRuleAction, parseRuleCommand, type RulePolicy, type RuleReceipt } from './rule-facts';
import { projectTaskInput } from './focused-input';
import type { Id, InitialTemplate, Json, PointWork, RequestMap, WorldContext, WorldState } from '../types';

/** The driver-shaped §7.1 narration input, mirrored from the scheduler's
 * assembleNarrationInput so the polisher can feed the real prompt layer. */
export interface RuleNarrationInput {
  pointId: Id;
  before: WorldState | null;
  delta: { timeAdvance: CommittedRead['timeAdvance']; entityDeltas: CommittedRead['entityDeltas'] };
  after: WorldState;
  perspective: string;
}

/** The polisher returns a candidate text; rule-session alone decides via
 * checkFactNarration whether it replaces the template. Returning null means
 * "polish disabled for this call" — the template stands with no fallback
 * event (the page toggles the experiment mid-session).
 *
 * focused is the projected §7.1 view (facts + allowed phrases only) — the
 * prompt the small model should read; attempt carries the regen context:
 * on index 2 the first candidate failed the fact check and previous.text /
 * previous.reason say what to correct. The judge gate itself lives in
 * narrateFromReads (§8.2: 校验调用，失败则只重生文本). */
export interface PolishAttempt {
  index: 1 | 2;
  previous?: { text: string; reason: string };
}
export type RuleNarrationPolisher = (
  input: RuleNarrationInput,
  packet: CommittedNarration,
  focused: Json,
  attempt: PolishAttempt,
  /** 逐调用证据回调（usage/timings/raw）。必须按调用传入——实例级回调会被
   * polisher 的模块级缓存吞掉（整链验收 v2 的 chain completion 证据为空即此因）。 */
  onCompletion?: (evidence: unknown) => void,
) => Promise<string | null>;

export type RuleSessionEvent =
  | { kind: 'terminal'; status: DriverStatus }
  | { kind: 'narration'; pointId: Id; version: number; text: string; polished: boolean; polishReason: string | null; attempts: number }
  | { kind: 'polishFallback'; pointId: Id; detail: string }
  | { kind: 'decision'; inputText: string; outcome: 'allowed' | 'refused'; reason: string | null; text: string }
  | { kind: 'unparsed'; inputText: string };

export interface RuleWorldSessionOptions {
  transport: WorldTransport;
  initial: InitialTemplate;
  policy: RulePolicy;
  holderId?: string;
  clock?: HeartbeatClock;
  heartbeatLeadMs?: number;
  retryBackoffMs?: number;
  polish?: RuleNarrationPolisher | null;
  onEvent?: (event: RuleSessionEvent) => void;
}

export interface RuleSessionSnapshot {
  world: WorldContext | null;
  work: PointWork | null;
  activeInput: { advanceId: Id; inputId: Id; text: string } | null;
}

interface IssuedGroup { receipt: RuleReceipt; result: Record<Id, string> }

/** One narration decision, isolated for tests: template by default; with a
 * polisher the model candidate must pass the fact-clause judge, and a
 * rejected candidate gets ONE regeneration attempt with feedback (§8.2:
 * 校验调用，失败则只重生文本) before the template stands. Any polisher
 * failure falls back to the template with a fallback event. */
export async function narrateFromReads(after: CommittedRead, before: CommittedRead | null,
  polisher: RuleNarrationPolisher | null, onEvent?: (event: RuleSessionEvent) => void): Promise<string> {
  const packet = projectCommittedNarration(after, before);
  const render = { time: after.timeAdvance?.duration ?? null };
  const template = renderCommittedNarration(packet, render);
  let text = template;
  let polished = false;
  let polishReason: string | null = null;
  let attempts = 0;
  if (polisher) {
    const protagonist = after.state.protagonistId;
    const name = after.state.initial.characters[protagonist]?.name ?? protagonist;
    const assembled: RuleNarrationInput = {
      pointId: after.pointId,
      before: before ? structuredClone(before.state) : null,
      delta: structuredClone({ timeAdvance: after.timeAdvance, entityDeltas: after.entityDeltas }),
      after: structuredClone(after.state),
      perspective: `主角视角（${protagonist}「${name}」）；只表达已结算的世界事实`,
    };
    const focused: Json = projectTaskInput('narration', structuredClone(assembled) as unknown as Json,
      { before, after });
    try {
      let previous: { text: string; reason: string } | undefined;
      for (const index of [1, 2] as const) {
        const candidate = await polisher(assembled, packet, focused, { index, previous });
        if (candidate === null) break; // polish disabled mid-session
        attempts = index;
        const verdict = selectFactNarration(packet, candidate, render);
        polishReason = verdict.reason;
        if (verdict.accepted) {
          text = verdict.text;
          polished = true;
          break;
        }
        previous = { text: candidate, reason: verdict.reason ?? 'unknown' };
        if (index === 1) continue; // §8.2: one regeneration with feedback
        break;
      }
    } catch (error) {
      onEvent?.({ kind: 'polishFallback', pointId: after.pointId,
        detail: error instanceof Error ? `${error.name}: ${error.message}` : String(error) });
    }
  }
  onEvent?.({ kind: 'narration', pointId: packet.anchor.pointId, version: packet.anchor.version, text, polished, polishReason, attempts });
  return text;
}

/** The per-command identity plan: a fresh allocationKey over the full slot
 * set. advanceDecision allocates only when ids.advance/input/round are
 * missing — the driver's preparePlayerInput clears them, so a second command
 * never silently reuses the finished round's identities. */
export function buildCommandPlan(holderId: string, order: Id[], counter: number): { plan: AllocationPlan; slotKeys: string[] } {
  const slots = [
    { slotKey: 'advance', kind: 'advance' as const }, { slotKey: 'input', kind: 'input' as const },
    { slotKey: 'round', kind: 'round' as const }, { slotKey: 'point', kind: 'point' as const },
    ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
  ];
  return { plan: { allocationKey: `${holderId}_cmd${counter}`, slots }, slotKeys: slots.map((slot) => slot.slotKey) };
}

export class RuleWorldSession {
  private readonly session: WorldSession;
  private readonly port: RuntimePortLike;
  private readonly memory: ControllerMemory;
  private readonly order: Id[];
  private readonly onEvent: (event: RuleSessionEvent) => void;
  private readonly polish: RuleNarrationPolisher | null;
  private readonly recoverWorldId: Id | undefined;
  private commandCounter = 0;
  /** Served-view mirrors captured from every envelope (world/work) and the
   * get_state reads (narration lineage). These back requireScope — the rule
   * authority only ever adjudicates against the CURRENTLY served facts. */
  private viewWorld: WorldContext | null = null;
  private viewWork: PointWork | null = null;
  private viewActiveInput: { advanceId: Id; inputId: Id; text: string } | null = null;
  private driver: ControllerDriver | null = null;

  constructor(private readonly options: RuleWorldSessionOptions, mode: 'new' | 'recover', worldId?: Id, heldLease?: RecoveryLease) {
    this.order = Object.keys(options.initial.characters).sort();
    this.onEvent = options.onEvent ?? (() => {});
    this.polish = options.polish ?? null;
    this.recoverWorldId = mode === 'recover' ? worldId : undefined;
    const holderId = options.holderId ?? `page_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    const prefix = `rule_${holderId}`;
    this.memory = initialMemory(prefix, holderId);
    if (mode === 'new') this.memory.initialTemplate = structuredClone(options.initial);
    const authority = new RuleAuthority(options.policy);
    const reads = new Map<Id, CommittedRead>();
    const groups = new Map<Id, IssuedGroup>();
    const requireScope = () => {
      if (!this.viewWorld || !this.viewWork) throw new Error('rule_live_scope_missing');
      // 读驱动的活引用：恢复会替换驱动的 memory 对象，会话侧捕获的引用会
      // 变陈旧（start_advance 的绑定只会落在驱动内存上）。
      const held = this.driver?.playerAdvance ?? this.viewActiveInput;
      if (!held || held.advanceId !== this.viewWorld.advance.advanceId || held.inputId !== this.viewWorld.advance.inputId) throw new Error('rule_input_identity_missing');
      return { world: this.viewWorld, work: this.viewWork, inputText: held.text };
    };
    const model: WorldModelPort = {
      generate: async (task: ModelTask, key: string, input: Json): Promise<Json> => {
        const driver = this.driver;
        if (!driver) throw new Error('rule_driver_missing');
        if (task === 'pointPlan') return [{ pointId: driver.getMemory().ids.point, kind: 'normal',
          timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } }, actorIds: [...this.order] }];
        if (task === 'action') {
          const data = input as unknown as { actor: string; advance: { inputText: string | null; intentStatus: string }; workingState: WorldState };
          const scope = requireScope();
          if (data.actor !== data.workingState.protagonistId || data.advance.intentStatus !== 'pending'
            || scope.world.advance.intentStatus !== 'pending') return { kind: 'skip' };
          if (data.advance.inputText !== scope.inputText) throw new Error('action_input_binding_changed');
          const proposal = parseRuleCommand(scope.inputText, data.workingState);
          if (!proposal) {
            this.onEvent({ kind: 'unparsed', inputText: scope.inputText });
            return { kind: 'skip' };
          }
          return { kind: 'act', text: encodeRuleAction(proposal) };
        }
        if (task === 'targets') return { targets: [] }; // no reaction/dice rules in this subset
        if (task === 'results') {
          const data = input as unknown as { groupId: string; members: { memberId: string; actionText: string; rollRefs: unknown[] }[]; workingState: WorldState };
          if (data.members.length !== 1 || data.members[0].memberId !== data.workingState.protagonistId || data.members[0].rollRefs.length) throw new Error('unsupported_rule_group');
          const scope = requireScope();
          const receipt = authority.adjudicate({ proposal: decodeRuleAction(data.members[0].actionText), inputText: scope.inputText,
            world: scope.world, state: data.workingState, pointId: scope.work.pointId });
          const record = authority.inspect(receipt);
          const text = describeRuleDecision(record.decision, data.workingState);
          const result = { [data.members[0].memberId]: text };
          groups.set(data.groupId, { receipt, result });
          this.onEvent({ kind: 'decision', inputText: scope.inputText, outcome: record.decision.outcome,
            reason: record.decision.outcome === 'refused' ? record.decision.reason : null, text });
          return result;
        }
        if (task === 'updates') {
          const data = input as unknown as { mode: string; groupId?: string; results?: unknown; stage?: string; workingState: WorldState };
          if (data.mode === 'time_scan') return data.stage ? { stage: data.stage, changes: {} } : [];
          const issued = data.groupId ? groups.get(data.groupId) : undefined;
          if (!issued) throw new Error('updates_without_rule_receipt');
          if (JSON.stringify(data.results) !== JSON.stringify(issued.result)) throw new Error('result_text_is_not_execution_authority');
          const scope = requireScope();
          const delta = authority.deltas(issued.receipt, scope.world, scope.work.pointId, data.workingState);
          const calls = Object.values(delta).flatMap<UpdatesCall>((change) => change.positionSet
            ? [{ stage: 'position', changes: { [change.entityId]: { entityId: change.entityId, positionSet: change.positionSet } } }]
            : [{ stage: 'tasks', changes: { [change.entityId]: { entityId: change.entityId, tasksAchieved: change.tasksAchieved } } },
              { stage: 'personality', changes: { [change.entityId]: { entityId: change.entityId, personalityChanges: change.personalityChanges } } },
              { stage: 'sanity', changes: { [change.entityId]: { entityId: change.entityId, sanitySet: change.sanitySet } } }]);
          return JSON.parse(JSON.stringify(data.stage ? calls.find((call) => call.stage === data.stage) ?? { stage: data.stage, changes: {} } : calls)) as Json;
        }
        if (task === 'narration') {
          const after = reads.get(key);
          if (!after) throw new Error('narration_requires_saved_point_read');
          const before = after.previousPointId ? reads.get(after.previousPointId) : null;
          if (before === undefined) throw new Error('narration_requires_saved_predecessor_read');
          return narrateFromReads(after, before, this.polish, this.onEvent);
        }
        if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
        throw new Error(`unsupported_rule_task:${task}`);
      },
    };
    this.port = { generate: model.generate, dispose: async () => {} }; // the polisher's engine is owned by the caller
    this.session = new WorldSession(options.transport, this.port, {
      recoverWorldId: this.recoverWorldId,
      recoveryLease: heldLease,
      clock: options.clock,
      heartbeatLeadMs: options.heartbeatLeadMs,
      retryBackoffMs: options.retryBackoffMs,
      hooks: { onStatus: (status) => this.onEvent({ kind: 'terminal', status }) },
      createDriver: (io) => {
        const tracked: WorldTransport = {
          execute: async (operation, request, scope, signal) => {
            const response = await io.transport.execute(operation, request, scope, signal);
            if ('world' in response) this.viewWorld = structuredClone(response.world);
            if ('work' in response) this.viewWork = structuredClone(response.work);
            if ('activeInput' in response) this.viewActiveInput = structuredClone(response.activeInput);
            if (operation === 'get_state') {
              const read = (response as unknown as { data: CommittedRead }).data;
              reads.set(read.pointId, structuredClone(read));
            }
            return response;
          },
        };
        this.driver = new ControllerDriver({ transport: tracked, model }, this.memory, {}, { identityGate: true });
        // G5 产品身份链：CONFIRMED continue 之后，新轮需要程序分配的 point 与
        // 服务端冻结 order 逐人的 group。allocationKey 按轮稳定（product_round_
        // <roundId>）——重试、且回执或新会话恢复补调时，服务端按 key 幂等重放
        // 同一批 id，不重复消费；响应在此做槽完整性校验，缺槽抛错交给驱动的
        // 身份屏障（roundIdentityBlocked → 可辨认 stop）。
        let identitySequence = 0;
        this.driver.setRoundIdentitySink(async (roundId, order) => {
          const live = this.driver!.getMemory();
          const worldId = this.viewWorld?.worldId;
          const fenceEpoch = this.viewWorld?.lease?.fenceEpoch;
          if (!worldId || !live.leaseToken || fenceEpoch == null) throw new Error('round_identity_scope_missing');
          // 请求命名空间按会话独立（idNamespace 计数器+时间+熵）：接管后新会话
          // 对同一轮的补调 requestId 不与旧会话碰撞——协议先核验请求幂等
          // （同 requestId 不同正文即 request_id_reused），业务重放只认
          // allocationKey。补调恒为新 requestId + 稳定 key，由业务层重放原批次。
          const namespace = this.session!.idNamespace;
          const allocationKey: Id = `product_round_${roundId}`;
          const slots = [{ slotKey: 'point', kind: 'point' as const },
            ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const }))];
          identitySequence += 1;
          // 分配经会话受控 transport（tracked → observed）：stop/失租及时
          // 结束等待、迟到回执不折入死会话、错误信封进入会话租约观察层；
          // 绝不绕行裸 transport。
          const response = await tracked.execute('allocate_ids', {
            protocolVersion: 2, requestId: `${namespace}_identity_${roundId}_${identitySequence}`, worldId,
            leaseToken: live.leaseToken, fenceEpoch, allocationKey, slots,
          } as RequestMap['allocate_ids'], { worldId });
          const allocations = (response as unknown as { data: { allocations: { slotKey: Id; id: Id }[] } }).data.allocations ?? [];
          const slotKeys = new Set(allocations.map((entry) => entry.slotKey));
          if (allocations.length !== slots.length || slotKeys.size !== slots.length || slots.some((slot) => !slotKeys.has(slot.slotKey))) {
            throw new Error('round_identity_allocation_incomplete');
          }
          return {
            ids: Object.fromEntries(allocations.map((entry) => [entry.slotKey, entry.id])),
            roundAllocations: { [roundId]: { allocationKey, slots } },
            allocatedKeys: [allocationKey],
          };
        });
        return this.driver;
      },
    });
  }

  static createNew(options: RuleWorldSessionOptions): RuleWorldSession {
    return new RuleWorldSession(options, 'new');
  }

  static createRecovered(options: RuleWorldSessionOptions, worldId: Id, heldLease?: RecoveryLease): RuleWorldSession {
    return new RuleWorldSession(options, 'recover', worldId, heldLease);
  }

  /** The worldId this session created or recovered; null before the first
   * envelope (a recovered session knows its id from construction). */
  get worldId(): Id | null {
    return this.viewWorld?.worldId ?? this.recoverWorldId ?? null;
  }

  get sessionStatus(): 'idle' | 'running' | 'stopped' | 'lost_lease' { return this.session.sessionStatus; }

  /** Read-only served view for the page between rounds. */
  snapshot(): RuleSessionSnapshot {
    return { world: structuredClone(this.viewWorld), work: structuredClone(this.viewWork), activeInput: structuredClone(this.viewActiveInput) };
  }

  getMemory(): ControllerMemory { return this.session.getMemory(); }

  /** Prepares ONE new player command in the SAME world and runs the driver
   * until it settles (handback → world_complete, or a terminal error). The
   * per-command plan goes through the driver's own preparePlayerInput —
   * bootstrapRecovery may have replaced the driver's memory object, so the
   * input binding must never land on a stale external clone. */
  async submit(command: string): Promise<DriverStatus> {
    if (this.sessionStatus === 'running') throw new Error('rule_session_busy');
    if (this.sessionStatus === 'stopped') throw new Error('rule_session_stopped');
    if (this.sessionStatus === 'lost_lease') throw new Error('rule_session_lease_lost');
    if (this.recoverWorldId !== undefined && !this.viewWorld) throw new Error('rule_session_recovery_incomplete');
    const driver = this.driver;
    if (!driver) throw new Error('rule_driver_missing');
    this.commandCounter += 1;
    const { plan, slotKeys } = buildCommandPlan(this.memory.holderId, this.order, this.commandCounter);
    driver.preparePlayerInput(command, this.order, plan, slotKeys);
    return this.session.run();
  }

  /** First run of a recovered session: the driver replays verified server
   * facts (mid-round work resumes automatically; a handback boundary settles
   * at once). */
  attach(): Promise<DriverStatus> {
    return this.session.run();
  }

  stop(): void { this.session.stop(); }
  async dispose(): Promise<void> { await this.session.dispose(); }
}
