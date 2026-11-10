import { describe, expect, test } from 'vitest';
import type { CommittedNarration } from '../../../runtime/committed-narration';
import type { CompleteOptions } from '../../../runtime/engine';
import { MODEL_CATALOG, DEFAULT_MODEL_ID, modelSpec, modelSpecByFile } from './catalog';
import { generateCandidate } from './candidate';
import { mergePositions, projectProseFacts } from './facts';
import {
  ThinkingFilter, buildMessages, cleanNarration, normalizeTime, renderFallbackPrompt, renderNarrationUser, stripThinking,
} from './template';
import type { CandidateArgs, ChatCapableEngine } from './types';

const ANCHOR = { worldId: 'world_a', pointId: 'p1', version: 1, stateDigest: 'f'.repeat(64), previousPointId: 'root' };

function movePacket(): CommittedNarration {
  return {
    anchor: ANCHOR,
    facts: [{ id: 'a:position', actorId: 'char_lin', name: '林川', kind: 'moved', fromId: 'corridor', from: '走廊', toId: 'hall', to: '门厅' }],
  };
}

const SPEC = modelSpec('qwen2.5-1.5b-instruct-q4km');

/** Records what the candidate asked the engine to do and streams a fixed
 * answer in chunks. `rounds` picks the chunk list per call, so a test can
 * script a first bad attempt and a repaired second one. */
function fakeEngine(rounds: string[][] | string[], options: { chat?: boolean } = {}) {
  const scripted: string[][] = Array.isArray(rounds[0]) ? (rounds as string[][]) : [rounds as string[]];
  const calls: { messages?: { role: string; content: string }[]; prompt?: string; options?: CompleteOptions }[] = [];
  let round = 0;
  const next = () => scripted[Math.min(round++, scripted.length - 1)]!;
  const run = (chunks: string[], callOptions?: CompleteOptions) => {
    let built = '';
    for (const piece of chunks) {
      built += piece;
      callOptions?.onProgress?.({ raw: built, elapsedMs: 1 });
    }
    callOptions?.onCompletion?.({ raw: built, finishReason: 'stop', firstTokenMs: 5, wallMs: 10 });
    return built;
  };
  const engine: ChatCapableEngine = {
    info: { backend: 'fake', modelId: 'fake' },
    load: async () => undefined,
    dispose: async () => undefined,
    complete: async (prompt, callOptions) => {
      calls.push({ prompt, options: callOptions });
      return run(next(), callOptions);
    },
  };
  if (options.chat !== false) {
    (engine as ChatCapableEngine & { chat: NonNullable<ChatCapableEngine['chat']> }).chat = async (messages, callOptions) => {
      calls.push({ messages, options: callOptions });
      return run(next(), callOptions);
    };
  }
  return { engine, calls };
}

function args(overrides: Partial<CandidateArgs> = {}): CandidateArgs {
  return {
    engine: fakeEngine(['林川从走廊走进门厅。']).engine,
    committed: movePacket(),
    inputText: '【视角】周宁。林川在走廊。',
    policy: {
      viewpoint: { id: 'char_zhou', name: '周宁' },
      roster: ['林川', '周宁'],
      locations: ['走廊', '门厅'],
      time: { amount: 2, unit: 'minute' },
      minChars: 10,
      targetChars: 120,
      temperature: 0.7,
      seed: 42,
    },
    ...overrides,
  };
}

const VERIFIED_TEXT = '两分钟里，林川从走廊走到门厅，脚步不急。';

