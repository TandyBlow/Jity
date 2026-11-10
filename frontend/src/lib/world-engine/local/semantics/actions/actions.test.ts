/** Structural and rule-level tests for the action handlers.
 *
 * The engine is scripted on purpose: these tests prove that inputs reach the
 * model, that the declared call shapes and the codec stay intact, and that
 * the program guards accept/reject/repair the cases they claim to. They are
 * NOT semantic evidence — a scripted reply says nothing about what a real
 * model does with these prompts. Real-model evidence lives in
 * frontend/scripts/parallel-actions/ and its archive.
 */
import { describe, expect, it } from 'vitest';
import type { InferenceEngine } from '../../../runtime/engine';
import { decodeTaskOutput } from '../../../runtime/structured-output';
import type { Json, WorldState } from '../../../types';
import { createActionHandlers, createActionModelPort, buildScene, targetsPrompt as targetsPromptForTest, type HandlerResult } from './index';
import { buildTestWorld, withPosition } from './fixtures';

type Reply = string | Error | ((prompt: string, call: number) => string);

class ScriptedEngine implements InferenceEngine {
  readonly info = { backend: 'scripted', modelId: 'scripted-test' };
  readonly prompts: string[] = [];
  private readonly replies: Reply[];
  constructor(replies: Reply[]) { this.replies = replies; }
  async load(): Promise<void> { /* nothing to load */ }
  async complete(prompt: string): Promise<string> {
    this.prompts.push(prompt);
    const reply = this.replies.shift();
    if (reply === undefined) throw new Error('scripted engine ran out of replies');
    if (reply instanceof Error) throw reply;
    return typeof reply === 'function' ? reply(prompt, this.prompts.length) : reply;
  }
  async dispose(): Promise<void> { /* nothing to dispose */ }
}

function actInput(state: WorldState, actor: string, inputText: string | null, intentStatus = 'pending'): Json {
  return { actor, advance: { inputText, intentStatus }, workingState: state } as unknown as Json;
}
function targetsInput(state: WorldState, sourceId: string, actionText: string): Json {
  return { sourceId, actionText, workingState: state } as unknown as Json;
}
function reactionInput(state: WorldState, sourceId: string, memberId: string, sourceActionText: string): Json {
  return { sourceId, memberId, sourceActionText, rollId: 'roll_1', workingState: state } as unknown as Json;
}
function codes(result: HandlerResult): string[] {
  return result.issues.map((item) => item.code);
}
function codecAccepts(result: HandlerResult): void {
  const raw = typeof result.value === 'string' ? result.value : JSON.stringify(result.value);
  expect(() => decodeTaskOutput(result.task, raw)).not.toThrow();
}

describe('prompts do not offer a copyable fake id', () => {
  it('shows a registered target id in the targets example', () => {
    const state = buildTestWorld();
    const scene = buildScene(state, 'hero');
    const prompt = targetsPromptForTest(scene, '阿宁把木箱推到门边。', 2);
    // A literal "角色id"/"id" in the example is what small models copy; the
    // 13:21Z run produced the literal `id` in the updates output.
    expect(prompt).toContain('"targetId":"ally"');
    expect(prompt).not.toContain('角色id');
    expect(prompt).not.toMatch(/"targetId":"id"/);
  });
});

describe('scene derivation', () => {
  it('separates present, nested-location, absent and carried entities', () => {
    const state = buildTestWorld();
    const scene = buildScene(state, 'hero');
    expect(scene.visible.map((character) => character.id)).toEqual(['ally']);
    // 小满 is inside cage (a child location of hall), so not in the same room.
    expect(scene.absent.map((character) => character.id)).toEqual(['rival', 'servant']);
    expect(scene.items.map((item) => item.id)).toEqual(['crate', 'knife', 'torch']);
    expect(scene.items.find((item) => item.id === 'knife')?.position).toContain('木箱');
    expect(scene.items.find((item) => item.id === 'knife')?.position).toContain('大厅');
    expect(scene.items.find((item) => item.id === 'torch')?.position).toContain('路明非');
    expect(scene.actor.tasks[0]).toMatchObject({ id: 'task_hero_key', status: 'pending' });
    expect(scene.roomChain).toEqual(['大厅']);
  });

  it('reports an unregistered focus id instead of inventing a scene', () => {
    expect(() => buildScene(buildTestWorld(), 'nobody')).toThrow(/actor_unknown/);
  });
});

