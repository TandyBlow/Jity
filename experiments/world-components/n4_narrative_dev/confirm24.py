"""24 new single-fact units for the A/B confirmation; labels frozen before running.

Categories (6 each): attribution, appearance owner, explicit move, container/object binding.
Half of each have subject == viewpoint character, half do not.
"""
import json, pathlib, re
HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parents[2] / "artifacts" / "world-components" / "n4-ablation-confirm24.json"

ARCH = ("潮汐档案馆", "天窗、长桌、门槛、铜灯", "夜；小雨；铜灯")
FERRY = ("潮渡>栈桥", "木桩、缆绳、船灯、水面、栈桥、石阶", "清晨；薄雾；船灯")
MARKET = ("早市", "帆布棚、鱼筐、案板、石板、银鳞鱼", "清晨；薄雾；棚下散光")
WALL = ("雾堤>堤面", "铁链、钟架、钟绳、警示灯", "夜；浓雾；警示灯")
LIGHT = ("旧灯塔>塔顶", "铜灯罩、铁链、备用灯芯、抹布、擦铜油", "夜；夜雾；铜灯已点亮")
ALLEY = ("潮生巷", "纸灯笼、排水沟、石板、油纸伞", "雨后；雨停；纸灯笼")

VIS = {"潮汐档案馆": ["潮汐簿", "铜灯", "干纸", "墨"],
       "潮渡>栈桥": ["缆绳", "渡船", "船灯", "系泊绳"],
       "早市": ["银鳞鱼", "鱼筐", "案板", "抹布"],
       "雾堤>堤面": ["钟绳", "雾警钟", "警示灯", "铁链"],
       "旧灯塔>塔顶": ["铜灯罩", "灯芯", "抹布", "擦铜油"],
       "潮生巷": ["油纸伞", "纸灯笼", "干纸", "墨"]}

def mv(fid, name, a, b, d="平"):
    return {"factId": fid, "kind": "moved", "name": name, "entityGroup": "characters",
            "from": a, "to": b, "direction": d}
def oc(fid, name, t):
    return {"factId": fid, "kind": "outcome", "name": name,
            "entityGroup": "characters", "resultText": t}
def ap(fid, name, t):
    return {"factId": fid, "kind": "appearance_changed", "name": name,
            "entityGroup": "characters", "text": t}

U = []
def unit(uid, cat, pov, scene, fact):
    U.append({"unitId": uid, "category": cat, "pov": pov, "scene": scene,
              "fact": fact, "subjectIsPov": fact["name"] == pov})

# 1 动作归属
unit("c1a", "attribution", "沈砚", ARCH, oc("f0", "沈砚", "把铜灯挪到长桌另一头"))
unit("c1b", "attribution", "沈砚", ARCH, oc("f0", "沈砚", "把湿伞靠在门槛边"))
unit("c1c", "attribution", "沈砚", ARCH, oc("f0", "沈砚", "把蜡烛吹灭"))
unit("c1d", "attribution", "沈砚", MARKET, oc("f0", "阿棠", "把鱼筐搬到案板底下"))
unit("c1e", "attribution", "沈砚", FERRY, oc("f0", "顾行舟", "把缆绳收成一卷"))
unit("c1f", "attribution", "沈砚", WALL, oc("f0", "韩渡", "把钟绳解开"))
# 2 外观所有者
unit("c2a", "appearance", "沈砚", LIGHT, ap("f0", "沈砚", "袖口沾了铜油"))
unit("c2b", "appearance", "阿棠", MARKET, ap("f0", "阿棠", "围裙上沾了鱼鳞"))
unit("c2c", "appearance", "叶知微", ARCH, ap("f0", "叶知微", "指尖沾了墨"))
unit("c2d", "appearance", "沈砚", MARKET, ap("f0", "阿棠", "辫梢沾了白汽"))
unit("c2e", "appearance", "沈砚", FERRY, ap("f0", "顾行舟", "手背上沾了盐沫"))
unit("c2f", "appearance", "叶知微", WALL, ap("f0", "韩渡", "外袍下摆被雾水打湿"))
# 3 明确起终点移动
unit("c3a", "move", "沈砚", ARCH, mv("f0", "沈砚", "潮生巷", "潮汐档案馆"))
unit("c3b", "move", "顾行舟", FERRY, mv("f0", "顾行舟", "潮渡", "雾堤", "上"))
unit("c3c", "move", "阿棠", MARKET, mv("f0", "阿棠", "早市", "潮汐档案馆"))
unit("c3d", "move", "沈砚", MARKET, mv("f0", "阿棠", "潮生巷", "早市"))
unit("c3e", "move", "沈砚", ARCH, mv("f0", "叶知微", "早市", "潮汐档案馆"))
unit("c3f", "move", "沈砚", WALL, mv("f0", "韩渡", "潮渡", "雾堤", "上"))
# 4 对象／容器绑定
unit("c4a", "binding", "沈砚", ARCH, oc("f0", "沈砚", "把擦铜油塞进油布包的夹层"))
unit("c4b", "binding", "沈砚", ARCH, oc("f0", "沈砚", "把干纸夹进潮汐簿的扉页"))
unit("c4c", "binding", "叶知微", LIGHT, oc("f0", "叶知微", "把灯芯收进铜灯罩底下"))
unit("c4d", "binding", "沈砚", MARKET, oc("f0", "阿棠", "把银鳞鱼码进鱼筐"))
unit("c4e", "binding", "沈砚", FERRY, oc("f0", "顾行舟", "把缆绳缠在木桩下半截"))
unit("c4f", "binding", "阿棠", WALL, oc("f0", "韩渡", "把钟绳挂回钟架"))

