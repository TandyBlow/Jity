import { describe, expect, it } from 'vitest';
import type { CompletionEvidence, CompleteOptions, EngineInfo, InferenceEngine } from '../../../runtime/engine';
import { applyPoint, buildInitialState } from '../../state';
import type { EntityDelta, Position, TimeAdvance, WorldState } from '../../../types';
import { cleanDraft, shapeIssues } from './clean';
import { projectFacts } from './facts';
import { TEST_WORLD } from './fixtures';
import { generateCandidate } from './index';
import { buildProjection } from './projection';
import { buildSceneUserPrompt, DEFAULT_SYSTEM_PROMPT, thirdPersonAction } from './prompt';
import { renderChatML, renderPrompt, resolvePromptMode, resolveTemplate, stripThinking } from './template';
import type { CandidateProgress, GenerateInstructCandidateArgs } from './types';

class ScriptedEngine implements InferenceEngine {
  readonly info: EngineInfo = { backend: 'fake', modelId: 'qwen2.5-1.5b-instruct' };
  readonly calls: { prompt: string; options?: CompleteOptions }[] = [];
  constructor(private readonly replies: string[], modelId?: string) {
    if (modelId) this.info.modelId = modelId;
  }
  async load(): Promise<void> {}
  async complete(prompt: string, options?: CompleteOptions): Promise<string> {
    this.calls.push({ prompt, options });
    const reply = this.replies.shift();
    if (reply === undefined) throw new Error('scripted engine ran out of replies');
    options?.onProgress?.({ raw: reply, elapsedMs: 1 });
    options?.onCompletion?.({ raw: reply, finishReason: 'stop', firstTokenMs: 1, wallMs: 1 } as CompletionEvidence);
    return reply;
  }
  async dispose(): Promise<void> {}
}

const initial = () => buildInitialState({ ...TEST_WORLD, worldId: 'world_test' });

interface SettleArgs {
  patches?: { entityId: string; containerId: string; slotId?: string | null }[];
  time?: TimeAdvance;
  delta?: { sanity?: Record<string, number>; tasksAchieved?: Record<string, string[]> };
}

function settle(state: WorldState, args: SettleArgs = {}) {
  const before = structuredClone(state);
  const target = structuredClone(state);
  for (const patch of args.patches ?? []) {
    const entity = target.characters[patch.entityId] ?? target.items[patch.entityId];
    entity.position = { containerId: patch.containerId, slotId: patch.slotId ?? null, relativeTo: null } as Position;
  }
  const entityDeltas: Record<string, EntityDelta> = {};
  for (const [id, character] of Object.entries(target.characters)) {
    const previous = before.characters[id];
    if (JSON.stringify(previous.position) !== JSON.stringify(character.position)) {
      entityDeltas[id] = { ...(entityDeltas[id] ?? { entityId: id }), positionSet: character.position };
    }
    if (args.delta?.sanity?.[id] !== undefined) entityDeltas[id] = { ...(entityDeltas[id] ?? { entityId: id }), sanitySet: args.delta.sanity[id] };
    if (args.delta?.tasksAchieved?.[id]?.length) entityDeltas[id] = { ...(entityDeltas[id] ?? { entityId: id }), tasksAchieved: args.delta.tasksAchieved[id] };
  }
  for (const [id, item] of Object.entries(target.items)) {
    const previous = before.items[id];
    if (JSON.stringify(previous.position) !== JSON.stringify(item.position)) {
      entityDeltas[id] = { ...(entityDeltas[id] ?? { entityId: id }), positionSet: item.position };
    }
  }
  const timeAdvance = args.time ?? { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } };
  const after = applyPoint(target, {
    worldId: 'world_test', id: 'p1', sequence: 1, kind: 'normal', previousPointId: 'root',
    roundId: 'r1', advanceId: 'a1', trigger: 'player', linkedFromPointId: null,
    timeAdvance, entityDeltas,
  });
  const delta = { timeAdvance, entityDeltas };
  return { before, after, delta, committed: projectFacts(before, delta, after) };
}

