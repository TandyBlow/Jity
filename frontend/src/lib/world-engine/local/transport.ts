/** Browser-local implementation of the v2 world operations. The Python kernel
 * remains the reference; this class is the only state authority at runtime and
 * keeps the same record shape (head, points, work, control, narration). Every
 * write runs on a draft and replaces the committed record only when the whole
 * operation succeeds, so a rejected candidate cannot leave partial state. */
import { WorldApiError, type WorldTransport } from '../transport';
import type {
  ClaimSummary, ControlState, CurrentClaim, DataMap, Digest, EntityDelta, ErrorCode, ErrorResponse,
  Id, InitialState, InitialTemplate, Json, NarrationStatus, PointWork, RequestMap, RollOutcome, RollSpec,
  Scope, SettlementGroup, Success, Task, TimelinePoint, TimeAdvance, WorldContext, WorldOperation, WorldState,
} from '../types';
import { canonicalDigest, canonicalJson } from './canonical';
import {
  applyPoint, buildInitialState, buildTimelinePoint, clone, KernelViolation, pointEntityDeltas, stateDigest,
} from './state';

const ENGINE = 'world-engine-v1' as const;
const SCHEMA = 2 as const;
const CANONICAL = 'world-canonical-v1' as const;
const LEASE_TTL = 3_600_000;
const CLAIM_TTL = 3_600_000;

interface Claim { claimToken: Id; generation: number; mode: 'head' | 'history'; fenceEpoch: number | null; issuedAtEpochMilli: number; expiresAtEpochMilli: number }
interface NarrationEntry { status: NarrationStatus; text: string | null; generation: number; claim: Claim | null }
type Gate = ControlState['gate'];
interface AdvanceRecord { advanceId: Id; inputId: Id; inputText: string; intentStatus: 'pending' | 'consumed' | 'expired' }
interface RoundRecord { roundId: Id; trigger: 'player' | 'automatic'; order: Id[]; cursor: number; actedIds: Id[]; visitedIds: Id[]; conclusion: WorldContext['round'] extends null ? never : any }
interface Working { cursor: number; actedIds: Id[]; visitedIds: Id[]; settledUnitIds: Id[]; intentStatus: 'pending' | 'consumed' | 'expired' }
interface GroupRecord {
  groupId: Id; sourceId: Id; memberIds: Id[]; targetIds: Id[]; targetIdsBySource: Record<Id, Id[] | null>;
  targetSpecsBySource: Record<Id, { targetId: Id; triggerKey: Id }[] | null>; frontierIds: Id[];
  closed: boolean; actionTexts: Record<Id, string | null>;
}
interface UnitRecord { unitId: Id; groupId: Id; memberIds: Id[]; contentHash: Digest; candidates: SettlementGroup; results: Record<Id, string> }
interface WorkRecord {
  pointId: Id; kind: 'normal' | 'instant' | 'linked'; timeAdvance: TimeAdvance; timeLocked: boolean;
  sealed: boolean; prefixDigest: Digest | null; timeScanComplete: boolean; timeScan: SettlementGroup | null;
  baseline: { headPointId: Id; version: number; stateDigest: Digest };
  phase: 'select_actor' | 'build_group' | 'settle_group'; working: Working; units: UnitRecord[];
  pendingGroup: GroupRecord | null; successor: any;
}
interface RollRecord extends RollOutcome { key: string }
interface PersistedRecord {
  worldId: Id; initial: InitialState; state: WorldState; version: number; rootPointId: Id; headPointId: Id;
  points: Record<Id, TimelinePoint>; pointStates: Record<Id, { version: number; state: WorldState; stateDigest: Digest }>;
  advance: AdvanceRecord | null; round: RoundRecord | null; work: WorkRecord | null;
  control: { phase: ControlState['phase']; paused: boolean; revision: number; gate: Gate };
  lease: { leaseToken: Id; fenceEpoch: number; expiresAtEpochMilli: number } | null;
  leaseEpoch: number; narrations: Record<Id, NarrationEntry>;
  allocations: Record<string, Record<string, Id>>; allocationSeq: number;
  idempotency: Record<string, { hash: string; response: unknown }>;
  rollSeq: number; rolls: Record<string, RollRecord>;
}

interface LocalOptions {
  worldId?: Id;
  /** Deterministic d20 source for tests/acceptance. Defaults to Web Crypto. */
  roll?: () => number;
  onPersist?: (snapshot: PersistedRecord) => void;
}

function now(): number { return Date.now(); }
function versionBlock() {
  return { protocolVersion: 2 as const, engineVersion: ENGINE, schemaVersion: SCHEMA, canonicalVersion: CANONICAL, serverTimeEpochMilli: now() };
}

const ERROR_CATALOG: Record<ErrorCode, { httpStatus: number; retryable: boolean; clientAction: ErrorResponse['error']['clientAction'] }> = {
  narration_blocked: { httpStatus: 409, retryable: true, clientAction: 'wait_narration' },
  cache_missing: { httpStatus: 409, retryable: false, clientAction: 'regenerate_narration' },
  claim_expired: { httpStatus: 409, retryable: false, clientAction: 'regenerate_narration' },
  claim_fenced: { httpStatus: 409, retryable: false, clientAction: 'refresh_context' },
  paused: { httpStatus: 409, retryable: false, clientAction: 'resolve_gate' },
  stale_epoch: { httpStatus: 409, retryable: false, clientAction: 'reacquire_lease' },
  lease_invalid: { httpStatus: 409, retryable: false, clientAction: 'reacquire_lease' },
  revision_mismatch: { httpStatus: 409, retryable: false, clientAction: 'refresh_context' },
  phase_invalid: { httpStatus: 409, retryable: false, clientAction: 'refresh_context' },
  version_mismatch: { httpStatus: 409, retryable: false, clientAction: 'refresh_context' },
  protocol_version_unsupported: { httpStatus: 400, retryable: false, clientAction: 'none' },
  request_id_reused: { httpStatus: 409, retryable: false, clientAction: 'fix_request' },
  request_in_progress: { httpStatus: 409, retryable: true, clientAction: 'retry_same_request' },
  point_time_locked: { httpStatus: 409, retryable: false, clientAction: 'fix_request' },
  frozen_work_missing: { httpStatus: 409, retryable: false, clientAction: 'pause' },
  frozen_work_corrupt: { httpStatus: 409, retryable: false, clientAction: 'pause' },
  preview_budget_exceeded: { httpStatus: 413, retryable: false, clientAction: 'fix_request' },
  request_malformed: { httpStatus: 400, retryable: false, clientAction: 'fix_request' },
};

class Refusal extends Error {
  constructor(readonly code: ErrorCode, detail: string, readonly details: Record<string, Json> = {}) { super(`${code}: ${detail}`); }
}

function refuse(code: ErrorCode, detail: string, details: Record<string, Json> = {}): never { throw new Refusal(code, detail, details); }

