# Tasks: goal-semantic-micro

## 1. Audit and data export

- [ ] 1.1 Publish the full call-path audit (`design/research/E54-semantic-call-audit.md`): per responsibility record input, output, trigger, fallback/retry/exception path, counts, latency, data source, existing replacements and unsolved capability; classify program vs language understanding vs extraction vs open generation. Verify: every `source=model` path in `local/semantics/**` maps to a row; counts reproduce E53 from `09-turns20-pi.json`.
- [ ] 1.2 Add `artifacts/goal/semantic-micro/export_calls.py` to join `semanticCalls` with the turn's `semanticPrompts` and emit per-task JSONL `(turn, task, key, prompt, raw, value, issues, ms, attempt)`. Verify: run on `09-turns20-pi.json` and `10-scenarios-*`; every `source=model` call with a captured prompt is emitted; a unit test covers order/signature matching and reports unmatched counts.
- [ ] 1.3 Add dataset manifest with hashes, counts per task, and split rules (scenario/fact-set/turn); assert the frozen 8-scenario and 20-input evidence never appear in train/validation/threshold scans. Verify: `python artifacts/goal/semantic-micro/check_split.py` exits 0 on the exported set and fails on a seeded leak.
- [ ] 1.4 Record per-port baselines (program / existing micro / original 0.6B / candidate) in `artifacts/goal/semantic-micro/baselines.json` with correctness, coverage, abstain rate, error types, params, bytes, latency. Verify: report regenerated from evidence by script; numbers match E53 and the frozen scenario summary.

## 2. Task achievement

- [ ] 2.1 Build the task-verification dataset from real turns: `(task goal, decomposed conditions, fact text, committed task status, LLM/silver verdict)`, labeled by committed state first and human-verified samples. Verify: dataset stats and 30-sample human check recorded; no frozen acceptance rows included.
- [ ] 2.2 Measure four baselines on a grouped held-out split: current condition head + program floor, current pair verifier, original 0.6B verifier prompt replay, and a new candidate. Verify: report with yes/partial/no confusion, abstain and false-achievement rates; held-out split by task/fact-set.
- [ ] 2.3 Train the candidate verifier (shared encoder or pair scorer) with the four-state evidence discipline; export int8 ONNX. Verify: PyTorch↔ONNX parity 100% within threshold; Node and browser forward pass agree on the held-out rows.
- [ ] 2.4 Wire the candidate behind `?taskVerifier=micro` and make low confidence resolve to no-achievement with `abstain_reason` recorded. Verify: Vitest covers yes/no/partial/abstain; a turn fixture with a true achievement is either accepted or counted as `abstain_reason`, never silently dropped.
- [ ] 2.5 Evaluate on the frozen 8-scenario and 20-input fixtures in the micro-only arm; report achieved tasks vs the hybrid arm, plus skipped legitimate achievements. Verify: 14/14 task expectation compared per scenario; differences listed.

## 3. New subtasks

- [ ] 3.1 Build the subtask dataset from real turns: parent task, facts, proposed subtask, committed/rejected reason (duplicate, foreign subject, restates fact, not grounded). Verify: rejection classes counted; frozen data excluded.
- [ ] 3.2 Implement candidate retrieval + micro ranking + template fill behind `?subtasks=micro`; no free-form generation. Verify: unit tests for each rejection class; an abstain produces zero new tasks with a recorded reason.
- [ ] 3.3 Evaluate subtask precision/recall on frozen fixtures and a fresh scenario set; report both wrong additions and skipped legitimate additions. Verify: report shows counts, not just accuracy; no reduction of task updates traded for success rate.

## 4. Personality and sanity

- [ ] 4.1 Export personality-change inputs/outputs and outcomes; build a grouped dataset. Verify: dataset covers all characters' trigger cases in the frozen evidence.
- [ ] 4.2 Replace personality with a program/micro judgment (change vs keep) and template-bound trait text; abstain = keep. Verify: rejected-echo and foreign-name guards still pass; unit tests cover add/remove/replace.
- [ ] 4.3 Replace sanity recalculation with a deterministic mapping from personality deltas plus a bounded micro head; abstain = keep current value. Verify: integer 0–100 bounds, paired personality/sanity commit test, no invented change.

