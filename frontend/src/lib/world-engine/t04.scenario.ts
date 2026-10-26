/** T04: real controller continuation, automatic round and model handback.
 * Context reads, idempotency replay and lease release are explicit harness
 * boundaries. Preview specimens have placeholder digests; the final body is
 * bound to the shared independent expectation at the state read. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ControllerDriver, initialMemory } from './controller';
import { buildCorpus, ScenarioModelPort, ScenarioTransport, servedBeforeSteps, type DeclaredModelCall, type PreviewSpecimenSpec, type ReadStateSpecimenSpec } from './harness';
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
  // 叙事组装（§7.1）：claim s11 后目标读＋前驱读。目标态=录制的 s16 提交态；
  // 点记录逐字取 s10 commit 请求；前驱态=既定近似（final 态＋引导时间）。
  const commitPoint = point as { previousPointId: Id | null; timeAdvance: Json; entityDeltas: Json };
  const beforeId = commitPoint.previousPointId as Id;
  const beforeState = { ...(structuredClone(state) as Record<string, unknown>), time: structuredClone((context.world as unknown as { time: Json }).time) } as unknown as Json;
  const readSpecimens: ReadStateSpecimenSpec[] = [
    { label: 'b-read-target-after-s11', afterStepId: 's11', data: { pointId: committed.world.head.pointId, version: 1, stateDigest: committed.world.head.stateDigest, previousPointId: commitPoint.previousPointId, timeAdvance: commitPoint.timeAdvance, entityDeltas: commitPoint.entityDeltas, state } as unknown as Json },
    { label: 'b-read-before-after-target', afterStepId: 'b-read-target-after-s11', data: { pointId: beforeId, version: 0, stateDigest: context.world.head.stateDigest, previousPointId: null, timeAdvance: null, entityDeltas: {}, state: beforeState } as unknown as Json },
  ];
  const corpus = buildCorpus(raw, sampleId, previews, ['s1', 's3', 's14', 's15', 's16', 's17'], [
    { previewStepId: 'b-t04-after-stage', expectationStepId: 's16', workingStatePath: '/data/workingState', workingStateDigestPath: '/data/workingStateDigest' },
  ], [], [{ stepId: 's15', kind: 'continue' }], readSpecimens);
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
  const recordedActiveInput = (context as unknown as { activeInput: { advanceId: Id; inputId: Id; text: string } | null }).activeInput;
  // §6.1：调用时刻的 advance——世界取 s4（begin）服务态，输入文本取最后一次
  // context 回包；s1/s3 都是 harness 边界，驱动器只播种 s1。
  // s1 已播种进驱动器；其余 inspect（s3/s14–s17）不经过驱动器。
  const servedBefore = servedBeforeSteps(trace.steps, responses, ['s3', 's14', 's15', 's16', 's17']);
  const actionAdvance = (() => {
    const served = servedBefore.get('s5')!;
    return { inputText: recordedActiveInput?.text ?? null, intentStatus: served.world!.advance.intentStatus } as Json;
  })();
  const personCActionText = (requests.get('s5') as { actionText: string }).actionText;
  const declared: DeclaredModelCall[] = [
    { task: 'continuation', key: context.world.activeRoundId!, input: { round: context.world.round, head: context.world.head, workingState: null }, output: requests.get('s2')!.conclusion as Json },
    { task: 'pointPlan', key: roundId, input: { round: automatic.world.round, head: automatic.world.head }, output: [{ pointId: begin.pointId, kind: begin.kind, timeAdvance: begin.timeAdvance, actorIds: ['person_c'] }] as Json },
    { task: 'action', key: 'person_c', input: { actor: 'person_c', advance: actionAdvance, workingState }, output: { kind: 'act', text: personCActionText } as Json },
    { task: 'targets', key: 'person_c', input: { sourceId: 'person_c', actionText: personCActionText, workingState } as Json, output: { targets: [] } },
    // §7.1：results 输入带全组冻结行动（T04 目标集为空——零骰点判定）。
    { task: 'results', key: groupId, input: { groupId, members: [{ memberId: 'person_c', actionText: personCActionText, rollRefs: [] }], workingState }, output: stage.results as Json },
    { task: 'updates', key: groupId, input: { groupId, mode: 'group', results: structuredClone(stage.results) as Json, workingState }, output: [] },
    { task: 'narration', key: committed.world.head.pointId, input: { pointId: committed.world.head.pointId, before: beforeState, delta: { timeAdvance: commitPoint.timeAdvance, entityDeltas: commitPoint.entityDeltas }, after: state, perspective: `主角视角（${(state as { protagonistId: Id }).protagonistId}「${(state as { initial: { characters: Record<string, { name: string }> } }).initial.characters[(state as { protagonistId: Id }).protagonistId].name}」）；只表达已结算的世界事实` }, output: requests.get('s12')!.text as Json },
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
  const driver = new ControllerDriver({ transport, model }, memory, { world: context.world, control: context.control, activeInput: recordedActiveInput });
  return { driver, transport, model, corpus };
}
