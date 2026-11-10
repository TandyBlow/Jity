import { afterEach, describe, expect, it } from 'vitest';
import type { EntityDelta, TimeAdvance } from '../../../types';
import type { InferenceEngine } from '../../../runtime/engine';
import { applyDelta, tinyWorld } from '../../narration-input/test-fixtures';
import { TRAINED_CANDIDATE } from './trained';
import { createNarrationRunner, SHIPPED_CANDIDATES } from './runner';
import { CONSTRAINED_CANDIDATE } from './constrained';
import { prepareNarration } from './projection';
import type { NarrationCandidate, NarrationPoint } from './types';

const TIME: TimeAdvance = { boundary: 'elapsed', duration: { amount: 3, unit: 'minute' } };

function settledPoint(): NarrationPoint {
  const before = tinyWorld();
  const delta: Record<string, EntityDelta> = {
    hero: {
      entityId: 'hero',
      positionSet: { containerId: 'cellar', slotId: null, relativeTo: null },
      personalityChanges: [{ id: 'change_1', text: '比刚才更警惕了', supersedes: [] }],
      sanitySet: 46,
    },
    friend: { entityId: 'friend', tasksAchieved: ['friend_root'] },
  };
  const after = applyDelta(before, delta, TIME);
  return {
    pointId: 'p_1',
    before,
    delta: { timeAdvance: TIME, entityDeltas: delta },
    after,
    playerInput: '我跟着阿白下到地窖，顺手提上铜灯。',
    priorText: null,
  };
}

function fakeEngine(answer = '阿青提着铜灯沿石阶往下走。', onCall?: () => void): InferenceEngine {
  return {
    info: { backend: 'test', modelId: 'fake' },
    load: async () => undefined,
    complete: async () => {
      onCall?.();
      return answer;
    },
    dispose: async () => undefined,
  };
}

function fakeCandidate(overrides: Partial<NarrationCandidate> & Pick<NarrationCandidate, 'run'>): NarrationCandidate {
  return {
    id: 'trained',
    route: 'trained',
    version: 'fake-v1',
    label: 'fake',
    requires: { modules: [], template: 'none' },
    productDefault: true,
    availability: () => ({ available: true, reason: null }),
    ...overrides,
  };
}

afterEach(() => {
  delete (globalThis as { __jityNarrationCandidate?: unknown }).__jityNarrationCandidate;
});

describe('narration projection of a settled point', () => {
  it('copies movement, task, personality, sanity and time from the sealed records', () => {
    const prepared = prepareNarration(settledPoint());
    const kinds = prepared.facts.facts.map((fact) => `${fact.kind}:${fact.id}`);
    expect(kinds).toContain('moved:hero:position');
    expect(kinds).toContain('task_achieved:friend:task:friend_root');
    expect(kinds).toContain('personality_changed:hero:change:change_1');
    expect(kinds).toContain('sanity_changed:hero:sanity');
    const moved = prepared.facts.facts.find((fact) => fact.kind === 'moved');
    expect(moved && moved.kind === 'moved' ? [moved.from, moved.to] : null).toEqual(['大厅', '地窖']);
    const task = prepared.facts.facts.find((fact) => fact.kind === 'task_achieved');
    expect(task && task.kind === 'task_achieved' ? task.goal : null).toBe('守住大厅的门');
    expect(prepared.mandatoryFactIds.sort()).toEqual([
      'friend:task:friend_root', 'hero:change:change_1', 'hero:position', 'hero:sanity',
    ]);
  });

  it('serializes the point with the lane-01 result renderer, not a local state dump', () => {
    const prepared = prepareNarration(settledPoint());
    expect(prepared.inputError).toBeNull();
    expect(prepared.inputText).toBeTruthy();
    expect(prepared.inputText).toContain('【正文】');
    expect(prepared.inputText).toContain('地窖');
    expect(prepared.inputText).toContain('找到父亲留下的箱子');
  });

  it('builds licensing and scene material from the after-state', () => {
    const prepared = prepareNarration(settledPoint());
    expect(prepared.viewpointName).toBe('阿青');
    expect(prepared.policy.roster).toEqual(expect.arrayContaining(['阿青', '阿白', '阿灰']));
    expect(prepared.policy.requireTime).toBe(true);
    expect(prepared.policy.time).toEqual(TIME);
    expect(prepared.scene.location).toBe('地窖');
    expect(prepared.scene.previousAction).toBe('我跟着阿白下到地窖，顺手提上铜灯。');
    // A visible room item and a carried item are licensed; the cellar box is not
    // visible from the room the viewpoint just entered? It is: the box lives there.
    expect(prepared.policy.visibleEntities).toEqual(expect.arrayContaining(['木箱', '纸条']));
    expect(prepared.policy.visibleEntities).not.toContain('旧照片');
  });

  it('reports a missing input instead of inventing one when there is no before-state', () => {
    const point = settledPoint();
    const prepared = prepareNarration({ ...point, before: null });
    expect(prepared.inputText).toBeNull();
    expect(prepared.inputError).toBe('no_before_state');
    expect(prepared.facts.facts.some((fact) => fact.kind === 'moved')).toBe(false);
  });
});

