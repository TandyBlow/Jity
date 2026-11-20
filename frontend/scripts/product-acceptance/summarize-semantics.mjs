// Summarize one semantics run into artifacts/goal/semantics/<stamp>.json.
// Reads the driver's own turn evidence; classifies each case and flags hard
// semantic violations. It never re-runs the model and never fills a missing
// value.

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const arg = (name, fallback = null) => {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const root = resolve(new URL('../../..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const runFile = resolve(arg('--run', resolve(root, 'artifacts/goal/semantics/run-20261120.json')));
const out = resolve(arg('--out', runFile.replace(/\.json$/, '-summary.json')));
const evidence = JSON.parse(readFileSync(runFile, 'utf8'));

const VIOLATIONS = [
  [/unknown character/i, 'unknown_entity'],
  [/duplicate task decision/i, 'duplicate_task_decision'],
  [/context_capacity_exceeded/i, 'context_overflow'],
  [/conflicting positions/i, 'position_conflict'],
  [/request_malformed/i, 'malformed_request'],
  [/personality changes and sanity recalculation must pair/i, 'personality_sanity_pair'],
];

const violations = [];
const turns = (evidence.turns ?? []).map((turn) => {
  const product = turn.product ?? {};
  const submission = turn.submission ?? product.submission ?? null;
  const calls = (submission?.calls ?? []).map((call) => ({
    task: call.task, key: call.key, stage: call.stage ?? null, ms: Math.round(call.ms ?? 0),
    fallback: Boolean(call.fallback), error: call.error ?? null,
    rawChars: typeof call.raw === 'string' ? call.raw.length : (call.rawChars ?? null),
    raw: typeof call.raw === 'string' ? call.raw.slice(0, 4000) : null,
    attempts: Array.isArray(call.attempts) ? call.attempts.length : null,
    stageMs: call.stageMs ?? null, coverage: call.coverage ?? null,
  }));
  const judge = turn.offscreenJudge ?? null;
  const deadlineAbort = (turn.stages ?? []).some((stage) => /295 秒时限/.test(stage.label ?? ''))
    || (submission?.stops ?? []).some((stop) => /AbortError/.test(stop));
  const rows = judge?.rows ?? [];
  const acts = rows.filter((row) => row.decision === 'act');
  const skips = rows.filter((row) => row.decision === 'skip');
  const repeated = [...new Set(acts.map((row) => row.actorId))].filter((id) => acts.filter((row) => row.actorId === id).length > 1);
  const seen = [];
  const flag = (code, detail) => { seen.push({ code, detail: String(detail).slice(0, 240) }); violations.push({ turn: turn.turn, id: turn.id, code, detail: String(detail).slice(0, 240) }); };
  for (const call of calls) {
    const text = `${call.error ?? ''} ${call.raw ?? ''}`;
    for (const [pattern, code] of VIOLATIONS) if (pattern.test(text)) flag(code, `${call.task}:${call.key} ${call.error ?? ''}`);
  }
  for (const problem of turn.problems ?? []) {
    for (const [pattern, code] of VIOLATIONS) if (pattern.test(problem)) flag(code, problem);
  }
  for (const line of turn.console ?? []) {
    if (!line.includes('[world-local refusal]')) continue;
    for (const [pattern, code] of VIOLATIONS) if (pattern.test(line)) flag(code, line.slice(0, 240));
  }
  const automaticCommitted = Object.values(turn.after?.transportPoints ?? {}).some((point) => point?.trigger === 'automatic');
  if (repeated.length && automaticCommitted) seen.push({ code: 'repeated_actor_across_rounds', detail: repeated.join(',') });
  else if (repeated.length) flag('repeated_actor', repeated.join(','));
  return {
    turn: turn.turn, id: turn.id, input: turn.input, purpose: turn.purpose,
    acceptedMs: product.acceptedMs ?? null, doneMs: turn.timings?.doneMs ?? null,
    actionRows: rows.length,
    acts: acts.map((row) => ({ actorId: row.actorId, source: row.source, issueCode: row.issueCode ?? null })),
    skips: skips.map((row) => ({ actorId: row.actorId, source: row.source, issueCode: row.issueCode ?? null })),
    actionsSourceBasis: judge?.basis ?? 'none',
    calls,
    continuationDecision: submission?.continuationDecision ?? null,
    stops: submission?.stops ?? [],
    deadlineAbort,
    violations: seen,
    problems: turn.problems ?? [],
  };
});

const count = (list, key) => list.reduce((acc, item) => { const value = item[key] ?? 'none'; acc[value] = (acc[value] ?? 0) + 1; return acc; }, {});
const summary = {
  kind: 'jity-goal-semantics-summary',
  generatedAt: new Date().toISOString(),
  source: { runFile, runId: evidence.runId, status: evidence.status, intent: evidence.intent, turnsFile: evidence.turnsFile },
  environment: { userAgent: evidence.environment?.userAgent ?? null, adapter: evidence.environment?.adapter ?? null, isolated: evidence.environment?.crossOriginIsolated ?? null, arm: evidence.arm ?? null },
  totals: {
    turns: turns.length,
    withAcceptedProse: turns.filter((turn) => turn.acceptedMs != null).length,
    actionDecisions: turns.reduce((sum, turn) => sum + turn.actionRows, 0),
    calls: turns.reduce((sum, turn) => sum + turn.calls.length, 0),
    fallbacks: turns.reduce((sum, turn) => sum + turn.calls.filter((call) => call.fallback).length, 0),
    attemptsWithError: turns.reduce((sum, turn) => sum + turn.calls.filter((call) => (call.attempts ?? 0) > 1).length, 0),
    deadlineAborts: turns.filter((turn) => turn.deadlineAbort).length,
    continuation: count(turns.map((turn) => ({ decision: turn.continuationDecision })), 'decision'),
    violations: violations.length,
    violationKinds: count(violations.map((item) => ({ code: item.code })), 'code'),
  },
  violations,
  turns,
};

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary.totals, null, 2));
console.log(`[semantics] ${out}`);
