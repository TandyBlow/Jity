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
import { projectStage, taskKeyIndex } from '../semantics/settlement/support';
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
        const output = outputs[index++];
        if (output == null) throw new Error('21c3 replay: no output left');
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

  it('stops the repeated 21c3 nono candidate after the first accepted auto round', async () => {
    const { state } = loadWorld();
    const text = '让红方的旗台行动有可执行的掩护，而不把路明非当诱';
    const proposal = JSON.stringify({ candidates: [{ characterId: 'nono', text }] });
    const judgment = JSON.stringify({ judgments: [{ candidateId: 'c1', likely: true, related: true, reason: text }] });
    const engine = scriptedEngine([proposal, judgment, proposal, judgment]);
    const handlers = createSettlementHandlers({ engine });
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
    expect((first.value as { kind: string }).kind).toBe('continue');
    const second = await handlers.continuation('round_auto_1', input('round_auto_1', 'p2'));
    expect(second.value).toBeNull();
    expect(second.error).toBe('continuation_policy_repeated_candidate');
  });

  it('includes the visible nono held item in the affected appearance scope', () => {
    const { state } = loadWorld();
    const projection = projectPoint(state, state, { lu: readSignFact }, {}, 'group');
    expect(projection.sceneCharacters).toContain('nono');
    expect(projection.sceneItems).toContain('red_band_nono');
    expect(projection.affectedAppearance).toContain('red_band_nono');
    expect(projection.unaffectedAppearance.map((row) => row.id)).not.toContain('red_band_nono');
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

  it('stops the b7cd identical nono candidate after the first accepted auto round', async () => {
    const { state } = loadWorld();
    const text = '让红方的旗台行动有可执行的掩护，而不把路明非当诱';
    const proposal = JSON.stringify({ candidates: [{ characterId: 'nono', text }] });
    const judgment = JSON.stringify({ judgments: [{ candidateId: 'c1', likely: true, related: true, reason: text }] });
    const handlers = createSettlementHandlers({ engine: scriptedEngine([proposal, judgment, proposal, judgment]) });
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
    expect((first.value as { kind: string }).kind).toBe('continue');
    const second = await handlers.continuation('round_auto_1', input('round_auto_1', 'p2'));
    expect(second.value).toBeNull();
    expect(second.error).toBe('continuation_policy_repeated_candidate');
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
