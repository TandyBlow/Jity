/** B1 controller driver: the only place controller memory mutates. Executes
 * scheduler decisions against the transport and the model port, applies each
 * response back into memory and the served-state view, owns the requestId
 * factory (new id per business operation, same id on retries) and routes
 * error clientActions. World state, dice and digests stay server-side.
 * Every transport call — scheduler-emitted, preview, or follow-up — goes
 * through call(): timeout/request_in_progress retry with the original
 * payload up to retryLimit, definitive rejections retire the operation and
 * re-schedule. External commands are consumed only when actually executed,
 * so a pause survives a lease detour. */
import { WorldApiError, WorldTimeoutError, type WorldTransport } from './transport';
import {
  assembleCandidates, errorReaction, initialNarrationAssembly, mergeUpdatesStages, PROGRAM_ROLL_RULE, scheduleNext, timeScanCandidates, workingStateKey,
  type ControllerMemory, type Decision, type HarnessCommand, type ModelTask, type PlannedPoint, type RollRule, type SourceAnalysis, type UpdatesCall,
} from './schedule';
import type {
  Conclusion, ControlState, CurrentClaim, EntityDelta, ErrorResponse, Id, InitialTemplate, Json, PointWork, RequestMap,
  SettlementGroup, TimeAdvance, WorldContext, WorldOperation,
} from './types';

export interface WorldModelPort { generate(task: ModelTask, key: string, input: Json): Promise<Json> }
export interface ControllerIo { transport: WorldTransport; model: WorldModelPort }
export interface DriverOptions {
  retryLimit?: number;
  /** Scenario identity binding: scheduler key → allocate slotKey (e.g.
   * 'group:person_a' → 'group'). Applied when allocation responses land, so
   * scenario keying stays config, never mid-flight memory steering. */
  identityAliases?: Record<string, string>;
}

export type DriverStatus =
  | { kind: 'await'; reason: string }
  | { kind: 'stop'; reason: string }
  | { kind: 'error'; detail: string };

interface ServedState { world: WorldContext | null; control: ControlState; work: PointWork | null; activeInput: { advanceId: Id; inputId: Id; text: string } | null }

const INITIAL_CONTROL: ControlState = {
  phase: 'select_actor', paused: false, revision: 0,
  gate: { status: 'none', generation: null, issuedAtEpochMilli: null, expiresAtEpochMilli: null },
  blockedReasons: [], canCompute: true,
};

export function initialMemory(prefix: string, holderId: string): ControllerMemory {
  return {
    requestId: `${prefix}_0`, leaseToken: null, holderId, ids: {}, allocPlan: null, roundAllocations: {}, allocatedKeys: [], playerInput: null, playerAdvance: null,
    plan: null, planIndex: 0, prepareSuccessor: false, localPause: false, budget: { used: 0, max: null },
    narration: null, workingState: null, sources: [], staged: [], stagedTimeScan: null, groupActors: [], groupActions: [], lastModel: null, lastTargets: null, lastResults: null,
    updatesStages: [], updatesCalls: [], updatesApplied: 0, updatesPreviewSkipped: 0, updatesPendingRefs: [],
    continuation: null, successorTime: null, commitPayload: null, initialTemplate: null,
  };
}

/** Targets roll in ASCII targetId order (the recorded create_rolls order);
 * the dice rule is the program constant — the model never supplies rules. */
function asAsciiTargets(targets: { targetId: Id; triggerKey: Id }[]) {
  return [...targets].sort((a, b) => (a.targetId < b.targetId ? -1 : 1)).map((t) => ({ targetId: t.targetId, triggerKey: t.triggerKey, rule: PROGRAM_ROLL_RULE }));
}

function sourceComplete(source: SourceAnalysis): boolean {
  return source.targetsExtended && source.pendingTargets.length === 0 && source.rolled.every((r) => r.reacted || r.admitted !== true);
}

/** Any applicable candidate content — the split-boundary progress test: a
 * forward-reference batch whose remainder is empty has nothing to preview. */
function deltasHaveContent(deltas: Record<Id, EntityDelta>): boolean {
  return Object.values(deltas).some((d) => !!d.positionSet || d.sanitySet != null
    || (d.appearanceChanges?.length ?? 0) > 0 || (d.personalityChanges?.length ?? 0) > 0
    || (d.tasksAchieved?.length ?? 0) > 0 || (d.subtasksAdded?.length ?? 0) > 0);
}

