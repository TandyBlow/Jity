/** Best-of-N candidate pool (lane 12).
 *
 * Public surface for 06's product wiring and for the offline arm comparison:
 *
 *   - `runCandidatePool` executes N preregistered seeds with real per-call and
 *     whole-pool budgets and keeps every raw result;
 *   - `buildDiversityReport` measures realization diversity (surface,
 *     structure and detail organisation) and the preregistered effective
 *     repetition `1 - distinctRealizationClusters / N`;
 *   - `selectCandidate` chooses one candidate by qualification, mandatory-fact
 *     coverage, in-text repetition and cross-turn echo. It never selects by
 *     character count or a model self-score, and it never adopts an unjudged
 *     text unless the caller explicitly asks for a provisional offline result.
 *
 * The caller owns fact/perspective qualification (lane 02 `verifyNarration`
 * plus the shared 01 rubric) and passes its verdicts in. This module does not
 * write world state, does not call a model itself and does not hide a failed
 * generation.
 */
export * from './types';
export {
  DEFAULT_DIVERSITY, buildDiversityReport, clusterProfiles, comparePair, containment,
  detailTokensOf, effectiveRepetition, jaccard, normalizeProse, profileSample, shinglesOf,
  splitSentences, textMetrics,
} from './diversity';
export { selectCandidate, transportFailed } from './select';
export { runCandidatePool, type PoolGenerate } from './pool';
