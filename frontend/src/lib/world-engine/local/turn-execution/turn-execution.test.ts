/** End-to-end turn execution through the REAL kernel: LocalWorldTransport +
 * ControllerDriver + the settlement port this lane owns. Only the semantic
 * answers (and the action lane's answers) are scripted fixtures here; state,
 * freezing, stage application, atomic commit and narration ordering are the
 * product's own code.
 *
 * What this file is for:
 *   - six stages stay full-cast: an off-screen character's achieved task and
 *     personality/sanity change are decided and committed;
 *   - later stages read the state after earlier stages were applied;
 *   - narration starts only after the whole point committed (the narrator sees
 *     the committed task status);
 *   - a continuation continues into an automatic round without re-consuming the
 *     player's text, and a model handback ends the chain;
 *   - a policy stop is surfaced as a visible failure, never recorded as
 *     `closedBy:'model'`.
 */
import { describe, expect, it } from 'vitest';
import { ControllerDriver, initialMemory, type WorldModelPort } from '../../controller';
import type { InferenceEngine } from '../../runtime/engine';
import type { ModelTask } from '../../schedule';
import type { InitialTemplate, Json } from '../../types';
import { SHORT_STATE } from '../../runtime/b3-short-samples';
import { LocalWorldTransport } from '../transport';
import { createSettlementModelPort, type PortCallRecord } from './index';

interface Brain {
  /** rooms by character id, so the fixture can express "off-screen". */
  placement: Record<string, string>;
  /** what the results answer says per scenario */
  taskAchieved?: boolean;
  /** appearance stage answers: room id -> op (may read the current record ids) */
  appearanceOps?: (prompt: string) => { entityId: string; op: string; recordIds: string[]; text: string | null }[];
  /** continuation answers, consumed in order */
  continuations: ({ candidates: { characterId: string; text: string }[]; judgments?: { likely: boolean; related: boolean }[] })[];
  /** every action call: the text and the advance's consumption state */
  seenInputs: { text: string | null; intentStatus: string | null; actor: string }[];
}

function brainState(overrides: Omit<Brain, 'seenInputs'>): Brain {
  return { seenInputs: [], ...overrides };
}

function initialState(brain: Brain): InitialTemplate {
  const initial = structuredClone(SHORT_STATE.initial) as InitialTemplate & { worldId?: string };
  delete initial.worldId;
  for (const [id, room] of Object.entries(brain.placement)) {
    initial.characters[id].initialPosition = { containerId: room, slotId: null, relativeTo: null };
  }
  return initial;
}

function scriptedEngine(brain: Brain): InferenceEngine {
  let continuationRound = 0;
  return {
    info: { backend: 'scripted', modelId: 'turn-execution-integration' },
    async load() {},
    async dispose() {},
    async complete(prompt: string): Promise<string> {
      if (prompt.includes('共同结算器')) {
        // One judgment + one fact for every frozen member of this group. The
        // member list comes from the prompt, so the same fixture serves a
        // player round (protagonist) and an automatic round (the NPC).
        const members = [...prompt.matchAll(/（id=([a-z_]+)）行动/gu)].map((match) => match[1]);
        const unique = [...new Set(members)];
        return JSON.stringify({
          judgments: unique.map((memberId) => ({
            memberId,
            label: memberId === 'person_c' && brain.taskAchieved ? 'achieved' : 'partial',
            reason: '这一组行动有明确结果。',
            effects: [],
          })),
          facts: unique.map((memberId) => ({
            text: memberId === 'person_c'
              ? (brain.taskAchieved ? '周宁把盒盖打开了。' : '周宁向盒盖伸了手，但没有打开。')
              : '林川朝门口走了一步，又停下来听。',
            memberIds: [memberId],
          })),
        });
      }
      if (prompt.includes('位置结算器')) return JSON.stringify({ changes: [] });
      if (prompt.includes('外貌结算器')) {
        return JSON.stringify({ operations: brain.appearanceOps ? brain.appearanceOps(prompt) : [] });
      }
      if (prompt.includes('任务条件核验器')) {
        return JSON.stringify({ judgments: [{
          characterId: 'person_a', taskId: 'task_watch', satisfied: 'yes', reason: '守门的条件已经成立。',
        }] });
      }
      if (prompt.includes('任务判定器')) {
        // One decision per character with tasks; the off-screen owner must be
        // decided too, and the decision covers all of that character's tasks.
        return JSON.stringify(brain.taskAchieved
          ? { unchanged: [], achieved: [{ characterId: 'person_a', tasks: [{ taskId: 'task_watch', basis: 'f1' }] }] }
          : { unchanged: ['person_a'], achieved: [] });
      }
      if (prompt.includes('新增小任务判断器')) return JSON.stringify({ subtasks: [] });
      if (prompt.includes('个性变化判断器')) {
        const operations = Object.keys(SHORT_STATE.initial.characters).map((id) => (
          brain.taskAchieved && id === 'person_a'
            ? { entityId: id, op: 'add', recordIds: [], text: '守了半天的门，反而更不肯离开。' }
            : { entityId: id, op: 'keep', recordIds: [], text: null }
        ));
        return JSON.stringify({ operations });
      }
      if (prompt.includes('理智重算器')) return JSON.stringify({ sanity: [{ characterId: 'person_a', value: 8 }] });
      if (prompt.includes('自动推进判断器')) {
        if (prompt.includes('{"candidates"')) {
          const plan = brain.continuations[continuationRound] ?? { candidates: [] };
          return JSON.stringify({ candidates: plan.candidates });
        }
        const plan = brain.continuations[continuationRound] ?? { candidates: [] };
        continuationRound += 1;
        const judgments = plan.candidates.map((candidate, index) => ({
          candidateId: `c${index + 1}`,
          characterId: candidate.characterId,
          text: candidate.text,
          likely: plan.judgments?.[index]?.likely ?? true,
          related: plan.judgments?.[index]?.related ?? true,
          reason: '与主角眼前这件事直接相关。',
        }));
        return JSON.stringify({ judgments });
      }
      throw new Error(`unexpected settlement prompt: ${prompt.slice(0, 60)}`);
    },
  };
}

