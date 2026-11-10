// Reads 09's real-page evidence JSON (`accept-world-local.mjs` output) and
// prints the action-family facts per turn: which model tasks ran, how long
// they took, whether a fallback/program answer was used, the round order when
// the page recorded it, and the staged player text.
//
// This is an analyzer, not a runner: it never starts a browser or a model and
// it never rewrites 09's file. Missing fields are reported as absent rather
// than guessed, so a run without `roundOrder` cannot look like a verified R06.
//
//   node scripts/parallel-actions/analyze-page-evidence.mjs --file <evidence.json>
//   node scripts/parallel-actions/analyze-page-evidence.mjs --self-test
import { readFileSync } from 'node:fs';

const TASKS = new Set(['action', 'targets', 'reaction']);

/** The page logs '[world-local task] action ally 5200ms fallback=false ' (see
 * page.tsx's onTask). A future line may append source=…; it is read when
 * present and reported as null when absent. */
export function parseTaskLine(line) {
  if (!line.includes('[world-local task]')) return null;
  const match = /\[world-local task\]\s+([a-z_]+)\s+(\S+)\s+(\d+)ms\s+fallback=(true|false)\s*(.*)$/.exec(line);
  if (!match) return null;
  const [, task, key, ms, fallback, rest] = match;
  const source = /\bsource=([a-z]+)/.exec(rest)?.[1] ?? null;
  const error = rest.replace(/\bsource=[a-z]+\b/, '').trim() || null;
  return { task, key, ms: Number(ms), fallback: fallback === 'true', source, error, raw: line.trim() };
}

/** One turn's action-family summary; every value is directly present in the evidence. */
export function summarizeTurn(turn) {
  // Prefer the page's structured per-turn list (`__worldTurns[i].actions`,
  // copied by 09 into `entry.actions` or `entry.product.actions`); fall back to
  // the console lines only when the structured list is absent.
  const structured = turn.actions ?? turn.product?.actions ?? null;
  const tasks = Array.isArray(structured)
    ? structured.map((entry) => ({
        task: entry.task ?? null, key: entry.key ?? null, ms: entry.ms ?? null,
        fallback: entry.fallback ?? null, source: entry.source ?? null,
        error: entry.error ?? null, raw: null,
      })).filter((entry) => TASKS.has(entry.task))
    : (turn.console ?? []).map(parseTaskLine).filter((entry) => entry && TASKS.has(entry.task));
  const round = turn.roundOrder ?? turn.submission?.roundOrder ?? turn.product?.roundOrder ?? null;
  // The page logs one [world-local task] action line per frozen slot, in the
  // order the controller visits them (offscreen skips are synchronous but still
  // awaited). Until the page records round.order, this sequence is the
  // observable order: a sanity order is not lexicographic.
  const observedOrder = [...new Set(tasks.filter((entry) => entry.task === 'action').map((entry) => entry.key))];
  const isAlphabetical = observedOrder.length > 2 && observedOrder.join(',') === [...observedOrder].sort().join(',');
  const texts = tasks.map((entry) => entry.raw ?? '').join('\n');
  return {
    turn: turn.turn ?? null,
    input: turn.input ?? null,
    roundOrder: round,
    observedOrder,
    observedOrderLooksAlphabetical: isAlphabetical,
    roundTrigger: turn.roundTrigger ?? turn.product?.roundTrigger ?? null,
    tasks,
    // source=program is a program decision even when fallback=false; only a
    // source=model (or, without source, fallback=false) is a model answer.
    modelCalls: tasks.filter((entry) => (entry.source ? entry.source === 'model' : entry.fallback === false)).length,
    fallbacks: tasks.filter((entry) => entry.fallback === true).length,
    errors: tasks.filter((entry) => entry.error).map((entry) => entry.error),
    // Program lines the page prints when a group member does not act.
    programSkips: (texts.match(/skip/g) ?? []).length,
    // The page's own reaction notice; its absence is not proof of a reaction.
    reactionNotices: (turn.text ?? '').match(/没有作出反应|反应/g)?.length ?? 0,
  };
}

