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

**Results (mean ± sd over 5 seeds, HPC job 280875; final).**
- info F1: shared-text 0.780 ± 0.117; shared-embed 0.636 ± 0.168; split 0.889 ± 0.000.
- env F1: shared-text 0.916 ± 0.054; shared-embed 0.769 ± 0.000; split 0.946 ± 0.027.
- The v1 numbers (shared 0.667) were an artifact of the seed and truncation
  defects and are withdrawn. `规则` remains at info 0.889 / env 1.000.
The pre-registered positive bar (split ≥ shared-text + 0.05 AND ≥ shared-embed
+ 0.05, CI lower bound > 0, ≥4/5 seeds same direction) is met on info only:
split − shared-text = +0.109 (info), +0.030 (env); split − shared-embed =
+0.253 (info), +0.177 (env). Because env misses +0.05, the criterion as written
is NOT met; decomposition has positive evidence on the harder field and none on
the near-saturated one. Field embedding is worse than the text prefix on both
fields.

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
