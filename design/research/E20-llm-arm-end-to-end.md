# E20 Five-arm end to end: the existing-LLM arm on the frozen scenarios

**Question.** The five-arm protocol needs end-to-end numbers for the LLM arm
on the same frozen scenarios, kernel, narration model, seed and inputs as the
hybrid micro arm. What does the page do when the semantic lanes are the LLM?

**Setup.** Same build, same `scenarios-independent-turns.json` + checks, seed
11, `narrationCandidate=trained&narrationMode=scene&narrationShape=prose-facts`,
**micro flags off** so targets/results/updates/continuation run through the
language model. One run, `evidence-llm-arm-scenarios-1.json`.

**Results.**
- Run: 8/8 turns completed, 0 driver problems; waits 242.7-289.8 s, mean
  **264.4 s** (max 289.8 s, next to the 300 s point limit).
- State assertions: **26/48 (54.2%)** — the failures are almost all character
  positions and item positions (movement not committed), plus task statuses.
- Task assertions: 11/14 (78.6%). Achievement checks: **0/3**, all three
  expected achievements missed; no false achievements.
- Prose-identity issues: 0.
- Hybrid micro arm on the same scenarios (E15): 48/48 state, 14/14 task, 3/3
  achievement, mean 61.9 s.

**Conditions.** One seed, one world; the LLM arm still narrates with the same
1.7B model and produces readable prose, so the gap is in semantic settlement
(movement/state commits), not narration. The arm is the in-page 0.6B LLM lane,
not the historical DeepSeek stack.

**Principle.** On identical inputs the micro workflow commits what the LLM
lane leaves uncommitted — movement and achievements — at a quarter of the
latency. The five-arm scoreboard's LLM cell now reads "slower and less
complete", which is the comparison the protocol asked for, not a narration
quality claim.

**Artifacts.** `evidence-llm-arm-scenarios-1.json`, `scenario_report.py`,
`five-arm-scoreboard.json`, D-118.
