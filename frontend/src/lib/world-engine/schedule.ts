/** B1 pure scheduler: derives the next controller decision from the served
 * context/work snapshot, controller memory and one harness command. Reads
 * memory, never mutates it — the driver applies responses and model outputs.
 * No world apply, dice, canonical digests or ID generation here; requests
 * bind only to served state and scenario-seeded/preallocated identities. */
import contract from '../../../../design/world-protocol/v2/api-contract.json';
import type {
  ClientAction, Conclusion, ControlState, CurrentClaim, EntityDelta, ErrorCode, ErrorResponse, Id,
  InitialTemplate, Json, PointWork, RequestMap, RollRef, RollSpec, Scope, SettlementGroup,
  TimeAdvance, TimelinePoint, WorldContext, WorldOperation, WorldState,
} from './types';

export type ModelTask = 'action' | 'targets' | 'reaction' | 'results' | 'updates' | 'continuation' | 'narration' | 'initial' | 'time' | 'pointPlan';
export const updateStages = ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity'] as const;
export type UpdatesStage = typeof updateStages[number];

/** One planned point: scenario segmentation with an explicit boundary — the
 * controller seals a point once every actorId here has been staged (or the
 * round members are skipped, or the empty point ran its time scan). */
export interface PlannedPoint { pointId: Id; kind: 'normal' | 'instant' | 'linked'; timeAdvance: TimeAdvance; actorIds: Id[] }
export interface RollRule { ruleVersion: RollSpec['ruleVersion']; target: number }
export interface PendingTarget { targetId: Id; triggerKey: Id; rule: RollRule }

/** DFS entry per analysed source of the open group (index 0 = current). */
export interface SourceAnalysis {
  sourceId: Id;
  actionText: string;
  targetsExtended: boolean;
  pendingTargets: PendingTarget[];
  rolled: { targetId: Id; triggerKey: Id; rule: RollRule; rollId: Id | null; admitted: boolean | null; reacted: boolean }[];
}

export interface StagedUnit { groupId: Id; actorIds: Id[]; candidates: SettlementGroup; results: Record<Id, string> }

export interface ModelResolution { task: ModelTask; key: string; output: Json }

export type HarnessCommand =
  | { kind: 'player_input' }
  | { kind: 'pause' }
  | { kind: 'resume' }
  | { kind: 'budget_exhausted' }
  | { kind: 'cancel'; reason: string };

export interface ControllerMemory {
  /** Driver-owned factory value: stamped into every emitted write request.
   * Retried operations reuse it; definitive rejections retire it. */
  requestId: Id;
  /** Lease token is client-held (the context only echoes fenceEpoch). */
  leaseToken: Id | null;
  holderId: Id;
  /** Scenario seed/slot map filled from allocate_ids responses and input
   * seeds ('advance', 'input', 'round', 'group:<actor>', 'successor', …). */
  ids: Record<string, Id>;
  allocPlan: { allocationKey: Id; slots: { slotKey: Id; kind: 'advance' | 'input' | 'round' | 'group' | 'task' | 'change' | 'point' | 'trigger'; scope?: Id | null }[] } | null;
  playerInput: { text: string; order: Id[] } | null;
  plan: PlannedPoint[] | null;
  planIndex: number;
  /** Set when the scenario pre-declares a successor binding (T08 path). */
  prepareSuccessor: boolean;
  localPause: boolean;
  budget: { used: number; max: number | null };
  narration: { pointId: Id; claim: CurrentClaim | null; input: Json } | null;
  workingState: { key: string; state: WorldState } | null;
  sources: SourceAnalysis[];
  staged: StagedUnit[];
  groupActors: Id[];
  lastModel: ModelResolution | null;
  lastResults: Record<Id, string> | null;
  /** Scenario-declared updates split; empty = one merged call. */
  updatesStages: UpdatesStage[];
  /** Driver accumulates one UpdatesCall per split stage here. */
  updatesCalls: UpdatesCall[];
  continuation: Conclusion | null;
  successorTime: TimeAdvance | null;
  commitPayload: { point: TimelinePoint; settlementGroups: SettlementGroup[] } | null;
  initialTemplate: InitialTemplate | null;
}

export type Decision =
  | { kind: 'transport'; operation: WorldOperation; request: RequestMap[WorldOperation]; scope: Scope }
  | { kind: 'read_working_state' }
  | { kind: 'model'; task: ModelTask; key: string; input: Json }
  | { kind: 'await_command'; reason: string }
  | { kind: 'stop'; reason: string };

export interface ScheduleView { world: WorldContext | null; control: ControlState; work: PointWork | null; memory: ControllerMemory; command?: HarnessCommand }

const STATE_COMPUTATION_TASKS: ModelTask[] = ['action', 'targets', 'reaction', 'results', 'updates', 'continuation'];

