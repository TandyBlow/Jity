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

`field R` is the fraction of gold `key=value` fields reproduced on the held-out
rows. Exact match requires the whole continuation to match. Conditions and
events are scored on the continuation: the `COND|` header and the event actor
are supplied as a decoder prefix, so they are not counted.

The independent rows above were produced in the same process as the multi-task
arms. A separate process (`measure_independent_models.py`, same data/split,
seed 20261126, 40 epochs) exported each independent model and measured CPU:

| arm | field R | exact | int8 MB | CPU p50 | CPU p95 |
|---|---:|---:|---:|---:|---:|
| 5M cond | 0.315 | 0.067 | 6.57 | 55.3 ms | 77.8 ms |
| 5M event | 0.400 | 0.000 | 6.57 | 54.2 ms | 77.4 ms |
| 15M cond | 0.417 | 0.250 | 19.84 | 81.1 ms | 132.5 ms |
| 15M event | 0.500 | 0.000 | 19.84 | 55.0 ms | 85.8 ms |
| 30M cond | 0.287 | 0.200 | 44.66 | 43.0 ms | 149.4 ms |
| 30M event | 0.350 | 0.000 | 44.66 | 105.9 ms | 133.6 ms |

The independent field-recall numbers differ from the earlier rows by training
order and run variance (for example 15M events 0.50 here vs 0.60 earlier; 15M
conditions 0.417 vs 0.333). The latency/size columns are the measured ones; the
CPU p50 spread at 30M is noise from a single-threaded desktop measurement.
Report: `artifacts/goal/micro-workflow/micro-generative/independent-report.json`.

Per-field for the independent 15M arms in this run: event `result` 0.833;
`target/item/dest/info/env` 0.000. Conditions `item` 0.312, `target` 0.364,
`conf` 0.368, `loc` 0.692 (absence-inclusive); `time/act/decision` 0.000.

### ONNX shape caveat

The exported graphs declare dynamic axes but the legacy exporter baked the
dummy lengths. `indep_5M_conditions-int8.onnx` runs at `src=55, tgt=18` and
fails at 54, 56, or 96×64; the other independent graphs have the same defect.
The declared `src_len`/`tgt_len` are nominal. Do not treat these as deployable
dynamic models or use the int8 MB as a browser memory number without re-export.

A fixed 96×64 export runs and quantizes: int8 7.86 MB for the 5M width, CPU p50
3.3 ms for one teacher-forcing forward (not the per-token decode loop, not a
browser). `check_fixed_onnx.py` / `fixed-onnx-report.json` record this. The next
browser arm must either pad to a fixed length and export separate encoder and
decoder-step graphs, or use a dynamo export (`onnxscript` is not installed).
The v2/v3 reports do not claim a browser number; the five-arm browser
measurement is still pending.

## Per-field, independent 15M arms (separate run)

15M event model (held-out actors): `result` 0.833; `target` 0.000; `item` 0.000;
`dest` 0.000; `info`, `env`, `promise`, `decision`, `cause` absent or 0.000.

15M conditions model (held-out tasks): `loc` 0.692 (many rows have no location;
absence counts as correct), `target` 0.364, `conf` 0.368, `item` 0.312,
`act` 0.000, `time` 0.000, `decision` 0.000.

The 15M event `result` accuracy is on a small held-out set (3 actors, positive
and negative rows); it is a signal for a hybrid result head, not a production
number. The earlier same-process run had `result` 1.000 and conditions
`item` 0.000; the difference is run variance.

## Findings

1. The format is learnable; held-out extraction is not. Train field recall is
   about 1.0, test conditions 0.21–0.42 and events 0.35–0.60 across the two
   runs; exact match 0–0.25. The four surface variants do not create semantic
   diversity.

2. Entity IDs are not copied reliably. The 15M event model gets `result`
   (0.833–1.0) but `target/item/dest` are 0; the conditions model gets some
   items/targets in the separate run but `time/act/decision` stay 0. Constrained
   decoding raised the 15M independent conditions arm from about 0.27 to
   0.33–0.42 across runs, but did not fix event entities. Entity IDs must stay
   with the linker/classifier or be selected from an explicit candidate set,
   not generated as free tokens.

3. Scale does not pay at this data size. Separate independent run: 5M
   conditions 0.315 / events 0.40; 15M 0.417 / 0.50; 30M 0.287 / 0.35. The best
   event arm is 15M; 30M is worse and 2.4× slower. 5M remains the latency/size
   baseline.

4. Independent dedicated models beat the shared variants. The 15M multi-task
   model reaches events 0.35 versus 0.50 for the independent 15M event model in
   the separate run; the shared encoder + two decoders reaches 0.35. The shared
   encoder trades event accuracy for conditions; there is no evidence for
   sharing at this data size.

5. The only high-accuracy generative field is event `result`. `info`, `env`,
   `promise`, `decision`, `cause`, `time`, `act`, and condition `item` are at
   or near zero (15M item 0.312 is the exception in one run). These are exactly
   the fields the LLM/rule/classifier stack currently supplies. A direct
   replacement would regress semantics.

6. Latency and size. The 15M model runs at 30–41 ms p50 GPU, 50–85 ms p95;
   CPU p50 is 66 ms for the multi 15M. int8 is 6.6 / 19.8 / 44.7 MB for
   5M/15M/30M. Browser WASM/WebGPU was not measured; the CPU numbers are a
   desktop lower bound and cannot be used as the browser cost. The ONNX graphs
   are fixed-shape at their traced lengths despite nominal dynamic axes; see
   the shape caveat above.

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
