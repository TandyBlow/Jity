// G6 dev-only fact check: compares each turn's narration prose with the
// settled facts the narration prompt carried. Report only, no product change
// (D-004 keeps the raw output; this is the development gate the user chose).
// Usage: node scripts/product-acceptance/check-prose-facts.mjs --runs a.json,b.json --out report.json

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const arg = (name, fallback = null) => {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const runs = (arg('--runs', '') || '').split(',').map((item) => item.trim()).filter(Boolean).map((item) => resolve(root, item));
const out = resolve(root, arg('--out', 'artifacts/goal/narration/prose-facts-check.json'));

const NO_BAND = /([^\s（(，。；]+)（id=([^）)]+)）[^\n。]*没有[^\n。]*识别带/u;
const DOOR_OPEN = /门[^。；]{0,4}(敞开|开着|打开)/u;
const DOOR_SHUT = /门[^。；]{0,4}(紧闭|关着|锁着)/u;
const PLACEHOLDER = /〈[^〉]*(?:做了什么|谁回应)[^〉]*〉/u;
const META_NOTE = /(结算|回退|fallback|本拍|本组|模型未|无法确认|未产生)/u;
const ID_IN_PARENS = /（id=([^）)]+)）/gu;

function clauses(text) {
  return text.split(/[。！？；\n]/u).map((part) => part.trim()).filter((part) => part.length >= 6);
}

function checkTurn(turn) {
  const prose = (turn.text ?? '').trim();
  const input = (turn.input ?? '').trim();
  const prompt = turn.product?.narration?.prompt ?? '';
  const flags = [];
  if (!prose) return flags;

  if (input && prose.includes(input)) flags.push({ kind: 'input_echo', quote: input.slice(0, 40) });
  else {
    const inputClauses = input.split(/[。！？；，、]/u).map((part) => part.trim()).filter((part) => part.replace(/[，、；。！？\s]/gu, '').length >= 10);
    for (const part of inputClauses) {
      const bare = part.replace(/[，、；。！？\s]/gu, '');
      if (bare.length >= 10 && prose.replace(/[，、；。！？\s]/gu, '').includes(bare)) {
        flags.push({ kind: 'input_echo', quote: part.slice(0, 40) });
        break;
      }
    }
  }

  // Appearance text is one long line mixing several characters. Collect the
  // names the prompt itself uses, then attach each "没有…识别带" clause to the
  // nearest name before it. Dev gate only; every hit carries the quote.
  const knownNames = new Set();
  for (const match of prompt.matchAll(/([一-龥]{2,4})（id=/gu)) knownNames.add(match[1]);
  for (const match of prompt.matchAll(/([一-龥]{2,4})：/gu)) knownNames.add(match[1]);
  for (const match of prompt.matchAll(/让([一-龥]{2,4})做的事/gu)) knownNames.add(match[1]);
  for (const match of prompt.matchAll(/屋里有([一-龥]{2,4})的/gu)) knownNames.add(match[1]);
  const noBand = new Map();
  for (const match of prompt.matchAll(/没有[^。]{0,12}识别带/gu)) {
    const before = prompt.slice(Math.max(0, match.index - 60), match.index);
    const owner = [...knownNames].filter((name) => before.includes(name)).sort((a, b) => b.length - a.length)[0];
    if (owner) noBand.set(owner, { id: null, line: prompt.slice(Math.max(0, match.index - 60), match.index + 12) });
  }
  for (const [name, info] of noBand) {
    const pattern = new RegExp(`${name}[^。；]{0,24}识别带|识别带[^。；]{0,12}${name}`, 'u');
    const hit = clauses(prose).find((part) => {
      if (!pattern.test(part)) return false;
      // "他肩上没有阵营识别带" is the correct sentence, not a claim.
      const at = part.indexOf('识别带');
      return !/没有|未|无|不带/u.test(part.slice(Math.max(0, at - 8), at));
    });
    if (hit) flags.push({ kind: 'band_claim', quote: hit.slice(0, 60), promptLine: info.line.slice(0, 80) });
  }

  if (DOOR_OPEN.test(prompt)) {
    const hit = clauses(prose).find((part) => DOOR_SHUT.test(part));
    if (hit) flags.push({ kind: 'door_claim', quote: hit.slice(0, 60) });
  }

  const placeholder = prose.match(PLACEHOLDER);
  if (placeholder) flags.push({ kind: 'placeholder', quote: placeholder[0].slice(0, 40) });

  const meta = prose.match(META_NOTE);
  if (meta) flags.push({ kind: 'meta_note', quote: prose.slice(Math.max(0, meta.index - 20), meta.index + 30).slice(0, 60) });

  return flags;
}

const report = { kind: 'jity-prose-facts-check', at: new Date().toISOString(), runs: [], totals: {} };
for (const file of runs) {
  if (!existsSync(file)) {
    report.runs.push({ file, error: 'missing' });
    continue;
  }
  const evidence = JSON.parse(readFileSync(file, 'utf8'));
  const entry = { file: file.replaceAll('\\', '/'), runId: evidence.runId, arm: evidence.arm ?? null, turns: [] };
  for (const turn of evidence.turns ?? []) {
    const flags = checkTurn(turn);
    entry.turns.push({ id: turn.id, source: turn.product?.source ?? null, flags });
    for (const flag of flags) report.totals[flag.kind] = (report.totals[flag.kind] ?? 0) + 1;
  }
  report.runs.push(entry);
}
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(report, null, 2) + '\n');
const flagged = report.runs.flatMap((run) => run.turns ?? []).filter((turn) => turn.flags.length);
console.log(`[prose-facts] runs=${report.runs.length} turns=${report.runs.flatMap((run) => run.turns ?? []).length} flagged=${flagged.length}`);
console.log(JSON.stringify(report.totals));
console.log(`-> ${out}`);
