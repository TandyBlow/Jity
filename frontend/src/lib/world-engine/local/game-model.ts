/** Real on-device model port for the local game. The controller still owns
 * freeze/settle/apply; this file only turns one task input into one validated
 * JSON/text answer. Prompts are deliberately short and id-oriented because the
 * first browser model is a 0.6B instruct model. A task never returns a
 * candidate that the controller's codec rejects; on a malformed answer it
 * retries once, then returns the task's explicit program fallback and records
 * the failure. */
import type { ModelTask } from '../schedule';
import type { WorldModelPort } from '../controller';
import type { EntityDelta, Id, Json, TimeAdvance, WorldState } from '../types';
import type { CompletionEvidence, InferenceEngine } from '../runtime/engine';
import { decodeTaskOutput } from '../runtime/structured-output';
import { alignNarration, EVENT_VERBS } from '../runtime/narration-alignment';
import { IncompleteGenerationError } from '../runtime/engine';
import type { CommittedNarration, NarrationFact } from '../runtime/committed-narration';
import { taskOutputSchema } from '../runtime/output-schema';
import { describeCharacter, describeDelta, describeItem, describeLocation, instructNarrationInput, legacyNarrationInput, locationName, roomName, roomOf, sameRoomItems, taskText, visibleCharacters, activeText } from './prompt';

export interface GameModelOptions {
  modelUrl?: string;
  contextSize?: number;
  nGpuLayers?: number;
  temperature?: number;
  narrationTemperature?: number;
  narrationMaxTokens?: number;
  narrationTimeoutMs?: number;
  narrationEngine?: InferenceEngine;
  /** 'legacy' continues the yuyan-prose format for the 0.5B checkpoint;
   * 'instruct' states the task for an instruction-tuned narration model. */
  narrationMode?: 'legacy' | 'instruct';
  maxTokensByTask?: Partial<Record<ModelTask, number>>;
  /** Automatic rounds after one player action. Default 0: one action = one round. */
  maxAutoContinuations?: number;
  /** Raw streaming text for the current narration point. */
  onNarrationProgress?: (progress: { pointId: Id; raw: string; elapsedMs: number }) => void;
  onNarrationComplete?: (progress: { pointId: Id; raw: string; completion: CompletionEvidence }) => void;
  onTask?: (task: ModelTask, key: string, detail: { ms: number; fallback: boolean; error?: string; raw?: string; promptChars?: number }) => void;
}

interface Generated { value: Json; raw: string; ms: number; fallback: boolean; error?: string }

const JSON_SCHEMAS = {
  targets: {
    type: 'object', additionalProperties: false, required: ['targets'],
    properties: { targets: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['targetId'], properties: { targetId: { type: 'string' } } } } },
  },
  results: { type: 'object', additionalProperties: { type: 'string' }, minProperties: 1 },
  continue: {
    type: 'object', additionalProperties: false, required: ['continue'],
    properties: { continue: { type: 'boolean' }, reason: { type: 'string' } },
  },
  move: {
    type: 'object', additionalProperties: false, required: ['moved'],
    properties: { moved: { type: 'boolean' }, toLocationId: { type: ['string', 'null'] } },
  },
  changes: {
    type: 'object', additionalProperties: false, required: ['changes'],
    properties: {
      move: {
    type: 'object', additionalProperties: false, required: ['moved'],
    properties: { moved: { type: 'boolean' }, toLocationId: { type: ['string', 'null'] } },
  },
  changes: { type: 'object', additionalProperties: {
        type: 'object', additionalProperties: false,
        properties: {
          positionSet: { anyOf: [{ type: 'null' }, { type: 'object', additionalProperties: false, required: ['containerId'], properties: {
            containerId: { type: 'string' }, slotId: { type: ['string', 'null'] },
            relativeTo: { anyOf: [{ type: 'null' }, { type: 'object', additionalProperties: false, required: ['entityId', 'relation'], properties: {
              entityId: { type: 'string' }, relation: { enum: ['under', 'above', 'beside', 'in_front_of', 'behind'] } } }] } } }] },
          appearanceChanges: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['id', 'text', 'supersedes'], properties: {
            id: { type: 'string' }, text: { type: ['string', 'null'] }, supersedes: { type: 'array', items: { type: 'string' } } } } },
          personalityChanges: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['id', 'text', 'supersedes'], properties: {
            id: { type: 'string' }, text: { type: ['string', 'null'] }, supersedes: { type: 'array', items: { type: 'string' } } } } },
          sanitySet: { type: ['number', 'null'] },
          tasksAchieved: { type: 'array', items: { type: 'string' } },
          subtasksAdded: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['id', 'ownerId', 'parentTaskId', 'goal', 'status'], properties: {
            id: { type: 'string' }, ownerId: { type: 'string' }, parentTaskId: { type: ['string', 'null'] },
            goal: { type: 'string' }, status: { enum: ['pending', 'achieved'] } } } },
        },
      } },
    },
  },
};

const TASK_MAX_TOKENS: Record<string, number> = {
  action: 96, targets: 96, reaction: 128, results: 320, updates: 640,
  continuation: 64, pointPlan: 64, narration: 900, time: 64, initial: 64,
};

export class LocalGameModel implements WorldModelPort {
  private readonly engine: InferenceEngine;
  private readonly narrationEngine: InferenceEngine;
  private readonly options: GameModelOptions;
  private roundCounter = 0;
  private lastPlayerInput = '';
  private lastResultsText = '';
  private autoContinuations = 0;

  constructor(engine: InferenceEngine, options: GameModelOptions = {}) {
    this.engine = engine;
    this.narrationEngine = options.narrationEngine ?? engine;
    this.options = options;
  }

  get info() { return this.engine.info; }

  resetAutoContinuations(): void { this.autoContinuations = 0; }

