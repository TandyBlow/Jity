/** Six-stage updates (R09): position -> appearance -> tasks -> subtasks ->
 * personality -> sanity. Later stages read the state after earlier stages were
 * applied. Task and personality scans cover the full registered cast; a
 * personality change is accepted only alongside its sanity recalculation, and
 * no personality change means no sanity write.
 *
 * Split-stage calls (input.stage) return one UpdatesCall; a merged call returns
 * all six UpdatesCall entries in canonical order. This is the exact shape
 * schedule.ts/controller.ts already consume.
 */
import type { Change, EntityDelta, Id, Json, WorldState } from '../../../types';
import type { InferenceEngine } from '../../../runtime/engine';
import type { UpdatesCall, UpdatesStage } from '../../../schedule';
import { callJson, JsonCallError, joinedMs, joinedRaw } from './engine-call';
import type { ModelCallEvidence, SettlementEvidence, SettlementOptions, SettlementOutcome } from './types';
import {
  SETTLEMENT_STAGES, activeChangeIds, activeRecords, allEntityIds, allKnownTaskIds, allTasks,
  appearanceLine, asInteger, asRecord, asString, currentAchieved, errorText,
  isPlaceholderId, isRecord, LocalIdAllocator, maxChangeSequence, movableIds, normalizeChangeText, personalityLine, personalityOwnersAbove,
  positionFromRow, projectStage, referenceError, resolveCharacterId, resolveEntityId, roster, sameChangeText, taskIndex, taskLine, toJson,
} from './support';
import type { SettlementStage } from './support';

interface UpdatesInput {
  groupId: Id | null;
  mode: 'group' | 'time_scan';
  stage: UpdatesStage | null;
  results: Record<Id, string>;
  workingState: WorldState;
}

interface StageContext {
  engine: InferenceEngine;
  state: WorldState;
  results: Record<Id, string>;
  mode: 'group' | 'time_scan';
  newAchieved: Set<Id>;
  recoveredAchieved: Set<Id>;
  personalityOwners: Set<Id>;
  allocator: LocalIdAllocator;
  options: SettlementOptions;
}

interface StageOutcome {
  changes: Record<Id, Partial<EntityDelta>>;
  detail: Record<string, unknown>;
  error?: string;
  fallback: boolean;
  calls: ModelCallEvidence[];
}

interface BatchMemory {
  baselineAchieved: Set<Id>;
  tasksAchieved: Set<Id>;
  personalityOwners: Set<Id>;
  tasksStageSeen: boolean;
  tasksFailed: boolean;
  baselineMaxSequence: number;
}

interface OperationRow {
  op: 'keep' | 'add' | 'remove' | 'replace';
  recordIds: Id[];
  text: string | null;
}

const STAGE_SET = new Set<string>(SETTLEMENT_STAGES);
const OPS = new Set(['keep', 'add', 'remove', 'replace']);
const RELATIONS = ['under', 'above', 'beside', 'in_front_of', 'behind'] as const;

const POSITION_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['changes'],
  properties: {
    changes: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['entityId', 'containerId', 'slotId', 'relativeTo'],
        properties: {
          entityId: { type: 'string' },
          containerId: { type: 'string' },
          slotId: { type: ['string', 'null'] },
          relativeTo: { anyOf: [{ type: 'null' }, {
            type: 'object', additionalProperties: false, required: ['entityId', 'relation'],
            properties: { entityId: { type: 'string' }, relation: { enum: [...RELATIONS] } },
          }] },
        },
      },
    },
  },
};

const OPERATIONS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['operations'],
  properties: {
    operations: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['entityId', 'op', 'recordIds', 'text'],
        properties: {
          entityId: { type: 'string' },
          op: { enum: [...OPS] },
          recordIds: { type: 'array', items: { type: 'string' } },
          text: { type: ['string', 'null'] },
        },
      },
    },
  },
};

const TASKS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['decisions'],
  properties: {
    decisions: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['characterId', 'achieved'],
        properties: {
          characterId: { type: 'string' },
          achieved: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
};

const SUBTASKS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['subtasks'],
  properties: {
    subtasks: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['parentTaskId', 'goal'],
        properties: { parentTaskId: { type: 'string' }, goal: { type: 'string' } },
      },
    },
  },
};

const SANITY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['sanity'],
  properties: {
    sanity: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['characterId', 'value'],
        properties: { characterId: { type: 'string' }, value: { type: 'integer', minimum: 0, maximum: 100 } },
      },
    },
  },
};

export class UpdatesRunner {
  private readonly batches = new Map<Id, BatchMemory>();
  private readonly allocator = new LocalIdAllocator();

  constructor(private readonly engine: InferenceEngine, private readonly options: SettlementOptions = {}) {}

  reset(): void {
    this.batches.clear();
  }

