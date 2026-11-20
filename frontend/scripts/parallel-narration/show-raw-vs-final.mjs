#!/usr/bin/env node
/**
 * Print, for one narration evidence file, what the model actually wrote and
 * what the product would have shown — and which sentences changed, so the
 * difference between generation, sentence-level repair and assembly is
 * visible instead of guessed.
 *
 *   node scripts/parallel-narration/show-raw-vs-final.mjs <evidence.json> [--json]
 */
import { readFileSync } from 'node:fs';

const file = process.argv[2];
if (!file) {
  console.error('usage: show-raw-vs-final.mjs <evidence.json> [--json]');
  process.exit(2);
}
const evidence = JSON.parse(readFileSync(file, 'utf8'));
const asJson = process.argv.includes('--json');

const sentences = (text) => (text ?? '')
  .split(/[。！？\n]+/u).map((part) => part.trim()).filter(Boolean);

const report = (evidence.runs ?? []).map((run) => {
  const attempts = (run.attempts ?? []).map((attempt) => ({
    attempt: attempt.attempt,
    accepted: attempt.accepted,
    chars: (attempt.raw ?? '').replace(/\s/gu, '').length,
    durationMs: attempt.durationMs ?? null,
    raw: (attempt.raw ?? '').trim(),
    hard: (attempt.issues ?? []).filter((issue) => issue.severity === 'hard').map((issue) => issue.kind),
    soft: (attempt.issues ?? []).filter((issue) => issue.severity === 'soft').map((issue) => issue.kind),
    repairedFrom: (attempt.repairedIssues ?? []).map((issue) => ({ kind: issue.kind, detail: issue.detail ?? null })),
  }));
  const final = (run.text ?? '').trim();
  // Compare against the attempt the product actually used, not blindly the
  // first one: a repaired second attempt is the text the page would show.
  const used = attempts.find((attempt) => attempt.accepted && attempt.raw === final)
    ?? attempts.find((attempt) => attempt.accepted)
    ?? attempts[0];
  const firstRaw = used?.raw ?? '';
  const rawSentences = new Set(sentences(firstRaw));
  const finalSentences = sentences(final);
  const kept = finalSentences.filter((sentence) => rawSentences.has(sentence));
  const added = finalSentences.filter((sentence) => !rawSentences.has(sentence));
  const dropped = [...rawSentences].filter((sentence) => !finalSentences.includes(sentence));
  return {
    scenario: run.id ?? run.scenario ?? null,
    status: run.status ?? null,
    accepted: run.accepted ?? null,
    finalChars: final.replace(/\s/gu, '').length,
    firstTextMs: run.firstTextMs ?? null,
    wallMs: run.wallMs ?? null,
    attempts,
    final,
    comparedAttempt: used?.attempt ?? null,
    change: {
      keptSentences: kept.length,
      addedSentences: added,
      droppedSentences: dropped,
      origin: added.length || dropped.length
        ? 'the final text is not the first raw draft: see repairedIssues (sentence-level repair) and the dropped/added sentences'
        : 'the final text is the first raw draft; whatever is wrong with it came from generation, not from editing',
    },
  };
});

if (asJson) {
  console.log(JSON.stringify(report, null, 2));
} else {
  for (const item of report) {
    console.log(`\n=== ${item.scenario} | ${item.status} | accepted=${item.accepted} | ${item.finalChars} chars | first ${Math.round(item.firstTextMs ?? 0)} ms / wall ${Math.round(item.wallMs ?? 0)} ms`);
    for (const attempt of item.attempts) {
      console.log(`\n-- attempt ${attempt.attempt} (accepted=${attempt.accepted}, ${attempt.chars} chars, ${Math.round(attempt.durationMs ?? 0)} ms)`);
      console.log(`   hard: ${attempt.hard.join(', ') || 'none'} | soft: ${attempt.soft.length}`);
      console.log(`   RAW: ${attempt.raw}`);
      for (const repair of attempt.repairedFrom) console.log(`   REPAIRED-FROM [${repair.kind}]: ${repair.detail}`);
    }
    console.log(`\n-- FINAL PROSE (${item.finalChars} chars):\n${item.final}`);
    console.log(`\n-- CHANGE: kept ${item.change.keptSentences} sentence(s)`);
    for (const sentence of item.change.droppedSentences) console.log(`   dropped: ${sentence}`);
    for (const sentence of item.change.addedSentences) console.log(`   added:   ${sentence}`);
    console.log(`   origin:  ${item.change.origin}`);
  }
}
