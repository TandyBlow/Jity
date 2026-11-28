/** D-139: replaying the stored record from S0 must reproduce every stored
 * point digest, both as saved and with non-head full states stripped. */
import { readFileSync } from 'node:fs';
import { verifySessionSnapshot } from '../src/lib/world-engine/local/state-invariants';

const path = process.argv[2] ?? '../artifacts/goal/micro-workflow/evidence-semantic-env-11-2026-11-27T1848-1519.json';
const evidence = JSON.parse(readFileSync(path, 'utf8'));
const record = evidence.turns.at(-1).snapshotAfterTurn;

async function main() {
const saved = await verifySessionSnapshot(record);

const compacted = structuredClone(record);
const transport = compacted.transport ?? compacted;
const states = transport.pointStates ?? record.pointStates;
const keptFull = new Set([transport.rootPointId ?? record.rootPointId, transport.headPointId ?? record.headPointId]);
let stripped = 0;
for (const [id, entry] of Object.entries(states)) {
  if (!keptFull.has(id) && (entry as { state?: unknown }).state !== undefined) {
    delete (entry as { state?: unknown }).state;
    stripped += 1;
  }
}
const strippedReport = await verifySessionSnapshot(compacted);

console.log(JSON.stringify({
  saved: { ok: saved.ok, points: saved.points, errors: saved.errors.slice(0, 10), bytes: JSON.stringify(record).length },
  compacted: { ok: strippedReport.ok, stripped, errors: strippedReport.errors.slice(0, 10), bytes: JSON.stringify(compacted).length },
}, null, 1));
}

main().catch((error) => { console.error(error); process.exit(1); });
