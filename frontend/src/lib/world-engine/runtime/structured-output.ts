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
    for (const entry of asArray(value, 'updates must be an array')) {
      const call = asObject(entry, 'update call must be an object');
      exactKeys(call, ['stage', 'changes'], 'update call keys');
      if (!updateStages.includes(call.stage as typeof updateStages[number])) throw new Error('unknown update stage');
      const changes = asObject(call.changes, 'update changes must be an object');
      for (const delta of Object.values(changes)) {
        if (!delta || typeof delta !== 'object' || Array.isArray(delta)) throw new Error('entity deltas must be objects');
      }
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
      if (!actorIds.length) throw new Error('planned point needs at least one actor');
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
