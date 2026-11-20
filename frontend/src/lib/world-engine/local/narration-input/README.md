# Narration input adapter

One projection from a committed `WorldState` pair + `EntityDelta` set, two
serializers:

| Version | Model path | Result block |
|---|---|---|
| `yuyan-prose-legacy-v1` | existing YuYan-700M checkpoint | no |
| `yuyan-prose-result-v2` | new training/inference path | yes |

Never feed a `result-v2` string to the legacy weights and call it the same
condition. The legacy bytes are frozen against the real 199-row dataset in
`goldens/legacy-rows-v1.json` and `goldens/legacy-rows-v1-manifest.json`.

```ts
import {
  projectNarrationInput, renderLegacyInput, renderResultInput,
} from '@/lib/world-engine/local/narration-input';

const { projection, includedEntities, visibleEntities, omittedFields, version } =
  projectNarrationInput({ before, after, delta, timeAdvance, viewpointId });
const legacy = renderLegacyInput(projection); // old checkpoint
const v2 = renderResultInput(projection);     // new result-block format
```

- `before` and `after` are committed `WorldState`s; `delta` is the point's
  `entityDeltas`; `timeAdvance` is the point's time advance.
- The state block is the **before** state. The after state appears only in
  `本回合状态`, changed entities and changed fields only.
- Only changed items enter. Same-room unchanged items stay out and are listed
  in `omittedFields` with `item_not_changed`.
- Visibility is the innermost location after following containers; slots do
  not split a scene.
- Names sort by Unicode code point, not `localeCompare`.
- No list slices or silent truncation. `policy.length` limits throw
  `NarrationInputError('too_long')` with measured sizes.
- The legacy serializer applies the old converter's exact `squash` rules and
  rejects any other whitespace/OOV before the text can reach the tokenizer.
- The projection contains no reference narrative or evaluation labels.

Regenerate the legacy goldens from the source dataset:

```bash
cd frontend
python -X utf8 scripts/parallel-input/build_legacy_goldens.py
```

Regenerate the v2 frozen sample after an intentional format change:

```bash
WRITE_RESULT_GOLDENS=1 npx vitest run src/lib/world-engine/local/narration-input/result-golden.test.ts
```
