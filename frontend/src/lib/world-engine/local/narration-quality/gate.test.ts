import { describe, expect, it } from 'vitest';
import { gateNarration } from './gate';
import { reviewNarration } from './review';

const input = {
  视角: '主角视角（甲）',
  上回合状态: { 人物: { 甲: { 位置: '院子', 精神值: 50 } } },
  本回合变化: { 时间推进: '2 分钟', 变化: { 甲: { 精神值: 48 } } },
  本回合状态: { 甲: { 位置: '院子', 精神值: 48 } },
} as never;

const clean = '两分钟过去，甲把外套的扣子扣好，站在院子当中听了一会儿。风从墙头过，草叶贴着地面倒下去，又慢慢立起来。';

describe('gateNarration', () => {
  it('holds, rather than accepts, a clean text with unbound sentences', () => {
    const report = reviewNarration({ id: 'a', input, text: clean });
    const gate = gateNarration(report, { minChars: 10 });
    expect(gate.decision).toBe('hold_for_review');
    expect(gate.reviewItems).toBeGreaterThan(0);
  });

  it('regenerates on a wrong settled number', () => {
    const report = reviewNarration({ id: 'b', input, text: '两分钟过去，甲的精神值从50变成了45。' });
    const gate = gateNarration(report);
    expect(gate.decision).toBe('regenerate');
    expect(gate.factFindings).toBeGreaterThan(0);
  });

  it('regenerates on a field-sentence recital of the right number', () => {
    const report = reviewNarration({ id: 'c', input, text: '两分钟过去，甲的精神值从50变成了48。' });
    const gate = gateNarration(report);
    expect(gate.decision).toBe('regenerate');
    expect(gate.blockingStyles.length).toBeGreaterThan(0);
  });

  it('regenerates a program fallback even when it is labelled model', () => {
    // A fallback that rewrites the facts instead of copying them still reads as
    // a state report: place and appearance lines, a "Name：…" panel.
    const fallbackInput = {
      视角: '主角视角（甲）',
      上回合状态: {
        地点: { 院子: { 位于: null, 外貌: ['院子里的墙头很高，草叶贴着地面。'] } },
        人物: {
          甲: { 位置: '院子', 精神值: 50, 外貌: [] },
          乙: { 位置: '院子', 精神值: 50, 外貌: ['袖子挽到肘上，手腕露在外面'] },
        },
        物品: {},
      },
      本回合变化: { 时间推进: '2 分钟', 变化: { 甲: { 精神值: 48 } } },
      本回合状态: { 人物: {}, 物品: {} },
    } as never;
    const fallback = '两分钟过去，甲还在院子。' + String.fromCharCode(10,10) + '院子里的墙头很高，草叶贴着地面。' + String.fromCharCode(10,10) + '身边还有乙，袖子挽到肘上，手腕露在外面。' + String.fromCharCode(10,10) + '甲：本组结算未能确认新的结果。';
    const report = reviewNarration({ id: 'e', input: fallbackInput, text: fallback });
    expect(report.fallbackSuspicion.suspected).toBe(true);
    expect(gateNarration(report, { textSource: 'model' }).decision).toBe('regenerate');
  });

  it('refuses to accept program fallback or mixed segments as model prose', () => {
    const report = reviewNarration({ id: 'd', input, text: clean });
    expect(gateNarration(report, { textSource: 'program_fallback' }).decision).toBe('regenerate');
    expect(gateNarration(report, { textSource: 'mixed' }).decision).toBe('regenerate');
    // 06's provenance labels: a committed draft and a program scene are not
    // accepted prose either, and an unknown source must not be assumed clean.
    expect(gateNarration(report, { textSource: 'draft' }).decision).toBe('regenerate');
    expect(gateNarration(report, { textSource: 'program' }).decision).toBe('regenerate');
    expect(gateNarration(report, { textSource: 'unknown' }).decision).toBe('regenerate');
  });

  it('regenerates when the settled time is missing', () => {
    const report = reviewNarration({ id: 'e', input, text: '甲站在院子当中，听了一会儿风。' });
    const gate = gateNarration(report);
    expect(gate.decision).toBe('regenerate');
    expect(gate.reasons).toContain('time_not_expressed');
  });
});
