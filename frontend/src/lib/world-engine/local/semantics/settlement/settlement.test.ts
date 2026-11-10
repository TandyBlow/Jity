import { describe, expect, it } from 'vitest';
import type { InferenceEngine } from '../../../runtime/engine';
import type { InitialState, Json, WorldState } from '../../../types';
import type { UpdatesCall, UpdatesStage } from '../../../schedule';
import { buildInitialState } from '../../state';
import { projectStage } from './support';
import { createSettlementHandlers, continuationPolicy } from './index';

class ScriptedEngine implements InferenceEngine {
  readonly info = { backend: 'scripted', modelId: 'scripted' };
  readonly prompts: string[] = [];
  private index = 0;

  constructor(private readonly outputs: (string | Error)[]) {}

  async load(): Promise<void> {}

  async complete(prompt: string): Promise<string> {
    this.prompts.push(prompt);
    const output = this.outputs[this.index++];
    if (output instanceof Error) throw output;
    if (output == null) throw new Error('scripted engine has no output left');
    return output;
  }

  async dispose(): Promise<void> {}
}

function world(options: { a1Achieved?: boolean; farOnly?: boolean } = {}): WorldState {
  const initial: InitialState = {
    engineVersion: 'world-engine-v1',
    schemaVersion: 1,
    worldId: 'w_settlement',
    protagonistId: 'a',
    initialTime: { calendar: 'gregorian', dateTime: '2026-11-09T12:00:00', instantOrdinal: 0 },
    locations: {
      room: { id: 'room', name: '房间', parentLocationId: null, initialAppearance: '一间普通的房间。' },
      far: { id: 'far', name: '远处', parentLocationId: null, initialAppearance: '远处的走廊。' },
    },
    items: {
      tool: { id: 'tool', name: '工具', initialPosition: { containerId: 'room' }, initialAppearance: '一把旧工具。' },
      box: { id: 'box', name: '盒子', initialPosition: { containerId: 'room' }, initialAppearance: '一个木盒。' },
    },
    characters: {
      a: {
        id: 'a', name: '甲', initialPosition: { containerId: 'room' },
        initialAppearance: '穿着外套。', initialPersonality: '谨慎。', initialSanity: 60,
        tasks: {
          a1: { id: 'a1', ownerId: 'a', parentTaskId: null, goal: '拿到工具', status: options.a1Achieved ? 'achieved' : 'pending' },
          a2: { id: 'a2', ownerId: 'a', parentTaskId: null, goal: '已经完成的事', status: 'achieved' },
        },
      },
      b: {
        id: 'b', name: '乙', initialPosition: { containerId: options.farOnly ? 'far' : 'room' },
        initialAppearance: '站在门边。', initialPersonality: '直率。', initialSanity: 55,
        tasks: { b1: { id: 'b1', ownerId: 'b', parentTaskId: null, goal: '协助甲', status: 'pending' } },
      },
      c: {
        id: 'c', name: '丁', initialPosition: { containerId: 'room' },
        initialAppearance: '沉默地坐着。', initialPersonality: '安静。', initialSanity: 70,
        tasks: {},
      },
      off: {
        id: 'off', name: '丙', initialPosition: { containerId: 'far' },
        initialAppearance: '在远处张望。', initialPersonality: '多疑。', initialSanity: 50,
        tasks: { off1: { id: 'off1', ownerId: 'off', parentTaskId: null, goal: '在远处等待', status: 'pending' } },
      },
    },
  };
  return buildInitialState(initial);
}

function resultsInput(state = world()) {
  return {
    groupId: 'g1',
    members: [
      { memberId: 'a', actionText: '甲把工具推向乙。', rollRefs: [{ targetId: 'b', rollId: 'r1', result: 15, eligible: true, admitted: true }] },
      { memberId: 'b', actionText: '乙伸手接住工具。', rollRefs: [] },
    ],
    workingState: state,
  } as unknown as Json;
}

function updatesInput(state = world(), stage?: UpdatesStage, mode: 'group' | 'time_scan' = 'group') {
  return {
    groupId: mode === 'group' ? 'g1' : undefined,
    mode,
    stage,
    results: mode === 'group' ? { a: '甲退到远处，工具被放进盒子。', b: '乙留在房间。', off: '丙仍在远处。' } : undefined,
    workingState: state,
  } as unknown as Json;
}

function continuationInput(roundChanges: Json[], roundId = 'r1', headPointId = 'p1') {
  return {
    round: { roundId, trigger: 'automatic', conclusion: null },
    head: { pointId: headPointId },
    workingState: world(),
    roundChanges,
  } as unknown as Json;
}

