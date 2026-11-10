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
import { createActionHandlers, type HandlerResult } from './semantics/actions';
import { createSettlementHandlers, requireSettlementValue, continuationPolicy } from './semantics/settlement';
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
  /** Automatic rounds after one player action. Default 0: one action = one round. */
  maxAutoContinuations?: number;
  /** How many non-protagonist actors may open their own frozen group in one
   * round. Reactions to admitted threats are separate and always run. */
  maxAutonomousActors?: number;
  /** Raw streaming text for the current narration point. */
  onNarrationProgress?: (progress: { pointId: Id; raw: string; elapsedMs: number }) => void;
  onNarrationComplete?: (progress: { pointId: Id; raw: string; completion: CompletionEvidence }) => void;
  /** Test/evaluation hook: exposes the draft, raw model text and each repair
   * stage. Never used to make a product decision. */
  onNarrationDebug?: (debug: { pointId: Id; draft: string; raw: string; cleaned: string; pruned: string; supported: string; text: string; violations: string[]; attempts: number[] }) => void;
  onTask?: (task: ModelTask, key: string, detail: { ms: number; fallback: boolean; error?: string; raw?: string; promptChars?: number }) => void;
}

interface Generated { value: Json; raw: string; ms: number; fallback: boolean; error?: string }


export class LocalGameModel implements WorldModelPort {
  private readonly engine: InferenceEngine;
  private readonly narrationEngine: InferenceEngine;
  private readonly options: GameModelOptions;
  private roundCounter = 0;
  private lastPlayerInput = '';
  private lastResultsText = '';
  private autoContinuations = 0;
  private recentEvents: string[] = [];
  private readonly settlement;
  private readonly actionHandlers;

  constructor(engine: InferenceEngine, options: GameModelOptions = {}) {
    this.engine = engine;
    this.narrationEngine = options.narrationEngine ?? engine;
    this.options = options;
    this.settlement = createSettlementHandlers({ engine, options: {
      onTask: (task, key, detail) => this.options.onTask?.(task, key, detail),
      nextRoundId: () => `round_auto_${Date.now().toString(36)}_${++this.roundCounter}`,
      maxPromptChars: 11_000,
      sceneScope: true,
      continuation: this.options.maxAutoContinuations == null ? continuationPolicy : { ...continuationPolicy, maxAutoContinuations: this.options.maxAutoContinuations },
    } });
    this.actionHandlers = createActionHandlers({ engine, options: {
      recentEvents: () => this.recentEvents,
      onCall: (call) => this.options.onTask?.(call.task, call.key, {
        ms: call.elapsedMs, fallback: !call.decoded, error: call.error, raw: call.raw, promptChars: call.promptChars,
      }),
    } });
  }

  get info() { return this.engine.info; }

