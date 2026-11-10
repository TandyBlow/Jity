/** Best-of-N candidate pool: contracts only.
 *
 * The pool is a *selection* layer, not a second writer and not a second fact
 * authority. It receives the raw output of N independent generations for ONE
 * settled point, keeps every raw text and timing, computes realization
 * diversity from the texts themselves, and returns the one candidate the
 * caller may submit plus the full rejection record.
 *
 * Nothing here reads a reference answer or a training target. Diversity is
 * measured by expression structure, narrative rhythm and detail organisation,
 * never by "same mandatory facts", because two candidates can share every
 * mandatory fact and still be the same scene written twice.
 */

/** One raw generation. `text` is what the model returned, unedited. */
export interface CandidateSample {
  /** Stable id, e.g. `frozen-row-0012:s17`. */
  id: string;
  /** Deterministic sampling seed used for this call. */
  seed: number;
  text: string;
  /** Transport outcome. A partial text from a failed call stays here for
   * evidence; it is never silently completed or adopted. */
  status: 'ok' | 'empty' | 'error' | 'timeout' | 'cancelled' | 'truncated';
  error?: string | null;
  /** Wall clock of this call; null when the caller did not measure it. */
  totalMs: number | null;
  firstTokenMs?: number | null;
  /** Model tokens emitted, when the runner can measure them. */
  tokens?: number | null;
}

/** Fact/perspective screen result for one candidate, produced by the caller's
 * committed checker (lane 02 `verifyNarration`) plus the shared 01 rubric when
 * that rubric exists. This module never invents a quality verdict. */
export interface CandidateAssessment {
  id: string;
  /** `true` = the checker accepted every hard rule; `false` = at least one
   * hard issue; `null` = not judged (rubric/checker unavailable). */
  qualified: boolean | null;
  /** Hard issue kinds, copied verbatim from the checker. */
  hardIssueKinds: string[];
  /** Explicit viewpoint verdict from the same checker. `false` means the text
   * has a viewpoint/pronoun/knowledge finding; the selector must not adopt it.
   * `undefined`/`null` means the caller did not separate this dimension. */
  perspectiveQualified?: boolean | null;
  /** Viewpoint/pronoun/knowledge findings behind `perspectiveQualified`. */
  perspectiveIssueKinds?: string[];
  /** Settled facts the checker proved expressed / required. */
  mandatoryCovered: number;
  mandatoryTotal: number;
  /** Human-readable evidence summary; never shown to the player. */
  detail?: string;
}

export interface DiversityConfig {
  /** Character n-gram size for the surface fingerprint. */
  ngram: number;
  /** Surface Jaccard at/above which two texts are a paraphrase duplicate. */
  surfaceNearDuplicate: number;
  /** Share of one text contained in the other for a copy/rewrite. */
  containmentDuplicate: number;
  /** Structural fingerprint Jaccard for the same skeleton. */
  skeletonStructure: number;
  /** Ordered detail-organisation Jaccard for the same skeleton. */
  skeletonDetail: number;
  /** Mean best sentence-to-sentence similarity for a synonym paraphrase. */
  skeletonAligned: number;
  /** Below this whole-text surface overlap the skeleton rule does not fire
   * (completely different wording can legitimately share a rhythm). */
  skeletonSurfaceFloor: number;
  /** Opening AND closing similarity for the template-edge rule. */
  edgeDuplicate: number;
  /** Texts shorter than this use the short-template rule. */
  shortTextChars: number;
  /** Surface Jaccard for two very short outputs to count as one template. */
  shortTextSurface: number;
  /** Scores within this distance of a threshold make the pair ambiguous and
   * require independent review instead of an automatic duplicate call. */
  ambiguityBand: number;
  /** Max sentence-count difference for the opening/closing rule. */
  sentenceCountTolerance: number;
}

export interface SampleProfile {
  id: string;
  seed: number;
  /** Normalized text used for surface comparison. */
  normalized: string;
  sentences: string[];
  /** Character n-gram set of `normalized`. */
  surfaceShingles: string[];
  /** Ordered per-sentence rhythm tokens (kind + length bucket + clause count). */
  structureTokens: string[];
  /** Ordered licensed-entity mentions, deduplicated by position. */
  detailTokens: string[];
  chars: number;
  dialogueRatio: number;
  sentenceLengths: number[];
}

