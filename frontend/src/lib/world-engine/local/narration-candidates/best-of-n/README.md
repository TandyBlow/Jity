# Best-of-N candidate pool (lane 12)

Selector and diversity measurement for several raw generations of ONE settled
point. It is not a generator, not a fact checker and not a page integration.

## Why

The product writes one scene per turn. A single sample can fail a hard fact,
drop the settled move or repeat the previous turn. Generating several samples
only helps when:

1. at least two samples are fact/perspective-qualified;
2. at least two qualified samples are genuinely different realizations (same
   mandatory facts is not a duplicate; the same rhythm with synonyms is);
3. the extra calls still fit the player-facing 60 s first-readable and 300 s
   full-turn limits, counting every call.

This module makes those three checks computable and keeps every raw candidate
and rejection reason as evidence.

## API

```ts
import {
  runCandidatePool, buildDiversityReport, profileSample, selectCandidate,
} from '@/lib/world-engine/local/narration-candidates/best-of-n';

// 1. N real calls, real budgets, every raw result kept.
const pool = await runCandidatePool(
  { seeds: [17, 29, 43, 61, 79, 97], concurrency: 1, perCallTimeoutMs: 60_000, totalBudgetMs: 120_000 },
  async (seed, signal) => engine.complete(prompt, { seed, maxTokens: 512, signal }),
);

// 2. Qualification comes from the caller's checker; this module never judges.
const assessments = verified.map((entry) => ({
  id: entry.id, qualified: entry.hardIssues.length === 0,
  hardIssueKinds: entry.hardIssues, mandatoryCovered: entry.covered, mandatoryTotal: entry.required,
}));

// 3. Diversity over the texts, not the fact list.
const profiles = pool.samples.map((sample) => profileSample({
  id: sample.id, seed: sample.seed, text: sample.text, licensedEntities,
}));
const diversity = buildDiversityReport({ profiles, qualifiedIds: assessments.filter((a) => a.qualified).map((a) => a.id) });
// diversity.effectiveRepetition = 1 - clusters / samples
// diversity.qualifiedDistinctClusters = clusters computed only over qualified texts

// 4. One candidate, with reasons and rejections.
const decision = selectCandidate({ candidates: pool.samples, assessments, options: { licensedEntities, priorText } });
```

`selectCandidate` order: qualified > coverage > in-text repetition > prior
echo > seed. Character count and a model self-score are not in the comparator.
`qualified: null` is never adopted by default; pass `allowProvisional: true`
only for offline arm comparisons and the decision is labelled `provisional`.

## Module boundaries

- Owned by lane 12 under `narration-candidates/best-of-n/`.
- Does not modify `selection/`, `trained-generation/`, `narration-generation/`,
  the page, the runtime or any existing checker.
- The experiment harness that produced its evidence lives in
  `experiments/narration-best-of-n/`; the preregistration and thresholds are
  frozen there before any generation was run.

## Not a product verdict

Passing unit tests or producing diverse candidates does not make a product
narration pass. 01 owns the shared rubric and independent review; 09 runs the
real browser product; 06 decides integration. Unjudged or provisional text must
stay labelled and must not be submitted as verified narration.
