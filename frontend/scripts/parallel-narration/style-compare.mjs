#!/usr/bin/env node
/** Descriptive style comparison: the accepted scenes against the reference
 * corpus. No score, no pass/fail; it reports the numbers a reader would use.
 *
 *   node scripts/parallel-narration/style-compare.mjs <samples.json> <corpus.jsonl>
 */
import fs from 'node:fs';

const samplesPath = process.argv[2];
const corpusPath = process.argv[3];
if (!samplesPath || !corpusPath) {
  console.error('usage: style-compare.mjs <samples.json> <corpus.jsonl>');
  process.exit(2);
}

const split = /[。！？]/u;
const stats = (text) => {
  const chars = [...text].length;
  const sentences = text.split(split).map((s) => s.trim()).filter(Boolean);
  const sentenceLens = sentences.map((s) => [...s].length);
  const dialogue = (text.match(/「[^」]*」/gu) ?? []).length;
  const commas = (text.match(/[，、]/gu) ?? []).length;
  const simile = (text.match(/(像|仿佛|似的|如同)/gu) ?? []).length;
  const perception = (text.match(/(看见|听见|闻到|觉得|感到|望着|盯着|看着)/gu) ?? []).length;
  const avg = sentenceLens.reduce((a, b) => a + b, 0) / (sentenceLens.length || 1);
  return {
    chars,
    sentences: sentences.length,
    avgSentence: Number(avg.toFixed(1)),
    maxSentence: sentenceLens.length ? Math.max(...sentenceLens) : 0,
    perSentenceComma: Number((commas / (sentences.length || 1)).toFixed(2)),
    dialogue,
    simile,
    perception,
  };
};

const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  if (!sorted.length) return null;
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : Number(((sorted[mid - 1] + sorted[mid]) / 2).toFixed(1));
};

const samples = JSON.parse(fs.readFileSync(samplesPath, 'utf8'));
const mine = Object.entries(samples).map(([id, sample]) => ({ id, ...stats(sample.final) }));

const corpus = fs.readFileSync(corpusPath, 'utf8').trim().split(/\r?\n/)
  .map((line) => JSON.parse(line)).map((row) => stats(String(row.targetText ?? '')));

const summary = (rows) => ({
  n: rows.length,
  charsMedian: median(rows.map((r) => r.chars)),
  sentenceMedian: median(rows.map((r) => r.sentences)),
  avgSentenceMedian: median(rows.map((r) => r.avgSentence)),
  maxSentenceMedian: median(rows.map((r) => r.maxSentence)),
  commaPerSentenceMedian: median(rows.map((r) => r.perSentenceComma)),
  dialogueShare: Number((rows.filter((r) => r.dialogue > 0).length / rows.length).toFixed(2)),
  simileShare: Number((rows.filter((r) => r.simile > 0).length / rows.length).toFixed(2)),
  perceptionShare: Number((rows.filter((r) => r.perception > 0).length / rows.length).toFixed(2)),
});

console.log(JSON.stringify({
  reference: summary(corpus),
  accepted: summary(mine),
  perScene: mine,
}, null, 2));