/** Semantic working-state cache key: only inputs of the working state may
 * invalidate it. checkpointRevision is deliberately not part of the key —
 * record_skip and pause/resume bump the revision without touching state.
 * timeScanComplete IS part of it: stage_time_scan rewrites tasks/personality/
 * sanity without touching settledUnitIds (T03 s3). */
export function workingStateKey(work: PointWork): string {
  return JSON.stringify([work.pointId, work.baseline.version, work.timeAdvance, work.working.settledUnitIds, work.timeScanComplete]);
}

function freshState(memory: ControllerMemory, work: PointWork): WorldState | null {
  return memory.workingState && memory.workingState.key === workingStateKey(work) ? memory.workingState.state : null;
}

/** Typed snapshots cross the model-port boundary as plain JSON. */
function asJson(value: unknown): Json {
  return JSON.parse(JSON.stringify(value)) as Json;
}

// ---------- error routing: the 18-code catalog comes from the frozen contract ----------

export interface ErrorCatalogEntry { httpStatus: number; retryable: boolean; clientAction: ClientAction }
export const errorCatalog = contract.errorCodes as unknown as Record<ErrorCode, ErrorCatalogEntry>;

export type ErrorFollowup =
  | 'retry_same_request'
  | 'lease_acquire'
  | 'refresh_context'
  | 'finish_own_narration'
  | 'pause_and_stop'
  | 'stop'
  | 'await_control';

/** Definitive rejections retire the operation: the driver builds a NEW
 * requestId for the follow-up business operation. Only request_in_progress
 * (and driver-observed timeouts) reuse the original requestId and payload. */
export function errorReaction(error: ErrorResponse): { clientAction: ClientAction; reuseRequestId: boolean; followup: ErrorFollowup } {
  const entry = errorCatalog[error.error.code];
  if (!entry) throw new Error(`Unknown error code: ${error.error.code}`);
  if (entry.clientAction !== error.error.clientAction || entry.httpStatus !== error.error.httpStatus || entry.retryable !== error.error.retryable) {
    throw new Error('ErrorResponse contradicts frozen error catalog');
  }
  const byAction: Record<ClientAction, ErrorFollowup> = {
    retry_same_request: 'retry_same_request',
    reacquire_lease: 'lease_acquire',
    refresh_context: 'refresh_context',
    wait_narration: 'finish_own_narration',
    regenerate_narration: 'finish_own_narration',
    resolve_gate: 'await_control',
    pause: 'pause_and_stop',
    fix_request: 'stop',
    none: 'stop',
  };
  return { clientAction: entry.clientAction, reuseRequestId: entry.clientAction === 'retry_same_request', followup: byAction[entry.clientAction] };
}

// ---------- updates stages: dangling-reference guard only ----------

export type UpdatesCall = { stage: UpdatesStage; changes: Record<Id, Partial<EntityDelta>> };

/** tasksAchieved entries and subtask parents are references; only
 * subtasksAdded objects produce task identities. */
function taskRefs(delta: Partial<EntityDelta>): Id[] {
  return [...(delta.tasksAchieved ?? []), ...(delta.subtasksAdded ?? []).map((t) => t.parentTaskId).filter((v): v is Id => v != null)];
}
function changeRefs(delta: Partial<EntityDelta>): Id[] {
  return [...(delta.appearanceChanges ?? []), ...(delta.personalityChanges ?? [])].flatMap((c) => c.supersedes ?? []);
}
function producedTasks(stages: UpdatesCall[]): Set<Id> {
  const ids = new Set<Id>();
  for (const call of stages) for (const delta of Object.values(call.changes)) {
    for (const task of delta.subtasksAdded ?? []) ids.add(task.id);
  }
  return ids;
}
function producedChanges(stages: UpdatesCall[]): Set<Id> {
  const ids = new Set<Id>();
  for (const call of stages) for (const delta of Object.values(call.changes)) {
    for (const change of [...(delta.appearanceChanges ?? []), ...(delta.personalityChanges ?? [])]) ids.add(change.id);
  }
  return ids;
}

/** Rejects only dangling references: a referenced task/change that appears in
 * neither the input state nor ANY stage output. Cross-stage overlap the
 * server accepts stays legal — T03-collapse puts v13 into tasksAchieved and
 * subtasksAdded (pending) and the final delta collapses to subtasksAdded. */
