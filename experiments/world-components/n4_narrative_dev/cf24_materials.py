"""24 multi-fact test sources for the cohesion check, no reference prose.

Only facts, must-express list, legal aliases and the packing inputs are written.
Reference texts are not needed: the evaluation is fact-level by a human plus a
separate cohesion rating.
"""
import json, pathlib, re
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "artifacts" / "world-components" / "n4-cf24-materials-v2.json"
WORLD = json.loads((HERE / "world.json").read_text(encoding="utf-8"))

ALIASES = {
    "潮汐档案馆": ["档案馆"], "潮渡": ["渡口"], "栈桥": ["木栈桥"],
    "早市": ["集市"], "雾堤": ["堤上"], "旧灯塔": ["灯塔"],
    "潮生巷": ["巷子"], "铜灯罩": ["灯罩"], "系泊绳": ["绳子"],
    "银鳞鱼": ["鱼"], "雾警钟": ["钟"],
}

S = []


def src(sid, pattern, loc, sub, time, weather, light, atm, present, visible, pov, facts):
    S.append(dict(id=sid, pattern=pattern, loc=loc, sub=sub, time=time,
                  weather=weather, light=light, atmosphere=atm,
                  present=present, visible=visible, pov=pov, facts=facts))


def mv(fid, name, a, b, direction="平"):
    return {"factId": fid, "kind": "moved", "name": name,
            "entityGroup": "characters", "from": a, "to": b,
            "direction": direction}


def oc(fid, name, text):
    return {"factId": fid, "kind": "outcome", "name": name,
            "entityGroup": "characters", "resultText": text}


def ap(fid, name, text, group="characters"):
    return {"factId": fid, "kind": "appearance_changed", "name": name,
            "entityGroup": group, "text": text}


def sa(fid, name):
    return {"factId": fid, "kind": "sanity_changed", "name": name,
            "entityGroup": "characters", "from": 12, "to": 9}


# ---- P1 同主体连续动作
src("t01", "P1-same-subject", "loc_archive", None, "夜", "小雨", "铜灯",
    "雨声压在窗外", ["沈砚"], ["潮汐簿", "铜灯", "干纸", "墨"], "沈砚",
    [oc("f0", "沈砚", "把潮汐簿缺的那页补全"),
     ap("f1", "沈砚", "指尖沾了墨"),
     oc("f2", "沈砚", "把簿子合上推到桌角")])
src("t02", "P1-same-subject", "loc_market", None, "清晨", "薄雾", "棚下散光",
    "白汽不散", ["阿棠"], ["银鳞鱼", "鱼筐", "案板", "抹布"], "阿棠",
    [oc("f0", "阿棠", "把银鳞鱼按大小分开装进两只鱼筐"),
     ap("f1", "阿棠", "袖口沾了鱼鳞"),
     oc("f2", "阿棠", "把空鱼筐摞到摊棚边上")])
src("t03", "P1-same-subject", "loc_lighthouse", "塔顶", "夜", "夜雾，海风",
    "铜灯已点亮", "风硬，铜灯罩嗡嗡响", ["叶知微"],
    ["铜灯罩", "抹布", "擦铜油", "灯芯"], "叶知微",
    [oc("f0", "叶知微", "把灯罩擦得透亮"),
     ap("f1", "叶知微", "袖口沾了铜油"),
     oc("f2", "叶知微", "把抹布搭回梯脚")])
src("t04", "P1-same-subject", "loc_ferry", "栈桥", "傍晚", "雾", "船灯",
    "河风把雾推上栈桥", ["顾行舟"], ["缆绳", "木桩", "渡船", "船灯"], "顾行舟",
    [oc("f0", "顾行舟", "把缆绳在木桩上绕了三圈"),
     oc("f1", "顾行舟", "把渡船推离栈桥"),
     ap("f2", "顾行舟", "外袍下摆被雾水打湿")])
src("t05", "P1-same-subject", "loc_seawall", "堤面", "夜", "浓雾", "警示灯",
    "浪沫打到石壁上", ["韩渡"], ["钟绳", "雾警钟", "警示灯", "铁链"], "韩渡",
    [oc("f0", "韩渡", "把松脱的钟绳重新系紧"),
     oc("f1", "韩渡", "把雾警钟敲响"),
     ap("f2", "韩渡", "手背上沾着盐沫")])
