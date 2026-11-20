# Short-pair delivery (13-way action-group judgement)

- pairs: **4225** (325 decisions, 325 positives)
- rows used: 295 of 300; excluded: 5
- second-step pairs: 390
- indistinguishable texts (same label): 13 (see `build-report.json`)
- label-conflicting texts: 0 (the build refuses them)
- tokens: p50 168 / p95 191 / p100 211, ceil32 224, over 512: 0
- serializer: `action-pairwise-x2` sha256 `55bc641f18793846179831eec4a527ab2069778fab3172ee2eefab10dad6f95d` (tracked=True, dirty=False)

## Positive count per candidate group

| group | positives |
|---|---|
| 言语 | 53 |
| 立场 | 14 |
| 物品 | 31 |
| 移动 | 36 |
| 感知 | 144 |
| 援助 | 4 |
| 请求 | 19 |
| 战斗 | 2 |
| 不动 | 22 |

9 groups have positives (感知 144, 移动 36, 战斗 2, 援助 4, 请求 19, 言语 53, 物品 31, 立场 14, 不动 22); 4 groups (胁迫/算计/情绪/身体) have zero training rows and are reported as `no_training_rows`, not as model failure.

Second step: 30 decisions, 8 with the same group as 已做 and 22 with a different one; report them apart.

## Omission totals

| what | count |
|---|---|
| goalsClipped | 18564 |
| presentClipped | 0 |
| itemsClipped | 5538 |
| recentClipped | 689 |

## Files

- `pairs.jsonl` sha256 `124fc0ebadc1a31190d03132bf9e74c2480fb5973bddbe53c235d38d3f85e627`
- `pairs-index.jsonl` sha256 `9bce7ca41c5b800775562536cef22daa0361e1347fba813bfef5cccb0a847c59`
- `rows-meta.jsonl` sha256 `919bfe201d7905968ddbb8e2cfbc6a3979d035228bd68dec52b002069310f764`
- `build-report.json` sha256 `55a93484995d764b70b2c7df4f93516019457941709dda5039eb53b34eaba3f6`
- `check.json` sha256 `9d661c81c549fc59a142193c5ab944f43d1cfec758401e26f72f81ce8e3e1df6`
- `index-report.json` sha256 `b5e5ff032c768e7bca1ff59111c4e22786539dd89dd4edc678504be28c5023c6`

## Reproduce

```bash
cd experiments/action-dataset-v1
python -X utf8 short_pairs/pair_index.py --rows rows/train13-full-candidates.jsonl \
  --labels ../../../results/action-dataset-20261111/labels-v1.json \
  --resolution ../../../results/action-short-pairs-20261111/01-shortx-exclusions.json \
  --out-dir short_pairs/out
python -X utf8 short_pairs/build_pairs.py --rows rows/train13-full-candidates.jsonl \
  --index short_pairs/out/pairs-index.jsonl --out-dir short_pairs/out \
  --allow-same-label-duplicates
python -X utf8 short_pairs/check_pairs.py --rows rows/train13-full-candidates.jsonl \
  --pairs short_pairs/out/pairs.jsonl --out short_pairs/out/check.json
python -X utf8 short_pairs/freeze.py --out-dir short_pairs/out \
  --rows rows/train13-full-candidates.jsonl \
  --exclusions ../../../results/action-short-pairs-20261111/01-shortx-exclusions.json
```

Source rows sha256 `cb4676b3eb74945331f73ee8855be300455c9e11db261c288d7534c7b02ef188` (the frozen 300-row file, unchanged).
Model snapshot config `02cc77ba23f292bf5265d76fff662ae8a8057bf85ee9723ba30342bf9ed30746`, vocab `45bbac6b341c319adc98a532532882e91a9cefc0329aa57bac9ae761c27b291c`, max_position_embeddings 512.

This is a training-input freeze, not a model result. The second step is teacher-forced: it keeps the
original X and only adds `已做`, so it is not yet evidence of the settled next state.
