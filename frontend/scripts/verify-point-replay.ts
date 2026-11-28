/** D-139 precondition: replaying the stored record from S0 must reproduce
 * every stored point digest (so per-point full states can be dropped). */
import { readFileSync } from 'node:fs';
import { verifySessionSnapshot } from '../src/lib/world-engine/local/state-invariants';

const path = process.argv[2] ?? '../artifacts/goal/micro-workflow/evidence-semantic-env-11-2026-11-27T1848-1519.json';
const evidence = JSON.parse(readFileSync(path, 'utf8'));
const report = await verifySessionSnapshot(evidence.turns.at(-1).snapshotAfterTurn);
console.log(JSON.stringify({
  ok: report.ok,
  points: report.points,
  errors: report.errors.slice(0, 10),
  warnings: (report.warnings ?? []).slice(0, 5),
}, null, 1));