  async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
    const generated = await this.run(task, key, input);
    return generated.value;
  }

  private async run(task: ModelTask, key: string, input: Json): Promise<Generated> {
    const started = performance.now();
    try {
      if (task === 'pointPlan') return { value: this.planPoints(input), raw: '', ms: 0, fallback: false };
      if (task === 'action') return await this.action(key, input);
      if (task === 'targets') return await this.targets(key, input);
      if (task === 'reaction') return await this.reaction(key, input);
      if (task === 'results') return await this.results(key, input);
      if (task === 'updates') return await this.updates(key, input);
      if (task === 'continuation') return await this.continuation(input);
      if (task === 'narration') return await this.narration(key, input);
      throw new Error(`unsupported game task: ${task}`);
    } catch (error) {
      this.options.onTask?.(task, key, { ms: performance.now() - started, fallback: true, error: error instanceof Error ? error.message : String(error) });
      throw error;
    }
  }

  /** One point per round covering the full frozen roster. Point segmentation
   * is program-owned here; the model owns the semantic action/results work. */
  private planPoints(input: Json): Json {
    const round = (input as { round?: { roundId?: Id; order?: Id[] } }).round;
    const order = round?.order ?? [];
    return [{ pointId: `point_${round?.roundId ?? 'round'}_1`, kind: 'normal',
      timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: order }];
  }

  private async action(key: Id, input: Json): Promise<Generated> {
    const data = input as { actor?: Id; advance?: { inputText?: string | null; intentStatus?: string }; workingState?: WorldState };
    const state = data.workingState;
    const actor = data.actor ?? key;
    if (!state) throw new Error('action without workingState');
    if (actor === state.protagonistId) {
      const text = data.advance?.inputText?.trim() ?? '';
      this.lastPlayerInput = text;
      return { value: text ? { kind: 'act', text } : { kind: 'skip' }, raw: '', ms: 0, fallback: false };
    }
    // Distant characters are not put in front of the player: judge the room
    // the protagonist can actually see. This is a visibility rule, not a
    // fixed command list; same-room NPCs do get a real model decision.
    if (roomOf(state, actor) !== roomOf(state, state.protagonistId)) {
      return { value: { kind: 'skip' }, raw: '', ms: 0, fallback: false };
    }
    const actorName = state.initial.characters[actor]?.name ?? actor;
    if (!this.lastPlayerInput.includes(actorName) || !INTERACTION.test(this.lastPlayerInput)) {
      return { value: { kind: 'skip' }, raw: '', ms: 0, fallback: false };
    }
    const visible = visibleCharacters(state, actor).filter((id) => id !== actor);
    const prompt = [
      '你是中文跑团游戏的角色行动判断器。只输出 JSON。',
      '判断下面这个角色此刻是否采取行动。可以是动作、对白或短句；若没有值得结算的行动，输出 {"kind":"skip"}。',
      '不要代替主角执行玩家命令；不要复述玩家输入；不要用“我”自称；不要新增未登记的人物、地点、物品或往事。',
      `当前角色：\n${describeCharacter(state, actor)}`,
      `同地点可见人物：\n${visible.map((id) => describeCharacter(state, id, false)).join('\n') || '无'}`,
      `玩家本回合输入：${data.advance?.inputText ?? '（无）'}`,
      `地点：${describeLocation(state, roomOf(state, actor))}`,
      '输出只能是：{"kind":"act","text":"一句话行动描述"} 或 {"kind":"skip"}。',
    ].join('\n');
    const generated = await this.jsonTask('action', prompt, undefined, key);
    const output = generated.value as { kind?: string; text?: string };
    if (output.kind === 'act') {
      const text = (output.text ?? '').trim();
      if (!text || text === (data.advance?.inputText ?? '').trim() || text.startsWith('我')) {
        this.options.onTask?.('action', key, { ms: generated.ms, fallback: true, error: 'npc_action_copied_player', raw: text });
        return { ...generated, value: { kind: 'skip' }, fallback: true };
      }
      return { ...generated, value: { kind: 'act', text } };
    }
    return generated;
  }

  private async targets(key: Id, input: Json): Promise<Generated> {
    const data = input as { sourceId?: Id; actionText?: string; workingState?: WorldState };
    const state = data.workingState;
    const source = data.sourceId ?? key;
    if (!state) throw new Error('targets without workingState');
    const candidates = visibleCharacters(state, source).filter((id) => id !== source);
    if (!candidates.length) return { value: { targets: [] }, raw: '', ms: 0, fallback: false };
    if (source === state.protagonistId && !INTERACTION.test(data.actionText ?? '')) return { value: { targets: [] }, raw: '', ms: 0, fallback: false };
    if (source !== state.protagonistId && !this.lastPlayerInput.includes(state.initial.characters[source]?.name ?? source)) return { value: { targets: [] }, raw: '', ms: 0, fallback: false };
    const prompt = [
      '你是中文跑团游戏的牵连判断器。只输出 JSON。',
      '下面是一条已经确认的行动。判断它直接牵连哪些同地点人物；只选会被这句话直接触及、需要立即反应的人。没有就返回空数组。',
      `行动者：${describeCharacter(state, source)}`,
      `行动：${data.actionText ?? ''}`,
      `同地点人物：\n${candidates.map((id) => describeCharacter(state, id, false)).join('\n')}`,
      '输出：{"targets":[{"targetId":"人物id"}]}。targetId 只能从上面的人物 id 中选。',
    ].join('\n');
    const generated = await this.jsonTask('targets', prompt, JSON_SCHEMAS.targets, key);
    const output = generated.value as { targets?: { targetId?: string }[] };
    const byName = new Map(candidates.map((id) => [state.initial.characters[id]?.name ?? id, id]));
    const allowed = new Set(candidates);
    const normalized = (output.targets ?? []).map((target) => {
      const raw = String(target.targetId ?? '');
      return allowed.has(raw) ? raw : byName.get(raw) ?? '';
    }).filter(Boolean);
    const unique = [...new Set(normalized)];
    if (unique.length > 2) this.options.onTask?.('targets', key, { ms: generated.ms, fallback: false, error: `targets_capped:${unique.length}->2` });
    return { ...generated, value: { targets: unique.slice(0, 2).map((targetId) => ({ targetId })) } as unknown as Json };
  }

  private async reaction(key: Id, input: Json): Promise<Generated> {
    const data = input as { sourceId?: Id; sourceActionText?: string; memberId?: Id; workingState?: WorldState };
    const state = data.workingState;
    const member = data.memberId ?? key;
    if (!state) throw new Error('reaction without workingState');
    const prompt = [
      '你是中文跑团游戏的反应生成器。只输出正文，不要 JSON。',
      '写被牵连角色的一句到两句即时反应。必须针对下面这条具体威胁；不得替主角行动，不得新增人物、地点、物品或往事。',
      `被牵连角色：${describeCharacter(state, member)}`,
      `发起者：${describeCharacter(state, data.sourceId ?? key, false)}`,
      `发起者的行动：${data.sourceActionText ?? ''}`,
      '反应：',
    ].join('\n');
    return this.textTask(prompt, `reaction:${key}`, 128, 0);
  }

  private async results(key: Id, input: Json): Promise<Generated> {
    const data = input as { groupId?: Id; members?: { memberId: Id; actionText?: string | null; rollRefs?: unknown[] }[]; workingState?: WorldState };
    const state = data.workingState;
    if (!state) throw new Error('results without workingState');
    const members = data.members ?? [];
    if (members.length === 1 && members[0].memberId === state.protagonistId) {
      const text = this.programResult(members[0].actionText ?? '', state);
      this.lastResultsText = text;
      this.options.onTask?.('results', key, { ms: 0, fallback: true, error: 'program_single_member', raw: text });
      return { value: { [members[0].memberId]: text } as unknown as Json, raw: text, ms: 0, fallback: true, error: 'program_single_member' };
    }
    const lines = members.map((member) => {
      const rolls = (member.rollRefs ?? []).length ? '有判定' : '无判定';
      return `- ${member.memberId}（${state.initial.characters[member.memberId]?.name ?? '?'}）行动：${member.actionText ?? '（无）'}；${rolls}`;
    });
    const prompt = [
      '你是中文跑团游戏的结算叙述器。不要输出 JSON，不要解释。',
      '为每个小组成员写一句结算结果，每行一个成员，格式：成员id：结果。',
      '结果要写“发生了什么”，不要复述行动；已接纳的行动可以成功或付出代价，未被接纳的行动要写被制止或没有发生。',
      '只能使用下面出现的人物、地点、物品；不得新增人物、地点、物品、往事、线索或任务。',
      `本组：${data.groupId ?? key}`,
      ...lines,
      '现在逐行输出结果：',
    ].join(String.fromCharCode(10));
    const started = performance.now();
    const raw = await this.engine.complete(prompt, { maxTokens: 360, temperature: 0, timeoutMs: 60_000 });
    const byName = new Map(members.map((member) => [state.initial.characters[member.memberId]?.name ?? member.memberId, member.memberId]));
    const normalized: Record<string, string> = {};
    for (const line of raw.split(/\r?\n/)) {
      const match = line.match(/^\s*[-*]?\s*([^：:|]+)\s*[：:|]\s*(.+)$/u);
      if (!match) continue;
      const rawKey = match[1].trim();
      const id = members.some((member) => member.memberId === rawKey) ? rawKey : byName.get(rawKey) ?? '';
      if (id && !normalized[id]) normalized[id] = match[2].trim();
    }
    for (const member of members) if (!normalized[member.memberId]) normalized[member.memberId] = '行动发生了，但没有产生新的结果。';
    this.lastResultsText = Object.values(normalized).join('；');
    this.options.onTask?.('results', key, { ms: performance.now() - started, fallback: false, raw, promptChars: prompt.length });
    return { value: normalized as unknown as Json, raw, ms: performance.now() - started, fallback: false };
  }

  private async updates(key: Id, input: Json): Promise<Generated> {
    const data = input as { workingState?: WorldState; results?: Record<Id, string>; mode?: string; stage?: string };
    const state = data.workingState;
    if (!state) throw new Error('updates without workingState');
    const resultLines = Object.entries(data.results ?? {}).map(([id, text]) => `${id}：${text}`).join('；');
    const characters = Object.keys(state.characters).sort().map((id) => describeCharacter(state, id, id === state.protagonistId)).join('；');
    const locations = locationIdCatalog(state);
    const prompt = [
      '你是中文跑团游戏的状态记录器。不要输出 JSON，不要解释。',
      '根据结算结果，列出世界状态的明确变化。每行一条，格式如下（只写有变化的）：',
      '实体id|position|地点id',
      '实体id|sanity|数字',
      '实体id|task|任务id',
      '实体id|appearance|一句新的外貌描述',
      '实体id|personality|一句新的个性描述',
      '没有变化就只输出 NONE。不能改变未涉及的人物，不能凭空新增地点或任务。',
      `结算结果：${resultLines || '（无）'}`,
      `人物（id、位置、精神、任务 id 和目标）：${characters}`,
      `地点 id 和名字（position 只能填地点 id）：${locations}`,
      '变化：',
    ].join(String.fromCharCode(10));
    const started = performance.now();
    const raw = await this.engine.complete(prompt, { maxTokens: 420, temperature: 0, timeoutMs: 60_000 });
    try {
      let value = parseLineChanges(raw, state);
      let fallback = false;
      // A small model often answers NONE for its own movement. Ask the one
      // question it can answer reliably — did the protagonist change room,
      // and which room id — and merge that into the parsed changes.
      const moved = await this.movementJudgement(state, data.results ?? {}, locations);
      const groups = value as unknown as { stage: string; changes: Record<Id, EntityDelta> }[];
      const hasMove = Array.isArray(groups) && groups.some((group) => group?.changes?.[state.protagonistId]?.positionSet);
      if (moved && !hasMove) {
        const positionStage = { stage: 'position', changes: { [state.protagonistId]: { entityId: state.protagonistId, positionSet: { containerId: moved, slotId: null, relativeTo: null } } } };
        const list = Array.isArray(groups) ? groups : [];
        value = [positionStage, ...list].sort((a, b) => STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage)) as unknown as Json;
      }
      if (Array.isArray(value) && value.length === 0) {
        const program = this.programMovementChanges(state, data.results ?? {});
        if (program.length) { value = program as unknown as Json; fallback = true; }
      }
      this.options.onTask?.('updates', key, { ms: performance.now() - started, fallback, raw, promptChars: prompt.length, error: fallback ? 'program_movement_fallback' : undefined });
      return { value: value as unknown as Json, raw, ms: performance.now() - started, fallback };
    } catch (error) {
      this.options.onTask?.('updates', key, { ms: performance.now() - started, fallback: true, error: error instanceof Error ? error.message : String(error), raw, promptChars: prompt.length });
      return { value: [], raw, ms: performance.now() - started, fallback: true, error: error instanceof Error ? error.message : String(error) };
    }
  }

  /** Structured movement judgement. The location catalog makes this a pick
   * from a list, which the 0.6B model answers far more reliably than free
   * text. Returns the destination id or null. */
  private async movementJudgement(state: WorldState, results: Record<Id, string>, locations: string): Promise<Id | null> {
    const current = state.characters[state.protagonistId]?.position.containerId;
    // Only rooms next to the protagonist are offered. The full catalog made
    // the 0.6B model teleport across the map because every name was legal.
    const candidates = adjacentLocations(state, current, [this.lastPlayerInput]);
    const prompt = [
      '你是中文跑团游戏的位置判断器。只输出 JSON。',
      '判断主角在这一回合结束后是否换了地点。只有主角真的移动到别处才算；原地说话、观察、等待都不算。',
      `主角：${describeCharacter(state, state.protagonistId, false)}`,
      `玩家输入：${this.lastPlayerInput}`,
      `结算结果：${Object.values(results).join('；') || '（无）'}`,
      `候选地点：${candidates}`,
      '输出：{"moved":true,"toLocationId":"地点id"} 或 {"moved":false,"toLocationId":null}。toLocationId 只能从候选地点里选，不能等于主角当前地点。',
    ].join(String.fromCharCode(10));
    try {
      const generated = await this.objectTask('updates', prompt, JSON_SCHEMAS.move, 'move');
      const output = generated.value as { moved?: boolean; toLocationId?: string | null };
      const target = typeof output?.toLocationId === 'string' ? output.toLocationId.trim() : '';
      if (output?.moved !== true || !state.initial.locations[target] || target === current) return null;
      return target;
    } catch {
      return null;
    }
  }

  private async continuation(input: Json): Promise<Generated> {
    const data = input as { workingState?: WorldState; roundChanges?: Json; round?: { roundId?: Id } };
    const state = data.workingState;
    if (!state) throw new Error('continuation without workingState');
    const prompt = [
      '你是中文跑团游戏的继续判断器。只输出 JSON。',
      '判断本回合结束后，是否还有一个与主角当前行动紧密相关、必须马上继续的后续行动。只有同一场景内、主角或在场人物已经明确开始且未完成的动作才继续；普通闲聊、等待、场景切换都交还玩家。',
      `主角：${describeCharacter(state, state.protagonistId)}`,
      `同地点人物：\n${visibleCharacters(state, state.protagonistId).filter((id) => id !== state.protagonistId).map((id) => describeCharacter(state, id, false)).join('\n') || '无'}`,
      `本回合变化：${JSON.stringify(data.roundChanges ?? {})}`,
      '输出：{"continue":true或false,"reason":"一句话理由"}。',
    ].join('\n');
    const generated = await this.objectTask('continuation', prompt, JSON_SCHEMAS.continue, 'continuation');
    const output = generated.value as { continue?: boolean; reason?: string };
    const nextRoundId = `round_auto_${Date.now().toString(36)}_${++this.roundCounter}`;
    const candidates = [state.protagonistId, ...visibleCharacters(state, state.protagonistId).filter((id) => id !== state.protagonistId)];
    const wantContinue = output.continue === true && this.autoContinuations < (this.options.maxAutoContinuations ?? 0);
    if (wantContinue) this.autoContinuations += 1;
    const conclusion = wantContinue
      ? { kind: 'continue', closedBy: 'model', cancelReason: null, nextRoundId, candidateCharacterIds: candidates }
      : { kind: 'handback', closedBy: 'model', cancelReason: null };
    return { ...generated, value: conclusion as unknown as Json };
  }

  private async narration(key: Id, input: Json): Promise<Generated> {
    const data = input as { pointId?: Id; before?: WorldState | null; delta?: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }; after?: WorldState; perspective?: string };
    const after = data.after;
    if (!after) throw new Error('narration without after state');
    const pointId = data.pointId ?? key;
    const view = after.protagonistId;
    const brief = this.options.narrationMode === 'instruct'
      ? instructNarrationInput(data.before ?? null, data.delta ?? {}, after, view, this.lastPlayerInput, this.lastResultsText)
      : { prompt: legacyNarrationInput(data.before ?? null, data.delta ?? {}, after, view), brief: legacyNarrationInput(data.before ?? null, data.delta ?? {}, after, view) };
    const facts = brief.prompt;
    const started = performance.now();
    let raw = '';
    try {
      raw = await this.narrationEngine.complete(facts, {
        maxTokens: this.options.narrationMaxTokens ?? 380, temperature: this.options.narrationTemperature ?? 0.7,
        timeoutMs: this.options.narrationTimeoutMs ?? 150_000,
        onProgress: (progress) => this.options.onNarrationProgress?.({ pointId, raw: progress.raw, elapsedMs: performance.now() - started }),
      });
    } catch (error) {
      // A length-limited generation still carries usable prose: keep the
      // complete sentences instead of throwing the whole point away.
      const partial = error instanceof IncompleteGenerationError ? error.completion.raw : '';
      if (partial.trim().length < 80) {
        const message = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
        const text = factualNarration(data.before ?? null, data.delta ?? {}, after, view, this.lastPlayerInput);
        this.options.onTask?.('narration', key, { ms: performance.now() - started, fallback: true, error: message, raw: text, promptChars: facts.length });
        return { value: text as unknown as Json, raw: text, ms: performance.now() - started, fallback: true, error: message };
      }
      raw = partial;
    }
    const cleaned = finishSentences(cleanNarration(raw).replace(/※/g, String.fromCharCode(10, 10))).trim();
    const validation = validateNarration(cleaned, brief.brief, after, view);
    const alignment = alignNarration(alignmentPacket(data.before ?? null, data.delta ?? {}, after), cleaned, {
      roster: Object.values(after.initial.characters).map((entity) => entity.name),
      locations: Object.values(after.initial.locations).map((entity) => entity.name),
      time: data.delta?.timeAdvance?.duration ?? null,
      knownPositions: visibleCharacters(after, view).filter((id) => id !== view).map((id) => ({ name: after.initial.characters[id]?.name ?? id, location: locationName(after, roomOf(after, id)) })),
      allowedEvents: EVENT_VERBS.filter((verb) => this.lastPlayerInput.includes(verb)),
    });
    // Sentence-level repair keeps the literary text and only removes the
    // claims the settled state cannot support. Whole-text rejection made the
    // page show a state summary almost every round, which is worse than a
    // slightly shorter scene.
    const pruned = pruneNarration(cleaned, alignment, after, view);
    const text = [...pruned.text].length >= 140 ? pruned.text : factualNarration(data.before ?? null, data.delta ?? {}, after, view, this.lastPlayerInput);
    const accepted = pruned.dropped.length === 0 && validation.ok && alignment.ok;
    const reason = accepted ? undefined : [validation.reason, ...pruned.dropped.map((entry) => entry.reason)].filter(Boolean).join(',');
    this.options.onTask?.('narration', key, { ms: performance.now() - started, fallback: !accepted, error: reason, raw: text, promptChars: facts.length });
    this.options.onNarrationComplete?.({ pointId, raw: text, completion: { raw: text, finishReason: accepted ? 'stop' : 'pruned', firstTokenMs: null, wallMs: performance.now() - started } });
    return { value: text as unknown as Json, raw: text, ms: performance.now() - started, fallback: !accepted, error: reason };
  }

  private normalizeChanges(input: { changes?: Record<Id, EntityDelta> }, state: WorldState): Json {
    const stages: { stage: string; changes: Record<Id, EntityDelta> }[] = [];
    const order: { stage: string; fields: (keyof EntityDelta)[] }[] = [
      { stage: 'position', fields: ['positionSet'] },
      { stage: 'appearance', fields: ['appearanceChanges'] },
      { stage: 'tasks', fields: ['tasksAchieved'] },
      { stage: 'subtasks', fields: ['subtasksAdded'] },
      { stage: 'personality', fields: ['personalityChanges'] },
      { stage: 'sanity', fields: ['sanitySet'] },
    ];
    for (const { stage, fields } of order) {
      const changes: Record<Id, EntityDelta> = {};
      for (const [id, delta] of Object.entries(input.changes ?? {})) {
        if (!state.characters[id] && !state.items[id]) continue;
        const picked: EntityDelta = { entityId: id };
        for (const field of fields) if (delta[field] !== undefined) (picked as unknown as Record<string, unknown>)[field] = delta[field];
        if (Object.keys(picked).length) changes[id] = picked;
      }
      if (Object.keys(changes).length) stages.push({ stage, changes });
    }
    return stages as unknown as Json;
  }

  private async objectTask(task: ModelTask, prompt: string, schema: object, key: string): Promise<Generated> {
    const started = performance.now();
    let lastError = '';
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const raw = await this.engine.complete(prompt, {
          maxTokens: this.options.maxTokensByTask?.[task] ?? TASK_MAX_TOKENS[task] ?? 256,
          temperature: attempt === 0 ? 0 : 0.2,
          jsonSchema: schema,
          timeoutMs: 60_000,
        });
        const value = parseJsonObject(raw);
        this.options.onTask?.(task, key, { ms: performance.now() - started, fallback: false, raw, promptChars: prompt.length });
        return { value: value as Json, raw, ms: performance.now() - started, fallback: false };
      } catch (error) {
        lastError = error instanceof Error ? error.message : String(error);
        if (attempt === 0) continue;
      }
    }
    this.options.onTask?.(task, key, { ms: performance.now() - started, fallback: true, error: lastError, promptChars: prompt.length });
    return { value: this.fallback(task, key), raw: '', ms: performance.now() - started, fallback: true, error: lastError };
  }

  private programMovementChanges(state: WorldState, results: Record<Id, string>): { stage: string; changes: Record<Id, EntityDelta> }[] {
    const input = this.lastPlayerInput;
    const destination = this.mentionedLocation(input, state);
    if (!destination || !MOVEMENT.test(input)) return [];
    const resultText = results[state.protagonistId] ?? '';
    if (/制止|失败|未能|没有发生|被打断/u.test(resultText)) return [];
    const current = state.characters[state.protagonistId]?.position.containerId;
    if (current === destination) return [];
    return [{ stage: 'position', changes: { [state.protagonistId]: { entityId: state.protagonistId, positionSet: { containerId: destination, slotId: null, relativeTo: null } } } }];
  }

  private programResult(action: string, state: WorldState): string {
    const name = state.initial.characters[state.protagonistId]?.name ?? '主角';
    const destination = this.mentionedLocation(action, state);
    if (destination && MOVEMENT.test(action)) return `${name}向${locationName(state, destination)}移动。`;
    return `${name}完成了刚才的动作。`;
  }

  private mentionedLocation(text: string, state: WorldState): Id | null {
    let best: { id: Id; length: number } | null = null;
    for (const [id, location] of Object.entries(state.initial.locations)) {
      if (location.name.length >= 2 && text.includes(location.name) && (!best || location.name.length > best.length)) {
        best = { id, length: location.name.length };
      }
    }
    return best?.id ?? null;
  }

  private async jsonTask(task: ModelTask, prompt: string, schema: object | undefined, key: string): Promise<Generated> {
    const started = performance.now();
    let lastError = '';
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const raw = await this.engine.complete(prompt, {
          maxTokens: this.options.maxTokensByTask?.[task] ?? TASK_MAX_TOKENS[task] ?? 256,
          temperature: attempt === 0 ? 0 : 0.2,
          jsonSchema: schema ?? taskOutputSchema(task, {} as Json),
          timeoutMs: 60_000,
          stop: ['\n\n\n'],
        });
        const value = decodeTaskOutput(task, raw);
        this.options.onTask?.(task, key, { ms: performance.now() - started, fallback: false, raw, promptChars: prompt.length });
        return { value: value as Json, raw, ms: performance.now() - started, fallback: false };
      } catch (error) {
        lastError = error instanceof Error ? error.message : String(error);
        if (attempt === 0) continue;
      }
    }
    this.options.onTask?.(task, key, { ms: performance.now() - started, fallback: true, error: lastError, promptChars: prompt.length });
    return { value: this.fallback(task, key), raw: '', ms: performance.now() - started, fallback: true, error: lastError };
  }

  private async textTask(prompt: string, _key: string, maxTokens: number, temperature: number): Promise<Generated> {
    const started = performance.now();
    const raw = await this.engine.complete(prompt, { maxTokens, temperature, timeoutMs: 60_000 });
    const text = raw.trim();
    return { value: text as unknown as Json, raw: text, ms: performance.now() - started, fallback: false };
  }

  private fallback(task: ModelTask, key: Id): Json {
    if (task === 'action') return { kind: 'skip' };
    if (task === 'targets') return { targets: [] };
    if (task === 'results') return { [key]: '行动发生了，但没有产生新的结果。' };
    if (task === 'updates') return [];
    if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
    if (task === 'reaction') return '对方没有反应。';
    return {};
  }
}

