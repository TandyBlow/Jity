"""Provenance check for the ten three-arm items' *change facts*.

Why: the change-only signature assumes each old item's facts describe this
point's own delta. Most of those items are hand-written packets, so that
assumption has to be checked, not assumed.

For every item this script records:
  - the packet's anchor (the samples carry a placeholder digest),
  - the declared facts and the ids they reference,
  - whether those ids exist in the registered fixture,
  - whether any committed point in the registered traces / archives produces the
    same change shape (kinds + actors + seconds),
  - the resulting basis: `authoritative-read` only when a stored committed point
    can be bound by identity; otherwise `undetermined`.

Outputs: sources/three-arm-provenance.json and .md

Usage: python artifacts/world-components/fresh-eval/tools/build_three_arm_provenance.py
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
REPO = OUT.parents[2]
FIXTURE = "design/world-protocol/v1/fixtures/school.initial-state.json"
NL = chr(10)

_spec = importlib.util.spec_from_file_location("screening", HERE / "screening.py")
screening = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_spec and screening)

SEARCH_GLOBS = [
    ("design/world-protocol/v2/traces", "*.json"),
    ("artifacts/rule-facts", "*.json"),
    ("artifacts/world-page", "*.json"),
    ("artifacts/narration-eval", "*.json"),
]


def walk_points(node, out):
    """Collect every dict that looks like a point (entityDeltas + timeAdvance)."""
    if isinstance(node, dict):
        if "entityDeltas" in node and isinstance(node["entityDeltas"], (dict, list)):
            out.append(node)
        for value in node.values():
            walk_points(value, out)
    elif isinstance(node, list):
        for value in node:
            walk_points(value, out)


def point_change_facts(point):
    deltas = point.get("entityDeltas") or {}
    if isinstance(deltas, list):
        deltas = {d.get("entityId"): d for d in deltas if isinstance(d, dict)}
    facts = []
    for eid, d in deltas.items():
        d = d or {}
        if d.get("positionSet") is not None:
            facts.append({"kind": "moved", "actor": eid})
        if d.get("sanitySet") is not None:
            facts.append({"kind": "sanity_changed", "actor": eid})
        for _ in d.get("tasksAchieved") or []:
            facts.append({"kind": "task_achieved", "actor": eid})
        for _ in d.get("personalityChanges") or []:
            facts.append({"kind": "personality_changed", "actor": eid})
    adv = point.get("timeAdvance") or {}
    dur = adv.get("duration") or {}
    return facts, {"amount": dur.get("amount"), "unit": dur.get("unit")}


def parse_items(path):
    text = path.read_text(encoding="utf-8")
    # ANCHOR(...) helper: stateDigest: 'f'.repeat(64) -- shared by every sample
    helper = re.search(r"stateDigest: '([^'])'\.repeat\((\d+)\)", text)
    helper_placeholder = bool(helper)
    helper_digest = (helper.group(1) * int(helper.group(2))) if helper else None
    starts = [m.start() for m in re.finditer(r"id: 'nv-", text)]
    blocks = [text[s:(starts[i + 1] if i + 1 < len(starts) else len(text))]
              for i, s in enumerate(starts)]
    items = []
    for blk in blocks:
        sid = re.search(r"id: '([^']+)'", blk).group(1)
        kinds = re.findall(r"kind: '([a-z_]+)'", blk)
        actors = re.findall(r"actorId: '([^']+)'", blk)
        tm = re.search(r"time: \{ amount: (\d+), unit: '(\w+)' \}", blk)
        anchor_call = re.search(r"anchor: ANCHOR\('([^']+)'\)", blk)
        ids = {
            "actors": sorted(set(actors)),
            "from": sorted(set(re.findall(r"fromId: '([^']+)'", blk))),
            "to": sorted(set(re.findall(r"toId: '([^']+)'", blk))),
            "at": sorted(set(re.findall(r"locationId: '([^']+)'", blk))),
            "tasks": sorted(set(re.findall(r"taskId: '([^']+)'", blk))),
        }
        time = ({"amount": int(tm.group(1)), "unit": tm.group(2)} if tm else {})
        anchor_value = helper_digest
        anchor_placeholder = helper_placeholder
        items.append({"id": sid, "kinds": kinds, "actors": sorted(set(actors)),
                      "anchorDigest": anchor_value,
                      "anchorPlaceholder": anchor_placeholder,
                      "anchorCall": anchor_call.group(1) if anchor_call else None,
                      "ids": ids, "time": time,
                      "changeSignature": screening.change_signature(
                          [{"kind": k, "actor": next((a for a in [actors[i]] if a), None)}
                           for i, k in enumerate(kinds)], time)})
    return items


def main() -> int:
    fixture = json.loads((REPO / FIXTURE).read_text(encoding="utf-8"))["initial"]
    known = {"characters": set(fixture["characters"]),
             "locations": set(fixture["locations"]),
             "items": set(fixture["items"])}
    tasks = {tid for ch in fixture["characters"].values() for tid in ch.get("tasks", {})}

    # committed points from the registered traces and archives
    committed = []
    for rel, pattern in SEARCH_GLOBS:
        base = REPO / rel
        if not base.exists():
            continue
        for path in sorted(base.glob(pattern)):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            points = []
            walk_points(data, points)
            for pt in points:
                facts, time = point_change_facts(pt)
                if not facts and not (time.get("amount") or 0):
                    continue
                committed.append({
                    "file": path.relative_to(REPO).as_posix(),
                    "pointId": pt.get("id") or pt.get("pointId"),
                    "facts": facts, "time": time,
                    "signature": screening.change_signature(facts, time),
                })

    samples_ts = REPO / "frontend/src/lib/world-engine/runtime/narration-eval-samples.ts"
    items = parse_items(samples_ts)
    rows = []
    for it in items:
        missing = []
        for cid in it["ids"]["actors"]:
            if cid not in known["characters"]:
                missing.append({"id": cid, "bucket": "characters"})
        for cid in it["ids"]["from"] + it["ids"]["to"] + it["ids"]["at"]:
            if cid not in known["locations"]:
                missing.append({"id": cid, "bucket": "locations"})
        for cid in it["ids"]["tasks"]:
            if cid not in tasks:
                missing.append({"id": cid, "bucket": "tasks"})
        shape_matches = [p for p in committed if p["signature"] == it["changeSignature"]]
        placeholder_anchor = bool(it["anchorPlaceholder"]) or (
            bool(it["anchorDigest"]) and set(it["anchorDigest"]) <= {"f"})
        basis = "undetermined"
        reason = []
        if placeholder_anchor:
            reason.append("sample 的 stateDigest 是占位值（全 f），不指向任何已提交读取")
        if missing:
            reason.append("引用的 ID 在夹具里不存在：" +
                          "、".join(sorted({m["id"] for m in missing})))
        if not shape_matches:
            reason.append("登记的轨迹与归档里没有形状相同的已提交点")
        else:
            reason.append(f"形状相同 {len(shape_matches)} 处，但无法按点位身份绑定")
        rows.append({
            "id": it["id"], "anchorDigest": it["anchorDigest"],
            "anchorCall": it.get("anchorCall"),
            "declaredKinds": it["kinds"], "declaredActors": it["actors"],
            "declaredTime": it["time"], "changeSignature": it["changeSignature"],
            "idsNotInFixture": sorted({m["id"] for m in missing}),
            "shapeMatchCount": len(shape_matches),
            "shapeMatches": [{"file": m["file"], "pointId": m["pointId"]}
                             for m in shape_matches[:5]],
            "basis": basis, "reasons": reason,
        })

    doc = {
        "formatVersion": 1,
        "question": "旧题的变化事实是否有权威读取支撑？",
        "rule": ("只有能按点位身份绑定到已存读取（trace step / 归档点）的，才算 "
                 "authoritative-read；手写叙事包、占位 anchor、或引用夹具里不存在的 ID "
                 "一律记 undetermined。"),
        "sourcesSearched": [rel for rel, _ in SEARCH_GLOBS],
        "committedPointsFound": len(committed),
        "items": rows,
        "summary": {
            "authoritative": sum(1 for r in rows if r["basis"] == "authoritative-read"),
            "undetermined": sum(1 for r in rows if r["basis"] == "undetermined"),
        },
        "limits": [
            "形状相同不等于同一事实：即使签名相同，也仍可能不是旧题当年的那个点。",
            "本脚本只读登记的轨迹与归档；未登记的运行产物不在检查范围内。",
        ],
    }
    screening.write_artifact(OUT / "sources/three-arm-provenance.json",
                             json.dumps(doc, ensure_ascii=False, indent=1) + NL)

    lines = ["# 旧题变化事实的来源核对（自动生成，勿手改）", "",
             f"检查了 {len(committed)} 个已存点，覆盖：{', '.join('`' + s + '`' for s in doc['sourcesSearched'])}。", "",
             f"结论：authoritative-read **{doc['summary']['authoritative']}** 条，"
             f"undetermined **{doc['summary']['undetermined']}** 条。", "",
             "| 旧题 | 变化签名 | anchor | 夹具里不存在的 ID | 形状相同的已存点 | 依据 |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| `{r['id']}` | `{r['changeSignature']}` | "
                     f"{'占位（全 f）' if r['anchorDigest'] and set(r['anchorDigest']) <= {'f'} else (r['anchorDigest'][:16] + '…' if r['anchorDigest'] else '无')} | "
                     f"{'、'.join(r['idsNotInFixture']) or '无'} | "
                     f"{r['shapeMatchCount']} 处 | {r['basis']} |")
    lines += ["", "## 逐条理由", ""]
    for r in rows:
        lines.append(f"- `{r['id']}`（anchor 调用 `{r.get('anchorCall') or '无'}`）："
                     + "；".join(r["reasons"]))
    lines += ["", "## 对签名比较的影响", "",
              "- 变化签名仍然是可比较的**形状**，但 `undetermined` 的旧题只能说明“按当前转换口径同形”，"
              "不能据此断定某个新点是旧题的派生。",
              "- 相应地，`c8d06` 第 2 点与 `nv-cont-2` 的关系写作“口径同形”，不写作“派生”。",
              "", "## 边界", ""] + [f"- {x}" for x in doc["limits"]]
    screening.write_artifact(OUT / "sources/three-arm-provenance.md", NL.join(lines) + NL)

    print(f"items={len(rows)} committedPoints={len(committed)} "
          f"authoritative={doc['summary']['authoritative']} "
          f"undetermined={doc['summary']['undetermined']}")
    for r in rows:
        if r["idsNotInFixture"]:
            print(f"  {r['id']}: ids not in fixture {r['idsNotInFixture']} shapeMatches={len(r['shapeMatches'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
