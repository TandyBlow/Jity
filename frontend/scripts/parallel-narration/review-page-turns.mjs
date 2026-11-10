// Descriptive review of the narration text a real page run produced.
//
//   node scripts/parallel-narration/review-page-turns.mjs \
//     ../../../results/product/evidence/09-product-10turn.json [--json out.json]
//
// This does not judge acceptance (lane 01 owns the standard). It counts and
// lists what a reader would check: pronoun use, invented-sense candidates,
// duplicated sentences across turns, dialogue share, length and per-turn
// prose source. Every number is derived from the evidence file as written.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const args = process.argv.slice(2);
const file = args.find((value) => !value.startsWith('--'));
if (!file) {
  console.error('usage: review-page-turns.mjs <page-evidence.json> [--json out.json]');
  process.exit(2);
}
const evidence = JSON.parse(readFileSync(resolve(file), 'utf8'));
const turns = evidence.turns ?? evidence.runs ?? [];
if (!turns.length) {
  console.error(`no turns in ${file}`);
  process.exit(1);
}

const SENTENCE = /[^。！？\n]+[。！？]?/gu;
const sentences = (text) => (text.match(SENTENCE) ?? []).map((value) => value.trim()).filter(Boolean);
const normalize = (text) => text.replace(/[\s，。！？；：、「」『』“”"'…—\-·]/gu, '');
const bigrams = (text) => {
  const clean = normalize(text);
  const grams = new Set();
  for (let i = 0; i < clean.length - 1; i += 1) grams.add(clean.slice(i, i + 2));
  return grams;
};
const overlap = (a, b) => {
  if (!a.size || !b.size) return 0;
  let shared = 0;
  for (const gram of a) if (b.has(gram)) shared += 1;
  return shared / Math.max(a.size, b.size);
};
// Sense nouns the writer can invent without a settled source. Listing them is
// not a verdict: the reviewer checks each against the turn's own input.
const SENSE = ['枪声', '脚步声', '风声', '心跳', '硝烟', '气味', '香味', '木香', '血腥', '回声', '铃声', '钟声', '水滴'];
const PRONOUN = /(?<![其])他(?![们])|她/gu;

const rows = [];
let previous = null;
for (const [index, turn] of turns.entries()) {
  const raw = turn.text ?? turn.narration ?? turn.prose ?? '';
  const text = String(raw ?? '');
  const list = sentences(text);
  const grams = bigrams(text);
  const echoed = [];
  for (const sentence of list) {
    const g = bigrams(sentence);
    for (const earlier of previous ?? []) {
      if (overlap(g, earlier.grams) >= 0.7) {
        echoed.push({ sentence, earlier: earlier.sentence, overlap: Number(overlap(g, earlier.grams).toFixed(2)) });
        break;
      }
    }
  }
  const senses = SENSE.filter((word) => text.includes(word));
  const notes = turn.note ?? null;
  const source = turn.narrationSource ?? turn.source ?? null;
  const row = {
    turn: turn.turn ?? index + 1,
    id: turn.id ?? null,
    chars: [...text].length,
    sentences: list.length,
    paragraphs: text.split(/\n{2,}/u).filter((value) => value.trim()).length,
    dialogueShare: text.includes('「') ? Number((([...text].length - [...text.replace(/「[^」]*」/gu, '')].length) / Math.max(1, [...text].length)).toFixed(2)) : 0,
    pronouns: (text.match(PRONOUN) ?? []).length,
    senses,
    echoed,
    source,
    note: notes,
    text,
  };
  rows.push(row);
  previous = [...(previous ?? []), ...list.map((sentence) => ({ sentence, grams: bigrams(sentence) }))];
}

for (const row of rows) {
  console.log(`turn ${String(row.turn).padStart(2)} chars=${String(row.chars).padStart(4)} sentences=${row.sentences} paras=${row.paragraphs} `
    + `pronouns=${row.pronouns} dialogue=${row.dialogueShare} source=${row.source ?? '-'}`
    + `${row.senses.length ? ` senses=${row.senses.join(',')}` : ''}${row.echoed.length ? ` echoed=${row.echoed.length}` : ''}`);
  if (row.echoed.length) {
    for (const item of row.echoed) console.log(`   echo(${item.overlap}) "${item.sentence}" ~ "${item.earlier}"`);
  }
  if (row.note) console.log(`   note: ${row.note}`);
}
console.log('');
for (const row of rows) console.log(`--- turn ${row.turn}\n${row.text || '(empty)'}\n`);

if (args.includes('--json')) {
  const out = args[args.indexOf('--json') + 1];
  writeFileSync(resolve(out), `${JSON.stringify({ source: file, turns: rows }, null, 2)}\n`, 'utf8');
  console.log(`written to ${out}`);
}
