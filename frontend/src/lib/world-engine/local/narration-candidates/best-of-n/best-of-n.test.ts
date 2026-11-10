import { describe, expect, it } from 'vitest';
import {
  buildDiversityReport, clusterProfiles, comparePair, effectiveRepetition, profileSample,
  textMetrics,
} from './diversity';
import { selectCandidate } from './select';
import { runCandidatePool } from './pool';
import type { CandidateAssessment, CandidateSample, SelectionCandidate } from './types';

const LICENSED = ['路明非', '诺诺', '器材棚', '巷口', '护目镜', '旧箱子', '庭院'];

const A = [
  '巷子里还留着雨后的水痕。',
  '路明非站在巷口，把护目镜推上去，确认镜片没有裂纹。',
  '诺诺在器材棚门口等他，手里拎着那只旧箱子。',
  '四分钟过去，两个人都没有动。',
].join('');

const B = [
  '巷子里的水痕还没有干。',
  '路明非停在巷口，将护目镜往上推，检查镜片是否有裂纹。',
  '诺诺在器材棚门前等着他，手上提着那只旧箱子。',
  '四分钟过去了，两个人都没有动。',
].join('');

const C = [
  '「镜片没事。」路明非把护目镜往上一推，先摸镜框，才抬头。',
  '器材棚的门半开着，诺诺靠在门边。',
  '她手里的旧箱子换了个姿势。',
  '巷口的积水映着灰天。',
  '四分钟里，谁也没往庭院走。',
].join('');

const D = [
  '天台的风把纸页吹得发响。',
  '黎含英从楼梯间出来，把门在身后带上。',
  '楼梯间墙上的刻字缺了半行。',
  '六分钟过去，她一直站在栏杆边。',
].join('');

function profile(id: string, text: string, seed = 0) {
  return profileSample({ id, seed, text, licensedEntities: LICENSED });
}

describe('realization diversity', () => {
  it('treats six identical drafts as one cluster and reports the preregistered formula', () => {
    const profiles = Array.from({ length: 6 }, (_, index) => profile(`s${index}`, A, index));
    const report = buildDiversityReport({ profiles });
    expect(report.clusters).toHaveLength(1);
    expect(report.effectiveRepetition).toBeCloseTo(1 - 1 / 6, 6);
    expect(report.pairs.every((pair) => pair.homogeneous)).toBe(true);
  });

  it('clusters a synonym rewrite with the same sentence rhythm as the same realization', () => {
    const first = profile('a', A, 1);
    const second = profile('b', B, 2);
    const pair = comparePair(first, second);
    expect(pair.homogeneous).toBe(true);
    expect(pair.reasons.join(' ')).toContain('same_skeleton');
  });

  it('keeps a different realization of the same mandatory facts in a separate cluster', () => {
    const pair = comparePair(profile('a', A, 1), profile('c', C, 2));
    expect(pair.homogeneous).toBe(false);
  });

  it('keeps a scene with different facts separate', () => {
    const pair = comparePair(profile('a', A, 1), profile('d', D, 2));
    expect(pair.homogeneous).toBe(false);
  });

  it('flags a shared opening and closing even when the middle differs', () => {
    const left = [
      '巷子里还留着雨后的水痕。',
      '路明非把护目镜摘下来，用袖口擦了擦镜片。',
      '诺诺踢开脚边一颗小石子。',
      '四分钟过去，两个人都没有动。',
    ].join('');
    const right = [
      '巷子里还留着雨后的水痕。',
      '诺诺把旧箱子放在地上，又提起来掂了掂。',
      '路明非听见远处有人喊了一声。',
      '四分钟过去，两个人都没有动。',
    ].join('');
    const pair = comparePair(profile('left', left, 1), profile('right', right, 2));
    expect(pair.homogeneous).toBe(true);
    expect(pair.reasons.join(' ')).toContain('same_opening_and_closing');
  });

  it('clusters with complete linkage so a mild similarity chain cannot merge two different scenes', () => {
    const profiles = [
      profile('a', A, 1),
      profile('b', B, 2),
      profile('c', C, 3),
    ];
    const clusters = clusterProfiles(profiles);
    expect(clusters.map((cluster) => cluster.members)).toEqual([['a', 'b'], ['c']]);
  });

  it('counts qualified clusters separately without replacing the repetition denominator', () => {
    const profiles = [
      profile('a', A, 1),
      profile('b', B, 2),
      profile('c', C, 3),
      profile('d', D, 4),
    ];
    const report = buildDiversityReport({ profiles, qualifiedIds: ['a', 'b', 'c'] });
    expect(report.effectiveRepetition).toBeCloseTo(1 - 3 / 4, 6);
    expect(report.qualifiedCount).toBe(3);
    // a/b are one realization; c is another; d is unqualified.
    expect(report.qualifiedClusters).toBe(2);
    expect(report.qualifiedDistinctClusters).toBe(2);
  });

  it('counts zero qualified clusters when no sample passed, without touching the repetition denominator', () => {
    const profiles = [profile('a', A, 1), profile('b', B, 2), profile('c', C, 3)];
    const report = buildDiversityReport({ profiles, qualifiedIds: [] });
    expect(report.qualifiedCount).toBe(0);
    expect(report.qualifiedClusters).toBe(0);
    expect(report.qualifiedDistinctClusters).toBe(0);
    expect(report.effectiveRepetition).toBeCloseTo(1 - 2 / 3, 6);
  });

  it('returns zero repetition for an empty pool and keeps the formula safe', () => {
    expect(effectiveRepetition(0, 0)).toBe(0);
  });
});

