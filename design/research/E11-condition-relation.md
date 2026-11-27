# E11 Condition relation: does a fact satisfy a task goal?

**Question.** Task condition is a relation family beyond info/env: given a
pending task goal and this point's settled facts, does the fact satisfy the
goal? The product currently decides this with an LLM stage whose prompt is
short-listed by goal/fact wording overlap (≥0.2 bigram share); is that wording
rule all there is, or can a small encoder decide better?

**Setup.** `build_relation_probes.py` freezes `relation-probes/condition.jsonl`
from the verified semantic export: 131 rows (108 train / 23 test, split by route
holdout `sm6- sm10- sm14- sm18- sm22-` and `sc` rows). Gold is the kernel task
status flip pending → achieved in the stateDiff ledger; negatives are the same
owner's pending task whose goal wording overlaps the fact most (hard negatives).
Input is `任务：<goal>\n事实：<facts, structured tags stripped>`. Arms, same
encoder/rows/epochs/seed: majority class, wording rule (overlap ≥0.2 — the
product's shortlist rule), MiniRBT-H256 binary head. HPC job 281000.

**Results (23 test rows; 5 positives).**
- majority: accuracy 0.783, macro-F1 0.439.
- wording rule: accuracy 0.783, macro-F1 0.439 — predicts "not satisfied" for
  every test row; the held-out positives all share <20% of the goal's bigrams,
  i.e. they are exactly the cases the shortlist would drop.
- head: accuracy 0.826, macro-F1 0.697. Finds 2/5 positives, misses 3, adds 1
  false positive (0→1); keeps 17/18 negatives.

**Conditions.** Five test positives — directional only. Gold is the kernel
ledger, so the head is measured against the same rule-based decisions the
product makes. The condition family uses the product's own task text and facts,
one world. `blocked`/`no_change`-like edge cases in task status are not in this
family.

**Principle.** The wording shortlist is a strict necessary condition on this
data: every test positive fell below it, and the encoder recovers part of that
gap (macro-F1 +0.26) without collapsing negatives. That is the first evidence
that a learned relation can extend the program rule rather than imitate it —
but with five positives it is a direction to scale, not a result.

**Artifacts.** `build_relation_probes.py`, `train_relation_condition.py`,
`relation-probes/condition.jsonl` (+ manifest), `_hpc_relation_submit.py`
(local), `.local/hpc-micro/relation-condition-head.pt`, D-104.
