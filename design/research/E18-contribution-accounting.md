# E18 Contribution accounting for the hybrid micro arm

**Question.** The five-arm protocol requires counting what each contributor
did: micro inferences, program calls, LLM generations, retries, abstains and
stage time. What does one 8-turn hybrid run actually contain?

**Setup.** `contribution_report.py` reads the acceptance evidence of the 8
frozen scenarios (`evidence-perf-taskskip-8.json`, micro arm, prose shape) and
counts per turn: micro rows and inferences by port, program rows, abstain rows,
LLM generations by engine (deduplicated by generation timestamp — the page's
generation log repeats across turns), retries, fallbacks, and stage
milliseconds. Output: `contribution-hybrid-8.json`.

**Results (8 turns, mean 61.9 s).**
- Micro: 5,131 scored items in 1,730 rows — judge 3,090 pair scores, results
  550, behaviour 496, continuation 508, task proposer 487. Per turn ≈ 641
  micro scorings.
- Program: 224 rows; 88 abstain rows (the ports that deferred to another lane).
- LLM: 133 generations (semantic 106, narration 27), 0 retries, 0 fallback
  rows; 67,924 prompt tokens with 74,114 cached-prefix tokens.
- Stage time: subtasks 80.7 s, tasks 65.5 s, personality 12.2 s, sanity 7.6 s,
  position 4.8 s, appearance 3.7 s, continuation 2.0 s, results 1.2 s. Sums
  exceed the 495 s wall time because stages overlap with generation.

**Conditions.** One evidence file, one world, one seed; the judge's pair count
is a scoring count, not a model call count; per-stage sums are wall-clock
slices that overlap. The LLM dedupe relies on the generation timestamp
uniqueness in this evidence.

**Principle.** In the hybrid arm the micro models do the bulk of the semantic
work by count (≈5.1k scorings vs 133 LLM generations), and the remaining wall
time is concentrated in the two LLM task stages — the same two stages D-103
measured. Contribution accounting belongs next to every arm's evidence; it
turns "mostly micro" into a number.

**Artifacts.** `contribution_report.py`, `contribution-hybrid-8.json`,
`evidence-perf-taskskip-8.json`, D-116.
