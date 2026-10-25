/** T01 fixed-response controller scenario. The corpus instantiates the
 * shared trace for one sample; every expectation — identity binding, model
 * outputs, model inputs, preview specimen — is derived from the declared
 * corpus or authored as a marked B specimen. Identity config (requestId
 * prefix, slot alias) is scenario-level and swappable for H1. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ControllerDriver, initialMemory, type DriverOptions } from './controller';
import { buildCorpus, ScenarioModelPort, ScenarioTransport, type Corpus, type PreviewSpecimenSpec, type ReadStateSpecimenSpec } from './harness';
import { ProtocolError } from './protocol';
import { instantiate, readTrace } from './trace-runner';
import type { WorldTransport } from './transport';
import type { Id, Json } from './types';

/** B-authored preview specimen after begin: the recorded working state of
 * the SAME point (the trace's own final preview, s16) with the point's
 * staged entity deltas reverted to the recorded initial positions — begin
 * has staged nothing yet. Entities, time and identity bindings are the real
 * T01 ones; only the specimen's digests are placeholders, never evidence. */
function buildSpecimen(realWorkingState: Json, realPointProjection: Json): { workingState: Json; pointProjection: Json; mergedEntityDeltas: Json } {
  const workingState = structuredClone(realWorkingState) as { characters: Record<string, { position: Json }>; initial: { characters: Record<string, { initialPosition: Json }> } };
  const deltas = (realPointProjection as { entityDeltas?: Record<string, { positionSet?: Json }> }).entityDeltas ?? {};
  for (const [entityId, delta] of Object.entries(deltas)) {
    const initialPosition = workingState.initial.characters[entityId]?.initialPosition;
    if (delta.positionSet && workingState.characters[entityId] && initialPosition) workingState.characters[entityId].position = structuredClone(initialPosition);
  }
  return {
    workingState: workingState as Json,
    pointProjection: { ...(structuredClone(realPointProjection) as Record<string, unknown>), entityDeltas: {} } as Json,
    mergedEntityDeltas: {},
  };
}

/** Independent digest pins for the final preview's pointProjectionDigest —
 * the one digest no later response references, so the runtime digest chain
 * cannot hold it. Precomputed OUTSIDE the corpus by the server's own recipe
 * (canonical sha256 over the recorded s16 pointProjection body,
 * app.schemas.world.canonical.canonical_digest) and re-verified against both
 * samples; the served corpus instance never feeds these values. */
const POINT_PROJECTION_DIGEST_PINS: Record<string, string> = {
  sample_1: '02b75b795d24430c01a1944fe42e720b574084cd12dd544474e2315814a3495a',
  sample_2: 'e6e2280db6d16f8b514e8af60348bf7114beae7a8ddcfb7d065636c33ebc9657',
};

/** B-authored root state built from the recorded S₀ template (§9.5
 * reconstruction shape): initial positions, empty change sets, root time.
 * Marked construction — the recorded trace has no root get_state read. */
function buildRootState(initial: Json, worldId: Id): Json {
  const template = structuredClone(initial) as {
    protagonistId: Id; initialTime: Json;
    locations: Record<string, { id: Id }>; items: Record<string, { id: Id; initialPosition: Json }>;
    characters: Record<string, { id: Id; initialPosition: Json; initialSanity: number; tasks: Json }>;
  };
  const locations: Record<string, Json> = {};
  for (const [key, location] of Object.entries(template.locations)) locations[key] = { id: location.id, appearanceChanges: [] };
  const items: Record<string, Json> = {};
  for (const [key, item] of Object.entries(template.items)) items[key] = { id: item.id, appearanceChanges: [], position: structuredClone(item.initialPosition) };
  const characters: Record<string, Json> = {};
  for (const [key, character] of Object.entries(template.characters)) characters[key] = { id: character.id, appearanceChanges: [], position: structuredClone(character.initialPosition), personalityChanges: [], sanity: character.initialSanity, tasks: structuredClone(character.tasks) };
  return {
    engineVersion: 'world-engine-v1', schemaVersion: 1, worldId,
    protagonistId: template.protagonistId, time: structuredClone(template.initialTime),
    initial: { ...structuredClone(template as unknown as Record<string, unknown>), worldId },
    locations, items, characters,
  };
}

/** 主角视角约束的字面量——独立于 assembleNarrationInput 的模板拼接；若生产
 * 侧改变措辞，这里的字面量必须随之显式更新并记录依据。 */
