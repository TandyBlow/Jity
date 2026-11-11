/** C-route adaptation: lane 04's constrained fact-to-prose candidate.
 *
 * 04 owns the fact skeleton and beat plan; this adapter passes the settled
 * facts, the read-only scene hints and the caller's limits, then returns the
 * model's beat text unchanged. There is no program route: program narration was
 * removed (NARRATION-RAW-OUTPUT-20261111).
 *
 * The facts-only packet is used on purpose. The full-state packet would require
 * a `get_state` anchor (version/digest/previousPointId) that the narration call
 * does not carry; inventing one would be a second truth. Scene detail comes
 * from the caller's already-settled `BeatSceneContext`.
 */
import { generateCandidate as generateConstrained } from '../constrained';
import type { CandidateNarrationResult, NarrationCandidate, PreparedNarration } from './types';

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
  async run({ engine, point, prepared, onProgress }): Promise<CandidateNarrationResult> {
    const result = await generateConstrained({
      engine,
      committed: {
        anchor: prepared.facts.anchor,
        facts: prepared.facts.facts,
        timeAdvance: point.delta.timeAdvance ?? null,
        inputText: prepared.inputText,
      },
      inputText: prepared.inputText,
      signal: point.signal,
      onProgress: (progress) => onProgress?.({
        text: progress.text, elapsedMs: progress.elapsedMs, verified: progress.verified, attempt: 0,
      }),
      policy: {
        viewpointId: prepared.viewpointId,
        scene: sceneHints(prepared),
        resultsText: point.settledResults?.length ? point.settledResults.join('；') : null,
        // 04's structured records are material for the beat prompt (who acted,
        // on whom, which outcome). They are not used to judge the prose.
        settledFacts: point.settledFacts ?? null,
        // The world's own names, so the facts-packet projection can refuse an
        // offscreen place or an unlisted person (09 35ad listed a whole route
        // through 西门/西回廊/检修口 with no move fact and it passed).
        worldNames: {
          characters: Object.values(point.after.initial.characters).map((entity) => entity.name),
          locations: Object.values(point.after.initial.locations).map((entity) => entity.name),
          items: Object.values(point.after.initial.items).map((entity) => entity.name),
        },
        sanityStyle: 'number',
        // Beat length limits are prompt material only; the answer is never
        // measured or cut.
        minChars: 18,
        maxChars: 380,
        model: {
          maxTokensPerBeat: prepared.policy.maxTokens ?? 480,
          temperature: prepared.policy.temperature ?? 0.45,
          timeoutMs: prepared.policy.timeoutMs ?? 90_000,
          maxAttempts: 1,
        },
      },
    });
    return {
      candidateId: 'constrained',
      route: 'constrained',
      text: result.text,
      status: result.status === 'accepted' ? 'accepted'
        : result.status === 'cancelled' ? 'cancelled'
          : result.status === 'error' ? 'error' : 'empty',
      attempts: result.rawAttempts.length,
      promptChars: result.rawAttempts.reduce((sum, beat) => sum + (beat.prompt?.length ?? 0), 0),
      timings: {
        totalMs: result.timings.totalMs,
        attemptMs: result.timings.beatsMs ?? [],
        firstTokenMs: result.timings.firstTextMs ?? null,
      },
      strategyVersion: result.strategyVersion,
      detail: {
        plan: result.plan?.beats.map((beat) => `${beat.id}:${beat.kind}:${beat.factIds.join(',')}`) ?? null,
        segments: result.segments.map((segment) => ({ id: segment.beatId, kind: segment.kind, source: 'model', text: segment.text })),
        beats: result.rawAttempts.map((beat) => ({
          beatId: beat.beatId,
          kind: beat.kind,
          source: beat.source,
          ms: Math.round(beat.ms),
          text: beat.text,
          prompt: beat.prompt,
          raw: beat.raw,
          error: beat.error ?? null,
        })),
        ...(result.detail ? { failure: result.detail } : {}),
      },
    };
  },
};
