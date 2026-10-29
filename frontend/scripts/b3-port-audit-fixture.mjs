// Port-audit negative fixture (review 20, P3): the harness port's own updates
// contract must reject an out-of-order merged batch BEFORE it reaches the
// transport — the product's mergeUpdatesStages throws on index <= last
// (frontend/src/lib/world-engine/schedule.ts:356), both scenes run the merged
// path through checkUpdatesStages, and the v3 action scene died exactly there
// via the port audit. The judge self-tests (b3-judges.mjs, 28 cases) cover the
// judge side; this fixture covers the port side of the same rule.
//
// The port audit is an inline closure inside the page evaluate, so the fixture
// slices the audit source out of run-world-b3.mjs mechanically and evaluates
// it here: a drift between the port and this fixture turns the test red.
//
//   node scripts/b3-port-audit-fixture.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const harness = readFileSync(new URL('./run-world-b3.mjs', import.meta.url), 'utf8');
const start = harness.indexOf('const auditUpdates = (out, expectedStage');
const end = harness.indexOf('\n    H.auditUpdates = auditUpdates;', start);
assert.ok(start >= 0 && end > start, 'updates arm not found in the harness source');
const auditSource = harness.slice(start, end).trimEnd();
// The slice starts at `const auditUpdates = (...) => {` — strip the LHS and
// arrow so `new Function` receives a plain function expression.
const arrowIdx = auditSource.indexOf('=>');
// CR-NL to NL, then re-add the parameter list as a plain function expression
// (`new Function('return ({...})')` would read the block as an object literal).
const body = auditSource.slice(arrowIdx + 2).replaceAll(String.fromCharCode(13, 10), String.fromCharCode(10))
  .trim().replace(/;$/, '');
const portAudit = new Function('taskOwnersOf', 'isObject', 'UPDATE_STAGES', 'UPDATE_FIELDS',
  `"use strict"; return (function (out, expectedStage, roster, taskOwners = {}) ${body});`)(
  (state) => {
    const owners = {};
    for (const [actorId, actor] of Object.entries(state?.characters ?? {})) {
      for (const taskId of Object.keys(actor.tasks ?? {})) owners[taskId] = actorId;
    }
    return owners;
  },
  (value) => value != null && typeof value === 'object' && !Array.isArray(value),
  ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity'],
  { position: ['positionSet'], appearance: ['appearanceChanges'], tasks: ['tasksAchieved'], subtasks: ['subtasksAdded'], personality: ['personalityChanges'], sanity: ['sanitySet'] });

const roster = new Set(['person_a', 'person_c']);
const owners = { task_watch: 'person_a', task_pressure: 'person_c' };
const results = [];
const check = (name, audit, expectMatch) => {
  results.push({ name, error: audit.error });
  if (expectMatch) assert.match(String(audit.error), expectMatch, `${name}: unexpected error`);
  else assert.equal(audit.error ?? null, null, `${name}: expected a pass`);
};

// 1) legal canonical batch passes
check('canonical three-stage batch passes',
  portAudit([
    { stage: 'tasks', changes: { person_c: { tasksAchieved: ['task_pressure'] } } },
    { stage: 'personality', changes: { person_c: { personalityChanges: [{ id: 'c1', text: '更沉稳', supersedes: [] }] } } },
    { stage: 'sanity', changes: { person_c: { sanitySet: 8 } } },
  ], null, roster, owners));

// 2) the exact v3 action shape: appearance AFTER tasks (the killing batch)
check('v3 action batch (appearance after tasks) fails with the product reason',
  portAudit([
    { stage: 'tasks', changes: { person_a: { tasksAchieved: [] } } },
    { stage: 'appearance', changes: { person_a: { appearanceChanges: [] } } },
    { stage: 'subtasks', changes: { person_a: { subtasksAdded: [] } } },
  ], null, roster, owners), /out-of-order\/duplicate stage appearance/);

// 3) disorderly batch (sanity first) reports the second call (sanity→tasks)
check('sanity-then-tasks reports the tasks violation',
  portAudit([
    { stage: 'sanity', changes: { person_c: { sanitySet: 8 } } },
    { stage: 'tasks', changes: { person_c: { tasksAchieved: ['task_pressure'] } } },
  ], null, roster, owners), /out-of-order\/duplicate stage tasks/);

// 4) duplicate stage fails
check('duplicate stage fails',
  portAudit([
    { stage: 'tasks', changes: { person_c: { tasksAchieved: ['task_pressure'] } } },
    { stage: 'tasks', changes: { person_c: { tasksAchieved: ['task_pressure'] } } },
  ], null, roster, owners), /out-of-order\/duplicate stage tasks/);

// 5) a declared split-stage single call still passes (stage pinned by enum)
check('declared split-stage call passes',
  portAudit({ stage: 'tasks', changes: { person_c: { tasksAchieved: ['task_pressure'] } } }, 'tasks', roster, owners));

// 6) illegal stage still fails
check('field-name-as-stage fails',
  portAudit([{ stage: 'appearanceChanges', changes: {} }], null, roster, owners), /illegal stage/);

console.log(`[b3-port-audit] ${results.length} checks, all as expected`);
console.log(`[b3-port-audit] audit source sha256 ${new (await import('node:crypto')).createHash('sha256')
  .update(auditSource).digest('hex')} (sliced live from run-world-b3.mjs)`);
for (const entry of results) console.log(`  - ${entry.name}: ${entry.error ?? 'ok'}`);