function same(a: unknown, b: unknown): boolean { return canonicalJson(a) === canonicalJson(b); }
function uniqSorted(values: Id[]): Id[] { return [...new Set(values)].sort(); }
function hasContent(delta: EntityDelta): boolean {
  return delta.positionSet != null || (delta.appearanceChanges?.length ?? 0) > 0
    || (delta.personalityChanges?.length ?? 0) > 0 || delta.sanitySet != null
    || (delta.tasksAchieved?.length ?? 0) > 0 || (delta.subtasksAdded?.length ?? 0) > 0;
}

function newNarration(record: PersistedRecord, pointId: Id, generation = 1): void {
  record.narrations[pointId] = { status: 'pending', text: null, generation, claim: null };
}

function clearGate(record: PersistedRecord): void {
  record.control.gate = { status: 'none', generation: null, issuedAtEpochMilli: null, expiresAtEpochMilli: null };
}

function headEntry(record: PersistedRecord): NarrationEntry {
  return record.narrations[record.headPointId] ?? { status: 'missing', text: null, generation: 0, claim: null };
}

function roster(record: PersistedRecord): Id[] { return Object.keys(record.state.characters).sort(); }

function validateUnit(record: PersistedRecord, unit: SettlementGroup): void {
  const characters = new Set(roster(record));
  for (const actor of unit.actorIds) if (!characters.has(actor)) refuse('request_malformed', `actor ${actor} is not a world character`);
  const characterOnly = new Set([...Object.keys(unit.tasksAchieved), ...Object.keys(unit.personalities), ...Object.keys(unit.sanities), ...Object.keys(unit.subtasksAdded)]);
  for (const id of characterOnly) if (!characters.has(id)) refuse('request_malformed', `character key ${id} is not a world character`);
  if (new Set(unit.taskCoverageIds).size !== characters.size || ![...characters].every((id) => unit.taskCoverageIds.includes(id))) {
    refuse('request_malformed', 'task coverage must list the full character set');
  }
  const expectedPersonality = Object.values(unit.tasksAchieved).some((list) => list.length > 0) ? [...characters].sort() : [];
  if (new Set(unit.personalityCoverageIds).size !== expectedPersonality.length
    || !expectedPersonality.every((id) => unit.personalityCoverageIds.includes(id))) {
    refuse('request_malformed', 'personality coverage must be empty without achieved tasks, else the full cast');
  }
  if (same(Object.keys(unit.sanities).sort(), Object.keys(unit.personalities).sort()) === false) {
    refuse('request_malformed', 'personality changes and sanity recalculation must pair');
  }
  if (Object.keys(unit.personalities).length && !Object.values(unit.tasksAchieved).some((list) => list.length > 0)) {
    refuse('request_malformed', 'personality stage requires newly achieved tasks');
  }
  for (const id of Object.keys(unit.personalities)) {
    if (!unit.personalityCoverageIds.includes(id)) refuse('request_malformed', `personality change ${id} falls outside the declared coverage`);
  }
}

function validateCommitGroups(record: PersistedRecord, groups: SettlementGroup[]): void {
  const seenGroups = new Set<Id>();
  const seenActors = new Set<Id>();
  for (const unit of groups) {
    if (unit.groupId != null) {
      if (seenGroups.has(unit.groupId)) refuse('request_malformed', `duplicate group ${unit.groupId}`);
      seenGroups.add(unit.groupId);
    }
    for (const actor of unit.actorIds) {
      if (seenActors.has(actor)) refuse('request_malformed', `actor ${actor} acts in two units of one point`);
      seenActors.add(actor);
    }
    validateUnit(record, unit);
  }
}

function handledPrefix(visited: Id[], order: Id[]): number {
  let prefix = 0;
  const set = new Set(visited);
  for (const slot of order) {
    if (set.has(slot)) prefix += 1;
    else break;
  }
  return prefix;
}

function consume(status: Working['intentStatus']): Working['intentStatus'] {
  return status === 'pending' ? 'consumed' : status;
}

function stageWorking(working: Working, unitId: Id, actors: Id[], order: Id[]): Working {
  const overlap = actors.filter((actor) => working.actedIds.includes(actor));
  if (overlap.length) refuse('request_malformed', `actors ${overlap.sort().join(',')} already acted in this round`);
  const visited = uniqSorted([...working.visitedIds, ...actors]);
  const acted = uniqSorted([...working.actedIds, ...actors]);
  return { cursor: handledPrefix(visited, order), actedIds: acted, visitedIds: visited,
    settledUnitIds: [...working.settledUnitIds, unitId], intentStatus: consume(working.intentStatus) };
}

function skipWorking(working: Working, slotActor: Id, order: Id[]): Working {
  const visited = uniqSorted([...working.visitedIds, slotActor]);
  return { ...working, cursor: handledPrefix(visited, order), visitedIds: visited, intentStatus: consume(working.intentStatus) };
}

function scanWorking(working: Working, order: Id[]): Working {
  return { ...working, cursor: order.length, visitedIds: [...order] };
}

function timeAdvanceValid(kind: WorkRecord['kind'], time: TimeAdvance): boolean {
  if (kind === 'normal') return time.boundary === 'elapsed';
  return time.boundary === 'instant' && (kind !== 'instant' || time.duration.amount === 0);
}

function asErrorResponse(record: PersistedRecord, operation: WorldOperation | null, requestId: Id | null, code: ErrorCode, details: Record<string, Json> = {}): Promise<ErrorResponse> {
  const entry = ERROR_CATALOG[code];
  return Promise.all([worldView(record), controlView(record), workView(record)]).then(([world, control, work]) => ({
    ...versionBlock(), replayed: false, operation, requestId, worldId: record.worldId,
    error: { code, httpStatus: entry.httpStatus, retryable: entry.retryable, clientAction: entry.clientAction, details },
    world, control, work,
  }));
}

async function controlView(record: PersistedRecord): Promise<ControlState> {
  const entry = headEntry(record);
  const blocked = new Set<ControlState['blockedReasons'][number]>();
  if (record.control.paused) blocked.add('paused');
  if (record.control.gate.status === 'pending') blocked.add('narration_pending');
  if (entry.status === 'failed') blocked.add('narration_failed');
  if (entry.status === 'missing') blocked.add('cache_missing');
  if (!record.lease) blocked.add('lease_invalid');
  return {
    phase: record.control.phase, paused: record.control.paused, revision: record.control.revision,
    gate: { ...record.control.gate }, blockedReasons: [...blocked].sort() as ControlState['blockedReasons'], canCompute: blocked.size === 0,
  };
}

async function worldView(record: PersistedRecord): Promise<WorldContext> {
  const entry = headEntry(record);
  const advance = record.advance;
  const round = record.round;
  return {
    worldId: record.worldId,
    head: { pointId: record.headPointId, version: record.version,
      stateDigest: record.pointStates[record.headPointId]?.stateDigest ?? '', narrationStatus: entry.status },
    advance: advance
      ? { advanceId: advance.advanceId, inputId: advance.inputId, intentStatus: advance.intentStatus, inputAvailable: true }
      : { advanceId: null, inputId: null, intentStatus: 'expired', inputAvailable: false },
    round: round ? { roundId: round.roundId, trigger: round.trigger, order: [...round.order], cursor: round.cursor,
      actedIds: [...round.actedIds], visitedIds: [...round.visitedIds], conclusion: round.conclusion } : null,
    time: clone(record.state.time),
    lease: record.lease ? { fenceEpoch: record.lease.fenceEpoch, expiresAtEpochMilli: record.lease.expiresAtEpochMilli } : null,
    successor: record.work?.successor ?? null,
    activePointId: record.work?.pointId ?? null,
    activeRoundId: round?.roundId ?? null,
  };
}