  async run(key: Id, input: Json): Promise<SettlementOutcome<UpdatesCall[] | UpdatesCall>> {
    const started = performance.now();
    const parsed = parseUpdatesInput(input);
    if ('error' in parsed) return this.failure(key, parsed.error, started);
    const baseKey = key.split('#')[0];
    const batchExisted = this.batches.has(baseKey);
    const batch = this.batch(baseKey, parsed.workingState);
    const currentAchievedIds = currentAchieved(parsed.workingState);
    const stage = parsed.stage;
    const beforeTasks = stage === 'tasks' || stage === 'position' || stage === 'appearance' || stage === 'subtasks';
    const newlyAchieved = beforeTasks ? new Set<Id>() : difference(currentAchievedIds, batch.baselineAchieved);
    const effectiveNew = batch.tasksAchieved.size > 0 ? new Set(batch.tasksAchieved) : newlyAchieved;
    const recovered = stage === 'personality' && !batch.tasksStageSeen && !batch.tasksFailed
      && effectiveNew.size === 0 && currentAchievedIds.size > 0
      ? currentAchievedIds
      : new Set<Id>();
    const sanityBasis = stage !== 'sanity'
      ? null
      : batch.personalityOwners.size > 0
        ? 'batch_personality_owners'
        : batchExisted
          ? 'sequence_after_baseline'
          : 'latest_personality_sequence';
    const splitPersonalityOwners = stage === 'sanity'
      ? (batch.personalityOwners.size > 0
        ? batch.personalityOwners
        : batchExisted
          ? personalityOwnersAbove(parsed.workingState, batch.baselineMaxSequence)
          : latestPersonalityOwners(parsed.workingState))
      : new Set<Id>();
    const ctx: StageContext = {
      engine: this.engine,
      state: parsed.workingState,
      results: parsed.results,
      mode: parsed.mode,
      newAchieved: effectiveNew,
      recoveredAchieved: recovered,
      personalityOwners: splitPersonalityOwners,
      allocator: this.allocator,
      options: this.options,
    };
    if (stage) {
      const outcome = await this.runStage(stage, ctx);
      const changes = this.guardStage(stage, ctx.state, outcome);
      if (outcome.error) {
        // A failed stage cannot be replaced by an empty delta: that would
        // commit a partial six-stage point and hide the model error.
        this.batches.delete(baseKey);
        return this.outcomeFailure(key, outcome.error, started, outcome.calls, {
          mode: ctx.mode,
          stage,
          stageDetail: outcome.detail,
          taskScope: (outcome.detail as { taskScope?: unknown }).taskScope ?? null,
          sanityBasis,
        });
      }
      if (stage === 'tasks') {
        batch.tasksStageSeen = true;
        batch.tasksFailed = false;
        batch.tasksAchieved = achievedFromChanges(changes);
      }
      if (stage === 'personality') batch.personalityOwners = new Set(Object.keys(changes));
      const value: UpdatesCall = { stage, changes: changes as UpdatesCall['changes'] };
      return this.finish(key, value, [outcome], started, {
        mode: ctx.mode,
        sanityBasis,
        taskCoverageIds: roster(ctx.state),
        taskScope: (outcome.detail as { taskScope?: unknown }).taskScope ?? null,
        personalityCoverageIds: stage === 'tasks'
          ? (achievedFromChanges(changes).size > 0 ? roster(ctx.state) : [])
          : stage === 'personality' && Object.keys(changes).length > 0
            ? roster(ctx.state)
            : [],
      });
    }
    const calls: UpdatesCall[] = [];
    const outcomes: StageOutcome[] = [];
    let view = ctx.state;
    let newAchieved = new Set<Id>();
    let mergedPersonalityOwners = new Set<Id>();
    for (const currentStage of SETTLEMENT_STAGES) {
      const stageCtx: StageContext = {
        ...ctx,
        state: view,
        newAchieved,
        recoveredAchieved: new Set<Id>(),
        personalityOwners: mergedPersonalityOwners,
      };
      const outcome = await this.runStage(currentStage, stageCtx);
      const changes = this.guardStage(currentStage, view, outcome);
      outcomes.push(outcome);
      calls.push({ stage: currentStage, changes: changes as UpdatesCall['changes'] });
      try {
        view = projectStage(view, currentStage, changes);
      } catch (error) {
        // A candidate the local kernel rejects must not be handed onward.
        // Keep the stage empty and preserve the failure in evidence.
        outcome.error = outcome.error ?? `stage_projection_rejected:${errorText(error)}`;
        outcome.fallback = true;
        calls[calls.length - 1] = { stage: currentStage, changes: {} };
      }
      if (currentStage === 'tasks') newAchieved = achievedFromChanges(changes);
      if (currentStage === 'personality') mergedPersonalityOwners = new Set(Object.keys(changes));
    }
    const failed = outcomes
      .map((outcome, index) => ({ outcome, stage: SETTLEMENT_STAGES[index] }))
      .filter((row) => Boolean(row.outcome.error));
    if (failed.length) {
      this.batches.delete(baseKey);
      return this.outcomeFailure(
        key,
        failed.map((row) => `${row.stage}:${row.outcome.error}`).join('; '),
        started,
        outcomes.flatMap((outcome) => outcome.calls),
        {
          mode: ctx.mode,
          stageErrors: failed.map((row) => ({ stage: row.stage, error: row.outcome.error ?? null })),
          taskScope: (outcomes[SETTLEMENT_STAGES.indexOf('tasks')]?.detail as { taskScope?: unknown } | undefined)?.taskScope ?? null,
        },
      );
    }
    const taskCoverageIds = roster(ctx.state);
    const personalityCoverageIds = newAchieved.size > 0 ? taskCoverageIds : [];
    const detail = {
      mode: ctx.mode,
      sanityBasis: 'merged_personality_stage',
      taskCoverageIds,
      taskScope: (outcomes[SETTLEMENT_STAGES.indexOf('tasks')]?.detail as { taskScope?: unknown } | undefined)?.taskScope ?? null,
      personalityCoverageIds,
      newlyAchievedTaskIds: [...newAchieved].sort(),
      personalityChangedIds: [...mergedPersonalityOwners].sort(),
      stages: outcomes.map((outcome, index) => ({
        stage: SETTLEMENT_STAGES[index],
        // Per-stage model time is what a slow-turn investigation needs; the
        // whole updates task has its own total in the ledger.
        ms: joinedMs(outcome.calls),
        error: outcome.error ?? null,
        fallback: outcome.fallback,
        ...outcome.detail,
      })),
    };
    return this.finish(key, calls, outcomes, started, detail);
  }

  private async runStage(stage: SettlementStage, ctx: StageContext): Promise<StageOutcome> {
    if (stage === 'position') return stagePosition(ctx);
    if (stage === 'appearance') return stageAppearance(ctx);
    if (stage === 'tasks') return stageTasks(ctx);
    if (stage === 'subtasks') return stageSubtasks(ctx);
    if (stage === 'personality') return stagePersonality(ctx);
    return stageSanity(ctx);
  }

  private guardStage(stage: SettlementStage, state: WorldState, outcome: StageOutcome): Record<Id, Partial<EntityDelta>> {
    if (!Object.keys(outcome.changes).length) return {};
    try {
      projectStage(state, stage, outcome.changes);
      return outcome.changes;
    } catch (error) {
      outcome.error = outcome.error ?? `stage_candidate_rejected:${errorText(error)}`;
      outcome.fallback = true;
      return {};
    }
  }

  private finish(
    key: Id,
    value: UpdatesCall[] | UpdatesCall,
    outcomes: StageOutcome[],
    started: number,
    extraDetail: Record<string, unknown> = {},
  ): SettlementOutcome<UpdatesCall[] | UpdatesCall> {
    const calls = outcomes.flatMap((outcome) => outcome.calls);
    const errors = outcomes.map((outcome) => outcome.error).filter((item): item is string => Boolean(item));
    const fallback = outcomes.some((outcome) => outcome.fallback);
    const ms = joinedMs(calls);
    const evidence: SettlementEvidence = {
      task: 'updates',
      key,
      raw: joinedRaw(calls),
      ms,
      fallback,
      error: errors.length ? errors.join('; ') : undefined,
      calls,
      detail: toJson({
        ...extraDetail,
        stageErrors: outcomes.map((outcome, index) => ({
          stage: Array.isArray(value) ? SETTLEMENT_STAGES[index] : value.stage,
          error: outcome.error ?? null,
          fallback: outcome.fallback,
        })),
      }),
    };
    const outcome: SettlementOutcome<UpdatesCall[] | UpdatesCall> = {
      value,
      raw: evidence.raw,
      ms,
      fallback,
      error: evidence.error,
      evidence,
    };
    this.options.onTask?.('updates', key, {
      ms,
      fallback,
      error: evidence.error,
      raw: evidence.raw,
      promptChars: calls.reduce((sum, call) => sum + call.prompt.length, 0),
    });
    return outcome;
  }

