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
    expect(genderOptions()).toEqual({ 周宁: 'female' });
    expect(REVIEWED_GENDERS.周宁.source).toMatch(/humanReviewFindings/u);
  });

  it('lists characters with no recorded source instead of guessing', () => {
    expect(unknownGenders(['周宁', '林川'])).toEqual(['林川']);
  });

  it('flags a wrong pronoun only when the binding is unambiguous', () => {
    const wrong = reviewNarration({ id: 'g1', input: scene, text: '两分钟过去，周宁把袖子卷起，他看了一眼门口。', options: { genders: genderOptions() } });
    expect(wrong.findings.some((finding) => finding.kind === 'fact.gender')).toBe(true);
    const right = reviewNarration({ id: 'g2', input: scene, text: '两分钟过去，周宁把袖子卷起，她看了一眼门口。', options: { genders: genderOptions() } });
    expect(right.findings.some((finding) => finding.kind === 'fact.gender')).toBe(false);
  });

  it('does not guess for a character with no recorded gender', () => {
    const report = reviewNarration({ id: 'g3', input: scene, text: '两分钟过去，林川把袖子卷起，她看了一眼门口。', options: { genders: genderOptions() } });
    expect(report.findings.some((finding) => finding.kind === 'fact.gender')).toBe(false);
  });
});
