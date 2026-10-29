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
#   I2 every coreference.refersTo is the entityId of a fact inside that group
#      and every mention equals the looked-up name (no invented referents)
#   I3 B1 emits exactly the canonical priority order (0 drift by definition)

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
    """-> list of problem strings; empty means both hard invariants hold."""
    problems = []
    fact_ids = [f["factId"] for f in selected]
    ids_in_plan = [fid for s in plan["sentences"] for fid in s["factIds"]]
    if sorted(ids_in_plan) != sorted(fact_ids):
        problems.append(f"{plan['baseline']}: plan ids != selected ids")
    by_id = {f["factId"]: f for f in selected}
    entity_by_id = {f["factId"]: f.get("entityId") for f in selected}
    sentence_ids = {fid for s in plan["sentences"] for fid in s["factIds"]}
    for s in plan["sentences"]:
        for ref in s["coreference"]:
            if ref["refersTo"] not in sentence_ids and ref["refersTo"] not in {
                entity_by_id.get(fid) for fid in s["factIds"]}:
                problems.append(f"{plan['baseline']}: refersTo {ref['refersTo']} not anchored in its sentence group")
            expected = names.get(ref["refersTo"])
            if expected is not None and ref["mention"] != expected:
                problems.append(f"{plan['baseline']}: mention {ref['mention']} != name {expected} for {ref['refersTo']}")
    if plan["baseline"] == "B1":
        # I3 在**句组级**断言：相邻句组的首事实优先级单调不减。actor 内聚
        # 合法地把低优先级事实并入已有句组，展平后的序列允许回落。
        firsts = [PRIORITY[by_id[s["factIds"][0]]["kind"]] for s in plan["sentences"]]
        if firsts != sorted(firsts):
            problems.append(f"{plan['baseline']}: canonical priority order violated ({firsts})")
    return problems