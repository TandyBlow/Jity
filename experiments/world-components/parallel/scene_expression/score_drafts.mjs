// 用冻结判分器给 30 份初稿打分，并复核“初稿 = 调用输出 + 程序句”。
// 用法（仓库根）：
//   tsc frontend/src/lib/world-engine/runtime/narration-split-eval.ts \
//     --target ES2020 --lib dom,dom.iterable,esnext --strict --skipLibCheck \
//     --esModuleInterop --module commonjs --moduleResolution node \
//     --outDir experiments/world-components/parallel/scene_expression/step4/scorer-build
//   node experiments/world-components/parallel/scene_expression/score_drafts.mjs
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..', '..', '..');
const STEP3 = join(HERE, 'step3');
const STEP4 = join(HERE, 'step4');
const BUILD = join(STEP4, 'scorer-build', 'runtime');

// ---- 与冻结协议第 10 节一致：判分器内部词表（逐字复制，含注释来源）----
// 来源：frontend/src/lib/world-engine/runtime/narration-split-eval.ts
const FUNCTION_TOKENS = ['过去了', '约', '从', '来到了', '来到', '完成了任务', '有了一个新任务',
  '理智值', '升为', '降为', '变得', '一个', '又'];
const FUNCTION_CHARS = /[的从了又约一个任务：、，。！？；\s「」]/g;
const UNIT_CN = { second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年' };
const CN_SMALL = ['零', '一', '两', '三', '四', '五', '六', '七', '八', '九', '十'];
const cnNum = (n) => (Number.isInteger(n) && n >= 0 && n <= 10 ? CN_SMALL[n] : String(n));

const readJson = (p) => JSON.parse(readFileSync(p, 'utf8'));
const readJsonl = (p) => readFileSync(p, 'utf8').split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));
const sha = (buf) => createHash('sha256').update(buf).digest('hex');

const evalMod = await import(pathToFileURL(join(BUILD, 'narration-split-eval.js')).href);
const samplesMod = await import(pathToFileURL(join(BUILD, 'narration-split-samples.js')).href);
const samples = new Map(samplesMod.NARRATION_SPLIT_SAMPLES.map((s) => [s.id, s]));

const selfTest = evalMod.scorerSelfTest();
const selfTestFailed = selfTest.filter((r) => !r.pass);
if (selfTestFailed.length) {
  throw new Error(`判分器自检未全过，停止评分: ${JSON.stringify(selfTestFailed)}`);
}

const materials = readJson(join(HERE, 'frozen/materials.json'));
const inputs = readJson(join(HERE, 'frozen/inputs.json'));
const calls = readJsonl(join(STEP3, 'calls.jsonl'));
const drafts = readJsonl(join(STEP3, 'drafts.jsonl'));

// ---- 1. 初稿完整性：调用记录 → 拼接规则 → 初稿 ----
const finish = (raw) => {
  const text = raw.trim();
  if (![...text].some((c) => /[A-Za-z0-9\u4e00-\u9fff]/.test(c))) return '';
  if (/[。！？]$/.test(text)) return text.replace(/[。！？]+$/, '') + text.slice(-1);
  return text.replace(/[，、；,.;：]+$/, '') + '。';
};
const byCall = new Map(calls.map((c) => [c.callId, c]));
const problems = [];
for (const d of drafts) {
  const parts = [];
  for (const slot of inputs[d.sampleId].slots) {
    if (slot.owner === 'program') {
      parts.push(slot.programText);
      continue;
    }
    const call = byCall.get(`${d.sampleId}/${d.arm}/${inputs[d.sampleId].slots.indexOf(slot)}`);
    if (!call) { problems.push(`missing call ${d.sampleId}/${d.arm}`); continue; }
    if (call.composedText !== finish(call.rawText)) problems.push(`normalise mismatch ${call.callId}`);
    const part = d.parts.find((p) => p.callId === call.callId);
    if (!part || part.text !== call.composedText) problems.push(`draft part mismatch ${call.callId}`);
    parts.push(call.composedText);
  }
  if (parts.join('') !== d.text) problems.push(`draft text mismatch ${d.sampleId}/${d.arm}`);
}
if (problems.length) throw new Error(`初稿与调用记录不一致（${problems.length}）: ${problems.slice(0, 5)}`);

// ---- 2. 共享授权词表（不区分该臂是否呈现），三臂同一张表 ----
const materialTokens = (sid) => {
  const set = new Set();
  const m = materials[sid];
  for (const group of ['location', 'items', 'characters']) {
    for (const item of m[group]) {
      set.add(item.text);
      if (item.name) set.add(item.name);
    }
  }
  return set;
};

