"""Turn the committed fresh fixture cases into a reviewable candidate pack.

Pack version 3 (after the 2026-11-08 second external review). The two changes
that matter:

  1. Exclusion checks (R1 text, R2 vocabulary, R3 signature) run on the FULL
     change set of the point's raw delta, never on what the model was asked to
     say. A separate `expressionSignature` records the spoken subset for
     narration analysis.

  2. Which facts reach the model is decided by the real N2 rule
     (experiments/world-components/n2_perspective.py, imported read-only), not
     by hand-written per-case guesses: `resolve_perspective` derives the
     viewpoint from the committed state, `classify_facts` marks every fact
     must / may / invisible with a visibility ground. Invisible facts stay in
     `answer.json` (the checking key) and are absent from `input.json`.

The only non-N2 scope rule left is the player instruction in c8e06, which
defers an entity: that is applied after N2, labelled `player-instruction`, and
recorded as a scope decision rather than a visibility decision.

Per case, under candidates-fresh/<id>/:
  facts.json     raw delta, change facts (both ends, ids and names), standing
  answer.json    the full N1 fact set + every N2 decision + withheld facts
  input.json     exactly what a narration model would receive
  screening.json R1 v1/v2, R2 (new-world), R3 on the full change set
  checks.md      four capability stages, withheld facts, human review items

No model is called; no production code is touched.

Usage: python artifacts/world-components/fresh-eval/tools/build_candidates_fresh.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
REPO = OUT.parents[2]
SRC = OUT / "fresh/source"
DEST = OUT / "candidates-fresh"
NL = chr(10)
PACK_VERSION = 3
N2_PATH = REPO / "experiments/world-components/n2_perspective.py"

_screening_spec = importlib.util.spec_from_file_location("screening", HERE / "screening.py")
screening = importlib.util.module_from_spec(_screening_spec)
_screening_spec.loader.exec_module(screening)

_n2_spec = importlib.util.spec_from_file_location("n2_perspective", N2_PATH)
n2 = importlib.util.module_from_spec(_n2_spec)
_n2_spec.loader.exec_module(n2)

# Player-scope rule (NOT a visibility rule): a player instruction can decline to
# expand an entity for this point. Applied after N2, so it never weakens a
# visibility judgment.
# Scenario salience (design intent, NOT visibility): visible facts this item
# asks the model to express even though N2 rates them `may`. Invisible facts can
# never be promoted by this list.
REQUIRE = {
    "c8e03": ["fe_wen:personality"],
    "c8e04": ["fi_gauge:position"],
    "c8e05": ["fi_seal:position", "fi_seal:appearance"],
}

PLAYER_SCOPE = {"c8e06": {"deferred": ["fe_wen"],
                          "constraint": ("玩家指令要求本轮暂不展开该角色：不进入成句输入；"
                                         "不得据此推出关注对象或任务达成。")}}

SCOPE_NOTES = {
    "c8e01": "三条都是普通人物位移，页面路径能全部写出；不覆盖限知与物品。",
    "c8e02": ("限知由 N2 规则判定：远处移动被标为 invisible/other-location，"
              "不进入成句输入。页面叙事路径本身不做视角过滤，所以本条不计页面叙述成绩。"),
    "c8e03": ("视角人物的任务、理智、人格与本点移动是必述；聂汀穗的移动被 N2 判为 may"
              "（同院可见），可写可省。不覆盖“父达成/子未达成”的情形。"),
    "c8e04": ("空间相对位置（beside）只在夹具与内核层成立；页面投影拒绝该形状。"
              "物品位移被 N2 判为 may，省略不扣分。"),
    "c8e05": ("持有转移与外貌变化都在物品上；页面投影既不接受物品位移，也不接受外貌变化。"
              "两条都被 N2 判为 may，只在模型写到时判正确性。"),
    "c8e06": ("玩家关注是本次作者编写的合成指令，不是真实玩家原话；只核关注解析，"
              "不称 N2 已支持该功能。被指令推迟的移动不进成句输入。"),
}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: pathlib.Path, text: str) -> None:
    screening.write_artifact(path, text)


def names_index(state):
    index = {}
    for bucket in ("characters", "locations", "items"):
        for eid, entry in state["state"]["initial"].get(bucket, {}).items():
            index[eid] = entry["name"]
    return index


def kind_of(eid, state):
    for bucket, label in (("characters", "character"), ("locations", "location"),
                          ("items", "item")):
        if eid in state["state"]["initial"].get(bucket, {}):
            return label
    return "unknown"


def derive(before, after):
    """This point's change facts and standing references, with ids and names."""
    names = names_index(after)
    changes, standing = [], []

    def ref(container_id):
        return container_id, names.get(container_id, container_id)

    for eid in sorted(after["state"]["characters"]):
        cur = after["state"]["characters"][eid]
        prev = before["state"]["characters"][eid]
        name = names.get(eid, eid)
        if cur["position"] != prev["position"]:
            from_id, from_name = ref(prev["position"]["containerId"])
            to_id, to_name = ref(cur["position"]["containerId"])
            rel = cur["position"].get("relativeTo")
            changes.append({
                "kind": "moved", "phase": "change", "entityId": eid, "actor": eid,
                "actorKind": "character", "name": name,
                "fromId": from_id, "from": from_name,
                "toId": to_id, "to": to_name,
                "relativeTo": ({"entityId": rel["entityId"],
                                "name": names.get(rel["entityId"], rel["entityId"]),
                                "relation": rel["relation"]} if rel else None),
                "fieldPath": f"state.characters.{eid}.position"})
        else:
            loc_id = cur["position"]["containerId"]
            standing.append({"kind": "at", "phase": "standing", "entityId": eid,
                             "actor": eid, "name": name,
                             "locationId": loc_id,
                             "location": names.get(loc_id, loc_id),
                             "fieldPath": f"state.characters.{eid}.position"})
        if cur["sanity"] != prev["sanity"]:
            changes.append({"kind": "sanity_changed", "phase": "change",
                            "entityId": eid, "actor": eid, "name": name,
                            "from": prev["sanity"], "to": cur["sanity"],
                            "fieldPath": f"state.characters.{eid}.sanity"})
        else:
            standing.append({"kind": "sanity", "phase": "standing", "entityId": eid,
                             "actor": eid, "name": name, "value": cur["sanity"],
                             "fieldPath": f"state.characters.{eid}.sanity"})
        for tid, task in sorted(cur["tasks"].items()):
            if prev["tasks"][tid]["status"] != task["status"]:
                changes.append({"kind": "task_achieved", "phase": "change",
                                "entityId": eid, "actor": eid, "name": name,
                                "taskId": tid, "goal": task["goal"],
                                "status": task["status"],
                                "fieldPath": f"state.characters.{eid}.tasks.{tid}.status"})
            elif task["status"] == "pending":
                standing.append({"kind": "task_pending", "phase": "standing",
                                 "entityId": eid, "actor": eid, "name": name,
                                 "taskId": tid, "goal": task["goal"],
                                 "fieldPath": f"state.characters.{eid}.tasks.{tid}.status"})
        before_ids = {c["id"] for c in prev["personalityChanges"]}
        for change in cur["personalityChanges"]:
            if change["id"] not in before_ids and change.get("active"):
                changes.append({"kind": "personality_changed", "phase": "change",
                                "entityId": eid, "actor": eid, "name": name,
                                "text": change["text"],
                                "fieldPath": f"state.characters.{eid}.personalityChanges"})

    for bucket in ("items", "locations"):
        for eid in sorted(after["state"][bucket]):
            cur, prev = after["state"][bucket][eid], before["state"][bucket][eid]
            if bucket == "locations":
                new = [c for c in cur["appearanceChanges"]
                       if c["id"] not in {p["id"] for p in prev["appearanceChanges"]}]
                for change in new:
                    changes.append({"kind": "appearance_changed", "phase": "change",
                                    "entityId": eid, "actor": eid,
                                    "actorKind": "location",
                                    "name": names.get(eid, eid),
                                    "text": change.get("text"),
                                    "fieldPath": f"state.locations.{eid}.appearanceChanges"})
                continue
            if cur["position"] != prev["position"]:
                from_id, from_name = ref(prev["position"]["containerId"])
                to_id, to_name = ref(cur["position"]["containerId"])
                rel = cur["position"].get("relativeTo")
                changes.append({
                    "kind": "moved_entity", "phase": "change",
                    "entityId": eid, "actor": eid, "actorKind": "item",
                    "name": names.get(eid, eid),
                    "fromId": from_id, "from": from_name,
                    "fromKind": kind_of(from_id, after),
                    "toId": to_id, "to": to_name,
                    "toKind": kind_of(to_id, after),
                    "holderChanged": (kind_of(from_id, after) == "character"
                                      or kind_of(to_id, after) == "character"),
                    "relativeTo": ({"entityId": rel["entityId"],
                                    "name": names.get(rel["entityId"], rel["entityId"]),
                                    "relation": rel["relation"]} if rel else None),
                    "fieldPath": f"state.items.{eid}.position"})
            new = [c for c in cur["appearanceChanges"]
                   if c["id"] not in {p["id"] for p in prev["appearanceChanges"]}]
            for change in new:
                changes.append({"kind": "appearance_changed", "phase": "change",
                                "entityId": eid, "actor": eid, "actorKind": "item",
                                "name": names.get(eid, eid),
                                "text": change.get("text"),
                                "fieldPath": f"state.items.{eid}.appearanceChanges"})
    return changes, standing