function parseJsonObject(raw: string): unknown {
  const text = raw.trim().replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/i, '').trim();
  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  if (start < 0 || end <= start) throw new Error('model output is not a JSON object');
  return JSON.parse(text.slice(start, end + 1));
}

function locationCatalog(state: WorldState): string {
  return Object.keys(state.initial.locations).sort().map((id) => describeLocation(state, id)).join('\n');
}

function itemCatalog(state: WorldState): string {
  return Object.keys(state.initial.items).sort().map((id) => describeItem(state, id)).join('\n');
}

function narrationFacts(before: WorldState | null, delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }, after: WorldState, view: Id): string {
  const changed = Object.keys(delta.entityDeltas ?? {});
  const visible = new Set([view, ...visibleCharacters(after, view), ...changed]);
  const beforeView = before ? [before.protagonistId, ...visibleCharacters(before, view), ...changed] : [];
  const afterLines = [...visible].filter((id) => after.characters[id]).map((id) => describeCharacter(after, id));
  const beforeLines = before ? [...new Set(beforeView)].filter((id) => before.characters[id]).map((id) => describeCharacter(before, id)) : [];
  const locations = new Set<Id>();
  for (const id of [...visible, ...beforeView]) { locations.add(roomOf(after, id)); if (before) locations.add(roomOf(before, id)); }
  const items = new Set<Id>();
  for (const id of [...visible, ...changed]) for (const item of sameRoomItems(after, id)) items.add(item);
  return [
    `【视角】${after.initial.characters[view]?.name ?? view}（id=${view}）`,
    before ? `【上回合状态】\n${beforeLines.join('\n')}` : '【上回合状态】故事开始。',
    `【本回合变化】\n${describeDelta(delta.entityDeltas ?? {}, after)}`,
    `【本回合状态】\n${afterLines.join('\n')}`,
    `【时间和地点】${delta.timeAdvance ? `时间推进 ${delta.timeAdvance.duration.amount} ${delta.timeAdvance.duration.unit}；` : ''}地点：${[...locations].map((id) => describeLocation(after, id)).join('；')}`,
    `【可写到的东西】${[...items].map((id) => describeItem(after, id)).join('；') || '无'}`,
  ].join('\n');
}

