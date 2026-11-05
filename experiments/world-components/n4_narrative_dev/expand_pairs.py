"""Build the 80 training units and 40 frozen confirmation units.

Runs all legality checks before writing; a non-zero exit means nothing usable
was produced.
"""
import json
import pathlib
import re
from collections import Counter

import expand_data as D
import expand_confirm as C

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WORLD = json.loads((HERE / "world.json").read_text(encoding="utf-8"))

SCENES = {
    "ARCH": ("潮汐档案馆", "天窗、长桌、门槛、铜灯",
             ["潮汐簿", "铜灯", "干纸", "墨", "油布包", "备用钥匙"], "夜；小雨；铜灯"),
    "FERRY": ("潮渡>栈桥", "木桩、缆绳、船灯、水面、栈桥",
              ["缆绳", "渡船", "船灯", "系泊绳", "木桩"], "清晨；薄雾；船灯"),
    "MARKET": ("早市", "帆布棚、鱼筐、案板、石板",
               ["银鳞鱼", "鱼筐", "案板", "抹布"], "清晨；薄雾；棚下散光"),
    "WALL": ("雾堤>堤面", "铁链、钟架、钟绳",
             ["钟绳", "雾警钟", "警示灯", "铁链"], "夜；浓雾；警示灯"),
    "LIGHT": ("旧灯塔>塔顶", "铜灯罩、铁链、备用灯芯、抹布",
              ["铜灯罩", "灯芯", "抹布", "擦铜油", "油壶"], "夜；夜雾；塔顶铜灯已点亮"),
    "ALLEY": ("潮生巷", "纸灯笼、排水沟、石板、墙根",
              ["油纸伞", "纸灯笼", "干纸", "墨", "备用钥匙"], "雨后；雨停；纸灯笼"),
}


def fact_line(f):
    k = f["kind"]
    if k == "moved":
        return f'移动｜{f["name"]}｜{f["from"]}→{f["to"]}'
    if k == "outcome":
        return f'结果｜{f["name"]}｜{f["text"]}'
    if k == "appearance_changed":
        return f'外观｜{f["name"]}｜{f["text"]}'
    if k == "no_change":
        return "无变化｜"
    raise ValueError(k)


def unit_input(scene_key, pov, fact):
    loc, feats, items, weather = SCENES[scene_key]
    vis = "、".join(items + feats.split("、")[:6])
    lines = ["短句任务。", f"地点={loc}", f"地点可见={vis}", f"场景={weather}",
             f"视角={pov}；第三人称", f'事实={fact_line(fact)}']
    if fact["kind"] == "moved":
        lines.append(f'方向={fact["direction"]}')
    lines += ["要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；"
              "只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；"
              "不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。", "短句："]
    return "\n".join(lines) + "\n"


def world_sets():
    chars = {v["name"] for v in WORLD["characters"].values()}
    items = {v["name"] for v in WORLD["items"].values()}
    feats = set()
    for L in WORLD["locations"].values():
        feats |= set(L.get("features") or [])
        for s in L.get("sublocations") or []:
            feats |= set((s.get("appearance") or "").replace("、", " ").split())
    locs = set()
    for L in WORLD["locations"].values():
        locs.add(L["name"])
        locs |= {s["name"] for s in L.get("sublocations") or []}
    parts = set()
    for v in WORLD["items"].values():
        for chunk in (v.get("appearance") or "").replace("；", " ").replace("，", " ").split():
            parts.add(chunk)
    for v in WORLD["characters"].values():
        for chunk in (v.get("appearance") or "").replace("；", " ").replace("，", " ").split():
            parts.add(chunk)
    for L in WORLD["locations"].values():
        for chunk in (L.get("appearance") or "").replace("；", " ").replace("，", " ").split():
            parts.add(chunk)
    extra = {"灯罩", "玻璃罩", "灯芯", "链环", "扉页", "横木", "船板", "伞骨",
             "袖口", "下摆", "辫梢", "鞋底", "手背", "指尖", "眉毛", "罐口",
             "边沿", "末端", "边角", "封面", "罩子"}
    return chars, items, feats, locs, parts | extra


