// Summarize G8 acceptance chunks into artifacts/goal/acceptance/summary.json.
// Reads the driver's own per-turn evidence; invents no clock. The 60 s gate is
// firstReadableAt - inputAt; the turn cap is the submission wait under 300 s
// (the page's 295 s deadline is the backstop). Failures stay in the output.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const arg = (name, fallback = null) => {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const root = resolve(new URL('../../..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const runs = (arg('--runs', '') || '').split(',').map((item) => item.trim()).filter(Boolean).map((item) => resolve(item));
const out = resolve(arg('--out', resolve(root, 'artifacts/goal/acceptance/summary.json')));
if (!runs.length) throw new Error('pass --runs file1,file2,...');

const FIRST_READABLE_LIMIT_MS = 60_000;
const TURN_LIMIT_MS = 300_000;
const inputs = [];
const failures = [];

for (const file of runs) {
  if (!existsSync(file)) throw new Error(`run file missing: ${file}`);
  const evidence = JSON.parse(readFileSync(file, 'utf8'));
  for (const turn of evidence.turns ?? []) {
    const product = turn.product ?? {};
    const firstReadable = product.firstReadableAtMs ?? null;
    const wait = turn.timings?.waitMs ?? null;
    const pointSlots = Object.values(product.pointNarration ?? {});
    const textDurations = pointSlots
      .map((slot) => (typeof slot?.completedAtMs === 'number' && typeof slot?.startedAtMs === 'number'
        ? slot.completedAtMs - slot.startedAtMs : null))
      .filter((value) => value != null);
    const row = {
      file: file.replaceAll('\\', '/'),
      run: evidence.runId,
      id: turn.id,
      input: turn.input,
      firstReadableAtMs: firstReadable,
      acceptedMs: product.acceptedMs ?? null,
      turnWaitMs: wait,
      longestPointTextMs: textDurations.length ? Math.max(...textDurations) : null,
      problems: turn.problems ?? [],
      firstReadablePass: firstReadable != null && firstReadable <= FIRST_READABLE_LIMIT_MS,
      turnCapPass: wait != null && wait < TURN_LIMIT_MS,
      deadlineAbort: (turn.stages ?? []).some((stage) => /295 秒时限/.test(String(stage.label ?? ''))),
    };
    inputs.push(row);
    if (!row.firstReadablePass || !row.turnCapPass) failures.push({ id: row.id, firstReadablePass: row.firstReadablePass, turnCapPass: row.turnCapPass });
  }
}

const byId = new Map();
for (const row of inputs) byId.set(row.id, row); // same id in a later chunk supersedes
const unique = [...byId.values()];
const summary = {
  kind: 'jity-goal-acceptance-summary',
  generatedAt: new Date().toISOString(),
  thresholds: { firstReadableMs: FIRST_READABLE_LIMIT_MS, turnMs: TURN_LIMIT_MS },
  sources: runs.map((file) => file.replaceAll('\\', '/')),
  inputs: unique,
  gates: {
    inputs: unique.length,
    firstReadablePass: unique.filter((row) => row.firstReadablePass).length,
    turnCapPass: unique.filter((row) => row.turnCapPass).length,
    deadlineStops: unique.filter((row) => row.deadlineAbort).length,
    failures,
  },
};

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(summary, null, 2));
console.log(JSON.stringify({ inputs: summary.gates.inputs, firstReadablePass: summary.gates.firstReadablePass, turnCapPass: summary.gates.turnCapPass, deadlineStops: summary.gates.deadlineStops }));
console.log(`[acceptance] ${out}`);
console.log(unique.map((row) => `${row.id}: firstRead=${row.firstReadableAtMs} wait=${row.turnWaitMs} ${row.firstReadablePass ? 'OK' : 'FAIL60'} ${row.turnCapPass ? 'OK' : 'FAIL300'}`).join('\n'));