async function workView(record: PersistedRecord): Promise<PointWork | null> {
  const work = record.work;
  if (!work) return null;
  return {
    pointId: work.pointId, kind: work.kind, timeAdvance: clone(work.timeAdvance), timeLocked: work.timeLocked,
    sealed: work.sealed, prefixDigest: work.prefixDigest, predecessorWorkDigest: null,
    timeScanComplete: work.timeScanComplete, baseline: { ...work.baseline },
    phase: work.phase, working: clone(work.working),
    settledUnits: work.units.map((unit) => ({ unitId: unit.unitId, groupId: unit.groupId, memberIds: [...unit.memberIds], contentHash: unit.contentHash })),
    pendingGroup: work.pendingGroup ? { groupId: work.pendingGroup.groupId, sourceId: work.pendingGroup.sourceId,
      memberIds: [...work.pendingGroup.memberIds], targetIds: [...work.pendingGroup.targetIds],
      frontierIds: [...work.pendingGroup.frontierIds], closed: work.pendingGroup.closed } : null,
    successor: work.successor ?? null,
  };
}

function checkLease(record: PersistedRecord, request: { leaseToken?: Id | null; fenceEpoch?: number | null }): void {
  const lease = record.lease;
  if (!lease || request.leaseToken !== lease.leaseToken) refuse('lease_invalid', 'unknown or released lease token');
  if (request.fenceEpoch !== lease.fenceEpoch) refuse('stale_epoch', 'lease epoch has moved on');
}

function checkExpected(record: PersistedRecord, request: { expectedPointId?: Id; expectedVersion?: number; expectedCheckpointRevision?: number }): void {
  if (request.expectedPointId !== undefined
    && (request.expectedPointId !== record.headPointId || request.expectedVersion !== record.version
      || request.expectedCheckpointRevision !== record.control.revision)) {
    refuse('version_mismatch', 'head, version or checkpoint revision binding differs');
  }
}

function checkChain(record: PersistedRecord, advanceId: Id, roundId: Id): void {
  if (!record.advance || record.advance.advanceId !== advanceId || !record.round || record.round.roundId !== roundId) {
    refuse('version_mismatch', 'advance or round binding differs from the active chain');
  }
}

function checkWorkPoint(record: PersistedRecord, pointId: Id): WorkRecord {
  const work = record.work;
  if (!work) refuse('phase_invalid', 'no active point work');
  if (work.pointId !== pointId) refuse('version_mismatch', 'point binding differs from the active work');
  return work;
}

function checkHeadReady(record: PersistedRecord): void {
  if (headEntry(record).status !== 'ready') refuse('narration_blocked', 'the head narration is not ready');
}

function checkNotPaused(record: PersistedRecord): void {
  if (record.control.paused) refuse('paused', 'the controller is paused');
}

function issueGate(record: PersistedRecord, generation: number): void {
  const at = now();
  record.control.gate = { status: 'pending', generation, issuedAtEpochMilli: at, expiresAtEpochMilli: at + CLAIM_TTL };
}

function issueClaim(record: PersistedRecord, pointId: Id, mode: 'head' | 'history', generation: number): Claim {
  const at = now();
  const claim: Claim = { claimToken: `claim_${pointId}_${generation}_${Math.floor(Math.random() * 1e9).toString(36)}`,
    generation, mode, fenceEpoch: mode === 'head' ? record.lease?.fenceEpoch ?? null : null,
    issuedAtEpochMilli: at, expiresAtEpochMilli: at + CLAIM_TTL };
  const entry = record.narrations[pointId];
  entry.status = 'pending';
  entry.text = null;
  entry.generation = generation;
  entry.claim = claim;
  if (mode === 'head') issueGate(record, generation);
  return claim;
}

function claimValid(claim: Claim | null): boolean {
  return !!claim && now() < claim.expiresAtEpochMilli;
}

function createRecord(initial: InitialTemplate, worldId: Id): PersistedRecord {
  const withId = { ...initial, worldId } as InitialState;
  const state = buildInitialState(withId);
  const rootPointId = `point_root_${worldId}`;
  const record: PersistedRecord = {
    worldId, initial: clone(withId), state, version: 0, rootPointId, headPointId: rootPointId,
    points: {}, pointStates: { [rootPointId]: { version: 0, state: clone(state), stateDigest: '' } },
    advance: null, round: null, work: null,
    control: { phase: 'select_actor', paused: false, revision: 0,
      gate: { status: 'pending', generation: 1, issuedAtEpochMilli: now(), expiresAtEpochMilli: now() + CLAIM_TTL } },
    lease: { leaseToken: `lease_${worldId}_1`, fenceEpoch: 1, expiresAtEpochMilli: now() + LEASE_TTL },
    leaseEpoch: 1, narrations: {}, allocations: {}, allocationSeq: 0, idempotency: {}, rollSeq: 0, rolls: {},
  };
  newNarration(record, rootPointId);
  return record;
}

async function finishCreate(record: PersistedRecord): Promise<void> {
  record.pointStates[record.rootPointId].stateDigest = await stateDigest(record.state);
}

function allocate(record: PersistedRecord, allocationKey: Id, slots: { slotKey: Id; kind: string; scope?: Id | null }[]): { slotKey: Id; id: Id }[] {
  const bucket = record.allocations[allocationKey] ?? (record.allocations[allocationKey] = {});
  return slots.map((slot) => {
    const key = `${slot.scope ?? ''}|${slot.slotKey}`;
    if (!bucket[key]) bucket[key] = `${slot.kind}_${++record.allocationSeq}`;
    return { slotKey: slot.slotKey, id: bucket[key] };
  });
}

function handleLeaseAcquire(record: PersistedRecord, request: RequestMap['lease_acquire']): DataMap['lease_acquire'] {
  if (record.lease && now() < record.lease.expiresAtEpochMilli) refuse('lease_invalid', 'lease is held', { reason: 'lease_held' });
  const fence = Math.max(record.leaseEpoch, record.lease?.fenceEpoch ?? 0) + 1;
  record.leaseEpoch = fence;
  const lease = { leaseToken: `lease_${record.worldId}_${fence}_${Math.random().toString(36).slice(2, 8)}`, fenceEpoch: fence, expiresAtEpochMilli: now() + LEASE_TTL };
  record.lease = lease;
  return { ...lease, holderId: request.holderId };
}

function handleLeaseRenew(record: PersistedRecord, request: RequestMap['lease_renew']): DataMap['lease_renew'] {
  checkLease(record, request);
  record.lease!.expiresAtEpochMilli = Math.max(record.lease!.expiresAtEpochMilli, now() + LEASE_TTL);
  return { ...record.lease! };
}

