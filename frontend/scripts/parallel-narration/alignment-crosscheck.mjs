// Read-only cross-check of the product's sentence alignment against the
// failure modes lane 10 measured on human gold prose (wrong_time on number
// substrings, dates inside a quoted task title, joint subjects).
//
//   npx tsx scripts/parallel-narration/alignment-crosscheck.mjs \
//     --tree ../06-recovery/frontend [--out out.json]
//
// It imports the alignment module from the given product tree, builds minimal
// committed packets, and reports which sentences the product path would treat
// as contradicting the settled facts. Nothing is written to that tree.
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { readFileSync, writeFileSync } from 'node:fs';

const args = process.argv.slice(2);
const option = (flag, fallback) => (args.includes(flag) ? args[args.indexOf(flag) + 1] : fallback);
const tree = resolve(option('--tree', '../06-recovery/frontend'));
const out = option('--out', '');
const module_ = await import(pathToFileURL(resolve(tree, 'src/lib/world-engine/runtime/narration-alignment.ts')).href);
const { alignNarration } = module_;

const anchor = { worldId: 'w', pointId: 'p1', version: 1, stateDigest: 'd', previousPointId: 'p0' };
const packet = (facts) => ({ anchor, facts });
const at = (name, location) => ({ id: `at:${name}`, kind: 'at', actorId: name, name, locationId: location, location });
const moved = (name, from, to) => ({ id: `moved:${name}`, kind: 'moved', actorId: name, name, fromId: from, from, toId: to, to });
const task = (name, goal) => ({ id: `task:${name}`, kind: 'task_achieved', actorId: name, name, taskId: `t:${name}`, goal });

const base = [at('秦既明', '借阅台'), at('韩照', '书库'), at('周书言', '书库'), at('温照', '书库')];

const cases = [
  {
    id: 'number-substring',
    why: 'Lane 10: 二十 also matches 十, so a correct sentence can read as the wrong duration.',
    facts: base, time: { amount: 20, unit: 'minute' },
    text: '二十分钟过去，地下书库的除湿机一直响着。',
  },
  {
    id: 'thirteen-minutes',
    why: 'Same substring bug with 十三 → 3.',
    facts: base, time: { amount: 13, unit: 'minute' },
    text: '十三分钟过去，雨点敲在报刊室的窗上。',
  },
  {
    id: 'date-in-task-title',
    why: 'Lane 10: a historical date inside a quoted task goal is read as this round’s duration.',
    facts: [...base, task('秦既明', '查清九八年秋天为什么换后门的锁')], time: { amount: 27, unit: 'minute' },
    text: '秦既明把「查清九八年秋天为什么换后门的锁」办完了。',
  },
  {
    id: 'joint-subject-task',
    why: 'Lane 10: three names sharing one predicate were read as an actor swap.',
    facts: [...base, task('韩照', '把三本缺页的书对照补字'), task('周书言', '把三本缺页的书对照补字'), task('温照', '把三本缺页的书对照补字')],
    time: { amount: 10, unit: 'minute' },
    text: '十分钟过去，韩照、周书言和温照都办完了「把三本缺页的书对照补字」。',
  },
  {
    id: 'accompany-verb',
    why: 'Lane 10: 答应/陪 sentences attributed the personality change to the wrong person.',
    facts: [...base, { id: 'p1', kind: 'personality_changed', actorId: '柏含章', name: '柏含章', changeId: 'c1', text: '遇事先替别人想' }],
    time: { amount: 10, unit: 'minute' },
    text: '柏含章答应陪周含章把那本簿子送去复印。',
  },
  {
    id: 'moved-then-standing',
    why: 'A move plus the destination restated is normal prose, not a contradiction.',
    facts: [...base, moved('秦既明', '借阅台', '报刊阅览室'), at('秦既明', '报刊阅览室')],
    time: { amount: 10, unit: 'minute' },
    text: '十分钟过去，秦既明离开借阅台，走进报刊阅览室，在窗边站住。',
  },
];

/** Product mode: run the product tree's alignment over the text one arm wrote
 * for the frozen fixture. Sentences it flags are the ones game-model.pruneNarration
 * would delete from that arm's output. */
const scenarioFile = option('--scenario', '');
const recordsFile = option('--records', '');
if (scenarioFile && recordsFile) {
  const scenario = JSON.parse(readFileSync(resolve(scenarioFile), 'utf8'));
  const records = JSON.parse(readFileSync(resolve(recordsFile), 'utf8')).runs ?? [];
  const policy = scenario.policy ?? {};
  const options = {
    roster: policy.roster ?? [],
    locations: policy.locations ?? [],
    knownPositions: policy.knownPositions ?? [],
    time: scenario.time?.duration ?? null,
    allowedEvents: [],
  };
  const rows = [];
  for (const record of records) {
    if (!record.text) continue;
    const result = alignNarration(scenario.committed, record.text, options);
    const flagged = result.violations.map((violation) => ({ kind: violation.kind, sentence: violation.sentence, detail: violation.detail }));
    rows.push({ id: record.id, accepted: record.accepted, chars: record.chars, flagged, omissions: result.omissions });
    console.log(`${flagged.length ? 'PRUNE' : 'keep '} ${record.id} accepted=${record.accepted} flagged=${flagged.length}`);
    for (const item of flagged) console.log(`   ${item.kind}: ${item.sentence}  (${item.detail})`);
  }
  if (out) {
    writeFileSync(resolve(out), `${JSON.stringify({ tree, scenario: scenarioFile, records: rows }, null, 2)}
`, 'utf8');
    console.log(`written to ${out}`);
  }
  process.exit(0);
}

const roster = base.map((fact) => fact.name).concat(['柏含章', '周含章', '韩照', '周书言', '温照']);
const locations = ['借阅台', '书库', '报刊阅览室', '地下书库', '装订间'];
const rows = [];
for (const item of cases) {
  const options = { roster: [...new Set(roster)], locations, time: item.time, allowedEvents: [] };
  const result = alignNarration(packet(item.facts), item.text, options);
  rows.push({
    id: item.id, why: item.why, text: item.text,
    violations: result.violations, omissions: result.omissions,
    timeExpressed: result.timeExpressed,
  });
}

for (const row of rows) {
  const problems = [...row.violations.map((value) => `violation:${value.kind ?? value.rule ?? JSON.stringify(value)}`),
    ...row.omissions.map((value) => `omission:${JSON.stringify(value)}`)];
  console.log(`${problems.length ? 'FLAG' : 'ok  '} ${row.id.padEnd(22)} ${problems.join(' | ') || '-'}`);
  if (problems.length) console.log(`     “${row.text}”`);
}
if (out) {
  writeFileSync(resolve(out), `${JSON.stringify({ tree, module: 'runtime/narration-alignment.ts', cases: rows }, null, 2)}\n`, 'utf8');
  console.log(`written to ${out}`);
}
