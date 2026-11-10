import { describe, expect, test } from 'vitest';
import type { CommittedNarration, CommittedRead, NarrationFact } from '../../runtime/committed-narration';
import { projectCommittedNarration } from '../../runtime/committed-narration';
import { IncompleteGenerationError, abortError, type CompleteOptions, type CompletionEvidence, type InferenceEngine } from '../../runtime/engine';
import { legacyNarrationInput } from '../prompt';
import { SHORT_STATE } from '../../runtime/b3-short-samples';
import type { WorldState } from '../../types';
import {
  NARRATION_STRATEGY_VERSION, dropDuplicateSentences, generateCommittedNarration, sanitizeNarration,
  type NarrationDisplayState, type NarrationPolicy,
} from './index';
import { planBeats } from './beats';

// ---------------------------------------------------------------------------
// Scripted engine: real interface, canned outputs. Progress is emitted in
// chunks so the streaming contract is exercised, and cancellation/timeout are
// honoured the same way the wllama adapter does.
// ---------------------------------------------------------------------------
type Step =
  | { kind: 'text'; text: string; finishReason?: 'stop' | 'length'; chunkSize?: number }
  | { kind: 'hold' }
  | { kind: 'stream-hold'; prefix: string }
  | { kind: 'throw'; error: Error };

class ScriptedEngine implements InferenceEngine {
  readonly info = { backend: 'scripted', modelId: 'scripted-v1' };
  readonly calls: { prompt: string; options: CompleteOptions }[] = [];
  constructor(private readonly steps: Step[]) {}

  async load(): Promise<void> {}
  async dispose(): Promise<void> {}

  async complete(prompt: string, options: CompleteOptions = {}): Promise<string> {
    const step = this.steps[Math.min(this.calls.length, this.steps.length - 1)];
    this.calls.push({ prompt, options });
    if (step.kind === 'throw') throw step.error;
    if (step.kind === 'hold') {
      await new Promise<void>((_resolve, reject) => {
        const onAbort = () => reject(abortError());
        if (options.signal?.aborted) { onAbort(); return; }
        options.signal?.addEventListener('abort', onAbort, { once: true });
      });
      return '';
    }
    if (step.kind === 'stream-hold') {
      options.onProgress?.({ raw: step.prefix, elapsedMs: 1 });
      await new Promise<void>((_resolve, reject) => {
        const onAbort = () => reject(abortError());
        if (options.signal?.aborted) { onAbort(); return; }
        options.signal?.addEventListener('abort', onAbort, { once: true });
      });
      return '';
    }
    const finishReason = step.finishReason ?? 'stop';
    const size = step.chunkSize ?? Math.max(1, Math.ceil(step.text.length / 4));
    let raw = '';
    for (let index = 0; index < step.text.length; index += size) {
      if (options.signal?.aborted) throw abortError();
      raw += step.text.slice(index, index + size);
      options.onProgress?.({ raw, elapsedMs: 1 });
      await new Promise((resolve) => setTimeout(resolve, 1));
    }
    const completion: CompletionEvidence = { raw, finishReason, firstTokenMs: 1, wallMs: 2 };
    options.onCompletion?.(completion);
    if (finishReason !== 'stop') throw new IncompleteGenerationError(completion);
    return raw;
  }
}

const moved: NarrationFact = {
  id: 'person_a:position', actorId: 'person_a', name: '林川', kind: 'moved',
  fromId: 'corridor', from: '走廊', toId: 'hall', to: '门厅',
};
const povAt: NarrationFact = {
  id: 'person_c:position', actorId: 'person_c', name: '周宁', kind: 'at', locationId: 'corridor', location: '走廊',
};
const povSanity: NarrationFact = { id: 'person_c:sanity', actorId: 'person_c', name: '周宁', kind: 'sanity', value: 10 };

const packet = (...facts: NarrationFact[]): CommittedNarration => ({
  anchor: { worldId: 'world_short', pointId: 'point_1', version: 1, stateDigest: 'digest', previousPointId: 'root' },
  facts,
});

const basePolicy: NarrationPolicy = {
  minChars: 20,
  targetChars: 200,
  roster: ['林川', '周宁'],
  locations: ['走廊', '门厅'],
  viewpoint: { id: 'person_c', name: '周宁' },
};

const ACCEPTED = '门厅那边的灯还亮着。林川从走廊走到门厅，脚步声压得很低。周宁留在走廊，没有跟上去。';

