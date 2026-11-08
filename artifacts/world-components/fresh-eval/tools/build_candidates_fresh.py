"""Turn the committed fresh fixture cases into a reviewable candidate pack.

For each committed case this writes, under candidates-fresh/<id>/:
  facts.json     raw delta, change facts (with ids and names), standing refs
  input.json     exactly what a narration model would receive - never the full
                 world state, and never a fact the scenario says is out of scope
  screening.json R1 v1/v2, R2 (new-world), R3 change signature
  checks.md      scope, capability status, human review items

Pack level: candidates.json, README.md, report.md, review-table.md.

Pack version 2 (after the 2026-11-08 external review):
  * item moves now carry both ends (`fromId`/`from`, `toId`/`to`, holder kind);
  * reference objects carry a readable name next to the id;
  * facts the scenario puts out of scope are NOT in mustExpress: a limited
    viewpoint puts facts outside the visible containers into `mayMention`
    (`offstage-perspective`), and a player instruction that defers an entity
    puts its changes there too (`deferredByInstruction`);
  * capability is reported as four separate stages instead of one boolean;
  * a zero-valued standing number is no longer swallowed by `or` chaining.

No model is called; no production code is touched. Screening numbers are
computed from the committed states and the raw delta only.

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
PACK_VERSION = 2

_spec = importlib.util.spec_from_file_location("screening", HERE / "screening.py")
screening = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(screening)

# ---------------------------------------------------------------- scoping ---
# Per item: which changes the model is actually asked to express, and why the
# rest are out of scope. `viewpoint` limits the visible containers; `deferred`
# lists entities a player instruction puts aside for this point.
CASE_RULES = {
    "c8e02": {
        "viewpoint": "fe_wen",
        "rules": {
            "offstage-perspective": (
                "限知视角：不在主体可见容器内的变化可以不提；若要提，"
                "不得写成主体亲眼所见或亲耳听到。"),
        },
    },
    "c8e06": {
        "deferred": ["fe_wen"],
        "rules": {
            "deferredByInstruction": (
                "玩家指令要求本轮暂不展开该角色：可以不提；若要提，"
                "不得写成关注对象，也不得据此推出任务达成。"),
        },
    },
}

# Per-item scope notes: what a check does NOT prove, and which module owns it.
SCOPE_NOTES = {
    "c8e01": "三条都是普通人物位移，页面路径能全部写出；不覆盖限知与物品。",
    "c8e02": ("限知范围只在 N2 视角臂成立：页面叙事路径不执行可见性过滤，"
              "所以本条不计页面叙述成绩。"),
    "c8e03": ("父子任务都已达成，事实同时给出人格与理智；不覆盖“父达成/子未达成”的情形。"),
    "c8e04": ("空间相对位置（beside）只在夹具与内核层成立；页面投影拒绝该形状。"),
    "c8e05": ("持有转移与外貌变化都在物品上；页面投影既不接受物品位移，也不接受外貌变化。"),
    "c8e06": ("玩家关注是本次作者编写的合成指令，不是真实玩家原话；"
              "只核关注解析数据，不称 N2 已支持该功能；纯任务达成在页面投影会被拒绝。"),
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


def kind_of(eid, index_state):
    for bucket, label in (("characters", "character"), ("locations", "location"),
                          ("items", "item")):
        if eid in index_state["state"]["initial"].get(bucket, {}):
            return label
    return "unknown"


def parents_of(state):
    out = {}
    for lid, entry in state["state"]["initial"]["locations"].items():
        out[lid] = entry.get("parentLocationId")
    return out


def visible_containers(state, viewpoint):
    """The viewpoint's own container plus its ancestors (a room sees its yard)."""
    parents = parents_of(state)
    start = state["state"]["characters"][viewpoint]["position"]["containerId"]
    seen, cur = set(), start
    while cur and cur not in seen:
        seen.add(cur)
        cur = parents.get(cur)
    return seen


def derive(before, after):
    """Split this point's facts by provenance, with ids and readable names."""
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


def classify(cid, changes, after):
    """Split changes into (must express, may mention + reason)."""
    rule = CASE_RULES.get(cid, {})
    viewpoint = rule.get("viewpoint")
    deferred = set(rule.get("deferred") or [])
    visible = visible_containers(after, viewpoint) if viewpoint else None
    must, may = [], []
    for fact in changes:
        reason = None
        if fact.get("actor") in deferred:
            reason = "deferredByInstruction"
        elif visible is not None:
            target = fact.get("toId") or fact.get("locationId")
            if target and target not in visible:
                reason = "offstage-perspective"
        if reason:
            entry = dict(fact)
            entry["reason"] = reason
            entry["constraint"] = rule["rules"][reason]
            may.append(entry)
        else:
            must.append(fact)
    return must, may