## 5. Appearance and position

- [ ] 5.1 Export appearance and position model calls with scene/state context; measure current program+micro coverage and abstain reasons. Verify: report per stage with counts.
- [ ] 5.2 Extend the program scene/position resolution (sub-location and container locality) and add a micro disambiguation head; abstain = no change. Verify: regression tests for cross-room container cases (D-136 residual) and ambiguity abstain.
- [ ] 5.3 Replace appearance with program patches + micro selection over existing sentence fragments; abstain = no change. Verify: no invented appearance text; frozen state assertions unchanged.

## 6. Action results and NPC behavior

- [ ] 6.1 Measure the remaining results LLM fallbacks (3/292) and define conservative results answers for micro-only. Verify: every abstain path produces a commit-acceptable answer in a unit test.
- [ ] 6.2 Replace action-understanding LLM fallback with structured candidate decoding + micro ranking; abstain = skip with reason. Verify: frozen scenario action counts, no increase in refused player actions, status/state assertions unchanged.
- [ ] 6.3 Replace target-recognition LLM abstentions (negation, absent name, pronoun) with micro ranking over scene candidates; abstain = empty targets. Verify: frozen targets fixtures and negation cases; no missed legal reactions traded for success.
- [ ] 6.4 Replace reaction LLM fallback with micro intent selection and conservative templates; abstain = neutral template. Verify: trigger-class fixtures and joint-settlement scenarios.

## 7. Structured events

- [ ] 7.1 Implement the read-only `structured-events` adapter from committed results/facts/state delta to event records with actor, target, action, object, result, degree, cause, location, info, env changes, relations and source. Verify: schema tests; events reproduce the same facts without changing `WorldState`.
- [ ] 7.2 Add four-state evidence (present/absent/insufficient/conflict) and export a validation report on real turns. Verify: insufficient/conflict are excluded from negative training rows by a checker.
- [ ] 7.3 Provide the adapter output to the narration side as a read-only reference; document field coverage and gaps. Verify: a fixture narration prompt can consume the event records without protocol changes.

## 8. Micro-only configuration

- [ ] 8.1 Add `?semanticArm=micro-only`: do not construct/load the semantic engine; inject `llmPolicy='block'` into every port; record arm identity and blocked-call counts. Verify: page evidence shows `__worldArm.semanticEngine=absent` and zero 0.6B requests; unit test covers the engine factory.
- [ ] 8.2 Implement kernel-safe conservative answers for every port (action skip, empty targets, neutral reaction, no-change results, no-change updates, handback continuation) with recorded reasons. Verify: a full turn completes in micro-only with the 0.6B file blocked; no `turn_in_progress` deadlock.
- [ ] 8.3 Add abstention and skipped-change accounting to turn evidence. Verify: a micro-only turn with forced abstain reports counts per port; the report separates abstains from successes.

## 9. Acceptance and delivery

- [ ] 9.1 Extend the acceptance driver to assert the semantic GGUF is never requested and the semantic engine is never constructed under micro-only. Verify: driver fails when a synthetic request is injected.
- [ ] 9.2 Run frozen 8-scenario and 20-input acceptance in micro-only on desktop; compare state 48/48, tasks 14/14, achievements 3/3, state diffs, skipped changes and extra errors. Verify: evidence JSON committed under `artifacts/goal/semantic-micro/`.
- [ ] 9.3 Run refresh restore, offline, server-blocked and two-device fork checks in micro-only. Verify: evidence files match the existing acceptance format.
- [ ] 9.4 Measure desktop and mobile semantic-stage latency, full-turn latency, model load, weight bytes, peak and steady memory. Verify: report table with raw runs.
- [ ] 9.5 Write the integration note: call-responsibility mapping, model assets and hashes, data manifest, training/eval commands, rollback to the hybrid arm, and open gaps. Verify: a fresh reader can rerun export, training and acceptance from the document.

## Workflow follow-up

- Archive the change after acceptance evidence and user review are complete.
