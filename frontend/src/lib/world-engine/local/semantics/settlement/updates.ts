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
  isRecord, LocalIdAllocator, maxChangeSequence, movableIds, normalizeChangeText, personalityLine, personalityOwnersAbove, scopedState,
  positionFromRow, projectStage, roster, sameChangeText, taskIndex, taskLine, toJson,
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
  /** The state the stages judge: the full world, or the protagonist's scene. */
  scope: WorldState;
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
        required: ['characterId', 'taskId', 'label'],
        properties: {
          characterId: { type: 'string' },
          taskId: { type: 'string' },
          label: { enum: ['pending', 'achieved'] },
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


const MERGED_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity'],
  properties: {
    position: POSITION_SCHEMA.properties.changes,
    appearance: OPERATIONS_SCHEMA.properties.operations,
    tasks: TASKS_SCHEMA.properties.decisions,
    subtasks: SUBTASKS_SCHEMA.properties.subtasks,
    personality: OPERATIONS_SCHEMA.properties.operations,
    sanity: SANITY_SCHEMA.properties.sanity,
  },
};

const MERGED_NOTE = [
  '一次回答，六个键，没有变化的键给空数组。',
  '规则：',
  '- position：只列真的换了位置的实体；containerId 必须是已登记 id；不能成环。',
  '- appearance：只列本回合外貌有变化的实体；op=add/remove/replace/keep，recordIds 指向已有记录 id，text 是新描述。',
  '- tasks：逐个判断待办任务；只有结果明确表明目标达成才写 achieved，只是尝试、接近、被制止都写 pending。没把握就不要列。',
  '- subtasks：只为已达成的大任务补下一步小目标，最多 3 条。',
  '- personality：只有本回合有新任务达成时才写；op=keep/add/remove/replace。',
  '- sanity：只为个性真的变化的人物写 0-100 的整数，其他人不要列。',
  '- 不得新增人物、地点、物品、任务、往事；不得把行动结果当成任务达成。',
];