function actionPort(state: () => InitialTemplate, brain: Brain): WorldModelPort {
  return {
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      if (task === 'pointPlan') {
        const data = input as { round?: { roundId: string; order: string[] } };
        const order = data.round?.order ?? [];
        return [{ pointId: `point_${data.round?.roundId ?? 'r'}_1`, kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: order }];
      }
      if (task === 'action') {
        const data = input as { actor: string; advance?: { inputText?: string | null; intentStatus?: string | null }; workingState: { protagonistId: string } };
        brain.seenInputs.push({
          text: data.advance?.inputText ?? null,
          intentStatus: data.advance?.intentStatus ?? null,
          actor: data.actor,
        });
        // The action lane's contract: a player command is executable only while
        // the advance is still `pending`. Once the round committed (consumed),
        // the same text is history, and an automatic round must decide from
        // world state instead of replaying the command.
        if (data.actor === data.workingState.protagonistId && data.advance?.intentStatus === 'pending' && data.advance.inputText) {
          return { kind: 'act', text: data.advance.inputText };
        }
        return data.actor === 'person_a'
          ? { kind: 'act', text: '林川朝盒盖那边走了一步。' }
          : { kind: 'skip' };
      }
      if (task === 'targets') return { targets: [] };
      if (task === 'reaction') return { kind: 'skip' };
      if (task === 'narration') {
        const data = input as { after: { characters: Record<string, { tasks: Record<string, { status: string }> }> } };
        const watched = data.after.characters.person_a?.tasks.task_watch?.status;
        return watched === 'achieved'
          ? '周宁把盒盖掀开，走廊里露出一点光。林川在门厅那头守着，没有回头。'
          : '周宁向盒盖伸出手，指节停在盖沿上。';
      }
      throw new Error(`unexpected action task ${task}`);
    },
  };
}

function driverFor(initial: InitialTemplate, brain: Brain) {
  const engine = scriptedEngine(brain);
  const settlement = createSettlementModelPort(engine);
  const actions = actionPort(() => initial, brain);
  const model: WorldModelPort = {
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      if (task === 'results' || task === 'updates' || task === 'continuation') {
        return settlement.generate(task, key, input);
      }
      return actions.generate(task, key, input);
    },
  };
  return { model, settlement, engine };
}

