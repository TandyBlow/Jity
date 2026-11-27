# E13 Cross-turn relation: a prior point's facts in the goal decision

**Question.** Task conditions can depend on what happened in an earlier point
(a promise, a decision, an environment change). Does adding the previous
point's facts to the input change the condition decision, and can it be decided
better than the wording rule?

**Setup.** `build_relation_probes.py` freezes `relation-probes/cross_turn.jsonl`
from consecutive points of the same session (`evidenceFile`, ordered by the
before-snapshot history count): 126 rows (107 train / 19 test), gold is the
kernel task flip pending → achieved in the later point, negatives are the same
owner's closest-wording pending task. Input:
`任务：<goal>\n上一回合：<prior point's facts>\n本回合：<this point's facts>`.
Arms, same encoder/rows/epochs/seed: majority, wording rule (goal/fact bigram
overlap ≥0.2), MiniRBT-H256 binary head. HPC job 281136.

**Results (19 test rows; 5 positives).**
- majority: accuracy 0.737, macro-F1 0.424.
- wording rule: accuracy 0.684, macro-F1 0.406 — 0/5 positives; the held-out
  positive cases all fall below the wording threshold.
- head: accuracy 0.895, macro-F1 0.864 — 4/5 positives, 13/14 negatives, 1
  false positive. The one miss is a positive.

**Conditions.** Five test positives — directional only. Same kernel-ledger
provenance as E11; the "previous point" is the immediately preceding point of
the same session, not the accumulated history. No comparison arm without the
prior line was run, so the head's gain cannot yet be attributed to the prior
context versus the encoder itself.

**Principle.** Cross-turn context is present in the data and a small encoder
recovers most held-out positives that the wording rule misses, without
collapsing negatives. Whether the prior line is what carries the decision needs
the no-prior ablation; until then this is a family with positive signal, not a
cross-turn result.

**Artifacts.** `build_relation_probes.py`, `train_relation_condition.py
--family cross_turn`, `relation-probes/cross_turn.jsonl` (+ manifest),
`.local/hpc-micro/relation-cross_turn-head.pt`, D-106.
