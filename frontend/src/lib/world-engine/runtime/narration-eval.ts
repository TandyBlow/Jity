/** Second narration batch harness: the SAME committed packet is rendered three
 * ways and graded by the state-alignment grader.
 *
 * - template   : renderCommittedNarration (the page's fallback, verbatim facts,
 *                since 2026-10-28 opened with the point's time passage and the
 *                empty-point fixed line)
 * - mechanical : the only wording the page currently accepts — declared short
 *                sentence variants concatenated (frozen per sample)
 * - natural    : the model writes prose from the structured facts; a failed
 *                grade triggers ONE regeneration with the violations fed back,
 *                and a second failure falls back to the template.
 *
 * The driver never parses model output structurally (narration is prose); the
 * only gate is fact alignment. Adoption/regeneration/fallback, per-call
 * latency and repetition are returned for the archive. */
import type { TimeAdvance } from '../types';
import { renderCommittedNarration, type CommittedNarration, type NarrationFact } from './committed-narration';
import { alignNarration, type AlignmentResult } from './narration-alignment';
import type { NarrationEvalSample } from './narration-eval-samples';

export interface NarrationGeneration {
  text: string;
  /** 生成耗时（毫秒，由引擎侧计时；不含评测开销）。 */
  ms: number;
  completion?: { promptTokens?: number; completionTokens?: number; promptMs?: number; predictedMs?: number };
}

export interface NarrationGenerator {
  generate(prompt: string, sample: NarrationEvalSample, attempt: number): Promise<NarrationGeneration>;
}

export interface NarrationAttempt {
  attempt: number;
  prompt: string;
  text: string;
  ms: number;
  verdict: AlignmentResult;
  completion?: NarrationGeneration['completion'];
}

export interface NarrationSampleRun {
  sampleId: string;
  category: NarrationEvalSample['category'];
  template: { text: string; verdict: AlignmentResult };
  mechanical: { text: string; verdict: AlignmentResult };
  natural: { attempts: NarrationAttempt[]; adopted: boolean; fellBack: boolean; text: string; final: AlignmentResult };
}

export interface NarrationEvalReport {
  samples: NarrationSampleRun[];
  summary: {
    samples: number;
    templateAccepted: number;
    mechanicalAccepted: number;
    /** 时间推进的覆盖：模板从不写时间，自然臂是否补上单独统计。 */
    timeNarratedTemplate: number;
    timeNarratedMechanical: number;
    timeNarratedNatural: number;
    naturalAdopted: number;
    naturalFirstAttempt: number;
    regenerated: number;
    fellBack: number;
    fallbackRate: number;
    omittedFacts: number;
    violations: number;
    unverifiedSentences: number;
    meanMs: number | null;
  };
}

const UNITS: Record<TimeAdvance['duration']['unit'], string> = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年',
};

/** Facts are given as FIELD VALUES, not as ready sentences: the model has to
 * do the phrasing, which is exactly what this batch measures. */
export function describeFact(fact: NarrationFact): string {
  switch (fact.kind) {
    case 'at': return `${fact.name} / 所在位置 = ${fact.location}`;
    case 'moved': return `${fact.name} / 位置 = 从 ${fact.from} 到 ${fact.to}`;
    case 'sanity': return `${fact.name} / 精神值 = ${fact.value}`;
    case 'sanity_changed': return `${fact.name} / 精神值 = ${fact.from} → ${fact.to}`;
    case 'task_achieved': return `${fact.name} / 达成任务 = 「${fact.goal}」`;
    case 'personality_changed': return `${fact.name} / 个性变化 = 「${fact.text}」`;
  }
}

export function buildNaturalPrompt(sample: NarrationEvalSample, feedback?: string[]): string {
  const lines = [
    '[任务: narration-natural]',
    '用一到三句顺畅的中文写出这一点位的叙事正文，像小说旁白，不要逐条罗列。',
    '只能使用下面的事实；人物动作的归属不得互换，方向、数值、任务名称必须与事实一致；不要补写没有给出的事件、物品或经过。',
    sample.time ? `本点时间推进：${sample.time.amount} ${UNITS[sample.time.unit]}（必须自然地写出来）。` : '',
    '事实：',
    ...sample.packet.facts.map((fact) => `- ${describeFact(fact)}`),
    sample.packet.facts.length === 0 ? '- 本点没有任何实体变化（只有时间推进）。' : '',
    sample.forbidden.length ? `不得出现：${sample.forbidden.join('；')}。` : '',
    '最后用一句话写出时间推进，时长数值必须与上面给出的完全一致。',
    '只输出正文文字，不要 JSON、不要标题、不要列表、不要解释。',
    feedback?.length ? `上一稿的问题：${feedback.join('；')}。请改写。` : '',
    '正文:',
  ];
  return lines.filter(Boolean).join('\n');
}

