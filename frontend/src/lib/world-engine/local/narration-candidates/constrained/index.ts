/** C route entry: settled facts -> beat plan -> constrained prose.
 *
 * `generateCandidate` is the only public entry. It never writes world state,
 * never re-parses the caller's serialized input as state, and returns every
 * attempt with timings and issues. Program mode needs no model at all; model
 * mode writes one verified beat per call; lane 07's composer plugs into the
 * same beat contract via `policy.composer`.
 */
import type { Id } from '../../../types';
import type { CommittedRead } from '../../../runtime/committed-narration';
import { isAbortError } from '../../../runtime/engine';
import { planBeats } from './beats';
import { composeBeatWithModel } from './compose';
import { absorbText, createRealizerContext, realizeBeat } from './realize';
import {
  projectConstrainedScene, projectFromFactsPacket, SceneProjectionError,
} from './projection';
import { verifyBeatText, verifyText } from './verify';
import type {
  BeatDirective, BeatEvidence, BeatPlan, CandidateIssue, CandidateProgress, CandidateResult,
  ComposeBeatResult, GenerateCandidateInput, SceneSkeleton,
} from './types';

export const STRATEGY_VERSION = 'constrained-candidate-v1.3';

const now = (): number => performance.now();

export async function generateCandidate(input: GenerateCandidateInput): Promise<CandidateResult> {
  const started = now();
  const policy = input.policy ?? {};
  const priorText = input.priorText ?? input.committed.priorText ?? null;
  const inputText = input.inputText ?? input.committed.inputText ?? null;
  const sanityStyle = policy.sanityStyle ?? 'direction';
  const progressLog: CandidateProgress[] = [];
  const emit = (progress: CandidateProgress) => {
    progressLog.push(progress);
    input.onProgress?.(progress);
  };

  let scene: SceneSkeleton;
  let base: CandidateResult['basePacket'] = null;
  const projectStarted = now();
  try {
    const projected = project(input, {
      viewpointId: policy.viewpointId,
      scene: policy.scene,
      knowledge: policy.knowledge,
      resultsText: policy.resultsText,
      priorText,
      inputText,
    });
    scene = projected.scene;
    base = projected.base;
  } catch (error) {
    const detail = error instanceof SceneProjectionError
      ? `${error.code}: ${error.message}`
      : error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    const issues: CandidateIssue[] = [{ kind: 'empty_text', severity: 'hard', beatId: null, detail: `projection_failed: ${detail}` }];
    return {
      text: '', accepted: false, rawAttempts: [], issues,
      timings: { totalMs: now() - started, planMs: 0, composeMs: 0, verifyMs: 0, beatsMs: [], firstTextMs: null },
      strategyVersion: STRATEGY_VERSION, status: 'error',
      verification: { ok: false, coverage: [], issues, unverifiedSentences: [], chars: 0, hiddenFactIds: [], repetition: null },
      skeleton: null, plan: null, composers: [], segments: [],
      beatCounts: { model: 0, program: 0, external: 0, fallback: 0 }, mixed: false, basePacket: null,
      display: { text: '', status: 'rejected', verified: false, elapsedMs: now() - started, beatId: null },
    };
  }

  const projectMs = now() - projectStarted;
  const requireTime = policy.requireTime ?? scene.facts.some((fact) => fact.kind === 'time');
  // The length floor scales with the settled content of the point, not with
  // the clock: an elapsed-time-only point has nothing to say beyond the time
  // and the room, so demanding a complex-scene budget would force invented
  // business. A point with several settled changes must not shrink into a
  // two-sentence summary.
  const changeCount = scene.facts.filter((fact) => fact.visibility === 'scene' && fact.mandatory && fact.kind !== 'time').length;
  const minChars = policy.minChars ?? (changeCount === 0 ? 30 : Math.min(100, 36 + changeCount * 8));
  const maxChars = policy.maxChars ?? 1400;
  // Program is the default: a caller that did not ask for model writing gets
  // deterministic prose and no model calls. Model/auto must be explicit.
  const modelRequested = policy.mode === 'model' || policy.mode === 'auto'
    ? policy.enableModel !== false
    : false;
  const planStarted = now();
  const plan = planBeats(scene, {
    narrateHiddenDeltas: policy.narrateHiddenDeltas === true,
    // Model mode spends one call per beat: keep the plan short. Program mode
    // can afford the extra beats that keep each settled change separate.
    maxBeats: policy.maxBeats ?? (modelRequested ? 6 : 10),
    seed: policy.seed,
    minChars: 18,
    maxChars: 150,
  });
  const planMs = now() - planStarted;

  const verifyOptions = {
    scene,
    base: base ?? { anchor: scene.anchor, facts: [] },
    priorText,
    requireTime,
    sanityStyle,
    forbiddenKnowledge: policy.forbiddenKnowledge ?? [],
  };

  const deadline = started + Math.max(5_000, policy.turnTimeoutMs ?? 180_000);
  let modelBudgetSpent = false;
  const modelBudget = (): { enabled: boolean; timeoutMs: number } => {
    if (!modelRequested || modelBudgetSpent) return { enabled: false, timeoutMs: 0 };
    const remaining = deadline - now();
    if (remaining <= 5_000) {
      modelBudgetSpent = true;
      return { enabled: false, timeoutMs: 0 };
    }
    return { enabled: true, timeoutMs: Math.min(policy.model?.timeoutMs ?? 90_000, remaining - 1_000) };
  };
  const modelEnabled = modelRequested;
  const ctx = createRealizerContext(scene, priorText, sanityStyle);
  ctx.avoidOpenings = policy.avoidOpenings ?? [];

  const beatsEvidence: BeatEvidence[] = [];
  const composers: string[] = [];
  const beatTexts: { beat: BeatDirective; text: string }[] = [];
  let cancelSeen = false;
  const composeStarted = now();
  let verifyMs = 0;

  for (const beat of plan.beats) {
    if (input.signal?.aborted) { cancelSeen = true; break; }
    const outcome = await writeBeat(beat, {
      input,
      scene,
      plan,
      ctx,
      policy,
      sanityStyle,
      verifyOptions,
      modelEnabled,
      modelBudget,
      modelBudgetSpent: () => modelBudgetSpent,
      prior: joinText(beatTexts),
      emit,
      addVerifyMs: (ms) => { verifyMs += ms; },
    });
    absorbText(ctx, outcome.evidence.text);
    beatsEvidence.push(outcome.evidence);
    composers.push(outcome.composer);
    beatTexts.push({ beat, text: outcome.evidence.text });
    // Program prose is returned whole; only a real writer (model/composer)
    // produces incremental progress. A completed paragraph is never disguised
    // as token streaming.
    if (outcome.evidence.source === 'model' || outcome.evidence.source === 'external') {
      emit({
        text: joinText(beatTexts),
        status: 'streaming',
        verified: false,
        elapsedMs: now() - started,
        beatId: beat.id,
      });
    }
  }
  const composeMs = now() - composeStarted;

  let assembled = dedupeSentences(joinText(beatTexts));
  const verifyStarted = now();
  let verification = verifyText(assembled, { ...verifyOptions, minChars, maxChars, checkPrior: true });
  verifyMs += now() - verifyStarted;

  // Beat-level repair: a mandatory fact that never surfaced is re-realized by
  // the program for the SAME beat, then the whole text is verified again.
  let repairs = 0;
  while (!verification.ok && !cancelSeen && repairs < 2) {
    const missing = new Set(verification.coverage.filter((entry) => !entry.expressed && entry.mandatory).map((entry) => entry.factId));
    const targets = beatTexts.filter(({ beat }) => beat.factIds.some((id) => missing.has(id)));
    if (!targets.length) break;
    repairs += 1;
    for (const target of targets) {
      const retryCtx = createRealizerContext(scene, assembled, sanityStyle);
      retryCtx.avoidOpenings = [...(policy.avoidOpenings ?? []), ...ctx.used];
      let text = realizeBeat(target.beat, retryCtx);
      if (!text) {
        const bumped = { ...target.beat, seed: (target.beat.seed + repairs * 7919) >>> 0 };
        text = realizeBeat(bumped, retryCtx);
      }
      target.text = text;
      absorbText(ctx, text);
      const evidence = beatsEvidence.find((entry) => entry.beatId === target.beat.id);
      if (evidence) {
        evidence.text = text;
        evidence.source = 'fallback';
        evidence.issues = [...evidence.issues, {
          kind: 'beat_repaired', severity: 'soft', beatId: target.beat.id,
          detail: 'mandatory fact was missing; beat re-realized by the program',
        }];
      }
      const index = composers.length - 1;
      if (index >= 0) composers[index] = composers[index] === 'program' ? 'program' : `${composers[index]}+repair`;
    }
    assembled = dedupeSentences(joinText(beatTexts));
    const startedVerify = now();
    verification = verifyText(assembled, { ...verifyOptions, minChars, maxChars, checkPrior: true });
    verifyMs += now() - startedVerify;
  }

  const issues = verification.issues;
  const accepted = verification.ok && !cancelSeen;
  const firstTextMs = beatsEvidence.length && beatsEvidence[0].text
    ? beatsEvidence[0].ms + projectMs + planMs
    : null;
  const displayText = assembled;
  const status = cancelSeen ? 'cancelled' : accepted ? 'accepted' : 'rejected';
  // Paragraph-level provenance: every beat keeps the writer that produced its
  // final text, so a partly program-written turn is visible as such.
  const segments = beatTexts.map(({ beat, text }, index) => ({
    beatId: beat.id,
    kind: beat.kind,
    source: beatsEvidence[index]?.source ?? 'program',
    text,
  })).filter((segment) => Boolean(segment.text));
  const beatCounts = { model: 0, program: 0, external: 0, fallback: 0 };
  for (const segment of segments) beatCounts[segment.source] += 1;
  const mixed = (beatCounts.model + beatCounts.external > 0)
    && (beatCounts.program + beatCounts.fallback > 0);
  const display: CandidateProgress = {
    text: displayText,
    status: cancelSeen ? 'rejected' : accepted ? 'accepted' : 'rejected',
    verified: accepted,
    elapsedMs: now() - started,
    beatId: null,
  };
  emit(display);
  return {
    text: displayText,
    accepted,
    rawAttempts: beatsEvidence,
    issues,
    timings: {
      totalMs: now() - started,
      planMs: projectMs + planMs,
      composeMs,
      verifyMs,
      beatsMs: beatsEvidence.map((entry) => entry.ms),
      firstTextMs,
    },
    strategyVersion: STRATEGY_VERSION,
    status,
    verification: {
      ok: verification.ok,
      coverage: verification.coverage,
      issues: verification.issues,
      unverifiedSentences: verification.unverifiedSentences,
      chars: verification.chars,
      hiddenFactIds: plan.hiddenFactIds,
      repetition: verification.repetition,
    },
    skeleton: scene,
    plan,
    composers,
    segments,
    beatCounts,
    mixed,
    basePacket: base,
    display,
  };
}

