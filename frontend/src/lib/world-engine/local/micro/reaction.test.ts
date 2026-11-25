import { describe, expect, it } from 'vitest';
import { buildScene } from '../semantics/actions/scene';
import { buildTestWorld } from '../semantics/actions/fixtures';
import { createMicroReaction, reactionCandidates, reactionTrigger } from './reaction';

function request() {
  const state = buildTestWorld();
  const scene = buildScene(state, 'ally');
  const source = scene.visible.find((character) => character.id === 'hero');
  if (!source) throw new Error('hero not visible');
  return { state, scene, source, sourceActionText: '路明非把木箱推到门边挡住门口。' };
}

describe('reaction micro workflow', () => {
  it('classifies the trigger before choosing an intent', () => {
    expect(reactionTrigger('我把护目镜递给诺诺。')).toBe('offer');
    expect(reactionTrigger('路明非把木门推开，问阿宁还能不能走。')).toBe('question');
    expect(reactionTrigger('路明非把木箱推到门边挡住门口。')).toBe('threat');
    expect(reactionTrigger('阿宁走向门口。')).toBe('move');
    expect(reactionTrigger('阿宁站着没动。')).toBe('other');
    expect(reactionCandidates(request().scene, request().source, 'threat').map((row) => row.intent))
      .toEqual(['avoid', 'guard', 'observe']);
  });

  it('selects the highest judge-scored rational intent', async () => {
    const stats: unknown[] = [];
    const port = createMicroReaction({
      judge: (pairs) => pairs.map((pair) => (
        pair.text.includes('护住要害')
          ? { task: 0.9, personality: 0.9, scene: 0.9 }
          : { task: 0.2, personality: 0.2, scene: 0.2 }
      )),
      onStats: (record) => stats.push(record),
    });
    const text = await port(request());
    expect(text).toContain('护住要害');
    expect(stats[0]).toMatchObject({ source: 'micro', pairs: 3, inferences: 0, headOutputs: 0 });
  });

  it('includes the trigger and source in the judge context', async () => {
    let seen = '';
    const port = createMicroReaction({
      judge: (pairs) => {
        seen = pairs[0].context;
        return pairs.map(() => ({ task: 0.9, personality: 0.9, scene: 0.9 }));
      },
    });
    await port(request());
    expect(seen).toContain('触发行动');
    expect(seen).toContain('木箱');
    expect(seen).toContain('发起者：路明非');
  });

  it('abstains when the judges are not confident', async () => {
    const port = createMicroReaction({
      judge: (pairs) => pairs.map(() => ({ task: 0.2, personality: 0.2, scene: 0.2 })),
    });
    expect(await port(request())).toBeNull();
  });

  it('abstains without a judge port', async () => {
    const port = createMicroReaction({});
    expect(await port(request())).toBeNull();
  });
});
