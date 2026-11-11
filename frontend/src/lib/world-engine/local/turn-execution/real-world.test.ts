/** The product world, not a toy fixture: 14 characters, 26 locations, 74 items
 * and 73 tasks. The scripted answers are mechanical (one off-screen task is
 * marked achieved; every other task stays pending), but the world, the
 * projection, the controller and the transport are the real ones. The transport
 * itself refuses a group whose task/personality coverage is not the full cast,
 * so a green run here proves the six-stage scope on the real data.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ControllerDriver, initialMemory } from '../../controller';
import type { InferenceEngine } from '../../runtime/engine';
import type { ModelTask } from '../../schedule';
import type { InitialState, InitialTemplate, Json, WorldState } from '../../types';
import { buildInitialState } from '../state';
import { LocalWorldTransport } from '../transport';
import { createSettlementModelPort } from './index';
import { createSettlementHandlers } from '../semantics/settlement/index';
import { projectStage, roundProgressFromState, taskKeyIndex } from '../semantics/settlement/support';
import { projectPoint } from '../semantics/settlement/projection';

function loadWorld(): { initial: InitialTemplate; state: WorldState } {
  const file = join(process.cwd(), 'public/worlds/dragon-raja-free-day.world.json');
  const world = JSON.parse(readFileSync(file, 'utf8'));
  const source = structuredClone(world.initial) as InitialTemplate & { worldId?: string };
  delete source.worldId;
  const initial = source as InitialTemplate;
  return { initial, state: buildInitialState(source as unknown as InitialState) };
}

/** The task owner the protagonist cannot see (different room). */
const OFFSCREEN = 'chu';
const OFFSCREEN_TASK = 'task_chu_hatch';

function engineFor(state: WorldState, seen: string[]): InferenceEngine {
  return {
    info: { backend: 'scripted', modelId: 'real-world-full-cast' },
    async load() {},
    async dispose() {},
    async complete(prompt: string): Promise<string> {
      seen.push(prompt);
      if (prompt.includes('共同结算器')) {
        return JSON.stringify({
          judgments: [{ memberId: 'lu', label: 'partial', reason: '路明非问清了地下门闩的情况。', effects: [] }],
          facts: [{ text: '路明非问起地下检修门的门闩，楚子航说会去确认。', memberIds: ['lu'] }],
        });
      }
      if (prompt.includes('位置结算器')) return JSON.stringify({ changes: [] });
      if (prompt.includes('外貌结算器')) return JSON.stringify({ operations: [] });
      if (prompt.includes('任务条件核验器')) {
        return JSON.stringify({ judgments: [{
          characterId: OFFSCREEN, taskId: OFFSCREEN_TASK, satisfied: 'yes', reason: '地下门闩的事实已经满足任务条件。',
        }] });
      }
      if (prompt.includes('任务判定器')) {
        // One decision per character; achieved lists only newly achieved tasks.
        const owners = Object.entries(state.characters)
          .filter(([, character]) => Object.keys(character.tasks).length > 0)
          .map(([ownerId]) => ownerId);
        return JSON.stringify({
          unchanged: owners.filter((ownerId) => ownerId !== OFFSCREEN),
          achieved: [{ characterId: OFFSCREEN, tasks: [{ taskId: OFFSCREEN_TASK, basis: 'f1' }] }],
        });
      }
      if (prompt.includes('新增小任务判断器')) return JSON.stringify({ subtasks: [] });
      if (prompt.includes('个性变化判断器')) {
        const operations = Object.keys(state.characters).map((id) => (
          id === OFFSCREEN
            ? { entityId: id, op: 'add', recordIds: [], text: '把地下门当成必须亲自确认的责任。' }
            : { entityId: id, op: 'keep', recordIds: [], text: null }
        ));
        return JSON.stringify({ operations });
      }
      if (prompt.includes('理智重算器')) return JSON.stringify({ sanity: [{ characterId: OFFSCREEN, value: 70 }] });
      if (prompt.includes('自动推进判断器')) return JSON.stringify({ candidates: [] });
      throw new Error(`unexpected prompt ${prompt.slice(0, 40)}`);
    },
  };
}