type CallOutcome = { ok: true; response: unknown } | { ok: false; terminal?: DriverStatus };

export class ControllerDriver {
  private state: ServedState;
  private memory: ControllerMemory;
  private command: HarnessCommand | null = null;
  private stepCommand: HarnessCommand | null = null;
  private requestCounter = 0;
  private readonly retryLimit: number;
  private readonly identityAliases: Record<string, string>;

  constructor(private io: ControllerIo, memory: ControllerMemory, state?: Partial<ServedState>, options?: DriverOptions) {
    this.memory = memory;
    this.state = { world: null, control: INITIAL_CONTROL, work: null, activeInput: null, ...state };
    this.retryLimit = options?.retryLimit ?? 3;
    this.identityAliases = options?.identityAliases ?? {};
  }

  getMemory(): ControllerMemory { return structuredClone(this.memory); }
  getRequestCounter(): number { return this.requestCounter; }

  /** Read-only scheduler introspection for declared scenario boundaries. */
  pendingDecision(): Decision {
    return scheduleNext({ world: this.state.world, control: this.state.control, work: this.state.work, memory: this.memory, activeInput: this.state.activeInput });
  }

  /** Queues an external command; consumed when its operation executes, so it survives detours (lease loss). */
  deliver(command: HarnessCommand): void { this.command = command; }

  private nextRequestId(): Id {
    const prefix = this.memory.requestId.replace(/_\d+$/, '');
    this.memory.requestId = `${prefix}_${++this.requestCounter}`;
    return this.memory.requestId;
  }

  private commandOperation(command: HarnessCommand): WorldOperation | null {
    switch (command.kind) {
      case 'pause': case 'budget_exhausted': return 'checkpoint_pause';
      case 'resume': return 'checkpoint_resume';
      case 'cancel': return 'round_conclusion_cancel';
      default: return null;
    }
  }

  /** Runs decisions until a terminal status or the step limit. */
  async run(limit = 500): Promise<DriverStatus> {
    for (let i = 0; i < limit; i++) {
      const terminal = await this.step();
      if (terminal) return terminal;
    }
    return { kind: 'error', detail: 'driver step limit exceeded' };
  }

  /** Executes exactly one decision. Returns a terminal status, or undefined.
   * Commands are consumed only when this.command still IS the captured
   * command — one delivered while a request is in flight survives. */
  async step(): Promise<DriverStatus | undefined> {
    const command = this.command;
    this.stepCommand = command;
    if (command?.kind === 'player_input' && this.command === command) this.command = null; // consumed via memory.playerInput
    const decision = scheduleNext({ world: this.state.world, control: this.state.control, work: this.state.work, memory: this.memory, command: command && command.kind !== 'player_input' ? command : undefined, activeInput: this.state.activeInput });
    switch (decision.kind) {
      case 'await_command':
        if (this.command === command) this.command = null;
        return { kind: 'await', reason: decision.reason };
      case 'stop':
        if (this.command === command) this.command = null;
        return { kind: 'stop', reason: decision.reason };
      case 'model': {
        const output = await this.io.model.generate(decision.task, decision.key, decision.input);
        if (this.command === command) this.command = null;
        this.consumeModelOutput(decision, output);
        return undefined;
      }
      case 'read_working_state':
        if (this.command === command) this.command = null;
        return this.preview();
      case 'transport': {
        const executesCommand = command != null && this.commandOperation(command) === decision.operation;
        const outcome = await this.call(decision.operation, decision.request, decision.scope);
        if (outcome.ok) {
          if ((!command || executesCommand) && this.command === command) this.command = null; // a diverted command survives; a newer delivered command always survives
          this.adoptSuccess(decision.operation, decision.request, outcome.response);
          this.memory.lastModel = null;
          this.nextRequestId();
          return undefined;
        }
        return outcome.terminal; // definitive rejection: the command survives; state was refreshed, re-schedule
      }
    }
  }

