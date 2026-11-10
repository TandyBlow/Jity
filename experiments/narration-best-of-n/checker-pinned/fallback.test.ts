import { describe, expect, it } from 'vitest';
import { reviewNarration } from './review';

/** Real texts only: no synthetic fallback strings. */
const input = {
  视角: '主角视角（路明非）；只表达已结算的世界事实',
  上回合状态: {
    人物: {
      路明非: {
        位置: '西回廊',
        精神值: 43,
        个性: ['习惯先用一句玩笑替自己解围'],
        任务: { 大任务: { 目标: '作出参赛选择', 状态: '未完成' }, 小任务: [{ 目标: '向诺诺问清当前红蓝两方局势和自己是否可以保持中立', 状态: '未完成' }] },
      },
      诺诺: { 位置: '西回廊', 精神值: 58 },
      林亦舟: { 位置: '西回廊', 精神值: 29 },
    },
  },
  本回合变化: {
    时间推进: '3 分钟',
    变化: {
      路明非: {
        精神值: 48,
        新增个性: ['不再等别人替他决定，愿意先迈出一步'],
        任务: { 小任务: [{ 目标: '向诺诺问清当前红蓝两方局势和自己是否可以保持中立', 状态: '已完成' }] },
      },
    },
  },
  本回合状态: {
    路明非: { 位置: '西回廊', 精神值: 48, 个性: ['不再等别人替他决定，愿意先迈出一步'],
      任务: { 小任务: [{ 目标: '向诺诺问清当前红蓝两方局势和自己是否可以保持中立', 状态: '已完成' }] } },
    诺诺: { 位置: '西回廊' },
    林亦舟: { 位置: '西回廊' },
  },
} as never;

const PANEL_TEXT = [
  '「站住！」林亦舟叫道。',
  '路明非把「向诺诺问清当前红蓝两方局势和自己是否可以保持中立」这件事做完了。',
  '路明非不再等别人替他决定，愿意先迈出一步。。',
  '路明非的精神值从43变成了48。',
  '约三分钟过去了。',
].join('\n\n');

const PROSE_TEXT = [
  '三分钟过去，路明非把护目镜往上推了推。',
  '「红蓝两边现在各占哪儿？」他问。',
  '诺诺拿枪口点了点西回廊。「红方在集结点，蓝方守着钟楼。」',
  '路明非没急着走，先问自己能不能不动。诺诺看了他一眼，没有答。',
].join('\n\n');

describe('fallback suspicion', () => {
  it('flags a text built only from settled-fact lines as consistent with a program fallback', () => {
    const report = reviewNarration({ id: 'panel', input, text: PANEL_TEXT });
    expect(report.fallbackSuspicion.suspected).toBe(true);
    expect(report.fallbackSuspicion.panelShare).toBeGreaterThanOrEqual(0.6);
  });

  it('does not flag prose with dialogue and unbound sentences', () => {
    const report = reviewNarration({ id: 'prose', input, text: PROSE_TEXT });
    expect(report.fallbackSuspicion.suspected).toBe(false);
    expect(report.metrics.dialogueRatio).toBeGreaterThan(0);
  });
});
