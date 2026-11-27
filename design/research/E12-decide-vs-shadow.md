# E12 Decide vs shadow on read turns: where the model's turn never comes

**Question.** On unseen read inputs, does the decide arm (existence gate →
candidate pointer → verbatim support) change state where the shadow arm only
scores, and are its decisions correct, with what inference cost?

**Setup.** Micro arm, seed 11, same build. Four generic reads
(`decide-turns-1.json`: 查看规则牌 / 读路线图 / 看短讯机 / 翻领用簿) run with
`semanticDecide=1` vs `existenceShadow=1`; four topic reads
(`decide-turns-3.json`: each names a topic with 关于/有没有) run in both arms.
The results port now logs both channels — `[world-local info] program
<entity>:<clause>` and `[world-local decide] info …` — and `decideInformation`
reports an abstain reason on every rejected path. Correctness: a logged clause
counts as corroborated when it is a verbatim substring of the read entity's
registered appearance (`score_decide_shadow.py`).

**Results.**
- Generic reads (4 turns): decide arm 0 model decisions. Abstain reasons over
  the four turns: `label` 12, `entity_count:none` 4, `no_topic` 15,
  `not_read` 25 — the decider never reaches existence or extraction. The one
  `entity_count:none` per turn is a read sub-action whose `itemIds` are empty.
- Topic reads (shadow arm, 4 turns): program channel fires 3/4 with exact
  clauses — `rules:医护白线禁射`, `map:地下检修通道用虚线标注`,
  `radio_nono:电池盖扣牢`; turn 4 (`器材领用簿`/折叠梯) has no program event.
- Topic reads (decide arm): 2 of 4 turns completed before the run was stopped
  by the host for low system memory (not a product failure); both completed
  turns match the shadow arm (1 program event, 0 model events). **Turn 4, the
  only case where the program abstains and the model could decide, was not
  measured.** Per the stop instruction the run was not restarted.

**Conditions.** Four inputs per set, one world, one seed. Correctness uses the
registered initial appearance; active appearance changes are not in the check.
The decide arm's abstains on these four turns are upstream of the models — the
read action carries no item id under the rules action analysis — so the
threshold calibration (0.75/0.6/0.15) is not exercised by this set at all.

**Principle.** The decide arm's operating range is narrower than "reads the
program misses": on generic reads it never gets an entity to decide about, and
on topic reads the program channel already fills 3/4. A model-vs-program
comparison needs inputs where the program abstains *and* the action analysis
resolves the read item; that case remains unmeasured (turn 4 stopped, the four
frozen paraphrases in `decide-turns-4.json` not yet run).

**Artifacts.** `evidence-decide-4.json` (generic decide), `evidence-info-topic-
shadow-1.json` (topic shadow), `evidence-info-topic-decide-1.json` (partial
topic decide), `decide-turns-3.json`, `decide-turns-4.json`,
`score_decide_shadow.py`, D-105.