def check_fact(f, uid, sets, problems):
    chars, items, feats, locs = sets
    if f["kind"] != "no_change" and f["name"] not in chars | items | feats:
        problems.append(f"{uid}: 主体 {f['name']} 不在世界表")
    if f["kind"] == "moved" and (f["from"] not in locs or f["to"] not in locs):
        problems.append(f"{uid}: 地点不在世界表")
    if re.search(r"[0-9]", f.get("text") or ""):
        problems.append(f"{uid}: 事实含数字")


def check_target(t, uid, problems, seen):
    if not re.search(r"[。]$", t):
        problems.append(f"{uid}: 目标不以句号结尾")
    if re.search(r"[0-9]", t):
        problems.append(f"{uid}: 目标含数字")
    if re.match(r"^[他她]", t):
        problems.append(f"{uid}: 目标以代词开头")
    if t in seen:
        problems.append(f"{uid}: 目标与 {seen[t]} 重复")
    seen[t] = uid


def main():
    sets = world_sets()
    problems, train, confirm, seen = [], [], [], {}
    for pk, cat, sc, pov, fa, ta, fb, tb in D.TRAIN:
        check_fact(fa, pk + "A", sets, problems)
        check_fact(fb, pk + "B", sets, problems)
        if ta == tb:
            problems.append(f"{pk}: 目标没随事实改变")
        for tag, f, t in (("A", fa, ta), ("B", fb, tb)):
            uid = pk + tag
            check_target(t, uid, problems, seen)
            train.append({"unitId": uid, "pairKey": pk, "category": cat,
                          "kind": f["kind"], "split": "vb-train",
                          "input": unit_input(sc, pov, f), "target": t})
    for i, (pk, cat, sc, pov, fa, fb) in enumerate(C.CONFIRM, 1):
        check_fact(fa, pk + "A", sets, problems)
        check_fact(fb, pk + "B", sets, problems)
        for tag, f in (("A", fa), ("B", fb)):
            uid = pk + tag
            if f["kind"] == "no_change":
                ref = C.NO_CHANGE_TARGETS[(i - 1) % len(C.NO_CHANGE_TARGETS)]
            else:
                ref = None
            confirm.append({"unitId": uid, "pairKey": pk, "category": cat,
                            "kind": f["kind"], "split": "confirm",
                            "input": unit_input(sc, pov, f), "fact": f,
                            "mustExpress": ["f0"], "referenceIfNeeded": ref})
    # 与训练集的组合隔离：同类别里，训练与确认不能共用同一 (主体, 动作文本)
    def sig(f):
        return (f["kind"], f.get("name"), f.get("text") or f.get("to") or "")
    tr_sig = {sig(f) for pk, c, s, p, fa, ta, fb, tb in D.TRAIN
              for f in (fa, fb) if f["kind"] != "no_change"}
    clash = [(u["unitId"], u["kind"]) for u in confirm
             if u["fact"]["kind"] != "no_change" and sig(u["fact"]) in tr_sig]
    if clash:
        problems.append(f"确认集与训练集组合重叠: {clash[:3]}")

    rec = {"purpose": "single-fact training expansion + frozen confirmation set",
           "world": "world.json",
           "rubric": {"S": "表达事实主体、动作/状态、对象或方向",
                      "A": "动作或状态挂到另一个具名实体",
                      "C": "与事实相反（方向反、内外反、所有者错、位置错）",
                      "O": "事实内容缺失（含 moved 起点或终点缺失）",
                      "noChangeMiss": "无变化被写成发生了变化",
                      "unsupported": "出现场景与事实之外的新事件/新状态；场景描写不算"},
           "trainUnits": len(train), "confirmUnits": len(confirm),
           "byCategory": {k: sum(1 for u in train if u["category"] == k)
                          for k in sorted({u["category"] for u in train})},
           "problems": problems}
    (ROOT / "artifacts" / "world-components" / "n4-expand-train80.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in train) + "\n",
        encoding="utf-8")
    (ROOT / "artifacts" / "world-components" / "n4-expand-confirm40-units.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in confirm) + "\n",
        encoding="utf-8")
    (ROOT / "artifacts" / "world-components" / "n4-expand-confirm40.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("train", len(train), dict(Counter(u["category"] for u in train)))
    print("confirm", len(confirm), dict(Counter(u["category"] for u in confirm)))
    print("problems", len(problems), problems[:6])
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
