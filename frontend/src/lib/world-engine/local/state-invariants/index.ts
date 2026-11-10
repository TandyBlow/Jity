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
  | 'world_mismatch'
  | 'initial_invalid'
  | 'root_state_missing'
  | 'root_state_mismatch'
  | 'point_sequence_gap'
  | 'version_regressed'
  | 'points_regressed'
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
  | 'task_coverage'
  | 'change_duplicate'
  | 'position_invalid'
  | 'head_mismatch'
  | 'version_mismatch'
  | 'state_mismatch'
  | 'advance_invalid'
  | 'roll_invalid'
  | 'round_invalid'
  | 'work_invalid'
  | 'checkpoint_invalid'
  | 'commands_invalid'
  | 'evidence_shape'
  | 'history_regressed'
  | 'history_delta'
  | 'history_missing_command'
  | 'history_text_missing'
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
  narrations?: unknown;
  advance?: unknown;
  round?: unknown;
  work?: unknown;
  control?: unknown;
  commands?: unknown;
  rolls?: unknown;
  rollSeq?: unknown;
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
      const otherTaskIds = new Set<Id>(
        Object.entries(state.characters)
          .filter(([characterId]) => characterId !== entityId)
          .flatMap(([, character]) => Object.keys(character.tasks)),
      );
      for (const task of delta.subtasksAdded ?? []) {
        if (added.has(task.id)) {
          issues.push(issue('task_duplicate_add', `${entityId} adds task ${task.id} twice in one point`, pointId));
        } else if (characterTasks[task.id]) {
          issues.push(issue('task_duplicate_add', `${entityId} re-adds existing task ${task.id}`, pointId));
        } else if (otherTaskIds.has(task.id)) {
          issues.push(issue('task_duplicate_add', `${entityId} reuses task id ${task.id} from another character`, pointId));
        }
        if (task.ownerId !== entityId) {
          issues.push(issue('task_hierarchy', `${entityId} adds task ${task.id} with owner ${task.ownerId}`, pointId));
        }
        if (task.parentTaskId != null && !characterTasks[task.parentTaskId] && !added.has(task.parentTaskId)) {
          issues.push(issue('task_hierarchy', `${entityId} adds task ${task.id} with unknown parent ${task.parentTaskId}`, pointId));
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
  checkRolls(record as Record<string, unknown>, report.errors);
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

function transportOfSnapshot(value: unknown): WorldRecordLike | null {
  if (!isRecord(value)) return null;
  const snapshot = value as SessionSnapshotLike;
  if (isRecord(snapshot.transport)) return snapshot.transport as WorldRecordLike;
  return value as WorldRecordLike;
}

function storedDigest(record: WorldRecordLike, pointId: unknown): string | null {
  if (!isNonBlankString(pointId) || !isRecord(record.pointStates)) return null;
  const entry = record.pointStates[pointId];
  if (!isRecord(entry) || typeof entry.stateDigest !== 'string') return null;
  return entry.stateDigest;
}

/** Verify a time-ordered list of full session snapshots (09 can capture one
 * after every turn with the read-only hook). Each snapshot replays its own S0
 * and chain; this cross-check additionally prevents a later file from being
 * older than an earlier one, or from silently replacing the previous head. */
export async function verifySnapshotSequence(values: unknown[]): Promise<InvariantReport> {
  const reports: InvariantReport[] = [];
  const snapshots: WorldRecordLike[] = [];
  for (const value of values) {
    const record = transportOfSnapshot(value);
    if (!record) continue;
    snapshots.push(record);
    reports.push(await verifySessionSnapshot(value));
    const display = verifyDisplayHistory(value);
    for (const warning of display.warnings) reports[reports.length - 1].warnings.push(warning);
  }
  if (reports.length === 0) return emptyReport('snapshot sequence has no full snapshot');
  const merged: InvariantReport = {
    ok: true, worldId: null, version: null, points: 0, headPointId: null,
    rootDigest: null, headDigest: null, replayDigest: null, errors: [], warnings: [],
  };
  for (let index = 0; index < reports.length; index += 1) {
    const report = reports[index];
    for (const error of report.errors) merged.errors.push(issue(error.code, `snapshot ${index + 1}: ${error.detail}`, error.pointId));
    for (const warning of report.warnings) merged.warnings.push(issue(warning.code, `snapshot ${index + 1}: ${warning.detail}`, warning.pointId));
    const record = snapshots[index];
    if (merged.worldId == null) merged.worldId = report.worldId;
    else if (report.worldId !== null && report.worldId !== merged.worldId) {
      merged.errors.push(issue('world_mismatch', `snapshot ${index + 1} world ${report.worldId} differs from ${merged.worldId}`));
    }
    const previous = index > 0 ? snapshots[index - 1] : null;
    if (previous) {
      const previousVersion = typeof previous.version === 'number' ? previous.version : null;
      const currentVersion = typeof record.version === 'number' ? record.version : null;
      if (previousVersion != null && currentVersion != null && currentVersion < previousVersion) {
        merged.errors.push(issue('version_regressed', `snapshot ${index + 1} version ${currentVersion} is older than ${previousVersion}`));
      }
      const previousPoints = isRecord(previous.points) ? Object.keys(previous.points).length : null;
      const currentPoints = isRecord(record.points) ? Object.keys(record.points).length : null;
      if (previousPoints != null && currentPoints != null && currentPoints < previousPoints) {
        merged.errors.push(issue('points_regressed', `snapshot ${index + 1} has ${currentPoints} points, fewer than ${previousPoints}`));
      }
      const previousHead = previous.headPointId;
      if (isNonBlankString(previousHead) && isRecord(record.points) && !(previousHead in record.points)) {
        merged.errors.push(issue('point_chain_broken', `snapshot ${index + 1} no longer contains the previous head ${previousHead}`, previousHead));
      }
      const previousDigest = storedDigest(previous, previousHead);
      const currentDigest = storedDigest(record, previousHead);
      if (previousDigest && currentDigest && previousDigest !== currentDigest) {
        merged.errors.push(issue('point_digest_mismatch', `snapshot ${index + 1} changed the stored digest of ${previousHead}`, String(previousHead)));
      }
    }
    merged.version = report.version ?? merged.version;
    merged.points = report.points;
    merged.headPointId = report.headPointId ?? merged.headPointId;
    merged.headDigest = report.headDigest ?? merged.headDigest;
    merged.replayDigest = report.replayDigest ?? merged.replayDigest;
  }
  merged.ok = merged.errors.length === 0;
  return merged;
}

function emptyReport(detail: string): InvariantReport {
  return {
    ok: false, worldId: null, version: null, points: 0, headPointId: null,
    rootDigest: null, headDigest: null, replayDigest: null,
    errors: [issue('evidence_shape', detail)], warnings: [],
  };
}

/** Read-only check of the player-visible history inside a full snapshot.
 * This does not replay state; it compares committed player points with the
 * command list and with the narration the page will render. */
export interface DisplayHistoryReport {
  ok: boolean;
  total: number;
  ready: number;
  errors: InvariantIssue[];
  warnings: InvariantIssue[];
}

export function verifyDisplayHistory(value: unknown): DisplayHistoryReport {
  const report: DisplayHistoryReport = { ok: false, total: 0, ready: 0, errors: [], warnings: [] };
  if (!isRecord(value)) {
    report.errors.push(issue('evidence_shape', 'display history is not a snapshot object'));
    return report;
  }
  const snapshot = value as SessionSnapshotLike;
  const record = transportOfSnapshot(value);
  if (!record) {
    report.errors.push(issue('evidence_shape', 'display history has no transport record'));
    return report;
  }
  const points = isRecord(record.points) ? Object.values(record.points) : [];
  const playerPoints = points.filter((point) => isRecord(point) && point.trigger === 'player') as Array<Record<string, unknown>>;
  report.total = playerPoints.length;
  const commands = snapshot.commands;
  if (commands !== undefined && (!isStringArray(commands) || commands.some((command) => !command.trim()))) {
    report.errors.push(issue('commands_invalid', 'commands must be a list of non-blank strings'));
  }
  if (commands !== undefined) {
    const commandCount = isStringArray(commands) ? commands.length : 0;
    if (commandCount < playerPoints.length) {
      report.errors.push(issue('history_missing_command', `snapshot has ${playerPoints.length} player points but only ${commandCount} commands`));
    } else if (commandCount > playerPoints.length) {
      report.warnings.push(issue('history_missing_command', `snapshot has ${commandCount} commands for ${playerPoints.length} committed player points; failed/cancelled inputs may be retained for resume`));
    }
  }
  const narrations = isRecord(record.narrations) ? record.narrations : null;
  for (const point of playerPoints) {
    const pointId = typeof point.id === 'string' ? point.id : null;
    if (!pointId) continue;
    const narration = narrations?.[pointId];
    if (!isRecord(narration) || narration.status !== 'ready' || typeof narration.text !== 'string' || !narration.text.trim()) {
      report.warnings.push(issue('history_text_missing', `committed point ${pointId} has no ready narration text`, pointId));
    } else {
      report.ready += 1;
    }
  }
  report.ok = report.errors.length === 0;
  return report;
}

/** A turn log entry from 09 can carry a full snapshot, or a before/point/after
 * triple. This checks the triple with the same kernel and returns one report. */
export async function verifyTurnEntry(entry: unknown): Promise<InvariantReport> {
  if (!isRecord(entry)) return emptyReport('turn entry is not an object');
  // 09 records the hook result as snapshotAfter (and optionally the pre-turn
  // snapshotBefore); older evidence used snapshot/transport/record.
  const snapshot = entry.snapshot ?? entry.snapshotAfter ?? entry.transport ?? entry.record ?? entry.snapshotBefore;
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
export interface TaskCoverageReport {
  ok: boolean;
  initialCharacters: number;
  initialTasks: number;
  characters: number;
  tasks: number;
  achieved: number;
  errors: InvariantIssue[];
  warnings: InvariantIssue[];
}

/** Read-only full-world task coverage check.
 *
 * A real turn may add a subtask, but it must not drop an initial character or
 * an initial task, and an achieved task must stay achieved. This checks the
 * stored world, not the model's task prompt: it cannot prove the settlement
 * considered every task, but it proves a later snapshot did not silently erase
 * the off-stage rows. */
export function verifyTaskCoverage(recordValue: WorldRecordLike | unknown): TaskCoverageReport {
  const report: TaskCoverageReport = {
    ok: false, initialCharacters: 0, initialTasks: 0, characters: 0, tasks: 0, achieved: 0,
    errors: [], warnings: [],
  };
  const record = isRecord(recordValue) ? recordValue : null;
  const initial = record && isRecord(record.initial) ? record.initial : null;
  const state = record && isRecord(record.state) ? record.state : null;
  if (!initial || !isRecord(initial.characters) || !state || !isRecord(state.characters)) {
    report.errors.push(issue('evidence_shape', 'record must carry initial.characters and state.characters'));
    return report;
  }
  const initialCharacters = initial.characters;
  const currentCharacters = state.characters;
  report.initialCharacters = Object.keys(initialCharacters).length;
  report.characters = Object.keys(currentCharacters).length;
  for (const [characterId, initialCharacter] of Object.entries(initialCharacters)) {
    if (!isRecord(initialCharacter)) continue;
    const initialTasks = isRecord(initialCharacter.tasks) ? initialCharacter.tasks : {};
    const currentCharacter = currentCharacters[characterId];
    if (!isRecord(currentCharacter)) {
      report.errors.push(issue('task_hierarchy', `${characterId} disappeared from the stored character registry`));
      continue;
    }
    const currentTasks = isRecord(currentCharacter.tasks) ? currentCharacter.tasks : {};
    for (const [taskId, initialTask] of Object.entries(initialTasks)) {
      report.initialTasks += 1;
      if (!isRecord(initialTask)) continue;
      const currentTask = currentTasks[taskId];
      if (!isRecord(currentTask)) {
        report.errors.push(issue('task_regressed', `${characterId}.${taskId} is missing from the stored task set`));
        continue;
      }
      if (initialTask.status === 'achieved' && currentTask.status !== 'achieved') {
        report.errors.push(issue('task_regressed', `${characterId}.${taskId} moved from achieved to ${String(currentTask.status)}`));
      }
    }
  }
  for (const [characterId, currentCharacter] of Object.entries(currentCharacters)) {
    if (!isRecord(currentCharacter) || !isRecord(currentCharacter.tasks)) continue;
    for (const [taskId, task] of Object.entries(currentCharacter.tasks)) {
      if (!isRecord(task)) continue;
      report.tasks += 1;
      if (task.status === 'achieved') report.achieved += 1;
      if (!initialCharacters[characterId]) {
        report.warnings.push(issue('task_unknown', `${characterId}.${taskId} belongs to a character absent from the initial world`));
      }
    }
  }
  report.ok = report.errors.length === 0;
  return report;
}

export interface TaskDecisionEvidenceReport {
  ok: boolean;
  characters: number | null;
  taskRows: number | null;
  assertedUnchanged: number | null;
  achieved: number;
  rejected: string[];
  errors: InvariantIssue[];
  warnings: InvariantIssue[];
}

/** Read-only check of 04's task-decision coverage ledger.
 *
 * This does not invent state or re-run the model. It checks that a real
 * settlement call reported every required character and every 73-row task
 * scope, that no row was excluded, and that the unchanged + achieved counts
 * account for the scope. Unknown/rejected task ids are errors: 04 may keep
 * valid sibling decisions while rejecting a hallucinated id, but the rejected
 * rows were not judged and full coverage cannot be claimed. */
export function verifyTaskDecisionEvidence(
  value: unknown,
  expected: { characters: number; tasks: number } = { characters: 14, tasks: 73 },
): TaskDecisionEvidenceReport {
  const report: TaskDecisionEvidenceReport = {
    ok: false, characters: null, taskRows: null, assertedUnchanged: null, achieved: 0, rejected: [],
    errors: [], warnings: [],
  };
  const outer = isRecord(value) ? value : null;
  const coverage = outer && isRecord(outer.coverage) ? outer.coverage : outer;
  if (!coverage) {
    report.errors.push(issue('evidence_shape', 'task coverage evidence must be an object'));
    return report;
  }
  const num = (raw: unknown): number | null => (typeof raw === 'number' && Number.isInteger(raw) && raw >= 0 ? raw : null);
  report.characters = num(coverage.tasks) ?? num(coverage.characters) ?? num(coverage.taskCoverageIds);
  report.taskRows = num(coverage.taskRows);
  report.assertedUnchanged = num(coverage.assertedUnchanged);
  const achievedByCharacter = Array.isArray(coverage.achievedByCharacter) ? coverage.achievedByCharacter : [];
  const achievedIds = new Set<string>();
  const achievedCharacters = new Set<string>();
  for (const entry of achievedByCharacter) {
    if (!isRecord(entry) || !Array.isArray(entry.taskIds)) continue;
    if (typeof entry.characterId === 'string' && entry.taskIds.length) achievedCharacters.add(entry.characterId);
    for (const taskId of entry.taskIds) if (typeof taskId === 'string') achievedIds.add(`${String(entry.characterId)}:${taskId}`);
  }
  report.achieved = achievedIds.size;
  if (Array.isArray(coverage.rejectedTaskIds)) {
    report.rejected = coverage.rejectedTaskIds.map((item) => isRecord(item) ? `${String(item.characterId)}:${String(item.taskId)}` : String(item));
  }
  if (coverage.mode && coverage.mode !== 'per_character_decision') {
    report.errors.push(issue('task_coverage', `unexpected task decision mode ${String(coverage.mode)}`));
  }
  if (report.characters !== expected.characters) {
    report.errors.push(issue('task_coverage', `task decisions cover ${String(report.characters)}/${expected.characters} characters`));
  }
  if (report.taskRows !== expected.tasks) {
    report.errors.push(issue('task_coverage', `task scope has ${String(report.taskRows)}/${expected.tasks} rows`));
  }
  if (Array.isArray(coverage.excluded) && coverage.excluded.length) {
    report.errors.push(issue('task_coverage', `task scope excludes ${coverage.excluded.length} entries; full-world coverage requires none`));
  }
  if (coverage.taskCoverageIds !== undefined) {
    const ids = Array.isArray(coverage.taskCoverageIds) ? coverage.taskCoverageIds : [];
    if (ids.length !== expected.characters) report.errors.push(issue('task_coverage', `taskCoverageIds has ${ids.length}/${expected.characters} characters`));
  }
  if (report.assertedUnchanged != null && report.taskRows != null && report.assertedUnchanged + report.achieved !== report.taskRows) {
    report.errors.push(issue('task_coverage', `assertedUnchanged ${report.assertedUnchanged} + achieved ${report.achieved} != taskRows ${report.taskRows}`));
  }
  if (report.assertedUnchanged == null && report.taskRows != null) {
    report.warnings.push(issue('task_coverage', 'assertedUnchanged is missing; cannot prove unchanged rows'));
  }
  if (report.rejected.length) {
    // A rejected id means that row was not actually judged. Dropping it may
    // keep valid sibling decisions, but it cannot be called full coverage.
    report.errors.push(issue('task_coverage', `rejected ${report.rejected.length} task ids; those rows are not decided`));
  }
  report.ok = report.errors.length === 0;
  return report;
}

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


/** Read-only check of what the page actually presented as a turn. A draft or
 * a timed-out draft is not a committed turn even if the harness wrote text to
 * its record. This does not replay state; it only rejects acceptance claims
 * that the displayed evidence itself contradicts. */
export function verifyDisplayedCommit(entries: unknown[]): {
  ok: boolean; errors: InvariantIssue[]; warnings: InvariantIssue[];
} {
  const errors: InvariantIssue[] = [];
  const warnings: InvariantIssue[] = [];
  const add = (target: InvariantIssue[], code: InvariantCode, detail: string): void => {
    if (!target.some((item) => item.code === code && item.detail === detail)) target.push(issue(code, detail));
  };
  const asRecord = (value: unknown): Record<string, unknown> | null => (isRecord(value) ? value : null);
  const numberOrNull = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);
  for (const raw of entries) {
    const turn = asRecord(raw);
    if (!turn) continue;
    const text = typeof turn.text === 'string' ? turn.text.trim() : '';
    const product = asRecord(turn.product);
    const source = typeof turn.textSource === 'string'
      ? turn.textSource : typeof product?.source === 'string' ? product.source : '';
    const problems = Array.isArray(turn.problems) ? turn.problems.filter((item): item is string => typeof item === 'string') : [];
    const timings = asRecord(turn.timings);
    const doneMs = numberOrNull(timings?.doneMs);
    const firstReadableMs = numberOrNull(timings?.firstReadableMs);
    const historyDelta = numberOrNull(turn.historyDelta);
    const acceptedMs = numberOrNull(product?.acceptedMs);
    const hasSubmission = turn.submission != null;
    const label = typeof turn.turn === 'number' ? `turn ${turn.turn}` : 'turn';
    if (!text) {
      continue;
    }
    if (source === 'draft' || problems.includes('draft_only_not_accepted')) {
      add(errors, 'evidence_shape', `${label}: displayed text is a draft, not a committed turn`);
    }
    if (acceptedMs == null) {
      add(errors, 'history_text_missing', `${label}: displayed text has no accepted model text (source ${source || 'unknown'})`);
    }
    if (historyDelta === 0) {
      // A draft-narration point can be committed without increasing the
      // accepted-history count. Do not turn this ambiguous display fact into a
      // claim that no point exists; the draft/accepted checks above are the
      // decisive ones.
      add(warnings, 'history_delta', `${label}: displayed text but history delta is 0`);
    }
    if (!hasSubmission) {
      add(errors, 'evidence_shape', `${label}: displayed text without a submission record`);
    }
    if (doneMs != null && doneMs > 300_000) {
      add(errors, 'evidence_shape', `${label}: turn took ${Math.round(doneMs / 1000)}s (>300s)`);
    }
    if (firstReadableMs != null && firstReadableMs > 60_000) {
      add(errors, 'evidence_shape', `${label}: first readable text at ${Math.round(firstReadableMs / 1000)}s (>60s)`);
    }
  }
  return { ok: errors.length === 0, errors, warnings };
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
      const exceptional = problems.some((problem) => /timeout|error|cancel|refresh|no_entry/i.test(problem));
      if (recorded < 0) {
        errors.push(issue('history_regressed', `history fell by ${-recorded} across a turn`));
      } else if (!exceptional && typeof entry.text === 'string' && entry.text.length > 0 && recorded !== 1) {
        warnings.push(issue('history_delta', `a turn with text added ${recorded} history entries instead of 1`));
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

/** The persisted roll ledger is the freeze evidence: a request that reuses a
 * trigger key must reuse the recorded roll, and no two outcomes may share an
 * id. This is structural; it does not reroll or compare randomness. */
function checkRolls(record: Record<string, unknown>, errors: InvariantIssue[]): void {
  if (record.rolls == null) return;
  if (!isRecord(record.rolls)) {
    errors.push(issue('roll_invalid', 'rolls is not an object'));
    return;
  }
  const ids = new Set<string>();
  let count = 0;
  for (const [key, raw] of Object.entries(record.rolls)) {
    count += 1;
    if (!isRecord(raw)) {
      errors.push(issue('roll_invalid', `roll ${key} is not an object`));
      continue;
    }
    if (raw.key !== key) errors.push(issue('roll_invalid', `roll ${key} has key ${String(raw.key)}`));
    if (!isNonBlankString(raw.rollId)) errors.push(issue('roll_invalid', `roll ${key} has no id`));
    else if (ids.has(raw.rollId)) errors.push(issue('roll_invalid', `roll id ${raw.rollId} is repeated`));
    else ids.add(raw.rollId);
    if (typeof raw.result !== 'number' || !Number.isInteger(raw.result) || raw.result < 1 || raw.result > 20) {
      errors.push(issue('roll_invalid', `roll ${key} result ${String(raw.result)} is outside 1..20`));
    }
    if (typeof raw.eligible !== 'boolean' || typeof raw.admitted !== 'boolean') {
      errors.push(issue('roll_invalid', `roll ${key} lacks eligibility flags`));
    }
  }
  if (typeof record.rollSeq === 'number' && record.rollSeq < count) {
    errors.push(issue('roll_invalid', `rollSeq ${record.rollSeq} is smaller than ${count} recorded rolls`));
  }
}
