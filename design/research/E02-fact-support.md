# E02 Fact-support verification: claim vs settled record

**Question.** Can a small head verify whether a settled record supports a
proposed content claim, and what construction of negatives avoids trivial
labels?

**Setup.** `build_fact_support.py` joins the verified dataset with the cached
proposals on (id, promptVersion v2, inputHash). Supported = final status
present (claim as verified); unsupported = final absent while the proposal
asserted present; insufficient/conflict are skipped (they are not negatives).
Facts = settled results texts plus state-diff env keys; no narrative. One
cross-row distractor negative per supported claim (different fact set that does
not contain the claim). 258 pairs: info 57 pos / 95 neg, env 53 pos / 53 neg.
MiniRBT-H256 head (`train_support_head.py`), int8 ONNX 10.55 MB.

**Arms.** Rules baseline: claim substring of the facts (the current program
check). Head: `主张：…\n结算事实：…` → supported / not.

**Results.** Env holdout sm6- 15/16 (8 pos, 7 neg, 1 false positive). Info
holdout sm10- 4/10 (5 negatives false-positive, 1 positive missed). Train loss
info 0.43 (not converged), env 0.05. The "hard" subset (claim not a literal
substring of the facts) has only 6 info rows today, all negatives; the info head
fails them.

**Conditions.** Env claims are mostly tag-grounded (the record contains the
tag), so the env number is operational rather than entailment; the info
negatives are rule-rejected claims (intent echo, structured-not-info) and
cross-row swaps. One world, one labeler model.

**Principle.** Claim verification needs negatives that are hard for the target
relation (wrong attribution, negation, partial support, cross-event evidence),
not merely different fact sets; tag-bearing records let a head learn record
matching instead of entailment, so report the literal-substring-free subset
separately. Env support is usable as a verifier; info support is not.

**Artifacts.** `semantic-support.jsonl`, `train_support_head.py`,
`support-{env,info}-int8.onnx`, D-084.