def change_text(fact):
    if fact["kind"] == "moved":
        base = f"{fact['name']}从{fact['from']}来到{fact['to']}"
        if fact.get("relativeTo"):
            base += f"，位于{fact['relativeTo']['name']}旁边"
        return base
    if fact["kind"] == "moved_entity":
        base = f"{fact['name']}从{fact['from']}转到{fact['to']}"
        if fact.get("relativeTo"):
            base += f"，位于{fact['relativeTo']['name']}旁边"
        return base
    if fact["kind"] == "task_achieved":
        return f"{fact['name']}完成了任务「{fact['goal']}」"
    if fact["kind"] == "personality_changed":
        return f"{fact['name']}的人格变化为「{fact['text']}」"
    if fact["kind"] == "sanity_changed":
        return f"{fact['name']}的精神值从{fact['from']}变为{fact['to']}"
    if fact["kind"] == "appearance_changed":
        return f"{fact['name']}的外貌变化为「{fact['text']}」"
    return ""


# ------------------------------------------------------------------- N2 ----
def path_of_container(state, container_id):
    """Location chain for a container; a holder's own location stands in for the
    item's container (documented adapter: N2 resolves locations only)."""
    if container_id in state["state"]["locations"]:
        return n2.location_path_ids(state["state"], {"containerId": container_id})
    holder = state["state"]["characters"].get(container_id)
    if holder is not None:
        return n2.location_path_ids(state["state"], holder["position"])
    return []