const baseTokens = (sample) => {
  const tokens = new Set([cnNum(sample.timeAdvance.duration.amount), UNIT_CN[sample.timeAdvance.duration.unit]]);
  for (const e of Object.values(sample.before.initial.characters)) tokens.add(e.name);
  for (const e of Object.values(sample.before.initial.items)) tokens.add(e.name);
  for (const e of Object.values(sample.before.initial.locations)) tokens.add(e.name);
  for (const [eid, d] of Object.entries(sample.delta)) {
    for (const c of [...(d.appearanceChanges ?? []), ...(d.personalityChanges ?? [])]) {
      if (c.text != null) tokens.add(c.text);
    }
    for (const tid of d.tasksAchieved ?? []) {
      const goal = sample.before.characters[eid]?.tasks[tid]?.goal;
      if (goal) tokens.add(goal);
    }
    for (const t of d.subtasksAdded ?? []) tokens.add(t.goal);
    if (d.sanitySet != null) tokens.add(String(d.sanitySet));
  }
  if (sample.requiredFacts.some((f) => f.kind === 'timeReached' && f.hour === 12)) tokens.add('中午');
  return tokens;
};

const residue = (sentence, tokens) => {
  let rest = sentence;
  for (const tok of [...tokens].sort((a, b) => b.length - a.length)) rest = rest.split(tok).join('');
  for (const tok of FUNCTION_TOKENS) rest = rest.split(tok).join('');
  return rest.replace(FUNCTION_CHARS, '');
};

// ---- 3. 打分 ----
const rows = drafts.map((d) => {
  const sample = samples.get(d.sampleId);
  const evaluation = evalMod.evaluateNarration(sample, d.text);
  const tokens = new Set([...baseTokens(sample), ...materialTokens(d.sampleId)]);
  const sentences = d.text.split('。').map((s) => s.trim()).filter(Boolean);
  const unsupported = sentences.filter((s) => residue(s, tokens).length > 0);
  return {
    sampleId: d.sampleId, arm: d.arm, programOnly: d.programOnly, text: d.text,
    factChecks: evaluation.factChecks, omissions: evaluation.omissions,
    historicalFabricationFlags: evaluation.fabricationFlags,
    unsupportedDetails: unsupported, repetition: evaluation.repetition,
  };
});

const byArm = {};
for (const arm of 'ABC') {
  const rowsArm = rows.filter((r) => r.arm === arm);
  byArm[arm] = {
    drafts: rowsArm.length,
    modelsDrafts: rowsArm.filter((r) => !r.programOnly).length,
    omissions: rowsArm.reduce((n, r) => n + r.omissions.length, 0),
    draftsWithOmission: rowsArm.filter((r) => r.omissions.length > 0).length,
    historicalFabricationFlags: rowsArm.reduce((n, r) => n + r.historicalFabricationFlags.length, 0),
    unsupportedDetailSentences: rowsArm.reduce((n, r) => n + r.unsupportedDetails.length, 0),
    draftsWithUnsupportedDetail: rowsArm.filter((r) => r.unsupportedDetails.length > 0).length,
  };
}

mkdirSync(STEP4, { recursive: true });
const out = {
  scoredAt: new Date().toISOString(),
  scorer: {
    source: 'frontend/src/lib/world-engine/runtime/narration-split-eval.ts',
    build: 'step4/scorer-build（tsc --strict --target ES2020 --module commonjs）',
    buildHashes: Object.fromEntries(['narration-split-eval.js', 'narration-split-samples.js', 'narration-split.js']
      .map((f) => [f, sha(readFileSync(join(BUILD, f)))])),
    selfTest,
    selfTestPassed: selfTest.every((r) => r.pass),
  },
  integrity: { calls: calls.length, drafts: drafts.length, problems },
  byArm,
  rows,
};
writeFileSync(join(STEP4, 'scores.json'), JSON.stringify(out, null, 1) + '\n', 'utf8');

console.log(JSON.stringify({ selfTestPassed: out.scorer.selfTestPassed, integrity: out.integrity.byArm, calls: calls.length, drafts: drafts.length, problems: problems.length }, null, 1));
console.log(JSON.stringify(byArm, null, 1));
for (const r of rows) {
  if (r.omissions.length || r.unsupportedDetails.length) {
    console.log(`${r.sampleId}/${r.arm} omit=${JSON.stringify(r.omissions)} residue=${JSON.stringify(r.unsupportedDetails)} hist=${JSON.stringify(r.historicalFabricationFlags)}`);
  }
}
