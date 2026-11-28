import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildTestWorld } from '../semantics/actions/fixtures';
import { createMicroGoalTasks } from './goal-verifier';
import { createBertTokenizer } from './tokenizer';

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
  it('tokenizes the training text exactly like transformers BertTokenizer', () => {
    const vocab = readFileSync(resolve('public/micro/minirbt-vocab.txt'), 'utf8');
    const tokenizer = createBertTokenizer(vocab);
    const ids = tokenizer.encode('把胸前护目镜戴好并确认镜片没有裂纹 ␟ 路明非把护目镜戴好，确认镜片无裂纹。', 192);
    expect(ids).toEqual([
      101, 2828, 5541, 1184, 2844, 4680, 7262, 2785, 1962, 2400, 4802, 6371, 7262, 4275, 3766, 3300,
      6162, 5292, 100, 6662, 3209, 7478, 2828, 2844, 4680, 7262, 2785, 1962, 8024, 4802, 6371, 7262,
      4275, 3187, 6162, 5292, 511, 102,
    ]);
  });

  it('keeps the best fact per task and accepts only above threshold', async () => {
    const port = createMicroGoalTasks({
      scoring: (rows) => rows.map((row) => (row.fact.includes('打开') && row.fact.includes('确认') ? 0.9 : 0.1)),
    });
    const out = await port({ state: state(), ownerIds: ['hero'], facts });
    expect(out?.achieved).toEqual([expect.objectContaining({ characterId: 'hero', taskId: 'task_hero_key', basis: 'f2' })]);
    expect(out?.scored).toHaveLength(2);
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

  it('candidates on a goal entity even when sentence overlap is low', async () => {
    const port = createMicroGoalTasks({ scoring: (rows) => rows.map(() => 0.9) });
    const out = await port({
      state: state(), ownerIds: ['hero'],
      facts: [{ id: 'f1', memberId: 'hero', text: '路明非检查了手电。' }],
    });
    expect(out?.achieved.map((row) => row.taskId)).toEqual(['task_hero_key']);
  });

  it('strict mode requires every decomposed goal condition in the fact', async () => {
    const port = createMicroGoalTasks({
      requireProgramCoverage: true,
      scoring: (rows) => rows.map(() => 0.9),
    });
    const partial = await port({
      state: state(), ownerIds: ['hero'],
      facts: [{ id: 'f1', memberId: 'hero', text: '路明非拿起手电（达到目的）。' }],
    });
    expect(partial?.achieved).toEqual([]);
    expect(partial?.scored).toEqual([]);
    const complete = await port({
      state: state(), ownerIds: ['hero'],
      facts: [{ id: 'f2', memberId: 'hero', text: '路明非打开手电，确认电量（达到目的）。' }],
    });
    expect(complete?.achieved.map((row) => row.taskId)).toEqual(['task_hero_key']);
  });

  it('accumulates condition evidence across facts and turns', async () => {
    const port = createMicroGoalTasks({
      requireProgramCoverage: true,
      scoring: (rows) => rows.map(() => 0.9),
    });
    const first = await port({
      state: state(), ownerIds: ['hero'],
      facts: [{ id: 'f1', memberId: 'hero', text: '路明非找到手电（达到目的）。' }],
    });
    expect(first?.achieved).toEqual([]);
    const second = await port({
      state: state(), ownerIds: ['hero'],
      facts: [{ id: 'f2', memberId: 'hero', text: '路明非打开它并确认电量（达到目的）。' }],
    });
    expect(second?.achieved).toEqual([
      expect.objectContaining({ taskId: 'task_hero_key', basis: 'cross_turn', covered: expect.any(Array) }),
    ]);
    expect(second?.achieved[0]?.covered?.map((row) => row.condition)).toEqual(
      expect.arrayContaining(['物品=手电', '动作=打开', '确认=确认']),
    );
  });

  it('restores accumulated evidence from a persisted ledger', async () => {
    const options = { requireProgramCoverage: true, scoring: () => [0.9] };
    const first = createMicroGoalTasks(options);
    await first({ state: state(), ownerIds: ['hero'], facts: [{ id: 'f1', memberId: 'hero', text: '路明非找到手电（达到目的）。' }] });
    const snapshot = first.exportLedger();
    expect(snapshot?.entries[0]?.covered.map((row) => row.condition)).toContain('物品=手电');
    const second = createMicroGoalTasks(options);
    second.importLedger(snapshot);
    const out = await second({
      state: state(), ownerIds: ['hero'],
      facts: [{ id: 'f2', memberId: 'hero', text: '路明非打开它并确认电量（达到目的）。' }],
    });
    expect(out?.achieved.map((row) => row.taskId)).toEqual(['task_hero_key']);
  });

  it('does not credit another member fact to a task unless it names the owner', async () => {
    const port = createMicroGoalTasks({ scoring: (rows) => rows.map(() => 0.9) });
    const notNamed = await port({
      state: state(), ownerIds: ['ally'],
      facts: [{ id: 'f1', memberId: 'hero', text: '路明非守住大厅木门，别让红方进来。' }],
    });
    expect(notNamed?.scored).toEqual([]);
    const named = await port({
      state: state(), ownerIds: ['ally'],
      facts: [{ id: 'f1', memberId: 'hero', text: '路明非把阿宁推到门后，阿宁守住大厅木门。' }],
    });
    expect(named?.achieved.map((row) => row.taskId)).toEqual(['task_ally_watch']);
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
