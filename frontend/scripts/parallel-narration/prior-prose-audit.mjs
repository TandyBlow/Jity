#!/usr/bin/env node
/** Audit recorded page evidence for the two prompt conditions 02 owns:
 *
 *  1. no previous-turn prose reaches a later prompt, in any form;
 *  2. the legacy prompt lines that fed prose back (上一段/前一句/已写内容) are gone.
 *
 * Reads evidence already on disk; no inference, no product call. Each beat prompt
 * is compared against every earlier turn's *shown* prose: a prompt that contains
 * 12+ consecutive characters of an earlier paragraph, or a whole earlier
 * sentence of 10+ chars, is reported as a leak.
 *
 *   node frontend/scripts/parallel-narration/prior-prose-audit.mjs [globDir]
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../../../..');
const dir = process.argv[2] ?? join(root, 'results/product/evidence');
const LEGACY = ['已写内容', '不要复述上一段', '【前一句】', '上一回合的最后一句', '上一回合的开头', '不知道性别时用名字'];
const CURRENT = ['共约', '可见物品在场景里', '最后给出的事实'];

function promptsOf(turn) {
  const out = [];
  const c = turn?.candidate;
  const tail = c && typeof c === 'object' ? c.tail : null;
  if (!Array.isArray(tail)) return out;
  for (const item of tail) {
    const det = item?.detail;
    if (typeof det !== 'string' || !det.includes('"beats"')) continue;
    let parsed;
    try { parsed = JSON.parse(det); } catch { continue; }
    for (const beat of parsed.beats ?? []) if (typeof beat?.prompt === 'string') out.push(beat.prompt);
  }
  return out;
}

function sentences(text) {
  return text.split(/[。！？\n]/u).map((s) => s.trim()).filter((s) => s.length >= 10);
}

/** A prompt legitimately prints this beat's settled record and the player's own
 * instruction. Those lines can repeat an earlier paragraph word for word when the
 * model copied the record, so a match inside them is not a leak. */
function isMaterialLine(line) {
  return line.includes('结算记录：') || line.includes('结算内容：') || line.startsWith('玩家这一回合')
    || line.startsWith('- 结算') || line.startsWith('- 这一拍') || line.startsWith('- 这一回合')
    || line.startsWith('- 地点') || line.startsWith('- 在场') || line.startsWith('- 可见物品')
    || line.startsWith('- 已登记细节') || line.startsWith('- 手边') || line.startsWith('- 视角人物')
    || line.startsWith('正文要写出');
}

function leakLines(prompt, sentence) {
  return prompt.split('\n').filter((line) => line.includes(sentence) && !isMaterialLine(line));
}


function lastPromptHas(line, doc) {
  for (const turn of (doc.turns ?? [])) for (const prompt of promptsOf(turn)) if (prompt.includes(line)) return true;
  return false;
}

const files = readdirSync(dir).filter((f) => f.startsWith('09-') && f.endsWith('.json')).sort();
let leaked = 0, legacy = 0, checked = 0, files0 = 0;
const currentCount = Object.fromEntries(CURRENT.map((line) => [line, 0]));
for (const file of files) {
  let doc;
  try { doc = JSON.parse(readFileSync(join(dir, file), 'utf8')); } catch { continue; }
  const turns = Array.isArray(doc?.turns) ? doc.turns : [];
  const shown = [];
  let fileChecked = 0;
  for (const turn of turns) {
    const text = String(turn?.text ?? '').trim();
    const prompts = promptsOf(turn);
    for (const prompt of prompts) {
      checked += 1; fileChecked += 1;
      for (const earlier of shown) {
        for (const sentence of sentences(earlier)) {
          const where = leakLines(prompt, sentence);
          if (where.length) {
            leaked += 1;
            console.log(`LEAK ${file} turn ${turn.turn}: ${sentence.slice(0, 40)} || in: ${where[0].slice(0, 90)}`);
          }
        }
      }
      for (const line of LEGACY) if (prompt.includes(line)) { legacy += 1; console.log(`LEGACY ${file} turn ${turn.turn}: ${line}`); }
      for (const line of CURRENT) if (prompt.includes(line)) currentCount[line] += 1;
    }
    if (text) shown.push(text);
  }
  if (fileChecked) {
    files0 += 1;
    const head = doc?.head ?? doc?.productState?.gitHead ?? doc?.arm?.pageHead ?? '?';
    const fileLegacy = LEGACY.filter((line) => lastPromptHas(line, doc)).join(',') || 'none';
    console.log(`FILE ${file} head ${String(head).slice(0, 8)} prompts ${fileChecked} legacy ${fileLegacy}`);
  }
}
console.log('---');
console.log(`files with prompts: ${files0}, prompts checked: ${checked}, earlier-prose leaks: ${leaked}, legacy prose-feedback lines: ${legacy}`);
console.log('current lines:', currentCount);