describe('prose projection', () => {
  const packet: CommittedNarration = {
    anchor: ANCHOR,
    facts: [
      { id: 'a:position', actorId: 'char_lin', name: '林川', kind: 'moved', fromId: 'corridor', from: '走廊', toId: 'hall', to: '门厅' },
      { id: 'b:position', actorId: 'char_zhou', name: '周宁', kind: 'at', locationId: 'corridor', location: '走廊' },
      { id: 'b:sanity', actorId: 'char_zhou', name: '周宁', kind: 'sanity_changed', from: 10, to: 8 },
    ],
  };

  test('movement stays required, standing position becomes scene, sanity becomes a hint', () => {
    const projected = projectProseFacts(packet);
    expect(projected.packet.facts.map((fact) => fact.kind)).toEqual(['moved']);
    expect(projected.positions).toEqual([{ name: '周宁', location: '走廊' }]);
    expect(projected.hints).toHaveLength(1);
    expect(projected.hints[0]).not.toMatch(/8|10/);
    expect(projected.withheld.map((fact) => fact.kind)).toEqual(['at', 'sanity_changed']);
  });

  test('the rendered prompt never lists a stat number and forbids unlisted actions', () => {
    const text = renderNarrationUser(packet, '', { time: { amount: 2, unit: 'minute' }, targetChars: 240 });
    expect(text).not.toContain('精神值');
    expect(text).not.toMatch(/精神.{0,6}\d/);
    expect(text).toContain('周宁在走廊');
    expect(text).toContain('不许新增没有列出的动作' .replace('不许', '不要'));
    expect(text).toContain('写成 3 段');
  });

  test('caller positions win over the packet and are not duplicated', () => {
    expect(mergePositions([{ name: '周宁', location: '门厅' }], [{ name: '周宁', location: '走廊' }, { name: '林川', location: '门厅' }]))
      .toEqual([{ name: '周宁', location: '门厅' }, { name: '林川', location: '门厅' }]);
  });
});

