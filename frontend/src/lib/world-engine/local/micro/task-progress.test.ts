import { describe, expect, it } from 'vitest';
import type { InferenceEngine } from '../../runtime/engine';
import { buildTestWorld } from '../semantics/actions/fixtures';
import { verifyTaskAchievements } from '../semantics/settlement/task-verifier';
import { conditionCoverage, createMicroTaskVerifier, decomposeTask, outcomeGate } from './task-progress';

function support(goal = '找到后门的钥匙') {
  return { characterId: 'hero', taskId: 'task_hero_key', goal, ownerName: '路明非', factText: '路明非找到后门的钥匙。' };
}

describe('task-progress micro workflow', () => {
  it('decomposes a goal into named conditions', () => {
    const conditions = decomposeTask('在15:45停赛前让红方取得可确认的旗台控制权', buildTestWorld(), '凯撒');
    expect(conditions.time).toBe('15:45');
    expect(conditions.confirmation).toBe('确认');
    expect(conditions.conditions.length).toBeGreaterThanOrEqual(2);
  });

  it('uses explicit outcome wording as a deterministic gate', () => {
    expect(outcomeGate('路明非找到钥匙（达到目的）。')).toBeNull();
    expect(outcomeGate('路明非只找到一半（只完成一部分）。')).toBe('partial');
    expect(outcomeGate('路明非没有找到钥匙（没有成功）。')).toBe('no');
    expect(outcomeGate('路明非找到钥匙。')).toBeNull();
  });

  it('downgrades a yes when the fact only covers one named condition', async () => {
    const port = createMicroTaskVerifier({
      scoring: () => [{ relevance: 0.9, satisfaction: [0.9, 0.05, 0.05] }],
    });
    const verdicts = await port({
      supports: [{
        characterId: 'hero', taskId: 'task_hero_key', goal: '把手电打开并确认电量',
        ownerName: '路明非', factText: '路明非打开手电。',
      }],
      state: buildTestWorld(),
    });
    expect(verdicts?.[0]).toMatchObject({ satisfied: 'partial' });
    expect(verdicts?.[0].reason).toContain('条件');
  });

  it('trusts the proposer condition labels over lexical overlap', async () => {
    const port = createMicroTaskVerifier({
      scoring: () => [{ relevance: 0.9, satisfaction: [0.9, 0.05, 0.05] }],
    });
    const verdicts = await port({
      supports: [{
        characterId: 'hero', taskId: 'task_hero_key', goal: '把手电打开并确认电量',
        ownerName: '路明非', factText: '路明非按了一下开关。',
        conditions: [
          { label: 'item：手电', state: 'satisfied' },
          { label: 'action：打开', state: 'satisfied' },
          { label: 'confirmation：确认', state: 'satisfied' },
        ],
      }],
      state: buildTestWorld(),
    });
    expect(verdicts?.[0]).toMatchObject({ satisfied: 'yes' });
  });

  it('covers the conditions named by a goal', () => {
    const state = buildTestWorld();
    const conditions = decomposeTask('把手电打开并确认电量', state, '路明非');
    expect(conditionCoverage(conditions, '路明非打开手电并按了一下开关确认电量。').matched)
      .toBe(conditionCoverage(conditions, '路明非打开手电并按了一下开关确认电量。').total);
    expect(conditionCoverage(conditions, '路明非打开手电。').matched).toBeLessThan(
      conditionCoverage(conditions, '路明非打开手电。').total,
    );
  });

  it('returns task verdicts from the pair scores', async () => {
    const port = createMicroTaskVerifier({
      scoring: (rows) => rows.map(() => ({ relevance: 0.9, satisfaction: [0.05, 0.05, 0.9] })),
    });
    const verdicts = await port({ supports: [support()], state: buildTestWorld() });
    expect(verdicts).toEqual([expect.objectContaining({ taskId: 'task_hero_key', satisfied: 'no', confidence: 0.9 })]);
  });

  it('abstains on low relevance instead of rejecting the achievement', async () => {
    const port = createMicroTaskVerifier({
      scoring: () => [{ relevance: 0.2, satisfaction: [0.9, 0.05, 0.05] }],
    });
    expect(await port({ supports: [support()], state: buildTestWorld() })).toBeNull();
  });

  it('shows cross-turn basis text to the LLM verifier', async () => {
    let prompt = '';
    const engine: InferenceEngine = {
      info: { backend: 'scripted', modelId: 'task-progress-test' },
      load: async () => undefined,
      dispose: async () => undefined,
      complete: async (text) => {
        prompt = text;
        return '{"judgments":[{"characterId":"hero","taskId":"task_hero_key","satisfied":"yes","reason":"跨回合满足"}]}';
      },
    };
    let calls = 0;
    const engineWithCount: InferenceEngine = {
      ...engine,
      complete: async (text) => {
        calls += 1;
        prompt = text;
        return '{"judgments":[{"characterId":"hero","taskId":"task_hero_key","satisfied":"yes","reason":"跨回合满足"}]}';
      },
    };
    const request = {
      engine: engineWithCount,
      state: buildTestWorld(),
      results: {},
      options: {},
    };
    const supports = [{ characterId: 'hero', taskId: 'task_hero_key', basis: 'cross_turn', basisText: '路明非打开手电；路明非确认电量。' }];
    const result = await verifyTaskAchievements(request, supports);
    expect(prompt).toContain('路明非打开手电；路明非确认电量。');
    expect(result.judgments[0]).toMatchObject({ satisfied: 'yes' });

    const cached = await verifyTaskAchievements(request, supports);
    expect(calls).toBe(1);
    expect(cached.cached).toBe(true);
    expect(cached.calls).toHaveLength(0);
    expect(cached.judgments).toEqual(result.judgments);
  });

  it('lets the micro verdict replace the LLM verifier call', async () => {
    const engine: InferenceEngine = {
      info: { backend: 'scripted', modelId: 'task-progress-test' },
      load: async () => undefined,
      dispose: async () => undefined,
      complete: async () => { throw new Error('LLM verifier must not run'); },
    };
    const result = await verifyTaskAchievements({
      engine,
      state: buildTestWorld(),
      results: { hero: '路明非找到后门的钥匙。' },
      options: {
        microTaskVerifier: () => [{
          characterId: 'hero', taskId: 'task_hero_key', satisfied: 'yes', confidence: 0.9, reason: '事实满足条件',
        }],
      },
    }, [{ characterId: 'hero', taskId: 'task_hero_key', basis: 'f1' }]);
    expect(result.calls).toHaveLength(0);
    expect(result.judgments).toEqual([expect.objectContaining({ taskId: 'task_hero_key', satisfied: 'yes' })]);
  });
});
