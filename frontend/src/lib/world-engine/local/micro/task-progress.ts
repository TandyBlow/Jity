/** Task-progress micro workflow: condition decomposition + a pair verifier.
 *
 * The program decomposes a task goal into the conditions it names (time,
 * location, item, target, confirmation, action). The pair model scores whether
 * a settled fact is relevant and whether it satisfies the goal. A low-
 * confidence or low-relevance answer returns null and the LLM verifier stays
 * the authority; this port never invents an achievement.
 */
import type { Id, WorldState } from '../../types';
import type { MicroTaskVerdict, MicroTaskVerifierFn } from '../semantics/settlement/types';
import { matchLocation } from '../semantics/settlement/fact-destinations';
import { matchItems } from '../semantics/actions/structure';
import { getMicroTokenizer } from './shared';
import { createMicroRuntime } from './runtime';

const CONFIRM = ['确认', '报告', '说明', '告知', '问清', '核实', '看见', '检查', '证明', '登记', '回答', '听清'];
const TIME = /\d{1,2}:\d{2}|停赛前|结束前|午夜|天亮|天黑|明天|次日|黄昏|清晨|小时后|分钟后|入夜/u;
const ACTION = ['前往', '走向', '走进', '进入', '赶到', '回到', '退到', '离开', '登上', '走到',
  '守住', '护住', '挡住', '拦住', '守', '递给', '交给', '报告', '说明', '询问', '问清', '检查', '确认'];

export interface TaskConditions {
  goal: string;
  time: string | null;
  location: string | null;
  item: string | null;
  target: string | null;
  confirmation: string | null;
  action: string | null;
  conditions: string[];
}

export function decomposeTask(goal: string, state: WorldState, ownerName: string): TaskConditions {
  const items = Object.entries(state.initial.items).map(([id, item]) => ({ id, name: item.name ?? id }));
  const itemId = matchItems(goal, items, ownerName)[0];
  const item = itemId ? (state.initial.items[itemId]?.name ?? itemId) : null;
  const target = Object.values(state.initial.characters).find((character) => character.name && goal.includes(character.name))?.name ?? null;
  const location = matchLocation(state, goal)?.name ?? null;
  const time = TIME.exec(goal)?.[0] ?? null;
  const confirmation = CONFIRM.find((word) => goal.includes(word)) ?? null;
  const action = ACTION.find((word) => goal.includes(word)) ?? null;
  const conditions = [
    time ? `时间=${time}` : '',
    location ? `地点=${location}` : '',
    item ? `物品=${item}` : '',
    target ? `对象=${target}` : '',
    confirmation ? `确认=${confirmation}` : '',
    action ? `动作=${action}` : '',
  ].filter(Boolean);
  return { goal, time, location, item, target, confirmation, action, conditions };
}

const SAT = ['yes', 'partial', 'no'] as const;

export interface MicroTaskProgressOptions {
  vocabUrl?: string;
  modelUrl?: string;
  threshold?: { relevance?: number; satisfaction?: number; yes?: number };
  onStats?: (record: {
    supports: number; inferences: number; headOutputs: number; ms: number; loadMs: number;
    source: 'micro' | 'abstain'; reason?: string;
  }) => void;
  /** Test/embedded scorer; the default runs the int8 pair model. */
  scoring?: (rows: Array<{ context: string; fact: string }>) => Promise<Array<{ relevance: number; satisfaction: number[] }> | null> | Array<{ relevance: number; satisfaction: number[] }> | null;
}

function sigmoid(value: number): number {
  return 1 / (1 + Math.exp(-value));
}

function softmax(values: number[]): number[] {
  const max = Math.max(...values);
  const exps = values.map((value) => Math.exp(value - max));
  const sum = exps.reduce((left, right) => left + right, 0);
  return exps.map((value) => value / sum);
}

/** Explicit outcome wording is deterministic evidence, but «达到目的» is NOT
 * task completion: an action can succeed while only one condition is met. */
export function outcomeGate(factText: string): 'partial' | 'no' | null {
  if (/（没有成功）|（被阻止）|（没有变化）|没有成功|被阻止/u.test(factText)) return 'no';
  if (/（只完成一部分）|只完成一部分/u.test(factText)) return 'partial';
  return null;
}

/** How many of the decomposed goal conditions the fact names. A `yes` from the
 * pair model is downgraded to partial unless every named condition is covered. */
export function conditionCoverage(conditions: TaskConditions, factText: string): { matched: number; total: number; missing: string[] } {
  const checks: Array<[string, boolean]> = [
    ...(conditions.time ? [[`时间=${conditions.time}`, factText.includes(conditions.time)] as [string, boolean]] : []),
    ...(conditions.location ? [[`地点=${conditions.location}`, factText.includes(conditions.location)] as [string, boolean]] : []),
    ...(conditions.item ? [[`物品=${conditions.item}`, factText.includes(conditions.item)] as [string, boolean]] : []),
    ...(conditions.target ? [[`对象=${conditions.target}`, factText.includes(conditions.target)] as [string, boolean]] : []),
    ...(conditions.confirmation ? [[`确认=${conditions.confirmation}`, CONFIRM.some((word) => factText.includes(word))] as [string, boolean]] : []),
    ...(conditions.action ? [[`动作=${conditions.action}`, ACTION.some((word) => factText.includes(word))] as [string, boolean]] : []),
  ];
  const missing = checks.filter(([, hit]) => !hit).map(([label]) => label);
  return { matched: checks.length - missing.length, total: checks.length, missing };
}

