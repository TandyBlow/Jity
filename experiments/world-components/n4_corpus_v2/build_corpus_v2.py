# N4 v2 grouped-interface corpus builder (commit 2).
#
# Case matrix x story family -> rows {world, rawDelta, plan, facts, input,
# target, ablatedInput, meta}. The plan of EVERY row is produced by the
# pipeline's own extract_facts on a constructed point (before + after
# states built from the family registry), organised by n3_organize.plan_v3
# with the family's gender hints, and must bind CLEAN
# (narration_pipeline.bind_point_full) — the same authority discipline the
# real chain enforces, applied to every corpus row. Targets are composed by
# compose_v2 through the plan's appellation grants.
#
# SPLITS ARE BY FAMILY: train+dev rows come from families A and B; the
# frozen test set comes ONLY from family C (a world training never sees).
#
# HISTORICAL v2 CORPUS (old N1 convention): this builder generated the
# committed holdout-v2/train-v2 rows when N1 still emitted automatic
# co-presence positioned_at facts. N1 no longer scans the roster (review
# change: presence is not "noticed"), so rerunning this file now produces a
# DIFFERENT corpus. Do not overwrite the frozen v2 archive with it; a new
# corpus/freeze is a separate, pre-registered run.
# The test split is written FIRST with its freeze registration (row count,
# case coverage, sha256) — the freeze lands before any training run and the
# training corpus must not contain family C rows (asserted at build time).
#
# Isolation: every content string is scanned against B's frozen exclusion
# pool (check_isolation.py, the pinned source lists) and the old flat
# corpus files. ZERO hits is a build precondition, not a post-hoc report.

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(WC))
sys.path.insert(0, str(WC / "n4_corpus_v2"))
sys.path.insert(0, str(WC / "n2_selection"))
sys.path.insert(0, str(WC / "n4_corpus"))
sys.path.insert(0, str(WC.parent.parent / "backend"))

from app.schemas.world.contracts import WorldState  # noqa: E402
import narration_pipeline as np_  # noqa: E402
import n3_organize  # noqa: E402
import worlds_v2  # noqa: E402
from render_v2 import render_input_v2, render_input_v2_ablated  # noqa: E402
from compose_v2 import compose_target  # noqa: E402
import check_isolation as ci  # noqa: E402

_TOK = None


def real_tokens(text: str) -> int:
    """Real T5 token count incl. special tokens -- the same counting the
    product's pre-model gate performs."""
    global _TOK
    if _TOK is None:
        from transformers.models.t5.tokenization_t5 import T5Tokenizer
        _TOK = T5Tokenizer.from_pretrained(
            str(WC / "assets" / "randeng-t5-77m"), legacy=False)
    return len(_TOK(text).input_ids)


REPO = WC.parent.parent
OUT_DIR = HERE / "corpus_v2"
ART = REPO / "artifacts" / "world-components"


# ---------- family state construction ---------------------------------------

def _stored(change: dict, i: int) -> dict:
    """StoredDescriptionChange requires provenance fields; corpus history
    entries get deterministic defaults."""
    return {**change, "sourcePointId": "pt-cv2-1",
            "sourceSequence": i + 1, "active": True}


