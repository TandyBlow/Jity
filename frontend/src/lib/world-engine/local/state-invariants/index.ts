/** Read-only continuity checks for a browser-local world record.
 *
 * The record is still owned by the transport; this module never writes state.
 * It rebuilds S0 from the recorded initial template, replays the committed
 * points through the same `applyPoint`/`stateDigest` kernel, and compares every
 * stored point projection and digest. It also checks the parts replay alone
 * cannot prove: the point chain, task completion monotonicity, change-id
 * uniqueness, position validity and the active advance/round/work bindings.
 *
 * This is an invariant verifier, not a second truth protocol: the expected
 * state comes from the existing kernel and the recorded point deltas. */
import { canonicalJson } from '../canonical';
import {
  applyPoint, buildInitialState, stateDigest, validateWorldPositions,
} from '../state';
import type {
  Change, Id, InitialState, StoredChange, Task, TimelinePoint, WorldState,
} from '../../types';

export type InvariantCode =
  | 'record_shape'
  | 'world_binding'
  | 'initial_invalid'
  | 'root_state_missing'
  | 'root_state_mismatch'
  | 'point_sequence_gap'
  | 'point_chain_broken'
  | 'point_state_missing'
  | 'point_state_orphan'
  | 'point_version_mismatch'
  | 'point_digest_mismatch'
  | 'point_state_mismatch'
  | 'point_apply_failed'
  | 'time_invalid'
  | 'task_unknown'
  | 'task_already_achieved'
  | 'task_duplicate_add'
  | 'task_regressed'
  | 'task_hierarchy'
  | 'change_duplicate'
  | 'position_invalid'
  | 'head_mismatch'
  | 'version_mismatch'
  | 'state_mismatch'
  | 'advance_invalid'
  | 'round_invalid'
  | 'work_invalid'
  | 'checkpoint_invalid'
  | 'commands_invalid'
  | 'evidence_shape'
  | 'history_regressed'
  | 'refresh_not_restored';


export interface InvariantIssue {
  code: InvariantCode;
  detail: string;
  pointId?: Id;
}

export interface InvariantReport {
  ok: boolean;
  worldId: Id | null;
  version: number | null;
  points: number;
  headPointId: Id | null;
  rootDigest: string | null;
  headDigest: string | null;
  replayDigest: string | null;
  errors: InvariantIssue[];
  warnings: InvariantIssue[];
}

interface StoredPointState {
  version: number;
  state: WorldState;
  stateDigest: string;
}

/** The subset of the transport record this verifier reads. Kept structural so
 * both the local transport and an exported acceptance record can be checked
 * without importing or mutating the transport class. */
export interface WorldRecordLike {
  worldId?: unknown;
  initial?: unknown;
  state?: unknown;
  version?: unknown;
  rootPointId?: unknown;
  headPointId?: unknown;
  points?: unknown;
  pointStates?: unknown;
  advance?: unknown;
  round?: unknown;
  work?: unknown;
  control?: unknown;
  commands?: unknown;
  checkpoint?: unknown;
}

export interface SessionSnapshotLike {
  transport?: unknown;
  commands?: unknown;
  checkpoint?: unknown;
}