  /** A resolved model answer could not be repaired. The caller must not commit
   * any stage of this point; the evidence keeps every call, raw output and
   * stage error so the failure is diagnosable and retryable. */
  private outcomeFailure(
    key: Id,
    error: string,
    started: number,
    calls: ModelCallEvidence[],
    detail: Record<string, unknown>,
  ): SettlementOutcome<UpdatesCall[] | UpdatesCall> {
    const ms = joinedMs(calls);
    const evidence: SettlementEvidence = {
      task: 'updates',
      key,
      raw: joinedRaw(calls),
      ms: ms || performance.now() - started,
      fallback: true,
      error,
      calls,
      detail: toJson({ ...detail, reason: 'point_aborted_after_repair' }),
    };
    this.options.onTask?.('updates', key, {
      ms: evidence.ms,
      fallback: true,
      error,
      raw: evidence.raw,
      promptChars: calls.reduce((sum, call) => sum + call.prompt.length, 0),
    });
    return { value: null, raw: evidence.raw, ms: evidence.ms, fallback: true, error, evidence };
  }

  private failure(key: Id, error: string, started: number): SettlementOutcome<UpdatesCall[] | UpdatesCall> {
    return {
      value: null,
      raw: '',
      ms: performance.now() - started,
      fallback: false,
      error,
      evidence: {
        task: 'updates',
        key,
        raw: '',
        ms: performance.now() - started,
        fallback: false,
        error,
        calls: [],
        detail: toJson({ reason: error }),
      },
    };
  }

  private batch(key: Id, state: WorldState): BatchMemory {
    let memory = this.batches.get(key);
    if (!memory) {
      memory = {
        baselineAchieved: currentAchieved(state), tasksAchieved: new Set(), personalityOwners: new Set(),
        tasksStageSeen: false, tasksFailed: false, baselineMaxSequence: maxChangeSequence(state),
      };
      this.batches.set(key, memory);
      if (this.batches.size > 64) {
        const oldest = this.batches.keys().next().value;
        if (oldest != null) this.batches.delete(oldest);
      }
    }
    return memory;
  }
}

export function createUpdatesRunner(engine: InferenceEngine, options: SettlementOptions = {}): UpdatesRunner {
  return new UpdatesRunner(engine, options);
}

function parseUpdatesInput(input: Json): UpdatesInput | { error: string } {
  const data = asRecord(input);
  const state = data.workingState;
  if (!isRecord(state) || !isRecord(state.initial) || !isRecord(state.initial.characters)
    || !isRecord(state.initial.items) || !isRecord(state.initial.locations)
    || !isRecord(state.characters) || !isRecord(state.items) || !isRecord(state.locations)) {
    return { error: 'updates_missing_working_state' };
  }
  const world = state as unknown as WorldState;
  const stageRaw = data.stage;
  let stage: UpdatesStage | null = null;
  if (stageRaw != null) {
    if (typeof stageRaw !== 'string' || !STAGE_SET.has(stageRaw)) return { error: `updates_unknown_stage:${String(stageRaw)}` };
    stage = stageRaw as UpdatesStage;
  }
  const groupId = asString(data.groupId) || null;
  const modeRaw = asString(data.mode);
  const mode: 'group' | 'time_scan' = modeRaw === 'time_scan' ? 'time_scan' : modeRaw === 'group' ? 'group' : groupId ? 'group' : 'time_scan';
  if (mode === 'group' && !groupId) return { error: 'updates_missing_group_id' };
  const results: Record<Id, string> = {};
  if (data.results != null) {
    if (!isRecord(data.results)) return { error: 'updates_results_not_object' };
    for (const [id, text] of Object.entries(data.results)) if (typeof text === 'string') results[id] = text;
  } else if (mode === 'group') {
    return { error: 'updates_missing_results' };
  }
  return { groupId, mode, stage, results, workingState: world };
}

async function stagePosition(ctx: StageContext): Promise<StageOutcome> {
  const scanned = movableIds(ctx.state);
  if (ctx.mode === 'time_scan') {
    return { changes: {}, detail: { scannedEntityIds: scanned, skipped: 'time_scan_no_action' }, fallback: false, calls: [] };
  }
  const prompt = buildPositionPrompt(ctx.state, ctx.results);
  try {
    const answer = await callJson(ctx.engine, prompt, {
      maxTokens: stageTokens(ctx, 240),
      temperature: ctx.options.temperature ?? 0,
      timeoutMs: ctx.options.timeoutMs,
      maxPromptChars: ctx.options.maxPromptChars,
      jsonSchema: POSITION_SCHEMA,
      validate: (value) => validatePositionAnswer(value, ctx.state),
    });
    const changes = readPositionChanges(answer.value, ctx.state);
    projectStage(ctx.state, 'position', changes);
    return {
      changes,
      detail: { scannedEntityIds: scanned, changedEntityIds: Object.keys(changes).sort() },
      fallback: false,
      calls: answer.calls,
    };
  } catch (error) {
    return stageFailure({ scannedEntityIds: scanned }, error);
  }
}

async function stageAppearance(ctx: StageContext): Promise<StageOutcome> {
  const scanned = allEntityIds(ctx.state);
  if (ctx.mode === 'time_scan') {
    return { changes: {}, detail: { scannedEntityIds: scanned, skipped: 'time_scan_no_action' }, fallback: false, calls: [] };
  }
  const prompt = buildDescriptionPrompt(ctx.state, ctx.results, 'appearance');
  try {
    const answer = await callJson(ctx.engine, prompt, {
      maxTokens: stageTokens(ctx, 420),
      temperature: ctx.options.temperature ?? 0,
      timeoutMs: ctx.options.timeoutMs,
      maxPromptChars: ctx.options.maxPromptChars,
      jsonSchema: OPERATIONS_SCHEMA,
      validate: (value) => readDescriptionOperations(value, ctx.state, 'appearance', ctx.allocator, false),
    });
    const changes = readDescriptionOperations(answer.value, ctx.state, 'appearance', ctx.allocator, false);
    projectStage(ctx.state, 'appearance', changes);
    return {
      changes,
      detail: { scannedEntityIds: scanned, changedEntityIds: Object.keys(changes).sort() },
      fallback: false,
      calls: answer.calls,
    };
  } catch (error) {
    return stageFailure({ scannedEntityIds: scanned }, error);
  }
}

