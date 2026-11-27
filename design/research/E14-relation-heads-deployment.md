# E14 Relation heads: int8 export and decision parity

**Question.** Do the three relation heads (E10 outcome, E11 condition, E13
cross-turn) survive the same deployment path as the existence/extraction
heads — ONNX int8, per-channel quantization, decision parity on the frozen
rows?

**Setup.** `export_relation_onnx.py` builds a fresh `Head` from the
MiniRBT snapshot, copies the HPC state dict, exports dynamic-length ONNX at
opset 17, quantizes weights per-channel int8, and compares torch vs ONNX on
every frozen row of the family. Rule: same argmax; no row crossing the 0.5
decision threshold outside a ±0.02 knife-edge band; `maxProbDiff` ≤ 0.25 as a
weight-mismatch alarm.

**Results.**
- `relation-condition-int8.onnx`: 131/131 agree, 0 hard flips, 0 threshold
  straddles, max Δp 0.008, 10.62 MB.
- `relation-cross-turn-int8.onnx`: 126/126 agree, 0 hard flips, 0 straddles,
  max Δp 0.062, 10.62 MB.
- `relation-outcome-int8.onnx`: 275/275 agree, 0 hard flips, max Δp 0.054,
  10.62 MB. The 0.5 straddle rule is not meaningful for a 5-class softmax; the
  argmax agreement is the operative check for this head.

**Conditions.** Desktop ORT CPU for the comparison; the per-channel int8
kernel was verified in ORT-WASM for the existence heads (E05) and is the same
graph structure here. Not yet wired into the page: no product decision uses
these heads, so this is deployment readiness, not integration.

**Principle.** The relation heads are exportable and numerically stable under
the project's quantization pipeline; adding a fourth, fifth or sixth head does
not change the deployment gate. Integration (a task proposer over the condition
head, a cross-turn evidence line in the tasks prompt) is a product decision
that still needs page evidence.

**Artifacts.** `export_relation_onnx.py`,
`.local/micro-heads/relation-{condition,cross-turn,outcome}[-int8].onnx`,
D-107.
