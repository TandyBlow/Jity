# N3 organisation-plan baselines (review round 20): B1 / B2.
#
# Interface (the contract restated in round 19): N3 consumes the SELECTED
# facts (id + content) and the viewpoint, and outputs a STRUCTURED PLAN, not
# prose:
#
#   { "baseline": "B1",
#     "sentences": [ { "index": 0, "factIds": [...],
#                      "coreference": [ { "mention": <name>, "refersTo": <entityId> } ] } ] }
#
# N4 keeps prose authority; N3 only orders, groups and suggests referents.
#
# B1 (kind-priority, actor-cohesive):
#   - priority position(moved/positioned_at) -> tasks -> personality -> sanity
#     -> appearance -> time -> no_change
#   - all facts with the same entityId join ONE sentence group
#   - coreference suggestion: the actor's NAME is the mention; within one
#     group repeated mentions stay the name (no pronouns are generated)
# B2 (plan-order, per-fact):
#   - keeps the plan's original fact order, one fact per sentence group
#
# Hard invariance (runner asserts; violation voids the archive):
#   I1 union(sentence.factIds) == selected fact ids (nothing lost/added)
#   I2 every coreference.refersTo is the entityId of a fact inside THAT
#      sentence group and every mention equals the looked-up name (no
#      invented referents, no cross-group anchoring)
#   I3 B1 emits exactly the canonical priority order (0 drift by definition)
#
# The runner's --tamper probe mutates a valid plan on purpose (cross-group
# entity / global factId / unknown entity / wrong mention / dropped fact /
# duplicated fact / fabricated factId / fabricated FIRST factId / empty
# sentence group) and asserts check_invariants catches every applicable
# case. That probe is the evidence that I1/I2 are not vacuously true.
#
# check_invariants never indexes a missing fact or an empty group: every
# invalid input is reported as a problem string, not raised as KeyError or
# IndexError.

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

PRIORITY = {
    "moved": 0, "positioned_at": 0,
    "task_achieved": 1,
    "personality_changed": 2,
    "sanity_changed": 3,
    "appearance_changed": 4,
    "time": 5,
    "no_change": 6,
}


def _coreference(group: list, names: dict) -> list:
    out = []
    for fact in group:
        entity = fact.get("entityId")
        if isinstance(entity, str) and entity:
            mention = names.get(entity, fact.get("name"))
            if mention:
                out.append({"mention": mention, "refersTo": entity})
    return out


def plan_b1(selected: list, names: dict) -> dict:
    """selected: facts (in plan order). Returns the structured plan."""
    ranked = sorted(enumerate(selected), key=lambda pair: (PRIORITY[pair[1]["kind"]], pair[0]))
    groups = []
    for _, fact in ranked:
        entity = fact.get("entityId")
        for group in groups:
            if entity and isinstance(entity, str) and any(f.get("entityId") == entity for f in group):
                group.append(fact)
                break
        else:
            groups.append([fact])
    sentences = []
    for index, group in enumerate(groups):
        sentences.append({
            "index": index,
            "factIds": [f["factId"] for f in group],
            "coreference": _coreference(group, names),
        })
    return {"baseline": "B1", "sentences": sentences,
            "note": "kind priority + actor cohesion; names only, no pronouns"}


def plan_b2(selected: list, names: dict) -> dict:
    sentences = [{
        "index": index,
        "factIds": [fact["factId"]],
        "coreference": _coreference([fact], names),
    } for index, fact in enumerate(selected)]
    return {"baseline": "B2", "sentences": sentences,
            "note": "plan order kept, one fact per sentence group"}


def check_invariants(plan: dict, selected: list, names: dict) -> list:
    """-> list of problem strings; empty means all hard invariants hold.

    I2 is anchored to the sentence group itself: a referent is legal only if
    it is the entityId of a fact INSIDE that group. The previous version
    also accepted any id present in the whole plan's factId set (a global
    `sentence_ids` set), which let a cross-group tamper pass whenever the
    forged referent happened to equal a factId from another group. The
    --tamper probe in run_n3_baselines.py pins this.
    """
    problems = []
    fact_ids = [f["factId"] for f in selected]
    ids_in_plan = [fid for s in plan["sentences"] for fid in s["factIds"]]
    if sorted(ids_in_plan) != sorted(fact_ids):
        problems.append(f"{plan['baseline']}: plan ids != selected ids")
    by_id = {f["factId"]: f for f in selected}
    for s in plan["sentences"]:
        if not s["factIds"]:
            problems.append(f"{plan['baseline']}: empty sentence group at index {s.get('index')}")
            continue
        group_entities = set()
        for fid in s["factIds"]:
            fact = by_id.get(fid)
            if fact is None:
                problems.append(f"{plan['baseline']}: unknown factId {fid} in sentence group")
                continue
            if fact.get("entityId"):
                group_entities.add(fact["entityId"])
        for ref in s["coreference"]:
            if ref["refersTo"] not in group_entities:
                problems.append(f"{plan['baseline']}: refersTo {ref['refersTo']} not anchored in its sentence group")
            expected = names.get(ref["refersTo"])
            if expected is not None and ref["mention"] != expected:
                problems.append(f"{plan['baseline']}: mention {ref['mention']} != name {expected} for {ref['refersTo']}")
    if plan["baseline"] == "B1":
        # I3 在**句组级**断言：相邻句组的首事实优先级单调不减。actor 内聚
        # 合法地把低优先级事实并入已有句组，展平后的序列允许回落。
        # 空组、捏造首编号和未知 kind 已在上方报告，这里只收集可判定的
        # 首事实；报告整体仍因已有 problem 而判违规。
        firsts = []
        for s in plan["sentences"]:
            if not s["factIds"]:
                continue
            fact = by_id.get(s["factIds"][0])
            if fact is None:
                continue
            kind = fact.get("kind")
            if kind not in PRIORITY:
                problems.append(f"{plan['baseline']}: unknown kind {kind!r} for factId {fact['factId']}")
                continue
            firsts.append(PRIORITY[kind])
        if firsts != sorted(firsts):
            problems.append(f"{plan['baseline']}: canonical priority order violated ({firsts})")
    return problems