function cleanNarration(raw: string): string {
  const body = raw.includes('【正文】') ? raw.split('【正文】').pop() ?? raw : raw;
  return body
    .replace(/```[\s\S]*?```/g, '')
    .replace(/【[^】]{1,8}】/g, '')
    .replace(/\*\*/g, '')
    .replace(/^#{1,6}\s*/gmu, '')
    .replace(/^\s*(正文|叙事|输出)[:：]\s*/u, '')
    .trim();
}

function validateNarration(text: string, facts: string, after: WorldState, view: Id): { ok: boolean; reason: string } {
  if ([...text].length < 40) return { ok: false, reason: 'too_short' };
  // Third-person prose may use “他/她” for a whole paragraph without naming
  // the protagonist; absence of the literal name is not a fact error.

  // A field table is not prose: the page must not show field headings.
  const fieldLines = text.split(String.fromCharCode(10)).filter((line) => /^(时间|地点|人物|事件|变化|视角|场景)[:：]/u.test(line.trim()));
  if (fieldLines.length >= 2) return { ok: false, reason: 'structure_dump' };
  // Copying the fact brief back is the other failure mode of a small model.
  const probe = briefProbe(facts);
  if (probe && text.includes(probe)) return { ok: false, reason: 'copied_brief' };
  const numbers = text.match(/\d+/g) ?? [];
  for (const number of numbers) if (!facts.includes(number)) return { ok: false, reason: `unverified_number:${number}` };
  // Any known character/location/item the projector did not put in the input
  // must not appear by name. This catches the common small-model failure of
  // pulling a familiar name from its pretraining into a scene where that
  // character is not present.
  const known = [
    ...Object.values(after.initial.characters).map((entity) => entity.name),
    ...Object.values(after.initial.locations).map((entity) => entity.name),
    ...Object.values(after.initial.items).map((entity) => entity.name),
  ];
  for (const name of known) {
    if (name.length < 2 || facts.includes(name)) continue;
    if (text.includes(name)) return { ok: false, reason: `unprojected_entity:${name}` };
  }
  return { ok: true, reason: '' };
}

function locationIdCatalog(state: WorldState): string {
  return Object.keys(state.initial.locations).sort().map((id) => `${id}=${state.initial.locations[id].name}`).join('；');
}

function parseLineChanges(raw: string, state: WorldState): Json {
  const text = raw.trim();
  if (!text || /^NONE$/i.test(text)) return [];
  const deltas = new Map<Id, EntityDelta>();
  const appearanceSeq = new Map<Id, number>();
  const personalitySeq = new Map<Id, number>();
  for (const line of text.split(/\r?\n/)) {
    const parts = line.split('|').map((part) => part.trim());
    if (parts.length < 3) continue;
    const [id, field, ...rest] = parts;
    const value = rest.join('|').trim();
    if (!state.characters[id] && !state.items[id]) continue;
    let delta = deltas.get(id);
    if (!delta) { delta = { entityId: id }; deltas.set(id, delta); }
    if (field === 'position') {
      const [containerId, slotId] = value.split('/').map((part) => part.trim());
      if (!state.initial.locations[containerId]) continue;
      delta.positionSet = { containerId, slotId: slotId || null, relativeTo: null };
    } else if (field === 'sanity') {
      const number = Number(value);
      if (Number.isFinite(number)) delta.sanitySet = Math.max(0, Math.min(100, Math.round(number)));
    } else if (field === 'task' && state.characters[id]) {
      const owner = state.characters[id];
      const taskId = value.split(/\s+/)[0];
      if (owner.tasks[taskId]) delta.tasksAchieved = [...(delta.tasksAchieved ?? []), taskId];
    } else if (field === 'appearance' && value) {
      const n = (appearanceSeq.get(id) ?? 0) + 1;
      appearanceSeq.set(id, n);
      delta.appearanceChanges = [...(delta.appearanceChanges ?? []), { id: `appearance_${id}_${n}`, text: value, supersedes: [] }];
    } else if (field === 'personality' && value) {
      const n = (personalitySeq.get(id) ?? 0) + 1;
      personalitySeq.set(id, n);
      delta.personalityChanges = [...(delta.personalityChanges ?? []), { id: `personality_${id}_${n}`, text: value, supersedes: [] }];
    }
  }
  const stages: { stage: string; changes: Record<Id, EntityDelta> }[] = [];
  const order: { stage: string; fields: (keyof EntityDelta)[] }[] = [
    { stage: 'position', fields: ['positionSet'] },
    { stage: 'appearance', fields: ['appearanceChanges'] },
    { stage: 'tasks', fields: ['tasksAchieved'] },
    { stage: 'subtasks', fields: ['subtasksAdded'] },
    { stage: 'personality', fields: ['personalityChanges'] },
    { stage: 'sanity', fields: ['sanitySet'] },
  ];
  for (const { stage, fields } of order) {
    const changes: Record<Id, EntityDelta> = {};
    for (const [id, delta] of deltas) {
      const picked: EntityDelta = { entityId: id };
      for (const field of fields) if (delta[field] !== undefined) (picked as unknown as Record<string, unknown>)[field] = delta[field];
      if (Object.keys(picked).length > 1) changes[id] = picked;
    }
    if (Object.keys(changes).length) stages.push({ stage, changes });
  }
  return stages as unknown as Json;
}

const INTERACTION = /问|叫|喊|看|望|盯|递|给|拿|抓|推|拉|拽|撞|拦|挡|攻击|打|踢|开火|射击|威胁|提醒|告诉|回答|答应|拒绝|扶|抱|拍|碰|搜|找|救|帮|交换|谈判/u;
const MOVEMENT = /走|跑|移动|前往|走向|进入|退|撤|爬|穿过|绕过|离开|去|赶到|溜|冲|贴墙|靠近|靠近/u;

/** Facts that the alignment grader is allowed to require. Only the
 * protagonist and entities with a committed delta enter the packet; static
 * "everyone is here" facts would demand a roll-call that the scene language
 * never uses. */
function alignmentPacket(before: WorldState | null, delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }, after: WorldState): CommittedNarration {
  const facts: NarrationFact[] = [];
  const view = after.protagonistId;
  const changed = Object.keys(delta.entityDeltas ?? {});
  const ids = new Set<Id>([view, ...changed]);
  for (const id of ids) {
    const character = after.characters[id];
    if (!character) continue;
    const name = after.initial.characters[id]?.name;
    const previous = before?.characters[id];
    if (!name) continue;
    const d = delta.entityDeltas?.[id];
    if (d?.positionSet) {
      const fromId = previous?.position.containerId;
      const from = fromId ? before?.initial.locations[fromId]?.name : undefined;
      if (from && fromId) facts.push({ id: `${id}:position`, actorId: id, name, kind: 'moved', fromId, from, toId: character.position.containerId, to: locationName(after, character.position.containerId) });
    } else if (id === view) {
      facts.push({ id: `${id}:position`, actorId: id, name, kind: 'at', locationId: character.position.containerId, location: locationName(after, character.position.containerId) });
    }
    if (d?.sanitySet != null && previous) facts.push({ id: `${id}:sanity`, actorId: id, name, kind: 'sanity_changed', from: previous.sanity, to: character.sanity });
    for (const taskId of d?.tasksAchieved ?? []) {
      const task = character.tasks[taskId];
      if (task) facts.push({ id: `${id}:task:${taskId}`, actorId: id, name, kind: 'task_achieved', taskId, goal: task.goal });
    }
    for (const change of d?.personalityChanges ?? []) if (change.text) facts.push({ id: `${id}:personality:${change.id}`, actorId: id, name, kind: 'personality_changed', changeId: change.id, text: change.text });
  }
  return { anchor: { worldId: after.worldId, pointId: `local_${Date.now()}`, version: 0, stateDigest: '', previousPointId: null }, facts };
}