async function runPlayerTurn(initial: InitialTemplate, brain: Brain, text: string) {
  const order = Object.keys(initial.characters).sort();
  const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
  const { model, settlement } = driverFor(initial, brain);
  const memory = initialMemory('test_turn', 'holder_turn');
  memory.initialTemplate = initial;
  memory.playerInput = { text, order };
  memory.allocPlan = {
    allocationKey: 'test_turn_command',
    slots: [
      { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
      { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
      ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
    ],
  };
  const driver = new ControllerDriver({ transport, model }, memory);
  settlement.beginSubmission(text);
  const status = await driver.run();
  const submission = settlement.endSubmission();
  return { status, transport, submission, settlement };
}

describe('turn execution through the real kernel', () => {
  it('settles a six-stage update for an off-screen character and narrates only after commit', async () => {
    const brain = brainState({
      // The protagonist waits in the corridor; the task owner stands in the hall.
      placement: { person_c: 'corridor', person_a: 'hall' },
      taskAchieved: true,
      continuations: [{ candidates: [] }],
    });
    const initial = initialState(brain);
    const { status, transport, submission } = await runPlayerTurn(initial, brain, '我打开盒盖。');
    expect(status.kind).not.toBe('error');
    const snapshot = transport.snapshot();
    expect(snapshot.version).toBe(1);
    const committed = snapshot.state.characters.person_a;
    // The off-screen task was found and committed...
    expect(committed.tasks.task_watch.status).toBe('achieved');
    // ...and its personality + sanity followed in the same point.
    expect(committed.personalityChanges.find((change) => change.active)?.text).toBe('守了半天的门，反而更不肯离开。');
    expect(committed.sanity).toBe(8);
    // Narration was produced from the committed state (see the narration fixture:
    // it only says "掀开" when the task is already achieved).
    const narration = snapshot.narrations[snapshot.headPointId];
    expect(narration?.status).toBe('ready');
    const text = JSON.stringify(narration);
    expect(text).toContain('掀开');
    // The player submission account covers the settlement work of the turn:
    // one joint results task, one merged six-stage updates task (six model
    // calls inside it) and one continuation assessment.
    // One results call and one merged six-stage updates task per frozen group;
    // this round has two frozen groups (the protagonist and the off-screen
    // owner), so both tasks run once per group.
    expect(submission?.resultsCalls).toBeGreaterThanOrEqual(1);
    const updates = submission?.calls.filter((call: PortCallRecord) => call.task === 'updates') ?? [];
    expect(updates).toHaveLength(submission?.resultsCalls ?? 0);
    // Every group runs the fixed stage order; stages with no trigger are
    // skipped by design (personality needs a new achievement, sanity needs a
    // personality change), so the achieved group's list is the full six.
    for (const task of updates) expect(task.stages?.slice(0, 4)).toEqual(['position', 'appearance', 'tasks', 'subtasks']);
    const full = updates.find((task) => task.stages?.length === 6);
    expect(full?.stages).toEqual(['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity']);
    // The program audit still counts the whole cast; only affected owners are
    // put in front of the model.
    const cast = Object.keys(initial.characters).length;
    expect(full?.coverage).toMatchObject({ tasks: cast, personality: cast, mode: 'affected_projection' });
    expect(full?.coverage?.taskRows).toBeGreaterThan(0);
    // The semantic decision is in the ledger, not only the row count.
    expect(full?.coverage?.achievedByCharacter).toEqual([{ characterId: 'person_a', taskIds: ['task_watch'] }]);
    expect(full?.coverage?.assertedUnchanged).toBeGreaterThanOrEqual(0);
    expect(Object.keys(full?.stageMs ?? {})).toEqual(['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity']);
    expect(Object.values(full?.stageMs ?? {}).every((ms) => Number.isFinite(ms) && ms >= 0)).toBe(true);
    expect(submission?.continuationCalls).toBe(1);
  });

  it('continues into an automatic round from model candidates without re-reading the player text', async () => {
    const brain = brainState({
      placement: { person_c: 'corridor', person_a: 'corridor' },
      taskAchieved: true,
      continuations: [
        { candidates: [{ characterId: 'person_a', text: '林川朝盒盖那边走了一步。' }] },
        { candidates: [] },
      ],
    });
    const initial = initialState(brain);
    const { status, transport, submission } = await runPlayerTurn(initial, brain, '我打开盒盖。');
    expect(status).not.toMatchObject({ kind: 'error' });
    const snapshot = transport.snapshot();
    // Two points: the player's round and the model-proposed follow-up round.
    expect(snapshot.version).toBe(2);
    expect(snapshot.round?.trigger).toBe('automatic');
    expect(submission?.continuationDecision).toBe('handback');
    // The automatic round's action was judged from state, not from the player
    // text: the only text the action task saw there was empty.
    // Input consumption: the automatic round ran with the player's advance
    // already `consumed`, so no actor could replay the command as a new action.
    const consumed = brain.seenInputs.filter((call) => call.intentStatus === 'consumed');
    expect(consumed.length).toBeGreaterThan(0);
    expect(consumed.every((call) => call.actor === 'person_c' || call.text === '我打开盒盖。')).toBe(true);
  });

  it('runs a multi-round chain, consumes the command once, and stops on no progress', async () => {
    const brain = brainState({
      placement: { person_c: 'corridor', person_a: 'corridor' },
      taskAchieved: false,
      continuations: [
        { candidates: [{ characterId: 'person_a', text: '林川朝盒盖那边走了一步。' }] },
        { candidates: [{ characterId: 'person_a', text: '林川又往前挪了半步。' }] },
        { candidates: [{ characterId: 'person_a', text: '林川伸手碰了碰盒沿。' }] },
        { candidates: [{ characterId: 'person_a', text: '林川低头看了看盒子。' }] },
      ],
    });
    const initial = initialState(brain);
    const order = Object.keys(initial.characters).sort();
    const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
    const { model, settlement } = driverFor(initial, brain);
    const memory = initialMemory('test_chain', 'holder_chain');
    memory.initialTemplate = initial;
    memory.playerInput = { text: '我打开盒盖。', order };
    memory.allocPlan = {
      allocationKey: 'test_chain_command',
      slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
        { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
        ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
      ],
    };
    const driver = new ControllerDriver({ transport, model }, memory);
    settlement.beginSubmission('我打开盒盖。');
    await expect(driver.run()).rejects.toThrow(/continuation_policy_no_progress/u);
    const submission = settlement.endSubmission()!;
    // Two rounds produced no committed change (the player's own round and the
    // first automatic round), which is the designed no-progress stop: the chain
    // ends after the second observation, not at a default call cap.
    expect(submission.continuationCalls).toBe(2);
    expect(submission.continuationDecision).toBe('policy_stop');
    expect(submission.stops).toContain('continuation:continuation_policy_no_progress');
    expect(submission.updatesCalls).toBeGreaterThanOrEqual(2);
    // The player command is executable exactly once; later rounds see it as
    // history and the action lane decides from state instead.
    const executedPlayerCommand = brain.seenInputs.filter((call) => call.text === '我打开盒盖。' && call.intentStatus === 'pending');
    expect(executedPlayerCommand.length).toBeGreaterThan(0);
    expect(brain.seenInputs.some((call) => call.intentStatus === 'consumed')).toBe(true);
    const snapshot = transport.snapshot();
    expect(snapshot.version).toBe(2);
    expect(snapshot.round?.trigger).toBe('automatic');
    expect(snapshot.round?.conclusion).toBeNull();
    // A policy stop never rewrites committed state.
    expect(snapshot.state.characters.person_a.tasks.task_watch?.status).toBe('pending');
  });

  // Shared bug fixed by 06 (schedule.ts `inputIds`): the working state's
  // location appearanceChanges are now registered as known change ids, so a
  // second change to the same room is a normal replacement instead of a
  // dangling reference. Promoted from `it.fails` when the fix landed.
  it('replaces the same room appearance on a second turn and keeps the old record', async () => {
    // Turn 1 adds the room's first change; turn 2 replaces that change with a
    // new id, which references a record the working state already has.
    let turn = 0;
    const brain = brainState({
      placement: { person_c: 'corridor', person_a: 'corridor' },
      taskAchieved: false,
      continuations: [{ candidates: [] }, { candidates: [] }],
      // Every actor gets an appearance-stage prompt; only the first one (turn 1)
      // and the first call of the next round (turn 4) touch the room, so the
      // add and its replacement land in different points. Several replacements
      // in one point would be refused for superseding a same-point change,
      // which is a different rule from the bug under test.
      appearanceOps: (prompt) => {
        turn += 1;
        if (turn !== 1 && turn !== 4) return [];
        const line = prompt.split(String.fromCharCode(10)).find((row) => row.includes('id=corridor'));
        const recordIds = /记录=\[([^\]]*)\]/u.exec(line ?? '')?.[1].split(',').filter(Boolean) ?? [];
        if (turn === 1) return [{ entityId: 'corridor', op: 'add', recordIds: [], text: '地板上多了一道新划痕。' }];
        return [{ entityId: 'corridor', op: 'replace', recordIds, text: '地板上的划痕被拖把抹开成一片。' }];
      },
    });
    const initial = initialState(brain);
    const order = Object.keys(initial.characters).sort();
    const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
    const { model } = driverFor(initial, brain);
    const memory = initialMemory('test_room', 'holder_room');
    memory.initialTemplate = initial;
    const slots = [
      { slotKey: 'advance', kind: 'advance' as const }, { slotKey: 'input', kind: 'input' as const },
      { slotKey: 'round', kind: 'round' as const }, { slotKey: 'point', kind: 'point' as const },
      ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
    ];
    memory.playerInput = { text: '我擦掉地板上的划痕。', order };
    memory.allocPlan = { allocationKey: 'turn_1', slots };
    const driver = new ControllerDriver({ transport, model }, memory);
    const first = await driver.run();
    expect(first.kind).not.toBe('error');
    const firstState = transport.snapshot();
    const added = firstState.state.locations.corridor.appearanceChanges;
    expect(added.some((change) => change.active && change.text === '地板上多了一道新划痕。')).toBe(true);
    const secondText = '我把地板擦干净。';
    driver.preparePlayerInput(secondText, order, { allocationKey: 'turn_2', slots }, Object.keys(driver.getMemory().ids));
    const second = await driver.run();
    expect(second.kind).not.toBe('error');
    const changes = transport.snapshot().state.locations.corridor.appearanceChanges;
    expect(changes.some((change) => change.active && change.text === '地板上的划痕被拖把抹开成一片。')).toBe(true);
  });

  it('surfaces a policy stop as a visible failure instead of a fake model handback', async () => {
    const brain = brainState({
      placement: { person_c: 'corridor', person_a: 'corridor' },
      taskAchieved: false,
      continuations: [
        { candidates: [{ characterId: 'person_a', text: '林川朝盒盖那边走了一步。' }] },
        { candidates: [{ characterId: 'person_a', text: '林川朝盒盖那边走了一步。' }] },
      ],
    });
    const initial = initialState(brain);
    const engine = scriptedEngine(brain);
    const settlement = createSettlementModelPort(engine, { continuation: { noProgressRounds: 99, repeatRounds: 99, maxAutoContinuations: 0 } });
    const actions = actionPort(() => initial, brain);
    const order = Object.keys(initial.characters).sort();
    const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
    const memory = initialMemory('test_cap', 'holder_cap');
    memory.initialTemplate = initial;
    memory.playerInput = { text: '我打开盒盖。', order };
    memory.allocPlan = {
      allocationKey: 'test_cap_command',
      slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
        { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
        ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
      ],
    };
    const driver = new ControllerDriver({
      transport,
      model: {
        async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
          if (task === 'results' || task === 'updates' || task === 'continuation') return settlement.generate(task, key, input);
          return actions.generate(task, key, input);
        },
      },
    }, memory);
    await expect(driver.run()).rejects.toThrow(/continuation_policy_safety_cap/u);
    // The committed point is untouched: a policy stop never rewrites state.
    const snapshot = transport.snapshot();
    expect(snapshot.round?.conclusion).toBeNull();
    expect(snapshot.round?.trigger).toBe('player');
  });
});

