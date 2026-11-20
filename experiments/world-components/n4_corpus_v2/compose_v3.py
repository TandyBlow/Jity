# N4 v3 target composer (N4 optimization experiment): the grouped plan is
# the same, but the target no longer emits one sentence per fact. Facts of
# the SAME entity inside a group are merged into one sentence with clause
# commas; different entities stay separate (never imply a shared action),
# and appearance/personality/no_change/time keep their own sentences.
#
# This is a target-style change, not a new fact vocabulary: every clause is
# the same recognizer-proven template as compose_v2, just joined with "，"
# instead of "。". The frozen v2 composer and its corpus stay untouched.

from compose_v2 import (  # noqa: E402
    PRONOUN, RELATION_CN, _pick, _TIME, _TIME_LEAD, compose_group_sentences,
)
from n4_render import num_cn, UNIT_CN  # noqa: E402

# clause-safe kinds: the surface starts with the subject (name/pronoun), so
# joining two such clauses with "，" reads as one sentence. Appearance /
# personality templates use the bare name and keep their own sentence.
MERGEABLE_KINDS = {"moved", "task_achieved", "sanity_changed",
                   "positioned_at", "position_relative", "slot_changed",
                   "subtask_added"}


def _non_time(facts_by_id, group):
    return [facts_by_id[fid] for fid in group["factIds"]
            if facts_by_id[fid]["kind"] != "time"]


def compose_group_v3(group, facts_by_id, variant, mentioned):
    """One group -> [sentence, ...]. Merge consecutive facts of the same
    entity when every clause is clause-safe; otherwise keep the per-fact
    sentences. The group's time is handled by compose_target_v3."""
    sents = compose_group_sentences(group, facts_by_id, variant, mentioned)
    facts = _non_time(facts_by_id, group)
    assert len(sents) == len(facts), (len(sents), len(facts))
    blocks = []
    for fact, sent in zip(facts, sents):
        eid = fact.get("entityId")
        if blocks and eid is not None and blocks[-1][0] == eid:
            blocks[-1][1].append((fact, sent))
        else:
            blocks.append((eid, [(fact, sent)]))
    pieces = []
    for _, block in blocks:
        kinds = {f["kind"] for f, _ in block}
        if len(block) >= 2 and None not in (b[0].get("entityId")
                                           for b in block) \
                and kinds <= MERGEABLE_KINDS:
            pieces.append("，".join(s.rstrip("。") for _, s in block) + "。")
        else:
            pieces.extend(s for _, s in block)
    return pieces


def compose_target_v3(plan, facts, variant=0):
    """-> merged-target text. Same time attribution as compose_v2: a leading
    time fact becomes a standalone time sentence; otherwise the time is a
    prefix on the group's first sentence."""
    facts_by_id = {f["factId"]: f for f in facts}
    sentences = []
    mentioned = set()
    for group in plan["sentences"]:
        pieces = compose_group_v3(group, facts_by_id, variant, mentioned)
        t = group.get("time")
        if t and t.get("amount") is not None:
            ts = num_cn(t["amount"]) + UNIT_CN.get(t["unit"], t["unit"])
            first_kind = (facts_by_id[group["factIds"][0]]["kind"]
                          if group["factIds"] else None)
            if first_kind == "time":
                pieces.insert(0, _pick(_TIME, variant).format(t=ts))
            else:
                lead = _pick(_TIME_LEAD, variant).format(t=ts)
                pieces[0] = lead + pieces[0]
        sentences.extend(pieces)
    return "".join(sentences)
