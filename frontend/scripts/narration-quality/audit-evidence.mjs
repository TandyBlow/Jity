#!/usr/bin/env node
/**
 * Layer audit for 09 product evidence.
 *
 * The product page can show four different things: the model's raw text, the
 * cleaned text, the pruned text (sentences removed), and the final shown text.
 * A report that only keeps one of them cannot prove what the player read.
 *
 * Usage:
 *   node frontend/scripts/narration-quality/audit-evidence.mjs <evidence.json> [more.json]
 *
 * Output: a per-turn table on stdout and a JSON summary next to the input,
 * `<name>.layers.json`. Missing layers are reported as `null`, never guessed.
 *
 * A derived file is bound to the exact base bytes: it records `runId`,
 * `baseSha256` and `baseBytes`. Two runs can share a file name (09 rewrites
 * `09-one-legal-turn.json`); a derived file from another run must not be read
 * as this one's. If the name is taken by a different base, the summary goes to
 * `<name>.layers.<sha8>.json` instead of overwriting it.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { basename, dirname, join } from 'node:path';

const LAYERS = ['raw', 'cleaned', 'pruned', 'shown'];

function chars(value) {
  return typeof value === 'string' ? [...value].length : null;
}

function pick(turn, keys) {
  for (const key of keys) {
    if (turn[key] !== undefined && turn[key] !== null) return turn[key];
  }
  return null;
}

function auditTurn(turn) {
  const product = turn.product ?? {};
  const debug = turn.narrationDebug ?? {};
  const shown = pick(turn, ['text', 'shownText']) ?? '';
  const layers = {
    raw: pick(turn, ['rawText', 'raw']) ?? null,
    cleaned: pick(turn, ['cleanedText', 'cleaned']) ?? null,
    pruned: pick(turn, ['prunedText', 'pruned']) ?? null,
    shown: typeof shown === 'string' ? shown : null,
  };
  const counts = {
    raw: chars(layers.raw) ?? debug.rawChars ?? null,
    cleaned: chars(layers.cleaned) ?? debug.cleanedChars ?? null,
    pruned: chars(layers.pruned) ?? debug.prunedChars ?? null,
    shown: chars(layers.shown) ?? debug.shownChars ?? null,
  };
  const sources = {
    productSource: product.source ?? null,
    acceptedMs: product.acceptedMs ?? null,
    draftMs: product.draftMs ?? null,
    programMs: product.programMs ?? null,
    textSource: product.source === 'program' ? 'program_fallback' : product.source === 'model' ? 'model' : 'unknown',
  };
  const calls = product.submission?.calls?.length ?? 0;
  const countersLookStale = calls === 0 && (counts.raw ?? 0) > 0;
  const missing = LAYERS.filter((layer) => layers[layer] === null);
  const mismatched = counts.pruned !== null && counts.shown !== null && counts.pruned > counts.shown;
  return {
    id: turn.id ?? null,
    turn: turn.turn ?? null,
    input: turn.input ?? null,
    problems: turn.problems ?? [],
    counts,
    sources,
    layersAvailable: LAYERS.filter((layer) => layers[layer] !== null),
    missingLayers: missing,
    prunedButNotShown: mismatched,
    countersLookStale,
    shownText: layers.shown,
    settledInput: turn.settled?.input ?? turn.settledInput ?? turn.inputState ?? null,
    note: missing.length
      ? `missing layers: ${missing.join(', ')}; the report cannot prove what was removed`
      : 'all four layers present',
  };
}

function audit(file, force) {
  const bytes = readFileSync(file);
  const baseSha256 = createHash('sha256').update(bytes).digest('hex');
  const raw = JSON.parse(bytes.toString('utf8'));
  const turns = Array.isArray(raw) ? raw : raw.turns ?? [];
  const records = turns.map(auditTurn);
  const summary = {
    file,
    runId: raw.runId ?? raw.id ?? null,
    baseSha256,
    baseBytes: bytes.length,
    startedAt: raw.startedAt ?? null,
    derivedAt: new Date().toISOString(),
    kind: raw.kind ?? null,
    status: raw.status ?? null,
    updatedAt: raw.updatedAt ?? null,
    turns: records.length,
    missingLayerTurns: records.filter((record) => record.missingLayers.length).length,
    programFallbackTurns: records.filter((record) => record.sources.textSource === 'program_fallback').length,
    unknownSourceTurns: records.filter((record) => record.sources.textSource === 'unknown').length,
    records,
  };
  const out = join(dirname(file), `${basename(file, '.json')}.layers.json`);
  writeFileSync(out, `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
  return { summary, out };
}

const args = process.argv.slice(2);
const batchFlag = args.indexOf('--batch');
const batchOut = batchFlag >= 0 ? args[batchFlag + 1] : null;
const force = args.includes('--force');
const files = args.filter((arg, index) => !(arg.startsWith('--')) && (batchFlag < 0 || index !== batchFlag + 1));
if (!files.length) {
  console.error('usage: node frontend/scripts/narration-quality/audit-evidence.mjs <evidence.json> [...]');
  process.exit(2);
}
const batchRows = [];
for (const file of files) {
  const { summary, out } = audit(file, force);
  console.log(`\n== ${file}`);
  console.log(`status=${summary.status} turns=${summary.turns} program_fallback=${summary.programFallbackTurns} unknown=${summary.unknownSourceTurns} missing_layers=${summary.missingLayerTurns}`);
  for (const record of summary.records) {
    console.log(`  ${record.id ?? '?'} source=${record.sources.textSource} raw=${record.counts.raw} cleaned=${record.counts.cleaned} pruned=${record.counts.pruned} shown=${record.counts.shown} missing=[${record.missingLayers.join(',')}] pruned>shown=${record.prunedButNotShown} stale_counters=${record.countersLookStale}`);
  }
  console.log(`  wrote ${out}`);
  for (const record of summary.records) {
    const input = record.settledInput ?? (record.setled ? record.settled?.input : null);
    if (!input || !record.shownText) continue;
    batchRows.push({ id: record.id ?? `turn-${record.turn}`, input, text: record.shownText, textSource: record.sources.textSource });
  }
}
if (batchOut) {
  const body = batchRows.map((row) => JSON.stringify(row)).join(String.fromCharCode(10));
  writeFileSync(batchOut, body + (batchRows.length ? String.fromCharCode(10) : ''), 'utf8');
  console.log(`
batch rows: ${batchRows.length} -> ${batchOut}${batchRows.length ? '' : ' (no turn carried its settled input; ask 09 to record it)'}`);
}
