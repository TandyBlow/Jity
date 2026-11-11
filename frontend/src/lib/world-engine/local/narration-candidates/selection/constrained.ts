/** C-route adaptation: lane 04's constrained fact-to-prose candidate.
 *
 * 04 owns the fact skeleton, beat plan and per-beat verification; this adapter
 * only passes the settled facts, the read-only scene hints and the caller's
 * limits, then maps the candidate's own verdict back.
 *
 * Two honest grades:
 *   - `candidate`: at least one beat was written by a model (or an injected
 *     composer) and every beat passed verification.
 *   - `program`: every beat was written by the program realizer. The text is
 *     fact-grounded and verified, but it is a downgrade, not model prose; the
 *     page must label it.
 *
 * The facts-only packet is used on purpose. The full-state packet would require
 * a `get_state` anchor (version/digest/previousPointId) that the narration call
 * does not carry; inventing one would be a second truth. Scene detail comes
 * from the caller's already-settled `BeatSceneContext`.
 */
import { generateCandidate as generateConstrained } from '../constrained';
// Lane 07's prose composer. It is deterministic (no model), reads only the
// skeleton and its licensed material, and plugs into 04's per-beat composer
// contract. It is used for the program route only; the model route keeps the
// model writer.
import { createBeatComposer } from '../prose-composer';

/** Lane 07's composer writes scene/move/close beats, but it has no branch for
 * 04's `result` beat and would fall through to a close texture. The settled
 * result line is mandatory (lane 04 v1.3), so the adapter lets 04's own
 * realizer write that one beat. */
const composerWithResultBeat = (() => {
  const composer = createBeatComposer();
  const mixed = async (request: Parameters<typeof composer>[0], options?: Parameters<typeof composer>[1]) => {
    if (request.beat.kind === 'result') throw new Error('result_beat_uses_04_realizer');
    return composer(request, options);
  };
  Object.defineProperty(mixed, 'name', { value: 'prose-composer+04-result' });
  return mixed;
})();
import type { CandidateNarrationResult, NarrationCandidate, PreparedNarration } from './types';

/** `program+model-failed` is still program text: the model attempt failed its
 * own beat verification and the realizer wrote that beat. Only a composer that
 * is not program-prefixed (the model itself, or an injected external composer)
 * counts as model prose. */
const isProgramComposer = (composer: string): boolean =>
  composer === 'fallback' || composer.startsWith('program');

function sceneHints(prepared: PreparedNarration) {
  const scene = prepared.scene;
  const presentNotes: Record<string, string> = {};
  for (const person of scene.present ?? []) {
    if (person.note) presentNotes[person.name] = person.note;
  }
  const objectNotes: Record<string, string> = {};
  for (const object of scene.objects ?? []) {
    if (object.note) objectNotes[object.name] = object.note;
  }
  return {
    placeNote: [scene.location, ...(scene.placeNotes ?? [])].filter(Boolean).join('：'),
    presentNotes,
    objectNotes,
    ...(scene.previousAction ? { previousAction: scene.previousAction } : {}),
  };
}

