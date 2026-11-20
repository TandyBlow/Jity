/** B-route adaptation: lane 02's committed-fact narration strategy (beats).
 *
 * The strategy owns prompt construction and returns the model's own text. This
 * adapter only supplies:
 *   - the fact packet (projected from the sealed delta by `projection.ts`),
 *   - lane 01's serialized input (licensing evidence; beats do not re-use it
 *     as the prompt),
 *   - the writing policy (viewpoint, roster, time, lengths, temperature),
 *   - real progress increments and the model's text, unmapped and unedited.
 */
// The product uses lane 02's current strategy module directly (one source of
// truth with their measured arm), not a vendored copy.
import { generateCandidate, NARRATION_STRATEGY_VERSION } from '../../narration-generation';
import type { NarrationIssue } from '../../narration-generation/types';
import type { CandidateNarrationResult, NarrationCandidate } from './types';

const hardKinds = (issues: NarrationIssue[]): string[] =>
  [...new Set(issues.filter((issue) => issue.severity === 'hard').map((issue) => issue.kind))];

export const TRAINED_CANDIDATE: NarrationCandidate = {
  id: 'trained',
  route: 'trained',
  version: `trained-beats:${NARRATION_STRATEGY_VERSION}`,
  label: '02-narration · committed-fact beats',
  requires: {
    modules: ['local/narration-generation', 'local/narration-input'],
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
      signal: point.signal,
      onProgress: (state) => onProgress?.({
        text: state.text, elapsedMs: state.elapsedMs, verified: state.verified, attempt: state.attempt,
      }),
      policy: {
        ...prepared.policy,
        // Variable-length contract: a short complete scene is allowed; the floor
        // only rejects a near-empty answer.
        minChars: 20,
        mode: runPolicy?.sceneMode === 'scene' ? 'scene' : 'beats',
        scene: prepared.scene,
        // Whole-scene prose on the deployable instruct model uses the
        // closed-book prompt shape (02's measured arm); the serialized state
        // record is the training shape and is kept for fine-tuned checkpoints.
        ...(runPolicy?.sceneMode === 'scene'
          ? { promptShape: runPolicy.promptShape ?? 'prose-facts' }
          : {}),
        // Scene mode otherwise writes a static tableau: the page model omitted
        // the settled move and the elapsed time and was rejected for it. This
        // is a constraint, not a fact: the model still reads the sealed delta.
        ...(runPolicy?.sceneMode === 'scene'
          ? { instruction: '正文必须写出【变化】里的移动和这段时间的推进；不要新增人物、物品、事件或往事。' }
          : {}),
      },
    });
    return {
      candidateId: 'trained',
      route: 'trained',
      text: result.text,
      status: result.status === 'accepted' ? 'accepted'
        : result.status === 'cancelled' ? 'cancelled'
          : result.status === 'error' ? 'error' : 'empty',
      attempts: result.rawAttempts.length,
      promptChars: result.timings.promptChars ?? 0,
      timings: {
        totalMs: result.timings.totalMs,
        attemptMs: result.rawAttempts.map((attempt) => attempt.ms ?? attempt.durationMs ?? 0),
        firstTokenMs: result.timings.firstTextMs ?? null,
      },
      strategyVersion: result.strategyVersion,
      detail: {
        segments: result.segments.map((segment) => ({ id: segment.id, kind: segment.kind, source: segment.source, text: segment.text })),
        beats: result.beats.map((beat) => ({
          beatId: beat.beatId, kind: beat.kind, factId: beat.factId ?? null,
          text: beat.text, prompt: beat.prompt, raw: beat.raw, ms: Math.round(beat.ms ?? beat.durationMs ?? 0),
        })),
      },
    };
  },
};