  resetAutoContinuations(): void { this.autoContinuations = 0; this.settlement.resetContinuation(); }

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
      if (task === 'continuation') return await this.continuation(key, input);
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
    const data = input as { actor?: Id; advance?: { inputText?: string | null; intentStatus?: string } | null; workingState?: WorldState };
    if (data.workingState && data.actor === data.workingState.protagonistId) {
      const text = data.advance?.inputText?.trim();
      if (text) this.lastPlayerInput = text;
    }
    // Scene budget: an unnamed same-room NPC still acts autonomously only
    // when the player's sentence puts them in play. Without this budget every
    // present actor becomes another frozen group and a single turn grows past
    // the readable-text wait; reactions still cover every admitted threat.
    if (data.workingState && data.actor && data.actor !== data.workingState.protagonistId) {
      if ((this.options.maxAutonomousActors ?? 1) <= 0) {
        return { value: { kind: 'skip' }, raw: '', ms: 0, fallback: false, error: 'autonomous_actor_budget' };
      }
      const name = data.workingState.initial.characters[data.actor]?.name ?? data.actor;
      const advanceText = data.advance?.inputText?.trim() || this.lastPlayerInput;
      if (!advanceText.includes(name)) {
        return { value: { kind: 'skip' }, raw: '', ms: 0, fallback: false, error: 'scene_budget_unnamed' };
      }
    }
    return this.reportAction(await this.actionHandlers.action(key, input));
  }

  private async targets(key: Id, input: Json): Promise<Generated> {
    return this.reportAction(await this.actionHandlers.targets(key, input));
  }

  private async reaction(key: Id, input: Json): Promise<Generated> {
    return this.reportAction(await this.actionHandlers.reaction(key, input));
  }

  private reportAction(result: HandlerResult): Generated {
    const error = result.issues.filter((issue) => issue.severity === 'error').map((issue) => issue.code).join(',') || undefined;
    this.options.onTask?.(result.task, result.key, {
      ms: result.elapsedMs, fallback: result.fallback, error, raw: result.raw,
    });
    return {
      value: result.value, raw: result.raw, ms: result.elapsedMs,
      fallback: result.fallback, error,
    };
  }

  private async results(key: Id, input: Json): Promise<Generated> {
    const outcome = await this.settlement.results(key, input);
    const value = requireSettlementValue(outcome);
    const state = (input as { workingState?: WorldState }).workingState;
    const lines = Object.entries(value).map(([id, text]) => {
      const name = state?.initial.characters[id]?.name ?? id;
      // A weak model sometimes answers the settlement with a state dump
      // ("id=… 位置=… 外貌=…"). Facts must be prose: drop field dumps rather
      // than feeding them into the narration brief and the page.
      const prose = text.split(/\n+/u).map((part) => part.trim())
        .filter((part) => part && !/id=/u.test(part) && !/^(位置|外貌|精神值|任务)[=：]/u.test(part));
      return prose.length ? `${name}：${prose.join('')}` : '';
    }).filter(Boolean);
    this.lastResultsText = /完成了刚才的动作|行动发生了，但没有产生新的结果/u.test(lines.join('；')) ? '' : lines.join('；');
    for (const line of lines) this.recentEvents.push(line);
    if (this.recentEvents.length > 4) this.recentEvents = this.recentEvents.slice(-4);
    return { value: value as unknown as Json, raw: outcome.raw, ms: outcome.ms, fallback: outcome.fallback, error: outcome.error };
  }

  private async updates(key: Id, input: Json): Promise<Generated> {
    const outcome = await this.settlement.updates(key, input);
    const value = requireSettlementValue(outcome);
    const state = (input as { workingState?: WorldState }).workingState;
    const results = (input as { results?: Record<Id, string> }).results ?? {};
    const stage = (input as { stage?: string }).stage;
    const merged = await this.injectMovement(state, value, results, stage);
    return { value: merged as unknown as Json, raw: outcome.raw, ms: outcome.ms, fallback: outcome.fallback, error: outcome.error };
  }

  /** A player sentence that walks to a named room is a movement the state must
   * reflect. The six-stage settlement leaves it to a free-text position scan,
   * which the small model often answers with "no change"; this asks the one
   * pick-from-a-list question it answers reliably and merges the result into
   * the position stage before the controller previews it. */
  private async injectMovement(state: WorldState | undefined, value: unknown, results: Record<Id, string>, stage: string | undefined): Promise<unknown> {
    if (!state || stage) return value;
    const view = state.protagonistId;
    if (!MOVEMENT.test(this.lastPlayerInput)) return value;
    const calls = Array.isArray(value) ? value as { stage: string; changes: Record<Id, EntityDelta> }[] : null;
    if (!calls) return value;
    const hasMove = calls.some((call) => call.changes?.[view]?.positionSet);
    if (hasMove) return value;
    const current = state.characters[view]?.position.containerId ?? '';
    const moved = await this.movementJudgement(state, results);
    if (!moved || moved === current) return value;
    const position: { stage: 'position'; changes: Record<Id, EntityDelta> } = {
      stage: 'position',
      changes: { [view]: { entityId: view, positionSet: { containerId: moved, slotId: null, relativeTo: null } } },
    };
    const index = calls.findIndex((call) => call.stage === 'position');
    if (index < 0) return [position, ...calls];
    const merged = { stage: 'position', changes: { ...calls[index].changes, ...position.changes } };
    return calls.map((call, at) => (at === index ? merged : call));
  }

  private async movementJudgement(state: WorldState, results: Record<Id, string>): Promise<Id | null> {
    const current = state.characters[state.protagonistId]?.position.containerId;
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
      const raw = await this.engine.complete(prompt, {
        maxTokens: 64, temperature: 0, timeoutMs: 60_000,
        jsonSchema: {
          type: 'object', additionalProperties: false, required: ['moved'],
          properties: { moved: { type: 'boolean' }, toLocationId: { type: ['string', 'null'] } },
        },
      });
      const text = raw.trim().replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/i, '');
      const start = text.indexOf('{');
      const end = text.lastIndexOf('}');
      if (start < 0 || end <= start) return null;
      const output = JSON.parse(text.slice(start, end + 1)) as { moved?: boolean; toLocationId?: string | null };
      const target = typeof output.toLocationId === 'string' ? output.toLocationId.trim() : '';
      if (output.moved !== true || !state.initial.locations[target] || target === current) return null;
      return target;
    } catch {
      return null;
    }
  }

  private async continuation(key: Id, input: Json): Promise<Generated> {
    // A one-action-per-round product setting is not a model judgement: with
    // automatic continuation switched off there is nothing to propose, so the
    // round is handed back without spending a model call (and without turning
    // a model hiccup into a failed round).
    if ((this.options.maxAutoContinuations ?? 0) <= 0) {
      return { value: { kind: 'handback', closedBy: 'model', cancelReason: null } as unknown as Json, raw: '', ms: 0, fallback: false, error: 'continuation_disabled' };
    }
    const outcome = await this.settlement.continuation(key, input);
    const value = requireSettlementValue(outcome);
    return { value: value as unknown as Json, raw: outcome.raw, ms: outcome.ms, fallback: outcome.fallback, error: outcome.error };
  }

  private async narration(key: Id, input: Json): Promise<Generated> {
    const data = input as { pointId?: Id; before?: WorldState | null; delta?: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }; after?: WorldState; perspective?: string };
    const after = data.after;
    if (!after) throw new Error('narration without after state');
    const pointId = data.pointId ?? key;
    const view = after.protagonistId;
    const started = performance.now();
    const before = data.before ?? null;
    const delta = data.delta ?? {};
    const draft = factualNarration(before, delta, after, view, this.lastPlayerInput, this.lastResultsText);
    const brief = this.options.narrationMode === 'instruct'
      ? instructNarrationInput(before, delta, after, view, this.lastPlayerInput, this.lastResultsText, draft)
      : { prompt: legacyNarrationInput(before, delta, after, view), brief: legacyNarrationInput(before, delta, after, view) };
    const packet = alignmentPacket(before, delta, after);
    const alignmentOptions = {
      roster: Object.values(after.initial.characters).map((entity) => entity.name),
      locations: Object.values(after.initial.locations).map((entity) => entity.name),
      time: delta.timeAdvance?.duration ?? null,
      knownPositions: visibleCharacters(after, view).filter((id) => id !== view).map((id) => ({ name: after.initial.characters[id]?.name ?? id, location: locationName(after, roomOf(after, id)) })),
      allowedEvents: EVENT_VERBS.filter((verb) => this.lastPlayerInput.includes(verb)),
    };

    const evaluate = (raw: string) => {
      const cleaned = finishSentences(cleanNarration(raw).replace(/※/g, String.fromCharCode(10, 10))).trim();
      const validation = validateNarration(cleaned, brief.brief, after, view);
      const alignment = alignNarration(packet, cleaned, alignmentOptions);
      // Sentence-level repair keeps the literary text and only removes the
      // claims the settled state cannot support. Whole-text rejection made the
      // page show a state summary almost every round, which is worse than a
      // slightly shorter scene.
      const pruned = pruneNarration(cleaned, alignment, after, view);
      const supported = supportNarration(bindNarrationAttributes(pruned.text, after, view), draft);
      return { raw, cleaned, pruned: pruned.text, supported, dropped: pruned.dropped, validation };
    };

    const generate = async (prompt: string, temperature: number): Promise<{ raw: string; error?: string }> => {
      try {
        const raw = await this.narrationEngine.complete(this.options.narrationMode === 'instruct' ? chatml(prompt) : prompt, {
          maxTokens: this.options.narrationMaxTokens ?? 240, temperature,
          timeoutMs: this.options.narrationTimeoutMs ?? 150_000,
          onProgress: (progress) => this.options.onNarrationProgress?.({ pointId, raw: progress.raw, elapsedMs: performance.now() - started }),
          ...(this.options.narrationMode === 'instruct' ? { stop: ['<|im_end|>'] } : {}),
        });
        return { raw };
      } catch (error) {
        // A length-limited generation still carries usable prose: keep the
        // complete sentences instead of throwing the whole point away.
        const partial = error instanceof IncompleteGenerationError ? error.completion.raw : '';
        const message = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
        return { raw: partial, error: message };
      }
    };

    // Two bounded attempts: a free scene first, then a strictly drafted
    // rewrite when the first answer cannot be supported by settled facts. The
    // player sees the better accepted candidate, not the last one generated.
    const attempts: ReturnType<typeof evaluate>[] = [];
    const first = await generate(brief.prompt, this.options.narrationTemperature ?? 0.45);
    attempts.push(evaluate(first.raw));
    if ([...attempts[0].supported].length < 80 && this.options.narrationMode === 'instruct') {
      const repair = instructNarrationInput(before, delta, after, view, this.lastPlayerInput, this.lastResultsText, draft, 'repair');
      const second = await generate(repair.prompt, Math.min(0.3, this.options.narrationTemperature ?? 0.45));
      attempts.push(evaluate(second.raw));
    }
    const best = attempts.reduce((left, right) => ([...right.supported].length > [...left.supported].length ? right : left));
    // The support filter works on wording; alignment works on claims. A
    // sentence can survive the first and still assert an uncommitted result,
    // so prune again on the accepted candidate until it stops contradicting
    // the settled facts (bounded: each pass only removes sentences).
    let safe = best.supported;
    let finalAlignment = alignNarration(packet, safe, alignmentOptions);
    for (let pass = 0; pass < 3 && finalAlignment.violations.length > 0; pass += 1) {
      safe = pruneNarration(safe, finalAlignment, after, view).text;
      finalAlignment = alignNarration(packet, safe, alignmentOptions);
    }
    const accepted = best.dropped.length === 0 && best.validation.ok && finalAlignment.ok && [...safe].length >= 80;
    const text = accepted ? safe : draft;
    const reason = accepted ? undefined : [...new Set([
      best.validation.reason,
      ...best.dropped.map((entry) => entry.reason),
      ...finalAlignment.violations.map((entry) => entry.kind),
      'low_support',
    ])].filter(Boolean).join(',');
    this.options.onNarrationDebug?.({ pointId, draft, raw: best.raw, cleaned: best.cleaned, pruned: best.pruned, supported: best.supported, text, violations: finalAlignment.violations.map((entry) => entry.kind), attempts: attempts.map((entry) => [...entry.supported].length) });
    this.options.onTask?.('narration', key, { ms: performance.now() - started, fallback: !accepted, error: reason, raw: text, promptChars: brief.prompt.length });
    this.options.onNarrationComplete?.({ pointId, raw: text, completion: { raw: text, finishReason: accepted ? 'stop' : 'drafted', firstTokenMs: null, wallMs: performance.now() - started } });
    return { value: text as unknown as Json, raw: text, ms: performance.now() - started, fallback: !accepted, error: reason };
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