function factualNarration(before: WorldState | null, delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }, after: WorldState, view: Id, actionText = ''): string {
  const out: string[] = [];
  const name = after.initial.characters[view]?.name ?? view;
  const time = delta.timeAdvance;
  if (time) out.push(`时间过去了约${time.duration.amount}${timeUnit(time.duration.unit)}。`);
  const change = delta.entityDeltas?.[view];
  const room = roomOf(after, view);
  if (change?.positionSet) {
    const from = before ? locationName(before, before.characters[view]?.position.containerId ?? '') : '';
    const to = locationName(after, change.positionSet.containerId);
    const declared = actionText.trim().replace(/^我/u, name);
    out.push(`${declared && MOVEMENT.test(declared) ? endSentence(declared) : `${name}${from ? `从${from}` : ''}走到${to}。`}`);
  }
  const appearance = after.initial.locations[room]?.initialAppearance;
  if (appearance) out.push(`${locationName(after, room)}里，${firstClause(appearance)}。`);
  for (const id of visibleCharacters(after, view).filter((candidate) => candidate !== view)) {
    const other = after.initial.characters[id]?.name;
    if (!other) continue;
    const look = after.initial.characters[id]?.initialAppearance;
    out.push(`${other}在${locationName(after, roomOf(after, id))}${look ? `，${firstClause(look)}` : ''}。`);
  }
  for (const [id, entity] of Object.entries(delta.entityDeltas ?? {})) {
    const other = after.initial.characters[id]?.name ?? after.initial.items[id]?.name;
    if (!other) continue;
    for (const taskId of entity.tasksAchieved ?? []) {
      const goal = after.characters[id]?.tasks[taskId]?.goal;
      if (goal) out.push(`${other}完成了「${goal}」。`);
    }
    if (entity.sanitySet != null) out.push(`${other}的精神值变成 ${entity.sanitySet}。`);
  }
  if (!out.length) out.push(`${name}停在${locationName(after, room)}，没有新的变化。`);
  return out.join('');
}

