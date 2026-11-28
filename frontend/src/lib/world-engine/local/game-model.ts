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
import { alignNarration, EVENT_VERBS } from '../runtime/narration-alignment';
import type { CommittedNarration, NarrationFact } from '../runtime/committed-narration';
import { taskOutputSchema } from '../runtime/output-schema';
import { createActionHandlers, type HandlerResult } from './semantics/actions';
import { createNarrationRunner, type NarrationRunner } from './narration-candidates/selection';
import { requireSettlementValue } from './semantics/settlement';
import { createSettlementModelPort, type PortSubmission, type SettlementModelPort, type SettlementPortSummary } from './turn-execution';
import { describeCharacter, describeDelta, describeItem, describeLocation, instructNarrationInput, legacyNarrationInput, locationName, roomName, roomOf, sameRoomItems, taskText, visibleCharacters, activeText } from './prompt';
import { rulesNarration } from './rules-narration';

/** One worked example for the instruct brief (evaluation arm). Names and
 * props belong to another scene; the instructions forbid copying them. */
const NARRATION_EXAMPLE = [
  '示例（另一场戏，只学写法；不要带进示例里的人名、物件和动作）：',
  '阿青把门闩推上，又退回桌边，把散开的纸页按顺序叠好。窗缝里透进的光落在桌角，杯子里还剩半口水。老周在门口站了一会儿，没说话，把钥匙放回口袋，转身走了。',
].join(String.fromCharCode(10));

function withNarrationExample(prompt: string): string {
  const marker = '正文：';
  const index = prompt.lastIndexOf(marker);
  return index < 0 ? `${prompt}${String.fromCharCode(10)}${NARRATION_EXAMPLE}` : `${prompt.slice(0, index)}${NARRATION_EXAMPLE}${String.fromCharCode(10)}${prompt.slice(index)}`;
}

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
  /** Evaluation arm: one worked example in the instruct brief. The shipped
   * default has no example; the page exposes it only through the URL query. */
  narrationFewShot?: boolean;
  /** Evaluation arm (D-022): drop the location look, room items and other
   * characters' appearance from the brief. Same instructions, less material for
   * the writer to recite or move between characters. */
  narrationProjection?: 'full' | 'compact';
  /** Evaluation arm (D-022): state the unknown-target rule in the results
   * prompt. Default off; the page exposes it only through the URL query. */
  settlementUnknownRule?: boolean;
  /** Evaluation arm (mobile): compact results-prompt scene list. */
  compactSettlement?: boolean;
  /** Evaluation arm: worked blocked example for unknown targets (results prompt). */
  settlementUnknownExample?: boolean;
  /** Deterministic guard for unregistered entities in settled facts (default
   * on). The page can disable it with strictKnownEntities=0 for A/B runs. */
  strictKnownEntities?: boolean;
  /** The player's character id. The point plan puts that character alone in
   * the round's first point so the player's own settlement can commit and be
   * narrated before the rest of the roster is judged (the 2026-11-11 turns
   * spent 280 s settling one point that held every actor). */
  protagonistId?: Id;
  /** Evaluation arm: off-screen actors are judged per actor ('judge') or
   * skipped by the action lane's program rule ('skip'). The page exposes it
   * only through the URL query; the shipped default stays 'judge'. */
  offscreenPolicy?: 'skip' | 'judge';
  /** Experimental structured-action arm: the action lane emits category,
   * target/item ids, destination and conditions for results to consume. */
  structuredActions?: boolean;
  /** Default on: a task-goal action answer accepts a checked template instead
   * of the repair calls. False keeps the repair prompt for experiments. */
  templateFallback?: boolean;
  /** Experimental: facts with structured destinations drive the position
   * stage directly; uncertain scenes fall back to the LLM. */
  programScene?: boolean;
  localPosition?: boolean;
  /** Experimental NPC behavior head: category → template action; null → LLM. */
  behavior?: import('./semantics/actions').ActionHandlerOptions['behavior'];
  judge?: import('./semantics/actions').ActionHandlerOptions['judge'];
  /** Experimental micro workflow: a rules+scorer targets port. When it returns
   * null or a rejected proposal, the existing LLM path runs and the reason is
   * recorded on the task evidence. Default off (undefined = LLM only). */
  microTargets?: import('./semantics/actions').MicroTargetsFn;
  /** Experimental micro workflow: a results head answers before the LLM; a
   * rejected or low-confidence answer falls back to the existing path. */
  microResults?: import('./semantics/settlement/types').MicroResultsFn;
  /** Experimental micro workflow: the movement head answers the position half
   * of the merged scene stage; an unsupported move falls back to the LLM. */
  microUpdates?: import('./semantics/settlement/types').MicroUpdatesFn;
  /** Experimental micro workflow: structured events + four heads replace the
   * continuation proposal/judgement LLM calls when they answer. */
  microContinuation?: import('./semantics/settlement/types').MicroContinuationFn;
  /** Experimental micro workflow: trigger class + intent candidates + the
   * three judges replace the reaction writer when they are confident. */
  microReaction?: import('./semantics/actions').ActionHandlerOptions['microReaction'];
  /** Experimental micro workflow: task/fact verifier. A null or low-confidence
   * answer falls back to the LLM verifier. */
  microTaskVerifier?: import('./semantics/settlement/types').MicroTaskVerifierFn;
  /** Experimental micro workflow: condition-level task proposer with a
   * session ledger; it only proposes and the verifier commits. */
  microTaskProposer?: import('./semantics/settlement/types').MicroTaskProposerFn;
  /** Internal narration candidate selection. `auto` only offers candidates
   * whose real-model evidence is positive, so the shipped default changes
   * nothing until one is accepted; the named routes exist for evaluation and
   * are never a player-visible setting. */
  narrationCandidate?: 'auto' | 'trained' | 'instruct' | 'constrained' | 'builtin' | 'rules';
  /** Rules arm only: append prev/fresh counters for diagnosis. */
  narrationDebug?: boolean;
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
  onNarrationComplete?: (progress: {
    pointId: Id; raw: string; completion: CompletionEvidence; fallback: boolean;
    /** `mixed` = some sentences are verified model prose and some are program
     * realizations; never counted as fully model-written. */
    source: 'model' | 'program' | 'mixed' | 'draft';
    segments?: Array<{ id: string; kind: string; source: string; text: string }>;
  }) => void;
  /** Test/evaluation hook: the raw model answer, the prompt it answered, and the
   * beat writer's per-beat record. Never used to make a product decision. */
  onNarrationDebug?: (debug: {
    pointId: Id; raw: string; text: string;
    rawAttempts: string[];
    prompt: string;
    draft?: string;
    violations?: string[];
    beats?: { id: string; ask: string; facts: string[]; model: string; fallback: string; reasons: string[] }[];
  }) => void;
  /** Internal evidence sink for candidate runs: candidate id, grade, per-beat
   * segments and the candidate's own attempt record. Never rendered. */
  onNarrationEvidence?: (record: Record<string, unknown>) => void;
  onTask?: (task: ModelTask, key: string, detail: {
    ms: number; fallback: boolean; error?: string; raw?: string; promptChars?: number;
    source?: 'program' | 'model' | 'fallback' | 'micro' | 'rule';
    issues?: { code: string; severity: string; message: string; detail?: string }[];
    calls?: HandlerResult['calls'];
    value?: Json;
    stageMs?: Record<string, number>;
    stages?: string[];
    scope?: { mode?: string; affectedCharacters?: number; unaffectedCharacters?: number; affectedTaskIds?: string[]; unaffectedTaskIds?: string[]; taskRows?: number } | null;
    /** One model attempt inside a task, not the accepted task result. */
    attempt?: boolean;
  }) => void;
}

