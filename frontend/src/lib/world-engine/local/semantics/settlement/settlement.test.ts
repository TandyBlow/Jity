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

  it('returns a conservative no-change result instead of success after repeated invalid output', async () => {
    const engine = new ScriptedEngine(['not json', 'still not json']);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.results('g1', resultsInput());
    expect(outcome.value).not.toBeNull();
    expect(outcome.fallback).toBe(true);
    expect(outcome.error).toContain('model_output_invalid');
    expect(outcome.value!.a).toBe('本组结算未能确认新的结果。');
    expect(outcome.value!.b).toBe('本组结算未能确认新的结果。');
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
      JSON.stringify({ decisions: [
        { characterId: 'a', taskId: 'a1', label: 'achieved' },
        { characterId: 'a', taskId: 'a2', label: 'achieved' },
        { characterId: 'b', taskId: 'b1', label: 'pending' },
        { characterId: 'off', taskId: 'off1', label: 'achieved' },
      ] }),
      JSON.stringify({ subtasks: [{ parentTaskId: 'a1', goal: '把工具从盒子里取回' }] }),
      JSON.stringify({ operations: [
        { entityId: 'a', op: 'add', recordIds: [], text: '更愿意相信同伴' },
        { entityId: 'b', op: 'keep', recordIds: [], text: null },
        { entityId: 'c', op: 'keep', recordIds: [], text: null },
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
  });

  it('does not re-achieve an already achieved task', async () => {
    const engine = new ScriptedEngine([
      JSON.stringify({ changes: [] }),
      JSON.stringify({ operations: [] }),
      JSON.stringify({ decisions: [
        { characterId: 'a', taskId: 'a1', label: 'pending' },
        { characterId: 'a', taskId: 'a2', label: 'achieved' },
        { characterId: 'b', taskId: 'b1', label: 'pending' },
        { characterId: 'off', taskId: 'off1', label: 'pending' },
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
        { characterId: 'a', taskId: 'a1', label: 'achieved' },
        { characterId: 'a', taskId: 'a2', label: 'achieved' },
        { characterId: 'b', taskId: 'b1', label: 'pending' },
        { characterId: 'off', taskId: 'off1', label: 'pending' },
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

  it('keeps the current sanity visible when the sanity answer is invalid (no invented personality)', async () => {
    const engine = new ScriptedEngine([
      JSON.stringify({ changes: [] }),
      JSON.stringify({ operations: [] }),
      JSON.stringify({ decisions: [
        { characterId: 'a', taskId: 'a1', label: 'achieved' },
        { characterId: 'a', taskId: 'a2', label: 'achieved' },
        { characterId: 'b', taskId: 'b1', label: 'pending' },
        { characterId: 'off', taskId: 'off1', label: 'pending' },
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
    const calls = outcome.value as UpdatesCall[];
    expect(calls[4].changes.a.personalityChanges?.[0].text).toBe('更愿意相信同伴');
    expect(calls[5].changes.a.sanitySet).toBe(60);
    expect(outcome.fallback).toBe(true);
    expect(outcome.error).toContain('missing sanity');
  });

  it('returns one UpdatesCall for a split stage and uses the batch task achievement for personality', async () => {
    const engine = new ScriptedEngine([
      JSON.stringify({ decisions: [
        { characterId: 'a', taskId: 'a1', label: 'achieved' },
        { characterId: 'a', taskId: 'a2', label: 'achieved' },
        { characterId: 'b', taskId: 'b1', label: 'pending' },
        { characterId: 'off', taskId: 'off1', label: 'pending' },
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