export function templateText(sample: NarrationEvalSample): string {
  return renderCommittedNarration(sample.packet, { time: sample.time });
}

function grade(sample: NarrationEvalSample, text: string, requireTime: boolean): AlignmentResult {
  return alignNarration(sample.packet as CommittedNarration, text, {
    time: sample.time, locations: sample.locations, roster: sample.roster,
    previousText: sample.previousText, requireTime,
  });
}

/** Violations and omissions become the regeneration instruction. Unverified
 * sentences are NOT fed back: they are review flags, not errors. */
export function feedbackFor(verdict: AlignmentResult): string[] {
  const parts = [...verdict.violations.map((violation) => violation.detail),
    ...verdict.omissions.map((omission) => `遗漏事实：${omission}`)];
  if (verdict.timeExpressed === false) parts.push('没有写出时间推进');
  return parts;
}

export async function runNarrationEvaluation(options: {
  samples: NarrationEvalSample[];
  generator: NarrationGenerator;
  maxAttempts?: number;
  /** 三个臂统一按「必须述及时间推进」判分（默认 false：现有页面门不要求时间，
   * 时间覆盖由 harness 单独统计）。2026-10-28 复核轮的 requireTime 重跑用 true。 */
  requireTime?: boolean;
}): Promise<NarrationEvalReport> {
  const maxAttempts = options.maxAttempts ?? 2;
  const requireTime = options.requireTime === true;
  const samples: NarrationSampleRun[] = [];
  for (const sample of options.samples) {
    const template = { text: templateText(sample), verdict: grade(sample, templateText(sample), requireTime) };
    const mechanical = { text: sample.mechanical, verdict: grade(sample, sample.mechanical, requireTime) };
    const attempts: NarrationAttempt[] = [];
    let adopted = false;
    for (let attempt = 1; attempt <= maxAttempts && !adopted; attempt++) {
      const feedback = attempt > 1 ? feedbackFor(attempts[attempts.length - 1].verdict) : undefined;
      const prompt = buildNaturalPrompt(sample, feedback);
      const generation = await options.generator.generate(prompt, sample, attempt);
      const verdict = grade(sample, generation.text, requireTime);
      attempts.push({ attempt, prompt, text: generation.text, ms: generation.ms, verdict,
        completion: generation.completion });
      adopted = verdict.ok;
    }
    samples.push({ sampleId: sample.id, category: sample.category, template, mechanical,
      natural: { attempts, adopted, fellBack: !adopted,
        text: adopted ? attempts[attempts.length - 1].text : template.text,
        // The natural arm's LAST verdict is always what it produced; the page
        // behaviour (fallback) is carried by `fellBack`/`text`, never by
        // replacing the verdict with the template's.
        final: attempts[attempts.length - 1].verdict } });
  }
  const totals = samples.reduce((acc, run) => {
    acc.omittedFacts += run.natural.final.omissions.length;
    acc.violations += run.natural.final.violations.length;
    acc.unverified += run.natural.final.unverified.length;
    acc.ms += run.natural.attempts.reduce((sum, attempt) => sum + attempt.ms, 0);
    return acc;
  }, { omittedFacts: 0, violations: 0, unverified: 0, ms: 0 });
  const calls = samples.reduce((sum, run) => sum + run.natural.attempts.length, 0);
  return {
    samples,
    summary: {
      samples: samples.length,
      templateAccepted: samples.filter((run) => run.template.verdict.ok).length,
      mechanicalAccepted: samples.filter((run) => run.mechanical.verdict.ok).length,
      naturalAdopted: samples.filter((run) => run.natural.adopted).length,
      naturalFirstAttempt: samples.filter((run) => run.natural.attempts[0]?.verdict.ok).length,
      regenerated: samples.filter((run) => run.natural.attempts.length > 1).length,
      timeNarratedTemplate: samples.filter((run) => run.template.verdict.timeExpressed === true).length,
      timeNarratedMechanical: samples.filter((run) => run.mechanical.verdict.timeExpressed === true).length,
      timeNarratedNatural: samples.filter((run) => run.natural.final.timeExpressed === true).length,
      fellBack: samples.filter((run) => run.natural.fellBack).length,
      fallbackRate: samples.length ? samples.filter((run) => run.natural.fellBack).length / samples.length : 0,
      omittedFacts: totals.omittedFacts,
      violations: totals.violations,
      unverifiedSentences: totals.unverified,
      meanMs: calls ? Math.round(totals.ms / calls) : null,
    },
  };
}
