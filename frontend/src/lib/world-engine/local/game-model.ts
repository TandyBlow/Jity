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
import { IncompleteGenerationError } from '../runtime/engine';
import type { CommittedNarration, NarrationFact } from '../runtime/committed-narration';
import { taskOutputSchema } from '../runtime/output-schema';
import { createActionHandlers, type HandlerResult } from './semantics/actions';
import { createNarrationRunner, type NarrationRunner } from './narration-candidates/selection';
import { requireSettlementValue } from './semantics/settlement';
import { createSettlementModelPort, type PortSubmission, type SettlementModelPort, type SettlementPortSummary } from './turn-execution';
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
  /** Internal narration candidate selection. `auto` only offers candidates
   * whose real-model evidence is positive, so the shipped default changes
   * nothing until one is accepted; the named routes exist for evaluation and
   * are never a player-visible setting. */
  narrationCandidate?: 'auto' | 'trained' | 'instruct' | 'constrained' | 'builtin';
  /** Constrained route only: `program` never calls the model, `model` writes
   * one verified beat per call. Internal. */

  /** Trained route only: whole-scene vs beats. Internal evaluation switch. */
  trainedMode?: 'beats' | 'scene';
  /** Trained whole-scene prompt shape. `serialized` is the training shape for
   * the fine-tuned checkpoints; `prose-facts` is the closed-book shape measured
   * for the deployable instruct model. Internal. */
  trainedPromptShape?: 'serialized' | 'prose-facts';
  /** Raw streaming text for the current narration point. */
  onNarrationProgress?: (progress: { pointId: Id; raw: string; elapsedMs: number }) => void;
  /** `fallback` is true when the shown text came from the program composer (a
   * labelled downgrade) rather than model prose the candidate's own gate
   * accepted. `source: 'model'` is that gate's verdict, never independent
   * quality review. The page must not count a fallback as readable model text. */
  onNarrationComplete?: (progress: {
    pointId: Id; raw: string; completion: CompletionEvidence; fallback: boolean;
    /** `mixed` = some sentences are verified model prose and some are program
     * realizations; never counted as fully model-written. */
    source: 'model' | 'program' | 'mixed' | 'draft';
    segments?: Array<{ id: string; kind: string; source: string; text: string }>;
  }) => void;
  /** Test/evaluation hook: the raw model answer and the prompt it answered.
   * Never used to make a product decision. */
  onNarrationDebug?: (debug: {
    pointId: Id; raw: string; text: string;
    /** Every model attempt's raw text, in order. */
    rawAttempts: string[];
    prompt: string;
  }) => void;
  /** Internal evidence sink for candidate runs: candidate id, grade, per-beat
   * segments and the candidate's own attempt record. Never rendered. */
  onNarrationEvidence?: (record: Record<string, unknown>) => void;
  onTask?: (task: ModelTask, key: string, detail: {
    ms: number; fallback: boolean; error?: string; raw?: string; promptChars?: number;
    /** Per-stage milliseconds for a multi-stage (updates) call. */
    stageMs?: Record<string, number>;
    stages?: string[];
    /** Affected-projection scope from the updates ledger. */
    scope?: { mode?: string; affectedCharacters?: number; unaffectedCharacters?: number; affectedTaskIds?: string[]; unaffectedTaskIds?: string[]; taskRows?: number } | null;
  }) => void;
}

interface Generated { value: Json; raw: string; ms: number; fallback: boolean; error?: string }

/** Violations that mean the text asserts something the settlement did not
 * produce. Style, length and wording are not in this set. */
const FATAL_ALIGNMENT = new Set([
  'added_event', 'actor_swap', 'direction_reversed', 'wrong_number',
  'movement_without_fact', 'task_claimed_without_fact', 'state_claim_without_fact',
]);


export class LocalGameModel implements WorldModelPort {
  private readonly engine: InferenceEngine;
  private readonly narrationEngine: InferenceEngine;
  /** One abort scope per player turn. Every engine port created here attaches
   * this signal, so a cancel stops the device work instead of only discarding
   * the answer the controller's cancel gate would have refused. */
  private turnAbort: AbortController | null = null;
  private readonly options: GameModelOptions;
  private roundCounter = 0;
  private lastPlayerInput = '';
  private lastResultsText = '';
  /** Structured settled results for the current point (04's actor/action/target/
   * outcome records), used by the candidate so it checks meaning, not wording. */
  private lastSettledFacts: Array<{ text: string; actorId: string; targetId?: string; action?: string; outcome: 'completed' | 'failed' | 'blocked' | 'unaffected'; implicit?: true }> = [];
  private recentEvents: string[] = [];
  private readonly narrationRunner: NarrationRunner | null;
  /** Last accepted prose (model or candidate). Only real prose is fed back as
   * continuation context; program/ledger paragraphs never are. */
  private readonly settlement: SettlementModelPort;
  private readonly actionHandlers;