describe('committed narration strategy: fact direction and bounded repair', () => {
  test('a draft that expresses the settled move in the right direction is accepted once', async () => {
    const engine = new ScriptedEngine([{ kind: 'text', text: ACCEPTED }]);
    const states: NarrationDisplayState[] = [];
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt, povSanity), inputText: '【正文】', priorText: null,
      onProgress: (state) => states.push(state), policy: basePolicy,
    });
    expect(result.accepted).toBe(true);
    expect(result.status).toBe('accepted');
    expect(result.text).toBe(ACCEPTED);
    expect(result.strategyVersion).toBe(NARRATION_STRATEGY_VERSION);
    expect(engine.calls).toHaveLength(1);
    expect(engine.calls[0].prompt).toBe('【正文】');
    expect(result.rawAttempts[0].progressEvents).toBeGreaterThan(1);
    expect(result.rawAttempts[0].alignment?.coverage).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'person_a:position', expressed: true }),
    ]));
    // Streaming is provisional, the accepted draft is verified, and the
    // accepted state is never emitted before a stream.
    const firstAccepted = states.findIndex((state) => state.status === 'accepted');
    expect(states.slice(0, firstAccepted).some((state) => state.status === 'streaming' && !state.verified)).toBe(true);
    expect(states[firstAccepted]).toMatchObject({ status: 'accepted', verified: true, text: ACCEPTED });
    expect(result.timings.totalMs).toBeGreaterThanOrEqual(result.timings.attemptsMs);
  });

  test('a reversed move is rejected, the retry prompt carries the committed direction, and the repair is timed end-to-end', async () => {
    const reversed = '林川从门厅回到走廊。周宁留在走廊。';
    const engine = new ScriptedEngine([{ kind: 'text', text: reversed }, { kind: 'text', text: ACCEPTED }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【视角】周宁\n【正文】', priorText: null, policy: basePolicy,
    });
    expect(result.accepted).toBe(true);
    expect(engine.calls).toHaveLength(2);
    expect(result.rawAttempts[0].accepted).toBe(false);
    const kinds = result.rawAttempts[0].issues.map((issue) => issue.kind);
    expect(kinds).toContain('fact_direction_reversed');
    expect(engine.calls[0].prompt).toBe('【视角】周宁\n【正文】');
    // Guidance is inserted before the body marker and quotes only the committed fact.
    expect(engine.calls[1].prompt).toContain('已结算的事实只能这样写：林川从走廊走到门厅。');
    expect(engine.calls[1].prompt.endsWith('【正文】')).toBe(true);
    expect(result.timings.attemptMs).toHaveLength(2);
    expect(result.timings.totalMs).toBeGreaterThanOrEqual(result.timings.attemptsMs);
    expect(result.rawAttempts[0].issues.some((issue) => issue.severity === 'hard')).toBe(true);
    expect(result.rawAttempts[1].issues.filter((issue) => issue.severity === 'hard')).toHaveLength(0);
  });

  test('a missing settled change is a hard omission and the retry is asked for it', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '周宁留在走廊，听着远处的动静。' },
      { kind: 'text', text: ACCEPTED },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null, policy: basePolicy,
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'fact_omitted', severity: 'hard', detail: '林川从走廊走到门厅' }),
    ]));
    expect(engine.calls[1].prompt).toContain('林川从走廊走到门厅');
  });

  test('a rejected pipeline returns the best draft with every issue instead of a fixed answer', async () => {
    const engine = new ScriptedEngine([{ kind: 'text', text: '林川从门厅回到走廊。' }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, maxAttempts: 2 },
    });
    expect(result.accepted).toBe(false);
    expect(result.status).toBe('rejected');
    expect(result.text).toBe('林川从门厅回到走廊。');
    expect(result.issues.some((issue) => issue.kind === 'fact_direction_reversed')).toBe(true);
    expect(result.rawAttempts).toHaveLength(2);
    // No template/fixed narration is invented here.
    expect(result.text).not.toContain('走到门厅。周宁');
  });
});

