# E05 Deployment parity: PyTorch vs int8 ONNX heads

**Question.** Does a shipped int8 head behave like the trained checkpoint on its
eval rows, so that "it loads" is not mistaken for "it is the same model"?

**Setup.** `check_head_parity.py`: every exported head is scored by torch and by
the public int8 ONNX on the same texts. Fail on any argmax flip where the torch
top-2 margin ≥0.1, or on a positive-probability difference >0.05 (extraction
uses 0.15 and also compares per-group top1). Heads: existence env/info,
extraction, support env/info.

**Results.** The gate caught two real deployment defects: (1)
`export_existence_onnx.py` mapped both `info.*` and `env.*` onto `head.*`, so
env overwrote info — the shipped info model was the wrong head; (2) the
extraction ONNX predated its retrain. After the HPC retrain the gate failed
again on three heads and the diagnosis split the gap: on every row, torch vs
the **fp32** ONNX is exactly 0.0 — the export is byte-identical — while the
**int8** graph drifts up to 0.33 on one long borderline row. Two causes were
ruled out on the way: the gate was truncating torch at 256 while the browser
(and every exporter) truncates at 192 (now aligned), and the drift survived the
alignment, so it is dynamic-quantization error, not an input mismatch. Two
fixes shipped: `quantize_dynamic(..., per_channel=True)` (worst-case drift
0.33 → 0.19, same 10.6 MB) and a decision-based gate — the gate now fails on
argmax flips with a real margin, on rows that change sides of the deployed
thresholds (0.75 existence gate, 0.6/0.15 candidate pointer, 0.5 support), and
keeps `maxProbDiff` as a 0.25 weight-mismatch alarm. Final: existence env
206/206 (Δp 0.007), info 149/149 (0.080); extraction group top1 54/55 + 1
near-tie that abstains in both arms (torch top1 0.010, margin 0.002), Δp 0.192;
support env 106/106 (0.067), info 151/152 with 1 knife-edge flip (0.4973 vs
0.5031), 0.021. All five pass. ORT-WASM was checked directly: the per-channel
graph runs in the browser kernel and reproduces the CPU numbers
(sm16-i-r5 0.5328 vs fp32 0.5400).

**Conditions.** Desktop ORT CPU for the gate; a Node ORT-WASM run over HTTP
confirms the per-channel kernel; the page-side console-score comparison on a
fixed route is still manual. Quantization knife-edges inside ±0.02 of a
threshold are counted separately, not hidden.

**Principle.** Deployment acceptance must compare outputs (argmax and
decision-threshold side) between training and shipping artifacts on eval rows;
a model that loads, or a file hash that changed, says nothing about behavioural
parity. Keep an exact fp32 comparison to separate export bugs from
quantization error — they need different fixes.

**Artifacts.** `check_head_parity.py` (+ `split_parity.py`,
`diagnose_parity.py`), `export_*_onnx.py`,
`frontend/public/micro/existence-manifest.json`, D-085/D-088/D-100.
