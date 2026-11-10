/** Regression tests built from the FIRST real-model run.
 *
 * The raw completions below are copied verbatim from
 * `artifacts/action-eval/run-1-unguarded.json` (Edge + wllama Qwen3-0.6B,
 * 2026-11-10). That run is evidence of the failures; replaying its exact
 * outputs through a scripted engine proves the current guards reject them.
 * These are not new semantic results — they are the failure corpus that must
 * stay rejected.
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

  it('A6: the protagonist task goal is not a continuation', async () => {
    const engine = new ScriptedEngine([
      '{"kind":"act","text":"向诺诺问清当前红蓝两方局势和自己是否可以保持中立"}',
      '{"kind":"act","text":"路明非把护目镜往上推了推，眯眼看向巷口。"}',
    ]);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.action('lu', action(base, 'lu', '我把护目镜推上去，先看巷口的动静。', 'consumed'));

    expect(result.attempts).toBe(2);
    expect(codes(result)).toContain('action_is_task_goal');
    expect(result.value).toEqual({ kind: 'act', text: '路明非把护目镜往上推了推，眯眼看向巷口。' });
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

  it('T3: moving to an absent person does not make the present bystander a target', async () => {
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"nono"}]}', '{"targets":[{"targetId":"nono"}]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('lu', targets(base, 'lu', '我去钟楼找楚子航。'));

    expect(codes(result)).toContain('target_unmentioned');
    expect(codes(result)).toContain('absent_character_named');
    expect(result.value).toEqual({ targets: [] });
    expect(result.fallback).toBe(true);
  });

  it('T4: handing an item to one present person does not target a bystander', async () => {
    const state = move(move(move(base, 'lu', 'shed'), 'nono', 'shed'), 'qin', 'cage');
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"fingel"}]}', '{"targets":[{"targetId":"fingel"}]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('lu', targets(state, 'lu', '我把货架上的备用护目镜拿下来，递给诺诺。'));

    expect(codes(result)).toContain('target_unmentioned');
    expect(result.value).toEqual({ targets: [] });
    expect(result.fallback).toBe(true);
  });

  it('T5: a movement action does not make the present bystander a target', async () => {
    const engine = new ScriptedEngine(['{"targets":[{"targetId":"nono"}]}', '{"targets":[{"targetId":"nono"}]}']);
    const handlers = createActionHandlers({ engine });
    const result = await handlers.targets('lu', targets(base, 'lu', '我走向巷子尽头的检修口。'));

    expect(codes(result)).toContain('target_unmentioned');
    expect(result.value).toEqual({ targets: [] });
    expect(result.fallback).toBe(true);
  });
});
