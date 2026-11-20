/** Independent narration-quality review.
 *
 * Usage:
 *   const report = reviewNarration({ id, input, text, options });
 *   report.findings          // fact / style / review items
 *   report.sentences         // per-sentence evidence record
 *   report.mandatory         // settled changes and whether they were narrated
 *
 * The report never claims a human pass. `counts.fact === 0` means "no
 * mechanically detectable contradiction or invention", not "good prose".
 */
export type {
  DatasetInput, DeltaBlock, ItemBlock, MoveFact, PersonBlock, PersonFact, PlaceBlock,
  SceneProjection, TaskState,
} from './scene';
export { parseViewpoint, parseMinutes, projectScene } from './scene';
export type {
  Finding, FindingKind, MandatoryReview, ReviewOptions, ReviewReport, SentenceReview, Severity,
} from './types';
export { reviewNarration } from './review';
