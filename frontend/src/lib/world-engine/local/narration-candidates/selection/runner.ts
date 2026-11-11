/** Narration candidate selection for the product page.
 *
 * The runtime never judges prose (NARRATION-RAW-OUTPUT-20261111). Selection is
 * only about which candidate writes this point:
 *   - `adopted` → the candidate returned non-empty model text; it is shown exactly
 *                 as returned, with its display segments;
 *   - `empty`   → the candidate ran but the model returned nothing; the page
 *                 shows a status note and no narration (never program prose).
 *
 * If every candidate is unavailable or errors, the caller falls back to the
 * in-model writer with `builtin`; a candidate is never "rejected" for its text.
 */
import type {
  CandidateNarrationResult, NarrationCandidate, NarrationPoint, NarrationProgress,
  NarrationRunResult, NarrationRunner, NarrationRunnerOptions, PreparedNarration,
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
    async generate(point: NarrationPoint, onProgress?: (progress: NarrationProgress) => void): Promise<NarrationRunResult> {
      const plan = ordered();
      if (plan.length === 0) {
        return { kind: 'unavailable', reason: requested === 'auto' ? 'no_product_candidate' : 'builtin_requested' };
      }
      let prepared: PreparedNarration;
      try {
        prepared = prepareNarration(point, limits);
      } catch (error) {
        return { kind: 'unavailable', reason: `prepare_error:${printable(error)}` };
      }
      const problems: string[] = [];
      let sawNonEmpty = false;
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
              ? { policy: { mode: 'model' } }
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
        if (result.text.trim().length > 0) {
          sawNonEmpty = true;
          return {
            kind: 'adopted',
            candidateId: result.candidateId,
            route: result.route,
            text: result.text,
            segments: resultSegments(result),
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
        if (result.status !== 'empty') problems.push(`${result.status}:${candidate.id}`);
      }
      // No candidate wrote anything. That is an empty answer, not a reason to
      // ask the legacy writer to describe the state again.
      return { kind: 'empty', reason: problems.join(';') || 'empty_model_output', sawNonEmpty };
    },
  };
}

function resultSegments(result: CandidateNarrationResult): Array<{ id: string; kind: string; source: string; text: string }> {
  const segments = result.detail?.segments as Array<{ id: string; kind: string; source: string; text: string }> | undefined;
  if (segments?.length) return segments;
  return [{ id: 'scene', kind: 'scene', source: 'model', text: result.text }];
}
