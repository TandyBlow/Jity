/** C route entry: settled facts -> beat plan -> one model call per beat.
 *
 * The runtime does not inspect, refuse, rewrite or replace non-empty model
 * prose (NARRATION-RAW-OUTPUT-20261111). This module therefore:
 *   - projects the committed point into a read-only scene skeleton,
 *   - plans display beats from the settled facts,
 *   - asks the model for each beat and keeps the answer exactly as returned,
 *   - joins the non-empty beat answers in plan order.
 *
 * Nothing here verifies prose, repairs sentences, dedupes wording, re-realizes a
 * beat with a program writer, or feeds an earlier paragraph back in. Empty or
 * whitespace-only model output is not prose: the beat is skipped and, when every
 * beat is empty, the result is empty (the caller shows a status note).
 */
import type { Id } from '../../../types';
import { isAbortError } from '../../../runtime/engine';
import { planBeats } from './beats';
import { composeBeatWithModel } from './compose';
import {
  projectConstrainedScene, projectFromFactsPacket, SceneProjectionError,
} from './projection';
import type {
  BeatDirective, BeatEvidence, BeatPlan, CandidateProgress, CandidateResult,
  GenerateCandidateInput, SceneSkeleton,
} from './types';

export const STRATEGY_VERSION = 'constrained-candidate-v2-raw';

const now = (): number => performance.now();

export async function generateCandidate(input: GenerateCandidateInput): Promise<CandidateResult> {
  const started = now();
  const policy = input.policy ?? {};
  const inputText = input.inputText ?? input.committed.inputText ?? null;
  const sanityStyle = policy.sanityStyle ?? 'direction';
  const progressLog: CandidateProgress[] = [];
  const emit = (progress: CandidateProgress) => {
    progressLog.push(progress);
    input.onProgress?.(progress);
  };

  const projectStarted = now();
  let scene: SceneSkeleton;
  try {
    const projected = project(input, {
      viewpointId: policy.viewpointId,
      scene: policy.scene,
      knowledge: policy.knowledge,
      resultsText: policy.resultsText,
      settledFacts: policy.settledFacts ?? null,
      ...(policy.worldNames ? { worldNames: policy.worldNames } : {}),
      inputText,
    });
    scene = projected.scene;
  } catch (error) {
    const detail = error instanceof SceneProjectionError
      ? `${error.code}: ${error.message}`
      : error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    const timings = { totalMs: now() - started, planMs: 0, composeMs: 0, beatsMs: [], firstTextMs: null };
    return {
      text: '', segments: [], rawAttempts: [], timings,
      strategyVersion: STRATEGY_VERSION, status: 'error', detail: `projection_failed: ${detail}`,
      skeleton: null, plan: null, display: { text: '', status: 'rejected', verified: false, elapsedMs: now() - started, beatId: null },
    };
  }
  const planMs = now() - projectStarted;

  const plan: BeatPlan = planBeats(scene, {
    narrateHiddenDeltas: policy.narrateHiddenDeltas === true,
    maxBeats: policy.maxBeats ?? 6,
    // Fact-carrying beats include the scene texture instead of adding separate
    // blank scene beats (the plan is a display boundary, not four fixed beats).
    combineSceneMaterial: true,
    seed: policy.seed,
    minChars: 18,
    maxChars: 380,
  });

  const deadline = started + Math.max(5_000, policy.turnTimeoutMs ?? 180_000);
  // One call per beat. No retry loop: a second call exists only when the caller
  // explicitly allows one model attempt per beat; the answer is never judged.
  const maxAttempts = Math.max(1, Math.min(2, policy.model?.maxAttempts ?? 1));
  const beatsEvidence: BeatEvidence[] = [];
  const segments: CandidateResult['segments'] = [];
  const beatTexts: string[] = [];
  const beatsMs: number[] = [];
  let firstTextMs: number | null = null;
  let cancelSeen = false;
  const composeStarted = now();

  for (const beat of plan.beats) {
    if (input.signal?.aborted) { cancelSeen = true; break; }
    const remaining = deadline - now();
    if (remaining <= 2_000) break;
    const promptStarted = now();
    let evidence: BeatEvidence = {
      beatId: beat.id, kind: beat.kind, source: 'model', text: '', prompt: null, raw: null,
      attempts: 0, ms: 0, issues: [],
    };
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const result = await composeBeatWithModel(input.engine, beat, scene, {
          sanityStyle,
          instruction: policy.model?.instruction ?? null,
          maxTokens: policy.model?.maxTokensPerBeat ?? policy.maxTokens ?? 480,
          temperature: policy.model?.temperature ?? policy.temperature ?? 0.7,
          timeoutMs: Math.min(policy.model?.timeoutMs ?? 90_000, Math.max(2_000, remaining - 1_000)),
          signal: input.signal,
          onProgress: (progress) => emit({
            text: joinNonEmpty([...beatTexts, progress.text]),
            status: 'streaming', verified: false, elapsedMs: now() - started, beatId: beat.id,
          }),
        });
        evidence = {
          beatId: beat.id, kind: beat.kind, source: 'model', text: result.text,
          prompt: result.prompt, raw: result.raw, attempts: attempt, ms: now() - promptStarted, issues: [],
        };
        break;
      } catch (error) {
        if (isAbortError(error)) { cancelSeen = true; break; }
        // A transport/model error is a run error, not a reason to invent prose.
        evidence = {
          ...evidence, attempts: attempt, ms: now() - promptStarted,
          error: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
        };
      }
    }
    beatsEvidence.push(evidence);
    beatsMs.push(evidence.ms);
    if (cancelSeen) break;
    if (evidence.text.trim()) {
      if (firstTextMs === null) firstTextMs = now() - started;
      beatTexts.push(evidence.text);
      segments.push({ beatId: beat.id, kind: beat.kind, source: 'model', text: evidence.text });
    }
  }

  const text = joinNonEmpty(beatTexts);
  const composeMs = now() - composeStarted;
  const status: CandidateResult['status'] = cancelSeen ? 'cancelled' : text.trim() ? 'accepted' : 'empty';
  const display: CandidateProgress = {
    text, status: cancelSeen ? 'rejected' : text.trim() ? 'accepted' : 'rejected',
    verified: false, elapsedMs: now() - started, beatId: null,
  };
  emit(display);
  return {
    text,
    segments,
    rawAttempts: beatsEvidence,
    timings: { totalMs: now() - started, planMs, composeMs, beatsMs, firstTextMs },
    strategyVersion: STRATEGY_VERSION,
    status,
    skeleton: scene,
    plan,
    display,
  };
}

function joinNonEmpty(parts: string[]): string {
  return parts.filter((part) => part.trim()).join('\n\n');
}

function project(input: GenerateCandidateInput, options: Parameters<typeof projectFromFactsPacket>[1]): {
  scene: SceneSkeleton;
} {
  if (input.committed.state) {
    return projectConstrainedScene(input.committed as unknown as Parameters<typeof projectConstrainedScene>[0], null, options);
  }
  return projectFromFactsPacket(input.committed, options);
}

export { planBeats } from './beats';
export { projectConstrainedScene, projectFromFactsPacket, SceneProjectionError } from './projection';
export { buildBeatPrompt, factDirective, sanitizeBeat } from './compose';
export type {
  BeatComposer, BeatDirective, BeatEvidence, BeatPlan, CandidateProgress,
  CandidateResult, ComposeBeatRequest, ComposeBeatResult, CommittedScenePacket, ConstrainedPolicy,
  GenerateCandidateInput, SceneFact, SceneKnowledge, SceneSkeleton, StructuredSettledFact,
} from './types';

export type { Id };