async function stageTasks(ctx: StageContext): Promise<StageOutcome> {
  const rows = allTasks(ctx.state);
  const characters = roster(ctx.state);
  if (!rows.length) {
    return { changes: {}, detail: { taskCoverageIds: characters, decidedTaskIds: [], skipped: 'no_tasks' }, fallback: false, calls: [] };
  }
  if (rows.every(({ task }) => task.status === 'achieved')) {
    return {
      changes: {},
      detail: { taskCoverageIds: characters, decidedTaskIds: [], skipped: 'all_tasks_already_achieved' },
      fallback: false,
      calls: [],
    };
  }
  const prompt = buildTasksPrompt(ctx);
  const taskScope = taskScopeFor(ctx.state);
  try {
    const answer = await callJson(ctx.engine, prompt, {
      maxTokens: stageTokens(ctx, 520),
      temperature: ctx.options.temperature ?? 0,
      timeoutMs: ctx.options.timeoutMs,
      maxPromptChars: ctx.options.maxPromptChars,
      jsonSchema: TASKS_SCHEMA,
      validate: (value) => readTaskDecisions(value, ctx.state),
    });
    const changes = readTaskDecisions(answer.value, ctx.state);
    const newlyAchieved = [...achievedFromChanges(changes)];
    return {
      changes,
      detail: {
        taskCoverageIds: characters,
        taskScope: { ...taskScope, assertedUnchanged: rows.length - newlyAchieved.length },
        decidedTaskIds: rows.map(({ task }) => task.id).sort(),
        newlyAchievedTaskIds: newlyAchieved.sort(),
      },
      fallback: false,
      calls: answer.calls,
    };
  } catch (error) {
    return stageFailure({ taskCoverageIds: characters, taskScope, decidedTaskIds: rows.map(({ task }) => task.id).sort() }, error);
  }
}

/** The full-world task scope this stage presents and the decision granularity
 * it records. Every character with tasks appears in the prompt and must make
 * one decision; that decision covers all of the character's tasks, so silence
 * is an explicit "no task of mine changed", not a program-filled pending row. */
function taskScopeFor(state: WorldState): { mode: string; characters: number; taskRows: number; excluded: string[] } {
  const rows = allTasks(state);
  return {
    mode: 'per_character_decision',
    characters: new Set(rows.map((row) => row.ownerId)).size,
    taskRows: rows.length,
    excluded: [],
  };
}

async function stageSubtasks(ctx: StageContext): Promise<StageOutcome> {
  const rows = allTasks(ctx.state);
  const characters = roster(ctx.state);
  if (!rows.length) {
    return { changes: {}, detail: { parentTaskIds: [], characterIds: characters, skipped: 'no_parent_tasks' }, fallback: false, calls: [] };
  }
  const prompt = buildSubtasksPrompt(ctx);
  try {
    const answer = await callJson(ctx.engine, prompt, {
      maxTokens: stageTokens(ctx, 260),
      temperature: ctx.options.temperature ?? 0,
      timeoutMs: ctx.options.timeoutMs,
      maxPromptChars: ctx.options.maxPromptChars,
      jsonSchema: SUBTASKS_SCHEMA,
      validate: (value) => readSubtaskProposals(value, ctx.state, ctx.allocator, ctx.options.maxNewTasks ?? 8),
    });
    const changes = readSubtaskProposals(answer.value, ctx.state, ctx.allocator, ctx.options.maxNewTasks ?? 8);
    return {
      changes,
      detail: {
        parentTaskIds: rows.map(({ task }) => task.id).sort(),
        characterIds: characters,
        addedTaskIds: Object.values(changes).flatMap((delta) => (delta.subtasksAdded ?? []).map((task) => task.id)).sort(),
      },
      fallback: false,
      calls: answer.calls,
    };
  } catch (error) {
    return stageFailure({ parentTaskIds: rows.map(({ task }) => task.id).sort(), characterIds: characters }, error);
  }
}

async function stagePersonality(ctx: StageContext): Promise<StageOutcome> {
  const characters = roster(ctx.state);
  const triggerIds = ctx.newAchieved.size > 0 ? [...ctx.newAchieved] : [...ctx.recoveredAchieved];
  if (!triggerIds.length) {
    return {
      changes: {},
      detail: { scannedCharacterIds: characters, triggeredByTaskIds: [], triggered: false },
      fallback: false,
      calls: [],
    };
  }
  const prompt = buildPersonalityPrompt(ctx, triggerIds, ctx.recoveredAchieved.size > 0);
  try {
    const answer = await callJson(ctx.engine, prompt, {
      maxTokens: stageTokens(ctx, 520),
      temperature: ctx.options.temperature ?? 0,
      timeoutMs: ctx.options.timeoutMs,
      maxPromptChars: ctx.options.maxPromptChars,
      jsonSchema: OPERATIONS_SCHEMA,
      validate: (value) => readDescriptionOperations(value, ctx.state, 'personality', ctx.allocator, true),
    });
    const changes = readDescriptionOperations(answer.value, ctx.state, 'personality', ctx.allocator, true);
    return {
      changes,
      detail: {
        scannedCharacterIds: characters,
        triggeredByTaskIds: triggerIds.sort(),
        triggerBasis: ctx.recoveredAchieved.size > 0 ? 'recovered_achieved_tasks' : 'new_tasks',
        changedCharacterIds: Object.keys(changes).sort(),
      },
      fallback: false,
      calls: answer.calls,
    };
  } catch (error) {
    return stageFailure({ scannedCharacterIds: characters, triggeredByTaskIds: triggerIds.sort() }, error);
  }
}

