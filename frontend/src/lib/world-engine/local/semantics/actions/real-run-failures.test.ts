/** Regression tests built from the FIRST real-model run.
 *
 * The raw completions below are copied verbatim from the real-model archives
 * (Edge + wllama Qwen3-0.6B, 2026-11-10): `run-1-unguarded.json` (first
 * handlers) and `run-5-subject.json` (the "start with the actor name" prompt
 * experiment, which produced two new false accepts). Those runs are evidence
 * of the failures; replaying their exact outputs through a scripted engine
 * proves the current guards reject them. These are not new semantic results —
 * they are the failure corpus that must stay rejected.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import type { InferenceEngine } from '../../../runtime/engine';
import type { Json, WorldState } from '../../../types';
import { buildInitialState } from '../../state';
import { createActionHandlers, type HandlerResult } from './index';

class ScriptedEngine implements InferenceEngine {
  readonly info = { backend: 'scripted', modelId: 'run-1-replay' };
  readonly prompts: string[] = [];
  private readonly replies: string[];
  constructor(replies: string[]) { this.replies = replies; }
  async load(): Promise<void> { /* nothing */ }
  async complete(prompt: string): Promise<string> {
    this.prompts.push(prompt);
    const reply = this.replies.shift();
    if (reply === undefined) throw new Error('run-1 replay ran out of replies');
    return reply;
  }
  async dispose(): Promise<void> { /* nothing */ }
}

const worldFile = fileURLToPath(new URL('../../../../../../public/worlds/dragon-raja-free-day.world.json', import.meta.url));
const world = JSON.parse(readFileSync(worldFile, 'utf8')) as { worldId: string; initial: Parameters<typeof buildInitialState>[0] };
const base = buildInitialState({ ...world.initial, worldId: world.worldId });

function move(state: WorldState, entityId: string, containerId: string): WorldState {
  const next = structuredClone(state);
  const entity = next.characters[entityId] ?? next.items[entityId];
  entity.position = { containerId, slotId: null, relativeTo: null };
  return next;
}

function action(state: WorldState, actor: string, inputText: string, intentStatus = 'pending'): Json {
  return { actor, advance: { inputText, intentStatus }, workingState: state } as unknown as Json;
}
function targets(state: WorldState, sourceId: string, actionText: string): Json {
  return { sourceId, actionText, workingState: state } as unknown as Json;
}
const codes = (result: HandlerResult): string[] => result.issues.map((item) => item.code);