src("t06", "P1-same-subject", "loc_alley", None, "雨后", "雨停", "纸灯笼",
    "墙根还在滴水", ["沈砚"], ["油纸伞", "纸灯笼", "排水沟", "石板"], "沈砚",
    [oc("f0", "沈砚", "把油纸伞收拢靠在墙根"),
     oc("f1", "沈砚", "把被风吹歪的纸灯笼扶正"),
     ap("f2", "沈砚", "鞋底沾了湿石板的水")])

# ---- P2 两人交替
src("t07", "P2-two-actor", "loc_seawall", "堤面", "夜", "浓雾", "警示灯",
    "浪沫打到石壁上", ["沈砚", "韩渡"], ["钟绳", "雾警钟", "铁链", "警示灯"], "沈砚",
    [mv("f0", "沈砚", "潮渡", "雾堤"),
     oc("f1", "韩渡", "把松脱的钟绳重新系紧"),
     oc("f2", "沈砚", "把雾警钟敲响"),
     ap("f3", "韩渡", "手背上沾着盐沫")])
src("t08", "P2-two-actor", "loc_market", None, "清晨", "薄雾", "棚下散光",
    "白汽不散", ["阿棠", "顾行舟"], ["银鳞鱼", "鱼筐", "案板", "缆绳"], "阿棠",
    [oc("f0", "阿棠", "把银鳞鱼搬上案板"),
     oc("f1", "顾行舟", "把缆绳绕上摊棚边的木桩"),
     ap("f2", "阿棠", "辫梢沾了白汽"),
     ap("f3", "顾行舟", "外袍下摆沾了泥水")])
src("t09", "P2-two-actor", "loc_archive", None, "午后", "阴", "铜灯",
    "天窗漏进灰光", ["沈砚", "叶知微"], ["潮汐簿", "铜灯", "干纸", "墨"], "沈砚",
    [mv("f0", "叶知微", "早市", "潮汐档案馆"),
     oc("f1", "沈砚", "把潮汐簿摊在铜灯下"),
     oc("f2", "叶知微", "把一叠干纸放在桌角"),
     ap("f3", "沈砚", "袖口沾了墨")])
src("t10", "P2-two-actor", "loc_ferry", "栈桥", "清晨", "薄雾", "船灯",
    "河面只有船灯", ["顾行舟", "沈砚"], ["缆绳", "木桩", "渡船", "系泊绳"], "沈砚",
    [oc("f0", "顾行舟", "把渡船系在栈桥的木桩上"),
     oc("f1", "沈砚", "把系泊绳从浅滩拖回岸上"),
     ap("f2", "顾行舟", "外袍下摆被雾水打湿"),
     sa("f3", "沈砚")])
src("t11", "P2-two-actor", "loc_lighthouse", "塔顶", "夜", "夜雾，海风",
    "铜灯已点亮", "风硬，铜灯罩嗡嗡响", ["沈砚", "叶知微"],
    ["铜灯罩", "备用灯芯", "抹布", "擦铜油"], "沈砚",
    [mv("f0", "沈砚", "潮生巷", "旧灯塔"),
     oc("f1", "叶知微", "把灯罩擦得透亮"),
     oc("f2", "沈砚", "换好塔顶的灯芯"),
     ap("f3", "叶知微", "袖口沾了铜油")])
src("t12", "P2-two-actor", "loc_alley", None, "入夜", "小雨", "纸灯笼",
    "排水沟有水声", ["沈砚", "阿棠"], ["油纸伞", "纸灯笼", "鱼筐", "排水沟"], "沈砚",
    [mv("f0", "阿棠", "早市", "潮生巷"),
     oc("f1", "沈砚", "把油纸伞收拢靠在墙根"),
     oc("f2", "阿棠", "把鱼筐放在门槛边"),
     ap("f3", "沈砚", "鞋底沾了湿石板的水")])