const baseArgs = (engine: InferenceEngine, point: ReturnType<typeof settle>, overrides: Partial<GenerateInstructCandidateArgs> = {}): GenerateInstructCandidateArgs => ({
  engine,
  pointId: 'p1',
  committed: point.committed,
  state: point.after,
  before: point.before,
  delta: point.delta,
  playerInput: '我把外套扣好，往庭院走。',
  policy: { template: 'qwen2.5-instruct', promptMode: 'raw', minChars: 20, targetChars: 120, maxAttempts: 2, temperature: 0.7, seed: 7 },
  ...overrides,
});

const GOOD_MOVE = '陈默从大厅走到庭院，前后大约两分钟。院里没有人，他站在石阶边，把衣领拢了拢。';

describe('chat templates', () => {
  it('renders ChatML for Qwen2.5 without a think block', () => {
    const prompt = renderChatML({ system: '规则', user: '场景' }, 'qwen2.5-instruct');
    expect(prompt).toBe('<|im_start|>system\n规则<|im_end|>\n<|im_start|>user\n场景<|im_end|>\n<|im_start|>assistant\n');
  });

  it('disables Qwen3 thinking with the empty think block', () => {
    const prompt = renderChatML({ system: '规则', user: '场景' }, 'qwen3-instruct');
    expect(prompt.endsWith('<|im_start|>assistant\n<think>\n\n</think>\n\n')).toBe(true);
  });

  it('resolves the template from the engine model id and refuses unknown models', () => {
    expect(resolveTemplate('auto', { backend: 'wllama', modelId: 'Qwen3-1.7B-Q4_K_M.gguf' })).toBe('qwen3-instruct');
    expect(resolveTemplate('auto', { backend: 'wllama', modelId: 'qwen2.5-1.5b-instruct-q4_k_m.gguf' })).toBe('qwen2.5-instruct');
    expect(() => resolveTemplate('auto', { backend: 'wllama', modelId: null })).toThrow(/unknown_instruct_template/);
    expect(() => resolveTemplate('auto', { backend: 'wllama', modelId: 'llama-3.2-1b.gguf' })).toThrow(/unknown_instruct_template/);
  });

  it('uses the engine chat template instead of double-templating in chat mode', () => {
    expect(resolvePromptMode('auto', { backend: 'wllama', modelId: 'x' })).toBe('chat');
    expect(resolvePromptMode('auto', { backend: 'fake', modelId: 'x' })).toBe('raw');
    expect(renderPrompt({ system: '规则', user: '场景' }, 'qwen2.5-instruct', 'chat')).toBe('规则\n\n场景');
  });
});

describe('draft cleanup', () => {
  it('removes think blocks, fences, prompt labels and an enclosing quote', () => {
    const raw = '<think>先想一想。</think>```\n【本次变化】\n正文：“陈默从大厅走到庭院，前后大约两分钟。”\n```';
    expect(cleanDraft(raw).text).toBe('陈默从大厅走到庭院，前后大约两分钟。');
    expect(cleanDraft(raw).removedThinking).toBe(true);
    expect(cleanDraft(raw).echoedLabels.length).toBeGreaterThan(0);
  });

  it('drops a bare reasoning preface and duplicated sentences', () => {
    const raw = '思考过程：先定位。\n正文：陈默走到庭院。\n陈默走到庭院。\n院里没有人。';
    const cleaned = cleanDraft(raw);
    expect(cleaned.removedThinking).toBe(true);
    expect(cleaned.repeatedSentences).toHaveLength(1);
    expect(cleaned.text).toBe('陈默走到庭院。院里没有人。');
  });

  it('flags a JSON/list draft instead of calling it prose', () => {
    expect(shapeIssues('{"kind":"act","text":"走"}').some((issue) => issue.kind === 'not_prose')).toBe(true);
    expect(shapeIssues('- 陈默走到庭院\n- 林夏抬头').some((issue) => issue.kind === 'not_prose')).toBe(true);
    expect(shapeIssues(GOOD_MOVE)).toEqual([]);
  });

  it('keeps a partially emitted think block out of the prose', () => {
    expect(stripThinking('<think>推理到一半被打断')).toBe('');
  });
});

