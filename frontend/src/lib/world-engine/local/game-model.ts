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
import { createNarrationRunner, type NarrationRunner } from './narration-candidates/selection';
import { requireSettlementValue } from './semantics/settlement';
import { createSettlementModelPort, type PortSubmission, type SettlementModelPort, type SettlementPortSummary } from './turn-execution';
import { describeCharacter, describeDelta, describeItem, describeLocation, instructNarrationInput, legacyNarrationInput, locationName, roomName, roomOf, sameRoomItems, taskText, visibleCharacters, activeText } from './prompt';
import { inventedObjectActions } from './narration-generation/licensed-action';

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
  constrainedMode?: 'program' | 'model';
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
  /** Test/evaluation hook: exposes the draft, raw model text and each repair
   * stage. Never used to make a product decision. */
  onNarrationDebug?: (debug: {
    pointId: Id; draft: string; raw: string; cleaned: string; pruned: string; supported: string; text: string;
    violations: string[]; attempts: number[];
    /** Every model attempt's raw text, in order. Kept separately from the
     * program draft so no one mistakes the draft for model output. */
    rawAttempts: string[];
    /** Share of accepted sentences that already appear verbatim in the program
     * draft that was shown to the model. High values mean the "model text" is an
     * echo of the draft, not independent generation. */
    draftEcho: number;
    programFallback: boolean;
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
  private lastAcceptedNarration: string | null = null;
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
        ...(options.constrainedMode ? { constrainedMode: options.constrainedMode } : {}),
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

  /** Alignment inputs shared by the in-model writer and the independent
   * candidate gate, so both judge the same committed facts with same rules. */
  private alignmentOptionsFor(
    before: WorldState | null,
    delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> },
    after: WorldState,
  ) {
    const view = after.protagonistId;
    return {
      roster: Object.values(after.initial.characters).map((entity) => entity.name),
      locations: Object.values(after.initial.locations).map((entity) => entity.name),
      time: delta.timeAdvance?.duration ?? null,
      knownPositions: visibleCharacters(after, view).filter((id) => id !== view)
        .map((id) => ({ name: after.initial.characters[id]?.name ?? id, location: locationName(after, roomOf(after, id)) })),
      allowedEvents: EVENT_VERBS.filter((verb) => this.lastPlayerInput.includes(verb)),
    };
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

    // Candidate path: one settled point in, one verified scene out. A rejected,
    // cancelled or unavailable candidate returns null and the in-model writer
    // below keeps the round; an accepted program scene is submitted with the
    // labelled downgrade flag, never as a quality claim.
    if (this.narrationRunner) {
      const adopted = await this.adoptNarrationCandidate(pointId, before, delta, after);
      if (adopted) return adopted;
    }
    const brief = this.options.narrationMode === 'instruct'
      ? instructNarrationInput(before, delta, after, view, this.lastPlayerInput, this.lastResultsText, draft)
      : { prompt: legacyNarrationInput(before, delta, after, view), brief: legacyNarrationInput(before, delta, after, view) };
    const packet = alignmentPacket(before, delta, after);
    const alignmentOptions = this.alignmentOptionsFor(before, delta, after);

    const sceneNamesList = sceneNames(after, view);
    const protagonistName = after.initial.characters[view]?.name ?? view;
    const acceptCandidate = (candidate: ReturnType<typeof evaluate>): boolean => {
      if (!candidate.validation.ok) return false;
      const audit = proseAudit(candidate.supported, protagonistName);
      const grounding = groundingRatio(candidate.supported, sceneNamesList);
      // The narration contract is 160–240 chars; a supported scene shorter than
      // 140 is a short summary, not the contracted paragraph.
      return audit.ok && grounding.ratio >= 0.5 && grounding.count >= 2;
    };

    const entityNames = [
      ...Object.values(after.initial.items).map((item) => item.name),
      ...Object.values(after.initial.characters).map((character) => character.name),
    ];
    const evaluate = (raw: string) => {
      const cleaned = finishSentences(cleanNarration(raw).replace(/※/g, String.fromCharCode(10, 10))).trim();
      const validation = validateNarration(cleaned, brief.brief, after, view);
      const baseAlignment = alignNarration(packet, cleaned, alignmentOptions);
      // A pickup/throw sentence whose object is not a world entity is an event
      // the settlement never produced (the d101 dice). Drop that sentence; the
      // rest of the scene is still judged normally.
      const invented = inventedObjectActions(cleaned, `${draft}${this.lastResultsText ?? ''}`, entityNames);
      const alignment = invented.length
        ? { ...baseAlignment, violations: [...baseAlignment.violations, ...invented.map((violation) => ({ sentence: violation.sentence, kind: 'added_event' }))] }
        : baseAlignment;
      // Sentence-level repair keeps the literary text and only removes the
      // claims the settled state cannot support. Whole-text rejection made the
      // page show a state summary almost every round, which is worse than a
      // slightly shorter scene.
      const pruned = pruneNarration(cleaned, alignment, after, view);
      const supported = supportNarration(bindNarrationAttributes(pruned.text, after, view), draft);
      return { raw, cleaned, pruned: pruned.text, supported, dropped: pruned.dropped, validation };
    };

    /** Same repair chain as the final acceptance, applied to the sentences the
     * model has finished so far. Only used to publish the stream. */
    const previewNarration = (partial: string): string => {
      const cleaned = finishSentences(cleanNarration(partial)).trim();
      if ([...cleaned].length < 12) return '';
      const alignment = alignNarration(packet, cleaned, alignmentOptions);
      const pruned = pruneNarration(cleaned, alignment, after, view);
      const deduped = dedupeSentences(pruned.text);
      return supportNarration(bindNarrationAttributes(deduped.text, after, view), draft).trim();
    };

    const generate = async (prompt: string, temperature: number): Promise<{ raw: string; error?: string }> => {
      try {
        let published = '';
        const raw = await this.narrationEngine.complete(this.options.narrationMode === 'instruct' ? chatml(prompt) : prompt, {
          maxTokens: this.options.narrationMaxTokens ?? 240, temperature,
          timeoutMs: this.options.narrationTimeoutMs ?? 150_000,
          onProgress: (progress) => {
            // Show the scene while it is being written, but only the part that
            // already holds up against the settled facts. Streaming raw model
            // text would print invented actions and then take them back.
            const complete = progress.raw.replace(/[^。！？!?\n]*$/u, '');
            if ([...complete].length <= [...published].length) return;
            const preview = previewNarration(complete);
            if (!preview || preview === published) return;
            published = preview;
            this.options.onNarrationProgress?.({ pointId, raw: preview, elapsedMs: performance.now() - started });
          },
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
    // Attempt one rewrites the grounded draft under strict rules: the small
    // writer model invents less when it is told exactly which facts it may
    // use. The freer scene prompt runs only if that rewrite is rejected, so a
    // normal round costs one generation instead of two.
    // Publish the settled draft the moment narration starts. The player reads a
    // true, third-person scene instead of waiting for the writer model; the
    // streamed rewrite replaces it only if it passes the same gate.
    this.options.onNarrationProgress?.({ pointId, raw: draft, elapsedMs: performance.now() - started });

    const attempts: ReturnType<typeof evaluate>[] = [];
    const rewrite = instructNarrationInput(before, delta, after, view, this.lastPlayerInput, this.lastResultsText, draft, 'repair');
    const first = await generate(rewrite.prompt, Math.min(0.35, this.options.narrationTemperature ?? 0.45));
    attempts.push(evaluate(first.raw));
    if (!acceptCandidate(attempts[0]) && this.options.narrationMode === 'instruct') {
      const second = await generate(brief.prompt, this.options.narrationTemperature ?? 0.45);
      attempts.push(evaluate(second.raw));
    }
    const best = attempts.reduce((left, right) => ([...right.supported].length > [...left.supported].length ? right : left));
    // The support filter works on wording; alignment works on claims. A
    // sentence can survive the first and still assert an uncommitted result,
    // so prune again on the accepted candidate until it stops contradicting
    // the settled facts (bounded: each pass only removes sentences).
    // Whole-answer acceptance. Pruning sentence by sentence and then gluing the
    // remains with draft lines produced text that was fact-clean and unreadable
    // at the same time, so a candidate is judged as a whole: it either passes
    // alignment, grounding and point of view by itself, or the page shows the
    // grounded draft.
    const deduped = dedupeSentences(best.supported);
    const safe = deduped.text;
    const finalAlignment = alignNarration(packet, safe, alignmentOptions);
    const repetition = deduped.dropped;
    // Sentence pruning is the repair, not a failure: acceptance is decided on
    // the text the player will read, not on whether repair had to run.
    const audit = proseAudit(safe, protagonistName);
    const grounding = groundingRatio(safe, sceneNamesList);
    const accepted = best.validation.ok && finalAlignment.ok && audit.ok
      && grounding.ratio >= 0.5 && grounding.count >= 2;
    const text = accepted ? safe : draft;
    if (accepted) this.lastAcceptedNarration = text;
    const reason = accepted ? undefined : [...new Set([
      best.validation.reason,
      ...best.dropped.map((entry) => entry.reason),
      ...finalAlignment.violations.map((entry) => entry.kind),
      ...(repetition.length ? ['repetition'] : []),
      ...(grounding.ratio < 0.5 || grounding.count < 2 ? ['ungrounded'] : []),
      audit.reason ?? 'low_support',
    ])].filter(Boolean).join(',');
    // The model could not carry this round. Replace the terse factual draft
    // with the constrained candidate's fact-grounded prose (lane 04 skeleton +
    // lane 07 composer, no model call) and keep the explicit downgrade label.
    // Accepted model prose above is never replaced and never becomes program.
    let finalText = text;
    let programFallback = false;
    if (!accepted && this.narrationRunner) {
      const program = await this.narrationRunner.generateProgram({
        pointId, before, delta, after,
        playerInput: this.lastPlayerInput,
        settledResults: this.lastResultsText ? [this.lastResultsText] : [],
        settledFacts: this.lastSettledFacts,
        priorText: this.lastAcceptedNarration,
        recentEvents: this.recentEvents,
      });
      if (program) {
        console.info('[narration] in-model rejected', reason, '-> program fallback');
        finalText = program.text;
        programFallback = true;
      }
    }
    const finalReason = programFallback ? '程序按已结算事实成文' : reason;
    // Provenance guard: the program draft is part of the prompt. If the model
    // echoes it, the accepted text is still model output but it is not
    // independent evidence of style or of state-copy behaviour. Measure it and
    // keep it separate in evidence.
    const draftSentences = draft.split(/[。！？!?]/u).map((part) => part.trim()).filter((part) => [...part].length >= 6);
    const acceptedSentences = text.split(/[。！？!?]/u).map((part) => part.trim()).filter((part) => [...part].length >= 6);
    const echoed = acceptedSentences.filter((sentence) => draftSentences.some((candidate) => candidate.includes(sentence) || sentence.includes(candidate))).length;
    const draftEcho = acceptedSentences.length ? echoed / acceptedSentences.length : 0;
    this.options.onNarrationDebug?.({ pointId, draft, raw: best.raw, cleaned: best.cleaned, pruned: best.pruned, supported: best.supported, text: finalText,
      violations: finalAlignment.violations.map((entry) => entry.kind), attempts: attempts.map((entry) => [...entry.supported].length),
      rawAttempts: attempts.map((entry) => entry.raw), draftEcho, programFallback, prompt: brief.prompt });
    this.options.onTask?.('narration', key, { ms: performance.now() - started, fallback: !accepted || programFallback, error: finalReason, raw: finalText, promptChars: brief.prompt.length });
    this.options.onNarrationComplete?.({ pointId, raw: finalText, fallback: !accepted || programFallback,
      source: accepted ? 'model' : programFallback ? 'program' : 'draft',
      completion: { raw: finalText, finishReason: accepted ? 'stop' : programFallback ? 'program' : 'drafted', firstTokenMs: null, wallMs: performance.now() - started } });
    return { value: finalText as unknown as Json, raw: finalText, ms: performance.now() - started, fallback: !accepted || programFallback, error: finalReason };
  }

  /** Run the configured candidate for this point. Only an accepted scene is
   * returned; every other outcome logs an internal reason and lets the
   * in-model writer produce the page's text. */
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
      // 04's structured records are what the verifier compares; without them the
      // result fact falls back to the impossible verbatim sentence check.
      settledFacts: this.lastSettledFacts,
      priorText: this.lastAcceptedNarration,
      recentEvents: this.recentEvents,
    }, (state) => this.options.onNarrationProgress?.({ pointId, raw: state.text, elapsedMs: state.elapsedMs }));
    if (result.kind !== 'adopted') {
      console.info('[narration] candidate fallback', result.reason);
      // A non-empty model scene rejected by its own gate is kept as a labelled
      // draft: replacing written prose with program text loses the model's
      // work. The page marks it 未通过校对 and it never fills accepted prose.
      const draft = result.kind === 'fallback' ? result.draft : null;
      if (draft && draft.text.trim()) {
        const segments = draft.segments
          ? draft.segments.map((segment) => ({ id: segment.id, kind: segment.kind, source: segment.source, text: segment.text }))
          : undefined;
        this.options.onTask?.('narration', pointId, {
          ms: draft.timings.totalMs,
          fallback: true,
          error: `未通过校对：${result.reason}`,
          raw: draft.text,
          promptChars: draft.promptChars ?? draft.text.length,
        });
        this.options.onNarrationEvidence?.({
          pointId, candidateId: draft.candidateId, route: draft.route ?? undefined, grade: 'candidate_unverified',
          strategyVersion: draft.strategyVersion, segments, beatCounts: draft.beatCounts,
          issues: draft.issues, timings: draft.timings, detail: draft.detail ?? null, rejectedBy: 'candidate_gate',
        });
        this.options.onNarrationComplete?.({
          pointId, raw: draft.text,
          completion: { raw: draft.text, finishReason: 'stop', firstTokenMs: draft.timings.firstTokenMs, wallMs: draft.timings.totalMs },
          fallback: true, source: 'draft', segments,
        });
        // A draft is not confirmed prose: it must not become the prior text a
        // later turn is asked to continue from.
        return { value: draft.text as unknown as Json, raw: draft.text, ms: draft.timings.totalMs, fallback: true };
      }
      return null;
    }
    // Independent protection against invented current events. The candidate's
    // own verifier accepted text with a speaking rule sign, a gunshot derived
    // from a conditional trait, and invented pistol handling. This gate is
    // fact-based (alignment against the committed packet), not a word ban: a
    // licensed micro-action stays, an event the settlement never produced is
    // refused for the whole point and the in-model writer takes over.
    if (result.grade !== 'program') {
      const packet = alignmentPacket(before, delta, after);
      const alignment = alignNarration(packet, result.text, this.alignmentOptionsFor(before, delta, after));
      const fatal = alignment.violations.filter((violation) => FATAL_ALIGNMENT.has(violation.kind));
      if (fatal.length > 0) {
        const reasons = [...new Set(fatal.map((violation) => violation.kind))];
        console.info('[narration] candidate rejected by the independent fact gate', reasons.join(','), fatal[0]?.sentence ?? '');
        this.options.onNarrationEvidence?.({
          pointId, candidateId: result.candidateId, grade: result.grade, rejectedBy: 'independent_fact_gate',
          reasons, sentences: fatal.map((violation) => violation.sentence), strategyVersion: result.strategyVersion,
        });
        // The candidate's own gate accepted this text; the independent gate
        // refuses a sentence it cannot ground. The prose is kept and labelled
        // as an unverified draft instead of being replaced by program text.
        const kept = refusedCandidateDraft({
          text: result.text,
          segments: result.segments,
          candidateId: result.candidateId,
          route: result.route,
          strategyVersion: result.strategyVersion,
          beatCounts: result.beatCounts,
          issues: result.issues,
          timings: result.timings,
          promptChars: result.promptChars,
          rejectedBy: 'independent_fact_gate',
          reasons,
        });
        this.options.onTask?.('narration', pointId, {
          ms: kept.ms, fallback: true, error: kept.error, raw: kept.text, promptChars: kept.promptChars,
        });
        this.options.onNarrationEvidence?.({
          pointId, candidateId: kept.candidateId, route: kept.route, grade: 'candidate_unverified',
          strategyVersion: kept.strategyVersion, segments: kept.segments, beatCounts: kept.beatCounts,
          issues: kept.issues, timings: kept.timings, detail: result.detail ?? null, rejectedBy: kept.rejectedBy,
        });
        this.options.onNarrationComplete?.({
          pointId, raw: kept.text,
          completion: { raw: kept.text, finishReason: 'stop', firstTokenMs: kept.timings.firstTokenMs, wallMs: kept.timings.totalMs },
          fallback: true, source: 'draft', segments: kept.segments,
        });
        return { value: kept.text as unknown as Json, raw: kept.text, ms: kept.ms, fallback: true };
      }
    }
    const program = result.grade === 'program';
    const mixed = result.grade === 'mixed';
    // Only fully model-accepted prose becomes the prior text a later turn
    // continues from: mixed (part program) and drafts are not confirmed prose.
    if (!program && !mixed) this.lastAcceptedNarration = result.text;
    this.options.onTask?.('narration', pointId, {
      ms: result.timings.totalMs,
      fallback: program,
      ...(program ? { error: '程序按已结算事实成文' } : mixed ? { error: '部分句子按已结算事实成文' } : {}),
      raw: result.text,
      promptChars: result.promptChars,
    });
    this.options.onNarrationEvidence?.({
      pointId, candidateId: result.candidateId, route: result.route, grade: result.grade,
      strategyVersion: result.strategyVersion, segments: result.segments, beatCounts: result.beatCounts,
      issues: result.issues, timings: result.timings, detail: result.detail ?? null,
    });
    this.options.onNarrationComplete?.({ pointId, raw: result.text, completion: result.completion,
      fallback: program, source: program ? 'program' : mixed ? 'mixed' : 'model', segments: result.segments });
    return { value: result.text as unknown as Json, raw: result.text, ms: result.timings.totalMs, fallback: program };
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
    .replace(/[」』”’"'）)\]]+\s*$/u, (tail) => (/[「『“‘"'（(\[]/u.test(body) ? tail : ''))
    .trim();
}

/** Names the viewpoint can legitimately see or know in this scene: the ones the
 * brief already lists, plus people in the same container and what they (or the
 * viewpoint) wear or hold. A known name outside this set is offscreen and may
 * not appear; a worn item (aa30's red band) is visible even when the brief does
 * not spell it out. */
export function visibleEntityNames(after: WorldState, view: Id, facts: string): Set<string> {
  const names = new Set<string>();
  const add = (name?: string | null) => { if (name && name.length >= 2) names.add(name); };
  const viewpoint = after.characters[view];
  const container = viewpoint?.position?.containerId ?? null;
  add(after.initial.characters[view]?.name);
  const containers = new Set<string>([view]);
  if (container) containers.add(container);
  for (const [id, character] of Object.entries(after.characters)) {
    const inside = character.position?.containerId;
    if (inside && containers.has(inside)) {
      add(after.initial.characters[id]?.name);
      containers.add(id);
    }
  }
  for (const [id, item] of Object.entries(after.items)) {
    const inside = item.position?.containerId;
    if (inside && containers.has(inside)) add(after.initial.items[id]?.name);
  }
  for (const name of names) if (!facts.includes(name)) names.add(name);
  return names;
}

/** A candidate whose text the independent gate refused keeps that text as a
 * labelled draft: same words, per-segment provenance, no accepted timing, and
 * the gate's own reasons. Never used as prior text and never a pass. */
export function refusedCandidateDraft(input: {
  text: string;
  segments?: Array<{ id: string; kind: string; source: string; text: string }>;
  candidateId: string;
  route: string;
  strategyVersion: string;
  beatCounts: unknown;
  issues: unknown;
  timings: { totalMs: number; firstTokenMs: number | null };
  promptChars: number;
  rejectedBy: string;
  reasons: string[];
}) {
  return {
    text: input.text,
    segments: input.segments?.map((segment) => ({ id: segment.id, kind: segment.kind, source: segment.source, text: segment.text })),
    candidateId: input.candidateId,
    route: input.route,
    strategyVersion: input.strategyVersion,
    beatCounts: input.beatCounts,
    issues: input.issues,
    timings: input.timings,
    promptChars: input.promptChars,
    rejectedBy: input.rejectedBy,
    error: `独立事实门拒绝：${input.reasons.join(',')}`,
    ms: input.timings.totalMs,
  };
}

export function validateNarration(text: string, facts: string, after: WorldState, view: Id): { ok: boolean; reason: string } {
  // Only near-empty text is empty. Length alone never rejects a complete scene:
  // a settled point can be said in one short paragraph (NARRATION-BOUNDARY-20261111).
  if ([...text].length < 20) return { ok: false, reason: 'too_short' };
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
  const visible = visibleEntityNames(after, view, facts);
  const known = [
    ...Object.values(after.initial.characters).map((entity) => entity.name),
    ...Object.values(after.initial.locations).map((entity) => entity.name),
    ...Object.values(after.initial.items).map((entity) => entity.name),
  ];
  for (const name of known) {
    if (name.length < 2 || facts.includes(name) || visible.has(name)) continue;
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
  const place = locationName(after, room);
  const declared = actionText.trim().replace(/^我(?!们)/u, '').replace(/[。！？!?]+$/u, '');
  const moves = Boolean(change?.positionSet);
  if (moves) {
    const from = before ? locationName(before, before.characters[view]?.position.containerId ?? '') : '';
    const to = locationName(after, change?.positionSet?.containerId ?? room);
    out.push(declared && MOVEMENT.test(declared)
      ? `${name}${declared}，最后停在${to}。`
      : `${name}${from ? `从${from}` : ''}走到${to}。`);
  } else if (declared) {
    // The player's sentence is first person ("我扶他起来"); narration is third
    // person, so the protagonist becomes the subject rather than a fragment.
    out.push(declared.startsWith(name) ? endSentence(declared) : `${name}${declared}。`);
  }
  const actionGrams = bigramsOf(declared);
  // A settlement judgment is not a scene fact. 09 d101 fed
  // «诺诺未成功完成目标，因为路明非的骰点资格为false且无法反应。» into the draft
  // and the page showed dice the player never touched; the 2026-11-10 page runs
  // printed «诺诺：……未被掀开袖口，未看到规则牌» and «诺诺：因此未被阻止或达成目标。».
  const JUDGMENT = /(骰点|骰子|判定|检定|资格|无法反应|未成功|未达成|未被|未获得|未能|因此)/u;
  for (const settled of resultsText.split('；').map((part) => part.trim()).filter(Boolean)) {
    if (JUDGMENT.test(settled)) continue;
    if (/完成了刚才的动作|行动发生了，但没有产生新的结果|本组结算未能确认|未能确认新的结果|向.+移动/u.test(settled)) continue;
    const sentence = endSentence(settled.replace(new RegExp(`^${name}[：:，,]?`, 'u'), name));
    if (out.includes(sentence)) continue;
    const grams = bigramsOf(sentence);
    let shared = 0;
    for (const gram of grams) if (actionGrams.has(gram)) shared += 1;
    if (actionGrams.size && shared / actionGrams.size > 0.6) continue;
    out.push(sentence);
  }

  // Room and people are written as one look around the scene instead of a list
  // of records: a place clause, then what the protagonist can see of it, then
  // whoever is there with the detail that actually matters.
  const scenery: string[] = [];
  const appearance = after.initial.locations[room]?.initialAppearance;
  if (appearance) scenery.push(pickClauses(appearance, 2));
  if (scenery.length) out.push(`${place}里，${scenery.join('，')}。`);

  const others = visibleCharacters(after, view).filter((candidate) => candidate !== view).slice(0, 2);
  for (const id of others) {
    const other = after.initial.characters[id]?.name;
    if (!other) continue;
    const look = after.initial.characters[id]?.initialAppearance;
    const where = roomOf(after, id) === room ? '' : `在${locationName(after, roomOf(after, id))}，`;
    out.push(`${other}${where}${look ? pickClauses(look, 2) : '没有出声'}。`);
  }
  for (const [id, entity] of Object.entries(delta.entityDeltas ?? {})) {
    const other = after.initial.characters[id]?.name ?? after.initial.items[id]?.name;
    if (!other) continue;
    for (const taskId of entity.tasksAchieved ?? []) {
      const goal = after.characters[id]?.tasks[taskId]?.goal;
      if (goal) out.push(`${other}完成了「${goal}」。`);
    }
  }
  return out.join('').replace(/\n{3,}/gu, '\n\n').trim();
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

/** Facts are policed by alignment; wording is not. The only wording rule left
 * is dialogue: an invented line puts words in a character's mouth, which is a
 * fact the settlement never produced, so quoted speech must already exist in
 * the grounded draft. */
function supportNarration(text: string, draft: string): string {
  const kept: string[] = [];
  for (const raw of text.split(/(?<=[。！？!?])|\n+/u)) {
    const sentence = raw.trim();
    if (!sentence || [...sentence].length < 4) continue;
    const opened = /[「『“]/u.test(sentence);
    const closed = /[」』”]/u.test(sentence);
    // A sentence that carries any quote mark is dialogue being written by the
    // model. Only a complete, grounded line may stay: a half-split quote or an
    // invented line both put words in a character's mouth.
    if (opened || closed) {
      const quoted = sentence.match(/[「『“]([^」』”]{1,60})[」』”]/u);
      if (!quoted || opened !== closed || !draft.includes(quoted[1].trim())) continue;
    }
    kept.push(sentence);
  }
  return kept.join('').replace(/\n{3,}/gu, '\n\n').trim();
}

function legacySupportNarration(text: string, draft: string): string {
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

/** Repetition is the failure mode a small model falls into once the claims
 * pass alignment: the same walk restated with different wording for eight
 * sentences. Those repeats carry no new fact, they only make the page read
 * like a log. Compare each sentence with what is already kept and drop the
 * restatements; keep the first mention. */
function dedupeSentences(text: string): { text: string; dropped: string[] } {
  const kept: string[] = [];
  const keptGrams: Set<string>[] = [];
  const dropped: string[] = [];
  for (const raw of text.split(/(?<=[。！？!?])|\n+/u)) {
    const sentence = raw.trim();
    if (!sentence) continue;
    const grams = bigramsOf(sentence);
    if (grams.size) {
      let restatement = false;
      for (const other of keptGrams) {
        let shared = 0;
        for (const gram of grams) if (other.has(gram)) shared += 1;
        const smaller = Math.min(grams.size, other.size);
        if (smaller > 0 && shared / smaller >= 0.5) { restatement = true; break; }
      }
      if (restatement) { dropped.push(sentence); continue; }
      keptGrams.push(grams);
    }
    kept.push(sentence);
  }
  return { text: kept.join(''), dropped };
}

/** A scene is told from the protagonist's side. Text that only follows other
 * characters is not a wrong fact, it is the wrong viewpoint, and it reads as
 * a report about strangers rather than as the player's own round. */
function proseAudit(text: string, protagonistName: string): { ok: boolean; reason?: string } {
  const length = [...text].length;
  if (length < 80) return { ok: false, reason: 'low_support' };
  if (protagonistName && !text.includes(protagonistName)) return { ok: false, reason: 'off_perspective' };
  return { ok: true };
}

/** Names the settled scene actually contains: the people in the room, the
 * items lying there, and the place itself. A sentence that mentions none of
 * them is talking about something the round never produced. */
function sceneNames(state: WorldState, view: Id): string[] {
  const room = roomOf(state, view);
  const names = new Set<string>();
  const protagonist = state.initial.characters[view]?.name;
  if (protagonist) names.add(protagonist);
  for (const id of Object.keys(state.characters)) {
    const entity = state.initial.characters[id];
    if (!entity) continue;
    if (id === view || roomOf(state, id) === room) names.add(entity.name);
  }
  for (const id of sameRoomItems(state, view)) {
    const entity = state.initial.items[id] ?? state.initial.characters[id];
    if (entity?.name) names.add(entity.name);
  }
  const location = state.initial.locations[room];
  if (location?.name) names.add(location.name);
  return [...names].filter(Boolean);
}

function groundingRatio(text: string, names: string[]): { ratio: number; count: number } {
  const sentences = text.split(/(?<=[。！？!?])|\n+/u).map((sentence) => sentence.trim()).filter((sentence) => [...sentence].length >= 6);
  if (!sentences.length) return { ratio: 0, count: 0 };
  let grounded = 0;
  for (const sentence of sentences) if (names.some((name) => sentence.includes(name))) grounded += 1;
  return { ratio: grounded / sentences.length, count: grounded };
}

function sentenceEnd(text: string): string {
  return /[。！？!?…]$/u.test(text) ? text : `${text}。`;
}

function firstFeature(text: string, max: number): string {
  const first = firstClause(text).split(/[，,]/u)[0]?.trim() ?? '';
  return [...first].length > max ? `${[...first].slice(0, max).join('')}……` : first;
}

/** World files describe people like a character sheet: posture, clothing,
 * marks, what they hold. Reading all of it aloud reads like a form, so pick the
 * one or two clauses that actually describe what the protagonist would notice:
 * what the person is doing, then the mark that matters. */
function pickClauses(text: string, max: number): string {
  const clauses = text.split(/[，,；;。]/u).map((clause) => clause.trim()).filter(Boolean);
  if (!clauses.length) return '';
  const score = (clause: string): number => {
    if (/^(坐|站|靠|蹲|躺|跪|趴|倚|背靠)/u.test(clause)) return 0;
    if (/(伤|血|肿|痕|绷带|按住|捂着)/u.test(clause)) return 1;
    if (/(手|枪|刀|绳|带|门|锁)/u.test(clause)) return 2;
    return 3;
  };
  const picked = clauses.map((clause, index) => ({ clause, index, rank: score(clause) }))
    .sort((left, right) => left.rank - right.rank || left.index - right.index)
    .slice(0, max)
    .sort((left, right) => left.index - right.index)
    .map((entry) => entry.clause);
  return picked.join('，');
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
