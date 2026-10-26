/** T02 fixed-response controller scenarios: DFS group expansion with
 * admitted and rejected rolls (T02) and the empty linked point with its
 * time scan (T02-empty-linked), both driven for both samples. The session
 * opens on an existing world: the bootstrap get_context (s1) and the final
 * get_state are harness-issued inspects; the driver is seeded with the
 * recorded context, the scenario's preallocated lease (the trace's input
 * ownership variable) and the recorded group identities — no create_world,
 * allocate or start_advance exists in these traces.
 *
 * B-authored preview specimens are inserted after every begin/stage anchor:
 * the driver needs a fresh working state there and the contract-layer
 * recording contains no previews. Both traces commit empty entity deltas,
 * so a specimen's working state is the trace's own recorded final state
 * body with the point's staged successor time (amount > 0 advances the
 * dateTime and resets the ordinal, a zero-length instant bumps it), and its
 * pointProjection is the recorded commit request's point — nothing is
 * authored by hand. Every distinct point state was verified at authoring
 * time against the recorded commit head digests (canonical sha256, both
 * samples), and the LAST preview is bound to the final get_state's
 * independent expectation at serve time. Model expectations are generated
 * by walking the recording: discover→action, targets-extend→targets,
 * admit-extend→reaction, stage_unit→results+updates, stage_time_scan→
 * time-scan updates, narration_submit→narration. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ControllerDriver, initialMemory } from './controller';
import { buildCorpus, frozenGroupActionsAtStage, ScenarioModelPort, ScenarioTransport, servedBeforeSteps, type Corpus, type DeclaredModelCall, type PreviewSpecimenSpec, type ReadStateSpecimenSpec } from './harness';
import { ProtocolError } from './protocol';
import { triggerSlotKey } from './schedule';
import { instantiate, readTrace } from './trace-runner';
import type { ControlState, Id, Json, WorldContext } from './types';

export type T02TraceName = 'T02' | 'T02-empty-linked';

export interface WallTime { calendar: string; dateTime: string; instantOrdinal: number }

export interface T02Scenario {
  driver: ControllerDriver;
  transport: ScenarioTransport;
  model: ScenarioModelPort;
  memory: ReturnType<typeof initialMemory>;
  corpus: Corpus;
  roundId: Id;
  bootstrapStepId: string;
  finalStepId: string;
}

/** Staged successor time: any advance moves the clock and resets the
 * ordinal; only a zero-length instant keeps the dateTime and bumps it.
 * Verified against every recorded commit head digest for both traces. */
