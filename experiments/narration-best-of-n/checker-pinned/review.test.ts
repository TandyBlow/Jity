import { describe, expect, it } from 'vitest';
import { parseMinutes, parseViewpoint, projectScene } from './scene';
import { reviewNarration } from './review';
import type { DatasetInput } from './scene';

const scene: DatasetInput = {
  视角: '主角视角（周宁）；只表达已结算的世界事实',
  上回合状态: {
    地点: {
      走廊: { 位于: null, 外貌: ['明亮的走廊，通往门厅。'] },
      门厅: { 位于: '走廊', 外貌: ['门厅的灯亮着。'] },
    },
    人物: {
      周宁: { 位置: '走廊', 精神值: 40, 外貌: ['穿蓝衣'], 个性: ['好奇'], 任务: { 大任务: { 目标: '把盒子交到门厅', 状态: '未完成' }, 小任务: [] } },
      林川: { 位置: '走廊', 精神值: 10, 外貌: ['穿灰衣'], 个性: ['谨慎'], 任务: { 小任务: [] } },
    },
    物品: { 盒子: { 位置: '走廊', 外貌: ['盒盖关闭'] } },
  },
  本回合变化: {
    时间推进: '2 分钟',
    变化: {
      林川: { 位置: '门厅' },
      周宁: { 精神值: 44, 任务: { 大任务: { 目标: '把盒子交到门厅', 状态: '已完成' }, 小任务: [] } },
    },
  },
  本回合状态: {
    林川: { 位置: '门厅' },
    周宁: { 精神值: 44, 任务: { 大任务: { 目标: '把盒子交到门厅', 状态: '已完成' }, 小任务: [] } },
  },
};

describe('scene projection', () => {
  it('parses viewpoint and minutes', () => {
    expect(parseViewpoint('主角视角（周宁）；只表达已结算的世界事实')).toBe('周宁');
    expect(parseMinutes('2 分钟')).toBe(2);
    expect(parseMinutes('二十二分钟')).toBe(22);
    expect(parseMinutes('半小时')).toBe(30);
    expect(parseMinutes('')).toBeNull();
  });

  it('derives moves, task completion and sanity from before/after', () => {
    const projection = projectScene(scene);
    expect(projection.moves).toEqual([{ id: 'move:林川', kind: 'person', name: '林川', from: '走廊', to: '门厅' }]);
    expect(projection.taskCompleted.map((task) => task.name)).toEqual(['周宁']);
    expect(projection.sanityChanges).toEqual([{ id: 'sanity:周宁', name: '周宁', from: 40, to: 44 }]);
    expect(projection.viewpoint).toBe('周宁');
  });
});

describe('independent review', () => {
  it('accepts a fact-faithful narration', () => {
    const report = reviewNarration({
      id: 'ok',
      input: scene,
      text: '两分钟过去，林川从走廊走进门厅。周宁留在走廊，把「把盒子交到门厅」这件事办完了，精神值从 40 升到 44。',
    });
    expect(report.findings.filter((entry) => entry.severity === 'fact')).toEqual([]);
    expect(report.time.expressed).toBe(true);
  });

  it('rejects a reversed move and a wrong sanity number', () => {
    const report = reviewNarration({
      id: 'bad',
      input: scene,
      text: '两分钟过去，林川从门厅走回走廊。周宁把「把盒子交到门厅」办完了，精神值从 40 升到 52。',
    });
    const kinds = report.findings.map((entry) => entry.kind);
    expect(kinds).toContain('fact.direction_reversed');
    expect(kinds).toContain('fact.wrong_number');
  });

  it('rejects a stat recital as style, without a fact error', () => {
    const report = reviewNarration({
      id: 'panel',
      input: scene,
      text: '两分钟过去，林川从走廊走进门厅。周宁把「把盒子交到门厅」这件事做完了。周宁的精神值从 40 变成了 44。',
    });
    expect(report.findings.filter((entry) => entry.severity === 'fact')).toEqual([]);
    const kinds = report.findings.map((entry) => entry.kind);
    expect(kinds).toContain('style.status_panel');
    expect(kinds).toContain('style.field_sentence');
  });

  it('never returns an empty judgement for an unbound sentence', () => {
    const report = reviewNarration({
      id: 'unbound',
      input: scene,
      text: '两分钟过去，林川从走廊走进门厅。空气里有一种说不清的味道。周宁把「把盒子交到门厅」办完了，精神值从 40 升到 44。',
    });
    const sentence = report.sentences.find((entry) => entry.sentence.includes('空气里'));
    expect(sentence?.judgement).not.toBe('fact_clean');
    expect(sentence?.findings.some((entry) => entry.kind === 'review.tone')).toBe(true);
  });

  it('flags a gender contradiction against the reviewed registry', () => {
    const single: DatasetInput = {
      视角: '主角视角（周宁）；只表达已结算的世界事实',
      上回合状态: {
        地点: { 走廊: { 位于: null, 外貌: ['明亮的走廊。'] } },
        人物: { 周宁: { 位置: '走廊', 精神值: 40, 外貌: ['穿蓝衣'], 个性: ['好奇'], 任务: { 小任务: [] } } },
      },
      本回合变化: { 时间推进: '2 分钟', 变化: {} },
    };
    const report = reviewNarration({
      id: 'gender',
      input: single,
      text: '两分钟过去。他站在走廊里，看着脚边的盒子，没有动。',
      options: { genders: { 周宁: 'female' } },
    });
    expect(report.findings.map((entry) => entry.kind)).toContain('fact.gender');
  });
});