function buildMergedPrompt(ctx: StageContext): string {
  const scope = ctx.scope;
  const entities = movableIds(scope).map((id) => `- ${positionLineFor(scope, id)}`);
  const tasks = roster(scope).map((id) => taskLine(scope, id));
  const people = roster(scope).map((id) => `- ${id}=${scope.initial.characters[id].name}：${personalityLine(scope, id)}`);
  return [
    '你是中文跑团游戏的结算记录器。只输出一个 JSON 对象，不要解释。',
    ...MERGED_NOTE,
    `结算结果：${resultText(ctx.results) || '（无）'}`,
    '可移动实体和当前位置：',
    ...entities,
    '地点和容器（id=名字，槽位）：',
    ...containerCatalog(scope),
    '人物和任务：',
    ...tasks,
    '人物个性：',
    ...people,
    `当前时间：${scope.time.dateTime}`,
    '输出：{"position":[],"appearance":[],"tasks":[],"subtasks":[],"personality":[],"sanity":[]}。',
  ].join('\n');
}

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
      scope: this.options.sceneScope ? scopedState(parsed.workingState, parsed.workingState.protagonistId) : parsed.workingState,
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
      if (stage === 'tasks') {
        batch.tasksStageSeen = true;
        batch.tasksFailed = Boolean(outcome.error) || outcome.fallback;
        batch.tasksAchieved = achievedFromChanges(changes);
      }
      if (stage === 'personality') batch.personalityOwners = new Set(Object.keys(changes));
      const value: UpdatesCall = { stage, changes: changes as UpdatesCall['changes'] };
      return this.finish(key, value, [outcome], started, {
        mode: ctx.mode,
        sanityBasis,
        taskCoverageIds: roster(ctx.scope),
        personalityCoverageIds: stage === 'tasks'
          ? (achievedFromChanges(changes).size > 0 ? roster(ctx.scope) : [])
          : stage === 'personality' && Object.keys(changes).length > 0
            ? roster(ctx.scope)
            : [],
      });
    }
    if (this.options.mergedStages) return this.runMerged(key, ctx, started);
    const calls: UpdatesCall[] = [];
    const outcomes: StageOutcome[] = [];
    let view = ctx.state;
    let newAchieved = new Set<Id>();
    let mergedPersonalityOwners = new Set<Id>();
    for (const currentStage of SETTLEMENT_STAGES) {
      const stageCtx: StageContext = {
        ...ctx,
        state: view,
        scope: this.options.sceneScope ? scopedState(view, view.protagonistId) : view,
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
    const taskCoverageIds = roster(ctx.scope);
    const personalityCoverageIds = newAchieved.size > 0 ? taskCoverageIds : [];
    const detail = {
      mode: ctx.mode,
      sanityBasis: 'merged_personality_stage',
      taskCoverageIds,
      personalityCoverageIds,
      newlyAchievedTaskIds: [...newAchieved].sort(),
      personalityChangedIds: [...mergedPersonalityOwners].sort(),
      stages: outcomes.map((outcome, index) => ({
        stage: SETTLEMENT_STAGES[index],
        error: outcome.error ?? null,
        fallback: outcome.fallback,
        ...outcome.detail,
      })),
    };
    return this.finish(key, calls, outcomes, started, detail);
  }


  /** One model call carrying all six stage sections. The stage order, the
   * validators and the projection checks stay identical; only the number of
   * round trips changes, which is what makes a six-stage settlement fit the
   * browser wait budget. Each section is validated on its own: a broken
   * section becomes an empty stage with evidence, never a discarded round. */
  private async runMerged(key: Id, ctx: StageContext, started: number): Promise<SettlementOutcome<UpdatesCall[] | UpdatesCall>> {
    const prompt = buildMergedPrompt(ctx);
    const outcomes: StageOutcome[] = [];
    const calls: UpdatesCall[] = [];
    let view = ctx.state;
    let newAchieved = new Set<Id>();
    let personalityOwners = new Set<Id>();
    let answer: { value: unknown; calls: ModelCallEvidence[] } | null = null;
    let overallError: string | undefined;
    try {
      answer = await callJson(this.engine, prompt, {
        maxTokens: this.options.maxTokens?.updates ?? 420,
        temperature: this.options.temperature ?? 0,
        timeoutMs: this.options.timeoutMs ?? 120_000,
        maxPromptChars: this.options.maxPromptChars ?? 11_000,
        jsonSchema: MERGED_SCHEMA,
        validate: (value) => {
          if (!isRecord(value)) throw new Error('merged answer must be an object');
          for (const section of ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity']) {
            if (!Array.isArray(value[section])) throw new Error(`merged answer is missing ${section}`);
          }
        },
      });
    } catch (error) {
      overallError = errorText(error);
    }
    const sections = (answer?.value ?? {}) as Record<string, unknown>;
    const read = <T>(label: string, fn: () => T, fallbackValue: T): T => {
      try {
        return fn();
      } catch (error) {
        outcomes.push({ changes: {}, detail: { mergedSection: label }, error: errorText(error), fallback: true, calls: [] });
        return fallbackValue;
      }
    };
    const nextCtx = (): StageContext => ({
      ...ctx,
      state: view,
      scope: this.options.sceneScope ? scopedState(view, view.protagonistId) : view,
      newAchieved,
      recoveredAchieved: new Set<Id>(),
      personalityOwners,
    });
    // The single merged model call is the evidence for the whole batch: attach
    // its call records to the first stage that lands so `ms`/`raw` report the
    // real generation instead of zero.
    let callsAttached = false;
    const mergedCalls = answer?.calls ?? [];
    const apply = (stage: UpdatesStage, changes: Record<Id, Partial<EntityDelta>>, detail: Record<string, unknown>) => {
      const attach = !callsAttached ? mergedCalls : [];
      callsAttached = true;
      try {
        view = projectStage(view, stage, changes);
      } catch (error) {
        outcomes.push({ changes: {}, detail: { ...detail, stage }, error: `stage_projection_rejected:${errorText(error)}`, fallback: true, calls: [] });
        calls.push({ stage, changes: {} });
        return;
      }
      outcomes.push({ changes, detail: { ...detail, stage, mergedSection: true }, fallback: false, calls: attach });
      calls.push({ stage, changes: changes as UpdatesCall['changes'] });
      if (stage === 'tasks') newAchieved = achievedFromChanges(changes);
      if (stage === 'personality') personalityOwners = new Set(Object.keys(changes));
    };

    const positionScope = nextCtx().scope;
    const position = read('position', () => readPositionChanges({ changes: sections.position }, positionScope), {});
    apply('position', position, { changedEntityIds: Object.keys(position).sort() });

    const appearanceScope = nextCtx().scope;
    const appearance = read('appearance', () => readDescriptionOperations({ operations: sections.appearance }, appearanceScope, 'appearance', this.allocator, false), {});
    apply('appearance', appearance, { changedEntityIds: Object.keys(appearance).sort() });

    const taskScope = nextCtx().scope;
    const tasks = read('tasks', () => readTaskDecisions({ decisions: sections.tasks }, taskScope), {});
    apply('tasks', tasks, { decisionCoverage: taskDecisionCoverage() });

    const subtaskScope = nextCtx().scope;
    const subtasks = read('subtasks', () => readSubtaskProposals({ subtasks: sections.subtasks }, subtaskScope, this.allocator, this.options.maxNewTasks ?? 8), {});
    apply('subtasks', subtasks, { addedTaskIds: Object.values(subtasks).flatMap((delta) => (delta.subtasksAdded ?? []).map((task) => task.id)).sort() });

    const personalityScope = nextCtx().scope;
    const personality = newAchieved.size > 0
      ? read('personality', () => readDescriptionOperations({ operations: sections.personality }, personalityScope, 'personality', this.allocator, true), {})
      : {};
    apply('personality', personality, { triggeredByTaskIds: [...newAchieved].sort(), triggered: newAchieved.size > 0 });

    const sanityOwners = [...personalityOwners].sort();
    const sanity: Record<Id, Partial<EntityDelta>> = {};
    if (sanityOwners.length) {
      try {
        const values = readSanityValues({ sanity: sections.sanity }, sanityOwners);
        for (const owner of sanityOwners) sanity[owner] = { sanitySet: values[owner] };
      } catch (error) {
        const current = nextCtx().scope;
        for (const owner of sanityOwners) if (current.characters[owner]) sanity[owner] = { sanitySet: current.characters[owner].sanity };
        outcomes.push({ changes: {}, detail: { mergedSection: 'sanity', fallback: 'current_sanity' }, error: errorText(error), fallback: true, calls: [] });
      }
    }
    apply('sanity', sanity, { owners: sanityOwners });

    if (overallError && calls.every((call) => Object.keys(call.changes).length === 0)) {
      return this.failure(key, overallError, started);
    }
    const detail = {
      mode: ctx.mode,
      mergedStages: true,
      taskCoverageIds: roster(ctx.scope),
      personalityCoverageIds: newAchieved.size > 0 ? roster(ctx.scope) : [],
      newlyAchievedTaskIds: [...newAchieved].sort(),
      personalityChangedIds: [...personalityOwners].sort(),
      stageErrors: outcomes.filter((outcome) => outcome.error).map((outcome) => outcome.error),
      stages: outcomes,
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
  const scanned = movableIds(ctx.scope);
  if (ctx.mode === 'time_scan') {
    return { changes: {}, detail: { scannedEntityIds: scanned, skipped: 'time_scan_no_action' }, fallback: false, calls: [] };
  }
  const prompt = buildPositionPrompt(ctx.scope, ctx.results);
  try {
    const answer = await callJson(ctx.engine, prompt, {
      maxTokens: stageTokens(ctx, 240),
      temperature: ctx.options.temperature ?? 0,
      timeoutMs: ctx.options.timeoutMs,
      maxPromptChars: ctx.options.maxPromptChars,
      jsonSchema: POSITION_SCHEMA,
      validate: (value) => validatePositionAnswer(value, ctx.scope),
    });
    const changes = readPositionChanges(answer.value, ctx.scope);
    projectStage(ctx.scope, 'position', changes);
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
  const scanned = allEntityIds(ctx.scope);
  if (ctx.mode === 'time_scan') {
    return { changes: {}, detail: { scannedEntityIds: scanned, skipped: 'time_scan_no_action' }, fallback: false, calls: [] };
  }
  const prompt = buildDescriptionPrompt(ctx.scope, ctx.results, 'appearance');
  try {
    const answer = await callJson(ctx.engine, prompt, {
      maxTokens: stageTokens(ctx, 420),
      temperature: ctx.options.temperature ?? 0,
      timeoutMs: ctx.options.timeoutMs,
      maxPromptChars: ctx.options.maxPromptChars,
      jsonSchema: OPERATIONS_SCHEMA,
      validate: (value) => readDescriptionOperations(value, ctx.scope, 'appearance', ctx.allocator, false),
    });
    const changes = readDescriptionOperations(answer.value, ctx.scope, 'appearance', ctx.allocator, false);
    projectStage(ctx.scope, 'appearance', changes);
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
  const rows = allTasks(ctx.scope);
  const characters = roster(ctx.scope);
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
  try {
    const answer = await callJson(ctx.engine, prompt, {
      maxTokens: stageTokens(ctx, 420),
      temperature: ctx.options.temperature ?? 0,
      timeoutMs: ctx.options.timeoutMs,
      maxPromptChars: ctx.options.maxPromptChars,
      jsonSchema: TASKS_SCHEMA,
      validate: (value) => readTaskDecisions(value, ctx.scope),
    });
    const changes = readTaskDecisions(answer.value, ctx.scope);
    return {
      changes,
      detail: {
        taskCoverageIds: characters,
        decidedTaskIds: rows.map(({ task }) => task.id).sort(),
        decisionCoverage: taskDecisionCoverage(),
        newlyAchievedTaskIds: [...achievedFromChanges(changes)].sort(),
      },
      fallback: false,
      calls: answer.calls,
    };
  } catch (error) {
    return stageFailure({ taskCoverageIds: characters, decidedTaskIds: rows.map(({ task }) => task.id).sort() }, error);
  }
}

async function stageSubtasks(ctx: StageContext): Promise<StageOutcome> {
  const rows = allTasks(ctx.scope);
  const characters = roster(ctx.scope);
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
      validate: (value) => readSubtaskProposals(value, ctx.scope, ctx.allocator, ctx.options.maxNewTasks ?? 8),
    });
    const changes = readSubtaskProposals(answer.value, ctx.scope, ctx.allocator, ctx.options.maxNewTasks ?? 8);
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
  const characters = roster(ctx.scope);
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
      validate: (value) => readDescriptionOperations(value, ctx.scope, 'personality', ctx.allocator, true),
    });
    const changes = readDescriptionOperations(answer.value, ctx.scope, 'personality', ctx.allocator, true);
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
  const owners = [...ctx.personalityOwners].filter((id) => Boolean(ctx.scope.characters[id])).sort();
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
      validate: (value) => readSanityValues(value, owners),
    });
    const values = readSanityValues(answer.value, owners);
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
    for (const owner of owners) changes[owner] = { sanitySet: ctx.scope.characters[owner].sanity };
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
    '输出 {"changes":[{"entityId":"id","containerId":"id","slotId":null,"relativeTo":null}]}；没有变化输出 {"changes":[]}。',
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
    const entityId = asString(raw.entityId);
    if (!movable.has(entityId)) throw new Error(`position entity is not movable: ${entityId || '?'}`);
    if (seen.has(entityId)) throw new Error(`duplicate position change: ${entityId}`);
    seen.add(entityId);
    const position = positionFromRow(raw);
    if (!position) throw new Error(`invalid position for ${entityId}`);
    if (!known.has(position.containerId)) throw new Error(`unknown container ${position.containerId}`);
    if (position.containerId === entityId) throw new Error(`entity ${entityId} cannot contain itself`);
    const slots = slotsOf(state, position.containerId);
    if (position.slotId != null && !slots.some((slot) => slot.id === position.slotId)) {
      throw new Error(`slot ${position.slotId} does not belong to ${position.containerId}`);
    }
    if (position.relativeTo) {
      if (!known.has(position.relativeTo.entityId)) throw new Error(`unknown relative target ${position.relativeTo.entityId}`);
      if (position.relativeTo.entityId === entityId) throw new Error(`entity ${entityId} cannot be relative to itself`);
      if (!RELATIONS.includes(position.relativeTo.relation)) throw new Error(`invalid relation ${position.relativeTo.relation}`);
    }
    changes[entityId] = { positionSet: position };
  }
  return changes;
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
    '输出 {"operations":[{"entityId":"id","op":"keep|add|remove|replace","recordIds":[],"text":null}]}。',
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
    const entityId = asString(raw.entityId);
    if (!targets.has(entityId)) throw new Error(`operation targets an unknown ${kind === 'appearance' ? 'entity' : 'character'}: ${entityId || '?'}`);
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
  const rows = roster(ctx.scope).map((id) => taskLine(ctx.scope, id));
  const now = ctx.scope.time.dateTime;
  return [
    '你是中文跑团游戏的任务判定器。只输出 JSON，不要解释。',
    '下面列出所有人物和他们的全部任务（包括已完成）。请逐个判断当前状态：pending 或 achieved。',
    '规则：',
    '- 已完成的任务保持 achieved，不能改回 pending。',
    '- 只有结算结果明确表明目标已经达成，才把 pending 改为 achieved；只是尝试、接近、部分完成、被制止、目标尚未完成，都保持 pending。',
    '- 行动结果里的 achieved 只描述那次行动，不等于任务完成；任务是否达成必须看目标本身。',
    '- 必须覆盖每一个任务；没有任务的人物不用输出。',
    `当前世界时间：${now}`,
    `结算结果：${resultText(ctx.results) || '（无）'}`,
    '人物和任务：',
    ...rows,
    '输出 {"decisions":[{"characterId":"人物id","taskId":"任务id","label":"pending|achieved"}]}。',
  ].join('\n');
}

