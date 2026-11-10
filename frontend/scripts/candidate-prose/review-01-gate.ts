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

interface Entity {
  id: string;
  name?: string;
  initialPosition?: { containerId: string | null };
  position?: { containerId: string | null };
  initialSanity?: number;
  sanity?: number;
  initialAppearance?: string;
  appearanceChanges?: Array<{ id: string; text: string }>;
  initialPersonality?: string;
  personalityChanges?: Array<{ id: string; text: string }>;
  tasks?: Record<string, { id: string; goal: string; status: string; parentTaskId: string | null }>;
}
interface WorldState {
  initial: {
    characters: Record<string, Entity>;
    locations: Record<string, { id: string; name: string; parentLocationId: string | null; initialAppearance?: string }>;
    items: Record<string, { id: string; name: string; initialPosition?: { containerId: string | null }; initialAppearance?: string }>;
  };
  characters: Record<string, Entity>;
  locations: Record<string, { id: string; appearanceChanges?: Array<{ id: string; text: string }> }>;
  items: Record<string, { id: string; position?: { containerId: string | null }; appearanceChanges?: Array<{ id: string; text: string }> }>;
}
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

function placeName(state: WorldState, containerId: string | null | undefined): string | undefined {
  if (!containerId) return undefined;
  return state.initial.locations[containerId]?.name;
}

const STATUS_LABEL: Record<string, string> = {
  achieved: '已完成', pending: '未完成', done: '已完成', open: '未完成',
};

function nameOfCharacter(state: WorldState, id: string): string {
  return state.initial.characters[id]?.name ?? id;
}
/** Full before-state block, keyed by display names the way 01's corpus is. */
function stateTables(state: WorldState) {
  const 人物: Record<string, unknown> = {};
  for (const [id, initial] of Object.entries(state.initial.characters)) {
    const live = state.characters[id] ?? initial;
    const tasks = Object.values(live.tasks ?? {});
    const big = tasks.find((task) => !task.parentTaskId);
    人物[initial.name ?? id] = {
      位置: placeName(state, live.position?.containerId ?? initial.initialPosition?.containerId),
      精神值: live.sanity ?? initial.initialSanity,
      外貌: [
        initial.initialAppearance,
        ...(live.appearanceChanges ?? []).map((change) => change.text),
      ].filter((text): text is string => Boolean(text)),
      个性: [
        initial.initialPersonality,
        ...(live.personalityChanges ?? []).map((change) => change.text),
      ].filter((text): text is string => Boolean(text)),
      任务: {
        ...(big ? { 大任务: { 目标: big.goal, 状态: STATUS_LABEL[big.status] ?? big.status } } : {}),
        小任务: tasks.filter((task) => task.parentTaskId)
          .map((task) => ({ 目标: task.goal, 状态: STATUS_LABEL[task.status] ?? task.status })),
      },
    };
  }
  const 地点: Record<string, unknown> = {};
  for (const [id, initial] of Object.entries(state.initial.locations)) {
    const live = state.locations[id];
    地点[initial.name ?? id] = {
      位于: initial.parentLocationId ? state.initial.locations[initial.parentLocationId]?.name ?? null : null,
      外貌: [initial.initialAppearance, ...(live?.appearanceChanges ?? []).map((change) => change.text)]
        .filter((text): text is string => Boolean(text)),
    };
  }
  const 物品: Record<string, unknown> = {};
  for (const [id, initial] of Object.entries(state.initial.items)) {
    const live = state.items[id];
    物品[initial.name ?? id] = {
      位置: placeName(state, live?.position?.containerId ?? initial.initialPosition?.containerId),
      外貌: [initial.initialAppearance, ...(live?.appearanceChanges ?? []).map((change) => change.text)]
        .filter((text): text is string => Boolean(text)),
    };
  }
  return { 人物, 地点, 物品 };
}

function rowFor(before: WorldState, after: WorldState, minutes: number) {
  const 变化: Record<string, unknown> = {};
  for (const [id, initial] of Object.entries(after.initial.characters)) {
    const b = before.characters[id] ?? initial;
    const a = after.characters[id] ?? initial;
    const delta: Record<string, unknown> = {};
    const beforePlace = placeName(before, b.position?.containerId ?? initial.initialPosition?.containerId);
    const afterPlace = placeName(after, a.position?.containerId ?? initial.initialPosition?.containerId);
    if (beforePlace !== afterPlace) delta.位置 = afterPlace;
    if (b.sanity !== a.sanity) delta.精神值 = a.sanity;
    const beforeAppearance = new Set((b.appearanceChanges ?? []).map((change) => change.text));
    const addedAppearance = (a.appearanceChanges ?? [])
      .map((change) => change.text).filter((text) => !beforeAppearance.has(text));
    const removedAppearance = (b.appearanceChanges ?? [])
      .map((change) => change.text).filter((text) => !new Set((a.appearanceChanges ?? []).map((c) => c.text)).has(text));
    if (addedAppearance.length) delta.新增外貌 = addedAppearance;
    if (removedAppearance.length) delta.解除外貌 = removedAppearance;
    const beforePersonality = new Set((b.personalityChanges ?? []).map((change) => change.text));
    const addedPersonality = (a.personalityChanges ?? [])
      .map((change) => change.text).filter((text) => !beforePersonality.has(text));
    const removedPersonality = (b.personalityChanges ?? [])
      .map((change) => change.text).filter((text) => !new Set((a.personalityChanges ?? []).map((c) => c.text)).has(text));
    if (addedPersonality.length) delta.新增个性 = addedPersonality;
    if (removedPersonality.length) delta.解除个性 = removedPersonality;
    const completed = Object.values(a.tasks ?? {})
      .filter((task) => task.status === 'achieved' && b.tasks?.[task.id]?.status !== 'achieved')
      .map((task) => task.goal);
    if (completed.length) delta.完成任务 = completed;
    const addedTasks = Object.values(a.tasks ?? {})
      .filter((task) => !b.tasks?.[task.id]).map((task) => task.goal);
    if (addedTasks.length) delta.新增任务 = addedTasks;
    if (Object.keys(delta).length) 变化[initial.name ?? id] = delta;
  }
  const 变化状态: Record<string, unknown> = {};
  for (const name of Object.keys(变化)) {
    const id = Object.keys(after.initial.characters)
      .find((key) => after.initial.characters[key].name === name);
    if (!id) continue;
    const live = after.characters[id];
    变化状态[name] = {
      位置: placeName(after, live.position?.containerId),
      精神值: live.sanity,
      外貌: (live.appearanceChanges ?? []).map((change) => change.text),
      个性: (live.personalityChanges ?? []).map((change) => change.text),
    };
  }
  const protagonist = worldProtagonist(after);
  return {
    视角: `主角视角（${nameOfCharacter(after, protagonist)}）；只表达已结算的世界事实`,
    上回合状态: stateTables(before),
    '本回合变化': { 时间推进: `${minutes} 分钟`, 变化 },
    '本回合状态': 变化状态,
  };
}

function worldProtagonist(state: WorldState): string {
  return (state as unknown as { protagonistId: string }).protagonistId;
}

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

  const row = rowFor(beforeRead.state as WorldState, after, turn.minutes);
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
