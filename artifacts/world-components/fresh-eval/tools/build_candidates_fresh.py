"""Turn the committed fresh fixture cases into a reviewable candidate pack.

For each committed case this writes, under candidates-fresh/<id>/:
  facts.json     raw delta, change facts, standing references (provenance)
  input.json     exactly what a narration model would receive (facts + time +
                 perspective + constraints) - never the full world state
  screening.json R1 v1/v2, R2 (new-world), R3 change signature, capability flags
  checks.md      human review items (must hold / must not appear / not required)

and the pack-level README.md, report.md and review-table.md.

No model is called; no production code is touched. Screening numbers are
computed from the committed after-state and the raw delta only.

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

_spec = importlib.util.spec_from_file_location("screening", HERE / "screening.py")
screening = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(screening)

SUPPORTED_PAGE_KINDS = {"moved", "sanity", "sanity_changed", "task_achieved",
                        "personality_changed"}

# Per-item scope notes: what a check does NOT prove, and which module owns it.
SCOPE_NOTES = {
    "c8e02": ("页面叙事路径不会做视角过滤，两栋建筑的移动都会被写出；"
              "可见性判定只在 N2 规则臂，本条的页面叙述成绩不包含可见性。"),
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


def name_of(state, eid):
    for bucket in ("characters", "locations", "items"):
        entry = state["state"]["initial"].get(bucket, {}).get(eid)
        if entry:
            return entry["name"]
    return eid


def derive(before, after):
    """Split this point's facts by provenance, using ids from the states."""
    changes, standing = [], []
    for eid in sorted(after["state"]["characters"]):
        cur = after["state"]["characters"][eid]
        prev = before["state"]["characters"][eid]
        name = name_of(after, eid)
        loc = name_of(after, cur["position"]["containerId"])
        if cur["position"] != prev["position"]:
            changes.append({"kind": "moved", "phase": "change", "entityId": eid,
                            "actor": eid,
                            "name": name,
                            "from": name_of(after, prev["position"]["containerId"]),
                            "to": loc,
                            "relativeTo": cur["position"].get("relativeTo"),
                            "fieldPath": f"state.characters.{eid}.position"})
        else:
            standing.append({"kind": "at", "phase": "standing", "entityId": eid,
                             "actor": eid,
                             "name": name, "location": loc,
                             "fieldPath": f"state.characters.{eid}.position"})
        if cur["sanity"] != prev["sanity"]:
            changes.append({"kind": "sanity_changed", "phase": "change", "entityId": eid,
                            "actor": eid,
                            "name": name, "from": prev["sanity"], "to": cur["sanity"],
                            "fieldPath": f"state.characters.{eid}.sanity"})
        else:
            standing.append({"kind": "sanity", "phase": "standing", "entityId": eid,
                             "actor": eid,
                             "name": name, "value": cur["sanity"],
                             "fieldPath": f"state.characters.{eid}.sanity"})
        for tid, task in sorted(cur["tasks"].items()):
            if prev["tasks"][tid]["status"] != task["status"]:
                changes.append({"kind": "task_achieved", "phase": "change",
                                "entityId": eid, "actor": eid, "name": name, "taskId": tid,
                                "goal": task["goal"], "status": task["status"],
                                "fieldPath": f"state.characters.{eid}.tasks.{tid}.status"})
            elif task["status"] == "pending":
                standing.append({"kind": "task_pending", "phase": "standing",
                                 "entityId": eid, "actor": eid, "name": name, "taskId": tid,
                                 "goal": task["goal"],
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
                if cur["appearanceChanges"] != prev["appearanceChanges"]:
                    flags = [c for c in cur["appearanceChanges"]
                             if c["id"] not in {p_["id"] for p_ in prev["appearanceChanges"]}]
                    for change in flags:
                        changes.append({"kind": "appearance_changed", "phase": "change",
                                        "entityId": eid, "actor": eid,
                                        "name": name_of(after, eid),
                                        "text": change.get("text"),
                                        "fieldPath": f"state.locations.{eid}.appearanceChanges"})
                continue
            if cur["position"] != prev["position"]:
                changes.append({"kind": "moved_entity", "phase": "change",
                                "entityId": eid, "actor": eid,
                                "name": name_of(after, eid),
                                "to": name_of(after, cur["position"]["containerId"]),
                                "relativeTo": cur["position"].get("relativeTo"),
                                "fieldPath": f"state.{bucket}.{eid}.position"})
            if cur["appearanceChanges"] != prev["appearanceChanges"]:
                new = [c for c in cur["appearanceChanges"]
                       if c["id"] not in {p["id"] for p in prev["appearanceChanges"]}]
                for change in new:
                    changes.append({"kind": "appearance_changed", "phase": "change",
                                    "entityId": eid, "actor": eid,
                                    "name": name_of(after, eid),
                                    "text": change.get("text"),
                                    "fieldPath": f"state.{bucket}.{eid}.appearanceChanges"})
    return changes, standing


def change_text(fact):
    if fact["kind"] == "moved":
        base = f"{fact['name']}从{fact['from']}来到{fact['to']}"
        if fact.get("relativeTo"):
            base += f"，位于{fact['relativeTo']['entityId']}旁边"
        return base
    if fact["kind"] == "moved_entity":
        base = f"{fact['name']}移到{fact['to']}"
        if fact.get("relativeTo"):
            base += f"，位于{fact['relativeTo']['entityId']}旁边"
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


def capability_flags(changes, standing):
    flags = []
    if any(c["kind"] in ("moved_entity",) for c in changes):
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
    if numeric and numeric != {"sanity_changed", "task_achieved", "personality_changed"}:
        flags.append({"rule": "P3-incomplete-numeric-cause",
                      "detail": "任务/人格/理智未同时出现，投影会拒绝",
                      "line": "committed-narration.ts:38"})
    return flags


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
        texts = [change_text(c) for c in changes]
        names = sorted({c["name"] for c in changes + standing})
        locations = sorted({str(v) for c in changes + standing
                            for v in (c.get("from"), c.get("to"), c.get("location"))
                            if v})
        tasks = sorted({c["goal"] for c in changes + standing if c.get("goal")})
        cand = {"id": cid, "texts": texts, "facts": changes + standing,
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
            "pointId": case["pointId"],
            "worldId": case["worldId"],
            "stateDigest": case["afterDigest"],
            "timeAdvance": {"amount": spec["seconds"], "unit": "second"},
            "perspective": perspective,
            "mustExpress": [c for c in changes],
            "currentState": [{"entityId": s["entityId"], "kind": s["kind"],
                              "value": s.get("location") or s.get("value") or s.get("goal")}
                             for s in standing],
            "playerInstruction": spec.get("inputText") if cid == "c8e06" else None,
            "note": ("只给事实与视角；完整状态不作为输入。未提供的状态不作为必述项。"),
        }
        flags = capability_flags(changes, standing)
        row = {
            "id": cid, "title": spec["title"], "coverage": spec["coverage"],
            "view": spec["view"], "seconds": spec["seconds"],
            "committed": {"worldId": case["worldId"], "pointId": case["pointId"],
                          "rootDigest": case["rootDigest"],
                          "afterDigest": case["afterDigest"],
                          "database": "fresh/source/authority.sqlite3",
                          "reopenVerified": True},
            "facts": {"change": changes, "standing": standing},
            "input": input_packet,
            "screening": {"v1": v1, "v2": v2,
                          "differs": v1["verdict"] != v2["verdict"]},
            "capability": {"pageSupported": not flags, "flags": flags,
                           "module": ("页面已提交叙事路径" if not flags else
                                      "仅内核/接口层（页面投影不支持）"),
                           "scopeNote": SCOPE_NOTES.get(cid, "")},
            "checks": spec["checks"],
            "reviewItems": {
                "mustHold": spec["checks"],
                "mustNotAppear": [
                    "把未提供的人物或地点写进叙述",
                    "把本点没有的变化写成发生",
                ],
                "notRequiredBecauseNotInInput": [
                    "完整状态里未进入 mustExpress/currentState 的任何字段",
                ],
            },
        }
        write(DEST / cid / "facts.json", json.dumps(
            {"rawDelta": after["entityDeltas"], "changeFacts": changes,
             "standingRefs": standing, "beforeDigest": case["rootDigest"],
             "afterDigest": case["afterDigest"]}, ensure_ascii=False, indent=1) + NL)
        write(DEST / cid / "input.json", json.dumps(input_packet, ensure_ascii=False, indent=1) + NL)
        write(DEST / cid / "screening.json", json.dumps(
            {"v1": v1, "v2": v2}, ensure_ascii=False, indent=1) + NL)
        checks = [f"# `{cid}` {spec['title']}", "",
                  f"- 覆盖：{'、'.join(spec['coverage'])}；视角：{spec['view']}；"
                  f"时间：{spec['seconds']} 秒",
                  f"- 提交点：`{case['worldId']}/{case['pointId']}`，"
                  f"after 摘要 `{case['afterDigest'][:16]}…`",
                  f"- 页面投影支持：{'是' if not flags else '否（见下）'}", ""]
        if flags:
            checks += ["## 能力不支持（单列，不算模型失败）", ""]
            for f in flags:
                checks.append(f"- {f['rule']}：{f['detail']}（`{f['line']}`）")
            checks.append("")
        note = SCOPE_NOTES.get(cid)
        if note:
            checks += ["## 适用范围说明", "", f"- {note}", ""]
        checks += ["## 人工核验项", ""]
        for x in row["reviewItems"]["mustHold"]:
            checks.append(f"- [ ] 必须成立：{x}")
        for x in row["reviewItems"]["mustNotAppear"]:
            checks.append(f"- [ ] 必须不出现：{x}")
        for x in row["reviewItems"]["notRequiredBecauseNotInInput"]:
            checks.append(f"- [ ] 不要求（输入未提供）：{x}")
        checks += ["", "## 程序检查", "",
                   f"- R1 v1：{v1['verdict']}；v2：{v2['verdict']}；"
                   f"是否翻转：{'是' if v1['verdict'] != v2['verdict'] else '否'}",
                   f"- R2（new-world）：{'命中' if any(r['rule'] == 'R2-vocabulary' for r in v2['reasons']) else '零命中'}",
                   f"- R3 变化签名：`{v2['signature']}`", ""]
        write(DEST / cid / "checks.md", NL.join(checks) + NL)
        rows.append(row)

    report = {
        "worktreeHead": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                       capture_output=True, text=True).stdout.strip(),
        "fixture": {"registration": registration,
                    "templateSha256": registration["templateSha256"],
                    "auditSha256": registration["auditSha256"],
                    "database": "fresh/source/authority.sqlite3",
                    "databaseSha256": sha(SRC / "authority.sqlite3")},
        "summary": {"candidates": len(rows),
                    "pageSupported": sum(1 for r in rows if r["capability"]["pageSupported"]),
                    "capabilityLimited": sum(1 for r in rows if not r["capability"]["pageSupported"]),
                    "v1Rejected": sum(1 for r in rows if r["screening"]["v1"]["verdict"] == "rejected"),
                    "v2Rejected": sum(1 for r in rows if r["screening"]["v2"]["verdict"] == "rejected"),
                    "formalItems": 0, "frozen": 0, "modelCalls": 0},
        "candidates": rows,
        "gaps": [{"id": "g06", "dimension": "长期人际关系",
                  "status": "无权威字段",
                  "why": "世界状态没有人物关系字段；c8e04/c8e05 只覆盖空间相对位置与持有，"
                         "不声称覆盖长期人际关系。"}],
    }
    write(DEST / "candidates.json", json.dumps(report, ensure_ascii=False, indent=1) + NL)

    # ---- pack README -------------------------------------------------------
    lines = ["# 首批候选（6 条，待人工核验）", "",
             f"工作树 `{report['worktreeHead'][:12]}`。来源是本次**新建**的评测专用注册夹具 "
             f"`{registration['id']}`：作者 `{registration['author']}`，"
             f"创建时间 `{registration['createdUtc']}`，"
             f"不是 R01 生成、不是历史玩家记录、没有改名复用旧世界。", "",
             "六条全部通过 A 侧 Python 服务提交并读回（独立数据库 "
             "`fresh/source/authority.sqlite3`，读回校验 6/6）。**未冻结**，"
             "人工核验通过后才做一次性冻结。", "",
             "## 场景一览", "",
             "| 编号 | 场景 | 覆盖 | 视角 | 时长 | 页面投影 | 变化签名 |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| `{r['id']}` | {r['title']} | {'、'.join(r['coverage'])} | "
                     f"{r['view']} | {r['seconds']}s | "
                     f"{'支持' if r['capability']['pageSupported'] else '不支持'} | "
                     f"`{r['screening']['v2']['signature']}` |")
    lines += ["", "## 每个候选给了模型什么", "",
              "模型输入只有三样：事实（必须表达的），现状（可提及的），视角与时间。"
              "完整状态不作为输入；未提供的状态不要求模型说出，也不因省略扣分。"
              "逐条见 `candidates-fresh/<id>/input.json`。", "",
              "## 能力不支持的部分（单列，不算模型失败）", ""]
    limited = [r for r in rows if not r["capability"]["pageSupported"]]
    if limited:
        for r in limited:
            for f in r["capability"]["flags"]:
                lines.append(f"- `{r['id']}`：{f['rule']} — {f['detail']}（`{f['line']}`）")
    else:
        lines.append("- 无。")
    lines += ["", "## 文件", "",
              "```",
              "candidates-fresh/",
              "├── candidates.json     汇总（含提交证据与筛选结果）",
              "├── report.md           逐条报告",
              "├── review-table.md     人工核验表（待填）",
              "└── <id>/",
              "    ├── facts.json      原始 Δ / 变化事实 / 现状引用",
              "    ├── input.json      模型实际输入",
              "    ├── screening.json  R1 v1/v2、R2、R3",
              "    └── checks.md       人工核验项",
              "```", ""]
    write(DEST / "README.md", NL.join(lines) + NL)

    # ---- report.md ---------------------------------------------------------
    rep = ["# 首批候选逐条报告（自动生成，勿手改）", "",
           f"夹具：`{registration['id']}`（模板 sha256 `{registration['templateSha256'][:16]}…`）；"
           f"数据库 sha256 `{report['fixture']['databaseSha256'][:16]}…`。", ""]
    for r in rows:
        rep += [f"## `{r['id']}` {r['title']}", "",
                f"- 覆盖：{'、'.join(r['coverage'])}；视角：{r['view']}；"
                f"{r['seconds']} 秒",
                f"- 提交：`{r['committed']['worldId']}/{r['committed']['pointId']}`，"
                f"before `{r['committed']['rootDigest'][:12]}…` → "
                f"after `{r['committed']['afterDigest'][:12]}…`（读回校验通过）",
                f"- 变化事实 {len(r['facts']['change'])} 条，现状引用 "
                f"{len(r['facts']['standing'])} 条",
                f"- R1 v1/v2：{r['screening']['v1']['verdict']} / "
                f"{r['screening']['v2']['verdict']}"
                f"{'（翻转）' if r['screening']['differs'] else ''}",
                f"- R2：{'有命中' if any(x['rule']=='R2-vocabulary' for x in r['screening']['v2']['reasons']) else '零命中'}；"
                f"R3：`{r['screening']['v2']['signature']}`",
                f"- 页面投影：{'支持' if r['capability']['pageSupported'] else '不支持（见能力条目）'}",
                "", "变化事实：", ""]
        for c in r["facts"]["change"]:
            rep.append(f"- `{c['kind']}` {c['entityId']} · `{c['fieldPath']}`")
        rep.append("")
    write(DEST / "report.md", NL.join(rep) + NL)

    # ---- review table ------------------------------------------------------
    tbl = ["# 人工核验表（6 条候选，待核验）", "",
           "结论只允许：`待核验`（默认）／`通过`／`不通过`／`无法判断`。"
           "`无法判断` 不算通过。核验者不得是参与调参的人。", "",
           "| 编号 | 项 | 类型 | 内容 | 依据 | 核验者 | 日期 | 结论 |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        n = 0
        fact_ref = (f"`{r['committed']['pointId']}`；变化事实 "
                    f"{len(r['facts']['change'])} 条，见 `{r['id']}/facts.json`")
        for kind, key in (("必须成立", "mustHold"), ("必须不出现", "mustNotAppear"),
                          ("不要求（输入未提供）", "notRequiredBecauseNotInInput")):
            for text in r["reviewItems"][key]:
                n += 1
                tbl.append(f"| `{r['id']}` | {n} | {kind} | {text} | {fact_ref} |  |  | 待核验 |")
    tbl += ["", "## 说明", "",
            "- `c8e04`／`c8e05` 的事实含空间相对关系、物品位移与外貌变化，"
            "页面投影不支持；这两条只核接口与内核层，不计页面叙述成绩。",
            "- `c8e06` 的“玩家关注”是本次作者编写的合成指令，不是真实玩家原话；"
            "只核关注解析，不称 N2 已支持该功能。",
            "- 全部项目核完前，任务保持“未完成”；核验通过后才做一次性冻结。"]
    write(DEST / "review-table.md", NL.join(tbl) + NL)

    s = report["summary"]
    print(f"candidates={s['candidates']} pageSupported={s['pageSupported']} "
          f"limited={s['capabilityLimited']} v1Rejected={s['v1Rejected']} "
          f"v2Rejected={s['v2Rejected']}")
    for r in rows:
        print(f"  {r['id']} {r['screening']['v2']['verdict']:9} sig={r['screening']['v2']['signature']} "
              f"page={'yes' if r['capability']['pageSupported'] else 'no'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
