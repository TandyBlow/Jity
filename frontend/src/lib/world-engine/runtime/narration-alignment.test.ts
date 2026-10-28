/** Grader self-test for the second narration batch.
 *
 * The user's acceptance for the instrument: the grader must RECOGNISE actor
 * swaps, reversed directions, wrong numbers, a completed task that has no
 * committed fact, and added events — while ordinary rewrites must not be
 * called fabrication just because they use wording outside the template
 * vocabulary. Both halves are asserted here, plus the frozen corpus invariant
 * that the template arm renders verbatim facts and both non-empty reference
 * arms pass cleanly. */
import { describe, expect, it } from 'vitest';
import { checkFactNarration, renderCommittedNarration } from './committed-narration';
import { alignNarration, cnNumber, mentionsNumber, mentionsTime } from './narration-alignment';
import { NARRATION_EVAL_SAMPLES, type NarrationEvalSample } from './narration-eval-samples';
import { NARRATION_EVAL_VALIDATION_SAMPLES } from './narration-eval-validation';
import { buildNaturalPrompt, runNarrationEvaluation, templateText, type NarrationGenerator } from './narration-eval';

const sample = (id: string): NarrationEvalSample => {
  const found = NARRATION_EVAL_SAMPLES.find((entry) => entry.id === id);
  if (!found) throw new Error(`missing sample ${id}`);
  return found;
};
const validation = (id: string): NarrationEvalSample => {
  const found = NARRATION_EVAL_VALIDATION_SAMPLES.find((entry) => entry.id === id);
  if (!found) throw new Error(`missing validation sample ${id}`);
  return found;
};
const gradeValidation = (id: string, text: string, requireTime = false) => {
  const entry = validation(id);
  return alignNarration(entry.packet, text, { time: entry.time, locations: entry.locations,
    roster: entry.roster, previousText: entry.previousText, requireTime });
};
const grade = (id: string, text: string, requireTime = false) => {
  const entry = sample(id);
  return alignNarration(entry.packet, text, { time: entry.time, locations: entry.locations,
    roster: entry.roster, previousText: entry.previousText, requireTime });
};

describe('frozen corpus', () => {
  it('freezes ten samples across the six required categories', () => {
    expect(NARRATION_EVAL_SAMPLES).toHaveLength(10);
    expect(new Set(NARRATION_EVAL_SAMPLES.map((entry) => entry.category))).toEqual(new Set([
      'movement', 'task_personality_sanity', 'multi_character', 'refused_action', 'no_change', 'continuity']));
    expect(new Set(NARRATION_EVAL_SAMPLES.map((entry) => entry.id)).size).toBe(10);
  });

  it('renders the template arm from the committed facts verbatim', () => {
    for (const entry of NARRATION_EVAL_SAMPLES) {
      expect(templateText(entry)).toBe(renderCommittedNarration(entry.packet, { time: entry.time }));
    }
  });

  // 2026-10-28 复核后的模板：先述本点时间（§5.2 timeAdvance 属于 Δ），空事实点
  // 用「时间 + 没有新的变化」固定句式——两个已知缺口（不写时间、空点空串）由此
  // 关闭，十点全部通过 requireTime 判分。
  it('narrates the time passage and gives empty points a fixed line, passing under requireTime', () => {
    for (const entry of NARRATION_EVAL_SAMPLES) {
      const verdict = alignNarration(entry.packet, templateText(entry),
        { time: entry.time, locations: entry.locations, roster: entry.roster, requireTime: true });
      expect(verdict.ok, `${entry.id}: ${JSON.stringify(verdict.violations)} missing=${JSON.stringify(verdict.omissions)}`).toBe(true);
      expect(verdict.unverified).toEqual([]);
      expect(verdict.timeExpressed).toBe(true);
    }
    expect(templateText(sample('nv-refused-1'))).toBe('约一秒过去了，没有新的变化。');
    // nv-cont-3 freezes the standing fact its reference asserts (2026-10-28
    // review amendment) — the template renders 时间 + 现状 from the packet.
    expect(templateText(sample('nv-cont-3'))).toBe('约五分钟过去了。学生A位于大厅。');
  });

  it('accepts every human reference and every non-empty mechanical text', () => {
    for (const entry of NARRATION_EVAL_SAMPLES) {
      const reference = grade(entry.id, entry.reference, true);
      expect(reference.ok, `${entry.id} reference: ${JSON.stringify(reference.violations)} missing=${JSON.stringify(reference.omissions)}`).toBe(true);
      if (entry.mechanical) {
        const mechanical = grade(entry.id, entry.mechanical);
        expect(mechanical.ok, `${entry.id} mechanical: ${JSON.stringify(mechanical.violations)}`).toBe(true);
        // The mechanical arm is the CEILING of what today's page gate accepts:
        // an arrangement of the declared variants, nothing freer.
        expect(checkFactNarration(entry.packet, entry.mechanical).ok,
          `${entry.id} must stay acceptable to the old exact-clause gate`).toBe(true);
      }
    }
  });
});