def build_state(family: dict, mutations: dict | None = None) -> dict:
    """A full WorldState (initial + live) for the family; mutations:
    {"positions": {eid: {"containerId","slotId","relativeTo"}},
     "taskStatus": {taskId: "achieved"}, "sanity": {eid: v},
     "charAppearance": {eid: [{"id","text","supersedes"}]},
     "charPersonality": {...}, "locAppearance": {locId: [...]},
     "slots": {containerId: [{"id","label"}]}}"""
    m = mutations or {}
    slots = {k: v for k, v in (m.get("slots") or {}).items()}

    def loc_slots(loc_id):
        return slots.get(loc_id) or [{"id": f"{loc_id}_s1", "label": "内格"}]

    locations = {}
    for loc in family["locations"]:
        locations[loc["id"]] = {
            "id": loc["id"], "name": loc["name"], "parentLocationId": None,
            "initialAppearance": "如常", "slots": loc_slots(loc["id"])}
    items = {}
    for item in family.get("items") or []:
        items[item["id"]] = {
            "id": item["id"], "name": item["name"],
            "initialPosition": {"containerId": item["home"], "slotId": None,
                                "relativeTo": None},
            "initialAppearance": "完好", "slots": []}
    characters = {}
    for c in family["characters"]:
        pos = (m.get("positions") or {}).get(c["id"]) or \
            {"containerId": c["home"], "slotId": None, "relativeTo": None}
        tasks = {t["id"]: {"id": t["id"], "ownerId": t["ownerId"],
                           "parentTaskId": None, "goal": t["goal"],
                           "status": "pending"}
                 for t in c["tasks"]}
        for t in (m.get("extraTasks") or {}).get(c["id"]) or []:
            tasks[t["id"]] = {"id": t["id"], "ownerId": t["ownerId"],
                              "parentTaskId": None, "goal": t["goal"],
                              "status": t.get("status", "pending")}
        characters[c["id"]] = {
            "id": c["id"], "name": c["name"], "initialPosition": pos,
            "initialAppearance": "如常",
            "initialPersonality": c["personality"],
            "initialSanity": c["sanity"],
            "tasks": tasks}
    ws = WorldState.model_validate({
        "engineVersion": "world-engine-v1", "schemaVersion": 1,
        "worldId": family["familyId"],
        "protagonistId": family["protagonistId"],
        "time": {"calendar": "gregorian",
                 "dateTime": "2026-11-02T00:00:00", "instantOrdinal": 2},
        "initial": {
            "engineVersion": "world-engine-v1", "schemaVersion": 1,
            "worldId": family["familyId"],
            "protagonistId": family["protagonistId"],
            "initialTime": {"calendar": "gregorian",
                            "dateTime": "2026-11-02T00:00:00",
                            "instantOrdinal": 1},
            "locations": locations, "items": items, "characters": characters,
        },
        "locations": {k: {"id": k,
                          "appearanceChanges": [
                              _stored(c, i) for i, c in
                              enumerate((m.get("locAppearance") or {})
                                        .get(k) or [])]}
                      for k in locations},
        "items": {k: {"id": k,
                      "position": (m.get("positions") or {}).get(k)
                      or {"containerId": items[k]["initialPosition"]["containerId"],
                          "slotId": None, "relativeTo": None},
                      "appearanceChanges": []}
                  for k in items},
        "characters": {k: {
            "id": k, "position": characters[k]["initialPosition"],
            "appearanceChanges": [
                _stored(c, i) for i, c in
                enumerate((m.get("charAppearance") or {}).get(k) or [])],
            "personalityChanges": [
                _stored(c, i) for i, c in
                enumerate((m.get("charPersonality") or {}).get(k) or [])],
            "sanity": (m.get("sanity") or {}).get(k, characters[k]["initialSanity"]),
            "tasks": characters[k]["tasks"]}
            for k in characters},
    })
    st = ws.model_dump(mode="json")
    # apply task status mutations to the live side
    for tid, status in (m.get("taskStatus") or {}).items():
        for eid, ent in st["characters"].items():
            if tid in (ent.get("tasks") or {}):
                ent["tasks"][tid]["status"] = status
    return st


def delta_for(eid, **kw):
    d = {"entityId": eid, "positionSet": kw.get("positionSet"),
         "appearanceChanges": kw.get("appearanceChanges") or [],
         "personalityChanges": kw.get("personalityChanges") or [],
         "subtasksAdded": kw.get("subtasksAdded") or [],
         "tasksAchieved": kw.get("tasksAchieved") or [],
         "sanitySet": kw.get("sanitySet")}
    return d


