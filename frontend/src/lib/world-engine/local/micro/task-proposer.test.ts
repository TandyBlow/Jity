import { describe, expect, it } from 'vitest';
import { buildTestWorld } from '../semantics/actions/fixtures';
import { createMicroTaskProposer } from './task-proposer';

function state() {
  const world = buildTestWorld();
  world.characters.hero.tasks.task_hero_key.goal = '把手电打开并确认电量';
  world.initial.characters.hero.tasks.task_hero_key.goal = '把手电打开并确认电量';
  return world;
}

const scoring = (rows: Array<{ condition: { kind: string }; text: string }>) => rows.map((row) => {
  if (row.condition.kind === 'item') {
    return row.text.includes('手电') ? { label: 'satisfied' as const, confidence: 0.9 } : { label: 'none' as const, confidence: 0.9 };
  }
  if (row.condition.kind === 'action') {
    return row.text.includes('打开')
      ? { label: 'satisfied' as const, confidence: 0.9 }
      : row.text.includes('拿起') ? { label: 'attempt' as const, confidence: 0.9 } : { label: 'none' as const, confidence: 0.9 };
  }
  if (row.condition.kind === 'confirmation') {
    return row.text.includes('确认') ? { label: 'satisfied' as const, confidence: 0.9 } : { label: 'none' as const, confidence: 0.9 };
  }
  return { label: 'none' as const, confidence: 0.9 };
});

