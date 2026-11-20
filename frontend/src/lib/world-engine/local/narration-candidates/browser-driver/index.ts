/** Shared browser candidate driver. Import from here so the Node entry only
 * depends on this barrel. */
export { applyProjectedPoint, buildScenarios, freeDayScenarios, projectWorldFacts, scenarioFromProjection, sceneFromState, shortWorldScenarios } from './scenarios';
export type { FreeDayWorldAsset, ProjectedPoint, ScenarioSet } from './scenarios';
export { attachEngine, disposeEngines, inspectCandidate, loadEngine, loadedModels, prepare, probeEngine, runOne, validateCandidateResult } from './run';
export type { EngineProbeConfig, InspectResult, LoadConfig, PrepareConfig, RunOneConfig, ScenarioSummary } from './run';
export type {
  AttemptEvidence, CandidateResult, CandidateScenario, CandidateSpec, EngineEvidence,
  GenerateCandidate, GenerateCandidateArgs, ProgressEvent, RunEvidence, SceneGrounding,
} from './types';