describe('action: autonomous, named and failed judgement', () => {
  it('asks the model for an unnamed same-room NPC and accepts an autonomous action', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"kind":"act","text":"阿宁退回门边，把门闩压紧。"}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('ally', actInput(state, 'ally', '我靠在墙边喘口气。'));

    expect(result.source).toBe('model');
    expect(result.value).toEqual({ kind: 'act', text: '阿宁退回门边，把门闩压紧。' });
    expect(result.attempts).toBe(1);
    expect(codes(result)).not.toContain('actor_out_of_scene');
    expect(codes(result)).not.toContain('model_skip');
    // The task and the scene are in the prompt: no name/interaction gate ran.
    expect(engine.prompts[0]).toContain('task_ally_watch');
    expect(engine.prompts[0]).toContain('我靠在墙边喘口气。');
    expect(engine.prompts[0]).toContain('守住大厅木门');
    expect(engine.prompts[0]).toContain('老周');
    codecAccepts(result);
  });

  it('lets a named NPC legitimately do nothing', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"kind":"skip"}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('ally', actInput(state, 'ally', '阿宁，你看见钥匙了吗？'));

    expect(result.source).toBe('model');
    expect(result.value).toEqual({ kind: 'skip' });
    expect(codes(result)).toContain('model_skip');
    expect(result.fallback).toBe(false);
    codecAccepts(result);
  });

  it('repairs an NPC action that copies the player words verbatim', async () => {
    const state = buildTestWorld();
    const player = '我把木箱推到门边挡住门。';
    const engine = new ScriptedEngine([
      JSON.stringify({ kind: 'act', text: player }),
      '{"kind":"act","text":"阿宁抬手抵住箱沿，把箱子挪正。"}',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('ally', actInput(state, 'ally', player));

    expect(result.attempts).toBe(2);
    expect(result.value).toEqual({ kind: 'act', text: '阿宁抬手抵住箱沿，把箱子挪正。' });
    expect(codes(result)).toContain('npc_repeats_player');
    expect(codes(result)).toContain('repair_requested');
    expect(engine.prompts[1]).toContain('上一次输出不能采用');
    codecAccepts(result);
  });

  it('falls back to inaction when the model keeps impersonating the player', async () => {
    const state = buildTestWorld();
    const player = '我把木箱推到门边挡住门。';
    const engine = new ScriptedEngine([JSON.stringify({ kind: 'act', text: player }), JSON.stringify({ kind: 'act', text: player })]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('ally', actInput(state, 'ally', player));

    expect(result.value).toEqual({ kind: 'skip' });
    expect(result.source).toBe('fallback');
    expect(result.fallback).toBe(true);
    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('repair_failed');
    codecAccepts(result);
  });

  it('skips a character in another room without spending a model call by default', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine([]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('rival', actInput(state, 'rival', '我靠在墙边喘口气。'));

    expect(result.value).toEqual({ kind: 'skip' });
    expect(result.source).toBe('program');
    expect(codes(result)).toContain('actor_out_of_scene');
    expect(engine.prompts).toHaveLength(0);
    codecAccepts(result);
  });

  it('judges a character in another room from its own scene when configured', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"kind":"act","text":"老周把字条塞进袖口，转身把书房门锁上。"}']);
    const handlers = createActionHandlers({ engine, options: { offscreenPolicy: 'judge' } });
    const result = await handlers.action('rival', actInput(state, 'rival', '我在大厅喊老周的名字。'));

    expect(result.source).toBe('model');
    expect(codes(result)).not.toContain('actor_out_of_scene');
    expect(result.value).toEqual({ kind: 'act', text: '老周把字条塞进袖口，转身把书房门锁上。' });
    // The actor gets its own room and tasks, never the protagonist's move.
    expect(engine.prompts[0]).toContain('task_rival_guard');
    expect(engine.prompts[0]).toContain('主角不在这里');
    expect(engine.prompts[0]).not.toContain('我在大厅喊老周的名字。');
    codecAccepts(result);
  });

  it('keeps the player pending command as the frozen action', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine([]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('hero', actInput(state, 'hero', '我推开木箱。'));

    expect(result.value).toEqual({ kind: 'act', text: '我推开木箱。' });
    expect(result.source).toBe('program');
    expect(codes(result)).toContain('protagonist_command');
    expect(engine.prompts).toHaveLength(0);
    codecAccepts(result);
  });

  it('never lets the model write the protagonist after the command was consumed', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"kind":"act","text":"路明非顺着箱盖的缝隙又顶了一下。"}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('hero', actInput(state, 'hero', '我推开木箱。', 'consumed'));

    // A consumed opportunity means the input was already handled (or this is
    // an automatic round). Replaying it would re-execute the player's command,
    // and generating a new protagonist action would take the decision away
    // from the player, so the program answers skip and spends no model call.
    expect(result.source).toBe('program');
    expect(result.value).toEqual({ kind: 'skip' });
    expect(result.attempts).toBe(0);
    expect(engine.prompts).toHaveLength(0);
    expect(codes(result)).toContain('protagonist_command_consumed');
    codecAccepts(result);
  });

  it('drops a leading answer label from an action and a reaction', async () => {
    const state = buildTestWorld();
    const actionEngine = new ScriptedEngine([JSON.stringify({ kind: 'act', text: '行动：阿宁把木门拉上，横过门栓。' })]);
    const actionResult = await createActionHandlers({ engine: actionEngine }).action('ally', actInput(state, 'ally', '我盯着门口。'));
    expect(actionResult.value).toEqual({ kind: 'act', text: '阿宁把木门拉上，横过门栓。' });

    const reactionEngine = new ScriptedEngine(['反应：阿宁按住门板，让路明非退到柜台后。']);
    const reactionResult = await createActionHandlers({ engine: reactionEngine }).reaction('hero', reactionInput(state, 'hero', 'ally', '路明非把木门推开，问阿宁还能不能走。'));
    expect(String(reactionResult.value)).toBe('阿宁按住门板，让路明非退到柜台后。');
  });

  it('rewrites a clause-initial first person instead of burning a repair', async () => {
    const state = buildTestWorld();
    // The 13:21Z run answered twice in first person and fell back to a skip.
    // The actor is known, so the subject is a deterministic reference: rewrite
    // it and keep the model's action, with the original recorded in the issue.
    const engine = new ScriptedEngine(['{"kind":"act","text":"我退回门边，把门闩压紧。"}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('ally', actInput(state, 'ally', '我靠在墙边喘口气。'));

    expect(result.attempts).toBe(1);
    expect(codes(result)).not.toContain('action_first_person');
    expect(codes(result)).toContain('first_person_rewritten');
    expect(result.value).toEqual({ kind: 'act', text: '阿宁退回门边，把门闩压紧。' });
    const rewritten = result.issues.find((item) => item.code === 'first_person_rewritten');
    expect(rewritten?.detail).toContain('我退回门边');
    codecAccepts(result);
  });

  it('still rejects a mid-clause first person that means the player', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine([
      '{"kind":"act","text":"老周把我推到门边，自己退开。"}',
      '{"kind":"act","text":"阿宁把门闩压紧，退到门边。"}',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('ally', actInput(state, 'ally', '我靠在墙边喘口气。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('action_first_person');
    expect(result.value).toEqual({ kind: 'act', text: '阿宁把门闩压紧，退到门边。' });
  });

  it('rejects an action that puts an absent character in the scene', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine([
      '{"kind":"act","text":"阿宁把钥匙交给老周。"}',
      '{"kind":"act","text":"阿宁把钥匙收进自己的口袋。"}',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('ally', actInput(state, 'ally', '我靠在墙边喘口气。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('absent_character_in_action');
    expect(result.value).toEqual({ kind: 'act', text: '阿宁把钥匙收进自己的口袋。' });
    codecAccepts(result);
  });

  it('keeps an incidental mention of someone elsewhere as a warning', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"kind":"act","text":"阿宁把老周的名字写在门框上，退开半步。"}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('ally', actInput(state, 'ally', '我靠在墙边喘口气。'));

    expect(result.source).toBe('model');
    expect(result.attempts).toBe(1);
    expect(result.issues.find((item) => item.code === 'absent_character_in_action')?.severity).toBe('warn');
    codecAccepts(result);
  });

  it('rejects a task goal copied as the action', async () => {
    const state = buildTestWorld();
    const goal = state.characters.ally!.tasks.task_ally_watch.goal;
    const engine = new ScriptedEngine([
      JSON.stringify({ kind: 'act', text: goal }),
      '{"kind":"act","text":"阿宁走到门后，把门闩扣上。"}',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('ally', actInput(state, 'ally', '我靠在墙边喘口气。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('action_is_task_goal');
    expect(result.value).toEqual({ kind: 'act', text: '阿宁走到门后，把门闩扣上。' });
    codecAccepts(result);
  });

  it('rejects a paraphrase of the player action, not only a verbatim copy', async () => {
    const state = buildTestWorld();
    // No 8-character contiguous span with the player line: only the
    // in-order coverage check can catch this dropped-subject restatement.
    const engine = new ScriptedEngine([
      '{"kind":"act","text":"把护目镜推上去，看巷口的动静。"}',
      '{"kind":"act","text":"阿宁把对讲机从腰间取下来，换了一块电池。"}',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('ally', actInput(state, 'ally', '我把护目镜推上去，先看巷口的动静。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('npc_repeats_player');
    expect(result.value).toEqual({ kind: 'act', text: '阿宁把对讲机从腰间取下来，换了一块电池。' });
    codecAccepts(result);
  });

  it('recovers from an unparsable answer with the paid evidence kept', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['不是 JSON', '{"kind":"skip"}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('ally', actInput(state, 'ally', '我靠在墙边喘口气。'));

    expect(result.attempts).toBe(2);
    expect(result.calls[0]).toMatchObject({ decoded: false, attempt: 1, raw: '不是 JSON' });
    expect(result.calls[0].error).toMatch(/structured output rejected/);
    expect(codes(result)).toContain('decode_failure');
    expect(result.value).toEqual({ kind: 'skip' });
    codecAccepts(result);
  });
});

describe('targets: anaphora, names, absence and containers', () => {
  it('resolves a pronoun to the only present character through the model', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"ally"}]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('hero', targetsInput(state, 'hero', '我把水壶递给他。'));

    expect(result.source).toBe('model');
    expect(result.value).toEqual({ targets: [{ targetId: 'ally' }] });
    expect(codes(result)).toContain('anaphora_present');
    expect(engine.prompts[0]).toContain('我把水壶递给他。');
    expect(engine.prompts[0]).toContain('指代');
    codecAccepts(result);
  });

  it('maps a target returned by name back to its id', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"阿宁"}]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('hero', targetsInput(state, 'hero', '我抬手拦住阿宁。'));

    expect(result.value).toEqual({ targets: [{ targetId: 'ally' }] });
    expect(result.source).toBe('model');
    codecAccepts(result);
  });

  it('drops an absent target and asks for a repair', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"rival"}]}', '{"targets":[]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('hero', targetsInput(state, 'hero', '我朝书架喊了一声。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('target_absent');
    expect(result.value).toEqual({ targets: [] });
    expect(engine.prompts[1]).toContain('不在本地点');
    codecAccepts(result);
  });

  it('rejects an item named as a target (container, not a person)', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"木箱"}]}', '{"targets":[]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('hero', targetsInput(state, 'hero', '我把木箱推开。'));

    expect(codes(result)).toContain('target_not_character');
    expect(result.value).toEqual({ targets: [] });
    codecAccepts(result);
  });

  it('returns empty targets without a model call when nobody is present', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine([]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('rival', targetsInput(state, 'rival', '我把字条收进袖子里。'));

    expect(result.value).toEqual({ targets: [] });
    expect(result.source).toBe('program');
    expect(codes(result)).toContain('no_visible_candidates');
    expect(engine.prompts).toHaveLength(0);
    codecAccepts(result);
  });

  it('accepts a legal empty target set as a model answer', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"targets":[]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('hero', targetsInput(state, 'hero', '我走到窗边看了一眼。'));

    expect(result.source).toBe('model');
    expect(result.value).toEqual({ targets: [] });
    expect(codes(result)).toContain('empty_targets');
    expect(result.fallback).toBe(false);
    codecAccepts(result);
  });

  it('treats a named absent character as background, not as a target', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"targets":[]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('hero', targetsInput(state, 'hero', '我去书房找老周。'));

    expect(result.value).toEqual({ targets: [] });
    expect(codes(result)).toContain('absent_character_named');
    codecAccepts(result);
  });

  it('caps the declared targets and reports the cap', async () => {
    const state = withPosition(buildTestWorld(), 'servant', { containerId: 'hall', slotId: null, relativeTo: null });
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"ally"},{"targetId":"servant"}]}']);
    const handlers = createActionHandlers({ engine, options: { maxTargets: 1 } });
    const result = await handlers.targets('hero', targetsInput(state, 'hero', '我朝阿宁和小满喊了一声。'));

    expect(result.value).toEqual({ targets: [{ targetId: 'ally' }] });
    expect(codes(result)).toContain('targets_capped');
    codecAccepts(result);
  });

  it('rejects a target the action never names and falls back to an empty set', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"ally"}]}', '{"targets":[{"targetId":"ally"}]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('hero', targetsInput(state, 'hero', '我走向巷子尽头的检修口。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('target_unmentioned');
    expect(codes(result)).toContain('repair_failed');
    expect(result.value).toEqual({ targets: [] });
    expect(result.fallback).toBe(true);
    codecAccepts(result);
  });
});