def capability(cid, changes, must, may, after):
    flags = []
    if any(c["kind"] == "moved_entity" for c in changes):
        flags.append({"rule": "P1-non-character-delta",
                      "detail": "物品位移不在页面叙事投影的支持范围内",
                      "line": "committed-narration.ts:28"})
    if any(c["kind"] == "appearance_changed" for c in changes):
        flags.append({"rule": "P2-appearance-change",
                      "detail": "实体外貌变化不在支持范围内",
                      "line": "committed-narration.ts:51"})
    if any((c.get("relativeTo") or {}) for c in changes):
        flags.append({"rule": "P4-position-slot-or-relative",
                      "detail": "relativeTo 会被投影拒绝（unsupported_narration_position）",
                      "line": "committed-narration.ts:49"})
    kinds = {c["kind"] for c in changes}
    numeric = kinds & {"sanity_changed", "task_achieved", "personality_changed"}
    trio = {"sanity_changed", "task_achieved", "personality_changed"}
    if numeric and numeric != trio:
        flags.append({"rule": "P3-incomplete-numeric-cause",
                      "detail": "任务/人格/理智未同时出现，投影会拒绝",
                      "line": "committed-narration.ts:38"})
    if may:
        flags.append({"rule": "P5-no-perspective-filter",
                      "detail": ("页面叙事路径不做视角过滤：世界为真的远处变化会被照写，"
                                 "本条的限知/推迟要求只能由 N2 规则臂或人工判定"),
                      "line": "committed-narration.ts:24-60"})
    ok_projection = not any(f["rule"] in ("P1-non-character-delta", "P2-appearance-change",
                                          "P3-incomplete-numeric-cause",
                                          "P4-position-slot-or-relative") for f in flags)
    return {
        "stages": {
            "stateCommitted": True,
            "pageProjectionAcceptsDelta": ok_projection,
            "perspectiveFilterEnforced": False,
            "narrationGenerated": False,
        },
        "pagePathSatisfiesExpectation": ok_projection and not may,
        "flags": flags,
        "module": ("页面已提交叙事路径" if ok_projection and not may else
                   "仅内核/接口层（页面投影或视角不支持）"),
        "scopeNote": SCOPE_NOTES.get(cid, ""),
    }