function chatml(prompt: string): string {
  return `<|im_start|>user
${prompt}<|im_end|>
<|im_start|>assistant
`;
}

function cleanNarration(raw: string): string {
  const body = raw.includes('【正文】') ? raw.split('【正文】').pop() ?? raw : raw;
  return body
    .replace(/```[\s\S]*?```/g, '')
    .replace(/【[^】]{1,8}】/g, '')
    .replace(/\*\*/g, '')
    .replace(/^#{1,6}\s*/gmu, '')
    .replace(/^\s*(正文|叙事|输出)[:：]\s*/u, '')
    .replace(/^[\s，。、；：！？·]+/u, '')
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

function factualNarration(before: WorldState | null, delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }, after: WorldState, view: Id, actionText = '', resultsText = ''): string {
  const out: string[] = [];
  const name = after.initial.characters[view]?.name ?? view;
  const time = delta.timeAdvance;
  if (time) out.push(`时间过去了约${time.duration.amount}${timeUnit(time.duration.unit)}。`);
  const change = delta.entityDeltas?.[view];
  const room = roomOf(after, view);
  const declared = actionText.trim().replace(/^我/u, name);
  if (change?.positionSet) {
    const from = before ? locationName(before, before.characters[view]?.position.containerId ?? '') : '';
    const to = locationName(after, change.positionSet.containerId);
    out.push(`${declared && MOVEMENT.test(declared) ? endSentence(declared) : `${name}${from ? `从${from}` : ''}走到${to}。`}`);
  }
  if (declared && !(change?.positionSet && MOVEMENT.test(declared))) out.push(endSentence(declared));
  for (const settled of resultsText.split('；').map((part) => part.trim()).filter(Boolean)) {
    if (/完成了刚才的动作|行动发生了，但没有产生新的结果|向.+移动/u.test(settled)) continue;
    const sentence = endSentence(settled.replace(new RegExp(`^${name}`, 'u'), name));
    if (!out.includes(sentence)) out.push(sentence);
  }
  const appearance = after.initial.locations[room]?.initialAppearance;
  if (appearance) out.push(`${locationName(after, room)}里，${sentenceEnd(shortClause(appearance, 96))}`);
  const others = visibleCharacters(after, view).filter((candidate) => candidate !== view).slice(0, 2);
  for (const id of others) {
    const other = after.initial.characters[id]?.name;
    if (!other) continue;
    const look = after.initial.characters[id]?.initialAppearance;
    out.push(`${other}在${locationName(after, roomOf(after, id))}${look ? `，${shortClause(look, 52)}` : ''}。`);
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

function bigramsOf(text: string): Set<string> {
  const stripped = text.replace(/[\s，。！？；：、,.!?;:"“”「」『』（）()]/gu, '');
  const out = new Set<string>();
  for (let index = 0; index + 1 < stripped.length; index += 1) out.add(stripped.slice(index, index + 2));
  return out;
}

/** Keep only sentences whose wording is substantially present in the settled
 * draft. A small model can produce a fluent sentence that invents a gesture,
 * a line of dialogue or a memory; those sentences have little character-bigram
 * overlap with the draft and are dropped before the player sees them. */
function bindNarrationAttributes(text: string, after: WorldState, view: Id): string {
  const protectedPhrases: { name: string; phrase: string }[] = [];
  for (const id of visibleCharacters(after, view)) {
    if (id === view) continue;
    const name = after.initial.characters[id]?.name;
    if (!name) continue;
    const looks = [after.initial.characters[id].initialAppearance, ...activeText(after.characters[id]?.appearanceChanges ?? [])];
    for (const look of looks) {
      for (const clause of look.split(/[，,；;。]/u)) {
        const phrase = clause.trim();
        if ([...phrase].length >= 4) protectedPhrases.push({ name, phrase });
      }
    }
  }
  return text.split(/(?<=[。！？!?])|\n+/u).filter((raw) => {
    const sentence = raw.trim();
    if (!sentence) return false;
    const unbound = protectedPhrases.filter(({ name, phrase }) => !sentence.includes(name)
      && (sentence.includes(phrase) || sentence.includes([...phrase].slice(0, 8).join(''))));
    return unbound.length === 0;
  }).join('').trim();
}

function supportNarration(text: string, draft: string): string {
  const source = bigramsOf(draft);
  if (!source.size) return '';
  const kept: string[] = [];
  for (const raw of text.split(/(?<=[。！？!?])|\n+/u)) {
    const sentence = raw.trim();
    if (!sentence) continue;
    if (/[「」“”"]/u.test(sentence) && !draft.includes(sentence.replace(/[「」“”"]/gu, ''))) continue;
    const grams = bigramsOf(sentence);
    if (grams.size < 6) { kept.push(sentence); continue; }
    let shared = 0;
    for (const gram of grams) if (source.has(gram)) shared += 1;
    if (shared / grams.size >= 0.12) kept.push(sentence);
  }
  return kept.join('').replace(/\n{3,}/gu, '\n\n').trim();
}

function sentenceEnd(text: string): string {
  return /[。！？!?…]$/u.test(text) ? text : `${text}。`;
}

function firstFeature(text: string, max: number): string {
  const first = firstClause(text).split(/[，,]/u)[0]?.trim() ?? '';
  return [...first].length > max ? `${[...first].slice(0, max).join('')}……` : first;
}

function shortClause(text: string, max: number): string {
  const clean = firstClause(text).replace(/[，,、\s]+$/u, '');
  if ([...clean].length <= max) return clean;
  const cut = [...clean].slice(0, max).join('');
  const at = Math.max(cut.lastIndexOf('，'), cut.lastIndexOf('、'));
  return `${(at > 8 ? cut.slice(0, at) : cut).replace(/[，,、\s]+$/u, '')}……`;
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
  const normalize = (value: string) => value.replace(/[。！？!?\s]+/gu, '');
  const hard = new Set(alignment.violations.map((violation) => normalize(violation.sentence)));
  const dropped = alignment.violations.map((violation) => ({ reason: violation.kind, sentence: violation.sentence }));
  const kept: string[] = [];
  for (const raw of text.split(/(?<=[。！？!?])|\n+/u)) {
    const sentence = raw.trim();
    if (!sentence || hard.has(normalize(sentence))) continue;
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
