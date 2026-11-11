import { describe, expect, it } from 'vitest';
import type { InferenceEngine } from '../../runtime/engine';
import type { InitialState, WorldState } from '../../types';
import { buildInitialState } from '../state';
import { LocalGameModel } from '../game-model';

/** The product model's per-point material.
 *
 * The queue test proves the transport/controller overlap with a synthetic
 * model. This one covers the other half: the real `LocalGameModel` must hand a
 * point's own settled text and the player's own sentence to that point's
 * narration, even after a later point has already settled in the same turn.
 */

class ScriptedEngine implements InferenceEngine {
  readonly info = { backend: 'scripted', modelId: 'scripted' };
  readonly prompts: string[] = [];
  private index = 0;
  constructor(private readonly outputs: string[]) {}
  async load(): Promise<void> {}
  async dispose(): Promise<void> {}
  async complete(prompt: string): Promise<string> {
    this.prompts.push(prompt);
    const output = this.outputs[Math.min(this.index++, this.outputs.length - 1)];
    if (output == null) throw new Error('scripted engine has no output');
    return output;
  }
}

function world(): WorldState {
  const initial: InitialState = {
    engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'w_point', protagonistId: 'a',
    initialTime: { calendar: 'gregorian', dateTime: '2026-11-11T12:00:00', instantOrdinal: 0 },
    locations: { room: { id: 'room', name: '房间', parentLocationId: null, initialAppearance: '一间房间。' } },
    items: {},
    characters: {
      a: {
        id: 'a', name: '甲', initialPosition: { containerId: 'room' }, initialAppearance: '站着。',
        initialPersonality: '谨慎。', initialSanity: 60, tasks: {},
      },
      b: {
        id: 'b', name: '乙', initialPosition: { containerId: 'room' }, initialAppearance: '坐着。',
        initialPersonality: '直率。', initialSanity: 55, tasks: {},
      },
    },
  };
  return buildInitialState(initial);
}

const resultsAnswer = (memberId: string, text: string) => JSON.stringify({
  judgments: [{ memberId, label: 'achieved', reason: text, effects: [] }],
  facts: [{ text, memberIds: [memberId], actorId: memberId, action: text, outcome: 'completed' }],
});

describe('per-point narration material', () => {
  it('gives each point its own settled text and keeps the later point out of the earlier prose', async () => {
    const state = world();
    const semantic = new ScriptedEngine([
      resultsAnswer('a', '甲把规则牌看清了。'),
      resultsAnswer('b', '乙把门推开了。'),
    ]);
    const narration = new ScriptedEngine(['第一点正文。', '第二点正文。']);
    const model = new LocalGameModel(semantic, {
      narrationEngine: narration,
      narrationCandidate: 'builtin',
      narrationMode: 'instruct',
    });

    model.beginSubmission('我走到规则牌前。');
    await model.generate('results', 'group_a', {
      groupId: 'group_a', pointId: 'p1', workingState: state,
      members: [{ memberId: 'a', actionText: '我走到规则牌前。', rollRefs: [] }],
    } as never);
    model.onPointCommitted('p1');

    await model.generate('results', 'group_b', {
      groupId: 'group_b', pointId: 'p2', workingState: state,
      members: [{ memberId: 'b', actionText: '乙把门推开。', rollRefs: [] }],
    } as never);
    model.onPointCommitted('p2');

    // p1's narration runs after p2 has settled: it must still see only p1.
    await model.generate('narration', 'p1', {
      pointId: 'p1', before: state, delta: {}, after: state, perspective: 'a',
    } as never);
    const p1Prompt = narration.prompts[0]!;
    // The brief renders the settled fact as '甲：…', so match the distinctive
    // part of the sentence rather than its subject.
    expect(p1Prompt).toContain('规则牌看清了');
    expect(p1Prompt).not.toContain('把门推开了');

    await model.generate('narration', 'p2', {
      pointId: 'p2', before: state, delta: {}, after: state, perspective: 'a',
    } as never);
    expect(narration.prompts[1]).toContain('把门推开了');
  });
});