def n1_facts(changes, after):
    """Map the pack's change facts onto the N1 fact shape N2 expects."""
    facts = []
    for fact in changes:
        kind, eid = fact["kind"], fact["entityId"]
        if kind == "moved":
            facts.append({"factId": f"{eid}:position", "kind": "moved",
                          "entityId": eid, "entityGroup": "characters",
                          "atPath": path_of_container(after, fact["toId"]),
                          "at": fact["to"]})
        elif kind == "moved_entity":
            facts.append({"factId": f"{eid}:position", "kind": "moved",
                          "entityId": eid, "entityGroup": "items",
                          "atPath": path_of_container(after, fact["toId"]),
                          "at": fact["to"]})
        elif kind == "task_achieved":
            facts.append({"factId": f"{eid}:task:{fact['taskId']}",
                          "kind": "task_achieved", "entityId": eid,
                          "entityGroup": "characters", "goal": fact["goal"]})
        elif kind == "personality_changed":
            facts.append({"factId": f"{eid}:personality", "kind": "personality_changed",
                          "entityId": eid, "entityGroup": "characters"})
        elif kind == "sanity_changed":
            facts.append({"factId": f"{eid}:sanity", "kind": "sanity_changed",
                          "entityId": eid, "entityGroup": "characters"})
        elif kind == "appearance_changed":
            if fact.get("actorKind") == "item":
                holder = after["state"]["items"][eid]["position"]["containerId"]
                path = path_of_container(after, holder)
                group = "items"
            else:
                path = n2.location_path_ids(after["state"], {"containerId": eid})
                group = "locations"
            facts.append({"factId": f"{eid}:appearance", "kind": "appearance_changed",
                          "entityId": eid, "entityGroup": group, "atPath": path})
    return facts


def classify(cid, changes, standing, after, spec):
    """N2 visibility classification + the player-scope rule on top."""
    viewpoint = n2.resolve_perspective(after["state"], ptype=spec["view"])
    if viewpoint["problems"]:
        raise RuntimeError(f"{cid}: perspective problems {viewpoint['problems']}")
    subject = viewpoint["perspective"].get("entityId") or after["state"]["protagonistId"]
    subject_tasks = after["state"]["characters"][subject]["tasks"]
    facts = n1_facts(changes, after)
    result = n2.classify_facts(facts, viewpoint["perspective"],
                               subject_tasks=subject_tasks, may_policy="select",
                               visible_other_actions=True)
    decided = {d["factId"]: d for d in result["decisions"] if d.get("factId")}
    scope = PLAYER_SCOPE.get(cid)
    scope_ids = set()
    by_id = {f["factId"]: f for f in facts}
    rows = []
    for fact in changes:
        fid = f"{fact['entityId']}:position" if fact["kind"] in ("moved", "moved_entity") \
            else f"{fact['entityId']}:task:{fact['taskId']}" if fact["kind"] == "task_achieved" \
            else f"{fact['entityId']}:personality" if fact["kind"] == "personality_changed" \
            else f"{fact['entityId']}:sanity" if fact["kind"] == "sanity_changed" \
            else f"{fact['entityId']}:appearance"
        decision = decided.get(fid, {"class": "unclassified", "ground": "missing",
                                     "selected": False, "reason": "N2 未返回该事实"})
        expression = {"must": "must", "may": "may",
                      "invisible": "withheld"}.get(decision["class"], "withheld")
        source = ("n2-must" if decision["class"] == "must" else
                  "n2-may" if decision["class"] == "may" else "n2-invisible")
        if expression == "may" and fid in (REQUIRE.get(cid) or []):
            expression, source = "must", "scenario-requirement"
        entry = dict(fact)
        entry.update({"factId": fid, "n2Class": decision["class"],
                      "n2Ground": decision["ground"], "n2Reason": decision["reason"],
                      "expression": expression, "requirementSource": source})
        if scope and fact.get("entityId") in scope["deferred"]:
            entry["expression"] = "withheld-by-instruction"
            entry["n2Reason"] = scope["constraint"]
            scope_ids.add(fid)
        rows.append(entry)
    must = [r for r in rows if r["expression"] == "must"]
    may = [r for r in rows if r["expression"] == "may"]
    withheld = [r for r in rows if r["expression"].startswith("withheld")]
    return {"perspective": viewpoint["perspective"], "n2": result,
            "rows": rows, "must": must, "may": may, "withheld": withheld,
            "scopeIds": sorted(scope_ids), "subject": subject}