let lastTaskCoverage: { decided: number; total: number } = { decided: 0, total: 0 };

function recordTaskCoverage(decided: number, total: number): void {
  lastTaskCoverage = { decided, total };
}

export function taskDecisionCoverage(): { decided: number; total: number } {
  return lastTaskCoverage;
}


function readTaskDecisions(value: unknown, state: WorldState): Record<Id, Partial<EntityDelta>> {
  const decisions = asRecord(value).decisions;
  if (!Array.isArray(decisions)) throw new Error('decisions must be an array');
  const rows = allTasks(state);
  const byTask = new Map(rows.map((row) => [row.task.id, row]));
  const seen = new Set<Id>();
  const achieved = new Map<Id, Id[]>();
  for (const raw of decisions) {
    if (!isRecord(raw)) throw new Error('decision must be an object');
    const characterId = asString(raw.characterId);
    const taskId = asString(raw.taskId);
    const row = byTask.get(taskId);
    if (!row || row.ownerId !== characterId) throw new Error(`decision names an unknown task/owner: ${characterId}/${taskId}`);
    if (seen.has(taskId)) throw new Error(`duplicate task decision: ${taskId}`);
    seen.add(taskId);
    const label = asString(raw.label);
    if (label !== 'pending' && label !== 'achieved') throw new Error(`invalid task label for ${taskId}`);
    if (row.task.status === 'achieved' && label !== 'achieved') throw new Error(`achieved task ${taskId} cannot be reopened`);
    if (row.task.status === 'pending' && label === 'achieved') {
      const list = achieved.get(characterId) ?? [];
      list.push(taskId);
      achieved.set(characterId, list);
    }
  }
  // A small model often answers only the tasks it thinks changed. Silence is
  // not evidence of completion: undecided tasks keep their current status,
  // and the coverage gap is recorded in evidence instead of rejecting the
  // whole stage (which threw away the tasks that were judged correctly).
  recordTaskCoverage(seen.size, rows.length);
  const changes: Record<Id, Partial<EntityDelta>> = {};
  for (const [ownerId, taskIds] of achieved) changes[ownerId] = { tasksAchieved: taskIds.sort() };
  return changes;
}