describe('reaction: causal link, attribution and player agency', () => {
  it('accepts a reaction of the admitted member toward the specific threat', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['阿宁伸手扶住箱角，没让箱盖砸到地上。']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.reaction('hero', reactionInput(state, 'hero', 'ally', '我把木箱推到门边。'));

    expect(result.source).toBe('model');
    expect(result.value).toBe('阿宁伸手扶住箱角，没让箱盖砸到地上。');
    expect(result.attempts).toBe(1);
    expect(engine.prompts[0]).toContain('我把木箱推到门边。');
    expect(engine.prompts[0]).toContain('发起者的行动');
    codecAccepts(result);
  });

  it('repairs a reaction that echoes the source action', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine([
      '我把木箱推到门边，挡住门口。',
      '阿宁侧身让开，伸手把箱沿往里一送。',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.reaction('hero', reactionInput(state, 'hero', 'ally', '我把木箱推到门边挡住门口。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('reaction_echoes_source');
    expect(result.value).toBe('阿宁侧身让开，伸手把箱沿往里一送。');
    codecAccepts(result);
  });

  it('rejects a reaction written as the source acting', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine([
      '路明非把木箱推开了，阿宁看着。',
      '阿宁看着木箱滑到自己面前。',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.reaction('hero', reactionInput(state, 'hero', 'ally', '我把木箱推到门边。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('reaction_acts_for_source');
    expect(result.value).toBe('阿宁看着木箱滑到自己面前。');
    codecAccepts(result);
  });

  it('rejects a reaction that invents a character outside the scene', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine([
      '阿宁冲老周喊了一声。',
      '阿宁抿住嘴，往门边挪了半步。',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.reaction('hero', reactionInput(state, 'hero', 'ally', '我把木箱推到门边。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('reaction_invents_character');
    expect(result.value).toBe('阿宁抿住嘴，往门边挪了半步。');
    codecAccepts(result);
  });

  it('repairs a reaction that is scene description instead of a response', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['窗外的雨声停了。', '阿宁把箱子往门边又推了半寸。']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.reaction('hero', reactionInput(state, 'hero', 'ally', '我把木箱推到门边。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('reaction_off_topic');
    expect(result.value).toBe('阿宁把箱子往门边又推了半寸。');
    codecAccepts(result);
  });

  it('never writes the player character as a reaction', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine([]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.reaction('ally', reactionInput(state, 'ally', 'hero', '阿宁把门闩压紧，回头看了路明非一眼。'));

    expect(result.source).toBe('program');
    expect(result.value).toBe('路明非没有作出反应。');
    expect(codes(result)).toContain('protagonist_reaction_minimal');
    expect(engine.prompts).toHaveLength(0);
    codecAccepts(result);
  });

  it('rejects a reaction that copies the member task goal', async () => {
    const state = buildTestWorld();
    const goal = state.characters.ally!.tasks.task_ally_watch.goal;
    const engine = new ScriptedEngine([
      goal,
      '阿宁把肩膀抵在门板上，侧耳听外头的脚步。',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.reaction('hero', reactionInput(state, 'hero', 'ally', '我把木箱推到门边。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('reaction_goal_copy');
    expect(result.value).toBe('阿宁把肩膀抵在门板上，侧耳听外头的脚步。');
    codecAccepts(result);
  });

  it('falls back to a minimal line after repeated bad reactions', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['我把木箱推到门边挡住门口。', '我把木箱推到门边挡住门口。']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.reaction('hero', reactionInput(state, 'hero', 'ally', '我把木箱推到门边挡住门口。'));

    expect(result.source).toBe('fallback');
    expect(result.fallback).toBe(true);
    expect(result.value).toBe('阿宁的反应慢了半拍。');
    expect(codes(result)).toContain('repair_failed');
    codecAccepts(result);
  });
});

describe('model-port adapter', () => {
  it('serves the three action tasks and refuses to impersonate other tasks', async () => {
    const state = buildTestWorld();
    const engine = new ScriptedEngine(['{"kind":"skip"}']);
    const port = createActionModelPort(engine);
    const value = await port.generate('action', 'ally', actInput(state, 'ally', '我靠在墙边喘口气。'));

    expect(value).toEqual({ kind: 'skip' });
    expect(port.evidence).toHaveLength(1);
    expect(port.evidence[0].task).toBe('action');
    await expect(port.generate('results', 'g1', { workingState: state } as unknown as Json))
      .rejects.toThrow(/unsupported_action_port_task:results/);
  });
});
