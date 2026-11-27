# E19 Per-role guard: the model channel is measurable again

**Question.** E17 found the decide arm's only corroborated decisions came
before the topic guard, which suppressed NPC reads too. Does scoping the guard
to the protagonist restore a measurable model channel in the page?

**Setup.** Guard scoped in `decideInformation` (D-115, commit `b82f7136`),
frontend rebuilt, same four topic reads (`decide-turns-3.json`), micro arm,
seed 11, `semanticDecide=1`. The run also exercises the retrained extraction
ONNX (E16) in the page.

**Results.**
- Program channel: 1 event on turns 1-3 (`rules:医护白线禁射`,
  `map:地下检修通道用虚线标注`, `radio_nono:电池盖扣牢`), 0 on turn 4 (the
  out-of-room ledger read — the room rule still rejects it, as designed).
- Model channel: **one decision every turn**, `empty_bed:制动轮已锁`, a
  verbatim clause of the read entity's appearance — the NPC read channel that
  the guard had suppressed.
- Abstain log now shows the models being exercised: `existence` 7, `score` 4,
  `not_read` 25, `label` 12, `entity_count` 4. Before the scoping, existence
  and score never appeared.
- All four turns completed, 0 problems, waits 46.5-56.8 s.

**Conditions.** One decision per turn on the same NPC read; verbatim support
proves no invented text, not that the clause answers the NPC's question. No
shadow counterpart was re-run on this build (the program channel is unchanged
by the guard scoping).

**Principle.** The model channel's apparent zero was a policy artefact: with
the guard scoped by role, a corroborated decision appears on every turn while
the protagonist keeps the guard that removed its wrong picks. This is the
first page evidence where both channels contribute in the same run, which is
what the decide-vs-program comparison needs.

**Frozen scenarios under the decide path.** The same build ran the 8 frozen
scenarios with `semanticDecide=1`: 48/48 state, 14/14 task, 3/3 achievement
assertions, 0 prose-identity issues, mean turn 64.8 s (max 81.3 s). The
refresh-restore check passed completely — state/history/entries restored, 8/8
entries, tasks stable, 39.2 s — so the swapped extraction ONNX and the per-role
guard leave the product scenarios and local restore intact.

**Artifacts.** `evidence-decide-roles-1.json`,
`evidence-decide-scenarios-1.json`, `fact-informations.ts`, D-117.
