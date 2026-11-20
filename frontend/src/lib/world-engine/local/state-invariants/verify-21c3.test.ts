/** CPU-only regression for the 21c3 stale-observation report.
 *
 * The end-of-turn sample is the root snapshot because 09 sampled it while the
 * submit/refresh path was still running. The reload sample is the same world
 * three points later. This test proves the save is a valid forward chain, not
 * that the page showed it at the stale instant.
 */
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { verifyDisplayHistory, verifySessionSnapshot, verifySnapshotSequence, verifyTaskDecisionEvidence } from './index';

const EVIDENCE = resolve('../../../results/product/evidence/09-one-legal-turn-21c3.json');
const hasEvidence = existsSync(EVIDENCE);
const evidence = hasEvidence ? JSON.parse(readFileSync(EVIDENCE, 'utf8')) : null;
const turn = evidence?.turns?.[0] ?? {};
const stale = turn.snapshotAfterTurn;
const recovered = evidence?.refreshRestore?.snapshotAfterReload;

describe.skipIf(!hasEvidence)('21c3 save recovery', () => {
  it('reads the reload snapshot as a valid three-point save', async () => {
    expect(stale.transport.version).toBe(0);
    expect(stale.commands).toEqual([]);
    expect(recovered.transport.version).toBe(3);
    expect(recovered.commands).toHaveLength(1);
    expect(Object.keys(recovered.transport.points)).toHaveLength(3);
    const report = await verifySessionSnapshot(recovered);
    expect(report.errors, JSON.stringify(report.errors)).toEqual([]);
    expect(report.ok).toBe(true);
    expect(report.version).toBe(3);
    expect(report.headPointId).toBe('point_round_auto_mwb3q8vp_2_1');
    const history = verifyDisplayHistory(recovered);
    expect(history.errors, JSON.stringify(history.errors)).toEqual([]);
    expect(history.total).toBe(1);
    expect(history.ready).toBe(1);
    expect(recovered.transport.state.characters.lu.tasks.task_lu_match.status).toBe('pending');
    const calls = (turn.submission?.calls ?? []).filter((call: { task?: string; coverage?: unknown }) => call.task === 'updates' && call.coverage);
    expect(calls).toHaveLength(4);
    for (const call of calls) {
      const coverage = verifyTaskDecisionEvidence(call.coverage);
      expect(coverage.errors, JSON.stringify(coverage.errors)).toEqual([]);
      expect(coverage.taskRows).toBe(73);
    }
  });

  it('treats the root sample as an earlier valid snapshot, not a lost save', async () => {
    const report = await verifySnapshotSequence([stale, recovered]);
    expect(report.errors, JSON.stringify(report.errors)).toEqual([]);
    expect(report.version).toBe(3);
    expect(report.points).toBe(3);
  });
});
