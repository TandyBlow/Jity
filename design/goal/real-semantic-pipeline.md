# Real semantic data pipeline — 2026-11-26

Status: pipeline in place; labeler running; not yet a trained three-task
pipeline.

## Source events

- 20 real product turns from `run41-turns-20-chunk*.json`.
- 8 frozen scenario turns from `evidence-independent-scenarios-6b.json`.
- Unique events by id (one duplicate s12 removed); 20 + 8 rows.
- Fields: player action, same-turn narration, before/after summaries, state
  snapshot, scenario checks for the 8.

## Labeling

`real_semantic_data.py` asks DeepSeek (`LLM_BASE_URL`, `DEEPSEEK_API_KEY`,
`deepseek-v4-pro`) for:

```json
{"info": {"present": true, "content": "...", "support": "..."},
 "env":  {"present": true, "content": "...", "support": "..."}}
```

- `info`: new information actually gained this turn.
- `env`: environment or item state actually changed this turn.
- The support must be a verbatim substring of the action/narration.
- Cache: `real-semantic-cache.jsonl`; reruns skip the API.

## Fact verification (stronger than substring)

- The support must appear verbatim.
- `env`: must contain an environment verb (提开/拖到/让出/固定/释放/…), must
  not be a movement (进入/停在/走/退/…), and must have a state appearance
  change in the snapshot or an explicit environment verb.
- `info`: must not be an action summary (求助/查完/记下/拿起/塞进/递给/…).
- Rejected fields become `present=false`; the raw model proposal stays in the
  cache for the spot-check.

This rejects the first obvious labeler errors: movement recorded as `env`
(sc03/sc05), item transfer recorded as `env` (sc04), and NPC action summaries
recorded as `info` (sc02/sc04).

## Spot-check

`real-semantic-spotcheck.md` lists every event with the action, proposal,
verifier decision and support. It is for the user; it is not auto-approved.

## What the first labels show

- sc01 (dialogue, no answer): info false, env false — correct for the task
  staying pending.
- sc03/sc05: the model proposes movement as `env`; the verifier rejects it.
- sc04: item transfer proposed as `env`; rejected.
- sc02: NPC action summary proposed as `info`; rejected.
- sc05: hatch/ladder observation kept as `info`.
- The labeler is slow on the pro model (5/28 cached when this note was
  written); the cache makes reruns cheap.

## Next

1. Finish the cache and review the spot-check file; replace weak labels.
2. Train the three tasks on the verified rows: info/env existence, specialized
   content extraction (given the correct category), and fact-support
   verification.
3. Evaluate on the held-out real events (sc06, sc08, sc01, s11, g8-t3):
   existence accuracy, extraction accuracy given category, full-workflow
   accuracy, and the state patch.
4. Wire the state patch: env -> item/location appearance change; info -> task
   condition/fact. The held-out sc06/sc08 checks are the state target.
5. Then the v3 candidate-pointer browser export and fixed vs KV-cache decode,
   followed by the five-arm comparison.

## Reproduce

```bash
cd /d/others/Jity
PYTHONUTF8=1 python -X utf8 artifacts/goal/micro-workflow/real_semantic_data.py
```

Outputs: `real-semantic.jsonl`, `real-semantic-cache.jsonl`,
`real-semantic-spotcheck.md`.
