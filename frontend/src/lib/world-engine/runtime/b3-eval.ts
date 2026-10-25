/** B3 evaluation harness: runs the frozen samples through the REAL model
 * port (encode → serial queue → engine → structured-output decode) and
 * reports, per task: the STRUCTURE rate (codec acceptance), the SEMANTIC
 * FLOOR rate (deterministic, plug-compatible judges — content-level
 * semantic quality arrives with real-model runs and richer judges), the
 * call count and the queue timings (queuedMs / runMs from the batch-one
 * instrumentation). The engine is injectable: a scripted engine makes the
 * harness itself deterministic in Node; the real wllama engine produces
 * the on-device numbers later — same harness, no code change. */
import type { ModelTask } from '../schedule';
import type { Json } from '../types';
import type { InferenceEngine } from './engine';
import { RuntimeWorldModelPort } from './model-port';
import { SerialInferenceQueue, type QueueTiming } from './inference-queue';
import { StructuredOutputError } from './structured-output';
import type { B3Sample } from './b3-samples';

/** Returns a failure note, or null when the output passes the floor. */
export type B3Judge = (input: Json, output: Json) => string | null;

/** The CHARACTER roster of an input's workingState (live and initial
 * sections): the pool trigger targets may draw from. */
function characterRoster(input: Json): Set<string> {
  const state = (input as { workingState?: Json }).workingState ?? {};
  const known = new Set<string>();
  for (const key of ['initial', undefined] as const) {
    const source = key ? (state as Record<string, Record<string, unknown>>)[key]?.characters : (state as Record<string, unknown>).characters;
    if (source && typeof source === 'object') for (const id of Object.keys(source as Record<string, unknown>)) known.add(id);
  }
  return known;
}

/** The entity roster an input's workingState actually presents: characters,
 * items AND locations, live and initial sections — the pool entity deltas
 * may address. */
function entityRoster(input: Json): Set<string> {
  const state = (input as { workingState?: Json }).workingState ?? {};
  const known = new Set<string>();
  for (const section of ['characters', 'items', 'locations'] as const) {
    for (const key of ['initial', undefined] as const) {
      const source = key ? (state as Record<string, Record<string, unknown>>)[key]?.[section] : (state as Record<string, unknown>)[section];
      if (source && typeof source === 'object') for (const id of Object.keys(source as Record<string, unknown>)) known.add(id);
    }
  }
  return known;
}

/** plan/continuation inputs carry no workingState — the round's frozen
 * order is the roster they plan over. */
function roundRoster(input: Json): Set<string> {
  const order = (input as { round?: { order?: string[] } }).round?.order ?? [];
  return new Set(order);
}

const DEFAULT_JUDGES: Partial<Record<ModelTask, B3Judge>> = {
  narration: (_input, output) => (typeof output === 'string' && [...output].length >= 10 ? null : '叙事正文不足 10 字'),
  reaction: (_input, output) => (typeof output === 'string' && [...output].length >= 4 ? null : '反应文本过短'),
  action: (_input, output) => {
    const kind = (output as { kind?: string }).kind;
    if (kind === 'skip') return null;
    return typeof (output as { text?: unknown }).text === 'string' && [...(output as { text: string }).text].length >= 2 ? null : '行动描述过短';
  },
  targets: (input, output) => {
    const known = characterRoster(input); // a trigger target is another CHARACTER, not a location or item
    const targets = (output as { targets: { targetId: string }[] }).targets;
    const unknown = targets.filter((target) => !known.has(target.targetId));
    return unknown.length === 0 ? null : `目标不在场: ${unknown.map((target) => target.targetId).join(', ')}`;
  },
  results: (_input, output) => (Object.keys(output as Record<string, unknown>).length >= 1 ? null : '结算结果为空'),
  updates: (input, output) => {
    const known = entityRoster(input);
    const calls = Array.isArray(output) ? output : [output];
    for (const call of calls) {
      for (const entityId of Object.keys((call as { changes: Record<string, unknown> }).changes)) {
        if (!known.has(entityId)) return `增量指向未知实体: ${entityId}`;
      }
    }
    return null;
  },
  pointPlan: (input, output) => {
    const known = roundRoster(input);
    for (const point of output as { actorIds: string[] }[]) {
      for (const actor of point.actorIds) {
        if (!known.has(actor)) return `计划了不在场的行动者: ${actor}`;
      }
    }
    return null;
  },
  continuation: (input, output) => {
    if ((output as { kind: string }).kind !== 'continue') return null;
    const known = roundRoster(input);
    const unknown = ((output as { candidateCharacterIds: string[] }).candidateCharacterIds).filter((id) => !known.has(id));
    return unknown.length === 0 ? null : `续轮候选不在场: ${unknown.join(', ')}`;
  },
};

/** Which phase failed: the engine call itself, the codec's structural
 * validation, the semantic floor — or the JUDGE crashing, which is an
 * evaluation-infrastructure failure: the structure verdict and the paid
 * generation cost stand, only the floor verdict is missing. A fully
 * successful sample fails nowhere. */
export type B3FailureStage = 'engine' | 'structure' | 'semantic' | 'judge';

export interface B3SampleResult {
  id: string;
  task: ModelTask;
  failure: B3FailureStage | null;
  structureError?: string;
  semanticNote?: string;
  judgeError?: string;
  /** Queue timing whenever the engine call completed (success or structural
   * rejection) — the generation cost happened either way. */
  timing: QueueTiming | null;
}

