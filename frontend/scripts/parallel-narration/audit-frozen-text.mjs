#!/usr/bin/env node
/** Replay a frozen batch's accepted text through the current verifier, offline.
 *
 * The 2026-11-10 route decision left seven frozen cases and lane 01's review of
 * each. Re-running inference is not allowed for a regression audit, and the
 * text itself is already fixed. This reads the batch JSON plus the fixture
 * directory, feeds each chosen text to the generator once (a scripted engine,
 * no model), and prints the issue kinds the current rules produce.
 *
 * Usage:
 *   tsx scripts/parallel-narration/audit-frozen-text.mjs \
 *     --batch ../../../results/product/operations/prompt-route-hour-20261110T222039Z/batch-1.json \
 *     --fixtures ../../../results/product/operations/prompt-route-hour-20261110T222039Z/fixtures \
 *     --out ../../../results/02-narration/route-batch-audit.json
 */
import fs from 'node:fs';
import path from 'node:path';
import { generateCommittedNarration } from '../../src/lib/world-engine/local/narration-generation/index.ts';

function option(name, fallback = '') {
  const at = process.argv.indexOf(name);
  return at >= 0 ? process.argv[at + 1] ?? fallback : fallback;
}

const batchPath = option('--batch');
const fixturesDir = option('--fixtures');
const outPath = option('--out');
if (!batchPath || !fixturesDir) {
  console.error('usage: audit-frozen-text.mjs --batch <batch.json> --fixtures <dir> [--out <json>]');
  process.exit(2);
}

const batch = JSON.parse(fs.readFileSync(batchPath, 'utf8'));
const fixtures = new Map();
for (const entry of fs.readdirSync(fixturesDir)) {
  if (!entry.endsWith('.json')) continue;
  const data = JSON.parse(fs.readFileSync(path.join(fixturesDir, entry), 'utf8'));
  fixtures.set(entry.replace(/\.json$/u, ''), data);
  // The file name and the scenario id differ for two frozen cases
  // (free-day-root-scenario-160.json carries id free-day-root-160).
  if (data.id) fixtures.set(String(data.id), data);
}

const engine = (text) => ({
  info: { backend: 'scripted', modelId: 'frozen-text' },
  async load() {},
  async dispose() {},
  async complete() { return text; },
});

const rows = [];
for (const run of batch.runs ?? []) {
  const fixtureName = String(run.id).replace(/::.*$/u, '');
  const fixture = fixtures.get(fixtureName);
  const text = String(run.text ?? '').trim();
  if (!fixture || !text) {
    rows.push({ id: run.id, skipped: !fixture ? 'fixture not found' : 'no chosen text' });
    continue;
  }
  const result = await generateCommittedNarration({
    engine: engine(text),
    committed: fixture.committed,
    inputText: fixture.inputText,
    priorText: fixture.priorText ?? null,
    policy: {
      ...fixture.policy,
      mode: 'scene',
      promptShape: 'prose-facts',
      scene: fixture.scene ?? null,
      time: fixture.time ?? fixture.policy?.time,
      maxAttempts: 1,
      deadlineMs: 60_000,
    },
  });
  const first = result.rawAttempts?.[0] ?? { issues: [] };
  const hard = first.issues.filter((issue) => issue.severity === 'hard');
  const soft = first.issues.filter((issue) => issue.severity !== 'hard');
  rows.push({
    id: run.id,
    acceptedByHarness: run.accepted,
    chars: run.chars,
    hard: hard.map((issue) => issue.kind),
    hardDetails: hard.map((issue) => ({ kind: issue.kind, detail: issue.detail, sentence: issue.sentence })),
    soft: [...new Set(soft.map((issue) => issue.kind))],
  });
}

const report = {
  kind: '02-frozen-text-audit',
  at: new Date().toISOString(),
  batch: batchPath,
  fixtures: fixturesDir,
  source: 'text replayed through the verifier; no inference',
  rows,
};
const json = JSON.stringify(report, null, 2);
if (outPath) fs.writeFileSync(outPath, `${json}\n`);
else console.log(json);
console.error(`audited ${rows.length} cases`);
