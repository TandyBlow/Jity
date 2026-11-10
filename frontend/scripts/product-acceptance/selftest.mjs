// Harness self-test for the 09 acceptance driver.
//
// This serves a *fixture page* that imitates the product's visible structure so
// the driver's completion detection, timing, history and refresh checks can be
// exercised without spending a GPU lease. It is NOT a product page and its
// evidence is labelled `harness-selftest`; it must never be quoted as
// acceptance. The fixture deliberately writes its own text and state the same
// way the driver expects to read them, so a selector break fails here first.
//
//   node scripts/product-acceptance/selftest.mjs

import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../../../..');

const PAGE = `<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>fixture</title></head>
<body><main id="root"></main>
<script>
const SAVE='jity.world.local.snapshot.v1';
const state = JSON.parse(localStorage.getItem(SAVE) || 'null') || { history: 0, place: '西侧服务巷', sanity: 62, turns: [] };
function render() {
  document.getElementById('root').innerHTML = \`
  <header><h1>fixture</h1><button id="reset">重新开始</button></header>
  <section><div><div><div><span>\${state.place}</span><span id="stage">\${state.history ? '本轮完成。' : '等待输入…'}</span></div>
  <div id="entries"></div></div>
  <textarea id="input"></textarea>
  <button id="act">行动</button></div>
  <aside><div><div>路明非</div><div>精神值：\${state.sanity}</div><div>地点：\${state.place}</div>
  <div>在附近</div><div>诺诺、林亦舟</div><div>当前任务</div><ul><li>问清红蓝局势</li></ul></div>
  <div>本地存档<div>已行动：\${state.history} 次</div></div></aside></section>\`;
  const entries = document.getElementById('entries');
  for (const turn of state.turns) {
    entries.insertAdjacentHTML('beforeend', \`<article><div>你：\${turn.input}</div><div style="white-space:pre-wrap">\${turn.text}</div>\${turn.note ? '<div>正文已按已结算事实修正：'+turn.note+'</div>' : ''}</article>\`);
  }
  document.getElementById('act').onclick = submit;
}
async function submit() {
  const input = document.getElementById('input').value.trim();
  if (!input) return;
  document.getElementById('input').value = '';
  const entry = { input, text: '', note: null };
  state.turns.push(entry);
  const stage = document.getElementById('stage');
  const entries = document.getElementById('entries');
  entries.insertAdjacentHTML('beforeend', \`<article><div>你：\${input}</div><div style="white-space:pre-wrap"></div></article>\`);
  const body = entries.lastElementChild.lastElementChild;
  stage.textContent = '结算中：结算';
  await new Promise((r) => setTimeout(r, 250));
  stage.textContent = '正在写正文';
  const full = 'fixture 正文：' + input.slice(0, 40) + '。风从巷口吹过来，路明非站着没动。';
  for (let i = 1; i <= full.length; i += 8) {
    body.textContent = full.slice(0, i);
    await new Promise((r) => setTimeout(r, 20));
  }
  body.textContent = full;
  entry.text = full;
  state.history += 1;
  state.place = state.history % 3 === 0 ? '西回廊' : state.place;
  state.sanity = Math.min(100, state.sanity + 1);
  localStorage.setItem(SAVE, JSON.stringify(state));
  stage.textContent = '本轮完成。';
}
document.getElementById('reset').onclick = () => { localStorage.removeItem(SAVE); location.reload(); };
render();
</script></body></html>`;

const server = createServer((request, response) => {
  if (request.url?.startsWith('/world-local')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    response.end(PAGE);
    return;
  }
  response.writeHead(404);
  response.end('not found');
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const base = `http://127.0.0.1:${server.address().port}`;

const dir = mkdtempSync(resolve(tmpdir(), 'accept-selftest-'));
const turnsPath = resolve(dir, 'turns.json');
const outPath = resolve(dir, 'evidence.json');
const turns = [
  { id: 'f1', purpose: 'first turn', input: '我先看一眼巷口，不移动。' },
  { id: 'f2', purpose: 'move', input: '我沿低墙走到器材棚。' },
  { id: 'f3', purpose: 'mid-settle refresh', input: '我进器材棚，找林亦舟。', refreshMidSettleMs: 300 },
  { id: 'f4', purpose: 'after refresh', input: '我问林亦舟脚踝怎么样。' },
];
import { writeFileSync } from 'node:fs';
writeFileSync(turnsPath, JSON.stringify(turns, null, 2));

// The fixture has no /models, so the model assertion is expected to fire; this
// self-test only checks the turn machinery.
const child = spawn(process.execPath, [
  resolve(here, 'accept-world-local.mjs'),
  '--base', base,
  '--turns', turnsPath,
  '--out', outPath,
  '--intent', 'harness-selftest',
  '--harness-selftest',
  '--turn-timeout-ms', '30000',
  '--ready-timeout-ms', '30000',
  '--refresh-timeout-ms', '30000',
], { cwd: resolve(here, '../..') });
let stderr = '';
child.stderr.on('data', (chunk) => { stderr += String(chunk); process.stderr.write(chunk); });
child.stdout.on('data', (chunk) => process.stdout.write(chunk));
const status = await new Promise((done) => child.on('close', done));
server.close();

const evidence = JSON.parse(readFileSync(outPath, 'utf8'));
const checks = [
  ['four turn records', evidence.turns.length === 4],
  ['first turn has text', Boolean(evidence.turns[0]?.text)],
  ['timing recorded', evidence.turns[0]?.timings?.firstReadableMs > 0],
  ['streaming stage seen', /正在写正文/.test(evidence.turns[0]?.stageSequence ?? '')],
  ['history increments', evidence.turns[0]?.historyDelta === 1],
  ['mid-refresh recorded', evidence.turns[2]?.problems?.includes('mid_settle_refresh')],
  ['mid-refresh restored without losing history', (evidence.turns[2]?.refreshMidSettle?.historyDelta ?? -1) >= 0],
  ['refresh restore kept entries', evidence.refreshRestore?.entriesKept === true],
  ['cancel control absence flagged', evidence.failures.some((failure) => /cancel/.test(failure.message))],
  ['kind labelled selftest', evidence.harness?.selfTest === true],
];
let failed = 0;
for (const [label, ok] of checks) {
  if (!ok) failed += 1;
  console.log(`[${ok ? 'ok' : 'FAIL'}] ${label}`);
}
console.log(`[selftest] ${failed === 0 ? 'PASS' : `FAIL (${failed})`} evidence=${outPath}`);
if (status !== 0 && failed === 0) console.log('[selftest] driver exit', status, stderr.slice(-400));
process.exit(failed === 0 ? 0 : 2);
