// 生成人工评审材料：固定种子的遮蔽顺序、空白选票、逐分句核验表。
// 只写 step4/；不改冻结文件，不预填任何人工结论。
// 用法（仓库根）：
//   node experiments/world-components/parallel/scene_expression/build_review_materials.mjs
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const STEP3 = join(HERE, 'step3');
const STEP4 = join(HERE, 'step4');
const SEED = 20261108;

const readJsonl = (p) => readFileSync(p, 'utf8').split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));
const sha = (s) => createHash('sha256').update(s).digest('hex');

// mulberry32：固定种子，任何机器上顺序一致
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = rng(SEED);
const shuffle = (arr) => {
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
};

const drafts = readJsonl(join(STEP3, 'drafts.jsonl'));
const inputs = JSON.parse(readFileSync(join(HERE, 'frozen/inputs.json'), 'utf8'));
const materials = JSON.parse(readFileSync(join(HERE, 'frozen/materials.json'), 'utf8'));

const bySample = new Map();
for (const d of drafts) {
  if (!bySample.has(d.sampleId)) bySample.set(d.sampleId, {});
  bySample.get(d.sampleId)[d.arm] = d;
}

// ---- 遮蔽顺序：每题三份文本随机排成 甲/乙/丙 ----
const labels = ['甲', '乙', '丙'];
const order = { seed: SEED, note: '顺序映射与选票分开保存；评审只看 ballot.json', permutations: {} };
const ballot = {
  question: '在事实表达不越权的前提下，哪份文字作为游戏当前时间点的叙事更连贯、读起来更像完整段落？不要因为长度更长就判优。',
  optionNoDifference: '看不出差别',
  instruction: '每题从 甲/乙/丙 中选一份，或选「看不出差别」；可写一句理由。不显示臂名。',
  seed: SEED,
  items: [],
};

for (const [sampleId, arms] of bySample) {
  const perm = shuffle(['A', 'B', 'C']);
  order.permutations[sampleId] = perm;
  ballot.items.push({
    sampleId,
    programOnly: inputs[sampleId].modelCallCount === 0,
    options: perm.map((arm, i) => ({ label: labels[i], text: arms[arm].text, sha256: sha(arms[arm].text) })),
    choice: null, reason: null,
  });
}

// ---- 逐分句核验表：全部标 undetermined，来源候选由素材/必述/程序句自动匹配 ----
const sourceIndex = (sid) => {
  const m = materials[sid];
  const out = [];
  for (const group of ['location', 'items', 'characters']) {
    for (const item of m[group]) out.push({ sourceId: item.sourceId, text: item.text });
  }
  return out;
};

const clauses = [];
for (const d of drafts) {
  const sources = sourceIndex(d.sampleId);
  const slots = inputs[d.sampleId].slots;
  const programTexts = slots.filter((s) => s.owner === 'program').map((s) => ({ kind: s.kind, text: s.programText }));
  const sentences = d.text.split('。').map((s) => s.trim()).filter(Boolean);
  sentences.forEach((clause, index) => {
    const candidates = [];
    for (const s of sources) {
      if (clause.includes(s.text) || s.text.includes(clause)) candidates.push(s.sourceId);
    }
    const program = programTexts.find((p) => p.text === `${clause}。`);
    if (program) candidates.push(`program:${program.kind}`);
    for (const slot of slots) {
      if (slot.owner !== 'model') continue;
      const key = slot.factLine.split('｜').slice(2).join('｜');
      if (key && clause.includes(key)) candidates.push(`fact:${slot.kind}:${slot.factLine}`);
    }
    clauses.push({
      sampleId: d.sampleId, arm: d.arm, clauseIndex: index, clause,
      label: 'undetermined',
      sourceId: [...new Set(candidates)],
      note: candidates.length ? '' : '自动匹配不到来源候选，需人工判断',
      human: { fluent: null, perspectiveOk: null, newAction: null, omission: null },
    });
  });
}

mkdirSync(join(STEP4, 'ballot'), { recursive: true });
writeFileSync(join(STEP4, 'ballot/order.json'), JSON.stringify(order, null, 1) + '\n', 'utf8');
writeFileSync(join(STEP4, 'ballot/ballot.json'), JSON.stringify(ballot, null, 1) + '\n', 'utf8');
writeFileSync(join(STEP4, 'clauses.jsonl'), clauses.map((c) => JSON.stringify(c)).join('\n') + '\n', 'utf8');

console.log(JSON.stringify({
  items: ballot.items.length,
  clauses: clauses.length,
  clausesWithoutCandidates: clauses.filter((c) => c.sourceId.length === 0).length,
  programOnlyItems: ballot.items.filter((i) => i.programOnly).length,
  seed: SEED,
}, null, 1));