  /** Single funnel for every transport call. Timeout/request_in_progress
   * retries, recovery hops and follow-up invocations all draw from ONE
   * shared budget, so no recovery chain can outlive retryLimit. A lease
   * held by another owner is a wait, not a reacquire loop. */
  private async call(operation: WorldOperation, request: unknown, scope: { worldId?: Id; pointId?: Id }, budget?: { left: number }): Promise<CallOutcome> {
    const retries = budget ?? { left: this.retryLimit };
    for (;;) {
      try {
        const response = await this.io.transport.execute(operation, request as never, scope);
        return { ok: true, response };
      } catch (error) {
        if (error instanceof WorldTimeoutError) {
          if (retries.left <= 0) return { ok: false, terminal: { kind: 'error', detail: `retry limit exceeded on ${operation} (timeout)` } };
          retries.left--;
          continue;
        }
        if (!(error instanceof WorldApiError)) throw error;
        const reaction = errorReaction(error.response);
        this.adoptState(error.response);
        if (reaction.followup === 'retry_same_request') {
          if (retries.left <= 0) return { ok: false, terminal: { kind: 'error', detail: `retry limit exceeded on ${operation} (${error.response.error.code})` } };
          retries.left--;
          continue;
        }
        if (error.response.error.code === 'lease_invalid' && error.response.error.details?.reason === 'lease_held') {
          return { ok: false, terminal: { kind: 'await', reason: 'lease_held_by_other' } };
        }
        if (retries.left <= 0) return { ok: false, terminal: { kind: 'error', detail: `recovery limit exceeded on ${operation} (${error.response.error.code})` } };
        retries.left--;
        this.nextRequestId();
        const terminal = await this.applyErrorFollowup(reaction.followup, error.response, retries);
        return { ok: false, terminal };
      }
    }
  }

  // ---------- model outputs ----------

  private consumeModelOutput(decision: Extract<Decision, { kind: 'model' }>, output: Json): void {
    this.memory.budget.used++;
    this.memory.lastModel = { task: decision.task, key: decision.key, output };
    switch (decision.task) {
      case 'pointPlan':
        this.memory.plan = structuredClone(output) as unknown as PlannedPoint[];
        break;
      case 'time':
        this.memory.successorTime = structuredClone(output) as unknown as TimeAdvance;
        break;
      case 'continuation':
        this.memory.continuation = structuredClone(output) as unknown as Conclusion;
        break;
      case 'initial':
        this.memory.initialTemplate = structuredClone(output) as unknown as InitialTemplate;
        break;
      case 'results':
        this.memory.lastResults = structuredClone(output) as Record<Id, string>;
        break;
      case 'targets': {
        // Capture the declared target set OUTSIDE lastModel: the runtime
        // allocate_ids hop clears lastModel on success and must not lose it.
        const declared = output as { targets?: unknown };
        if (!Array.isArray(declared.targets)) throw new Error('Targets output must carry a targets array');
        this.memory.lastTargets = { sourceId: decision.key, targets: (declared.targets as { targetId: Id }[]).map((t) => t.targetId) };
        break;
      }
      case 'updates':
        if (this.memory.updatesStages.length > 0) this.memory.updatesCalls.push(structuredClone(output) as unknown as UpdatesCall);
        break;
      default:
        break;
    }
  }

  // ---------- transport ----------