function handleNarrationClaim(record: PersistedRecord, request: RequestMap['narration_claim']): ClaimSummary & { claimToken: Id } {
  const pointId = request.pointId;
  const entry = record.narrations[pointId];
  if (!entry) refuse('version_mismatch', 'narration requires a committed point');
  if (request.mode === 'head') {
    checkLease(record, request);
    if (pointId !== record.headPointId) refuse('version_mismatch', 'head narration targets another point');
  } else if (pointId === record.headPointId) {
    refuse('claim_fenced', 'history narration cannot target the current head');
  }
  if (request.currentClaim && (!entry.claim || entry.claim.claimToken !== request.currentClaim.claimToken
    || entry.claim.generation !== request.currentClaim.generation)) refuse('claim_fenced', 'caller holds a superseded claim');
  let claim = entry.claim;
  if (!claim || claim.mode !== request.mode || !claimValid(claim) || entry.status === 'failed' || entry.status === 'missing') {
    claim = issueClaim(record, pointId, request.mode, entry.generation + (claim ? 1 : 0));
  }
  return { pointId, mode: request.mode, claimToken: claim.claimToken, generation: claim.generation,
    fenceEpoch: claim.fenceEpoch, issuedAtEpochMilli: claim.issuedAtEpochMilli, expiresAtEpochMilli: claim.expiresAtEpochMilli };
}

function handleNarrationRenew(record: PersistedRecord, request: RequestMap['narration_claim_renew']): ClaimSummary {
  const entry = record.narrations[request.pointId];
  if (!entry?.claim || entry.claim.claimToken !== request.claimToken || entry.claim.generation !== request.generation
    || entry.claim.mode !== request.mode) refuse('claim_fenced', 'claim identity or mode has moved on');
  if (!claimValid(entry.claim)) refuse('claim_expired', 'claim authority is no longer valid');
  entry.claim.expiresAtEpochMilli = Math.max(entry.claim.expiresAtEpochMilli, now() + CLAIM_TTL);
  return { pointId: request.pointId, mode: request.mode, generation: entry.claim.generation,
    fenceEpoch: entry.claim.fenceEpoch, issuedAtEpochMilli: entry.claim.issuedAtEpochMilli, expiresAtEpochMilli: entry.claim.expiresAtEpochMilli };
}

function handleNarrationSubmit(record: PersistedRecord, request: RequestMap['narration_submit']): DataMap['narration_submit'] {
  const entry = record.narrations[request.pointId];
  if (!entry?.claim || entry.claim.claimToken !== request.claimToken || entry.claim.generation !== request.generation
    || entry.claim.mode !== request.mode) refuse('claim_fenced', 'claim identity or mode has moved on');
  if (!claimValid(entry.claim)) refuse('claim_expired', 'claim authority is no longer valid');
  if (entry.status === 'ready' && (request.outcome !== 'ready' || request.text !== entry.text)) {
    refuse('request_malformed', 'narration text is immutable within a generation');
  }
  entry.status = request.outcome;
  entry.text = request.outcome === 'ready' ? request.text : null;
  if (request.mode === 'head' && request.outcome === 'ready') {
    clearGate(record);
  }
  return { pointId: request.pointId, narrationStatus: entry.status, generation: request.generation };
}

function handleNarrationDelete(record: PersistedRecord, request: RequestMap['narration_delete']): DataMap['narration_delete'] {
  let pointId: Id | null = null;
  if (request.mode === 'head') {
    checkLease(record, request);
    pointId = record.headPointId;
  } else {
    for (const [candidate, entry] of Object.entries(record.narrations)) {
      if (entry.claim?.claimToken === request.claimToken && entry.claim.generation === request.generation && entry.claim.mode === request.mode) {
        pointId = candidate;
        break;
      }
    }
  }
  if (!pointId) refuse('claim_fenced', 'delete has no matching point claim');
  const entry = record.narrations[pointId];
  if (!entry?.claim || entry.claim.claimToken !== request.claimToken || entry.claim.generation !== request.generation) {
    refuse('claim_fenced', 'delete with a superseded or mismatched claim');
  }
  const generation = entry.generation;
  entry.status = 'missing';
  entry.text = null;
  entry.claim = null;
  entry.generation = generation + 1;
  if (pointId === record.headPointId) issueGate(record, generation + 1);
  return { pointId, narrationStatus: 'missing', invalidatedGeneration: generation };
}

function handleStartAdvance(record: PersistedRecord, request: RequestMap['checkpoint_start_advance']): DataMap['checkpoint_start_advance'] {
  checkLease(record, request);
  checkExpected(record, request);
  checkNotPaused(record);
  if (record.advance) refuse('phase_invalid', 'an active advance already exists');
  if (record.work) refuse('phase_invalid', 'a point work is still active');
  checkHeadReady(record);
  const characters = roster(record);
  if (new Set(request.order).size !== characters.length || !characters.every((id) => request.order.includes(id))) {
    refuse('request_malformed', 'a player round must freeze the complete character roster');
  }
  record.advance = { advanceId: request.advanceId, inputId: request.inputId, inputText: request.inputText, intentStatus: 'pending' };
  record.round = { roundId: request.roundId, trigger: 'player', order: [...request.order], cursor: 0, actedIds: [], visitedIds: [], conclusion: null };
  record.control.phase = 'select_actor';
  record.control.revision += 1;
  return { advanceId: request.advanceId, inputId: request.inputId, roundId: request.roundId };
}

function handleBeginPoint(record: PersistedRecord, request: RequestMap['checkpoint_begin_point']): DataMap['checkpoint_begin_point'] {
  checkLease(record, request);
  checkExpected(record, request);
  checkNotPaused(record);
  if (record.work) refuse('phase_invalid', 'a point work is still active');
  if (!record.advance || !record.round) refuse('phase_invalid', 'no active advance');
  if (request.pointId === record.rootPointId || record.points[request.pointId]) refuse('version_mismatch', 'point id is already committed');
  if (!timeAdvanceValid(request.kind, request.timeAdvance)) refuse('request_malformed', 'point time does not match its kind');
  record.work = {
    pointId: request.pointId, kind: request.kind, timeAdvance: clone(request.timeAdvance), timeLocked: false,
    sealed: false, prefixDigest: null, timeScanComplete: false, timeScan: null,
    baseline: { headPointId: record.headPointId, version: record.version, stateDigest: record.pointStates[record.headPointId].stateDigest },
    phase: 'select_actor',
    working: { cursor: record.round.cursor, actedIds: [...record.round.actedIds], visitedIds: [...record.round.visitedIds], settledUnitIds: [], intentStatus: record.advance.intentStatus },
    units: [], pendingGroup: null, successor: null,
  };
  record.control.phase = 'select_actor';
  record.control.revision += 1;
  return { pointId: request.pointId };
}