describe('text metrics', () => {
  it('measures in-draft repetition and prior echo without judging style', () => {
    const repeated = '巷子里还留着雨后的水痕。巷子里还留着雨后的水痕。四分钟过去，两个人都没有动。';
    const metrics = textMetrics(repeated, A);
    expect(metrics.repeatedSentenceRatio).toBeGreaterThan(0);
    expect(metrics.priorEcho).toBeGreaterThan(0);
  });

  it('reports empty sentences instead of treating them as content', () => {
    const metrics = textMetrics('……\n\n片刻之后，一切安静下来。');
    expect(metrics.emptySentenceRatio).toBeGreaterThan(0);
  });
});

function sample(id: string, seed: number, text: string, status: CandidateSample['status'] = 'ok'): CandidateSample {
  return { id, seed, text, status, totalMs: 1000, firstTokenMs: 200, tokens: 100 };
}

function assessment(
  id: string,
  qualified: boolean | null,
  mandatoryCovered = 1,
  mandatoryTotal = 1,
  hardIssueKinds: string[] = [],
): CandidateAssessment {
  return { id, qualified, mandatoryCovered, mandatoryTotal, hardIssueKinds };
}

describe('candidate selection', () => {
  const candidates: SelectionCandidate[] = [
    sample('long-early', 1, `${A}${A}`),
    sample('short-late', 2, A),
  ];

  it('prefers full mandatory coverage over a longer text', () => {
    const decision = selectCandidate({
      candidates,
      assessments: [assessment('long-early', true, 1, 2), assessment('short-late', true, 2, 2)],
    });
    expect(decision.selectedId).toBe('short-late');
    expect(decision.verdict).toBe('adopted');
  });

  it('never adopts an unjudged candidate by default', () => {
    const decision = selectCandidate({
      candidates: [sample('x', 1, A)],
      assessments: [assessment('x', null)],
    });
    expect(decision.selectedId).toBeNull();
    expect(decision.verdict).toBe('none');
  });

  it('marks a provisional offline decision when explicitly allowed', () => {
    const decision = selectCandidate({
      candidates: [sample('x', 1, A)],
      assessments: [assessment('x', null)],
      options: { allowProvisional: true },
    });
    expect(decision.selectedId).toBe('x');
    expect(decision.verdict).toBe('provisional');
  });

  it('never selects a transport-failed partial text', () => {
    const decision = selectCandidate({
      candidates: [sample('timeout', 1, A, 'timeout')],
      assessments: [assessment('timeout', true)],
    });
    expect(decision.selectedId).toBeNull();
    expect(decision.rejected[0].reason).toBe('transport_failed');
  });

  it('rejects a hard-failing candidate and keeps it in evidence', () => {
    const decision = selectCandidate({
      candidates: [sample('bad', 1, A), sample('good', 2, C)],
      assessments: [assessment('bad', false, 1, 1, ['fact_event_added']), assessment('good', true, 1, 1)],
    });
    expect(decision.selectedId).toBe('good');
    expect(decision.rejected.find((entry) => entry.id === 'bad')?.reason).toBe('not_qualified');
    expect(decision.considered).toEqual(['bad', 'good']);
  });

  it('prefers the candidate that does not echo the accepted prior turn', () => {
    const echo = sample('echo', 1, A);
    const fresh = sample('fresh', 2, C);
    const decision = selectCandidate({
      candidates: [echo, fresh],
      assessments: [assessment('echo', true), assessment('fresh', true)],
      options: { priorText: A, licensedEntities: LICENSED },
    });
    expect(decision.selectedId).toBe('fresh');
  });

  it('records a homogeneous duplicate as a wasted call, not a second choice', () => {
    const decision = selectCandidate({
      candidates: [sample('a', 1, A), sample('b', 2, B)],
      assessments: [assessment('a', true), assessment('b', true)],
      options: { licensedEntities: LICENSED },
    });
    expect(decision.selectedId).toBe('a');
    expect(decision.rejected.find((entry) => entry.id === 'b')?.reason).toBe('homogeneous_duplicate');
  });

  it('uses seed order as the deterministic last tie-break', () => {
    const decision = selectCandidate({
      candidates: [sample('second', 2, C), sample('first', 1, A)],
      assessments: [assessment('second', true, 1, 1), assessment('first', true, 1, 1)],
    });
    expect(decision.ranking.map((entry) => entry.id)).toEqual(['first', 'second']);
  });
});

