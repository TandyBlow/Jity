# Short-pair derivation (13-way action-group judgement)

Derived from the frozen 300 rows. The frozen rows, their labels and the old
freeze are read-only here; this directory holds a new derived dataset with its
own freeze. The only text serializer is 04's
`experiments/action-next-step/pairwise_serialize.py`; this lane imports it and
never ships a second renderer.

## What a pair is

One row × one step × one candidate group. 12 groups + `不动` = 13 pairs per
decision, exactly one positive:

- a normal row has one decision (its step 0);
- a two-step row has two decisions (step 0 and step 1); step 1 is shown
  `已做：<first group>（<first object or 无>）` and never its own label;
- a skip row has one decision whose positive is `不动`.

Pairs for the 300 frozen rows are 4290. 01 excluded five rows that carry a
different label for an X identical except the clock (`01-shortx-exclusions.json`),
so the training set is 295 rows / 325 decisions / **4225 pairs**. The excluded
rows stay untouched in the frozen 300; they are only absent from this derived
set.

## Files

| file | role |
|---|---|
| `pair_index.py` | builds the decision index (no model text): pairId, rowId, stepIndex, candidate group, positive flag, group label, object id/name, `已做`, candidate index; refuses to run while a label conflict is unresolved |
| `build_pairs.py` | calls 04's serializer for every indexed pair, refuses opposite-label duplicates, optionally keeps same-label indistinguishable duplicates and lists them |
| `check_pairs.py` | independent re-render, count/positive checks, label-leak check, clock-row check, object resolution, real-tokenizer length |
| `freeze.py` | writes `out/freeze.json` with file hashes, counts, serializer digest, tokenizer/model hashes and the exclusion list |
| `out/` | the deliverable (pairs, metadata, reports, freeze) |
| `out-provisional/` | pre-time-field run, kept only as evidence; never train on it |

## Commands

```bash
cd experiments/action-dataset-v1

# 1. decision index with 01's exclusions
python -X utf8 short_pairs/pair_index.py \
  --rows rows/train13-full-candidates.jsonl \
  --labels ../../../results/action-dataset-20261111/labels-v1.json \
  --resolution ../../../results/action-short-pairs-20261111/01-shortx-exclusions.json \
  --out-dir short_pairs/out

# 2. render through 04's serializer
python -X utf8 short_pairs/build_pairs.py \
  --rows rows/train13-full-candidates.jsonl \
  --index short_pairs/out/pairs-index.jsonl \
  --out-dir short_pairs/out \
  --allow-same-label-duplicates   # only for the one indistinguishable pair 01 accepted

# 3. independent check (real MiniRBT tokenizer)
python -X utf8 short_pairs/check_pairs.py \
  --rows rows/train13-full-candidates.jsonl \
  --pairs short_pairs/out/pairs.jsonl \
  --out short_pairs/out/check.json

# 4. freeze
python -X utf8 short_pairs/freeze.py --out-dir short_pairs/out \
  --rows rows/train13-full-candidates.jsonl \
  --exclusions ../../../results/action-short-pairs-20261111/01-shortx-exclusions.json
```

## Rules this directory enforces

- No second serializer. `build_pairs.py` imports 04's file and refuses to run
  if it is missing, its version changes, or its group order changes.
- No silent truncation. Every pair carries 04's `omitted` record (clipped
  goals, dropped present/items, extra recent events).
- No opposite-label duplicates. A shared short text with two labels stops the
  build; exclusion happens in `pair_index.py`, never by editing Y.
- Same-label indistinguishable duplicates are allowed only with the explicit
  flag and are listed in the build report (`indistinguishable`), per 01's
  ruling for `b5-0035`/`b6-0010`.
- Clock-dependent rows must show `时间=`; `check_pairs.py` fails if they do not.
- The frozen 300-row file and its freeze are never modified.
