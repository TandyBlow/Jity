/** Independent narration-quality review types.
 *
 * This module is deliberately independent of the generation-side verifier in
 * `local/narration-generation/`: it reads the dataset row (`视角` /
 * `上回合状态` / `本回合变化` / `本回合状态`) directly and derives its own
 * scene projection, so a bug or an added allowance in the generation verifier
 * cannot silently hide a defect here.
 *
 * Three severities, matching the product quality split:
 *  - `fact`: a contradiction with, or an invention beyond, the settled state.
 *    A single one makes the text unusable regardless of style.
 *  - `style`: readable-text defects (field recital, loops, echo, punctuation).
 *    Not a fact error, but a "give this to a player" failure.
 *  - `review`: a statement a machine cannot decide. It is never a pass; a
 *    human must read it. The report keeps the sentence and its input basis.
 *
 * `reviewer` is always the checker identity. There is no field to claim a
 * human signature; human review is recorded separately by whoever does it.
 */

export type Severity = 'fact' | 'style' | 'review';

export type FindingKind =
  // Facts: contradictions with settled state.
  | 'fact.actor_swap'
  | 'fact.direction_reversed'
  | 'fact.wrong_source'
  | 'fact.wrong_number'
  | 'fact.false_position'
  | 'fact.item_misattribution'
  | 'fact.gender'
  | 'fact.state_contradiction'
  | 'fact.body_mark_added'
  | 'fact.wrong_place'
  | 'fact.time_added'
  // Facts: inventions without a settled basis.
  | 'fact.event_added'
  | 'fact.sound_added'
  | 'fact.object_added'
  | 'fact.past_added'
  | 'fact.trait_as_event'
  | 'fact.object_speaks'
  | 'fact.promise_added'
  | 'fact.knowledge_leak'
  | 'fact.viewpoint_interiority'
  // Facts: omissions of settled, player-visible changes.
  | 'fact.time_missing'
  | 'fact.move_omitted'
  | 'fact.task_omitted'
  | 'fact.sanity_omitted'
  | 'fact.personality_omitted'
  | 'fact.item_state_omitted'
  // Style.
  | 'style.status_panel'
  | 'style.field_sentence'
  | 'style.loop'
  | 'style.echo_prior'
  | 'style.repeated_opening'
  | 'style.roster_recital'
  | 'style.filler'
  | 'style.punctuation'
  | 'style.truncated'
  | 'style.premature_closure'
  | 'style.meta'
  | 'style.placeholder'
  // Undecidable.
  | 'review.unbound'
  | 'review.pronoun'
  | 'review.number'
  | 'review.speech_act'
  | 'review.micro_action'
  | 'review.object_added'
  | 'review.trait_as_event'
  | 'review.unseen_entity'
  | 'review.natural_sanity'
  | 'review.tone';

export interface Finding {
  kind: FindingKind;
  severity: Severity;
  /** The narration sentence (or clause) the finding is about. */
  sentence: string;
  /** Why this fired, in plain language. */
  detail: string;
  /** Verbatim input substrings that justify the judgement. */
  basis: string[];
  /** Fact ids from the independent projection, when applicable. */
  factIds?: string[];
}

export interface SentenceReview {
  index: number;
  paragraph: number;
  sentence: string;
  /** Independent fact ids this sentence expresses or contradicts. */
  factIds: string[];
  /** Verbatim input substrings used as basis. */
  basis: string[];
  findings: Finding[];
  /** `fact_error` if any fact finding, `needs_review` if any review item or
   * no binding, otherwise `fact_clean`. Never means "quality passed". */
  judgement: 'fact_error' | 'needs_review' | 'fact_clean';
}

export interface MandatoryReview {
  factId: string;
  summary: string;
  expressed: boolean;
  /** The sentence that expresses it, if any. */
  sentence: string | null;
  /** For sanity/personality: literal expression vs reaction (needs review). */
  form: 'literal' | 'reaction' | 'missing';
}

export interface ReviewReport {
  id: string;
  chars: number;
  viewpoint: string | null;
  time: {
    committed: string | null;
    minutes: number | null;
    /** Whether the narration states the settled advance. */
    expressed: boolean;
    forms: string[];
    /** True when the same advance is stated more than once. */
    repeated: number;
  };
  mandatory: MandatoryReview[];
  sentences: SentenceReview[];
  findings: Finding[];
  counts: Record<Severity, number>;
  /** Facts clean: no detectable contradiction, invention or omission. */
  factsClean: boolean;
  /** Readable-as-prose: no blocking style defect. Field/register findings are
   * reported but not treated as blocking here. */
  readable: boolean;
  blockingStyles: string[];
  metrics: {
    sentences: number;
    paragraphs: number;
    dialogueRatio: number;
    boundSentences: number;
    unboundSentences: number;
    styleFindings: number;
  };
  /** Metadata check for integration: a text made only of settled-fact lines,
   * with no dialogue, is what a program fallback emits. It must not be labelled
   * model prose without per-segment metadata. */
  fallbackSuspicion: {
    suspected: boolean;
    factOnlySentences: number;
    sentences: number;
    dialogueRatio: number;
    panelShare: number;
    note: string;
  };
  reviewer: 'ai-independent-checker-v1';
  /** Explicit reminder stored in every report. */
  disclaimer: string;
}

export interface ReviewOptions {
  /** name -> 'male' | 'female' from a reviewed registry (never model input). */
  genders?: Record<string, 'male' | 'female'>;
  /** Accepted narration of earlier turns of the same session, oldest first. */
  priorTexts?: string[];
  /** Minimum characters for a whole-scene text. */
  minChars?: number;
  /** Intended length; used to judge premature closure. */
  targetChars?: number;
  /** Product audit (default): a settled task must be narrated literally.
   * Supervision screening can relax this to a review item. */
  strict?: boolean;
  /** Writing-instruction strings that must never appear in the prose. */
  promptEchoMarkers?: string[];
  /** Names the page offered as visible/known; anything else is unlicensed. */
  licensedEntities?: string[];
  /** Beat ceiling (hard) when the caller generates one beat at a time. */
  maxChars?: number;
  /** Strings the viewpoint must not reveal. */
  mustNotReveal?: string[];
  /** Entities the viewpoint cannot know about yet. */
  unseenEntities?: string[];
}
