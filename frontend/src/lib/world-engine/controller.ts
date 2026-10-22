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
  errorReaction, scheduleNext, workingStateKey,
  type ControllerMemory, type Decision, type HarnessCommand, type ModelTask, type PlannedPoint, type RollRule, type SourceAnalysis, type UpdatesCall,
} from './schedule';
import type {
  Conclusion, ControlState, CurrentClaim, Id, InitialTemplate, Json, PointWork, RequestMap,
  TimeAdvance, WorldContext, WorldOperation,
} from './types';

export interface WorldModelPort { generate(task: ModelTask, key: string, input: Json): Promise<Json> }
export interface ControllerIo { transport: WorldTransport; model: WorldModelPort }
export interface DriverOptions { retryLimit?: number }

export type DriverStatus =
  | { kind: 'await'; reason: string }
  | { kind: 'stop'; reason: string }
  | { kind: 'error'; detail: string };

interface ServedState { world: WorldContext | null; control: ControlState; work: PointWork | null }

const INITIAL_CONTROL: ControlState = {
  phase: 'select_actor', paused: false, revision: 0,
  gate: { status: 'none', generation: null, issuedAtEpochMilli: null, expiresAtEpochMilli: null },
  blockedReasons: [], canCompute: true,
};

export function initialMemory(prefix: string, holderId: string): ControllerMemory {
  return {
    requestId: `${prefix}_0`, leaseToken: null, holderId, ids: {}, allocPlan: null, playerInput: null,
    plan: null, planIndex: 0, prepareSuccessor: false, localPause: false, budget: { used: 0, max: null },
    narration: null, workingState: null, sources: [], staged: [], groupActors: [], lastModel: null, lastResults: null,
    updatesStages: [], updatesCalls: [],
    continuation: null, successorTime: null, commitPayload: null, initialTemplate: null,
  };
}

function asAsciiTargets(targets: { targetId: Id; triggerKey: Id }[], rules: Record<Id, RollRule>) {
  return [...targets].sort((a, b) => (a.targetId < b.targetId ? -1 : 1)).map((t) => ({ targetId: t.targetId, triggerKey: t.triggerKey, rule: rules[t.triggerKey] ?? { ruleVersion: 'reaction-fixture-v1' as const, target: 11 } }));
}

function sourceComplete(source: SourceAnalysis): boolean {
  return source.targetsExtended && source.pendingTargets.length === 0 && source.rolled.every((r) => r.reacted || r.admitted !== true);
}

type CallOutcome = { ok: true; response: unknown } | { ok: false; terminal?: DriverStatus };

export class ControllerDriver {
  private state: ServedState;
  private memory: ControllerMemory;
  private command: HarnessCommand | null = null;
  private requestCounter = 0;
  private readonly retryLimit: number;

  constructor(private io: ControllerIo, memory: ControllerMemory, state?: Partial<ServedState>, options?: DriverOptions) {
    this.memory = memory;
    this.state = { world: null, control: INITIAL_CONTROL, work: null, ...state };
    this.retryLimit = options?.retryLimit ?? 3;
  }

  getMemory(): ControllerMemory { return structuredClone(this.memory); }
  getRequestCounter(): number { return this.requestCounter; }

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

  /** Executes exactly one decision. Returns a terminal status, or undefined. */
  async step(): Promise<DriverStatus | undefined> {
    const command = this.command;
    if (command?.kind === 'player_input') this.command = null; // consumed via memory.playerInput
    const decision = scheduleNext({ world: this.state.world, control: this.state.control, work: this.state.work, memory: this.memory, command: command && command.kind !== 'player_input' ? command : undefined });
    switch (decision.kind) {
      case 'await_command':
        this.command = null;
        return { kind: 'await', reason: decision.reason };
      case 'stop':
        this.command = null;
        return { kind: 'stop', reason: decision.reason };
      case 'model': {
        this.command = null;
        const output = await this.io.model.generate(decision.task, decision.key, decision.input);
        this.consumeModelOutput(decision, output);
        return undefined;
      }
      case 'read_working_state':
        this.command = null;
        return this.preview();
      case 'transport': {
        const executesCommand = command != null && this.commandOperation(command) === decision.operation;
        const outcome = await this.call(decision.operation, decision.request, decision.scope);
        if (outcome.ok) {
          if (!command || executesCommand) this.command = null; // a diverted command (e.g. pause after lease_acquire) survives
          this.adoptSuccess(decision.operation, decision.request, outcome.response);
          this.memory.lastModel = null;
          this.nextRequestId();
          return undefined;
        }
        return outcome.terminal; // definitive rejection: the command survives; state was refreshed, re-schedule
      }
    }
  }