function handleDiscoverGroup(record: PersistedRecord, request: RequestMap['checkpoint_discover_group']): DataMap['checkpoint_discover_group'] {
  checkLease(record, request);
  checkExpected(record, request);
  const work = checkWorkPoint(record, request.pointId);
  checkNotPaused(record);
  if (work.sealed || work.pendingGroup) refuse('phase_invalid', 'group discovery needs an open work without a pending group');
  if (!record.round || request.initiatorId !== record.round.order[work.working.cursor]) {
    refuse('request_malformed', 'group initiator is not the next frozen character slot');
  }
  work.pendingGroup = { groupId: request.groupId, sourceId: request.initiatorId, memberIds: [request.initiatorId],
    targetIds: request.targetIds ?? [], targetIdsBySource: { [request.initiatorId]: request.targetIds ?? null },
    targetSpecsBySource: { [request.initiatorId]: null }, frontierIds: [], closed: false, actionTexts: { [request.initiatorId]: request.actionText } };
  work.phase = 'build_group';
  work.timeLocked = true;
  record.control.phase = 'build_group';
  record.control.revision += 1;
  return { groupId: request.groupId, targetIds: request.targetIds ?? null };
}

function handleExtendGroup(record: PersistedRecord, request: RequestMap['checkpoint_extend_group']): DataMap['checkpoint_extend_group'] {
  checkLease(record, request);
  checkExpected(record, request);
  const work = checkWorkPoint(record, request.pointId);
  checkNotPaused(record);
  const group = work.pendingGroup;
  if (!group || group.groupId !== request.groupId) refuse('version_mismatch', 'group binding differs from the pending group');
  if (!group.memberIds.includes(request.sourceId)) refuse('request_malformed', 'target source is not a group member');
  if ('targets' in request && request.targets != null) {
    if (group.targetIdsBySource[request.sourceId] !== null) refuse('request_malformed', 'targets are already confirmed for this member');
    group.targetIdsBySource[request.sourceId] = request.targets.map((target) => target.targetId);
    group.targetSpecsBySource[request.sourceId] = request.targets.map((target) => ({ targetId: target.targetId, triggerKey: target.triggerKey }));
    group.targetIds = [...new Set(Object.values(group.targetIdsBySource).flatMap((targets) => targets ?? []))].sort();
  } else {
    const member = request.admittedMember;
    if (!member) refuse('request_malformed', 'extend needs targets or an admitted member');
    if (!group.memberIds.includes(member.memberId)) {
      group.memberIds.push(member.memberId);
      group.targetIdsBySource[member.memberId] = null;
      group.targetSpecsBySource[member.memberId] = null;
    }
    group.actionTexts[member.memberId] = member.actionText ?? '';
    group.sourceId = member.memberId;
  }
  group.frontierIds = [...group.memberIds].filter((member) => group.actionTexts[member] == null || group.targetIdsBySource[member] === null).sort();
  record.control.revision += 1;
  return { groupId: group.groupId, memberIds: uniqSorted(group.memberIds), frontierIds: [...group.frontierIds] };
}

function handleCloseGroup(record: PersistedRecord, request: RequestMap['checkpoint_close_group']): DataMap['checkpoint_close_group'] {
  checkLease(record, request);
  checkExpected(record, request);
  const work = checkWorkPoint(record, request.pointId);
  checkNotPaused(record);
  const group = work.pendingGroup;
  if (!group || group.groupId !== request.groupId) refuse('version_mismatch', 'group binding differs from the pending group');
  if (group.memberIds.some((member) => group.targetIdsBySource[member] === null)) refuse('request_malformed', 'close needs every member target set confirmed first');
  if (group.frontierIds.length) refuse('request_malformed', 'close requires an empty reaction frontier');
  group.closed = true;
  work.phase = 'settle_group';
  record.control.phase = 'settle_group';
  record.control.revision += 1;
  return { groupId: group.groupId, closed: true };
}

async function handleStageUnit(record: PersistedRecord, request: RequestMap['checkpoint_stage_unit']): Promise<DataMap['checkpoint_stage_unit']> {
  checkLease(record, request);
  checkExpected(record, request);
  const work = checkWorkPoint(record, request.pointId);
  checkNotPaused(record);
  const group = work.pendingGroup;
  if (!group || group.groupId !== request.groupId) refuse('version_mismatch', 'group binding differs from the pending group');
  if (!group.closed) refuse('phase_invalid', 'staging requires a closed group');
  const candidates = request.candidates;
  if (candidates.groupId !== request.groupId) refuse('request_malformed', 'candidates name another group');
  if (!same([...candidates.actorIds].sort(), uniqSorted(group.memberIds))) refuse('request_malformed', 'staged actors differ from the admitted closed-group members');
  validateCommitGroups(record, [candidates]);
  const unitId = `unit_${work.units.length + 1}_${group.groupId}`;
  work.units.push({ unitId, groupId: group.groupId, memberIds: uniqSorted(candidates.actorIds), contentHash: await canonicalDigest(candidates), candidates: clone(candidates), results: clone(request.results) });
  work.working = stageWorking(work.working, unitId, candidates.actorIds, record.round!.order);
  work.pendingGroup = null;
  work.phase = 'select_actor';
  record.control.phase = 'select_actor';
  record.control.revision += 1;
  return { groupId: group.groupId, unitId, working: clone(work.working) };
}

function handleRecordSkip(record: PersistedRecord, request: RequestMap['checkpoint_record_skip']): DataMap['checkpoint_record_skip'] {
  checkLease(record, request);
  checkExpected(record, request);
  const work = checkWorkPoint(record, request.pointId);
  checkNotPaused(record);
  if (!record.round) refuse('phase_invalid', 'no active round');
  const cursor = work.working.cursor;
  if (cursor >= record.round.order.length || request.slotActorId !== record.round.order[cursor]) refuse('request_malformed', 'skip must record the current order slot');
  work.timeLocked = true;
  work.working = skipWorking(work.working, request.slotActorId, record.round.order);
  record.control.revision += 1;
  return { pointId: work.pointId, working: clone(work.working) };
}


function handleStageTimeScan(record: PersistedRecord, request: RequestMap['checkpoint_stage_time_scan']): DataMap['checkpoint_stage_time_scan'] {
  checkLease(record, request);
  checkExpected(record, request);
  const work = checkWorkPoint(record, request.pointId);
  checkNotPaused(record);
  if (work.timeScanComplete) refuse('request_malformed', 'time-scan candidates are already confirmed');
  if (request.candidates.groupId !== null) refuse('request_malformed', 'time-scan candidates cannot name a group');
  validateCommitGroups(record, [request.candidates]);
  work.timeScan = clone(request.candidates);
  work.timeScanComplete = true;
  work.timeLocked = true;
  work.working = scanWorking(work.working, record.round!.order);
  record.control.revision += 1;
  return { pointId: work.pointId, working: clone(work.working) };
}

async function handleSealPoint(record: PersistedRecord, request: RequestMap['checkpoint_seal_point']): Promise<DataMap['checkpoint_seal_point']> {
  checkLease(record, request);
  checkExpected(record, request);
  const work = checkWorkPoint(record, request.pointId);
  checkNotPaused(record);
  if (work.sealed) refuse('phase_invalid', 'point work is already sealed');
  if (!work.units.length && !work.timeScanComplete) refuse('phase_invalid', 'an empty point needs its time-scan candidates first');
  work.sealed = true;
  work.prefixDigest = await canonicalDigest({ pointId: work.pointId, kind: work.kind, baseline: work.baseline, timeAdvance: work.timeAdvance,
    timeLocked: true, working: work.working,
    settledUnits: work.units.map((unit) => ({ unitId: unit.unitId, groupId: unit.groupId, memberIds: unit.memberIds, contentHash: unit.contentHash })),
    timeScanComplete: work.timeScanComplete });
  record.control.revision += 1;
  return { pointId: work.pointId, prefixDigest: work.prefixDigest };
}