function issue(code: InvariantCode, detail: string, pointId?: Id): InvariantIssue {
  return pointId ? { code, detail, pointId } : { code, detail };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function isNonBlankString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function same(left: unknown, right: unknown): boolean {
  return canonicalJson(left) === canonicalJson(right);
}

function storedChangeIds(changes: StoredChange[] | undefined): Set<Id> {
  return new Set((changes ?? []).map((change) => change.id));
}

function taskMap(state: WorldState, entityId: Id): Record<Id, Task> | null {
  return state.characters[entityId]?.tasks ?? null;
}

/** Continuity checks that must run before a point is applied. The reference
 * kernel currently replaces a task when `subtasksAdded` reuses an existing id,
 * and appends a duplicate description id; both let a committed fact move
 * backwards. The product record must reject those points instead of writing
 * them and discovering the regression only after replay. */
export function pointContinuityIssues(state: WorldState, point: TimelinePoint): InvariantIssue[] {
  const issues: InvariantIssue[] = [];
  const pointId = point.id;
  for (const [entityId, delta] of Object.entries(point.entityDeltas ?? {})) {
    const characterTasks = taskMap(state, entityId);
    if (characterTasks) {
      for (const taskId of delta.tasksAchieved ?? []) {
        const task = characterTasks[taskId];
        if (!task) {
          issues.push(issue('task_unknown', `${entityId} has no task ${taskId}`, pointId));
        } else if (task.status !== 'pending') {
          issues.push(issue('task_already_achieved', `${entityId}.${taskId} is already ${task.status}`, pointId));
        }
      }
      const added = new Set<Id>();
      for (const task of delta.subtasksAdded ?? []) {
        if (added.has(task.id)) {
          issues.push(issue('task_duplicate_add', `${entityId} adds task ${task.id} twice in one point`, pointId));
        } else if (characterTasks[task.id]) {
          issues.push(issue('task_duplicate_add', `${entityId} re-adds existing task ${task.id}`, pointId));
        }
        added.add(task.id);
      }
    }

    const item = state.items[entityId];
    const character = state.characters[entityId];
    const location = state.locations[entityId];
    const appearance = storedChangeIds((character ?? item ?? location)?.appearanceChanges);
    const personality = storedChangeIds(character?.personalityChanges);
    checkChangeIds(issues, delta.appearanceChanges, appearance, `${entityId}.appearanceChanges`, pointId);
    if (character) {
      checkChangeIds(issues, delta.personalityChanges, personality, `${entityId}.personalityChanges`, pointId);
    }
  }
  return issues;
}

function checkChangeIds(
  issues: InvariantIssue[],
  changes: Change[] | undefined,
  existing: Set<Id>,
  field: string,
  pointId: Id,
): void {
  const local = new Set<Id>();
  for (const change of changes ?? []) {
    if (local.has(change.id) || existing.has(change.id)) {
      issues.push(issue('change_duplicate', `${field} repeats change ${change.id}`, pointId));
    }
    local.add(change.id);
  }
}

export class RecordInvariantError extends Error {
  readonly name = 'RecordInvariantError';
  constructor(readonly report: InvariantReport) {
    super(`local_record_invariant:${report.errors.map((item) => item.code).join(',')}`);
  }
}

/** Throws before a point is committed if it would break continuity. The caller
 * keeps the record untouched; this is intended for the commit path. */
export function assertPointContinuity(state: WorldState, point: TimelinePoint): void {
  const issues = pointContinuityIssues(state, point);
  if (issues.length) {
    throw new RecordInvariantError({
      ok: false, worldId: state.worldId, version: null, points: 0, headPointId: null,
      rootDigest: null, headDigest: null, replayDigest: null, errors: issues, warnings: [],
    });
  }
}

function checkTime(point: TimelinePoint, issues: InvariantIssue[]): void {
  const advance = point.timeAdvance;
  if (!advance || !advance.duration || typeof advance.duration.amount !== 'number') {
    issues.push(issue('time_invalid', 'point has no contract timeAdvance', point.id));
    return;
  }
  if (point.kind === 'normal') {
    if (advance.boundary !== 'elapsed') {
      issues.push(issue('time_invalid', 'normal point must use an elapsed boundary', point.id));
    }
    if (point.linkedFromPointId !== null) {
      issues.push(issue('time_invalid', 'normal point must not carry linkedFromPointId', point.id));
    }
  } else {
    if (advance.boundary !== 'instant') {
      issues.push(issue('time_invalid', `${point.kind} point must use an instant boundary`, point.id));
    }
    if (advance.duration.amount !== 0) {
      issues.push(issue('time_invalid', `${point.kind} point must not advance clock time`, point.id));
    }
    if (point.linkedFromPointId !== point.previousPointId) {
      issues.push(issue('point_chain_broken', `${point.kind} point must link to its previous point`, point.id));
    }
  }
}

function checkPointAgainstState(
  state: WorldState,
  point: TimelinePoint,
  expectedSequence: number,
  expectedPrevious: Id,
  issues: InvariantIssue[],
): void {
  if (point.sequence !== expectedSequence) {
    issues.push(issue('point_sequence_gap', `expected sequence ${expectedSequence}, got ${point.sequence}`, point.id));
  }
  if (point.previousPointId !== expectedPrevious) {
    issues.push(issue('point_chain_broken', `expected previous ${expectedPrevious}, got ${point.previousPointId}`, point.id));
  }
  if (point.worldId !== state.worldId) {
    issues.push(issue('world_binding', `point world ${point.worldId} differs from ${state.worldId}`, point.id));
  }
  if (!isNonBlankString(point.roundId) || !isNonBlankString(point.advanceId)) {
    issues.push(issue('point_chain_broken', 'point has no round/advance identity', point.id));
  }
  if (point.trigger !== 'player' && point.trigger !== 'automatic') {
    issues.push(issue('point_chain_broken', `unknown trigger ${String(point.trigger)}`, point.id));
  }
  checkTime(point, issues);
  issues.push(...pointContinuityIssues(state, point));
}

function checkTaskMonotonicity(before: WorldState, after: WorldState, pointId: Id, issues: InvariantIssue[]): void {
  for (const [entityId, previous] of Object.entries(before.characters)) {
    const current = after.characters[entityId];
    if (!current) {
      issues.push(issue('task_regressed', `${entityId} disappeared from the character registry`, pointId));
      continue;
    }
    for (const [taskId, task] of Object.entries(previous.tasks)) {
      if (task.status === 'achieved' && current.tasks[taskId]?.status !== 'achieved') {
        issues.push(issue('task_regressed', `${entityId}.${taskId} moved from achieved to ${current.tasks[taskId]?.status ?? 'missing'}`, pointId));
      }
    }
  }
}

function checkActiveChain(record: Record<string, unknown>, state: WorldState, headDigest: string, issues: InvariantIssue[], warnings: InvariantIssue[]): void {
  const advance = record.advance;
  const round = record.round;
  const work = record.work;
  if (advance != null && !isRecord(advance)) {
    issues.push(issue('advance_invalid', 'advance is not an object'));
  }
  if (round != null && !isRecord(round)) {
    issues.push(issue('round_invalid', 'round is not an object'));
  }
  if (work != null && !isRecord(work)) {
    issues.push(issue('work_invalid', 'work is not an object'));
  }
  const advanceRecord = isRecord(advance) ? advance : null;
  const roundRecord = isRecord(round) ? round : null;
  const workRecord = isRecord(work) ? work : null;

  if (advanceRecord && !roundRecord) {
    issues.push(issue('advance_invalid', 'an active advance must have an active round'));
  }
  if (!advanceRecord && roundRecord && roundRecord.conclusion == null) {
    issues.push(issue('round_invalid', 'a round without an active advance must be concluded'));
  }
  if (advanceRecord) {
    if (!isNonBlankString(advanceRecord.advanceId) || !isNonBlankString(advanceRecord.inputId)) {
      issues.push(issue('advance_invalid', 'advance identity or input identity is missing'));
    }
    if (!['pending', 'consumed', 'expired'].includes(String(advanceRecord.intentStatus))) {
      issues.push(issue('advance_invalid', `unknown intentStatus ${String(advanceRecord.intentStatus)}`));
    }
  }
  if (roundRecord) {
    const order = roundRecord.order;
    if (!isStringArray(order) || order.length === 0) {
      issues.push(issue('round_invalid', 'round.order must be a non-empty string list'));
    } else {
      if (new Set(order).size !== order.length) issues.push(issue('round_invalid', 'round.order repeats a character'));
      for (const id of order) if (!state.characters[id]) issues.push(issue('round_invalid', `round.order has unknown character ${id}`));
      const cursor = roundRecord.cursor;
      if (typeof cursor !== 'number' || !Number.isInteger(cursor) || cursor < 0 || cursor > order.length) {
        issues.push(issue('round_invalid', `round.cursor ${String(cursor)} is outside 0..${order.length}`));
      }
      for (const field of ['actedIds', 'visitedIds'] as const) {
        const values = roundRecord[field];
        if (!isStringArray(values)) {
          issues.push(issue('round_invalid', `round.${field} must be a string list`));
        } else {
          if (new Set(values).size !== values.length) issues.push(issue('round_invalid', `round.${field} repeats an id`));
          for (const id of values) if (!order.includes(id)) issues.push(issue('round_invalid', `round.${field} has ${id} outside the frozen order`));
        }
      }
      if (roundRecord.trigger === 'player' && order.length !== Object.keys(state.characters).length) {
        issues.push(issue('round_invalid', 'a player round must freeze the complete character roster'));
      }
      if (isStringArray(roundRecord.visitedIds) && typeof roundRecord.cursor === 'number') {
        const visited = new Set(roundRecord.visitedIds);
        let prefix = 0;
        for (const id of order) {
          if (!visited.has(id)) break;
          prefix += 1;
        }
        if (roundRecord.cursor !== prefix) {
          issues.push(issue('round_invalid', `round.cursor ${roundRecord.cursor} differs from the visited prefix ${prefix}`));
        }
      }
    }
    if (roundRecord.trigger !== 'player' && roundRecord.trigger !== 'automatic') {
      issues.push(issue('round_invalid', `unknown round trigger ${String(roundRecord.trigger)}`));
    }
    if (advanceRecord == null && roundRecord.conclusion == null) {
      issues.push(issue('round_invalid', 'a completed round without an active advance must have a conclusion'));
    }
    if (advanceRecord != null && roundRecord.conclusion != null) {
      issues.push(issue('round_invalid', 'an active advance cannot already have a conclusion'));
    }
  }
  if (workRecord) {
    if (advanceRecord == null || roundRecord == null) {
      issues.push(issue('work_invalid', 'active work requires an active advance and round'));
    }
    if (!isNonBlankString(workRecord.pointId)) issues.push(issue('work_invalid', 'work.pointId is missing'));
    if (record.points && isRecord(record.points) && typeof workRecord.pointId === 'string' && record.points[workRecord.pointId]) {
      issues.push(issue('work_invalid', `work point ${workRecord.pointId} is already committed`));
    }
    const baseline = workRecord.baseline;
    if (!isRecord(baseline)) {
      issues.push(issue('work_invalid', 'work has no baseline'));
    } else {
      if (baseline.headPointId !== record.headPointId) issues.push(issue('work_invalid', 'work baseline head differs from the current head'));
      if (baseline.version !== record.version) issues.push(issue('work_invalid', 'work baseline version differs from the current version'));
      if (baseline.stateDigest !== headDigest) issues.push(issue('work_invalid', 'work baseline digest differs from the head digest'));
    }
    const working = workRecord.working;
    if (isRecord(working)) {
      if (!['pending', 'consumed', 'expired'].includes(String(working.intentStatus))) {
        issues.push(issue('advance_invalid', `unknown work intentStatus ${String(working.intentStatus)}`));
      } else if (advanceRecord && working.intentStatus !== advanceRecord.intentStatus) {
        // The working copy is consumed as soon as an actor settles; the
        // authoritative advance record is updated at commit. A difference is
        // expected mid-settlement, not a broken record.
        warnings.push(issue('advance_invalid', 'work intentStatus differs from the active advance (expected before commit)'));
      }
    }
  }
  const control = record.control;
  if (isRecord(control)) {
    if (typeof control.revision !== 'number' || !Number.isInteger(control.revision) || control.revision < 0) {
      issues.push(issue('work_invalid', 'control.revision must be a non-negative integer'));
    }
    if (control.phase === 'complete' && (advanceRecord != null || workRecord != null)) {
      issues.push(issue('advance_invalid', 'phase complete still has an active advance or work'));
    }
  } else {
    warnings.push(issue('work_invalid', 'record has no control block to inspect'));
  }
}

/** Verify one transport record. Never mutates the argument; replay uses fresh
 * clones from `buildInitialState` and `applyPoint`. */
export async function verifyWorldRecord(value: unknown): Promise<InvariantReport> {
  const report: InvariantReport = {
    ok: false, worldId: null, version: null, points: 0, headPointId: null,
    rootDigest: null, headDigest: null, replayDigest: null, errors: [], warnings: [],
  };
  if (!isRecord(value)) {
    report.errors.push(issue('record_shape', 'record is not an object'));
    return report;
  }
  const record = value as WorldRecordLike;
  if (!isNonBlankString(record.worldId)) {
    report.errors.push(issue('record_shape', 'record.worldId is missing'));
    return report;
  }
  report.worldId = record.worldId;
  if (typeof record.version !== 'number' || !Number.isInteger(record.version) || record.version < 0) {
    report.errors.push(issue('record_shape', 'record.version must be a non-negative integer'));
  } else {
    report.version = record.version;
  }
  if (!isNonBlankString(record.rootPointId)) {
    report.errors.push(issue('record_shape', 'record.rootPointId is missing'));
    return report;
  }
  if (!isNonBlankString(record.headPointId)) {
    report.errors.push(issue('record_shape', 'record.headPointId is missing'));
    return report;
  }
  report.headPointId = record.headPointId;
  if (!isRecord(record.points) || !isRecord(record.pointStates)) {
    report.errors.push(issue('record_shape', 'record.points/pointStates must be objects'));
    return report;
  }
  if (record.initial == null) {
    report.errors.push(issue('initial_invalid', 'record has no initial template to rebuild S0'));
    return report;
  }
  if (!isRecord(record.state)) {
    report.errors.push(issue('record_shape', 'record.state is missing'));
    return report;
  }

  let s0: WorldState;
  try {
    s0 = buildInitialState(record.initial as InitialState);
  } catch (error) {
    report.errors.push(issue('initial_invalid', `S0 construction failed: ${(error as Error).message}`));
    return report;
  }
  if (s0.worldId !== record.worldId) {
    report.errors.push(issue('world_binding', `S0 world ${s0.worldId} differs from record ${record.worldId}`));
  }
  const rootDigest = await stateDigest(s0);
  report.rootDigest = rootDigest;
  const rootState = (record.pointStates as Record<string, unknown>)[record.rootPointId];
  if (!isRecord(rootState)) {
    report.errors.push(issue('root_state_missing', `pointStates has no root ${record.rootPointId}`));
  } else {
    if (rootState.version !== 0) report.errors.push(issue('root_state_mismatch', 'root point state version is not 0'));
    if (!same(rootState.state, s0)) report.errors.push(issue('root_state_mismatch', 'root point state differs from rebuilt S0'));
    if (rootState.stateDigest !== rootDigest) report.errors.push(issue('root_state_mismatch', 'root point state digest differs from rebuilt S0'));
  }

  const pointIds = Object.keys(record.points as Record<string, unknown>);
  const points: TimelinePoint[] = [];
  for (const id of pointIds) {
    const point = (record.points as Record<string, unknown>)[id];
    if (!isRecord(point)) {
      report.errors.push(issue('point_state_missing', `point ${id} is not an object`, id));
      continue;
    }
    points.push(point as unknown as TimelinePoint);
  }
  points.sort((left, right) => (left.sequence ?? 0) - (right.sequence ?? 0));
  report.points = points.length;
  const expectedVersion = points.length;
  if (report.version != null && report.version !== expectedVersion) {
    report.errors.push(issue('version_mismatch', `record.version ${report.version} differs from ${expectedVersion} committed points`));
  }

  const stateEntries = record.pointStates as Record<string, unknown>;
  for (const id of Object.keys(stateEntries)) {
    if (id !== record.rootPointId && !(record.points as Record<string, unknown>)[id]) {
      report.errors.push(issue('point_state_orphan', `pointStates has orphan ${id}`, id));
    }
  }

  let replay = s0;
  let previousId = record.rootPointId;
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index];
    if (!isNonBlankString(point.id)) {
      report.errors.push(issue('point_chain_broken', 'point id is missing'));
      break;
    }
    checkPointAgainstState(replay, point, index + 1, previousId, report.errors);
    const before = replay;
    let after: WorldState;
    try {
      after = applyPoint(before, point);
    } catch (error) {
      report.errors.push(issue('point_apply_failed', `replay failed: ${(error as Error).message}`, point.id));
      break;
    }
    checkTaskMonotonicity(before, after, point.id, report.errors);
    if (after.time.instantOrdinal < before.time.instantOrdinal) {
      report.errors.push(issue('time_invalid', `time moved backwards: ${before.time.instantOrdinal} -> ${after.time.instantOrdinal}`, point.id));
    }
    const digest = await stateDigest(after);
    const stored = stateEntries[point.id];
    if (!isRecord(stored)) {
      report.errors.push(issue('point_state_missing', `pointStates has no ${point.id}`, point.id));
    } else {
      if (stored.version !== point.sequence) {
        report.errors.push(issue('point_version_mismatch', `stored version ${String(stored.version)} differs from sequence ${point.sequence}`, point.id));
      }
      if (stored.stateDigest !== digest) {
        report.errors.push(issue('point_digest_mismatch', `stored digest ${String(stored.stateDigest)} differs from replay ${digest}`, point.id));
      }
      if (!same(stored.state, after)) {
        report.errors.push(issue('point_state_mismatch', 'stored state differs from replayed state', point.id));
      }
    }
    replay = after;
    previousId = point.id;
  }

  report.replayDigest = await stateDigest(replay);
  const expectedHead = points.length ? points[points.length - 1].id : record.rootPointId;
  if (record.headPointId !== expectedHead) {
    report.errors.push(issue('head_mismatch', `head ${record.headPointId} differs from last point ${expectedHead}`));
  }
  const headState = stateEntries[record.headPointId];
  if (!isRecord(headState)) {
    report.errors.push(issue('point_state_missing', `head ${record.headPointId} has no cached state`));
  } else {
    if (headState.stateDigest !== report.replayDigest) {
      report.errors.push(issue('point_digest_mismatch', `head digest ${String(headState.stateDigest)} differs from replay ${report.replayDigest}`));
    }
    report.headDigest = typeof headState.stateDigest === 'string' ? headState.stateDigest : null;
    if (!same(headState.state, replay)) {
      report.errors.push(issue('state_mismatch', 'head cached state differs from replayed state'));
    }
  }
  if (!same(record.state, replay)) {
    report.errors.push(issue('state_mismatch', 'record.state differs from replayed head state'));
  }
  for (const error of validateWorldPositions(replay)) {
    report.errors.push(issue('position_invalid', error));
  }
  for (const error of validateTaskHierarchy(replay)) {
    report.errors.push(issue('task_hierarchy', error));
  }
  // A tampered cache can carry a broken hierarchy that is absent from replay;
  // report it on the stored state too instead of only flagging the mismatch.
  for (const stored of [headState, record.state]) {
    if (!isRecord(stored)) continue;
    const state = (isRecord(stored.state) ? stored.state : stored) as unknown as WorldState;
    for (const error of validateTaskHierarchy(state)) {
      report.errors.push(issue('task_hierarchy', `stored: ${error}`));
    }
  }
  checkActiveChain(record as Record<string, unknown>, replay, report.replayDigest, report.errors, report.warnings);

  report.ok = report.errors.length === 0;
  return report;
}

