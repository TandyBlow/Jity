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
import { rankItems } from '../semantics/actions/structure';
import { getMicroTokenizer } from './shared';
import { createMicroRuntime } from './runtime';

export const CONFIRM = ['确认', '报告', '说明', '告知', '问清', '核实', '看见', '检查', '证明', '登记', '回答', '听清', '核对'];
const TIME = /\d{1,2}:\d{2}|停赛前|结束前|午夜|天亮|天黑|明天|次日|黄昏|清晨|小时后|分钟后|入夜/u;
const ACTION = ['前往', '走向', '走进', '进入', '赶到', '回到', '退到', '离开', '登上', '走到',
  '守住', '护住', '挡住', '拦住', '守', '递给', '交给', '戴上', '戴好', '拿起', '拿到', '取得',
  '获取', '开笼', '放出', '发布', '扣好', '恢复', '更换', '换上', '打开', '使用', '到达',
  '安排', '询问', '查明', '保留', '让出', '拖到', '推到', '拍', '搬', '移', '摆', '叠', '挂'];

export interface TaskConditions {
  goal: string;
  time: string | null;
  location: string | null;
  item: string | null;
  target: string | null;
  confirmation: string | null;
  action: string | null;
  decision: string | null;
  conditions: string[];
}

/** Lexical relevance prefilter, not a satisfaction decision: if the fact does
 * not mention the condition's entity/verb at all, the model is not asked. */
export function conditionRelevant(condition: TaskCondition, text: string): boolean {
  const core = condition.value.replace(/^.+?的/u, '');
  if (condition.kind === 'item') return text.includes(core) || text.includes(condition.value);
  if (condition.kind === 'location' || condition.kind === 'target') {
    return text.includes(condition.value) || (condition.value.length > 4 && text.includes(condition.value.slice(-4)));
  }
  if (condition.kind === 'time') return text.includes(condition.value);
  if (condition.kind === 'confirmation') return CONFIRM.some((word) => text.includes(word));
  if (condition.kind === 'decision') return /决定|选择|选定|选|走|路线|通道|回廊|庭院/u.test(text);
  if (condition.kind === 'action') {
    return text.includes(condition.value) || ACTION.some((word) => text.includes(word))
      || /戴|穿|拿|打|开|关|放|递|接|检查|确认|报告|问|说/u.test(text);
  }
  return true;
}

export interface TaskCondition {
  id: string;
  kind: 'time' | 'location' | 'item' | 'target' | 'confirmation' | 'action' | 'decision';
  value: string;
  label: string;
}

/** Per-condition rows for the proposer; same decomposition as decomposeTask. */
export function taskConditions(goal: string, state: WorldState, ownerName: string): TaskCondition[] {
  const conditions = decomposeTask(goal, state, ownerName);
  const rows: TaskCondition[] = [];
  const push = (kind: TaskCondition['kind'], value: string) => {
    rows.push({ id: `c${rows.length + 1}`, kind, value, label: `${kind}：${value}` });
  };
  if (conditions.time) push('time', conditions.time);
  if (conditions.location) push('location', conditions.location);
  if (conditions.item) push('item', conditions.item);
  if (conditions.target) push('target', conditions.target);
  if (conditions.decision) push('decision', conditions.decision);
  if (conditions.confirmation) push('confirmation', conditions.confirmation);
  if (conditions.action) push('action', conditions.action);
  return rows;
}