// Automatic rounds may only carry a same-scene character other than the
// protagonist: the player owns the protagonist's next action.
const continueProposal = (text = '乙继续向前走。') => JSON.stringify({ candidates: [{ characterId: 'b', text }] });
const continueJudgment = (text = '乙继续向前走。') => JSON.stringify({
  judgments: [{ characterId: 'b', text, likely: true, related: true, reason: '与主角眼前这件事直接相关。' }],
});

describe('common-group results', () => {
  it('attributes shared facts to every member and keeps member facts separate', async () => {
    const engine = new ScriptedEngine([JSON.stringify({
      judgments: [
        { memberId: 'a', label: 'partial', reason: '推到了但没交稳。', effects: [{ targetId: 'b', reacted: true }] },
        { memberId: 'b', label: 'achieved', reason: '接住了。', effects: [] },
      ],
      facts: [
        { text: '甲把工具推向乙，乙伸手接住。', memberIds: ['a', 'b'] },
        { text: '工具落在乙脚边。', memberIds: ['b'] },
      ],
    })]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.results('g1', resultsInput());
    expect(outcome.value).not.toBeNull();
    expect(outcome.value!.a).toContain('乙伸手接住');
    expect(outcome.value!.b).toContain('乙伸手接住');
    expect(outcome.value!.b).toContain('工具落在乙脚边');
    expect(outcome.fallback).toBe(false);
    const detail = outcome.evidence.detail as { memberFactCoverage: { memberId: string; factCount: number }[] };
    expect(detail.memberFactCoverage).toEqual([
      { memberId: 'a', factCount: 1 },
      { memberId: 'b', factCount: 2 },
    ]);
  });

  it('rejects a denied roll narrated as a reaction and retries with feedback', async () => {
    const state = world();
    const input = {
      groupId: 'g1',
      members: [
        { memberId: 'a', actionText: '甲伸手抓向乙。', rollRefs: [{ targetId: 'b', rollId: 'r1', result: 3, eligible: true, admitted: false }] },
        { memberId: 'b', actionText: '乙侧身避开。', rollRefs: [] },
      ],
      workingState: state,
    } as unknown as Json;
    const invalid = JSON.stringify({
      judgments: [
        { memberId: 'a', label: 'partial', reason: '抓到了。', effects: [{ targetId: 'b', reacted: true }] },
        { memberId: 'b', label: 'achieved', reason: '躲开。', effects: [] },
      ],
      facts: [{ text: '甲抓住了乙。', memberIds: ['a', 'b'] }],
    });
    const valid = JSON.stringify({
      judgments: [
        { memberId: 'a', label: 'not_achieved', reason: '乙没有反应。', effects: [{ targetId: 'b', reacted: false }] },
        { memberId: 'b', label: 'no_change', reason: '乙没有被迫行动。', effects: [] },
      ],
      facts: [{ text: '甲伸手，乙没有反应。', memberIds: ['a', 'b'] }],
    });
    const engine = new ScriptedEngine([invalid, valid]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.results('g1', input);
    expect(outcome.value!.a).toContain('乙没有反应');
    expect(outcome.evidence.calls).toHaveLength(2);
    expect(engine.prompts[1]).toContain('reacted=true contradicts admitted=false');
  });

  it('aborts the point after repeated invalid output instead of inventing a result', async () => {
    const engine = new ScriptedEngine(['not json', 'still not json']);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.results('g1', resultsInput());
    expect(outcome.value).toBeNull();
    expect(outcome.fallback).toBe(true);
    expect(outcome.error).toContain('model_output_invalid');
    const detail = outcome.evidence.detail as { reason: string };
    expect(detail.reason).toBe('point_aborted_after_repair');
    expect(outcome.raw).toContain('not json');
  });
});

describe('six-stage updates', () => {
  it('runs the canonical six stages, moves an item, covers the full cast, and pairs personality with sanity', async () => {
    const engine = new ScriptedEngine([
      JSON.stringify({ changes: [
        { entityId: 'a', containerId: 'far', slotId: null, relativeTo: null },
        { entityId: 'tool', containerId: 'box', slotId: null, relativeTo: null },
      ] }),
      JSON.stringify({ operations: [{ entityId: 'tool', op: 'add', recordIds: [], text: '表面沾了灰' }] }),
      JSON.stringify({ unchanged: ['b'], achieved: [
        { characterId: 'a', achieved: ['a1'] },
        { characterId: 'off', achieved: ['off1'] },
      ] }),
      JSON.stringify({ subtasks: [{ parentTaskId: 'a1', goal: '把工具从盒子里取回' }] }),
      JSON.stringify({ scanned: ['a', 'b', 'c', 'off'], changes: [
        { entityId: 'a', op: 'add', recordIds: [], text: '更愿意相信同伴' },
        { entityId: 'off', op: 'add', recordIds: [], text: '开始留意远处的动静' },
      ] }),
      JSON.stringify({ sanity: [{ characterId: 'a', value: 52 }, { characterId: 'off', value: 48 }] }),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('g1', updatesInput());
    expect(Array.isArray(outcome.value)).toBe(true);
    const calls = outcome.value as UpdatesCall[];
    expect(calls.map((call) => call.stage)).toEqual(['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity']);
    expect(calls[0].changes.a.positionSet).toEqual({ containerId: 'far', slotId: null, relativeTo: null });
    expect(calls[0].changes.tool.positionSet).toEqual({ containerId: 'box', slotId: null, relativeTo: null });
    expect(calls[1].changes.tool.appearanceChanges?.[0].text).toBe('表面沾了灰');
    expect(calls[2].changes.a.tasksAchieved).toEqual(['a1']);
    expect(calls[2].changes.a.tasksAchieved).not.toContain('a2');
    expect(calls[2].changes.off.tasksAchieved).toEqual(['off1']);
    expect(calls[3].changes.a.subtasksAdded?.[0]).toMatchObject({ ownerId: 'a', parentTaskId: 'a1', status: 'pending' });
    expect(Object.keys(calls[4].changes).sort()).toEqual(['a', 'off']);
    expect(calls[5].changes.a.sanitySet).toBe(52);
    expect(calls[5].changes.off.sanitySet).toBe(48);
    const detail = outcome.evidence.detail as { taskCoverageIds: string[]; personalityCoverageIds: string[] };
    expect(detail.taskCoverageIds).toEqual(['a', 'b', 'c', 'off']);
    expect(detail.personalityCoverageIds).toEqual(['a', 'b', 'c', 'off']);
    // The tasks stage reads the post-position working state.
    const tasksPrompt = engine.prompts.find((prompt) => prompt.includes('任务判定器'))!;
    expect(tasksPrompt).toContain('甲（id=a）位置=远处');
    const personalityPrompt = engine.prompts.find((prompt) => prompt.includes('个性变化判断器'))!;
    for (const id of ['a', 'b', 'c', 'off']) expect(personalityPrompt).toContain(`\"${id}\"`);
  });

  it('does not re-achieve an already achieved task', async () => {
    const engine = new ScriptedEngine([
      JSON.stringify({ changes: [] }),
      JSON.stringify({ operations: [] }),
      JSON.stringify({ decisions: [
        { characterId: 'a', achieved: [] },
        { characterId: 'b', achieved: [] },
        { characterId: 'off', achieved: [] },
      ] }),
      JSON.stringify({ subtasks: [] }),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('g1', updatesInput());
    const calls = outcome.value as UpdatesCall[];
    expect(calls[2].changes).toEqual({});
    expect(engine.prompts.filter((prompt) => prompt.includes('个性变化判断器'))).toHaveLength(0);
    expect(engine.prompts.filter((prompt) => prompt.includes('理智重算器'))).toHaveLength(0);
  });

  it('skips position/appearance on a time scan, scans every task, and keeps sanity empty when personality stays unchanged', async () => {
    const engine = new ScriptedEngine([
      JSON.stringify({ decisions: [
        { characterId: 'a', achieved: ['a1'] },
        { characterId: 'b', achieved: [] },
        { characterId: 'off', achieved: [] },
      ] }),
      JSON.stringify({ subtasks: [] }),
      JSON.stringify({ operations: [
        { entityId: 'a', op: 'keep', recordIds: [], text: null },
        { entityId: 'b', op: 'keep', recordIds: [], text: null },
        { entityId: 'c', op: 'keep', recordIds: [], text: null },
        { entityId: 'off', op: 'keep', recordIds: [], text: null },
      ] }),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('time_scan:p1', updatesInput(world(), undefined, 'time_scan'));
    const calls = outcome.value as UpdatesCall[];
    expect(calls[0].changes).toEqual({});
    expect(calls[1].changes).toEqual({});
    expect(calls[2].changes.a.tasksAchieved).toEqual(['a1']);
    expect(calls[4].changes).toEqual({});
    expect(calls[5].changes).toEqual({});
    expect(engine.prompts.every((prompt) => !prompt.includes('位置结算器'))).toBe(true);
    expect(engine.prompts.every((prompt) => !prompt.includes('外貌结算器'))).toBe(true);
    expect(engine.prompts.some((prompt) => prompt.includes('理智重算器'))).toBe(false);
  });

  it('aborts the whole six-stage point when the sanity answer cannot be repaired', async () => {
    const engine = new ScriptedEngine([
      JSON.stringify({ changes: [] }),
      JSON.stringify({ operations: [] }),
      JSON.stringify({ decisions: [
        { characterId: 'a', achieved: ['a1'] },
        { characterId: 'b', achieved: [] },
        { characterId: 'off', achieved: [] },
      ] }),
      JSON.stringify({ subtasks: [] }),
      JSON.stringify({ operations: [
        { entityId: 'a', op: 'add', recordIds: [], text: '更愿意相信同伴' },
        { entityId: 'b', op: 'keep', recordIds: [], text: null },
        { entityId: 'c', op: 'keep', recordIds: [], text: null },
        { entityId: 'off', op: 'keep', recordIds: [], text: null },
      ] }),
      JSON.stringify({ sanity: [] }),
      JSON.stringify({ sanity: [] }),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('g1', updatesInput());
    expect(outcome.value).toBeNull();
    expect(outcome.fallback).toBe(true);
    expect(outcome.error).toContain('missing sanity');
    const detail = outcome.evidence.detail as { reason: string; stageErrors?: { stage: string }[] };
    expect(detail.reason).toBe('point_aborted_after_repair');
    expect(detail.stageErrors?.map((row) => row.stage)).toEqual(['sanity']);
  });

  it('returns one UpdatesCall for a split stage and uses the batch task achievement for personality', async () => {
    const engine = new ScriptedEngine([
      JSON.stringify({ decisions: [
        { characterId: 'a', achieved: ['a1'] },
        { characterId: 'b', achieved: [] },
        { characterId: 'off', achieved: [] },
      ] }),
      JSON.stringify({ operations: [
        { entityId: 'a', op: 'keep', recordIds: [], text: null },
        { entityId: 'b', op: 'keep', recordIds: [], text: null },
        { entityId: 'c', op: 'keep', recordIds: [], text: null },
        { entityId: 'off', op: 'keep', recordIds: [], text: null },
      ] }),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const state = world();
    const tasks = await handlers.updates('g1#tasks', updatesInput(state, 'tasks'));
    expect(Array.isArray(tasks.value)).toBe(false);
    const taskCall = tasks.value as UpdatesCall;
    expect(taskCall.stage).toBe('tasks');
    expect(taskCall.changes.a.tasksAchieved).toEqual(['a1']);
    const afterTasks = projectStage(state, 'tasks', taskCall.changes);
    const personality = await handlers.updates('g1#personality', updatesInput(afterTasks, 'personality'));
    expect(Array.isArray(personality.value)).toBe(false);
    expect(engine.prompts.filter((prompt) => prompt.includes('个性变化判断器'))).toHaveLength(1);
    const sanity = await handlers.updates('g1#sanity', updatesInput(afterTasks, 'sanity'));
    expect(Array.isArray(sanity.value)).toBe(false);
    expect(engine.prompts.filter((prompt) => prompt.includes('理智重算器'))).toHaveLength(0);
  });
});

describe('continuation', () => {
  const progress = (amount = 59): Json[] => [{
    pointId: 'p1',
    timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
    entityDeltas: { a: { entityId: 'a', sanitySet: amount } },
  }];

  it('continues when a candidate is likely and related', async () => {
    const engine = new ScriptedEngine([continueProposal(), continueJudgment()]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.continuation('r1', continuationInput(progress()));
    expect(outcome.value).toEqual({
      kind: 'continue', closedBy: 'model', cancelReason: null,
      candidateCharacterIds: ['b'], nextRoundId: expect.any(String),
    });
    expect((outcome.value as { nextRoundId: string }).nextRoundId).not.toBe('r1');
    expect((outcome.evidence.detail as { decision: string }).decision).toBe('continue');
  });

  it('accepts candidateId judgments from the constrained schema', async () => {
    const engine = new ScriptedEngine([
      continueProposal(),
      JSON.stringify({ judgments: [{ candidateId: 'c1', likely: true, related: true, reason: '主角自己的下一步。' }] }),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.continuation('r1', continuationInput(progress()));
    expect((outcome.value as { kind: string }).kind).toBe('continue');
  });

  it('hands back when the model proposes no candidate', async () => {
    const engine = new ScriptedEngine([JSON.stringify({ candidates: [] })]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.continuation('r1', continuationInput(progress()));
    expect(outcome.value).toEqual({ kind: 'handback', closedBy: 'model', cancelReason: null });
    expect((outcome.evidence.detail as { reason: string }).reason).toBe('model_no_candidate');
    expect(engine.prompts).toHaveLength(1);
  });

  it('does not use a default call cap: three progressing chains all continue', async () => {
    const engine = new ScriptedEngine([
      continueProposal('乙继续向前走。'), continueJudgment('乙继续向前走。'),
      continueProposal('乙推开门。'), continueJudgment('乙推开门。'),
      continueProposal('乙走进门里。'), continueJudgment('乙走进门里。'),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const outcomes = [];
    for (let index = 0; index < 3; index += 1) {
      outcomes.push(await handlers.continuation(`r${index + 1}`, continuationInput(progress(59 - index), `r${index + 1}`)));
    }
    expect(outcomes.map((outcome) => (outcome.value as { kind: string }).kind)).toEqual(['continue', 'continue', 'continue']);
    expect((outcomes[2].evidence.detail as { policy: { continues: number } }).policy.continues).toBe(3);
    expect(continuationPolicy.maxAutoContinuations).toBeNull();
  });

  it('stops a no-progress chain as a policy stop, never as a model handback', async () => {
    const engine = new ScriptedEngine([
      continueProposal('乙继续向前走。'), continueJudgment('乙继续向前走。'),
      continueProposal('乙停下来听。'), continueJudgment('乙停下来听。'),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const first = await handlers.continuation('r1', continuationInput([]));
    const second = await handlers.continuation('r2', continuationInput([]));
    expect((first.value as { kind: string }).kind).toBe('continue');
    // The transport records every handback as closedBy:'model'; a policy stop
    // therefore must carry no conclusion value at all.
    expect(second.value).toBeNull();
    expect(second.error).toBe('continuation_policy_no_progress');
    const detail = second.evidence.detail as { decision: string; policy: { anomaly: boolean } };
    expect(detail.decision).toBe('policy_stop');
    expect(detail.policy.anomaly).toBe(false);
    expect(continuationPolicy.noProgressRounds).toBe(2);
  });

  it('hands back when the same candidate repeats after two progressing rounds', async () => {
    const engine = new ScriptedEngine([
      continueProposal('乙继续向前走。'), continueJudgment('乙继续向前走。'),
      continueProposal('乙继续向前走。'), continueJudgment('乙继续向前走。'),
      continueProposal('乙继续向前走。'), continueJudgment('乙继续向前走。'),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const first = await handlers.continuation('r1', continuationInput(progress(59)));
    const second = await handlers.continuation('r2', continuationInput(progress(58)));
    const third = await handlers.continuation('r3', continuationInput(progress(57)));
    expect((first.value as { kind: string }).kind).toBe('continue');
    expect((second.value as { kind: string }).kind).toBe('continue');
    expect(third.value).toBeNull();
    expect(third.error).toBe('continuation_policy_repeated_candidate');
    expect((third.evidence.detail as { decision: string }).decision).toBe('policy_stop');
  });

  it('turns a configured 0 call cap into a policy stop, not a model handback', async () => {
    const engine = new ScriptedEngine([continueProposal(), continueJudgment()]);
    const handlers = createSettlementHandlers({ engine, options: { continuation: { maxAutoContinuations: 0 } } });
    const outcome = await handlers.continuation('r1', continuationInput(progress(59)));
    expect(outcome.value).toBeNull();
    expect(outcome.error).toBe('continuation_policy_safety_cap');
    const detail = outcome.evidence.detail as { decision: string; anomaly: boolean; policy: { reason: string } };
    expect(detail.decision).toBe('policy_stop');
    expect(detail.anomaly).toBe(true);
    expect(detail.policy.reason).toBe('safety_cap');
    // The model still ran: the cap is a program stop, not a skipped judgement.
    expect(engine.prompts).toHaveLength(2);
  });

  it('drops a protagonist candidate: the player owns the protagonist action', async () => {
    const engine = new ScriptedEngine([JSON.stringify({ candidates: [{ characterId: 'a', text: '甲自己继续向前走。' }] })]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.continuation('r1', continuationInput(progress()));
    expect(outcome.value).toEqual({ kind: 'handback', closedBy: 'model', cancelReason: null });
    const detail = outcome.evidence.detail as { reason: string; rejectedCandidates: { reason: string }[] };
    expect(detail.reason).toBe('no_eligible_candidate');
    expect(detail.rejectedCandidates[0].reason).toBe('protagonist_action_belongs_to_player');
    // The judgment call is not spent on an ineligible candidate.
    expect(engine.prompts).toHaveLength(1);
    expect(engine.prompts[0]).toContain('主角自己的下一步由玩家决定');
  });

  it('drops a candidate who is outside the protagonist scene', async () => {
    const packet = continuationInput(progress());
    (packet as unknown as { workingState: ReturnType<typeof world> }).workingState = world({ farOnly: true });
    const engine = new ScriptedEngine([JSON.stringify({ candidates: [{ characterId: 'b', text: '乙在远处继续向前走。' }] })]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.continuation('r1', packet);
    expect(outcome.value).toEqual({ kind: 'handback', closedBy: 'model', cancelReason: null });
    const detail = outcome.evidence.detail as { reason: string; rejectedCandidates: { reason: string }[] };
    expect(detail.reason).toBe('no_eligible_candidate');
    expect(detail.rejectedCandidates[0].reason).toBe('character_outside_protagonist_scene');
  });

  it('surfaces a model failure as no candidate, never as a handback', async () => {
    const engine = new ScriptedEngine([new Error('engine offline'), new Error('engine offline')]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.continuation('r1', continuationInput(progress()));
    expect(outcome.value).toBeNull();
    expect(outcome.error).toContain('engine offline');
    expect(outcome.evidence.detail).toMatchObject({ decision: 'failed' });
  });

  it('rejects a stale head instead of deciding on mismatched round changes', async () => {
    const engine = new ScriptedEngine([]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.continuation('r1', continuationInput(progress(), 'r1', 'other_point'));
    expect(outcome.value).toBeNull();
    expect(outcome.error).toContain('continuation_head_mismatch');
    expect(engine.prompts).toHaveLength(0);
  });
});

describe('real failed-output shapes (09 product run)', () => {
  it('repairs a task answer that skips a whole character, then covers every character', async () => {
    const partial = JSON.stringify({ decisions: [
      { characterId: 'a', achieved: ['a1'] },
      { characterId: 'b', achieved: [] },
    ] });
    const full = JSON.stringify({ decisions: [
      { characterId: 'a', achieved: ['a1'] },
      { characterId: 'b', achieved: [] },
      { characterId: 'off', achieved: ['off1'] },
    ] });
    const engine = new ScriptedEngine([partial, full]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('g1#tasks', updatesInput(world(), 'tasks'));
    expect(outcome.value).not.toBeNull();
    const call = outcome.value as UpdatesCall;
    expect(call.changes.a?.tasksAchieved).toEqual(['a1']);
    expect(call.changes.off?.tasksAchieved).toEqual(['off1']);
    expect(engine.prompts).toHaveLength(2);
    expect(engine.prompts[1]).toContain('task character coverage incomplete: 2/3; missing off');
    expect(engine.prompts[1]).toContain('每个有任务的人物必须出现一次');
    // The first prompt already carries a copyable row for every required
    // character, so a format-copying model still answers all of them.
    for (const id of ['a', 'b', 'off']) expect(engine.prompts[0]).toContain(`\"${id}\"`);
    const detail = outcome.evidence.detail as { taskScope: { mode: string; characters: number; taskRows: number; assertedUnchanged: number } };
    expect(detail.taskScope).toMatchObject({
      mode: 'per_character_decision', characters: 3, taskRows: 4, assertedUnchanged: 2, excluded: [], emptyCharacters: 1,
      achievedByCharacter: [{ characterId: 'a', taskIds: ['a1'] }, { characterId: 'off', taskIds: ['off1'] }],
    });
  });

  it('accepts a unique full character name for a task decision', async () => {
    const engine = new ScriptedEngine([JSON.stringify({ decisions: [
      { characterId: '甲', achieved: ['a1'] },
      { characterId: '乙', achieved: [] },
      { characterId: '丙', achieved: [] },
    ] })]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('g1#tasks', updatesInput(world(), 'tasks'));
    const call = outcome.value as UpdatesCall;
    expect(call.changes.a?.tasksAchieved).toEqual(['a1']);
  });

  it('repairs the literal id placeholder before accepting a position change', async () => {
    const engine = new ScriptedEngine([
      JSON.stringify({ changes: [{ entityId: 'id', containerId: 'far', slotId: null, relativeTo: null }] }),
      JSON.stringify({ changes: [{ entityId: 'a', containerId: 'far', slotId: null, relativeTo: null }] }),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('g1#position', updatesInput(world(), 'position'));
    expect(outcome.value).not.toBeNull();
    expect((outcome.value as UpdatesCall).changes.a?.positionSet?.containerId).toBe('far');
    expect(engine.prompts[1]).toContain('placeholder_id:id');
    expect(engine.prompts[1]).toContain('例如 a');
  });

  it('aborts a position stage whose placeholder is not repaired', async () => {
    const engine = new ScriptedEngine([
      JSON.stringify({ changes: [{ entityId: 'id', containerId: 'far', slotId: null, relativeTo: null }] }),
      JSON.stringify({ changes: [{ entityId: 'id', containerId: 'far', slotId: null, relativeTo: null }] }),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('g1#position', updatesInput(world(), 'position'));
    expect(outcome.value).toBeNull();
    expect(outcome.error).toContain('placeholder_id:id');
    expect(outcome.evidence.detail).toMatchObject({ reason: 'point_aborted_after_repair' });
  });

  it('repairs an effect for an undeclared target and resolves full names', async () => {
    const invalid = JSON.stringify({
      judgments: [
        { memberId: 'a', label: 'partial', reason: '推到了。', effects: [{ targetId: 'tool', reacted: true }] },
        { memberId: 'b', label: 'no_change', reason: '没有反应。', effects: [] },
      ],
      facts: [{ text: '甲把工具推向乙。', memberIds: ['a', 'b'] }],
    });
    const valid = JSON.stringify({
      judgments: [
        { memberId: '甲', label: 'partial', reason: '推到了。', effects: [{ targetId: '乙', reacted: true }] },
        { memberId: '乙', label: 'no_change', reason: '没有反应。', effects: [] },
      ],
      facts: [{ text: '甲把工具推向乙。', memberIds: ['甲', '乙'] }],
    });
    const engine = new ScriptedEngine([invalid, valid]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.results('g1', resultsInput());
    expect(outcome.value).not.toBeNull();
    expect(outcome.value!.a).toContain('甲把工具推向乙');
    expect(engine.prompts[1]).toContain('effect for undeclared target tool');
    expect(engine.prompts[1]).toContain('判定目标只有 b');
  });

  it('does not invent a member when the model writes the schema placeholder', async () => {
    const invalid = JSON.stringify({
      judgments: [
        { memberId: '成员id', label: 'partial', reason: '推到了。', effects: [] },
        { memberId: 'b', label: 'no_change', reason: '没有反应。', effects: [] },
      ],
      facts: [{ text: '甲把工具推向乙。', memberIds: ['a', 'b'] }],
    });
    const valid = JSON.stringify({
      judgments: [
        { memberId: 'a', label: 'partial', reason: '推到了。', effects: [{ targetId: 'b', reacted: true }] },
        { memberId: 'b', label: 'no_change', reason: '没有反应。', effects: [] },
      ],
      facts: [{ text: '甲把工具推向乙。', memberIds: ['a', 'b'] }],
    });
    const engine = new ScriptedEngine([invalid, valid]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.results('g1', resultsInput());
    expect(outcome.value).not.toBeNull();
    expect(engine.prompts[1]).toContain('placeholder_id:成员id');
  });

  it('resolves a protagonist full name to the id and still drops the candidate', async () => {
    const engine = new ScriptedEngine([JSON.stringify({ candidates: [{ characterId: '甲', text: '甲自己继续向前走。' }] })]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.continuation('r1', continuationInput([]));
    expect(outcome.value).toEqual({ kind: 'handback', closedBy: 'model', cancelReason: null });
    const detail = outcome.evidence.detail as { reason: string; rejectedCandidates: { characterId: string; reason: string }[] };
    expect(detail.reason).toBe('no_eligible_candidate');
    expect(detail.rejectedCandidates[0]).toMatchObject({ characterId: 'a', reason: 'protagonist_action_belongs_to_player' });
    expect(engine.prompts).toHaveLength(1);
  });

  it('resolves a full name in both the proposal and the judgment', async () => {
    const proposal = JSON.stringify({ candidates: [{ characterId: '乙', text: '乙继续向前走。' }] });
    const judgment = JSON.stringify({ judgments: [{ characterId: '乙', text: '乙继续向前走。', likely: true, related: true, reason: '相关。' }] });
    const engine = new ScriptedEngine([proposal, judgment]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.continuation('r1', continuationInput([]));
    expect(outcome.value).toMatchObject({ kind: 'continue' });
  });
});

describe('results group membership (09 one-legal-turn shape)', () => {
  const memberFact = (text: string) => ({ text, memberIds: ['a', 'b'] });

  it('drops a scene bystander judgment with no effect instead of failing the turn', async () => {
    const answer = JSON.stringify({
      judgments: [
        { memberId: 'a', label: 'partial', reason: '甲推到了。', effects: [{ targetId: 'b', reacted: true }] },
        { memberId: 'b', label: 'no_change', reason: '乙没有反应。', effects: [] },
        { memberId: 'c', label: 'partial', reason: '丁在旁边问了一句。', effects: [] },
      ],
      facts: [memberFact('甲把工具推向乙，丁在旁边看着。')],
    });
    const engine = new ScriptedEngine([answer]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.results('g1', resultsInput());
    expect(outcome.value).not.toBeNull();
    expect(outcome.value!.a).toContain('甲把工具推向乙');
    // The non-member observation is kept as evidence, not committed as a judge.
    const detail = outcome.evidence.detail as { droppedNonMemberJudgments: { memberId: string; reason: string }[] };
    expect(detail.droppedNonMemberJudgments).toEqual([{ memberId: 'c', label: 'partial', reason: 'not_a_group_member' }]);
    // One model call: a harmless bystander observation needs no repair round.
    expect(engine.prompts).toHaveLength(1);
  });

  it('still rejects an effect for a non-member and repairs it', async () => {
    const invalid = JSON.stringify({
      judgments: [
        { memberId: 'a', label: 'partial', reason: '甲推到了。', effects: [{ targetId: 'b', reacted: true }] },
        { memberId: 'b', label: 'no_change', reason: '乙没有反应。', effects: [] },
        { memberId: 'c', label: 'partial', reason: '丁被推了。', effects: [{ targetId: 'a', reacted: true }] },
      ],
      facts: [memberFact('甲把工具推向乙。')],
    });
    const valid = JSON.stringify({
      judgments: [
        { memberId: 'a', label: 'partial', reason: '甲推到了。', effects: [{ targetId: 'b', reacted: true }] },
        { memberId: 'b', label: 'no_change', reason: '乙没有反应。', effects: [] },
      ],
      facts: [memberFact('甲把工具推向乙。')],
    });
    const engine = new ScriptedEngine([invalid, valid]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.results('g1', resultsInput());
    expect(outcome.value).not.toBeNull();
    expect(engine.prompts[1]).toContain('未冻结人物不能写 effect');
  });

  it('rejects a fact attributed to a non-member and repairs it', async () => {
    const invalid = JSON.stringify({
      judgments: [
        { memberId: 'a', label: 'partial', reason: '甲推到了。', effects: [{ targetId: 'b', reacted: true }] },
        { memberId: 'b', label: 'no_change', reason: '乙没有反应。', effects: [] },
      ],
      facts: [memberFact('甲把工具推向乙。'), { text: '丁在旁边问了一句。', memberIds: ['c'] }],
    });
    const valid = JSON.stringify({
      judgments: [
        { memberId: 'a', label: 'partial', reason: '甲推到了。', effects: [{ targetId: 'b', reacted: true }] },
        { memberId: 'b', label: 'no_change', reason: '乙没有反应。', effects: [] },
      ],
      facts: [memberFact('甲把工具推向乙。')],
    });
    const engine = new ScriptedEngine([invalid, valid]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.results('g1', resultsInput());
    expect(outcome.value).not.toBeNull();
    expect(engine.prompts[1]).toContain('facts 的 memberIds 只能填本组成员');
  });
});

describe('bounded task-id contract', () => {
  it('rejects an invented or wrong-owner task id per entry and keeps the valid decisions', async () => {
    const engine = new ScriptedEngine([JSON.stringify({ decisions: [
      { characterId: 'a', achieved: ['a1', 'task_ghost'] },
      { characterId: 'b', achieved: ['a1'] },
      { characterId: 'off', achieved: [] },
    ] })]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('g1#tasks', updatesInput(world(), 'tasks'));
    expect(outcome.value).not.toBeNull();
    const call = outcome.value as UpdatesCall;
    expect(call.changes.a?.tasksAchieved).toEqual(['a1']);
    expect(call.changes.b).toBeUndefined();
    const detail = outcome.evidence.detail as { taskScope: { rejectedTaskIds: { characterId: string; taskId: string; reason: string }[] } };
    expect(detail.taskScope.rejectedTaskIds).toEqual([
      { characterId: 'a', taskId: 'task_ghost', reason: 'unknown_task_id' },
      { characterId: 'b', taskId: 'a1', reason: 'task_belongs_to_a' },
    ]);
    // A bounded reject does not spend a repair call.
    expect(engine.prompts).toHaveLength(1);
  });

  it('still refuses a task answer that omits a whole character', async () => {
    const engine = new ScriptedEngine([
      JSON.stringify({ decisions: [{ characterId: 'a', achieved: [] }, { characterId: 'b', achieved: [] }] }),
      JSON.stringify({ decisions: [{ characterId: 'a', achieved: [] }, { characterId: 'b', achieved: [] }] }),
    ]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('g1#tasks', updatesInput(world(), 'tasks'));
    expect(outcome.value).toBeNull();
    expect(outcome.error).toContain('task character coverage incomplete: 2/3; missing off');
  });
});

describe('compact task keys', () => {
  it('prints t1..tN and expands a short key back to the real task id', async () => {
    const engine = new ScriptedEngine([JSON.stringify({ decisions: [
      { characterId: 'a', achieved: ['t1'] },
      { characterId: 'b', achieved: [] },
      { characterId: 'off', achieved: [] },
    ] })]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('g1#tasks', updatesInput(world(), 'tasks'));
    expect(engine.prompts[0]).toContain('t1：拿到工具');
    expect(engine.prompts[0]).not.toContain('a1：拿到工具');
    const call = outcome.value as UpdatesCall;
    expect(call.changes.a?.tasksAchieved).toEqual(['a1']);
    expect((outcome.evidence.detail as { taskScope: { rejectedTaskIds: unknown[] } }).taskScope.rejectedTaskIds).toEqual([]);
  });
});

describe('compact subtask parent keys', () => {
  it('expands a short parent key and rejects an unknown key', async () => {
    const engine = new ScriptedEngine([JSON.stringify({ subtasks: [
      { parentTaskId: 't1', goal: '查看工具上的刻痕' },
    ] })]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.updates('g1#subtasks', updatesInput(world(), 'subtasks'));
    expect(outcome.value).not.toBeNull();
    const call = outcome.value as UpdatesCall;
    expect(call.changes.a?.subtasksAdded?.[0]?.parentTaskId).toBe('a1');
    expect(engine.prompts[0]).toContain('t1：拿到工具');
  });
});