describe('selection policy', () => {
  it('stays on the in-model writer when no candidate marks itself product-default', async () => {
    let calls = 0;
    const runner = createNarrationRunner({ engine: fakeEngine(undefined, () => { calls += 1; }), candidate: 'auto' });
    const result = await runner.generate(settledPoint());
    expect(result).toMatchObject({ kind: 'fallback', reason: 'no_product_candidate' });
    expect(calls).toBe(0);
    // Program/ledger prose is a debug downgrade, never the product's narrator.
    expect(SHIPPED_CANDIDATES.filter((candidate) => candidate.productDefault)).toEqual([]);
  });

  it('honours the internal QA override without letting it leak into the page', () => {
    (globalThis as { __jityNarrationCandidate?: unknown }).__jityNarrationCandidate = 'trained';
    const runner = createNarrationRunner({ engine: fakeEngine(), candidate: 'builtin' });
    expect(runner.selection.requested).toBe('trained');
    expect(runner.selection.productDefault).toBeNull();
  });

  it('adopts verified candidate prose and forwards its real increments', async () => {
    const progress: string[] = [];
    const runner = createNarrationRunner({
      engine: fakeEngine(),
      candidate: 'trained',
      candidates: [fakeCandidate({
        run: async ({ onProgress }) => {
          onProgress?.({ text: '阿青提着', elapsedMs: 10, verified: false, attempt: 0 });
          onProgress?.({ text: '阿青提着铜灯沿石阶往下走。', elapsedMs: 20, verified: false, attempt: 0 });
          return {
            candidateId: 'trained', route: 'trained', text: '阿青提着铜灯沿石阶往下走。', accepted: true,
            grade: 'candidate', status: 'accepted', reason: null, issues: [], attempts: 1, promptChars: 120,
            timings: { totalMs: 30, attemptMs: [30], firstTokenMs: 10 },
            strategyVersion: 'fake-v1', allFellBack: false,
          };
        },
      })],
    });
    const result = await runner.generate(settledPoint(), (state) => progress.push(state.text));
    expect(result).toMatchObject({
      kind: 'adopted', candidateId: 'trained', text: '阿青提着铜灯沿石阶往下走。', grade: 'candidate',
    });
    expect(progress).toEqual(['阿青提着', '阿青提着铜灯沿石阶往下走。']);
  });

  it('never adopts a rejected draft and keeps the reason for the fallback record', async () => {
    const runner = createNarrationRunner({
      engine: fakeEngine(),
      candidates: [fakeCandidate({
        run: async () => ({
          candidateId: 'trained', route: 'trained', text: '阿青连人带灯摔进了雕像里。', accepted: false,
          grade: 'candidate_unverified', status: 'rejected', reason: 'rejected:added_event', issues: [{ kind: 'added_event', severity: 'hard' }],
          attempts: 2, promptChars: 240, timings: { totalMs: 60, attemptMs: [30, 30], firstTokenMs: 8 },
          strategyVersion: 'fake-v1', allFellBack: false,
        }),
      })],
      candidate: 'trained',
    });
    const result = await runner.generate(settledPoint());
    expect(result.kind).toBe('fallback');
    if (result.kind === 'fallback') {
      expect(result.reason).toContain('rejected:trained');
      expect(result.reason).toContain('added_event');
      expect(result.grade).toBe('program_fallback');
      expect(result.notice).toBeNull();
    }
  });

  it('survives a candidate that throws and records the error', async () => {
    const runner = createNarrationRunner({
      engine: fakeEngine(),
      candidates: [fakeCandidate({ run: async () => { throw new Error('boom'); } })],
      candidate: 'trained',
    });
    const result = await runner.generate(settledPoint());
    expect(result).toMatchObject({ kind: 'fallback' });
    if (result.kind === 'fallback') expect(result.reason).toContain('error:trained|Error:boom');
  });

  it('skips the shipped candidate when the serialized input is unavailable', async () => {
    const runner = createNarrationRunner({ engine: fakeEngine(), candidates: [TRAINED_CANDIDATE], candidate: 'trained' });
    const point = { ...settledPoint(), before: null };
    const result = await runner.generate(point);
    expect(result.kind).toBe('fallback');
    if (result.kind === 'fallback') expect(result.reason).toContain('unavailable:trained|input_unavailable:no_before_state');
  });

  it('runs the shipped beats candidate against a real engine contract and reports rejection honestly', async () => {
    const runner = createNarrationRunner({
      engine: fakeEngine('阿青提着铜灯沿石阶往下走，石阶上落着灰，阿白在下面等他。'),
      candidates: [TRAINED_CANDIDATE],
      candidate: 'trained',
      minChars: 40,
      maxTokens: 60,
      deadlineMs: 15_000,
    });
    const result = await runner.generate(settledPoint());
    expect(result.kind).toBe('fallback');
    if (result.kind === 'fallback') {
      expect(result.reason).toContain('trained');
      // The strategy may accept or reject this fixture; what must hold is that a
      // rejection is reported as a fallback and never as adopted text.
      if (result.reason.startsWith('rejected:trained')) expect(result.reason).toMatch(/rejected:trained\|/);
    }
  });
});

