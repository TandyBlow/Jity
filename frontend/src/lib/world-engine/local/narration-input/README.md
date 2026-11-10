# Narration input adapter

One projection from a committed `WorldState` pair + `EntityDelta` set, serialized
into the exact format lane 10 trained and froze.

| Version | Model path | Result block |
|---|---|---|
| `yuyan-prose-legacy-v1` | existing YuYan-700M checkpoint | no |
| `yuyan-prose-result-v2` | v2 arm actually trained by lane 10 | yes |

The projection is `narration-result-view-v2` for both paths; legacy is a
serializer variant over the same normalized projection, not a different
projection. Never feed a `result-v2` string to the legacy weights and call it
the same condition.

```ts
import { buildNarrationInput, renderNarrationInput, projectNarrationInput } from
  '@/lib/world-engine/local/narration-input';

const projected = projectNarrationInput({ before, after, delta, timeAdvance, viewpointId });
const v2 = renderNarrationInput(projected.projection);           // trained path
const legacy = renderNarrationInput(projected.projection, { model: 'legacy' });

// One-shot, returning projection metadata + rendered bytes:
const { projection, tasks, textCarryLimits, omittedFields, rendered } =
  buildNarrationInput({ before, after, delta, timeAdvance, viewpointId });
```

`rendered` contains `text`, `sha256`, `bytesUtf8Hex`, `utf8Bytes`, `charCount`,
`segments`, `serializerVersion`, and the version/tokenizer binding. The SHA is
over the exact UTF-8 bytes. There is no partial-text fallback: every validation
failure throws, with a stable `stage`, `code`, and `path`.

- `before` and `after` are committed `WorldState`s; `delta` is the point's
  `entityDeltas`; `timeAdvance` is required. The state block is the **before**
  state; the after state appears only in `本回合状态`, changed entities and
  changed fields only.
- Every changed entity enters. Only changed items enter; unchanged same-room
  items stay out and are listed in `omittedFields` with `item_not_changed`.
  Visibility is the innermost location after following containers; slots do
  not split a scene.
- Names sort by Unicode code point, not `localeCompare` or UTF-16 order.
- `yuyan-prose-result-v2` item lines are `名称（位于<位置>）：…`, so the item
  position is no longer lost. The legacy serializer intentionally keeps the old
  bytes, including the old item-position loss.
- Task status lines are flat in the text: `任务<目标>（<状态>）`. The structured
  `tasks` result and `textCarryLimits` record the parent link and depth that the
  text cannot carry (`task_parent_relation_not_in_v2_text`,
  `task_depth_not_in_v2_text`). Do not claim the old training text contained a
  hierarchy.
- Ordinary spaces/tabs/U+3000 are removed with a normalization ledger; CR/LF
  and other whitespace are refused (`newline_not_allowed`,
  `unsupported_whitespace`). Characters outside the YuYan vocabulary are refused
  at the `tokenizer` stage (`tokenizer_oov`).
- No list slices or silent truncation. `limits` throw `input_too_long` with
  measured `charCount` and `utf8Bytes`.
- The tokenizer is bound to `yuyan-char-v1`, vocabulary file
  `tokenizer/yuyan-v1/dict.txt` (13,668 entries), SHA-256
  `20287a9d1a2ec9d82b2a13f02c10c7b81e8bb015f114134bca6b06e5c8d376b4`.
  `yuyan-charset-v1.json` is derived from that exact file and its
  source hash is checked at import.
- The projection contains no reference narrative or evaluation labels.

## Frozen reference

The v2 format was defined and trained by lane 10. This adapter is tested against
that reference, not against a self-defined expectation:

- `goldens/runtime-v2/vectors.jsonl`: lane 10's 49 golden vectors (20 real, 16
  synthetic, 13 negative), with expected bytes/SHA/segments or error
  code/stage/path.
- `goldens/runtime-v2/train-projections.jsonl`: the 199 trained projections
  (`{id, x}`) from `data/rows-v2.jsonl`.
- `goldens/runtime-v2/train-rows-index.json`: expected `xProse` SHA/char/byte
  counts and legacy SHA/counts for all 199 rows, plus the source file hashes.
- `goldens/runtime-v2/length-stats.json`: measured v2/legacy lengths.

Refresh the freeze from the lane-10 source (default path is the 10-training
worktree; the source hash is checked before copying):

```bash
cd frontend
python -X utf8 scripts/parallel-input/sync_v2_contract.py
```

The legacy 199-row goldens are generated from the original dataset by
`scripts/parallel-input/build_legacy_goldens.py`.

## Tests

```bash
cd frontend
npx vitest run src/lib/world-engine/local/narration-input --maxWorkers=1
```

`vectors.test.ts` compares all 49 vectors byte for byte (including segments and
error stages/codes/paths); `train-rows.test.ts` compares all 199 trained v2
inputs and their legacy counterparts, and cross-checks the live lane-10 file
when present; `legacy-golden.test.ts` freezes the old bytes; `project.test.ts`
and `free-day.test.ts` cover collection, positions, tasks, whitespace, OOV,
limits, and the real free-day world.

## Limitations

- No real GPU/browser generation is run here. This is an input adapter; narration
  quality and latency belong to the quality lanes and the integration run.
- `yuyan-prose-result-v2` text is the trained format; the v2 weights themselves
  are lane 10's artifact and are not stored in this lane.
- The legacy format is lossy by design: item lines omit the position, task
  depth is flattened, and there is no result block. No general lossless reverse
  parsing is claimed.
- Only character and UTF-8 byte counts are measured here; token counts require
  the actual tokenizer runtime.
- A character with no task tree or with more than one root task is rejected
  (`empty_tasks`, `multiple_task_roots`); the format cannot represent those
  states without inventing a hierarchy.
- Location dependencies add the room seeds plus one immediate parent, matching
  the source dataset rule. A deeper ancestor policy needs a new projection
  version and matching training inputs.