describe('21c3 trace replay (CPU)', () => {
  const readSignFact = '路明非成功看清墙上的演习规则牌并准备行动，符合行动要求。';

  function scriptedEngine(outputs: string[]): InferenceEngine {
    let index = 0;
    return {
      info: { backend: 'scripted', modelId: '21c3-replay' },
      async load() {},
      async dispose() {},
      async complete() {
        // A results point now allows three attempts, so an abort replay repeats
        // its last answer instead of failing on a helper exhaustion error.
        const output = outputs[Math.min(index++, outputs.length - 1)];
        if (output == null) throw new Error('21c3 replay: no output');
        return output;
      },
    };
  }

  it('keeps the valid lu lane move and rejects the invented slot_waist entry', async () => {
    const { state } = loadWorld();
    const raw = JSON.stringify({ changes: [
      { entityId: 'nono', containerId: 'lane', slotId: 'slot_waist', relativeTo: null },
      { entityId: 'lu', containerId: 'lane', slotId: null, relativeTo: null },
    ] });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw]) });
    const outcome = await handlers.updates('g1#position', {
      groupId: 'g1', mode: 'group', stage: 'position',
      results: { lu: readSignFact }, workingState: state,
    } as unknown as Json);
    expect(outcome.value).not.toBeNull();
    const changes = (outcome.value as { changes: Record<string, { positionSet: { containerId: string; slotId: string | null } }> }).changes;
    expect(Object.keys(changes)).toEqual(['lu']);
    expect(changes.lu.positionSet.containerId).toBe('lane');
    expect(changes.lu.positionSet.slotId).toBeNull();
    const detail = outcome.evidence.detail as {
      stageDetail: { droppedNoopEntityIds?: string[]; rejectedPositionEntries?: { entityId: string; reason: string }[] };
    };
    expect(detail.stageDetail.rejectedPositionEntries).toHaveLength(1);
    expect(detail.stageDetail.rejectedPositionEntries?.[0]?.entityId).toBe('nono');
    expect(detail.stageDetail.rejectedPositionEntries?.[0]?.reason).toContain('slot_waist');
  });

  it('drops the auto2 position answer that repeats the post-auto1 state', async () => {
    const { state } = loadWorld();
    const afterAuto1 = projectStage(state, 'position', {
      lu: { positionSet: { containerId: 'lane', slotId: null, relativeTo: null } },
    });
    const raw = JSON.stringify({ changes: [
      { entityId: 'nono', containerId: 'lane', slotId: 'slot_waist', relativeTo: null },
      { entityId: 'lu', containerId: 'lane', slotId: null, relativeTo: null },
    ] });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw]) });
    const outcome = await handlers.updates('g1#position', {
      groupId: 'g1', mode: 'group', stage: 'position',
      results: { lu: readSignFact }, workingState: afterAuto1,
    } as unknown as Json);
    expect(outcome.value).not.toBeNull();
    expect((outcome.value as { changes: Record<string, unknown> }).changes).toEqual({});
    const detail = outcome.evidence.detail as { stageDetail: { droppedNoopEntityIds?: string[]; rejectedPositionEntries?: unknown[] } };
    expect(detail.stageDetail.droppedNoopEntityIds).toEqual(['lu']);
    expect(detail.stageDetail.rejectedPositionEntries).toHaveLength(1);
  });

  it('rejects the 21c3 nono task-goal restatement before judging or settling it', async () => {
    const { state } = loadWorld();
    const text = '让红方的旗台行动有可执行的掩护，而不把路明非当诱';
    const proposal = JSON.stringify({ candidates: [{ characterId: 'nono', text }] });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([proposal]) });
    const roundChanges = (pointId: string): Json[] => [{
      pointId,
      timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
      entityDeltas: { lu: { positionSet: { containerId: 'lane', slotId: null, relativeTo: null } } },
    }];
    const input = (roundId: string, pointId: string) => ({
      round: { roundId, trigger: 'automatic', conclusion: null },
      head: { pointId },
      workingState: state,
      roundChanges: roundChanges(pointId),
    }) as unknown as Json;
    const first = await handlers.continuation('round_3', input('round_3', 'p1'));
    expect(first.value).toBeNull();
    expect(first.error).toBe('continuation_policy_abstract_task_goal');
    const detail = first.evidence.detail as {
      decision: string;
      policy: { reason: string };
      rejectedCandidates: { reason: string; text: string }[];
    };
    expect(detail.decision).toBe('policy_stop');
    expect(detail.policy.reason).toBe('abstract_task_goal');
    expect(detail.rejectedCandidates[0]?.reason).toBe('abstract_task_goal');
  });

  it('counts a reading action/fact and a real state/time change, not a repeated position echo', async () => {
    const { state } = loadWorld();
    // loadWorld() strips worldId to feed InitialTemplate; the built state still
    // needs a world id for a canonical digest.
    state.worldId = 'dragon-raja-free-day';
    state.initial = { ...state.initial, worldId: 'dragon-raja-free-day' };
    const same = structuredClone(state);
    const reading = await roundProgressFromState({
      before: state,
      after: same,
      facts: ['路明非看清了演习规则板上的三条路线。'],
      actions: ['路明非阅读演习规则板。'],
      knownFacts: new Set<string>(),
      knownActions: new Set<string>(),
    });
    expect(reading.evidence.progress).toBe(true);
    expect(reading.evidence.reason).toBe('new_action');
    expect(reading.newFacts).toHaveLength(1);
    expect(reading.newActions).toHaveLength(1);

    const repeated = await roundProgressFromState({
      before: state,
      after: same,
      facts: ['路明非看清了演习规则板上的三条路线。'],
      actions: ['路明非阅读演习规则板。'],
      knownFacts: new Set(reading.newFacts),
      knownActions: new Set(reading.newActions),
    });
    expect(repeated.evidence.progress).toBe(false);
    expect(repeated.evidence.reason).toBe('no_change');

    // The action lane re-sent the same position assignment with no action,
    // fact, time or state change: this must not refresh the progress streak.
    const echoed = await roundProgressFromState({
      before: state,
      after: same,
      facts: [],
      actions: ['lu:路明非在西侧服务巷。'],
      knownFacts: new Set<string>(),
      knownActions: new Set(['lu:路明非在西侧服务巷']),
    });
    expect(echoed.evidence.progress).toBe(false);

    const otherActorSameWords = await roundProgressFromState({
      before: state,
      after: same,
      facts: [],
      actions: ['nono:路明非在西侧服务巷。'],
      knownFacts: new Set<string>(),
      knownActions: new Set(['lu:路明非在西侧服务巷']),
    });
    expect(otherActorSameWords.evidence.progress).toBe(true);
    expect(otherActorSameWords.evidence.reason).toBe('new_action');

    const later = structuredClone(state);
    later.time = { ...later.time, dateTime: '2026-11-09T12:01:00' };
    const time = await roundProgressFromState({
      before: state, after: later, facts: [], actions: [],
      knownFacts: new Set<string>(), knownActions: new Set<string>(),
    });
    expect(time.evidence.timeAdvanced).toBe(true);
    expect(time.evidence.progress).toBe(true);

    // The controller applies the clock before the first results; the captured
    // before/after can then be identical. The settled timeAdvance still counts.
    const settledTime = await roundProgressFromState({
      before: state, after: same, facts: [], actions: [],
      knownFacts: new Set<string>(), knownActions: new Set<string>(),
      timeAdvanced: true,
    });
    expect(settledTime.evidence.timeAdvanced).toBe(true);
    expect(settledTime.evidence.progress).toBe(true);

    const offscreen = structuredClone(state);
    const fingelTask = Object.keys(offscreen.characters.fingel.tasks)[0];
    offscreen.characters.fingel.tasks[fingelTask].status = 'achieved';
    const dependency = await roundProgressFromState({
      before: state, after: offscreen, facts: [], actions: [],
      knownFacts: new Set<string>(), knownActions: new Set<string>(),
    });
    expect(dependency.evidence.stateChanged).toBe(true);
    expect(dependency.evidence.progress).toBe(true);
  });

  it('includes the visible nono held item in the affected appearance scope', () => {
    const { state } = loadWorld();
    const projection = projectPoint(state, state, { lu: readSignFact }, {}, 'group');
    expect(projection.sceneCharacters).toContain('nono');
    expect(projection.sceneItems).toContain('red_band_nono');
    expect(projection.affectedAppearance).toContain('red_band_nono');
    expect(projection.unaffectedAppearance.map((row) => row.id)).not.toContain('red_band_nono');
  });

  it('drops the d101 completion fact after the last repair instead of killing the turn', async () => {
    const { state } = loadWorld();
    const answer = (period: string): string => JSON.stringify({
      judgments: [
        { memberId: 'lu', label: 'achieved', reason: '路明非成功完成自己的参赛选择并完成任务，符合规则要求' + period, effects: [] },
        { memberId: 'nono', label: 'partial', reason: '诺诺询问了路明非的参赛意愿。', effects: [] },
      ],
      facts: [{ text: '路明非成功完成自己的参赛选择并完成任务，符合规则要求' + period, memberIds: ['lu'] }],
    });
    const engine = scriptedEngine([answer('。'), answer('.')]);
    const handlers = createSettlementHandlers({ engine });
    const outcome = await handlers.results('g1', {
      groupId: 'g1',
      members: [{ memberId: 'lu', actionText: '路明非看规则牌。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    // Two repairs ask for the real result; the third answer is accepted with the
    // empty fact dropped and recorded, so the point still settles.
    expect(outcome.evidence.calls).toHaveLength(3);
    expect(outcome.value).not.toBeNull();
    const detail = outcome.evidence.detail as { facts: unknown[]; droppedFacts: { reason: string }[] };
    expect(detail.facts).toHaveLength(0);
    expect(detail.droppedFacts[0].reason).toBe('no_result_text');
  });

  it('rejects the aa30 question-group answers for their content, not for a missing judgement row', async () => {
    // 09-product-03turn-aa30.json turn 2, group_29 (lu asks nono the situation).
    // The two real answers each judged one member: the first left nono without a
    // result sentence, the second left only a mechanics clause and its causal
    // tail. Both are content failures the repair can fix; neither is the old
    // "missing judgment for lu" abort.
    const { state } = loadWorld();
    const first = JSON.stringify({
      judgments: [{ memberId: 'lu', label: 'partial', reason: '路明非的行动成功获得诺诺的确认，且诺诺的判定为准入=true，因此行动被接纳并部分成功完成。', effects: [{ targetId: 'nono', reacted: true }] }],
      facts: [{ text: '路明非向诺诺询问路线图，确认了路明非的行动。', memberIds: ['lu'] }],
    });
    const second = JSON.stringify({
      judgments: [{ memberId: 'nono', label: 'not_achieved', reason: '路明非的骰点未触发，因此未被接纳。', effects: [{ targetId: 'lu', reacted: false }] }],
      facts: [{ text: '路明非的骰点未被触发，因此未被接纳。', memberIds: ['lu'] }],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([first, second]) });
    const outcome = await handlers.results('group_29', {
      groupId: 'group_29',
      members: [
        { memberId: 'lu', actionText: '我向诺诺问：现在红蓝两方各在哪，我能不能先保持中立？', rollRefs: [{ targetId: 'nono', rollId: 'r1', result: 12, eligible: true, admitted: true }] },
        { memberId: 'nono', actionText: '诺诺回答。', rollRefs: [{ targetId: 'lu', rollId: 'r2', result: 9, eligible: true, admitted: false }] },
      ],
      workingState: state,
    } as unknown as Json);
    // Attempt 1 asks for nono's fact; attempt 2's lu fact is a mechanics tail and
    // is rejected; attempt 3 (the same text) is accepted with it dropped, so the
    // point settles instead of killing the turn.
    expect(outcome.evidence.calls[0]?.error).toContain('no fact attributed to nono');
    expect(outcome.evidence.calls[1]?.error).toContain('no action result left');
    expect(outcome.error ?? null).toBeNull();
    expect(outcome.value).not.toBeNull();
    const detail = outcome.evidence.detail as { droppedFacts: { reason: string }[] };
    expect(detail.droppedFacts[0].reason).toBe('no_result_text');
  });

  it('settles the 73f3 reaction group with no invented fact when the model only writes a mechanics line', async () => {
    // 09-product-03turn-73f3.json turn 1, group_12: nono's reaction was denied
    // (reacted=false) and the model answered 路明非未被判定为反应 for her. The
    // old path aborted the point after two repairs and killed the turn.
    const { state } = loadWorld();
    const raw = JSON.stringify({
      judgments: [{ memberId: 'nono', label: 'not_achieved', reason: '路明非未被判定为反应', effects: [{ targetId: 'lu', reacted: false }] }],
      facts: [{ text: '路明非未被判定为反应。', memberIds: ['nono'] }],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw, raw]) });
    const outcome = await handlers.results('group_12', {
      groupId: 'group_12',
      members: [{
        memberId: 'nono',
        actionText: '诺诺蹲下，掀开路明非的袖口看伤口。',
        rollRefs: [{ targetId: 'lu', rollId: 'r1', result: 4, eligible: true, admitted: false }],
      }],
      workingState: state,
    } as unknown as Json);
    expect(outcome.value).not.toBeNull();
    expect(outcome.value!.nono).toBe('');
    expect(outcome.evidence.calls).toHaveLength(1);
    const detail = outcome.evidence.detail as { droppedFacts: { reason: string; original: string }[] };
    expect(detail.droppedFacts[0]).toMatchObject({ reason: 'inactive_no_result' });
    expect(detail.droppedFacts[0].original).toContain('路明非未被判定为反应');
  });

  it('re-derives a blocked outcome that the sentence does not support', async () => {
    // 9eae turn 2: 诺诺摇头说不知道 was committed as outcome blocked.
    const { state } = loadWorld();
    const raw = JSON.stringify({
      judgments: [{ memberId: 'lu', label: 'not_achieved', reason: '诺诺没有被迫反应。', effects: [{ targetId: 'nono', reacted: false }] }],
      facts: [{ text: '路明非问诺诺红蓝两方的方位，诺诺说她也不清楚。', memberIds: ['lu'], actorId: 'lu', outcome: 'blocked' }],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw, raw]) });
    const outcome = await handlers.results('group_29', {
      groupId: 'group_29',
      members: [{
        memberId: 'lu',
        actionText: '我向诺诺问现在的局势。',
        rollRefs: [{ targetId: 'nono', rollId: 'r1', result: 12, eligible: true, admitted: false }],
      }],
      workingState: state,
    } as unknown as Json);
    // The turn no longer dies on a direction word: the fact stays, the outcome
    // follows the model's own not_achieved judgement.
    expect(outcome.value).not.toBeNull();
    const detail = outcome.evidence.detail as { facts: { outcome: string; outcomeSource: string }[]; outcomeAdjusted: { why: string; written: string; derived: string }[] };
    expect(detail.facts[0]).toMatchObject({ outcome: 'failed', outcomeSource: 'derived' });
    expect(detail.outcomeAdjusted[0]).toMatchObject({ why: 'blocked_without_cue', written: 'blocked', derived: 'failed' });
    // A real obstruction keeps the written blocked outcome.
    const blocked = JSON.stringify({
      judgments: [{ memberId: 'lu', label: 'not_achieved', reason: '门被顶住。', effects: [] }],
      facts: [{ text: '路明非被门板挡住，没有挤进器材棚。', memberIds: ['lu'], actorId: 'lu', outcome: 'blocked' }],
    });
    const ok = await createSettlementHandlers({ engine: scriptedEngine([blocked]) }).results('group_29', {
      groupId: 'group_29',
      members: [{ memberId: 'lu', actionText: '我挤进器材棚。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    expect(ok.value).not.toBeNull();
    expect((ok.evidence.detail as { facts: { outcome: string; outcomeSource: string }[] }).facts[0]).toMatchObject({ outcome: 'blocked', outcomeSource: 'model' });
  });

  it('rejects a fact that gives one character’s item to another', async () => {
    // d531 turn 2 wrote 路明非的红色识别带… although the band is 诺诺's.
    const { state } = loadWorld();
    const raw = JSON.stringify({
      judgments: [
        { memberId: 'nono', label: 'partial', reason: '诺诺低声说话。', effects: [{ targetId: 'lu', reacted: true }] },
        { memberId: 'lu', label: 'achieved', reason: '路明非听着。', effects: [] },
      ],
      facts: [
        { text: '路明非的红色识别带在胸前微微发烫，她低声说出一条路线。', memberIds: ['nono'], actorId: 'nono', outcome: 'completed' },
        { text: '路明非听着诺诺说的路线。', memberIds: ['lu'], actorId: 'lu', outcome: 'completed' },
      ],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw, raw]) });
    const outcome = await handlers.results('group_29', {
      groupId: 'group_29',
      members: [
        { memberId: 'nono', actionText: '诺诺低声说出路线。', rollRefs: [{ targetId: 'lu', rollId: 'r1', result: 9, eligible: true, admitted: true }] },
        { memberId: 'lu', actionText: '我听诺诺说。', rollRefs: [] },
      ],
      workingState: state,
    } as unknown as Json);
    // The frozen owner is written instead of spending the turn on a retry: the
    // observation (a warm band, a whispered route) is what the stages need.
    expect(outcome.error ?? null).toBeNull();
    expect(outcome.value).not.toBeNull();
    const detail = outcome.evidence.detail as {
      facts: { text: string }[];
      ownershipAdjusted: { from: string; to: string; item: string }[];
    };
    expect(detail.facts[0].text).toContain('诺诺的红色识别带');
    expect(detail.facts[0].text).not.toContain('路明非的红色识别带');
    expect(detail.ownershipAdjusted[0]).toMatchObject({ from: '路明非', to: '诺诺', item: '红色识别带' });
  });

  it('rejects a protagonist fact that copied the player’s “我” sentence', async () => {
    // 35ad turn 3: the player wrote 我请诺诺带我走一条有掩护、能到钟楼西侧的路线。and
    // the results answer repeated it verbatim with outcome completed.
    const { state } = loadWorld();
    const raw = JSON.stringify({
      judgments: [{ memberId: 'lu', label: 'achieved', reason: '路明非请求诺诺。', effects: [{ targetId: 'nono', reacted: true }] }],
      facts: [
        { text: '路明非请诺诺带我走一条有掩护、能到钟楼西侧的路线', memberIds: ['lu'], actorId: 'lu', outcome: 'completed' },
        { text: '诺诺听着，没有立刻回答。', memberIds: ['nono'], actorId: 'nono', outcome: 'unaffected' },
      ],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw, raw]) });
    const outcome = await handlers.results('group_49', {
      groupId: 'group_49',
      members: [
        {
          memberId: 'lu',
          actionText: '我请诺诺带我走一条有掩护、能到钟楼西侧的路线。',
          rollRefs: [{ targetId: 'nono', rollId: 'r1', result: 11, eligible: true, admitted: true }],
        },
        { memberId: 'nono', actionText: '诺诺考虑路线。', rollRefs: [] },
      ],
      workingState: state,
    } as unknown as Json);
    // The subject is frozen (the protagonist), so the pronoun is rewritten to
    // the name instead of rejecting the answer and paying another 25–50 s call.
    expect(outcome.error ?? null).toBeNull();
    expect(outcome.value).not.toBeNull();
    const detail = outcome.evidence.detail as { facts: { text: string }[]; firstPersonAdjusted: { text: string }[] };
    expect(detail.facts[0].text).toBe('路明非请诺诺带路明非走一条有掩护、能到钟楼西侧的路线');
    expect(detail.firstPersonAdjusted[0].text).toBe('路明非请诺诺带路明非走一条有掩护、能到钟楼西侧的路线');
    // Quoted speech keeps the first person: it is the character's own words.
    const quoted = JSON.stringify({
      judgments: [{ memberId: 'lu', label: 'achieved', reason: '路明非开口。', effects: [{ targetId: 'nono', reacted: true }] }],
      facts: [
        { text: '路明非对诺诺说：“我带你走。”诺诺点头。', memberIds: ['lu'], actorId: 'lu', outcome: 'completed' },
        { text: '诺诺点头。', memberIds: ['nono'], actorId: 'nono', outcome: 'completed' },
      ],
    });
    const kept = await createSettlementHandlers({ engine: scriptedEngine([quoted]) }).results('group_49', {
      groupId: 'group_49',
      members: [
        { memberId: 'lu', actionText: '我对诺诺说：我带你走。', rollRefs: [{ targetId: 'nono', rollId: 'r1', result: 11, eligible: true, admitted: true }] },
        { memberId: 'nono', actionText: '诺诺点头。', rollRefs: [] },
      ],
      workingState: state,
    } as unknown as Json);
    expect(kept.error ?? null).toBeNull();
    expect((kept.evidence.detail as { facts: { text: string }[] }).facts[0].text).toContain('“我带你走。”');
  });

  it('drops a fact that wraps another member’s whole sentence', async () => {
    // 1e59 turn 3: lu's fact was 路明非请诺诺带我走…，诺诺的红色识别带…你愿意带我走这条路吗？
    // — a short wrapper around nono's own fact.
    const { state } = loadWorld();
    const nonoLine = '诺诺的红色识别带在路明非的护目镜上闪烁了一下，随即拉住路明非的手，语气中带着一丝警惕';
    const raw = JSON.stringify({
      judgments: [
        { memberId: 'lu', label: 'achieved', reason: '路明非提出请求。', effects: [{ targetId: 'nono', reacted: true }] },
        { memberId: 'nono', label: 'not_achieved', reason: '诺诺拉住他的手。', effects: [{ targetId: 'lu', reacted: true }] },
      ],
      facts: [
        { text: `路明非请诺诺带我走一条有掩护的路线，${nonoLine}`, memberIds: ['lu'], actorId: 'lu', outcome: 'completed' },
        { text: nonoLine, memberIds: ['nono'], actorId: 'nono', outcome: 'failed' },
      ],
    });
    const outcome = await createSettlementHandlers({ engine: scriptedEngine([raw]) }).results('group_49', {
      groupId: 'group_49',
      members: [
        { memberId: 'lu', actionText: '我请诺诺带我走一条有掩护的路线。', rollRefs: [{ targetId: 'nono', rollId: 'r1', result: 11, eligible: true, admitted: true }] },
        { memberId: 'nono', actionText: '诺诺考虑。', rollRefs: [{ targetId: 'lu', rollId: 'r2', result: 7, eligible: true, admitted: true }] },
      ],
      workingState: state,
    } as unknown as Json);
    expect(outcome.error ?? null).toBeNull();
    const detail = outcome.evidence.detail as { facts: { text: string; actorId: string }[]; droppedFacts: { reason: string }[] };
    expect(detail.facts.map((fact) => fact.actorId)).toEqual(['nono']);
    expect(detail.droppedFacts[0].reason).toBe('duplicates_another_member');
  });

  it('keeps the real d101 pending task goal out of the results prompt', async () => {
    const { state } = loadWorld();
    const seen: string[] = [];
    const handlers = createSettlementHandlers({ engine: engineFor(state, seen) });
    const outcome = await handlers.results('group_10', {
      groupId: 'group_10',
      members: [{ memberId: 'lu', actionText: '我沿着服务巷往里走，先看清墙上的演习规则牌。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    expect(outcome.value).not.toBeNull();
    const prompt = seen.find((text) => text.includes('共同结算器')) ?? '';
    expect(prompt).toContain('我沿着服务巷往里走');
    expect(prompt).not.toContain('待办=');
    expect(prompt).not.toContain('作出自己的参赛选择');
  });

  it('strips the d101 dice/check clause into a natural result', async () => {
    const { state } = loadWorld();
    const raw = JSON.stringify({
      judgments: [{ memberId: 'nono', label: 'not_achieved', reason: '诺诺无法反应。', effects: [] }],
      facts: [{ text: '诺诺未成功完成目标，因为路明非的骰点资格为false且无法反应。', memberIds: ['nono'] }],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw, raw]) });
    const outcome = await handlers.results('g1', {
      groupId: 'g1',
      members: [{ memberId: 'nono', actionText: '诺诺观察路明非。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    expect(outcome.value).not.toBeNull();
    expect(outcome.value!.nono).toBe('诺诺未成功');
    expect(outcome.value!.nono).not.toMatch(/骰点|骰子|false|判定|完成目标/u);
    const detail = outcome.evidence.detail as { sanitizedFacts: { removed: string[] }[] };
    expect(detail.sanitizedFacts[0].removed).toEqual(expect.arrayContaining(['骰点']));
  });

  it('drops a fact that is only an invented dice action after the last repair', async () => {
    const { state } = loadWorld();
    const raw = JSON.stringify({
      judgments: [{ memberId: 'lu', label: 'achieved', reason: '路明非和骰子互动。', effects: [] }],
      facts: [{ text: '路明非抓起骰子。', memberIds: ['lu'] }],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw, raw]) });
    const outcome = await handlers.results('g1', {
      groupId: 'g1',
      members: [{ memberId: 'lu', actionText: '路明非看规则牌。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    // 抓起骰子 is mechanics vocabulary; the repair asks for a visible result and
    // the last attempt is accepted with the fact dropped.
    expect(outcome.value).not.toBeNull();
    expect((outcome.evidence.detail as { droppedFacts: { reason: string }[] }).droppedFacts[0].reason).toBe('no_result_text');
  });

  it('sanitizes the b7cd result fact so a pending task cannot read as finished', async () => {
    const { state } = loadWorld();
    const raw = JSON.stringify({
      judgments: [{ memberId: 'nono', label: 'achieved', reason: '诺诺确认了联络状态。', effects: [] }],
      facts: [{ text: '诺诺确认了故障短讯机与凯撒的联络状态是否正常，且未被阻止或阻碍，行动成功完成。', memberIds: ['nono'] }],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw]) });
    const outcome = await handlers.results('g1', {
      groupId: 'g1',
      members: [{ memberId: 'nono', actionText: '诺诺确认故障短讯机状态。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    expect(outcome.value).not.toBeNull();
    expect(outcome.value!.nono).toBe('诺诺确认了故障短讯机与凯撒的联络状态是否正常，且未被阻止或阻碍。');
    expect(outcome.value!.nono).not.toContain('行动成功完成');
    const detail = outcome.evidence.detail as { sanitizedFacts: { removed: string[] }[] };
    expect(detail.sanitizedFacts[0]?.removed).toContain('行动成功完成');
  });

  it('sanitizes the 21c3 fact that said 任务完成 while every task row was pending', async () => {
    const { state } = loadWorld();
    const raw = JSON.stringify({
      judgments: [{ memberId: 'nono', label: 'achieved', reason: '诺诺检查了故障短讯机状态。', effects: [] }],
      facts: [{ text: '诺诺确认任务完成并检查故障短讯机状态，成功执行行动。', memberIds: ['nono'] }],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw]) });
    const outcome = await handlers.results('g1', {
      groupId: 'g1',
      members: [{ memberId: 'nono', actionText: '诺诺检查故障短讯机。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    expect(outcome.value!.nono).toBe('诺诺确认并检查故障短讯机状态。');
    for (const task of Object.values(state.characters.nono.tasks)) expect(task.status).toBe('pending');
  });

  it('sanitizes the exact e9a5 third-paragraph fact with its speaker label', async () => {
    const { state } = loadWorld();
    const raw = JSON.stringify({
      judgments: [{ memberId: 'nono', label: 'achieved', reason: '诺诺检查了故障短讯机状态。', effects: [] }],
      facts: [{ text: '诺诺：确认任务完成并检查故障短讯机状态，成功执行行动。', memberIds: ['nono'] }],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw]) });
    const outcome = await handlers.results('g1', {
      groupId: 'g1',
      members: [{ memberId: 'nono', actionText: '诺诺检查故障短讯机。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    expect(outcome.value!.nono).toBe('诺诺：确认并检查故障短讯机状态。');
    expect(outcome.value!.nono).not.toContain('任务完成');
    expect(outcome.value!.nono).not.toContain('成功执行行动');
    const detail = outcome.evidence.detail as { sanitizedFacts: { removed: string[] }[] };
    expect(detail.sanitizedFacts[0]?.removed).toEqual(expect.arrayContaining(['任务完成', '成功执行行动']));
  });

  it('repairs then drops the 95dc fact that only claims a choice/task completion', async () => {
    const { state } = loadWorld();
    const raw = JSON.stringify({
      judgments: [{ memberId: 'lu', label: 'achieved', reason: '路明非完成了任务。', effects: [] }],
      facts: [{ text: '路明非成功完成自己的参赛选择并完成任务，符合规则要求。', memberIds: ['lu'] }],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw, raw]) });
    const outcome = await handlers.results('g1', {
      groupId: 'g1',
      members: [{ memberId: 'lu', actionText: '我沿着服务巷往里走，先看清墙上的演习规则牌。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    // The old product committed this as the player's result; now the point
    // settles without it and the drop is visible in evidence.
    expect(outcome.value).not.toBeNull();
    const detail = outcome.evidence.detail as { droppedFacts: { reason: string; original: string }[] };
    expect(detail.droppedFacts[0].reason).toBe('no_result_text');
    expect(detail.droppedFacts[0].original).toContain('参赛选择');
  });

  it('strips 95dc dice mechanics into a natural result and still strips task claims', async () => {
    const { state } = loadWorld();
    const raw = JSON.stringify({
      judgments: [{ memberId: 'nono', label: 'not_achieved', reason: '没有允许路明非反应。', effects: [] }],
      facts: [{ text: '诺诺未成功触发路明非的骰点资格为false，且未被允许反应。', memberIds: ['nono'] }],
    });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw, raw]) });
    const outcome = await handlers.results('g1', {
      groupId: 'g1',
      members: [{ memberId: 'nono', actionText: '诺诺观察路明非。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    expect(outcome.value!.nono).toBe('诺诺未被允许反应。');
    expect(outcome.value!.nono).not.toContain('骰点');
    expect(outcome.value!.nono).not.toContain('false');
    const detail = outcome.evidence.detail as { sanitizedFacts: { removed: string[] }[] };
    expect(detail.sanitizedFacts[0]?.removed).toContain('骰点');

    // A fact whose only subject is a character outside the group is the
    // judgement's explanation of that character's action, not this group's
    // result. It is repaired; a repair that repeats it aborts the point.
    const raw2 = JSON.stringify({
      judgments: [{ memberId: 'nono', label: 'not_achieved', reason: '没有允许路明非反应。', effects: [] }],
      facts: [{ text: '路明非未被允许反应，因此未达成目标。', memberIds: ['nono'] }],
    });
    const handlers2 = createSettlementHandlers({ engine: scriptedEngine([raw2, raw2]) });
    const outcome2 = await handlers2.results('g1', {
      groupId: 'g1',
      members: [{ memberId: 'nono', actionText: '诺诺观察路明非。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    expect(outcome2.value).toBeNull();
    expect(outcome2.error).toContain('fact names only 路明非');

    // The repair keeps the target observation but names the group's own member.
    const repaired = JSON.stringify({
      judgments: [{ memberId: 'nono', label: 'not_achieved', reason: '没有允许路明非反应。', effects: [] }],
      facts: [{ text: '诺诺没有让路明非反应。', memberIds: ['nono'] }],
    });
    const handlers3 = createSettlementHandlers({ engine: scriptedEngine([raw2, repaired]) });
    const outcome3 = await handlers3.results('g1', {
      groupId: 'g1',
      members: [{ memberId: 'nono', actionText: '诺诺观察路明非。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    expect(outcome3.value!.nono).toBe('诺诺没有让路明非反应。');
    expect(outcome3.evidence.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('keeps the 736a player walk/read fact and rejects the reaction group explanation', async () => {
    const { state } = loadWorld();
    const walk = JSON.stringify({
      judgments: [
        { memberId: 'lu', label: 'achieved', reason: '路明非沿着服务巷往里走，先看清墙上的演习规则牌。', effects: [] },
        { memberId: 'nono', label: 'not_achieved', reason: '诺诺的位置和装备不符合演习规则，未触发相关效果。', effects: [] },
      ],
      facts: [{ text: '路明非沿着服务巷往里走，先看清墙上的演习规则牌。', memberIds: ['lu'] }],
    });
    const player = await createSettlementHandlers({ engine: scriptedEngine([walk]) }).results('group_10', {
      groupId: 'group_10',
      members: [{ memberId: 'lu', actionText: '我沿着服务巷往里走，先看清墙上的演习规则牌。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json);
    expect(player.value!.lu).toBe('路明非沿着服务巷往里走，先看清墙上的演习规则牌。');

    // 736a group_12 copied the judgement reason: 路明非未被掀开袖口，未看到
    // 规则牌… It names nobody in the group and denies what group_10 settled.
    const explanation = JSON.stringify({
      judgments: [{ memberId: 'nono', label: 'not_achieved', reason: '路明非的袖口未被掀开，且未看到规则牌，骰点未触发准入条件。行动未成功或被阻止。', effects: [{ targetId: 'lu', reacted: false }] }],
      facts: [{ text: '路明非未被掀开袖口，未看到规则牌，骰点未触发准入条件。行动未成功或被阻止。', memberIds: ['nono'] }],
    });
    const rolls = [{ targetId: 'lu', rollId: 'r1', result: 12, eligible: false, admitted: false }];
    // nono's action provably did not happen (not_achieved + denied roll), so the
    // group has no result to narrate: the explanation is dropped, not repaired
    // and not committed. This keeps the point free of a contradiction and costs
    // no extra model call.
    const reaction = await createSettlementHandlers({ engine: scriptedEngine([explanation, explanation]) }).results('group_12', {
      groupId: 'group_12',
      members: [{ memberId: 'nono', actionText: '诺诺确认路明非的袖口。', rollRefs: rolls }],
      workingState: state,
    } as unknown as Json);
    expect(reaction.value).toEqual({ nono: '' });
    expect(reaction.evidence.calls).toHaveLength(1);
    const dropped = reaction.evidence.detail as { droppedFacts: { reason: string; original: string }[] };
    expect(dropped.droppedFacts?.[0]?.reason).toBe('explains_another_character');
    expect(dropped.droppedFacts?.[0]?.original).toContain('未看到规则牌');

    // A member whose action may have happened still needs its own result; the
    // explanation is repaired, not dropped.
    const partial = JSON.stringify({
      judgments: [{ memberId: 'nono', label: 'partial', reason: '诺诺看了一眼路明非的袖口。', effects: [{ targetId: 'lu', reacted: false }] }],
      facts: [{ text: '路明非未被掀开袖口，未看到规则牌。', memberIds: ['nono'] }],
    });
    const repaired = await createSettlementHandlers({ engine: scriptedEngine([partial, partial]) }).results('group_12', {
      groupId: 'group_12',
      members: [{ memberId: 'nono', actionText: '诺诺确认路明非的袖口。', rollRefs: rolls }],
      workingState: state,
    } as unknown as Json);
    expect(repaired.value).toBeNull();
    expect(repaired.error).toContain('fact names only 路明非');
    expect(repaired.error).toContain('诺诺确认路明非的袖口');
  });

  it('drops the b7cd auto1 position answer that only echoed lu lane', async () => {
    const { state } = loadWorld();
    const afterFirst = projectStage(state, 'position', {
      lu: { positionSet: { containerId: 'lane', slotId: null, relativeTo: null } },
    });
    const raw = JSON.stringify({ changes: [{ entityId: 'lu', containerId: 'lane', slotId: null, relativeTo: null }] });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw]) });
    const outcome = await handlers.updates('g1#position', {
      groupId: 'g1', mode: 'group', stage: 'position',
      results: { lu: readSignFact }, workingState: afterFirst,
    } as unknown as Json);
    expect(outcome.value).not.toBeNull();
    expect((outcome.value as { changes: Record<string, unknown> }).changes).toEqual({});
    const detail = outcome.evidence.detail as { stageDetail: { droppedNoopEntityIds?: string[] } };
    expect(detail.stageDetail.droppedNoopEntityIds).toEqual(['lu']);
  });

  it('rejects the b7cd nono task-goal restatement before judging or settling it', async () => {
    const { state } = loadWorld();
    const text = '让红方的旗台行动有可执行的掩护，而不把路明非当诱';
    const proposal = JSON.stringify({ candidates: [{ characterId: 'nono', text }] });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([proposal]) });
    const roundChanges = (pointId: string): Json[] => [{
      pointId,
      timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
      entityDeltas: { lu: { positionSet: { containerId: 'lane', slotId: null, relativeTo: null } } },
    }];
    const input = (roundId: string, pointId: string) => ({
      round: { roundId, trigger: 'automatic', conclusion: null },
      head: { pointId },
      workingState: state,
      roundChanges: roundChanges(pointId),
    }) as unknown as Json;
    const first = await handlers.continuation('round_3', input('round_3', 'p1'));
    expect(first.value).toBeNull();
    expect(first.error).toBe('continuation_policy_abstract_task_goal');
    const detail = first.evidence.detail as {
      decision: string;
      policy: { reason: string };
      rejectedCandidates: { reason: string; text: string }[];
    };
    expect(detail.decision).toBe('policy_stop');
    expect(detail.policy.reason).toBe('abstract_task_goal');
    expect(detail.rejectedCandidates[0]?.reason).toBe('abstract_task_goal');
  });

  it('keeps the 21c3 all-pending task answer as no task change', async () => {
    const { state } = loadWorld();
    const raw = JSON.stringify({ unchanged: ['fingel', 'lu', 'nono'], achieved: [], subtasks: [] });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw]), options: { requireTaskSupport: true } });
    const outcome = await handlers.updates('g1#tasks', {
      groupId: 'g1', mode: 'group', stage: 'tasks',
      results: { lu: readSignFact }, workingState: state,
    } as unknown as Json);
    expect(outcome.value).not.toBeNull();
    expect((outcome.value as { changes: Record<string, unknown> }).changes).toEqual({});
    const scope = (outcome.evidence.detail as { stageDetail: { taskScope: {
      mode: string; taskRows: number; affectedCharacters: number;
      achievedByCharacter: unknown[]; supports: unknown[];
    } } }).stageDetail.taskScope;
    expect(scope.mode).toBe('affected_projection');
    expect(scope.taskRows).toBe(73);
    expect(scope.achievedByCharacter).toEqual([]);
    expect(scope.supports).toEqual([]);
    for (const owner of ['lu', 'nono', 'fingel']) {
      for (const task of Object.values(state.characters[owner].tasks)) {
        expect(task.status).toBe(Object.entries(state.initial.characters[owner].tasks).find(([id]) => id === task.id)?.[1]?.status ?? task.status);
      }
    }
  });

  it('does not let a results fact saying 任务完成 auto-achieve the task', async () => {
    const { state } = loadWorld();
    const before = Object.fromEntries(Object.entries(state.characters.nono.tasks).map(([id, task]) => [id, task.status]));
    // The 21c3 group_12 task answer: caesar/fingel/lu/nono unchanged, empty
    // achieved. The nono fact claims 任务完成, and the task stage must not turn
    // that prose into a task achievement on its own.
    const raw = JSON.stringify({ unchanged: ['caesar', 'fingel', 'lu', 'nono'], achieved: [], subtasks: [] });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([raw]), options: { requireTaskSupport: true } });
    const outcome = await handlers.updates('g1#tasks', {
      groupId: 'g1', mode: 'group', stage: 'tasks',
      results: { nono: '诺诺确认任务完成并检查故障短讯机状态，成功执行行动。' },
      workingState: state,
    } as unknown as Json);
    expect(outcome.value).not.toBeNull();
    expect((outcome.value as { changes: Record<string, unknown> }).changes).toEqual({});
    for (const [taskId, status] of Object.entries(before)) {
      expect(state.characters.nono.tasks[taskId].status).toBe(status);
    }
  });
});

describe('real product world task-truth regression', () => {
  it('aborts the 17:37 all-cast no-support answer for the walk/read-sign action', async () => {
    const { state } = loadWorld();
    const beforeLu = Object.fromEntries(Object.entries(state.characters.lu.tasks).map(([id, task]) => [id, task.status]));
    const allCast = Object.fromEntries(Object.entries(state.characters)
      .map(([ownerId, character]) => [ownerId, Object.values(character.tasks)])
      .filter(([, tasks]) => tasks.length > 0)
      .map(([ownerId, tasks]) => [ownerId, (tasks as { id: string }[]).map((task) => ({ taskId: task.id }))]));
    const answer = JSON.stringify({
      unchanged: [],
      achieved: Object.entries(allCast).map(([characterId, tasks]) => ({ characterId, tasks })),
    });
    const engine: InferenceEngine = {
      info: { backend: 'scripted', modelId: '17-37-all-cast-no-support' },
      async load() {},
      async dispose() {},
      async complete() { return answer; },
    };
    const handlers = createSettlementHandlers({ engine, options: { requireTaskSupport: true } });
    const outcome = await handlers.updates('g1#tasks', {
      groupId: 'g1',
      mode: 'group',
      stage: 'tasks',
      results: { lu: '路明非沿着服务巷往里走，先看清墙上的演习规则牌。' },
      workingState: state,
    } as unknown as Json);
    expect(outcome.value).toBeNull();
    expect(outcome.error).toContain('task_support_incomplete');
    // The abort leaves every task exactly as it was: no new achievement, no
    // pending row flipped to achieved.
    for (const [taskId, status] of Object.entries(beforeLu)) {
      expect(state.characters.lu.tasks[taskId].status).toBe(status);
    }
  });
});

describe('real product world through the real kernel', () => {
  it('decides and commits the full cast, including an off-screen owner', async () => {
    const { initial, state } = loadWorld();
    const order = Object.keys(initial.characters).sort();
    const seen: string[] = [];
    const engine = engineFor(state, seen);
    const settlement = createSettlementModelPort(engine);
    const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
    const memory = initialMemory('test_world', 'holder_world');
    memory.initialTemplate = initial;
    memory.playerInput = { text: '我问楚子航地下检修门的门闩到底会不会再插上。', order };
    memory.allocPlan = {
      allocationKey: 'test_world_command',
      slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
        { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
        ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
      ],
    };
    const model = {
      async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
        if (task === 'results' || task === 'updates' || task === 'continuation') return settlement.generate(task, key, input);
        if (task === 'pointPlan') {
          return [{ pointId: 'point_real_1', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, actorIds: order }];
        }
        if (task === 'action') {
          const data = input as unknown as { actor: string; advance?: { inputText?: string | null; intentStatus?: string }; workingState: WorldState };
          if (data.actor === data.workingState.protagonistId && data.advance?.intentStatus === 'pending') {
            return { kind: 'act', text: data.advance.inputText ?? '路明非问起门闩。' };
          }
          return { kind: 'skip' };
        }
        if (task === 'targets') return { targets: [] };
        if (task === 'reaction') return { kind: 'skip' };
        if (task === 'narration') return '路明非问了一句门闩的事，没有得到回答，先把这句话记在心里。';
        throw new Error(`unexpected task ${task}`);
      },
    };
    const driver = new ControllerDriver({ transport, model }, memory);
    const status = await driver.run();
    expect(status.kind).not.toBe('error');
    const snapshot = transport.snapshot();
    const committed = snapshot.state.characters[OFFSCREEN];
    expect(committed.tasks[OFFSCREEN_TASK].status).toBe('achieved');
    expect(committed.personalityChanges.find((change) => change.active)?.text).toBe('把地下门当成必须亲自确认的责任。');
    expect(committed.sanity).toBe(70);
    // The dependency projection puts the off-screen fact owner in front of the
    // model, but does not re-send unrelated owners just to hear "unchanged".
    const taskPrompt = seen.find((prompt) => prompt.includes('任务判定器')) ?? '';
    expect(taskPrompt).toContain(`id=${OFFSCREEN}`);
    expect(taskPrompt).not.toContain('id=caesar');
    const taskIds = Object.values(state.characters).flatMap((character) => Object.keys(character.tasks));
    expect(taskIds).toHaveLength(73);
    const keys = taskKeyIndex(state);
    expect(keys.size).toBe(73);
    expect(taskPrompt.length).toBeLessThan(6000);
    // Same for appearance: the affected scene/fact entities are listed, not
    // all 114 rows.
    const appearancePrompt = seen.find((prompt) => prompt.includes('外貌结算器')) ?? '';
    expect(appearancePrompt).toContain(`id=${OFFSCREEN}`);
    expect(appearancePrompt).not.toContain('id=caesar');
    expect(appearancePrompt.length).toBeLessThan(8000);
    const personalityPrompt = seen.find((prompt) => prompt.includes('个性变化判断器')) ?? '';
    expect(personalityPrompt).toContain(`id=${OFFSCREEN}`);
    expect(personalityPrompt).not.toContain('id=caesar');
    expect(personalityPrompt.length).toBeLessThan(6000);
  });
});