  private async preview(): Promise<DriverStatus | undefined> {
    const { world, control, work } = this.state;
    if (!world || !work) throw new Error('Preview without served point work');
    // Between-stage application (§6.3): with unapplied split-stage
    // candidates, fold the synthetic in-progress group into the preview so
    // the served working state reflects every prior stage — later stage
    // calls READ Python-applied state instead of re-declaring prior deltas.
    let inProgressGroup: SettlementGroup | null = null;
    if (this.memory.updatesCalls.length > this.memory.updatesApplied) {
      const pending = work.pendingGroup;
      const roster = this.memory.workingState ? Object.keys(this.memory.workingState.state.characters) : [];
      const mergedStages = mergeUpdatesStages(this.memory.updatesCalls);
      // 前向任务引用预检＋已应用/未决拆分（2026-10-26 复审修正 1；v5 修正：
      // 引用核对=当前状态∪本批已生产候选）：在途候选引用的任务，凡当前状
      // 态存在、或本批 subtasksAdded 已生产的，随合并候选交 A 共同投影——
      // A 在同一批内先建后达，个性等后序阶段立即读到 achieved（v5 实测组合
      // 路径的读错输入回归：只查状态会把已生产任务继续延后）。只有当前状
      // 态与本批生产都不覆盖的悬挂引用才滤出、记「未决」（updatesPendingRefs），
      // 由后序 subtasks 阶段生产、随最终批次经 checkUpdatesStages 结算；可
      // 达变化照常折入本边界 preview（§6.3：不能凭「后面还有 subtasks」就
      // 放行读旧状态），有效部分为空才整边界跳过（计一次 skip）；既无剩余
      // 生产者的悬挂引用明确停止。其余一切候选/绑定错误照常走 call() 的原
      // 有处理（超时/租约/刷新/终态），绝不按错误码吞咽。
      const liveTasks = this.memory.workingState?.state.characters ?? {};
      const producedByBatch = new Set<string>();
      for (const [entity, delta] of Object.entries(mergedStages)) {
        for (const task of delta.subtasksAdded ?? []) producedByBatch.add(`${entity}:${task.id}`);
      }
      const validDeltas: Record<Id, EntityDelta> = {};
      const forwardRefs: string[] = [];
      for (const [entity, delta] of Object.entries(mergedStages)) {
        const achieved = delta.tasksAchieved ?? [];
        const forward = achieved.filter((taskId) => liveTasks[entity]?.tasks?.[taskId] == null && !producedByBatch.has(`${entity}:${taskId}`));
        for (const taskId of forward) forwardRefs.push(`${entity}:${taskId}`);
        validDeltas[entity] = forward.length === 0 ? delta : { ...delta, tasksAchieved: achieved.filter((taskId) => !forward.includes(taskId)) };
      }
      // Named group → the action-unit shape; time scan → the groupId-less
      // candidates shape (wire rule: a null groupId may not invent actors,
      // movement or appearance — 2026-10-26 review finding 1).
      const fold = (deltas: Record<Id, EntityDelta>): SettlementGroup => (pending
        ? assembleCandidates({
            groupId: pending.groupId,
            actorIds: pending.memberIds.length ? pending.memberIds : [pending.sourceId],
            deltas,
            roster,
          })
        : timeScanCandidates(deltas, roster));
      if (forwardRefs.length === 0) {
        this.memory.updatesPendingRefs = [];
        inProgressGroup = fold(mergedStages);
      } else {
        // 悬挂引用只可能由剩余的 subtasks 阶段生产（本批生产已被共同投影
        // 排除）——无剩余生产者即明确停止。
        if (!this.memory.updatesStages.slice(this.memory.updatesCalls.length).includes('subtasks')) {
          this.memory.lastModel = null;
          this.memory.updatesPendingRefs = forwardRefs;
          return { kind: 'stop', reason: `dangling_updates_refs:${JSON.stringify(forwardRefs)}` };
        }
        this.memory.lastModel = null;
        this.memory.updatesPendingRefs = forwardRefs;
        if (!deltasHaveContent(validDeltas)) {
          // 整批皆未决：零网络调用跳过本边界，后序阶段读最后良好状态。
          this.memory.updatesApplied = this.memory.updatesCalls.length;
          this.memory.updatesPreviewSkipped += 1;
          return undefined;
        }
        // 拆分应用：有效部分随本边界 preview 进入服务状态；未决部分留在
        // 原始 calls 里（applied 只前移放行后序阶段，最终批次负责结算）。
        inProgressGroup = fold(validDeltas);
      }
    }
    const request: RequestMap['preview_point'] = {
      protocolVersion: 2, worldId: world.worldId,
      advanceId: world.advance.advanceId!, roundId: world.activeRoundId ?? world.round?.roundId ?? '',
      pointId: work.pointId, expectedPointId: world.head.pointId, expectedVersion: world.head.version,
      expectedCheckpointRevision: control.revision, timeAdvance: work.timeAdvance,
      // One settlement list, no separate channel: named staged units plus the
      // point's time-scan candidate once it has been staged (A §7), plus the
      // in-progress split-stage group while one is being assembled.
      settlementGroups: [
        ...this.memory.staged.map((s) => s.candidates),
        ...(this.memory.stagedTimeScan ? [this.memory.stagedTimeScan] : []),
        ...(inProgressGroup ? [inProgressGroup] : []),
      ],
    };
    let outcome: CallOutcome;
    if (inProgressGroup != null) {
      // 有界重算（2026-10-26 P1 修正）：在途组的候选性拒绝（如非法位置 →
      // ID_UNRESOLVED → version_mismatch）不会被上下文刷新自愈，而 call() 的
      // refresh followup 每步拿到新预算会无限循环。这里至多一次上下文刷新＋
      // 一次重试；仍拒绝则明确停止——绝不让后序阶段在旧状态上继续。
      outcome = { ok: false };
      for (let attempt = 0; attempt < 2 && !outcome.ok; attempt++) {
        try {
          const response = await this.io.transport.execute('preview_point', attempt === 0 ? request as never : { ...request, expectedCheckpointRevision: this.state.control.revision, expectedPointId: this.state.world!.head.pointId, expectedVersion: this.state.world!.head.version } as never, { worldId: world.worldId });
          outcome = { ok: true, response };
        } catch (error) {
          if (!(error instanceof WorldApiError)) throw error;
          if (attempt === 0 && error.response.error.clientAction === 'refresh_context') {
            const ctx = await this.call('get_context', {}, { worldId: world.worldId });
            if (!ctx.ok) return ctx.terminal;
            // 复审修正 2（2026-10-26）：刷新必须真正采纳——把 get_context
            // 回包写回控制器状态，attempt 1 的重试绑定才会取到新 revision/
            // version（否则原样重发旧 expected*，被再次拒绝）。采纳后先核对
            // 工作基线未迁移：仍是同一个 head 点才允许重试；基线已变明确停
            // 止，绝不拿着旧点位的候选去碰新点位。
            this.adoptState(ctx.response);
            this.memory.lastModel = null;
            const fresh = this.state.world;
            if (!fresh || !this.state.work || fresh.head.pointId !== world.head.pointId) {
              return { kind: 'stop', reason: `updates_preview_baseline_moved:${world.head.pointId}->${fresh?.head.pointId ?? 'null'}` };
            }
            continue;
          }
          return { kind: 'stop', reason: `updates_preview_refused:${error.response.error.code}` };
        }
      }
      if (!outcome.ok) return { kind: 'stop', reason: 'updates_preview_refused:unreachable' };
    } else {
      outcome = await this.call('preview_point', request, { worldId: world.worldId });
      if (!outcome.ok) return outcome.terminal;
    }
    this.adoptState(outcome.response);
    const data = (outcome.response as unknown as { data: { workingState: unknown; pointProjection: unknown } }).data;
    this.memory.workingState = { key: workingStateKey(this.state.work!), state: structuredClone(data.workingState) as never };
    this.memory.commitPayload = { point: structuredClone(data.pointProjection) as never, settlementGroups: this.memory.staged.map((s) => s.candidates) };
    this.memory.updatesApplied = this.memory.updatesCalls.length;
    this.memory.lastModel = null;
    this.nextRequestId();
    return undefined;
  }