interface Generated { value: Json; raw: string; ms: number; fallback: boolean; error?: string }

type SettledFactRecord = {
  text: string; actorId: string; targetId?: string; action?: string;
  outcome: 'completed' | 'partial' | 'failed' | 'blocked' | 'unaffected'; implicit?: true;
};

interface PointNarrationSnapshot {
  resultsText: string;
  facts: SettledFactRecord[];
  playerInput: string;
}

/** Violations that mean the text asserts something the settlement did not
 * produce. Style, length and wording are not in this set. */
const FATAL_ALIGNMENT = new Set([
  'added_event', 'actor_swap', 'direction_reversed', 'wrong_number',
  'movement_without_fact', 'task_claimed_without_fact', 'state_claim_without_fact',
  'presence_contradiction', 'item_ownership_contradiction', 'ledger_leak',
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
  /** The player's character. Taken from the options (the page knows the static
   * world) and refreshed from any working state a settlement handler sees. */
  private protagonistId: Id | null = null;
  private lastPlayerInput = '';
  private lastResultsText = '';
  /** Structured settled results for the current point (04's actor/action/target/
   * outcome records), used by the candidate so it checks meaning, not wording. */
  private lastSettledFacts: SettledFactRecord[] = [];
  /** Per-point settlement material, frozen at commit. Narration for an older
   * point must never read the next point's mutable lastResultsText/facts. */
  private readonly pointResults = new Map<Id, string[]>();
  private readonly pointFacts = new Map<Id, SettledFactRecord[]>();
  private readonly seenFactTexts = new Set<string>();
  private readonly narrationSnapshots = new Map<Id, PointNarrationSnapshot>();

  /** Planned actors per point; the action line follows this, not the delta. */
  private readonly plannedActors = new Map<Id, Id[]>();
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
    this.protagonistId = options.protagonistId ?? null;
    // Lane 04's settlement port owns results/updates (six stages) and the
    // continuation judgement. A policy stop is a visible stop; there is no
    // product-side "one action per round" switch and no fabricated handback.
    this.settlement = createSettlementModelPort(semanticEngine, {
      microResults: this.options.microResults,
      microUpdates: this.options.microUpdates,
      microContinuation: this.options.microContinuation,
      microTaskVerifier: this.options.microTaskVerifier,
      microTaskProposer: this.options.microTaskProposer,
      programScene: this.options.programScene,
      localPosition: this.options.localPosition,
      onTask: (task, key, detail) => this.options.onTask?.(task, key, detail),
      nextRoundId: () => `round_auto_${Date.now().toString(36)}_${++this.roundCounter}`,
      // The appearance stage measures 7877 chars on the shipped world; a retry
      // with feedback is ~7970. The guard must leave room for the repair while
      // still refusing a runaway prompt (lane 04's measured numbers).
      // 11,900 admits the measured position prompt (11,776) plus the small
      // output budget; the engine context is 12,288 tokens.
      maxPromptChars: 11_900,
      unknownEntityRule: options.settlementUnknownRule ?? false,
      strictKnownEntities: options.strictKnownEntities ?? true,
      compactPrompts: options.compactSettlement ?? false,
      unknownEntityExample: options.settlementUnknownExample ?? false,
    });
    this.narrationRunner = (options.narrationCandidate ?? 'auto') === 'builtin'
      || options.narrationCandidate === 'rules'
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
      microTargets: this.options.microTargets,
      structuredActions: this.options.structuredActions,
      templateFallback: this.options.templateFallback,
      behavior: this.options.behavior,
      judge: this.options.judge,
      microReaction: this.options.microReaction,
      recentEvents: () => this.recentEvents,
      offscreenPolicy: this.options.offscreenPolicy ?? 'judge',
      onCall: (call) => this.options.onTask?.(call.task, call.key, {
        ms: call.elapsedMs, fallback: !call.decoded, error: call.error, raw: call.raw, promptChars: call.promptChars,
        source: 'model', attempt: true,
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
  beginSubmission(inputText: string): void {
    this.settlement.beginSubmission(inputText);
    this.pointResults.clear();
    this.pointFacts.clear();
    this.seenFactTexts.clear();
    this.narrationSnapshots.clear();
    this.plannedActors.clear();
  }

  /** The controller committed this point. Freeze the settlement material that
   * belongs to it before a later point overwrites the live caches. */
  onPointCommitted(pointId: Id): void {
    // No cross-point results fallback.
    const resultsText = (this.pointResults.get(pointId) ?? []).join('；');
    const facts = this.pointFacts.get(pointId) ?? [];
    this.narrationSnapshots.set(pointId, {
      resultsText,
      facts: facts.map((fact) => ({ ...fact })),
      playerInput: this.lastPlayerInput,
    });
  }
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

  /** Point segmentation is program-owned; the model owns the semantic
   * action/results work.
   *
   * A player round becomes two points. The first holds only the player's own
   * character, so its settlement group (the player's action, its targets and
   * their reactions) commits and goes to narration as soon as it is done; the
   * remaining roster is judged in a zero-duration instant point after it. The
   * 2026-11-11 runs put all fourteen actors in one point: the first commit
   * waited 248-280 s for six settlement groups, far past the 60 s target. No
   * settlement group is split — the player's group keeps its targets and
   * reactions, and every other actor's own group is settled in the second
   * point, which is where it was already settled before.
   *
   * Automatic (continuation) rounds keep one point: their order is the
   * model's candidate list and has no player slot to isolate. */
  private planPoints(input: Json): Json {
    const round = (input as { round?: { roundId?: Id; order?: Id[]; trigger?: string } }).round;
    const order = round?.order ?? [];
    const roundId = round?.roundId ?? 'round';
    const single = { pointId: `point_${roundId}_1`, kind: 'normal',
      timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: order };
    const protagonist = this.protagonistId;
    if (round?.trigger !== 'player' || protagonist === null || order.length < 2 || !order.includes(protagonist)) {
      this.plannedActors.set(single.pointId, [...order]);
      return [single];
    }
    const rest = order.filter((actor) => actor !== protagonist);
    if (rest.length === 0) {
      this.plannedActors.set(single.pointId, [...order]);
      return [single];
    }
    const player = { ...single, actorIds: [protagonist] };
    const instant = { pointId: `point_${roundId}_2`, kind: 'instant',
      // An instant point must carry a zero duration; the round's time already
      // advanced with the first point.
      timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } }, actorIds: rest };
    this.plannedActors.set(player.pointId, [protagonist]);
    this.plannedActors.set(instant.pointId, [...rest]);
    return [player, instant];
  }

  private async action(key: Id, input: Json): Promise<Generated> {
    const data = input as { actor?: Id; advance?: { inputText?: string | null; intentStatus?: string } | null; workingState?: WorldState };
    this.noteProtagonist(data.workingState);
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

  /** Any settlement input carries the working state; remember the player's id
   * so the next round's plan can isolate the player's point even if the page
   * did not pass one. */
  private noteProtagonist(state: WorldState | undefined): void {
    if (state?.protagonistId) this.protagonistId = state.protagonistId;
  }

  private reportAction(result: HandlerResult): Generated {
    const error = result.issues.filter((issue) => issue.severity === 'error').map((issue) => issue.code).join(',') || undefined;
    this.options.onTask?.(result.task, result.key, {
      ms: result.elapsedMs, fallback: result.fallback, error, raw: result.raw,
      source: result.source,
      issues: result.issues.map((issue) => ({ code: issue.code, severity: issue.severity, message: issue.message, detail: issue.detail })),
      calls: result.calls,
      value: result.value,
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
    const pointId = (input as { pointId?: Id }).pointId;
    if (pointId) {
      this.pointResults.set(pointId, [...(this.pointResults.get(pointId) ?? []), ...story]);
      const facts = this.pointFacts.get(pointId) ?? [];
      for (const fact of this.lastSettledFacts) {
        if (this.seenFactTexts.has(fact.text)) continue;
        this.seenFactTexts.add(fact.text);
        facts.push({ ...fact });
      }
      this.pointFacts.set(pointId, facts);
    }
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
    // The continuation judgement is lane 04's port. A policy stop has no model
    // conclusion value; it is passed to the controller as a typed stop so the
    // round closes as a visible cancel (never a fabricated model handback) and
    // the narration of the committed points still runs.
    const started = performance.now();
    try {
      const value = await this.settlement.generate('continuation', key, input);
      return { value, raw: '', ms: performance.now() - started, fallback: false };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const marker = 'settlement_failed:continuation:continuation_policy_';
      if (message.startsWith(marker)) {
        return {
          value: { kind: 'policy_stop', reason: message.slice('settlement_failed:continuation:'.length) },
          raw: '', ms: performance.now() - started, fallback: false,
        };
      }
      throw error;
    }
  }

  /** Narration is written one small beat at a time. A 1.5B writer asked for a
   * whole scene invents people, dialogue and physical effects; asked for one
   * sentence about a named fact, it mostly restates that fact. Each beat is
   * generated, streamed and gated on its own, and a beat that cannot be
   * supported falls back to its own grounded draft line instead of dragging the
   * whole scene down with it. */
  private async narration(key: Id, input: Json): Promise<Generated> {
    const data = input as { pointId?: Id; before?: WorldState | null; delta?: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }; after?: WorldState; perspective?: string };
    const after = data.after;
    if (!after) throw new Error('narration without after state');
    const pointId = data.pointId ?? key;
    const view = after.protagonistId;
    const started = performance.now();
    const before = data.before ?? null;
    const delta = data.delta ?? {};
    // Material for THIS point, frozen at its commit. A later point's live
    // caches must not reach an older point's prose.
    const snapshot = this.narrationSnapshots.get(pointId);
    // Action line only for the player's point.
    const actors = this.plannedActors.get(pointId);
    const inPoint = actors && after.protagonistId ? actors.includes(after.protagonistId) : true;
    const playerInput = inPoint ? (snapshot?.playerInput ?? this.lastPlayerInput) : '';
    const resultsText = snapshot?.resultsText ?? '';
    const settledFacts = snapshot?.facts ?? [];

    // Zero-parameter arm: the brief is the whole input, no engine is touched.
    if (this.options.narrationCandidate === 'rules') {
      const input = instructNarrationInput(before, delta, after, view, playerInput, resultsText, '', 'scene', this.options.narrationProjection === 'compact');
      const text = rulesNarration({
        sentences: input.sentences, resultsText,
        names: Object.values(after.initial.characters).map((entry) => String(entry.name ?? '')),
        protagonist: after.initial.characters[view]?.name ?? view,
      });
      const ms = performance.now() - started;
      this.options.onNarrationDebug?.({ pointId, raw: text, text, rawAttempts: [], prompt: input.prompt });
      this.options.onTask?.('narration', key, { ms, fallback: false, raw: text, promptChars: input.prompt.length, source: 'rule' });
      this.options.onNarrationComplete?.({
        pointId, raw: text,
        completion: { raw: text, finishReason: 'stop', firstTokenMs: null, wallMs: ms },
        fallback: false, source: 'program', segments: [],
      });
      return { value: text as unknown as Json, raw: text, ms, fallback: false };
    }

    // Candidate path: one settled point in, the candidate's own beat text out.
    // Nothing here inspects, refuses, rewrites or replaces that text.
    if (this.narrationRunner) {
      const adopted = await this.adoptNarrationCandidate(pointId, before, delta, after, playerInput, resultsText, settledFacts);
      if (adopted) return adopted;


    // In-model writer: one call with the settled state as its only material.
    const baseBrief = this.options.narrationMode === 'instruct'
      ? instructNarrationInput(before, delta, after, view, playerInput, resultsText, '', 'scene', this.options.narrationProjection === 'compact')
      : { prompt: legacyNarrationInput(before, delta, after, view), brief: legacyNarrationInput(before, delta, after, view) };
    const brief = this.options.narrationMode === 'instruct' && this.options.narrationFewShot
      ? { ...baseBrief, prompt: withNarrationExample(baseBrief.prompt) }
      : baseBrief;
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
    let text = protocolText(raw);
    let consistency = this.stateConsistencyViolations(before, delta, after, view, playerInput, text);
    if (consistency.length) {
      // Keep the model's supported sentences; only the contradicting ones go.
      const pruned = dropViolatingSentences(text, consistency);
      if (pruned.trim() && !this.stateConsistencyViolations(before, delta, after, view, playerInput, pruned).length) {
        raw = pruned;
        text = pruned;
        consistency = [];
      }
    }
    if (consistency.length) {
      // One repair call with the explicit contradiction. A program draft is
      // only the last resort; the product path prefers model prose.
      const draftForRepair = factualNarration(before, delta, after, view, playerInput, resultsText);
      const repair = `你是中文小说作者。把下面这段已经结算的事实改写成 2 到 3 句第三人称正文；不得改变事实，不得新增人物、动作、物品或去向，不得写与事实相反的在场或缺席。
事实：${draftForRepair}
正文：`;
      try {
        const repaired = await this.narrationEngine.complete(
          this.options.narrationMode === 'instruct' ? chatml(repair) : repair,
          {
            maxTokens: this.options.narrationMaxTokens ?? 240,
            temperature: this.options.narrationTemperature ?? 0.45,
            timeoutMs: this.options.narrationTimeoutMs ?? 150_000,
            ...(this.options.narrationMode === 'instruct' ? { stop: ['<|im_end|>'] } : {}),
          },
        );
        const repairedText = protocolText(repaired);
        const repairedViolations = this.stateConsistencyViolations(before, delta, after, view, playerInput, repairedText);
        if (repairedText.trim() && !repairedViolations.length) {
          raw = repaired;
          text = repairedText;
          consistency = [];
        }
      } catch {
        // The repair is best-effort; the draft stays the last resort below.
      }
    }
    if (consistency.length) {
      const draft = factualNarration(before, delta, after, view, playerInput, resultsText);
      this.options.onNarrationEvidence?.({ pointId, stateConsistencyRejected: consistency, replacedWith: 'draft' });
      this.options.onNarrationDebug?.({ pointId, raw, text: draft, rawAttempts: [raw], prompt: brief.prompt, violations: consistency.map((row) => row.kind) });
      this.options.onTask?.('narration', key, {
        ms: performance.now() - started, fallback: true, error: 'state_consistency_violation', raw: draft,
        promptChars: brief.prompt.length, source: 'fallback',
      });
      this.options.onNarrationComplete?.({
        pointId, raw: draft,
        completion: { raw: draft, finishReason: 'stop', firstTokenMs: null, wallMs: performance.now() - started },
        fallback: true, source: 'program', segments: [],
      });
      return { value: draft as unknown as Json, raw: draft, ms: performance.now() - started, fallback: true, error: 'state_consistency_violation' };
    }
    const empty = text.trim().length === 0;
    this.options.onNarrationDebug?.({ pointId, raw, text, rawAttempts: [raw], prompt: brief.prompt });
    this.options.onTask?.('narration', key, {
      ms: performance.now() - started, fallback: false,
      ...(empty ? { error: 'empty_model_output' } : {}),
      raw: text, promptChars: brief.prompt.length, source: 'model',
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

    const name = after.initial.characters[view]?.name ?? view;
    const draft = factualNarration(before, delta, after, view, playerInput, resultsText);
    const packet = alignmentPacket(before, delta, after);
    const alignmentOptions = {
      roster: Object.values(after.initial.characters).map((entity) => entity.name),
      locations: Object.values(after.initial.locations).map((entity) => entity.name),
      time: delta.timeAdvance?.duration ?? null,
      knownPositions: visibleCharacters(after, view).filter((id) => id !== view).map((id) => ({ name: after.initial.characters[id]?.name ?? id, location: locationName(after, roomOf(after, id)) })),
      presentNames: visibleCharacters(after, view).filter((id) => id !== view).map((id) => after.initial.characters[id]?.name ?? id),
      itemOwners: Object.entries(after.items).flatMap(([id, row]) => {
        const owner = after.initial.characters[row.position.containerId]?.name;
        return owner ? [{ item: after.initial.items[id]?.name ?? id, owner }] : [];
      }),
      allowedEvents: EVENT_VERBS.filter((verb) => playerInput.includes(verb)),
    };
    const sceneNamesList = sceneNames(after, view);

    // Publish the settled draft the moment narration starts: the player reads a
    // true scene at once, and each accepted beat replaces its own draft line as
    // it streams in.
    this.options.onNarrationProgress?.({ pointId, raw: draft, elapsedMs: performance.now() - started });

    const beats = this.narrationBeats(after, before, delta, view, playerInput, resultsText);
    if (!beats.length) {
      this.finishNarration(key, pointId, started, draft, [], draft, []);
      return { value: draft as unknown as Json, raw: draft, ms: performance.now() - started, fallback: true, error: 'empty_scene' };
    }

    const results: BeatResult[] = [];
    const publish = (): void => {
      const text = results.map((beat) => beat.text || beat.fallback).join('');
      this.options.onNarrationProgress?.({ pointId, raw: text || draft, elapsedMs: performance.now() - started });
    };

    for (const beat of beats) {
      const prompt = beatPrompt(name, beat);
      let published = 0;
      const accepted = await this.writeBeat(prompt, beat, packet, alignmentOptions, after, view, draft, playerInput, resultsText, (partial) => {
        const proven = this.gateBeat(partial, beat, packet, alignmentOptions, after, view, sceneNamesList, playerInput, resultsText);
        if (!proven || [...proven].length <= published) return;
        published = [...proven].length;
        results.push({ ...beat, text: proven });
        publish();
        results.pop();
      });
      results.push({ ...beat, text: accepted });
      publish();
    }

    const text = results.map((beat) => beat.text || beat.fallback).join('');
    const rejected = results.filter((beat) => !beat.text);
    const reason = rejected.length ? [...new Set(rejected.flatMap((beat) => beat.reasons))].join(',') : undefined;
    this.finishNarration(key, pointId, started, text, results, draft, rejected.flatMap((beat) => beat.reasons));
    return { value: text as unknown as Json, raw: text, ms: performance.now() - started, fallback: rejected.length > 0, error: reason };
  }

  private finishNarration(
    key: Id,
    pointId: Id,
    started: number,
    text: string,
    beats: BeatResult[],
    draft: string,
    reasons: string[],
  ): void {
    const modelBeats = beats.filter((beat) => beat.text).length;
    const fallback = reasons.length > 0 || modelBeats === 0;
    const source = modelBeats === 0 ? 'draft' as const : (reasons.length ? 'mixed' as const : 'model' as const);
    this.options.onNarrationDebug?.({
      pointId, raw: text, text,
      rawAttempts: beats.map((beat) => beat.text).filter(Boolean),
      prompt: '',
      draft,
      beats: beats.map((beat) => ({ id: beat.id, ask: beat.ask, facts: beat.facts, model: beat.text, fallback: beat.fallback, reasons: beat.reasons })),
      violations: [...new Set(reasons)],
    });
    this.options.onTask?.('narration', key, {
      ms: performance.now() - started, fallback,
      error: reasons.length ? [...new Set(reasons)].join(',') : undefined, raw: text,
      source: source === 'draft' ? 'fallback' : 'model',
    });
    this.options.onNarrationComplete?.({ pointId, raw: text, completion: { raw: text, finishReason: fallback ? 'drafted' : 'stop', firstTokenMs: null, wallMs: performance.now() - started }, fallback, source });
  }

  /** The three facts the player is entitled to read this round: where the round
   * happens and who is there, what the protagonist just did and what came of
   * it, and the one detail worth noticing. Everything else is style. */
  private narrationBeats(
    after: WorldState,
    before: WorldState | null,
    delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> },
    view: Id,
    playerInput: string,
    resultsText: string,
  ): Beat[] {
    const name = after.initial.characters[view]?.name ?? view;
    const room = roomOf(after, view);
    const place = locationName(after, room);
    const appearance = after.initial.locations[room]?.initialAppearance;
    const others = visibleCharacters(after, view).filter((id) => id !== view).slice(0, 2);
    const people = others.map((id) => {
      const entity = after.initial.characters[id];
      const looks = [entity?.initialAppearance, ...activeText(after.characters[id]?.appearanceChanges ?? [])].filter(Boolean).join('，');
      return `${entity?.name ?? id}${looks ? `（${pickClauses(looks, 2)}）` : ''}`;
    });
    const scenery = appearance ? pickClauses(appearance, 2) : '';
    const declared = playerInput.trim().replace(/^我(?!们)/u, '');
    const settledText = resultsText.trim();
    const change = delta.entityDeltas?.[view];
    const moved = change?.positionSet ? locationName(after, change.positionSet.containerId) : '';

    const beats: Beat[] = [];
    beats.push({
      id: 'scene',
      facts: [`地点：${place}${scenery ? `；${scenery}` : ''}`, ...(people.length ? [`在场：${people.join('；')}`] : ['在场：没有别人'])],
      ask: `用一到两句写${name}此刻所在的地方，和在场的人。`,
      fallback: `${place}里，${scenery || '看不出什么特别'}。${people.length ? `${people.map((person) => person.split('（')[0]).join('、')}也在。` : ''}`,
      reasons: [],
      text: '',
    });
    if (declared || settledText) {
      beats.push({
        id: 'act',
        facts: [
          `玩家这一回合让${name}做的事：${declared || '（没有说话，只是行动）'}`,
          ...(moved ? [`${name}因此到了${moved}`] : []),
          ...(settledText ? [`结算结果：${settledText}`] : []),
        ],
        ask: `用一到两句写${name}刚做了什么，结果怎么样。`,
        fallback: `${declared ? `${name}${declared}。` : ''}${settledText ? `${settledText.replace(new RegExp(`^${name}[：:，,]?`, 'u'), name)}。` : ''}`,
        reasons: [],
        text: '',
      });
    }
    const detailSource = others.length
      ? [after.initial.characters[others[0]]?.name ?? '', ...[after.initial.characters[others[0]]?.initialAppearance ?? ''].map((value) => pickClauses(value, 2))].filter(Boolean).join('：')
      : scenery;
    if (detailSource) {
      beats.push({
        id: 'detail',
        facts: [`可以写的细节只有这一条：${detailSource}`],
        ask: '用一句话写此刻最该被注意到的一个细节。',
        fallback: '',
        reasons: [],
        text: '',
      });
    }
    return beats;
  }

  private async writeBeat(
    prompt: string,
    beat: Beat,
    packet: ReturnType<typeof alignmentPacket>,
    alignmentOptions: Parameters<typeof alignNarration>[2],
    after: WorldState,
    view: Id,
    draft: string,
    playerInput: string,
    resultsText: string,
    onPartial: (text: string) => void,
  ): Promise<string> {
    try {
      const raw = await this.narrationEngine.complete(chatml(prompt), {
        maxTokens: 96,
        temperature: this.options.narrationTemperature ?? 0.45,
        timeoutMs: this.options.narrationTimeoutMs ?? 120_000,
        stop: ['<|im_end|>'],
        onProgress: (progress) => {
          const complete = progress.raw.replace(/[^。！？!?]*$/u, '');
          if (!complete) return;
          onPartial(complete);
        },
      });
      const gated = this.gateBeat(raw, beat, packet, alignmentOptions, after, view, sceneNames(after, view), playerInput, resultsText);
      if (gated && [...gated].length >= 6) return gated;
      beat.reasons.push('beat_unsupported');
      return '';
    } catch (error) {
      const partial = error instanceof IncompleteGenerationError ? error.completion.raw : '';
      const gated = partial ? this.gateBeat(partial, beat, packet, alignmentOptions, after, view, sceneNames(after, view), playerInput, resultsText) : '';
      if (gated && [...gated].length >= 6) return gated;
      beat.reasons.push(error instanceof Error && error.name === 'TimeoutError' ? 'beat_timeout' : 'beat_failed');
      return '';
    }
  }

  /** One beat's text, checked against this round's settled facts. Anything that
   * asserts a physical effect, invents dialogue, switches to first person or
   * mentions something outside the beat's own facts is dropped sentence by
   * sentence; a beat with nothing left is not shown. */
  private gateBeat(
    raw: string,
    beat: Beat,
    packet: ReturnType<typeof alignmentPacket>,
    alignmentOptions: Parameters<typeof alignNarration>[2],
    after: WorldState,
    view: Id,
    sceneNamesList: string[],
    playerInput: string,
    resultsText: string,
  ): string {
    const cleaned = finishSentences(cleanNarration(raw)).trim();
    if (!cleaned) return '';
    const allowed = [...beat.facts, playerInput, resultsText].join('；');
    const alignment = alignNarration(packet, cleaned, alignmentOptions);
    const pruned = pruneNarration(cleaned, alignment, after, view).text || cleaned;
    const supported = supportNarration(bindNarrationAttributes(pruned, after, view), allowed);
    const kept: string[] = [];
    for (const sentence of supported.split(/(?<=[。！？!?])/u)) {
      const trimmed = sentence.trim();
      if ([...trimmed].length < 5) continue;
      if (/[^「『“]我(?!们)/u.test(trimmed.replace(/[「『“][^」』”]*[」』”]/gu, ''))) continue;
      kept.push(trimmed);
    }
    const text = kept.join('');
    if (!text) return '';
    const grounding = groundingRatio(text, sceneNamesList);
    if (grounding.count === 0 && [...text].length > 40) return '';
    return text;
  }
  /** State-consistency violations for a finished narration text. This is the
   * same aligned check as gateBeat, exposed for routes that bypass it. */
  private stateConsistencyViolations(
    before: WorldState | null,
    delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> },
    after: WorldState,
    view: Id,
    playerInput: string,
    text: string,
  ) {
    const packet = alignmentPacket(before, delta, after);
    const alignment = alignNarration(packet, text, {
      roster: Object.values(after.initial.characters).map((entity) => entity.name),
      locations: Object.values(after.initial.locations).map((entity) => entity.name),
      time: delta.timeAdvance?.duration ?? null,
      knownPositions: visibleCharacters(after, view).filter((id) => id !== view)
        .map((id) => ({ name: after.initial.characters[id]?.name ?? id, location: locationName(after, roomOf(after, id)) })),
      presentNames: visibleCharacters(after, view).filter((id) => id !== view)
        .map((id) => after.initial.characters[id]?.name ?? id),
      itemOwners: Object.entries(after.items).flatMap(([id, row]) => {
        const owner = after.initial.characters[row.position.containerId]?.name;
        return owner ? [{ item: after.initial.items[id]?.name ?? id, owner }] : [];
      }),
      allowedEvents: EVENT_VERBS.filter((verb) => playerInput.includes(verb)),
    });
    return alignment.violations.filter((violation) => FATAL_ALIGNMENT.has(violation.kind));
  }

  /** Run the configured candidate for this point. The candidate's text is used
   * exactly as returned; only an empty answer falls through. */
  private async adoptNarrationCandidate(
    pointId: Id,
    before: WorldState | null,
    delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> },
    after: WorldState,
    playerInput: string,
    resultsText: string,
    settledFacts: SettledFactRecord[],
  ): Promise<Generated | null> {
    if (!this.narrationRunner) return null;
    const result = await this.narrationRunner.generate({
      pointId,
      before,
      delta,
      after,
      playerInput,
      settledResults: resultsText ? [resultsText] : [],
      settledFacts,
    }, (state) => this.options.onNarrationProgress?.({ pointId, raw: state.text, elapsedMs: state.elapsedMs }));
    if (result.kind !== 'adopted') {
      return null;
    }
    // The candidate route bypasses gateBeat; run the same state-consistency
    // check here. A contradiction rejects this candidate and lets the beat
    // writer produce a grounded text.
    if (this.stateConsistencyViolations(before, delta, after, after.protagonistId, playerInput, result.text).length) {
      this.options.onNarrationEvidence?.({
        pointId, candidateId: result.candidateId, route: result.route,
        stateConsistencyRejected: true,
      });
      return null;
    }
    this.options.onTask?.('narration', pointId, {
      ms: result.timings.totalMs, fallback: false, raw: result.text, promptChars: result.promptChars,
      source: 'model',
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

const MOVEMENT = /走|跑|移动|前往|走向|进入|退|撤|爬|穿过|绕过|离开|去|赶到|溜|冲|贴墙|靠近|靠近/u;

/** Facts that the alignment grader is allowed to require. Only the
 * protagonist and entities with a committed delta enter the packet; static
 * "everyone is here" facts would demand a roll-call that the scene language
 * never uses. */
export function alignmentPacket(before: WorldState | null, delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }, after: WorldState): CommittedNarration {
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
      const toId = character.position.containerId;
      const from = fromId ? before?.initial.locations[fromId]?.name : undefined;
      if (from && fromId && fromId !== toId) {
        facts.push({ id: `${id}:position`, actorId: id, name, kind: 'moved', fromId, from, toId, to: locationName(after, toId) });
      } else if (id === view) {
        // A slot change inside the same location is not a move; describing it
        // as «从中央庭院走到中央庭院» is a no-op movement.
        facts.push({ id: `${id}:position`, actorId: id, name, kind: 'at', locationId: toId, location: locationName(after, toId) });
      }
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

/** Remove only the sentences an alignment violation points at. */
function dropViolatingSentences(text: string, violations: Array<{ sentence: string }>): string {
  const bad = violations.map((violation) => violation.sentence.trim()).filter(Boolean);
  return text.split(/(?<=[。！？!?])/u)
    .filter((sentence) => {
      const value = sentence.trim();
      return value && !bad.some((row) => row === value || row.includes(value) || value.includes(row));
    })
    .join('');
}

function factualNarration(before: WorldState | null, delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }, after: WorldState, view: Id, actionText = '', resultsText = ''): string {
  const out: string[] = [];
  const name = after.initial.characters[view]?.name ?? view;
  const time = delta.timeAdvance;
  if (time && time.duration.amount > 0) out.push(`时间过去了约${time.duration.amount}${timeUnit(time.duration.unit)}。`);
  const change = delta.entityDeltas?.[view];
  const room = roomOf(after, view);
  const place = locationName(after, room);
  const declared = actionText.trim().replace(/^我(?!们)/u, '').replace(/[。！？!?]+$/u, '');
  const moves = Boolean(change?.positionSet && before
    && before.characters[view]?.position.containerId !== change.positionSet.containerId);
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
  for (const rawSettled of resultsText.split('；').map((part) => part.trim()).filter(Boolean)) {
    // 读取信息是玩家能看到的内容，转成一句正文而不是丢掉
    const info = /^信息[=＝]([^:：]+)[:：](.+)$/u.exec(rawSettled);
    if (info) {
      const item = after.initial.items[info[1]]?.name ?? info[1];
      const clause = info[2].trim().replace(/^[^：:，。]{1,8}[：:]/u, '');
      out.push(endSentence(`${name}看清了${item}上的内容：${clause}`));
      continue;
    }
    // Structured markers are evidence, not prose.
    if (/^(?:去向|涉及|环境)=/u.test(rawSettled)) continue;
    const settled = rawSettled.replace(/；?(?:去向|环境)=[^；。]*/gu, '').replace(/；?信息=[^；。]*/gu, '').replace(/；?涉及=[^；。]*/gu, '')
      .replace(/（(?:达到目的|只完成一部分|没有成功|被阻止|没有变化)）/gu, '')
      .replace(/^([^：:，。]{1,8})[：:]/u, '$1').trim();
    if (!settled) continue;
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
const CLAIM_WORDS = [
  '血', '肿', '伤', '裂', '骨折', '断', '湿', '破', '碎', '烫', '淤',
  '触', '摸', '碰', '扶', '抱', '拉', '推', '拽', '按住', '捂住', '抓住',
  '掏出', '拿出', '收进', '塞进', '递给', '接过', '放下', '举起', '打开', '关上',
  '解开', '系上', '拔出', '插回', '拧', '撬', '踢', '打', '开枪',
];

function supportNarration(text: string, draft: string): string {
  const kept: string[] = [];
  for (const raw of text.split(/(?<=[。！？!?])|\n+/u)) {
    const sentence = raw.trim();
    if (!sentence || [...sentence].length < 4) continue;
    // Effect words are claims, not style. If the settlement never mentions
    // blood, a wound, a hand closing on someone or an object changing hands,
    // the sentence is inventing a physical change and cannot be shown.
    const claimed = CLAIM_WORDS.filter((word) => sentence.includes(word) && !draft.includes(word));
    if (claimed.length) continue;
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
interface Beat {
  id: string;
  facts: string[];
  ask: string;
  fallback: string;
  reasons: string[];
  text: string;
}

type BeatResult = Beat;

function beatPrompt(name: string, beat: Beat): string {
  return [
    '你是中文小说作者。只写这一件事，一到两句，直接写正文。',
    `主角：${name}。第三人称，只能用“${name}”或“他”，不要写“我”。`,
    '事实：',
    ...beat.facts.map((fact) => `- ${fact}`),
    `写什么：${beat.ask}`,
    '要求：只写事实里出现的动作、位置、外观和结果；不要新增动作、对白、物品、人物、数字、伤情、往事、心理活动或比喻；不要写标题、列表或解释。',
    '正文：',
  ].join(String.fromCharCode(10));
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