describe('committed narration strategy: viewpoint, knowledge and names', () => {
  test('non-POV interiority is a perspective leak; POV interiority is allowed', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川心里一沉。林川从走廊走到门厅。周宁留在走廊。' },
      { kind: 'text', text: '林川从走廊走到门厅。周宁留在走廊，心里数着脚步声。' },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null, policy: basePolicy,
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'perspective_leak', severity: 'hard' }),
    ]));
    expect(engine.calls[1].prompt).toContain('只写周宁能看到、能知道的内容');
    const firstKinds = result.rawAttempts[1].issues.map((issue) => issue.kind);
    expect(firstKinds).not.toContain('perspective_leak');
  });

  test('hidden knowledge is rejected and the repair prompt never repeats the secret', async () => {
    const secret = '保险箱的密码是四七一';
    const engine = new ScriptedEngine([
      { kind: 'text', text: `她低声说，${secret}。林川从走廊走到门厅。周宁留在走廊。` },
      { kind: 'text', text: ACCEPTED },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, forbiddenKnowledge: [secret] },
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'knowledge_leak')).toBe(true);
    expect(engine.calls[1].prompt).not.toContain(secret);
  });

  test('a bare numeral in a non-sanity clause is not a sanity error', async () => {
    const engine = new ScriptedEngine([{ kind: 'text', text: '林川从走廊走到门厅。周宁接过来，是一本旧书。' }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt, povSanity), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, minChars: 10 },
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'fact_wrong_number')).toBe(false);
  });

  test('a real sanity value error is still rejected', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '周宁的精神值从十降到八。林川从走廊走到门厅。' },
      { kind: 'text', text: ACCEPTED },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt, povSanity), inputText: '【正文】', priorText: null, policy: basePolicy,
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'fact_wrong_number')).toBe(true);
  });

  test('a committed sanity transition is not mistaken for movement', async () => {
    const sanityChanged: NarrationFact = {
      id: 'person_c:sanity', actorId: 'person_c', name: '周宁', kind: 'sanity_changed', from: 10, to: 8,
    };
    const engine = new ScriptedEngine([{ kind: 'text', text: '周宁的精神值从十降到八。林川从走廊走到门厅。' }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt, sanityChanged), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, minChars: 10 },
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'fact_movement_claimed')).toBe(false);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'fact_wrong_number')).toBe(false);
  });

  test('a negated event verb is not an added event', async () => {
    const engine = new ScriptedEngine([{
      kind: 'text', text: '林川没有推开门，只是从走廊走到门厅。周宁留在走廊。',
    }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, minChars: 10 },
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'fact_event_added')).toBe(false);
  });

  test('a new promise is rejected unless the input or caller licenses it', async () => {
    const text = '林川说：「我答应你，明天把盒子带来。」林川从走廊走到门厅。周宁留在走廊。';
    const engine = new ScriptedEngine([{ kind: 'text', text }, { kind: 'text', text: ACCEPTED }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, minChars: 10 },
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'promise_without_fact')).toBe(true);
    expect(engine.calls[1].prompt).toContain('不要新增输入里没有的承诺');

    const licensed = new ScriptedEngine([{ kind: 'text', text }]);
    const allowed = await generateCommittedNarration({
      engine: licensed, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, minChars: 10, licensedEvents: ['答应'] },
    });
    expect(allowed.accepted).toBe(true);
    expect(allowed.rawAttempts[0].issues.some((issue) => issue.kind === 'promise_without_fact')).toBe(false);
  });

  test('a fabricated past reference is rejected unless it already exists in prior prose', async () => {
    const text = '林川小时候摔过一跤。林川从走廊走到门厅。周宁留在走廊。';
    const engine = new ScriptedEngine([{ kind: 'text', text }, { kind: 'text', text: ACCEPTED }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, minChars: 10 },
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'past_without_fact')).toBe(true);
    expect(engine.calls[1].prompt).toContain('不要补写输入里没有的往事');

    const licensed = new ScriptedEngine([{ kind: 'text', text }]);
    const allowed = await generateCommittedNarration({
      engine: licensed, committed: packet(moved, povAt), inputText: '【正文】',
      priorText: '他小时候摔过一次，谁也没再提。',
      policy: { ...basePolicy, minChars: 10 },
    });
    expect(allowed.accepted).toBe(true);
    expect(allowed.rawAttempts[0].issues.some((issue) => issue.kind === 'past_without_fact')).toBe(false);
  });

  test('a known name absent from the serialized input and facts is unlicensed', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '陆明站在门厅。林川从走廊走到门厅。周宁留在走廊。' },
      { kind: 'text', text: ACCEPTED },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, knownEntities: ['林川', '周宁', '陆明', '走廊', '门厅'] },
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'unlicensed_entity')).toBe(true);
    expect(engine.calls[1].prompt).toContain('只使用输入里出现的人名、地点和物品');
  });
});

describe('committed narration strategy: repetition and length', () => {
  test('the same sentence repeated three times is rejected and the retry asks for new wording', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川从走廊走到门厅。林川从走廊走到门厅。林川从走廊走到门厅。' },
      { kind: 'text', text: ACCEPTED },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, minChars: 10 },
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'loop_repeated_sentence', severity: 'hard' }),
    ]));
    expect(engine.calls[1].prompt).toContain('不要重复上一段或本段已经出现的句子');
  });

  test('echoing the previous accepted narration is rejected', async () => {
    const engine = new ScriptedEngine([{ kind: 'text', text: ACCEPTED }, { kind: 'text', text: ACCEPTED }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: ACCEPTED, policy: basePolicy,
    });
    expect(result.accepted).toBe(false);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'echo_prior')).toBe(true);
    expect(result.rawAttempts[0].metrics?.echoRatio).toBe(1);
  });

  test('short prose that closes the scene early is rejected as premature, not accepted as style', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川从走廊走到门厅。这一夜就这样过去了。' },
      { kind: 'text', text: '林川从走廊走到门厅。这一夜就这样过去了。' },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, minChars: 10, targetChars: 400, maxAttempts: 2 },
    });
    expect(result.accepted).toBe(false);
    expect(result.issues.some((issue) => issue.kind === 'premature_closure')).toBe(true);
    expect(result.status).toBe('rejected');
  });

  test('a length-truncated draft is rejected and the retry raises the token budget', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川从走廊走到门厅', finishReason: 'length' },
      { kind: 'text', text: ACCEPTED },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, minChars: 10, maxTokens: 100, maxTokensCeiling: 600 },
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'truncated')).toBe(true);
    expect(engine.calls[0].options.maxTokens).toBe(100);
    expect(engine.calls[1].options.maxTokens).toBeGreaterThan(100);
    expect(engine.calls[1].prompt).toContain('上一稿被截断');
  });
});

