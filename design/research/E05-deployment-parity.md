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
extraction ONNX predated its retrain. After fixes: existence env 206/206
(max Δp 0.0001), info 149/149 (0.0241); extraction 203/203, group top1 55/55
(max Δp 0.099); support env 106/106 (0.0355), info 151/152 with 0 hard flips
(1 near-tie).

**Conditions.** Desktop ORT CPU; the browser uses ORT-WASM with the same int8
graph — the page-side check compares recorded console scores on a fixed route
(still to be automated). Quantization near-ties are tolerated by the margin
rule; the tolerance is documented, not silent.

**Principle.** Deployment acceptance must compare outputs (argmax and
probability) between training and shipping artifacts on eval rows; a model that
loads, or a file hash that changed, says nothing about behavioural parity.

**Artifacts.** `check_head_parity.py`, `export_*_onnx.py`,
`frontend/public/micro/existence-manifest.json`, D-085/D-088.
