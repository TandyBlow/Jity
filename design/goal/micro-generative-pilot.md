# Micro generative pilot — 2026-11-26

Status: pilot evidence, not a deployment result.

## Scope

From-scratch encoder-decoder models at three widths, for two tasks:

- `conditions`: task goal -> short structured condition fields using world entity IDs.
- `events`: action/fact -> actual result, targets, items, destination, information,
  environment change, promise, decision, cause.

Inputs carry a compact entity glossary (`名称=id`) from the world. Outputs are
pipe-separated `key=value` sequences. Entity-valued fields use the registered
IDs. A constrained-decoding pass restricts `target/item/loc/dest` to IDs present
in the row glossary; the owner/actor is excluded from `target`.

Data: 380 rows (308 train / 72 test), built from the 73 world tasks and 18
action/result fixtures. 15 tasks and 3 event actors are held out. Each task has
four surface variants (prefix/suffix forms). Event rows include same-keyword
different-result negatives (`blocked`, `failed`).

The labels are rule/action-structure teachers. This measures format learning,
scale, architecture and latency; it is **not** a semantic-generalization or
human-label result. Training field recall is about 1.0, so the test gap is
memorization, not underfit.

## Arms and results

Hardware: RTX 4060 Laptop, batch 1, greedy decoding, 32-token cap. Timings are
single-process GPU unless `cpu` is marked. CPU is the same desktop CPU, not a
browser.

| arm | params | fp32 MB | int8 MB | GPU p50 | GPU p95 | CPU p50 | cond field R | event field R | exact |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| multi 5M | 4.69M | 19.1 | 6.6 | 23.1 ms | 32.8 ms | 42.0 ms | 0.324 | 0.05 | 0.125 |
| multi 15M | 14.63M | 58.9 | 19.8 | 30.3 ms | 52.1 ms | 66.1 ms | 0.361 | 0.35 | 0.222 |
| multi 30M | 33.30M | 133.7 | 44.7 | 43.6 ms | 123.0 ms | 109.9 ms | 0.306 | 0.40 | 0.222 |
| indep 5M cond | 4.69M | 19.1 | 6.6* | 26.8 ms | 43.6 ms | — | 0.213 | — | 0.150 |
| indep 5M event | 4.69M | 19.1 | 6.6* | 34.3 ms | 47.3 ms | — | — | 0.35 | 0.000 |
| indep 15M cond | 14.63M | 58.9 | 19.8* | 31.2 ms | 85.0 ms | — | 0.333 | — | 0.167 |
| indep 15M event | 14.63M | 58.9 | 19.8* | 40.9 ms | 50.6 ms | — | — | 0.60 | 0.000 |
| indep 30M cond | 33.30M | 133.7 | 44.7* | 38.7 ms | 100.3 ms | — | 0.278 | — | 0.183 |
| indep 30M event | 33.30M | 133.7 | 44.7* | 35.9 ms | 54.1 ms | — | — | 0.45 | 0.000 |
| shared 2-decoder 15M | 22.59M | 90.3 | — | 32.2 ms | 50.5 ms | — | 0.278 | 0.35 | 0.111 |

`*` the int8 size is the measured per-scale model size; the ONNX export is the
multi-task graph. Per-task independent graphs were not exported separately.

`field R` is the fraction of gold `key=value` fields reproduced on the held-out
rows. Exact match requires the whole continuation to match. Conditions and
events are scored on the continuation: the `COND|` header and the event actor
are supplied as a decoder prefix, so they are not counted.

## Per-field, best dedicated arms

15M event model (held-out actors): `result` 1.000; `target` 0.000; `item` 0.000;
`dest` 0.000; `info`, `env`, `promise`, `decision`, `cause` absent or 0.000.

15M conditions model (held-out tasks): `loc` 0.800 (many rows have no location;
absence counts as correct), `target` 0.333, `conf` 0.167, `act` 0.000,
`time` 0.000, `decision` 0.000, `item` 0.000.

The 15M event `result` accuracy is on a small held-out set (3 actors, positive
and negative rows); it is a signal for a hybrid result head, not a production
number.

## Findings

1. The format is learnable; held-out extraction is not. Train field recall is
   about 1.0, test conditions 0.21–0.36 and events 0.35–0.60; exact match
   0–0.22. The four surface variants do not create semantic diversity.

2. Entity IDs are not copied reliably. The 15M event model gets `result` but
   `target/item/dest` are 0; the conditions model gets some targets but no
   items. Constrained decoding raised the 15M independent conditions arm from
   about 0.27 to 0.33–0.34 across runs, but did not fix event entities. Entity IDs must stay
   with the linker/classifier or be selected from an explicit candidate set,
   not generated as free tokens.

3. Scale does not pay at this data size. 5M conditions 0.213 / events 0.35;
   15M 0.333 / 0.60; 30M 0.278 / 0.45. The best event arm is 15M independent;
   30M is worse and 2.4× slower. 5M remains the latency/size baseline.

4. Independent dedicated models beat the shared variants. The 15M multi-task
   model reaches events 0.35 versus 0.60 for the independent 15M event model;
   the shared encoder + two decoders reaches 0.35. The shared encoder trades
   event accuracy for conditions; there is no evidence for sharing at 308 rows.

5. The only high-accuracy generative field is event `result`. `info`, `env`,
   `promise`, `decision`, `cause`, `time`, `act`, and condition `item` are at
   or near zero. These are exactly the fields the LLM/rule/classifier stack
   currently supplies. A direct replacement would regress semantics.

6. Latency and size. The 15M model runs at 30–41 ms p50 GPU, 50–85 ms p95;
   CPU p50 is 66 ms for the multi 15M. int8 is 6.6 / 19.8 / 44.7 MB for
   5M/15M/30M. Browser WASM/WebGPU was not measured; the CPU numbers are a
   desktop lower bound and cannot be used as the browser cost.

## Decision

Do not integrate the generative arm as-is. Do not replace the task-condition
classifier or the entity linker.

Next experiments, in order:

1. A hand-authored/human-labeled event and condition test set (synonyms,
   negation, implied results, other-person information, multi-event rows,
   same-keyword/different-result negatives). Keep the current frozen scenario
   set separate.
2. A hybrid event head: 5M–15M model for `result` only, with the rule/action
   structure providing actor/target/item/dest and the LLM retained for
   `info/env/promise/decision/cause`; gate every accepted field with the
   existing verifier.
3. Task-condition generation only for decision/composite wording at task
   creation, cached per task; entity IDs from the linker. Do not generate
   `time/act/item` fields.
4. Re-run the five-arm comparison (rules, classifiers, generative, hybrid, LLM)
   on the frozen `scenarios-independent.json` after the hybrid is wired into
   `/world-local`; measure real achievement, false achievement, missed
   achievement, state assertions, prose consistency and full-turn time.
5. Export the selected model as separate encoder/decoder ONNX graphs and
   measure `onnxruntime-web` on the product page; the current export is a
   teacher-forcing graph, not the browser decode loop.

## Reproduce

```bash
cd /d/others/Jity
PYTHONUTF8=1 python -X utf8 artifacts/goal/micro-workflow/micro_generative_pilot.py
```

Outputs: `artifacts/goal/micro-workflow/micro-generative/pilot-report.json`,
`rows.jsonl`, and per-scale `multi_*.onnx` / `multi_*-int8.onnx` (local, not
committed). The ONNX files are generated artifacts; the script is the source
of truth.
