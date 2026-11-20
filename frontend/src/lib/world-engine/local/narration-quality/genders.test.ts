import { describe, expect, it } from 'vitest';
import { REVIEWED_GENDERS, genderOptions, unknownGenders } from './genders';
import { reviewNarration } from './review';

const scene = {
  视角: '主角视角（周宁）',
  上回合状态: { 人物: { 周宁: { 位置: '走廊', 精神值: 50, 外貌: ['穿蓝衣'] }, 林川: { 位置: '走廊', 精神值: 40 } } },
  本回合变化: { 时间推进: '2 分钟', 变化: {} },
  本回合状态: { 周宁: { 位置: '走廊' }, 林川: { 位置: '走廊' } },
} as never;

describe('reviewed genders', () => {
  it('only exposes entries with a recorded source', () => {
    expect(genderOptions()).toEqual({
      周宁: 'female', 路明非: 'male', 诺诺: 'female', 楚子航: 'male', 林亦舟: 'male', 沈澄: 'female',
    });
    expect(REVIEWED_GENDERS.周宁.source).toMatch(/humanReviewFindings/u);
    for (const name of ['路明非', '诺诺', '楚子航', '林亦舟', '沈澄']) {
      expect(REVIEWED_GENDERS[name].source).toMatch(/character-gender-evidence|world-file|initialPersonality|initialAppearance/u);
    }
  });

  it('lists characters with no recorded source instead of guessing', () => {
    expect(unknownGenders(['周宁', '林川'])).toEqual(['林川']);
  });

  it('flags a wrong pronoun only when the binding is unambiguous', () => {
    const alone = {
      视角: '主角视角（周宁）',
      上回合状态: { 人物: { 周宁: { 位置: '走廊', 精神值: 50, 外貌: ['穿蓝衣'] } } },
      本回合变化: { 时间推进: '2 分钟', 变化: {} },
      本回合状态: { 周宁: { 位置: '走廊' } },
    } as never;
    const wrong = reviewNarration({ id: 'g1', input: alone, text: '两分钟过去，周宁把袖子卷起，他看了一眼门口。', options: { genders: genderOptions() } });
    expect(wrong.findings.some((finding) => finding.kind === 'fact.gender')).toBe(true);
    // A co-present person whose gender is not recorded makes 他 ambiguous, not a
    // hard error: the checker cannot rule out that the pronoun means 林川.
    const ambiguous = reviewNarration({ id: 'g1b', input: scene, text: '两分钟过去，周宁把袖子卷起，他看了一眼门口。', options: { genders: genderOptions() } });
    expect(ambiguous.findings.some((finding) => finding.kind === 'fact.gender')).toBe(false);
    expect(ambiguous.findings.some((finding) => finding.kind === 'review.pronoun')).toBe(true);
    const right = reviewNarration({ id: 'g2', input: scene, text: '两分钟过去，周宁把袖子卷起，她看了一眼门口。', options: { genders: genderOptions() } });
    expect(right.findings.some((finding) => finding.kind === 'fact.gender')).toBe(false);
  });

  it('does not guess for a character with no recorded gender', () => {
    const report = reviewNarration({ id: 'g3', input: scene, text: '两分钟过去，林川把袖子卷起，她看了一眼门口。', options: { genders: genderOptions() } });
    expect(report.findings.some((finding) => finding.kind === 'fact.gender')).toBe(false);
  });
});
