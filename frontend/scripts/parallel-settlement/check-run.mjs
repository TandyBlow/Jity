#!/usr/bin/env node
/**
 * Read-only checker for real /world-local runs, lane 04's part only.
 *
 * Input is the settlement ledger the page exposes after each submission
 * (`window.__worldSubmission`) or a file that wraps several of them. The
 * checker does not judge prose, and it never calls a model. It answers:
 *
 *   - did every submission run its common-group results and its six stages?
 *   - are the stages in the fixed order position → appearance → tasks →
 *     subtasks → personality → sanity, with no stage repeated or reordered?
 *   - do the task/personality answers cover the full cast (default 14)?
 *   - is a policy stop kept out of the model-handback record?
 *   - is the whole-submission timing recorded (not a model-only timer)?
 *
 * It exits 1 on any hard failure so a runner can gate on it.
 *
 *   node scripts/parallel-settlement/check-run.mjs <file.json> [--cast 14] [--task-rows 73]
 *   node scripts/parallel-settlement/check-run.mjs --self-test
 */
import { readFileSync } from 'node:fs';

const STAGES = ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity'];

function submissionsOf(input) {
  // A raw window.__worldTurns dump is an array of turn records; each record
  // carries its settlement ledger under `submission`.
  if (Array.isArray(input)) return input.map((item) => item?.submission ?? item).filter(Boolean);
  if (Array.isArray(input?.submissions)) return input.submissions;
  if (Array.isArray(input?.turns)) return input.turns.map((turn) => turn?.submission ?? turn).filter(Boolean);
  if (input?.submission) return [input.submission];
  if (input?.calls) return [input];
  return [];
}

/** A time-scan round has no actor action, so position/appearance are skipped by
 * design; every other round must start at position. */
function stageProblems(call, where) {
  const issues = [];
  const stages = Array.isArray(call.stages) ? call.stages : [];
  if (!stages.length) {
    issues.push(`${where}: updates call recorded no stage list`);
    return issues;
  }
  if (new Set(stages).size !== stages.length) issues.push(`${where}: a stage ran twice (${stages.join(',')})`);
  const start = stages[0] === 'tasks' ? 2 : 0;
  const expected = STAGES.slice(start, start + stages.length);
  if (stages.join(',') !== expected.join(',')) {
    issues.push(`${where}: stage order is ${stages.join(',')} but the fixed order is ${expected.join(',')}`);
  }
  return issues;
}

export function checkRun(input, options = {}) {
  const cast = options.cast ?? 14;
  const expectedTaskRows = Number(options.taskRows) || 0;
  const collectTimings = options.timings === true;
  const timingRows = [];
  const subs = submissionsOf(input);
  const hard = [];
  const soft = [];
  if (!subs.length) hard.push('no submission found in the input');
  subs.forEach((sub, index) => {
    const where = `submission ${index + 1}`;
    const calls = Array.isArray(sub.calls) ? sub.calls : [];
    if (!calls.length) {
      hard.push(`${where}: settlement ledger has no calls`);
      return;
    }
    const results = calls.filter((call) => call.task === 'results');
    const updates = calls.filter((call) => call.task === 'updates');
    const continuation = calls.filter((call) => call.task === 'continuation');
    if ((sub.resultsCalls ?? results.length) !== results.length) {
      hard.push(`${where}: resultsCalls=${sub.resultsCalls} but ${results.length} results records exist`);
    }
    if ((sub.updatesCalls ?? updates.length) !== updates.length) {
      hard.push(`${where}: updatesCalls=${sub.updatesCalls} but ${updates.length} updates records exist`);
    }
    if ((sub.continuationCalls ?? continuation.length) !== continuation.length) {
      hard.push(`${where}: continuationCalls=${sub.continuationCalls} but ${continuation.length} continuation records exist`);
    }
    if (!results.length) soft.push(`${where}: no results call (allowed only for a round without a frozen group)`);
    if (!updates.length) hard.push(`${where}: no six-stage updates call for a submission that settled a group`);
    for (const call of updates) {
      hard.push(...stageProblems(call, `${where} updates/${call.key}`));
      const coverage = call.coverage;
      if (!coverage) soft.push(`${where} updates/${call.key}: no coverage counts recorded`);
      else {
        if (coverage.tasks < cast) hard.push(`${where} updates/${call.key}: task coverage ${coverage.tasks} < cast ${cast}`);
        if (coverage.personality > 0 && coverage.personality < cast) {
          hard.push(`${where} updates/${call.key}: personality coverage ${coverage.personality} < cast ${cast}`);
        }
        if (coverage.taskRows != null && coverage.taskRows < coverage.tasks) {
          hard.push(`${where} updates/${call.key}: task rows ${coverage.taskRows} < characters ${coverage.tasks}`);
        }
        if (coverage.taskRows == null) soft.push(`${where} updates/${call.key}: taskRows not recorded (pre-04-15ac9d93 evidence)`);
        if (expectedTaskRows && Number(coverage.taskRows) !== expectedTaskRows) {
          hard.push(`${where} updates/${call.key}: task rows ${coverage.taskRows} != expected ${expectedTaskRows}`);
        }
        if (Array.isArray(coverage.achievedByCharacter)) {
          for (const row of coverage.achievedByCharacter) {
            if (!row || typeof row.characterId !== 'string' || !Array.isArray(row.taskIds)) {
              hard.push(`${where} updates/${call.key}: achievedByCharacter entry is not {characterId, taskIds}`);
              break;
            }
          }
          if (coverage.achievedByCharacter.length === coverage.tasks && (coverage.taskRows ?? 0) > coverage.tasks) {
            soft.push(`${where} updates/${call.key}: every one of ${coverage.tasks} characters achieved something; check the semantic decisions, not just coverage`);
          }
        } else {
          soft.push(`${where} updates/${call.key}: achievedByCharacter not recorded (pre-f97c90bc evidence)`);
        }
        if (coverage.rejectedTaskIds != null && !Array.isArray(coverage.rejectedTaskIds)) {
          hard.push(`${where} updates/${call.key}: rejectedTaskIds is not an array`);
        }
      }
      if (call.fallback) soft.push(`${where} updates/${call.key}: fell back (${call.error ?? 'no error text'})`);
      if (call.error) soft.push(`${where} updates/${call.key}: error ${call.error}`);
    }
    for (const call of results) {
      if (call.fallback) soft.push(`${where} results/${call.key}: failed, point aborted (${call.error ?? 'no error text'})`);
    }
    const decision = sub.continuationDecision ?? 'handback';
    if (decision === 'continue' && !continuation.length) hard.push(`${where}: decision is continue but no continuation call ran`);
    if (decision === 'failed' && continuation.length) soft.push(`${where}: continuation failed (no candidate; not a normal handback)`);
    const stops = Array.isArray(sub.stops) ? sub.stops : [];
    const policyStops = stops.filter((stop) => String(stop).includes('continuation_policy_'));
    if (policyStops.length) {
      const conclusion = sub.conclusion ?? sub.roundConclusion ?? null;
      if (conclusion?.kind === 'handback' || sub.closedBy === 'model') {
        hard.push(`${where}: policy stop ${policyStops.join(';')} was recorded as a model handback`);
      }
      soft.push(`${where}: policy stop ${policyStops.join(';')} (visible failure, no state rewrite expected)`);
    }
    if (collectTimings) {
      const stages = {};
      let updatesMs = 0;
      let resultsMs = 0;
      for (const call of calls) {
        if (call.task === 'updates') {
          updatesMs += Number(call.ms) || 0;
          for (const [stage, ms] of Object.entries(call.stageMs ?? {})) stages[stage] = (stages[stage] ?? 0) + Number(ms);
        }
        if (call.task === 'results') resultsMs += Number(call.ms) || 0;
      }
      timingRows.push({ submission: index + 1, input: sub.inputText ?? '', resultsMs: Math.round(resultsMs), updatesMs: Math.round(updatesMs), stages, submissionMs: typeof sub.startedAtMs === 'number' && typeof sub.endedAtMs === 'number' ? Math.round(sub.endedAtMs - sub.startedAtMs) : null });
    }
    const started = sub.startedAtMs;
    const ended = sub.endedAtMs;
    if (typeof started !== 'number' || typeof ended !== 'number') {
      soft.push(`${where}: whole-submission timing missing (startedAtMs/endedAtMs)`);
    } else if (ended < started) hard.push(`${where}: end time precedes start time`);
  });
  const result = { ok: hard.length === 0, submissions: subs.length, cast, hard, soft };
  if (collectTimings) {
    const totals = {};
    for (const row of timingRows) for (const [stage, ms] of Object.entries(row.stages)) totals[stage] = (totals[stage] ?? 0) + ms;
    result.timings = { rows: timingRows, totals };
  }
  return result;
}