/** Strict canonical stage order; out-of-order or duplicate splits rejected. */
export function checkUpdatesStages(input: { taskIds: ReadonlySet<Id>; changeIds: ReadonlySet<Id> }, stages: UpdatesCall[]): { ok: true; merged: Record<Id, EntityDelta> } | { ok: false; dangling: { stage: UpdatesStage; entity: Id; kind: 'task' | 'change'; id: Id }[] } {
  const tasks = producedTasks(stages);
  const changes = producedChanges(stages);
  let lastIndex = -1;
  const dangling: { stage: UpdatesStage; entity: Id; kind: 'task' | 'change'; id: Id }[] = [];
  for (const call of stages) {
    const index = updateStages.indexOf(call.stage);
    if (index < 0 || index <= lastIndex) throw new Error(`Out-of-order/duplicate updates stage: ${call.stage}`);
    lastIndex = index;
    for (const [entity, delta] of Object.entries(call.changes)) {
      for (const id of taskRefs(delta)) if (!input.taskIds.has(id) && !tasks.has(id)) dangling.push({ stage: call.stage, entity, kind: 'task', id });
      for (const id of changeRefs(delta)) if (!input.changeIds.has(id) && !changes.has(id)) dangling.push({ stage: call.stage, entity, kind: 'change', id });
    }
  }
  if (dangling.length) return { ok: false, dangling };
  const merged: Record<Id, EntityDelta> = {};
  for (const call of stages) for (const [entity, delta] of Object.entries(call.changes)) {
    const target = merged[entity] ?? (merged[entity] = { entityId: entity });
    if (delta.positionSet !== undefined) target.positionSet = delta.positionSet;
    if (delta.appearanceChanges !== undefined) target.appearanceChanges = [...(target.appearanceChanges ?? []), ...delta.appearanceChanges];
    if (delta.personalityChanges !== undefined) target.personalityChanges = [...(target.personalityChanges ?? []), ...delta.personalityChanges];
    if (delta.sanitySet !== undefined) target.sanitySet = delta.sanitySet;
    if (delta.tasksAchieved !== undefined) target.tasksAchieved = [...(target.tasksAchieved ?? []), ...delta.tasksAchieved];
    if (delta.subtasksAdded !== undefined) target.subtasksAdded = [...(target.subtasksAdded ?? []), ...delta.subtasksAdded];
  }
  return { ok: true, merged };
}

// ---------- shared request bindings ----------

interface WriteBind { worldId: Id; leaseToken: Id; fenceEpoch: number; expectedPointId: Id; expectedVersion: number; expectedCheckpointRevision: number }

function writeBind(view: ScheduleView): WriteBind {
  const { world, control, memory } = view;
  if (!world || !world.lease || !memory.leaseToken) throw new Error('Write binding without lease');
  return {
    worldId: world.worldId, leaseToken: memory.leaseToken, fenceEpoch: world.lease.fenceEpoch,
    expectedPointId: world.head.pointId, expectedVersion: world.head.version, expectedCheckpointRevision: control.revision,
  };
}

function worldScope(view: ScheduleView): Scope {
  return { worldId: view.world?.worldId };
}

function narrationScope(view: ScheduleView): Scope {
  return { worldId: view.world!.worldId, pointId: view.world!.head.pointId };
}

function roundIdOf(world: WorldContext): Id {
  return world.activeRoundId ?? world.round?.roundId ?? '';
}

function modelBlocked(view: ScheduleView, task: ModelTask): Decision | null {
  // Narration, pointPlan and time are never budget- or compute-blocked: the
  // narration pipeline must run through pause (T05) and a budget pause must
  // not deadlock a pending narration.
  if (!STATE_COMPUTATION_TASKS.includes(task)) return null;
  if (!view.control.canCompute) return { kind: 'await_command', reason: 'phase_not_computable' };
  const { max, used } = view.memory.budget;
  if (max != null && used >= max) {
    const bind = writeBind(view);
    return {
      kind: 'transport', operation: 'checkpoint_pause',
      request: { protocolVersion: 2, requestId: view.memory.requestId, ...bind, operation: 'pause' } as RequestMap['checkpoint_pause'],
      scope: worldScope(view),
    };
  }
  return null;
}

// ---------- entry ----------

export function scheduleNext(view: ScheduleView): Decision {
  const { world, control, work, memory } = view;
  const command = view.command;
  if (command && command.kind !== 'player_input') return commandDecision(view, command);
  if (!world) {
    if (memory.initialTemplate) {
      return { kind: 'transport', operation: 'create_world', request: { protocolVersion: 2, requestId: memory.requestId, initial: memory.initialTemplate }, scope: {} };
    }
    return { kind: 'model', task: 'initial', key: 'initial', input: null };
  }
  // Narration first: it runs through pause (T05 s7/s8), pending gates and the
  // complete phase (T01 s1–s3: phase=complete, gate=pending, narration pending).
  const narration = narrationDecision(view);
  if (narration) return narration;

  if (!world.lease || !memory.leaseToken) {
    return { kind: 'transport', operation: 'lease_acquire', request: { protocolVersion: 2, requestId: memory.requestId, worldId: world.worldId, holderId: memory.holderId }, scope: worldScope(view) };
  }
  if (control.gate.status !== 'none') return { kind: 'await_command', reason: `gate_${control.gate.status}` };
  if (control.paused) return { kind: 'await_command', reason: memory.localPause ? 'local_budget_pause' : 'paused_externally' };
  // complete = no settlement work; starting a pending advance stays legal
  // (T01 s4–s5 allocate/start under phase=complete).
  if (control.phase === 'complete') {
    if (world.advance.advanceId === null && memory.playerInput) return advanceDecision(view);
    return { kind: 'stop', reason: 'world_complete' };
  }
  if (world.advance.advanceId === null) return advanceDecision(view);
  if (control.phase === 'assess_continuation') return continuationDecision(view);
  if (work) return pointDecision(view);
  return idlePointDecision(view);
}