function endSentence(text: string): string {
  return `${text.replace(/[。！？!?；;\s]+$/u, '')}。`;
}

function firstClause(text: string): string {
  return text.split(/[。；;]/u).slice(0, 2).join('，').replace(/[，,]\s*$/u, '').slice(0, 120);
}

function timeUnit(unit: TimeAdvance['duration']['unit']): string {
  return ({ second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年' } as Record<string, string>)[unit] ?? unit;
}

/** Drop unsupported sentences, then re-add the position/time facts the scene
 * must state. Alignment reports which sentence broke which rule, so the repair
 * needs no second pass over the model output. */
function pruneNarration(
  text: string,
  alignment: { violations: { sentence: string; kind: string }[]; omissions: string[] },
  after: WorldState,
  view: Id,
): { text: string; dropped: { reason: string; sentence: string }[] } {
  const hard = new Set(alignment.violations.map((violation) => violation.sentence.trim()));
  const dropped = alignment.violations.map((violation) => ({ reason: violation.kind, sentence: violation.sentence }));
  const kept: string[] = [];
  for (const raw of text.split(/(?<=[。！？!?])|\n+/u)) {
    const sentence = raw.trim();
    if (!sentence || hard.has(sentence)) continue;
    kept.push(sentence);
  }
  const body = kept.join('');
  const name = after.initial.characters[view]?.name ?? view;
  const place = locationName(after, roomOf(after, view));
  const positionOmitted = alignment.omissions.some((entry) => entry.includes('position'));
  const headText = positionOmitted || !body.includes(place) ? `${name}在${place}。` : '';
  return { text: `${headText}${body}`.replace(/\n{3,}/gu, '\n\n').trim(), dropped };
}

/** Longest brief slice to look for in the prose. Short fragments like a name
 * or a location are expected in any scene. */
function briefProbe(facts: string): string {
  const lines = facts.split(String.fromCharCode(10)).map((line) => line.trim()).filter((line) => line.length > 40);
  const longest = lines.sort((a, b) => b.length - a.length)[0] ?? '';
  return longest.slice(0, 28);
}


const STAGE_ORDER = ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity'];


/** Cut a truncated generation back to its last complete sentence. */
function finishSentences(text: string): string {
  const last = Math.max(text.lastIndexOf('。'), text.lastIndexOf('！'), text.lastIndexOf('？'), text.lastIndexOf('」'));
  return last > 40 ? text.slice(0, last + 1) : text;
}


/** Rooms the protagonist can reach in one point: the current room, its
 * parent, its siblings and its children, plus any room the player named. */
export function adjacentLocations(state: WorldState, current: Id, named: string[] = []): string {
  const locations = state.initial.locations;
  const parent = locations[current]?.parentLocationId ?? null;
  const ids = new Set<Id>([current]);
  if (parent) {
    ids.add(parent);
    for (const [id, location] of Object.entries(locations)) if (location.parentLocationId === parent) ids.add(id);
  }
  for (const [id, location] of Object.entries(locations)) if (location.parentLocationId === current) ids.add(id);
  for (const [id, location] of Object.entries(locations)) if (named.some((text) => text.includes(location.name))) ids.add(id);
  return [...ids].map((id) => `${id}=${locations[id]?.name ?? id}`).join('；');
}