# ---- P3 移动接动作
src("t13", "P3-move-then-act", "loc_archive", None, "午后", "阴", "铜灯",
    "天窗漏进灰光", ["叶知微"], ["干纸", "潮汐簿", "铜灯", "墨"], "叶知微",
    [mv("f0", "叶知微", "早市", "潮汐档案馆"),
     oc("f1", "叶知微", "把一叠干纸放在桌角"),
     ap("f2", "叶知微", "袖口沾了墨")])
src("t14", "P3-move-then-act", "loc_seawall", "堤面", "傍晚", "雾", "警示灯",
    "风把浪沫吹上堤面", ["顾行舟"], ["钟架", "缆绳", "钟绳", "警示灯"], "顾行舟",
    [mv("f0", "顾行舟", "潮渡", "雾堤"),
     oc("f1", "顾行舟", "把缆绳绕在钟架上"),
     ap("f2", "顾行舟", "外袍下摆被雾水打湿")])
src("t15", "P3-move-then-act", "loc_ferry", "栈桥", "清晨", "薄雾", "船灯",
    "河面只有船灯", ["韩渡"], ["渡船", "木桩", "缆绳", "船灯"], "韩渡",
    [mv("f0", "韩渡", "潮生巷", "潮渡"),
     oc("f1", "韩渡", "把渡船推离栈桥"),
     ap("f2", "韩渡", "手背沾着盐沫")])
src("t16", "P3-move-then-act", "loc_alley", None, "雨后", "雨停", "纸灯笼",
    "墙根还在滴水", ["沈砚"], ["油布包", "备用钥匙", "纸灯笼", "石板"], "沈砚",
    [mv("f0", "沈砚", "潮汐档案馆", "潮生巷"),
     oc("f1", "沈砚", "把备用钥匙塞进油布包的内层"),
     sa("f2", "沈砚")])
src("t17", "P3-move-then-act", "loc_market", None, "清晨", "薄雾", "棚下散光",
    "白汽不散", ["阿棠"], ["银鳞鱼", "鱼筐", "案板", "抹布"], "阿棠",
    [mv("f0", "阿棠", "潮生巷", "早市"),
     oc("f1", "阿棠", "把银鳞鱼搬上案板"),
     ap("f2", "阿棠", "辫梢沾了白汽")])
src("t18", "P3-move-then-act", "loc_lighthouse", "塔顶", "夜", "夜雾，海风",
    "铜灯已点亮", "风硬，铜灯罩嗡嗡响", ["叶知微"],
    ["铜灯罩", "抹布", "擦铜油", "灯芯"], "叶知微",
    [mv("f0", "叶知微", "潮渡", "旧灯塔"),
     oc("f1", "叶知微", "把灯罩擦得透亮"),
     ap("f2", "叶知微", "袖口沾了铜油"),
     oc("f3", "叶知微", "把抹布搭回梯脚")])

# ---- P4 多对象描写
src("t19", "P4-multi-object", "loc_market", None, "清晨", "薄雾", "棚下散光",
    "白汽不散", ["沈砚", "阿棠"], ["银鳞鱼", "鱼筐", "案板", "油纸伞"], "沈砚",
    [ap("f0", "阿棠", "袖口沾了鱼鳞"),
     ap("f1", "沈砚", "外袍下摆沾了泥水"),
     oc("f2", "阿棠", "把银鳞鱼装进鱼筐"),
     oc("f3", "沈砚", "把油纸伞收拢靠在摊棚边")])
src("t20", "P4-multi-object", "loc_seawall", "堤面", "夜", "浓雾", "警示灯",
    "浪沫打到石壁上", ["沈砚", "韩渡"], ["警示灯", "钟绳", "钟架", "铁链"], "沈砚",
    [ap("f0", "警示灯", "铜框玻璃罩被风吹歪", "items"),
     ap("f1", "钟绳", "磨出了毛边", "items"),
     oc("f2", "沈砚", "把警示灯扶正"),
     oc("f3", "韩渡", "把钟绳重新绕在钟架上")])
src("t21", "P4-multi-object", "loc_archive", None, "夜", "小雨", "铜灯",
    "雨声压在窗外", ["沈砚", "叶知微"], ["潮汐簿", "铜灯", "干纸", "墨"], "沈砚",
    [ap("f0", "潮汐簿", "缺页的边缘毛糙", "items"),
     ap("f1", "铜灯", "灯罩上积了灰", "items"),
     oc("f2", "沈砚", "把铜灯擦亮"),
     oc("f3", "叶知微", "把干纸放在桌角")])
