import { describe, expect, it } from 'vitest';
import { buildTestWorld } from '../semantics/actions/fixtures';
import { createMicroGoalTasks } from './goal-verifier';

function state() {
  const world = buildTestWorld();
  world.characters.hero.tasks.task_hero_key.goal = '把手电打开并确认电量';
  world.initial.characters.hero.tasks.task_hero_key.goal = '把手电打开并确认电量';
  return world;
}

const facts = [
  { id: 'f1', memberId: 'hero', text: '路明非拿起手电。' },
  { id: 'f2', memberId: 'hero', text: '路明非打开手电并确认电量。' },
];

describe('goal-level task stage', () => {
  it('keeps the best fact per task and accepts only above threshold', async () => {
    const port = createMicroGoalTasks({
      scoring: (rows) => rows.map((row) => (row.fact.includes('打开') && row.fact.includes('确认') ? 0.9 : 0.1)),
    });
    const out = await port({ state: state(), ownerIds: ['hero'], facts });
    expect(out?.achieved).toEqual([expect.objectContaining({ characterId: 'hero', taskId: 'task_hero_key', basis: 'f2' })]);
    expect(out?.scored).toHaveLength(1);
  });

  it('returns no achievement, not null, when candidates exist but score low', async () => {
    const port = createMicroGoalTasks({ scoring: (rows) => rows.map(() => 0.2) });
    const out = await port({ state: state(), ownerIds: ['hero'], facts });
    expect(out).toEqual({ achieved: [], scored: expect.any(Array), source: 'micro' });
  });

  it('abstains when the scorer fails', async () => {
    const port = createMicroGoalTasks({ scoring: () => null });
    expect(await port({ state: state(), ownerIds: ['hero'], facts })).toBeNull();
  });

  it('skips owners outside the affected set and facts with no goal wording', async () => {
    const port = createMicroGoalTasks({ scoring: (rows) => rows.map(() => 0.9) });
    const out = await port({
      state: state(), ownerIds: ['nobody'],
      facts: [{ id: 'f9', memberId: 'hero', text: '路明非靠着墙站着。' }],
    });
    expect(out?.achieved).toEqual([]);
    expect(out?.scored).toEqual([]);
  });
});