describe('projection', () => {
  it('projects the viewpoint room, the visible people and the visible items only', () => {
    const point = settle(initial(), { patches: [{ entityId: 'hero', containerId: 'yard' }] });
    const projection = buildProjection({ state: point.after, before: point.before, delta: point.delta, committed: point.committed });
    expect(projection.viewpoint.name).toBe('陈默');
    expect(projection.place.name).toBe('庭院');
    expect(projection.characters.map((entry) => entry.name)).toEqual(['陈默']);
    expect(projection.items.map((item) => item.name)).not.toContain('仓库钥匙');
    expect(projection.facts.map((fact) => fact.statement)).toContain('陈默从大厅走到庭院');
    expect(projection.facts[0].statement).toContain('2 分钟');
    expect(projection.facts[0].statement).not.toContain('minute');
  });

  it('keeps the viewpoint personality to the first behavioural clause', () => {
    const point = settle(initial());
    const projection = buildProjection({ state: point.after, before: point.before, delta: point.delta, committed: point.committed });
    const hero = projection.characters.find((entry) => entry.viewpoint);
    expect(hero?.personality).toContain('遇到麻烦反而更安静');
    expect(hero?.personality).not.toContain('不擅长求人');
  });

  it('turns an item handover into a mandatory change with the item name', () => {
    const point = settle(initial(), { patches: [{ entityId: 'map', containerId: 'ally' }] });
    const projection = buildProjection({ state: point.after, before: point.before, delta: point.delta, committed: point.committed });
    const fact = projection.facts.find((entry) => entry.kind === 'item_moved');
    expect(fact?.statement).toContain('旧地图');
    expect(fact?.entity).toBe('旧地图');
    expect(fact?.mandatory).toBe(true);
  });

  it('prints present people and room items, never someone from another room', () => {
    const point = settle(initial());
    const projection = buildProjection({ state: point.after, before: point.before, delta: point.delta, committed: point.committed });
    const prompt = buildSceneUserPrompt(projection, {});
    expect(prompt).toContain('林夏');
    expect(prompt).not.toContain('周舟');
    expect(prompt).toContain('铜台灯');
    expect(prompt).not.toContain('- 仓库钥匙（');
    expect(prompt).toContain('【本次变化】');
    expect(prompt).toContain('大约过了 2 分钟');
  });

  it('parses a serialized inputText scene when no state is supplied', () => {
    const inputText = [
      '【视角】陈默（id=hero）',
      '【本回合变化】\n- 陈默从大厅走到庭院',
      '【本回合状态】\n- 陈默（id=hero）位置=庭院；精神值=50',
      '【时间和地点】时间推进 2 分钟；地点：庭院',
      '【可写到的东西】铜台灯（灯罩有裂纹）；旧地图',
    ].join('\n');
    const moved = settle(initial(), { patches: [{ entityId: 'hero', containerId: 'yard' }] });
    const projection = buildProjection({ inputText, committed: moved.committed });
    expect(projection.fromState).toBe(false);
    expect(projection.viewpoint.name).toBe('陈默');
    expect(projection.place.name).toBe('庭院');
    expect(projection.facts.map((fact) => fact.kind)).toContain('moved');
  });
});