src("t22", "P4-multi-object", "loc_ferry", "浅滩", "退潮", "雾", "天光",
    "泥滩上留着水痕", ["顾行舟", "沈砚"], ["系泊绳", "木桩", "渡船", "缆绳"], "沈砚",
    [ap("f0", "系泊绳", "泥水结了一层白盐", "items"),
     ap("f1", "木桩", "缠着的旧缆绳断了", "items"),
     oc("f2", "顾行舟", "把缆绳重新绕上木桩"),
     oc("f3", "沈砚", "把系泊绳拖回岸上")])
src("t23", "P4-multi-object", "loc_lighthouse", "塔顶", "夜", "夜雾，海风",
    "铜灯已点亮", "风硬，铜灯罩嗡嗡响", ["叶知微", "沈砚"],
    ["铜灯罩", "铁链", "灯芯", "抹布"], "沈砚",
    [ap("f0", "铜灯罩", "玻璃上蒙了盐雾", "items"),
     ap("f1", "铁链", "链环上结了锈", "items"),
     oc("f2", "叶知微", "把灯罩擦得透亮"),
     oc("f3", "沈砚", "换好塔顶的灯芯")])
src("t24", "P4-multi-object", "loc_alley", None, "雨后", "雨停", "纸灯笼",
    "墙根还在滴水", ["沈砚", "阿棠"], ["纸灯笼", "排水沟", "鱼筐", "石板"], "沈砚",
    [ap("f0", "纸灯笼", "被风扯破一角", "items"),
     ap("f1", "排水沟", "里面积了泥", "items"),
     oc("f2", "沈砚", "把纸灯笼扶正"),
     oc("f3", "阿棠", "把鱼筐放在门槛边")])


def scene_block(s):
    L = WORLD["locations"][s["loc"]]
    path = L["name"] if not s["sub"] else f'{L["name"]}>{s["sub"]}'
    feats = list(L.get("features") or [])
    if s["sub"]:
        for sub in L["sublocations"]:
            if sub["name"] == s["sub"]:
                feats = [sub["appearance"]] + feats
    return path, "、".join(feats[:6]) + \
        f'；{s["weather"]}；{s["time"]}；{s["light"]}；{s["atmosphere"]}'


def fact_line(f):
    k = f["kind"]
    if k == "moved":
        return f'{f["factId"]}｜移动｜{f["name"]}｜{f["from"]}→{f["to"]}'
    if k == "outcome":
        return f'{f["factId"]}｜结果｜{f["name"]}｜{f["resultText"]}'
    if k == "appearance_changed":
        return f'{f["factId"]}｜外观｜{f["name"]}｜{f["text"]}'
    if k == "sanity_changed":
        d = "上升" if f["to"] > f["from"] else "下降"
        return f'{f["factId"]}｜理智｜{f["name"]}｜{d}'
    raise ValueError(k)


def paragraph_input(s):
    path, app = scene_block(s)
    people = []
    for name in s["present"]:
        cid = next(k for k, v in WORLD["characters"].items() if v["name"] == name)
        c = WORLD["characters"][cid]
        items = "、".join(WORLD["items"][i]["name"] for i in c.get("inventory") or [])
        people.append(f'{c["name"]}｜性格={c["personality"]}｜外貌={c["appearance"]}'
                      f'｜随身={items}')
    by_name = {v["name"]: v for v in WORLD["items"].values()}
    visible = [f'{n}={by_name[n].get("appearance", "")}'
               for n in s["visible"] if n in by_name]
    return ("叙事任务。\n场景：\n" f"地点={path}\n地点外貌={app}\n" "人物：\n"
            + "\n".join(people) + "\n可见：\n" + "\n".join(visible) + "\n事实：\n"
            + "\n".join(fact_line(f) for f in s["facts"]) + "\n分组：\n"
            f'G1｜{" ".join(f["factId"] for f in s["facts"])}｜组后时间=过去了一会儿\n'
            f'视角：{s["pov"]}；第三人称限知；只写{s["pov"]}的内心，他人只写可见动作。\n'
            "要求：写场景、行动与视角人物心理；不写任务标题、数值面板、具体时长、字段名；"
            "不新增未列出的具名人物/物品/地点；他人只写可见动作。\n正文：\n")


