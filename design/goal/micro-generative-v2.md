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

| arm | field R | entity R | open R | dragon entity | mistport entity | result | params | p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BERT candidate | 0.244 | 0.333 | 0.196 | 0.364 | 0.200 | 0.583 | 14.80M | 47.1 ms |
| scratch candidate | 0.205 | 0.296 | 0.157 | 0.364 | 0.000 | 0.500 | 7.82M | 41.8 ms |

The candidate head is the first arm to beat free IDs overall (0.244 vs 0.231)
and the only arm to select unseen-world entities (mistport 0.200 vs 0). The
gain is small and the mistport subset is four rows. The frozen BERT encoder is
required: the scratch candidate head gets seen-world entities but 0 on
mistport.

The open-field recall (0.196) is still mostly `result`/`conf`; `info`, `env`,
`promise`, `decision`, `cause` and `time` remain 0.

## Result classifier vs generative result

The BERT + linear classifier scores 0.583 on 12 hand events; it predicts
`completed` for every row. The BERT candidate model's generated `result` is also
0.583; the scratch candidate is 0.500. The classifier is a proxy, not the
product results head, and the classes are imbalanced (7/12 `completed`). The
data does not show a generation advantage for this finite field; keep it as a
classifier until a larger balanced set says otherwise.

## Findings

1. The output representation matters, but the implementation matters more.
   Emitting an index token is not a pointer: it did not beat free IDs. Scoring
   candidate states from the decoder is the first representation that selects
   unseen entities.
2. The pretrained encoder is necessary for unseen entities. BERT candidate
   mistport entity 0.200 vs scratch 0.000; BERT free overall 0.231 vs scratch
   0.064. The cost is 14.8M params and ~47 ms p50 GPU.
3. Data remains the bottleneck. 95 training rows, 24 hand test rows; the open
   fields have too few examples and score 0. The result class is balanced poorly.
   This is a seed, not a scale comparison.
4. Finite categories should stay classifiers. The result classifier ties the
   generative result; the classifier is cheaper and easier to calibrate.
5. Browser cost is not measured. The v2/v3 numbers are PyTorch GPU; the pilot's
   independent ONNX/CPU measurements cover the v1 models only.

## Decision

- Use the candidate-scoring pointer + frozen MiniRBT encoder for entity fields
  in the next hybrid prototype; keep the entity linker/candidate generator
  outside the model.
- Keep `result` as a classifier. Do not use generation for finite labels.
- Use generation only for open fields after hand-authored training data covers
  `info/env/promise/decision/cause`, and for composite task conditions.
- Expand hand-authored training data next (not only the test set), with
  separate test sets by world, task type and event type. The current test set
  is 24 rows and cannot support a five-arm claim.
- Then wire the hybrid into `/world-local`, run the frozen
  `scenarios-independent.json` five-arm comparison, and measure
  `onnxruntime-web` latency and product benefit.

## Reproduce

```bash
cd /d/others/Jity
PYTHONUTF8=1 python -X utf8 artifacts/goal/micro-workflow/micro_generative_v2.py
PYTHONUTF8=1 python -X utf8 artifacts/goal/micro-workflow/summarize_v2.py
PYTHONUTF8=1 python -X utf8 artifacts/goal/micro-workflow/micro_generative_v3.py
```

Reports: `artifacts/goal/micro-workflow/micro-generative/v2-report.json`,
`v3-report.json`. `hand_test.py` is the hand-authored test source.
