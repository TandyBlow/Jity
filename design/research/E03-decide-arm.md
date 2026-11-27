# E03 Existence-gated decision arm for information reads

**Question.** Can the existence and candidate heads decide an information event
when the program has no topic, without making the program channel worse?

**Setup.** `?semanticDecide=1` (default off) vs `?existenceShadow=1` (scores
only). Pipeline: existence gate (first-person action text, info ≥0.75) →
candidate pointer (top1 ≥0.6, margin ≥0.15) → verbatim support (chosen clause
must be a committed appearance slice). Page arms share kernel, rules, narration
model, seed 11; evidence under `artifacts/goal/micro-workflow/evidence-decide-*`.

**Results.** (a) Before an interrogative guard, the fixed heads decided
`rules:15:45停赛` for a generic "查看规则牌" (existence 0.9486 on the normalized
text) — the exact wrong case predicted by the audit. (b) With the guard
(关于/想知道/有没有/能不能/是否/什么/哪/多少/几), two generic reads produced 0
decisions and 0 `信息=` tags. (c) NPC "查看空床/饮水杯" decided plausible clauses
(制动轮已锁 / 杯沿未破). (d) Shadow vs decide A/B on two open interrogative
reads: both 0 decisions; the existence gate passed (0.8464/0.8209) and the
candidate margin held. (e) Calibration on the real info head, first-person:
positives 0.86–0.94, negatives ≤0.69; normalized inputs shrink the margin
(repeat read 0.8618 vs true read 0.8586), so the gate consumes the action text
as trained.

**Conditions.** Four-turn routes; one world; thresholds fixed before the runs;
no unseen-event positives were produced, so the arm adds no measured recall yet.

**Principle.** A confidence gate must consume the same input distribution it was
trained on, and an open-ended selector needs an explicit interrogative plus
margin-aware abstention; otherwise the model invents a target. Under these
guards the arm is safe but empty — recall is bounded by extraction quality, not
by loosening thresholds.

**Artifacts.** `evidence-decide-1/2/3`, `evidence-ab-{shadow,decide}-1`,
D-084/D-085/D-087.