describe('grader rejects factual contradictions', () => {
  it('flags an actor swap', () => {
    const verdict = grade('nv-multi-1', '主角从走廊走到大厅。学生A还留在走廊。大约过了一分钟。');
    expect(verdict.ok).toBe(false);
    expect(verdict.violations.map((violation) => violation.kind)).toContain('actor_swap');
  });

  // at 事实的角色本点没有移动：到达声明要么是 swap（把别人的移动安到他头上），
  // 要么是无事实移动（目的地不在任何事实里）——两种都要拦。
  it('flags a movement invented for an actor committed at one place', () => {
    const swapped = grade('nv-multi-1', '主角从走廊来到大厅时，学生A已经在大厅里等着了。大约过了一分钟。');
    expect(swapped.ok).toBe(false);
    expect(swapped.violations.map((violation) => violation.kind)).toContain('actor_swap');
    const moved = grade('nv-multi-1', '主角从走廊走到了教室。');
    expect(moved.ok).toBe(false);
    expect(moved.violations.map((violation) => violation.kind)).toContain('movement_without_fact');
  });

  // 复核重跑（artifacts/narration-eval-recheck 首跑）抓到的两个洞，稿子原样：
  // 强签名事实即使已被绑定，别的分句把同一载荷安给其他角色仍是 swap；
  // 完成声明骑在已绑定的位置事实上，仍是无事实任务。
  it('flags a sanity change invented for an actor with no fact at all', () => {
    const verdict = gradeValidation('hv-sanity-1', '学生C的精神值从12降至9，学生D的精神值从12降至9。时间推进，2分钟。');
    expect(verdict.ok).toBe(false);
    expect(verdict.violations.map((violation) => violation.kind)).toContain('actor_swap');
  });

  it('flags a completion claim riding on a bound position fact', () => {
    const verdict = grade('nv-cont-3', '学生A在大厅内完成任务，时间推进为5分钟。');
    expect(verdict.ok).toBe(false);
    expect(verdict.violations.map((violation) => violation.kind)).toContain('task_claimed_without_fact');
  });

  // 二轮复核：人格宽容只容程度副词——「健壮而谈吐粗鲁」是另一种人格，不是
  // 「健谈」的口语改写，不得绑定（复核探针原样：其余事实全对仍 ok=true）。
  it('does not bind a different trait as a colloquial insert', () => {
    const verdict = grade('nv-task-pers-sanity-1',
      '学生B完成了任务「帮主角熟悉校园」，变得健壮而谈吐粗鲁，精神值从10升到12。一分钟过去了。', true);
    expect(verdict.ok).toBe(false);
    expect(verdict.violations).toEqual([]);
    expect(verdict.omissions).toEqual(['学生B的人格变化为「变得健谈」']);
  });

  // 三轮复核：事件检查不再有任何豁免——重复主语绕不过（复核探针原样：
  // 分句含已绑定人名曾被当作背书）、「推开门」也不是移动事实的合法措辞：
  // 没有哪种已提交事实能背书事件发生。四轮复核：引用豁免收窄为「与当前
  // 事实包冻结原文逐字一致」——给自己的捏造套引号（并「打开」门）不能借
  // bareOf 的无条件剥引号逃过扫描。
  it('flags event verbs regardless of fact binding, clause, or quoting', () => {
    const repeat = grade('nv-move-1', '学生A从走廊走到大厅，学生A打开门。两分钟过去了。');
    expect(repeat.ok).toBe(false);
    expect(repeat.violations.map((violation) => violation.kind)).toContain('added_event');
    const phrased = grade('nv-move-1', '学生A推开门走进大厅，前后大约花了两分钟。');
    expect(phrased.ok).toBe(false);
    expect(phrased.violations.map((violation) => violation.kind)).toContain('added_event');
    // 复核探针原样：该包没有任何含「打开」的冻结原文，引号不构成豁免。
    const quoted = grade('nv-move-1', '学生A从走廊走到大厅，并「打开」门。两分钟过去了。');
    expect(quoted.ok).toBe(false);
    expect(quoted.violations.map((violation) => violation.kind)).toContain('added_event');
    // 冻结原文引用（与事实包逐字一致）才豁免：目标原文自带动词时引用它不算事件。
    const packet = { anchor: { worldId: 'world_school', pointId: 'p_quote', version: 1,
      stateDigest: '1'.repeat(64), previousPointId: 'root' }, facts: [
      { id: 'p:task:t1', actorId: 'p', name: '学生A', kind: 'task_achieved' as const,
        taskId: 't1', goal: '砸碎封印救出守林人' }] };
    const cited = alignNarration(packet, '学生A完成了任务「砸碎封印救出守林人」。约一分钟过去了。',
      { time: { amount: 1, unit: 'minute' }, roster: ['学生A'] });
    expect(cited.ok).toBe(true);
    expect(cited.violations).toEqual([]);
    const done = alignNarration(packet, '学生A完成了任务「砸碎封印救出守林人」，随后砸碎了门锁。约一分钟过去了。',
      { time: { amount: 1, unit: 'minute' }, roster: ['学生A'] });
    expect(done.ok).toBe(false);
    expect(done.violations.map((violation) => violation.kind)).toContain('added_event');
    // 引号里的内容对不上任何冻结原文时照扫。
    const invented = alignNarration(packet, '学生A「打开」了门。约一分钟过去了。',
      { time: { amount: 1, unit: 'minute' }, roster: ['学生A'] });
    expect(invented.ok).toBe(false);
    expect(invented.violations.map((violation) => violation.kind)).toContain('added_event');
  });

  it('flags a reversed direction', () => {
    const verdict = grade('nv-move-1', '学生A从大厅走到走廊，前后大约花了两分钟。');
    expect(verdict.ok).toBe(false);
    expect(verdict.violations.map((violation) => violation.kind)).toContain('direction_reversed');
  });

  it('flags a wrong number', () => {
    const verdict = grade('nv-task-pers-sanity-1',
      '带着主角在校园里转了一圈之后，学生B完成了任务「帮主角熟悉校园」。学生B变得健谈起来，精神值从10升到了13。前后不过一分钟。');
    expect(verdict.ok).toBe(false);
    expect(verdict.violations.map((violation) => violation.kind)).toContain('wrong_number');
  });

  it('flags a completion claimed with no committed task', () => {
    const verdict = grade('nv-empty-1', '四周安静下来，五分钟过去了，主角完成了任务「取回柜子里的东西」。');
    expect(verdict.ok).toBe(false);
    expect(verdict.violations.map((violation) => violation.kind)).toContain('task_claimed_without_fact');
  });

  it('flags an added event', () => {
    const verdict = grade('nv-move-1', '学生A离开走廊，走进大厅，大约花了两分钟。他推开门冲了进去。');
    expect(verdict.ok).toBe(false);
    expect(verdict.violations.map((violation) => violation.kind)).toContain('added_event');
  });

  it('flags movement claimed for a refused action', () => {
    const verdict = grade('nv-refused-1', '主角走到了门厅。一秒钟就这样过去了。');
    expect(verdict.ok).toBe(false);
    expect(verdict.violations.map((violation) => violation.kind)).toContain('movement_without_fact');
  });

  it('flags a wrong duration copied from an example', () => {
    // 2-second point narrated as two minutes — the 0.6B model's measured
    // failure mode after the prompt showed a literal example duration.
    const verdict = grade('nv-cont-1', '学生A从走廊走到大厅。两分钟过去了。');
    expect(verdict.ok).toBe(false);
    expect(verdict.violations.map((violation) => violation.kind)).toContain('wrong_time');
    expect(verdict.timeExpressed).toBe(false);
  });

  it('flags a standing-location claim with no committed fact', () => {
    const verdict = grade('nv-cont-2', '学生B还站在大厅里，学生A位于走廊。两分钟过去了。');
    expect(verdict.ok).toBe(false);
    expect(verdict.violations.map((violation) => violation.kind)).toContain('state_claim_without_fact');
  });

  // 复核发现的洞：零位置事实的点上 positions.length > 0 短路，任何站位声明都
  // 被放行（ok=true、只记 unverified）——恰好是三个空点，模型写什么站位都过。
  it('flags standing-location claims on points without any position fact', () => {
    const refused = grade('nv-refused-1', '主角在门厅。');
    expect(refused.ok).toBe(false);
    expect(refused.violations.map((violation) => violation.kind)).toContain('state_claim_without_fact');
    const empty = grade('nv-empty-1', '学生B位于教室。');
    expect(empty.ok).toBe(false);
    expect(empty.violations.map((violation) => violation.kind)).toContain('state_claim_without_fact');
    // 补冻现状事实后的 nv-cont-3：把他放到别处仍然会被识别。
    const series = grade('nv-cont-3', '学生A在走廊。');
    expect(series.ok).toBe(false);
    expect(series.violations.map((violation) => violation.kind)).toContain('state_claim_without_fact');
  });

  // 日常中文不是时长：十分健谈不是十分钟，第二天是序数日不是两天过去。
  it('does not read degree adverbs or ordinal days as durations', () => {
    const ten = grade('nv-task-pers-sanity-1',
      '学生B完成了任务「帮主角熟悉校园」，变得十分健谈，精神值从10升到12。一分钟过去了。', true);
    expect(ten.violations).toEqual([]);
    expect(ten.ok).toBe(true);
    const ordinal = grade('nv-move-1', '第二天，学生A从走廊走到大厅。');
    expect(ordinal.violations).toEqual([]);
    // 序数日不满足两分钟的要求——它只是不被误判成错误时长。
    expect(ordinal.timeExpressed).toBe(false);
    expect(grade('nv-move-1', '第二天，学生A从走廊走到大厅。', true).ok).toBe(false);
  });

  // 数值硬违规同样覆盖汉字读数（从十升到十三 之前不产生任何违规）。
  it('reads Chinese numerals in the value check', () => {
    const wrong = grade('nv-task-pers-sanity-1',
      '学生B完成了任务「帮主角熟悉校园」。学生B变得健谈，精神值从十升到十三。一分钟过去了。');
    expect(wrong.ok).toBe(false);
    expect(wrong.violations.map((violation) => violation.kind)).toContain('wrong_number');
    const right = grade('nv-task-pers-sanity-1',
      '学生B完成了任务「帮主角熟悉校园」。学生B变得健谈，精神值从十升到十二。一分钟过去了。');
    expect(right.ok).toBe(true);
  });

  it('accepts a space between the amount and its unit', () => {
    expect(mentionsTime('时间推进：5 分钟', { amount: 5, unit: 'minute' })).toBe(true);
    expect(grade('nv-empty-1', '时间推进：5 分钟。', true).ok).toBe(true);
  });

  it('binds a destination stance for a moved fact', () => {
    const verdict = grade('nv-move-1', '两分钟过去了，学生A在大厅。', true);
    expect(verdict.ok).toBe(true);
    expect(verdict.omissions).toEqual([]);
  });

  it('attributes two actors in one sentence by clause, not by sentence', () => {
    const verdict = grade('nv-multi-opposite-1', '3秒钟里，学生A从走廊走到大厅，学生B从大厅回到走廊。', true);
    expect(verdict.ok).toBe(true);
    expect(verdict.omissions).toEqual([]);
    expect(verdict.timeExpressed).toBe(true);
  });

  it('flags an omitted fact and a missing time mention', () => {
    const omitted = grade('nv-task-only-1', '主角完成了任务「取回柜子里的东西」。', true);
    expect(omitted.ok).toBe(false);
    expect(omitted.omissions).toHaveLength(0); // the fact is expressed…
    expect(omitted.timeExpressed).toBe(false); // …but the time is not
    const missing = grade('nv-move-1', '两分钟过去了。', true);
    expect(missing.omissions).toHaveLength(1);
    expect(missing.ok).toBe(false);
  });

  it('does not call ordinary rewording fabrication', () => {
    // Out-of-vocabulary connectives, idioms and order changes; every fact is
    // still asserted, no contradiction, no new event.
    const verdict = grade('nv-move-1', '前后大约两分钟，学生A这才离开走廊，走进大厅。', true);
    expect(verdict.violations).toEqual([]);
    expect(verdict.ok).toBe(true);
    const task = grade('nv-task-pers-sanity-1',
      '学生B带着主角把校园转了一圈，任务「帮主角熟悉校园」顺利完成。学生B的性格开朗了不少，用「变得健谈」来说也合适，精神值则从10升到12。整个过程一分钟。', true);
    expect(task.violations).toEqual([]);
    expect(task.ok).toBe(true);
  });

  it('reports unverified sentences without failing them', () => {
    const verdict = grade('nv-move-1', '学生A离开走廊，走进大厅。走廊里一时安静下来。前后大约两分钟。', true);
    expect(verdict.ok).toBe(true);
    expect(verdict.unverified).toEqual(['走廊里一时安静下来']);
  });

  it('measures repetition against the previous point', () => {
    const fresh = grade('nv-cont-3', '五分钟又过去了，学生A仍然在大厅。', true);
    const repeated = grade('nv-cont-3', '学生A从走廊走到大厅。学生B还站在大厅里，两分钟过去，他的呼吸慢慢平复了。五分钟又过去了。', true);
    expect(fresh.repetition).not.toBeNull();
    expect(repeated.repetition).toBeGreaterThan(fresh.repetition ?? 0);
  });
});