async function stageSanity(ctx: StageContext): Promise<StageOutcome> {
  const owners = [...ctx.personalityOwners].filter((id) => Boolean(ctx.state.characters[id])).sort();
  if (!owners.length) {
    return { changes: {}, detail: { owners: [], skipped: 'no_personality_change' }, fallback: false, calls: [] };
  }
  const prompt = buildSanityPrompt(ctx, owners);
  try {
    const answer = await callJson(ctx.engine, prompt, {
      maxTokens: stageTokens(ctx, 160),
      temperature: ctx.options.temperature ?? 0,
      timeoutMs: ctx.options.timeoutMs,
      maxPromptChars: ctx.options.maxPromptChars,
      jsonSchema: SANITY_SCHEMA,
      validate: (value) => readSanityValues(value, owners, ctx.state),
    });
    const values = readSanityValues(answer.value, owners, ctx.state);
    const changes: Record<Id, Partial<EntityDelta>> = {};
    for (const owner of owners) changes[owner] = { sanitySet: values[owner] };
    return {
      changes,
      detail: { owners, values },
      fallback: false,
      calls: answer.calls,
    };
  } catch (error) {
    // Personality changes and sanity values must pair. A conservative recalc
    // that keeps the current value is legal and visible; it never invents a
    // psychological change.
    const changes: Record<Id, Partial<EntityDelta>> = {};
    for (const owner of owners) changes[owner] = { sanitySet: ctx.state.characters[owner].sanity };
    const calls = error instanceof JsonCallError ? error.calls : [];
    return {
      changes,
      detail: { owners, fallback: 'current_sanity', reason: errorText(error) },
      error: errorText(error),
      fallback: true,
      calls,
    };
  }
}

function stageFailure(detail: Record<string, unknown>, error: unknown): StageOutcome {
  const calls = error instanceof JsonCallError ? error.calls : [];
  return {
    changes: {},
    detail: { ...detail, reason: errorText(error) },
    error: errorText(error),
    fallback: true,
    calls,
  };
}

function stageTokens(ctx: StageContext, fallback: number): number {
  return ctx.options.maxTokens?.updates ?? fallback;
}

function difference(left: Set<Id>, right: Set<Id>): Set<Id> {
  const result = new Set<Id>();
  for (const id of left) if (!right.has(id)) result.add(id);
  return result;
}

function achievedFromChanges(changes: Record<Id, Partial<EntityDelta>>): Set<Id> {
  const achieved = new Set<Id>();
  for (const delta of Object.values(changes)) for (const taskId of delta.tasksAchieved ?? []) achieved.add(taskId);
  return achieved;
}

function latestPersonalityOwners(state: WorldState): Set<Id> {
  let latest = -1;
  for (const id of Object.keys(state.characters)) {
    for (const record of state.characters[id].personalityChanges) {
      if (record.active) latest = Math.max(latest, record.sourceSequence);
    }
  }
  const owners = new Set<Id>();
  if (latest < 0) return owners;
  for (const id of Object.keys(state.characters)) {
    if (state.characters[id].personalityChanges.some((record) => record.active && record.sourceSequence === latest)) owners.add(id);
  }
  return owners;
}

function buildPositionPrompt(state: WorldState, results: Record<Id, string>): string {
  const entities = movableIds(state).map((id) => `- ${positionLineFor(state, id)}`);
  const sampleId = movableIds(state)[0] ?? '';
  const sampleContainer = state.characters[sampleId]?.position.containerId
    ?? state.items[sampleId]?.position.containerId
    ?? allEntityIds(state)[0] ?? '';
  return [
    '你是中文跑团游戏的位置结算器。只输出 JSON，不要解释。',
    '下面列出所有可移动实体（人物和物品）的当前位置。根据本组结算结果，判断哪些实体改变了位置；没有移动就不要列出。',
    '规则：',
    '- entityId 必须是下面实体之一；containerId 必须是已登记实体 id；slotId 只能填该容器的槽位 id；relativeTo 只能指向同一地点的实体。',
    '- 不要新增地点、物品或人物；不要重复列出同一实体。',
    '- 位置变化是同时发生的，最终结构不能成环。',
    `结算结果：${resultText(results) || '（无）'}`,
    '实体：',
    ...entities,
    '地点和容器（id=名字，槽位）：',
    ...containerCatalog(state),
    `输出 {"changes":[{"entityId":"${sampleId}","containerId":"${sampleContainer}","slotId":null,"relativeTo":null}]}；没有变化输出 {"changes":[]}。`,
  ].join('\n');
}

function positionLineFor(state: WorldState, id: Id): string {
  const name = state.initial.characters[id]?.name ?? state.initial.items[id]?.name ?? id;
  const entity = state.characters[id] ?? state.items[id];
  const position = entity.position;
  const base = `${position.containerId}${position.slotId ? `/${position.slotId}` : ''}`;
  const relative = position.relativeTo
    ? `~${position.relativeTo.relation}:${position.relativeTo.entityId}`
    : '';
  return `${id}=${name}@${base}${relative}`;
}

function containerCatalog(state: WorldState): string[] {
  return allEntityIds(state).map((id) => {
    const name = state.initial.locations[id]?.name ?? state.initial.items[id]?.name ?? state.initial.characters[id]?.name ?? id;
    const slots = state.initial.locations[id]?.slots ?? state.initial.items[id]?.slots ?? state.initial.characters[id]?.slots ?? [];
    return `${id}=${name}${slots.length ? `[${slots.map((slot) => slot.id).join(',')}]` : ''}`;
  });
}

function validatePositionAnswer(value: unknown, state: WorldState): void {
  readPositionChanges(value, state);
}

function readPositionChanges(value: unknown, state: WorldState): Record<Id, Partial<EntityDelta>> {
  const rows = asRecord(value).changes;
  if (!Array.isArray(rows)) throw new Error('changes must be an array');
  const movable = new Set(movableIds(state));
  const known = new Set(allEntityIds(state));
  const seen = new Set<Id>();
  const changes: Record<Id, Partial<EntityDelta>> = {};
  for (const raw of rows) {
    if (!isRecord(raw)) throw new Error('change must be an object');
    const rawEntityId = asString(raw.entityId);
    const entityId = resolveEntityId(state, rawEntityId);
    if (!entityId) throw new Error(referenceError(state, rawEntityId, 'entity', movableIds(state)[0]));
    if (!movable.has(entityId)) throw new Error(`position entity is not movable: ${rawEntityId}${entityId !== rawEntityId ? ` (${entityId})` : ''}`);
    if (seen.has(entityId)) throw new Error(`duplicate position change: ${entityId}`);
    seen.add(entityId);
    const position = positionFromRow(raw);
    if (!position) throw new Error(`invalid position for ${entityId}`);
    const rawContainerId = position.containerId;
    const containerId = resolveEntityId(state, rawContainerId);
    if (!containerId) throw new Error(referenceError(state, rawContainerId, 'entity', sampleContainerId(state)));
    position.containerId = containerId;
    if (!known.has(position.containerId)) throw new Error(`unknown container ${rawContainerId}${containerId !== rawContainerId ? ` (${containerId})` : ''}`);
    if (position.containerId === entityId) throw new Error(`entity ${entityId} cannot contain itself`);
    const slots = slotsOf(state, position.containerId);
    if (position.slotId != null && !slots.some((slot) => slot.id === position.slotId)) {
      throw new Error(`slot ${position.slotId} does not belong to ${position.containerId}`);
    }
    if (position.relativeTo) {
      const rawRelativeId = position.relativeTo.entityId;
      const relativeId = resolveEntityId(state, rawRelativeId);
      if (!relativeId) throw new Error(referenceError(state, rawRelativeId, 'entity', movableIds(state)[0]));
      position.relativeTo.entityId = relativeId;
      if (!known.has(position.relativeTo.entityId)) throw new Error(`unknown relative target ${rawRelativeId}${relativeId !== rawRelativeId ? ` (${relativeId})` : ''}`);
      if (position.relativeTo.entityId === entityId) throw new Error(`entity ${entityId} cannot be relative to itself`);
      if (!RELATIONS.includes(position.relativeTo.relation)) throw new Error(`invalid relation ${position.relativeTo.relation}`);
    }
    changes[entityId] = { positionSet: position };
  }
  return changes;
}