function print(result) {
  console.log(JSON.stringify(result, null, 1));
}

function selfTest() {
  const good = JSON.parse(readFileSync(new URL('./fixtures/ledger-sample.json', import.meta.url), 'utf8'));
  const base = good.submission;
  const cases = [
    ['real ledger sample', base, true],
    ['narrowed cast', { ...base, calls: base.calls.map((call) => (
      call.task === 'updates' ? { ...call, coverage: { tasks: 13, personality: 13 } } : call
    )) }, false],
    ['reordered stages', { ...base, calls: base.calls.map((call) => (
      call.task === 'updates' ? { ...call, stages: ['appearance', 'position', 'tasks', 'subtasks', 'personality', 'sanity'] } : call
    )) }, false],
    ['policy stop as handback', { ...base, continuationDecision: 'policy_stop', stops: ['continuation:continuation_policy_no_progress'], closedBy: 'model' }, false],
    ['time scan round', { ...base, calls: base.calls.map((call) => (
      call.task === 'updates'
        ? { ...call, stages: ['tasks', 'subtasks'], coverage: { tasks: 14, personality: 0 } }
        : call
    )) }, true],
    ['raw __worldTurns array', [{ index: 1, submission: base }], true],
  ];
  let failed = 0;
  for (const [name, input, expected] of cases) {
    const result = checkRun(input);
    const pass = result.ok === expected;
    if (!pass) failed += 1;
    console.log(`${pass ? 'ok  ' : 'FAIL'} ${name}: ok=${result.ok} hard=${result.hard.length} soft=${result.soft.length}`);
    if (!pass) print(result);
  }
  if (failed) process.exitCode = 1;
}

const args = process.argv.slice(2);
if (args.includes('--self-test')) {
  selfTest();
} else {
  const file = args.find((arg) => !arg.startsWith('--'));
  if (!file) {
    console.error('usage: node check-run.mjs <file.json> [--cast 14] [--task-rows 73] [--timings]');
    process.exit(2);
  }
  const castIndex = args.indexOf('--cast');
  const cast = castIndex >= 0 ? Number(args[castIndex + 1]) : undefined;
  const rowsIndex = args.indexOf('--task-rows');
  const taskRows = rowsIndex >= 0 ? Number(args[rowsIndex + 1]) : undefined;
  const result = checkRun(JSON.parse(readFileSync(file, 'utf8')), {
    ...(cast ? { cast } : {}), ...(taskRows ? { taskRows } : {}), timings: args.includes('--timings'),
  });
  print(result);
  process.exitCode = result.ok ? 0 : 1;
}