export function summarize(evidence) {
  const turns = (evidence.turns ?? []).map(summarizeTurn);
  const calls = turns.reduce((sum, turn) => sum + turn.tasks.length, 0);
  const modelCalls = turns.reduce((sum, turn) => sum + turn.modelCalls, 0);
  const fallbacks = turns.reduce((sum, turn) => sum + turn.fallbacks, 0);
  return {
    productCommit: evidence.productCommit ?? evidence.commit ?? null,
    startedAt: evidence.startedAt ?? null,
    finishedAt: evidence.finishedAt ?? null,
    status: evidence.status ?? null,
    turns,
    totals: { turns: turns.length, actionFamilyCalls: calls, modelAnswers: modelCalls, fallbacks },
    // R06 evidence is only present when the page recorded the order.
    orderRecorded: turns.some((turn) => Array.isArray(turn.roundOrder)),
    orderFrozenAtNewPoint: null, // a human must compare two turns' orders; never inferred here
  };
}

const SAMPLE = {
  productCommit: 'ed2a93bb',
  status: 'DONE',
  turns: [
    {
      turn: 1, input: '我把护目镜推上去，盯着巷口。',
      console: [
        '[world-local task] action nono 5200ms fallback=false ',
        '[world-local task] targets nono 4100ms fallback=false ',
        '[world-local task] action fingel 0ms fallback=false ',
      ],
      text: '诺诺的演习短枪抵在你背上。“别动。”',
      submission: { roundOrder: ['lin', 'tang', 'shen', 'lu', 'zhou', 'fingel', 'nono'], roundTrigger: 'player' },
    },
    {
      turn: 2, input: '我走到器材棚门口，问芬格尔有没有备用电池。',
      console: [
        '[world-local task] action nono 0ms fallback=true timeout',
        '[world-local task] action fingel 6100ms fallback=false ',
        '[world-local task] targets fingel 3900ms fallback=false ',
        '[world-local task] reaction hero 3400ms fallback=false ',
      ],
      text: '芬格尔把电池抛给你，自己退到门边。',
      submission: { roundOrder: ['lin', 'tang', 'shen', 'lu', 'zhou', 'fingel', 'nono'], roundTrigger: 'player' },
    },
    {
      turn: 3, input: '我把护目镜戴好。',
      console: [],
      product: {
        roundOrder: ['lin', 'tang', 'shen', 'lu', 'zhou', 'fingel', 'nono'],
        roundTrigger: 'player',
        actions: [
          { task: 'action', key: 'lu', ms: 0, fallback: false, source: 'program', error: null },
        ],
      },
      text: '你戴上护目镜。',
    },
  ],
};

if (process.argv.includes('--self-test')) {
  const report = summarize(SAMPLE);
  const expected = {
    turns: 3,
    actionFamilyCalls: 8,
    modelAnswers: 6,
    fallbacks: 1,
    orderRecorded: true,
    observedOrder: ['nono', 'fingel'],
  };
  const actual = {
    turns: report.totals.turns,
    actionFamilyCalls: report.totals.actionFamilyCalls,
    modelAnswers: report.totals.modelAnswers,
    fallbacks: report.totals.fallbacks,
    orderRecorded: report.orderRecorded,
    observedOrder: report.turns[0].observedOrder,
  };
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    console.error('self-test failed', { actual, expected });
    process.exit(1);
  }
  console.log('self-test ok', JSON.stringify(actual));
} else {
  const at = process.argv.indexOf('--file');
  if (at < 0 || !process.argv[at + 1]) {
    console.error('usage: --file <evidence.json> | --self-test');
    process.exit(2);
  }
  const evidence = JSON.parse(readFileSync(process.argv[at + 1], 'utf8'));
  const report = summarize(evidence);
  console.log(JSON.stringify(report, null, 2));
  for (const turn of report.turns) {
    const parts = turn.tasks.map((entry) => `${entry.task}:${entry.key ?? '?'} ${entry.ms ?? '?'}ms${entry.fallback ? ' fallback' : ''}${entry.source ? ` source=${entry.source}` : ''}${entry.error ? ` error=${entry.error}` : ''}`);
    console.log(`t${turn.turn} ${turn.input ?? ''}\n  order: ${turn.roundOrder ? turn.roundOrder.join(' < ') : 'not recorded'}\n  ${parts.join(' | ') || 'no action-family task'}`);
  }
}
