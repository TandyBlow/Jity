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

  it('refuses to accept program fallback or mixed segments as model prose', () => {
    const report = reviewNarration({ id: 'd', input, text: clean });
    expect(gateNarration(report, { textSource: 'program_fallback' }).decision).toBe('regenerate');
    expect(gateNarration(report, { textSource: 'mixed' }).decision).toBe('regenerate');
  });

  it('regenerates when the settled time is missing', () => {
    const report = reviewNarration({ id: 'e', input, text: '甲站在院子当中，听了一会儿风。' });
    const gate = gateNarration(report);
    expect(gate.decision).toBe('regenerate');
    expect(gate.reasons).toContain('time_not_expressed');
  });
});