export function createMicroTaskVerifier(options: MicroTaskProgressOptions = {}): MicroTaskVerifierFn {
  const runtime = createMicroRuntime({ threads: 1 });
  async function ensure() {
    return {
      tok: await getMicroTokenizer(options.vocabUrl),
      session: await runtime.load(options.modelUrl ?? '/micro/task-match-int8.onnx'),
    };
  }

  async function scoreDefault(rows: Array<{ context: string; fact: string }>): Promise<Array<{ relevance: number; satisfaction: number[] }> | null> {
    const { tok, session } = await ensure();
    const ort = await import('onnxruntime-web/wasm');
    const out: Array<{ relevance: number; satisfaction: number[] }> = [];
    for (const row of rows) {
      const { ids } = tok.encodePair(row.context, row.fact, 160);
      const data = BigInt64Array.from(ids, (value) => BigInt(value));
      const mask = BigInt64Array.from(ids, () => 1n);
      const result = await session.run({
        input_ids: new ort.Tensor('int64', data, [1, ids.length]),
        attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
      });
      const relevanceLogit = (result.relevance?.data as Float32Array | undefined)?.[0];
      const satisfaction = Array.from((result.satisfaction?.data ?? []) as Float32Array);
      if (relevanceLogit == null || satisfaction.length !== SAT.length) return null;
      out.push({ relevance: sigmoid(relevanceLogit), satisfaction: softmax(satisfaction) });
    }
    return out;
  }

  return async (request): Promise<MicroTaskVerdict[] | null> => {
    const started = performance.now();
    if (!request.supports.length) return [];
    const rows = request.supports.map((support) => ({ context: `任务：${support.goal}`, fact: support.factText }));
    let scores: Array<{ relevance: number; satisfaction: number[] }> | null;
    try {
      scores = await (options.scoring ?? scoreDefault)(rows);
    } catch {
      scores = null;
    }
    if (!scores || scores.length !== request.supports.length) {
      return abstain(started, runtime, options, request.supports.length, 'model_unavailable');
    }
    const threshold = {
      relevance: options.threshold?.relevance ?? 0.5,
      satisfaction: options.threshold?.satisfaction ?? 0.6,
      yes: options.threshold?.yes ?? 0.7,
    };
    const verdicts: MicroTaskVerdict[] = [];
    for (const [index, support] of request.supports.entries()) {
      const score = scores[index];
      // A fact the model cannot connect to the task is not a rejection: it is
      // an abstain, so the LLM verifier keeps authority over false negatives.
      if (score.relevance < threshold.relevance) {
        return abstain(started, runtime, options, request.supports.length, 'low_relevance');
      }
      const gate = outcomeGate(support.factText);
      const conditions = decomposeTask(support.goal, request.state, support.ownerName);
      const coverage = conditionCoverage(conditions, support.factText);
      const probabilities = score.satisfaction;
      const best = probabilities.indexOf(Math.max(...probabilities));
      let label = gate ?? SAT[best];
      let confidence = gate ? 1 : probabilities[best];
      // An action success is not a task completion: require the conditions the
      // goal actually names. Missing conditions cap the verdict at partial;
      // a fact matching none of them is a no.
      if (coverage.total > 0 && coverage.matched < coverage.total && label === 'yes') {
        label = 'partial';
        confidence = Math.min(confidence, 0.7);
      }
      if (coverage.total > 0 && coverage.matched === 0 && label !== 'no') {
        label = 'no';
        confidence = Math.min(confidence, 0.7);
      }
      const minimum = label === 'yes' ? threshold.yes : threshold.satisfaction;
      if (confidence < minimum) {
        return abstain(started, runtime, options, request.supports.length, 'low_confidence');
      }
      verdicts.push({
        characterId: support.characterId,
        taskId: support.taskId,
        satisfied: label,
        confidence,
        reason: `条件 ${coverage.matched}/${coverage.total}${coverage.missing.length ? `，缺 ${coverage.missing.join('、')}` : ''}`,
      });
    }
    options.onStats?.({
      supports: request.supports.length, inferences: request.supports.length,
      headOutputs: request.supports.length * 2,
      ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs),
      source: 'micro',
    });
    return verdicts;
  };
}
function abstain(
  started: number,
  runtime: ReturnType<typeof createMicroRuntime>,
  options: MicroTaskProgressOptions,
  supports: number,
  reason: string,
): null {
  options.onStats?.({
    supports, inferences: 0, headOutputs: 0,
    ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs),
    source: 'abstain', reason,
  });
  return null;
}