  constructor(engine: InferenceEngine, options: GameModelOptions = {}) {
    // The handlers below keep their own engine references, so they get the
    // same abort-scoped port as the direct calls in this class.
    const scoped = (inner: InferenceEngine): InferenceEngine => ({
      get info() { return inner.info; },
      load: (loadOptions) => inner.load(loadOptions),
      dispose: () => inner.dispose(),
      complete: (prompt, completeOptions) => {
        const signal = completeOptions?.signal ?? this.turnAbort?.signal;
        if (signal?.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'));
        return inner.complete(prompt, signal ? { ...completeOptions, signal } : completeOptions);
      },
    });
    const semanticEngine = scoped(engine);
    const narrationPort = scoped(options.narrationEngine ?? engine);
    this.engine = semanticEngine;
    this.narrationEngine = narrationPort;
    this.options = options;
    // Lane 04's settlement port owns results/updates (six stages) and the
    // continuation judgement. A policy stop is a visible stop; there is no
    // product-side "one action per round" switch and no fabricated handback.
    this.settlement = createSettlementModelPort(semanticEngine, {
      onTask: (task, key, detail) => this.options.onTask?.(task, key, detail),
      nextRoundId: () => `round_auto_${Date.now().toString(36)}_${++this.roundCounter}`,
      // The appearance stage measures 7877 chars on the shipped world; a retry
      // with feedback is ~7970. The guard must leave room for the repair while
      // still refusing a runaway prompt (lane 04's measured numbers).
      maxPromptChars: 11_000,
    });
    this.narrationRunner = (options.narrationCandidate ?? 'auto') === 'builtin'
      ? null
      : createNarrationRunner({
        engine: narrationPort,
        candidate: options.narrationCandidate ?? 'auto',
        ...(options.trainedMode ? { trainedMode: options.trainedMode } : {}),
        ...(options.trainedPromptShape ? { trainedPromptShape: options.trainedPromptShape } : {}),
        // The page's chat model expects one templated user turn; the candidates
        // send plain text, so the runner wraps them the same way.
        engineTemplate: options.narrationMode === 'instruct' ? 'chatml' : 'none',
        temperature: options.narrationTemperature ?? 0.45,
        maxTokens: options.narrationMaxTokens ?? 240,
        timeoutMs: options.narrationTimeoutMs ?? 150_000,
        // Variable-length contract: a short complete paragraph is allowed, so
        // candidates only reject a near-empty string, not a scene under a
        // fixed character count.
        minChars: 20,
      });
    this.actionHandlers = createActionHandlers({ engine: semanticEngine, options: {
      recentEvents: () => this.recentEvents,
      onCall: (call) => this.options.onTask?.(call.task, call.key, {
        ms: call.elapsedMs, fallback: !call.decoded, error: call.error, raw: call.raw, promptChars: call.promptChars,
      }),
    } });
  }

  get info() { return this.engine.info; }

  /** Open a fresh abort scope at the start of a player turn. */
  beginTurn(): void { this.turnAbort = new AbortController(); }

  /** Abort in-flight inference for the current turn. The controller's cancel
   * command still owns the state conclusion; this only stops device work. The
   * aborted scope stays in place so a late task cannot start a fresh generation
   * after the cancel; `beginTurn()` opens the next scope. */
  abortTurn(): void { this.turnAbort?.abort(); }

  /** Player-submission account for the settlement side: which calls ran, per
   * stage, with the real milliseconds. Internal evidence, not page text. */
  beginSubmission(inputText: string): void { this.settlement.beginSubmission(inputText); }
  endSubmission(): PortSubmission | null { return this.settlement.endSubmission(); }
  settlementSummary(): SettlementPortSummary { return this.settlement.summary(); }
  resetSettlement(): void { this.settlement.reset(); }

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
    // Every actor the controller freezes is judged; the old "unnamed NPC is
    // skipped" budget was a product shortcut, not a model decision. Scene scope
    // for those judgements is owned by the settlement port, not this gate.
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
    const started = performance.now();
    const value = await this.settlement.generate('results', key, input) as Record<Id, string>;
    const outcome = { raw: '', ms: performance.now() - started, fallback: false, error: undefined as string | undefined };
    const state = (input as { workingState?: WorldState }).workingState;
    const lines = Object.entries(value).map(([id, text]) => {
      const name = state?.initial.characters[id]?.name ?? id;
      // A weak model sometimes answers the settlement with a state dump
      // ("id=… 位置=… 外貌=…"). Facts must be prose: drop field dumps rather
      // than feeding them into the narration brief and the page.
      const prose = text.split(/\n+/u).map((part) => part.trim())
        .filter((part) => part && !/id=/u.test(part) && !/^(位置|外貌|精神值|任务)[=：]/u.test(part));
      const body = prose.join('').replace(new RegExp(`^${name}[：:，,]?`, 'u'), '');
      return body ? `${name}：${body}` : '';
    }).filter(Boolean);
    // Settlement-internal wording is not story material. Lane 04's results
    // step falls back to "本组结算未能确认新的结果。" and the action lane uses
    // "无判定"; both used to leak into the program prose as if a character said
    // them. They stay out of the narration brief and the recent events.
    const internal = /本组结算未能确认|未能确认新的结果|无判定|没有产生新的结果|完成了刚才的动作/u;
    const story = lines.filter((line) => !internal.test(line));
    this.lastResultsText = internal.test(lines.join('；')) ? '' : story.join('；');
    // 04's structured records are the authoritative description of what the
    // settlement produced; the free-text line above is only its rendering.
    this.lastSettledFacts = this.settlement.settledFacts().map((fact) => ({
      text: fact.text,
      actorId: fact.actorId,
      ...(fact.targetId ? { targetId: fact.targetId } : {}),
      ...(fact.action ? { action: fact.action } : {}),
      outcome: fact.outcome,
      ...(fact.implicit ? { implicit: true as const } : {}),
    }));
    for (const line of story) this.recentEvents.push(line);
    if (this.recentEvents.length > 4) this.recentEvents = this.recentEvents.slice(-4);
    return { value: value as unknown as Json, raw: outcome.raw, ms: outcome.ms, fallback: outcome.fallback, error: outcome.error };
  }

