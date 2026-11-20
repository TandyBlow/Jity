"""Build the 40 object-binding training units and 24 frozen confirmation units."""
import json
import pathlib
import re
from collections import Counter

import object_data as O
from expand_pairs import SCENES, unit_input, world_sets, fact_line

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WORLD = json.loads((HERE / "world.json").read_text(encoding="utf-8"))


def check_fact(f, uid, sets, problems):
    chars, items, feats, locs, parts = sets
    if f["kind"] != "no_change" and f["name"] not in chars | items | feats:
        problems.append(f"{uid}: 主体 {f['name']} 不在世界表")
    if f["kind"] == "moved" and (f["from"] not in locs or f["to"] not in locs):
        problems.append(f"{uid}: 地点不在世界表")
    text = f.get("text") or ""
    if re.search(r"[0-9]", text):
        problems.append(f"{uid}: 事实含数字")


def main():
    sets = world_sets()
    problems, train, confirm = [], [], []
    seen = {}
    for pk, cat, sc, pov, fa, ta, fb, tb in O.TRAIN_OBJ:
        check_fact(fa, pk + "A", sets, problems)
        check_fact(fb, pk + "B", sets, problems)
        if ta == tb:
            problems.append(f"{pk}: 目标没随事实改变")
        for tag, f, t in (("A", fa, ta), ("B", fb, tb)):
            uid = pk + tag
            if not re.search(r"[。]$", t):
                problems.append(f"{uid}: 目标不是完整句")
            if re.search(r"[0-9]", t):
                problems.append(f"{uid}: 目标含数字")
            if t in seen:
                problems.append(f"{uid}: 目标与 {seen[t]} 重复")
            seen[t] = uid
            train.append({"unitId": uid, "pairKey": pk, "category": "object_" + cat,
                          "kind": f["kind"], "split": "vb-train",
                          "input": unit_input(sc, pov, f), "target": t})
    for pk, cat, sc, pov, fa, fb in O.CONFIRM_OBJ:
        check_fact(fa, pk + "A", sets, problems)
        check_fact(fb, pk + "B", sets, problems)
        for tag, f in (("A", fa), ("B", fb)):
            confirm.append({"unitId": pk + tag, "pairKey": pk,
                            "category": "object_" + cat, "kind": f["kind"],
                            "split": "confirm_obj",
                            "input": unit_input(sc, pov, f), "fact": f,
                            "mustExpress": ["f0"]})
    # 训练/确认按整对隔离：不能出现同一 (种类, 主体, 状态文本)
    def sig(f):
        return (f["kind"], f.get("name"), f.get("text") or f.get("to") or "")
    tr = {sig(f) for pk, c, s, p, fa, ta, fb, tb in O.TRAIN_OBJ for f in (fa, fb)}
    clash = [u["unitId"] for u in confirm if sig(u["fact"]) in tr]
    if clash:
        problems.append(f"确认与训练组合重叠: {clash}")
    # 部件合法性：只在“整体/部件”类上机械校验——出现“整体X的Y”时 Y 必须是登记部件
    legal = sets[4]
    whole_part = [u for u in train + confirm
                  if u["category"] == "object_whole_part"]
    for u in whole_part:
        for t in filter(None, (u.get("target"),)):
            for m in re.finditer(r"([一-鿿]{2,3})的([一-鿿]{2})", t):
                whole, part = m.group(1), m.group(2)
                if whole in {"顾行舟", "沈砚", "叶知微", "阿棠", "韩渡"}:
                    continue
                # 部件可以从多字词里截出来（“玻璃罩”前两个字是“玻璃”），
                # 所以反过来看 target 里紧跟“的”之后是否出现登记部件。
                tail = t[m.end(1) + 1:]
                if not any(tail.startswith(x) for x in legal):
                    problems.append(f'{u["unitId"]}: 部件 {part} 未登记（整体 {whole}）')
    rec = {"purpose": "object-binding expansion: same scene, only the subject object changes",
           "legalParts": sorted(legal),
           "rule": {"part": "部件必须出现在 world.json（物品外貌／人物外貌／地点特征）",
                    "wholeVsPart": "整体写整体名，部件写“整体名+的+部件名”，两者算不同事实",
                    "rubric": "S 表达主体物件与状态/位置；A 状态挂到另一个物件；"
                              "C 与事实相反（位置错、部件错）；O 缺失；"
                              "另记未经支持的新增（场景描写不算）"},
           "trainUnits": len(train), "confirmUnits": len(confirm),
           "byCategory": dict(Counter(u["category"] for u in train)),
           "problems": problems}
    (ROOT / "artifacts" / "world-components" / "n4-object-train40.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in train) + "\n", encoding="utf-8")
    (ROOT / "artifacts" / "world-components" / "n4-object-confirm24-units.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in confirm) + "\n", encoding="utf-8")
    (ROOT / "artifacts" / "world-components" / "n4-object-confirm24.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("train", len(train), dict(Counter(u["category"] for u in train)))
    print("confirm", len(confirm), dict(Counter(u["category"] for u in confirm)))
    print("problems", len(problems), problems[:6])
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
