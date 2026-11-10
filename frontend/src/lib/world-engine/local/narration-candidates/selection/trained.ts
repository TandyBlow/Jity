/** B-route adaptation: lane 02's committed-fact narration strategy (beats).
 *
 * The strategy owns prompt construction, verification and repair. This adapter
 * only supplies:
 *   - the fact packet (projected from the sealed delta by `projection.ts`),
 *   - lane 01's serialized input (licensing evidence; beats do not re-use it
 *     as the prompt),
 *   - the writing policy (viewpoint, roster, time, lengths, temperature),
 *   - real progress increments and the final verdict, unmapped and unedited.
 *
 * `productDefault` stays false until a real-model evidence record shows at
 * least one accepted narration; the selection layer never promotes a candidate
 * on unit-test evidence alone.
 */
import { generateCandidate, NARRATION_STRATEGY_VERSION } from '../trained-generation';
import type { NarrationIssue } from '../trained-generation/types';
import type { CandidateNarrationResult, NarrationCandidate } from './types';

const hardKinds = (issues: NarrationIssue[]): string[] =>
  [...new Set(issues.filter((issue) => issue.severity === 'hard').map((issue) => issue.kind))];

export const TRAINED_CANDIDATE: NarrationCandidate = {
  id: 'trained',
  route: 'trained',
  version: `trained-beats:${NARRATION_STRATEGY_VERSION}`,
  label: '02-narration · committed-fact beats',
  requires: {
    modules: ['local/narration-candidates/trained-generation', 'local/narration-input'],
    template: 'engine chat template (no manual ChatML wrap)',
  },
  productDefault: false,
  availability(_point, prepared) {
    if (!prepared.inputText) {
      return { available: false, reason: `input_unavailable:${prepared.inputError ?? 'empty'}` };
    }
    return { available: true, reason: null };
  },
  async run({ engine, point, prepared, onProgress, policy: runPolicy }): Promise<CandidateNarrationResult> {
    const result = await generateCandidate({
      engine,
      committed: prepared.facts,
      inputText: prepared.inputText ?? '',
      priorText: point.priorText ?? null,
      signal: point.signal,
      onProgress: (state) => onProgress?.({
        text: state.text, elapsedMs: state.elapsedMs, verified: state.verified, attempt: state.attempt,
      }),
      policy: {
        ...prepared.policy,
        mode: runPolicy?.sceneMode === 'scene' ? 'scene' : 'beats',
        scene: prepared.scene,
        // Scene mode otherwise writes a static tableau: the page model omitted
        // the settled move and the elapsed time and was rejected for it. This
        // is a constraint, not a fact: the model still reads the sealed delta.
        ...(runPolicy?.sceneMode === 'scene'
          ? { instruction: '正文必须写出【变化】里的移动和这段时间的推进；不要新增人物、物品、事件或往事。' }
          : {}),
      },
    });
    const issues = result.issues.map((issue) => ({
      kind: issue.kind,
      severity: issue.severity,
      attempt: issue.attempt,
    }));
    const allFellBack = result.beats.length > 0 && result.beats.every((beat) => beat.source !== 'model');
    const hard = hardKinds(result.issues);
    const reason = result.accepted
      ? null
      : result.status === 'cancelled' ? 'cancelled'
        : result.status === 'timeout' ? 'timeout'
          : `rejected:${hard.join('+') || 'unknown'}`;
    return {
      candidateId: 'trained',
      route: 'trained',
      text: result.text,
      accepted: result.accepted && result.text.trim().length > 0,
      grade: result.accepted ? 'candidate' : allFellBack ? 'program' : 'candidate_unverified',
      status: result.status,
      reason,
      issues,
      attempts: result.rawAttempts.length,
      promptChars: result.rawAttempts.reduce((sum, attempt) => sum + attempt.promptChars, 0),
      timings: {
        totalMs: result.timings.totalMs,
        attemptMs: result.timings.attemptMs,
        firstTokenMs: result.timings.firstTokenMs,
      },
      strategyVersion: result.strategyVersion,
      allFellBack,
      detail: {
        mandatory: prepared.mandatoryFactIds,
        beats: result.beats.map((beat) => ({
          id: beat.beatId, kind: beat.kind, source: beat.source, attempts: beat.attempts,
          durationMs: beat.durationMs, text: beat.text,
          issues: beat.issues.map((issue) => `${issue.severity}:${issue.kind}`),
        })),
        assembly: result.assembly,
        // Raw engine output per attempt. Truncated for the evidence file; the
        // prompt is already recorded per beat inside the strategy's evidence.
        attemptsEvidence: result.rawAttempts.map((attempt) => ({
          attempt: attempt.attempt,
          promptChars: attempt.promptChars,
          durationMs: attempt.durationMs,
          firstTokenMs: attempt.firstTokenMs,
          finishReason: attempt.finishReason,
          error: attempt.error,
          raw: attempt.raw.slice(0, 1200),
          cleaned: attempt.cleaned.slice(0, 600),
          issues: attempt.issues.map((issue) => `${issue.severity}:${issue.kind}`),
        })),
      },
    };
  },
};
