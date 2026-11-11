# lane 13 handoff — action dataset (batch1 repair checkpoint)

Status: **not complete**. 01's audit of the first 220 rows returned 132 pass / 88 fail, and 01 required a small diverse repair batch (20–30 rows) to be reviewed **before** the remaining rows are built. This handoff records the repair batch and the open decisions; the 300-row deliverable is still pending.

## What 01 found

| Cause | Rows | Disposition |
|---|---|---|
| skip built by marking every task achieved, then calling it skip | 82 | retired; `cases/02-skip.jsonl` is history only, `build_rows.py` refuses rows whose actor has no pending goal |
| actor placed inside the locked equipment cage (unreachable) | 3 (`0132/0149/0182` = `d-043`, `d-061`, `e-012`) | deleted: there is no unlock transform, and moving the actor outside the cage removes the very item the label points at, so no honest repair exists |
| identical X with two different labels | 2 pairs (`0106/0172`, `0125/0186`) | one row of each pair already deleted (`d-013`, `d-035`); the surviving rows are unique |
| `刚才` written as an engine log line | 1 (`0011`, later corrected to pass by the user) | `刚才` is now restricted to perceivable scene lines |

The other 122 constructed rows and 11 real rows pass; 133 rows remain (11 real + 73 direct + 49 condition), all with a 01 pass verdict, and are rebuilt under the new X shape after the batch verdict.

## What changed in the code

1. **X uses 04's frozen loader shape.** `tools/loader.py` imports `worktrees/04-settlement/experiments/action-next-step/serialize.py` read-only; every row records its version and sha256. There is no second serializer. `check_dataset.py` renders each row through that file and resolves each step's `object` through `object_index`.
2. **`刚才` is perceivable only.** Position changes become `X 到了<目的地>`, appearance changes become `X：<可见描述>`; authored `perceived` sentences must name the entity and the destination anchor. Task/sanity/personality changes stay in provenance. Engine phrasing (`移动到/任务/已完成`) is rejected by the projection.
3. **skip has a written blocking fact** and rows without a pending goal are refused. The batch's 5 skip rows cover: waiting for someone (injured, alone), time gate + observer post, pinned by fire, holding a window, holding the flag base.
4. **Provenance** records each evidence run's `status`; the primary pointer prefers a non-`FAILED` run and `copies` lists every location of the same state with its status.

## Batch 1 (delivered for review)

- 24 rows: 9 A (condition present), 10 B (create the condition), 5 skip; 18 one-step, 1 two-step; 3 from real committed snapshots, 21 constructed; 21 rows carry `刚才`; 9 actors; 11 predicates; 23 of 48 TRAIN goals; 0 duplicate X.
- Replay: 24/24 rows rebuilt from base + transforms with exact X equality; frozen input hashes re-checked; 0 held-out goals.
- Rows `experiments/action-dataset-v1/rows/batch1-candidates.jsonl` (sha256 `d23bbbf4…93487a`), provenance `batch1-provenance.jsonl` (`a0974e73…0656a7`), check `batch1-check.json` (`21c03921…4390a3`).
- Branch `goal/local-13-action-dataset`, head `2b283d04`, pushed to origin.
- Shared notes: `results/action-dataset-20261111/13-to-01-repair-batch1.md` (review request + questions), `13-to-04-x-shape.md` (X shape proof + two renderer requests + length measurements), `13/completion.json`.

## Open decisions (not mine to make)

1. skip vs `等待`/`观察` for the 5 boundary rows.
2. whether a cross-room move destination may become a candidate (2 rows use `object: null`).
3. whether states that only exist in `FAILED` runs are excluded outright (2 of 9).
4. where time lives in X (currently appended to the 地点 slot text).
5. X length: 04's `maxLen` cap 384 truncates 24/24 rows, and truncation cuts the last slot (候选, which `object` points into). Options measured: id-only candidates → p50 611, + no item place → 591, + goals 1–2 → 445, + personality 60 → 420/max 821.
6. whether 03's blind re-review covers only the 11 real rows or also the 122 passing constructed rows.

## Next

After 01's verdict on this batch: fix the failed rows only, rebuild the 122 passing rows under the new X shape, add the remaining rows to 300 with A/B coverage per TRAIN goal, re-run `build_rows.py` + `check_dataset.py` + tests, and hand the full set to 01 for 100% review.
