import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ControllerDriver, initialMemory, type WorldModelPort } from '../../controller';
import type { ModelTask } from '../../schedule';
import type { InitialTemplate, Json } from '../../types';
import { buildInitialState } from '../state';
import { LocalWorldTransport } from '../transport';
import { createActionExecutionModel } from './port';
import { roundOrder } from './order';

/** The shipped free-day world, not a fixture: the action port must survive the
 * real 14-character roster, slots, carried items and 26 locations. */
function loadProductWorld(): { initial: InitialTemplate; state: ReturnType<typeof buildInitialState> } {
  const raw = JSON.parse(readFileSync(resolve(process.cwd(), 'public/worlds/dragon-raja-free-day.world.json'), 'utf8')) as { worldId: string; initial: InitialTemplate & { worldId: string } };
  const initial = structuredClone(raw.initial) as InitialTemplate & { worldId?: string };
  delete initial.worldId;
  const state = buildInitialState({ ...structuredClone(raw.initial), worldId: raw.worldId });
  return { initial, state };
}

describe('free-day product world through the action port', () => {
  it('orders by sanity and judges the same-room NPC from the real scene', async () => {
    const { initial, state } = loadProductWorld();
    const order = roundOrder(state);
    expect(order.slice(0, 5)).toEqual(['lin', 'tang', 'shen', 'lu', 'zhou']);
    expect(order.at(-1)).toBe('manstein');

    const prompts: string[] = [];
    const engine = {
      info: { backend: 'fake', modelId: 'fake' },
      async load() {},
      async dispose() {},
      async complete(prompt: string): Promise<string> {
        if (prompt.includes('角色行动判断器')) {
          prompts.push(prompt);
          return JSON.stringify({ kind: 'act', text: '诺诺把短枪往腰后一压，抬眼看向巷口。' });
        }
        if (prompt.includes('牵连判断器')) return JSON.stringify({ targets: [] });
        throw new Error('no reaction is expected in this round');
      },
    };
    const captured: { task: ModelTask; input: Json }[] = [];
    const delegate: WorldModelPort = {
      async generate(task, _key, input) {
        captured.push({ task, input });
        if (task === 'pointPlan') return [{ pointId: 'point_free_1', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: [] }];
        if (task === 'results') {
          const members = (input as { members: { memberId: string }[] }).members;
          return Object.fromEntries(members.map((member) => [member.memberId, `${member.memberId} 把动作做完了。`]));
        }
        if (task === 'updates') return [];
        if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
        if (task === 'narration') return '西侧服务巷里，诺诺抬眼看过来，远处钟楼的影子压在操场上。';
        throw new Error(`unexpected ${task}`);
      },
    };
    const port = createActionExecutionModel(delegate, engine, { attempts: 1 });
    const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
    const memory = initialMemory('free_day_actions', 'holder');
    memory.initialTemplate = initial;
    memory.playerInput = { text: '我把护目镜推上去，盯着巷口。', order };
    memory.allocPlan = {
      allocationKey: 'free_day_command',
      slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
        { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
        ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
      ],
    };
    const status = await new ControllerDriver({ transport, model: port }, memory).run();
    expect(status.kind).not.toBe('error');

    // Only 诺诺 shares the lane with 路明非; the other twelve slots are a
    // visibility scope skip, not a name rule.
    const actions = port.evidence.filter((entry) => entry.task === 'action');
    expect(actions.map((entry) => entry.key)).toEqual(['lin', 'tang', 'shen', 'lu', 'zhou', 'fingel', 'nono', 'qin', 'su', 'chu', 'caesar', 'tomiyama', 'doctor', 'manstein']);
    expect(actions.filter((entry) => entry.source === 'model').map((entry) => entry.key)).toEqual(['nono']);
    expect(prompts).toHaveLength(1);
    expect(prompts[0]).toContain('诺诺');
    expect(prompts[0]).toContain('路明非');            // same room, other character
    expect(prompts[0]).toContain('诺诺的演习短枪');     // carried item is in the scene
    expect(prompts[0]).toContain('不在场角色');         // off-screen roster is labelled, not hidden
    expect(prompts[0]).toContain('芬格尔');

    const snapshot = transport.snapshot();
    expect(snapshot.round?.order).toEqual(order);
    expect(snapshot.round?.cursor).toBe(order.length);
    expect(snapshot.state.time.dateTime).toBe('2009-10-17T15:21:00');
    expect(snapshot.version).toBe(1);
    // The player command is the protagonist's frozen action, verbatim.
    const protagonist = port.evidence.find((entry) => entry.task === 'action' && entry.key === 'lu');
    expect(protagonist?.value).toEqual({ kind: 'act', text: '我把护目镜推上去，盯着巷口。' });
  }, 30000);
});