function sampleContainerId(state: WorldState): Id {
  return allEntityIds(state)[0] ?? '';
}

function slotsOf(state: WorldState, containerId: Id): { id: Id; label: string }[] {
  return state.initial.locations[containerId]?.slots
    ?? state.initial.items[containerId]?.slots
    ?? state.initial.characters[containerId]?.slots
    ?? [];
}

function buildDescriptionPrompt(state: WorldState, results: Record<Id, string>, kind: 'appearance' | 'personality'): string {
  const ids = kind === 'appearance' ? allEntityIds(state) : roster(state);
  // The appearance scan covers every entity, so the per-line prose budget is
  // derived from the cast size: a bigger world gets shorter tails, the line
  // set itself is never cut. Rules + settled results take roughly 3.5k chars.
  const tail = kind === 'appearance' ? Math.max(20, Math.min(88, Math.floor(3400 / Math.max(1, ids.length)))) : 0;
  const lines = ids.map((id) => (kind === 'appearance'
    ? appearanceLine(state, id, { compactTail: tail })
    : `- ${personalityLine(state, id)}`));
  const title = kind === 'appearance' ? '外貌' : '个性';
  return [
    `你是中文跑团游戏的${title}结算器。只输出 JSON，不要解释。`,
    `扫描下面所有${kind === 'appearance' ? '实体（人物、物品、地点）' : '人物（包括不在场人物）'}的${title}。根据结算结果，判断是否需要新增、解除或替换${title}变化。没有变化就返回空操作。`,
    '规则：',
    `- 不能修改初始${title}；remove/replace 只能用 recordIds 引用该实体已有的有效变化 id。`,
    '- add 的 text 必须非空，recordIds 为空；replace 的 text 必须与旧文本不同；remove 的 text 为 null。',
    '- 同一个有效记录不能被重复 keep/remove/replace；如果一个实体有操作，它的全部有效记录都必须被 keep 或替换/解除覆盖，否则整段拒绝。',
    '- 不要新增实体；没有实际变化就 keep，不要为了凑变化而改写。',
    `结算结果：${resultText(results) || '（无）'}`,
    kind === 'appearance' ? '实体：' : '人物：',
    ...lines,
    `输出 {"operations":[{"entityId":"${ids[0] ?? ''}","op":"keep|add|remove|replace","recordIds":[],"text":null}]}。`,
  ].join('\n');
}

function readDescriptionOperations(
  value: unknown,
  state: WorldState,
  kind: 'appearance' | 'personality',
  allocator: LocalIdAllocator,
  requireEveryEntity: boolean,
): Record<Id, Partial<EntityDelta>> {
  const rows = asRecord(value).operations;
  if (!Array.isArray(rows)) throw new Error('operations must be an array');
  const targets = kind === 'appearance' ? new Set(allEntityIds(state)) : new Set(roster(state));
  const byEntity = new Map<Id, OperationRow[]>();
  for (const raw of rows) {
    if (!isRecord(raw)) throw new Error('operation must be an object');
    const rawEntityId = asString(raw.entityId);
    const entityId = kind === 'appearance' ? resolveEntityId(state, rawEntityId) : resolveCharacterId(state, rawEntityId);
    if (!entityId) throw new Error(referenceError(state, rawEntityId, kind === 'appearance' ? 'entity' : 'character', [...targets][0]));
    if (!targets.has(entityId)) throw new Error(`operation targets an unknown ${kind === 'appearance' ? 'entity' : 'character'}: ${rawEntityId}${entityId !== rawEntityId ? ` (${entityId})` : ''}`);
    const op = asString(raw.op);
    if (!OPS.has(op)) throw new Error(`invalid operation ${op || '?'} for ${entityId}`);
    const recordIds = Array.isArray(raw.recordIds) ? raw.recordIds.map(asString).filter(Boolean) : null;
    if (!recordIds) throw new Error(`recordIds must be an array for ${entityId}`);
    const text = raw.text == null ? null : asString(raw.text);
    if (op === 'keep' && text != null && text !== '') throw new Error(`keep cannot add text for ${entityId}`);
    if (op === 'add' && !text) throw new Error(`add requires text for ${entityId}`);
    if (op === 'add' && recordIds.length) throw new Error(`add cannot supersede records for ${entityId}`);
    if (op === 'remove' && text) throw new Error(`remove cannot add text for ${entityId}`);
    if (op === 'remove' && !recordIds.length) throw new Error(`remove requires record ids for ${entityId}`);
    if (op === 'replace' && !text) throw new Error(`replace requires text for ${entityId}`);
    if (op === 'replace' && !recordIds.length) throw new Error(`replace requires record ids for ${entityId}`);
    const list = byEntity.get(entityId) ?? [];
    list.push({ op: op as OperationRow['op'], recordIds, text });
    byEntity.set(entityId, list);
  }
  if (requireEveryEntity) {
    for (const id of targets) if (!byEntity.has(id)) throw new Error(`personality scan omitted ${id}`);
  }
  const used = activeChangeIds(state);
  const changes: Record<Id, Partial<EntityDelta>> = {};
  for (const [entityId, ops] of byEntity) {
    const active = activeRecords(state, kind, entityId).filter((record) => record.active);
    const activeIds = new Set(active.map((record) => record.id));
    const covered = new Set<Id>();
    const generated: { change: Change; oldTexts: string[] }[] = [];
    for (const op of ops) {
      for (const recordId of op.recordIds) {
        if (!activeIds.has(recordId)) throw new Error(`${entityId} has no active record ${recordId}`);
        if (covered.has(recordId)) throw new Error(`${entityId} record ${recordId} is covered twice`);
        covered.add(recordId);
      }
      if (op.op === 'keep') continue;
      const supersedes = op.op === 'remove' || op.op === 'replace' ? [...op.recordIds] : [];
      const change: Change = {
        id: allocator.changeId(kind, entityId, used),
        text: op.op === 'remove' ? null : op.text,
        supersedes,
      };
      used.add(change.id);
      generated.push({
        change,
        oldTexts: active.filter((record) => supersedes.includes(record.id)).map((record) => record.text).filter((text): text is string => Boolean(text)),
      });
    }
    if (activeIds.size > 0 && covered.size !== activeIds.size) {
      throw new Error(`${entityId} record operation coverage incomplete`);
    }
    const remaining = active
      .filter((record) => !covered.has(record.id))
      .map((record) => record.text)
      .filter((text): text is string => Boolean(text));
    const seenTexts = new Set(remaining.map(normalizeChangeText));
    for (const { change, oldTexts } of generated) {
      if (change.text == null) continue;
      const normalized = normalizeChangeText(change.text);
      if (!normalized) throw new Error(`${entityId} has empty ${kind} text`);
      if (seenTexts.has(normalized)) throw new Error(`${entityId} ${kind} operation makes no effective change`);
      for (const oldText of oldTexts) if (sameChangeText(oldText, change.text)) {
        throw new Error(`${entityId} ${kind} replacement repeats an old record`);
      }
      seenTexts.add(normalized);
    }
    if (generated.length) {
      changes[entityId] = kind === 'appearance'
        ? { appearanceChanges: generated.map(({ change }) => change) }
        : { personalityChanges: generated.map(({ change }) => change) };
    }
  }
  return changes;
}