def unit_input(s, f):
    path, _ = scene_block(s)
    L = WORLD["locations"][s["loc"]]
    feats = list(L.get("features") or [])
    if s["sub"]:
        for sub in L["sublocations"]:
            if sub["name"] == s["sub"]:
                feats = [sub["appearance"]] + feats
    by_name = {v["name"]: v for v in WORLD["items"].values()}
    items = [n for n in s["visible"] if n in by_name]
    return ("短句任务。\n" f"地点={path}\n地点可见={'、'.join(items + feats[:6])}\n"
            f'场景={s["time"]}；{s["weather"]}；{s["light"]}\n'
            f'视角={s["pov"]}；第三人称\n'
            f"事实={fact_line(f).split('｜', 1)[1]}\n"
            + (f'方向={f.get("direction", "平")}\n' if f["kind"] == "moved" else "")
            + "要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；"
              "只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；"
              "不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。\n短句：\n")


def main():
    charnames = {v["name"] for v in WORLD["characters"].values()}
    itemnames = {v["name"] for v in WORLD["items"].values()}
    features = set()
    for L in WORLD["locations"].values():
        features |= set(L.get("features") or [])
        for sub in L.get("sublocations") or []:
            features |= set((sub.get("appearance") or "").replace("、", " ").split())
    locn = set()
    for L in WORLD["locations"].values():
        locn.add(L["name"])
        locn |= {x["name"] for x in L.get("sublocations") or []}
    problems, out = [], []
    for s in S:
        if not (3 <= len(s["facts"]) <= 5):
            problems.append(f'{s["id"]}: 事实数不在 3–5')
        ids = [f["factId"] for f in s["facts"]]
        if len(ids) != len(set(ids)):
            problems.append(f'{s["id"]}: factId 重复')
        for f in s["facts"]:
            if f["kind"] == "moved" and (f["from"] not in locn or f["to"] not in locn):
                problems.append(f'{s["id"]}/{f["factId"]}: 地点不在世界表')
            # 场景特征（木桩、铁链、纸灯笼这类）也可以作外观事实的主体：
            # 它们在 world.json 的 features 里，是可看见的实体。
            if f["name"] not in charnames and f["name"] not in itemnames                     and f["name"] not in features:
                problems.append(f'{s["id"]}/{f["factId"]}: 主体不在世界表')
            key = f.get("resultText") or f.get("text") or ""
            if re.search(r"[0-9]", key):
                problems.append(f'{s["id"]}/{f["factId"]}: 事实文本含数字')
            for it in s["visible"]:
                if it not in itemnames and it not in features:
                    problems.append(f'{s["id"]}: 可见物 {it} 既不是物品也不是场景特征')
        out.append({"id": s["id"], "pattern": s["pattern"], "pov": s["pov"],
                    "facts": s["facts"],
                    "mustExpress": [f["factId"] for f in s["facts"]],
                    "aliases": {f["name"]: ALIASES[f["name"]] for f in s["facts"]
                                if f["name"] in ALIASES},
                    "paragraphInput": paragraph_input(s),
                    "unitInputs": {f["factId"]: unit_input(s, f) for f in s["facts"]}})
    rec = {"purpose": "24 multi-fact sources for the cohesion check; no reference prose",
           "world": "world.json",
           "rubric": {
               "factLevel": "逐 factId 记 S(支持)/O(遗漏)/C(矛盾)/A(归属错误)，"
                            "另记未在事实里的新事件",
               "sourceLevel": "必述完整且无错误新增 = 所有 fact 为 S 且无新事件",
               "cohesion": "衔接 1–5、重复次数、指代是否清楚、清单感 1–5",
               "aliases": "地点/物件可用别名，不计为新增实体",
           },
           "sources": out, "problems": problems}
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("sources", len(out), "| facts", sum(len(s["facts"]) for s in out),
          "| patterns", dict(Counter(s["pattern"] for s in out)))
    print("problems", len(problems), problems[:6])
    print("->", OUT)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
