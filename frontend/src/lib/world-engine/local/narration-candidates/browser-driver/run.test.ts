import { afterEach, describe, expect, it } from 'vitest';

import type { InferenceEngine } from '../../../runtime/engine';
import { attachEngine, disposeEngines, inspectCandidate, prepare, runOne } from './run';
import type { CandidateSpec } from './types';

const fixtureUrl = new URL('./__fixtures__/fake-candidate.ts', import.meta.url).href;
const fixtureId = 'fixture-candidate';

const spec = (overrides: Partial<CandidateSpec> = {}): CandidateSpec => ({
  id: fixtureId,
  owner: 'test',
  moduleUrl: fixtureUrl,
  exportName: 'generateCandidate',
  modelUrl: '/models/fixture.gguf',
  ...overrides,
});

function fakeEngine(): InferenceEngine {
  let disposed = false;
  return {
    info: { backend: 'fake', modelId: 'fake.gguf' },
    async load() {},
    async complete() { return 'unused'; },
    async dispose() { disposed = true; void disposed; },
  };
}

afterEach(async () => {
  await disposeEngines();
});

describe('browser candidate queue mechanics', () => {
  it('resolves a documented export without loading a model', async () => {
    const inspected = await inspectCandidate(spec());
    expect(inspected.usedExport).toBe('generateCandidate');
    expect(inspected.hasDocumentedExport).toBe(true);
    expect(inspected.moduleExports).toContain('generateBroken');
  });

  it('records real progress, paragraphs and a contract-valid result', async () => {
    attachEngine('/models/fixture.gguf', fakeEngine(), { info: { backend: 'fake', modelId: 'fixture.gguf' } });
    await prepare({
      set: 'short', include: ['short-root'], candidates: [spec()],
    });
    const run = await runOne({ candidateId: fixtureId, scenarioId: 'short-root', hardTimeoutMs: 10_000 });
    expect(run.error).toBeNull();
    expect(run.contract).toEqual({ ok: true, missing: [], notes: [] });
    expect(run.result.accepted).toBe(true);
    expect(run.result.paragraphs).toHaveLength(2);
    expect(run.result.firstParagraph).toBe('周宁没有动，只把手按在门框上。');
    expect(run.result.attempts).toHaveLength(1);
    expect(run.result.attempts[0].prompt).toContain('fixture prompt');
    expect(run.progress.count).toBe(2);
    expect(run.progress.firstReadableAtMs).not.toBeNull();
    expect(run.identity.worldId).toBe('world_short');
    expect(run.input.text).toContain('【视角】主角视角（周宁）');
  });

  it('passes the accepted text of the previous scenario as priorText', async () => {
    attachEngine('/models/fixture.gguf', fakeEngine());
    await prepare({ set: 'short', include: ['short-root', 'short-move'], candidates: [spec()] });
    const root = await runOne({ candidateId: fixtureId, scenarioId: 'short-root', hardTimeoutMs: 10_000 });
    expect(root.result.accepted).toBe(true);
    const move = await runOne({ candidateId: fixtureId, scenarioId: 'short-move', hardTimeoutMs: 10_000 });
    expect(move.input.priorText).toBe(root.result.text);
    expect(move.contract.notes).not.toContain('continuation_source_missing');
  });

  it('reports missing result fields instead of inventing them', async () => {
    attachEngine('/models/fixture.gguf', fakeEngine());
    await prepare({ set: 'short', include: ['short-root'], candidates: [spec({ exportName: 'generateBroken' })] });
    const run = await runOne({ candidateId: fixtureId, scenarioId: 'short-root', hardTimeoutMs: 10_000 });
    expect(run.contract.ok).toBe(false);
    expect(run.contract.missing).toEqual(['accepted', 'rawAttempts', 'issues', 'timings', 'strategyVersion']);
    expect(run.contract.notes).toContain('empty_text');
    expect(run.result.text.trim()).toBe('');
    expect(run.result.paragraphs).toEqual([]);
  });

  it('never reports accepted=true for an empty result', async () => {
    attachEngine('/models/fixture.gguf', fakeEngine());
    await prepare({ set: 'short', include: ['short-root'], candidates: [spec({ exportName: 'generateEmptyAccepted' })] });
    const run = await runOne({ candidateId: fixtureId, scenarioId: 'short-root', hardTimeoutMs: 10_000 });
    expect(run.result.accepted).toBe(false);
    expect(run.contract.ok).toBe(false);
    expect(run.contract.notes).toContain('accepted_with_empty_text');
  });

  it('records a thrown candidate as an error with no fabricated text', async () => {
    attachEngine('/models/fixture.gguf', fakeEngine());
    await prepare({ set: 'short', include: ['short-root'], candidates: [spec({ exportName: 'generateThrows' })] });
    const run = await runOne({ candidateId: fixtureId, scenarioId: 'short-root', hardTimeoutMs: 10_000 });
    expect(run.error).toBe('Error: fixture_failure');
    expect(run.contract.ok).toBe(false);
    expect(run.contract.notes).toContain('error:Error: fixture_failure');
    expect(run.result.text).toBe('');
  });

  it('refuses a scenario that was never prepared', async () => {
    attachEngine('/models/fixture.gguf', fakeEngine());
    await prepare({ set: 'short', include: ['short-root'], candidates: [spec()] });
    await expect(runOne({ candidateId: fixtureId, scenarioId: 'nope', hardTimeoutMs: 1000 }))
      .rejects.toThrow(/scenario_not_prepared:nope/);
  });
});

describe('continuation source', () => {
  it('reports accepted versus displayed fallback explicitly', async () => {
    attachEngine('/models/fixture.gguf', fakeEngine());
    await prepare({ set: 'short', include: ['short-root', 'short-move'], candidates: [spec()] });
    const root = await runOne({ candidateId: fixtureId, scenarioId: 'short-root', hardTimeoutMs: 10_000 });
    expect(root.input.priorSource).toBeNull();
    const moveAccepted = await runOne({ candidateId: fixtureId, scenarioId: 'short-move', hardTimeoutMs: 10_000 });
    expect(moveAccepted.input.priorSource).toBe('accepted');
  });

  it('can continue from displayed fallback and says so', async () => {
    attachEngine('/models/fixture.gguf', fakeEngine());
    await prepare({ set: 'short', include: ['short-root', 'short-move'], candidates: [spec()] });
    await runOne({ candidateId: fixtureId, scenarioId: 'short-root', hardTimeoutMs: 10_000 });
    const move = await runOne({
      candidateId: fixtureId, scenarioId: 'short-move', hardTimeoutMs: 10_000, continuation: 'displayed',
    });
    expect(move.input.priorText).toBeTruthy();
    expect(['accepted', 'displayed_fallback']).toContain(move.input.priorSource ?? '');
  });
});
