import { describe, expect, test } from 'vitest';
import { SHORT_STATE } from './b3-short-samples';
import { RuleAuthority, decodeRuleAction, parseRuleCommand, type RulePolicy, type RuleReceipt } from './rule-facts';
import { createRuleController } from './rule-controller';
import type { InitialTemplate, WorldContext, WorldState } from '../types';

export const TEST_POLICY: RulePolicy = {
  routes: [{ from: 'corridor', to: 'hall', minimumSanity: 5 }],
  sanity: { minimum: 0, maximum: 10, effects: { strain: -2, recover: 1 }, milestones: {
    strain: { taskId: 'task_pressure', goal: '完成压力试验', requiredLocationId: 'corridor', minimumElapsedSeconds: 1, personalityText: '经历压力试验后更谨慎' },
    recover: { taskId: 'task_recover', goal: '完成恢复练习', requiredLocationId: 'corridor', minimumElapsedSeconds: 1, personalityText: '完成恢复练习后更善于自我调节' },
  } },
};
export function testRuleState(): WorldState {
  const state = structuredClone(SHORT_STATE) as unknown as WorldState;
  for (const milestone of Object.values(TEST_POLICY.sanity.milestones)) {
    const task = { id: milestone.taskId, ownerId: 'person_c', parentTaskId: null, goal: milestone.goal, status: 'pending' as const };
    state.initial.characters.person_c.tasks[task.id] = task;
    state.characters.person_c.tasks[task.id] = structuredClone(task);
  }
  state.time = { ...state.time, dateTime: '2026-10-27T09:00:01' };
  return state;
}
export function testRuleWorld(): WorldContext {
  return { worldId: 'world_short', head: { pointId: 'root', version: 0, stateDigest: 'digest_root', narrationStatus: 'ready' },
    advance: { advanceId: 'advance_1', inputId: 'input_1', intentStatus: 'pending', inputAvailable: true },
    round: { roundId: 'round_1', trigger: 'player', order: ['person_a', 'person_c'], cursor: 1, actedIds: [], visitedIds: ['person_a'], conclusion: null },
    time: { calendar: 'gregorian', dateTime: '2026-10-27T09:00:00', instantOrdinal: 0 },
    lease: { fenceEpoch: 1, expiresAtEpochMilli: Number.MAX_SAFE_INTEGER }, successor: null, activePointId: 'point_1', activeRoundId: 'round_1' };
}