function commandDecision(view: ScheduleView, command: Exclude<HarnessCommand, { kind: 'player_input' }>): Decision {
  if (!view.world?.lease || !view.memory.leaseToken) {
    return { kind: 'transport', operation: 'lease_acquire', request: { protocolVersion: 2, requestId: view.memory.requestId, worldId: view.world?.worldId ?? '', holderId: view.memory.holderId }, scope: worldScope(view) };
  }
  const bind = writeBind(view);
  const base = { protocolVersion: 2 as const, requestId: view.memory.requestId, ...bind };
  if (command.kind === 'pause' || command.kind === 'budget_exhausted') {
    return { kind: 'transport', operation: 'checkpoint_pause', request: { ...base, operation: 'pause' } as RequestMap['checkpoint_pause'], scope: worldScope(view) };
  }
  if (command.kind === 'resume') {
    return { kind: 'transport', operation: 'checkpoint_resume', request: { ...base, operation: 'resume' } as RequestMap['checkpoint_resume'], scope: worldScope(view) };
  }
  return {
    kind: 'transport', operation: 'round_conclusion_cancel',
    request: { ...base, operation: 'cancel', advanceId: view.world!.advance.advanceId!, roundId: roundIdOf(view.world!), cancelReason: command.reason } as RequestMap['round_conclusion_cancel'],
    scope: worldScope(view),
  };
}

// ---------- narration (root and every committed point) ----------

function narrationDecision(view: ScheduleView): Decision | null {
  const { world, memory } = view;
  if (!world) return null;
  const status = world.head.narrationStatus;
  if (status === 'ready') return null;
  const pointId = world.head.pointId;
  const narration = memory.narration && memory.narration.pointId === pointId ? memory.narration : null;
  if (!world.lease || !memory.leaseToken) {
    // Pending narration must not throw before the entry order reaches
    // lease_acquire; a held claim without a lease is a driver invariant break.
    if (narration?.claim) throw new Error('Narration claim survived lease loss');
    return null;
  }
  if (narration?.claim && memory.lastModel?.task === 'narration') {
    const bind = writeBind(view);
    const claim = narration.claim;
    const text = memory.lastModel.output;
    if (text != null && typeof text !== 'string') throw new Error('Narration output must be text or null');
    const outcome = text === null
      ? ({ outcome: 'failed', text: null, failureReason: 'model_failed' } as const)
      : ({ outcome: 'ready', text, failureReason: null } as const);
    return {
      kind: 'transport', operation: 'narration_submit',
      request: {
        protocolVersion: 2, requestId: memory.requestId, worldId: world.worldId, mode: 'head' as const,
        leaseToken: bind.leaseToken, fenceEpoch: bind.fenceEpoch, pointId,
        claimToken: claim.claimToken, generation: claim.generation, issuedAtEpochMilli: claim.issuedAtEpochMilli,
        ...outcome,
      } as RequestMap['narration_submit'],
      scope: narrationScope(view),
    };
  }
  if (!narration?.claim) {
    const bind = writeBind(view);
    return {
      kind: 'transport', operation: 'narration_claim',
      request: { protocolVersion: 2, requestId: memory.requestId, worldId: world.worldId, mode: 'head' as const, leaseToken: bind.leaseToken, fenceEpoch: bind.fenceEpoch, pointId, currentClaim: null },
      scope: narrationScope(view),
    };
  }
  const blocked = modelBlocked(view, 'narration');
  if (blocked) return blocked;
  return { kind: 'model', task: 'narration', key: pointId, input: narration.input };
}

// ---------- advance / continuation / between points ----------

function advanceDecision(view: ScheduleView): Decision {
  const { world, memory } = view;
  if (!memory.playerInput) return { kind: 'await_command', reason: 'player_input' };
  if (!memory.allocPlan || !memory.ids.advance || !memory.ids.input || !memory.ids.round) {
    if (!memory.allocPlan) throw new Error('Missing scenario allocation plan before start_advance');
    const bind = writeBind(view);
    return {
      kind: 'transport', operation: 'allocate_ids',
      request: { protocolVersion: 2, requestId: memory.requestId, worldId: world!.worldId, leaseToken: bind.leaseToken, fenceEpoch: bind.fenceEpoch, allocationKey: memory.allocPlan.allocationKey, slots: memory.allocPlan.slots },
      scope: worldScope(view),
    };
  }
  const bind = writeBind(view);
  return {
    kind: 'transport', operation: 'checkpoint_start_advance',
    request: {
      protocolVersion: 2, requestId: memory.requestId, ...bind,
      operation: 'start_advance', advanceId: memory.ids.advance, inputId: memory.ids.input, roundId: memory.ids.round,
      inputText: memory.playerInput.text, order: memory.playerInput.order,
    } as RequestMap['checkpoint_start_advance'],
    scope: worldScope(view),
  };
}