export function advanceTime(time: WallTime, timeAdvance: { duration: { amount: number } }): WallTime {
  const next = { ...time };
  const amount = timeAdvance.duration.amount;
  if (amount > 0) {
    const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(next.dateTime);
    if (!match) throw new ProtocolError(`Unreadable dateTime: ${next.dateTime}`);
    const total = Number(match[2]) * 3600 + Number(match[3]) * 60 + Number(match[4]) + amount;
    next.dateTime = `${match[1]}T${String(Math.floor(total / 3600)).padStart(2, '0')}:${String(Math.floor((total % 3600) / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
    next.instantOrdinal = 0;
  } else {
    next.instantOrdinal = next.instantOrdinal + 1;
  }
  return next;
}

export function buildT02Scenario(traceName: T02TraceName, sampleId: string): T02Scenario {
  const raw = JSON.parse(readFileSync(resolve(process.cwd(), `../design/world-protocol/v2/traces/${traceName}.json`), 'utf8'));
  const trace = readTrace(raw);
  const sample = trace.samples.find((s) => s.id === sampleId);
  if (!sample) throw new ProtocolError(`Unknown sample ${sampleId}`);
  const requestOf = new Map<string, Record<string, unknown>>();
  const responseOf = new Map<string, Record<string, unknown>>();
  for (const step of trace.steps) {
    requestOf.set(step.id, instantiate(step.request, sample.values) as Record<string, unknown>);
    responseOf.set(step.id, instantiate(step.response, sample.values) as Record<string, unknown>);
  }
  const steps = trace.steps;
  const stepIndex = new Map(steps.map((s, i) => [s.id as string, i]));

  const context = responseOf.get('s1') as unknown as { world: WorldContext & { time: WallTime }; control: ControlState };
  if ((context as { work?: unknown }).work != null) throw new ProtocolError(`[${traceName}] bootstrap context unexpectedly carries point work`);
  const roundId = (context.world.activeRoundId ?? context.world.round?.roundId) as Id;
  const order = (context.world.round as { order: Id[] }).order;
  const finalStep = [...steps].reverse().find((s) => s.operation === 'get_state');
  if (!finalStep) throw new ProtocolError(`[${traceName}] no final get_state step`);
  const finalState = (responseOf.get(finalStep.id) as unknown as { data: { state: Json } }).data.state;

  // Session shape: points are the segments between begins; actors are the
  // discover initiators plus admitted members, in round order.
  const begins = steps.filter((s) => s.operation === 'checkpoint_begin_point');
  if (begins.length === 0) throw new ProtocolError(`[${traceName}] no begin points`);
  const beginIndex = begins.map((b) => stepIndex.get(b.id)!);
  const pointAt = (index: number): number => {
    let point = -1;
    for (let i = 0; i < beginIndex.length; i++) if (beginIndex[i] <= index) point = i;
    if (point < 0) throw new ProtocolError(`[${traceName}] step index ${index} precedes the first begin`);
    return point;
  };
  const actorsByPoint = begins.map((_, i) => {
    const end = i + 1 < beginIndex.length ? beginIndex[i + 1] : steps.length;
    const actors = new Set<Id>();
    const actionText = new Map<Id, string>();
    for (const s of steps.slice(beginIndex[i], end)) {
      const req = requestOf.get(s.id)!;
      if (s.operation === 'checkpoint_discover_group') {
        actors.add(req.initiatorId as Id);
        actionText.set(req.initiatorId as Id, req.actionText as string);
      }
      const admit = req.admittedMember as { memberId: Id; actionText?: string | null } | null | undefined;
      if (admit?.memberId) {
        actors.add(admit.memberId);
        actionText.set(admit.memberId, admit.actionText ?? '');
      }
    }
    return { actors: order.filter((id) => actors.has(id)), actionText };
  });
  // 本组冻结行动与全部骰点判定（§7.1 results 输入）——与控制器 groupActions
  // 逐字镜像：discover 重置建立、admit 前插、create_rolls 追加判定。按组注册
  // （一点可结算多组，驱动器记忆按组重置）。
  const commitByPoint = begins.map((_, i) => {
    const end = i + 1 < beginIndex.length ? beginIndex[i + 1] : steps.length;
    const commit = steps.slice(beginIndex[i], end).find((s) => s.operation === 'commit_point');
    if (!commit) throw new ProtocolError(`[${traceName}] point ${i + 1} has no commit`);
    return commit;
  });

  // Point times: walk the recorded advances from the bootstrap clock.
  const pointTimes: WallTime[] = [];
  {
    let walk: WallTime = structuredClone(context.world.time);
    for (const b of begins) {
      walk = advanceTime(walk, (requestOf.get(b.id)! as { timeAdvance: { duration: { amount: number } } }).timeAdvance);
      pointTimes.push(structuredClone(walk));
    }
  }

  // 触发键与骰点规则自 #8 起由程序提供（fixture-v1/11 与录制一致），
  // 不再从录制的 create_rolls 反推进模型输出。

  // Preview specimens after every begin/stage anchor: recorded final-state
  // body under the point's staged time, recorded commit point as projection,
  // and the candidates staged so far in the point (the driver re-sends them
  // in every preview request once a unit has settled).
  const anchorSteps = steps.filter((s) => ['checkpoint_begin_point', 'checkpoint_stage_unit', 'checkpoint_stage_time_scan'].includes(s.operation));
  const stagedAt = (anchorIndex: number, pointIndex: number): Json[] => {
    const groups: Json[] = [];
    for (const s of steps.slice(beginIndex[pointIndex], anchorIndex + 1)) { // inclusive: the anchor's own stage counts
      // The time-scan unit rides in the same settlement list (A §7) — its
      // candidate enters every later preview of the point.
      if (s.operation === 'checkpoint_stage_unit' || s.operation === 'checkpoint_stage_time_scan') {
        groups.push(structuredClone((requestOf.get(s.id)! as { candidates: Json }).candidates));
      }
    }
    return groups;
  };
  const specimenSpecs = anchorSteps.map((anchor) => {
    const pointIndex = pointAt(stepIndex.get(anchor.id)!);
    return {
      label: `b-preview-after-${anchor.id}`,
      anchorIndex: stepIndex.get(anchor.id)!,
      time: pointTimes[pointIndex],
      projection: structuredClone((requestOf.get(commitByPoint[pointIndex].id)! as { point: Json }).point),
      settlementGroups: stagedAt(stepIndex.get(anchor.id)!, pointIndex),
    };
  });
  const specimenBody = (spec: (typeof specimenSpecs)[number]): { workingState: Json; pointProjection: Json; mergedEntityDeltas: Json; settlementGroups: Json[] } => ({
    workingState: { ...(structuredClone(finalState) as Record<string, unknown>), time: structuredClone(spec.time) } as unknown as Json,
    pointProjection: structuredClone(spec.projection),
    mergedEntityDeltas: {},
    settlementGroups: structuredClone(spec.settlementGroups),
  });
  const specimens: PreviewSpecimenSpec[] = specimenSpecs.map((spec) => ({
    afterStepId: steps[spec.anchorIndex].id,
    label: spec.label,
    build: () => specimenBody(spec),
  }));
  const previewStateAt = (index: number): Json => {
    // STRICTLY before: a model call declared at a step runs before that step
    // is consumed, so the anchor AT the index has not served yet. (T02's
    // empty deltas masked this — the bodies coincided.)
    let chosen: (typeof specimenSpecs)[number] | null = null;
    for (const spec of specimenSpecs) if (spec.anchorIndex < index) chosen = spec;
    if (!chosen) throw new ProtocolError(`[${traceName}] no preview anchor before step index ${index}`);
    return specimenBody(chosen).workingState;
  };

  // 叙事组装（§7.1）：每个 claim 后插入目标读＋前驱读标本。目标态=既定近似
  // 保真度（finalState+点位时间）；点记录逐字取自该点 commit 请求。
  const readSpecimens: ReadStateSpecimenSpec[] = [];
  {
    const bootstrapTime = structuredClone((context.world as unknown as { time: Json }).time);
    const bootstrapHead = (context.world as { head: { pointId: Id; stateDigest: string } }).head;
    const atTime = (time: Json): Json => ({ ...(structuredClone(finalState) as Record<string, unknown>), time: structuredClone(time) }) as unknown as Json;
    for (let i = 0; i < steps.length; i++) {
      if (steps[i].operation !== 'narration_submit') continue;
      const claimStep = steps[i - 1];
      if (!claimStep || claimStep.operation !== 'narration_claim') throw new ProtocolError(`[${traceName}] narration_submit at ${steps[i].id} has no preceding claim`);
      const k = pointAt(stepIndex.get(steps[i].id)!);
      const commitReq = requestOf.get(commitByPoint[k].id)! as { point: { previousPointId: Id | null; timeAdvance: Json; entityDeltas: Json } };
      const head = (responseOf.get(commitByPoint[k].id) as unknown as { world: { head: { pointId: Id; stateDigest: string } } }).world.head;
      const targetState = atTime(pointTimes[k] as unknown as Json);
      const beforeState = k > 0 ? atTime(pointTimes[k - 1] as unknown as Json) : atTime(bootstrapTime);
      const beforeId = commitReq.point.previousPointId as Id;
      const beforeDigest = k > 0
        ? (responseOf.get(commitByPoint[k - 1].id) as unknown as { world: { head: { stateDigest: string } } }).world.head.stateDigest
        : bootstrapHead.stateDigest;
      readSpecimens.push({
        label: `b-read-target-after-${claimStep.id}`,
        afterStepId: claimStep.id,
        data: { pointId: head.pointId, version: 1, stateDigest: head.stateDigest, previousPointId: commitReq.point.previousPointId, timeAdvance: commitReq.point.timeAdvance, entityDeltas: commitReq.point.entityDeltas, state: targetState } as unknown as Json,
      });
      readSpecimens.push({
        label: `b-read-before-after-${claimStep.id}`,
        afterStepId: `b-read-target-after-${claimStep.id}`,
        data: { pointId: beforeId, version: 0, stateDigest: beforeDigest, previousPointId: null, timeAdvance: null, entityDeltas: {}, state: beforeState } as unknown as Json,
      });
    }
  }
  const corpus = buildCorpus(raw, sampleId, specimens, ['s1', finalStep.id], [
    { previewStepId: specimenSpecs[specimenSpecs.length - 1].label, expectationStepId: finalStep.id, workingStatePath: '/data/workingState', workingStateDigestPath: '/data/workingStateDigest' },
  ], [], [], readSpecimens);
  // Serialization adaptation only: the recording writes `targets: null` on
  // admit-shaped extend requests, the driver omits the key. Business fields
  // keep their recorded values.
  for (const step of corpus.steps) {
    if (step.operation === 'checkpoint_extend_group' && (step.request as { targets?: unknown }).targets === null) {
      delete (step.request as { targets?: unknown }).targets;
    }
  }

  // Model expectations, generated by walking the recording.
  const declared: DeclaredModelCall[] = [];
  declared.push({ task: 'pointPlan', key: roundId, input: { round: structuredClone(context.world.round) as Json, head: structuredClone(context.world.head) as Json }, output: begins.map((b, i) => {
    const req = requestOf.get(b.id)! as { pointId: Id; kind: Json; timeAdvance: Json };
    return { pointId: req.pointId, kind: req.kind, timeAdvance: structuredClone(req.timeAdvance), actorIds: actorsByPoint[i].actors };
  }) as unknown as Json });
  const recordedActiveInput = (context as unknown as { activeInput: { advanceId: Id; inputId: Id; text: string } | null }).activeInput;
  // §6.1：行动输入携带调用时刻的链级 advance——玩家输入文本（最后一次
  // context 回包）与消费状态（最近服务态；本轨迹的 2/3 点已在 commit 后
  // 转为 consumed）。
  // 除已播种的引导 context 外，其余 inspect 步骤不经过驱动器，不得更新
  // 「调用时刻服务态」的推导。
  const servedBefore = servedBeforeSteps(steps, responseOf, [finalStep.id]);
  const declaredAdvance = (stepId: string): Json => {
    const served = servedBefore.get(stepId)!;
    return { inputText: served.activeInput?.text ?? null, intentStatus: served.world!.advance.intentStatus };
  };
  // §7.1：results 输入的全组冻结行动与骰点判定——与控制器 groupActions 同源同序。
  const frozenActions = frozenGroupActionsAtStage(steps, requestOf, responseOf);
  for (const s of steps) {
    const index = stepIndex.get(s.id)!;
    const req = requestOf.get(s.id)!;
    if (s.operation === 'checkpoint_discover_group') {
      declared.push({ task: 'action', key: req.initiatorId as Id, input: { actor: req.initiatorId as Id, advance: declaredAdvance(s.id), workingState: previewStateAt(index) }, output: { kind: 'act', text: req.actionText } as unknown as Json });
    } else if (s.operation === 'checkpoint_extend_group') {
      if (req.targets != null) {
        const targetIds = (req.targets as { targetId: Id }[]).map((t) => ({ targetId: t.targetId }));
        const actionText = actorsByPoint[pointAt(index)].actionText.get(req.sourceId as Id) ?? '';
        declared.push({ task: 'targets', key: req.sourceId as Id, input: { sourceId: req.sourceId as Id, actionText, workingState: previewStateAt(index) }, output: { targets: targetIds } as unknown as Json });
      } else {
        const admit = req.admittedMember as { memberId: Id; actionText: string; rollRefs: { rollId: Id }[] };
        const sourceActionText = actorsByPoint[pointAt(index)].actionText.get(req.sourceId as Id) ?? '';
        declared.push({ task: 'reaction', key: req.sourceId as Id, input: { sourceId: req.sourceId as Id, sourceActionText, memberId: admit.memberId, rollId: admit.rollRefs[0].rollId, workingState: previewStateAt(index) }, output: admit.actionText as unknown as Json });
      }
    } else if (s.operation === 'checkpoint_stage_unit') {
      const groupId = (req.candidates as { groupId: Id }).groupId;
      declared.push({ task: 'results', key: groupId, input: { groupId, members: structuredClone(frozenActions.get(s.id)!) as unknown as Json, workingState: previewStateAt(index) }, output: structuredClone(req.results) as Json });
      declared.push({ task: 'updates', key: groupId, input: { groupId, mode: 'group', results: structuredClone(req.results) as Json, workingState: previewStateAt(index) }, output: [] as unknown as Json });
    } else if (s.operation === 'checkpoint_stage_time_scan') {
      declared.push({ task: 'updates', key: `time_scan:${req.pointId as Id}`, input: { mode: 'time_scan', workingState: previewStateAt(index) }, output: [] as unknown as Json });
    } else if (s.operation === 'narration_submit') {
      const k = pointAt(index);
      const head = (responseOf.get(commitByPoint[k].id) as unknown as { world: { head: { pointId: Id; stateDigest: string } } }).world.head;
      const commitReq = requestOf.get(commitByPoint[k].id)! as { point: { previousPointId: Id | null; timeAdvance: Json; entityDeltas: Json } };
      const atTimeLit = (time: Json): Json => ({ ...(structuredClone(finalState) as Record<string, unknown>), time: structuredClone(time) }) as unknown as Json;
      const targetState = atTimeLit(pointTimes[k] as unknown as Json);
      const beforeState = k > 0 ? atTimeLit(pointTimes[k - 1] as unknown as Json) : atTimeLit(structuredClone((context.world as unknown as { time: Json }).time));
      const protagonistId = (finalState as { protagonistId: Id }).protagonistId;
      const protagonistName = ((finalState as { initial: { characters: Record<string, { name: string }> } }).initial.characters[protagonistId]).name;
      // 独立字面量（不经 assembleNarrationInput）。
      declared.push({
        task: 'narration', key: head.pointId,
        input: {
          pointId: head.pointId, before: beforeState,
          delta: { timeAdvance: commitReq.point.timeAdvance, entityDeltas: commitReq.point.entityDeltas },
          after: targetState,
          perspective: `主角视角（${protagonistId}「${protagonistName}」）；只表达已结算的世界事实`,
        },
        output: req.text as unknown as Json,
      });
    }
  }

  const ownership = trace.variables.find((v) => v.origin === 'input' && v.kind === 'ownership');
  if (!ownership) throw new ProtocolError(`[${traceName}] no input ownership variable to seed the lease`);
  const memory = initialMemory(`req_${traceName}`, 'browser');
  memory.leaseToken = sample.values[ownership.name] as Id;
  // 程序掌握触发身份（§9.3）：录制值按调度器的槽位键绑定进 id 表——模型
  // 输出不再携带 triggerKey，控制器从已分配映射解析；create_rolls 的规则
  // 值由程序常量（fixture-v1/11）发出，与录制一致。
  for (const s of steps) {
    if (s.operation === 'checkpoint_discover_group') {
      const req = requestOf.get(s.id)! as { initiatorId: Id; groupId: Id };
      memory.ids[`group:${req.initiatorId}`] = req.groupId;
    }
    if (s.operation === 'checkpoint_extend_group') {
      const req = requestOf.get(s.id)! as { groupId: Id; sourceId: Id; targets?: { targetId: Id; triggerKey: Id }[] | null };
      if (Array.isArray(req.targets)) for (const t of req.targets) memory.ids[triggerSlotKey(req.groupId as Id, req.sourceId as Id, t.targetId)] = t.triggerKey;
    }
  }

  const transport = new ScenarioTransport(corpus.steps, traceName);
  const model = new ScenarioModelPort(declared, traceName);
  const driver = new ControllerDriver({ transport, model }, memory, { world: context.world, control: context.control, activeInput: recordedActiveInput }, { retryLimit: 3 });
  return { driver, transport, model, memory, corpus, roundId, bootstrapStepId: 's1', finalStepId: finalStep.id };
}
