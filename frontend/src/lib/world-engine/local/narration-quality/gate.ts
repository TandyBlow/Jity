/** Integration gate for the independent checker.
 *
 * This is a decision helper for 06's page loop, not a quality verdict. It
 * answers one narrow question: may this text be shown as fact-clean model
 * prose, must it be held, or must it be regenerated?
 *
 * Rules (deliberately conservative):
 *  - any `fact` finding blocks;
 *  - a blocking style finding blocks (field recital, loop, echo, truncation,
 *    roster recital, meta);
 *  - `fallbackSuspicion` does not block by itself, but it forces the caller to
 *    provide the per-segment source: a text that is mostly settled-fact lines
 *    cannot be labelled model prose without it;
 *  - `review` items never block generation and never count as a pass.
 *
 * No rule here loosens the checker: the gate can only hold or regenerate.
 */

import type { ReviewReport } from './types';

export type GateDecision = 'accept_as_model_prose' | 'hold_for_review' | 'regenerate';

export interface GatePolicy {
  /** Per-segment source of the text, when the pipeline knows it.
   * `draft`/`program` are 06's provenance labels; `program_fallback` is the
   * earlier name for the same state. None of them may pass as model prose. */
  textSource?: 'model' | 'program_fallback' | 'program' | 'mixed' | 'draft' | 'unknown';
  /** Minimum characters for a whole-scene text. */
  minChars?: number;
  /** A hard ceiling for a single beat. */
  maxChars?: number;
  /** Corpus screening only: allow sanity/level number sentences. Product
   * defaults to blocking them, because a player never reads a status field. */
  allowFieldSentences?: boolean;
}

export interface GateResult {
  decision: GateDecision;
  /** Machine-readable reasons, always present, never a human judgement. */
  reasons: string[];
  factFindings: number;
  blockingStyles: string[];
  reviewItems: number;
  fallbackSuspected: boolean;
}

export function gateNarration(report: ReviewReport, policy: GatePolicy = {}): GateResult {
  const reasons: string[] = [];
  const factFindings = report.counts.fact;
  const fieldSentences = report.findings.filter((entry) => entry.kind === 'style.field_sentence').length;
  const blockingStyles = policy.allowFieldSentences
    ? report.blockingStyles
    : [...report.blockingStyles, ...(fieldSentences ? ['style.field_sentence'] : [])];
  const reviewItems = report.counts.review;
  const fallbackSuspected = report.fallbackSuspicion.suspected;

  if (factFindings > 0) reasons.push(`fact_findings:${factFindings}`);
  if (blockingStyles.length) reasons.push(`blocking_style:${blockingStyles.join(',')}`);
  if (policy.minChars !== undefined && report.chars < policy.minChars) reasons.push(`too_short:${report.chars}<${policy.minChars}`);
  if (policy.maxChars !== undefined && report.chars > policy.maxChars) reasons.push(`too_long:${report.chars}>${policy.maxChars}`);
  // Only a point that actually advances time has to state it.
  if (report.time.minutes !== null && !report.time.expressed) reasons.push('time_not_expressed');
  if (fallbackSuspected && !policy.textSource) reasons.push('fallback_suspected_source_unknown');
  if (fallbackSuspected && policy.textSource === 'program_fallback') reasons.push('program_fallback_cannot_be_model_prose');
  if (fallbackSuspected && policy.textSource === 'model') reasons.push('fallback_suspected_but_labelled_model');
  if (policy.textSource === 'mixed') reasons.push('mixed_source_cannot_be_whole_model_prose');
  if (policy.textSource === 'draft') reasons.push('draft_source_cannot_be_accepted_prose');
  if (policy.textSource === 'program') reasons.push('program_fallback_cannot_be_model_prose');
  if (policy.textSource === 'unknown') reasons.push('source_unknown_cannot_be_model_prose');

  let decision: GateDecision = 'accept_as_model_prose';
  if (factFindings > 0 || blockingStyles.length || reasons.includes('time_not_expressed')
    || reasons.some((reason) => reason.startsWith('too_short') || reason.startsWith('too_long'))
    || policy.textSource === 'mixed' || policy.textSource === 'program_fallback'
    || policy.textSource === 'program' || policy.textSource === 'draft'
    || policy.textSource === 'unknown'
    || reasons.includes('fallback_suspected_but_labelled_model')) {
    decision = 'regenerate';
  } else if (fallbackSuspected || reviewItems > 0) {
    decision = 'hold_for_review';
  }

  return {
    decision,
    reasons,
    factFindings,
    blockingStyles,
    reviewItems,
    fallbackSuspected,
  };
}
