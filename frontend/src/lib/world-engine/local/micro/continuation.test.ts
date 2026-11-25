import { describe, expect, it } from 'vitest';
import type { WorldState } from '../../types';
import type { MicroContinuationScores } from '../semantics/settlement/types';
import { createMicroContinuation } from './continuation';

function state(): WorldState {
  const initial = {
    engineVersion: 'world-engine-v1' as const,
    schemaVersion: 1 as const,
    protagonistId: 'lu',
    initialTime: { calendar: 'gregorian' as const, dateTime: '2026-11-25T10:00:00', instantOrdinal: 0 },
    locations: {
      yard: { id: 'yard', name: '中央庭院', parentLocationId: null, initialAppearance: '' },
      lane: { id: 'lane', name: '西侧服务巷', parentLocationId: null, initialAppearance: '' },
    },
    items: {},
    characters: {
      lu: {
        id: 'lu', name: '路明非', initialPosition: { containerId: 'lane' }, initialAppearance: '',
        initialPersonality: '谨慎', initialSanity: 50,
        tasks: { task_lu: { id: 'task_lu', ownerId: 'lu', parentTaskId: null, goal: '确认地图', status: 'pending' as const } },
      },
      tang: {
        id: 'tang', name: '唐骁', initialPosition: { containerId: 'lane' }, initialAppearance: '',
        initialPersonality: '果断', initialSanity: 50,
        tasks: { task_tang: { id: 'task_tang', ownerId: 'tang', parentTaskId: null, goal: '前往中央庭院守住旗台', status: 'pending' as const } },
      },
    },
  };
  const characters = Object.fromEntries(Object.entries(initial.characters).map(([id, row]) => [id, {
    id, appearanceChanges: [], position: { ...row.initialPosition }, personalityChanges: [], sanity: row.initialSanity,
    tasks: structuredClone(row.tasks),
  }]));
  return {
    engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'w', protagonistId: 'lu',
    time: { calendar: 'gregorian', dateTime: '2026-11-25T10:00:00', instantOrdinal: 0 }, initial: { ...initial, worldId: 'w' },
    locations: {
      yard: { id: 'yard', appearanceChanges: [] },
      lane: { id: 'lane', appearanceChanges: [] },
    },
    items: {},
    characters,
  } as WorldState;
}

const HIGH = (row: { text: string }): MicroContinuationScores => (
  row.text.includes('走向中央庭院') ? { novelty: 0.9, unfinished: 0.9, necessity: 0.9, intervene: 0.1 }
    : row.text.includes('求助') ? { novelty: 0.9, unfinished: 0.9, necessity: 0.9, intervene: 0.1 }
      : { novelty: 0.1, unfinished: 0.1, necessity: 0.1, intervene: 0.1 });

const progress = {
  progress: true, reason: 'state_changed' as const, stateChanged: true, timeAdvanced: false,
  newActionCount: 0, newSettledFactCount: 0, worldDigest: 'd1',
};

describe('micro continuation', () => {
  it('continues with the character whose event passes all four heads', async () => {
    const stats: unknown[] = [];
    const port = createMicroContinuation({
      scoring: (rows) => rows.map(HIGH),
      maxCandidatesPerCharacter: 8,
      onStats: (record) => stats.push(record),
    });
    const answer = await port({
      roundId: 'round_1', trigger: 'player', state: state(), roundChanges: [],
      roundProgress: progress, history: [],
    });
    expect(answer?.decision).toBe('continue');
    expect(answer?.accepted.map((row) => row.characterId)).toEqual(['tang']);
    expect(answer?.accepted[0].text).toContain('走向中央庭院');
    expect(answer?.candidates.length).toBeGreaterThan(0);
    expect(stats).toHaveLength(1);
    // Wait rows are scored (an encoder run each) and then rejected, so the
    // inference count can exceed the evidence candidate list.
    const inferences = (stats[0] as { inferences: number }).inferences;
    expect(inferences).toBeGreaterThanOrEqual(answer?.candidates.length ?? 0);
    expect((stats[0] as { headOutputs: number }).headOutputs).toBe(inferences * 4);
  });

  it('rejects an exact repeat under an unchanged world before scoring', async () => {
    const port = createMicroContinuation({
      scoring: (rows) => rows.map(HIGH),
      maxCandidatesPerCharacter: 8,
    });
    const answer = await port({
      roundId: 'round_2', trigger: 'automatic', state: state(), roundChanges: [],
      roundProgress: progress,
      history: [{ characterId: 'tang', text: '唐骁走向中央庭院。', worldDigest: 'd1' }],
    });
    expect(answer?.candidates.some((row) => row.text === '唐骁走向中央庭院。')).toBe(false);
    expect(answer?.rejected.some((row) => row.reason === 'repeat_no_new_event')).toBe(true);
  });

  it('hands back when the only necessary follow-up targets the protagonist', async () => {
    const port = createMicroContinuation({
      scoring: (rows) => rows.map((row) => (
        row.text.includes('求助')
          ? { novelty: 0.9, unfinished: 0.9, necessity: 0.9, intervene: 0.1 }
          : { novelty: 0.1, unfinished: 0.1, necessity: 0.1, intervene: 0.1 }
      )),
      maxCandidatesPerCharacter: 8,
    });
    const answer = await port({
      roundId: 'round_3', trigger: 'player', state: state(), roundChanges: [],
      roundProgress: progress, history: [],
    });
    expect(answer?.decision).toBe('handback');
    expect(answer?.reason).toBe('player_intervention');
  });

  it('returns null when the scorer is unavailable', async () => {
    const port = createMicroContinuation({ scoring: () => null, maxCandidatesPerCharacter: 8 });
    const answer = await port({
      roundId: 'round_4', trigger: 'player', state: state(), roundChanges: [],
      roundProgress: progress, history: [],
    });
    expect(answer).toBeNull();
  });
});
