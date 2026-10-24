/** Structured output validation for every ModelTask. JSON tasks are fenced-
 * block tolerant on the way in (a leading ```json block is the one 0.6B
 * habit worth accommodating) and strict on shape: every validator is pinned
 * to an existing schedule/controller consumption site, not to a new spec —
 * a rejected shape here is a shape that would corrupt controller memory or
 * build a broken request. narration and reaction are TEXT tasks: raw
 * non-empty strings, never JSON-parsed — the narrative-quality finding that
 * JSON contracts poison small-model prose does not come back through the
 * validation layer. No repair retries here: output quality and retry policy
 * belong to the B3 prompt layer; this layer only guarantees that a shape
 * that was accepted really is the declared shape. */
import type { Json } from '../types';
import type { ModelTask } from '../schedule';
import { updateStages } from '../schedule';

export class StructuredOutputError extends Error {
  readonly name = 'StructuredOutputError';
  constructor(readonly task: ModelTask, readonly reason: string, readonly raw: string) {
    super(`[${task}] structured output rejected: ${reason}`);
  }
}

type Unknown = Record<string, unknown>;

function asObject(value: unknown, reason: string): Unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(reason);
  return value as Unknown;
}

function asString(value: unknown, reason: string): string {
  if (typeof value !== 'string' || !value.length) throw new Error(reason);
  return value;
}

function asFiniteNumber(value: unknown, reason: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(reason);
  return value;
}

function asArray(value: unknown, reason: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(reason);
  return value;
}

function exactKeys(value: Unknown, keys: string[], reason: string): void {
  if (Object.keys(value).sort().join() !== [...keys].sort().join()) throw new Error(reason);
}

const TIME_UNITS = ['second', 'minute', 'hour', 'day', 'month', 'year'] as const;

function validateTimeAdvance(value: unknown, reason: string): void {
  const time = asObject(value, reason);
  exactKeys(time, ['boundary', 'duration'], `${reason} (keys)`);
  if (time.boundary !== 'elapsed' && time.boundary !== 'instant') throw new Error(`${reason} (boundary)`);
  const duration = asObject(time.duration, `${reason} (duration)`);
  exactKeys(duration, ['amount', 'unit'], `${reason} (duration keys)`);
  const amount = asFiniteNumber(duration.amount, `${reason} (amount)`);
  if (!Number.isInteger(amount) || amount < 0) throw new Error(`${reason} (amount)`);
  if (!TIME_UNITS.includes(duration.unit as typeof TIME_UNITS[number])) throw new Error(`${reason} (unit)`);
}

const RULE_VERSIONS = ['reaction-fixture-v1', 'reaction-d20-v1'] as const;
const RELATIONS = ['under', 'above', 'beside', 'in_front_of', 'behind'] as const;

/** EntityDelta field validation, pinned to types.ts: unknown fields reject,
 * present fields must match their declared types — mergeUpdatesStages must
 * never meet a shape it cannot consume. */
