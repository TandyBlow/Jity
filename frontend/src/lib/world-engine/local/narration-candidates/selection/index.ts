/** Public entry of the narration candidate selection layer.
 *
 * The product integration imports only `createNarrationRunner` (and, for an
 * internal QA run, nothing else). Everything below it is candidate adaptation.
 */
export { createNarrationRunner, SHIPPED_CANDIDATES, internalCandidateOverride } from './runner';
export { TRAINED_CANDIDATE } from './trained';
export { CONSTRAINED_CANDIDATE } from './constrained';
export {
  narrationPolicy, narrationScene, prepareNarration, projectNarrationFacts, serializeNarrationInput,
} from './projection';
export type {
  CandidateAvailability, CandidateIssueSummary, CandidateNarrationResult, CandidateRunArgs,
  NarrationCandidate, NarrationPoint, NarrationProgress, NarrationRunResult, NarrationRunner,
  NarrationRunnerOptions, PreparedNarration, ProgramFallback,
} from './types';
