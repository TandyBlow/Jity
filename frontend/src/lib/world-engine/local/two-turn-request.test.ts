import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { LocalGameModel } from './game-model';
import { buildInitialState } from './state';
import type { InferenceEngine } from '../runtime/engine';
import type { InitialState, WorldState } from '../types';

/** NARRATION-RAW-OUTPUT-20261111: a later model call must contain only the
 * structured world state and the current input — no previous-turn prose,
 * summary, chat history or implicit continuation. This captures the ACTUAL
 * request the second narration call makes. */
function world(): WorldState {
  const raw = JSON.parse(readFileSync(resolve('public/worlds/dragon-raja-free-day.world.json'), 'utf8'));
  return buildInitialState(raw.initial as InitialState);
}

function point(state: WorldState, id: string, input: string) {
  return { pointId: id, before: state, delta: { timeAdvance: null, entityDeltas: {} }, after: state, playerInput: input };
}

describe('the second narration request carries no previous prose', () => {
  it('does not include the first answer, a summary or chat history', async () => {
    const prompts: string[] = [];
    const answers = [
      '路明非沿着服务巷往里走，先看清墙上的演习规则牌。',
      '诺诺站在巷口，红发用发圈束在脑后。',
    ];
    const narration: InferenceEngine = {
      info: { backend: 'test', modelId: 'capture' },
      load: async () => undefined,
      dispose: async () => undefined,
      async complete(prompt: string) {
        prompts.push(prompt);
        return answers[Math.min(prompts.length - 1, answers.length - 1)];
      },
    };
    const semantic: InferenceEngine = {
      info: { backend: 'test', modelId: 'unused' },
      load: async () => undefined,
      dispose: async () => undefined,
      async complete() { throw new Error('semantic engine must not be called'); },
    };
    const state = world();
    const model = new LocalGameModel(semantic, {
      narrationEngine: narration,
      narrationMode: 'instruct',
      narrationCandidate: 'builtin',
    });
    // The action handler records the current input; narration then reads only
    // the structured state plus that input.
    const asPlayer = (text: string) => ({
      actor: state.protagonistId,
      advance: { inputText: text },
      workingState: state,
    });
    const actionPort = model as unknown as { action?: (key: string, input: unknown) => Promise<unknown> };
    // The private handler is reached through generate('action'), whose output
    // is the action report; its side effect is the recorded player input.
    await model.generate('action', state.protagonistId, asPlayer('我沿着服务巷往里走。') as never).catch(() => undefined);
    await model.generate('narration', 'p1', point(state, 'p1', '我沿着服务巷往里走。') as never);
    await model.generate('action', state.protagonistId, asPlayer('我问诺诺现在的情况。') as never).catch(() => undefined);
    await model.generate('narration', 'p2', point(state, 'p2', '我问诺诺现在的情况。') as never);

    expect(prompts).toHaveLength(2);
    const second = prompts[1];
    // The first answer and its distinctive phrases are absent.
    expect(second).not.toContain(answers[0]);
    expect(second).not.toContain('演习规则牌。');
    // The second prompt is built from the structured state and this input.
    // The player's current sentence is present (as the character's action).
    expect(second).toContain('问诺诺现在的情况');
    expect(second).toContain('路明非');
    // One chat template wrapper for this call (not a transcript of two turns)
    // and no previous-turn section.
    expect(second.split('<|im_start|>user')).toHaveLength(2);
    expect(second.split('<|im_start|>assistant')).toHaveLength(2);
    expect(second).not.toContain('上一回合');
  });
});