  private async updates(key: Id, input: Json): Promise<Generated> {
    const started = performance.now();
    const value = await this.settlement.generate('updates', key, input);
    const state = (input as { workingState?: WorldState }).workingState;
    const results = (input as { results?: Record<Id, string> }).results ?? {};
    const stage = (input as { stage?: string }).stage;
    const merged = await this.injectMovement(state, value, results, stage);
    return { value: merged as unknown as Json, raw: '', ms: performance.now() - started, fallback: false };
  }

  /** A player sentence that walks to a named room is a movement the state must
   * reflect. The six-stage settlement leaves it to a free-text position scan,
   * which the small model often answers with "no change"; this asks the one
   * pick-from-a-list question it answers reliably and merges the result into
   * the position stage before the controller previews it. */
  private async injectMovement(state: WorldState | undefined, value: unknown, results: Record<Id, string>, stage: string | undefined): Promise<unknown> {
    if (!state || stage) return value;
    const view = state.protagonistId;
    if (!/走|跑|移动|前往|走向|进入|退|撤|爬|穿过|绕过|离开|去|赶到|溜|冲|贴墙|靠近/u.test(this.lastPlayerInput)) return value;
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
    const named = Object.values(state.initial.locations).map((location) => location.name).filter((name) => name && this.lastPlayerInput.includes(name));
    const candidates = adjacentLocations(state, current, [this.lastPlayerInput]);
    const prompt = [
      '你是中文跑团游戏的位置判断器。只输出 JSON。',
      '判断主角在这一回合结束后是否换了地点。只有主角真的移动到别处才算；原地说话、观察、等待都不算。',
      `主角：${describeCharacter(state, state.protagonistId, false)}`,
      `玩家输入：${this.lastPlayerInput}`,
      `结算结果：${Object.values(results).join('；') || '（无）'}`,
      `候选地点：${candidates}`,
      ...(named.length === 1 ? [`玩家这一句只点名了一个地点：${named[0]}。只回答他去没去那里。`] : []),
      ...(named.length ? [`玩家句子里点名的地点：${named.join('、')}。句子点名它就是要走过去，除非结果明确写他被拦住没走成。`] : []),
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
      if (output.moved !== true) return null;
      // When the player's own sentence names exactly one location, that name is
      // the destination. Letting the model re-pick from the adjacency list made
      // it answer with the parent area («器材棚» became «演习区»), which moved
      // the protagonist to the wrong place.
      const fixed = named.length === 1
        ? Object.values(state.initial.locations).find((location) => location.name === named[0])?.id ?? null
        : null;
      const target = fixed ?? (typeof output.toLocationId === 'string' ? output.toLocationId.trim() : '');
      if (!state.initial.locations[target] || target === current) return null;
      return target;
    } catch {
      return null;
    }
  }