const PERSPECTIVE_PERSON_C = '主角视角（person_c「C」）；只表达已结算的世界事实';

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
  const trace = readTrace(raw); // pin + schema gate before anything derives from it
  const sample = trace.samples.find((s) => s.id === sampleId);
  if (!sample) throw new ProtocolError(`Unknown sample ${sampleId}`);
  const recordedPreview = trace.steps.find((s) => s.id === 's16');
  if (!recordedPreview) throw new ProtocolError('[T01] trace has no s16 preview to derive the preview specimen from');
  const recorded = instantiate(recordedPreview.response, sample.values) as { data: { workingState: Json; pointProjection: Json } };
  const specimen = buildSpecimen(recorded.data.workingState, recorded.data.pointProjection);
  // Narration assembly material (§7.1), instantiated straight from the
  // trace — BEFORE the corpus exists. The root state is a marked B
  // construction from S₀ (the trace records no root get_state read); the p1
  // read copies the recorded s21 get_state response data verbatim (state +
  // the point's own saved record).
  const s1head = (instantiate(trace.steps.find((step) => step.id === 's1')!.response, sample.values) as unknown as { world: { worldId: Id; head: { pointId: Id; stateDigest: string } } }).world;
  const rootId = s1head.head.pointId;
  const rootState = buildRootState((instantiate(trace.steps.find((step) => step.id === 's1')!.request, sample.values) as unknown as { initial: Json }).initial, s1head.worldId);
  const rootReadData: Json = {
    pointId: rootId, version: 0, stateDigest: s1head.head.stateDigest,
    previousPointId: null, timeAdvance: null, entityDeltas: {},
    state: rootState,
  };
  const s21data = (instantiate(trace.steps.find((step) => step.id === 's21')!.response, sample.values) as unknown as { data: Json }).data;
  const s21payload = s21data as { pointId: Id; state: Json; previousPointId: Id | null; timeAdvance: Json; entityDeltas: Json };
  const readSpecimens: ReadStateSpecimenSpec[] = [
    { label: 'b-read-root-after-s2', afterStepId: 's2', data: rootReadData },
    { label: 'b-read-p1-after-s19', afterStepId: 's19', data: s21data },
    { label: 'b-read-root-after-p1-read', afterStepId: 'b-read-p1-after-s19', data: rootReadData },
  ];
  // Declared narration inputs are INDEPENDENT literals (never produced by
  // assembleNarrationInput): a shared omission must fail the match loudly.
  const declaredRootNarrationInput: Json = {
    pointId: rootId, before: null,
    delta: { timeAdvance: null, entityDeltas: {} },
    after: rootState,
    perspective: PERSPECTIVE_PERSON_C,
  };
  const declaredP1NarrationInput: Json = {
    pointId: s21payload.pointId,
    before: rootState,
    delta: { timeAdvance: s21payload.timeAdvance, entityDeltas: s21payload.entityDeltas },
    after: s21payload.state,
    perspective: PERSPECTIVE_PERSON_C,
  };
  const specimens: PreviewSpecimenSpec[] = [{ afterStepId: 's6', label: 'b-preview-after-begin-s6', build: () => structuredClone(specimen) }];
  const projectionPin = POINT_PROJECTION_DIGEST_PINS[sampleId];
  if (!projectionPin) throw new ProtocolError(`[T01] no independent pointProjectionDigest pin for ${sampleId}`);
  // The final preview (s16) is bound to s21's independent expectation: its
  // served working state must BE the expected committed projection and its
  // workingStateDigest the independently pinned state digest.
  const corpus = buildCorpus(raw, sampleId, specimens, ['s21', 's22', 's23'],
    [{ previewStepId: 's16', expectationStepId: 's21', workingStatePath: '/data/workingState', workingStateDigestPath: '/data/workingStateDigest' }],
    [{ stepId: 's16', path: '/data/pointProjectionDigest', digest: projectionPin }], [],
    readSpecimens);
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
  const specimenState = specimen.workingState;

  const model = new ScenarioModelPort([
    { task: 'initial', key: 'initial', input: null, output: reqS1.initial },
    { task: 'narration', key: head1.pointId, input: declaredRootNarrationInput, output: reqS3.text },
    { task: 'pointPlan', key: roundId, input: { round: structuredClone(world5.round) as Json, head: structuredClone(world5.head) as Json }, output: [{ pointId: reqS6.pointId, kind: reqS6.kind, timeAdvance: reqS6.timeAdvance, actorIds: ['person_a'] }] },
    { task: 'action', key: 'person_a', input: { actor: 'person_a', workingState: specimenState }, output: { kind: 'act', text: reqS7.actionText } as unknown as Json },
    { task: 'targets', key: 'person_a', input: { sourceId: 'person_a', actionText: reqS7.actionText, workingState: specimenState }, output: { targets: [] } },
    { task: 'results', key: groupId, input: { groupId, workingState: specimenState }, output: structuredClone(reqS10.results) },
    { task: 'updates', key: groupId, input: { groupId, mode: 'group', workingState: specimenState }, output: [{ stage: 'position', changes: { person_a: { positionSet: structuredClone(position) } } }] },
    { task: 'narration', key: head18.pointId, input: declaredP1NarrationInput, output: reqS20.text },
  ], 'T01');

  const memory = initialMemory('req_T01', 'browser');
  memory.playerInput = { text: reqS5.inputText, order: [...reqS5.order] };
  memory.allocPlan = { allocationKey: reqS4.allocationKey, slots: structuredClone(reqS4.slots) };
  const transport = new ScenarioTransport(corpus.steps, 'T01');
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