function project(
  input: GenerateCandidateInput,
  options: Parameters<typeof projectConstrainedScene>[2],
) {
  const packet = input.committed;
  if (packet.state) {
    const after: CommittedRead = {
      pointId: packet.anchor.pointId,
      version: packet.anchor.version,
      state: packet.state,
      stateDigest: packet.anchor.stateDigest,
      previousPointId: packet.anchor.previousPointId,
      timeAdvance: packet.timeAdvance ?? null,
      entityDeltas: packet.entityDeltas ?? {},
    };
    const before = packet.beforeState && packet.anchor.previousPointId
      ? {
        pointId: packet.anchor.previousPointId,
        version: Math.max(0, packet.anchor.version - 1),
        state: packet.beforeState,
        stateDigest: 'derived-before-state',
        previousPointId: null,
        timeAdvance: null,
        entityDeltas: {},
      } satisfies CommittedRead
      : null;
    return projectConstrainedScene(after, before, options);
  }
  return projectFromFactsPacket(packet, { ...options, timeAdvance: packet.timeAdvance ?? null });
}

interface WriteBeatArgs {
  input: GenerateCandidateInput;
  scene: SceneSkeleton;
  plan: BeatPlan;
  ctx: ReturnType<typeof createRealizerContext>;
  policy: NonNullable<GenerateCandidateInput['policy']>;
  sanityStyle: 'direction' | 'number';
  verifyOptions: Parameters<typeof verifyText>[1];
  modelEnabled: boolean;
  modelBudget: () => { enabled: boolean; timeoutMs: number };
  modelBudgetSpent: () => boolean;
  prior: string;
  emit: (progress: CandidateProgress) => void;
  addVerifyMs: (ms: number) => void;
}

