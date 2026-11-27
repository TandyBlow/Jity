# E17 The decide arm's only measured increments predate the topic guard

**Question.** D-114 says the extraction dataset cannot show the model's added
value because it is built from program successes. Do any page runs contain
model decisions on reads the program missed, and do they hold up?

**Setup.** By construction `decidedInfo` is computed only when `programInfo` is
null, so every `[world-local decide] info` line is a decision on a
program-missed read. The pre-guard decide evidence (2026-11-26,
`evidence-decide-1/2.json`, four generic reads each) is parsed and each clause
is checked verbatim against the read entity's registered appearance.

**Results.**
- Three distinct model decisions, every clause verbatim from the entity's
  appearance: `empty_bed:制动轮已锁`, `water:杯沿未破`,
  `rules:15:45停赛`. They repeat across turns and inputs — other actors' reads
  in the same rounds, not the protagonist's.
- The later runs (after the interrogative/topic guard, D-087) show zero model
  decisions on the same generic reads: the guard rejects them for every member
  before the decider runs.

**Conditions.** Three decisions, no independent semantics — corroboration is
"verbatim slice of the committed appearance", which proves the model did not
invent text, not that the chosen clause answers the read. The pre-guard runs
also produced wrong choices on the protagonist's generic reads (that is why
the guard exists). No run isolates the protagonist from NPCs under the guard.

**Principle.** The decide arm's measured increment is currently zero by policy,
not by capability: the guard that removed its wrong picks on generic
protagonist reads also removed its correct picks on NPC reads. The next
measurement is per-role: keep the guard for the protagonist's topicless reads,
let NPC reads reach the decider, and score both channels from the same run.
That comparison, not another threshold sweep, decides whether the model
channel earns a place in the product.

**Implementation.** The guard is now scoped to the protagonist
(`decideInformation` checks `memberId` against `state.protagonistId`); a unit
test covers both sides — the protagonist's topicless read still abstains, an
NPC's topicless read reaches the decider and takes the confident verbatim
clause. Full suite 1460 passed. The page measurement (both channels in one
run) still needs the acceptance lane.

**Artifacts.** `evidence-decide-1.json`, `evidence-decide-2.json`,
`score_decide_shadow.py`, `fact-informations.ts`, D-115.