describe('number and time helpers', () => {
  it('reads Chinese numerals and rejects digit prefixes', () => {
    expect(cnNumber(2)).toBe('二');
    expect(cnNumber(12)).toBe('十二');
    expect(cnNumber(30)).toBe('三十');
    expect(cnNumber(100)).toBeNull();
    expect(mentionsNumber('精神值从10升到12', 12)).toBe(true);
    expect(mentionsNumber('精神值从10升到12', 2)).toBe(false);
    expect(mentionsNumber('两分钟', 2)).toBe(true);
    expect(mentionsNumber('两分钟', 20)).toBe(false);
  });

  it('requires both the amount and the unit for a time mention', () => {
    expect(mentionsTime('两分钟过去了', { amount: 2, unit: 'minute' })).toBe(true);
    expect(mentionsTime('过了一会儿', { amount: 2, unit: 'minute' })).toBe(false);
    expect(mentionsTime('两秒钟过去了', { amount: 2, unit: 'minute' })).toBe(false);
  });
});

describe('validation corpus', () => {
  // 口径：冻结时是留出集，但 hv-sanity-1 的重跑采纳稿随后推动了判分器修正并
  // 进入回归——这六例现在是验证集，不再声明「从未参与校准」。
  it('freezes six validation samples over a different surface', () => {
    expect(NARRATION_EVAL_VALIDATION_SAMPLES).toHaveLength(6);
    expect(new Set(NARRATION_EVAL_VALIDATION_SAMPLES.map((entry) => entry.id)).size).toBe(6);
    const main = new Set(NARRATION_EVAL_SAMPLES.map((entry) => entry.id));
    for (const entry of NARRATION_EVAL_VALIDATION_SAMPLES) expect(main.has(entry.id)).toBe(false);
    expect(NARRATION_EVAL_VALIDATION_SAMPLES.every((entry) => entry.roster.includes('学生C'))).toBe(true);
    expect(NARRATION_EVAL_SAMPLES.some((entry) => entry.roster.includes('学生C'))).toBe(false);
  });

  it('accepts every validation reference under requireTime and the template arm', () => {
    for (const entry of NARRATION_EVAL_VALIDATION_SAMPLES) {
      const reference = alignNarration(entry.packet, entry.reference,
        { time: entry.time, locations: entry.locations, roster: entry.roster, previousText: entry.previousText, requireTime: true });
      expect(reference.ok, `${entry.id} reference: ${JSON.stringify(reference.violations)} missing=${JSON.stringify(reference.omissions)}`).toBe(true);
      const template = alignNarration(entry.packet, templateText(entry),
        { time: entry.time, locations: entry.locations, roster: entry.roster, requireTime: true });
      expect(template.ok, `${entry.id} template: ${JSON.stringify(template.violations)}`).toBe(true);
    }
  });

  it('keeps every validation mechanical text inside the old exact-clause gate', () => {
    for (const entry of NARRATION_EVAL_VALIDATION_SAMPLES) {
      if (!entry.mechanical) continue;
      expect(checkFactNarration(entry.packet, entry.mechanical).ok,
        `${entry.id} must stay acceptable to the old exact-clause gate`).toBe(true);
      expect(gradeValidation(entry.id, entry.mechanical).ok).toBe(true);
    }
  });

  it('still rejects the validation mutations the corpus documents', () => {
    expect(gradeValidation('hv-move-1', '学生C从操场走到食堂，前后约三分钟。').violations.map((violation) => violation.kind))
      .toContain('direction_reversed');
    expect(gradeValidation('hv-sanity-1', '学生C的精神值从12变为了8，前后大约两分钟。').violations.map((violation) => violation.kind))
      .toContain('wrong_number');
    expect(gradeValidation('hv-refused-1', '学生C走到了图书馆。').violations.map((violation) => violation.kind))
      .toContain('movement_without_fact');
    expect(gradeValidation('hv-empty-1', '学生C站在食堂。').violations.map((violation) => violation.kind))
      .toContain('state_claim_without_fact');
    expect(gradeValidation('hv-task-pers-1', '学生C完成了任务「整理图书角」。').violations.map((violation) => violation.kind))
      .toContain('actor_swap');
    // hv-sanity-1 重跑首稿原样：给无事实的学生D 捏造同款数值变化。
    expect(gradeValidation('hv-sanity-1', '学生D的精神值从12降到了9，前后大约两分钟。').violations.map((violation) => violation.kind))
      .toContain('actor_swap');
  });
});

