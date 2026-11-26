# Micro generative scale and open fields — 2026-11-26

Status: fixed-architecture component experiment; not integrated.

## Setup

- Architecture fixed: frozen MiniRBT encoder + decoder + candidate-scoring
  pointer (v3). No architecture change in this round.
- Training: 123 hand/rule rows + 877 template-gold generated rows = 1000.
  The generated rows are compositional templates over the world entities, not
  hand labels. The 24-row hand test is frozen and never used for training.
- Stages: warm-start the same model at 250 rows, then 500, then 1000.
- Test: 20 original-world rows + 4 unseen-world (`mistport`) rows; 12
  conditions / 12 events.

## Learning curve

| train rows | field R | entity R | open R | exact | dragon entity | mistport entity | p50 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 250 | 0.333 | 0.370 | 0.314 | 0.083 | 0.455 | 0.000 | 78.8 ms |
| 500 | 0.333 | 0.333 | 0.333 | 0.042 | 0.409 | 0.000 | 86.3 ms |
| 1000 | 0.359 | 0.481 | 0.294 | 0.042 | 0.591 | 0.000 | 86.7 ms |

The 24-row test is noisy, but there is no clean monotonic curve. More
importantly, the 28-row hand seed from D-048 reached 0.346 field / 0.481 entity
/ mistport 0.400; the 1000-row template set reaches 0.359 / 0.481 / 0.000. The
template-generated rows do not transfer to the hand test's unseen world; the
data source, not just count, is the bottleneck.

## Open-field diagnostics

Open-field counts in the 1000 train rows: info 223, cause 162, promise 146,
decision 104, env 92, neg 48. Test positives: info 6, decision 7, env 4,
promise 4, cause 4, neg 1.

Generation (v3, 1000): `info`, `env`, `promise`, `cause` precision/recall 0 at
all scales; `decision` P 0.2 / R 0.33; `neg` 0. Entity fields are over-emitted:
`item` R 1.0 at P 0.36, `target` R 0.75 at P 0.67.

Existence classifier (same 1000 rows, frozen BERT + 6-way multi-label head):
info F1 0.31, env 0.73, promise 0.67, decision 0.67, cause 0.40, neg 0.50.
Presence is learnable from the same data that the generator cannot emit.

Span coverage of the hand open fields: env 0.0, cause 0.0, info 0.17, promise
0.25, decision 0.43, neg 1.0. The hand gold values are often summaries, not
substrings of the input. Text-span extraction cannot produce them; short-seq
generation is the right extractor, but it must be a specialized model after an
existence decision.

The sequence loss / format is the likely blocker, not only data volume: the
existence head sees the same rows and reaches F1 0.3–0.7, while the shared
decoder omits the field text. Field-level loss and train-fit were not
instrumented; that is the next diagnostic, not a claim.

## Result classifier

Unweighted vs class-weighted BERT + linear on the 12 hand events:

| arm | accuracy | confusion |
|---|---:|---|
| unweighted | 0.667 | completed 6/7, failed 1/1, blocked 1/1, partial 0/3 |
| weighted | 0.333 | completed 2/7, failed 1/1, blocked 1/1, partial 0/3 (5 completed + 1 partial predicted failed) |

Class weights over-correct on 12 rows and reduce accuracy. Keep the unweighted
classifier until a larger balanced set; the weighted model is not adopted.

## Browser token loop

A real encoder + decoder-step ONNX export (fixed 96/64, int8, ORT-WASM) runs a
greedy loop in Edge. 5M pilot: load 939 ms, encode 33.8 ms, 9.61 ms/token,
12 tokens, full 118.1 ms p50 / 150.2 ms p95. This proves the browser loop and
the fixed-shape workaround. It is the 5M pilot model, not the v3 candidate
pointer; the v3 export and browser cost are still pending.

## Findings

1. The hand seed still beats template scale on the unseen world (0.400 vs
   0.000 mistport entity). Do not report a data-scale curve as generalization
   when the added rows are templates.
2. Presence and content are different problems. The existence classifier
   learns 0.31–0.73 F1; the shared generator emits none of the open content.
   Split the next design: existence classifier -> specialized extractor.
3. Span extraction is not sufficient: the open gold values are mostly not
   substrings (env/cause 0%, info 17%). Use short-seq generation for content
   after existence is decided.
4. Class weighting hurts on the 12-row result test; keep the unweighted
   classifier and instrument per-class metrics on a larger set.
5. The browser token loop is proven on the 5M pilot; the v3 candidate-pointer
   export is the next engineering task.

## Next

- Stop adding architecture. Keep BERT candidate pointer for entity fields.
- Replace template-generated volume with hand/verified semantic rows; measure
  the 250/500/1000 curve on those, not on templates.
- Implement existence -> specialized open-field extractor; compare with the
  shared generator on the frozen hand test; instrument field-level loss and
  train fit.
- Keep the unweighted result classifier; add a calibrated/thresholded version
  on a larger balanced set.
- Export and measure the v3 candidate pointer token-by-token in the browser;
  then the hybrid five-arm and product integration.

## Reproduce

```bash
cd /d/others/Jity
PYTHONUTF8=1 python -X utf8 artifacts/goal/micro-workflow/micro_generative_scale.py
PYTHONUTF8=1 python -X utf8 artifacts/goal/micro-workflow/micro_generative_exists.py
cd frontend
npx playwright test e2e/micro-seq2seq-probe.spec.ts
```

Reports: `scale-report.json`, `exists-report.json`, `seq2seq-steps-report.json`,
`browser-seq2seq-probe.json`.
