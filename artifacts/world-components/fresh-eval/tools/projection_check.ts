/**
 * Run the real page projection over the six committed cases.
 *
 * This is the countercheck for the pack's `capability.stages`: the Python side
 * predicts what `projectCommittedNarration` will do; this script actually calls
 * it on the committed before/after records and records the outcome.
 *
 * No model is involved. Usage:
 *   node --experimental-strip-types tools/projection_check.ts <fresh/source> <out.json>
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, resolve } from 'node:path';

// Resolve the repository from this file, never from a machine-specific path:
// tools/ -> fresh-eval/ -> world-components/ -> artifacts/ -> repo root.
const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '../../../..');
const MODULE_PATH = resolve(REPO, 'frontend/src/lib/world-engine/runtime/committed-narration.ts');
const { projectCommittedNarration } =
  await import(pathToFileURL(MODULE_PATH).href);

const [sourceDir, outPath] = process.argv.slice(2);
if (!sourceDir || !outPath) {
  console.error('usage: projection_check.ts <fresh/source> <out.json>');
  process.exit(2);
}
const ids = ['c8e01', 'c8e02', 'c8e03', 'c8e04', 'c8e05', 'c8e06'];
const cases = JSON.parse(readFileSync(`${sourceDir}/cases.json`, 'utf8'));
const results: any[] = [];

for (const id of ids) {
  const before = JSON.parse(readFileSync(`${sourceDir}/${id}.before.json`, 'utf8'));
  const after = JSON.parse(readFileSync(`${sourceDir}/${id}.after.json`, 'utf8'));
  const entry: any = { id };
  try {
    const packet = projectCommittedNarration(after, before);
    entry.accepted = true;
    entry.factCount = packet.facts.length;
    entry.kinds = packet.facts.map((f: any) => f.kind);
    entry.actors = [...new Set(packet.facts.map((f: any) => f.actorId))];
  } catch (error) {
    entry.accepted = false;
    entry.reason = (error as Error).message;
  }
  const answerPath = `${sourceDir}/../../candidates-fresh/${id}/answer.json`;
  try {
    const answer = JSON.parse(readFileSync(answerPath, 'utf8'));
    entry.withheldActors = [...new Set((answer.withheld || []).map((w: any) => w.entityId))];
    entry.projectionNarratesWithheld = entry.accepted
      ? entry.withheldActors.some((actor: string) => entry.actors.includes(actor))
      : null;
  } catch {
    entry.withheldActors = null;
  }
  const c = cases.find((x: any) => x.id === id);
  entry.pointId = c?.pointId ?? null;
  entry.afterDigest = c?.afterDigest ?? null;
  results.push(entry);
}

const moduleSha = createHash('sha256').update(readFileSync(MODULE_PATH)).digest('hex');
writeFileSync(outPath, JSON.stringify({
  node: process.version,
  module: 'frontend/src/lib/world-engine/runtime/committed-narration.ts',
  moduleSha256: moduleSha,
  modelCalls: 0,
  cases: results,
}, null, 1) + '\n');
console.log(results.map((r) => `${r.id} ${r.accepted ? 'ACCEPTED' : 'REJECTED ' + r.reason}`).join('\n'));
