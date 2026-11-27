# E07 Negation/failure probes across arm definitions

**Question.** On verified failure/negation turns (expected: no event), do the
program rules, the existence head and the event annotation differ, and which
arm trades recall for false events?

**Setup.** Existing turns only, no authored golds:
`score_relation_probes.py` joins `real-semantic.jsonl` verified labels with the
raw facts (tag rule), the MiniRBT existence heads and the v2 event annotation.
Gold = the verified `target` for that field; turns without a trainable label are
dropped. Env: 54 verified successes, 3 verified failures. Info: 75 verified
successes, 3 verified failures.

**Results.** Env: rules 51/54 successes and 3/3 failures; head 51/54 and 3/3 —
identical on the verified subset. Info: rules 73/75 and 3/3; head 69/75 and 3/3.
The v2 event annotation reaches 32/75 success turns (it requires a novel item,
which many rule-positive turns do not have) and 0/3 failure turns (it lists
ambient observations on those turns: the tasks differ, not the accuracy).
Class-based gold (scenario intent) had inflated the head's recall earlier
(58/67 env, 69/104 info); with verified golds the gap disappears.

**Conditions.** Three verified failure probes per field; one world; verified
labels derived from the labeler, themselves partly rule-grounded. Authored
minimal pairs (success vs negated success) are still needed to test negation
beyond observed turns.

**Principle.** On the verified existence task no arm beats the rule; a head
trained on rule labels reproduces its decisions, including its failure
handling. Failure robustness must be measured with verified golds, not scenario
class names, and event-level annotation measures a different task (ambient
information is still information).

**Artifacts.** `score_relation_probes.py`, D-091.