describe('committed narration strategy: time, licensed events and prompt safety', () => {
  test('an elapsed advance must be narrated; zero/instant advances are not required', async () => {
    const time = { boundary: 'elapsed' as const, duration: { amount: 2, unit: 'minute' as const } };
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川从走廊走到门厅。周宁留在走廊。' },
      { kind: 'text', text: '两分钟过去了。林川从走廊走到门厅。周宁留在走廊。' },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, time },
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'time_missing', severity: 'hard' }),
    ]));
    expect(engine.calls[1].prompt).toContain('要写出时间过去了约2分钟');
    expect(result.rawAttempts[1].alignment?.timeExpressed).toBe(true);
  });

  test('an event verb is allowed only when the player action licensed it', async () => {
    const text = '林川推开门，从走廊走到门厅。周宁留在走廊。';
    const licensed = new ScriptedEngine([{ kind: 'text', text }]);
    const allowed = await generateCommittedNarration({
      engine: licensed, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, licensedEvents: ['推开'] },
    });
    expect(allowed.accepted).toBe(true);
    expect(allowed.rawAttempts[0].issues.some((issue) => issue.kind === 'fact_event_added')).toBe(false);

    const unlicensed = new ScriptedEngine([{ kind: 'text', text }, { kind: 'text', text: ACCEPTED }]);
    const rejected = await generateCommittedNarration({
      engine: unlicensed, committed: packet(moved, povAt), inputText: '【正文】', priorText: null, policy: basePolicy,
    });
    expect(rejected.rawAttempts[0].issues.some((issue) => issue.kind === 'fact_event_added')).toBe(true);
  });

  test('copying the task instruction into the prose is a hard prompt echo', async () => {
    const instruction = '请写二百五十字左右的中文小说正文';
    const engine = new ScriptedEngine([
      { kind: 'text', text: '请写二百五十字左右的中文小说正文。林川从走廊走到门厅。周宁留在走廊。' },
      { kind: 'text', text: ACCEPTED },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, instruction },
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'prompt_echo')).toBe(true);
    expect(engine.calls[0].prompt).toContain(instruction);
  });

  test('revise mode shows the previous draft; regenerate mode does not', async () => {
    const reversed = '林川从门厅回到走廊。周宁留在走廊。';
    const reviseEngine = new ScriptedEngine([{ kind: 'text', text: reversed }, { kind: 'text', text: ACCEPTED }]);
    await generateCommittedNarration({
      engine: reviseEngine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, revisionMode: 'revise' },
    });
    expect(reviseEngine.calls[1].prompt).toContain('【上一稿】');
    expect(reviseEngine.calls[1].prompt).toContain(reversed);

    const regenerateEngine = new ScriptedEngine([{ kind: 'text', text: reversed }, { kind: 'text', text: ACCEPTED }]);
    await generateCommittedNarration({
      engine: regenerateEngine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null, policy: basePolicy,
    });
    expect(regenerateEngine.calls[1].prompt).not.toContain('【上一稿】');
  });
});

describe('committed narration strategy: cancellation, timeout and evidence chain', () => {
  test('an external abort stops the engine call, keeps partial evidence and never retries', async () => {
    const engine = new ScriptedEngine([{ kind: 'hold' }]);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10);
    try {
      const result = await generateCommittedNarration({
        engine, committed: packet(moved), inputText: '【正文】', priorText: null,
        signal: controller.signal, policy: basePolicy,
      });
      expect(result.accepted).toBe(false);
      expect(result.status).toBe('cancelled');
      expect(result.text).toBe('');
      expect(engine.calls).toHaveLength(1);
      expect(result.rawAttempts[0].cancelled).toBe(true);
      expect(result.issues.some((issue) => issue.kind === 'cancelled')).toBe(true);
    } finally {
      clearTimeout(timer);
    }
  });

  test('cancellation mid-stream keeps the partial raw text as unverified evidence', async () => {
    const engine = new ScriptedEngine([{ kind: 'stream-hold', prefix: '林川从走廊' }]);
    const controller = new AbortController();
    const states: NarrationDisplayState[] = [];
    const timer = setTimeout(() => controller.abort(), 15);
    try {
      const result = await generateCommittedNarration({
        engine, committed: packet(moved), inputText: '【正文】', priorText: null,
        signal: controller.signal, onProgress: (state) => states.push(state), policy: basePolicy,
      });
      expect(result.accepted).toBe(false);
      expect(result.status).toBe('cancelled');
      expect(result.rawAttempts[0].raw).toBe('林川从走廊');
      expect(result.rawAttempts[0].cancelled).toBe(true);
      expect(result.text).toBe('林川从走廊');
      expect(states.some((state) => state.status === 'streaming' && state.text === '林川从走廊')).toBe(true);
      expect(states.at(-1)?.status).toBe('cancelled');
      expect(states.some((state) => state.status === 'accepted')).toBe(false);
    } finally {
      clearTimeout(timer);
    }
  });

  test('a pre-aborted signal performs no inference at all', async () => {
    const engine = new ScriptedEngine([{ kind: 'text', text: ACCEPTED }]);
    const controller = new AbortController();
    controller.abort();
    const result = await generateCommittedNarration({
      engine, committed: packet(moved), inputText: '【正文】', priorText: null,
      signal: controller.signal, policy: basePolicy,
    });
    expect(engine.calls).toHaveLength(0);
    expect(result.status).toBe('cancelled');
    expect(result.rawAttempts).toHaveLength(0);
    expect(result.issues[0].kind).toBe('cancelled');
  });

  test('the end-to-end deadline interrupts generation and reports a timeout with raw evidence', async () => {
    const engine = new ScriptedEngine([{ kind: 'hold' }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, deadlineMs: 40, timeoutMs: 40 },
    });
    expect(result.accepted).toBe(false);
    expect(result.status).toBe('timeout');
    expect(result.rawAttempts).toHaveLength(1);
    expect(result.rawAttempts[0].timedOut).toBe(true);
    expect(result.timings.deadlineExceeded).toBe(true);
    expect(result.issues.some((issue) => issue.kind === 'timeout')).toBe(true);
    expect(result.timings.totalMs).toBeGreaterThanOrEqual(20);
  });

  test('an engine error is retried once, then reported as an error, not hidden', async () => {
    const engine = new ScriptedEngine([
      { kind: 'throw', error: new Error('wasm exploded') },
      { kind: 'throw', error: new Error('wasm exploded again') },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved), inputText: '【正文】', priorText: null,
      policy: { ...basePolicy, maxAttempts: 2 },
    });
    expect(result.accepted).toBe(false);
    expect(result.status).toBe('error');
    expect(result.rawAttempts).toHaveLength(2);
    expect(result.rawAttempts.every((attempt) => attempt.error?.includes('wasm exploded'))).toBe(true);
    expect(result.issues.some((issue) => issue.kind === 'engine_error')).toBe(true);
  });

  test('evidence chain: prompts, raw text, finish reasons and per-attempt timings survive', async () => {
    const engine = new ScriptedEngine([{ kind: 'text', text: '林川从门厅回到走廊。' }, { kind: 'text', text: ACCEPTED }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(moved, povAt), inputText: '【正文】', priorText: null, policy: basePolicy,
    });
    expect(result.rawAttempts).toHaveLength(2);
    for (const attempt of result.rawAttempts) {
      expect(attempt.promptChars).toBe(attempt.prompt.length);
      expect(attempt.raw.length).toBeGreaterThan(0);
      expect(attempt.finishReason).toBe('stop');
      expect(attempt.durationMs).toBeGreaterThan(0);
      expect(attempt.alignment).not.toBeNull();
    }
    expect(result.rawAttempts[0].prompt).not.toContain('【本次写作要求】');
    expect(result.rawAttempts[1].prompt).toContain('【本次写作要求】');
    expect(result.attemptIndex).toBe(1);
    expect(result.timings.attemptMs).toEqual(result.rawAttempts.map((attempt) => attempt.durationMs));
    expect(result.timings.attemptsMs).toBe(result.timings.attemptMs.reduce((sum, value) => sum + value, 0));
  });
});