function buildSubtasksPrompt(ctx: StageContext): string {
  const rows = roster(ctx.scope).map((id) => taskLine(ctx.scope, id));
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
    const parent = index.get(parentTaskId);
    if (!parent) throw new Error(`unknown subtask parent ${parentTaskId || '?'}`);
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
  const index = taskIndex(ctx.scope);
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
    ...roster(ctx.scope).map((id) => `- ${personalityLine(ctx.scope, id)}`),
    '输出 {"operations":[{"entityId":"人物id","op":"keep|add|remove|replace","recordIds":[],"text":null}]}。',
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
    ...owners.map((id) => `- ${personalityLine(ctx.scope, id)}`),
    '输出 {"sanity":[{"characterId":"人物id","value":整数}]}。',
  ].join('\n');
}

function readSanityValues(value: unknown, owners: Id[]): Record<Id, number> {
  const rows = asRecord(value).sanity;
  if (!Array.isArray(rows)) throw new Error('sanity must be an array');
  const expected = new Set(owners);
  const seen = new Set<Id>();
  const values: Record<Id, number> = {};
  for (const raw of rows) {
    if (!isRecord(raw)) throw new Error('sanity row must be an object');
    const characterId = asString(raw.characterId);
    if (!expected.has(characterId)) throw new Error(`sanity for a character without a personality change: ${characterId || '?'}`);
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
