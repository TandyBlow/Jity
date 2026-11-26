# Real semantic data pipeline — 2026-11-26

Status: four-state verifier; 7/28 cached; not yet a trained three-task
pipeline.

## Source events

- 20 real product turns from `run41-turns-20-chunk*.json` (5 separate chunks;
  the first turn of each chunk has no before snapshot).
- 8 frozen scenario turns from `evidence-independent-scenarios-6b.json`; the
  whole set is test-only.
- Each row stores: player intent, settled actions (`actions` results),
  same-turn narration, before/after summaries, before/after snapshots, and the
  scenario checks for the 8.

## Separation

- **intent**: the player input; never treated as a settled fact.
- **settled**: `actions` entries with `recordKind=result`; the factual source
  for `info` and for the action half of `env`.
- **narration**: the prose; can corroborate but cannot create a state change.
- **state**: the before/after snapshot diff of active item/location
  `appearanceChanges`.

## State diff

`state_diff(row)` compares the previous turn's snapshot with this turn's
snapshot and returns `known`, `added`, `removed`. The first turn of each chunk/
scenario has `known=false`. A missing before snapshot never becomes a negative
label. This replaces the old post-turn `state_summary` that read the active
appearance list instead of this turn's new records.

## Four label states

- `present`: support verified, and for `env` a matching new appearance record
  or a settled action fact for `info`.
- `absent`: confirmed negative only — explicit no-answer/no-change evidence
  (sc01 “没有答出”) or a known empty state diff with no environment action.
- `insufficient`: evidence missing (unknown before, support not found, env
  action without a state diff, ambiguous info). Not a negative sample.
- `conflict`: the settled action/narration and the old state disagree (sc06
  hatch open but no new appearance; sc08 table moved but no new appearance).
  This is the **fix set**, never a negative sample.

Unverified proposals keep their raw content/support for the spot-check; they
are not rewritten to `present=false` as training negatives.

## Split

- Test: all 8 scenario ids; they are one continuous game process and stay
  entirely out of training.
- Train: the 20 product turns, grouped by the 5 chunks; no turn is split across
  train/test.
- The 8 scenario checks are evaluation only; they are not shown to the labeler.

## First verified rows (7 cached)

- sc01: info `absent` (“诺诺没有答出”), env `insufficient` (no before snapshot).
- sc02/sc04: info `insufficient` (NPC action summaries, not information);
  env `insufficient` (movement/item transfer, not environment).
- sc03/sc05/sc07: info `present` (people/camera, hatch/ladder, foyer door);
  env `insufficient` (movement, not an environment change).
- sc06: env `conflict` — the action opens the hatch but the old state has no
  new appearance. This is the fix set the user predicted.
- sc06 info `insufficient`: the proposal labels the route decision, not the
  observation of the ladder/tunnel; the spot-check must correct it.
- sc08 is not cached yet; the expected result from the action is a conflict
  (table moved, old state missing the appearance).
- The strong model's category mistakes remain visible in the raw cache; the
  verifier downgrades them instead of turning them into negatives.

## Next

1. Finish the cache (or label the remaining 21 with the strong model), then
   review the spot-check; correct the conflict/fix set and the sc06 info.
2. Expand verified real events; do not add template volume.
3. Train the three tasks only on `present`/`absent` rows: existence,
   specialized extraction given the category, fact-support verification.
4. Evaluate on the 8 held-out scenarios: existence accuracy, extraction given
   category, full workflow, and the state patch. The patch must add the
   sc06/sc08 environment changes and must not add extra changes.
5. Then the v3 candidate-pointer browser export and fixed vs KV-cache decode;
   followed by the five-arm comparison.

## Reproduce

```bash
cd /d/others/Jity
PYTHONUTF8=1 CACHE_ONLY=1 python -X utf8 artifacts/goal/micro-workflow/real_semantic_data.py
# without CACHE_ONLY, missing ids are sent to the strong model
```

Outputs: `real-semantic.jsonl`, `real-semantic-cache.jsonl`,
`real-semantic-spotcheck.md`.