describe('generateCandidate', () => {
  it('accepts a faithful draft in one call', async () => {
    const engine = new ScriptedEngine([GOOD_MOVE]);
    const point = settle(initial(), { patches: [{ entityId: 'hero', containerId: 'yard' }] });
    const result = await generateCandidate(baseArgs(engine, point));
    expect(result.accepted).toBe(true);
    expect(result.status).toBe('accepted');
    expect(result.text).toBe(GOOD_MOVE);
    expect(result.rawAttempts).toHaveLength(1);
    expect(result.template).toBe('qwen2.5-instruct');
    expect(engine.calls[0].prompt).toContain(DEFAULT_SYSTEM_PROMPT.slice(0, 8));
    expect(engine.calls[0].prompt).toContain('<|im_start|>assistant');
    expect(engine.calls[0].options?.temperature).toBe(0.7);
    expect(engine.calls[0].options?.stop).toContain('<|im_end|>');
  });

  it('retries once with named problems and keeps the rejected attempt', async () => {
    const engine = new ScriptedEngine(['陈默站在大厅里，看着窗外的天色。', GOOD_MOVE]);
    const point = settle(initial(), { patches: [{ entityId: 'hero', containerId: 'yard' }] });
    const result = await generateCandidate(baseArgs(engine, point));
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts).toHaveLength(2);
    expect(result.rawAttempts[0].accepted).toBe(false);
    expect(result.rawAttempts[0].issues.map((issue) => issue.kind)).toContain('fact_omitted');
    expect(engine.calls[1].prompt).toContain('上一次没有通过检查');
    expect(engine.calls[1].prompt).toContain('漏掉');
    expect(engine.calls[1].options?.temperature).toBe(0.35);
    expect(result.timings.attemptMs).toHaveLength(2);
  });

  it('returns an honest rejection when both attempts fail', async () => {
    const engine = new ScriptedEngine(['陈默站在大厅里。', '他抬头看灯。']);
    const point = settle(initial(), { patches: [{ entityId: 'hero', containerId: 'yard' }] });
    const result = await generateCandidate(baseArgs(engine, point));
    expect(result.accepted).toBe(false);
    expect(result.status).toBe('rejected');
    expect(result.text.length).toBeGreaterThan(0);
    expect(result.issues.some((issue) => issue.kind === 'fact_omitted')).toBe(true);
    expect(result.attemptIndex).not.toBeNull();
  });

  it('strips a leaked think block and still accepts the prose', async () => {
    const engine = new ScriptedEngine([`<think>先想移动。</think>${GOOD_MOVE}`]);
    const point = settle(initial(), { patches: [{ entityId: 'hero', containerId: 'yard' }] });
    const result = await generateCandidate(baseArgs(engine, point));
    expect(result.accepted).toBe(true);
    expect(result.text).not.toContain('think');
    expect(result.rawAttempts[0].raw).toContain('<think>');
  });

  it('rejects a name that is not in the scene', async () => {
    const engine = new ScriptedEngine(['周舟从仓库出来，站在庭院门口。', GOOD_MOVE]);
    const point = settle(initial(), { patches: [{ entityId: 'hero', containerId: 'yard' }] });
    const result = await generateCandidate(baseArgs(engine, point));
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts[0].issues.map((issue) => issue.kind)).toContain('unlicensed_entity');
  });

  it('downgrades an event verb licensed by the player action and rejects it otherwise', async () => {
    const draft = '陈默从大厅走到庭院，前后大约两分钟。林夏把旧地图递给他。';
    const point = settle(initial(), { patches: [{ entityId: 'hero', containerId: 'yard' }] });
    const licensed = await generateCandidate(baseArgs(new ScriptedEngine([draft]), point, { playerInput: '我让林夏把旧地图递给我。' }));
    expect(licensed.accepted).toBe(true);
    expect(licensed.issues.some((issue) => issue.kind === 'licensed_event' && issue.severity === 'soft')).toBe(true);
    const unlicensed = await generateCandidate(baseArgs(new ScriptedEngine([draft, draft]), point, { playerInput: '我往庭院走。' }));
    expect(unlicensed.accepted).toBe(false);
    expect(unlicensed.issues.some((issue) => issue.kind === 'added_event' && issue.severity === 'hard')).toBe(true);
  });

  it('rejects first-person narration and an unchanged repeat of the previous prose', async () => {
    const point = settle(initial(), { patches: [{ entityId: 'hero', containerId: 'yard' }] });
    const firstPerson = await generateCandidate(baseArgs(new ScriptedEngine(['我从大厅走到庭院，前后大约两分钟。']), point));
    expect(firstPerson.issues.map((issue) => issue.kind)).toContain('first_person_narrator');
    const echo = await generateCandidate(baseArgs(new ScriptedEngine([GOOD_MOVE, GOOD_MOVE]), point, { priorText: GOOD_MOVE }));
    expect(echo.accepted).toBe(false);
    expect(echo.rawAttempts[0].issues.map((issue) => issue.kind)).toContain('echo_prior');
  });

  it('refuses to accept a draft without a committed packet', async () => {
    const point = settle(initial());
    const result = await generateCandidate(baseArgs(new ScriptedEngine([GOOD_MOVE]), point, { committed: null }));
    expect(result.accepted).toBe(false);
    expect(result.issues.map((issue) => issue.kind)).toContain('facts_unverified');
  });

  it('emits streaming progress and a final verified state', async () => {
    const engine = new ScriptedEngine([GOOD_MOVE]);
    const point = settle(initial(), { patches: [{ entityId: 'hero', containerId: 'yard' }] });
    const states: CandidateProgress[] = [];
    const result = await generateCandidate(baseArgs(engine, point, { onProgress: (state) => states.push(state) }));
    expect(states[0].status).toBe('streaming');
    expect(states[0].verified).toBe(false);
    expect(states[states.length - 1].status).toBe('accepted');
    expect(states[states.length - 1].verified).toBe(true);
    expect(result.timings.firstTokenMs).not.toBeNull();
  });

  it('narrates a task by its result words and treats the stat change as soft', async () => {
    const draft = '林夏把旧收音机修好了，沙沙的电流声重新清楚起来，前后不过两分钟。她的肩膀也松了下来。';
    const point = settle(initial(), { time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, delta: { sanity: { ally: 62 }, tasksAchieved: { ally: ['t2'] } } });
    const result = await generateCandidate(baseArgs(new ScriptedEngine([draft]), point, { playerInput: '我问林夏收音机修好没有。' }));
    expect(result.accepted).toBe(true);
    const omissions = result.issues.filter((issue) => issue.kind === 'fact_omitted');
    expect(omissions.every((issue) => issue.severity === 'soft')).toBe(true);
  });

  it('turns the player action into third person outside quotes', () => {
    expect(thirdPersonAction('我把外套扣好，说：“我先走了。”', '陈默')).toBe('陈默把外套扣好，说：“我先走了。”');
  });
});

describe('chat-capable engine', () => {
  it('uses the real system turn when the adapter exposes chat()', async () => {
    const point = settle(initial(), { patches: [{ entityId: 'hero', containerId: 'yard' }] });
    const messages: { role: string; content: string }[] = [];
    const engine = {
      info: { backend: 'wllama', modelId: 'qwen2.5-1.5b-instruct-q4_k_m.gguf' },
      async load() {},
      async dispose() {},
      async complete() { throw new Error('complete() must not be used when chat() exists'); },
      async chat(turns: { role: string; content: string }[]) {
        messages.push(...turns);
        return GOOD_MOVE;
      },
    };
    const result = await generateCandidate(baseArgs(engine, point, { policy: { targetChars: 120, minChars: 20, maxAttempts: 1 } }));
    expect(result.accepted).toBe(true);
    expect(messages.map((turn) => turn.role)).toEqual(['system', 'user']);
    expect(messages[0].content).toContain('中文小说作者');
    expect(messages[1].content).toContain('陈默从大厅走到庭院');
  });
});
