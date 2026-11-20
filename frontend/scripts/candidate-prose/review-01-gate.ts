/** Grade this composer's own text with lane 01's independent reviewer.
 *
 * 01's checker rebuilds facts from a dataset row (视角 / 上回合状态 /
 * 本回合变化 / 本回合状态) and never imports the generation side, so it can
 * disagree with this composer. Here the same ten settled points used by
 * `chain-10.ts` are converted into that row shape, the composer writes the
 * text, and 01's reviewer + gate read it back.
 *
 *   LANE01_ROOT=../../01-input LANE04_ROOT=../04-settlement \
 *     ./node_modules/.bin/jiti ./scripts/candidate-prose/review-01-gate.ts
 *
 * This is an automated check, not human review and not product acceptance.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { generateCandidate } from '../../src/lib/world-engine/local/narration-candidates/prose-composer/index';
import { CHAIN_TURNS } from './chain-turns';
import { rowFor01, type WorldState } from './row-for-01';

const lane04 = process.env.LANE04_ROOT
  ?? 'D:/others/Jity/.local/parallel-local-game/worktrees/04-settlement';
const lane01 = process.env.LANE01_ROOT
  ?? 'D:/others/Jity/.local/parallel-local-game/worktrees/01-input';

const load = async (root: string, modulePath: string) =>
  import(pathToFileURL(join(root, modulePath)).href) as Promise<Record<string, unknown>>;

const stateModule = await load(lane04, 'frontend/src/lib/world-engine/local/state.ts');
const constrained = await load(lane04, 'frontend/src/lib/world-engine/local/narration-candidates/constrained/index.ts');
const quality = await load(lane01, 'frontend/src/lib/world-engine/local/narration-quality/index.ts');

const buildInitialState = stateModule.buildInitialState as (initial: unknown) => WorldState;
const applyPoint = stateModule.applyPoint as (state: unknown, point: unknown) => WorldState;
const projectConstrainedScene = constrained.projectConstrainedScene as (
  after: unknown, before: unknown,
) => { base: unknown };
const reviewNarration = quality.reviewNarration as (args: {
  id: string; input: unknown; text: string;
}) => ReviewReport;
const gateModule = await load(lane01, 'frontend/src/lib/world-engine/local/narration-quality/gate.ts');
const gateNarration = gateModule.gateNarration as (report: ReviewReport, policy?: unknown) => GateResult;

interface ReviewReport {
  findings: Array<{ kind: string; severity: string; detail: string; sentence?: string }>;
  counts?: Record<string, number>;
  mandatory?: Array<{ id: string; narrated: boolean; label?: string }>;
}
interface GateResult { decision: 'accept_as_model_prose' | 'hold_for_review' | 'regenerate'; reasons?: string[] }

const world = JSON.parse(readFileSync(
  join(process.cwd(), '..', 'data', 'worlds', 'dragon-raja-free-day.world.json'),
  'utf8',
)) as { worldId: string; initial: unknown };

const turns = CHAIN_TURNS.map((turn) => ({
  text: turn.text, minutes: turn.time.amount, deltas: turn.deltas,
}));

let state = buildInitialState(world.initial);
let beforeRead = {
  pointId: 'root', version: 0, state, stateDigest: 'root',
  previousPointId: null, timeAdvance: null, entityDeltas: {},
} as Record<string, unknown>;
let priorText: string | null = null;
const transcript: string[] = [];
const allFindings: Array<{ turn: number; kind: string; severity: string; detail: string }> = [];
let blocked = 0;

for (const [index, turn] of turns.entries()) {
  const point = {
    worldId: world.worldId,
    id: `gate_${index + 1}`,
    sequence: index + 1,
    kind: 'normal',
    previousPointId: beforeRead.pointId,
    roundId: `gate_r${index + 1}`,
    advanceId: `gate_a${index + 1}`,
    trigger: 'player',
    linkedFromPointId: null,
    timeAdvance: { boundary: 'elapsed', duration: { amount: turn.minutes, unit: 'minute' } },
    entityDeltas: turn.deltas,
  } as Record<string, unknown>;
  const after = applyPoint(beforeRead.state, point);
  const afterRead = {
    pointId: point.id, version: index + 1, state: after,
    stateDigest: `gate-digest-${index + 1}`,
    previousPointId: beforeRead.pointId,
    timeAdvance: point.timeAdvance, entityDeltas: point.entityDeltas,
  };
  const { base: committed } = projectConstrainedScene(afterRead, beforeRead);
  const result = generateCandidate({
    committed: { ...(committed as Record<string, unknown>), state: after },
    state: after,
    beforeState: beforeRead.state,
    delta: { timeAdvance: point.timeAdvance },
    priorText,
    policy: { minChars: 12, avoidText: transcript.join(String.fromCharCode(10)) || null },
  } as never);

  const row = rowFor01(beforeRead.state as WorldState, after, turn.minutes);
  const report = reviewNarration({ id: `turn-${index + 1}`, input: row, text: result.text });
  const gate = gateNarration(report, {});
  const findings = report.findings.filter((finding) => finding.severity !== 'review');
  for (const finding of findings) {
    allFindings.push({ turn: index + 1, kind: finding.kind, severity: finding.severity, detail: finding.detail });
  }
  if (gate.decision === 'regenerate') blocked += 1;
  console.log(`\n===== turn ${index + 1}: ${turn.text}`);
  console.log(`composer accepted=${result.accepted} chars=${[...result.text].length}`);
  console.log(result.text);
  console.log(`01 gate=${gate.decision} findings=${findings.length}`
    + (findings.length ? ` ${JSON.stringify(findings.map((f) => f.kind))}` : ''));
  for (const finding of findings) console.log(`  [${finding.severity}] ${finding.kind}: ${finding.detail}`);

  if (result.text) transcript.push(result.text);
  priorText = result.text || priorText;
  beforeRead = afterRead;
  state = after;
}

console.log('\n===== summary');
console.log(`turns ${turns.length}, gate regenerate ${blocked}/${turns.length}`);
const byKind = new Map<string, number>();
for (const finding of allFindings) byKind.set(finding.kind, (byKind.get(finding.kind) ?? 0) + 1);
for (const [kind, count] of [...byKind.entries()].sort((a, b) => b[1] - a[1])) {
  console.log(`  ${count} x ${kind}`);
}
