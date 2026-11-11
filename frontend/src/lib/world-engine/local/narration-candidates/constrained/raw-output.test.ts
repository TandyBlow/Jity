import { describe, expect, it } from 'vitest';
import { generateCandidate } from './index';
import type { BeatDirective, SceneSkeleton } from './types';
import type { InferenceEngine } from '../../../runtime/engine';

/** The runtime shows non-empty model prose exactly as returned
 * (NARRATION-RAW-OUTPUT-20261111). These are pipeline tests: the fixed answers
 * below used to trigger length, name, person, punctuation or repetition checks;
 * none of them may now change the text or cause an extra call. */
function scene(): SceneSkeleton {
  return {
    anchor: { worldId: 'w', pointId: 'p', version: 1, stateDigest: 'd', previousPointId: 'root' },
    viewpoint: { id: 'lu', name: '路明非', locationId: 'lane', location: '服务巷', note: '', personality: '', sanity: 43 },
    time: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
    place: { id: 'lane', name: '服务巷', note: '墙上有演习规则牌', parentName: null },
    present: [{ id: 'nono', name: '诺诺', note: '红发用发圈束在脑后', viewpoint: false }],
    objects: [],
    facts: [],
    licensed: { names: ['路明非', '诺诺'], locations: ['服务巷'], items: [], details: [], quotes: [] },
    knowledge: { discoveredItemIds: [], visitedLocationIds: [], metCharacterIds: [] },
    inputText: null,
    previousAction: '我沿着服务巷往里走，先看清墙上的演习规则牌。',
    resultsText: null,
    worldNames: { characters: ['路明非', '诺诺'], locations: ['服务巷', '钟楼'], items: [] },
    hasSceneMaterial: true,
    timeOnly: false,
  };
}

function packet() {
  return {
    anchor: scene().anchor,
    facts: [
      { id: 'f_at', kind: 'at' as const, actorId: 'lu', name: '路明非', locationId: 'lane', location: '服务巷' },
      { id: 'f_nono', kind: 'at' as const, actorId: 'nono', name: '诺诺', locationId: 'lane', location: '服务巷' },
      {
        id: 'f_res', kind: 'result' as const, name: '路明非',
        text: '路明非看清了墙上的演习规则牌',
        structured: { actor: '路明非', action: '看清演习规则牌', target: null, outcome: 'completed' as const },
      },
    ],
    timeAdvance: { boundary: 'elapsed' as const, duration: { amount: 1, unit: 'minute' as const } },
    state: undefined,
  };
}

function engineWith(answer: string, calls: { count: number }): InferenceEngine {
  return {
    info: { backend: 'test', modelId: 'fixed' },
    load: async () => undefined,
    dispose: async () => undefined,
    async complete(prompt: string) {
      calls.count += 1;
      // A beat prompt ends with the body marker; the model "writes" the answer.
      return prompt.includes('正文') ? answer : answer;
    },
  };
}

async function run(answer: string) {
  const calls = { count: 0 };
  const result = await generateCandidate({
    engine: engineWith(answer, calls),
    committed: packet() as never,
    inputText: '路明非在服务巷。',
    policy: { mode: 'model', minChars: 18, model: { maxAttempts: 1, maxTokensPerBeat: 200 } },
  });
  return { result, calls };
}

describe('non-empty model text is displayed verbatim', () => {
  it.each([
    ['short', '他站着。'],
    ['offscreen name', '路明非朝钟楼走去，西门那边没有人。'],
    ['first person', '我沿着服务巷往里走。'],
    ['no final punctuation', '路明非站在服务巷里看着演习规则牌'],
    ['repeated sentence', '路明非站在服务巷。路明非站在服务巷。'],
    ['field dump', '时间：一分钟。地点：服务巷。人物：路明非。'],
  ])('%s text survives unchanged', async (_label, answer) => {
    const { result, calls } = await run(answer);
    // Every text the model wrote appears, in plan order, unedited.
    const beatCount = result.plan?.beats.length ?? 0;
    expect(calls.count).toBe(beatCount);
    if (result.segments.length > 0) {
      expect(result.text).toContain(answer);
      for (const segment of result.segments) expect(answer).toContain(segment.text);
    } else {
      // The beat gate may have planned zero beats for an empty fact set; then
      // no call was made and the answer never had a beat to land in.
      expect(beatCount).toBe(0);
    }
  });

  it('whitespace-only output is empty, not prose', async () => {
    const { result } = await run('  \n\n  ');
    expect(result.text.trim()).toBe('');
    expect(result.status).not.toBe('accepted');
  });

  it('never makes a second call because of the text', async () => {
    const { result, calls } = await run('胡说八道，完全无关。');
    expect(calls.count).toBe(planCount(result.plan?.beats ?? []));
  });
});

function planCount(beats: BeatDirective[]): number {
  return beats.length;
}