describe('scene-word overlap is not an echo (13:21Z run)', () => {
  it('accepts an action that only reuses registered scene names', async () => {
    // The 13:21Z page run rejected 诺诺's action twice with npc_repeats_player
    // and fell back to a skip. A sentence made of the scene's own names is not
    // the player's sentence; only the predicate overlap can prove an echo.
    const engine = new ScriptedEngine([
      '{"kind":"act","text":"诺诺看演习规则牌，又看西侧服务巷和路明非的护目镜。"}',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('nono', action(base, 'nono', '演习规则牌，西侧服务巷，诺诺，路明非的护目镜。'));

    expect(result.attempts).toBe(1);
    expect(result.fallback).toBe(false);
    expect(result.value).toEqual({ kind: 'act', text: '诺诺看演习规则牌，又看西侧服务巷和路明非的护目镜。' });
    const repeat = result.issues.find((item) => item.code === 'npc_repeats_player');
    expect(repeat?.severity).toBe('warn');
  });

  it('keeps a paraphrased player sentence an error (run-1 A1)', () => {
    // Covered by 'A1: the player action restated without its subject...' above;
    // this asserts the same text still produces an ERROR, not the new warning.
    return (async () => {
      const engine = new ScriptedEngine([
        '{"kind":"act","text":"靠在巷口墙边，确认护目镜是否起雾"}',
        '{"kind":"act","text":"诺诺把故障短讯机举到耳边，试了试信号。"}',
      ]);
      const handlers = createActionHandlers({ engine });
      const result = await handlers.action('nono', action(base, 'nono', '我靠在巷口墙边，先确认护目镜有没有起雾。'));
      expect(result.attempts).toBe(2);
      expect(result.issues.filter((item) => item.code === 'npc_repeats_player' && item.severity === 'error').length).toBeGreaterThan(0);
    })();
  });
});

describe('run-1 failures stay rejected', () => {
  it('A1: the player action restated without its subject is not the NPC action', async () => {
    const engine = new ScriptedEngine([
      '{"kind":"act","text":"靠在巷口墙边，确认护目镜是否起雾"}',
      '{"kind":"act","text":"诺诺把故障短讯机举到耳边，试了试信号。"}',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('nono', action(base, 'nono', '我靠在巷口墙边，先确认护目镜有没有起雾。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('npc_repeats_player');
    expect(result.value).toEqual({ kind: 'act', text: '诺诺把故障短讯机举到耳边，试了试信号。' });
  });

  it('A4b: a copied camera task goal is not an action', async () => {
    const engine = new ScriptedEngine([
      '{"kind":"act","text":"换上相机备用电池，拍到有辨识度的争旗场面"}',
      '{"kind":"act","text":"芬格尔把电池从口袋里摸出来，换上相机。"}',
    ]);
    const handlers = createActionHandlers({ engine, options: { offscreenPolicy: 'judge' } });
    const result = await handlers.action('fingel', action(base, 'fingel', '我靠在巷口墙边喘口气。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('action_is_task_goal');
    expect(result.value).toEqual({ kind: 'act', text: '芬格尔把电池从口袋里摸出来，换上相机。' });
  });

  it('A6: a consumed protagonist opportunity never reaches the model, so no goal can become one', async () => {
    // run-5 produced Nono's/Lu's task goal as the protagonist's next step
    // because the protagonist was still sent to the model after the command
    // was consumed. The product now answers a consumed protagonist slot with
    // a program skip, so the goal string has no path into a player action.
    const engine = new ScriptedEngine([
      '{"kind":"act","text":"向诺诺问清当前红蓝两方局势和自己是否可以保持中立"}',
      '{"kind":"act","text":"路明非把护目镜往上推了推，眯眼看向巷口。"}',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('lu', action(base, 'lu', '我把护目镜推上去，先看巷口的动静。', 'consumed'));

    expect(result.source).toBe('program');
    expect(result.value).toEqual({ kind: 'skip' });
    expect(engine.prompts).toHaveLength(0);
    expect(codes(result)).toContain('protagonist_command_consumed');
  });

  it('A7: a copied squad goal is not an action', async () => {
    const engine = new ScriptedEngine([
      '{"kind":"act","text":"让红方的旗台行动有可执行的掩护，而不把路明非当诱饵"}',
      '{"kind":"act","text":"诺诺抬手指了指钟楼方向，没有接话。"}',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('nono', action(base, 'nono', '楚子航在钟楼吗？'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('action_is_task_goal');
    expect(result.value).toEqual({ kind: 'act', text: '诺诺抬手指了指钟楼方向，没有接话。' });
  });

  // Naming is the model's semantic call: a visible person selected without
  // being named is kept as-is. The three shapes below used to be rejected by
  // the wording rule; the structural checks (unknown, absent, self, duplicate,
  // cap, visibility) still reject what they claim.
  it('T3: a visible bystander selected by the model stays selected; the absent person is still rejected', async () => {
    const present = new ScriptedEngine(['{"targets":[{"targetId":"nono"}]}']);
    const accepted = await createActionHandlers({ engine: present }).targets('lu', targets(base, 'lu', '我去钟楼找楚子航。'));
    expect(codes(accepted)).toContain('absent_character_named');
    expect(accepted.value).toEqual({ targets: [{ targetId: 'nono' }] });
    expect(accepted.source).toBe('model');

    const absent = new ScriptedEngine(['{"targets":[{"targetId":"qin"}]}']);
    const rejected = await createActionHandlers({ engine: absent }).targets('lu', targets(base, 'lu', '我去钟楼找楚子航。'));
    expect(codes(rejected)).toContain('target_absent');
    expect(rejected.value).toEqual({ targets: [] });
  });

  it('T4: handing an item to one present person, with another present person selected, stays the model call', async () => {
    const state = move(move(move(base, 'lu', 'shed'), 'nono', 'shed'), 'qin', 'cage');
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"fingel"}]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('lu', targets(state, 'lu', '我把货架上的备用护目镜拿下来，递给诺诺。'));

    expect(engine.prompts).toHaveLength(1);
    expect(result.value).toEqual({ targets: [{ targetId: 'fingel' }] });
    expect(result.source).toBe('model');
  });

  it('T5: a movement action, with the present bystander selected, keeps the model answer', async () => {
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"nono"}]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('lu', targets(base, 'lu', '我走向巷子尽头的检修口。'));

    expect(result.value).toEqual({ targets: [{ targetId: 'nono' }] });
    expect(result.source).toBe('model');
  });

  it('T5b: an unknown id is still rejected no matter the wording', async () => {
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"nobody"}]}', '{"targets":[]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('lu', targets(base, 'lu', '我走向巷子尽头的检修口。'));
    expect(codes(result)).toContain('target_unknown');
    expect(result.value).toEqual({ targets: [] });
  });
});

describe('run-5 prompt-experiment false accepts stay rejected', () => {
  it('A1: the actor name prefixed onto the player sentence is still an echo', async () => {
    // run-5: the model answered the unnamed-NPC case with the player's own
    // sentence plus a subject. Value-normalized coverage alone missed it.
    const engine = new ScriptedEngine([
      '{"kind":"act","text":"诺诺靠在巷口墙边，确认护目镜是否起雾"}',
      '{"kind":"act","text":"诺诺把故障短讯机举到耳边，试了试信号。"}',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('nono', action(base, 'nono', '我靠在巷口墙边，先确认护目镜有没有起雾。'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('npc_repeats_player');
    expect(result.value).toEqual({ kind: 'act', text: '诺诺把故障短讯机举到耳边，试了试信号。' });
  });

  it('A6: a verbatim goal and a long paraphrase of it are both rejected', async () => {
    // run-5: the model produced Nono's goal as the protagonist's next step.
    // The consumed-protagonist rule above closes the path from a goal string to
    // a player action, and the all-character list still catches a verbatim copy.
    const verbatim = base.characters.nono.tasks
      ? Object.values(base.characters.nono.tasks)[0]!.goal
      : '';
    const rejected = await createActionHandlers({
      engine: new ScriptedEngine([
        JSON.stringify({ kind: 'act', text: verbatim }),
        '{"kind":"act","text":"诺诺抬手指了指钟楼方向，没有接话。"}',
      ]),
    }).action('nono', action(base, 'nono', '楚子航在钟楼吗？'));
    expect(rejected.attempts).toBe(2);
    expect(codes(rejected)).toContain('action_is_task_goal');

    // The broad subsequence branch is back (the 20ee comparison showed the
    // remaining real rejections were exact copies, so removing it reduced
    // nothing). A long paraphrase is caught again, as it was before the trial.
    const paraphrase = await createActionHandlers({
      engine: new ScriptedEngine([
        '{"kind":"act","text":"诺诺问清路明非的参赛意愿并说明三条接近钟楼的路线"}',
        '{"kind":"act","text":"诺诺抬手指了指钟楼方向，没有接话。"}',
      ]),
    }).action('nono', action(base, 'nono', '楚子航在钟楼吗？'));
    expect(paraphrase.attempts).toBe(2);
    expect(codes(paraphrase)).toContain('action_is_task_goal');
  });
});