describe('constrained (C route) candidate', () => {
  const point = (): NarrationPoint => ({
    pointId: 'p_c',
    before: tinyWorld(),
    delta: {
      timeAdvance: TIME,
      entityDeltas: {
        hero: { entityId: 'hero', positionSet: { containerId: 'cellar', slotId: null, relativeTo: null } },
        friend: { entityId: 'friend', tasksAchieved: ['friend_root'] },
      },
    },
    after: applyDelta(tinyWorld(), {
      hero: { entityId: 'hero', positionSet: { containerId: 'cellar', slotId: null, relativeTo: null } },
      friend: { entityId: 'friend', tasksAchieved: ['friend_root'] },
    }, TIME),
    playerInput: '我去地窖找那只箱子。',
  });

  it('accepts program-realized prose and marks it as a downgrade, not model prose', async () => {
    const runner = createNarrationRunner({ engine: fakeEngine(), candidate: 'constrained', minChars: 20 });
    const result = await runner.generate(point());
    expect(result.kind).toBe('adopted');
    if (result.kind === 'adopted') {
      expect(result.candidateId).toBe('constrained');
      expect(result.grade).toBe('program');
      expect(result.text.length).toBeGreaterThan(0);
      expect(result.text).toContain('地窖');
      // The product route uses lane 07's composer, not 04's flat realizer.
      expect(String(result.detail?.composers ?? '')).toContain('prose-composer');
    }
  });

  it('declares itself unavailable for the world-opening point', () => {
    const prepared = prepareNarration(point());
    expect(CONSTRAINED_CANDIDATE.availability({ ...point(), before: null }, prepared)).toEqual({
      available: false, reason: 'root_point',
    });
  });

  it('declares itself unavailable when the packet carries no scene fact', () => {
    const prepared = prepareNarration(point());
    const withoutScene = { ...prepared, facts: { ...prepared.facts, facts: [] } };
    expect(CONSTRAINED_CANDIDATE.availability(point(), withoutScene)).toEqual({
      available: false, reason: 'facts_packet_without_scene',
    });
  });
});
