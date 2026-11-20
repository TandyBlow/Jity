// Collect narration samples from driver runs into artifacts/goal/narration/.
// Raw text only: the reader compares it with the committed facts; nothing is
// scored or rewritten here.

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const arg = (name, fallback = null) => {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const root = resolve(new URL('../../..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const runs = (arg('--runs', '') || '').split(',').map((item) => item.trim()).filter(Boolean).map((item) => resolve(item));
const out = resolve(arg('--out', resolve(root, 'artifacts/goal/narration/samples.json')));

const samples = [];
const sources = [];
for (const file of runs) {
  if (!existsSync(file)) throw new Error(`run file missing: ${file}`);
  const evidence = JSON.parse(readFileSync(file, 'utf8'));
  sources.push({ file: file.replaceAll('\\', '/'), runId: evidence.runId, status: evidence.status, turnsFile: evidence.turnsFile, arm: evidence.arm ?? null });
  for (const turn of evidence.turns ?? []) {
    const text = (turn.text ?? '').trim();
    if (!text) continue;
    const narration = turn.product?.narration ?? null;
    samples.push({
      id: `${evidence.runId}:${turn.id}`,
      run: evidence.runId,
      turn: turn.turn,
      turnId: turn.id,
      pointId: turn.product?.narration?.pointId ?? null,
      input: turn.input ?? null,
      purpose: turn.purpose ?? null,
      text,
      textChars: text.length,
      source: turn.product?.source ?? turn.textSource ?? null,
      narrationModel: turn.product?.narrationModel ?? evidence.arm?.narrationModel ?? null,
      modelId: turn.product?.modelId ?? null,
      acceptedMs: turn.product?.acceptedMs ?? null,
      doneMs: turn.timings?.doneMs ?? null,
      stops: turn.submission?.stops ?? [],
      continuationDecision: turn.submission?.continuationDecision ?? null,
      problems: turn.problems ?? [],
      note: turn.note ?? null,
      // The projection the model saw, so a reviewer can compare prose vs facts.
      narrationPrompt: typeof narration?.prompt === 'string' ? narration.prompt.slice(0, 4000) : null,
      narrationRaw: typeof narration?.raw === 'string' ? narration.raw.slice(0, 2000) : null,
    });
  }
}

const summary = {
  kind: 'jity-goal-narration-samples',
  generatedAt: new Date().toISOString(),
  note: 'Raw model text as displayed (D-004). Read-eval happens in the review sheet; this file only collects samples.',
  sources,
  count: samples.length,
  samples,
};
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(summary, null, 2));
console.log(`[narration] ${samples.length} samples from ${sources.length} runs -> ${out}`);