export const CONSTRAINED_CANDIDATE: NarrationCandidate = {
  id: 'constrained',
  route: 'constrained',
  version: 'constrained-candidate-v1',
  label: '04/07 · constrained fact-to-prose',
  requires: {
    modules: ['local/narration-candidates/constrained'],
    template: 'program realizer (no model) unless mode=model',
  },
  productDefault: false,
  availability(point, prepared) {
    // The world-opening narration is a one-off scene the player reads first;
    // keep the existing in-model writer there. Program prose starts with the
    // first settled round.
    if (!point.before) return { available: false, reason: 'root_point' };
    if (!prepared.facts.facts.some((fact) => fact.kind === 'at' || fact.kind === 'moved')) {
      return { available: false, reason: 'facts_packet_without_scene' };
    }
    return { available: true, reason: null };
  },
  async run({ engine, point, prepared, onProgress, policy: runPolicy }): Promise<CandidateNarrationResult> {
    const mode = runPolicy?.mode === 'model' ? 'model' : 'program';
    const result = await generateConstrained({
      engine,
      committed: {
        anchor: prepared.facts.anchor,
        facts: prepared.facts.facts,
        timeAdvance: point.delta.timeAdvance ?? null,
        inputText: prepared.inputText,
        priorText: point.priorText ?? null,
      },
      inputText: prepared.inputText,
      priorText: point.priorText ?? null,
      signal: point.signal,
      onProgress: (progress) => onProgress?.({
        text: progress.text, elapsedMs: progress.elapsedMs, verified: progress.verified, attempt: 0,
      }),
      policy: {
        mode,
        viewpointId: prepared.viewpointId,
        scene: sceneHints(prepared),
        resultsText: point.settledResults?.length ? point.settledResults.join('；') : null,
        // The program realizer states one sentence per settled fact; a thin
        // point (time + presence) is short on purpose. 40 keeps it readable
        // without padding it with invented detail.
        minChars: 40,
        // Variable length: a rich turn must not be rejected for being long
        // (6e3a: four model beats composed >500 chars and the whole candidate
        // was rejected as too_long, falling back to program). The cap only
        // guards a runaway answer.
        maxChars: 1200,
        requireTime: prepared.policy.requireTime ?? false,
        sanityStyle: 'number',
        ...(mode === 'program' ? { composer: composerWithResultBeat } : {}),
        model: {
          maxTokensPerBeat: prepared.policy.maxTokens ?? 160,
          temperature: prepared.policy.temperature ?? 0.45,
          timeoutMs: prepared.policy.timeoutMs ?? 90_000,
          maxAttempts: 2,
        },
      },
    });
    const modelComposed = result.composers.length > 0 && !result.composers.every(isProgramComposer);
    const programBeats = result.composers.filter(isProgramComposer).length;
    // A scene with some model beats and some program beats is MIXED, not model
    // prose: the 448e run had two model beats and two program beats but was
    // labelled 模型正文 on the page.
    const grade = !result.accepted
      ? (modelComposed ? 'candidate_unverified' : 'program')
      : modelComposed && programBeats > 0 ? 'candidate_with_program_sentences'
        : modelComposed ? 'candidate' : 'program';
    const hard = result.issues.filter((issue) => issue.severity === 'hard').map((issue) => issue.kind);
    return {
      candidateId: 'constrained',
      route: 'constrained',
      text: result.text,
      accepted: result.accepted && result.text.trim().length > 0,
      grade,
      status: result.status === 'rejected' ? 'rejected' : result.status,
      reason: result.accepted ? null : result.status === 'cancelled' ? 'cancelled' : `rejected:${hard.join('+') || 'unknown'}`,
      issues: result.issues.map((issue) => ({ kind: issue.kind, severity: issue.severity })),
      attempts: result.rawAttempts.length,
      promptChars: result.rawAttempts.reduce((sum, beat) => sum + (beat.prompt?.length ?? 0), 0),
      timings: {
        totalMs: result.timings.totalMs,
        attemptMs: result.timings.beatsMs ?? [],
        firstTokenMs: result.timings.firstTextMs ?? null,
      },
      strategyVersion: result.strategyVersion,
      allFellBack: !modelComposed,
      detail: {
        composers: result.composers,
        // Flattened to strings: an acceptance driver serializes this record, and
        // nested objects became "[object]" in 09's evidence, hiding why every
        // model beat failed.
        coverage: (result.verification.coverage as unknown[]).map((entry) => typeof entry === 'object' ? JSON.stringify(entry) : String(entry)),
        unverifiedSentences: result.verification.unverifiedSentences,
        hiddenFactIds: result.verification.hiddenFactIds,
        plan: result.plan?.beats.map((beat) => `${beat.id}:${beat.kind}:${beat.factIds.join(',')}`) ?? null,
        beats: result.rawAttempts.map((beat) => ({
          beatId: beat.beatId,
          kind: beat.kind,
          source: beat.source,
          ms: Math.round(beat.ms),
          text: beat.text,
          issues: beat.issues.map((issue) => `${issue.kind}/${issue.severity}: ${issue.detail ?? ''}${issue.sentence ? ` | ${issue.sentence}` : ''}`),
        })),
      },
    };
  },
};