  private async applyErrorFollowup(followup: ReturnType<typeof errorReaction>['followup'], error: ErrorResponse, budget: { left: number }): Promise<DriverStatus | undefined> {
    const code = error.error.code;
    const world = this.state.world;
    switch (followup) {
      case 'retry_same_request':
        return undefined;
      case 'refresh_context': {
        const outcome = await this.call('get_context', {}, { worldId: world?.worldId }, budget);
        if (!outcome.ok) return outcome.terminal;
        this.adoptState(outcome.response);
        this.memory.lastModel = null;
        // A refreshed context may carry a new fence: a held narration claim is
        // no longer trustworthy (claim_fenced) — drop it and re-claim.
        if (this.memory.narration) this.memory.narration.claim = null;
        this.nextRequestId();
        return undefined;
      }
      case 'lease_acquire': {
        const request = { protocolVersion: 2 as const, requestId: this.memory.requestId, worldId: world?.worldId ?? '', holderId: this.memory.holderId };
        const outcome = await this.call('lease_acquire', request, { worldId: world?.worldId }, budget);
        if (!outcome.ok) return outcome.terminal;
        this.adoptSuccess('lease_acquire', request, outcome.response);
        this.memory.lastModel = null;
        this.nextRequestId();
        return undefined;
      }
      case 'finish_own_narration': {
        const pointId = world?.head.pointId;
        if (world && pointId) {
          const input = this.memory.narration?.pointId === pointId ? this.memory.narration.input : initialNarrationAssembly(pointId);
          // Drop the exhausted claim and any stale narration output: the next
          // round-trip must claim afresh (claim_expired/cache_missing).
          this.memory.narration = { pointId, claim: null, input };
          this.memory.lastModel = null;
        }
        return undefined;
      }
      case 'pause_and_stop': {
        const request = {
          protocolVersion: 2 as const, requestId: this.memory.requestId, worldId: world?.worldId ?? '',
          leaseToken: this.memory.leaseToken ?? '', fenceEpoch: world?.lease?.fenceEpoch ?? 0,
          expectedPointId: world?.head.pointId ?? '', expectedVersion: world?.head.version ?? 0,
          expectedCheckpointRevision: this.state.control.revision, operation: 'pause' as const,
        };
        const outcome = await this.call('checkpoint_pause', request, { worldId: world?.worldId }, budget);
        if (!outcome.ok) return outcome.terminal;
        return { kind: 'stop', reason: `pause_and_stop:${code}` };
      }
      case 'await_control':
        if (this.command === this.stepCommand) this.command = null; // keep commands delivered while the request was in flight
        return { kind: 'await', reason: 'resolve_gate' };
      case 'stop':
        if (this.command === this.stepCommand) this.command = null;
        return { kind: 'stop', reason: `fix_request:${code}` };
    }
  }