export interface PairVerdict {
  a: string;
  b: string;
  homogeneous: boolean;
  reasons: string[];
  surfaceJaccard: number;
  containment: number;
  alignedJaccard: number;
  structureJaccard: number;
  /** null when neither text names a licensed entity (not comparable). */
  detailJaccard: number | null;
  openingJaccard: number;
  closingJaccard: number;
  ambiguous: boolean;
}

export interface RealizationCluster {
  id: number;
  members: string[];
}

export interface DiversityReport {
  sampleCount: number;
  profiles: SampleProfile[];
  pairs: PairVerdict[];
  clusters: RealizationCluster[];
  /** 1 - distinctRealizationClusters / sampleCount. The preregistered formula;
   * the denominator is always the number of generated samples. */
  effectiveRepetition: number;
  /** Clusters that contain at least one fact-qualified candidate. */
  qualifiedClusters: number | null;
  /** Distinct realization clusters computed only over fact-qualified inputs.
   * This is a count, never a replacement denominator for repetition. */
  qualifiedDistinctClusters: number | null;
  qualifiedCount: number | null;
  /** Pairs whose verdict sits inside the ambiguity band. */
  ambiguousPairs: Array<{ a: string; b: string; reasons: string[] }>;
}

export interface TextMetrics {
  chars: number;
  sentences: number;
  /** Share of normalized sentences that occur more than once in one text. */
  repeatedSentenceRatio: number;
  /** Share of long clauses that repeat three or more times in one text. */
  repeatedClauseRatio: number;
  /** Share of sentences with almost no content (short or filler-only). */
  emptySentenceRatio: number;
  /** Bigram containment of `priorText` inside this text; 0 without prior. */
  priorEcho: number;
  dialogueRatio: number;
}

export interface SelectionCandidate {
  id: string;
  seed: number;
  text: string;
  /** Transport outcome when the caller has it. A failed call is never
   * eligible even if a partial text leaked out of the engine. */
  status?: CandidateSample['status'];
}

export interface SelectionOptions {
  /** Product default false: an unjudged candidate is never adopted. The
   * offline arm comparison sets true and labels the result provisional. */
  allowProvisional?: boolean;
  priorText?: string | null;
  /** Licensed names used only for detail-organisation comparison. */
  licensedEntities?: readonly string[];
  diversity?: Partial<DiversityConfig>;
}

export interface CandidateRank {
  id: string;
  eligible: boolean;
  /** Ordered decision trace with the concrete values behind it. */
  reason: string;
  mandatoryCovered: number;
  mandatoryTotal: number;
  metrics: TextMetrics;
}

export interface SelectionRejection {
  id: string;
  reason: 'not_qualified' | 'not_perspective_qualified' | 'unjudged' | 'empty' | 'transport_failed' | 'budget_exceeded' | 'homogeneous_duplicate';
  detail: string;
}

export interface SelectionDecision {
  selectedId: string | null;
  /** `provisional` means the fact/perspective verdict came from the offline
   * screen before the shared 01 rubric landed; it is not a product verdict. */
  verdict: 'adopted' | 'provisional' | 'none';
  reason: string;
  ranking: CandidateRank[];
  rejected: SelectionRejection[];
  /** Every input candidate id, in seed order. Nothing is dropped from the
   * evidence even when rejected. */
  considered: string[];
}

export interface PoolConfig {
  seeds: readonly number[];
  /** Real parallel calls on the target runtime. The browser engine is serial;
   * 1 is the honest product default. */
  concurrency: number;
  perCallTimeoutMs: number;
  /** Whole-pool budget including every call and retry the caller performs. */
  totalBudgetMs: number;
}

export interface PoolCallResult {
  text: string;
  finishReason: string | null;
  totalMs: number;
  firstTokenMs?: number | null;
  tokens?: number | null;
}

export interface PoolSample extends CandidateSample {
  startedAtMs: number;
  endedAtMs: number;
}

export interface PoolRun {
  samples: PoolSample[];
  /** Submit-to-selection wall clock (including failed calls and waits). */
  wallMs: number;
  requested: number;
  completed: number;
  failed: number;
  peakConcurrency: number;
  budgetExceeded: boolean;
}