describe('committed narration strategy: wiring shape', () => {
  test('the real projector and the injected legacy serializer drive the strategy unchanged', async () => {
    const before: CommittedRead = {
      pointId: 'root', previousPointId: null, version: 0, stateDigest: 'root_digest',
      state: structuredClone(SHORT_STATE) as unknown as WorldState, timeAdvance: null, entityDeltas: {},
    };
    const after = structuredClone(before);
    Object.assign(after, {
      pointId: 'point_1', previousPointId: 'root', version: 1, stateDigest: 'point_digest',
      timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } },
      entityDeltas: { person_c: { entityId: 'person_c', positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } },
    });
    after.state.characters.person_c.position.containerId = 'hall';
    after.state.time = { ...after.state.time, dateTime: '2026-10-27T09:00:01' };
    const committed = projectCommittedNarration(after, before);
    const inputText = legacyNarrationInput(before.state, { timeAdvance: after.timeAdvance, entityDeltas: after.entityDeltas }, after.state, 'person_c');
    expect(inputText.endsWith('【正文】')).toBe(true);

    const engine = new ScriptedEngine([{ kind: 'text', text: '周宁从走廊走到门厅，脚步很轻。林川留在走廊，没有跟上去。' }]);
    const result = await generateCommittedNarration({
      engine, committed, inputText, priorText: null,
      policy: { minChars: 20, roster: ['林川', '周宁'], locations: ['走廊', '门厅'], viewpoint: { id: 'person_c', name: '周宁' } },
    });
    expect(result.accepted).toBe(true);
    expect(engine.calls[0].prompt).toBe(inputText);
    expect(result.ledger.mandatory.map((fact) => fact.id)).toEqual(['person_c:position']);
  });
});

// ---------------------------------------------------------------------------
// Beat mode: one committed thing per model call. The scripted engine answers
// in the same order the beats are planned.
// ---------------------------------------------------------------------------
const sceneContext = {
  location: '走廊',
  placeNotes: ['走廊尽头那盏灯不亮'],
  present: [{ name: '林川' }, { name: '周宁' }],
};
const beatPolicy: NarrationPolicy = {
  ...basePolicy,
  mode: 'beats',
  scene: sceneContext,
  minChars: 20,
  targetChars: 200,
  beatAttempts: 2,
};

