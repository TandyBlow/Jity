import { describe, expect, it } from 'vitest';
import { generateCommittedNarration } from './index';
import type { InferenceEngine } from '../../runtime/engine';

/** Scene and beat narration return the model's own text
 * (NARRATION-RAW-OUTPUT-20261111). These tests fix the answer and assert it is
 * identical in the result, with no second call and no repair. */
const committed = {
  anchor: { worldId: 'w', pointId: 'p', version: 1, stateDigest: 'd', previousPointId: 'root' },
  facts: [
    { id: 'f1', kind: 'at' as const, actorId: 'hero', name: '阿青', locationId: 'cellar', location: '地窖' },
  ],
};

function engine(answer: string, calls: { count: number }): InferenceEngine {
  return {
    info: { backend: 'test', modelId: 'fixed' },
    load: async () => undefined,
    dispose: async () => undefined,
    async complete() { calls.count += 1; return answer; },
  };
}

describe('narration-generation raw scene', () => {
  it.each([
    ['short', '他站着。'],
    ['no punctuation', '阿青提着铜灯沿石阶往下走'],
    ['repeated', '阿青提着铜灯。阿青提着铜灯。'],
    ['unknown name', '阿青看见西门开了。'],
  ])('%s answer is returned unchanged', async (_label, answer) => {
    const calls = { count: 0 };
    const result = await generateCommittedNarration({
      engine: engine(answer, calls), committed, inputText: '阿青在地窖。',
      policy: { mode: 'scene', minChars: 20 },
    });
    expect(calls.count).toBe(1);
    expect(result.text).toBe(answer);
    expect(result.status).toBe('accepted');
  });

  it('whitespace-only is empty, with exactly one call', async () => {
    const calls = { count: 0 };
    const result = await generateCommittedNarration({
      engine: engine(' \n ', calls), committed, inputText: '阿青在地窖。',
      policy: { mode: 'scene' },
    });
    expect(calls.count).toBe(1);
    expect(result.text.trim()).toBe('');
    expect(result.status).toBe('empty');
  });
});
