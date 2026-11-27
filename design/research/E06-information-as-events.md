# E06 Information as events: independent annotation vs clause labels

**Question.** Is "gain new information" the same task as "pick one appearance
clause for the read verb"? What changes when the task allows 0..N items from
observation, dialogue, locations and prior events?

**Setup.** New independent pass `annotate_info_events.py` (prompt `info-v1`,
DeepSeek chat, temperature 0): input = player action + settled facts (markers
stripped) + same-turn narration + prior facts; output = `abstain` or 0..N items
`{content, mode ∈ specified|open|multi|inference, source ∈
question|dialogue|observation|location|history|cross_event, evidence quote,
novel}`. Program verification only checks that the evidence appears verbatim in
the given text, enum values, `specified` implies a question marker, and novelty
against prior turns; it never chooses content. 229 semantic turns annotated; 148
items kept, 108 rejected by the verifier.

**Results.** 102/229 turns received at least one item; 127 none; 147/148 items
novel. Modes: multi 76, open 43, specified 29, inference 0. Sources: observation
130, location 7, question 7, dialogue 4, history/cross-event 0. Cross-tab with
the old rule labels (`信息=` tag): both present 17, v2 items & old absent 85, v2
none & old present 40, both absent 87 — the two task definitions agree on 104 of
229 turns (45%). The rule marks 40 turns present that the independent annotator
finds no new information for; the annotator finds observed information in 85
turns the rule never scores. Example: opening the hatch lists ambient
observations (Nono's band, the lowered rope) rather than the hatch clause.

**Conditions.** One annotator model, single pass, one world; the verifier
rejects evidence not present verbatim (47% of proposed items); no inference
items appeared, so cross-event information is unmeasured; novelty is exact-text
against prior turns (no world seeding, no semantic same/conflict).

**Principle.** Information acquisition is not clause selection: judged as
events, most informative turns come from observation and many read turns yield
nothing new under a receiver-scoped novelty rule. A task decomposition that
fixes the output cardinality to top-1 measures the program's clause picker, not
the model's ability to understand what a character learned.

**Artifacts.** `annotate_info_events.py`, `info-events-cache.jsonl`,
`semantic-info-events-v2.jsonl`, `semantic-info-events-v2-report.json`,
D-089.