describe('three-arm harness', () => {
  it('adopts a fact-faithful natural text and falls back otherwise', async () => {
    const generator: NarrationGenerator = {
      async generate(prompt, entry, attempt) {
        // Faithful for movement, contradictory for the task sample; the second
        // attempt is checked to have received the feedback.
        if (entry.id === 'nv-move-1') return { text: '学生A从走廊走进大厅，前后大约两分钟。', ms: 10 };
        if (entry.id === 'nv-task-pers-sanity-1' && attempt === 1) {
          expect(prompt).not.toContain('上一稿的问题');
          return { text: '学生B完成了任务「帮主角熟悉校园」，精神值从10变成了9。', ms: 20 };
        }
        if (entry.id === 'nv-task-pers-sanity-1') {
          expect(prompt).toContain('上一稿的问题');
          return { text: '学生B完成了任务「帮主角熟悉校园」。学生B变得健谈，精神值从10升到12。一分钟过去了。', ms: 30 };
        }
        return { text: entry.reference, ms: 5 };
      },
    };
    const report = await runNarrationEvaluation({ samples: NARRATION_EVAL_SAMPLES, generator });
    expect(report.summary.samples).toBe(10);
    // the template narrates time everywhere and fills empty points with the
    // fixed line, so all ten pass fact alignment.
    expect(report.summary.templateAccepted).toBe(10);
    expect(report.summary.naturalAdopted).toBe(10);
    expect(report.summary.regenerated).toBe(1);
    expect(report.summary.fellBack).toBe(0);
    const task = report.samples.find((run) => run.sampleId === 'nv-task-pers-sanity-1');
    expect(task?.natural.attempts).toHaveLength(2);
    expect(task?.natural.attempts[0].verdict.violations[0]?.kind).toBe('wrong_number');
    expect(task?.natural.attempts[1].verdict.ok).toBe(true);
  });

  it('falls back to the template after the retry budget', async () => {
    const generator: NarrationGenerator = {
      async generate() { return { text: '主角走到了门厅。', ms: 1 }; },
    };
    const report = await runNarrationEvaluation({ samples: [sample('nv-refused-1')], generator });
    expect(report.summary.fellBack).toBe(1);
    expect(report.summary.fallbackRate).toBe(1);
    expect(report.samples[0].natural.text).toBe(templateText(sample('nv-refused-1')));
  });

  it('never shows the model a literal example duration', () => {
    const prompt = buildNaturalPrompt(sample('nv-cont-1'));
    expect(prompt).toContain('时长数值必须与上面给出的完全一致');
    expect(prompt).not.toContain('两分钟过去了');
  });

  it('gives the model field values, never ready sentences', () => {
    const prompt = buildNaturalPrompt(sample('nv-move-1'));
    expect(prompt).toContain('学生A / 位置 = 从 走廊 到 大厅');
    expect(prompt).toContain('本点时间推进：2 分钟');
    expect(prompt).not.toContain('学生A从走廊走到大厅');
  });
});