  // ---------- response adoption ----------

  private adoptState(response: unknown): void {
    const envelope = response as { world?: WorldContext | null; control?: ControlState; work?: PointWork | null };
    if (envelope.world !== undefined) {
      const previousEpoch = this.state.world?.lease?.fenceEpoch ?? null;
      const nextEpoch = envelope.world?.lease?.fenceEpoch ?? null;
      this.state.world = envelope.world;
      // A lease-generation change — including losing the lease entirely —
      // fences every held narration claim.
      if (previousEpoch != null && previousEpoch !== nextEpoch && this.memory.narration) {
        this.memory.narration.claim = null;
      }
    }
    if (envelope.control !== undefined) {
      this.state.control = envelope.control;
      // A successful resume may still report claim_expired. Retire that
      // held generation before generating or submitting narration again.
      if (envelope.control.blockedReasons.includes('claim_expired') && this.memory.narration) {
        this.memory.narration.claim = null;
        this.memory.lastModel = null;
      }
    }
    if (envelope.work !== undefined) this.state.work = envelope.work;
    // 玩家输入文本（仅 context 回包携带该字段；undefined=未携带，保持现状）。
    if ((envelope as { activeInput?: unknown }).activeInput !== undefined) {
      this.state.activeInput = (envelope as { activeInput: { advanceId: Id; inputId: Id; text: string } | null }).activeInput;
    }
  }

  private retireFinishedSources(): void {
    while (this.memory.sources[0] && sourceComplete(this.memory.sources[0])) this.memory.sources.shift();
  }

