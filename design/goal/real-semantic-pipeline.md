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

## Independent audit (2026-11-26)

An independent read-only audit returned **pass=false**. The formal split and
the sc06 conflict/sc01 absent cases are right, but the pipeline still violates
the user's concerns:

1. `verify()` still writes `present=false` for `insufficient`/`conflict`; 10/14
   field labels are unverified but binary negatives. No `trainable` flag.
2. All 7 cache labels came from the old prompt that injected post-turn
   summaries and the scenario checks; the new prompt produced no labels. The
   cache has no `evidence` field, and all 7 are test rows with check
   contamination.
3. `env absent` defaults to an empty appearance diff. The 912 item/location
   entries have zero appearance records, so an empty diff is not evidence of
   no change. `active_changes` tests `superseded` while the engine uses
   `supersedes`; the diff ignores characters/positions/tasks; `ENV_VERBS`
   mirrors the held-out sc06/sc08 checks and misses s07's 推/挪动.
4. Player intent is accepted as support: `settled` includes the protagonist
   command echo (`task=action`, text equals the input), and `info` can be
   decided by the player's own words. Intent, settled actions, narration and
   state are not separated.
5. The diff only looks at item/location appearance; characters (sc02 check),
   item container (sc04), task status (sc06) and `removed` are invisible.

**No training is allowed on this dataset.** The next pass must fix these
before the three tasks.

## Next after the audit

1. Add a three-value target (`true`/`false`/`null`) plus `trainable`; never
   encode `insufficient`/`conflict` as `present=false`.
2. Replace the appearance-only diff with a full state diff: characters,
   positions, tasks, item containers/slots, item/location appearance with the
   engine's `supersedes`; use `removed`; keep the environment field tied to
   actual environment changes, not held-out check regexes.
3. Exclude the protagonist command echo from `settled`; support must come from
   settled actions or narration, never from the player intent; separate the
   four sources in the row and prompt.
4. `env absent` only with explicit no-change/no-action evidence; a missing
   before snapshot or an empty appearance channel is `insufficient`.
5. Add a prompt version to the cache, invalidate the old 7 check-contaminated
   test labels, and re-label the 20 train + 8 test with the checks-free prompt;
   the 8 scenarios stay test-only and the checks stay evaluation-only.
6. Only then train the three tasks on `trainable` rows and evaluate the state
   patch on the 8 scenarios, including extra-change checks.

The v3 candidate-pointer browser arm and KV-cache measurement are already
done (D-052); the product/five-arm work waits for the data pass.

## Reproduce

```bash
cd /d/others/Jity
PYTHONUTF8=1 CACHE_ONLY=1 python -X utf8 artifacts/goal/micro-workflow/real_semantic_data.py
# without CACHE_ONLY, missing ids are sent to the strong model
```

Outputs: `real-semantic.jsonl`, `real-semantic-cache.jsonl`,
`real-semantic-spotcheck.md`.