/** Verify the persisted session envelope, including the scheduler checkpoint.
 * The checkpoint is a resume hint only; it is validated structurally and never
 * allowed to introduce game facts. */
export async function verifySessionSnapshot(value: unknown): Promise<InvariantReport> {
  if (!isRecord(value)) {
    const report = emptyReport('session snapshot is not an object');
    return report;
  }
  const snapshot = value as SessionSnapshotLike;
  const transport = snapshot.transport ?? value;
  const report = await verifyWorldRecord(transport);
  if (snapshot.commands !== undefined) {
    if (!isStringArray(snapshot.commands) || snapshot.commands.some((command) => !command.trim())) {
      report.errors.push(issue('commands_invalid', 'commands must be a list of non-blank strings'));
    }
  }
  if (snapshot.checkpoint !== undefined && snapshot.checkpoint !== null) {
    const checkpoint = snapshot.checkpoint;
    if (!isRecord(checkpoint) || !isNonBlankString(checkpoint.roundId) || !Array.isArray(checkpoint.plan)
      || typeof checkpoint.planIndex !== 'number' || !Number.isInteger(checkpoint.planIndex) || checkpoint.planIndex < 0) {
      report.errors.push(issue('checkpoint_invalid', 'scheduler checkpoint is not a valid resume hint'));
    }
  }
  report.ok = report.errors.length === 0;
  return report;
}