async function handlePrepareSuccessor(record: PersistedRecord, request: RequestMap['checkpoint_prepare_successor']): Promise<DataMap['checkpoint_prepare_successor']> {
  const data = await handleSealPoint(record, { ...request, operation: 'seal_point' } as never);
  const work = record.work!;
  work.successor = { pointId: request.successorPointId, predecessorPointId: work.pointId, timeAdvance: clone(request.timeAdvance),
    expectedPredecessorVersion: record.version, prefixDigest: data.prefixDigest,
    expectedPredecessorStateDigest: record.pointStates[record.headPointId].stateDigest, baseline: { ...work.baseline } };
  return { pointId: work.pointId, successorPointId: request.successorPointId, prefixDigest: data.prefixDigest, successor: clone(work.successor) };
}

function handlePause(record: PersistedRecord, request: RequestMap['checkpoint_pause']): DataMap['checkpoint_pause'] {
  checkLease(record, request);
  checkExpected(record, request);
  if (!record.control.paused) { record.control.paused = true; record.control.revision += 1; }
  return { paused: true };
}

function handleResume(record: PersistedRecord, request: RequestMap['checkpoint_resume']): DataMap['checkpoint_resume'] {
  checkLease(record, request);
  checkExpected(record, request);
  if (record.control.paused) { record.control.paused = false; record.control.revision += 1; }
  return { paused: false };
}

async function handlePreview(record: PersistedRecord, request: RequestMap['preview_point']): Promise<DataMap['preview_point']> {
  checkExpected(record, request);
  const work = checkWorkPoint(record, request.pointId);
  if (!record.advance || !record.round) refuse('phase_invalid', 'no active chain');
  if (request.advanceId !== record.advance.advanceId || request.roundId !== record.round.roundId) refuse('version_mismatch', 'preview is outside the active chain');
  if (canonicalJson(request.timeAdvance) !== canonicalJson(work.timeAdvance)) refuse('version_mismatch', 'preview time differs from the begin reservation');
  const point = buildTimelinePoint({
    worldId: record.worldId, id: request.pointId, sequence: work.baseline.version + 1, kind: work.kind,
    previousPointId: work.baseline.headPointId, roundId: request.roundId, advanceId: request.advanceId,
    trigger: record.round.trigger, linkedFromPointId: work.kind === 'normal' ? null : work.baseline.headPointId,
    timeAdvance: clone(request.timeAdvance), entityDeltas: {},
  });
  const merged = pointEntityDeltas(request.settlementGroups, null);
  const projection = { ...point, entityDeltas: clone(merged) };
  const working = applyPoint(record.state, projection);
  return { pointId: request.pointId, pointProjection: projection, mergedEntityDeltas: clone(merged),
    workingStateDigest: await stateDigest(working), pointProjectionDigest: await canonicalDigest(projection), workingState: working };
}

function handleCreateRolls(record: PersistedRecord, request: RequestMap['create_rolls'], roll: () => number): DataMap['create_rolls'] {
  checkLease(record, request);
  checkExpected(record, request);
  if (!record.advance || !record.round) refuse('phase_invalid', 'no active chain');
  const work = record.work;
  const group = work?.pendingGroup;
  if (!work || !group || !work.timeLocked || group.closed) refuse('phase_invalid', 'rolls require the active open group with locked time');
  const output: RollOutcome[] = [];
  for (const spec of request.rolls) {
    if (spec.advanceId !== record.advance.advanceId || spec.roundId !== record.round.roundId || spec.groupId !== group.groupId) {
      refuse('version_mismatch', 'judgment is outside the active chain or group');
    }
    if (!group.memberIds.includes(spec.sourceId) || !record.state.characters[spec.targetId]) refuse('request_malformed', 'judgment source or target is not an active world character');
    const confirmed = group.targetSpecsBySource[spec.sourceId];
    if (!confirmed || !confirmed.some((target) => target.targetId === spec.targetId && target.triggerKey === spec.triggerKey)) {
      refuse('request_malformed', 'judgment does not name a confirmed complete target set');
    }
    const key = [spec.sourceId, spec.targetId, spec.triggerKey].join('|');
    const existing = record.rolls[key];
    if (existing) {
      if (existing.ruleVersion !== spec.ruleVersion || existing.target !== spec.target) refuse('request_malformed', 'a fixed judgment cannot change its rule or threshold');
      output.push({ ...existing });
      continue;
    }
    const accepted = new Set(Object.entries(group.actionTexts).filter(([, action]) => action != null).map(([member]) => member));
    const eligible = !work.working.actedIds.includes(spec.targetId) && !accepted.has(spec.targetId);
    const result = spec.ruleVersion === 'reaction-d20-v1' ? roll() : 1;
    const outcome: RollRecord = { ...spec, rollId: `roll_${++record.rollSeq}`, result,
      eligibilityBaselineDigest: '', eligible, admitted: eligible && result >= spec.target, key };
    record.rolls[key] = outcome;
    output.push({ ...outcome });
  }
  return { rolls: output };
}

async function handleCommitPoint(record: PersistedRecord, request: RequestMap['commit_point']): Promise<DataMap['commit_point']> {
  const work = record.work;
  if (!work || !work.sealed) refuse('phase_invalid', 'commit requires a sealed point work');
  checkLease(record, request);
  checkExpected(record, request);
  checkChain(record, request.advanceId, request.roundId);
  checkNotPaused(record);
  if (request.pointId !== work.pointId) refuse('version_mismatch', 'commit targets another point than the sealed work');
  if (request.point.kind !== work.kind || canonicalJson(request.point.timeAdvance) !== canonicalJson(work.timeAdvance)) {
    refuse('version_mismatch', 'point kind or time differs from the sealed prefix', { reason: 'prefix_binding_mismatch' });
  }
  if (request.point.id !== work.pointId || request.point.previousPointId !== record.headPointId) refuse('version_mismatch', 'point chains from another head');
  if (request.point.advanceId !== request.advanceId || request.point.roundId !== request.roundId
    || request.point.sequence !== record.version + 1 || request.point.trigger !== record.round!.trigger) {
    refuse('version_mismatch', 'commit point metadata differs from the active chain');
  }
  const staged = work.units;
  if (request.settlementGroups.length !== staged.length) refuse('version_mismatch', 'settlementGroups differ from the sealed settledUnits', { reason: 'prefix_binding_mismatch' });
  for (let index = 0; index < staged.length; index++) {
    const unit = staged[index];
    const group = request.settlementGroups[index];
    if (unit.groupId !== group.groupId || canonicalJson(unit.memberIds) !== canonicalJson([...group.actorIds].sort())
      || unit.contentHash !== await canonicalDigest(group)) {
      refuse('version_mismatch', 'settlementGroups differ from the sealed settledUnits', { reason: 'prefix_binding_mismatch' });
    }
  }
  validateCommitGroups(record, request.settlementGroups);
  const merged = pointEntityDeltas(request.settlementGroups, work.timeScan);
  if (!same(request.point.entityDeltas, merged)) refuse('request_malformed', 'point deltas differ from the merged settlement');
  const newState = applyPoint(record.state, request.point);
  record.state = newState;
  record.version += 1;
  record.points[request.pointId] = clone(request.point);
  record.pointStates[request.pointId] = { version: record.version, state: clone(newState), stateDigest: await stateDigest(newState) };
  record.round!.cursor = work.working.cursor;
  record.round!.actedIds = [...work.working.actedIds];
  record.round!.visitedIds = [...work.working.visitedIds];
  if (record.advance) record.advance.intentStatus = work.working.intentStatus;
  record.work = null;
  record.headPointId = request.pointId;
  newNarration(record, request.pointId);
  issueGate(record, 1);
  if (record.round!.cursor === record.round!.order.length && record.round!.conclusion === null) record.control.phase = 'assess_continuation';
  else record.control.phase = 'select_actor';
  record.control.revision += 1;
  return { pointId: request.pointId, version: record.version, stateDigest: record.pointStates[request.pointId].stateDigest };
}