def fl(f):
    k = f["kind"]
    if k == "moved":
        return f'移动｜{f["name"]}｜{f["from"]}→{f["to"]}'
    if k == "outcome":
        return f'结果｜{f["name"]}｜{f["resultText"]}'
    return f'外观｜{f["name"]}｜{f["text"]}'

def unit_input(u, keep_pov_name):
    loc, feats, scene = u["scene"]
    items = "、".join(VIS[loc] + feats.split("、")[:6])
    pov = f'视角={u["pov"]}；第三人称' if keep_pov_name else "视角=第三人称"
    lines = ["短句任务。", f"地点={loc}", f"地点可见={items}", f"场景={scene}", pov,
             f'事实={fl(u["fact"])}']
    if u["fact"]["kind"] == "moved":
        lines.append(f'方向={u["fact"]["direction"]}')
    lines += ["要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；"
              "只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；"
              "不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。", "短句："]
    return "\n".join(lines) + "\n"

def main():
    bad = []
    items = set()
    world = json.loads((HERE / "world.json").read_text(encoding="utf-8"))
    for v in world["items"].values(): items.add(v["name"])
    locs = set()
    for L in world["locations"].values():
        locs.add(L["name"]); locs |= {s["name"] for s in L.get("sublocations") or []}
    for u in U:
        f = u["fact"]
        if f["kind"] == "moved" and (f["from"] not in locs or f["to"] not in locs):
            bad.append(u["unitId"] + ":地点")
        key = f.get("resultText") or f.get("text") or ""
        if re.search(r"[0-9]", key): bad.append(u["unitId"] + ":数字")
        if f["name"] not in {"沈砚","顾行舟","叶知微","阿棠","韩渡"}:
            bad.append(u["unitId"] + ":主体")
    rec = {"purpose": "A/B confirmation set, labels frozen before generation",
           "categories": ["attribution", "appearance", "move", "binding"],
           "rule": {"S": "表达事实主体+动作/状态+对象/方向",
                    "A": "动作或状态挂到另一个具名实体",
                    "C": "与事实相反（方向反、内外反、所有者错）",
                    "O": "事实内容缺失",
                    "unsupported": "出现事实与场景之外的新事件/新状态",
                    "sceneDetail": "场景描写不算未支持"},
           "units": [dict(u, inputA=unit_input(u, True), inputB=unit_input(u, False))
                     for u in U],
           "problems": bad}
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print("units", len(U), "by category", dict(Counter(u["category"] for u in U)),
          "subject==pov", sum(u["subjectIsPov"] for u in U))
    print("problems", bad)
    print("->", OUT)
    return 1 if bad else 0

if __name__ == "__main__":
    raise SystemExit(main())