export interface B3TaskReport {
  task: ModelTask;
  samples: number;
  structureOk: number;
  structureRate: number;
  semanticFloorOk: number;
  semanticFloorRate: number;
  /** Actual engine completions (a failed load completes zero times). */
  calls: number;
  /** Average generation cost over EVERY completed generation — structural
   * rejections included: the tokens were burned either way. */
  avgQueuedMs: number;
  avgRunMs: number;
}

export interface B3Report {
  engine: { backend: string; modelId: string | null };
  totals: { samples: number; structureOk: number; semanticFloorOk: number; calls: number };
  perTask: B3TaskReport[];
  results: B3SampleResult[];
}

export interface B3EvalOptions {
  judges?: Partial<Record<ModelTask, B3Judge>>;
}

export async function runB3Evaluation(engine: InferenceEngine, samples: readonly B3Sample[] = [], options: B3EvalOptions = {}): Promise<B3Report> {
  const judges: Partial<Record<ModelTask, B3Judge>> = { ...DEFAULT_JUDGES, ...options.judges };
  // The harness counts ACTUAL completions by wrapping complete — no
  // engine cooperation needed, no receiver lost, and a failed load wraps
  // to zero calls.
  let completions = 0;
  // Explicit method forwarding on the ORIGINAL receiver: object spread
  // only copies own enumerable properties, so a class instance's
  // prototype methods (load/dispose) would be silently dropped.
  const countingEngine: InferenceEngine = {
    info: engine.info,
    load: (options) => engine.load(options),
    complete: (prompt, options) => {
      completions += 1;
      return engine.complete(prompt, options);
    },
    dispose: () => engine.dispose(),
  };
  const port = new RuntimeWorldModelPort(countingEngine, new SerialInferenceQueue());
  const engineCalls = new Map<string, number>(); // per sample: actual engine completions
  const results: B3SampleResult[] = [];
  for (const sample of samples) {
    const callsAtStart = completions;
    try {
      const generation = await port.generateDetailed(sample.task, sample.key, sample.input);
      engineCalls.set(sample.id, completions - callsAtStart);
      // The judge runs OUTSIDE the generation try: its crash must not
      // overturn the structure verdict or drop the paid timing.
      let note: string | null = null;
      let judgeError: string | undefined;
      try {
        note = judges[sample.task]?.(sample.input, generation.value) ?? null;
      } catch (error) {
        judgeError = `${(error as Error).name}: ${(error as Error).message}`;
      }
      results.push({
        id: sample.id, task: sample.task,
        failure: judgeError !== undefined ? 'judge' : note === null ? null : 'semantic',
        semanticNote: note ?? undefined, judgeError, timing: generation.timing,
      });
    } catch (error) {
      engineCalls.set(sample.id, completions - callsAtStart);
      if (error instanceof StructuredOutputError) {
        // The decode rejection carries the completed generation's timing:
        // the cost was paid even though the output was rejected.
        results.push({ id: sample.id, task: sample.task, failure: 'structure', structureError: error.reason, timing: (error as { timing?: QueueTiming }).timing ?? null });
      } else {
        results.push({ id: sample.id, task: sample.task, failure: 'engine', structureError: `${(error as Error).name}: ${(error as Error).message}`, timing: null });
      }
    }
  }
  const tasks = [...new Set(samples.map((sample) => sample.task))];
  const perTask: B3TaskReport[] = tasks.map((task) => {
    const rows = results.filter((result) => result.task === task);
    const timed = rows.filter((row) => row.timing !== null);
    const avg = (pick: (timing: QueueTiming) => number) => (timed.length ? timed.reduce((sum, row) => sum + pick(row.timing!), 0) / timed.length : 0);
    return {
      task, samples: rows.length,
      structureOk: rows.filter((row) => row.failure !== 'engine' && row.failure !== 'structure').length,
      structureRate: rows.length ? rows.filter((row) => row.failure !== 'engine' && row.failure !== 'structure').length / rows.length : 0,
      semanticFloorOk: rows.filter((row) => row.failure === null).length,
      semanticFloorRate: rows.length ? rows.filter((row) => row.failure === null).length / rows.length : 0,
      calls: rows.reduce((sum, row) => sum + (engineCalls.get(row.id) ?? 0), 0),
      avgQueuedMs: Math.round(avg((timing) => timing.queuedMs) * 100) / 100,
      avgRunMs: Math.round(avg((timing) => timing.runMs) * 100) / 100,
    };
  });
  return {
    engine: { ...engine.info },
    totals: {
      samples: results.length,
      structureOk: results.filter((row) => row.failure !== 'engine' && row.failure !== 'structure').length,
      semanticFloorOk: results.filter((row) => row.failure === null).length,
      calls: results.reduce((sum, row) => sum + (engineCalls.get(row.id) ?? 0), 0),
    },
    perTask,
    results,
  };
}

/** One-line console summary for manual runs. */
export function formatB3Summary(report: B3Report): string {
  const lines = report.perTask.map((row) =>
    `${row.task}: 结构 ${row.structureOk}/${row.samples}，底线 ${row.semanticFloorOk}/${row.samples}，调用 ${row.calls}，排队 ${row.avgQueuedMs}ms / 推理 ${row.avgRunMs}ms`);
  return [`B3 评测 ${report.engine.backend}（${report.engine.modelId ?? 'no model'}）：结构 ${report.totals.structureOk}/${report.totals.samples}，底线 ${report.totals.semanticFloorOk}/${report.totals.samples}`, ...lines].join('\n');
}