function continuationDecision(view: ScheduleView): Decision {
  const { world, memory } = view;
  if (memory.continuation) {
    const bind = writeBind(view);
    return {
      kind: 'transport', operation: 'round_conclusion_conclude',
      request: {
        protocolVersion: 2, requestId: memory.requestId, ...bind,
        operation: 'conclude', advanceId: world!.advance.advanceId!, roundId: roundIdOf(world!), conclusion: memory.continuation,
      } as RequestMap['round_conclusion_conclude'],
      scope: worldScope(view),
    };
  }
  const blocked = modelBlocked(view, 'continuation');
  if (blocked) return blocked;
  const state = view.work ? freshState(memory, view.work) : memory.workingState?.state ?? null;
  return { kind: 'model', task: 'continuation', key: roundIdOf(world!), input: { round: asJson(world!.round), head: asJson(world!.head), workingState: state ? asJson(state) : null } };
}

function idlePointDecision(view: ScheduleView): Decision {
  const { world, control, memory } = view;
  if (!memory.plan) {
    const blocked = modelBlocked(view, 'pointPlan');
    if (blocked) return blocked;
    return { kind: 'model', task: 'pointPlan', key: roundIdOf(world!), input: { round: world!.round, head: world!.head } };
  }
  if (memory.planIndex >= memory.plan.length) return { kind: 'await_command', reason: 'round_points_exhausted' };
  const planned = memory.plan[memory.planIndex];
  const bind = writeBind(view);
  return {
    kind: 'transport', operation: 'checkpoint_begin_point',
    request: {
      protocolVersion: 2, requestId: memory.requestId, ...bind,
      operation: 'begin_point', pointId: planned.pointId, kind: planned.kind, timeAdvance: planned.timeAdvance,
    } as RequestMap['checkpoint_begin_point'],
    scope: worldScope(view),
  };
}

// ---------- inside a point ----------

function pointDecision(view: ScheduleView): Decision {
  const { world, control, work, memory } = view;
  const pending = work!.pendingGroup;
  if (work!.sealed) {
    if (!memory.commitPayload) return { kind: 'await_command', reason: 'commit_payload_missing' };
    const bind = writeBind(view);
    return {
      kind: 'transport', operation: 'commit_point',
      request: {
        protocolVersion: 2, requestId: memory.requestId, ...bind,
        advanceId: world!.advance.advanceId!, roundId: roundIdOf(world!), pointId: work!.pointId,
        point: memory.commitPayload.point, settlementGroups: memory.commitPayload.settlementGroups,
      } as RequestMap['commit_point'],
      scope: worldScope(view),
    };
  }
  if (work!.phase === 'settle_group' && pending?.closed) return settleDecision(view);
  if (work!.phase === 'build_group' && pending && !pending.closed) return buildDecision(view);
  if (work!.phase === 'select_actor') return selectActorDecision(view);
  throw new Error(`Unschedulable point state: phase=${work!.phase} closed=${pending?.closed ?? 'null'}`);
}

function actorsComplete(view: ScheduleView): boolean {
  const planned = view.memory.plan?.[view.memory.planIndex];
  if (!planned) return true;
  const started = new Set(view.memory.groupActors);
  return planned.actorIds.every((actor) => started.has(actor));
}