def make_point(before_state, after_state, deltas, amount, unit="minute",
               version=2):
    ta = None if amount is None else {"boundary": "elapsed",
                                      "duration": {"amount": amount,
                                                   "unit": unit}}
    return {"pointId": "pt-cv2", "version": version, "state": after_state,
            "stateDigest": "d" * 8, "previousPointId": "pt-cv2-1",
            "timeAdvance": ta, "entityDeltas": deltas}


def names_of(family):
    out = {c["id"]: c["name"] for c in family["characters"]}
    out.update({i["id"]: i["name"] for i in family.get("items") or []})
    out.update({l["id"]: l["name"] for l in family["locations"]})
    return out


def build_row(family, case, split, mut, before_mut, deltas, amount,
              unit="minute", variant=0, fact_order=None):
    """One corpus row through the REAL chain: extract -> organise ->
    render -> compose, with a clean binding as the authority check.
    fact_order optionally reorders the extracted facts before planning
    (the plan is order-sensitive by design; sources stay bound)."""
    before_state = build_state(family, before_mut)
    after_state = build_state(family, mut)
    before = {**make_point(None, before_state, {}, None),
              "pointId": "pt-cv2-1", "version": 1}
    point = make_point(before_state, after_state, deltas, amount, unit)
    n1 = np_.extract_facts(point, before)
    if n1["diagnostics"]:
        raise AssertionError(f"{case}: extraction diagnostics "
                             f"{n1['diagnostics']}")
    problems = np_.bind_point_full(point, before, n1["facts"])
    if problems:
        raise AssertionError(f"{case}: binding problems {problems}")
    facts = n1["facts"]
    if fact_order is not None:
        facts = fact_order(facts)
    names = names_of(family)
    hints = worlds_v2.gender_hints(family)
    plan = n3_organize.plan_v3(facts, names, hints)
    if "refusal" in plan:
        raise AssertionError(f"{case}: planner refusal {plan['refusal']}")
    problems = n3_organize.check_plan_v3(plan, facts, names, hints)
    if problems:
        raise AssertionError(f"{case}: plan invariant violations {problems}")
    target = compose_target(plan, facts, variant)
    input_text = render_input_v2(plan, facts)
    n_tok = real_tokens(input_text)
    if n_tok > 128:
        # the product gate refuses model calls over 128 REAL tokens; a row
        # the gate would refuse can never flow at runtime, so it must not
        # enter the corpus (the builder reports the skip count)
        return None
    return {
        "rowId": f"{family['familyId']}:{case}:v{variant}",
        "sourceGroupId": f"v2-{family['familyId']}-{case}",
        "rowOrigin": "program-case-matrix-v2",
        "task": "n4-sentence-v2",
        "split": split,
        "familyId": family["familyId"],
        "world": {"familyId": family["familyId"],
                  "names": sorted(set(names.values()))},
        "rawDelta": {"entityDeltas": deltas,
                     "time": ({"amount": amount, "unit": unit}
                              if amount is not None else None)},
        "plan": plan, "facts": facts,
        "input": input_text,
        "inputRealTokens": n_tok,
        "ablatedInput": render_input_v2_ablated(plan, facts),
        "text": target,
        "mustExpress": [f["factId"] for f in facts],
        "pronounElicited": any(g.get("pronoun")
                               for s in plan["sentences"]
                               for g in s["coreference"]),
        "genderHints": hints,
        "hashes": {"facts": hashlib.sha256(
            json.dumps(facts, ensure_ascii=False, sort_keys=True)
            .encode("utf-8")).hexdigest()},
    }


def _reorder_time(facts, position):
    """Move the time fact so its input position lands it in the intended
    group (R3 attaches time to the input-order predecessor)."""
    time_f = next((f for f in facts if f["kind"] == "time"), None)
    rest = [f for f in facts if f["kind"] != "time"]
    if time_f is None or position == "tail":
        return facts
    if position == "lead":
        return [time_f] + rest
    return rest[:1] + [time_f] + rest[1:]


