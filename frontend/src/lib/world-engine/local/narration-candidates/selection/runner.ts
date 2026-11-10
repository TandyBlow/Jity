/** Narration candidate selection for the product page.
 *
 * The page sees ONE decision: did a candidate accept a scene for this point?
 *   - `adopted`  → the candidate's verified prose is this point's narration;
 *   - `fallback` → the existing in-model path keeps writing the text it writes
 *                  today (the page already labels that text honestly).
 *
 * Selection order is internal configuration, never a player-visible option:
 *   1. `globalThis.__jityNarrationCandidate` — QA/evaluation override, set by
 *      scripts before the page boots; unset in normal play.
 *   2. the `candidate` option the integrator passes;
 *   3. `auto`, which only offers candidates marked `productDefault`.
 *
 * A candidate marked unavailable, that throws, or that rejects its own draft
 * never becomes this point's narration. The user's cancel path is the engine's
 * own; this runner adds no second truth and no hidden retry loop.
 */
import type {
  CandidateNarrationResult, NarrationCandidate, NarrationPoint, NarrationProgress,
  NarrationRunResult, NarrationRunner, NarrationRunnerOptions, PreparedNarration, ProgramFallback,
} from './types';
import { prepareNarration } from './projection';
import { createChatTemplatedEngine } from './engine-template';
import { TRAINED_CANDIDATE } from './trained';
import { CONSTRAINED_CANDIDATE } from './constrained';

/** Candidates that exist in this tree. A/C adapters are added here when their
 * entry modules land; nothing else in the product has to change. */
export const SHIPPED_CANDIDATES: NarrationCandidate[] = [TRAINED_CANDIDATE, CONSTRAINED_CANDIDATE];

/** QA override. Internal: the page never renders or documents this name. */
export function internalCandidateOverride(): string | null {
  const value = (globalThis as { __jityNarrationCandidate?: unknown }).__jityNarrationCandidate;
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
}

const printable = (error: unknown): string => (error instanceof Error ? `${error.name}:${error.message}` : String(error));

/** Map a candidate's own provenance to the page-facing grade. A partially
 * model-written scene is `mixed`, never `candidate`: the page and the evidence
 * must be able to tell which sentences are program realizations. */
function gradeOf(result: CandidateNarrationResult): 'candidate' | 'program' | 'mixed' {
  if (result.grade === 'program') return 'program';
  if (result.grade === 'candidate_with_program_sentences') return 'mixed';
  const sources = (result.detail?.segments as Array<{ source?: string }> | undefined) ?? [];
  if (sources.length && sources.some((s) => s.source === 'program' || s.source === 'fallback')
    && sources.some((s) => s.source === 'model' || s.source === 'external')) return 'mixed';
  return 'candidate';
}

function resultSegments(result: CandidateNarrationResult): Array<{ id: string; kind: string; source: string; text: string }> {
  const segments = result.detail?.segments as Array<{ id: string; kind: string; source: string; text: string }> | undefined;
  if (segments?.length) return segments;
  // Whole-scene candidates have no per-sentence segmentation; the whole text
  // is one segment attributed to the candidate's own grade.
  return [{ id: 'scene', kind: 'scene', source: result.grade === 'program' ? 'program' : 'model', text: result.text }];
}

function resultBeatCounts(result: CandidateNarrationResult): { model: number; program: number; other: number } {
  const counts = result.detail?.beatCounts as { model: number; program: number; other: number } | undefined;
  if (counts) return counts;
  return result.grade === 'program'
    ? { model: 0, program: 1, other: 0 }
    : { model: 1, program: 0, other: 0 };
}

function summarize(result: CandidateNarrationResult): string {
  if (result.accepted) return '';
  const kinds = result.issues.filter((issue) => issue.severity === 'hard').map((issue) => issue.kind);
  return [result.reason ?? result.status, kinds.length ? kinds.join('+') : null].filter(Boolean).join('|');
}

