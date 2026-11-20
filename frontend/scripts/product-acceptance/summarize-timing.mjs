// Summarize acceptance run JSONs into artifacts/goal/timing-baseline.json.
// Reads the driver's own output; invents no clocks. A missing clock stays null
// and fails the gate instead of being filled from a different measurement.
//
//   node frontend/scripts/product-acceptance/summarize-timing.mjs \
//     --runs artifacts/goal/timing-runs/cold-1.json,artifacts/goal/timing-runs/points-10.json \
//     --out artifacts/goal/timing-baseline.json

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const arg = (name, fallback = null) => {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const root = resolve(new URL('../../..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const runs = (arg('--runs', '') || '').split(',').map((item) => item.trim()).filter(Boolean)
  .map((item) => resolve(item));
const out = resolve(arg('--out', resolve(root, 'artifacts/goal/timing-baseline.json')));

const FIRST_READABLE_LIMIT_MS = 60_000;
const POINT_LIMIT_MS = 300_000;
const mb = (bytes) => (bytes == null ? null : Math.round(bytes / 1048576));

function generationPick(turn) {
  const list = Array.isArray(turn.generations) ? turn.generations : [];
  const narration = list.find((entry) => /narrat/i.test(String(entry?.engine ?? entry?.label ?? '')))
    ?? list.at(-1) ?? null;
  const gaps = list.map((entry) => entry?.maxStreamGapMs).filter((value) => typeof value === 'number');
  return {
    firstTokenAtMs: narration?.firstTokenMs ?? null,
    firstReadableAtMs: narration?.firstReadableMs ?? null,
    longestStreamGapMs: gaps.length ? Math.max(...gaps) : null,
    wallMs: narration?.wallMs ?? null,
    finishReason: narration?.finishReason ?? null,
    streamChunks: narration?.streamChunks ?? null,
  };
}

function stageRows(turn) {
  const calls = turn.submission?.calls ?? turn.product?.submission?.calls ?? [];
  return calls.map((call) => ({ task: call.task, key: call.key, stage: call.stage ?? null, ms: Math.round(call.ms ?? 0), fallback: Boolean(call.fallback) }));
}

const coldStarts = [];
const points = [];
const sources = [];
for (const file of runs) {
  if (!existsSync(file)) throw new Error(`run file missing: ${file}`);
  const evidence = JSON.parse(readFileSync(file, 'utf8'));
  sources.push({ file: file.replaceAll('\\', '/'), runId: evidence.runId, status: evidence.status, intent: evidence.intent, turnsFile: evidence.turnsFile });
  if (evidence.status === 'PREFLIGHT' || (Array.isArray(evidence.turns) && evidence.turns.length === 0)) {
    coldStarts.push({
      file: file.replaceAll('\\', '/'), runId: evidence.runId, startedAt: evidence.startedAt,
      readyMs: evidence.readyMs, crossOriginIsolated: evidence.environment?.crossOriginIsolated ?? null,
      adapter: evidence.environment?.adapter ?? null, models: evidence.models ?? null,
      jsHeapAtReady: evidence.jsHeapAtReady ?? null, arm: evidence.arm ?? null,
    });
    continue;
  }
  for (const turn of evidence.turns ?? []) {
    const record = turn.product ?? null;
    const generation = generationPick(turn);
    const commit = record?.pointCommittedAtMs ?? null;
    const pointNarration = record?.pointNarration ?? null;
    const completions = Object.values(pointNarration ?? {}).map((slot) => slot?.completedAtMs).filter((value) => typeof value === 'number');
    // Per-point completion, not the first accepted point: a later point can
    // settle while an earlier text is still writing, and the 300 s gate is per point.
    const finished = completions.length ? Math.max(...completions) : (record?.acceptedMs ?? null);
    const finishMinusCommit = finished != null ? finished - (commit ?? 0) : null;
    const firstReadablePass = record?.firstReadableAtMs != null && record.firstReadableAtMs <= FIRST_READABLE_LIMIT_MS;
    const pointPass = finishMinusCommit != null && finishMinusCommit <= POINT_LIMIT_MS;
    // A point clock only proves timing when the turn actually finished. A stop
    // after the first point's prose means the round's later point never
    // committed; counting that as a timing pass hid the settlement failure.
    const turnIncomplete = String(turn.message ?? '').startsWith('本轮停止')
      || (turn.problems ?? []).some((problem) => /submit_refused|over_300s|turn_timeout|deadline/i.test(problem))
      || (turn.stages ?? []).some((stage) => /295 秒时限/.test(String(stage.label ?? '')))
      || (turn.submission?.stops ?? []).some((stop) => /AbortError|settlement_failed/.test(stop));
    points.push({
      run: evidence.runId, turn: turn.turn, id: turn.id, input: turn.input, purpose: turn.purpose,
      inputAt: turn.submittedAt,
      clocks: {
        pointCommittedAtMs: commit,
        narrationStartedAtMs: record?.narrationStartedAtMs ?? null,
        firstReadableAtMs: record?.firstReadableAtMs ?? null,
        firstReadableSource: record?.firstReadableSource ?? null,
        pointTextFinishedAtMs: finished,
        firstAcceptedAtMs: record?.acceptedMs ?? null,
        pointTextFinishedMinusCommitMs: finishMinusCommit,
        completionSource: completions.length ? 'pointNarration.max' : 'acceptedMs',
        pointNarration: pointNarration ?? null,
        driverDoneMs: turn.timings?.doneMs ?? null,
        commitMissing: commit == null,
      },
      firstTokenAtMs: generation.firstTokenAtMs,
      longestStreamGapMs: generation.longestStreamGapMs,
      generation: { wallMs: generation.wallMs, finishReason: generation.finishReason, streamChunks: generation.streamChunks },
      stages: stageRows(turn),
      uiStages: turn.stages ?? [],
      peakMemoryMB: mb(turn.jsHeap?.usedJSHeapSize),
      modelId: record?.modelId ?? turn.modelId ?? null,
      narrationModel: record?.narrationModel ?? null,
      source: record?.source ?? null,
      continuationDecision: turn.submission?.continuationDecision ?? record?.submission?.continuationDecision ?? null,
      submissionCalls: (turn.submission?.calls ?? []).length,
      problems: turn.problems ?? [],
      turnIncomplete,
      excluded: turn.refreshMidSettle ? 'mid_settle_refresh' : (turn.cancelled ? 'cancelled' : null),
    });
  }
}

const timedAll = points.filter((point) => point.excluded == null && point.clocks.pointTextFinishedAtMs != null);
// One scenario counted once: a rerun of the same turn id supersedes the earlier
// attempt (the input is the unit, not the page load).
const byId = new Map();
for (const point of timedAll) byId.set(point.id, point);
const timed = [...byId.values()];
const firstGate = timed.map((point) => point.clocks.firstReadableAtMs).filter((value) => value != null);
const pointGate = timed.map((point) => point.clocks.pointTextFinishedMinusCommitMs).filter((value) => value != null);
const pass = timed.length >= 10
  && timed.every((point) => !point.turnIncomplete)
  && timed.every((point) => point.clocks.firstReadableAtMs != null && point.clocks.firstReadableAtMs <= FIRST_READABLE_LIMIT_MS)
  && timed.every((point) => point.clocks.pointTextFinishedMinusCommitMs != null && point.clocks.pointTextFinishedMinusCommitMs <= POINT_LIMIT_MS);

const summary = {
  kind: 'jity-goal-timing-baseline',
  generatedAt: new Date().toISOString(),
  thresholds: { firstReadableMs: FIRST_READABLE_LIMIT_MS, pointTextMs: POINT_LIMIT_MS },
  sources,
  coldStarts,
  points,
  gates: {
    evaluatedPoints: timed.length,
    firstReadable: {
      evaluated: firstGate.length, failed: timed.filter((point) => !(point.clocks.firstReadableAtMs != null && point.clocks.firstReadableAtMs <= FIRST_READABLE_LIMIT_MS)).length,
      worstMs: firstGate.length ? Math.max(...firstGate) : null,
    },
    pointText: {
      evaluated: pointGate.length, failed: timed.filter((point) => !(point.clocks.pointTextFinishedMinusCommitMs != null && point.clocks.pointTextFinishedMinusCommitMs <= POINT_LIMIT_MS)).length,
      worstMs: pointGate.length ? Math.max(...pointGate) : null,
    },
    turnCompletion: {
      evaluated: timed.length,
      failed: timed.filter((point) => point.turnIncomplete).length,
      ids: timed.filter((point) => point.turnIncomplete).map((point) => point.id),
    },
    autoChainPoints: timed.filter((point) => point.continuationDecision === 'continue').length,
    status: pass ? 'PASS' : 'FAIL_OR_INCOMPLETE',
  },
};

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary.gates, null, 2));
console.log(`[timing] ${out}`);
if (!pass) process.exitCode = 1;