export function decomposeTask(goal: string, state: WorldState, ownerName: string): TaskConditions {
  const items = Object.entries(state.initial.items).map(([id, item]) => ({ id, name: item.name ?? id }));
  // A precondition ("在进入交火区前…") names an action that must NOT count as the
  // goal's own action; strip those clauses before matching verbs.
  const actionText = goal.replace(/在[^，。；]*?[前后]/gu, '');
  // The matcher's single best item can be an unregistered mention such as
  // «备用护目镜»; try every ranked candidate against the goal's own wording.
  const itemId = rankItems(goal, items).map((row) => row.id).find((id) => {
    const name = state.initial.items[id]?.name ?? id;
    const core = name.replace(/^.+?的/u, '');
    return goal.includes(core) && (core.length >= 3 || goal.includes(name));
  });
  const item = itemId ? (state.initial.items[itemId]?.name ?? itemId) : null;
  const target = Object.values(state.initial.characters).find((character) => character.name && goal.includes(character.name))?.name ?? null;
  const decision = /选择|决定|选定|选一条/u.test(goal)
    ? (goal.match(/选择[^，。；]*|决定[^，。；]*|选定[^，。；]*|选一条[^，。；]*/u)?.[0] ?? '选择') : null;
  const location = decision ? null : matchLocation(state, goal)?.name ?? null;
  const time = TIME.exec(goal)?.[0] ?? null;
  const confirmation = CONFIRM.find((word) => goal.includes(word)) ?? null;
  // The first verb in the sentence is the goal's own action; later verbs are
  // usually objects or purpose clauses (安排旗台的持守与撤退信号).
  let action: string | null = null;
  let actionAt = Number.POSITIVE_INFINITY;
  for (const word of ACTION) {
    const at = actionText.indexOf(word);
    if (at < 0) continue;
    if (at < actionAt || (at === actionAt && action !== null && word.length > action.length)) {
      action = word;
      actionAt = at;
    }
  }
  const conditions = [
    time ? `时间=${time}` : '',
    location ? `地点=${location}` : '',
    item ? `物品=${item}` : '',
    target ? `对象=${target}` : '',
    decision ? `决策=${decision}` : '',
    confirmation ? `确认=${confirmation}` : '',
    action ? `动作=${action}` : '',
  ].filter(Boolean);
  return { goal, time, location, item, target, confirmation, action, decision, conditions };
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

/** All condition labels for a decomposed goal, in the same order as hits. */
export function taskConditionLabels(conditions: TaskConditions): string[] {
  return [
    conditions.time ? `时间=${conditions.time}` : '',
    conditions.location ? `地点=${conditions.location}` : '',
    conditions.item ? `物品=${conditions.item}` : '',
    conditions.target ? `对象=${conditions.target}` : '',
    conditions.decision ? `决策=${conditions.decision}` : '',
    conditions.confirmation ? `确认=${conditions.confirmation}` : '',
    conditions.action ? `动作=${conditions.action}` : '',
  ].filter(Boolean);
}

/** Strict per-condition hits for the task ledger (S06): the condition's own
 * action/confirmation word must appear, not just any verb from the lexicon.
 * One fact need not cover the whole goal; the ledger accumulates. */
export function strictConditionHits(conditions: TaskConditions, factText: string): string[] {
  const checks: Array<[string, boolean]> = [
    ...(conditions.time ? [[`时间=${conditions.time}`, factText.includes(conditions.time)] as [string, boolean]] : []),
    ...(conditions.location ? [[`地点=${conditions.location}`, factText.includes(conditions.location)] as [string, boolean]] : []),
    ...(conditions.item ? [[`物品=${conditions.item}`, factText.includes(conditions.item) || factText.includes(conditions.item.replace(/^.+?的/u, ''))] as [string, boolean]] : []),
    ...(conditions.target ? [[`对象=${conditions.target}`, factText.includes(conditions.target)] as [string, boolean]] : []),
    ...(conditions.decision ? [[`决策=${conditions.decision}`, /决定|选择|选定|选了|就走|走这/u.test(factText)] as [string, boolean]] : []),
    ...(conditions.confirmation ? [[`确认=${conditions.confirmation}`, factText.includes(conditions.confirmation)] as [string, boolean]] : []),
    ...(conditions.action ? [[`动作=${conditions.action}`, factText.includes(conditions.action)] as [string, boolean]] : []),
  ];
  return checks.filter(([, hit]) => hit).map(([label]) => label);
}

/** Which decomposed goal conditions this fact names, as condition labels. The
 * task stage accumulates these across facts/turns; one fact need not cover the
 * whole goal. */
export function conditionHits(conditions: TaskConditions, factText: string): string[] {
  return conditionChecks(conditions, factText).filter(([, hit]) => hit).map(([label]) => label);
}

function conditionChecks(conditions: TaskConditions, factText: string): Array<[string, boolean]> {
  return [
    ...(conditions.time ? [[`时间=${conditions.time}`, factText.includes(conditions.time)] as [string, boolean]] : []),
    ...(conditions.location ? [[`地点=${conditions.location}`, factText.includes(conditions.location)] as [string, boolean]] : []),
    ...(conditions.item ? [[`物品=${conditions.item}`, factText.includes(conditions.item)] as [string, boolean]] : []),
    ...(conditions.target ? [[`对象=${conditions.target}`, factText.includes(conditions.target)] as [string, boolean]] : []),
    ...(conditions.decision ? [[`决策=${conditions.decision}`, /决定|选择|选定|选了|就走|走这/u.test(factText)] as [string, boolean]] : []),
    ...(conditions.confirmation ? [[`确认=${conditions.confirmation}`, CONFIRM.some((word) => factText.includes(word))] as [string, boolean]] : []),
    ...(conditions.action ? [[`动作=${conditions.action}`, ACTION.some((word) => factText.includes(word))] as [string, boolean]] : []),
  ];
}

/** How many of the decomposed goal conditions the fact names. A `yes` from the
 * pair model is downgraded to partial unless every named condition is covered. */
export function conditionCoverage(conditions: TaskConditions, factText: string): { matched: number; total: number; missing: string[] } {
  const checks = conditionChecks(conditions, factText);
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
      const coverage = support.conditions?.length
        ? {
          matched: support.conditions.filter((condition) => condition.state === 'satisfied').length,
          total: support.conditions.length,
          missing: support.conditions.filter((condition) => condition.state !== 'satisfied').map((condition) => condition.label),
        }
        : conditionCoverage(conditions, support.factText);
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