export function createNarrationRunner(options: NarrationRunnerOptions): NarrationRunner {
  const candidates = options.candidates ?? SHIPPED_CANDIDATES;
  // A chat model needs the same wrapper the in-model writer applies. The
  // decorator only changes prompt/stop, never identity or abort.
  const engine = options.engineTemplate === 'chatml'
    ? createChatTemplatedEngine(options.engine)
    : options.engine;
  const requested = internalCandidateOverride() ?? options.candidate ?? 'auto';
  const productDefault = candidates.find((candidate) => candidate.productDefault)?.id ?? null;
  const limits = {
    temperature: options.temperature,
    retryTemperature: options.retryTemperature,
    maxTokens: options.maxTokens,
    maxTokensCeiling: options.maxTokensCeiling,
    timeoutMs: options.timeoutMs,
    deadlineMs: options.deadlineMs,
    minChars: options.minChars,
    targetChars: options.targetChars,
  };

  const ordered = (): NarrationCandidate[] => {
    if (requested === 'builtin') return [];
    if (requested === 'auto') return candidates.filter((candidate) => candidate.productDefault);
    return candidates.filter((candidate) => candidate.id === requested);
  };

  return {
    selection: {
      requested,
      available: candidates.map((candidate) => candidate.id),
      productDefault,
    },
    async generateProgram(point: NarrationPoint): Promise<ProgramFallback | null> {
      // The in-model writer already tried and failed before this is called, so
      // the world-opening guard does not apply: a readable program scene is
      // better than the terse factual draft, and it is labelled as a downgrade.
      if (!point.after) return null;
      let prepared: PreparedNarration;
      try {
        prepared = prepareNarration(point, limits);
      } catch {
        return null;
      }
      const candidate = candidates.find((entry) => entry.id === 'constrained') ?? CONSTRAINED_CANDIDATE;
      try {
        const result = await candidate.run({
          engine, point, prepared,
          policy: { mode: 'program' },
        });
        if (!result.accepted || result.text.trim().length === 0) return null;
        return {
          text: result.text,
          strategyVersion: result.strategyVersion,
          timings: result.timings,
          issues: result.issues,
        };
      } catch {
        return null;
      }
    },
    async generate(point: NarrationPoint, onProgress?: (progress: NarrationProgress) => void): Promise<NarrationRunResult> {
      const plan = ordered();
      if (plan.length === 0) {
        return {
          kind: 'fallback',
          candidateId: null,
          grade: 'program_fallback',
          reason: requested === 'auto' ? 'no_product_candidate' : requested === 'builtin' ? 'builtin_requested' : `unknown_candidate:${requested}`,
          notice: null,
        };
      }
      let prepared: PreparedNarration;
      try {
        prepared = prepareNarration(point, limits);
      } catch (error) {
        return {
          kind: 'fallback', candidateId: null, grade: 'program_fallback',
          reason: `prepare_error:${printable(error)}`, notice: null,
        };
      }
      const problems: string[] = [];
      let last: CandidateNarrationResult | null = null;
      for (const candidate of plan) {
        const availability = candidate.availability(point, prepared);
        if (!availability.available) {
          problems.push(`unavailable:${candidate.id}|${availability.reason ?? 'unknown'}`);
          continue;
        }
        let result: CandidateNarrationResult;
        try {
          result = await candidate.run({
            engine, point, prepared, onProgress,
            ...(candidate.route === 'constrained'
              ? { policy: { mode: options.constrainedMode ?? 'program' } }
              : candidate.route === 'trained'
                ? { policy: {
                  sceneMode: options.trainedMode ?? 'beats',
                  ...(options.trainedPromptShape ? { promptShape: options.trainedPromptShape } : {}),
                } }
                : {}),
          });
        } catch (error) {
          problems.push(`error:${candidate.id}|${printable(error)}`);
          continue;
        }
        last = result;
        if (result.accepted && result.text.trim().length > 0) {
          return {
            kind: 'adopted',
            candidateId: result.candidateId,
            route: result.route,
            text: result.text,
            accepted: true,
            grade: gradeOf(result),
            segments: resultSegments(result),
            beatCounts: resultBeatCounts(result),
            issues: result.issues,
            timings: result.timings,
            promptChars: result.promptChars,
            strategyVersion: result.strategyVersion,
            attempts: result.attempts,
            detail: result.detail ?? null,
            completion: {
              raw: result.text,
              finishReason: 'stop',
              firstTokenMs: result.timings.firstTokenMs,
              wallMs: result.timings.totalMs,
            },
          };
        }
        problems.push(`${result.status}:${candidate.id}|${summarize(result)}`);
      }
      return {
        kind: 'fallback',
        candidateId: plan[0]?.id ?? null,
        grade: 'program_fallback',
        reason: problems.join(';') || 'candidate_rejected',
        notice: null,
        detail: last ? {
          candidateId: last.candidateId,
          status: last.status,
          text: last.text,
          issues: last.issues,
          timings: last.timings,
          strategyVersion: last.strategyVersion,
          attempts: last.attempts,
          candidate: last.detail ?? null,
        } : undefined,
      };
    },
  };
}