def current_state_entries(cid, standing, after, perspective, deferred=()):
    """Standing references the viewpoint may mention (never a must).

    `deferred` entities are dropped here too: leaving their sanity and pending
    tasks in the packet would still surface a character the instruction put
    aside."""
    if perspective["type"] == "omniscient":
        allowed = lambda entry: True            # no secret to keep in omniscient
        own_only = False
    else:
        visible_cache = {}

        def allowed(entry):
            eid = entry["entityId"]
            if eid not in visible_cache:
                ch = after["state"]["characters"].get(eid)
                path = n2.location_path_ids(after["state"], ch["position"]) if ch else []
                visible, _ = n2._visibility_ground(
                    {"kind": "positioned_at", "entityId": eid, "atPath": path},
                    perspective)
                visible_cache[eid] = visible
            return visible_cache[eid]
        own_only = True
    out = []
    for s in standing:
        if s["entityId"] in set(deferred):
            continue
        if not allowed(s):
            continue
        if own_only and s["kind"] in ("sanity", "task_pending") \
                and s["entityId"] != perspective.get("entityId"):
            continue                       # others' inner state / task goals stay out
        if "locationId" in s:
            value = s["location"]
        elif "value" in s:                 # explicit presence: a 0 must survive
            value = s["value"]
        else:
            value = s["goal"]
        out.append({"entityId": s["entityId"], "name": s["name"],
                    "kind": s["kind"], "value": value})
    return out


def capability(cid, changes, withheld, after):
    """Four stages, judged per character for the numeric group (the page
    projection checks `narration_requires_complete_numeric_cause` inside its
    per-entity loop, committed-narration.ts:33-39)."""
    flags = []
    if any(c["kind"] in ("moved_entity", "appearance_changed")
           and (c["kind"] == "moved_entity" or c.get("actorKind") != "character")
           for c in changes):
        flags.append({"rule": "P1-item-or-location-delta",
                      "detail": "物品/地点的位移与外貌变化都会被拒（world change 比较整块）",
                      "line": "committed-narration.ts:28"})
    if any(c["kind"] == "appearance_changed" and c.get("actorKind") == "character"
           for c in changes):
        flags.append({"rule": "P2-character-appearance",
                      "detail": "人物外貌变化不在支持范围内",
                      "line": "committed-narration.ts:51"})
    if any(c["kind"] == "moved" and (c.get("relativeTo") or {}) for c in changes):
        flags.append({"rule": "P4-position-relative",
                      "detail": "人物位置的 relativeTo 会被投影拒绝",
                      "line": "committed-narration.ts:49"})
    by_actor = {}
    for c in changes:
        if c["kind"] in ("sanity_changed", "task_achieved", "personality_changed"):
            by_actor.setdefault(c["actor"], set()).add(c["kind"])
    trio = {"sanity_changed", "task_achieved", "personality_changed"}
    incomplete = {a: sorted(trio - kinds) for a, kinds in by_actor.items()
                  if kinds != trio}
    if incomplete:
        flags.append({"rule": "P3-incomplete-numeric-cause",
                      "detail": ("按人物逐一看："
                                 + "；".join(f"{a} 缺 {','.join(v)}"
                                             for a, v in sorted(incomplete.items()))
                                 + "，投影会拒绝"),
                      "line": "committed-narration.ts:33-39"})
    projection_ok = not any(f["rule"].startswith(("P1", "P2", "P3", "P4"))
                            for f in flags)
    if withheld:
        flags.append({"rule": "P5-no-perspective-filter",
                      "detail": ("页面叙事路径不做视角过滤：N2 判为不可见或按指令推迟的事实"
                                 "仍会从世界状态被照写；本条只能由 N2 规则臂或人工判定"),
                      "line": "committed-narration.ts:24-60"})
    return {
        "stages": {"stateCommitted": True,
                   "pageProjectionAcceptsDelta": projection_ok,
                   "perspectiveFilterEnforced": False,
                   "narrationGenerated": False},
        "pagePathSatisfiesExpectation": projection_ok and not withheld,
        "flags": flags,
        "module": ("页面已提交叙事路径" if projection_ok and not withheld else
                   "仅内核/接口层（页面投影或视角不支持）"),
        "scopeNote": SCOPE_NOTES.get(cid, ""),
    }


