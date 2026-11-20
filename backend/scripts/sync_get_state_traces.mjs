// One-shot fixture sync for the GetStateData contract extension (2026-10-25,
// target-identity revision 2026-10-26): every recorded get_state response
// gains the point's own saved record — previousPointId / timeAdvance /
// entityDeltas — copied VERBATIM (templated $var references included) from
// the matching commit_point step's request.point. Target determination is by
// POINT IDENTITY, never by parameter omission:
//   - request.point resolving to the trace's rootPointId → root record
//     (null/null/{}), whether or not the parameter is present;
//   - request.point omitted → HEAD read: the nearest preceding commit's
//     record (the head is the last committed point; before any commit the
//     head is the root);
//   - request.point naming another point → that point's commit record;
//     no matching commit and not the root → hard error (no silent fallback).
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const tracesDir = resolve(root, 'design/world-protocol/v2/traces');

const isVar = (v) => v != null && typeof v === 'object' && '$var' in v;
const sameRef = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const resolveVar = (v, values) => (isVar(v) && values[v.$var] !== undefined ? values[v.$var] : v);

for (const name of ['T01', 'T02', 'T02-empty-linked', 'T03', 'T03-collapse', 'T04', 'T05', 'T06', 'T07', 'T08', 'T09']) {
  const file = resolve(tracesDir, `${name}.json`);
  const trace = JSON.parse(readFileSync(file, 'utf8'));
  const values = trace.samples[0]?.values ?? {};
  // The trace's root point id comes from create_world's response; traces
  // recorded mid-session (no create_world) fall back to the first served
  // head — for a session with no commits the head IS the root.
  const createStep = trace.steps.find((s) => s.operation === 'create_world');
  let rootPointId = createStep ? resolveVar(createStep.response?.data?.rootPointId ?? null, values) : null;
  if (rootPointId == null) {
    const contextStep = trace.steps.find((s) => s.response?.world?.head?.pointId != null);
    rootPointId = contextStep ? resolveVar(contextStep.response.world.head.pointId, values) : null;
  }
  let patched = 0;
  for (let i = 0; i < trace.steps.length; i++) {
    const step = trace.steps[i];
    if (step.operation !== 'get_state') continue;
    const data = step.response?.data;
    if (!data) throw new Error(`${name} step ${step.id}: get_state response has no data`);
    const requested = step.request?.point ?? null;

    // Nearest preceding commit (identity fallback for head reads).
    let nearestCommit = null;
    for (let j = i - 1; j >= 0; j--) {
      if (trace.steps[j].operation === 'commit_point') { nearestCommit = trace.steps[j].request?.point ?? null; break; }
    }
    // Point-matched commit (explicit point reads).
    let matchedCommit = null;
    if (requested != null) {
      for (let j = i - 1; j >= 0; j--) {
        if (trace.steps[j].operation !== 'commit_point') continue;
        const candidate = trace.steps[j].request?.point ?? null;
        if (sameRef(candidate?.id ?? null, requested)) { matchedCommit = candidate; break; }
      }
    }

    const resolvedPoint = resolveVar(requested, values);
    const isRootRead = requested != null && rootPointId != null && sameRef(resolvedPoint, rootPointId);
    let record;
    if (isRootRead) {
      record = { previousPointId: null, timeAdvance: null, entityDeltas: {} };
      console.log(`${name} ${step.id}: root read (identity) → null/null/{}`);
    } else if (requested == null) {
      if (nearestCommit == null) {
        record = { previousPointId: null, timeAdvance: null, entityDeltas: {} };
        console.log(`${name} ${step.id}: head read before any commit (head=root) → null/null/{}`);
      } else {
        record = { previousPointId: nearestCommit.previousPointId ?? null, timeAdvance: nearestCommit.timeAdvance ?? null, entityDeltas: nearestCommit.entityDeltas ?? {} };
        console.log(`${name} ${step.id}: head read → nearest commit ${JSON.stringify(nearestCommit.id)} (deltas ${Object.keys(record.entityDeltas).length})`);
      }
    } else if (matchedCommit != null) {
      record = { previousPointId: matchedCommit.previousPointId ?? null, timeAdvance: matchedCommit.timeAdvance ?? null, entityDeltas: matchedCommit.entityDeltas ?? {} };
      console.log(`${name} ${step.id}: point read ${JSON.stringify(requested)} ← commit ${JSON.stringify(matchedCommit.id)} (deltas ${Object.keys(record.entityDeltas).length})`);
    } else {
      throw new Error(`${name} step ${step.id}: requested point ${JSON.stringify(requested)} matches no preceding commit and is not the root (${JSON.stringify(rootPointId)})`);
    }
    data.previousPointId = record.previousPointId;
    data.timeAdvance = record.timeAdvance;
    data.entityDeltas = record.entityDeltas;
    patched += 1;
  }
  writeFileSync(file, JSON.stringify(trace, null, 2) + '\n');
  console.log(`→ ${name}.json: ${patched} get_state steps synced`);
}