describe('candidate pool', () => {
  it('runs every seed and records real concurrency and per-call time', async () => {
    const pool = await runCandidatePool(
      { seeds: [1, 2, 3, 4, 5], concurrency: 2, perCallTimeoutMs: 1000, totalBudgetMs: 5000 },
      async (seed, signal) => {
        await new Promise((resolve) => setTimeout(resolve, 5));
        if (signal.aborted) throw new Error('aborted');
        return { text: `text-${seed}`, finishReason: 'stop', totalMs: 5, firstTokenMs: 1, tokens: 3 };
      },
    );
    expect(pool.requested).toBe(5);
    expect(pool.completed).toBe(5);
    expect(pool.failed).toBe(0);
    expect(pool.peakConcurrency).toBe(2);
    expect(pool.samples.map((entry) => entry.seed)).toEqual([1, 2, 3, 4, 5]);
    expect(pool.samples.every((entry) => entry.status === 'ok')).toBe(true);
  });

  it('keeps a transport failure as a failed sample and does not retry it silently', async () => {
    const pool = await runCandidatePool(
      { seeds: [1, 2], concurrency: 1, perCallTimeoutMs: 1000, totalBudgetMs: 5000 },
      async (seed) => {
        if (seed === 2) throw new Error('engine down');
        return { text: 'ok', finishReason: 'stop', totalMs: 1 };
      },
    );
    expect(pool.completed).toBe(1);
    expect(pool.failed).toBe(1);
    expect(pool.samples[1].status).toBe('error');
    expect(pool.samples[1].error).toContain('engine down');
  });

  it('enforces the whole-pool budget and keeps the unfinished seeds as cancelled', async () => {
    const pool = await runCandidatePool(
      { seeds: [1, 2, 3], concurrency: 1, perCallTimeoutMs: 1000, totalBudgetMs: 15 },
      async (_seed, signal) => {
        await new Promise<void>((resolve, reject) => {
          const timer = setTimeout(resolve, 200);
          signal.addEventListener('abort', () => {
            clearTimeout(timer);
            const error = new Error('aborted');
            error.name = 'AbortError';
            reject(error);
          }, { once: true });
        });
        return { text: 'late', finishReason: 'stop', totalMs: 200 };
      },
    );
    expect(pool.budgetExceeded).toBe(true);
    expect(pool.samples.every((entry) => entry.status === 'cancelled')).toBe(true);
    expect(pool.samples.some((entry) => entry.error === 'pool_budget_exceeded')).toBe(true);
  });

  it('marks a call that hit its own timeout', async () => {
    const pool = await runCandidatePool(
      { seeds: [1], concurrency: 1, perCallTimeoutMs: 10, totalBudgetMs: 5000 },
      async (_seed, signal) => new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => {
          const error = new Error('timeout');
          error.name = 'AbortError';
          reject(error);
        }, { once: true });
      }),
    );
    expect(pool.samples[0].status).toBe('timeout');
  });

  it('records a length stop as truncated instead of a complete scene', async () => {
    const pool = await runCandidatePool(
      { seeds: [1], concurrency: 1, perCallTimeoutMs: 1000, totalBudgetMs: 5000 },
      async () => ({ text: '半句', finishReason: 'length', totalMs: 5 }),
    );
    expect(pool.samples[0].status).toBe('truncated');
  });
});
