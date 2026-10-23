/** T04: real controller continuation, automatic round and model handback.
 * Context reads, idempotency replay and lease release are explicit harness
 * boundaries. Preview specimens have placeholder digests; the final body is
 * bound to the shared independent expectation at the state read. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ControllerDriver, initialMemory } from './controller';
import { buildCorpus, ScenarioModelPort, ScenarioTransport, type DeclaredModelCall, type PreviewSpecimenSpec } from './harness';
import { instantiate, readTrace } from './trace-runner';
import { advanceTime, type WallTime } from './t02.scenario';
import type { ControlState, Id, Json, WorldContext } from './types';

export function buildT04Scenario(sampleId: string) {
  const raw = JSON.parse(readFileSync(resolve(process.cwd(), '../design/world-protocol/v2/traces/T04.json'), 'utf8'));
  const trace = readTrace(raw);
  const sample = trace.samples.find((entry) => entry.id === sampleId);
  if (!sample) throw new Error(`Unknown T04 sample ${sampleId}`);
  const requests = new Map(trace.steps.map((step) => [step.id, instantiate(step.request, sample.values) as Record<string, unknown>]));
  const responses = new Map(trace.steps.map((step) => [step.id, instantiate(step.response, sample.values) as Record<string, unknown>]));
  const context = responses.get('s1') as unknown as { world: WorldContext; control: ControlState };
  const automatic = responses.get('s2') as unknown as { world: WorldContext };
  const committed = responses.get('s10') as unknown as { world: WorldContext };
  const begin = requests.get('s4')!;
  const stage = requests.get('s8')!;
  const point = (requests.get('s10')! as { point: Json }).point;
  const state = (responses.get('s16') as { data: { state: Json } }).data.state;
  const stagedTime = advanceTime(context.world.time as WallTime, begin.timeAdvance as { duration: { amount: number } });
  const workingState = { ...(structuredClone(state) as Record<string, unknown>), time: stagedTime } as unknown as Json;
  const previews: PreviewSpecimenSpec[] = [
    { afterStepId: 's4', label: 'b-t04-after-begin', build: () => ({ workingState, pointProjection: point, mergedEntityDeltas: {}, settlementGroups: [] }) },
    { afterStepId: 's8', label: 'b-t04-after-stage', build: () => ({ workingState, pointProjection: point, mergedEntityDeltas: {}, settlementGroups: [stage.candidates as Json] }) },
  ];
  const corpus = buildCorpus(raw, sampleId, previews, ['s1', 's3', 's14', 's15', 's16', 's17'], [
    { previewStepId: 'b-t04-after-stage', expectationStepId: 's16', workingStatePath: '/data/workingState', workingStateDigestPath: '/data/workingStateDigest' },
  ], [], [{ stepId: 's15', kind: 'continue' }]);
  // Independent lifecycle rules, not read back from either recorded
  // conclude response. Enforce at serve time before the driver adopts it.
  for (const [stepId, inputAvailable] of [['s2', true], ['s13', false]] as const) {
    corpus.steps.find((step) => step.id === stepId)!.businessAssertions = [
      { path: '/world/advance/inputAvailable', expected: inputAvailable },
      { path: '/world/advance/intentStatus', expected: 'consumed' },
    ];
  }
  const groupId = stage.groupId as Id;
  const roundId = automatic.world.activeRoundId!;
  const declared: DeclaredModelCall[] = [
    { task: 'continuation', key: context.world.activeRoundId!, input: { round: context.world.round, head: context.world.head, workingState: null }, output: requests.get('s2')!.conclusion as Json },
    { task: 'pointPlan', key: roundId, input: { round: automatic.world.round, head: automatic.world.head }, output: [{ pointId: begin.pointId, kind: begin.kind, timeAdvance: begin.timeAdvance, actorIds: ['person_c'] }] as Json },
    { task: 'action', key: 'person_c', input: { actor: 'person_c', workingState }, output: { kind: 'act', text: requests.get('s5')!.actionText } as Json },
    { task: 'targets', key: 'person_c', input: { sourceId: 'person_c', actionText: requests.get('s5')!.actionText, workingState } as Json, output: { targets: [] } },
    { task: 'results', key: groupId, input: { groupId, workingState }, output: stage.results as Json },
    { task: 'updates', key: groupId, input: { groupId, mode: 'group', workingState, priorStages: [], appliedDelta: {} }, output: [] },
    { task: 'narration', key: committed.world.head.pointId, input: { pointId: committed.world.head.pointId, stateDigest: committed.world.head.stateDigest }, output: requests.get('s12')!.text as Json },
    { task: 'continuation', key: roundId, input: { round: committed.world.round, head: { ...committed.world.head, narrationStatus: 'ready' }, workingState }, output: requests.get('s13')!.conclusion as Json },
  ];
  const memory = initialMemory('req_T04', 'browser');
  const ownership = trace.variables.find((variable) => variable.origin === 'input' && variable.kind === 'ownership')!;
  memory.leaseToken = sample.values[ownership.name] as Id;
  memory.ids['group:person_c'] = groupId;
  // A preceding player plan must be retired by continue, without the
  // harness resetting the driver's memory between rounds.
  memory.plan = [{ pointId: context.world.head.pointId, kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } }, actorIds: ['person_a'] }];
  memory.planIndex = 1;
  const transport = new ScenarioTransport(corpus.steps, 'T04');
  const model = new ScenarioModelPort(declared, 'T04');
  const driver = new ControllerDriver({ transport, model }, memory, { world: context.world, control: context.control });
  return { driver, transport, model, corpus };
}