describe('trained-shape prompt insertion', () => {
  test('guidance and instruction go before the body marker', async () => {
    const { composeNarrationPrompt } = await import('./prompt');
    const inputText = ['【状态】{}', '【视角】主角视角（周宁）', '【叙事】'].join(String.fromCharCode(10));
    const guidance = ['【本次写作要求】', '要写出时间过去了约2分钟'].join(String.fromCharCode(10));
    const prompt = composeNarrationPrompt({
      inputText, attempt: 1, guidance, previousDraft: null, instruction: null,
    }, {});
    expect(prompt.indexOf('【本次写作要求】')).toBeGreaterThan(prompt.indexOf('【视角】'));
    expect(prompt.endsWith('【叙事】')).toBe(true);
  });
});

describe('beat mode', () => {
  test('writes one beat per committed thing and assembles paragraphs', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '走廊尽头那盏灯不亮。' },
      { kind: 'text', text: '林川从走廊走到门厅，脚步不快。' },
      { kind: 'text', text: '约两分钟过去了。' },
    ]);
    const result = await generateCommittedNarration({
      engine,
      committed: packet(moved, povAt),
      inputText: '【正文】',
      policy: { ...beatPolicy, time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, requireTime: true },
    });
    expect(result.accepted).toBe(true);
    expect(result.status).toBe('accepted');
    expect(result.strategyVersion).toBe(NARRATION_STRATEGY_VERSION);
    expect(result.beats.map((beat) => beat.kind)).toEqual(['scene', 'fact', 'time']);
    expect(result.beats.every((beat) => beat.source === 'model')).toBe(true);
    expect(result.text).toBe([
      '走廊尽头那盏灯不亮。',
      '林川从走廊走到门厅，脚步不快。',
      '约两分钟过去了。',
    ].join('\n\n'));
    expect(engine.calls).toHaveLength(3);
    // Each beat prompt names only its own thing and forbids new material.
    expect(engine.calls[1].prompt).toContain('林川从走廊走到门厅');
    expect(engine.calls[1].prompt).toContain('不新增人物');
    expect(result.timings.totalMs).toBeGreaterThanOrEqual(0);
  });

  test('streams the growing scene after every beat and inside a beat', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川从走廊走到门厅。', chunkSize: 3 },
      { kind: 'text', text: '约两分钟过去了。', chunkSize: 3 },
    ]);
    const states: NarrationDisplayState[] = [];
    const result = await generateCommittedNarration({
      engine,
      committed: packet(moved, povAt),
      inputText: '【正文】',
      onProgress: (state) => states.push(state),
      policy: {
        ...beatPolicy, scene: null, mode: 'beats', minChars: 10,
        time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, requireTime: true,
      },
    });
    const streaming = states.filter((state) => state.status === 'streaming');
    expect(streaming.length).toBeGreaterThan(2);
    expect(streaming.some((state) => state.text.includes('林川从') && !state.text.includes('两分钟'))).toBe(true);
    expect(streaming.at(-1)?.text).toContain('约两分钟过去了');
    expect(result.accepted).toBe(true);
    expect(states.at(-1)?.status).toBe('accepted');
    expect(states.at(-1)?.verified).toBe(true);
  });

  test('repairs one beat instead of regenerating the whole scene', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川从门厅走到走廊。' },
      { kind: 'text', text: '林川从走廊走到门厅，走到一半停了停。' },
    ]);
    const result = await generateCommittedNarration({
      engine,
      committed: packet(moved, povAt),
      inputText: '【正文】',
      policy: { ...beatPolicy, scene: null, mode: 'beats', minChars: 10 },
    });
    expect(result.accepted).toBe(true);
    expect(result.beats[0].source).toBe('model');
    expect(result.beats[0].attempts).toBe(2);
    expect(result.beats[0].issues.some((issue) => issue.kind === 'fact_direction_reversed')).toBe(true);
    expect(engine.calls[1].prompt).toContain('【改写要求】');
    expect(result.text).toBe('林川从走廊走到门厅，走到一半停了停。');
  });

  test('falls back to the committed sentence for a beat that never obeys', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川从门厅走到走廊。' },
      { kind: 'text', text: '林川又从门厅走到走廊。' },
      { kind: 'text', text: '约两分钟过去了。' },
    ]);
    const result = await generateCommittedNarration({
      engine,
      committed: packet(moved, povAt),
      inputText: '【正文】',
      policy: {
        ...beatPolicy, scene: null, mode: 'beats', minChars: 10,
        time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, requireTime: true,
      },
    });
    expect(result.accepted).toBe(true);
    expect(result.beats[0].source).toBe('fallback');
    expect(result.beats[0].text).toBe('林川从走廊走到了门厅。');
    expect(result.text).toContain('林川从走廊走到了门厅。');
  });

  test('a scene written only from committed sentences is reported, not passed', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川从门厅走到走廊。' },
      { kind: 'text', text: '林川又从门厅走到走廊。' },
    ]);
    const result = await generateCommittedNarration({
      engine,
      committed: packet(moved),
      inputText: '【正文】',
      policy: { ...beatPolicy, scene: null, mode: 'beats', minChars: 1 },
    });
    expect(result.accepted).toBe(false);
    expect(result.issues.some((issue) => issue.kind === 'all_beats_fell_back')).toBe(true);
    expect(result.text).toBe('林川从走廊走到了门厅。');
  });

  test('drops a duplicate sentence that repeats an earlier beat', async () => {
    const taskFact: NarrationFact = {
      id: 'person_a:task', actorId: 'person_a', name: '林川', kind: 'task_achieved',
      taskId: 'task_1', goal: '把盒子送回库房',
    };
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川从走廊走到门厅。' },
      { kind: 'text', text: '林川从走廊走到门厅。林川完成了「把盒子送回库房」这件事。' },
    ]);
    const result = await generateCommittedNarration({
      engine,
      committed: packet(moved, taskFact),
      inputText: '【正文】',
      // Echo against the previous beat is allowed here so the assembly-level
      // duplicate removal is what gets exercised.
      policy: { ...beatPolicy, scene: null, mode: 'beats', minChars: 10, maxPriorOverlap: 1 },
    });
    expect(result.assembly.droppedSentences).toEqual(['林川从走廊走到门厅。']);
    expect(result.text.match(/林川从走廊走到门厅。/gu)).toHaveLength(1);
    expect(result.text).toContain('林川完成了「把盒子送回库房」这件事。');
    expect(result.accepted).toBe(true);
  });

  test('a leaked non-POV interior is repaired by the next beat attempt', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川心里一沉，从走廊走到门厅。' },
      { kind: 'text', text: '林川从走廊走到门厅。' },
    ]);
    const result = await generateCommittedNarration({
      engine,
      committed: packet(moved, povAt),
      inputText: '【正文】',
      policy: { ...beatPolicy, scene: null, mode: 'beats', minChars: 10 },
    });
    expect(result.accepted).toBe(true);
    expect(result.beats[0].issues.some((issue) => issue.kind === 'perspective_leak')).toBe(true);
    expect(engine.calls[1].prompt).toContain('只写周宁能看到、能知道的内容');
  });

  test('cancelling mid-beat keeps the beats already written and reports cancelled', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '林川从走廊走到门厅。' },
      { kind: 'stream-hold', prefix: '门厅里' },
    ]);
    const controller = new AbortController();
    let firstBeatWritten!: () => void;
    const wroteFirstBeat = new Promise<void>((resolve) => { firstBeatWritten = resolve; });
    const pending = generateCommittedNarration({
      engine,
      committed: packet(moved, povAt),
      inputText: '【正文】',
      signal: controller.signal,
      onProgress: (state) => {
        if (state.text.includes('林川从走廊走到门厅。')) firstBeatWritten();
      },
      policy: {
        ...beatPolicy, scene: null, mode: 'beats', minChars: 10,
        time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, requireTime: true,
      },
    });
    await wroteFirstBeat;
    controller.abort();
    const result = await pending;
    expect(result.status).toBe('cancelled');
    expect(result.accepted).toBe(false);
    expect(result.text).toContain('林川从走廊走到门厅。');
    // The cancelled beat never started, so no fake evidence row is added.
    expect(result.beats).toHaveLength(1);
    expect(result.beats[0].source).toBe('model');
  });

  test('a non-sanity numeral does not hide an invented event in the same sentence', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '周宁的心跳加速，盒子缓缓打开，里面是一张纸条。' },
      { kind: 'text', text: '林川从走廊走到门厅。' },
    ]);
    const result = await generateCommittedNarration({
      engine,
      committed: packet(moved, povAt),
      inputText: '【正文】',
      policy: { ...beatPolicy, scene: null, mode: 'beats', minChars: 1, beatAttempts: 1 },
    });
    // 一张纸条 reads as sanity 1 to the grader; the false number is dropped,
    // but 打开 must still be reported instead of disappearing with it.
    expect(result.beats[0].issues.some((issue) => issue.kind === 'fact_event_added')).toBe(true);
    expect(result.beats[0].source).toBe('fallback');
  });

  test('the time sentence changes wording when the previous scene already used it', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '她站在原地。' },
      { kind: 'text', text: '光从窗缝里进来。' },
    ]);
    const result = await generateCommittedNarration({
      engine,
      committed: packet(),
      inputText: '【正文】',
      priorText: '灯灭了一会儿。\n\n约两分钟过去了。',
      policy: {
        ...beatPolicy, scene: null, mode: 'beats', minChars: 10,
        time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, requireTime: true,
        beatAttempts: 1,
      },
    });
    expect(result.text).not.toContain('约两分钟过去了。');
    expect(result.text).toMatch(/两分钟/);
    expect(result.issues.some((issue) => issue.kind === 'echo_prior')).toBe(false);
  });

  test('a sanity drop shown through a reaction is not a fact omission', async () => {
    const sanityDrop: NarrationFact = {
      id: 'person_c:sanity_changed', actorId: 'person_c', name: '周宁',
      kind: 'sanity_changed', from: 10, to: 8,
    };
    const engine = new ScriptedEngine([{
      kind: 'text', text: '周宁的呼吸比刚才浅，手指在袖口上停了一会儿。',
    }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(sanityDrop), inputText: '【正文】',
      policy: { ...basePolicy, minChars: 10 },
    });
    expect(result.issues.some((issue) => issue.kind === 'fact_omitted')).toBe(false);
    expect(result.issues.some((issue) => issue.kind === 'unverified_sentence' && issue.severity === 'soft')).toBe(true);
  });

  test('a sanity rise shown with the opposite reaction is still rejected', async () => {
    const sanityDrop: NarrationFact = {
      id: 'person_c:sanity_changed', actorId: 'person_c', name: '周宁',
      kind: 'sanity_changed', from: 10, to: 8,
    };
    const engine = new ScriptedEngine([{
      kind: 'text', text: '周宁的呼吸稳了下来，手指也松开了。',
    }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(sanityDrop), inputText: '【正文】',
      policy: { ...basePolicy, minChars: 10 },
    });
    expect(result.accepted).toBe(false);
    expect(result.issues.some((issue) => issue.kind === 'fact_wrong_number')).toBe(true);
  });

  test('a promise inside a committed personality fact is licensed from the fact itself', async () => {
    const trait: NarrationFact = {
      id: 'person_c:personality', actorId: 'person_c', name: '周宁',
      kind: 'personality_changed', changeId: 'chg_trait', text: '答应替林川查那批旧报纸，只是一直没开口',
    };
    const engine = new ScriptedEngine([{
      kind: 'text', text: '周宁这次点了点头，答应明天去查那批旧报纸。',
    }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(trait), inputText: '【正文】',
      policy: { ...basePolicy, minChars: 10 },
    });
    expect(result.issues.some((issue) => issue.kind === 'promise_without_fact')).toBe(false);
  });

  test('a personality change shown through a changed act is a soft review, not an omission', async () => {
    const trait: NarrationFact = {
      id: 'person_c:personality', actorId: 'person_c', name: '周宁',
      kind: 'personality_changed', changeId: 'chg_trait', text: '答应替林川查那批旧报纸，只是一直没开口',
    };
    const engine = new ScriptedEngine([{
      kind: 'text', text: '周宁这次没有把话推回去，只是点了点头。',
    }]);
    const result = await generateCommittedNarration({
      engine, committed: packet(trait), inputText: '【正文】',
      policy: { ...basePolicy, minChars: 10 },
    });
    expect(result.issues.some((issue) => issue.kind === 'fact_omitted')).toBe(false);
    expect(result.issues.some((issue) => issue.kind === 'unverified_sentence')).toBe(true);
  });

  test('the 1.5B elapsed sample that used to pass is rejected for opening the box', async () => {
    const atLin: NarrationFact = {
      id: 'person_a:at', actorId: 'person_a', name: '林川', kind: 'at',
      locationId: 'hall', location: '门厅',
    };
    const atZhou: NarrationFact = {
      id: 'person_c:at', actorId: 'person_c', name: '周宁', kind: 'at',
      locationId: 'corridor', location: '走廊',
    };
    const text = [
      '光从盒子缝隙中透出，映在走廊的每一面墙壁上。声音是轻柔的铃声，偶尔几下脚步声在走廊尽头渐行渐远。',
      '周宁的手指轻轻触碰盒盖，盒子缓缓开启，映入眼帘的是一块精致的古董，上面雕刻着精美的图案。',
      '约两分钟过去了。',
    ].join(String.fromCharCode(10, 10));
    const engine = new ScriptedEngine([{ kind: 'text', text }]);
    const result = await generateCommittedNarration({
      engine,
      committed: packet(atLin, atZhou),
      inputText: '【正文】',
      policy: {
        ...beatPolicy, scene: null, mode: 'beats', minChars: 1, beatAttempts: 1,
        visibleEntities: ['盒子'],
        time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, requireTime: true,
      },
    });
    expect(result.accepted).toBe(false);
    // The time beat is rejected for opening the box; the final scene is the
    // explicit time fallback, not the model's invention.
    expect(result.beats[0].issues.some((issue) => issue.kind === 'fact_event_added')).toBe(true);
    expect(result.text).not.toContain('盒子缓缓开启');
    expect(result.text).toContain('两分钟');
  });

  test('planBeats orders location before movement and adds a time beat only when required', () => {
    const beats = planBeats({
      committed: packet(moved, povAt),
      ledger: {
        viewpoint: { id: 'person_c', name: '周宁' }, mandatory: [moved, povAt], optional: [],
        actorNames: ['林川', '周宁'], locationNames: ['走廊', '门厅'], licensedEntities: [],
        allowedEvents: [], licensedPromises: [], licensedPastMarkers: [],
        time: null, requireTime: false, forbiddenKnowledge: [],
      },
      policy: {},
      scene: null,
    });
    expect(beats.map((beat) => beat.kind)).toEqual(['fact', 'fact']);
    expect(beats[0].fact?.kind).toBe('at');
    expect(beats[1].fact?.kind).toBe('moved');
    expect(beats.every((beat) => beat.fallback !== 'time-sentence')).toBe(true);
  });

  test('dropDuplicateSentences keeps the first copy inside a paragraph', () => {
    const result = dropDuplicateSentences('他把灯关了。他把灯关了。\n\n风停了。');
    expect(result.dropped).toEqual(['他把灯关了。']);
    expect(result.text).toBe('他把灯关了。\n\n风停了。');
  });
});

describe('sanitizeNarration', () => {
  test('strips wrappers but leaves the prose', () => {
    expect(sanitizeNarration('```\n【正文】\n**走廊**很安静。\n```')).toBe('走廊很安静。');
    expect(sanitizeNarration('正文：他推门进去。')).toBe('他推门进去。');
  });
});