function selectActorDecision(view: ScheduleView): Decision {
  const { world, control, work, memory } = view;
  const bind = writeBind(view);
  const planned = memory.plan?.[memory.planIndex];
  if (!actorsComplete(view)) {
    const actor = planned!.actorIds.find((a) => !memory.groupActors.includes(a))!;
    if (memory.lastModel?.task === 'action' && memory.lastModel.key === actor) {
      const output = memory.lastModel.output as { kind: 'act'; text: string } | { kind: 'skip' };
      if (output.kind === 'skip') {
        return {
          kind: 'transport', operation: 'checkpoint_record_skip',
          request: {
            protocolVersion: 2, requestId: memory.requestId, ...bind,
            operation: 'record_skip', pointId: work!.pointId, slotActorId: actor,
          } as RequestMap['checkpoint_record_skip'],
          scope: worldScope(view),
        };
      }
      if (output.kind !== 'act' || typeof output.text !== 'string') throw new Error('Action output must be {kind:"act",text} or {kind:"skip"}');
      return {
        kind: 'transport', operation: 'checkpoint_discover_group',
        request: {
          protocolVersion: 2, requestId: memory.requestId, ...bind,
          operation: 'discover_group', pointId: work!.pointId, groupId: memory.ids[`group:${actor}`],
          initiatorId: actor, actionText: output.text, targetIds: null,
        } as RequestMap['checkpoint_discover_group'],
        scope: worldScope(view),
      };
    }
    const blocked = modelBlocked(view, 'action');
    if (blocked) return blocked;
    if (!freshState(memory, work!)) return { kind: 'read_working_state' };
    return { kind: 'model', task: 'action', key: actor, input: { actor, workingState: asJson(memory.workingState!.state) } };
  }
  // Time scan: required for empty/actionless points (T03) AND for actor
  // points whose every planned actor skipped — nothing settled means the
  // point still owes its time-scan candidates before sealing.
  if (planned && !work!.timeScanComplete && memory.staged.length === 0) {
    const single = memory.updatesStages.length === 0;
    const calls: UpdatesCall[] | null = single
      ? (memory.lastModel?.task === 'updates' ? memory.lastModel.output as unknown as UpdatesCall[] : null)
      : (memory.updatesCalls.length >= memory.updatesStages.length ? memory.updatesCalls : null);
    if (calls) {
      const guard = checkUpdatesStages(inputIds(memory), calls);
      if (!guard.ok) return { kind: 'stop', reason: `dangling_updates_refs:${JSON.stringify(guard.dangling)}` };
      return {
        kind: 'transport', operation: 'checkpoint_stage_time_scan',
        request: {
          protocolVersion: 2, requestId: memory.requestId, ...bind,
          operation: 'stage_time_scan', pointId: work!.pointId,
          candidates: timeScanCandidates(guard.merged, world!.round?.order ?? []),
        } as RequestMap['checkpoint_stage_time_scan'],
        scope: worldScope(view),
      };
    }
    const blocked = modelBlocked(view, 'updates');
    if (blocked) return blocked;
    if (!freshState(memory, work!)) return { kind: 'read_working_state' };
    return updatesModelCall(view, `time_scan:${work!.pointId}`, { mode: 'time_scan', workingState: asJson(memory.workingState!.state) });
  }
  // Actor points: record explicit skips for round members this point leaves
  // behind AND no later planned point covers (T01 skips b–f; T02 P1 seals at
  // once because c–f belong to P2/P3). Empty points never skip (T03).
  const round = world!.round;
  const plannedNow = memory.plan?.[memory.planIndex];
  if (round && plannedNow && plannedNow.actorIds.length > 0) {
    const coveredLater = new Set(memory.plan!.slice(memory.planIndex + 1).flatMap((p) => p.actorIds));
    const pendingSkip = round.order.slice(work!.working.cursor).find((id) => !coveredLater.has(id));
    if (pendingSkip) {
      return {
        kind: 'transport', operation: 'checkpoint_record_skip',
        request: {
          protocolVersion: 2, requestId: memory.requestId, ...bind,
          operation: 'record_skip', pointId: work!.pointId, slotActorId: pendingSkip,
        } as RequestMap['checkpoint_record_skip'],
        scope: worldScope(view),
      };
    }
  }
  // Successor pre-binding (T08 path) then seal, both behind a fresh preview.
  if (memory.prepareSuccessor && !work!.successor) {
    if (memory.successorTime) {
      return {
        kind: 'transport', operation: 'checkpoint_prepare_successor',
        request: {
          protocolVersion: 2, requestId: memory.requestId, ...bind,
          operation: 'prepare_successor', pointId: work!.pointId, successorPointId: memory.ids.successor, timeAdvance: memory.successorTime,
        } as RequestMap['checkpoint_prepare_successor'],
        scope: worldScope(view),
      };
    }
    const blocked = modelBlocked(view, 'time');
    if (blocked) return blocked;
    return { kind: 'model', task: 'time', key: `successor:${work!.pointId}`, input: { head: asJson(world!.head), workingState: memory.workingState ? asJson(memory.workingState.state) : null } };
  }
  if (!freshState(memory, work!)) return { kind: 'read_working_state' };
  return {
    kind: 'transport', operation: 'checkpoint_seal_point',
    request: { protocolVersion: 2, requestId: memory.requestId, ...bind, operation: 'seal_point', pointId: work!.pointId } as RequestMap['checkpoint_seal_point'],
    scope: worldScope(view),
  };
}

