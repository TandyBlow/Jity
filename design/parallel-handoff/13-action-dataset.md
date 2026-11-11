# lane 13 handoff — action dataset (300 rows frozen and reviewed)

Status: **delivered and frozen**. 300 training candidates are built, replayed and reviewed; 01 passed them 300/300 at the label level and asked for no further edits. This is a reviewed label set, not a model-effect result: the effect still needs 04's training + holdout and 09's real runs.

## Frozen object

- Branch `goal/local-13-action-dataset`, commit `b49b16c1`, pushed to origin.
- Delivery file `experiments/action-dataset-v1/rows/train13-full-candidates.jsonl`, 300 rows, sha256 `cb4676b3…b02ef188`.
- Provenance `train13-full-provenance.jsonl` sha256 `41e55dfd…78bd6c2`; independent replay `train13-full-check.json` sha256 `0cdaafa2…cb58176a` (300/300).
- Freeze record `rows/freeze-300.json` (also `results/action-dataset-20261111/13/freeze-300.json`): counts, hashes of the criterion/labels/goal list, serializer version and sha256, known gaps, review reference.
- Do not edit the frozen files. A change means a new freeze record and a fresh 01 review.

## What the 300 rows are

| Dimension | Value |
|---|---|
| Rows | 300: A 176 (condition present), B 98 (first create the condition), skip 26 |
| Steps | 244 one-step, 30 two-step, 26 skip |
| Skip ratio | 8.7%; 01 waived the ~30% target because every skip is derivable from X |
| Unique X | 300 of 300; cross-file duplicates are refused by `scripts/assemble.py` |
| Sources | 19 committed snapshots untouched, 276 snapshot + transforms, 5 built from world s0 |
| Goals | 45/48 TRAIN goals have an A row, 36/48 have a B row; 3 goals are achieved at S0 and can only be A |
| Groups | 感知 145 / 言语 51 / 移动 41 / 物品 31 / 请求 18 / 立场 12 / 援助 4 / 战斗 2; 胁迫/算计/情绪/身体 absent by 01's decision |
| X length | min 400 / p50 629 / p95 1207 / max 1460 chars (04's frozen serializer) |

## How the rows were built

1. **X is rendered by 04's frozen serializer only.** `tools/loader.py` imports `worktrees/04-settlement/experiments/action-next-step/serialize.py` read-only; each row records the serializer version and sha256. There is no second serializer.
2. **`刚才` is perceivable only.** Position changes become `X 到了<目的地>`, appearance changes become `X：<可见描述>`; an authored `perceived` sentence must name the entity and the destination anchor, and engine phrasing (`移动到/任务/已完成`) is rejected. Perception is limited to the actor's innermost room.
3. **One row per unique X.** `build_rows.py` refuses duplicate X inside a build, `assemble.py` refuses duplicates across the seven batch files.
4. **Provenance honesty.** `row.source == provenance.source`; `derivation` says `committed-snapshot`, `committed-snapshot+transforms` or `world-s0+transforms`; evidence pointers prefer a non-`FAILED` run and list every copy with its run status.
5. **skip needs a blocking fact in X** (waiting, blocked, duty, time gate, injury) and the actor must still have a pending goal. The "finish every task then skip" recipe is retired and refused by the builder.
6. **Independent replay.** `check_dataset.py` rebuilds every X from base + transforms, compares it, re-renders through 04's serializer, resolves every `object` through `object_index`, re-checks the frozen input hashes and the skip ratio.

## Review trail

- `results/action-dataset-20261111/01-audit-v1.jsonl` / `-v1b.jsonl` / `-combined-v1.json`: the first 220 rows, 132 pass / 88 fail; the fail causes were repaired, not waved through.
- `01-audit-batch1*.jsonl`, `-batch2.jsonl`, `-batch3.jsonl`, `-batch4.jsonl`, `-batch5.jsonl`: per-batch reviews of the repair batches; every cited fail was fixed and re-cited in `13-to-01-batch4-6*.md`.
- `01-audit-full300.jsonl` + `01-to-13-full300-r2.md`: the final read of the frozen file, **300/300 pass**, with the note that this is a label-level verdict.

## Open items for later work (not blockers for this lane)

1. X length: p50 629 exceeds the frozen `maxLen` 384, and truncation would cut `候选` (the slot `object` points into). 04 owns the projection decision (`results/action-dataset-20261111/04-x-length-decision.md`).
2. Cross-room `移动` rows carry `object: null` until the contract has a destination slot.
3. Time is appended to the 地点 slot; there is no dedicated time slot.
4. The four absent groups (胁迫/算计/情绪/身体) are deferred to the next data version, pending the first model's confusion matrix.
5. 03's blind re-review of a random 10% is 01's process; 13 does not see test answers.

## Reproduce

```bash
cd experiments/action-dataset-v1
python -X utf8 scripts/build_rows.py --catalog cases/01-real.jsonl cases/03-direct.jsonl cases/04-condition.jsonl \
  --class-defaults cases/classes-v1.json --allowed-goals <01-train-goals-for-13.json> --row-prefix train13r \
  --out rows/train13r-candidates.jsonl --provenance-out rows/train13r-provenance.jsonl --report-out rows/train13r-report.json
python -X utf8 scripts/build_rows.py --catalog cases/batch1 --row-prefix b1 ...   # batch2…batch6 likewise
python -X utf8 scripts/assemble.py --rows-dir rows --out rows/train13-full-candidates.jsonl \
  --provenance-out rows/train13-full-provenance.jsonl --report-out rows/train13-full-report.json
python -X utf8 scripts/check_dataset.py --rows rows/train13-full-candidates.jsonl \
  --provenance rows/train13-full-provenance.jsonl --allowed-goals <01-train-goals-for-13.json> --out rows/train13-full-check.json
python -X utf8 -m pytest tests -q   # 41 passed
```