function buildTasksPrompt(ctx: StageContext): string {
  const rows = roster(ctx.state).map((id) => taskLine(ctx.state, id));
  const now = ctx.state.time.dateTime;
  const sample = allTasks(ctx.state)[0]?.ownerId;
  return [
    '你是中文跑团游戏的任务判定器。只输出 JSON，不要解释。',
    '下面列出所有人物和他们的全部任务（包括已完成，也包括不在场人物）。请对每个人物给出一条决定。',
    '规则：',
    '- decisions 必须为每个有任务的人物各写一条，characterId 用括号里的 id 或人物全名；不能只写在场人物。',
    '- achieved 只列本轮新达成的任务 id；该人物其余任务保持原状，不要逐条输出 pending。',
    '- 没有新达成就写空数组；已完成的任务保持 achieved，不能改回 pending，也不要在 achieved 里重复列出。',
    '- 只有结算结果明确表明目标已经达成，才列入 achieved；只是尝试、接近、部分完成、被制止，都保持原状。',
    '- 行动结果里的 achieved 只描述那次行动，不等于任务完成；任务是否达成必须看目标本身。',
    `当前世界时间：${now}`,
    `结算结果：${resultText(ctx.results) || '（无）'}`,
    '人物和任务：',
    ...rows,
    `输出 {"decisions":[{"characterId":"${sample ?? '人物id'}","achieved":[]}]}。`,
  ].join('\n');
}

/** One decision per character covers all of that character's tasks. A missing
 * character is a hard coverage failure (retry, then abort the point); a missing
 * task row is not silently filled as pending because the character decision
 * itself asserts "none of my other tasks changed". */
function readTaskDecisions(value: unknown, state: WorldState): Record<Id, Partial<EntityDelta>> {
  const decisions = asRecord(value).decisions;
  if (!Array.isArray(decisions)) throw new Error('decisions must be an array');
  const rows = allTasks(state);
  const byTask = new Map(rows.map((row) => [row.task.id, row]));
  const ownerTasks = new Map<Id, Set<Id>>();
  for (const { ownerId, task } of rows) {
    const list = ownerTasks.get(ownerId) ?? new Set<Id>();
    list.add(task.id);
    ownerTasks.set(ownerId, list);
  }
  const required = [...ownerTasks.keys()].sort();
  const byCharacter = new Map<Id, Id[]>();
  for (const raw of decisions) {
    if (!isRecord(raw)) throw new Error('decision must be an object');
    const rawCharacterId = asString(raw.characterId);
    const characterId = resolveCharacterId(state, rawCharacterId);
    if (!characterId) throw new Error(referenceError(state, rawCharacterId, 'character', required[0]));
    if (!state.characters[characterId]) throw new Error(referenceError(state, rawCharacterId, 'character', required[0]));
    if (!Array.isArray(raw.achieved)) throw new Error(`achieved must be an array for ${characterId}`);
    const achieved = raw.achieved.map((item) => asString(item));
    if (!ownerTasks.has(characterId)) {
      if (achieved.length) throw new Error(`character ${characterId} has no tasks; achieved must be empty`);
      continue;
    }
    if (byCharacter.has(characterId)) throw new Error(`duplicate task decision for ${characterId}`);
    const own = ownerTasks.get(characterId)!;
    const seen = new Set<Id>();
    const list: Id[] = [];
    for (const taskId of achieved) {
      if (!taskId) throw new Error(`empty task id for ${characterId}`);
      if (isPlaceholderId(taskId)) throw new Error(referenceError(state, taskId, 'task', [...own][0]));
      if (!byTask.has(taskId)) throw new Error(referenceError(state, taskId, 'task', [...own][0]));
      const row = byTask.get(taskId)!;
      if (row.ownerId !== characterId) throw new Error(`task ${taskId} belongs to ${row.ownerId}, not ${characterId}`);
      if (seen.has(taskId)) throw new Error(`duplicate task ${taskId} under ${characterId}`);
      seen.add(taskId);
      if (row.task.status === 'achieved') continue;
      list.push(taskId);
    }
    byCharacter.set(characterId, list);
  }
  const missing = required.filter((id) => !byCharacter.has(id));
  if (missing.length) {
    throw new Error(`task character coverage incomplete: ${byCharacter.size}/${required.length}; missing ${missing.join(',')}`);
  }
  const changes: Record<Id, Partial<EntityDelta>> = {};
  for (const [ownerId, taskIds] of byCharacter) {
    if (taskIds.length) changes[ownerId] = { tasksAchieved: taskIds.sort() };
  }
  return changes;
}

