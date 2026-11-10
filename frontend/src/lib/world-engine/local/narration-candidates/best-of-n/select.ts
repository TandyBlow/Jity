/** Deterministic candidate selection.
 *
 * The selector answers one question: which raw sample may this settled point
 * submit? It is deliberately NOT "the longest" and NOT "the model's own
 * score":
 *
 *   1. hard fact/perspective qualification from the caller's checker;
 *   2. mandatory-fact coverage;
 *   3. in-text repetition / empty sentences;
 *   4. cross-turn echo against the already accepted prior narration;
 *   5. seed order as the final deterministic tie-break.
 *
 * Character count and a model self-score are absent from the comparator. An
 * unjudged candidate is never adopted by default: `allowProvisional` exists
 * only for the offline arm comparison, and marks the decision provisional.
 */
import { comparePair, profileSample, textMetrics } from './diversity';
import type {
  CandidateAssessment, CandidateRank, CandidateSample, DiversityConfig, SelectionCandidate,
  SelectionDecision, SelectionOptions, SelectionRejection,
} from './types';

const SEED_ORDER = (a: { seed: number; id: string }, b: { seed: number; id: string }): number =>
  a.seed - b.seed || a.id.localeCompare(b.id);

function coverageRate(covered: number, total: number): number {
  if (total <= 0) return 1;
  return covered / total;
}

function repetitionScore(metrics: CandidateRank['metrics']): number {
  return metrics.repeatedSentenceRatio + metrics.repeatedClauseRatio + metrics.emptySentenceRatio;
}

function rankReason(rank: Omit<CandidateRank, 'reason'>, provisional: boolean): string {
  const coverage = coverageRate(rank.mandatoryCovered, rank.mandatoryTotal);
  return [
    provisional ? 'provisional_screen' : 'qualified',
    `coverage=${coverage.toFixed(2)}`,
    `repetition=${repetitionScore(rank.metrics).toFixed(2)}`,
    `priorEcho=${rank.metrics.priorEcho.toFixed(2)}`,
  ].join(';');
}

export function selectCandidate(input: {
  candidates: readonly SelectionCandidate[];
  assessments: readonly CandidateAssessment[];
  options?: SelectionOptions;
}): SelectionDecision {
  const options = input.options ?? {};
  const allowProvisional = options.allowProvisional === true;
  const config: Partial<DiversityConfig> = options.diversity ?? {};
  const assessments = new Map(input.assessments.map((entry) => [entry.id, entry]));
  const ordered = [...input.candidates].sort(SEED_ORDER);
  const rejected: SelectionRejection[] = [];
  const ranking: CandidateRank[] = [];

  for (const candidate of ordered) {
    if (candidate.status && candidate.status !== 'ok' && candidate.status !== 'truncated' && candidate.status !== 'empty') {
      rejected.push({ id: candidate.id, reason: 'transport_failed', detail: candidate.status });
      continue;
    }
    if (!candidate.text.trim()) {
      rejected.push({ id: candidate.id, reason: 'empty', detail: 'empty text' });
      continue;
    }
    const assessment = assessments.get(candidate.id);
    if (!assessment) {
      rejected.push({ id: candidate.id, reason: 'unjudged', detail: 'no checker assessment' });
      continue;
    }
    if (assessment.qualified === false) {
      rejected.push({
        id: candidate.id,
        reason: 'not_qualified',
        detail: assessment.hardIssueKinds.join('+') || 'hard issue',
      });
      continue;
    }
    if (assessment.qualified === null && !allowProvisional) {
      rejected.push({ id: candidate.id, reason: 'unjudged', detail: assessment.detail ?? 'checker returned no verdict' });
      continue;
    }
    const metrics = textMetrics(candidate.text, options.priorText ?? null);
    const rank: Omit<CandidateRank, 'reason'> = {
      id: candidate.id,
      eligible: true,
      mandatoryCovered: assessment.mandatoryCovered,
      mandatoryTotal: assessment.mandatoryTotal,
      metrics,
    };
    ranking.push({ ...rank, reason: rankReason(rank, assessment.qualified === null) });
    if (assessment.qualified === null) {
      rejected.push({
        id: candidate.id,
        reason: 'unjudged',
        detail: `provisional only${assessment.detail ? `: ${assessment.detail}` : ''}`,
      });
    }
  }

  ranking.sort((a, b) => {
    const aJudged = assessments.get(a.id)?.qualified === true ? 1 : 0;
    const bJudged = assessments.get(b.id)?.qualified === true ? 1 : 0;
    if (aJudged !== bJudged) return bJudged - aJudged;
    const aCoverage = coverageRate(a.mandatoryCovered, a.mandatoryTotal);
    const bCoverage = coverageRate(b.mandatoryCovered, b.mandatoryTotal);
    if (aCoverage !== bCoverage) return bCoverage - aCoverage;
    const aRepetition = repetitionScore(a.metrics);
    const bRepetition = repetitionScore(b.metrics);
    if (aRepetition !== bRepetition) return aRepetition - bRepetition;
    if (a.metrics.priorEcho !== b.metrics.priorEcho) return a.metrics.priorEcho - b.metrics.priorEcho;
    const aSeed = ordered.find((entry) => entry.id === a.id)?.seed ?? 0;
    const bSeed = ordered.find((entry) => entry.id === b.id)?.seed ?? 0;
    return aSeed - bSeed || a.id.localeCompare(b.id);
  });

  // Homogeneity is reported against the selected text; a later duplicate stays
  // in evidence as a wasted call, never as a second choice.
  const selected = ranking[0] ?? null;
  if (selected) {
    const selectedText = ordered.find((entry) => entry.id === selected.id);
    if (selectedText) {
      const selectedProfile = profileSample({
        id: selected.id,
        seed: selectedText.seed,
        text: selectedText.text,
        licensedEntities: options.licensedEntities,
        config,
      });
      for (const other of ranking.slice(1)) {
        const otherText = ordered.find((entry) => entry.id === other.id);
        if (!otherText) continue;
        const otherProfile = profileSample({
          id: other.id,
          seed: otherText.seed,
          text: otherText.text,
          licensedEntities: options.licensedEntities,
          config,
        });
        const pair = comparePair(selectedProfile, otherProfile, config);
        if (pair.homogeneous) {
          rejected.push({
            id: other.id,
            reason: 'homogeneous_duplicate',
            detail: pair.reasons.join('; '),
          });
        }
      }
    }
  }

  const selectedAssessment = selected ? assessments.get(selected.id) : undefined;
  const verdict: SelectionDecision['verdict'] = selected
    ? selectedAssessment?.qualified === true ? 'adopted' : 'provisional'
    : 'none';
  return {
    selectedId: selected?.id ?? null,
    verdict,
    reason: selected
      ? `${verdict}:${selected.reason}`
      : `no_eligible_candidate:${rejected.map((entry) => entry.reason).join('+') || 'no_candidates'}`,
    ranking,
    rejected,
    considered: ordered.map((entry) => entry.id),
  };
}

/** Samples that never reached a text (transport failure) must never enter a
 * selection ranking. Kept as a helper so evidence paths stay explicit. */
export function transportFailed(sample: Pick<CandidateSample, 'status' | 'text'>): boolean {
  if (sample.status === 'ok' || sample.status === 'truncated') return false;
  if (sample.status === 'empty') return true;
  return sample.text.trim().length === 0;
}
