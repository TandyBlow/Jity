"""Build the C8 diagnostic-fixture deliverable.

For each of the six diagnostics:
  1. build the before state from the registered fixture and check the digest;
  2. apply every point with the A-side kernel (read-only import);
  3. split facts by provenance: raw delta changes vs standing references;
  4. compute both signatures (change-only = the unified standard, full = the
     earlier one that counted standing items);
  5. run R1 v1 and R1 v2 separately, plus R2/R3, and record the difference;
  6. check projection support against the rule table read from
     committed-narration.ts (pinned by hash).

Outputs (diagnostics/):
  report.json / report.md      kernel + facts + signatures + both verdicts
  rule-diff.md                 v1 vs v2 per item, with hit details
  fact-provenance.json / .md   raw delta / change facts / standing references
  gaps.md                      projection gaps for the owning module
  review-table.md              human review table (annotator columns empty)

Usage: python artifacts/world-components/fresh-eval/tools/build_diagnostics.py
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
MAIN_TREE = REPO.parents[2]
FIXTURE = "design/world-protocol/v1/fixtures/school.initial-state.json"
COMMITTED_TS = "frontend/src/lib/world-engine/runtime/committed-narration.ts"
ROOT_DIGEST = "9301b7992248a972f78706c34f56b6b6834f4ce7283c48159589ceca949079a5"

_spec = importlib.util.spec_from_file_location("screening", HERE / "screening.py")
screening = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(screening)

TIME_CN = ["零", "一", "两", "三", "四", "五", "六", "七", "八", "九", "十"]
UNIT_CN = {"second": "秒", "minute": "分钟", "hour": "小时", "day": "天",
           "month": "个月", "year": "年"}
NL = chr(10)


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_kernel():
    sys.path.insert(0, str(MAIN_TREE / "backend"))
    from app.schemas.world.contracts import TimelinePoint, WorldInitialState
    from app.services.world.apply import apply_point
    from app.services.world.state import build_initial_state, state_digest
    import app.services.world.violations as violations
    return dict(WorldInitialState=WorldInitialState, TimelinePoint=TimelinePoint,
                apply_point=apply_point, build_initial_state=build_initial_state,
                state_digest=state_digest, violation=violations.KernelViolation)


def time_text(t):
    amt = t["amount"]
    return f"{TIME_CN[amt] if amt <= 10 else amt}{UNIT_CN[t['unit']]}"


def point_facts(before, after, delta, initial):
    """Split this point's facts by provenance.

    changes  : produced by the raw delta (moved / task / personality / sanity_changed)
    standing : readings of entities the delta did not touch (at / plain sanity)
    """
    changes, standing = [], []
    for eid in sorted(after.characters):
        cur, prev = after.characters[eid], before.characters.get(eid)
        name = initial.characters[eid].name
        loc_id = cur.position.containerId
        loc = initial.locations[loc_id].name
        d = delta.get(eid) or {}
        if "positionSet" in d and d["positionSet"] is not None and prev:
            frm_id = prev.position.containerId
            changes.append({"kind": "moved", "actorId": eid, "name": name,
                            "from": initial.locations[frm_id].name, "to": loc,
                            "fieldPath": f"characters.{eid}.position.containerId",
                            "fromValue": frm_id, "toValue": loc_id})
        else:
            standing.append({"kind": "at", "actorId": eid, "name": name,
                             "location": loc,
                             "fieldPath": f"characters.{eid}.position.containerId",
                             "value": loc_id})
        if "sanitySet" in d and d["sanitySet"] is not None and prev:
            changes.append({"kind": "sanity_changed", "actorId": eid, "name": name,
                            "from": prev.sanity, "to": cur.sanity,
                            "fieldPath": f"characters.{eid}.sanity",
                            "fromValue": prev.sanity, "toValue": cur.sanity})
            for tid in d.get("tasksAchieved") or []:
                changes.append({"kind": "task_achieved", "actorId": eid, "name": name,
                                "taskId": tid, "goal": cur.tasks[tid].goal,
                                "fieldPath": f"characters.{eid}.tasks.{tid}.status",
                                "fromValue": "pending", "toValue": "achieved"})
            for ch in d.get("personalityChanges") or []:
                changes.append({"kind": "personality_changed", "actorId": eid,
                                "name": name, "changeId": ch["id"],
                                "text": ch["text"],
                                "fieldPath": f"characters.{eid}.personalityChanges",
                                "toValue": ch["id"]})
        else:
            standing.append({"kind": "sanity", "actorId": eid, "name": name,
                             "value": cur.sanity,
                             "fieldPath": f"characters.{eid}.sanity",
                             "rawValue": cur.sanity})
    return changes, standing


def projection_problems(after, delta):
    problems = []
    for eid, d in delta.items():
        d = d or {}
        if d.get("appearanceChanges"):
            problems.append("P2-appearance-change")
        if d.get("subtasksAdded"):
            problems.append("P2-subtask-added")
        if any(k in d for k in ("sanitySet", "tasksAchieved", "personalityChanges")) and not all(
                k in d for k in ("sanitySet", "tasksAchieved", "personalityChanges")):
            problems.append("P3-incomplete-numeric-cause")
        ent = after.characters.get(eid)
        if ent and (ent.position.slotId is not None or ent.position.relativeTo is not None):
            problems.append("P4-position-slot-or-relative")
    return sorted(set(problems))


def snapshot(state):
    return {"time": state.time.dateTime,
            "characters": {eid: {"position": c.position.containerId,
                                 "sanity": c.sanity,
                                 "tasks": {t: v.status for t, v in sorted(c.tasks.items())}}
                           for eid, c in sorted(state.characters.items())}}


def apply_points(item, before0, kernel):
    state, prev_id, steps = before0, "root_0", []
    for seq, pt in enumerate(item["points"], start=1):
        payload = {"worldId": "world_school", "id": pt["id"], "sequence": seq,
                   "kind": "normal", "previousPointId": prev_id, "roundId": "round_1",
                   "advanceId": "advance_1", "trigger": "player", "linkedFromPointId": None,
                   "timeAdvance": {"boundary": "elapsed",
                                   "duration": {"amount": pt["time"]["amount"],
                                                "unit": pt["time"]["unit"]}},
                   "entityDeltas": pt["delta"]}
        try:
            point = kernel["TimelinePoint"].model_validate(payload)
            after = kernel["apply_point"](state, point)
            err = None
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}".split(NL)[0][:200]
            after = None
        if after is None:
            steps.append({"pointId": pt["id"], "kernel": "violation", "error": err})
            break
        changes, standing = point_facts(state, after, pt["delta"], state.initial)
        steps.append({
            "pointId": pt["id"], "kernel": "ok",
            "before": snapshot(state), "after": snapshot(after),
            "stateDigestAfter": kernel["state_digest"](after),
            "timeAdvance": time_text(pt["time"]),
            "rawDelta": pt["delta"],
            "changeFacts": changes,
            "standingRefs": standing,
            "changeSignature": screening.change_signature(changes, pt["time"]),
            "fullSignature": screening.full_signature(changes + standing, pt["time"]),
            "projectionProblems": projection_problems(after, pt["delta"]),
        })
        state, prev_id = after, pt["id"]
    return steps


def main() -> int:
    data = json.loads((OUT / "diagnostics/diagnostics.json").read_text(encoding="utf-8"))
    corpus, vocab, scope = screening.load_sources()
    signatures = {sig: list(ids) for sig, ids in scope["signatureOwners"].items()}
    prov_path = OUT / "sources/three-arm-provenance.json"
    basis = {}
    if prov_path.exists():
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
        basis = {row["id"]: row["basis"] for row in prov["items"]}
    kernel = load_kernel()

    fixture_path = REPO / FIXTURE
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    initial = kernel["WorldInitialState"].model_validate(fixture["initial"])
    before0 = kernel["build_initial_state"](initial)
    digest0 = kernel["state_digest"](before0)

    rows = []
    for item in data["items"]:
        steps = apply_points(item, before0, kernel)
        checks = []
        for st in steps:
            if st["kernel"] != "ok":
                continue
            cand = {"id": f"{item['id']}:{st['pointId']}",
                    "texts": [_change_text(f) for f in st["changeFacts"]],
                    "facts": st["changeFacts"] + st["standingRefs"],
                    "time": _time_of(item, st["pointId"])}
            checks.append({"pointId": st["pointId"],
                           "screening": screening.screen_both(
                               cand, corpus, vocab, signatures,
                               mode="source-bound", basis=basis)})
        rows.append({
            "id": item["id"], "title": item["title"], "module": item["module"],
            "kind": item["kind"],
            "statuses": {
                "sourceBinding": (f"registered-fixture {FIXTURE} "
                                  f"sha256 {sha256(fixture_path)[:16]}… state root_0 "
                                  f"digest {digest0[:16]}…"),
                "kernelValidation": ("accepted by apply_point"
                                     if all(s["kernel"] == "ok" for s in steps)
                                     else "violation"),
                "commitStatus": ("not-committed: hypothetical point, no "
                                 "round/group/settle/points record"),
                "independence": ("undetermined: fixture vocabulary appears in corpora and "
                                 "archives; no evidence shows these points were excluded "
                                 "from training or tuning"),
            },
            "declaredParameters": item["declaredParameters"],
            "reviewChecks": item["reviewChecks"],
            "points": steps,
            "screening": checks,
        })

    sig_owners = {}
    for i in scope["threeArmItems"]:
        sig_owners.setdefault(i["signature"], []).append(i["id"])
    old_collisions = {sig: ids for sig, ids in sig_owners.items() if len(ids) > 1}

    diag_collisions = []
    for row in rows:
        for chk in row["screening"]:
            for reason in chk["screening"]["v2"]["reasons"]:
                if reason["rule"] == "R3-signature":
                    diag_collisions.append({"item": row["id"], "point": chk["pointId"],
                                            "signature": reason["signature"],
                                            "matches": reason["matches"]})

    report = {
        "worktreeHead": git_head(),
        "positioning": data["positioning"],
        "kernelSource": {"tree": "main (world-server checkout, read-only import)",
                         "applyPySha256": sha256(MAIN_TREE / "backend/app/services/world/apply.py"),
                         "applyHead": git_head(MAIN_TREE)},
        "fixture": {"file": FIXTURE, "sha256": sha256(fixture_path),
                    "rootDigest": digest0,
                    "matchesCommittedRoot": digest0 == ROOT_DIGEST},
        "projectionRuleSource": {
            "file": COMMITTED_TS, "sha256": sha256(REPO / COMMITTED_TS),
            "how": "人工阅读 TS 的 throw 分支写成规则表；未执行 TS 代码",
            "rules": {
                "P1-non-character-delta": "地点或物品有任何变化 → unsupported_narration_world_change（第 28 行）",
                "P2-appearance-change": "人物外貌变化 → unrecorded_appearance_change（第 51 行）",
                "P2-subtask-added": "delta 含 subtasksAdded → unsupported_committed_delta（第 35 行）",
                "P3-incomplete-numeric-cause": "任务/人格/理智未同时出现 → narration_requires_complete_numeric_cause（第 38 行）",
                "P4-position-slot-or-relative": "position 带槽位或相对关系 → unsupported_narration_position（第 49 行）",
            },
        },
        "signatureStandard": {
            "used": "change-only：只统计本点原始 Δ 产生的事实；现状读数不进签名",
            "time": "时长折算秒数后比较（保留）",
            "oldItemCollisions": old_collisions,
            "diagnosticCollisions": diag_collisions,
        },
        "summary": {"diagnostics": len(rows), "formalItems": 0,
                    "kernelAccepted": sum(1 for r in rows
                                          if r["statuses"]["kernelValidation"].startswith("accepted")),
                    "frozen": 0},
        "items": rows,
        "gaps": json.loads((OUT / "diagnostics/gaps.json")
                           .read_text(encoding="utf-8"))["gaps"],
    }
    screening.write_artifact(OUT / "diagnostics/report.json",
                             json.dumps(report, ensure_ascii=False, indent=1) + NL)

    write_report_md(report, rows, fixture_path, digest0, old_collisions, diag_collisions,
                    basis)
    write_rule_diff(rows)
    write_fact_provenance(rows)
    write_gaps()
    write_review_table(data)
    write_review_packets(rows, data)
    write_expectation_review(rows)
    write_grader_handoff(rows)

    accepted = report["summary"]["kernelAccepted"]
    print(f"head={report['worktreeHead'][:12]} diagnostics={len(rows)} "
          f"kernelAccepted={accepted}/{len(rows)} formalItems=0 "
          f"oldCollisions={len(old_collisions)} diagCollisions={len(diag_collisions)}")
    for row in rows:
        for c in row["screening"]:
            s1, s2 = c["screening"]["v1"], c["screening"]["v2"]
            flag = " DIFF" if c["screening"]["differs"] else ""
            print(f"  {row['id']}/{c['pointId']} v1={s1['verdict']}"
                  f"{[r['rule'] for r in s1['reasons']]} v2={s2['verdict']}"
                  f"{[r['rule'] for r in s2['reasons']]}{flag} sig={s2['signature']}")
    return 0


# ------------------------------------------------------------------ docs ----
def write_report_md(report, rows, fixture_path, digest0, old_collisions, diag_collisions,
                    basis):
    lines = ["# 六条诊断夹具核验报告（自动生成，勿手改）", "",
             f"工作树 HEAD：`{report['worktreeHead'][:12]}`；脚本 `tools/build_diagnostics.py`。", "",
             "**定位**：六条诊断夹具、零条正式独立评测题、未冻结。内核通过只说明增量被接受，"
             "不说明该点已提交，也不说明它未参与训练或调参。", "",
             "**本轮范围**：没有模型输出，也没有人工结论。核验只到“题目与预期是否成立”，"
             "未核项一律记 `待核验`；不运行模型、不追加候选。", "",
             "**通则**：模型只对给定输入负责——输入未提供的状态不作为必述项，"
             "也不因省略扣分；超出输入支持的断言可以判“没有依据”。", "",
             "**两条不能外推的结论**：R3 自检通过只证明规则按当前口径工作，"
             "**不证明**历史变化事实可靠（十条旧题的依据全部 `undetermined`），"
             "**也不证明**任何新题独立。", "",
             f"绑定来源：`{FIXTURE}`（sha256 `{sha256(fixture_path)[:16]}…`），"
             f"根点摘要 `{digest0[:16]}…`，与已提交根点一致："
             f"{'是' if digest0 == ROOT_DIGEST else '否'}。"
             "（这只证明初始状态一致，不证明点位身份或独立性。）", "",
             "| 编号 | 内容 | 模块 | 类型 | 内核 | 投影 | v1 | v2 | 变化签名 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        probs = sorted({p for s in row["points"] for p in s["projectionProblems"]})
        sigs = "；".join(f"{c['pointId']}: `{c['screening']['v2']['signature']}`"
                         for c in row["screening"]) or "—"
        v1 = "；".join(c["screening"]["v1"]["verdict"] for c in row["screening"])
        v2 = "；".join(c["screening"]["v2"]["verdict"] for c in row["screening"])
        lines.append(f"| `{row['id']}` | {row['title']} | {row['module']} | {row['kind']} | "
                     f"{row['statuses']['kernelValidation']} | "
                     f"{', '.join(probs) or '全部支持'} | {v1} | {v2} | {sigs} |")
    lines += ["", "## 三个状态分别记录", ""]
    for row in rows:
        st = row["statuses"]
        lines += [f"### `{row['id']}`", "",
                  f"- 来源绑定：{st['sourceBinding']}",
                  f"- 内核校验：{st['kernelValidation']}",
                  f"- 提交状态：{st['commitStatus']}",
                  f"- 独立性：{st['independence']}", ""]
    lines += ["## 人工指定的参数", ""]
    for row in rows:
        lines.append(f"- `{row['id']}`：{'；'.join(row['declaredParameters'])}")
    lines += ["", "## 签名口径", "",
              f"- 采用：{report['signatureStandard']['used']}",
              f"- 时间：{report['signatureStandard']['time']}", ""]
    if old_collisions:
        lines.append("- **旧题内部同形**（变化口径无法区分）：")
        for sig, ids in old_collisions.items():
            lines.append(f"    - `{sig}` ← {', '.join(ids)}")
    if diag_collisions:
        lines.append("- **诊断夹具与旧题同形（口径同形，不写作派生）**：")
        for c in diag_collisions:
            basis_note = "旧题变化依据 undetermined" if all(
                (basis.get(m) == "undetermined") for m in c["matches"]) else "旧题有权威读取"
            lines.append(f"    - `{c['item']}` / `{c['point']}` 的 `{c['signature']}` "
                         f"等于 {', '.join('`'+m+'`' for m in c['matches'])}（{basis_note}）")
    else:
        lines.append("- 诊断夹具与旧题无变化签名重合。")
    lines += ["", "## 边界", "",
              "- 叙事事实是按 TS 规则在 Python 里重写的镜像，不是执行 TS；"
              "投影是否真的接受仍需在该路径上跑一次。",
              "- 本批全部为假设点，没有提交记录；不得用于任何独立性与能力结论。",
              "- 未冻结；未做人工核验（表见 `review-table.md`，逐条材料见 `review-packets.md`）。",
              "- 旧题的变化事实依据全部 `undetermined`（见 `sources/three-arm-provenance.md`）："
              "签名相同只说明“按当前转换口径同形”。",
              "- 预期复核见 `expectation-review.md`：两条预期目前只能人工判定。",
              "- `nv-task-only-1` 是手写包与生产投影的输入契约不一致（`gaps.md` g05）："
              "这解释该包不能代表页面生产路径，但不豁免输出判分——明确给定事实包时，"
              "模型写错事实仍记输出错误；两者分开记账。",
              "- 判分缺口（理智方向、全部完成类总结句）已交维护方，见 `grader-handoff.md`。"]
    screening.write_artifact(OUT / "diagnostics/report.md", NL.join(lines) + NL)


def write_rule_diff(rows):
    lines = ["# R1 两版规则与逐条判定差异（自动生成，勿手改）", "", "## 版本", "",
             "| 版本 | 定义 | 何时出现 |", "|---|---|---|",
             "| **v1** | 候选正文（≥4 汉字）与排除串任一方向包含即命中；剥注记变体同样比对 | 首次筛候选时使用 |",
             "| **v2** | 相等→命中；候选被排除串包含→命中；排除串被候选包含时，"
             "仅当该排除串 ≥8 汉字才命中，更短记 `R1-short-phrase` | **看过候选之后**才写，属事后规则变更 |",
             "", "两版都保留时间归一化（R3 折算秒数），差异只在 R1。", "",
             "## 逐条判定", "",
             "| 项 | 点 | v1 | v1 命中 | v2 | v2 命中 | 差异 |", "|---|---|---|---|---|---|---|"]
    for row in rows:
        for chk in row["screening"]:
            a, b = chk["screening"]["v1"], chk["screening"]["v2"]
            ra = ", ".join(r["rule"] for r in a["reasons"]) or "无"
            rb = ", ".join(r["rule"] for r in b["reasons"]) or "无"
            lines.append(f"| `{row['id']}` | {chk['pointId']} | {a['verdict']} | {ra} | "
                         f"{b['verdict']} | {rb} | "
                         f"{'**不同**' if chk['screening']['differs'] else '相同'} |")
    lines += ["", "## 差异明细", ""]
    shown = False
    for row in rows:
        for chk in row["screening"]:
            if not chk["screening"]["differs"]:
                continue
            shown = True
            v1 = chk["screening"]["v1"]
            lines.append(f"- `{row['id']}` / `{chk['pointId']}`：v1 判 {v1['verdict']}，"
                         f"v2 判 {chk['screening']['v2']['verdict']}")
            for reason in v1["reasons"]:
                if reason["rule"] == "R1-substring":
                    for h in reason["hits"][:3]:
                        lines.append(f"    - v1 命中：候选句 `{h['candidateText'][:44]}` "
                                     f"含排除串 `{h['excluded'][:20]}`"
                                     f"（来源 {','.join(h['sources'])}）")
    if not shown:
        lines.append("- 无差异。")
    lines += ["", "## 首跑结果（事后无法复原的部分）", "",
              "首次筛这六条时用的是 **R1 v1 + 全包签名**（现状读数也进签名），当时输出为："
              "`candidate=0 fixtureBound=6 rejected=0`——六条全部通过，一条也没被拦。"
              "那次只有控制台摘要，没有单独存成文件；本表的 v1 列是**按 v1 的 R1 规则重跑**的结果，"
              "但签名已换成变化口径，所以 v1 列不是当时那次运行的逐字复现。",
              "",
              "改口径后出现两处翻转，都记在下面：",
              "- `c8d04`：v1 的 R1 判 rejected，v2 放行（规则变更造成）。",
              "- `c8d06_p2`：全包签名下不撞旧题，变化口径下与 `nv-cont-2` 同形（`none|0|120s`）而判 rejected。",
              "", "## 结论口径", "",
              "- v2 是看过候选之后写的，**不能用 v2 的结果证明候选自身独立**。",
              "- 本批在 v1 下 1 条被拦（c8d04），在 v2 下通过；该差异只作规则开发记录。",
              "- 时间归一化（2 分钟＝120 秒）不属放宽，两版都保留，"
              "并由 `deriv-unit-renamed-300s` 用例守住。"]
    screening.write_artifact(OUT / "diagnostics/rule-diff.md", NL.join(lines) + NL)


def write_fact_provenance(rows):
    doc = {"worktreeHead": git_head(), "items": []}
    lines = ["# 事实来源对账表（自动生成，勿手改）", "",
             "三列分开存：**原始 Δ**（设计者给的变化）、**变化事实**（Δ 产生的叙事事实）、"
             "**现状引用**（未变化实体的读数）。只有变化事实参与签名。", ""]
    for row in rows:
        doc["items"].append({"id": row["id"], "points": [
            {"pointId": s["pointId"], "rawDelta": s["rawDelta"],
             "changeFacts": s["changeFacts"], "standingRefs": s["standingRefs"],
             "changeSignature": s["changeSignature"],
             "fullSignature": s["fullSignature"]}
            for s in row["points"]]})
        lines += [f"## `{row['id']}` {row['title']}", ""]
        for s in row["points"]:
            if s["kernel"] != "ok":
                lines.append(f"- `{s['pointId']}`：内核拒绝（{s['error']}）")
                continue
            lines += [f"### `{s['pointId']}`（{s['timeAdvance']}）", "",
                      f"- 原始 Δ 键：{', '.join(sorted(s['rawDelta'])) or '空'}",
                      f"- 变化事实 {len(s['changeFacts'])} 条："]
            for f in s["changeFacts"]:
                lines.append(f"    - `{f['kind']}` {f['actorId']} · `{f['fieldPath']}` · "
                             f"{f.get('fromValue')} → {f.get('toValue')}")
            lines.append(f"- 现状引用 {len(s['standingRefs'])} 条（不进签名）：")
            for f in s["standingRefs"]:
                lines.append(f"    - `{f['kind']}` {f['actorId']} · "
                             f"`{f['fieldPath']}` = {f.get('value')}")
            lines += [f"- 变化签名：`{s['changeSignature']}`",
                      f"- 全包签名（含现状，仅参考）：`{s['fullSignature']}`", ""]
    screening.write_artifact(OUT / "diagnostics/fact-provenance.json",
                             json.dumps(doc, ensure_ascii=False, indent=1) + NL)
    screening.write_artifact(OUT / "diagnostics/fact-provenance.md",
                             NL.join(lines) + NL)


def write_gaps():
    doc = json.loads((OUT / "diagnostics/gaps.json").read_text(encoding="utf-8"))
    lines = ["# 覆盖缺口：叙事投影（交对应模块处理，c8 不修）", "",
             "每条：合法输入 → 抛错位置 → 影响 → 需要谁改 → 补上之后的要求。", "",
             "| 编号 | 维度 | 抛错 | 影响 |", "|---|---|---|---|"]
    for g in doc["gaps"]:
        lines.append(f"| {g['id']} | {g['dimension']} | `{g['throwPoint']}` | {g['impact']} |")
    lines += ["", "## 明细", ""]
    for g in doc["gaps"]:
        lines += [f"### {g['id']} {g['dimension']}", "",
                  f"- 合法输入：{g['legalInput']}",
                  f"- 触发条件：{g['condition']}",
                  f"- 抛错位置：`{g['throwPoint']}`",
                  f"- 影响：{g['impact']}",
                  *([f"- 账目：{json.dumps(g['accounting'], ensure_ascii=False)}"]
                    if g.get("accounting") else []),
                  f"- 需要：{g['ownerAction']}",
                  f"- 补上之后：{g['afterFix']}",
                  f"- 证据：{g['evidence']}", ""]
    screening.write_artifact(OUT / "diagnostics/gaps.md", NL.join(lines) + NL)


def write_review_table(data):
    """One row per check item, so a reviewer can judge each separately."""
    lines = ["# 人工核验表（六条诊断，逐项，待核验）", "",
             "**本轮没有模型输出**，所以只能核验“题目与预期是否成立”，"
             "不能填写模型表现。结论列只允许：`待核验`（默认）／`通过`／`不通过`／`无法判断`。"
             "`无法判断` 不算通过。", "",
             "核验者不得是参与调参的人。依据一栏要写清引用了哪份材料（夹具路径、字段、行号）。", "",
             "| 编号 | 项 | 类型 | 内容 | 依据（事实／字段） | 核验者 | 日期 | 结论 |",
             "|---|---|---|---|---|---|---|---|"]
    for item in data["items"]:
        binding = item["binding"]
        fields = "、".join(f"`{f}`" for f in binding.get("fieldPaths", [])) or "—"
        base = (f"`{binding['fixture'].split('/')[-1]}` @ `{binding['statePointId']}`；"
                f"字段 {fields}")
        n = 0
        for kind, key in (("必须成立", "mustHold"), ("必须不出现", "mustNotAppear")):
            for text in item["reviewChecks"][key]:
                n += 1
                lines.append(f"| `{item['id']}` | {n} | {kind} | {text} | {base} "
                             f"|  |  | 待核验 |")
    lines += ["", "## 输入未提供、因此不要求模型写出的项", "",
              "这些项**不计入扣分**；只在人工核验里作为说明。", ""]
    for item in data["items"]:
        for text in item["reviewChecks"].get("notRequiredBecauseNotInInput", []):
            lines.append(f"- `{item['id']}`：{text}")
    lines += ["", "## 超出输入支持的断言（可人工判定）", ""]
    for item in data["items"]:
        for text in item["reviewChecks"].get("beyondInputSupport", []):
            lines.append(f"- `{item['id']}`：{text}")
    lines += ["", "## 仅作人工依据（不由判定器判）", ""]
    for item in data["items"]:
        for text in item["reviewChecks"].get("humanEvidenceOnly", []):
            lines.append(f"- `{item['id']}`：{text}")
    lines += ["", "## 逐条提示", "",
              "- `c8d04`：明查**数值方向**（30→26 是下降，不是上升）。"
              "判定器目前不查方向词，所以这一项只能由人给结论。",
              "- `c8d06`：只核**父任务达成是否写对**，以及是否出现**超出输入支持**的"
              "“全部任务完成”类断言。子任务 pending 不在输入里，"
              "**不要求模型写出，也不因省略扣分**；"
              "若核验者用完整状态确认句子与 pending 矛盾，把这条写在“仅作人工依据”里。",
              "- `c8d03`：只核 N2 规则臂的判定与理由，不核页面视角过滤，不计入端到端成绩。",
              "- `c8d05`：时间必述可程序检查；“没有编造”只能部分检查（见 `expectation-review.md`）。",
              "",
              "## 汇总（待人工填写）", "",
              "| 编号 | 已核项 | 通过 | 不通过 | 无法判断 | 待核验 | 备注 |",
              "|---|---|---|---|---|---|---|"]
    for item in data["items"]:
        total = len(item["reviewChecks"]["mustHold"]) + len(item["reviewChecks"]["mustNotAppear"])
        lines.append(f"| `{item['id']}` | 0/{total} | 0 | 0 | 0 | {total} |  |")
    lines += ["", "## 结论口径", "",
              "- 全部项目核完才可把该条从“待核验”移出；缺项按“待核验”记，不合并成“通过”。",
              "- 核验通过不等于可以冻结：来源独立性仍是 `undetermined`。",
              "- 本表不含模型输出；模型表现另开记录，且不得回填到本表。"]
    screening.write_artifact(OUT / "diagnostics/review-table.md", NL.join(lines) + NL)


def write_expectation_review(rows):
    """What the program actually checks, what it does not, what stays human."""
    items = [
        ("c8d01",
         "移动方向（大堂→走廊）；其余五人只写现状",
         "按分句检查 `moved` 的 from/to 是否被写反（`direction_reversed`）；"
         "检查人物名是否被换到别人的事实（`actor_swap`）；"
         "对没有位置事实的站位声明报 `state_claim_without_fact`",
         "只覆盖已知地点名与已登记动词；改写成不含已知地点名的方位描述、"
         "或使用词表外动词的事件，不在检查范围内",
         "“其余五人只写现状”的语义完整性；新增细节是否算编造"),
        ("c8d02",
         "三条移动各自对应、不得互换",
         "同上：逐分句方向检查 + 人物互换检查；同一点多条 `moved` 时每条独立比对",
         "不检查三条移动之间的联合一致性（例如把两个目的地写进同一句、"
         "再靠分句切分绕开），也不检查“多写一条不存在的移动”之外的顺序问题",
         "多人物同句的表达是否仍能逐条对上"),
        ("c8d03",
         "N2 规则臂把视角外移动判为不可见，并记录理由",
         "只做了**辅助函数级**验证：直接调用 `_visibility_ground`，"
         "对 `{kind:moved, entityId:person_a, at:corridor}` 返回 `(False, 'other-location')`",
         "**没有**跑整条 `classify_facts` / N1 抽取 / 选择策略；"
         "事实的 `at` 由上游填充，上游若填错，本验证不覆盖",
         "整条筛选路径的实际输出；理由文案；must/may 的最终集合"),
        ("c8d04",
         "理智必须写成下降（30→26）",
         "`wrong_number` 只检查句中的数字是否属于 `{from, to}`，"
         "即 26、30 两个数字出现任意顺序都通过",
         "**方向词完全没有检查**：“从26升到30”会通过；"
         "改写成“降到 30、原来是 26”之类同样通过",
         "数值方向（升/降）判定；这正是该诊断要人工确认的一项"),
        ("c8d05",
         "必须写出时间流逝；不得编造变化",
         "`timeRequired` + `mentionsTime` 证明**时间要求被检查**（是否提到该时长）；"
         "对已登记地点名的无事实站位、以及词表内动词的无事实事件，会报违规",
         "**不证明“没有编造”**：词表外动词、未登记物件、"
         "不含已知地点名的方位描述都不会被拦；"
         "“没有变化”类总结句也不在检查范围",
         "是否存在检查器不认识的编造；空点叙述是否自然"),
        ("c8d06",
         "第三点只写父任务达成；不得把“两个任务都完成”当作有输入支持的事实",
         "只要句子绑定任意 `task_achieved` 事实即可通过；"
         "未绑定任务事实的完成说法会报 `task_claimed_without_fact`",
         "**输入里没有子任务状态**：事实包只有父任务的 `task_achieved`，"
         "所以不能要求模型写出“子任务仍 pending”，也不能因省略扣分；"
         "不点人物的总结句（“全部任务完成”）被判定器显式排除在范围外",
         "“全部任务完成”是否超出输入支持（人工判定）；"
         "若用完整状态核对出与 pending 矛盾，单列为人工依据，不算模型漏述"),
    ]
    lines = ["# 六条诊断的预期复核（自动生成，勿手改）", "",
             "问题：预期里写的“必须／不得”，现有工具到底检查了哪一部分？"
             "下表按 `narration-alignment.ts`（sha256 309ca19f…）与 "
             "`n2_perspective.py` 的规则逐条对照，并列出剩余交人工的部分。", "",
             "**检查器存在 ≠ 预期被完整覆盖**。下表第三列是“程序实际检查什么”，"
             "第四列是“不覆盖什么”，第五列是“只能交人工的部分”。", "",
             "**一条通则**：模型只对给定输入负责。输入没有提供的事实不得作为必述项，"
             "也不得因省略扣分；超出输入支持的断言可以判，但那是“没有依据”，"
             "不是“与隐藏事实矛盾”。", "",
             "| 项 | 预期 | 程序实际检查什么 | 程序不覆盖什么 | 交人工的部分 |",
             "|---|---|---|---|---|"]
    for item_id, expect, checks, not_covered, human in items:
        lines.append(f"| `{item_id}` | {expect} | {checks} | {not_covered} | {human} |")
    lines += ["", "## 结论", "",
              "- 六条里没有一条是“程序完整覆盖预期”：`c8d01`／`c8d02` 覆盖方向与人物绑定，"
              "但不覆盖改写后的表达完整性；`c8d05` 只覆盖时间必述与部分编造类别；"
              "`c8d03` 只到辅助函数；`c8d04`／`c8d06` 的关键项**完全不可程序判定**。",
              "- 因此复核表里每一格都必须由人给结论；程序结果只能作为参考证据，不能替代。",
              "- 要让 `c8d04`／`c8d06` 可判，得先改判定器（见 `grader-handoff.md`），"
              "改完要重跑受影响的旧题基线并记录判分器版本变化。",
              "", "## 边界", "",
              "- 表中“程序检查什么”来自阅读 TS 与一次 `_visibility_ground` 直接调用，"
              "没有执行整条页面路径。",
              "- 判定器是否在真实输出上误判，仍以实际运行为准；本批没有运行模型。"]
    screening.write_artifact(OUT / "diagnostics/expectation-review.md", NL.join(lines) + NL)


def write_grader_handoff(rows):
    """Two concrete counterexamples for the grader maintainer."""
    by_id = {r["id"]: r for r in rows}

    def facts_of(row_id, point_id=None):
        row = by_id[row_id]
        for st in row["points"]:
            if point_id and st["pointId"] != point_id:
                continue
            return st
        return None

    d04 = facts_of("c8d04")
    d06 = facts_of("c8d06", "c8d06_p3")
    lines = ["# 判分缺口交接（给判定器维护方，自动生成，勿手改）", "",
             "c8 只保留诊断材料，不修改判定器、不修改生产投影。下面两个反例都来自本批诊断的事实包，"
             "可以直接作为回归用例。", "",
             "判定器：`frontend/src/lib/world-engine/runtime/narration-alignment.ts`"
             "（sha256 309ca19f…，本批未运行，结论来自阅读源码）。", "",
             "## 反例一：理智方向写反不被拦", "",
             "**事实包（c8d04 第三点同型，去掉人格/任务后仍成立）**", "",
             "```json",
             json.dumps({"facts": [
                 {"kind": "sanity_changed", "name": "C", "from": 30, "to": 26},
                 {"kind": "at", "name": "C", "location": "一号教室"},
             ], "time": {"amount": 2, "unit": "minute"}}, ensure_ascii=False, indent=1),
             "```", "",
             "**输入句**：`C的精神值从26升到30。`", "",
             "**应判结果**：违规（方向写反：事实是 30→26 下降）。"
             "建议违规种类沿用 `wrong_number` 或新增 `direction_reversed`（sanity 分支）。", "",
             "**当前行为**：通过。`narration-alignment.ts:396-403` 的 `wrong_number` 只检查"
             "句中数字是否属于 `{from, to}`；26 和 30 都在集合里，顺序不被检查。", "",
             "## 反例二：把父任务达成写成“全部任务完成”不被拦", "",
             "**事实包（c8d06 第三点）**", "",
             "```json",
             json.dumps({"facts": d06["changeFacts"], "time": {"amount": 3, "unit": "minute"}},
                        ensure_ascii=False, indent=1),
             "```", "",
             "**输入句**："
             "`C完成了任务「安全度过校园中的这段时间」，校园里的所有任务都完成了。`", "",
             "**应判结果**：违规，理由是**超出输入支持**：事实只支持 `task_c_root` 达成，"
             "“所有任务都完成了”不是本点事实能支持的说法。", "",
             "**不要写成“与事实矛盾”**：子任务 `task_wait_noon` 仍为 pending 这件事"
             "**不在事实包里**（`committed-narration.ts` 只发 `task_achieved`，不发任务状态），"
             "模型也没有拿到它。因此不能要求模型写出这条 pending，也不能因为省略扣分。"
             "“全部完成”与 pending 的矛盾，只能在人工用完整状态核对时单列为依据。", "",
             "**当前行为**：通过。`narration-alignment.ts:439-444` 只要句子里绑上任意 "
             "`task_achieved` 事实就放行；不点人物的总结句（“全部任务完成”）"
             "被第 433 行注释显式排除在检查范围外。", "",
             "**额外问题（契约，不是判定器能单独解决的）**：本批事实包只含父任务的 "
             "`task_achieved`，子任务 pending **根本不在包里**（`committed-narration.ts` 只发"
             " `task_achieved`，不发任务状态）。所以即使判定器加了“全部完成”规则，"
             "也缺一条可核对的 pending 事实。要修需二选一：", "",
             "1. 投影补一条“任务状态”事实（或允许 `task_pending` 类事实），判定器据此比对；",
             "2. 明确产品口径：父任务达成时不允许叙述引申到子任务，按措辞规则（而非事实比对）拦。", "",
             "## 修复后的要求", "",
             "- 两条反例都加成回归用例，必须判违规；本批六条诊断的事实包可直接复用。",
             "- 重跑受影响的旧题基线（至少 `nv-task-pers-sanity-1`、`nv-task-only-1`），"
             "并记录判分器版本变化（文件哈希 + 行为变更说明）。",
             "- 若修改了事实包形状（增加 pending 事实），旧题基线同样要重跑，"
             "并同步更新 `sources/three-arm-provenance.md` 的结论。",
             "- c8 不代改判定器；修复完成后由维护方给出新版本证据，c8 只做引用。",
             ]
    screening.write_artifact(OUT / "diagnostics/grader-handoff.md", NL.join(lines) + NL)


def _time_of(item, point_id):
    for pt in item["points"]:
        if pt["id"] == point_id:
            return pt["time"]
    return {}


def _change_text(f):
    if f["kind"] == "moved":
        return f"{f['name']}从{f['from']}来到{f['to']}"
    if f["kind"] == "task_achieved":
        return f"{f['name']}完成了任务「{f['goal']}」"
    if f["kind"] == "personality_changed":
        return f"{f['name']}的人格变化为「{f['text']}」"
    if f["kind"] == "sanity_changed":
        return f"{f['name']}的精神值从{f['from']}变为{f['to']}"
    return ""


def git_head(path: pathlib.Path = REPO) -> str:
    try:
        return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"




def write_review_packets(rows, data):
    """One packet per diagnostic: source+params, before/Δ/after, facts, checks."""
    by_id = {item["id"]: item for item in data["items"]}
    lines = ["# 六条诊断的人工核验包（自动生成，勿手改）", "",
             "每条给出：来源与参数、before／原始 Δ／after、变化事实与现状引用、"
             "允许与禁止的表述、程序检查结果。标注者、日期、结论留空，由人工填写。", "",
             "`c8d06` 是三个点，按点分节。程序检查里的“投影支持”是按 "
             "`committed-narration.ts` 的规则表判定的（见 report.json 的 projectionRuleSource），"
             "不是执行 TS 的结果。", ""]
    for row in rows:
        item = by_id[row["id"]]
        b = item["binding"]
        lines += [f"## `{row['id']}` {row['title']}", "",
                  f"- 模块：{row['module']}",
                  f"- 类型：{row['kind']}",
                  f"- 来源：`{b['fixture']}`（sha256 `{b['fixtureSha256'][:16]}…`），"
                  f"before 为 `{b['statePointId']}`，摘要 `{b['stateDigest'][:16]}…`",
                  f"- 提交状态：{row['statuses']['commitStatus']}",
                  f"- 独立性：{row['statuses']['independence']}",
                  f"- 人工指定参数：{'；'.join(item['declaredParameters'])}"]
        if "perspective" in b:
            lines.append(f"- 视角：`{b['perspective']['entityId']}` @ `{b['perspective']['at']}`")
        lines += ["", "**允许的表述**", ""]
        for x in item["reviewChecks"]["mustHold"]:
            lines.append(f"- {x}")
        lines += ["", "**禁止的表述**", ""]
        for x in item["reviewChecks"]["mustNotAppear"]:
            lines.append(f"- {x}")
        for key, title in (("notRequiredBecauseNotInInput",
                            "不要求模型写出（输入未提供，不得因省略扣分）"),
                           ("beyondInputSupport", "超出输入支持的断言"),
                           ("humanEvidenceOnly", "仅作人工依据")):
            values = item["reviewChecks"].get(key, [])
            if values:
                lines += ["", f"**{title}**", ""]
                for x in values:
                    lines.append(f"- {x}")
        for step, chk in zip(row["points"], row["screening"]):
            pt = next(p for p in item["points"] if p["id"] == step["pointId"])
            lines += ["", f"### `{step['pointId']}`（{step['timeAdvance']}）", "",
                      "**before**", "",
                      "| 实体 | 位置 | 理智 | 任务 |", "|---|---|---|---|"]
            for eid, st in step["before"]["characters"].items():
                tasks = "、".join(f"{k}={v}" for k, v in st["tasks"].items()) or "—"
                lines.append(f"| {eid} | {st['position']} | {st['sanity']} | {tasks} |")
            lines += ["", "**原始 Δ**", "", "```json",
                      json.dumps(pt["delta"], ensure_ascii=False, indent=1), "```", "",
                      "**after**", "", "| 实体 | 位置 | 理智 | 任务 |", "|---|---|---|---|"]
            for eid, st in step["after"]["characters"].items():
                tasks = "、".join(f"{k}={v}" for k, v in st["tasks"].items()) or "—"
                lines.append(f"| {eid} | {st['position']} | {st['sanity']} | {tasks} |")
            lines += ["", "**变化事实**（进签名）", ""]
            if step["changeFacts"]:
                lines += ["| 种类 | 实体 | 字段 | 从 | 到 |", "|---|---|---|---|---|"]
                for f in step["changeFacts"]:
                    lines.append(f"| {f['kind']} | {f['actorId']} | `{f['fieldPath']}` | "
                                 f"{f.get('fromValue')} | {f.get('toValue')} |")
            else:
                lines.append("（本点没有变化事实）")
            lines += ["", "**现状引用**（不进签名）", ""]
            if step["standingRefs"]:
                lines += ["| 种类 | 实体 | 字段 | 值 |", "|---|---|---|---|"]
                for f in step["standingRefs"]:
                    lines.append(f"| {f['kind']} | {f['actorId']} | `{f['fieldPath']}` | "
                                 f"{f.get('value')} |")
            else:
                lines.append("（无）")
            v1, v2 = chk["screening"]["v1"], chk["screening"]["v2"]
            r3_text = "- R3：" + (
                ", ".join(
                    r["signature"] + " ← " + "/".join(r.get("matches", []))
                    for r in v2["reasons"] if r["rule"] == "R3-signature")
                or "无命中")
            lines += ["", "**程序检查结果**", "",
                      f"- 内核：{step['kernel']}；after 摘要 `{step['stateDigestAfter'][:16]}…`",
                      f"- 投影支持：{'全部支持' if not step['projectionProblems'] else ', '.join(step['projectionProblems'])}",
                      f"- 变化签名：`{step['changeSignature']}`；"
                      f"全包签名（参考）：`{step['fullSignature']}`",
                      f"- R1 v1：{v1['verdict']}；R1 v2：{v2['verdict']}；"
                      f"R2 已登记复用 {len([w for w in v2['warnings'] if w['rule'] == 'R2-registered-overlap'])} 组；",
                      r3_text, ""]
        lines += ["**人工核验记录（待填）**", "",
                  "| 标注者 | 日期 | 结论 | 依据 |", "|---|---|---|---|",
                  "|  |  |  |  |", ""]
    screening.write_artifact(OUT / "diagnostics/review-packets.md", NL.join(lines) + NL)


if __name__ == "__main__":
    sys.exit(main())
