# E15 Five-arm scoreboard: what is measured, what is not

**Question.** The goal requires a five-arm comparison (rules, classifier,
micro-generative, hybrid micro workflow, existing LLM) on both fixed events and
real page rounds. Which cells can be filled from frozen evidence today, and
which need runs?

**Setup.** All cells are read from frozen artifacts only; no arm was re-run for
this record except the offline fixed-event scoring. Fixed events:
`semantic-existence.jsonl` holdouts (env `sm6-` 9 rows, info `sm10-` 10 rows).
End to end: the 8 frozen scenarios with the hybrid micro arm on the current
build (`evidence-perf-taskskip-8.json`). The machine-readable scoreboard is
`artifacts/goal/micro-workflow/five-arm-scoreboard.json`.

**Results (measured cells).**
- Rules, fixed events: env 9/9 (P/R/F1 1/1/1); info 9/10 (0.8/1/0.889, one
  false positive).
- Classifier (existence heads, HPC checkpoints, per-channel int8), fixed
  events: env 8/9 (1/0.875/0.933); info 9/10 (0.8/1/0.889); ONNX parity 9/9
  and 10/10.
- Hybrid micro workflow, end to end: 8/8 turns, 48/48 state, 14/14 task, 3/3
  achievement assertions, 0 prose-identity issues, mean turn 61.9 s (max
  85.1 s), narration accepted from the model on 8/8 turns (mean 12.5 s).
- Hybrid micro workflow, candidate pointer at fixed events (deployed 0.6/0.15
  thresholds, `score_pointer_abstain.py`, torch and shipped int8): torch 48/55
  decide, 43 correct (89.6%); int8 49/55 decide, 44 correct (89.8%). On the
  appearance-level holdout (14 pairs) torch decides 8 and is right 4, int8
  decides 9 and is right 5 — **at chance when it decides** in both graphs; the
  confidence rule does not protect unseen appearances. A threshold sweep
  (`score_pointer_calibration.py`) shows why: the four wrong holdout decisions
  score 0.865-0.995 with margins 0.359-0.975, while train precision stays 0.975
  at every reasonable threshold — they are confidently wrong, so no
  train-chosen threshold removes them.
- Micro-generative: no fixed-event or end-to-end number — the v3 models are a
  runtime probe, not wired into the page.
- Existing LLM: historical CAMP/DeepSeek stack, different schema/world — not
  measurable in the current kernel.

**Conditions.** Fixed-event rows are route holdouts with rule-derived labels
(D-085); the end-to-end arm uses one world, one seed and the evaluation query
string recorded in the scoreboard. `meanTurnS` is submit-to-handback, not
first-readable; first-readable was 7.3-20.7 s accepted narration per turn in
the same evidence.

**Principle.** Two of five arms have fixed-event numbers, the hybrid arm has
both an end-to-end number and a pointer cell, and two arms remain blank. The
pointer cell changes the risk picture: its confidence rule abstains on half of
the unseen appearances but is at chance on the ones it accepts, so the decide
arm must stay experimental and the program channel stays the default until the
pointer is calibrated on held-out appearances. Next: hybrid existence-gate
cell, micro-generative wiring, LLM arm.

**Artifacts.** `five-arm-scoreboard.json`, `score_fixed_arms.py`,
`evidence-perf-taskskip-8.json`, D-108.
