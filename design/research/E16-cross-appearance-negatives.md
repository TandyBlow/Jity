# E16 Cross-appearance negatives fix the extraction pointer

**Question.** E15/D-109 showed the candidate pointer at chance on unseen
appearances while being confidently wrong (D-110) and not merely repeating
actions (D-111), even though the action names the target's topic (D-112). The
diagnosis: within-appearance negatives teach position/format cues. Does adding
negatives from *other* appearances fix it?

**Setup.** `train_extraction_head.py` now adds, for every training pair, two
negatives built from another *training* appearance's clause (seeded shuffle,
two per pair; holdout appearances are never negative sources). Training rows
152 → 234; holdout unchanged at 51 rows / 14 appearance groups. HPC job 281251,
same encoder/epochs/seed/optimizer.

**Results.**
- Head top1 on the appearance holdout: 7/14 → **9/14** (bigram baseline 12/14,
  first/longest 5/14).
- With the deployed 0.6/0.15 abstention, torch: all pairs 49 decide / 48
  correct; holdout **9 decide / 8 correct / 1 wrong (88.9%)** — was 8 decide /
  4 correct (50%). Shipped int8: all 50/48; holdout 10 decide / 8 correct / 2
  wrong (80%) — was 5/9.
- Torch-vs-ONNX gate with the retrained head: 202/203 argmax, group top1 55/55,
  every head passes; manifest hash/bytes updated (`d670a27f…`).

**Conditions.** Fourteen holdout groups; the improvement is two decisions on a
small set. Every training and holdout pair comes from a settled `信息=` tag,
i.e. a read the program already resolved (D-114), so these numbers measure
distillation and cross-appearance generalisation — not added value over the
rule. That needs a separately frozen set of program-missed reads. The head still trails the bigram rule on raw top1, so the rule stays
the floor and the model arm the experimental one. The page was not re-run after
the swap (acceptance lane paused); loading in ORT-WASM is covered by the same
per-channel graph verified in E05, but a page smoke is still owed.

**Principle.** The pointer's failure was a data-distribution failure: negatives
from the same appearance taught surface cues that did not transfer. Two
cross-appearance negatives per pair moved the *deployed* behaviour on unseen
appearances from coin-flip to 8/9 correct. The next lever is more
appearance-level data, not thresholds (D-110).

**Artifacts.** `train_extraction_head.py`, `semantic-extraction.jsonl`,
`.local/hpc-micro/extraction-head-xneg.pt` (shipped copy in
`.local/micro-semantic/`), `frontend/public/micro/extraction-head-int8.onnx`,
manifest, `score_pointer_abstain.py`, `calib-report-xneg.json`, D-113.