def main() -> int:
    cases = json.loads((SRC / "cases.json").read_text(encoding="utf-8"))
    specs = {s["id"]: s for s in
             json.loads((SRC / "scenario-specs.json").read_text(encoding="utf-8"))}
    registration = json.loads((SRC / "registration.json").read_text(encoding="utf-8"))
    corpus, vocab, scope = screening.load_sources()
    signatures = {sig: list(ids) for sig, ids in scope["signatureOwners"].items()}
    prov_path = OUT / "sources/three-arm-provenance.json"
    basis = {}
    if prov_path.exists():
        basis = {row["id"]: row["basis"]
                 for row in json.loads(prov_path.read_text(encoding="utf-8"))["items"]}

    rows = []
    for case in cases:
        cid = case["id"]
        spec = specs[cid]
        before = json.loads((SRC / f"{cid}.before.json").read_text(encoding="utf-8"))
        after = json.loads((SRC / f"{cid}.after.json").read_text(encoding="utf-8"))
        changes, standing = derive(before, after)
        cls = classify(cid, changes, standing, after, spec)
        must, may, withheld = cls["must"], cls["may"], cls["withheld"]

        # Exclusion screening always runs on the FULL change set.
        texts = [change_text(c) for c in changes]
        names = sorted({c["name"] for c in changes + standing})
        locations = sorted({str(v) for c in changes + standing
                            for v in (c.get("from"), c.get("to"), c.get("location"))
                            if v})
        tasks = sorted({c["goal"] for c in changes + standing if c.get("goal")})
        cand = {"id": cid, "texts": texts, "facts": changes,
                "time": {"amount": spec["seconds"], "unit": "second"},
                "characters": names, "locations": locations, "tasks": tasks}
        v1 = screening.screen(cand, corpus, vocab, signatures, mode="new-world",
                              r1_version="v1", basis=basis)
        v2 = screening.screen(cand, corpus, vocab, signatures, mode="new-world",
                              r1_version="v2", basis=basis)
        expression = screening.change_signature(must, cand["time"])
        caps = capability(cid, changes, withheld, after)

        deferred = set((PLAYER_SCOPE.get(cid) or {}).get("deferred") or [])
        current = current_state_entries(cid, standing, after, cls["perspective"],
                                        deferred=deferred)
        input_packet = {
            "packVersion": PACK_VERSION,
            "pointId": case["pointId"],
            "worldId": case["worldId"],
            "stateDigest": case["afterDigest"],
            "timeAdvance": {"amount": spec["seconds"], "unit": "second"},
            "perspective": cls["perspective"],
            "mustExpress": must,
            "mayMention": may,
            "currentState": current,
            "playerInstruction": spec.get("inputText") if cid == "c8e06" else None,
            "playerScopeExcludedFromState": sorted(deferred),
            "withheld": {
                "count": len(withheld),
                "rule": "不可见或按玩家指令推迟的事实不进入本输入；内容只留在 answer.json。",
                "grounds": sorted({w["n2Ground"] if w["expression"] == "withheld"
                                   else "player-instruction" for w in withheld}),
            },
            "rules": {
                "mustExpress": "本点提交的变化事实，必须表达，不得改向、改数、改人。",
                "mayMention": "可以不提；若提，内容须与事实一致，不得写成必述之外的新事件。",
                "currentState": "只作可提及的现状，不是必述项；省略不扣分。",
                "notProvided": "输入里没有的状态不要求模型说出，也不作为矛盾证据。",
            },
            "note": "只给事实、现状、视角与时间；完整状态与不可见事实都不作为输入。",
        }
        write(DEST / cid / "facts.json", json.dumps(
            {"rawDelta": after["entityDeltas"], "changeFacts": changes,
             "standingRefs": standing, "beforeDigest": case["rootDigest"],
             "afterDigest": case["afterDigest"]}, ensure_ascii=False, indent=1) + NL)
        write(DEST / cid / "answer.json", json.dumps(
            {"packVersion": PACK_VERSION,
             "perspective": cls["perspective"],
             "n1Facts": n1_facts(changes, after),
             "n2": {"module": str(N2_PATH.relative_to(REPO)).replace("\\", "/"),
                    "moduleSha256": sha(N2_PATH),
                    "status": cls["n2"]["status"],
                    "summary": cls["n2"]["summary"],
                    "stops": cls["n2"]["stops"],
                    "refusals": cls["n2"]["refusals"],
                    "decisions": cls["n2"]["decisions"]},
             "expression": {r["factId"]: r["expression"] for r in cls["rows"]},
             "withheld": withheld,
             "playerScope": {"ids": cls["scopeIds"],
                             "constraint": (PLAYER_SCOPE.get(cid) or {}).get("constraint")}},
            ensure_ascii=False, indent=1) + NL)
        write(DEST / cid / "input.json", json.dumps(input_packet, ensure_ascii=False,
                                                    indent=1) + NL)
        write(DEST / cid / "screening.json", json.dumps(
            {"v1": v1, "v2": v2, "expressionSignature": expression,
             "note": "R1/R2/R3 使用完整变化集合；expressionSignature 只用于叙述分析"},
            ensure_ascii=False, indent=1) + NL)

        must_hold = list(spec["checks"])
        must_not = ["把未提供的人物或地点写进叙述", "把本点没有的变化写成发生"]
        not_required = []
        for w in withheld:
            if w["expression"] == "withheld-by-instruction":
                must_not.append(f"把 `{w['name']}` 的移动当成关注对象或任务达成依据")
                not_required.append(f"`{w['name']}` 的移动（玩家指令要求暂不展开，且不在输入里）")
            else:
                must_not.append(f"在输入或叙述里出现 `{w['name']}` 的移动起终点")
                not_required.append(f"`{w['name']}` 的移动（N2 判为不可见：{w['n2Ground']}）")
        for m in may:
            not_required.append(f"省略 `{m['name']}` 的 `{m['kind']}`（N2 判为 may）")
        not_required.append("输入未提供的完整状态字段")

        row = {
            "id": cid, "title": spec["title"], "coverage": spec["coverage"],
            "view": spec["view"], "seconds": spec["seconds"],
            "committed": {"worldId": case["worldId"], "pointId": case["pointId"],
                          "rootDigest": case["rootDigest"],
                          "afterDigest": case["afterDigest"],
                          "database": "fresh/source/authority.sqlite3",
                          "reopenVerified": True},
            "facts": {"change": changes, "mustExpress": must, "mayMention": may,
                      "withheld": withheld, "standing": standing},
            "n2": {"perspective": cls["perspective"],
                   "summary": cls["n2"]["summary"],
                   "status": cls["n2"]["status"]},
            "input": input_packet,
            "screening": {"v1": v1, "v2": v2, "expressionSignature": expression,
                          "differs": v1["verdict"] != v2["verdict"]},
            "capability": caps,
            "checks": spec["checks"],
            "reviewItems": {"mustHold": must_hold, "mustNotAppear": must_not,
                            "notRequiredBecauseNotInInput": not_required},
        }
        checks = [f"# `{cid}` {spec['title']}", "",
                  f"- 覆盖：{'、'.join(spec['coverage'])}；视角：{spec['view']}；"
                  f"时间：{spec['seconds']} 秒",
                  f"- 提交点：`{case['worldId']}/{case['pointId']}`，"
                  f"after 摘要 `{case['afterDigest'][:16]}…`（读回校验通过）",
                  f"- 完整变化 {len(changes)} 条：必述 {len(must)}、可提及 {len(may)}、"
                  f"不进入输入 {len(withheld)}；现状引用 {len(current)} 条", "",
                  "## 四段状态", "",
                  "| 段 | 状态 | 证据 |", "|---|---|---|",
                  f"| 世界状态已提交 | 是 | `{case['pointId']}` + 读回 |",
                  f"| 页面投影接受该 Δ | {'是' if caps['stages']['pageProjectionAcceptsDelta'] else '否'} | "
                  f"{'无拒绝规则命中' if caps['stages']['pageProjectionAcceptsDelta'] else '、'.join(f['rule'] for f in caps['flags'] if f['rule'].startswith(('P1','P2','P3','P4')))} |",
                  f"| 视角过滤已执行 | N2 已判 | `{len(withheld)}` 条被排除（{', '.join(sorted({w['n2Ground'] for w in withheld})) or '无'}） |",
                  "| 叙事已生成 | 否 | 本轮不调用模型 |", ""]
        if withheld:
            checks += ["## 不进入成句输入的事实（答案侧保留）", ""]
            for w in withheld:
                checks.append(f"- `{w['name']}` · {w['kind']} — {w['n2Ground']}"
                              f"（{w['n2Reason']}）")
            checks.append("")
        if caps["flags"]:
            checks += ["## 能力不支持（单列，不算模型失败）", ""]
            for f in caps["flags"]:
                checks.append(f"- {f['rule']}：{f['detail']}（`{f['line']}`）")
            checks.append("")
        if caps["scopeNote"]:
            checks += ["## 适用范围说明", "", f"- {caps['scopeNote']}", ""]
        checks += ["## 人工核验项", ""]
        for x in row["reviewItems"]["mustHold"]:
            checks.append(f"- [ ] 必须成立：{x}")
        for x in row["reviewItems"]["mustNotAppear"]:
            checks.append(f"- [ ] 必须不出现：{x}")
        for x in row["reviewItems"]["notRequiredBecauseNotInInput"]:
            checks.append(f"- [ ] 不要求：{x}")
        checks += ["", "## 程序检查", "",
                   f"- R1 v1：{v1['verdict']}；v2：{v2['verdict']}；"
                   f"是否翻转：{'是' if v1['verdict'] != v2['verdict'] else '否'}",
                   f"- R2（new-world）：{'命中' if any(r['rule'] == 'R2-vocabulary' for r in v2['reasons']) else '零命中'}",
                   f"- R3 完整变化签名：`{v2['signature']}`",
                   f"- 必述子集签名（仅叙述分析）：`{expression}`", ""]
        write(DEST / cid / "checks.md", NL.join(checks) + NL)
        rows.append(row)

    report = {
        "packVersion": PACK_VERSION,
        "worktreeHead": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                       capture_output=True, text=True).stdout.strip(),
        "fixture": {"registration": registration,
                    "templateSha256": registration["templateSha256"],
                    "auditSha256": registration["auditSha256"],
                    "database": "fresh/source/authority.sqlite3",
                    "databaseSha256": sha(SRC / "authority.sqlite3")},
        "n2": {"path": str(N2_PATH.relative_to(REPO)).replace("\\", "/"),
               "sha256": sha(N2_PATH),
               "mayPolicy": "select", "visibleOtherActions": True,
               "note": "N2 为只读导入；mayPolicy/visibleOtherActions 是本文档选择，不改 N2"},
        "summary": {"candidates": len(rows),
                    "pageSupported": sum(1 for r in rows
                                         if r["capability"]["pagePathSatisfiesExpectation"]),
                    "capabilityLimited": sum(1 for r in rows
                                             if not r["capability"]["pagePathSatisfiesExpectation"]),
                    "withWithheldFacts": sum(1 for r in rows if r["facts"]["withheld"]),
                    "v1Rejected": sum(1 for r in rows if r["screening"]["v1"]["verdict"] == "rejected"),
                    "v2Rejected": sum(1 for r in rows if r["screening"]["v2"]["verdict"] == "rejected"),
                    "formalItems": 0, "frozen": 0, "modelCalls": 0},
        "candidates": rows,
        "gaps": [
            {"id": "g06", "dimension": "长期人际关系", "status": "无权威字段",
             "why": "世界状态没有人物关系字段；c8e04/c8e05 只覆盖空间相对位置与持有。"},
            {"id": "g07", "dimension": "物品由人物持有时 N2 的位置解析",
             "status": "适配层补齐",
             "why": "n2_perspective 只解析地点容器；物品被人物持有时，本包用持有人的"
                    "地点链代替并记录，未改 N2。"},
        ],
        "revisions": [
            {"version": 2, "date": "2026-11-08",
             "trigger": "外部静态审查（第一轮）",
             "fixed": ["c8e02 远处移动移出必述", "c8e06 被推迟移动移出必述",
                       "c8e05 物品位移补起止两端", "c8e04 参照对象补名称",
                       "能力拆四段", "currentState 不再吞 0"],
             "notChanged": ["夹具、数据库、六个提交点与摘要"]},
            {"version": 3, "date": "2026-11-08",
             "trigger": "外部静态审查（第二轮）",
             "fixed": ["R1/R2/R3 回到完整变化集合，另存必述子集签名",
                       "视野筛选改由真实 N2 判定（不可见事实只留在 answer.json）",
                       "c8e03 同一套 N2 判定：聂汀穗的移动为 may，不再当必述",
                       "能力判断按人物逐一检查任务/人格/理智三件套"],
             "notChanged": ["夹具、数据库、六个提交点与摘要", "R1 v1/v2、R2、R3 口径本身"]},
        ],
    }
    write(DEST / "candidates.json", json.dumps(report, ensure_ascii=False, indent=1) + NL)

    esc = lambda s: s.replace("|", chr(92) + "|")
    lines = ["# 首批候选（6 条，待人工核验）", "",
             f"输入包版本 v{PACK_VERSION}（2026-11-08 第二轮外部审查后修订，见 `report.md`）。",
             f"工作树 `{report['worktreeHead'][:12]}`。来源是本次**新建**的评测专用注册夹具 "
             f"`{registration['id']}`：作者 `{registration['author']}`，"
             f"创建时间 `{registration['createdUtc']}`，"
             "不是 R01 生成、不是历史玩家记录、没有改名复用旧世界。", "",
             "六条全部通过 A 侧 Python 服务提交并读回（独立数据库 "
             "`fresh/source/authority.sqlite3`，读回校验 6/6）。**未冻结**，"
             "人工核验通过后才做一次性冻结。", "",
             "## 场景一览", "",
             "| 编号 | 场景 | 覆盖 | 视角 | 时长 | 必述/可提及/不进输入 | 页面路径 | 完整变化签名 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| `{r['id']}` | {r['title']} | {'、'.join(r['coverage'])} | "
                     f"{r['view']} | {r['seconds']}s | "
                     f"{len(r['facts']['mustExpress'])}/{len(r['facts']['mayMention'])}/"
                     f"{len(r['facts']['withheld'])} | "
                     f"{'满足' if r['capability']['pagePathSatisfiesExpectation'] else '不满足'} | "
                     f"`{esc(r['screening']['v2']['signature'])}` |")
    lines += ["", "## 模型看到什么、看不到什么", "",
              "可见性不由本包自定，而是导入真实 N2 规则（`experiments/world-components/"
              "n2_perspective.py`，只读）逐条判定 must / may / invisible。",
              "不可见的事实只写进 `answer.json`（核验答案），**不进 `input.json`**。"
              "唯一的非可见性排除是 `c8e06` 的玩家指令，单独标为 `player-instruction`。", "",
              "## 能力不支持的部分（单列，不算模型失败）", ""]
    limited = [r for r in rows if r["capability"]["flags"]]
    if limited:
        for r in limited:
            for f in r["capability"]["flags"]:
                lines.append(f"- `{r['id']}`：{f['rule']} — {f['detail']}（`{f['line']}`）")
    else:
        lines.append("- 无。")
    lines += ["", "## 文件", "",
              "```",
              "candidates-fresh/",
              "├── candidates.json     汇总（提交证据、四段状态、筛选、修订记录）",
              "├── report.md           逐条报告",
              "├── review-table.md     人工核验表（待填）",
              "└── <id>/",
              "    ├── facts.json      原始 Δ / 变化事实 / 现状",
              "    ├── answer.json     完整事实 + N2 逐条判定 + 被排除的事实",
              "    ├── input.json      模型实际输入（含 withheld 计数，不含其内容）",
              "    ├── screening.json  R1 v1/v2、R2、R3（完整变化集）",
              "    └── checks.md       四段状态、排除事实、人工核验项",
              "```", ""]
    write(DEST / "README.md", NL.join(lines) + NL)

    rep = ["# 首批候选逐条报告（自动生成，勿手改）", "",
           f"输入包 v{PACK_VERSION}。夹具：`{registration['id']}`"
           f"（模板 sha256 `{registration['templateSha256'][:16]}…`）；"
           f"数据库 sha256 `{report['fixture']['databaseSha256'][:16]}…`；"
           f"N2 模块 sha256 `{report['n2']['sha256'][:16]}…`。", ""]
    for r in rows:
        rep += [f"## `{r['id']}` {r['title']}", "",
                f"- 覆盖：{'、'.join(r['coverage'])}；视角：{r['view']}；{r['seconds']} 秒",
                f"- 提交：`{r['committed']['worldId']}/{r['committed']['pointId']}`，"
                f"before `{r['committed']['rootDigest'][:12]}…` → "
                f"after `{r['committed']['afterDigest'][:12]}…`（读回校验通过）",
                f"- 完整变化 {len(r['facts']['change'])} 条：必述 "
                f"{len(r['facts']['mustExpress'])}、可提及 {len(r['facts']['mayMention'])}、"
                f"不进入输入 {len(r['facts']['withheld'])}",
                f"- N2：{r['n2']['status']}，must {r['n2']['summary'].get('must')}／"
                f"may {r['n2']['summary'].get('may')}／invisible "
                f"{r['n2']['summary'].get('invisible')}",
                f"- R1 v1/v2：{r['screening']['v1']['verdict']} / "
                f"{r['screening']['v2']['verdict']}；R3 `{r['screening']['v2']['signature']}`",
                f"- 四段：状态已提交 是｜页面投影接受 Δ "
                f"{'是' if r['capability']['stages']['pageProjectionAcceptsDelta'] else '否'}｜"
                f"视角过滤 N2 已判（排除 {len(r['facts']['withheld'])} 条）｜叙事已生成 否",
                "", "必述：", ""]
        for c in r["facts"]["mustExpress"]:
            rep.append(f"- `{c['kind']}` {c['entityId']} · `{c['fieldPath']}`"
                       f"（{c['n2Ground']}）")
        if r["facts"]["mayMention"]:
            rep += ["", "可提及：", ""]
            for c in r["facts"]["mayMention"]:
                rep.append(f"- `{c['kind']}` {c['entityId']}（{c['n2Ground']}）")
        if r["facts"]["withheld"]:
            rep += ["", "不进入输入（答案侧保留）：", ""]
            for c in r["facts"]["withheld"]:
                rep.append(f"- `{c['kind']}` {c['entityId']}（{c['n2Ground']}）")
        rep.append("")
    rep += ["## 修订记录", ""]
    for rev in report["revisions"]:
        rep += [f"### v{rev['version']}（{rev['date']}）", "",
                f"触发：{rev['trigger']}", "", "改动：", ""]
        rep += [f"- {x}" for x in rev["fixed"]]
        rep += ["", "未改动：", ""] + [f"- {x}" for x in rev["notChanged"]] + [""]
    write(DEST / "report.md", NL.join(rep) + NL)

    tbl = ["# 人工核验表（6 条候选，待核验）", "",
           "**本轮没有模型输出**：现在能核的是“题目、事实与预期是否成立”，"
           "不是模型表现。结论只允许：`待核验`（默认）／`通过`／`不通过`／`无法判断`；"
           "`无法判断` 不算通过。核验者不得是参与调参的人。", "",
           "| 编号 | 项 | 类型 | 内容 | 依据 | 核验者 | 日期 | 结论 |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        n = 0
        fact_ref = (f"`{r['committed']['pointId']}`；必述 "
                    f"{len(r['facts']['mustExpress'])} 条，见 `{r['id']}/facts.json`")
        for kind, key in (("必须成立", "mustHold"), ("必须不出现", "mustNotAppear"),
                          ("不要求（输入未提供）", "notRequiredBecauseNotInInput")):
            for text in r["reviewItems"][key]:
                n += 1
                tbl.append(f"| `{r['id']}` | {n} | {kind} | {text} | {fact_ref} |  |  | 待核验 |")
    tbl += ["", "## 说明", "",
            "- 作者写的部分核对项是**核验时的注意事项**，不是对模型输出的要求；"
            "判不了就记无法判断。",
            "- `c8e02`／`c8e04`／`c8e05`／`c8e06` 的页面路径不满足预期（视角过滤、物品位移、"
            "外貌变化或纯任务达成），只核内核/接口层与 N2 规则臂。",
            "- `c8e06` 的“玩家关注”是本次作者编写的合成指令，不是真实玩家原话。",
            "- 全部项目核完前，任务保持“未完成”；核验通过后才做一次性冻结。"]
    write(DEST / "review-table.md", NL.join(tbl) + NL)

    s = report["summary"]
    print(f"pack=v{PACK_VERSION} candidates={s['candidates']} pageSupported={s['pageSupported']} "
          f"limited={s['capabilityLimited']} withheld={s['withWithheldFacts']} "
          f"v1Rejected={s['v1Rejected']} v2Rejected={s['v2Rejected']}")
    for r in rows:
        print(f"  {r['id']} {r['screening']['v2']['verdict']:9} "
              f"must={len(r['facts']['mustExpress'])} may={len(r['facts']['mayMention'])} "
              f"withheld={len(r['facts']['withheld'])} "
              f"page={'ok' if r['capability']['pagePathSatisfiesExpectation'] else 'no'} "
              f"full={r['screening']['v2']['signature']} expr={r['screening']['expressionSignature']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