  private adoptSuccess(operation: WorldOperation, request: unknown, response: unknown): void {
    this.adoptState(response);
    const req = request as Record<string, unknown>;
    const data = (response as unknown as { data?: Record<string, unknown>; replayed?: boolean }).data ?? {};
    const sources = this.memory.sources;
    switch (operation) {
      case 'create_world':
        this.memory.leaseToken = (data as unknown as { lease: { leaseToken: Id } }).lease.leaseToken;
        break;
      case 'allocate_ids': {
        const allocations = (data as { allocations: { slotKey: Id; id: Id }[] }).allocations ?? [];
        const slots = req.slots as { slotKey: Id }[];
        const keys = new Set(allocations.map((allocation) => allocation.slotKey));
        if (allocations.length !== slots.length || keys.size !== slots.length || slots.some((slot) => !keys.has(slot.slotKey))) throw new Error('Allocation response does not match requested slots');
        for (const allocation of allocations) {
          this.memory.ids[allocation.slotKey] = allocation.id;
          for (const [alias, slot] of Object.entries(this.identityAliases)) if (slot === allocation.slotKey) this.memory.ids[alias] = allocation.id;
        }
        if (!this.memory.allocatedKeys.includes(req.allocationKey as Id)) this.memory.allocatedKeys.push(req.allocationKey as Id);
        break;
      }
      case 'checkpoint_start_advance': {
        // §6.1 正常输入路径：驱动自己发起的 advance 留下与身份绑定的原文，
        // 行动读它（不需要 context 回包）；advanceId 变化后自动失效。
        const startData = data as { advanceId?: Id; inputId?: Id };
        const sentText = req.inputText;
        this.memory.playerAdvance = startData.advanceId && startData.inputId && typeof sentText === 'string'
          ? { advanceId: startData.advanceId, inputId: startData.inputId, text: sentText }
          : null;
        this.memory.playerInput = null;
        break;
      }
      case 'checkpoint_discover_group': {
        const actor = req.initiatorId as Id;
        if (!this.memory.groupActors.includes(actor)) this.memory.groupActors.push(actor);
        this.memory.sources = [{ sourceId: actor, actionText: req.actionText as string, targetsExtended: false, pendingTargets: [], rolled: [] }];
        this.memory.groupActions = [{ memberId: actor, actionText: req.actionText as string, rolls: [] }];
        this.memory.updatesCalls = [];
        this.memory.updatesApplied = 0;
        this.memory.updatesPendingRefs = [];
        this.memory.lastResults = null;
        break;
      }
      case 'checkpoint_extend_group': {
        const current = sources[0];
        if (!current || req.sourceId !== current.sourceId) throw new Error('Extend response without matching source');
        if (Array.isArray(req.targets)) {
          current.targetsExtended = true;
          // Keys were resolved from the allocated-id map before this call;
          // the dice rule is the program constant (§6.2), never model-declared.
          current.pendingTargets = asAsciiTargets(req.targets as { targetId: Id; triggerKey: Id }[]);
          this.memory.lastTargets = null;
        } else if (req.admittedMember && typeof req.admittedMember === 'object') {
          const member = req.admittedMember as { memberId: Id; actionText?: string | null; rollRefs: { rollId: Id }[] };
          const entry = current.rolled.find((r) => r.rollId === member.rollRefs[0]?.rollId);
          if (entry) entry.reacted = true;
          if (!this.memory.groupActors.includes(member.memberId)) this.memory.groupActors.push(member.memberId); // the member has acted in this point
          sources.unshift({ sourceId: member.memberId, actionText: member.actionText ?? '', targetsExtended: false, pendingTargets: [], rolled: [] });
          this.memory.groupActions.unshift({ memberId: member.memberId, actionText: member.actionText ?? '', rolls: [] });
        }
        this.retireFinishedSources();
        break;
      }
      case 'create_rolls': {
        const current = sources[0];
        const spec = (req.rolls as { sourceId: Id; targetId: Id; triggerKey: Id; ruleVersion: RollRule['ruleVersion']; target: number }[])[0];
        const outcome = (data as { rolls: { rollId: Id; result: number; eligible: boolean; admitted: boolean }[] }).rolls[0];
        if (!current || current.sourceId !== spec.sourceId || !outcome) throw new Error('Roll outcome without matching source');
        const pending = current.pendingTargets.find((t) => t.targetId === spec.targetId);
        current.pendingTargets = current.pendingTargets.filter((t) => t !== pending);
        current.rolled.push({ targetId: spec.targetId, triggerKey: spec.triggerKey, rule: pending?.rule ?? { ruleVersion: spec.ruleVersion, target: spec.target }, rollId: outcome.rollId, admitted: outcome.admitted, reacted: false });
        // 判定留存（§7.1 results 输入）：未准入与已行动目标都带结果。
        const frozenMember = this.memory.groupActions.find((member) => member.memberId === spec.sourceId);
        frozenMember?.rolls.push({ targetId: spec.targetId, rollId: outcome.rollId, result: outcome.result, eligible: outcome.eligible, admitted: outcome.admitted });
        this.retireFinishedSources(); // a final not-admitted roll can finish the source too
        break;
      }
      case 'checkpoint_stage_unit':
        this.memory.staged.push({ groupId: req.groupId as Id, actorIds: (req.candidates as { actorIds: Id[] }).actorIds, candidates: req.candidates as never, results: req.results as Record<Id, string> });
        this.memory.lastResults = null;
        this.memory.updatesCalls = [];
        this.memory.updatesApplied = 0;
        this.memory.updatesPendingRefs = []; // 未决引用已随结算批次成为状态事实
        this.memory.groupActions = []; // 本组冻结行动已随暂存批次结算
        this.memory.commitPayload = null;
        break;
      case 'checkpoint_stage_time_scan':
        // The scan candidate joins later previews' settlement lists, but a
        // named-group member it is not: commit keeps its plain groups.
        this.memory.stagedTimeScan = structuredClone((req.candidates ?? null) as SettlementGroup | null);
        this.memory.lastResults = null;
        this.memory.updatesCalls = [];
        this.memory.updatesApplied = 0;
        this.memory.updatesPendingRefs = []; // 未决引用已随结算批次成为状态事实
        this.memory.groupActions = []; // 本组冻结行动已随暂存批次结算
        this.memory.commitPayload = null;
        break;
      case 'checkpoint_record_skip': {
        const slotActorId = req.slotActorId as Id;
        const plannedActor = this.memory.plan?.[this.memory.planIndex]?.actorIds.includes(slotActorId);
        if (plannedActor && !this.memory.groupActors.includes(slotActorId)) this.memory.groupActors.push(slotActorId);
        break;
      }
      case 'checkpoint_prepare_successor':
        this.memory.prepareSuccessor = false;
        this.memory.successorTime = null;
        break;
      case 'commit_point': {
        this.memory.planIndex++;
        this.memory.staged = [];
        this.memory.stagedTimeScan = null;
        this.memory.groupActors = [];
        this.memory.updatesCalls = [];
        this.memory.updatesApplied = 0;
        this.memory.updatesPendingRefs = [];
        this.memory.groupActions = [];
        this.memory.commitPayload = null;
        const head = this.state.world?.head;
        if (head) this.memory.narration = { pointId: head.pointId, claim: null, input: initialNarrationAssembly(head.pointId) };
        break;
      }
      case 'get_state': {
        // Narration assembly routing (§7.1): the TARGET point's read fills
        // after + the point's own saved record; the PREDECESSOR read fills
        // before. A served response missing the required record fields marks
        // the read capability incomplete — generation stops, no empty-delta
        // assumption. Reads for unrelated points are ignored here.
        const narration = this.memory.narration;
        if (!narration) break;
        const payload = data as {
          pointId?: Id; state?: unknown; stateDigest?: unknown;
          previousPointId?: Id | null; timeAdvance?: unknown; entityDeltas?: unknown;
        };
        if (payload.pointId === narration.input.pointId) {
          if (payload.previousPointId === undefined || payload.timeAdvance === undefined || payload.entityDeltas === undefined || payload.state === undefined) {
            narration.input.readIncomplete = true;
            break;
          }
          narration.input.after = structuredClone(payload.state) as never;
          narration.input.previousPointId = payload.previousPointId;
          narration.input.delta = structuredClone({ timeAdvance: payload.timeAdvance, entityDeltas: payload.entityDeltas }) as never;
        } else if (payload.pointId != null && payload.pointId === narration.input.previousPointId) {
          if (payload.state === undefined) {
            narration.input.readIncomplete = true;
            break;
          }
          narration.input.before = structuredClone(payload.state) as never;
        } else {
          // 返回点与请求不符：服务端/read 标本错位——明确停止，忽略会造成
          // 同一缺失读反复请求。
          narration.input.readIncomplete = true;
        }
        break;
      }
      case 'narration_claim': {
        const responseReplayed = (response as unknown as { replayed?: boolean }).replayed === true;
        const summary = data as unknown as CurrentClaim & { claimToken?: Id };
        const pointId = req.pointId as Id;
        if (!responseReplayed && summary.claimToken) {
          if (!this.memory.narration || this.memory.narration.pointId !== pointId) {
            this.memory.narration = { pointId, claim: null, input: initialNarrationAssembly(pointId) };
          }
          this.memory.narration.claim = { claimToken: summary.claimToken, generation: summary.generation, issuedAtEpochMilli: summary.issuedAtEpochMilli };
        }
        break;
      }
      case 'narration_submit':
        this.memory.narration = null;
        break;
      case 'round_conclusion_conclude': {
        this.memory.continuation = null;
        const kind = (data as { kind?: string }).kind;
        if (kind === 'continue') {
          this.memory.plan = null;
          this.memory.planIndex = 0;
        } else if (kind === 'handback') {
          this.clearRoundWork();
        }
        break;
      }
      case 'round_conclusion_cancel':
        this.clearRoundWork();
        break;
      case 'checkpoint_pause':
        // The triggering command owns the origin. An external pause is
        // still external when the local numeric budget happens to be spent.
        this.memory.localPause = this.stepCommand?.kind === 'budget_exhausted'
          || (this.stepCommand?.kind !== 'pause' && this.memory.budget.max != null && this.memory.budget.used >= this.memory.budget.max);
        break;
      case 'checkpoint_resume':
        this.memory.localPause = false;
        break;
      case 'lease_acquire':
        this.memory.leaseToken = (data as unknown as { leaseToken: Id }).leaseToken;
        if (this.state.world) this.state.world.lease = { fenceEpoch: (data as unknown as { fenceEpoch: number }).fenceEpoch, expiresAtEpochMilli: (data as unknown as { expiresAtEpochMilli: number }).expiresAtEpochMilli };
        break;
      default:
        break;
    }
  }

  private clearRoundWork(): void {
    Object.assign(this.memory, {
      playerInput: null, plan: null, planIndex: 0, prepareSuccessor: false,
      workingState: null, sources: [], staged: [], stagedTimeScan: null,
      groupActors: [], groupActions: [], lastModel: null, lastTargets: null, lastResults: null, updatesCalls: [], updatesApplied: 0, updatesPreviewSkipped: 0, updatesPendingRefs: [],
      continuation: null, successorTime: null, commitPayload: null, narration: null,
    });
  }
}
