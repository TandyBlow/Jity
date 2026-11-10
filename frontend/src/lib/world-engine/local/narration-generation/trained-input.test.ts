// Trained-shape renderer tests: the prompt the checkpoints were trained on
// must be reproducible from the same read-only state the page has.
import { describe, expect, test } from 'vitest';
import { SHORT_STATE } from '../../runtime/b3-short-samples';
import type { EntityDelta, WorldState } from '../../types';
import {
  renderTrainedInstructUser, renderTrainedRawPrompt, trainedSceneView, wrapChatml,
} from './trained-input';

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const position = (containerId: string) => ({ containerId, slotId: null, relativeTo: null });

describe('trained-shaped scene input', () => {
  test('renders the movement point in the trained 视角/上回合状态/本回合变化/本回合状态 shape', () => {
    const before = clone(SHORT_STATE) as WorldState;
    const after = clone(SHORT_STATE) as WorldState;
    after.characters.person_a.position = position('hall');
    const delta: Record<string, EntityDelta> = {
      person_a: { entityId: 'person_a', positionSet: position('hall') },
    };
    const view = trainedSceneView({
      before, after, delta,
      timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } },
    });
    expect(view.视角).toBe('主角视角（周宁）；只表达已结算的世界事实');
    expect(Object.keys(view.上回合状态.地点)).toEqual(expect.arrayContaining(['走廊', '门厅']));
    expect(view.上回合状态.人物['林川'].位置).toBe('门厅');
    expect(view.上回合状态.人物['周宁'].位置).toBe('走廊');
    expect(view.本回合变化.变化['林川']).toEqual({ 位置: '门厅' });
    expect(view.本回合变化.时间推进).toBe('0 秒');
    expect(view.本回合状态['林川']).toEqual({ 位置: '门厅' });
    // Only changed entities appear in the result block.
    expect(Object.keys(view.本回合状态)).toEqual(['林川']);
    const raw = renderTrainedRawPrompt(view);
    expect(raw.startsWith('【状态】{')).toBe(true);
    expect(raw.endsWith('\n【视角】主角视角（周宁）；只表达已结算的世界事实\n【叙事】')).toBe(true);
    const user = renderTrainedInstructUser(view);
    expect(user.split('\n').filter((line) => line.startsWith('【'))).toEqual([
      '【上回合状态】', '【本回合变化】', '【本回合状态】', '【视角】',
    ]);
    expect(wrapChatml('SYS', 'USER')).toBe(
      '<|im_start|>system\nSYS<|im_end|>\n<|im_start|>user\nUSER<|im_end|>\n<|im_start|>assistant\n',
    );
  });

  test('renders appearance and task changes with their removal lines', () => {
    const before = clone(SHORT_STATE) as WorldState;
    before.characters.person_a.appearanceChanges = [{
      id: 'chg_1', text: '袖口破了', supersedes: [], sourcePointId: 'root', sourceSequence: 0, active: true,
    }] as never;
    const after = clone(before) as WorldState;
    after.characters.person_a.appearanceChanges = [{
      id: 'chg_2', text: '袖口缝好了', supersedes: ['chg_1'], sourcePointId: 'p1', sourceSequence: 1, active: true,
    }] as never;
    after.characters.person_a.tasks.task_watch.status = 'achieved';
    const delta: Record<string, EntityDelta> = {
      person_a: {
        entityId: 'person_a',
        appearanceChanges: [{ id: 'chg_2', text: '袖口缝好了', supersedes: ['chg_1'] }],
        tasksAchieved: ['task_watch'],
      },
    };
    const view = trainedSceneView({ before, after, delta, timeAdvance: null });
    expect(view.本回合变化.变化['林川']).toMatchObject({
      新增外貌: ['袖口缝好了'],
      解除外貌: ['袖口破了'],
      完成任务: ['留在走廊守门，不碰盒子'],
    });
    expect(view.本回合状态['林川'].外貌).toEqual(['穿灰衣', '袖口缝好了']);
    expect(view.本回合状态['林川'].任务).toEqual({ 大任务: { 目标: '留在走廊守门，不碰盒子', 状态: '已完成' } });
  });

  test('root point has an empty change block and no time line', () => {
    const state = clone(SHORT_STATE) as WorldState;
    const view = trainedSceneView({ before: null, after: state, delta: null, timeAdvance: null });
    expect(view.本回合变化).toEqual({ 变化: {} });
    expect(view.本回合状态).toEqual({});
  });
});
