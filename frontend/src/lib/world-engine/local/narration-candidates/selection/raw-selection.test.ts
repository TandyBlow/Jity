import { describe, expect, it } from 'vitest';
import { tinyWorld, applyDelta } from '../../narration-input/test-fixtures';
import { createNarrationRunner } from './runner';
import type { NarrationCandidate, NarrationPoint } from './types';
import type { TimeAdvance } from '../../../types';

const TIME: TimeAdvance = { boundary: 'elapsed', duration: { amount: 3, unit: 'minute' } };

function point(priorText?: string): NarrationPoint {
  const before = tinyWorld();
  const delta = { hero: { entityId: 'hero', positionSet: { containerId: 'cellar', slotId: null, relativeTo: null } } };
  const after = applyDelta(before, delta, TIME);
  return { pointId: 'p_1', before, delta: { timeAdvance: TIME, entityDeltas: delta }, after, playerInput: '我下到地窖。' };
}

function candidate(answer: string, calls: { count: number }, status: 'accepted' | 'empty' = 'accepted'): NarrationCandidate {
  return {
    id: 'trained', route: 'trained', version: 'raw-v1', label: 'raw',
    requires: { modules: [], template: 'none' }, productDefault: true,
    availability: () => ({ available: true, reason: null }),
    async run() {
      calls.count += 1;
      return {
        candidateId: 'trained', route: 'trained', text: answer, status,
        attempts: 1, promptChars: 10,
        timings: { totalMs: 5, attemptMs: [5], firstTokenMs: 1 },
        strategyVersion: 'raw',
      };
    },
  };
}

const engine = {
  info: { backend: 'test', modelId: 'fake' },
  load: async () => undefined,
  dispose: async () => undefined,
  complete: async () => '',
};

describe('selection returns the model text unchanged', () => {
  it('adopts non-empty text with its display segments', async () => {
    const calls = { count: 0 };
    const runner = createNarrationRunner({ engine: engine as never, candidate: 'trained', candidates: [candidate('阿青提着铜灯往下走。', calls)] });
    const result = await runner.generate(point());
    expect(result.kind).toBe('adopted');
    if (result.kind !== 'adopted') return;
    expect(result.text).toBe('阿青提着铜灯往下走。');
    expect(result.segments).toEqual([{ id: 'scene', kind: 'scene', source: 'model', text: '阿青提着铜灯往下走。' }]);
  });

  it('does not trim or rewrite an awkward sentence', async () => {
    const awkward = '  阿青摔了。铜灯也摔了！！  ';
    const runner = createNarrationRunner({ engine: engine as never, candidate: 'trained', candidates: [candidate(awkward, { count: 0 })] });
    const result = await runner.generate(point());
    expect(result.kind).toBe('adopted');
    if (result.kind === 'adopted') expect(result.text).toBe(awkward);
  });

  it('reports an empty answer as empty, not as a fallback story', async () => {
    const runner = createNarrationRunner({ engine: engine as never, candidate: 'trained', candidates: [candidate('   ', { count: 0 }, 'empty')] });
    const result = await runner.generate(point());
    expect(result.kind).toBe('empty');
  });

  it('reports an unavailable candidate without a second writer', async () => {
    const unavailable: NarrationCandidate = {
      ...candidate('x', { count: 0 }),
      availability: () => ({ available: false, reason: 'root_point' }),
    };
    const runner = createNarrationRunner({ engine: engine as never, candidate: 'trained', candidates: [unavailable] });
    const result = await runner.generate(point());
    expect(result.kind).toBe('empty');
    if (result.kind === 'empty') expect(result.reason).toContain('unavailable');
  });
});