function buildDecision(view: ScheduleView): Decision {
  const { world, control, work, memory } = view;
  const bind = writeBind(view);
  const pending = work!.pendingGroup!;
  const current = memory.sources[0];
  if (!current) {
    return {
      kind: 'transport', operation: 'checkpoint_close_group',
      request: {
        protocolVersion: 2, requestId: memory.requestId, ...bind,
        operation: 'close_group', pointId: work!.pointId, groupId: pending.groupId,
      } as RequestMap['checkpoint_close_group'],
      scope: worldScope(view),
    };
  }
  if (memory.lastModel?.task === 'targets' && memory.lastModel.key === current.sourceId && !current.targetsExtended) {
    const declared = memory.lastModel.output as { targets: { targetId: Id; triggerKey: Id; ruleVersion: RollSpec['ruleVersion']; target: number }[] };
    if (!Array.isArray(declared.targets)) throw new Error('Targets output must carry a targets array');
    return {
      kind: 'transport', operation: 'checkpoint_extend_group',
      request: {
        protocolVersion: 2, requestId: memory.requestId, ...bind,
        operation: 'extend_group', pointId: work!.pointId, groupId: pending.groupId, sourceId: current.sourceId,
        targets: declared.targets.map((t) => ({ targetId: t.targetId, triggerKey: t.triggerKey })), admittedMember: null,
      } as RequestMap['checkpoint_extend_group'],
      scope: worldScope(view),
    };
  }
  if (memory.lastModel?.task === 'reaction' && memory.lastModel.key === current.sourceId) {
    const entry = [...current.rolled].reverse().find((r) => r.admitted === true && !r.reacted);
    if (!entry || entry.rollId == null) throw new Error('Reaction output without an admitted roll');
    const text = memory.lastModel.output;
    if (typeof text !== 'string') throw new Error('Reaction output must be action text');
    const rollRefs: RollRef[] = [{ sourceId: current.sourceId, targetId: entry.targetId, triggerKey: entry.triggerKey, rollId: entry.rollId }];
    return {
      kind: 'transport', operation: 'checkpoint_extend_group',
      request: {
        protocolVersion: 2, requestId: memory.requestId, ...bind,
        operation: 'extend_group', pointId: work!.pointId, groupId: pending.groupId, sourceId: current.sourceId,
        admittedMember: { memberId: entry.targetId, actionText: text, rollRefs },
      } as RequestMap['checkpoint_extend_group'],
      scope: worldScope(view),
    };
  }
  if (!current.targetsExtended) {
    const blocked = modelBlocked(view, 'targets');
    if (blocked) return blocked;
    if (!freshState(memory, work!)) return { kind: 'read_working_state' };
    return { kind: 'model', task: 'targets', key: current.sourceId, input: { sourceId: current.sourceId, actionText: current.actionText, workingState: asJson(memory.workingState!.state) } };
  }
  // DFS (T02-el s5–s8): a rolled-and-admitted target finishes its whole
  // subtree — reaction, admitted extend, its own analysis — before the next
  // sibling target is rolled.
  const waiting = current.rolled.find((r) => r.admitted === true && !r.reacted);
  if (waiting) {
    const blocked = modelBlocked(view, 'reaction');
    if (blocked) return blocked;
    if (!freshState(memory, work!)) return { kind: 'read_working_state' };
    return { kind: 'model', task: 'reaction', key: current.sourceId, input: { sourceId: current.sourceId, memberId: waiting.targetId, rollId: waiting.rollId, workingState: asJson(memory.workingState!.state) } };
  }
  const next = current.pendingTargets[0];
  if (next) {
    return {
      kind: 'transport', operation: 'create_rolls',
      request: {
        protocolVersion: 2, requestId: memory.requestId, ...bind,
        rolls: [{ advanceId: world!.advance.advanceId!, roundId: roundIdOf(world!), groupId: pending.groupId, sourceId: current.sourceId, targetId: next.targetId, triggerKey: next.triggerKey, ruleVersion: next.rule.ruleVersion, target: next.rule.target }],
      } as RequestMap['create_rolls'],
      scope: worldScope(view),
    };
  }
  throw new Error(`Source ${current.sourceId} finished but was not retired by the driver`);
}

/** Split updates run 1–6 per-stage calls keyed by stage (scenario-declared
 * sequence); empty updatesStages = one merged call. Later stages see the
 * accumulated calls and their applied merge, not just the raw state. */
function updatesModelCall(view: ScheduleView, keyBase: string, base: Record<string, Json>): Decision {
  const { memory } = view;
  const stage = memory.updatesStages[memory.updatesCalls.length];
  const priorStages = asJson(memory.updatesCalls);
  let appliedDelta: Json = {};
  if (memory.updatesCalls.length) {
    const merged = checkUpdatesStages(inputIds(memory), memory.updatesCalls);
    if (!merged.ok) return { kind: 'stop', reason: `dangling_updates_refs:${JSON.stringify(merged.dangling)}` };
    appliedDelta = asJson(merged.merged);
  }
  const fields: Record<string, Json> = { ...base, priorStages, appliedDelta };
  if (stage) return { kind: 'model', task: 'updates', key: `${keyBase}#${stage}`, input: { ...fields, stage } };
  return { kind: 'model', task: 'updates', key: keyBase, input: fields };
}

