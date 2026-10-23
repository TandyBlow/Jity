/** T01 fixed-response controller scenario. The corpus instantiates the
 * shared trace for one sample; every expectation — identity binding, model
 * outputs, model inputs, preview specimen — is derived from the declared
 * corpus or authored as a marked B specimen. Identity config (requestId
 * prefix, slot alias) is scenario-level and swappable for H1. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ControllerDriver, initialMemory, type DriverOptions } from './controller';
import { buildCorpus, ScenarioModelPort, ScenarioTransport, type Corpus, type PreviewSpecimenSpec, type ServedSnapshot } from './harness';
import { readTrace } from './trace-runner';
import type { WorldTransport } from './transport';
import type { Id, Json } from './types';

const ROSTER = ['person_a', 'person_b', 'person_c', 'person_d', 'person_e', 'person_f'];

/** B-authored working state for the extra preview after begin: the full
 * world roster (candidate coverage derives from it) with person_a in the
 * corridor. The specimen's digests are placeholders, never digest evidence. */
function specimenWorkingState(worldId: Id, position: { containerId: string; slotId: null; relativeTo: null }): Json {
  const time = { calendar: 'gregorian', dateTime: '2026-01-01T00:00:00', instantOrdinal: 0 };
  const characters = Object.fromEntries(ROSTER.map((id) => [id, { id, appearanceChanges: [], position, personalityChanges: [], sanity: 50, tasks: {} }]));
  return {
    engineVersion: 'world-engine-v1', schemaVersion: 1, worldId, protagonistId: 'person_a', time,
    initial: { engineVersion: 'world-engine-v1', schemaVersion: 1, protagonistId: 'person_a', worldId, initialTime: time, locations: { corridor: { id: 'corridor', name: '走廊', parentLocationId: null, initialAppearance: '空旷' } }, items: {}, characters: Object.fromEntries(ROSTER.map((id) => [id, { id, name: id, initialPosition: position, initialAppearance: '正常', initialPersonality: '冷静', initialSanity: 50, tasks: {} }])) },
    locations: { corridor: { id: 'corridor', appearanceChanges: [] } },
    items: {},
    characters,
  } as Json;
}

function specimenBuild(served: ServedSnapshot): { workingState: Json; pointProjection: Json; mergedEntityDeltas: Json } {
  const world = served.world!;
  const work = served.work!;
  const position = { containerId: 'corridor', slotId: null, relativeTo: null };
  return {
    workingState: specimenWorkingState(world.worldId, position),
    pointProjection: {
      worldId: world.worldId, id: work.pointId, sequence: 1, kind: 'normal',
      previousPointId: world.head.pointId, roundId: work.baseline.headPointId,
      advanceId: world.advance.advanceId, trigger: 'player', linkedFromPointId: null,
      timeAdvance: work.timeAdvance, entityDeltas: {},
    } as unknown as Json,
    mergedEntityDeltas: {},
  };
}

export interface T01Scenario {
  driver: ControllerDriver;
  transport: ScenarioTransport;
  model: ScenarioModelPort;
  memory: ReturnType<typeof initialMemory>;
  corpus: Corpus;
  roundId: Id;
}