def cases_for(family, variants=None):
    """Yield (case, mut, before_mut, deltas, amount, unit, variant,
    fact_order). variants=None keeps every surface variant; the frozen
    test family passes {0}."""
    keep = (lambda v: v in variants) if variants is not None \
        else (lambda v: True)
    prot = family["protagonistId"]
    prot_c = next(c for c in family["characters"] if c["id"] == prot)
    other = next(c for c in family["characters"] if c["id"] != prot)
    unknown = next(c for c in family["characters"] if c["gender"] == "unknown")
    dup = [c for c in family["characters"]
           if sum(1 for x in family["characters"]
                  if x["name"] == c["name"]) > 1]
    dup_a, dup_b = dup[0], dup[1]
    locs = [l["id"] for l in family["locations"]]
    other_loc = next(l for l in locs if l != prot_c["home"])
    third_loc = next(l for l in locs
                     if l not in (prot_c["home"], other["home"], other_loc))
    items_homes = {i["home"] for i in family.get("items") or []}
    nondup = [c for c in family["characters"]
              if sum(1 for x in family["characters"]
                     if x["name"] == c["name"]) == 1]
    # the helper needs an item-free (or <=1-item) home because the
    # protagonist moves there; it need not have a unique name -- a helper
    # with a duplicated name simply never receives a pronoun grant
    helpers = [c for c in family["characters"]
               if sum(1 for i in family.get("items") or []
                      if i["home"] == c["home"]) <= 1
               and c["id"] != prot and c["id"] != unknown["id"] and c["tasks"]]
    helper = helpers[0]
    # helper2 only LEAVES its home for the protagonist's (item-free) home,
    # so its own home may keep items
    # helper2 may carry a duplicate name: it only contributes a move to
    # the protagonist's (item-free) home, and a duplicated name is never
    # granted a pronoun anyway
    helper2 = next(c for c in family["characters"]
                   if c["id"] not in (prot, helper["id"], unknown["id"])
                   and c["tasks"])
    # helper2's destination must not be its own home (a no-op position)
    helper2_dest = prot_c["home"] if helper2["home"] != prot_c["home"]         else helper["home"]
    t1 = prot_c["tasks"][0]
    t2 = prot_c["tasks"][1] if len(prot_c["tasks"]) > 1 else prot_c["tasks"][0]

    def pos(cid, container, slot=None, rel=None):
        return {"containerId": container, "slotId": slot, "relativeTo": rel}

    out = []
    add = out.append
    # 1 core: move + task in one group, time attached -- swept over every
    # character, every legal destination and durations so the model sees
    # the whole roster, not just the protagonist
    for c in family["characters"]:
        c_tasks = c["tasks"]
        if not c_tasks:
            continue
        for dest in locs:
            if dest == c["home"]:
                continue
            for dur, unit, variant in ((5, "minute", 0), (12, "minute", 1),
                                       (1, "hour", 2), (40, "second", 1),
                                       (3, "minute", 0), (15, "minute", 2),
                                       (2, "hour", 1), (90, "second", 2)):
                if not keep(variant):
                    continue
                add((f"core-move-task-{c['id']}-{dest}-{dur}{unit}",
                     {"positions": {c["id"]: pos(c["id"], dest)},
                      "taskStatus": {c_tasks[0]["id"]: "achieved"}},
                     {},
                     {c["id"]: delta_for(c["id"],
                                         positionSet=pos(c["id"], dest),
                                         tasksAchieved=[c_tasks[0]["id"]])},
                     dur, unit, variant, None))
    # 2 cross-sentence reference: one entity's facts share ONE bucket, so
    # the cross-sentence shape uses a second entity as the middle group:
    # A moves (g1), B achieves a task (g2), A sanity (g3) -- A's bucket
    # spans g1+g3 and the pronoun is granted in g3 (antecedent in g1)
    for variant in (0, 1, 2):
        for dur, unit in ((8, "minute"), (15, "minute"), (2, "hour")):
            if not keep(variant) or (variants is not None and dur != 8):
                continue
            mut = {"positions": {prot: pos(prot, helper["home"]),
                                 helper["id"]: pos(helper["id"], helper["home"])},
                   "taskStatus": {helper["tasks"][0]["id"]: "achieved"},
                   "sanity": {prot: 14}}
            add((f"cross-reference-{dur}{unit}", mut, {},
                 {prot: delta_for(prot, positionSet=pos(prot, helper["home"]),
                                  sanitySet=14),
                  helper["id"]: delta_for(helper["id"],
                                          tasksAchieved=[helper["tasks"][0]["id"]])},
                 dur, unit, variant, None))
    # 3 two-person alternation: A move / B task / A sanity / B move
    for variant in (0, 1):
        for dur, unit in ((6, "minute"), (20, "minute")):
            if not keep(variant) or (variants is not None and dur != 6):
                continue
            mut = {"positions": {prot: pos(prot, helper["home"]),
                                 helper["id"]: pos(helper["id"], helper["home"]),
                                 helper2["id"]: pos(helper2["id"], helper2_dest)},
                   "taskStatus": {helper["tasks"][0]["id"]: "achieved"}}
            add((f"alternating-{dur}{unit}", mut, {},
                 {prot: delta_for(prot, positionSet=pos(prot, helper["home"])),
                  helper["id"]: delta_for(helper["id"],
                                          tasksAchieved=[helper["tasks"][0]["id"]]),
                  helper2["id"]: delta_for(
                      helper2["id"], positionSet=pos(helper2["id"], helper2_dest))},
                 dur, unit, variant, None))
    # 4 same-name pair: distinct goals, two groups, names only
    for variant in (0, 1):
        if not keep(variant):
            continue
        mut = {"taskStatus": {dup_a["tasks"][0]["id"]: "achieved",
                              dup_b["tasks"][0]["id"]: "achieved"}}
        add(("same-name", mut, {},
             {dup_a["id"]: delta_for(dup_a["id"],
                                     tasksAchieved=[dup_a["tasks"][0]["id"]]),
              dup_b["id"]: delta_for(dup_b["id"],
                                     tasksAchieved=[dup_b["tasks"][0]["id"]])},
             4, "minute", variant, None))
    # 5 gender-unknown entity: [move] [task] -> TA from the second group
    for variant in (0, 1):
        for dur, unit in ((7, "minute"), (25, "minute")):
            if not keep(variant) or (variants is not None and dur != 7):
                continue
            mut = {"positions": {unknown["id"]: pos(unknown["id"], helper["home"]),
                                 helper["id"]: pos(helper["id"], helper["home"])},
                   "taskStatus": {unknown["tasks"][0]["id"]: "achieved"}}
            add((f"gender-unknown-{dur}{unit}", mut, {},
                 {unknown["id"]: delta_for(
                     unknown["id"], positionSet=pos(unknown["id"], helper["home"]),
                     tasksAchieved=[unknown["tasks"][0]["id"]])},
                 dur, unit, variant, None))
    # 6 pronoun conflict: two same-gender entities with the SAME goal text
    # (registered to both) -> union-find merges -> R2b splits -> names for
    # both; the ambiguity is resolved by the rule, never by guessing
    shared_goal = "合力抬盐包"
    mut = {"extraTasks": {
        dup_a["id"]: [{"id": f"{dup_a['id']}_shared", "ownerId": dup_a["id"],
                       "parentTaskId": None, "goal": shared_goal,
                       "status": "achieved"}],
        dup_b["id"]: [{"id": f"{dup_b['id']}_shared", "ownerId": dup_b["id"],
                       "parentTaskId": None, "goal": shared_goal,
                       "status": "achieved"}]}}
    add(("conflict-shared-goal", mut, {},
         {dup_a["id"]: delta_for(dup_a["id"],
                                 tasksAchieved=[f"{dup_a['id']}_shared"]),
          dup_b["id"]: delta_for(dup_b["id"],
                                 tasksAchieved=[f"{dup_b['id']}_shared"])},
         3, "minute", 0, None))
    # 7 time position: two entity groups, the time fact reordered so R3
    # lands it at the lead/middle/tail slot
    base_mut = {"positions": {prot: pos(prot, other_loc),
                              other["id"]: pos(other["id"], third_loc)},
                "taskStatus": {other["tasks"][0]["id"]: "achieved"}}
    base_d = {prot: delta_for(prot, positionSet=pos(prot, other_loc)),
              other["id"]: delta_for(other["id"],
                                     tasksAchieved=[other["tasks"][0]["id"]])}
    carriers = [c for c in (helper, helper2)
                if c["home"] != prot_c["home"] and c["tasks"]]
    for tag, order_name in (("time-lead", "lead"), ("time-mid", "mid"),
                            ("time-tail", "tail")):
        for dur, carrier in zip((9, 25, 3), carriers):
            mut = {"positions": {prot: pos(prot, carrier["home"]),
                                 carrier["id"]: pos(carrier["id"],
                                                    carrier["home"])},
                   "taskStatus": {carrier["tasks"][0]["id"]: "achieved"}}
            d = {prot: delta_for(prot, positionSet=pos(prot, carrier["home"])),
                 carrier["id"]: delta_for(
                     carrier["id"],
                     tasksAchieved=[carrier["tasks"][0]["id"]])}
            add((f"{tag}-{dur}{unit if False else ''}".rstrip("-"),
                 mut, {}, d, dur, "minute", 0,
                 (lambda facts, o=order_name: _reorder_time(facts, o))))
    # 8 group order: swap the input order of the two entity blocks
    for variant in (0, 1):
        if not keep(variant):
            continue
        mut = {"positions": {helper["id"]: pos(helper["id"], prot_c["home"]),
                             prot: pos(prot, prot_c["home"])},
               "taskStatus": {t2["id"]: "achieved"}}
        add((f"group-order-{variant}", mut, {},
             {helper["id"]: delta_for(
                 helper["id"], positionSet=pos(helper["id"], prot_c["home"])),
              prot: delta_for(prot, tasksAchieved=[t2["id"]])},
             5, "minute", variant, None))
    # 7b four-entity alternation: the deepest cross-group pronoun
    # discipline stress (each entity exactly one group, grants 他/她/TA/名)
    chars4 = [prot_c] + [c for c in family["characters"]
                         if c["id"] not in (prot,)] [:3]
    if len(chars4) == 4 and all(c["tasks"] for c in chars4):
        mut = {"positions": {chars4[0]["id"]: pos(chars4[0]["id"], helper["home"]),
                             chars4[2]["id"]: pos(chars4[2]["id"], chars4[0]["home"])},
               "taskStatus": {chars4[1]["tasks"][0]["id"]: "achieved",
                              chars4[3]["tasks"][0]["id"]: "achieved"}}
        d4e = {chars4[0]["id"]: delta_for(
                   chars4[0]["id"], positionSet=pos(chars4[0]["id"], helper["home"])),
               chars4[1]["id"]: delta_for(
                   chars4[1]["id"], tasksAchieved=[chars4[1]["tasks"][0]["id"]]),
               chars4[2]["id"]: delta_for(
                   chars4[2]["id"], positionSet=pos(chars4[2]["id"], chars4[0]["home"])),
               chars4[3]["id"]: delta_for(
                   chars4[3]["id"], tasksAchieved=[chars4[3]["tasks"][0]["id"]])}
        add(("alternating-4", mut, {}, d4e, 12, "minute", 0, None))
    # 8b personality add/modify/remove (a frozen kind the matrix missed)
    pe_a = {"id": "pe_v2a", "text": "变得缄默", "supersedes": []}
    pe_b = {"id": "pe_v2b", "text": "话多起来", "supersedes": ["pe_v2a"]}
    pe_c = {"id": "pe_v2c", "text": None, "supersedes": ["pe_v2b"]}
    add(("personality-add",
         {"charPersonality": {prot: [pe_a]}},
         {},
         {prot: delta_for(prot, personalityChanges=[pe_a])},
         5, "minute", 0, None))
    add(("personality-modify",
         {"charPersonality": {prot: [pe_a, pe_b]}},
         {"charPersonality": {prot: [pe_a]}},
         {prot: delta_for(prot, personalityChanges=[pe_b])},
         5, "minute", 0, None))
    add(("personality-remove",
         {"charPersonality": {prot: [pe_a, pe_b, pe_c]}},
         {"charPersonality": {prot: [pe_a, pe_b]}},
         {prot: delta_for(prot, personalityChanges=[pe_c])},
         5, "minute", 0, None))
    # 9 new vocabulary kinds (relative position, slot, subtask, appearance)
    rel_after = {"containerId": prot_c["home"], "slotId": None,
                 "relativeTo": {"entityId": other["id"], "relation": "beside"}}
    add(("new-relative",
         {"positions": {prot: rel_after,
                        other["id"]: pos(other["id"], prot_c["home"])}},
         {}, {prot: delta_for(prot, positionSet=rel_after)},
         2, "minute", 0, None))
    add(("new-slot",
         {"positions": {prot: {"containerId": prot_c["home"],
                               "slotId": f"{prot_c['home']}_s1",
                               "relativeTo": None}}},
         {}, {prot: delta_for(prot, positionSet={
             "containerId": prot_c["home"], "slotId": f"{prot_c['home']}_s1",
             "relativeTo": None})}, 2, "minute", 0, None))
    sub = {"id": "sub_v2", "ownerId": prot, "parentTaskId": t1["id"],
           "goal": "先借到长梯", "status": "pending"}
    add(("new-subtask", {"taskStatus": {t1["id"]: "achieved"}}, {},
         {prot: delta_for(prot, tasksAchieved=[t1["id"]],
                          subtasksAdded=[sub])}, 3, "minute", 0, None))
    ch_a = {"id": "ch_v2a", "text": "肩头被盐渍蚀出了白痕", "supersedes": []}
    ch_b = {"id": "ch_v2b", "text": "换上了蓑衣", "supersedes": ["ch_v2a"]}
    ch_c = {"id": "ch_v2c", "text": None, "supersedes": ["ch_v2b"]}
    add(("appearance-modify",
         {"charAppearance": {prot: [ch_a, ch_b]}},
         {"charAppearance": {prot: [ch_a]}},
         {prot: delta_for(prot, appearanceChanges=[ch_b])},
         4, "minute", 0, None))
    add(("appearance-remove",
         {"charAppearance": {prot: [ch_a, ch_b, ch_c]}},
         {"charAppearance": {prot: [ch_a, ch_b]}},
         {prot: delta_for(prot, appearanceChanges=[ch_c])},
         4, "minute", 0, None))
    # 10 co-presence positioned_at
    for variant in (0, 1):
        if not keep(variant):
            continue
        mut = {"positions": {prot: pos(prot, other["home"]),
                             other["id"]: pos(other["id"], other["home"])}}
        add(("co-presence", mut, {},
             {prot: delta_for(prot, positionSet=pos(prot, other["home"]))},
             5, "minute", variant, None))
    # 11 no change (global no_change + time in one group); family B uses
    # different durations so the name-free rows stay byte-distinct
    nc_durs = (0, 10) if family is worlds_v2.FAMILIES["train_a"] or         family is worlds_v2.FAMILIES["test_c"] else (5, 20)
    for dur in nc_durs:
        add((f"no-change-{dur}", {}, {}, {}, dur, "minute", 0, None))
    # 12 location scenery
    for li in (1, 2):
        ch = {"id": f"chl{li}", "text": "檐下的灯笼蒙了层盐霜",
              "supersedes": []}
        add((f"loc-appearance-{li}", {"locAppearance": {locs[li]: [ch]}}, {},
             {locs[li]: delta_for(locs[li], appearanceChanges=[ch])},
             6, "minute", 0, None))
    return out