def current_state_entries(standing):
    out = []
    for s in standing:
        if "locationId" in s:
            out.append({"entityId": s["entityId"], "name": s["name"],
                        "kind": s["kind"], "value": s["location"]})
        elif "value" in s:            # explicit presence: a 0 must survive
            out.append({"entityId": s["entityId"], "name": s["name"],
                        "kind": s["kind"], "value": s["value"]})
        elif "goal" in s:
            out.append({"entityId": s["entityId"], "name": s["name"],
                        "kind": s["kind"], "value": s["goal"]})
    return out


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
        must, may = classify(cid, changes, after)

        texts = [change_text(c) for c in must]
        names = sorted({c["name"] for c in changes + standing})
        locations = sorted({str(v) for c in changes + standing
                            for v in (c.get("from"), c.get("to"), c.get("location"))
                            if v})
        tasks = sorted({c["goal"] for c in changes + standing if c.get("goal")})
        cand = {"id": cid, "texts": texts, "facts": must,
                "time": {"amount": spec["seconds"], "unit": "second"},
                "characters": names, "locations": locations, "tasks": tasks}
        v1 = screening.screen(cand, corpus, vocab, signatures, mode="new-world",
                              r1_version="v1", basis=basis)
        v2 = screening.screen(cand, corpus, vocab, signatures, mode="new-world",
                              r1_version="v2", basis=basis)

        perspective = ({"type": "omniscient"} if spec["view"] == "omniscient"
                       else {"type": "protagonist", "entityId": "fe_wen",
                             "at": after["state"]["characters"]["fe_wen"]["position"]["containerId"]})
        input_packet = {
            "packVersion": PACK_VERSION,
            "pointId": case["pointId"],
            "worldId": case["worldId"],
            "stateDigest": case["afterDigest"],
            "timeAdvance": {"amount": spec["seconds"], "unit": "second"},
            "perspective": perspective,
            "mustExpress": must,
            "mayMention": [{"fact": {k: v for k, v in entry.items()
                                     if k not in ("reason", "constraint")},
                            "reason": entry["reason"],
                            "constraint": entry["constraint"]} for entry in may],
            "currentState": current_state_entries(standing),
            "playerInstruction": spec.get("inputText") if cid == "c8e06" else None,
            "rules": {
                "mustExpress": "本点提交的变化事实，必须表达，不得改向、改数、改人。",
                "mayMention": "可以不提；若要提，遵守 constraint，且不得反过来当成必述项。",
                "currentState": "只作可提及的现状，不是必述项；省略不扣分。",
                "notProvided": "输入里没有的状态不要求模型说出，也不作为矛盾证据。",
            },
            "note": "只给事实、现状、视角与时间；完整状态不作为输入。",
        }
        caps = capability(cid, changes, must, may, after)
        scope_rules = CASE_RULES.get(cid, {}).get("rules", {})

        must_hold = list(spec["checks"])
        must_not = ["把未提供的人物或地点写进叙述", "把本点没有的变化写成发生"]
        not_required = ["完整状态里未进入 mustExpress/currentState 的任何字段"]
        for entry in may:
            reason = entry["reason"]
            if reason == "offstage-perspective":
                must_not.append("把限知范围外的移动写成主体亲眼所见")
                not_required.append(f"省略 `{entry['name']}` 在远处的移动")
            elif reason == "deferredByInstruction":
                must_not.append(f"把 `{entry['name']}` 的移动写成关注对象或任务达成依据")
                not_required.append(f"省略 `{entry['name']}` 的移动（玩家指令要求暂不展开）")

        row = {
            "id": cid, "title": spec["title"], "coverage": spec["coverage"],
            "view": spec["view"], "seconds": spec["seconds"],
            "committed": {"worldId": case["worldId"], "pointId": case["pointId"],
                          "rootDigest": case["rootDigest"],
                          "afterDigest": case["afterDigest"],
                          "database": "fresh/source/authority.sqlite3",
                          "reopenVerified": True},
            "facts": {"change": changes, "mustExpress": must, "mayMention": may,
                      "standing": standing},
            "input": input_packet,
            "screening": {"v1": v1, "v2": v2,
                          "differs": v1["verdict"] != v2["verdict"]},
            "capability": caps,
            "checks": spec["checks"],
            "reviewItems": {"mustHold": must_hold, "mustNotAppear": must_not,
                            "notRequiredBecauseNotInInput": not_required},
        }
        write(DEST / cid / "facts.json", json.dumps(
            {"rawDelta": after["entityDeltas"], "changeFacts": changes,
             "mustExpress": must, "mayMention": may, "standingRefs": standing,
             "beforeDigest": case["rootDigest"], "afterDigest": case["afterDigest"]},
            ensure_ascii=False, indent=1) + NL)
        write(DEST / cid / "input.json", json.dumps(input_packet, ensure_ascii=False,
                                                    indent=1) + NL)
        write(DEST / cid / "screening.json", json.dumps(
            {"v1": v1, "v2": v2}, ensure_ascii=False, indent=1) + NL)

        checks = [f"# `{cid}` {spec['title']}", "",
                  f"- 覆盖：{'、'.join(spec['coverage'])}；视角：{spec['view']}；"
                  f"时间：{spec['seconds']} 秒",
                  f"- 提交点：`{case['worldId']}/{case['pointId']}`，"
                  f"after 摘要 `{case['afterDigest'][:16]}…`（读回校验通过）",
                  f"- 必述 {len(must)} 条；可不提 {len(may)} 条；"
                  f"现状引用 {len(standing)} 条", "",
                  "## 四段状态", "",
                  "| 段 | 状态 | 证据 |", "|---|---|---|",
                  f"| 世界状态已提交 | 是 | `{case['pointId']}` + 读回 |",
                  f"| 页面投影接受该 Δ | {'是' if caps['stages']['pageProjectionAcceptsDelta'] else '否'} | "
                  f"{'无拒绝规则命中' if caps['stages']['pageProjectionAcceptsDelta'] else '、'.join(f['rule'] for f in caps['flags'])} |",
                  "| 视角过滤已执行 | 否 | 页面路径无可见性判定 |",
                  "| 叙事已生成 | 否 | 本轮不调用模型 |", ""]
        if caps["flags"]:
            checks += ["## 能力不支持（单列，不算模型失败）", ""]
            for f in caps["flags"]:
                checks.append(f"- {f['rule']}：{f['detail']}（`{f['line']}`）")
            checks.append("")
        note = caps["scopeNote"]
        if note:
            checks += ["## 适用范围说明", "", f"- {note}", ""]
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
                   f"- R3 变化签名：`{v2['signature']}`", ""]
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
        "summary": {"candidates": len(rows),
                    "pageSupported": sum(1 for r in rows
                                         if r["capability"]["pagePathSatisfiesExpectation"]),
                    "capabilityLimited": sum(1 for r in rows
                                             if not r["capability"]["pagePathSatisfiesExpectation"]),
                    "withOutOfScopeFacts": sum(1 for r in rows if r["facts"]["mayMention"]),
                    "v1Rejected": sum(1 for r in rows if r["screening"]["v1"]["verdict"] == "rejected"),
                    "v2Rejected": sum(1 for r in rows if r["screening"]["v2"]["verdict"] == "rejected"),
                    "formalItems": 0, "frozen": 0, "modelCalls": 0},
        "candidates": rows,
        "gaps": [{"id": "g06", "dimension": "长期人际关系",
                  "status": "无权威字段",
                  "why": "世界状态没有人物关系字段；c8e04/c8e05 只覆盖空间相对位置与持有，"
                         "不声称覆盖长期人际关系。"}],
        "revisions": [
            {"version": 2, "date": "2026-11-08",
             "trigger": "外部静态审查（未运行测试）",
             "fixed": [
                 "c8e02：远处移动不再进入 mustExpress，改为 mayMention/offstage-perspective",
                 "c8e06：被指令推迟的移动不再进入 mustExpress，改为 mayMention/deferredByInstruction",
                 "c8e05：物品位移补全 fromId/from 与 toKind、holderChanged",
                 "c8e04：relativeTo 补全可读名称",
                 "全部：能力拆成四段状态，页面路径是否满足预期单独判定",
                 "全部：currentState 取值不再用 or 链，0 不会被吞成 null",
             ],
             "notChanged": [
                 "夹具、数据库、六个提交点与摘要未动（输入包是派生物）",
                 "R1 v1/v2、R2、R3 口径未动；六条仍然零命中",
             ]},
        ],
    }
    write(DEST / "candidates.json", json.dumps(report, ensure_ascii=False, indent=1) + NL)

    # ---- pack README -------------------------------------------------------
    lines = ["# 首批候选（6 条，待人工核验）", "",
             f"输入包版本 v{PACK_VERSION}（2026-11-08 按外部审查修订，见 `report.md` 末尾“修订记录”）。",
             f"工作树 `{report['worktreeHead'][:12]}`。来源是本次**新建**的评测专用注册夹具 "
             f"`{registration['id']}`：作者 `{registration['author']}`，"
             f"创建时间 `{registration['createdUtc']}`，"
             "不是 R01 生成、不是历史玩家记录、没有改名复用旧世界。", "",
             "六条全部通过 A 侧 Python 服务提交并读回（独立数据库 "
             "`fresh/source/authority.sqlite3`，读回校验 6/6）。**未冻结**，"
             "人工核验通过后才做一次性冻结。", "",
             "## 场景一览", "",
             "| 编号 | 场景 | 覆盖 | 视角 | 时长 | 必述/可不提 | 页面路径 | 变化签名 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| `{r['id']}` | {r['title']} | {'、'.join(r['coverage'])} | "
                     f"{r['view']} | {r['seconds']}s | "
                     f"{len(r['facts']['mustExpress'])}/{len(r['facts']['mayMention'])} | "
                     f"{'满足' if r['capability']['pagePathSatisfiesExpectation'] else '不满足'} | "
                     f"`{r['screening']['v2']['signature'].replace('|', chr(92) + '|')}` |")
    lines += ["", "## 每个候选给了模型什么", "",
              "模型输入四块：`mustExpress`（必须表达）、`mayMention`（可以不提，提则受限）、"
              "`currentState`（可提及的现状）、视角与时间。完整状态不作为输入；"
              "输入未提供的状态不要求模型说出，也不因省略扣分。"
              "逐条见 `candidates-fresh/<id>/input.json`。", "",
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
              "├── candidates.json     汇总（提交证据、四段状态、筛选结果、修订记录）",
              "├── report.md           逐条报告",
              "├── review-table.md     人工核验表（待填）",
              "└── <id>/",
              "    ├── facts.json      原始 Δ / 变化事实 / 必述 / 可不提 / 现状",
              "    ├── input.json      模型实际输入",
              "    ├── screening.json  R1 v1/v2、R2、R3",
              "    └── checks.md       四段状态、能力说明、人工核验项",
              "```", ""]
    write(DEST / "README.md", NL.join(lines) + NL)

    # ---- report.md ---------------------------------------------------------
    rep = ["# 首批候选逐条报告（自动生成，勿手改）", "",
           f"输入包 v{PACK_VERSION}。夹具：`{registration['id']}`"
           f"（模板 sha256 `{registration['templateSha256'][:16]}…`）；"
           f"数据库 sha256 `{report['fixture']['databaseSha256'][:16]}…`。", ""]
    for r in rows:
        rep += [f"## `{r['id']}` {r['title']}", "",
                f"- 覆盖：{'、'.join(r['coverage'])}；视角：{r['view']}；{r['seconds']} 秒",
                f"- 提交：`{r['committed']['worldId']}/{r['committed']['pointId']}`，"
                f"before `{r['committed']['rootDigest'][:12]}…` → "
                f"after `{r['committed']['afterDigest'][:12]}…`（读回校验通过）",
                f"- 必述 {len(r['facts']['mustExpress'])} 条；可不提 "
                f"{len(r['facts']['mayMention'])} 条；现状引用 {len(r['facts']['standing'])} 条",
                f"- R1 v1/v2：{r['screening']['v1']['verdict']} / "
                f"{r['screening']['v2']['verdict']}"
                f"{'（翻转）' if r['screening']['differs'] else ''}；"
                f"R3 `{r['screening']['v2']['signature']}`",
                f"- 四段：状态已提交 是｜页面投影接受 Δ "
                f"{'是' if r['capability']['stages']['pageProjectionAcceptsDelta'] else '否'}｜"
                "视角过滤已执行 否｜叙事已生成 否",
                "", "必述事实：", ""]
        for c in r["facts"]["mustExpress"]:
            rep.append(f"- `{c['kind']}` {c['entityId']} · `{c['fieldPath']}`")
        if r["facts"]["mayMention"]:
            rep += ["", "可不提（提则受限）：", ""]
            for c in r["facts"]["mayMention"]:
                rep.append(f"- `{c['kind']}` {c['entityId']} — {c['reason']}："
                           f"{c['constraint']}")
        if r["capability"]["flags"]:
            rep += ["", "能力不支持：", ""]
            for f in r["capability"]["flags"]:
                rep.append(f"- {f['rule']}：{f['detail']}")
        rep.append("")
    rep += ["## 修订记录", ""]
    for rev in report["revisions"]:
        rep += [f"### v{rev['version']}（{rev['date']}）", "",
                f"触发：{rev['trigger']}", "", "改动：", ""]
        rep += [f"- {x}" for x in rev["fixed"]]
        rep += ["", "未改动：", ""] + [f"- {x}" for x in rev["notChanged"]] + [""]
    write(DEST / "report.md", NL.join(rep) + NL)

    # ---- review table ------------------------------------------------------
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
            "- 作者写的部分核对项是**核验时的注意事项**（例如“不因未提未提供的 pending 扣分”），"
            "不是对模型输出的要求；核到这类条目时按“是否被正确执行”判，判不了就记无法判断。",
            "- `c8e02`／`c8e04`／`c8e05`／`c8e06` 的页面路径不满足预期（视角过滤、物品位移、"
            "外貌变化或纯任务达成），只核内核/接口层与 N2 规则臂，不计页面叙述成绩。",
            "- `c8e06` 的“玩家关注”是本次作者编写的合成指令，不是真实玩家原话；"
            "只核关注解析，不称 N2 已支持该功能。",
            "- 全部项目核完前，任务保持“未完成”；核验通过后才做一次性冻结。"]
    write(DEST / "review-table.md", NL.join(tbl) + NL)

    s = report["summary"]
    print(f"candidates={s['candidates']} pageSupported={s['pageSupported']} "
          f"limited={s['capabilityLimited']} outOfScope={s['withOutOfScopeFacts']} "
          f"v1Rejected={s['v1Rejected']} v2Rejected={s['v2Rejected']}")
    for r in rows:
        print(f"  {r['id']} {r['screening']['v2']['verdict']:9} "
              f"must={len(r['facts']['mustExpress'])} may={len(r['facts']['mayMention'])} "
              f"page={'ok' if r['capability']['pagePathSatisfiesExpectation'] else 'no'} "
              f"sig={r['screening']['v2']['signature']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