function validateEntityDelta(value: unknown): void {
  const delta = asObject(value, 'entity deltas must be objects');
  for (const [key, field] of Object.entries(delta)) {
    switch (key) {
      case 'entityId':
        asString(field, 'entityId must be a non-empty string');
        break;
      case 'positionSet': {
        if (field === null) break;
        const position = asObject(field, 'positionSet must be an object or null');
        asString(position.containerId, 'positionSet containerId must be a non-empty string');
        if (position.slotId !== undefined && position.slotId !== null) asString(position.slotId, 'slotId must be a string or null');
        if (position.relativeTo !== undefined && position.relativeTo !== null) {
          const relative = asObject(position.relativeTo, 'relativeTo must be an object or null');
          exactKeys(relative, ['entityId', 'relation'], 'relativeTo keys');
          asString(relative.entityId, 'relativeTo entityId must be a non-empty string');
          if (!RELATIONS.includes(relative.relation as typeof RELATIONS[number])) throw new Error('unknown relativeTo relation');
        }
        break;
      }
      case 'appearanceChanges':
      case 'personalityChanges': {
        for (const entry of asArray(field, `${key} must be an array`)) {
          const change = asObject(entry, `${key} entries must be objects`);
          exactKeys(change, ['id', 'text', 'supersedes'], 'change keys');
          asString(change.id, 'change id must be a non-empty string');
          if (change.text !== null) asString(change.text, 'change text must be a string or null');
          for (const id of asArray(change.supersedes, 'supersedes must be an array')) asString(id, 'superseded ids must be non-empty strings');
        }
        break;
      }
      case 'sanitySet':
        if (field !== null) asFiniteNumber(field, 'sanitySet must be a number or null');
        break;
      case 'tasksAchieved':
        for (const id of asArray(field, 'tasksAchieved must be an array')) asString(id, 'achieved task ids must be non-empty strings');
        break;
      case 'subtasksAdded': {
        for (const entry of asArray(field, 'subtasksAdded must be an array')) {
          const task = asObject(entry, 'subtasksAdded entries must be objects');
          exactKeys(task, ['id', 'ownerId', 'parentTaskId', 'goal', 'status'], 'subtask keys');
          asString(task.id, 'subtask id must be a non-empty string');
          asString(task.ownerId, 'subtask ownerId must be a non-empty string');
          if (task.parentTaskId !== null) asString(task.parentTaskId, 'subtask parentTaskId must be a string or null');
          asString(task.goal, 'subtask goal must be a non-empty string');
          if (task.status !== 'pending' && task.status !== 'achieved') throw new Error('unknown subtask status');
        }
        break;
      }
      default:
        throw new Error(`unknown entity delta field: ${key}`);
    }
  }
}

