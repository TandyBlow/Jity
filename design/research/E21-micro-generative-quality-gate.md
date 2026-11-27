# E21 Micro-generative arm: measured, below its own gate

**Question.** The five-arm protocol needs the micro-generative arm in the game.
Before wiring it, what does it actually score on its held-out sets?

**Setup.** Frozen reports, no new training: `v2-report.json` (hand-authored
test set, 24 rows: 12 events, 12 conditions; four arms) and
`independent-report.json` (72 test rows held out by task and actor; 5M/15M/30M
from-scratch models, conditions and events). Exact match = the whole generated
object equals the gold; field recall = per-field hit rate.

**Results.**
- v2 arms (24 rows): scratch_pointer 0.0 exact / 0.179 recall; bert_pointer
  0.0 / 0.179; scratch_free 0.0 / 0.064; bert_free 0.042 / 0.231.
- Independent models (72 rows): conditions exact 0.067 (5M), 0.25 (15M),
  0.20 (30M), recall 0.315 / 0.417 / 0.287; events exact **0.0 at every
  scale**, recall 0.40 / 0.50 / 0.35.
- Runtime is fine (p50 30-58 ms CPU, int8 6.6-44.7 MB); the failure is output
  correctness, not speed.

**Conditions.** Hand-authored test rows with multi-field gold objects; the v3
runtime probes (`browser-v3-*.json`) show one sample's exact output but are not
a quality measurement. No arm was retrained for this record.

**Principle.** A generated event that misses half its fields cannot be
committed safely by the kernel, and 0% exact match at every scale is a hard
gate failure. Wiring this arm into the game now would violate "质量达标后接入"
and produce wrong state patches. The five-arm scoreboard's generative cell is
therefore measured-and-failing, not blank-because-unmeasured; the missing piece
is a model that clears the event gate, which is a training question (data
diversity per E16) rather than a wiring task.

**Artifacts.** `micro-generative/v2-report.json`,
`micro-generative/independent-report.json`, `browser-v3-fixed.json`,
`browser-v3-kv.json`, D-119.