describe('settlement port failure evidence', () => {
  it('aborts a failed repair and keeps raw output, attempts and timings in the ledger', async () => {
    const engine: InferenceEngine = {
      info: { backend: 'scripted', modelId: 'failure-evidence' },
      async load() {},
      async dispose() {},
      async complete() { return 'not json'; },
    };
    const port = createSettlementModelPort(engine);
    const state = structuredClone(SHORT_STATE) as unknown as Json;
    const input = {
      groupId: 'group_failure',
      members: [{ memberId: 'person_c', actionText: '我推门。', rollRefs: [] }],
      workingState: state,
    } as unknown as Json;
    port.beginSubmission('我推门。');
    await expect(port.generate('results', 'group_failure', input)).rejects.toThrow('settlement_failed:results');
    const submission = port.endSubmission();
    expect(submission?.resultsCalls).toBe(1);
    expect(submission?.stops[0]).toContain('model_output_invalid');
    const record = submission?.calls[0];
    expect(record?.fallback).toBe(true);
    expect(record?.raw).toContain('not json');
    expect(record?.rawChars).toBeGreaterThan(0);
    expect(record?.attempts).toHaveLength(2);
    expect(record?.attempts?.[0].ms).toBeGreaterThanOrEqual(0);
    expect(record?.attempts?.[0].rawChars).toBe(8);
  });
});
