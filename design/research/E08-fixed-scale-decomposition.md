# E08 Fixed-scale ablation: one shared head vs task-specific heads

**Question.** At the same encoder, training rows, epochs, seed and optimizer,
does splitting a semantic task into task-specific heads beat one model that
receives the field name and answers with a single head — and where do both
stand against the program rule?

**Setup.** `train_joint_existence.py` on `semantic-existence.jsonl` (env 53/153,
info 57/92). Arm S: one MiniRBT encoder + one 2-logit head, input
`字段：<field>\n<text>`. Arm D: the same encoder + per-field heads (the shipped
existence heads). Both trained 30 epochs, lr 2e-5, seed 20261127, identical row
order. Holdouts: env `sm6-` (9 rows), info `sm10-` (10 rows). Rules arm = the
`环境=`/`信息=` tag; hybrid = rules when a tag exists, else the head.
`eval_joint_ablation.py` recomputes from the saved models.

**Results.** Heads (F1 / P / R):
- info: shared 0.667 / 0.60 / 0.75; split 0.889 / 0.80 / 1.00; rules 0.889.
- env: shared 0.933 / 1.00 / 0.875; split 0.933 / 1.00 / 0.875; rules 1.000.
- hybrid: shared info 0.800, env 1.000; split info 0.889, env 1.000.
Splitting the heads recovers 0.22 F1 on the harder field and ties on env, at
identical parameters (one 2-logit head vs two) and identical training cost. No
head arm beats the rule on these holdouts.

**Conditions.** Nine and ten holdout rows; labels are rule-derived, so the rule
is the ceiling by construction; the "single model" here is a shared-head variant
of the same encoder, not a 0.6B LLM. The field name costs a few prompt tokens
and is part of the shared arm's budget.

**Principle.** Task-specific heads can beat a single shared head at equal scale
and budget when the tasks pull the representation in different directions, but
decomposition alone does not exceed a strong deterministic rule on
rule-grounded data. Positive evidence for the architecture requires the
decomposition to beat a *comparable single model* on tasks the rule cannot do
(open-ended relations), not to reproduce the rule.

**Artifacts.** `train_joint_existence.py`, `eval_joint_ablation.py`,
`ablation-report.json`, models `joint-ablation-{shared,split}.pt`, D-092.
