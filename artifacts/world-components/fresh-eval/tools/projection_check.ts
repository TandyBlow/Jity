/**
 * Run the real page projection over the six committed cases.
 *
 * This is the countercheck for the pack's `capability.stages`: the Python side
 * predicts what `projectCommittedNarration` will do; this script actually calls
 * it on the committed before/after records and records the outcome.
 *
 * Leak detection is fact-level, not actor-level: a withheld move only counts as
 * leaked when the projection emits that move fact (`<id>:position`, kind
 * moved). A character still showing up as a standing `at`/`sanity` fact is not
 * a leak of the withheld change. Two synthetic controls prove the detector can
 * both fire and stay quiet.
 *
 * No model is involved. Usage:
 *   node --experimental-strip-types tools/projection_check.ts <fresh/source> <out.json>
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, resolve } from 'node:path';

// Resolve the repository from this file, never from a machine-specific path:
// tools/ -> fresh-eval/ -> world-components/ -> artifacts/ -> repo root.
const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '../../../..');
const MODULE_PATH = resolve(REPO, 'frontend/src/lib/world-engine/runtime/committed-narration.ts');
const { projectCommittedNarration } =
  await import(pathToFileURL(MODULE_PATH).href);

const [sourceDir, outPath] = process.argv.slice(2);
if (!sourceDir || !outPath) {
  console.error('usage: projection_check.ts <fresh/source> <out.json>');
  process.exit(2);
}

/** Map one withheld change fact onto the fact id/kind the projection emits. */
function withheldTarget(w: any): { factId: string; kind: string } | null {
  const eid = w.entityId;
  switch (w.kind) {
    case 'moved':
    case 'moved_entity':
      return { factId: `${eid}:position`, kind: 'moved' };
    case 'sanity_changed':
      return { factId: `${eid}:sanity`, kind: 'sanity_changed' };
    case 'task_achieved':
      return { factId: `${eid}:task:${w.taskId}`, kind: 'task_achieved' };
    case 'personality_changed':
      return { factId: `${eid}:personality`, kind: 'personality_changed' };
    case 'appearance_changed':
      return { factId: `${eid}:appearance`, kind: 'appearance_changed' };
    default:
      return null;
  }
}

function leaked(packet: any, w: any): boolean | null {
  const target = withheldTarget(w);
  if (!target) return null;
  return packet.facts.some((f: any) => f.id === target.factId && f.kind === target.kind);
}

const ids = ['c8e01', 'c8e02', 'c8e03', 'c8e04', 'c8e05', 'c8e06'];
const cases = JSON.parse(readFileSync(`${sourceDir}/cases.json`, 'utf8'));
const results: any[] = [];

for (const id of ids) {
  const before = JSON.parse(readFileSync(`${sourceDir}/${id}.before.json`, 'utf8'));
  const after = JSON.parse(readFileSync(`${sourceDir}/${id}.after.json`, 'utf8'));
  const entry: any = { id };
  let packet: any = null;
  try {
    packet = projectCommittedNarration(after, before);
    entry.accepted = true;
    entry.factCount = packet.facts.length;
    entry.kinds = packet.facts.map((f: any) => f.kind);
    entry.factIds = packet.facts.map((f: any) => f.id);
  } catch (error) {
    entry.accepted = false;
    entry.reason = (error as Error).message;
  }
  const answerPath = `${sourceDir}/../../candidates-fresh/${id}/answer.json`;
  try {
    const answer = JSON.parse(readFileSync(answerPath, 'utf8'));
    const withheld = answer.withheld || [];
    entry.withheldFacts = withheld.map((w: any) => ({
      entityId: w.entityId, kind: w.kind, target: withheldTarget(w),
    }));
    entry.leakedFactIds = packet
      ? withheld.filter((w: any) => leaked(packet, w) === true)
          .map((w: any) => withheldTarget(w)?.factId)
      : null;
    entry.projectionNarratesWithheld = entry.accepted
      ? entry.leakedFactIds.length > 0 : null;
  } catch {
    entry.withheldFacts = null;
  }
  const c = cases.find((x: any) => x.id === id);
  entry.pointId = c?.pointId ?? null;
  entry.afterDigest = c?.afterDigest ?? null;
  results.push(entry);
}

// ---------------------------------------------------------------- controls ---
const loc = (id: string) => ({
  id, name: id, parentLocationId: null, initialAppearance: '', slots: [],
});
const baseState = () => ({
  worldId: 'w',
  initial: {
    characters: { x: { id: 'x', name: '甲', initialAppearance: '', slots: [] } },
    items: {}, locations: { fy: loc('fy'), fz: loc('fz') },
  },
  items: {}, locations: { fy: loc('fy'), fz: loc('fz') },
});
const person = (containerId: string, sanity = 50) => ({
  id: 'x', sanity, tasks: {}, personalityChanges: [], appearanceChanges: [],
  position: { containerId, slotId: null, relativeTo: null },
});
function record(version: number, previousPointId: string, containerId: string,
                deltas: any, digest: string) {
  const state = baseState();
  return {
    pointId: `p${version}`, version, stateDigest: digest, previousPointId,
    timeAdvance: version === 0 ? null : { boundary: 'elapsed', duration: { amount: 30, unit: 'second' } },
    state: { ...state, characters: { x: person(containerId) } },
    entityDeltas: deltas,
  } as any;
}
const controls: any[] = [];
{
  // A. character present, nothing moved: the detector must stay quiet even
  //    though the actor has at/sanity facts.
  const before = record(0, null, 'fy', {}, 'd0');
  const after = record(1, 'p0', 'fy', { x: { entityId: 'x' } }, 'd1');
  const packet = projectCommittedNarration(after, before);
  const observed = leaked(packet, { entityId: 'x', kind: 'moved' });
  controls.push({ name: 'standing-only-no-leak', expected: false,
                  observed, ok: observed === false,
                  factKinds: packet.facts.map((f: any) => f.kind) });
}
{
  // B. the withheld move really happens: the detector must fire.
  const before = record(0, null, 'fy', {}, 'd0');
  const after = record(1, 'p0', 'fz',
                       { x: { entityId: 'x', positionSet: { containerId: 'fz', slotId: null, relativeTo: null } } },
                       'd1');
  const packet = projectCommittedNarration(after, before);
  const observed = leaked(packet, { entityId: 'x', kind: 'moved' });
  controls.push({ name: 'withheld-move-leaks', expected: true,
                  observed, ok: observed === true,
                  factKinds: packet.facts.map((f: any) => f.kind) });
}

const moduleSha = createHash('sha256').update(readFileSync(MODULE_PATH)).digest('hex');
const open = results.filter((r) => r.accepted).length;
writeFileSync(outPath, JSON.stringify({
  node: process.version,
  module: 'frontend/src/lib/world-engine/runtime/committed-narration.ts',
  moduleSha256: moduleSha,
  modelCalls: 0,
  cases: results,
  controls,
  summary: { accepted: open, rejected: results.length - open,
             controlsOk: controls.every((c) => c.ok),
             leakDetected: results.some((r) => r.projectionNarratesWithheld === true) },
}, null, 1) + '\n');
console.log(results.map((r) => `${r.id} ${r.accepted ? 'ACCEPTED' : 'REJECTED ' + r.reason}`
  + ` leaked=${JSON.stringify(r.leakedFactIds)}`).join('\n'));
console.log('controls ' + controls.map((c) => `${c.name}=${c.observed}`).join(' '));