describe('model catalog', () => {
  test('every entry carries identity, a template and a real hash', () => {
    expect(MODEL_CATALOG.length).toBeGreaterThanOrEqual(4);
    for (const spec of MODEL_CATALOG) {
      expect(spec.gguf).toMatch(/\.gguf$/);
      expect(spec.sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(spec.bytes).toBeGreaterThan(100_000_000);
      expect(spec.template.id.length).toBeGreaterThan(3);
      expect(spec.recommended.contextSize).toBeGreaterThanOrEqual(2048);
    }
    expect(DEFAULT_MODEL_ID).toBe('qwen2.5-1.5b-instruct-q4km');
    expect(modelSpec('qwen3-1.7b-q4km').thinking).toBe('hybrid');
    expect(modelSpec('qwen3-4b-instruct-2507-q4km').thinking).toBe('none');
    expect(modelSpecByFile('D:/models/Qwen3-1.7B-Q4_K_M.gguf').id).toBe('qwen3-1.7b-q4km');
    expect(() => modelSpec('nope')).toThrow(/unknown candidate model/);
  });
});

describe('prompt rendering', () => {
  test('the user turn carries the committed fact, elapsed time and scene without copying raw state', () => {
    const text = renderNarrationUser(movePacket(), '【状态】原始投影串', {
      viewpoint: { id: 'char_zhou', name: '周宁' },
      scene: { location: '门厅', placeNotes: ['地砖很亮。'], present: [{ name: '林川', note: '穿灰衣' }], objects: [{ name: '盒子' }] },
      time: { amount: 2, unit: 'minute' },
      knownPositions: [{ name: '周宁', location: '走廊' }],
      knownEntities: ['林川', '周宁', '门厅'],
      targetChars: 240,
      minChars: 120,
    });
    expect(text).toContain('视角人物：周宁');
    expect(text).toContain('场景：门厅。地砖很亮。');
    expect(text).toContain('在场人物：林川（穿灰衣）');
    expect(text).toContain('- 林川从走廊移动到门厅。');
    expect(text).toContain('本回合经过的时间：2分钟。');
    expect(text).toContain('- 周宁在走廊。');
    expect(text).toContain('可用专名：林川、周宁、门厅');
    expect(text).toContain('120～240 字');
    // The raw serializer string is not fed to the prose by default (it makes
    // instruct models copy field labels); it stays available on request.
    expect(text).not.toContain('本点输入资料');
    expect(text).not.toContain('【状态】原始投影串');
    const withInput = renderNarrationUser(movePacket(), '【状态】原始投影串', { includeInputText: true });
    expect(withInput).toContain('本点输入资料');
    expect(withInput.indexOf('【状态】原始投影串')).toBeGreaterThan(withInput.indexOf('这一小段时间里发生的事'));
  });

  test('an empty delta explicitly forbids inventing changes', () => {
    const text = renderNarrationUser({ anchor: ANCHOR, facts: [] }, '', { time: { amount: 5, unit: 'minute' } });
    expect(text).toContain('这一小段时间里没有实体变化');
    expect(text).toContain('不要写任何移动、任务达成或新的动作');
    expect(text).toContain('5分钟');
  });

  test('a chat spec sends a system + user message; a legacy engine gets a labelled prompt', () => {
    const messages = buildMessages(SPEC, 'USER');
    expect(messages[0]!.role).toBe('system');
    expect(messages[0]!.content).toContain('不要列点');
    expect(messages[1]).toEqual({ role: 'user', content: 'USER' });
    const prompt = renderFallbackPrompt(SPEC, 'USER');
    expect(prompt).toContain('不要列点');
    expect(prompt.endsWith('USER')).toBe(true);
  });
});

const OPEN_THINK = '<' + 'think>';
const CLOSE_THINK = '</' + 'think>';

describe('thinking handling', () => {
  test('complete answers drop a closed or unclosed think block', () => {
    expect(stripThinking(OPEN_THINK + '思考很久' + CLOSE_THINK + '\n答：正文。')).toBe('答：正文。');
    expect(stripThinking(OPEN_THINK + '思考没有结束')).toBe('');
    expect(stripThinking('正文直接开始。')).toBe('正文直接开始。');
  });

  test('the streaming filter never emits think text, even across chunk splits', () => {
    const filter = new ThinkingFilter();
    const out = [
      filter.push(OPEN_THINK.slice(0, 4)), filter.push(OPEN_THINK.slice(4) + 'internal reasoning'),
      filter.push(' more'),
      filter.push(CLOSE_THINK.slice(0, 5)), filter.push(CLOSE_THINK.slice(5) + '\n正'),
      filter.push('文。'),
    ].join('');
    expect(out).toBe('\n正文。');
    expect(filter.push('')).toBe('');
    expect(filter.flush()).toBe('');
    expect(filter.text).toBe('\n正文。');
  });

  test('the filter holds a partial opening tag at the end instead of leaking it', () => {
    const filter = new ThinkingFilter();
    expect(filter.push('好的<')).toBe('好的');
    expect(filter.push('think>')).toBe('');
    expect(filter.push('想')).toBe('');
    expect(filter.push(CLOSE_THINK + '正文')).toBe('正文');
  });

  test('cleanNarration removes fences, role labels and chat markers', () => {
    expect(cleanNarration('```\n正文：他走进门厅。\n```')).toBe('他走进门厅。');
    expect(cleanNarration('正文：他走进门厅。<|im_end|>')).toBe('他走进门厅。');
  });
});

describe('generateCandidate', () => {
  test('streams real chunks, reports timings, and accepts a fact-aligned scene', async () => {
    const { engine, calls } = fakeEngine(['两分钟', '里，林川从走廊走到门厅', '，脚步不急。']);
    const seen: { status: string; verified: boolean; text: string }[] = [];
    const result = await generateCandidate({
      ...args({ engine }),
      onProgress: (progress) => seen.push({ status: progress.status, verified: progress.verified, text: progress.text }),
    }, { spec: SPEC });
    expect(result.accepted).toBe(true);
    expect(result.text).toBe(VERIFIED_TEXT);
    expect(result.issues.filter((issue) => issue.severity === 'hard')).toHaveLength(0);
    expect(result.verification?.coverage[0]?.expressed).toBe(true);
    expect(result.verification?.timeExpressed).toBe(true);
    // A chat-capable engine with a chat spec got messages, not a pasted template.
    expect(calls[0]!.messages?.[0]!.role).toBe('system');
    expect(calls[0]!.messages?.[1]!.content).toContain('林川从走廊移动到门厅');
    expect(calls[0]!.options).toMatchObject({ maxTokens: 192, temperature: 0.7, seed: 42 });
    expect(result.timings.calls).toBe(1);
    expect(result.timings.firstReadableMs).not.toBeNull();
    expect(seen[0]!.status).toBe('streaming');
    expect(seen.at(-1)).toMatchObject({ status: 'done', verified: true });
  });

  test('an engine without chat() gets the combined prompt and still works', async () => {
    const { engine, calls } = fakeEngine([VERIFIED_TEXT], { chat: false });
    const result = await generateCandidate(args({ engine }), { spec: SPEC });
    expect(result.accepted).toBe(true);
    expect(calls[0]!.prompt).toContain('不要列点');
    expect(calls[0]!.prompt).toContain('林川从走廊移动到门厅');
    expect(calls[0]!.messages).toBeUndefined();
  });

  test('a fact-wrong first attempt is retried with the exact repair note, then accepted', async () => {
    const { engine, calls } = fakeEngine([
      ['林川从门厅走回走廊，花了两分钟。'],
      [VERIFIED_TEXT],
    ]);
    const result = await generateCandidate(args({ engine }), { spec: SPEC });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts).toHaveLength(2);
    expect(result.rawAttempts[0]!.verification?.violations.map((violation) => violation.kind)).toContain('direction_reversed');
    const repairPrompt = result.rawAttempts[1]!.prompt;
    expect(repairPrompt).toContain('方向写反了');
    expect(result.timings.calls).toBe(2);
    expect(result.rawAttempts[1]!.temperature).toBeLessThan(result.rawAttempts[0]!.temperature);
    expect(calls).toHaveLength(2);
  });

  test('two failing attempts return the draft with accepted:false and hard issues, never a fabricated template', async () => {
    const { engine } = fakeEngine([
      ['走廊里安静了下来，没有任何人经过。'],
      ['门厅的灯还亮着，没有人说话。'],
    ]);
    const result = await generateCandidate(args({ engine }), { spec: SPEC });
    expect(result.accepted).toBe(false);
    const hard = result.issues.filter((issue) => issue.severity === 'hard').map((issue) => issue.kind);
    expect(hard).toContain('omitted_fact');
    expect(hard).toContain('time_not_narrated');
    // The draft stays the model's own text; the candidate never substitutes prose.
    expect(result.text).toContain('走廊里安静了下来');
    expect(result.model).toEqual({ id: SPEC.id, templateId: SPEC.template.id });
  });

  test('accepts a settled TimeAdvance (09 driver shape) and states the duration', async () => {
    const packet = movePacket();
    const timeAdvance = { kind: 'advance' as const, duration: { amount: 2, unit: 'minute' as const } };
    const text = renderNarrationUser(packet, '', { time: timeAdvance });
    expect(text).toContain('本回合经过的时间：2分钟');
    expect(text).not.toContain('[object Object]');
    expect(normalizeTime(timeAdvance)).toEqual({ amount: 2, unit: 'minute' });
    expect(normalizeTime({ amount: 3, unit: 'second' })).toEqual({ amount: 3, unit: 'second' });
    expect(normalizeTime(null)).toBeNull();
  });

  test('a length-capped answer is kept as a non-accepted draft and retried shorter', async () => {
    const { IncompleteGenerationError } = await import('../../../runtime/engine');
    let round = 0;
    const engine: ChatCapableEngine = {
      info: { backend: 'fake', modelId: 'fake' },
      load: async () => undefined,
      dispose: async () => undefined,
      complete: async () => { throw new Error('unused'); },
      chat: async (_messages, options) => {
        round += 1;
        if (round === 1) {
          options?.onProgress?.({ raw: '两分钟里，林川从走廊走到', elapsedMs: 1 });
          throw new IncompleteGenerationError({
            raw: '两分钟里，林川从走廊走到', finishReason: 'length', firstTokenMs: 5, wallMs: 10,
          });
        }
        options?.onProgress?.({ raw: VERIFIED_TEXT, elapsedMs: 1 });
        return VERIFIED_TEXT;
      },
    };
    const result = await generateCandidate(args({ engine }), { spec: SPEC });
    expect(result.rawAttempts).toHaveLength(2);
    expect(result.rawAttempts[0]!.text).toContain('林川从走廊走到');
    expect(result.rawAttempts[0]!.issueKinds).toContain('truncated');
    expect(result.rawAttempts[0]!.accepted).toBe(false);
    expect(result.rawAttempts[1]!.prompt).toContain('被截断');
    expect(result.accepted).toBe(true);
  });

  test('an engine deadline is terminal: no second call into a stopped worker', async () => {
    const { IncompleteGenerationError } = await import('../../../runtime/engine');
    let calls = 0;
    const engine: ChatCapableEngine = {
      info: { backend: 'fake', modelId: 'fake' },
      load: async () => undefined,
      dispose: async () => undefined,
      complete: async () => { throw new Error('unused'); },
      chat: async (_messages, options) => {
        calls += 1;
        options?.onProgress?.({ raw: '两分钟里，林川从走廊', elapsedMs: 1 });
        throw new IncompleteGenerationError({
          raw: '两分钟里，林川从走廊', finishReason: 'timeout', firstTokenMs: 5, wallMs: 10,
        });
      },
    };
    const result = await generateCandidate(args({ engine }), { spec: SPEC });
    expect(calls).toBe(1);
    expect(result.status).toBe('timeout');
    expect(result.accepted).toBe(false);
    expect(result.rawAttempts[0]!.issueKinds).toContain('timeout');
    expect(result.text).toContain('林川从走廊');
    expect(result.timings.calls).toBe(1);
  });

  test('a dead engine returns an error result instead of throwing the point away', async () => {
    let calls = 0;
    const engine: ChatCapableEngine = {
      info: { backend: 'fake', modelId: 'fake' },
      load: async () => undefined,
      dispose: async () => undefined,
      complete: async () => { throw new Error('unused'); },
      chat: async () => { calls += 1; throw new Error('wllama engine is not loaded'); },
    };
    const result = await generateCandidate(args({ engine }), { spec: SPEC });
    expect(calls).toBe(1);
    expect(result.status).toBe('error');
    expect(result.accepted).toBe(false);
    expect(result.rawAttempts).toHaveLength(1);
    expect(result.rawAttempts[0]!.issueKinds).toContain('generation_failed');
    expect(result.issues.some((issue) => issue.kind === 'generation_failed')).toBe(true);
    expect(result.text).toBe('');
  });

  test('a model that aborts does not get turned into an accepted scene', async () => {
    const controller = new AbortController();
    const { engine } = fakeEngine([VERIFIED_TEXT]);
    const aborting: ChatCapableEngine = {
      ...engine,
      chat: async () => { controller.abort(); throw new DOMException('Aborted', 'AbortError'); },
    };
    await expect(generateCandidate(args({ engine: aborting, signal: controller.signal }), { spec: SPEC })).rejects.toMatchObject({ name: 'AbortError' });
  });

  test('an empty delta point passed with invented movement is rejected', async () => {
    const { engine } = fakeEngine([['他走进门厅，五分钟就这样过去了。']]);
    const result = await generateCandidate({
      ...args({ engine }),
      committed: { anchor: ANCHOR, facts: [] },
      policy: { roster: ['林川'], locations: ['走廊', '门厅'], time: { amount: 5, unit: 'minute' }, minChars: 5 },
    });
    expect(result.accepted).toBe(false);
    expect(result.issues.map((issue) => issue.kind)).toContain('movement_without_fact');
  });
});