  /** Single funnel for every transport call. Retries timeouts and
   * request_in_progress with the original payload up to retryLimit;
   * definitive rejections retire the requestId, run the clientAction
   * follow-up, and make the caller re-schedule. */
  private async call(operation: WorldOperation, request: unknown, scope: { worldId?: Id; pointId?: Id }): Promise<CallOutcome> {
    let retries = 0;
    for (;;) {
      try {
        const response = await this.io.transport.execute(operation, request as never, scope);
        return { ok: true, response };
      } catch (error) {
        if (error instanceof WorldTimeoutError) {
          if (++retries > this.retryLimit) return { ok: false, terminal: { kind: 'error', detail: `retry limit exceeded on ${operation} (timeout)` } };
          continue;
        }
        if (!(error instanceof WorldApiError)) throw error;
        const reaction = errorReaction(error.response);
        this.adoptState(error.response);
        if (reaction.followup === 'retry_same_request') {
          if (++retries > this.retryLimit) return { ok: false, terminal: { kind: 'error', detail: `retry limit exceeded on ${operation} (${error.response.error.code})` } };
          continue;
        }
        this.nextRequestId();
        const terminal = await this.applyErrorFollowup(reaction.followup, error.response.error.code);
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
    const request: RequestMap['preview_point'] = {
      protocolVersion: 2, worldId: world.worldId,
      advanceId: world.advance.advanceId!, roundId: world.activeRoundId ?? world.round?.roundId ?? '',
      pointId: work.pointId, expectedPointId: world.head.pointId, expectedVersion: world.head.version,
      expectedCheckpointRevision: control.revision, timeAdvance: work.timeAdvance,
      settlementGroups: this.memory.staged.map((s) => s.candidates),
    };
    const outcome = await this.call('preview_point', request, { worldId: world.worldId });
    if (!outcome.ok) return outcome.terminal;
    this.adoptState(outcome.response);
    const data = (outcome.response as unknown as { data: { workingState: unknown; pointProjection: unknown } }).data;
    this.memory.workingState = { key: workingStateKey(this.state.work!), state: structuredClone(data.workingState) as never };
    this.memory.commitPayload = { point: structuredClone(data.pointProjection) as never, settlementGroups: this.memory.staged.map((s) => s.candidates) };
    this.memory.lastModel = null;
    this.nextRequestId();
    return undefined;
  }

  private async applyErrorFollowup(followup: ReturnType<typeof errorReaction>['followup'], code: string): Promise<DriverStatus | undefined> {
    const world = this.state.world;
    switch (followup) {
      case 'retry_same_request':
        return undefined;
      case 'refresh_context': {
        const outcome = await this.call('get_context', {}, { worldId: world?.worldId });
        if (!outcome.ok) return outcome.terminal;
        this.adoptState(outcome.response);
        this.memory.lastModel = null;
        this.nextRequestId();
        return undefined;
      }
      case 'lease_acquire': {
        const request = { protocolVersion: 2 as const, requestId: this.memory.requestId, worldId: world?.worldId ?? '', holderId: this.memory.holderId };
        const outcome = await this.call('lease_acquire', request, { worldId: world?.worldId });
        if (!outcome.ok) return outcome.terminal;
        this.adoptSuccess('lease_acquire', request, outcome.response);
        this.memory.lastModel = null;
        this.nextRequestId();
        return undefined;
      }
      case 'finish_own_narration': {
        const pointId = world?.head.pointId;
        if (world && pointId) {
          const input = this.memory.narration?.pointId === pointId ? this.memory.narration.input : { pointId, stateDigest: world.head.stateDigest };
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
        const outcome = await this.call('checkpoint_pause', request, { worldId: world?.worldId });
        if (!outcome.ok) return outcome.terminal;
        return { kind: 'stop', reason: `pause_and_stop:${code}` };
      }
      case 'await_control':
        this.command = null;
        return { kind: 'await', reason: 'resolve_gate' };
      case 'stop':
        this.command = null;
        return { kind: 'stop', reason: `fix_request:${code}` };
    }
  }

  // ---------- response adoption ----------

  private adoptState(response: unknown): void {
    const envelope = response as { world?: WorldContext | null; control?: ControlState; work?: PointWork | null };
    if (envelope.world !== undefined) this.state.world = envelope.world;
    if (envelope.control !== undefined) this.state.control = envelope.control;
    if (envelope.work !== undefined) this.state.work = envelope.work;
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
      case 'allocate_ids':
        for (const allocation of (data as { allocations: { slotKey: Id; id: Id }[] }).allocations ?? []) this.memory.ids[allocation.slotKey] = allocation.id;
        break;
      case 'checkpoint_start_advance':
        this.memory.playerInput = null;
        break;
      case 'checkpoint_discover_group': {
        const actor = req.initiatorId as Id;
        if (!this.memory.groupActors.includes(actor)) this.memory.groupActors.push(actor);
        this.memory.sources = [{ sourceId: actor, actionText: req.actionText as string, targetsExtended: false, pendingTargets: [], rolled: [] }];
        this.memory.updatesCalls = [];
        this.memory.lastResults = null;
        break;
      }
      case 'checkpoint_extend_group': {
        const current = sources[0];
        if (!current || req.sourceId !== current.sourceId) throw new Error('Extend response without matching source');
        if (Array.isArray(req.targets)) {
          const declared = this.memory.lastModel?.task === 'targets' ? (this.memory.lastModel.output as { targets: { triggerKey: Id; ruleVersion: RollRule['ruleVersion']; target: number }[] }) : { targets: [] };
          const rules: Record<Id, RollRule> = {};
          for (const t of declared.targets) rules[t.triggerKey] = { ruleVersion: t.ruleVersion, target: t.target };
          current.targetsExtended = true;
          current.pendingTargets = asAsciiTargets(req.targets as { targetId: Id; triggerKey: Id }[], rules);
        } else if (req.admittedMember && typeof req.admittedMember === 'object') {
          const member = req.admittedMember as { memberId: Id; actionText?: string | null; rollRefs: { rollId: Id }[] };
          const entry = current.rolled.find((r) => r.rollId === member.rollRefs[0]?.rollId);
          if (entry) entry.reacted = true;
          if (!this.memory.groupActors.includes(member.memberId)) this.memory.groupActors.push(member.memberId); // the member has acted in this point
          sources.unshift({ sourceId: member.memberId, actionText: member.actionText ?? '', targetsExtended: false, pendingTargets: [], rolled: [] });
        }
        this.retireFinishedSources();
        break;
      }
      case 'create_rolls': {
        const current = sources[0];
        const spec = (req.rolls as { sourceId: Id; targetId: Id; triggerKey: Id; ruleVersion: RollRule['ruleVersion']; target: number }[])[0];
        const outcome = (data as { rolls: { rollId: Id; admitted: boolean }[] }).rolls[0];
        if (!current || current.sourceId !== spec.sourceId || !outcome) throw new Error('Roll outcome without matching source');
        const pending = current.pendingTargets.find((t) => t.targetId === spec.targetId);
        current.pendingTargets = current.pendingTargets.filter((t) => t !== pending);
        current.rolled.push({ targetId: spec.targetId, triggerKey: spec.triggerKey, rule: pending?.rule ?? { ruleVersion: spec.ruleVersion, target: spec.target }, rollId: outcome.rollId, admitted: outcome.admitted, reacted: false });
        this.retireFinishedSources(); // a final not-admitted roll can finish the source too
        break;
      }
      case 'checkpoint_stage_unit':
        this.memory.staged.push({ groupId: req.groupId as Id, actorIds: (req.candidates as { actorIds: Id[] }).actorIds, candidates: req.candidates as never, results: req.results as Record<Id, string> });
        this.memory.lastResults = null;
        this.memory.updatesCalls = [];
        this.memory.commitPayload = null;
        break;
      case 'checkpoint_stage_time_scan':
        this.memory.lastResults = null;
        this.memory.updatesCalls = [];
        this.memory.commitPayload = null;
        break;
      case 'checkpoint_record_skip': {
        const slotActorId = req.slotActorId as Id;
        const plannedActor = this.memory.plan?.[this.memory.planIndex]?.actorIds.includes(slotActorId);
        if (plannedActor && !this.memory.groupActors.includes(slotActorId)) this.memory.groupActors.push(slotActorId);
        break;
      }
      case 'commit_point': {
        this.memory.planIndex++;
        this.memory.staged = [];
        this.memory.groupActors = [];
        this.memory.updatesCalls = [];
        this.memory.commitPayload = null;
        const head = this.state.world?.head;
        if (head) this.memory.narration = { pointId: head.pointId, claim: null, input: { pointId: head.pointId, stateDigest: head.stateDigest } };
        break;
      }
      case 'narration_claim': {
        const responseReplayed = (response as unknown as { replayed?: boolean }).replayed === true;
        const summary = data as unknown as CurrentClaim & { claimToken?: Id };
        const pointId = req.pointId as Id;
        if (!responseReplayed && summary.claimToken) {
          if (!this.memory.narration || this.memory.narration.pointId !== pointId) {
            this.memory.narration = { pointId, claim: null, input: { pointId, stateDigest: this.state.world?.head.stateDigest ?? '' } };
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
        }
        break;
      }
      case 'checkpoint_pause':
        if (this.memory.budget.max != null && this.memory.budget.used >= this.memory.budget.max) this.memory.localPause = true;
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
}
