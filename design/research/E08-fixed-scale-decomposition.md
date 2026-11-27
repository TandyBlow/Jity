# E08 Fixed-scale ablation: one shared head vs task-specific heads (corrected)

**Question.** At the same encoder, training rows, epochs, seed and optimizer,
does decomposing the semantic task into task-specific heads beat a single model
that handles both fields — and does it beat a single model conditioned on a
learned field embedding?

**Setup.** `train_joint_existence.py` v2 on `semantic-existence.jsonl`. The v1
protocol had three defects (seed set after construction, bodies not truncated
before the text prefix, no field-embedding control); v2 fixes them: bodies
truncate to 240 tokens before any prefix, each arm starts from the same seeded
initialization, 5 seeds (`20261127..31`), AdamW 2e-5, 30 epochs, batch 1.
Arms: `shared-text` (one encoder + one head, `字段：<field>\n` prefix),
`shared-embed` (one encoder + one head, CLS + learned 2-dim field embedding),
`split` (one encoder + per-field heads). Holdouts: env `sm6-` (9 rows), info
`sm10-` (10 rows). Params: shared-text 15,797,778; split 15,798,292; the
difference is 514 weights (0.0033%).

**Results (mean ± sd over 5 seeds; split still running at 2 seeds).**
- info F1: shared-text 0.855 ± 0.054; shared-embed 0.678 ± 0.088; split 0.889 ± 0.0 (n=2).
- env F1: shared-text 0.918 ± 0.030; shared-embed 0.769 ± 0.000; split 0.933 ± 0.0 (n=2).
- The v1 numbers (shared 0.667) were an artifact of the seed and truncation
  defects and are withdrawn. `规则` remains at info 0.889 / env 1.000.
The pre-registered positive bar (split ≥ shared-text + 0.05 AND ≥ shared-embed
+ 0.05, CI lower bound > 0, ≥4/5 seeds same direction) is likely NOT met for
shared-text: the observed gap is ~0.03 on info and ~0.015 on env with n=2.
Field embedding actively hurts (−0.18 info, −0.15 env).

**Conditions.** Nine and ten holdout rows; rule-derived labels; one world;
5 seeds but only 2 for split so far; no route-level 5-fold CV yet. `shared-text`
encodes twice per turn (one call per field), while `split` encodes once and runs
two heads — an inference-cost difference in split's favour that does not affect
this training comparison.

**Principle.** At equal scale and budget, simply conditioning a single model on
the field name recovers almost all of the benefit of task-specific heads; a
learned field embedding is worse than the text prefix. Decomposition is not
automatically better — on rule-grounded tasks the rule still wins, and positive
architecture evidence must come from open relations, not from head splitting.

**Artifacts.** `train_joint_existence.py`, `ablation-report-v2.json` (written at
the end of the run), D-092 (superseded numbers), D-096.
