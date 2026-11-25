import { describe, expect, it } from 'vitest';
import type { InferenceEngine } from '../../runtime/engine';
import { buildTestWorld } from '../semantics/actions/fixtures';
import { verifyTaskAchievements } from '../semantics/settlement/task-verifier';
import { createMicroTaskVerifier, decomposeTask, outcomeGate } from './task-progress';

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
    expect(outcomeGate('路明非找到钥匙（达到目的）。')).toBe('yes');
    expect(outcomeGate('路明非只找到一半（只完成一部分）。')).toBe('partial');
    expect(outcomeGate('路明非没有找到钥匙（没有成功）。')).toBe('no');
    expect(outcomeGate('路明非找到钥匙。')).toBeNull();
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
