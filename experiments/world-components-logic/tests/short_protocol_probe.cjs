/* Actual B consumer probe. Inputs are synthetic engineering fixtures, not models. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../..');
const options = Object.fromEntries(process.argv.slice(2).reduce((pairs, arg, i, all) => {
  if (arg.startsWith('--')) pairs.push([arg.slice(2), all[i + 1]]);
  return pairs;
}, []));
const tsPath = options.typescript || process.env.JITY_TYPESCRIPT_MODULE ||
  path.join(root, 'frontend/node_modules/typescript');
const ts = require(tsPath);
const packet = JSON.parse(fs.readFileSync(0, 'utf8'));
const files = {
  schedule: 'frontend/src/lib/world-engine/schedule.ts',
  decoder: 'frontend/src/lib/world-engine/runtime/structured-output.ts',
  contract: 'design/world-protocol/v2/api-contract.json',
};
const sources = Object.fromEntries(Object.entries(files).map(([key, value]) => [key, fs.readFileSync(path.join(root, value), 'utf8')]));
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const compiled = {};
for (const key of ['schedule', 'decoder']) {
  const output = ts.transpileModule(sources[key], {
    fileName: files[key], reportDiagnostics: true,
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true},
  });
  const errors = (output.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error);
  assert.equal(errors.length, 0, 'actual consumer transpile errors: ' + errors.map(e => e.messageText).join(';'));
  compiled[key] = output.outputText;
}
function executeProbe(modules, contract, packet) {
  const cache = {};
  function load(name) {
    if (cache[name]) return cache[name].exports;
    const module = {exports: {}}; cache[name] = module;
    const requireLocal = dep => {
      if (dep === '../schedule') return load('schedule');
      if (dep === '../../../../design/world-protocol/v2/api-contract.json') return contract;
      throw new Error('undeclared consumer dependency: ' + dep);
    };
    new Function('require', 'module', 'exports', modules[name])(requireLocal, module, module.exports);
    return module.exports;
  }
  const decoder = load('decoder'), schedule = load('schedule');
  const stable = value => JSON.stringify(value, (_key, nested) => nested && typeof nested === 'object' && !Array.isArray(nested)
    ? Object.fromEntries(Object.entries(nested).sort(([a], [b]) => a.localeCompare(b))) : nested);
  const checks = packet.cases.map(row => {
    try {
      const raw = ['reaction', 'narration'].includes(row.task) ? row.value : JSON.stringify(row.value);
      const decoded = decoder.decodeTaskOutput(row.task, raw, row.constraints);
      if (row.expectReject) throw new Error('invalid candidate was accepted');
      if (stable(decoded) !== stable(row.value)) throw new Error('decoder changed candidate');
      return {id: row.id, task: row.task, passed: true, outcome: 'accepted_exact_value'};
    } catch (error) {
      if (row.expectReject && error.name === 'StructuredOutputError') return {id: row.id, task: row.task, passed: true, outcome: 'rejected_invalid_shape', reason: error.reason};
      return {id: row.id, task: row.task, passed: false, outcome: 'failure', reason: String(error)};
    }
  });
  const x = packet.updatesComparison;
  try {
    const merged = schedule.mergeUpdatesStages(x.calls);
    const actual = schedule.assembleCandidates({groupId: x.groupId, actorIds: x.actorIds, roster: x.roster, deltas: merged});
    if (stable(actual) !== stable(x.expected)) throw new Error('new candidate differs from existing scheduler assembly');
    const checked = schedule.checkUpdatesStages({taskIds: new Set(x.taskIds), changeIds: new Set(x.changeIds)}, x.calls);
    if (!checked.ok) throw new Error('actual scheduler found dangling references: ' + JSON.stringify(checked.dangling));
    checks.push({id: 'scheduler-six-stage-consumption', passed: true, outcome: 'exact_candidate_match'});
  } catch (error) { checks.push({id: 'scheduler-six-stage-consumption', passed: false, reason: String(error)}); }
  try {
    schedule.mergeUpdatesStages([x.calls[1], x.calls[0]]);
    checks.push({id: 'scheduler-order-rejection', passed: false, reason: 'out-of-order accepted'});
  } catch (_) { checks.push({id: 'scheduler-order-rejection', passed: true, outcome: 'rejected'}); }
  return {scope: 'actual_decoder_and_scheduler_engineering_only', semanticEvidence: false,
    realModelCalls: 0, fullBrowserChain: false, passed: checks.every(c => c.passed), checks};
}
const result = executeProbe(compiled, JSON.parse(sources.contract), packet);
result.sourceIdentity = Object.fromEntries(Object.entries(files).map(([k, value]) => [value, sha(sources[k])]));
result.environment = {node: process.version, typescript: ts.version};
if (options.html) {
  const embed = value => JSON.stringify(value).replaceAll('<', '\\u003c');
  const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>D 短语义协议探针</title>
<style>body{font:16px system-ui,sans-serif;margin:40px auto;padding:0 24px;max-width:1000px;color:#1d2c3b;background:#f7fafc}h1{font-size:28px}p{line-height:1.7}.badge{display:inline-block;padding:7px 14px;background:#e8edf4;border-radius:20px}button{padding:10px 20px;border:1px solid #b6c5d6;border-radius:6px;background:white}table{width:100%;border-collapse:collapse;background:white;margin-top:24px}td,th{border-bottom:1px solid #e1e6ed;text-align:left;padding:12px}.pass{color:#167044}.fail{color:#a32323}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}</style>
<h1>D 短语义协议探针</h1><p class="badge">工程测试夹具 · 不代表模型能力</p><p>读取本分支实际输出解码器和调度器，核对新组件候选能否按既有协议消费。没有调用模型、服务、数据库或 C 叙事；没有进行完整请求计时。</p><button id="rerun">重新核验</button><h2 id="status"></h2><table><thead><tr><th>检查</th><th>结果</th></tr></thead><tbody id="rows"></tbody></table><details><summary>代码身份</summary><pre id="identity"></pre></details>
<script>const probe=${executeProbe.toString()};const modules=${embed(compiled)};const contract=${embed(JSON.parse(sources.contract))};const packet=${embed(packet)};const sourceIdentity=${embed(result.sourceIdentity)};
function render(){const result=probe(modules,contract,packet);window.__probeResult=result;document.getElementById('status').textContent=(result.passed?'通过':'失败')+'：'+result.checks.filter(x=>x.passed).length+' / '+result.checks.length;const body=document.getElementById('rows');body.replaceChildren();for(const row of result.checks){const tr=document.createElement('tr');const id=document.createElement('td');id.textContent=row.id;const outcome=document.createElement('td');outcome.className=row.passed?'pass':'fail';outcome.textContent=(row.passed?'通过 · ':'失败 · ')+(row.reason||row.outcome);tr.append(id,outcome);body.append(tr);}document.getElementById('identity').textContent=JSON.stringify(sourceIdentity,null,2);}document.getElementById('rerun').onclick=render;render();</script></html>`;
  fs.writeFileSync(options.html, html, {flag: 'wx'});
  result.browserArtifact = path.resolve(options.html);
}
process.stdout.write(JSON.stringify(result, null, 2) + '\n');
if (!result.passed) process.exitCode = 1;
