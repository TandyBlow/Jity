/** Scorer for the narration-split baseline. Scores output against the FROZEN
 * requiredFacts of each sample — never against free keyword presence. Two
 * design points from the 2026-10-25 review:
 * 1. Sentence-scoped matching: a fact must be asserted within ONE sentence,
 *    so cross-sentence token leakage ("学生A" in an unrelated sentence) cannot
 *    satisfy a position/task fact.
 * 2. Residue-based fabrication check: every sentence must reduce to declared
 *    vocabulary (entity names, change texts, goals, values, time tokens) plus
 *    function words — invented content ("获得一把不存在的宝剑") leaves residue
 *    and is flagged. **残留检查是「疑似错误提示」而非定罪**：评价小模型的不
 *    同措辞时，词表外表达不得直接判成捏造（方向反转、新增实体等结构化事实
 *    错误由同句绑定与方向核对判定）；语义捏造始终归人工抽查。
 * scorerSelfTest ships the review's counterexample classes (wrong duration,
 * negated result, subject swap, invented item) and they MUST fail; the rule
 * baseline's own text MUST pass clean. */
import type { NarrationSplitSample, RequiredFact } from './narration-split-samples';
import { NARRATION_SPLIT_SAMPLES } from './narration-split-samples';
import { cnNum, entityName, runNarrationPipeline, UNIT_CN } from './narration-split';

export interface FactCheck {
  phrase: string;
  kind: RequiredFact['kind'];
  pass: boolean;
}

export interface NarrationEval {
  factChecks: FactCheck[];
  /** 未达成的必述事实（phrase）。 */
  omissions: string[];
  /** 残差检查标出的句子（疑似捏造/不可追溯内容）。 */
  fabricationFlags: string[];
  /** 序列样本：与同序列前点的字符 bigram 最大重叠（自然度输入，非捏造）。 */
  repetition: number | null;
}

/** 功能词/模板词表（声明式；模型臂的词汇表另行冻结）。 */
const FUNCTION_TOKENS = ['过去了', '过去了', '约', '从', '来到了', '来到', '完成了任务', '有了一个新任务', '理智值', '升为', '降为', '变得', '一个', '又'];
const FUNCTION_CHARS = /[的从了又约一个任务：、，。！？；\s「」]/g;

function sentences(text: string): string[] {
  return text.split('。').map((s) => s.trim()).filter((s) => s.length > 0);
}

function checkFact(sample: NarrationSplitSample, fact: RequiredFact, sents: string[]): boolean {
  switch (fact.kind) {
    case 'position': {
      const name = entityName(sample.before, fact.entityId);
      // 同句包含三个词不等于方向正确：「学生A从大厅来到了走廊」曾全过——
      // 要求「从{起点}」的方向标记同句成立（其他方向措辞的接受度留待
      // 小模型对照评价，v0 从严）。
      return sents.some((s) => s.includes(name) && s.includes(`从${fact.fromName}`) && s.includes(fact.toName));
    }
    case 'appearanceText':
    case 'personalityText':
      return sents.some((s) => s.includes(fact.text));
    case 'taskGoal': {
      const name = entityName(sample.before, fact.entityId);
      return sents.some((s) => s.includes(fact.goal) && s.includes(name));
    }
    case 'sanityValue': {
      const name = entityName(sample.before, fact.entityId);
      return sents.some((s) => s.includes(String(fact.value)) && s.includes(name));
    }
    case 'timePassage':
      return sents.some((s) => s.includes(cnNum(fact.amount)) && s.includes(UNIT_CN[fact.unit]));
    case 'timeReached': {
      const token = fact.hour === 12 ? '中午' : `${fact.hour}点`;
      // 「坚持到中午」引号内出现的「中午」是任务名的引用，不是时间断言——
      // 剥除引号内容后再核对。
      return sents.some((s) => s.replace(/「[^」]*」/g, '').includes(token));
    }
  }
}

function fabricationCheck(sample: NarrationSplitSample, sents: string[]): string[] {
  const tokens = new Set<string>([cnNum(sample.timeAdvance.duration.amount), UNIT_CN[sample.timeAdvance.duration.unit]]);
  const initial = sample.before.initial;
  for (const e of Object.values(initial.characters)) tokens.add(e.name);
  for (const e of Object.values(initial.items)) tokens.add(e.name);
  for (const e of Object.values(initial.locations)) tokens.add(e.name);
  for (const [eid, d] of Object.entries(sample.delta)) {
    for (const c of [...(d.appearanceChanges ?? []), ...(d.personalityChanges ?? [])]) if (c.text != null) tokens.add(c.text);
    for (const tid of d.tasksAchieved ?? []) {
      const goal = sample.before.characters[eid]?.tasks[tid]?.goal;
      if (goal) tokens.add(goal);
    }
    for (const t of d.subtasksAdded ?? []) tokens.add(t.goal);
    if (d.sanitySet != null) tokens.add(String(d.sanitySet));
  }
  return sents.filter((s) => {
    let residue = s;
    // 长词先删：短词先删会破坏长词匹配（「主角」⊂「帮主角熟悉校园」、
    // 「钥匙」⊂「黄铜钥匙的表面蒙上了一层灰尘」曾把合规句误标为捏造）。
    const ordered = [...tokens].sort((a, b) => b.length - a.length);
    for (const tok of ordered) residue = residue.split(tok).join('');
    for (const tok of FUNCTION_TOKENS) residue = residue.split(tok).join('');
    residue = residue.replace(FUNCTION_CHARS, '');
    return residue.length > 0;
  });
}