function handleConclude(record: PersistedRecord, request: RequestMap['round_conclusion_conclude']): DataMap['round_conclusion_conclude'] {
  checkLease(record, request);
  checkExpected(record, request);
  checkChain(record, request.advanceId, request.roundId);
  if (record.control.phase !== 'assess_continuation') refuse('phase_invalid', 'continuation is not being assessed');
  const conclusion = request.conclusion;
  if (conclusion.kind === 'continue') {
    const candidates = conclusion.candidateCharacterIds;
    if (!candidates.length || !candidates.every((id) => !!record.state.characters[id])) refuse('request_malformed', 'automatic candidates must be registered characters');
    record.round!.conclusion = { kind: 'continue', closedBy: 'model', cancelReason: null, candidateCharacterIds: [...candidates], nextRoundId: conclusion.nextRoundId };
    record.round = { roundId: conclusion.nextRoundId, trigger: 'automatic', order: [...candidates], cursor: 0, actedIds: [], visitedIds: [], conclusion: null };
    record.control.phase = 'select_actor';
    record.control.revision += 1;
    return { kind: 'continue', roundId: request.roundId, nextRoundId: conclusion.nextRoundId };
  }
  record.round!.conclusion = { kind: 'handback', closedBy: 'model', cancelReason: null };
  record.control.phase = 'complete';
  record.advance = null;
  record.control.revision += 1;
  return { kind: 'handback', roundId: request.roundId, nextRoundId: null };
}

function handleCancel(record: PersistedRecord, request: RequestMap['round_conclusion_cancel']): DataMap['round_conclusion_cancel'] {
  checkLease(record, request);
  checkExpected(record, request);
  checkChain(record, request.advanceId, request.roundId);
  checkHeadReady(record);
  const abandoned: Id[] = [];
  if (record.work?.pendingGroup) abandoned.push(record.work.pendingGroup.groupId);
  record.work = null;
  record.round!.conclusion = { kind: 'handback', closedBy: 'cancel', cancelReason: request.cancelReason };
  record.control.phase = 'complete';
  record.advance = null;
  record.control.revision += 1;
  return { roundId: request.roundId, abandonedGroupIds: abandoned };
}

function handleGetState(record: PersistedRecord, request: RequestMap['get_state']): DataMap['get_state'] {
  const pointId = request.point ?? record.headPointId;
  const cached = record.pointStates[pointId];
  if (!cached) refuse('version_mismatch', 'unknown point');
  if (pointId === record.rootPointId) {
    return { pointId, version: cached.version, state: clone(cached.state), stateDigest: cached.stateDigest,
      previousPointId: null, timeAdvance: null, entityDeltas: {} };
  }
  const point = record.points[pointId];
  return { pointId, version: cached.version, state: clone(cached.state), stateDigest: cached.stateDigest,
    previousPointId: point.previousPointId, timeAdvance: clone(point.timeAdvance), entityDeltas: clone(point.entityDeltas) };
}

function handleListPoints(record: PersistedRecord, request: RequestMap['list_points']): DataMap['list_points'] {
  const points = Object.entries(record.pointStates).map(([pointId, cached]) => {
    if (pointId === record.rootPointId) return { pointId, sequence: 0, kind: 'root' as const, roundId: null, advanceId: null, stateDigest: cached.stateDigest };
    const point = record.points[pointId];
    return { pointId, sequence: point.sequence, kind: point.kind, roundId: point.roundId, advanceId: point.advanceId, stateDigest: cached.stateDigest };
  }).sort((a, b) => a.sequence - b.sequence);
  const after = request.after ?? null;
  const filtered = after == null ? points : points.filter((point) => point.sequence > after);
  return { points: filtered.slice(0, request.limit ?? 50) };
}

function handleNarrationGet(record: PersistedRecord, scope: Scope): DataMap['narration_get'] {
  const pointId = scope.pointId ?? record.headPointId;
  const entry = record.narrations[pointId];
  if (!entry) return { pointId, narrationStatus: 'missing', generation: null, text: null };
  return { pointId, narrationStatus: entry.status, generation: entry.generation, text: entry.status === 'ready' ? entry.text : null };
}

type WriteOperation = Exclude<WorldOperation, 'get_context' | 'get_state' | 'list_points' | 'narration_get'>;

export class LocalWorldTransport implements WorldTransport {
  private record: PersistedRecord;
  private readonly options: LocalOptions;
  private readonly roll: () => number;

  private constructor(record: PersistedRecord, options: LocalOptions = {}) {
    this.record = record;
    this.options = options;
    this.roll = options.roll ?? (() => {
      const bytes = new Uint32Array(1);
      globalThis.crypto.getRandomValues(bytes);
      return (bytes[0] % 20) + 1;
    });
  }

  static async create(initial: InitialTemplate, options: LocalOptions = {}): Promise<LocalWorldTransport> {
    const worldId = options.worldId ?? `world_local_${Date.now().toString(36)}_${Math.floor(Math.random() * 1e6).toString(36)}`;
    const record = createRecord(initial, worldId);
    await finishCreate(record);
    return new LocalWorldTransport(record, options);
  }

  static async restore(snapshot: PersistedRecord, options: LocalOptions = {}): Promise<LocalWorldTransport> {
    return new LocalWorldTransport(clone(snapshot), options);
  }

  get worldId(): Id { return this.record.worldId; }
  get headPointId(): Id { return this.record.headPointId; }
  get state(): WorldState { return clone(this.record.state); }
  snapshot(): PersistedRecord { return clone(this.record); }