async function writeBeat(beat: BeatDirective, args: WriteBeatArgs): Promise<{ evidence: BeatEvidence; composer: string }> {
  const { input, scene, policy, sanityStyle, verifyOptions, modelEnabled } = args;
  const starts = now();
  const issues: CandidateIssue[] = [];
  const started = (): number => now();

  // 1. Lane 07's composer, when injected.
  if (policy.composer) {
    const at = started();
    try {
      const result: ComposeBeatResult = await policy.composer(
        { beat, scene, prior: args.prior || null },
        {
          signal: input.signal,
          onProgress: (progress) => args.emit({
            text: progress.text, status: 'streaming', verified: false,
            elapsedMs: now() - at, beatId: beat.id,
          }),
        },
      );
      const checkStarted = now();
      const beatIssues = verifyBeatText(result.text, beat, verifyOptions);
      args.addVerifyMs(now() - checkStarted);
      if (!beatIssues.some((issue) => issue.severity === 'hard')) {
        return {
          composer: `${result.source}:${policy.composer.name || 'external'}`,
          evidence: {
            beatId: beat.id, kind: beat.kind, source: result.source, text: result.text,
            prompt: null, raw: result.raw ?? null, attempts: result.attempts ?? 1,
            ms: result.ms ?? now() - at, issues: beatIssues,
          },
        };
      }
      issues.push(...beatIssues);
    } catch (error) {
      if (isAbortError(error)) throw error;
      issues.push({ kind: 'engine_error', severity: 'soft', beatId: beat.id, detail: errorText(error) });
    }
    issues.push({ kind: 'beat_repaired', severity: 'soft', beatId: beat.id, detail: 'composer text failed the beat gate' });
  }

  // 2. Constrained model writer (one call per beat, one feedback retry).
  let modelAttempted = false;
  let modelFailed = false;
  if (modelEnabled && args.modelBudget().enabled) {
    modelAttempted = true;
    const maxAttempts = Math.max(1, Math.min(2, policy.model?.maxAttempts ?? 2));
    let feedback: string | null = null;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      const at = started();
      try {
        const result = await composeBeatWithModel(input.engine, beat, scene, args.prior || null, {
          sanityStyle,
          instruction: policy.model?.instruction ?? null,
          maxTokens: policy.model?.maxTokensPerBeat ?? policy.maxTokens ?? 200,
          temperature: policy.model?.temperature ?? policy.temperature ?? 0.7,
          timeoutMs: args.modelBudget().timeoutMs,
          signal: input.signal,
          feedback,
          onProgress: (progress) => args.emit({
            text: progress.text, status: 'streaming', verified: false,
            elapsedMs: now() - at, beatId: beat.id,
          }),
        });
        const checkStarted = now();
        const beatIssues = verifyBeatText(result.text, beat, verifyOptions);
        args.addVerifyMs(now() - checkStarted);
        if (!beatIssues.some((issue) => issue.severity === 'hard')) {
          return {
            composer: 'model',
            evidence: {
              beatId: beat.id, kind: beat.kind, source: 'model', text: result.text,
              prompt: result.prompt, raw: result.raw, attempts: attempt, ms: result.ms, issues: beatIssues,
            },
          };
        }
        issues.push(...beatIssues);
        feedback = `上一稿没有写清：${beatIssues.filter((issue) => issue.kind === 'fact_missing').map((issue) => issue.detail).join('；') || '事实或措辞不合要求'}。请重写这一段。`;
      } catch (error) {
        if (isAbortError(error)) throw error;
        issues.push({ kind: 'engine_error', severity: 'soft', beatId: beat.id, detail: errorText(error) });
        break;
      }
    }
    modelFailed = true;
    issues.push({ kind: 'beat_fallback', severity: 'soft', beatId: beat.id, detail: 'model beat fell back to the program realizer' });
  }

  if (modelEnabled && !modelAttempted) {
    issues.push({ kind: 'beat_fallback', severity: 'soft', beatId: beat.id, detail: 'turn budget spent; program wrote this beat' });
  }

  // 3. Program realization of the same beat.
  let text = realizeBeat(beat, args.ctx);
  let checkStarted = now();
  let beatIssues = verifyBeatText(text, beat, verifyOptions);
  args.addVerifyMs(now() - checkStarted);
  if (beatIssues.some((issue) => issue.severity === 'hard')) {
    const retryCtx = createRealizerContext(scene, args.prior || null, sanityStyle);
    retryCtx.avoidOpenings = [...(policy.avoidOpenings ?? []), ...args.ctx.used];
    const bumped = { ...beat, seed: (beat.seed + 104729) >>> 0 };
    const retry = realizeBeat(bumped, retryCtx);
    checkStarted = now();
    const retryIssues = verifyBeatText(retry, beat, verifyOptions);
    args.addVerifyMs(now() - checkStarted);
    if (retry && !retryIssues.some((issue) => issue.severity === 'hard')) {
      text = retry;
      beatIssues = retryIssues;
    } else {
      beatIssues = [...beatIssues, ...retryIssues];
    }
  }
  return {
    composer: modelAttempted ? (modelFailed ? 'program+model-failed' : 'program') : 'program',
    evidence: {
      beatId: beat.id, kind: beat.kind, source: beatIssues.some((issue) => issue.severity === 'hard') ? 'fallback' : 'program',
      text, prompt: null, raw: null, attempts: 1, ms: now() - starts, issues: [...issues, ...beatIssues],
    },
  };
}

