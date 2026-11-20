import { describe, expect, it } from 'vitest';
import type { InferenceEngine } from '../runtime/engine';
import type { Json } from '../types';
import { LocalGameModel, type GameModelOptions } from './game-model';
import { tinyWorld } from './narration-input/test-fixtures';

describe('action evidence at the product callback', () => {
  it('retains the rejected goal, full first output and successful repair separately', async () => {
    const state = tinyWorld();
    const goal = state.characters.friend.tasks.friend_root.goal;
    const rejected = JSON.stringify({ kind: 'act', text: goal });
    const repaired = JSON.stringify({ kind: 'skip' });
    const replies = [rejected, repaired];
    const engine: InferenceEngine = {
      info: { backend: 'scripted', modelId: 'action-evidence-test' },
      load: async () => undefined,
      dispose: async () => undefined,
      complete: async () => replies.shift()!,
    };
    type Detail = Parameters<NonNullable<GameModelOptions['onTask']>>[2];
    const records: Detail[] = [];
    const model = new LocalGameModel(engine, { onTask: (task, _key, detail) => {
      if (task === 'action') records.push(detail);
    } });
    await model.generate('action', 'friend', { workingState: state } as unknown as Json);
    const result = records.find((record) => record.source === 'model');
    expect(result).toBeDefined();
    expect(result!.value).toEqual({ kind: 'skip' });
    expect(result!.raw).toBe(repaired);
    expect(result!.calls!.map((call) => call.raw)).toEqual([rejected, repaired]);
    expect(result!.issues).toContainEqual(expect.objectContaining({
      code: 'action_is_task_goal', severity: 'error', detail: goal,
      message: expect.stringContaining(goal),
    }));
    // Per-attempt callbacks are not extra character decisions.
    expect(records.filter((record) => record.source !== undefined)).toHaveLength(1);
  });
});
