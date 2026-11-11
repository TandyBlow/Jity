// Compare the arms of one browser session (scene / prose / beats).
//
//   node scripts/parallel-narration/compare-arms.mjs \
//     ../../../results/02-narration/real-qwen3-free-day-arms.json [--json out.json]
//
// Reads the run records written by run-real-narration.mjs (`runs`) and prints
// one row per (scenario, arm). It only reports what the record contains; it
// does not call a model and it does not rewrite any text.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const args = process.argv.slice(2);
const file = args.find((value) => !value.startsWith('--'));
const outIndex = args.indexOf('--json');
if (!file) {
  console.error('usage: compare-arms.mjs <evidence.json> [--json summary.json]');
  process.exit(2);
}
const evidence = JSON.parse(readFileSync(resolve(file), 'utf8'));
const runs = evidence.runs ?? evidence.records ?? [];
if (!runs.length) {
  console.error(`no runs in ${file} (status ${evidence.status ?? 'unknown'}${evidence.error ? `: ${String(evidence.error).slice(0, 200)}` : ''})`);
  process.exit(1);
}

const modeOf = (run) => run.mode ?? run.id.split('::')[1] ?? 'scene';
const scenarioOf = (run) => run.id.split('::')[0];
const hardIssues = (run) => run.attempts.flatMap((attempt) => attempt.issues.filter((issue) => issue.severity === 'hard').map((issue) => issue.kind));
const softIssues = (run) => run.attempts.flatMap((attempt) => attempt.issues.filter((issue) => issue.severity !== 'hard').map((issue) => issue.kind));
const uniq = (list) => [...new Set(list)];
const beatSources = (run) => (run.beats ?? []).map((beat) => beat.source);
const round = (value) => (typeof value === 'number' ? Math.round(value) : null);

const rows = runs.map((run) => ({
  scenario: scenarioOf(run), arm: modeOf(run),
  accepted: run.accepted, status: run.status,
  chars: run.chars,
  firstTextMs: round(run.firstTextMs), wallMs: round(run.wallMs),
  attempts: (run.attempts ?? []).length,
  promptChars: run.attempts?.[0]?.promptChars ?? null,
  hard: uniq(hardIssues(run)), soft: uniq(softIssues(run)),
  beats: beatSources(run),
  fallbackBeats: beatSources(run).filter((source) => source === 'fallback').length,
  droppedSentences: (run.assembly?.droppedSentences ?? []).length,
  appendedSentences: (run.assembly?.appendedSentences ?? []).length,
  displayStatus: run.displayStatus,
  text: run.text,
}));

const pad = (value, width) => `${String(value ?? '-')}`.padEnd(width);
const header = ['scenario', 'arm', 'ok', 'chars', 'firstMs', 'wallMs', 'try', 'hard', 'soft'];
const table = rows.map((row) => [
  row.scenario, row.arm, row.accepted ? 'y' : 'n', row.chars,
  row.firstTextMs, row.wallMs, row.attempts,
  row.hard.join(',') || '-', row.soft.join(',') || '-',
].map(String));
const widths = header.map((_, index) => Math.max(header[index].length, ...table.map((cells) => cells[index].length)));
const line = (cells) => cells.map((cell, index) => pad(cell, widths[index])).join('  ');
console.log(line(header));
for (const cells of table) console.log(line(cells));
console.log('');
// Three sources must stay separate when judging an arm: the model's raw output,
// what the module accepted, and any sentence the program supplied. Reading the
// displayed page text as if it were model output was a real attribution error:
// game-model.factualNarration() writes time + room + visible people itself.
for (const run of runs) {
  const scenario = scenarioOf(run); const arm = modeOf(run);
  const segments = run.segments ?? [];
  const programSentences = [
    ...(run.assembly?.appendedSentences ?? []),
    ...segments.filter((segment) => segment.source !== 'model').map((segment) => segment.text),
  ].filter(Boolean);
  console.log(`=== ${scenario} [${arm}] status=${run.status} display=${run.displayStatus} accepted=${run.accepted}`);
  console.log(`    attempt ${run.attempts?.[0]?.promptChars ?? '?'} prompt chars; firstTextMs=${round(run.firstTextMs) ?? '-'}; wallMs=${round(run.wallMs) ?? '-'}`);
  for (const attempt of run.attempts ?? []) {
    console.log(`-- RAW model output, attempt ${attempt.attempt} (${attempt.finishReason ?? '?'}, ${round(attempt.durationMs) ?? '-'} ms)`);
    console.log(attempt.raw ? attempt.raw.trim() : '(empty)');
    const issues = (attempt.issues ?? []).map((issue) => `${issue.severity}:${issue.kind}`);
    if (issues.length) console.log(`   issues: ${issues.join(', ')}`);
  }
  console.log('-- ACCEPTED/DRAFT text returned by the module' + (run.accepted ? '' : ' (REJECTED, do not present as narration)'));
  console.log(run.text ?? '(no text)');
  if (run.beats?.length) {
    console.log(`-- BEAT SOURCES ${run.beats.map((beat) => `${beat.beatId}:${beat.source}`).join(', ')}`);
    for (const beat of run.beats.filter((value) => value.source !== 'model')) {
      console.log(`   [${beat.source}] ${beat.text}`);
    }
  }
  if (programSentences.length) {
    console.log('-- PROGRAM sentences inside the returned text');
    for (const sentence of programSentences) console.log(`   ${sentence}`);
  }
  console.log('');
}

if (outIndex >= 0) {
  const out = args[outIndex + 1];
  writeFileSync(resolve(out), `${JSON.stringify({
    source: file, model: evidence.model ?? evidence.config?.model ?? null,
    status: evidence.status, runs: rows.map(({ text, ...rest }) => rest),
  }, null, 2)}\n`, 'utf8');
  console.log(`summary written to ${out}`);
}
