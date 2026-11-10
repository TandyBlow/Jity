/** Replay one recorded product turn on the 07 program fallback, then read both
 * texts with lane 01's independent reviewer.
 *
 * The input is the real page turn recorded in
 * `results/product/evidence/09-product-10turn.json` (turn 1): the player walked
 * into the lane and the page showed a program fallback because settlement
 * could not confirm new results. 02's review of that text found three defects:
 * an internal status line in the body, a 5-paragraph shape, and an unlicensed
 * "stood there for a while" action.
 *
 * This script does not claim the page was fixed. It answers a narrower,
 * checkable question: on the same settled turn (same world, same place, no
 * state delta, the one minute the recorded text states), what does the 07
 * composer write, and what does 01's reviewer say about each text?
 *
 *   LANE01_ROOT=../../01-input LANE04_ROOT=../04-settlement \
 *     ./node_modules/.bin/jiti ./scripts/candidate-prose/fallback-same-input.ts
 *
 * Development evidence only: program prose, no model, not product acceptance.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { generateCandidate } from '../../src/lib/world-engine/local/narration-candidates/prose-composer/index';
import { rowFor01, type WorldState } from './row-for-01';

const lane04 = process.env.LANE04_ROOT
  ?? 'D:/others/Jity/.local/parallel-local-game/worktrees/04-settlement';
const lane01 = process.env.LANE01_ROOT
  ?? 'D:/others/Jity/.local/parallel-local-game/worktrees/01-input';
const evidencePath = process.env.EVIDENCE
  ?? 'D:/others/Jity/.local/parallel-local-game/results/product/evidence/09-product-10turn.json';

const load = async (root: string, modulePath: string) =>
  import(pathToFileURL(join(root, modulePath)).href) as Promise<Record<string, unknown>>;

const stateModule = await load(lane04, 'frontend/src/lib/world-engine/local/state.ts');
const constrained = await load(lane04, 'frontend/src/lib/world-engine/local/narration-candidates/constrained/index.ts');
const quality = await load(lane01, 'frontend/src/lib/world-engine/local/narration-quality/index.ts');
const gateModule = await load(lane01, 'frontend/src/lib/world-engine/local/narration-quality/gate.ts');

const buildInitialState = stateModule.buildInitialState as (initial: unknown) => WorldState;
const applyPoint = stateModule.applyPoint as (state: unknown, point: unknown) => WorldState;
const projectConstrainedScene = constrained.projectConstrainedScene as (
  after: unknown, before: unknown,
) => { base: unknown };
const reviewNarration = quality.reviewNarration as (args: {
  id: string; input: unknown; text: string;
}) => { findings: Array<{ kind: string; severity: string; detail: string }> };
const gateNarration = gateModule.gateNarration as (report: unknown, policy?: unknown) => { decision: string };

interface RecordedTurn {
  input?: string;
  text?: string;
  note?: string | null;
  purpose?: string;
  before?: { place?: string; sanity?: string };
  after?: { place?: string; sanity?: string };
}

const evidence = JSON.parse(readFileSync(evidencePath, 'utf8')) as { turns?: RecordedTurn[] };
const recorded = evidence.turns?.[0];
if (!recorded?.text) throw new Error(`no first recorded turn in ${evidencePath}`);

const world = JSON.parse(readFileSync(
  join(process.cwd(), '..', 'data', 'worlds', 'dragon-raja-free-day.world.json'),
  'utf8',
)) as { worldId: string; initial: unknown };

// The recorded turn changed no visible state: same place, same sanity, no task
// change. Its own text states one minute passed, so that is the only delta.
const before = buildInitialState(world.initial);
const point = {
  worldId: world.worldId,
  id: 'recorded_09_turn_1',
  sequence: 1,
  kind: 'normal',
  previousPointId: 'root',
  roundId: 'recorded_09_round_1',
  advanceId: 'recorded_09_advance_1',
  trigger: 'player',
  linkedFromPointId: null,
  timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
  entityDeltas: {},
} as Record<string, unknown>;
const after = applyPoint(before, point);
const beforeRead = {
  pointId: 'root', version: 0, state: before, stateDigest: 'root',
  previousPointId: null, timeAdvance: null, entityDeltas: {},
} as Record<string, unknown>;
const afterRead = {
  pointId: point.id, version: 1, state: after, stateDigest: 'recorded_09_turn_1',
  previousPointId: 'root', timeAdvance: point.timeAdvance, entityDeltas: point.entityDeltas,
};
const { base: committed } = projectConstrainedScene(afterRead, beforeRead);

const result = generateCandidate({
  committed: { ...(committed as Record<string, unknown>), state: after },
  state: after,
  beforeState: before,
  delta: { timeAdvance: point.timeAdvance },
  priorText: null,
  policy: { minChars: 12 },
} as never);

const row = rowFor01(before, after, 1);
const oldReport = reviewNarration({ id: 'recorded-old-fallback', input: row, text: recorded.text });
const newReport = reviewNarration({ id: 'recorded-07-fallback', input: row, text: result.text });
const oldGate = gateNarration(oldReport, {});
const newGate = gateNarration(newReport, {});
const kinds = (report: { findings: Array<{ kind: string; severity: string }> }) =>
  report.findings.filter((finding) => finding.severity !== 'review').map((finding) => finding.kind);

const forbidden = [
  { pattern: /本组结算|未能确认|结算未/u, why: 'internal settlement status in the body' },
  { pattern: /：/u, why: 'a field-style colon (dialogue belongs in 「」)' },
  { pattern: /站在原地|站了一会儿/u, why: 'an action the settled turn did not contain' },
];
const violations = forbidden.filter((entry) => entry.pattern.test(result.text));

console.log('===== recorded input');
console.log(`${recorded.input ?? '(unknown)'}  [${recorded.purpose ?? 'purpose not recorded'}]`);
console.log('\n===== old page fallback (recorded, not written by this composer)');
console.log(recorded.text);
console.log(`chars=${[...recorded.text].length} gate=${oldGate.decision} findings=${JSON.stringify(kinds(oldReport))}`);
console.log(`note=${recorded.note ?? ''}`);
console.log('\n===== 07 composer on the same settled turn');
console.log(result.text);
console.log(`chars=${[...result.text].length} accepted=${result.accepted} issues=${JSON.stringify(result.issues)}`);
console.log(`gate=${newGate.decision} findings=${JSON.stringify(kinds(newReport))}`);

const oldCount = kinds(oldReport).length;
const newCount = kinds(newReport).length;
console.log('\n===== summary');
console.log(`old fallback: ${[...recorded.text].length} chars, ${oldGate.decision}, ${oldCount} hard findings`);
console.log(`07 composer:  ${[...result.text].length} chars, ${newGate.decision}, ${newCount} hard findings, `
  + `${violations.length} forbidden markers`);
for (const violation of violations) console.log(`  forbidden: ${violation.why}`);
if (!result.accepted) {
  console.log('the 07 composer rejected its own quiet turn; that is a finding, not a pass');
  process.exitCode = 1;
}
if (violations.length || newGate.decision === 'regenerate') {
  process.exitCode = 1;
}