function bigrams(text: string): Set<string> {
  const set = new Set<string>();
  for (let i = 0; i + 1 < text.length; i++) set.add(text.slice(i, i + 2));
  return set;
}

function overlap(a: Set<string>, b: Set<string>): number {
  let n = 0;
  for (const g of a) if (b.has(g)) n++;
  return a.size ? n / a.size : 0;
}

/** mustExpress 与 requiredFacts 的冻结一致性：每条 mustExpress 必须有对应的
 * requiredFact phrase，判分才允许引用 mustExpress 作为人类可读镜像。 */
export function assertFrozenRequirements(sample: NarrationSplitSample): void {
  const phrases = new Set(sample.requiredFacts.map((f) => f.phrase));
  for (const m of sample.mustExpress) {
    if (!phrases.has(m)) throw new Error(`${sample.id}: mustExpress「${m}」没有对应的 requiredFact`);
  }
}

export function evaluateNarration(sample: NarrationSplitSample, text: string, previousSeriesTexts: readonly string[] = []): NarrationEval {
  const sents = sentences(text);
  const factChecks = sample.requiredFacts.map((f) => ({ phrase: f.phrase, kind: f.kind, pass: checkFact(sample, f, sents) }));
  let repetition: number | null = null;
  if (sample.series && previousSeriesTexts.length > 0) {
    const cur = bigrams(text);
    repetition = Math.max(...previousSeriesTexts.map((p) => overlap(cur, bigrams(p))));
  }
  return {
    factChecks,
    omissions: factChecks.filter((f) => !f.pass).map((f) => f.phrase),
    fabricationFlags: fabricationCheck(sample, sents),
    repetition,
  };
}

export interface SelfTestResult {
  name: string;
  pass: boolean;
  detail: string;
}

/** 判分器反例自检：四类反例必须失败，规则基线原文必须全过。任何一项不过，
 * 判分器本身不可信，基线结果作废。 */
export function scorerSelfTest(): SelfTestResult[] {
  const byId = new Map(NARRATION_SPLIT_SAMPLES.map((s) => [s.id, s]));
  const pipelineText = (id: string): string => {
    const s = byId.get(id);
    if (!s) throw new Error(`self-test: ${id} missing`);
    return runNarrationPipeline({ before: s.before, delta: s.delta, after: s.after, timeAdvance: s.timeAdvance, perspective: s.perspective }).text;
  };
  const pos = byId.get('ns-pos-1')!;
  const baselineText = pipelineText('ns-pos-1');
  const cases: { name: string; sampleId: string; text: string; expect: (e: NarrationEval) => boolean; detail: string }[] = [
    {
      name: '错误时长（约九千分钟）必须失败',
      sampleId: 'ns-pos-1',
      text: '约九千分钟过去了。学生A从走廊来到了大厅。',
      expect: (e) => e.factChecks.some((f) => f.kind === 'timePassage' && !f.pass) && e.fabricationFlags.length >= 1,
      detail: 'timePassage 要求句内同时含正确数量词与单位；残差「九千」必须被标记',
    },
    {
      name: '否定结果必须失败',
      sampleId: 'ns-pos-1',
      text: '约两分钟过去了。学生A没有来到大厅。',
      expect: (e) => e.factChecks.some((f) => f.kind === 'position' && !f.pass),
      detail: 'position 需要 name+from+to 同句成立',
    },
    {
      name: '主体交换必须失败',
      sampleId: 'ns-pos-1',
      text: '约两分钟过去了。学生B从走廊来到了大厅。',
      expect: (e) => e.factChecks.some((f) => f.kind === 'position' && !f.pass),
      detail: '主体与动作绑定在同句内核对',
    },
    {
      name: '方向反转必须失败',
      sampleId: 'ns-pos-1',
      text: '约两分钟过去了。学生A从大厅来到了走廊。',
      expect: (e) => e.factChecks.some((f) => f.kind === 'position' && !f.pass),
      detail: '同句含三词≠方向正确——要求「从{起点}」同句成立',
    },
    {
      name: '新增物品必须标捏造',
      sampleId: 'ns-pos-1',
      text: '约两分钟过去了。学生A从走廊来到了大厅。学生A获得一把不存在的宝剑。',
      expect: (e) => e.fabricationFlags.length >= 1,
      detail: '残差「获得一把不存在宝剑」不可追溯',
    },
    {
      name: '规则基线原文必须全过（ns-pos-1）',
      sampleId: 'ns-pos-1',
      text: baselineText,
      expect: (e) => e.omissions.length === 0 && e.fabricationFlags.length === 0,
      detail: baselineText,
    },
    {
      name: '重叠词宿主句必须零标记（ns-pers-1）',
      sampleId: 'ns-pers-1',
      text: pipelineText('ns-pers-1'),
      expect: (e) => e.omissions.length === 0 && e.fabricationFlags.length === 0,
      detail: '「主角」⊂任务名等嵌套词曾致合规句误标——长词先删后必须干净',
    },
    {
      name: '「时间已到中午」未被显式断言必须记遗漏（ns-task-time-1）',
      sampleId: 'ns-task-time-1',
      text: pipelineText('ns-task-time-1'),
      expect: (e) => e.omissions.includes('时间已到中午'),
      detail: '「坚持到中午」引号内的「中午」是任务名引用，不是时间断言',
    },
  ];
  return cases.map((c) => {
    const e = evaluateNarration(byId.get(c.sampleId)!, c.text);
    return { name: c.name, pass: c.expect(e), detail: c.detail };
  });
}
