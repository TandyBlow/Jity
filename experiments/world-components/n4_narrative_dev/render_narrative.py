# N4 narrative input renderer v0 (approved corpus, review prototype).
#
# This is the INPUT contract the N4 narrator must read:
#   - scene/location appearance, weather, time-of-day, visible items;
#   - present characters' personality/appearance/inventory (personality is
#     READ, not necessarily surfaced; other characters' inner states stay
#     forbidden);
#   - the point's facts as constraints: moved / outcome resultText / sanity
#     direction (qualitative, no numbers) / appearance detail / personality
#     behaviour / no_change;
#   - time is internal: only "过去了一会儿（不写具体时长）"; no amount/unit;
#   - task goals and task IDs are not included; only outcome resultText;
#   - perspective + the boundary instructions.
#
# It does NOT train or call a model. preview_inputs.py renders the 12
# approved cases and reports real-token lengths against the current N4
# training limit (160); the new contract will need a larger max input.

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent


def load_world(path=None):
    p = pathlib.Path(path) if path else HERE / "world.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _loc_name(world, lid):
    if lid in world["locations"]:
        return world["locations"][lid]["name"]
    for loc in world["locations"].values():
        for sub in loc.get("sublocations", []):
            if sub["id"] == lid:
                return sub["name"]
    return lid


def _loc_appearance(world, lid):
    if lid in world["locations"]:
        return world["locations"][lid]["appearance"]
    for loc in world["locations"].values():
        for sub in loc.get("sublocations", []):
            if sub["id"] == lid:
                return sub["appearance"]
    return ""


def _item_name(world, iid):
    return world["items"].get(iid, {}).get("name", iid)


def _item_appearance(world, iid):
    return world["items"].get(iid, {}).get("appearance", "")


def _fact_line(f, world):
    kind = f["kind"]
    name = f.get("name") or ""
    if kind == "moved":
        return f"{name}从{f['from']}来到{f['to']}。"
    if kind == "outcome":
        # resultText is the surface; goal/taskId never enter the input
        return f"{name}{f['resultText']}。"
    if kind == "sanity_changed":
        if f["to"] > f["from"]:
            return f"{name}的呼吸比刚才顺了一些。"
        if f["to"] < f["from"]:
            return f"{name}的呼吸有些发紧。"
        return f"{name}的呼吸没有变化。"
    if kind == "appearance_changed":
        return f"{name}的{f['text']}。"
    if kind == "personality_changed":
        return f"{name}的行为倾向：{f['text']}。"
    if kind == "no_change":
        return "这一拍没有新的变化。"
    if kind == "time":
        return None
    return f"{name}{json.dumps(f, ensure_ascii=False)}"


def _context_lines(case, world):
    ss = case["sceneState"]
    path = " → ".join(_loc_name(world, x) for x in ss["locationPath"])
    deepest = ss["locationPath"][-1]
    appearance = _loc_appearance(world, deepest)
    lines = ["叙事任务。"]
    lines.append(f"场景：{path}。{appearance}。"
                 f"天气：{ss['weather']}。时间：{ss['time']}。")
    for cc in case.get("characterContext", []):
        inv = "、".join(_item_name(world, x)
                        for x in cc.get("inventory", [])) or "无"
        lines.append(f"{cc['name']}（性格：{cc['personality']}；"
                     f"外貌：{cc['appearance']}；随身：{inv}）")
    items = []
    for iid in ss.get("visibleItems", []):
        items.append(f"{_item_name(world, iid)}（{_item_appearance(world, iid)}）")
    if items:
        lines.append("可见物：" + "；".join(items) + "。")
    return lines


def _pov_name(case, world):
    eid = (case.get("perspective") or {}).get("entityId")
    if not eid and case.get("characterContext"):
        eid = case["characterContext"][0].get("entityId")
    if eid:
        return world.get("characters", {}).get(eid, {}).get("name", eid)
    return "沈砚"


def _tail_lines(pov):
    return [
        f"视角：{pov}（第三人称限知）；只写{pov}的内心，他人只写可见动作。",
        "要求：不要写任务标题、数值面板、具体时长、"
        "‘性格/外貌’字段名；不要新增未列出的具名人物/物品/地点。",
        "正文：",
    ]


def render_input(case, world):
    lines = _context_lines(case, world)
    lines.append("这一拍：")
    n = 0
    has_time = False
    for f in case["facts"]:
        if f["kind"] == "time":
            has_time = True
            continue
        line = _fact_line(f, world)
        if line:
            n += 1
            lines.append(f"{n}. {line}")
    if has_time:
        lines.append("时间：过去了一会儿（不写具体时长）。")
    lines.extend(_tail_lines(_pov_name(case, world)))
    return "\n".join(lines)


def render_plan_input(case, plan, world):
    """N4 input from the N2-selected N3 plan (grouped facts + per-group time)."""
    if "refusal" in plan:
        return "PLAN REFUSAL: " + json.dumps(plan["refusal"], ensure_ascii=False)
    lines = _context_lines(case, world)
    by_id = {f["factId"]: f for f in case["facts"]}
    lines.append("这一拍（按叙述分组）：")
    has_group_time = False
    for s in plan["sentences"]:
        lines.append(f"第 {s['index'] + 1} 组：")
        n = 0
        for fid in s["factIds"]:
            f = by_id[fid]
            if f["kind"] == "time":
                continue
            line = _fact_line(f, world)
            if line:
                n += 1
                lines.append(f"{n}. {line}")
        if s.get("time"):
            has_group_time = True
            lines.append("这一组之后，过去了一会儿（不写具体时长）。")
    if not has_group_time and any(f["kind"] == "time" for f in case["facts"]):
        lines.append("时间：过去了一会儿（不写具体时长）。")
    lines.extend(_tail_lines(_pov_name(case, world)))
    return "\n".join(lines)

def main():
    import json as _json
    world = load_world()
    corpus = [ _json.loads(l) for l in
               (HERE / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
               if l.strip()]
    for c in corpus:
        print("=" * 80)
        print(c["id"], c["title"])
        print(render_input(c, world))


if __name__ == "__main__":
    main()