function settleDecision(view: ScheduleView): Decision {
  const { world, work, memory } = view;
  const bind = writeBind(view);
  const pending = work!.pendingGroup!;
  const single = memory.updatesStages.length === 0;
  const calls: UpdatesCall[] | null = single
    ? (memory.lastModel?.task === 'updates' ? memory.lastModel.output as unknown as UpdatesCall[] : null)
    : (memory.updatesCalls.length >= memory.updatesStages.length ? memory.updatesCalls : null);
  if (calls) {
    const guard = checkUpdatesStages(inputIds(memory), calls);
    if (!guard.ok) return { kind: 'stop', reason: `dangling_updates_refs:${JSON.stringify(guard.dangling)}` };
    if (!memory.lastResults) throw new Error('Updates output without stored results');
    if (!memory.workingState) throw new Error('Candidates assembly without working state');
    const actorIds = pending.memberIds.length ? pending.memberIds : [pending.sourceId];
    const candidates = assembleCandidates({
      groupId: pending.groupId, actorIds, deltas: guard.merged,
      taskCoverageIds: world!.round?.order ?? actorIds,
    });
    return {
      kind: 'transport', operation: 'checkpoint_stage_unit',
      request: {
        protocolVersion: 2, requestId: memory.requestId, ...bind,
        operation: 'stage_unit', pointId: work!.pointId, groupId: pending.groupId, candidates, results: memory.lastResults,
      } as RequestMap['checkpoint_stage_unit'],
      scope: worldScope(view),
    };
  }
  if (!memory.lastResults) {
    const blocked = modelBlocked(view, 'results');
    if (blocked) return blocked;
    if (!freshState(memory, work!)) return { kind: 'read_working_state' };
    return { kind: 'model', task: 'results', key: pending.groupId, input: { groupId: pending.groupId, workingState: asJson(memory.workingState!.state) } };
  }
  const blocked = modelBlocked(view, 'updates');
  if (blocked) return blocked;
  return updatesModelCall(view, pending.groupId, { groupId: pending.groupId, mode: 'group', workingState: memory.workingState ? asJson(memory.workingState.state) : null });
}

// ---------- memory readers ----------

function inputIds(memory: ControllerMemory): { taskIds: Set<Id>; changeIds: Set<Id> } {
  const taskIds = new Set<Id>();
  const changeIds = new Set<Id>();
  const state = memory.workingState?.state;
  if (state) {
    for (const item of Object.values(state.items)) {
      for (const change of item.appearanceChanges) { changeIds.add(change.id); for (const id of change.supersedes) changeIds.add(id); }
    }
    for (const character of Object.values(state.characters)) {
      for (const task of Object.keys(character.tasks)) taskIds.add(task);
      for (const change of character.appearanceChanges) { changeIds.add(change.id); for (const id of change.supersedes) changeIds.add(id); }
      for (const change of character.personalityChanges) { changeIds.add(change.id); for (const id of change.supersedes) changeIds.add(id); }
    }
  }
  return { taskIds, changeIds };
}

function groupFromDeltas(base: { groupId: Id | null; actorIds: Id[]; taskCoverageIds: Id[]; personalityCoverageIds: Id[] }, deltas: Record<Id, EntityDelta>): SettlementGroup {
  const appearances: SettlementGroup['appearances'] = {};
  const tasksAchieved: SettlementGroup['tasksAchieved'] = {};
  const subtasksAdded: SettlementGroup['subtasksAdded'] = {};
  const personalities: SettlementGroup['personalities'] = {};
  const sanities: SettlementGroup['sanities'] = {};
  const positions: SettlementGroup['positions'] = {};
  for (const [entity, delta] of Object.entries(deltas)) {
    if (delta.appearanceChanges?.length) appearances[entity] = delta.appearanceChanges;
    if (delta.tasksAchieved?.length) tasksAchieved[entity] = delta.tasksAchieved;
    if (delta.subtasksAdded?.length) subtasksAdded[entity] = delta.subtasksAdded;
    if (delta.personalityChanges?.length) personalities[entity] = delta.personalityChanges;
    if (delta.sanitySet != null) sanities[entity] = delta.sanitySet;
    if (delta.positionSet) positions[entity] = delta.positionSet;
  }
  return { groupId: base.groupId, actorIds: base.actorIds, positions, appearances, tasksAchieved, subtasksAdded, personalities, sanities, taskCoverageIds: base.taskCoverageIds, personalityCoverageIds: base.personalityCoverageIds };
}

/** personalityCoverage declares who was considered for personality change:
 * with tasks achieved, a scan covers the whole round order and a group covers
 * its actors; without tasks nobody is declared (T03 a–f, T03-collapse [c],
 * T01/T02 []). Positions come only from positionSet deltas (T02 positions {}). */
function hasTasksAchieved(deltas: Record<Id, EntityDelta>): boolean {
  return Object.values(deltas).some((d) => d.tasksAchieved?.length);
}

function timeScanCandidates(deltas: Record<Id, EntityDelta>, coverageIds: Id[]): SettlementGroup {
  return groupFromDeltas({ groupId: null, actorIds: [], taskCoverageIds: coverageIds, personalityCoverageIds: hasTasksAchieved(deltas) ? coverageIds : [] }, deltas);
}

export function assembleCandidates(args: { groupId: Id; actorIds: Id[]; deltas: Record<Id, EntityDelta>; taskCoverageIds: Id[] }): SettlementGroup {
  return groupFromDeltas({ groupId: args.groupId, actorIds: args.actorIds, taskCoverageIds: args.taskCoverageIds, personalityCoverageIds: hasTasksAchieved(args.deltas) ? args.actorIds : [] }, args.deltas);
}
