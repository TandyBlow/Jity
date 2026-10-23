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
import { buildCorpus, ScenarioModelPort, ScenarioTransport, type Corpus, type DeclaredModelCall, type PreviewSpecimenSpec } from './harness';
import { ProtocolError } from './protocol';
import { instantiate, readTrace } from './trace-runner';
import type { ControlState, Id, Json, WorldContext } from './types';

export type T02TraceName = 'T02' | 'T02-empty-linked';

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

interface WallTime { calendar: string; dateTime: string; instantOrdinal: number }

/** Staged successor time: any advance moves the clock and resets the
 * ordinal; only a zero-length instant keeps the dateTime and bumps it.
 * Verified against every recorded commit head digest for both traces. */
function advanceTime(time: WallTime, timeAdvance: { duration: { amount: number } }): WallTime {
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

  // Roll rules travel with the targets declarations.
  const ruleByTrigger: Record<string, { ruleVersion: string; target: number }> = {};
  for (const s of steps) {
    if (s.operation === 'create_rolls') {
      for (const roll of (requestOf.get(s.id)! as { rolls: { triggerKey: Id; ruleVersion: string; target: number }[] }).rolls) {
        ruleByTrigger[roll.triggerKey] = { ruleVersion: roll.ruleVersion, target: roll.target };
      }
    }
  }

  // Preview specimens after every begin/stage anchor: recorded final-state
  // body under the point's staged time, recorded commit point as projection,
  // and the candidates staged so far in the point (the driver re-sends them
  // in every preview request once a unit has settled).
  const anchorSteps = steps.filter((s) => ['checkpoint_begin_point', 'checkpoint_stage_unit', 'checkpoint_stage_time_scan'].includes(s.operation));
  const stagedAt = (anchorIndex: number, pointIndex: number): Json[] => {
    const groups: Json[] = [];
    for (const s of steps.slice(beginIndex[pointIndex], anchorIndex + 1)) { // inclusive: the anchor's own stage counts
      if (s.operation === 'checkpoint_stage_unit') groups.push(structuredClone((requestOf.get(s.id)! as { candidates: Json }).candidates));
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
    let chosen: (typeof specimenSpecs)[number] | null = null;
    for (const spec of specimenSpecs) if (spec.anchorIndex <= index) chosen = spec;
    if (!chosen) throw new ProtocolError(`[${traceName}] no preview anchor before step index ${index}`);
    return specimenBody(chosen).workingState;
  };

  const corpus = buildCorpus(raw, sampleId, specimens, ['s1', finalStep.id], [
    { previewStepId: specimenSpecs[specimenSpecs.length - 1].label, expectationStepId: finalStep.id, workingStatePath: '/data/workingState', workingStateDigestPath: '/data/workingStateDigest' },
  ], []);
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
  for (const s of steps) {
    const index = stepIndex.get(s.id)!;
    const req = requestOf.get(s.id)!;
    if (s.operation === 'checkpoint_discover_group') {
      declared.push({ task: 'action', key: req.initiatorId as Id, input: { actor: req.initiatorId as Id, workingState: previewStateAt(index) }, output: { kind: 'act', text: req.actionText } as unknown as Json });
    } else if (s.operation === 'checkpoint_extend_group') {
      if (req.targets != null) {
        const targets = (req.targets as { targetId: Id; triggerKey: Id }[]).map((t) => ({ targetId: t.targetId, triggerKey: t.triggerKey, ...ruleByTrigger[t.triggerKey] }));
        const actionText = actorsByPoint[pointAt(index)].actionText.get(req.sourceId as Id) ?? '';
        declared.push({ task: 'targets', key: req.sourceId as Id, input: { sourceId: req.sourceId as Id, actionText, workingState: previewStateAt(index) }, output: { targets } as unknown as Json });
      } else {
        const admit = req.admittedMember as { memberId: Id; actionText: string; rollRefs: { rollId: Id }[] };
        declared.push({ task: 'reaction', key: req.sourceId as Id, input: { sourceId: req.sourceId as Id, memberId: admit.memberId, rollId: admit.rollRefs[0].rollId, workingState: previewStateAt(index) }, output: admit.actionText as unknown as Json });
      }
    } else if (s.operation === 'checkpoint_stage_unit') {
      const groupId = (req.candidates as { groupId: Id }).groupId;
      declared.push({ task: 'results', key: groupId, input: { groupId, workingState: previewStateAt(index) }, output: structuredClone(req.results) as Json });
      declared.push({ task: 'updates', key: groupId, input: { groupId, mode: 'group', workingState: previewStateAt(index), priorStages: [], appliedDelta: {} }, output: [] as unknown as Json });
    } else if (s.operation === 'checkpoint_stage_time_scan') {
      declared.push({ task: 'updates', key: `time_scan:${req.pointId as Id}`, input: { mode: 'time_scan', workingState: previewStateAt(index), priorStages: [], appliedDelta: {} }, output: [] as unknown as Json });
    } else if (s.operation === 'narration_submit') {
      const head = (responseOf.get(commitByPoint[pointAt(index)].id) as unknown as { world: { head: { pointId: Id; stateDigest: string } } }).world.head;
      declared.push({ task: 'narration', key: head.pointId, input: { pointId: head.pointId, stateDigest: head.stateDigest }, output: req.text as unknown as Json });
    }
  }

  const ownership = trace.variables.find((v) => v.origin === 'input' && v.kind === 'ownership');
  if (!ownership) throw new ProtocolError(`[${traceName}] no input ownership variable to seed the lease`);
  const memory = initialMemory(`req_${traceName}`, 'browser');
  memory.leaseToken = sample.values[ownership.name] as Id;
  for (const s of steps) {
    if (s.operation === 'checkpoint_discover_group') {
      const req = requestOf.get(s.id)! as { initiatorId: Id; groupId: Id };
      memory.ids[`group:${req.initiatorId}`] = req.groupId;
    }
  }

  const transport = new ScenarioTransport(corpus.steps, traceName);
  const model = new ScenarioModelPort(declared, traceName);
  const driver = new ControllerDriver({ transport, model }, memory, { world: context.world, control: context.control }, { retryLimit: 3 });
  return { driver, transport, model, memory, corpus, roundId, bootstrapStepId: 's1', finalStepId: finalStep.id };
}
