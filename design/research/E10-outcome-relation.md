# E10 Outcome relation: model head vs rule on narration text

**Question.** Action outcomes are a relation family beyond info/env: after a
fact is settled, is its outcome (achieved / partial / not achieved / blocked /
no change) recoverable from the narration sentence alone, better than a
negation-word rule?

**Setup.** `build_relation_probes.py` freezes 275 rows from verified facts,
one per unique results fact, with the kernel outcome marker and structured
tags stripped from the input; gold is the marker itself (program-record
ceiling, not independent semantics). Split by route: 231 train / 44 test
(`sm6-`, `sm10-`, `sm14-`, `sm18-`, `sm22-` routes and `sc` rows test). Arms,
same encoder/rows/epochs/seed: majority class, negation-word rule
(`没有/未能/被阻止/…` → not achieved; `部分/一半` → partial; else achieved),
MiniRBT-H256 5-class head. Training on HPC job 280969 (RTX 4090 D, torch
2.5.1+cu124), 30 epochs.

**Results (44 test rows).**
- majority: accuracy 0.636, macro-F1 0.156.
- negation rule: accuracy 0.636, macro-F1 0.156 (no test row matched its
  negation pattern; the rule collapses to majority here).
- head: accuracy 0.886, macro-F1 0.488. Confusion: achieved 26/30, partial
  11/13, not_achieved 2/5; errors are partial→achieved (2), achieved→partial
  (1), achieved→not_achieved (1), not_achieved→partial (1). `blocked` and
  `no_change` have no test rows (4 train rows each), so those classes are not
  evaluated.

**Conditions.** One world; 44 test rows with heavy imbalance; gold is the
kernel marker, so the head is measured against the same rule-based labels the
product uses, not against human annotation. The rule baseline is weak on this
text (it keys on wording the narration rarely uses), so the +0.25 accuracy is
model-vs-rule in this world, not proof of general outcome understanding.

**Principle.** Outcome is learnable from the narration sentence with a small
encoder well above the lexical rule, and the remaining errors concentrate on
the achieved/partial boundary — the boundary the product's settlement already
treats as the risky one. The next relation families (task condition, causality,
cross-turn evidence) need authored minimal pairs; this file only covers the
families derivable from verified facts.

**Artifacts.** `build_relation_probes.py`, `train_relation_outcome.py`,
`relation-probes/outcome.jsonl` (+ `manifest.json`), `_hpc_relation_submit.py`,
`.local/hpc-micro/relation-outcome-head.pt`, D-101.
