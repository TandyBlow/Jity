"""Final independent confirmation: 24 sources x 3-4 facts, frozen before running.

Only facts, must-express ids, legal expression boundary and the rubric are
written. No reference prose. Precheck runs before the file is frozen.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from precheck import check_unit  # noqa: E402

ROOT = HERE.parents[2]
OUT = ROOT / "artifacts" / "world-components" / "n4-final24.jsonl"

# scene key -> (地点, 特征串, 天气串)
SC = {
    "ARCH": ("潮汐档案馆", "天窗、长桌、门槛、铜灯", "夜；小雨；铜灯"),
    "FERRY": ("潮渡>栈桥", "木桩、缆绳、船灯、水面、栈桥", "清晨；薄雾；船灯"),
    "MARKET": ("早市", "帆布棚、鱼筐、案板、石板", "清晨；薄雾；棚下散光"),
    "WALL": ("雾堤>堤面", "铁链、钟架、钟绳", "夜；浓雾；警示灯"),
    "LIGHT": ("旧灯塔>塔顶", "铜灯罩、铁链、备用灯芯、抹布", "夜；夜雾；塔顶铜灯已点亮"),
    "ALLEY": ("潮生巷", "纸灯笼、排水沟、石板、墙根", "雨后；雨停；纸灯笼"),
}


def oc(name, t):
    return {"factId": None, "kind": "outcome", "name": name, "text": t}


def ap(name, t):
    return {"factId": None, "kind": "appearance_changed", "name": name, "text": t}


def mv(name, a, b, d="平"):
    return {"factId": None, "kind": "moved", "name": name, "from": a, "to": b,
            "direction": d}


def sn(name, up=False):
    return {"factId": None, "kind": "sanity_changed", "name": name,
            "from": 9 if up else 12, "to": 12 if up else 9}


def nc():
    return {"factId": None, "kind": "no_change", "name": None, "text": ""}


# (id, group, scene, pov, visible_items, facts)
S = [
    # 跨主体动作归属
    ("v01", "actor", "WALL", "沈砚", ["钟绳", "雾警钟", "警示灯", "铁链"],
     [mv("沈砚", "潮渡", "雾堤", "上"), oc("韩渡", "把松脱的钟绳重新系紧"),
      oc("沈砚", "把警示灯扶正"), ap("韩渡", "袖口沾了盐沫")]),
    ("v02", "actor", "MARKET", "阿棠", ["银鳞鱼", "鱼筐", "案板", "抹布"],
     [oc("阿棠", "把银鳞鱼按大小分开装进鱼筐"), oc("顾行舟", "把抹布拧干"),
      ap("顾行舟", "手背上沾了鱼鳞")]),
    ("v03", "actor", "ARCH", "沈砚", ["潮汐簿", "铜灯", "干纸", "墨"],
     [oc("沈砚", "把潮汐簿缺的那页补全"), oc("叶知微", "把干纸码成一小摞"),
      ap("叶知微", "指尖沾了墨"), nc()]),
    ("v04", "actor", "FERRY", "顾行舟", ["缆绳", "渡船", "船灯", "系泊绳"],
     [oc("顾行舟", "把渡船系在栈桥的木桩上"), oc("韩渡", "把系泊绳收成一卷"),
      ap("韩渡", "手背上沾了盐沫")]),

    # 外观归属
    ("v05", "appearance", "LIGHT", "沈砚", ["铜灯罩", "灯芯", "抹布", "擦铜油"],
     [ap("叶知微", "袖口沾了铜油"), ap("沈砚", "手背上沾了铜油"),
      oc("叶知微", "把灯罩擦得透亮"), nc()]),
    ("v06", "appearance", "ALLEY", "阿棠", ["油纸伞", "纸灯笼", "干纸", "鱼筐"],
     [ap("阿棠", "鞋底沾了湿石板的水"), ap("沈砚", "袖口沾了雨"),
      oc("阿棠", "把纸灯笼扶正")]),

    # 多物件 / 整体与部件
    ("v07", "object", "ARCH", "沈砚", ["铜灯", "蜡烛", "潮汐簿", "冷茶"],
     [ap("铜灯", "灯罩上积了灰"), ap("潮汐簿", "封面蒙了一层灰"),
      oc("沈砚", "把铜灯擦亮")]),
    ("v08", "object", "WALL", "韩渡", ["警示灯", "钟绳", "钟架", "铁链"],
     [ap("警示灯", "玻璃罩被风吹歪"), ap("钟绳", "磨出了毛边"),
      oc("韩渡", "把钟绳重新绕在钟架上")]),
    ("v09", "object", "MARKET", "阿棠", ["鱼筐", "案板", "银鳞鱼", "抹布"],
     [ap("鱼筐", "边沿沾着鱼鳞"), ap("案板", "边沿沾着鱼鳞"),
      oc("阿棠", "把银鳞鱼装进鱼筐")]),
    ("v10", "object", "LIGHT", "叶知微", ["铜灯罩", "铁链", "抹布", "擦铜油"],
     [ap("铁链", "链环上结了锈"), ap("铜灯罩", "玻璃上蒙了盐雾"),
      oc("叶知微", "把擦铜油放回梯脚")]),

    # 明确起终点的移动
    ("v11", "move", "ARCH", "沈砚", ["潮汐簿", "铜灯", "干纸", "墨"],
     [mv("沈砚", "潮生巷", "潮汐档案馆"), oc("沈砚", "把铜灯挪到门槛边"),
      nc(), ap("沈砚", "袖口沾了墨")]),
    ("v12", "move", "MARKET", "阿棠", ["银鳞鱼", "鱼筐", "案板", "抹布"],
     [mv("阿棠", "潮生巷", "早市"), oc("阿棠", "把银鳞鱼搬上案板"),
      ap("阿棠", "辫梢沾了白汽")]),
    ("v13", "move", "LIGHT", "叶知微", ["铜灯罩", "灯芯", "抹布", "擦铜油"],
     [mv("叶知微", "潮渡", "旧灯塔"), oc("叶知微", "换好塔顶的灯芯"),
      ap("叶知微", "袖口沾了铜油")]),
    ("v14", "move", "FERRY", "沈砚", ["缆绳", "渡船", "船灯", "系泊绳"],
     [mv("沈砚", "潮汐档案馆", "潮渡"), oc("沈砚", "把系泊绳拖回岸上"),
      sn("沈砚")]),

    # 容器内外
    ("v15", "container", "ARCH", "沈砚", ["油布包", "备用钥匙", "潮汐簿", "干纸"],
     [oc("沈砚", "把备用钥匙塞进油布包的内层"), oc("沈砚", "把干纸夹进潮汐簿的扉页"),
      oc("沈砚", "把潮汐簿合上推到桌角")]),
    ("v16", "container", "MARKET", "阿棠", ["鱼筐", "抹布", "银鳞鱼", "案板"],
     [oc("阿棠", "把抹布塞进鱼筐底下"), oc("阿棠", "把银鳞鱼摆在案板旁边"),
      ap("阿棠", "袖口沾了鱼鳞")]),
    ("v17", "container", "LIGHT", "叶知微", ["铜灯罩", "灯芯", "油壶", "抹布"],
     [oc("叶知微", "把灯芯收进铜灯罩底下"), oc("叶知微", "把油壶搁在铜灯罩上"),
      ap("叶知微", "指尖沾了铜油")]),

    # 理智等带字段值的事实
    ("v18", "sanity", "WALL", "沈砚", ["钟绳", "雾警钟", "警示灯", "铁链"],
     [mv("沈砚", "潮渡", "雾堤", "上"), oc("沈砚", "把雾警钟敲响"), sn("沈砚")]),
    ("v19", "sanity", "ARCH", "叶知微", ["潮汐簿", "铜灯", "干纸", "墨"],
     [oc("叶知微", "把干纸放在桌角"), sn("叶知微"), nc()]),
    ("v20", "sanity", "FERRY", "沈砚", ["缆绳", "渡船", "船灯", "系泊绳"],
     [mv("沈砚", "潮生巷", "潮渡"), sn("沈砚", True), oc("沈砚", "把渡船推离栈桥")]),

    # 具体变化 / 无变化
    ("v21", "change", "ARCH", "沈砚", ["潮汐簿", "铜灯", "干纸", "墨"],
     [oc("沈砚", "把铜灯挪到长桌另一头"), nc(), ap("沈砚", "指尖沾了墨")]),
    ("v22", "change", "ALLEY", "阿棠", ["纸灯笼", "排水沟", "鱼筐", "石板"],
     [oc("阿棠", "把鱼筐放在门槛边"), nc(), ap("阿棠", "鞋底沾了湿石板的水")]),
    ("v23", "change", "MARKET", "顾行舟", ["银鳞鱼", "鱼筐", "案板", "抹布"],
     [oc("顾行舟", "把缆绳绕上摊棚边的木桩"), nc(), ap("顾行舟", "手背上沾了鱼鳞")]),
    ("v24", "change", "WALL", "韩渡", ["钟绳", "雾警钟", "警示灯", "铁链"],
     [oc("韩渡", "把钟绳解开"), nc(), ap("韩渡", "手背上沾了盐沫")]),
]


def fact_line(f):
    k = f["kind"]
    if k == "moved":
        return f'移动｜{f["name"]}｜{f["from"]}→{f["to"]}'
    if k == "outcome":
        return f'结果｜{f["name"]}｜{f["text"]}'
    if k == "appearance_changed":
        return f'外观｜{f["name"]}｜{f["text"]}'
    if k == "sanity_changed":
        return f'理智｜{f["name"]}｜{"上升" if f["to"] > f["from"] else "下降"}'
    if k == "no_change":
        return "无变化｜"
    raise ValueError(k)


def unit_input(scene, pov, vis, f):
    loc, feats, wx = SC[scene]
    items = "、".join(vis + feats.split("、")[:6])
    lines = ["短句任务。", f"地点={loc}", f"地点可见={items}", f"场景={wx}",
             f"视角={pov}；第三人称", f"事实={fact_line(f)}"]
    if f["kind"] == "moved":
        lines.append(f'方向={f["direction"]}')
    lines += ["要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；"
              "只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；"
              "不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。", "短句："]
    return "\n".join(lines) + "\n"


def main():
    problems, units, sources = [], [], []
    for sid, group, scene, pov, vis, facts in S:
        ids, stored = [], []
        for i, f in enumerate(facts, 1):
            f = dict(f, factId=f"f{i - 1}")
            ids.append(f["factId"])
            stored.append(f)
            u = {"unitId": f'{sid}:{f["factId"]}', "sourceId": sid, "group": group,
                 "kind": f["kind"], "input": unit_input(scene, pov, vis, f),
                 "fact": f}
            pr = check_unit(u)
            if pr:
                problems.append({"unitId": u["unitId"], "problems": pr})
            units.append(u)
        sources.append({"sourceId": sid, "group": group,
                        "mustExpress": ids, "facts": stored})
    rec = {"purpose": "final independent confirmation, 24 sources",
           "world": "world.json",
           "legalParts": "部件只能来自 precheck.PARTS_OF 登记表；整体必须可见",
           "rubric": {"S": "表达事实主体与动作/状态/对象/方向；moved 必须写出起点与终点",
                      "O": "事实内容缺失（含 moved 缺起点或缺终点、sanity 未表达方向）",
                      "C": "与事实相反（方向反、内外反、所有者错、位置错、理智方向反）",
                      "A": "动作或状态挂到另一个具名实体",
                      "valueLeak": "直接写出“上升/下降/数值”等字段值视为未表达（记 O）",
                      "unsupported": "出现事实与场景之外的新事件或物件；场景描写不算",
                      "sourceClean": "所有必述事实为 S 且无未支持新增"},
           "sources": sources, "units": units, "problems": problems}
    (ROOT / "artifacts" / "world-components" / "n4-final24.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT).write_text("\n".join(json.dumps(u, ensure_ascii=False) for u in units) + "\n",
                     encoding="utf-8")
    from collections import Counter
    print("sources", len(sources), "units", len(units),
          "byGroup", dict(Counter(s["group"] for s in sources)),
          "factsPerSource", dict(Counter(len(s["mustExpress"]) for s in sources)))
    print("problems", len(problems), problems[:5])
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