  async execute<K extends WorldOperation>(operation: K, request: RequestMap[K], scope: Scope): Promise<Success<K>> {
    if (operation === 'get_context') return this.readContext() as unknown as Success<K>;
    if (operation === 'get_state') return this.readState(request as RequestMap['get_state']) as unknown as Success<K>;
    if (operation === 'list_points') return this.readPoints(request as RequestMap['list_points']) as unknown as Success<K>;
    if (operation === 'narration_get') return this.readNarration(scope) as unknown as Success<K>;
    if (operation === 'preview_point') {
      const data = await handlePreview(this.record, request as RequestMap['preview_point']);
      const [world, control, work] = await Promise.all([worldView(this.record), controlView(this.record), workView(this.record)]);
      return { ...versionBlock(), operation, world, control, work, data } as unknown as Success<K>;
    }

    const write = request as unknown as { requestId?: Id };
    const requestId = write.requestId;
    if (!requestId) throw new Error(`${operation} requires requestId`);
    const requestHash = await canonicalDigest(request);
    const previous = this.record.idempotency[requestId];
    if (previous) {
      if (previous.hash !== requestHash) {
        throw new WorldApiError(await asErrorResponse(this.record, operation, requestId, 'request_id_reused'));
      }
      const replay = clone(previous.response) as Record<string, unknown>;
      replay.replayed = true;
      return replay as unknown as Success<K>;
    }

    const draft = clone(this.record);
    let data: unknown;
    try {
      data = await this.handleWrite(draft, operation as WriteOperation, request as never, scope);
    } catch (error) {
      if (error instanceof Refusal) {
        throw new WorldApiError(await asErrorResponse(this.record, operation, requestId, error.code, error.details));
      }
      if (error instanceof KernelViolation) {
        const code: ErrorCode = error.kind === 'id_unresolved' || error.kind === 'prefix_binding' ? 'version_mismatch'
          : error.kind === 'position_invalid' ? 'request_malformed' : 'request_malformed';
        throw new WorldApiError(await asErrorResponse(this.record, operation, requestId, code));
      }
      throw error;
    }

    const [world, control, work] = await Promise.all([worldView(draft), controlView(draft), workView(draft)]);
    let response: Record<string, unknown>;
    if (operation === 'create_world') {
      response = { ...versionBlock(), replayed: false, operation, requestId, requestHash, world, control, work, data };
    } else if (operation === 'get_context') {
      response = { ...versionBlock(), world, control, work, activeInput: activeInput(draft), recovery: null };
    } else {
      response = { ...versionBlock(), replayed: false, operation, requestId, requestHash, world, control, work, data };
    }
    this.record = draft;
    this.record.idempotency[requestId] = { hash: requestHash, response: clone(response) };
    const keys = Object.keys(this.record.idempotency);
    if (keys.length > 200) for (const key of keys.slice(0, keys.length - 200)) delete this.record.idempotency[key];
    this.options.onPersist?.(clone(this.record));
    return response as unknown as Success<K>;
  }

  private async handleWrite(record: PersistedRecord, operation: WriteOperation, request: any, scope: Scope): Promise<unknown> {
    switch (operation) {
      case 'create_world': {
        const requested = request.initial as InitialTemplate;
        const worldId = (requested as unknown as { worldId?: Id }).worldId ?? this.options.worldId
          ?? `world_local_${Date.now().toString(36)}_${Math.floor(Math.random() * 1e6).toString(36)}`;
        const created = createRecord(requested, worldId);
        await finishCreate(created);
        Object.assign(record, created);
        return { worldId: created.worldId, rootPointId: created.rootPointId, lease: { ...created.lease! } };
      }
      case 'lease_acquire': return handleLeaseAcquire(record, request);
      case 'lease_renew': return handleLeaseRenew(record, request);
      case 'lease_release': {
        checkLease(record, request);
        record.lease = null;
        return { released: true };
      }
      case 'allocate_ids': {
        checkLease(record, request);
        return { allocations: allocate(record, request.allocationKey, request.slots) };
      }
      case 'checkpoint_start_advance': return handleStartAdvance(record, request);
      case 'checkpoint_begin_point': return handleBeginPoint(record, request);
      case 'checkpoint_discover_group': return handleDiscoverGroup(record, request);
      case 'checkpoint_extend_group': return handleExtendGroup(record, request);
      case 'checkpoint_close_group': return handleCloseGroup(record, request);
      case 'checkpoint_stage_unit': return handleStageUnit(record, request);
      case 'checkpoint_record_skip': return handleRecordSkip(record, request);
      case 'checkpoint_stage_time_scan': return handleStageTimeScan(record, request);
      case 'checkpoint_seal_point': return handleSealPoint(record, request);
      case 'checkpoint_prepare_successor': return handlePrepareSuccessor(record, request);
      case 'checkpoint_set_point_time': {
        checkLease(record, request);
        const work = checkWorkPoint(record, request.pointId);
        if (work.timeLocked) refuse('point_time_locked', 'point time is locked');
        if (!timeAdvanceValid(work.kind, request.timeAdvance)) refuse('request_malformed', 'point time does not match its kind');
        work.timeAdvance = clone(request.timeAdvance);
        record.control.revision += 1;
        return { pointId: work.pointId, timeAdvance: clone(work.timeAdvance) };
      }
      case 'checkpoint_restore_group_work': refuse('frozen_work_missing', 'no accepted restore source in the local store', { reason: 'source_not_active' });
      case 'checkpoint_pause': return handlePause(record, request);
      case 'checkpoint_resume': return handleResume(record, request);
      case 'preview_point': return handlePreview(record, request);
      case 'create_rolls': return handleCreateRolls(record, request, this.roll);
      case 'commit_point': return handleCommitPoint(record, request);
      case 'round_conclusion_conclude': return handleConclude(record, request);
      case 'round_conclusion_cancel': return handleCancel(record, request);
      case 'narration_claim': return handleNarrationClaim(record, request);
      case 'narration_claim_renew': return handleNarrationRenew(record, request);
      case 'narration_submit': return handleNarrationSubmit(record, request);
      case 'narration_delete': return handleNarrationDelete(record, request);
      default: throw new Error(`unsupported local operation: ${operation}`);
    }
  }

  private async readContext(): Promise<Success<'get_context'>> {
    const [world, control, work] = await Promise.all([worldView(this.record), controlView(this.record), workView(this.record)]);
    return { ...versionBlock(), world, control, work, activeInput: activeInput(this.record), recovery: null } as unknown as Success<'get_context'>;
  }

  private async readState(request: RequestMap['get_state']): Promise<Success<'get_state'>> {
    const data = handleGetState(this.record, request);
    return { ...versionBlock(), world: await worldView(this.record), data } as unknown as Success<'get_state'>;
  }

  private async readPoints(request: RequestMap['list_points']): Promise<Success<'list_points'>> {
    const data = handleListPoints(this.record, request);
    return { ...versionBlock(), world: await worldView(this.record), data } as unknown as Success<'list_points'>;
  }

  private async readNarration(scope: Scope): Promise<Success<'narration_get'>> {
    const data = handleNarrationGet(this.record, scope);
    return { ...versionBlock(), world: await worldView(this.record), data } as unknown as Success<'narration_get'>;
  }
}

function activeInput(record: PersistedRecord) {
  if (record.advance && record.advance.intentStatus === 'pending') {
    return { advanceId: record.advance.advanceId, inputId: record.advance.inputId, text: record.advance.inputText };
  }
  return null;
}

