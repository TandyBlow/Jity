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

/** One planned point: scenario segmentation with an explicit boundary. The
 * actorIds declare which frozen slots this point covers (a later point's
 * slots are deferred); actors NO point covers are still judged here (§6.1),
 * and an empty list keeps the actorless rule (time scan owns the slots). */
export interface PlannedPoint { pointId: Id; kind: 'normal' | 'instant' | 'linked'; timeAdvance: TimeAdvance; actorIds: Id[] }
export interface RollRule { ruleVersion: RollSpec['ruleVersion']; target: number }
/** Program-owned dice rule (§6.2): the model never declares versions or
 * thresholds. Stage 0–3 fixture rule; the d20 baseline swaps this constant. */
export const PROGRAM_ROLL_RULE: RollRule = { ruleVersion: 'reaction-fixture-v1', target: 11 };

// ---------- 稳定组合身份键（§9.3） ----------

const SHA256_K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);
const rotr32 = (x: number, n: number): number => ((x >>> n) | (x << (32 - n))) >>> 0;

/** Compact sync SHA-256 over ASCII (IDs are ASCII per world-canonical-v1;
 * non-ASCII throws instead of silently corrupting bytes). Hex output. Used
 * ONLY for bounded composite identity keys — state digests stay server-side. */
export function sha256Hex(message: string): string {
  const bytes: number[] = [];
  for (const ch of message) {
    const code = ch.charCodeAt(0);
    if (code > 127) throw new Error('sha256Hex: non-ASCII input (IDs must be ASCII)');
    bytes.push(code);
  }
  const bitLen = bytes.length * 8;
  bytes.push(0x80);
  while (bytes.length % 64 !== 56) bytes.push(0);
  for (let shift = 56; shift >= 0; shift -= 8) bytes.push(Math.floor(bitLen / 2 ** shift) & 0xff);
  const H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
  const w = new Uint32Array(64);
  for (let off = 0; off < bytes.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = ((bytes[off + i * 4] << 24) | (bytes[off + i * 4 + 1] << 16) | (bytes[off + i * 4 + 2] << 8) | bytes[off + i * 4 + 3]) >>> 0;
    for (let i = 16; i < 64; i++) {
      const s0 = rotr32(w[i - 15], 7) ^ rotr32(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rotr32(w[i - 2], 17) ^ rotr32(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }
    let a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
    for (let i = 0; i < 64; i++) {
      const S1 = rotr32(e, 6) ^ rotr32(e, 11) ^ rotr32(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (h + S1 + ch + SHA256_K[i] + w[i]) >>> 0;
      const S0 = rotr32(a, 2) ^ rotr32(a, 13) ^ rotr32(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) >>> 0;
      h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0; H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
    H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0; H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
  }
  return H.map((x) => x.toString(16).padStart(8, '0')).join('');
}

/** 无歧义且有界的稳定组合身份：各段做长度前缀折叠（「来源 a:b+目标 c」与
 * 「来源 a+目标 b:c」的前像必然不同），SHA-256 截断 128 位——拼接直接入键
 * 会碰撞且超长（三个 50 字符合法 ID 拼接 160 字符，wire 上限 128）。 */
export function foldIdentity(...parts: Id[]): string {
  const preimage = parts.map((p) => `${p.length}:${p}`).join('');
  return sha256Hex(preimage).slice(0, 32);
}

/** 触发分配的组合身份键（程序所有，模型不见）：allocationKey 绑定组与来源，
 * slotKey 再绑目标；键文本 ≤ 40 字符（wire 上限 128）。 */
export function triggerAllocationKey(groupId: Id, sourceId: Id): Id {
  return `trigger:${foldIdentity(groupId, sourceId)}`;
}
export function triggerSlotKey(groupId: Id, sourceId: Id, targetId: Id): Id {
  return `trigger:${foldIdentity(groupId, sourceId, targetId)}`;
}
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

/** Narration assembly (§7.1: Sₜ₋₁、Δₜ、Sₜ、视角). `delta` is the target
 * point's ORIGINAL saved record — commit-time capture is only ever a cache;
 * recovery paths read it from the server. */
export interface NarrationAssembly {
  pointId: Id;
  after: WorldState | null;
  delta: { timeAdvance: TimeAdvance | null; entityDeltas: Record<Id, EntityDelta> } | null;
  previousPointId: Id | null;
  /** Root points never read a before-state; it stays null. */
  before: WorldState | null;
  /** Set when a served get_state lacked the required record fields: the
   * read capability is incomplete and generation must stop — never assume
   * an empty delta. */
  readIncomplete?: boolean;
}

export function initialNarrationAssembly(pointId: Id): NarrationAssembly {
  return { pointId, after: null, delta: null, previousPointId: null, before: null };
}

/** The narration model input. Scenario declared expectations must NOT call
 * this — they hand-write literals so a shared omission fails loudly. */
export function assembleNarrationInput(input: NarrationAssembly): Json | null {
  if (!input.after || !input.delta) return null;
  if (input.previousPointId != null && !input.before) return null;
  const protagonist = input.after.initial.characters[input.after.protagonistId];
  const name = protagonist?.name ?? input.after.protagonistId;
  return {
    pointId: input.pointId,
    before: input.before ? JSON.parse(JSON.stringify(input.before)) : null,
    delta: JSON.parse(JSON.stringify(input.delta)),
    after: JSON.parse(JSON.stringify(input.after)),
    perspective: `主角视角（${input.after.protagonistId}「${name}」）；只表达已结算的世界事实`,
  };
}

export type AllocationPlan = Pick<RequestMap['allocate_ids'], 'allocationKey' | 'slots'>;

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
  allocPlan: AllocationPlan | null;
  /** Explicit per-round identity requirements, fulfilled before pointPlan.
   * Allocations are confirmed by allocationKey, not inferred from stale slot
   * values left by an earlier round. */
  roundAllocations: Record<Id, AllocationPlan>;
  allocatedKeys: Id[];
  playerInput: { text: string; order: Id[] } | null;
  /** The advance the driver itself started, with the input text it sent —
   * identity-bound (§6.1): action reads it only while the world's advanceId
   * still matches, so a record from an earlier advance never leaks into a
   * new one. The normal path has no get_context at all (T01), so without
   * this retention the player text would be lost. */
  playerAdvance: { advanceId: Id; inputId: Id; text: string } | null;
  plan: PlannedPoint[] | null;
  planIndex: number;
  /** Set when the scenario pre-declares a successor binding (T08 path). */
  prepareSuccessor: boolean;
  localPause: boolean;
  budget: { used: number; max: number | null };
  /** Narration assembly state (§7.1): the pipeline reads the target point's
   * state plus its own saved record (get_state.data: previousPointId /
   * timeAdvance / entityDeltas — the ORIGINAL Δ), then the predecessor's
   * state. Fields fill progressively through adoptSuccess; a root point
   * never reads a before-state. */
  narration: { pointId: Id; claim: CurrentClaim | null; input: NarrationAssembly } | null;
  workingState: { key: string; state: WorldState } | null;
  sources: SourceAnalysis[];
  staged: StagedUnit[];
  /** Confirmed candidates recovered before stage_unit; replay verbatim. */
  restoredUnit?: StagedUnit | null;
  /** Time-scan unit staged for the open point: it rides into every later
   * preview's settlementGroups (A §7: one list, no separate channel) but is
   * NOT a named group — commit_point keeps its plain settlementGroups. */
  stagedTimeScan: SettlementGroup | null;
  /** Actors of this point/round already processed — acted in a discovered
   * group or explicitly skipped (record_skip). A processed slot is never
   * judged twice (§5.1: a common-settlement member never acts again at its
   * own slot). Reset at commit/round teardown. */
  groupActors: Id[];
  /** 本结算组的冻结行动与全部骰点判定（§7.1 results 输入；含未准入 roll）。
   * 随 sources 同生命周期：discover 建立、admit 前插、create_rolls 追加、
   * stage/commit 归零——只覆盖当前组，不是长期行动记录。 */
  groupActions: { memberId: Id; actionText: string; rolls: { targetId: Id; rollId: Id; result: number; eligible: boolean; admitted: boolean }[] }[];
  lastModel: ModelResolution | null;
  /** Targets the model just declared for the current source, kept OUT of
   * lastModel on purpose: every successful transport clears lastModel, and
   * the runtime allocate_ids hop between the targets call and extend_group
   * must not lose the declared set (no re-sampling of targets). */
  lastTargets: { sourceId: Id; targets: Id[] } | null;
  lastResults: Record<Id, string> | null;
  /** Scenario-declared updates split; empty = one merged call. */
  updatesStages: UpdatesStage[];
  /** Driver accumulates one UpdatesCall per split stage here. */
  updatesCalls: UpdatesCall[];
  /** How many split stages the between-stage ladder has consumed (the
   * scheduler gates each stage call on this catching up to
   * updatesCalls.length). With a deferred forward reference this advances
   * WITHOUT the deferred part being reflected in workingState —
   * updatesPendingRefs records exactly what the served state does not yet
   * contain (§6.3: later stages read applied state, never re-declare). */
  updatesApplied: number;
  /** Boundaries skipped with ZERO applicable content — the whole in-progress
   * batch was forward references a later subtasks stage produces. The next
   * stage reads the last-good state; counted for evaluation visibility,
   * never retried. A split boundary (valid part applied, refs deferred) is
   * NOT a skip: it ran a real preview. */
  updatesPreviewSkipped: number;
  /** Forward task references currently deferred at a between-stage boundary
   * (entity:task) — not yet state facts; a later subtasks stage produces
   * them and the settle batch carries them in (checkUpdatesStages produced
   * ruling). Reset once the group's ladder is consumed (stage/commit) —
   * the dangling stop keeps its refs in the terminal reason. */
  updatesPendingRefs: string[];
  continuation: Conclusion | null;
  /** This round's committed point Δs in commit order — the continuation
   * input's 「本轮状态变化」 (§7.1). Built from the client's own committed
   * point projections (no extra read). null until this driver commits a point
   * of the round: a session opened mid-transition has no local history. */
  roundChanges: { roundId: Id; points: { pointId: Id; timeAdvance: TimeAdvance; entityDeltas: Record<Id, EntityDelta> }[] } | null;
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

export interface ScheduleView { world: WorldContext | null; control: ControlState; work: PointWork | null; memory: ControllerMemory; command?: HarnessCommand; activeInput: { advanceId: Id; inputId: Id; text: string } | null }

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

export interface ErrorCatalogEntry { httpStatus: number; retryable: boolean; clientAction: ClientAction; controlRequired: boolean }
export const errorCatalog = contract.errorCodes as unknown as Record<ErrorCode, ErrorCatalogEntry>;

/** The wire-safe error body — exactly the fields ErrorBody's schema allows.
 * Built here so internal catalog bookkeeping (controlRequired) cannot leak
 * into a response envelope by construction, not by caller discipline. */
export function errorBodyFor(code: ErrorCode, details: Record<string, Json> = {}): { code: ErrorCode; httpStatus: number; retryable: boolean; clientAction: ClientAction; details: Record<string, Json> } {
  const { controlRequired: _ledgerOnly, ...entry } = errorCatalog[code];
  return { code, ...entry, details };
}

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

/** Merge stages in canonical order; throws on out-of-order/duplicate splits.
 * Performs NO reference validation: a mid-sequence merge legally contains
 * references that later stages will produce (T03-collapse puts v13 into
 * tasksAchieved before the subtasks stage declares it). */
export function mergeUpdatesStages(stages: UpdatesCall[]): Record<Id, EntityDelta> {
  let lastIndex = -1;
  for (const call of stages) {
    const index = updateStages.indexOf(call.stage);
    if (index < 0 || index <= lastIndex) throw new Error(`Out-of-order/duplicate updates stage: ${call.stage}`);
    lastIndex = index;
  }
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
  return merged;
}

/** Full validation for a COMPLETE stage sequence: canonical order, then the
 * dangling-reference guard (every referenced task/change must appear in the
 * input state or in some stage output; cross-stage overlap the server
 * accepts stays legal — v13 ends up both achieved and re-added pending).
 * Never run mid-sequence — use mergeUpdatesStages there. */
export function checkUpdatesStages(input: { taskIds: ReadonlySet<Id>; changeIds: ReadonlySet<Id> }, stages: UpdatesCall[]): { ok: true; merged: Record<Id, EntityDelta> } | { ok: false; dangling: { stage: UpdatesStage; entity: Id; kind: 'task' | 'change'; id: Id }[] } {
  const merged = mergeUpdatesStages(stages);
  const tasks = producedTasks(stages);
  const changes = producedChanges(stages);
  const dangling: { stage: UpdatesStage; entity: Id; kind: 'task' | 'change'; id: Id }[] = [];
  for (const call of stages) {
    for (const [entity, delta] of Object.entries(call.changes)) {
      for (const id of taskRefs(delta)) if (!input.taskIds.has(id) && !tasks.has(id)) dangling.push({ stage: call.stage, entity, kind: 'task', id });
      for (const id of changeRefs(delta)) if (!input.changeIds.has(id) && !changes.has(id)) dangling.push({ stage: call.stage, entity, kind: 'change', id });
    }
  }
  if (dangling.length) return { ok: false, dangling };
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
  if (narration.input.readIncomplete) return { kind: 'stop', reason: 'narration_read_incomplete' };
  // Assembly ladder (§7.1): reads are plain GETs — no lease binding, no
  // requestId. The target read carries the point's own saved record back.
  if (!narration.input.after || !narration.input.delta) {
    return {
      kind: 'transport', operation: 'get_state',
      request: { point: pointId } as RequestMap['get_state'],
      scope: worldScope(view),
    };
  }
  if (narration.input.previousPointId != null && !narration.input.before) {
    return {
      kind: 'transport', operation: 'get_state',
      request: { point: narration.input.previousPointId } as RequestMap['get_state'],
      scope: worldScope(view),
    };
  }
  const assembled = assembleNarrationInput(narration.input);
  if (!assembled) return { kind: 'stop', reason: 'narration_read_incomplete' };
  const blocked = modelBlocked(view, 'narration');
  if (blocked) return blocked;
  return { kind: 'model', task: 'narration', key: pointId, input: assembled };
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
  // 缺少判断依据时明确停止：没有当前世界或没有本轮变化就不得调用模型，
  // 更不能把模型输出写成结论（H2 的补读另做）。
  const state = view.work ? freshState(memory, view.work) : memory.workingState?.state ?? null;
  const roundId = roundIdOf(world!);
  const missing: string[] = [];
  if (!state) missing.push('workingState');
  if (!memory.roundChanges || memory.roundChanges.roundId !== roundId) missing.push('roundChanges');
  if (missing.length > 0) return { kind: 'stop', reason: `continuation_context_missing:${missing.join(',')}` };
  const blocked = modelBlocked(view, 'continuation');
  if (blocked) return blocked;
  // §7.1：继续推进判断读「主角、当前世界和本轮状态变化」。主角与当前世界都
  // 在 workingState 里（protagonistId/characters）；本轮变化是已提交点的时间
  // 与实体 Δ，按提交顺序给出。零本地历史（会话在半途打开）时为 null——不
  // 假装「本轮没有变化」。
  const roundChanges = asJson(memory.roundChanges!.points);
  return {
    kind: 'model', task: 'continuation', key: roundId,
    input: { round: asJson(world!.round), head: asJson(world!.head), workingState: asJson(state!), roundChanges },
  };
}

function idlePointDecision(view: ScheduleView): Decision {
  const { world, control, memory } = view;
  const allocation = memory.roundAllocations[roundIdOf(world!)];
  if (allocation && !memory.allocatedKeys.includes(allocation.allocationKey)) {
    const bind = writeBind(view);
    return {
      kind: 'transport', operation: 'allocate_ids',
      request: { protocolVersion: 2, requestId: memory.requestId, worldId: world!.worldId, leaseToken: bind.leaseToken, fenceEpoch: bind.fenceEpoch, ...allocation },
      scope: worldScope(view),
    };
  }
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
    if (!memory.commitPayload) {
      // A preview can rebuild the projection only when ALL saved candidate
      // bytes are present. Missing frozen units must never become an empty
      // preview/commit followed by an automatic conflict loop.
      const complete = memory.staged.length === work!.settledUnits.length
        && work!.settledUnits.every((unit, index) => {
          const staged = memory.staged[index];
          return staged.groupId === unit.groupId && staged.candidates.groupId === unit.groupId
            && JSON.stringify([...staged.actorIds].sort()) === JSON.stringify([...unit.memberIds].sort());
        }) && (!work!.timeScanComplete || memory.stagedTimeScan != null)
        && (work!.settledUnits.length > 0 || work!.timeScanComplete);
      return complete ? { kind: 'read_working_state' } : { kind: 'stop', reason: 'sealed_work_missing' };
    }
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

/** The actor whose action opportunity comes next, in the FROZEN order at the
 * served working cursor. A slot covered by a LATER planned point is deferred
 * (skipping it now would visit it and cancel its later opportunity); a slot
 * no point covers is still JUDGED here — a pointPlan omission is never a
 * skip, not even when the plan lists NOBODY while unvisited slots remain (an
 * actorless plan is only legitimate once every opportunity is processed).
 * Actors already processed (acted or explicitly skipped) never repeat. */
function nextActor(view: ScheduleView): Id | null {
  const { world, work, memory } = view;
  const round = world!.round;
  const planned = memory.plan?.[memory.planIndex];
  if (!round || !planned) return null;
  const plannedNow = new Set(planned.actorIds);
  const coveredLater = new Set(memory.plan!.slice(memory.planIndex + 1).flatMap((point) => point.actorIds));
  for (const actor of round.order.slice(work!.working.cursor)) {
    if (memory.groupActors.includes(actor)) continue;
    if (!plannedNow.has(actor) && coveredLater.has(actor)) return null;
    return actor;
  }
  return null;
}

/** §6.1 action advance input. The player text is identity-bound: a get_context
 * activeInput counts only for the advance it names (server authority), the
 * driver's own start_advance record covers the normal path with no context
 * read at all (T01). Neither source ever leaks across advances. */
function actionAdvance(view: ScheduleView): { inputText: string | null; intentStatus: WorldContext['advance']['intentStatus'] } {
  const advanceId = view.world!.advance.advanceId;
  const served = advanceId !== null && view.activeInput?.advanceId === advanceId ? view.activeInput.text : null;
  const retained = advanceId !== null && view.memory.playerAdvance?.advanceId === advanceId ? view.memory.playerAdvance.text : null;
  return { inputText: served ?? retained, intentStatus: view.world!.advance.intentStatus };
}

function selectActorDecision(view: ScheduleView): Decision {
  const { world, work, memory } = view;
  const bind = writeBind(view);
  const planned = memory.plan?.[memory.planIndex];
  // §5.1/§6.1：行动机会按冻结顺序与游标逐人判断。计划里的 actorIds 只决定
  // 点位切分（哪些槽位属于后序点），不决定谁被问；未被任何点覆盖的槽位
  // 也要在本点判断——省略不是跳过。空点（actorIds 为空）仍由时间扫描
  // 承包所有槽位，保留 T03/T02-empty-linked 的原有规则。
  const actor = nextActor(view);
  if (actor) {
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
    // §6.1：行动输入携带链级 advance 上下文——玩家输入文本与消费状态。
    // 文本只能来自与当前 advance 身份绑定的记录（驱动器 start_advance 的
    // 原文，或同一 advance 的 context activeInput）；状态来自 world.advance。
    return {
      kind: 'model', task: 'action', key: actor,
      input: {
        actor,
        advance: actionAdvance(view),
        workingState: asJson(memory.workingState!.state),
      },
    };
  }
  // Time scan: required for empty/actionless points (T03) AND for actor
  // points whose every judged actor skipped — nothing settled means the
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
          candidates: timeScanCandidates(guard.merged, worldRoster(memory)),
        } as RequestMap['checkpoint_stage_time_scan'],
        scope: worldScope(view),
      };
    }
    const blocked = modelBlocked(view, 'updates');
    if (blocked) return blocked;
    if (!freshState(memory, work!)) return { kind: 'read_working_state' };
    return updatesModelCall(view, `time_scan:${work!.pointId}`, { mode: 'time_scan', workingState: asJson(memory.workingState!.state) });
  }
  // Successor time generation and sealing both need the latest staged state.
  if (!freshState(memory, work!)) return { kind: 'read_working_state' };
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
  if (memory.lastTargets?.sourceId === current.sourceId && !current.targetsExtended) {
    // Program-owned trigger identity (§9.3): the model names targets only —
    // keys resolve from the allocated-id map, and missing keys go through a
    // runtime allocate_ids first (stable allocationKey → server-idempotent on
    // retry; confirmed keys are never re-allocated; empty sets allocate
    // nothing). Slots bind group+SOURCE+target — the trigger is per-threat
    // identity (判定键含 sourceId), so two sources threatening the same
    // target hold distinct keys and neither reuses nor overwrites the
    // other's. Only THIS source's missing slots are requested.
    const targetIds = [...new Set(memory.lastTargets.targets)];
    const missing = targetIds.filter((targetId) => memory.ids[triggerSlotKey(pending.groupId, current.sourceId, targetId)] == null);
    if (missing.length > 0) {
      return {
        kind: 'transport', operation: 'allocate_ids',
        // LeaseBound only — AllocateIdsRequest has no expected* bindings, so
        // this request must not spread writeBind's CheckpointRequest fields.
        request: {
          protocolVersion: 2, requestId: memory.requestId,
          worldId: bind.worldId, leaseToken: bind.leaseToken, fenceEpoch: bind.fenceEpoch,
          allocationKey: triggerAllocationKey(pending.groupId, current.sourceId),
          slots: missing.map((targetId) => ({ slotKey: triggerSlotKey(pending.groupId, current.sourceId, targetId), kind: 'trigger' as const })),
        } as RequestMap['allocate_ids'],
        scope: worldScope(view),
      };
    }
    return {
      kind: 'transport', operation: 'checkpoint_extend_group',
      request: {
        protocolVersion: 2, requestId: memory.requestId, ...bind,
        operation: 'extend_group', pointId: work!.pointId, groupId: pending.groupId, sourceId: current.sourceId,
        targets: targetIds.map((targetId) => ({ targetId, triggerKey: memory.ids[triggerSlotKey(pending.groupId, current.sourceId, targetId)]! })), admittedMember: null,
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
    // §6.2 步骤 4：目标读取发起者的具体威胁（冻结行动文本）生成反应。
    return { kind: 'model', task: 'reaction', key: current.sourceId, input: { sourceId: current.sourceId, sourceActionText: current.actionText, memberId: waiting.targetId, rollId: waiting.rollId, workingState: asJson(memory.workingState!.state) } };
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
 * sequence); empty updatesStages = one merged call. Later stages READ the
 * post-preview working state (the controller applies accumulated prior
 * candidates through preview_point before the next stage call) — the input
 * carries no priorStages/appliedDelta data for the model to apply itself
 * (§6.3: stage n reads the state after stage n−1 applied). */
function updatesModelCall(view: ScheduleView, keyBase: string, base: Record<string, Json>): Decision {
  const { memory } = view;
  if (memory.updatesCalls.length > memory.updatesApplied) {
    // Prior stage candidates are not yet applied: preview first (the
    // controller folds the synthetic in-progress group into the request).
    return { kind: 'read_working_state' };
  }
  const stage = memory.updatesStages[memory.updatesCalls.length];
  if (stage) return { kind: 'model', task: 'updates', key: `${keyBase}#${stage}`, input: { ...base, stage } };
  return { kind: 'model', task: 'updates', key: keyBase, input: base };
}

function settleDecision(view: ScheduleView): Decision {
  const { world, work, memory } = view;
  const bind = writeBind(view);
  const pending = work!.pendingGroup!;
  if (memory.restoredUnit) {
    if (memory.restoredUnit.groupId !== pending.groupId) return { kind: 'stop', reason: 'recovery_group_mismatch' };
    return { kind: 'transport', operation: 'checkpoint_stage_unit', scope: worldScope(view),
      request: { protocolVersion: 2, requestId: memory.requestId, ...bind, operation: 'stage_unit', pointId: work!.pointId,
        groupId: pending.groupId, candidates: memory.restoredUnit.candidates, results: memory.restoredUnit.results } as RequestMap['checkpoint_stage_unit'] };
  }
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
      groupId: pending.groupId, actorIds, deltas: guard.merged, roster: worldRoster(memory),
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
    // §7.1 完整性：模型只能结算它确实读到的冻结行动。组成员缺失（刷新/冷
    // 启动丢内存）时不得用空列表生成结果——补数据（H2 从服务端 FrozenGroup
    // 恢复）之前明确停止。
    const requiredActors = pending.memberIds.length ? pending.memberIds : [pending.sourceId];
    const known = new Set(memory.groupActions.map((member) => member.memberId));
    const missing = requiredActors.filter((actor) => !known.has(actor));
    if (missing.length > 0) return { kind: 'stop', reason: `frozen_actions_missing:${missing.join(',')}` };
    // §7.1：结算输入携带全组冻结行动与全部骰点判定（含未准入 roll）——
    // 记忆字段 groupActions 与 sources 同生命周期，只覆盖当前组。
    return {
      kind: 'model', task: 'results', key: pending.groupId,
      input: {
        groupId: pending.groupId,
        members: memory.groupActions.map((member) => ({ memberId: member.memberId, actionText: member.actionText, rollRefs: member.rolls })),
        workingState: asJson(memory.workingState!.state),
      },
    };
  }
  const blocked = modelBlocked(view, 'updates');
  if (blocked) return blocked;
  // §7.1：更新读已确认结果——results 是上一步模型产出、随本批次结算的事实。
  return updatesModelCall(view, pending.groupId, { groupId: pending.groupId, mode: 'group', results: asJson(memory.lastResults), workingState: memory.workingState ? asJson(memory.workingState.state) : null });
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

/** Coverage (2026-10-22 ruling, aligned with A's validate_unit): task
 * coverage always equals the world's full character roster; personality
 * coverage stays empty without achieved tasks and otherwise lists the same
 * roster — named groups and the time-scan unit share the rule. The roster
 * comes from the served working state, never round.order. Positions come
 * only from positionSet deltas (T02 positions {}). */
function hasTasksAchieved(deltas: Record<Id, EntityDelta>): boolean {
  return Object.values(deltas).some((d) => d.tasksAchieved?.length);
}

function worldRoster(memory: ControllerMemory): Id[] {
  const state = memory.workingState?.state;
  if (!state) throw new Error('World roster without working state');
  return Object.keys(state.characters).sort();
}

export function timeScanCandidates(deltas: Record<Id, EntityDelta>, roster: Id[]): SettlementGroup {
  return groupFromDeltas({ groupId: null, actorIds: [], taskCoverageIds: roster, personalityCoverageIds: hasTasksAchieved(deltas) ? roster : [] }, deltas);
}

export function assembleCandidates(args: { groupId: Id; actorIds: Id[]; deltas: Record<Id, EntityDelta>; roster: Id[] }): SettlementGroup {
  return groupFromDeltas({ groupId: args.groupId, actorIds: args.actorIds, taskCoverageIds: args.roster, personalityCoverageIds: hasTasksAchieved(args.deltas) ? args.roster : [] }, args.deltas);
}
