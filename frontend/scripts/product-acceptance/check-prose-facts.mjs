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
      if (/没有|未|无|不带/u.test(part.slice(Math.max(0, at - 8), at))) return false;
      // "记下别人的识别带颜色" is not a claim he wears one.
      const between = part.slice(part.indexOf(name), at);
      if (/[一-龥]{2,4}的$/u.test(between) && between !== `${name}的`) return false;
      return true;
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

  // Invented atmosphere: sensory words the prose adds that the settled facts
  // never carried (run77's trained arm wrote 夕阳/汗/泥土/机械运转声). The word
  // list is deliberately narrow: every hit must be absent from the prompt.
  for (const term of ['夕阳', '暮色', '晨光', '月光', '星光', '风声', '气味', '汗', '泥土', '焦糊', '脚步声', '心跳', '寒意', '霉味', '血腥味']) {
    if (prompt.includes(term) || !prose.includes(term)) continue;
    const at = prose.indexOf(term);
    flags.push({ kind: 'invented_detail', quote: prose.slice(Math.max(0, at - 12), at + term.length + 12).slice(0, 60) });
  }

  // Position claim: the prose moves the protagonist to a registered place other
  // than the committed one. run92 t8 wrote 二层平台 while the state still said
  // 西侧服务巷. Places inside one complex count as the same place, so a climb
  // inside the tower is not flagged.
  const committed = /路明非现在在([^，。；\n]+)/u.exec(prompt)?.[1]?.trim() ?? '';
  const placeFamilies = [
    ['钟楼', '钟楼门厅', '二层平台', '顶层旗台'],
    ['西侧服务巷', '服务巷检修口'],
    ['器材棚'],
    ['西回廊'],
    ['庭院'],
    ['跨溪小桥'],
    ['西侧器材区'],
    ['医护附楼'],
  ];
  const moved = /(走进|走到|走上|上到|上了|进了|进入|跑到|赶到|穿过|站在|停在|爬)/u;
  if (committed) {
    const home = placeFamilies.find((names) => names.includes(committed)) ?? [committed];
    for (const place of placeFamilies.flat()) {
      if (home.includes(place)) continue;
      const clause = clauses(prose).find((part) => part.includes('路明非') && part.includes(place) && moved.test(part));
      if (clause) flags.push({ kind: 'place_claim', quote: clause.slice(0, 60), committed: committed.slice(0, 20) });
    }
  }

  // Item owner claim: the protagonist handling an item the prompt attributes to
  // someone else (run92 t5: 诺诺's 短枪 became 路明非's). Attribution is read at
  // the prompt's clause level: the item's clause names the owner, and no clause
  // gives the same item to the protagonist.
  const promptClauses = prompt.split(/[。\n]/u);
  for (const [owner, item, named] of [
    ['诺诺', '短枪', /短枪|枪口/u], ['诺诺', '短讯机', /短讯机|短讯/u], ['芬格尔', '相机', /相机/u],
    ['秦越', '器材笼钥匙', /器材笼钥匙|笼钥匙/u], ['林亦舟', '演习枪', /演习枪/u],
  ]) {
    const itemClauses = promptClauses.filter((part) => part.includes(item));
    if (!itemClauses.length) continue;
    if (!itemClauses.some((part) => part.includes(owner))) continue;
    if (itemClauses.some((part) => part.includes('路明非') && !part.includes(owner))) continue;
    const clause = clauses(prose).find((part) => part.includes('路明非') && named.test(part) && !part.includes(owner));
    if (clause) flags.push({ kind: 'item_owner_claim', quote: clause.slice(0, 60), item });
  }

  // Unknown-entity claim: a name the player introduced that the world does not
  // contain. The settlement may refuse the act (unknown entity) while the prose
  // still writes it; run40-e is the measured case. Dev gate only.
  const introduced = [...input.matchAll(/(?:给|向|让|跟)([一-龥]{2,3})/gu)].map((match) => match[1]);
  const unknown = [...new Set(introduced)]
    .filter((name) => !knownNames.has(name) && !/^(他|她|它|自己|裁判|大家)/u.test(name) && !/[的了着过]/u.test(name));
  for (const name of unknown) {
    if (!prose.includes(name)) continue;
    const clause = clauses(prose).find((part) => part.includes(name));
    if (clause && !/没有|没找到|没见到|未能|未被|被拒|拒绝|无法/u.test(clause)) {
      flags.push({ kind: 'unknown_entity_claim', quote: clause.slice(0, 60) });
    }
  }

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
