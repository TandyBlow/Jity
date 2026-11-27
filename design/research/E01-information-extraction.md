# E01 Information extraction: rule distillation vs appearance-level holdout

**Question.** Can a small BERT candidate-pointer head extract the content a read
action asks for, beyond what the program's topic-match rule already does?

**Setup.** `semantic-extraction.jsonl` (55 action/appearance/clause pairs from
real `/world-local` turns). MiniRBT-H256 + linear head, int8 ONNX 10.55 MB,
CPU p50 1.3 ms. Trainer `train_extraction_head.py`; data
`build_extraction_data.py`; parity `check_head_parity.py`.

**Data.** Labels come from the program's `信息=` markers (`fact-informations.ts`),
so the dataset measures agreement with the rule, not semantic ground truth.
Split: appearance-level holdout (sha1-sorted appearances, every 5th) → 14 groups;
the earlier id-level split leaked 3 appearances and one copy hit.

**Arms.** Head (top1 candidate), first clause, longest clause, action-bigram
overlap (max shared character bigrams with the action). Program rule = label
source (100% by construction).

**Results.** Appearance-level holdout top1: head 9/14, first 5/14, longest 5/14,
bigram 12/14. The head is below a purely lexical baseline. Failure modes:
same-appearance cross-action interference (sm10 rule sign: chose 15:45停赛 for a
different question), name-adjacent locative clause, and a pronoun-fragment
target ("和她…登记相符"). Coverage: 42 entities read (< half the items+people),
1/14 characters, 0/26 locations.

**Conditions.** 14 holdout groups; labels rule-derived; single world. No claim
about unseen worlds or open-ended reads.

**Principle.** When training labels are produced by a deterministic rule, a
model trained on them can at best imitate the rule; measure against lexical
baselines and hold out by entity/appearance family before attributing semantic
extraction ability. Open-ended information needs a different task decomposition
(0..N items, sources beyond item appearance), not a better top1 selector.

**Artifacts.** `semantic-extraction.jsonl`, `train_extraction_head.py`,
`frontend/public/micro/extraction-head-int8.onnx` (sha256 7444…), D-084/D-086.