export function buildT01Scenario(sampleId: string, rawOverride?: object, driverOptions?: Partial<DriverOptions>): T01Scenario {
  const raw = rawOverride ?? JSON.parse(readFileSync(resolve(process.cwd(), '../design/world-protocol/v2/traces/T01.json'), 'utf8'));
  readTrace(raw); // pin + schema gate before anything derives from it
  const specimens: PreviewSpecimenSpec[] = [{ afterStepId: 's6', label: 'b-preview-after-begin-s6', build: specimenBuild }];
  const corpus = buildCorpus(raw, sampleId, specimens, ['s21', 's22', 's23']);
  const roundId = (corpus.servedAfter.s5.world!.activeRoundId ?? corpus.servedAfter.s5.world!.round!.roundId) as Id;

  const reqS1 = corpus.requests.s1 as unknown as { initial: Json };
  const reqS3 = corpus.requests.s3 as unknown as { text: string };
  const reqS4 = corpus.requests.s4 as unknown as { allocationKey: Id; slots: { slotKey: Id; kind: 'advance' | 'input' | 'round' | 'group'; scope?: Id | null }[] };
  const reqS5 = corpus.requests.s5 as unknown as { inputText: string; order: Id[] };
  const reqS6 = corpus.requests.s6 as unknown as { pointId: Id; kind: 'normal' | 'instant' | 'linked'; timeAdvance: Json };
  const reqS7 = corpus.requests.s7 as unknown as { actionText: string };
  const reqS10 = corpus.requests.s10 as unknown as { candidates: { groupId: Id; positions: Record<string, { containerId: string; slotId: null; relativeTo: null }> }; results: Record<string, string> };
  const reqS20 = corpus.requests.s20 as unknown as { text: string };
  const head1 = corpus.servedAfter.s1.world!.head;
  const world5 = corpus.servedAfter.s5.world!;
  const head18 = corpus.servedAfter.s18.world!.head;
  const groupId = reqS10.candidates.groupId;
  const position = reqS10.candidates.positions.person_a;
  const specimenState = specimenBuild(corpus.servedAfter.s6).workingState;

  const model = new ScenarioModelPort([
    { task: 'initial', key: 'initial', input: null, output: reqS1.initial },
    { task: 'narration', key: head1.pointId, input: { pointId: head1.pointId, stateDigest: head1.stateDigest }, output: reqS3.text },
    { task: 'pointPlan', key: roundId, input: { round: structuredClone(world5.round) as Json, head: structuredClone(world5.head) as Json }, output: [{ pointId: reqS6.pointId, kind: reqS6.kind, timeAdvance: reqS6.timeAdvance, actorIds: ['person_a'] }] },
    { task: 'action', key: 'person_a', input: { actor: 'person_a', workingState: specimenState }, output: { kind: 'act', text: reqS7.actionText } as unknown as Json },
    { task: 'targets', key: 'person_a', input: { sourceId: 'person_a', actionText: reqS7.actionText, workingState: specimenState }, output: { targets: [] } },
    { task: 'results', key: groupId, input: { groupId, workingState: specimenState }, output: structuredClone(reqS10.results) },
    { task: 'updates', key: groupId, input: { groupId, mode: 'group', workingState: specimenState, priorStages: [], appliedDelta: {} }, output: [{ stage: 'position', changes: { person_a: { positionSet: structuredClone(position) } } }] },
    { task: 'narration', key: head18.pointId, input: { pointId: head18.pointId, stateDigest: head18.stateDigest }, output: reqS20.text },
  ], 'T01');

  const memory = initialMemory('req_T01', 'browser');
  memory.playerInput = { text: reqS5.inputText, order: [...reqS5.order] };
  memory.allocPlan = { allocationKey: reqS4.allocationKey, slots: structuredClone(reqS4.slots) };
  const transport = new ScenarioTransport(corpus.steps, () => memory.requestId, 'T01');
  const options: DriverOptions = {
    retryLimit: 3,
    identityAliases: { 'group:person_a': 'group', ...(driverOptions?.identityAliases ?? {}) },
    ...driverOptions,
  };
  const driver = new ControllerDriver({ transport, model }, memory, { world: null }, options);
  return { driver, transport, model, memory, corpus, roundId };
}

/** Drives the controller segment until every controller/preview step and
 * model call is consumed; any early terminal status fails the run. Inspect
 * steps stay for the harness to issue afterwards. */
export async function driveControllerSegment(scenario: T01Scenario): Promise<void> {
  for (;;) {
    const terminal = await scenario.driver.step();
    if (terminal) throw new Error(`[T01] controller segment ended early: ${terminal.kind}/${'reason' in terminal ? terminal.reason : terminal.detail}`);
    if (scenario.transport.controllerDrained && scenario.model.exhausted) return;
  }
}