function buildSubtasksPrompt(ctx: StageContext): string {
  const rows = roster(ctx.state).map((id) => taskLine(ctx.state, id));
  return [
    '你是中文跑团游戏的新增小任务判断器。只输出 JSON，不要解释。',
    '根据本组结算结果和当前任务状态，判断已有任务是否需要新增小任务。',
    '规则：',
    '- 小任务必须挂在已有任务下，parentTaskId 必须是下面出现的任务 id；负责人必须是父任务的负责人。',
    '- 新任务一律 pending，不要输出 status 或 ownerId；没有就输出空数组。',
    '- 不要为了凑数量新增任务；只有结算结果确实产生了新的具体目标时才新增。',
    `结算结果：${resultText(ctx.results) || '（无）'}`,
    '人物和任务：',
    ...rows,
    '输出 {"subtasks":[{"parentTaskId":"任务id","goal":"一句话具体目标"}]}。',
  ].join('\n');
}

function readSubtaskProposals(
  value: unknown,
  state: WorldState,
  allocator: LocalIdAllocator,
  maxNewTasks: number,
): Record<Id, Partial<EntityDelta>> {
  const rows = asRecord(value).subtasks;
  if (!Array.isArray(rows)) throw new Error('subtasks must be an array');
  if (rows.length > maxNewTasks) throw new Error(`subtask_budget_exceeded:${rows.length}>${maxNewTasks}`);
  const index = taskIndex(state);
  const used = new Set<Id>([...allKnownTaskIds(state), ...allEntityIds(state)]);
  const usedGoals = new Set<string>();
  const changes: Record<Id, Partial<EntityDelta>> = {};
  for (const raw of rows) {
    if (!isRecord(raw)) throw new Error('subtask must be an object');
    const parentTaskId = asString(raw.parentTaskId);
    if (isPlaceholderId(parentTaskId)) throw new Error(referenceError(state, parentTaskId, 'task', rows[0]?.task.id));
    const parent = index.get(parentTaskId);
    if (!parent) throw new Error(referenceError(state, parentTaskId, 'task', allTasks(state)[0]?.task.id));
    const goal = asString(raw.goal);
    if (!goal) throw new Error(`subtask for ${parentTaskId} has an empty goal`);
    const key = `${parentTaskId}:${normalizeChangeText(goal)}`;
    if (usedGoals.has(key)) throw new Error(`duplicate subtask under ${parentTaskId}`);
    usedGoals.add(key);
    const task = {
      id: allocator.taskId(parentTaskId, used),
      ownerId: parent.ownerId,
      parentTaskId,
      goal,
      status: 'pending' as const,
    };
    used.add(task.id);
    const list = changes[parent.ownerId]?.subtasksAdded ?? [];
    list.push(task);
    changes[parent.ownerId] = { subtasksAdded: list };
  }
  return changes;
}

function buildPersonalityPrompt(ctx: StageContext, triggerIds: Id[], recovered: boolean): string {
  const index = taskIndex(ctx.state);
  const triggerLines = triggerIds.map((taskId) => {
    const row = index.get(taskId);
    return row ? `- ${row.ownerId}：${row.task.id} ${row.task.goal}` : `- ${taskId}`;
  });
  return [
    '你是中文跑团游戏中的人物个性变化判断器。只输出 JSON，不要解释。',
    '本轮有新任务达成。请扫描所有人物（包括不在场人物），判断他们的个性是否因这些达成或当前处境发生变化。',
    '规则：',
    '- 只能新增、解除或替换已有有效个性变化；不能改初始个性；remove/replace 必须用 recordIds 引用该人物已有的有效变化 id。',
    '- 必须为每一个人物输出至少一个操作；没有变化就输出 keep，并列出该人物全部有效记录（没有记录则 recordIds 为空）。',
    '- 每个有效记录必须被 keep/remove/replace 覆盖一次；不能重复。',
    '- 新个性文本必须与旧文本有实际差异；没有实际变化就 keep。',
    '- 个性变化只由新达成任务触发；不要因为普通动作直接改个性。',
    recovered ? '- 本次是恢复后的补判定：只考虑本轮结算结果能够支持的新达成任务，不要把以前达成的任务当成新触发。' : '',
    `本组结算结果：${resultText(ctx.results) || '（无）'}`,
    '触发任务：',
    ...triggerLines,
    '人物个性：',
    ...roster(ctx.state).map((id) => `- ${personalityLine(ctx.state, id)}`),
    `输出 {"operations":[{"entityId":"${roster(ctx.state)[0] ?? '人物id'}","op":"keep|add|remove|replace","recordIds":[],"text":null}]}；entityId 用真实 id 或人物全名。`,
  ].filter(Boolean).join('\n');
}

function buildSanityPrompt(ctx: StageContext, owners: Id[]): string {
  return [
    '你是中文跑团游戏中的人物理智重算器。只输出 JSON，不要解释。',
    '下面这些人物在本轮发生了有效个性变化。请根据他们变化后的当前个性，重新给出 0-100 的整数理智值。',
    '规则：',
    '- 只为下面列出的人物输出；没有个性变化的人物不要输出。',
    '- 理智必须是 0 到 100 的整数；不要用小数、布尔或字符串。',
    '- 只依据变化后的个性和本轮已结算事实，不要新增任务、往事或心理原因。',
    `本组结算结果：${resultText(ctx.results) || '（无）'}`,
    ...owners.map((id) => `- ${personalityLine(ctx.state, id)}`),
    `输出 {"sanity":[{"characterId":"${owners[0]}","value":整数}]}；characterId 用真实 id 或人物全名。`,
  ].join('\n');
}

function readSanityValues(value: unknown, owners: Id[], state: WorldState): Record<Id, number> {
  const rows = asRecord(value).sanity;
  if (!Array.isArray(rows)) throw new Error('sanity must be an array');
  const expected = new Set(owners);
  const seen = new Set<Id>();
  const values: Record<Id, number> = {};
  for (const raw of rows) {
    if (!isRecord(raw)) throw new Error('sanity row must be an object');
    const rawCharacterId = asString(raw.characterId);
    const characterId = resolveCharacterId(state, rawCharacterId);
    if (!characterId) throw new Error(referenceError(state, rawCharacterId, 'character', owners[0]));
    if (!expected.has(characterId)) throw new Error(`sanity for a character without a personality change: ${rawCharacterId}${characterId !== rawCharacterId ? ` (${characterId})` : ''}`);
    if (seen.has(characterId)) throw new Error(`duplicate sanity for ${characterId}`);
    seen.add(characterId);
    const value = asInteger(raw.value);
    if (value == null || value < 0 || value > 100) throw new Error(`sanity must be an integer 0..100 for ${characterId}`);
    values[characterId] = value;
  }
  for (const owner of owners) if (!seen.has(owner)) throw new Error(`missing sanity for ${owner}`);
  return values;
}

function resultText(results: Record<Id, string>): string {
  return Object.entries(results).map(([id, text]) => `${id}：${text}`).join('；');
}
