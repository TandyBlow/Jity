# Action-classifier browser runner (09 lane)

Runs the MiniRBT-H256 action classifier **in a real browser**, once-loaded and
batched, under the shared inference lease. It never uses wllama: the model is a
BERT encoder plus heads exported to ONNX, so the runtime is onnxruntime-web.

## What it refuses to do

- run without a frozen export manifest (model, tokenizer, config hashes),
- run without the frozen split/test files described by the manifest,
- run without the lease,
- run before 04 publishes the validated export and 01 freezes the test split.

## Files

- `serve.mjs` — static server for the probe page, the ORT distribution and the
  exported model. Sends COOP/COEP so a multithreaded wasm build stays available,
  and supports range requests for the ONNX file.
- `run.mjs` — Playwright (Edge) driver: one model load, then the frozen inputs in
  batches; writes one JSONL record per input with the serialised X, token ids,
  raw head logits, decoded Y, per-item and per-batch times, and the hashes.
- `page.html` — imports onnxruntime-web, builds the tokenizer from the exported
  `vocab.txt`, and exposes `window.__classify(batch)`.

## Export contract (04)

`export.json` next to the ONNX file:

```json
{
  "model": { "file": "model.onnx", "sha256": "…" },
  "tokenizer": { "file": "vocab.txt", "sha256": "…", "lowercase": true, "maxLen": 192,
                 "parity": [{ "text": "…", "ids": [101, …] }] },
  "config": { "sha256": "…", "serializer": "x-v1" },
  "heads": [
    { "name": "steps",      "output": "steps_logits",   "labels": ["0", "1", "2"] },
    { "name": "s1_action",  "output": "s1_action_logits", "labels": ["观察", "…115"] },
    { "name": "s1_object",  "output": "s1_object_logits", "labels": ["null", "…candidate ids"] },
    { "name": "s2_action",  "output": "s2_action_logits", "labels": ["观察", "…115"] },
    { "name": "s2_object",  "output": "s2_object_logits", "labels": ["null", "…candidate ids"] }
  ],
  "test": { "file": "test.jsonl", "sha256": "…" },
  "input": { "field": "x", "idField": "rowId" }
}
```

The runner applies the same argmax rule as 04's Python evaluation; thresholds and
any masking are read from the manifest, never fitted in the browser.

## Checks the runner enforces before any batch

1. every `export.json` hash matches the file on disk (model, tokenizer, config, test),
2. the frozen test file is non-empty and every row has an id and an `x` text,
3. the browser tokenizer reproduces 04's `tokenizer.parity` ids exactly — otherwise
   the run aborts, because a different tokenisation means the numbers describe
   different inputs than the training data,
4. the output file does not exist (evidence is never overwritten).

## What it records

One JSONL record per input: rowId, the serialised X it received, its length and
sha256, the token ids the page produced, every head's raw logits for that row,
the argmax index/probability/label per head, and the batch's wall time. Plus
`run-start` (all hashes, batch size), `model-loaded` (providers, load ms, thread
count), `tokenizer-parity`, and `run-end`.