function emptyReport(detail: string): InvariantReport {
  return {
    ok: false, worldId: null, version: null, points: 0, headPointId: null,
    rootDigest: null, headDigest: null, replayDigest: null,
    errors: [issue('evidence_shape', detail)], warnings: [],
  };
}

/** A turn log entry from 09 can carry a full snapshot, or a before/point/after
 * triple. This checks the triple with the same kernel and returns one report. */
export async function verifyTurnEntry(entry: unknown): Promise<InvariantReport> {
  if (!isRecord(entry)) return emptyReport('turn entry is not an object');
  const snapshot = entry.snapshot ?? entry.transport ?? entry.record;
  if (snapshot != null) return verifySessionSnapshot(snapshot);
  const before = entry.before ?? entry.stateBefore;
  const after = entry.after ?? entry.stateAfter;
  const point = entry.point ?? entry.delta;
  if (!isRecord(before) || !isRecord(point)) {
    return emptyReport('turn entry has neither a snapshot nor before+point');
  }
  const report: InvariantReport = {
    ok: false, worldId: null, version: null, points: 0, headPointId: null,
    rootDigest: null, headDigest: null, replayDigest: null, errors: [], warnings: [],
  };
  let replayed: WorldState;
  try {
    const start = before as unknown as WorldState;
    const issues = pointContinuityIssues(start, point as unknown as TimelinePoint);
    report.errors.push(...issues);
    replayed = applyPoint(start, point as unknown as TimelinePoint);
    report.replayDigest = await stateDigest(replayed);
  } catch (error) {
    report.errors.push(issue('point_apply_failed', `turn replay failed: ${(error as Error).message}`));
    return report;
  }
  if (after != null) {
    const digest = await stateDigest(after as WorldState);
    if (digest !== report.replayDigest) {
      report.errors.push(issue('point_digest_mismatch', `turn after digest ${digest} differs from replay ${report.replayDigest}`));
    }
    if (!same(after, replayed)) report.errors.push(issue('point_state_mismatch', 'turn after state differs from replay'));
  }
  for (const error of validateWorldPositions(replayed)) report.errors.push(issue('position_invalid', error));
  for (const error of validateTaskHierarchy(replayed)) report.errors.push(issue('task_hierarchy', error));
  report.ok = report.errors.length === 0;
  return report;
}

