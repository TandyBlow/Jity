# E09 Narration representation A/B: prose-facts vs serialized

**Question.** On the same 1.7B narration LoRA, world, seed and output budget,
does the fact representation (`narrationShape=prose-facts` vs `serialized`)
change fact consistency, repetition, or readability?

**Setup.** Pre-registered in D-099. Frozen 8 scenario turns
(`scenarios-independent-turns.json`), micro arm, seed 11, both arms
`narrationCandidate=trained&narrationMode=scene`, temperature 0.45, page
default output budget. One build, same weights, only `narrationShape`
differs. Metrics: model vs program source, length, paragraph count, within-text
and cross-turn bigram repetition, fallback markers, latency, and the scenario
state/task/achievement assertions (`scenario_report.py`).

**Results (8 turns per arm, evidence `evidence-narr-prose-1.json`,
`evidence-narr-serialized-2.json`).**
- Source: 8/8 model in both arms; 0 fallbacks, 0 program text.
- Scenario assertions: both arms 48/48 state, 14/14 task, 3/3 achievement,
  0 false achievements, 0 prose-identity issues.
- Length: prose-facts 149.4 chars mean; serialized 222.8 (+49%).
- Cross-turn bigram repetition: 0.217 vs 0.233 (Δ0.016, within noise at n=8).
- Within-text repetition: 0.664 vs 0.658.
- Latency: mean wait 67.0 s vs 76.6 s (max 93.8 / 97.0).
- Hard alignment (the project's existing dev gate,
  `check-prose-facts.mjs`, run on both evidence files): prose-facts 0 flags in
  8 turns; serialized 3 flags — 2 `unknown_entity_claim` (sc01, sc08) and 1
  `input_echo` (sc02). This gate was missed in the first scoring pass; it is
  the project's own hard-alignment measure, not the review runner.
- Verdict per the pre-registered rule: state assertions did not drop, both
  arms are all-model, and prose-facts has fewer hard-alignment flags
  (0 vs 3) → **positive signal for prose-facts**. Direction only: one seed,
  8 turns, and the gate's flags are heuristic (the sc01 flag quotes a clause
  that also echoes the input; the name-introduction rule can fire on echoed
  address forms).

**Conditions.** One seed, 8 turns, one world, no blind judge; the D1 measure is
the dev gate's heuristic flags, not `narration-quality/review.ts` (still no
evidence-level runner for it). The serialized arm's first attempt crashed the
renderer after two turns (turns 1-2 at 116 s and 217 s); the clean rerun on a
fresh browser ran 57-97 s per turn. Same build, so this is page stability under
a long multi-point session, not an arm property.

**Principle.** The dev fact gate separates the arms (0 vs 3 flags) while
length, repetition and scenario assertions do not; a representation claim needs
a hard-alignment measure, and the project already had one — it just wasn't in
the first scoring pass. The serialized shape buys 49% more text for ~10 s more
wait and more flagged clauses; the review-based metric is still the better D1
and needs an evidence-level runner.

**Artifacts.** D-099/D-102, `scenarios-independent-turns.json`,
`evidence-narr-prose-1.json`, `evidence-narr-serialized-2.json`,
`score_narration_arms.py`, `scenario_report.py`.