const jsonValidators: Record<Exclude<ModelTask, 'narration' | 'reaction'>, (value: unknown) => void> = {
  action: (value) => {
    const output = asObject(value, 'action must be an object');
    if (output.kind === 'skip') {
      exactKeys(output, ['kind'], 'skip action must carry only kind');
      return;
    }
    exactKeys(output, ['kind', 'text'], 'act action must carry kind and text');
    if (output.kind !== 'act' || typeof asString(output.text, 'act action text must be a non-empty string') !== 'string') throw new Error('unknown action kind');
  },
  targets: (value) => {
    const output = asObject(value, 'targets must be an object');
    exactKeys(output, ['targets'], 'targets must carry only targets');
    for (const entry of asArray(output.targets, 'targets must be an array')) {
      const target = asObject(entry, 'target must be an object');
      exactKeys(target, ['targetId', 'triggerKey', 'ruleVersion', 'target'], 'target keys');
      asString(target.targetId, 'targetId must be a non-empty string');
      asString(target.triggerKey, 'triggerKey must be a non-empty string');
      if (!RULE_VERSIONS.includes(target.ruleVersion as typeof RULE_VERSIONS[number])) throw new Error('unknown ruleVersion');
      if (!Number.isInteger(asFiniteNumber(target.target, 'target must be a number'))) throw new Error('target must be an integer');
    }
  },
  results: (value) => {
    const output = asObject(value, 'results must be an object');
    for (const [key, entry] of Object.entries(output)) {
      asString(key, 'result keys must be non-empty');
      asString(entry, 'result values must be non-empty strings');
    }
  },
  updates: (value) => {
    // Batch mode consumes an array of calls; split mode (updatesStages)
    // consumes a single call per stage — both shapes are legal and pass
    // through unnormalized, exactly as the controller consumes them.
    const calls = Array.isArray(value) ? value : [value];
    for (const entry of calls) {
      const call = asObject(entry, 'update call must be an object');
      exactKeys(call, ['stage', 'changes'], 'update call keys');
      if (!updateStages.includes(call.stage as typeof updateStages[number])) throw new Error('unknown update stage');
      const changes = asObject(call.changes, 'update changes must be an object');
      for (const delta of Object.values(changes)) validateEntityDelta(delta);
    }
  },
  continuation: (value) => {
    const output = asObject(value, 'continuation must be an object');
    if (output.kind === 'continue') {
      exactKeys(output, ['kind', 'closedBy', 'cancelReason', 'candidateCharacterIds', 'nextRoundId'], 'continuation keys');
      if (output.closedBy !== 'model' || output.cancelReason !== null) throw new Error('model continuation must be closedBy=model, cancelReason=null');
      for (const id of asArray(output.candidateCharacterIds, 'candidateCharacterIds must be an array')) asString(id, 'candidate ids must be non-empty strings');
      asString(output.nextRoundId, 'nextRoundId must be a non-empty string');
      return;
    }
    if (output.kind === 'handback') {
      exactKeys(output, ['kind', 'closedBy', 'cancelReason'], 'continuation keys');
      if (output.closedBy !== 'model' || output.cancelReason !== null) throw new Error('model continuation must be closedBy=model, cancelReason=null');
      return;
    }
    throw new Error('unknown continuation kind');
  },
  initial: (value) => {
    const output = asObject(value, 'initial must be an object');
    // Top-level contract only: the deep template shape is re-validated by
    // the wire schema when create_world consumes it, so corruption cannot
    // pass silently — unlike memory-resident outputs.
    exactKeys(output, ['engineVersion', 'schemaVersion', 'protagonistId', 'initialTime', 'locations', 'items', 'characters'], 'initial keys');
    if (output.engineVersion !== 'world-engine-v1' || output.schemaVersion !== 1) throw new Error('initial version constants');
    asString(output.protagonistId, 'protagonistId must be a non-empty string');
    for (const key of ['initialTime', 'locations', 'items', 'characters'] as const) {
      if (!output[key] || typeof output[key] !== 'object' || Array.isArray(output[key])) throw new Error(`initial ${key} must be an object`);
    }
  },
  time: (value) => validateTimeAdvance(value, 'time must be a TimeAdvance'),
  pointPlan: (value) => {
    const plan = asArray(value, 'pointPlan must be an array');
    if (!plan.length) throw new Error('pointPlan must not be empty');
    for (const entry of plan) {
      const point = asObject(entry, 'planned point must be an object');
      exactKeys(point, ['pointId', 'kind', 'timeAdvance', 'actorIds'], 'planned point keys');
      asString(point.pointId, 'pointId must be a non-empty string');
      if (point.kind !== 'normal' && point.kind !== 'instant' && point.kind !== 'linked') throw new Error('unknown point kind');
      validateTimeAdvance(point.timeAdvance, 'planned timeAdvance must be a TimeAdvance');
      const actorIds = asArray(point.actorIds, 'actorIds must be an array');
      // An empty list is legal: T03's actionless time-scan and empty linked
      // points plan no actors.
      for (const id of actorIds) asString(id, 'actor ids must be non-empty strings');
    }
  },
};

/** Strips the one tolerated wrapper (a leading fenced code block) before
 * parsing; anything the model wraps otherwise is rejected, not guessed. */
function parseJsonTask(raw: string, task: ModelTask): unknown {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(raw);
  const candidate = (fenced ? fenced[1] : raw).trim();
  if (!candidate.length) throw new StructuredOutputError(task, 'empty output', raw);
  try {
    return JSON.parse(candidate);
  } catch {
    throw new StructuredOutputError(task, 'output is not valid JSON', raw);
  }
}

export function decodeTaskOutput(task: ModelTask, raw: string): Json {
  if (task === 'narration' || task === 'reaction') {
    const text = raw.trim();
    if (!text.length) throw new StructuredOutputError(task, 'empty output', raw);
    return text;
  }
  const parsed = parseJsonTask(raw, task);
  try {
    jsonValidators[task](parsed);
  } catch (error) {
    throw new StructuredOutputError(task, error instanceof Error ? error.message : String(error), raw);
  }
  return parsed as Json;
}