  private async continuation(key: Id, input: Json): Promise<Generated> {
    // The continuation judgement is lane 04's port. A policy stop comes back as
    // an explicit stop conclusion, never as a fabricated handback.
    const started = performance.now();
    const value = await this.settlement.generate('continuation', key, input);
    return { value, raw: '', ms: performance.now() - started, fallback: false };
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

    // Candidate path: one settled point in, the candidate's own beat text out.
    // Nothing here inspects, refuses, rewrites or replaces that text.
    if (this.narrationRunner) {
      const adopted = await this.adoptNarrationCandidate(pointId, before, delta, after);
      if (adopted) return adopted;
    }

    // In-model writer: one call with the settled state as its only material.
    const brief = this.options.narrationMode === 'instruct'
      ? instructNarrationInput(before, delta, after, view, this.lastPlayerInput, this.lastResultsText)
      : { prompt: legacyNarrationInput(before, delta, after, view), brief: legacyNarrationInput(before, delta, after, view) };
    let raw = '';
    let error: string | undefined;
    try {
      raw = await this.narrationEngine.complete(this.options.narrationMode === 'instruct' ? chatml(brief.prompt) : brief.prompt, {
        maxTokens: this.options.narrationMaxTokens ?? 240,
        temperature: this.options.narrationTemperature ?? 0.45,
        timeoutMs: this.options.narrationTimeoutMs ?? 150_000,
        onProgress: (progress) => {
          // The page shows the model's own text while it is written. There is no
          // sentence filter in the stream.
          if (progress.raw.trim()) this.options.onNarrationProgress?.({ pointId, raw: progress.raw, elapsedMs: performance.now() - started });
        },
        ...(this.options.narrationMode === 'instruct' ? { stop: ['<|im_end|>'] } : {}),
      });
    } catch (caught) {
      if (caught instanceof IncompleteGenerationError) {
        // A length-limited generation still returned text: it is the content.
        raw = caught.completion.raw;
      } else {
        // A transport/model failure is a run error, not a reason to invent prose.
        throw caught;
      }
    }
    const text = protocolText(raw);
    const empty = text.trim().length === 0;
    this.options.onNarrationDebug?.({ pointId, raw, text, rawAttempts: [raw], prompt: brief.prompt });
    this.options.onTask?.('narration', key, {
      ms: performance.now() - started, fallback: false,
      ...(empty ? { error: 'empty_model_output' } : {}),
      raw: text, promptChars: brief.prompt.length,
    });
    if (empty) {
      // The only non-content case: no model text. The page shows a status note;
      // no program narration is written.
      this.options.onNarrationComplete?.({
        pointId, raw: '',
        completion: { raw, finishReason: 'stop', firstTokenMs: null, wallMs: performance.now() - started },
        fallback: false, source: 'model', segments: [],
      });
      return { value: '' as unknown as Json, raw, ms: performance.now() - started, fallback: false, error: 'empty_model_output' };
    }
    this.options.onNarrationComplete?.({
      pointId, raw: text,
      completion: { raw: text, finishReason: 'stop', firstTokenMs: null, wallMs: performance.now() - started },
      fallback: false, source: 'model',
    });
    return { value: text as unknown as Json, raw: text, ms: performance.now() - started, fallback: false };
  }

  /** Run the configured candidate for this point. The candidate's text is used
   * exactly as returned; only an empty answer falls through. */
  private async adoptNarrationCandidate(
    pointId: Id,
    before: WorldState | null,
    delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> },
    after: WorldState,
  ): Promise<Generated | null> {
    if (!this.narrationRunner) return null;
    const result = await this.narrationRunner.generate({
      pointId,
      before,
      delta,
      after,
      playerInput: this.lastPlayerInput,
      settledResults: this.lastResultsText ? [this.lastResultsText] : [],
      settledFacts: this.lastSettledFacts,
    }, (state) => this.options.onNarrationProgress?.({ pointId, raw: state.text, elapsedMs: state.elapsedMs }));
    if (result.kind !== 'adopted') {
      return null;
    }
    this.options.onTask?.('narration', pointId, {
      ms: result.timings.totalMs, fallback: false, raw: result.text, promptChars: result.promptChars,
    });
    this.options.onNarrationEvidence?.({
      pointId, candidateId: result.candidateId, route: result.route,
      strategyVersion: result.strategyVersion, segments: result.segments,
      timings: result.timings, detail: result.detail ?? null,
    });
    this.options.onNarrationComplete?.({
      pointId, raw: result.text, completion: result.completion, fallback: false, source: 'model', segments: result.segments,
    });
    return { value: result.text as unknown as Json, raw: result.text, ms: result.timings.totalMs, fallback: false };
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

/** Protocol framing only: chat-template tokens and the prompt's 【正文】 marker
 * are not story content. The text itself is returned untouched — no sentence or
 * character is removed for style, facts or length. */
function protocolText(raw: string): string {
  const marker = String.fromCharCode(0x3010) + '正文' + String.fromCharCode(0x3011);
  let text = raw.includes(marker) ? raw.split(marker).pop() ?? raw : raw;
  for (const token of ['<|im_end|>', '<|im_start|>', '<|endoftext|>']) {
    text = text.split(token).join('');
  }
  return text;
}

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