describe('task proposer', () => {
  it('accumulates conditions across calls and proposes only when all are satisfied', async () => {
    const proposer = createMicroTaskProposer({ scoring });
    const first = await proposer({ state: state(), facts: [{ id: 'f1', memberId: 'hero', text: '路明非拿起手电。' }] });
    expect(first?.supports).toEqual([]);
    expect(first?.pending.find((row) => row.taskId === 'task_hero_key')).toMatchObject({ matched: 1, total: 3 });

    const second = await proposer({ state: state(), facts: [{ id: 'f2', memberId: 'hero', text: '路明非打开手电。' }] });
    expect(second?.supports).toEqual([]);
    expect(second?.pending.find((row) => row.taskId === 'task_hero_key')).toMatchObject({ matched: 2, total: 3 });

    const third = await proposer({ state: state(), facts: [{ id: 'f3', memberId: 'hero', text: '路明非确认电量。' }] });
    expect(third?.supports).toEqual([expect.objectContaining({ characterId: 'hero', taskId: 'task_hero_key', basis: 'cross_turn' })]);
    expect(third?.supports[0]?.basisText).toContain('拿起手电');
    expect(third?.supports[0]?.basisText).toContain('确认电量');
  });

  it('caps a satisfied action when the action verb is absent', async () => {
    const proposer = createMicroTaskProposer({
      scoring: (rows) => rows.map(() => ({ label: 'satisfied' as const, confidence: 0.99 })),
    });
    const first = await proposer({ state: state(), facts: [{ id: 'f1', memberId: 'hero', text: '路明非拿起手电。' }] });
    expect(first?.pending.find((row) => row.taskId === 'task_hero_key')).toMatchObject({ matched: 1, total: 3 });
    expect(first?.updates.find((row) => row.label !== 'satisfied')).toMatchObject({ taskId: 'task_hero_key', label: 'attempt' });

    const second = await proposer({ state: state(), facts: [{ id: 'f2', memberId: 'hero', text: '路明非打开手电。' }] });
    expect(second?.pending.find((row) => row.taskId === 'task_hero_key')).toMatchObject({ matched: 2, total: 3 });

    const third = await proposer({ state: state(), facts: [{ id: 'f3', memberId: 'hero', text: '路明非确认电量。' }] });
    expect(third?.supports).toEqual([expect.objectContaining({ taskId: 'task_hero_key' })]);
  });

  it('caps a confirmation that names no entity of the task', async () => {
    const world = state();
    const choice = { id: 'task_hero_choice', ownerId: 'hero', parentTaskId: null, goal: '作出选择并确认', status: 'pending' as const };
    world.characters.hero.tasks.task_hero_choice = { ...choice };
    world.initial.characters.hero.tasks.task_hero_choice = { ...choice };
    const proposer = createMicroTaskProposer({
      scoring: (rows) => rows.map(() => ({ label: 'satisfied' as const, confidence: 0.99 })),
    });
    const result = await proposer({ state: world, facts: [{ id: 'f1', memberId: 'hero', text: '路明非检查电量。' }] });
    expect(result?.supports).toEqual([]);
    expect(result?.pending.find((row) => row.taskId === 'task_hero_choice')).toMatchObject({ matched: 0, total: 2 });
    expect(result?.updates.find((row) => row.taskId === 'task_hero_choice')?.label).toBe('keyword');
  });

  it('restores the cross-turn ledger from a snapshot and dedupes facts', async () => {
    const first = createMicroTaskProposer({ scoring });
    await first({ state: state(), facts: [{ id: 'f1', memberId: 'hero', text: '路明非拿起手电。' }] });
    await first({ state: state(), facts: [{ id: 'f2', memberId: 'hero', text: '路明非打开手电。' }] });
    const snapshot = first.exportLedger();
    expect(snapshot?.entries.find((entry) => entry.taskId === 'task_hero_key')?.status).toMatchObject({ c1: 'satisfied', c3: 'satisfied' });
    expect(snapshot?.seenFacts).toContain('hero:路明非拿起手电。');

    const second = createMicroTaskProposer({ scoring });
    second.importLedger(snapshot);
    const third = await second({
      state: state(),
      facts: [
        { id: 'f1', memberId: 'hero', text: '路明非拿起手电。' },
        { id: 'f2', memberId: 'hero', text: '路明非打开手电。' },
        { id: 'f3', memberId: 'hero', text: '路明非确认电量。' },
      ],
    });
    expect(third?.supports).toEqual([expect.objectContaining({ characterId: 'hero', taskId: 'task_hero_key' })]);
  });

  it('invalidates a satisfied item condition when the item leaves the owner', async () => {
    const world = state();
    const proposer = createMicroTaskProposer({ scoring });
    const facts = [
      { id: 'f1', memberId: 'hero', text: '路明非拿起手电。' },
      { id: 'f2', memberId: 'hero', text: '路明非打开手电。' },
      { id: 'f3', memberId: 'hero', text: '路明非确认电量。' },
    ];
    await proposer({ state: world, facts });
    world.items.torch.position.containerId = 'ally';
    const after = await proposer({ state: world, facts: [] });
    expect(after?.supports).toEqual([]);
    const pending = after?.pending.find((row) => row.taskId === 'task_hero_key');
    expect(pending).toMatchObject({ matched: 2, total: 3 });
    expect(pending?.missing.join('')).toContain('已失效');

    world.items.torch.position.containerId = 'hero';
    const again = await proposer({ state: world, facts: [] });
    expect(again?.supports).toEqual([expect.objectContaining({ taskId: 'task_hero_key' })]);
  });

  it('credits another character\'s answer to the task owner', async () => {
    const world = state();
    const ask = { id: 'task_hero_ask', ownerId: 'hero', parentTaskId: null, goal: '向阿宁问清门后有没有人', status: 'pending' as const };
    world.characters.hero.tasks.task_hero_ask = { ...ask };
    world.initial.characters.hero.tasks.task_hero_ask = { ...ask };
    const proposer = createMicroTaskProposer({
      scoring: (rows) => rows.map((row) => {
        if (row.condition.kind === 'target') return { label: row.text.includes('阿宁') ? 'satisfied' as const : 'none' as const, confidence: 0.95 };
        if (row.condition.kind === 'confirmation') return { label: row.text.includes('回答') ? 'satisfied' as const : 'none' as const, confidence: 0.95 };
        return { label: 'none' as const, confidence: 0.95 };
      }),
    });
    const asked = await proposer({ state: world, facts: [{ id: 'f1', memberId: 'hero', text: '路明非问阿宁门后有没有人。' }] });
    expect(asked?.pending.find((row) => row.taskId === 'task_hero_ask')).toMatchObject({ matched: 1, total: 2 });
    expect(asked?.supports).toEqual([]);

    const answered = await proposer({ state: world, facts: [{ id: 'f2', memberId: 'ally', text: '阿宁回答路明非，门后没有人。' }] });
    expect(answered?.supports).toEqual([expect.objectContaining({ characterId: 'hero', taskId: 'task_hero_ask' })]);
  });

  it('does not treat a negated answer as a confirmation', async () => {
    const world = state();
    const ask = { id: 'task_hero_ask', ownerId: 'hero', parentTaskId: null, goal: '向阿宁问清门后有没有人', status: 'pending' as const };
    world.characters.hero.tasks.task_hero_ask = { ...ask };
    world.initial.characters.hero.tasks.task_hero_ask = { ...ask };
    const proposer = createMicroTaskProposer({
      scoring: (rows) => rows.map(() => ({ label: 'satisfied' as const, confidence: 0.99 })),
    });
    await proposer({ state: world, facts: [{ id: 'f1', memberId: 'hero', text: '路明非问阿宁门后有没有人。' }] });
    const answer = await proposer({ state: world, facts: [{ id: 'f2', memberId: 'ally', text: '阿宁没有回答路明非。' }] });
    expect(answer?.supports).toEqual([]);
  });

  it('does not count keyword or attempt as a satisfied condition', async () => {
    const proposer = createMicroTaskProposer({
      scoring: (rows) => rows.map(() => ({ label: 'keyword' as const, confidence: 0.9 })),
    });
    const result = await proposer({ state: state(), facts: [{ id: 'f1', memberId: 'hero', text: '手电挂在墙上。' }] });
    expect(result?.supports).toEqual([]);
    expect(result?.pending[0]?.matched).toBe(0);
  });
});