def main() -> int:
    rows, skipped = [], {}
    for split_key, variants in (("train_a", None), ("train_b", None),
                                ("test_c", {0})):
        family = worlds_v2.FAMILIES[split_key]
        split = "test" if split_key == "test_c" else "train"
        for case, mut, before_mut, deltas, amount, unit, variant, order in \
                cases_for(family, variants):
            row = build_row(family, case, split, mut, before_mut,
                            deltas, amount, unit, variant, order)
            if row is None:
                skipped[case] = skipped.get(case, 0) + 1
                continue
            rows.append(row)
    train = [r for r in rows if r["split"] == "train"]
    for i, r in enumerate(sorted(train, key=lambda r: r["rowId"])):
        r["split"] = "dev" if i % 6 == 5 else "train"
    test = [r for r in rows if r["split"] == "test"]

    OUT_DIR.mkdir(exist_ok=True)
    test_path = OUT_DIR / "holdout-v2.jsonl"
    test_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in test),
        encoding="utf-8", newline="\n")
    test_sha = hashlib.sha256(test_path.read_bytes()).hexdigest()
    freeze = {
        "freeze": "n4-v2-holdout (commit 2) -- frozen BEFORE any v2 "
                  "training run; the training corpus asserts zero family-C "
                  "rows",
        "file": "holdout-v2.jsonl", "rows": len(test),
        "caseCoverage": sorted({r["rowId"].split(":")[1] for r in test}),
        "familyId": worlds_v2.FAMILY_C["familyId"],
        "sha256": test_sha,
        "criteria": "see eval_n4_v2.py header (pre-registered there; the "
                    "pronoun threshold is fixed on the train-family dev "
                    "split before the test eval)",
    }
    (OUT_DIR / "holdout-v2-freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")

    train_rows = [r for r in rows if r["split"] in ("train", "dev")]
    assert not any(r["familyId"] == worlds_v2.FAMILY_C["familyId"]
                   for r in train_rows), "family C leaked into training"
    train_path = OUT_DIR / "train-v2.jsonl"
    train_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in train_rows),
        encoding="utf-8", newline="\n")

    # ---- isolation: zero hits against B's frozen pool + the old corpus ---
    pool, _manifest, missing, _details = ci.collect_live()
    old_strings = set()
    for f in ("corpus.seeds.jsonl", "rewrites.jsonl"):
        for line in (HERE.parent / "n4_corpus" / f).read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                for e in d.get("plan") or []:
                    for k in ("name", "from", "to", "goal", "text", "at"):
                        v = e.get(k)
                        if isinstance(v, str) and len(v) >= 2:
                            old_strings.add(v)
                w = d.get("world") or {}
                for c in w.get("characters") or []:
                    old_strings.add(c["name"])
                for l in w.get("locations") or []:
                    old_strings.add(l["name"])
    new_strings = set()
    for r in rows:
        for f in r["facts"]:
            for k in ("name", "from", "to", "goal", "text", "at",
                      "targetName", "slotLabel", "parentGoal"):
                v = f.get(k)
                if isinstance(v, str) and len(v) >= 2:
                    new_strings.add(v)
    b_hits = ci.match_hits(pool, {s: ["v2"] for s in new_strings})
    old_hits = {s: "old-corpus" for s in new_strings if s in old_strings}
    ok = (not b_hits) and (not old_hits) and not missing
    report = {"rows": {"train": sum(1 for r in train_rows
                                    if r["split"] == "train"),
                       "dev": sum(1 for r in train_rows
                                  if r["split"] == "dev"),
                       "test": len(test)},
              "caseCoverage": sorted({r["rowId"].split(":")[1] for r in rows}),
              "isolation": {"poolStrings": len(pool),
                            "missingSources": missing,
                            "bPoolHits": b_hits, "oldCorpusHits": old_hits},
              "isolationOk": ok, "freeze": freeze,
              "skippedOver128Tokens": skipped}
    (ART / "n4-v2-corpus-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in report.items() if k != "isolation"},
                     ensure_ascii=False, indent=1))
    iso = report["isolation"]
    print("isolation:", "ZERO-HIT" if ok else json.dumps(iso,
                                                         ensure_ascii=False)[:400])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())