/** Optional check for 09's page-visible acceptance summary. That file does not
 * contain a full transport record, so this is not a replay: it only checks
 * monotonic history/task continuity and the refresh marker. A full snapshot is
 * still required for the S0+delta invariant checks. */
export interface VisibleStateLike {
  historyCount?: unknown;
  place?: unknown;
  tasks?: unknown;
}

export interface VisibleTurnLike {
  before?: unknown;
  after?: unknown;
  text?: unknown;
  historyDelta?: unknown;
  problems?: unknown;
  refreshMidSettle?: unknown;
}

function visibleHistory(value: unknown): number | null {
  if (!isRecord(value)) return null;
  const raw = value.historyCount;
  if (typeof raw === 'number' && Number.isInteger(raw)) return raw;
  if (typeof raw === 'string' && /^\d+$/.test(raw)) return Number(raw);
  return null;
}

function visibleTasks(value: unknown): Map<string, boolean> | null {
  if (!isRecord(value) || !Array.isArray(value.tasks)) return null;
  const tasks = new Map<string, boolean>();
  for (const task of value.tasks) {
    if (!isRecord(task) || typeof task.goal !== 'string' || typeof task.done !== 'boolean') continue;
    tasks.set(task.goal, task.done);
  }
  return tasks;
}

export function verifyVisibleAcceptance(entries: unknown[]): { ok: boolean; errors: InvariantIssue[]; warnings: InvariantIssue[] } {
  const errors: InvariantIssue[] = [];
  const warnings: InvariantIssue[] = [];
  const seenDone = new Map<string, boolean>();
  let lastHistory: number | null = null;
  let sawSnapshot = false;
  for (const raw of entries) {
    if (!isRecord(raw)) continue;
    const entry = raw as VisibleTurnLike;
    if ('snapshot' in raw || 'transport' in raw || 'record' in raw) sawSnapshot = true;
    const before = visibleHistory(entry.before);
    const after = visibleHistory(entry.after);
    if (before != null) {
      if (lastHistory != null && before < lastHistory) {
        errors.push(issue('history_regressed', `history count fell from ${lastHistory} to ${before}`));
      }
      lastHistory = before;
    }
    if (before != null && after != null) {
      if (after < before) errors.push(issue('history_regressed', `history count fell from ${before} to ${after}`));
      const recorded = typeof entry.historyDelta === 'number' ? entry.historyDelta : after - before;
      const problems = isStringArray(entry.problems) ? entry.problems : [];
      const exceptional = problems.some((problem) => /timeout|error|cancel|refresh/i.test(problem));
      if (!exceptional && typeof entry.text === 'string' && entry.text.length > 0 && recorded !== 1) {
        errors.push(issue('history_regressed', `a completed turn added ${recorded} history entries instead of 1`));
      }
      lastHistory = after;
    }
    const tasks = visibleTasks(entry.after) ?? visibleTasks(entry.before);
    if (tasks) {
      for (const [goal, done] of seenDone) {
        if (done && tasks.get(goal) === false) {
          errors.push(issue('task_regressed', `visible task returned to not-done: ${goal}`));
        }
      }
      for (const [goal, done] of tasks) seenDone.set(goal, done);
    }
    if (entry.refreshMidSettle != null) {
      if (!isRecord(entry.refreshMidSettle) || entry.refreshMidSettle.restored !== true) {
        errors.push(issue('refresh_not_restored', 'mid-settlement refresh was not marked restored'));
      } else if (typeof entry.refreshMidSettle.historyDelta === 'number' && entry.refreshMidSettle.historyDelta < 0) {
        errors.push(issue('history_regressed', 'history fell across a mid-settlement refresh'));
      }
    }
  }
  if (!sawSnapshot) warnings.push(issue('evidence_shape', 'no full transport snapshot in this record; only visible history/task/refresh continuity was checked'));
  return { ok: errors.length === 0, errors, warnings };
}

/** Every task must belong to its character, keep one id, and point at a parent
 * that exists in the same character. A subtask with a dangling parent is a
 * broken hierarchy even when every status is individually legal. */
export function validateTaskHierarchy(state: WorldState): string[] {
  const issues: string[] = [];
  const seen = new Map<Id, Id>();
  for (const [characterId, character] of Object.entries(state.characters)) {
    for (const [key, task] of Object.entries(character.tasks)) {
      if (!task || typeof task !== 'object') {
        issues.push(`${characterId}.${key}: task is not an object`);
        continue;
      }
      if (task.id !== key) issues.push(`${characterId}.${key}: id is ${String(task.id)}`);
      if (task.ownerId !== characterId) issues.push(`${characterId}.${key}: owner is ${String(task.ownerId)}`);
      const previousOwner = seen.get(task.id);
      if (previousOwner != null) issues.push(`task id ${task.id} appears under ${previousOwner} and ${characterId}`);
      else seen.set(task.id, characterId);
      if (task.parentTaskId != null && !character.tasks[task.parentTaskId]) {
        issues.push(`${characterId}.${key}: parent ${String(task.parentTaskId)} does not exist`);
      }
    }
  }
  return issues;
}
