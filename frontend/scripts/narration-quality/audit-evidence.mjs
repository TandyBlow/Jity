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
 */
import { readFileSync, writeFileSync } from 'node:fs';
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
    note: missing.length
      ? `missing layers: ${missing.join(', ')}; the report cannot prove what was removed`
      : 'all four layers present',
  };
}

function audit(file) {
  const raw = JSON.parse(readFileSync(file, 'utf8'));
  const turns = Array.isArray(raw) ? raw : raw.turns ?? [];
  const records = turns.map(auditTurn);
  const summary = {
    file,
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

const files = process.argv.slice(2);
if (!files.length) {
  console.error('usage: node frontend/scripts/narration-quality/audit-evidence.mjs <evidence.json> [...]');
  process.exit(2);
}
for (const file of files) {
  const { summary, out } = audit(file);
  console.log(`\n== ${file}`);
  console.log(`status=${summary.status} turns=${summary.turns} program_fallback=${summary.programFallbackTurns} unknown=${summary.unknownSourceTurns} missing_layers=${summary.missingLayerTurns}`);
  for (const record of summary.records) {
    console.log(`  ${record.id ?? '?'} source=${record.sources.textSource} raw=${record.counts.raw} cleaned=${record.counts.cleaned} pruned=${record.counts.pruned} shown=${record.counts.shown} missing=[${record.missingLayers.join(',')}] pruned>shown=${record.prunedButNotShown} stale_counters=${record.countersLookStale}`);
  }
  console.log(`  wrote ${out}`);
}
