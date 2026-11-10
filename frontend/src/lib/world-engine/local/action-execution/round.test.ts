import { describe, expect, it } from 'vitest';
import { ControllerDriver, initialMemory, type WorldModelPort } from '../../controller';
import type { ModelTask } from '../../schedule';
import type { InitialTemplate, Json, RequestMap } from '../../types';
import { LocalWorldTransport } from '../transport';
import { buildTestWorld } from '../semantics/actions/fixtures';
import { createActionExecutionModel } from './port';
import { roundOrder } from './order';

function template(): InitialTemplate {
  const initial = structuredClone(buildTestWorld().initial) as InitialTemplate & { worldId?: string };
  delete initial.worldId;
  return initial;
}

interface Captured { task: ModelTask; key: string; input: Json }

/** Engine that answers the three action-family tasks. `servant` is offscreen
 * and never reaches it; the protagonist is program-frozen; so the only action
 * answer this engine must give is 阿宁's. */
function actionEngine(calls: string[]) {
  return {
    info: { backend: 'fake', modelId: 'fake-actions' },
    async load() {},
    async dispose() {},
    async complete(prompt: string): Promise<string> {
      if (prompt.includes('角色行动判断器')) {
        calls.push('action');
        expect(prompt).toContain('阿宁');
        return JSON.stringify({ kind: 'act', text: '阿宁把木门拉上，横过门栓。' });
      }
      if (prompt.includes('牵连判断器')) {
        calls.push('targets');
        // 阿宁's own action (closing the door) forces nobody. The player's
        // action asks 阿宁 directly, so it names her as the target.
        if (prompt.includes('推门走进大厅')) return JSON.stringify({ targets: [{ targetId: 'ally' }] });
        return JSON.stringify({ targets: [] });
      }
      if (prompt.includes('反应生成器')) {
        calls.push('reaction');
        throw new Error('this round must not ask for a reaction after the target already acted');
      }
      throw new Error(`unexpected prompt: ${prompt.slice(0, 40)}`);
    },
  };
}

/** Results/updates/continuation/narration stay scripted: they are not this
 * module's task, but the round cannot commit without them. */
function settlementModel(captured: Captured[]): WorldModelPort {
  return {
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      captured.push({ task, key, input });
      if (task === 'pointPlan') {
        return [{ pointId: 'point_round_1_1', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: [] }];
      }
      if (task === 'results') {
        const members = (input as { members: { memberId: string }[] }).members;
        return Object.fromEntries(members.map((member) => [member.memberId, `${member.memberId} 的行动有了结果。`]));
      }
      if (task === 'updates') return [];
      if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
      if (task === 'narration') return '大厅里安静了一拍，门栓落下，走廊那头没有回声。';
      throw new Error(`unexpected settlement task: ${task}`);
    },
  };
}

describe('real round through the controller with the action-execution port', () => {
  it('freezes sanity order, acts without being named, keeps dice of an already-acted target and stages one group', async () => {
    const initial = template();
    const state = buildTestWorld();
    const order = roundOrder(state);
    expect(order).toEqual(['servant', 'ally', 'hero', 'rival']);

    const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
    const captured: Captured[] = [];
    const modelCalls: string[] = [];
    const port = createActionExecutionModel(settlementModel(captured), actionEngine(modelCalls), { attempts: 1 });

    const playerText = '我推门走进大厅，把护目镜往上推，问阿宁门外的动静。';
    const memory = initialMemory('test_actions', 'holder_actions');
    memory.initialTemplate = initial;
    memory.playerInput = { text: playerText, order };
    memory.allocPlan = {
      allocationKey: 'test_actions_command',
      slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
        { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
        ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
      ],
    };
    // Record the single commit request so the group units can be inspected:
    // the point is one atomic write, and each frozen group is one unit.
    const commits: RequestMap['commit_point'][] = [];
    const observed = {
      execute: async (operation: Parameters<typeof transport.execute>[0], request: never, scope: never) => {
        if (operation === 'commit_point') commits.push(request as unknown as RequestMap['commit_point']);
        return transport.execute(operation, request, scope);
      },
    } as unknown as typeof transport;
    const driver = new ControllerDriver({ transport: observed, model: port }, memory);
    const status = await driver.run();
    expect(status.kind).not.toBe('error');

    const snapshot = transport.snapshot();
    expect(snapshot.round?.order).toEqual(order);
    expect(snapshot.round?.cursor).toBe(order.length);
    expect(snapshot.round?.actedIds).toEqual(expect.arrayContaining(['ally', 'hero']));
    expect(snapshot.version).toBe(1);

    // The player command is frozen verbatim as the protagonist action even
    // though it matches no fixed command list.
    const protagonist = port.evidence.find((entry) => entry.task === 'action' && entry.key === 'hero');
    expect(protagonist?.source).toBe('program');
    expect(protagonist?.value).toEqual({ kind: 'act', text: playerText });

    // 阿宁 acted from her own task without being named by the player.
    const npc = port.evidence.find((entry) => entry.task === 'action' && entry.key === 'ally');
    expect(npc?.source).toBe('model');
    expect(npc?.value).toEqual({ kind: 'act', text: '阿宁把木门拉上，横过门栓。' });

    // 老周 is in the study: a scope skip, not a name rule.
    const offscreen = port.evidence.find((entry) => entry.task === 'action' && entry.key === 'rival');
    expect(offscreen?.source).toBe('program');
    expect(offscreen?.value).toEqual({ kind: 'skip' });

    // The protagonist's action named 阿宁; she already acted, so the roll is
    // recorded with eligible=false and stays as result input, while no second
    // reaction call is made.
    const rolls = Object.values(snapshot.rolls ?? {});
    expect(rolls).toHaveLength(1);
    expect(rolls[0]).toMatchObject({ sourceId: 'hero', targetId: 'ally', eligible: false, admitted: false });
    expect(port.evidence.some((entry) => entry.task === 'reaction')).toBe(false);

    // One results call per settled group, with the surviving roll attached to
    // the source member, and no partial group result written.
    const results = captured.filter((entry) => entry.task === 'results');
    expect(results).toHaveLength(2);
    const heroResults = results.at(-1)!.input as { members: { memberId: string; rollRefs: unknown[] }[] };
    expect(heroResults.members[0].memberId).toBe('hero');
    expect(heroResults.members[0].rollRefs).toHaveLength(1);

    // One action judgement (阿宁) and one target judgement per acting group
    // source (阿宁, then the protagonist); 老周 stayed out of the scene.
    expect(modelCalls).toEqual(['action', 'targets', 'targets']);

    // Both settlements were frozen and committed inside the same point, each
    // group as one unit — no partial group result was written between them.
    expect(commits).toHaveLength(1);
    expect(commits[0].settlementGroups.map((group) => group.actorIds)).toEqual([['ally'], ['hero']]);
    expect(commits[0].settlementGroups[0].groupId).not.toBe(commits[0].settlementGroups[1].groupId);
  });
});
