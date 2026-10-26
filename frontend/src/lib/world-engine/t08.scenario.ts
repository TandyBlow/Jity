/** T08 controller material, with explicit separation of three kinds of
 * exchange: normal successor/commit/cancel; the recorded invalid time-write
 * probe (harness-owned); and an optional B fault specimen that returns the
 * recorded version_mismatch for the driver's LEGAL commit payload, followed
 * by a context-read bridge. The shared trace is never rewritten. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ControllerDriver, initialMemory } from './controller';
import { buildCorpus, ScenarioModelPort, ScenarioTransport, type CorpusStep, type DeclaredModelCall, type PreviewSpecimenSpec, type ReadStateSpecimenSpec } from './harness';
import { instantiate, readTrace } from './trace-runner';
import { advanceTime, type WallTime } from './t02.scenario';
import type { ControlState, Id, Json, WorldContext } from './types';

export type T08Mode = 'normal' | 'commit_conflict';

export function buildT08Scenario(sampleId: string, mode: T08Mode = 'normal') {
  const raw = JSON.parse(readFileSync(resolve(process.cwd(), '../design/world-protocol/v2/traces/T08.json'), 'utf8'));
  const trace = readTrace(raw);
  const sample = trace.samples.find((entry) => entry.id === sampleId);
  if (!sample) throw new Error(`Unknown T08 sample ${sampleId}`);
  const requests = new Map(trace.steps.map((step) => [step.id, instantiate(step.request, sample.values) as Record<string, unknown>]));
  const responses = new Map(trace.steps.map((step) => [step.id, instantiate(step.response, sample.values) as Record<string, unknown>]));
  const context = responses.get('s1') as unknown as { world: WorldContext; control: ControlState };
  const begin = requests.get('s2')!;
  const stage = requests.get('s6')!;
  const prepare = requests.get('s7')!;
  const committed = responses.get('s10') as unknown as { world: WorldContext };
  const point = (requests.get('s10')! as { point: Json }).point;
  const state = (responses.get('s15') as { data: { state: Json } }).data.state;
  const time = advanceTime(context.world.time as WallTime, begin.timeAdvance as { duration: { amount: number } });
  const workingState = { ...(structuredClone(state) as Record<string, unknown>), time } as unknown as Json;
  const specimens: PreviewSpecimenSpec[] = [
    { afterStepId: 's2', label: 'b-t08-after-begin', build: () => ({ workingState, pointProjection: point, mergedEntityDeltas: {}, settlementGroups: [] }) },
    { afterStepId: 's6', label: 'b-t08-after-stage', build: () => ({ workingState, pointProjection: point, mergedEntityDeltas: {}, settlementGroups: [stage.candidates as Json] }) },
  ];
  // 叙事组装（§7.1）：claim s11 后目标读＋前驱读。目标态=录制的 s15 提交态；
  // 点记录逐字取 s9 commit 请求；前驱态=既定近似（final 态＋引导时间）。
  const commitPoint = point as { previousPointId: Id | null; timeAdvance: Json; entityDeltas: Json };
  const beforeId = commitPoint.previousPointId as Id;
  const beforeState = { ...(structuredClone(state) as Record<string, unknown>), time: structuredClone((context.world as unknown as { time: Json }).time) } as unknown as Json;
  const readSpecimens: ReadStateSpecimenSpec[] = [
    { label: 'b-read-target-after-s11', afterStepId: 's11', data: { pointId: committed.world.head.pointId, version: 1, stateDigest: committed.world.head.stateDigest, previousPointId: commitPoint.previousPointId, timeAdvance: commitPoint.timeAdvance, entityDeltas: commitPoint.entityDeltas, state } as unknown as Json },
    { label: 'b-read-before-after-target', afterStepId: 'b-read-target-after-s11', data: { pointId: beforeId, version: 0, stateDigest: context.world.head.stateDigest, previousPointId: null, timeAdvance: null, entityDeltas: {}, state: beforeState } as unknown as Json },
  ];
  const corpus = buildCorpus(raw, sampleId, specimens, ['s1', 's14', 's15'], [
    { previewStepId: 'b-t08-after-stage', expectationStepId: 's15', workingStatePath: '/data/workingState', workingStateDigestPath: '/data/workingStateDigest' },
  ], [], [], readSpecimens);
  corpus.steps.find((step) => step.id === 's8')!.segment = 'probe';
  corpus.steps.find((step) => step.id === 's13')!.segment = 'command';
  const invalidCommitIndex = corpus.steps.findIndex((step) => step.id === 's9');
  const invalidCommit = corpus.steps[invalidCommitIndex];
  if (mode === 'normal') {
    // s9 deliberately submits the wrong locked time. Normal scheduling
    // cannot emit it, so it stays solely in the shared contract suite.
    corpus.steps.splice(invalidCommitIndex, 1);
  } else {
    const legal = corpus.steps.find((step) => step.id === 's10')!;
    const error = invalidCommit.response as Record<string, Json>;
    const faultId = 'b-t08-legal-commit-conflict';
    const fault: CorpusStep = {
      ...invalidCommit, id: faultId, sharedStepId: null, request: structuredClone(legal.request),
      digestChain: invalidCommit.digestChain.map((link) => ({ ...link, captureStepId: link.captureStepId === 's9' ? faultId : link.captureStepId })),
    };
    const bridge: CorpusStep = {
      id: 'b-t08-refresh-after-conflict', sharedStepId: null, segment: 'controller',
      operation: 'get_context', request: {}, requestIdRequired: false, requestIdExpectation: 'fresh', scope: structuredClone(invalidCommit.scope),
      response: {
        ...structuredClone(responses.get('s1')!), serverTimeEpochMilli: error.serverTimeEpochMilli,
        world: structuredClone(error.world), control: structuredClone(error.control), work: structuredClone(error.work),
      } as Json,
      responseKind: 'success', captures: [], digestChain: [],
    };
    corpus.steps.splice(invalidCommitIndex, 1, fault, bridge);
  }
  const groupId = stage.groupId as Id;
  const recordedActiveInput = (context as unknown as { activeInput: { advanceId: Id; inputId: Id; text: string } | null }).activeInput;
  const declared: DeclaredModelCall[] = [
    { task: 'pointPlan', key: context.world.activeRoundId!, input: { round: context.world.round, head: context.world.head }, output: [
      { pointId: begin.pointId, kind: begin.kind, timeAdvance: begin.timeAdvance, actorIds: ['person_a'] },
      // Remaining actors belong to the reserved successor. Cancel is an
      // external command before any of their model calls, not fake skips.
      { pointId: prepare.successorPointId, kind: 'instant', timeAdvance: prepare.timeAdvance, actorIds: ['person_b', 'person_c', 'person_d', 'person_e', 'person_f'] },
    ] as Json },
    { task: 'action', key: 'person_a', input: { actor: 'person_a', advance: { inputText: recordedActiveInput?.text ?? null, intentStatus: context.world.advance.intentStatus }, workingState }, output: { kind: 'act', text: requests.get('s3')!.actionText } as Json },
    { task: 'targets', key: 'person_a', input: { sourceId: 'person_a', actionText: requests.get('s3')!.actionText, workingState } as Json, output: { targets: [] } },
    // §7.1：results 输入带全组冻结行动（T08 目标集为空——零骰点判定）。
    { task: 'results', key: groupId, input: { groupId, members: [{ memberId: 'person_a', actionText: (requests.get('s3') as { actionText: string }).actionText, rollRefs: [] }], workingState }, output: stage.results as Json },
    { task: 'updates', key: groupId, input: { groupId, mode: 'group', workingState }, output: [] },
    { task: 'time', key: `successor:${begin.pointId as Id}`, input: { head: context.world.head, workingState }, output: prepare.timeAdvance as Json },
    { task: 'narration', key: committed.world.head.pointId, input: { pointId: committed.world.head.pointId, before: beforeState, delta: { timeAdvance: commitPoint.timeAdvance, entityDeltas: commitPoint.entityDeltas }, after: state, perspective: `主角视角（${(state as { protagonistId: Id }).protagonistId}「${(state as { initial: { characters: Record<string, { name: string }> } }).initial.characters[(state as { protagonistId: Id }).protagonistId].name}」）；只表达已结算的世界事实` }, output: requests.get('s12')!.text as Json },
  ];
  const memory = initialMemory('req_T08', 'browser');
  const ownership = trace.variables.find((variable) => variable.origin === 'input' && variable.kind === 'ownership')!;
  memory.leaseToken = sample.values[ownership.name] as Id;
  memory.ids['group:person_a'] = groupId;
  memory.ids.successor = prepare.successorPointId as Id;
  memory.prepareSuccessor = true;
  const transport = new ScenarioTransport(corpus.steps, 'T08');
  const model = new ScenarioModelPort(declared, 'T08');
  const driver = new ControllerDriver({ transport, model }, memory, { world: context.world, control: context.control, activeInput: recordedActiveInput });
  return { driver, transport, model, corpus, cancelReason: requests.get('s13')!.cancelReason as string };
}
