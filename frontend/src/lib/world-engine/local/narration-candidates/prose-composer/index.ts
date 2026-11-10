/** Route C language layer: turn a read-only fact skeleton into prose. */

export * from './types';
export { composeProse, validateScene, PROSE_STRATEGY_VERSION } from './compose';
export { generateCandidate, CANDIDATE_STRATEGY_VERSION } from './candidate';
export type {
  CandidateIssue, CandidatePolicy, CandidateProgress, CandidateResult, GenerateCandidateArgs,
} from './candidate';
export { sceneFromCommitted } from './from-committed';
export type { AdaptedScene, CommittedAdapterPolicy, CommittedFactLike, CommittedLike } from './from-committed';
export { buildLicense, guardSentence, echoOfPrior } from './guard';
export { composeConstrainedBeat, createBeatComposer, sceneFromBeatRequest } from './from-beat';
export type {
  BeatComposerLike, BeatDirectiveLike, BeatFactLike, ComposeBeatRequestLike, ComposeBeatResultLike,
  SceneSkeletonLike,
} from './from-beat';