function joinText(parts: { text: string }[]): string {
  return parts.map((part) => part.text).filter(Boolean).join('\n\n');
}

/** Drop duplicate sentences so two beats cannot repeat the same clause. */
export function dedupeSentences(text: string): string {
  const paragraphs = text.split(/\n{2,}/u).map((paragraph) => paragraph.trim()).filter(Boolean);
  const seen = new Set<string>();
  const kept: string[] = [];
  for (const paragraph of paragraphs) {
    const sentences = paragraph.split(/(?<=[。！？])/u).map((sentence) => sentence.trim()).filter(Boolean);
    const keptSentences: string[] = [];
    for (const sentence of sentences) {
      const key = sentence.replace(/[。！？\s]/gu, '');
      if (!key || seen.has(key)) continue;
      seen.add(key);
      keptSentences.push(sentence);
    }
    if (keptSentences.length) kept.push(keptSentences.join(''));
  }
  return kept.join('\n\n').trim();
}

function errorText(error: unknown): string {
  return error instanceof Error ? `${error.name}: ${error.message}` : String(error);
}

export { planBeats } from './beats';
export { projectConstrainedScene, projectFromFactsPacket, SceneProjectionError } from './projection';
export { createRealizerContext, realizeBeat, durationLabel, sanityDirection } from './realize';
export { verifyText, verifyBeatText } from './verify';
export { buildBeatPrompt, factDirective, sanitizeBeat } from './compose';
export type {
  BeatComposer, BeatDirective, BeatEvidence, BeatPlan, CandidateIssue, CandidateProgress,
  CandidateResult, ComposeBeatRequest, ComposeBeatResult, CommittedScenePacket, ConstrainedPolicy,
  GenerateCandidateInput, SceneFact, SceneKnowledge, SceneSkeleton,
} from './types';

export type { Id };
