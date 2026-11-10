import { describe, expect, it } from 'vitest';
import { reviewSequence, statedMinutes, type TurnRecord } from './sequence';

const place = (name: string, where: string) => ({ 位置: where });

function turn(turnNumber: number, input: Record<string, unknown>, text: string): TurnRecord {
  return { groupId: 'g1', turn: turnNumber, input: input as never, text };
}

const baseInput = {
  视角: '主角视角（甲）',
  上回合状态: { 人物: { 甲: place('甲', '院子'), 乙: place('乙', '门口') }, 物品: { 灯: { 位置: '院子' } } },
  本回合变化: { 时间推进: '2 分钟', 变化: {} },
  本回合状态: { 甲: place('甲', '院子'), 乙: place('乙', '门口') },
};

describe('statedMinutes', () => {
  it('reads arabic, chinese and half-hour forms', () => {
    expect(statedMinutes('两分钟过去，又过了 3 分钟')).toEqual([2, 3]);
    expect(statedMinutes('半小时后')).toEqual([0.5]);
    expect(statedMinutes('十二分钟')).toEqual([12]);
  });
});

describe('reviewSequence', () => {
  it('passes a consistent two-turn sequence', () => {
    const report = reviewSequence([
      turn(1, baseInput, '两分钟过去，甲还站在院子里。'),
      turn(2, {
        ...baseInput,
        本回合变化: { 时间推进: '3 分钟', 变化: {} },
      }, '又过了三分钟，乙走到门口，甲没有动。'),
    ]);
    expect(report.counts.conflict).toBe(0);
    expect(report.turns).toBe(2);
  });

  it('flags a presence regression when a settled person is written as leaving', () => {
    const report = reviewSequence([
      turn(1, baseInput, '两分钟过去，甲站在院子里。'),
      turn(2, baseInput, '乙离开了门口，甲还站在院子里。'),
    ]);
    expect(report.findings.some((f) => f.check === 'presence' && f.status === 'conflict')).toBe(true);
  });

  it('flags a completed task written as unfinished later', () => {
    const done = {
      视角: '主角视角（甲）',
      上回合状态: { 人物: { 甲: { 位置: '院子', 任务: { 小任务: [{ 目标: '核查水位', 状态: '未完成' }] } } } },
      本回合变化: { 时间推进: '2 分钟', 变化: { 甲: { 任务: { 小任务: [{ 目标: '核查水位', 状态: '已完成' }] } } } },
      本回合状态: { 甲: { 位置: '院子', 任务: { 小任务: [{ 目标: '核查水位', 状态: '已完成' }] } } },
    };
    const later = {
      视角: '主角视角（甲）',
      上回合状态: done.本回合状态,
      本回合变化: { 时间推进: '2 分钟', 变化: {} },
      本回合状态: { 甲: { 位置: '院子', 任务: { 小任务: [{ 目标: '核查水位', 状态: '已完成' }] } } },
    };
    const report = reviewSequence([
      turn(1, done, '两分钟过去，甲把水位核查做完了。'),
      turn(2, later, '甲想起核查水位还没做，又看了一眼水位尺。'),
    ]);
    expect(report.findings.some((f) => f.check === 'task' && f.status === 'conflict')).toBe(true);
  });

  it('flags an item the prose already knew being treated as unknown', () => {
    const report = reviewSequence([
      turn(1, baseInput, '两分钟过去，灯还在院子里。'),
      turn(2, baseInput, '甲看着院子，不知道那盏灯是什么。'),
    ]);
    expect(report.findings.some((f) => f.check === 'item_knowledge' && f.status === 'conflict')).toBe(true);
  });

  it('flags the same elapsed span stated in two turns', () => {
    const report = reviewSequence([
      turn(1, baseInput, '两分钟过去，甲站在院子里。'),
      turn(2, baseInput, '两分钟过去，乙还站在门口。'),
    ]);
    expect(report.findings.some((f) => f.check === 'event_time' && f.status === 'conflict')).toBe(true);
  });

  it('flags a settled time that the prose never states', () => {
    const report = reviewSequence([turn(1, baseInput, '甲站在院子里，看着门口。')]);
    expect(report.findings.some((f) => f.check === 'event_time' && f.status === 'conflict')).toBe(true);
  });

  it('marks a stated time with no settled advance as undetermined, not pass', () => {
    const noTime = {
      视角: '主角视角（甲）',
      上回合状态: { 人物: { 甲: place('甲', '院子') } },
      本回合变化: { 变化: {} },
      本回合状态: { 甲: place('甲', '院子') },
    };
    const report = reviewSequence([turn(1, noTime, '五分钟过去，甲站在院子里。')]);
    expect(report.findings.some((f) => f.check === 'event_time' && f.status === 'undetermined')).toBe(true);
    expect(report.counts.pass).toBe(0);
  });
});
