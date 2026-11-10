import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ControllerDriver, initialMemory, type WorldModelPort } from '../../controller';
import type { ModelTask } from '../../schedule';
import type { InitialTemplate, Json } from '../../types';
import { buildInitialState } from '../state';
import { LocalWorldTransport } from '../transport';
import { createActionExecutionModel } from './port';
import { createActionHandlers } from '../semantics/actions';
import { checkActionText } from '../semantics/actions/checks';
import { sharedSubsequence, skeleton } from '../semantics/actions/text';
import { buildScene } from '../semantics/actions/scene';
import { targetsPrompt } from '../semantics/actions/prompts';
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

describe('task-goal classifier on the shipped world', () => {
  it('accepts a concrete task-driven action and still rejects a verbatim goal', () => {
    const { state } = loadProductWorld();
    const scene = buildScene(state, 'nono');
    const options = { maxActionChars: 120, maxReactionChars: 200, maxTargets: 4 };
    // The classifier flags an action when >=85% of the ACTION's characters
    // are a subsequence of a registered goal. A concrete step that uses the
    // task vocabulary but is longer than the goal is not a copy (0.84 here);
    // a shortened goal restatement is (1.0). This is the boundary the 0b69
    // diagnosis depends on: the model was emitting goal fragments, so the
    // fix is the prompt/repair, not loosening the guard.
    const goal = '确认西回廊的蓝方伤员是否需要真正的医护帮助';
    const concrete = '诺诺蹲下确认西回廊的蓝方伤员，是否需要真正的医护帮助。';
    expect(sharedSubsequence(skeleton(concrete), skeleton(goal)).coverage).toBeLessThan(0.85);
    const concreteIssues = checkActionText(concrete, scene, state, options).issues;
    expect(concreteIssues.filter((issue) => issue.code === 'action_is_task_goal')).toHaveLength(0);
    const fragment = '确认西回廊的蓝方伤员是否需要医护帮助。';
    expect(sharedSubsequence(skeleton(fragment), skeleton(goal)).coverage).toBeGreaterThanOrEqual(0.85);
    const fragmentIssues = checkActionText(fragment, scene, state, options).issues;
    expect(fragmentIssues.some((issue) => issue.code === 'action_is_task_goal')).toBe(true);
    // A verbatim goal is still caught.
    const verbatim = '确认西回廊的蓝方伤员是否需要真正的医护帮助。';
    const copyIssues = checkActionText(verbatim, scene, state, options).issues;
    expect(copyIssues.some((issue) => issue.code === 'action_is_task_goal')).toBe(true);
  });
});

describe('the real 17:01Z nono prompt on the shipped world', () => {
  it('carries no player sentence and no echo event', async () => {
    const { state } = loadProductWorld();
    const prompts: string[] = [];
    const engine = {
      info: { backend: 'fake', modelId: 'fake' },
      async load() {},
      async dispose() {},
      async complete(prompt: string): Promise<string> { prompts.push(prompt); return '{"kind":"skip"}'; },
    };
    const handlers = createActionHandlers({ engine, options: {
      recentEvents: () => [
        // The 17:01Z firstReadableSample shape: the player's action with one
        // name substituted, then a scene line that must survive.
        '路明非沿着服务巷往里走，先看清墙上的演习规则牌。路明非成功看清墙上的演习规则牌并准备行动，符合行动要求。',
        '西侧服务巷里，巷口的黄黑绳已放下，墙角留下新鲜的演习弹红痕。',
      ],
    } });
    const text = '我沿着服务巷往里走，先看清墙上的演习规则牌。';
    const result = await handlers.action('nono', {
      advance: { inputText: text, intentStatus: 'pending' },
      workingState: state,
    } as unknown as Json);
    expect(result.value).toEqual({ kind: 'skip' });
    const prompt = prompts[0]!;
    expect(prompt).toContain('诺诺');
    expect(prompt).toContain('主角也在同一地点');
    expect(prompt).not.toContain('我沿着服务巷往里走');
    expect(prompt).not.toContain('路明非沿着服务巷往里走');
    expect(prompt).toContain('黄黑绳');
    // One NPC action prompt on the real 14-character world stays small; this
    // is the 03 side of the 04/03 prefill question.
    expect(prompt.length).toBeLessThan(4000);
  });
});

describe('joint-group input coverage on the shipped world', () => {
  it('the targets prompt for a question to 诺诺 lists her as a visible candidate', () => {
    const { state } = loadProductWorld();
    const scene = buildScene(state, 'lu');
    expect(scene.isProtagonist).toBe(true);
    expect(scene.visible.some((character) => character.id === 'nono')).toBe(true);
    const text = '我把护目镜推上去，问诺诺：现在红蓝两方各在哪？';
    const prompt = targetsPrompt(scene, text, 2);
    // The model must be able to connect the named target to a registered id;
    // the prompt carries her name, her id and the exact frozen action.
    expect(prompt).toContain('诺诺（id=nono）');
    // 诺诺 is visible, so she must not appear in the absent list (which marks
    // each entry with its room: 「诺诺（id=nono）在…」).
    expect(prompt).not.toContain('诺诺（id=nono）在');
    expect(prompt).toContain(text);
    // 路明非's own goggles and the lane's rules board are in the scene list.
    expect(prompt).toContain('路明非的护目镜');
    expect(prompt).toContain('演习规则牌');
  });
});

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
