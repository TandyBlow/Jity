# Micro generative v2/v3 — 2026-11-26

Status: component pilot. Not integrated into `/world-local`.

## What changed

- Training rows are the deduplicated pilot rows: 73 conditions and 22 events
  (one surface form per task/event, negatives kept), not 380 prefix variants.
- Test rows are hand-authored in `hand_test.py`: 24 rows, never used for
  training. 12 conditions / 12 events; 20 in the original world and 4 in a
  second world (`mistport`) whose entity IDs never appear in training.
- Two output schemes: free IDs in the sequence, or a pointer to a candidate.
  Two pointer implementations:
  - v2 `<pN>` index token (the model emits an index from the candidate list).
  - v3 candidate-scoring head: the decoder emits `<e>` at an entity field and a
    dot-product head selects among the row candidates from the decoder state.
- Two encoders: from-scratch Transformer and frozen MiniRBT-H256 (BERT).
- A BERT + linear result classifier is compared with the generative `result`.

## v2: free ID vs `<pN>`, scratch vs BERT

| arm | field R | entity R | dragon entity | mistport entity | exact |
|---|---:|---:|---:|---:|---:|
| scratch free | 0.064 | 0.037 | 0.045 | 0.000 | 0.000 |
| scratch `<pN>` | 0.179 | 0.111 | 0.136 | 0.000 | 0.000 |
| BERT free | 0.231 | 0.259 | 0.318 | 0.000 | 0.042 |
| BERT `<pN>` | 0.179 | 0.111 | 0.136 | 0.000 | 0.000 |

Params 7.8M (scratch) / 14.8M (BERT); GPU p50 39.5–57.8 ms. The `<pN>` index
token did not beat free IDs. All arms score 0 on mistport entity fields; the
free-ID model cannot emit unseen IDs, and the index-token model did not learn
to select unseen candidates.

## v3: candidate-scoring pointer

Without hand-authored training rows (95 rule rows), then with 28 hand-authored
training rows added (123 train; the 24-row hand test is unchanged):

| train | arm | field R | entity R | open R | dragon entity | mistport entity | result | params | p50 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 95 rule | BERT candidate | 0.244 | 0.333 | 0.196 | 0.364 | 0.200 | 0.583 | 14.80M | 47.1 ms |
| 95 rule | scratch candidate | 0.205 | 0.296 | 0.157 | 0.364 | 0.000 | 0.500 | 7.82M | 41.8 ms |
| +28 hand | BERT candidate | 0.346 | 0.481 | 0.275 | 0.500 | 0.400 | 0.500 | 14.83M | 93.7 ms |
| +28 hand | scratch candidate | 0.295 | 0.333 | 0.275 | 0.364 | 0.200 | 0.750 | 7.86M | 85.7 ms |

The candidate head is the first arm to beat free IDs overall (0.244 vs 0.231)
and the only arm to select unseen-world entities (mistport 0.200 vs 0). The
28 hand rows raise the BERT candidate field recall 0.244→0.346, entity
0.333→0.481 and mistport entity 0.200→0.400; the scratch arm also gains
(0.205→0.295, mistport 0→0.2). The mistport subset is four rows; this is a
data-scaling signal, not a final number.

The `open R` is still `result`/`conf`/`act`/`decision`/`time`; `info`, `env`,
`promise`, `cause` and `neg` remain 0 even after the hand rows that contain
them. The open-text generation needs much more data and a different decoding
target, not only more pointer rows.

The p50 rose from ~47 to ~94 ms because the hand-trained model emits longer
outputs (more fields); this is generation length, not a larger model.

## Result classifier vs generative result

The BERT + linear classifier scores 0.583 on 12 hand events; it predicts
`completed` for every row. With 95 rule rows, the BERT candidate generated
`result` was also 0.583 and scratch 0.500. With the 28 hand rows, BERT drops to
0.500 and scratch rises to 0.750. The classifier is a proxy, not the product
results head, and the test has 7/12 `completed`. Across the two runs there is no
stable generation advantage; a class-weighted classifier is the safer baseline
and must be compared on a larger balanced set.

## Findings

1. The output representation matters, but the implementation matters more.
   Emitting an index token is not a pointer: it did not beat free IDs. Scoring
   candidate states from the decoder is the first representation that selects
   unseen entities.
2. The pretrained encoder is necessary for unseen entities. With hand train,
   BERT candidate mistport entity 0.400 vs scratch 0.200; BERT free overall
   0.231 vs scratch 0.064 without hand train. The cost is 14.8M params and
   ~47–94 ms p50 GPU depending on output length.
3. Data remains the bottleneck, but it responds. 28 hand rows raised the BERT
   candidate field recall 0.244→0.346 and entity 0.333→0.481. The open fields
   (`info/env/promise/cause/neg`) still score 0 even when the hand rows contain
   them; the decoder needs many more open-field examples and a different target.
4. Finite categories should stay classifiers. The result classifier (0.583)
   beats BERT generation (0.500) and loses to scratch generation (0.750) on 12
   rows; no stable generation advantage. Use a class-weighted classifier
   baseline, not generation, for `result`.
5. Browser cost is not measured. The v2/v3 numbers are PyTorch GPU; the v1
   ONNX graphs are fixed-shape at their traced lengths, so they cannot be used
   as dynamic browser models. See the v1 shape caveat.

## Decision

- Use the candidate-scoring pointer + frozen MiniRBT encoder for entity fields
  in the next hybrid prototype; keep the entity linker/candidate generator
  outside the model.
- Keep `result` as a classifier. Do not use generation for finite labels.
- Use generation only for open fields after hand-authored training data covers
  `info/env/promise/decision/cause`, and for composite task conditions. The
  28-row hand train seed did not move those fields off 0; the next batch must be
  several hundred rows with balanced open-field targets, not more prefixes.
- Continue hand-authored training data (the 28 rows are an agent-authored seed,
  not user-verified), with separate test sets by world, task type and event
  type. The current 24-row test cannot support a five-arm claim.
- Then wire the hybrid into `/world-local`, run the frozen
  `scenarios-independent.json` five-arm comparison, and measure
  `onnxruntime-web` latency and product benefit. Re-export with fixed padding
  and separate encoder/decoder-step graphs (or dynamo) before claiming browser
  numbers; the current ONNX graphs are fixed at their traced lengths.

## Reproduce

```bash
cd /d/others/Jity
PYTHONUTF8=1 python -X utf8 artifacts/goal/micro-workflow/micro_generative_v2.py
PYTHONUTF8=1 python -X utf8 artifacts/goal/micro-workflow/summarize_v2.py
PYTHONUTF8=1 python -X utf8 artifacts/goal/micro-workflow/micro_generative_v3.py
```

Reports: `artifacts/goal/micro-workflow/micro-generative/v2-report.json`,
`v3-report.json`. `hand_test.py` is the hand-authored test source.