describe('explicit execution authority', () => {
  test('natural-language assertions and a model numeric set cannot mint a receipt', () => {
    const state = testRuleState();
    const authority = new RuleAuthority(TEST_POLICY);
    expect(parseRuleCommand('周宁已经在门厅，精神值已经是8。', state)).toBeNull();
    expect(() => decodeRuleAction('周宁已经到门厅。')).toThrow(/free_text/);
    expect(() => authority.adjudicate({ proposal: { kind: 'sanity', actorId: 'person_c', effect: 'strain', to: 8 },
      inputText: '完成压力试验', state, world: testRuleWorld(), pointId: 'point_1' })).toThrow(/unsupported_rule_proposal/);
    expect(() => authority.inspect({ decision: 'allowed' } as unknown as RuleReceipt)).toThrow(/not_issued/);
  });

  test('a move is a checked proposal, then a deterministic position delta', () => {
    const authority = new RuleAuthority(TEST_POLICY);
    const state = testRuleState();
    const world = testRuleWorld();
    const receipt = authority.adjudicate({ proposal: parseRuleCommand('走到门厅', state), inputText: '走到门厅', state, world, pointId: 'point_1' });
    expect(authority.inspect(receipt).decision).toEqual({ outcome: 'allowed', effects: [{ kind: 'moved', actorId: 'person_c', from: 'corridor', to: 'hall' }] });
    const expected = { person_c: { entityId: 'person_c', positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } };
    expect(authority.deltas(receipt, world, 'point_1', state)).toEqual(expected);
    expect(authority.deltas(receipt, world, 'point_1', state)).toEqual(expected); // preview/retry is not another execution
    const otherAuthority = new RuleAuthority(TEST_POLICY);
    expect(() => otherAuthority.inspect(receipt)).toThrow(/not_issued/);
  });

  test('route and threshold failures have no effects; command actor cannot be substituted', () => {
    const authority = new RuleAuthority(TEST_POLICY);
    const state = testRuleState(); state.characters.person_c.sanity = 2;
    const world = testRuleWorld();
    const receipt = authority.adjudicate({ proposal: parseRuleCommand('走到门厅', state), inputText: '走到门厅', state, world, pointId: 'point_1' });
    expect(authority.inspect(receipt).decision).toEqual({ outcome: 'refused', reason: 'sanity_below_route_minimum', effects: [] });
    expect(authority.deltas(receipt, world, 'point_1', state)).toEqual({});
    expect(() => authority.adjudicate({ proposal: { kind: 'move', actorId: 'person_a', destinationId: 'hall' }, inputText: '走到门厅', state, world, pointId: 'point_1' })).toThrow(/not_bound/);
  });

  test('numeric execution requires an actual registered pending task and the execution interval', () => {
    const authority = new RuleAuthority(TEST_POLICY);
    const state = testRuleState();
    const world = testRuleWorld();
    const request = () => ({ proposal: parseRuleCommand('完成压力试验', state), inputText: '完成压力试验', state, world, pointId: 'point_1' });
    const receipt = authority.adjudicate(request());
    expect(authority.deltas(receipt, world, 'point_1', state)).toEqual({ person_c: {
      entityId: 'person_c', sanitySet: 8, tasksAchieved: ['task_pressure'],
      personalityChanges: [{ id: 'rule_strain_input_1', text: '经历压力试验后更谨慎', supersedes: [] }],
    } });
    const task = state.characters.person_c.tasks.task_pressure;
    task.status = 'achieved';
    expect(authority.inspect(authority.adjudicate(request())).decision).toMatchObject({ outcome: 'refused', reason: 'task_already_achieved' });
    expect(() => authority.deltas(receipt, world, 'point_1', state)).toThrow(/task_already_consumed/);
    task.status = 'pending'; task.goal = '其他任务';
    expect(authority.inspect(authority.adjudicate(request())).decision).toMatchObject({ outcome: 'refused', reason: 'registered_task_missing_or_mismatched' });
    task.goal = '完成压力试验'; state.time.dateTime = world.time.dateTime;
    expect(authority.inspect(authority.adjudicate(request())).decision).toMatchObject({ outcome: 'refused', reason: 'milestone_execution_time_incomplete' });
  });

  test('receipts cannot cross input, point, baseline, epoch, or consumed server intent', () => {
    const authority = new RuleAuthority(TEST_POLICY);
    const state = testRuleState(); const world = testRuleWorld();
    const receipt = authority.adjudicate({ proposal: parseRuleCommand('走到门厅', state), inputText: '走到门厅', state, world, pointId: 'point_1' });
    for (const mutate of [
      (w: WorldContext) => { w.advance.inputId = 'another_input'; },
      (w: WorldContext) => { w.head.stateDigest = 'another_digest'; },
      (w: WorldContext) => { w.lease!.fenceEpoch++; },
    ]) {
      const changed = structuredClone(world); mutate(changed);
      expect(() => authority.deltas(receipt, changed, 'point_1', state)).toThrow(/scope_changed/);
    }
    const consumed = structuredClone(world); consumed.advance.intentStatus = 'consumed'; consumed.advance.inputAvailable = false;
    expect(() => authority.deltas(receipt, consumed, 'point_1', state)).toThrow(/input_not_pending/);
    expect(() => authority.adjudicate({ proposal: parseRuleCommand('走到门厅', state), inputText: '走到门厅', state, world: consumed, pointId: 'point_1' })).toThrow(/input_not_pending/);
    const anotherPoint = structuredClone(world); anotherPoint.activePointId = 'point_2';
    expect(() => authority.deltas(receipt, anotherPoint, 'point_2', state)).toThrow(/scope_changed/);
  });

  test('result text alone cannot enter the rule controller updates path', async () => {
    const { worldId: _id, ...initial } = testRuleState().initial;
    const run = createRuleController({ initial: initial as InitialTemplate, command: '走到门厅', policy: TEST_POLICY,
      prefix: 'rule_test', transport: { execute: async () => { throw new Error('No transport expected'); } } });
    await expect(run.model.generate('updates', 'invented_group', { mode: 'group', groupId: 'invented_group', results: { person_c: '已经成功' } })).rejects.toThrow(/without_rule_receipt/);
  });
});
