import { describe, expect, it } from 'vitest';
import { buildTestWorld } from '../semantics/actions/fixtures';
import { createProgramSubtasks } from './subtasks';

function state() {
  const world = buildTestWorld();
  world.characters.hero.tasks.task_hero_key.goal = '把手电打开并确认电量';
  world.initial.characters.hero.tasks.task_hero_key.goal = '把手电打开并确认电量';
  return world;
}

describe('program subtask proposer', () => {
  it('turns a structured info marker into a concrete subgoal under a related task', async () => {
    const out = await createProgramSubtasks({
      state: state(), ownerIds: ['hero'],
      facts: [{ id: 'f1', memberId: 'hero', text: '路明非打开手电并确认电量（达到目的）；信息=torch:开关在侧边' }],
    });
    expect(out?.subtasks).toEqual([
      expect.objectContaining({ parentTaskId: 'task_hero_key', goal: '查看手电上的内容', basis: 'f1' }),
    ]);
  });

  it('returns no new goal when the fact has no structured marker', async () => {
    const out = await createProgramSubtasks({
      state: state(), ownerIds: ['hero'],
      facts: [{ id: 'f1', memberId: 'hero', text: '路明非打开手电并确认电量（达到目的）。' }],
    });
    expect(out?.subtasks).toEqual([]);
  });

  it('does not propose the same goal twice', async () => {
    const world = state();
    const first = await createProgramSubtasks({
      state: world, ownerIds: ['hero'],
      facts: [{ id: 'f1', memberId: 'hero', text: '路明非检查手电（达到目的）；信息=torch:开关在侧边' }],
    });
    const goal = first?.subtasks[0]?.goal ?? '';
    world.characters.hero.tasks.task_new = {
      id: 'task_new', ownerId: 'hero', parentTaskId: 'task_hero_key', goal, status: 'pending',
    };
    const second = await createProgramSubtasks({
      state: world, ownerIds: ['hero'],
      facts: [{ id: 'f2', memberId: 'hero', text: '路明非检查手电（达到目的）；信息=torch:开关在侧边' }],
    });
    expect(second?.subtasks).toEqual([]);
  });
});
