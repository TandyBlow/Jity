# Generate a scene-sentence corpus by controlled grammar (v2).
#
# Predicates are pooled by grammatical shape, not just material:
#   state  : subject + stative VP           石阶湿得发亮 / 木门冻住了
#   on     : locative post-position VP      落着雪 / 结着霜 / 蒙着灰
#   motion : bare intransitive VP           在风里晃 / 在雾里响 / 滴着水
#   caused : transitive result VP (把 only)  吹得发晃 / 掀起一角 / 压得发弯
#   clause : already a full clause         凉气往上冒 / 缝里塞着旧布
# Frames pick specific pools, so no frame can host a shape it cannot take.
#
# Holdout: unseen nouns (8) and unseen frames (F6 two-clause, F7 locative+on).
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/gen_scene_corpus.py

import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

OUT_TRAIN = HERE / "scenegen_pairs.jsonl"
OUT_DEV = HERE / "scenegen_dev.jsonl"
OUT_HF = HERE / "scenegen_holdout_frame.jsonl"
OUT_HN = HERE / "scenegen_holdout_noun.jsonl"

LOCS = {
    "stone": ["堤上", "桥头", "巷口", "塔下", "院墙外", "栈桥边", "旧码头",
              "石级上"],
    "wood": ["驿站", "棚下", "塔下", "院墙外", "栈桥边", "渡口", "门廊里"],
    "metal": ["桥头", "塔下", "棚下", "栈桥边", "渡口", "旧码头"],
    "rope": ["驿站", "棚下", "院墙外", "渡口", "门廊里"],
    "water": ["堤上", "桥头", "溪边", "栈桥边", "石级上"],
    "plant": ["溪边", "院墙外", "堤上", "巷口", "旧码头"],
    "fire": ["驿站", "棚下", "门廊里", "客房"],
    "air": ["堤上", "桥头", "溪边", "巷口", "山口", "旧码头"],
}

NOUNS = {
    "石阶": "stone", "石壁": "stone", "石桥": "stone", "石堆": "stone",
    "石台": "stone", "石缝": "stone", "石板": "stone", "门槛": "stone",
    "木门": "wood", "木梯": "wood", "木栏": "wood", "门板": "wood",
    "木箱": "wood", "木桩": "wood", "棚柱": "wood", "窗框": "wood",
    "铁链": "metal", "铜环": "metal", "铜铃": "metal", "灯罩": "metal",
    "铁皮": "metal",
    "麻绳": "rope", "草帘": "rope", "帆布": "rope", "窗纸": "rope",
    "冰面": "water", "冰棱": "water", "水洼": "water", "溪水": "water",
    "雪堆": "water", "霜花": "water",
    "枯草": "plant", "干草": "plant", "苔藓": "plant", "树枝": "plant",
    "炭火": "fire", "炭盆": "fire", "油灯": "fire", "马灯": "fire",
    "纸灯笼": "fire", "火苗": "fire",
    "雪粒": "air", "雾气": "air", "浪头": "air",
}
HOLDOUT_NOUNS = ["石碑", "石径", "木桶", "瓦檐", "铜锁", "旧布", "草绳",
                 "霜凌"]
NOUNS.update({"石碑": "stone", "石径": "stone", "木桶": "wood",
              "瓦檐": "wood", "铜锁": "metal", "旧布": "rope",
              "草绳": "rope", "霜凌": "water"})

POOLS = {
    "stone": {
        "state": ["湿得发亮", "结着一层薄冰", "边角结着霜", "冻得发脆",
                  "边上塌了一块", "颜色比别处深",
                  "磨得圆滑", "积着一层薄雪"],
        "on": ["落着一层雪", "积着雪", "塞着化了一半的雪", "盖着薄雪"],
        "clause": ["缝里塞着雪", "边上积着水", "石面泛着冷光"],
    },
    "wood": {
        "state": ["冻住了", "合页松了", "边角翘起",
                  "磨得发亮",
                  "摸上去发凉"],
        "on": ["结着一层霜", "积着雪", "搭着一块旧布", "蒙着一层灰"],
        "clause": ["缝里塞着旧布", "边角翘起一块", "木头泛着潮气"],
    },
    "metal": {
        "state": ["冻得发脆", "边上锈了一圈", "冻在一起",
                  "摸上去冰凉", "表面起了白霜",
                  "被磨得发亮", "边角卷起", "蒙着水汽", "发乌"],
        "on": ["挂着一层霜", "积着雪", "盖着薄雪", "落着霜"],
        "clause": ["边上锈了一圈", "响声很低", "表面起了白霜"],
    },
    "rope": {
        "state": ["冻得发硬", "被雪水浸透", "边角磨散了", "绷得很紧",
                  "垂在一边", "松了半圈", "起了毛边", "被拉得发长",
                  "颜色发灰", "摸上去扎手"],
        "on": ["挂着一层霜", "积着雪", "蒙着一层霜", "搭在柱子上"],
        "clause": ["一头垂在地上", "边上磨散了", "绳结冻硬了"],
    },
    "water": {
        "state": ["结着一层薄冰", "边上有碎冰", "裂开一道缝",
                  "反着灰白的光",
                  "泛着冷光", "边上结了霜", "水位很低"],
        "on": ["落着雪", "积着雪", "盖着一层雪", "浮着薄冰"],
        "clause": ["底下的水还在流", "凉气往上冒", "水面泛着冷光"],
    },
    "plant": {
        "state": ["颜色发黄", "冻得发脆", "边上露出黑土",
                  "贴着地面", "枯了一半",
                  "结着霜", "摸上去扎手"],
        "on": ["挂着一层霜", "积着雪", "压着一层雪", "蒙着薄霜"],
        "clause": ["从雪里支出来", "边上露出黑土", "草根冻在土里"],
    },
    "fire": {
        "state": ["压得很低", "烧透了一半", "只剩一点暗红", "冒着白汽",
                  "映得墙上发红", "火苗很稳", "烧得发响", "暗下去",
                  "边上覆着白灰", "亮着"],
        "on": ["落了一层灰", "盖着一层白灰", "积着炭灰"],
        "clause": ["偶尔炸出一声轻响", "照出一圈暖光", "边上覆着白灰"],
    },
    "air": {
        "state": ["",
                  "压在石面上", "很密", "发白", "贴着地面",
                  ""],
        "on": ["落着一层雪", "积着雪", "蒙着白汽"],
        "clause": ["从山口灌下来", "打在石头上"],
    },
}

FRAMES = {
    "F1": ("{N}{P}", {"state"}),
    "F2": ("{N}上{P}", {"on"}),
    "F3": ("{L}的{N}{P}", {"state"}),
    "F4": ("{L}的{N}上{P}", {"on"}),
}
HOLDOUT_FRAMES = {"F4"}
NOUN_EXTRA = {
    "石阶": ["踩上去发滑", "边角磨圆了"],
    "石板": ["踩上去发滑", "缝里塞着泥"],
    "木门": ["推起来发涩", "漆皮掉了大半", "合页松了"],
    "门板": ["边角翘起", "蒙着一层灰"],
    "木梯": ["横档裂了一级", "踩上去会晃"],
    "木箱": ["角上包着铁皮", "盖子合不严"],
    "木栏": ["有一根断了", "被雪压得发弯"],
    "棚柱": ["底下垫着石头", "被风吹得发响"],
    "窗框": ["糊着旧窗纸", "边角翘起"],
    "铁链": ["锈迹很深", "一环扣着一环"],
    "铜铃": ["铃舌被绳子系住", "内壁发黑"],
    "冰面": ["有一道裂痕", "薄得能看见水"],
    "溪水": ["很浅", "绕着一块石头流"],
    "枯草": ["被雪压弯", "从雪里支出来"],
    "树枝": ["被雪压弯", "挂着冰碴"],
    "炭火": ["偶尔炸出一声轻响", "照出一圈暖光"],
    "油灯": ["火苗很小", "灯芯烧黑了"],
    "纸灯笼": ["糊纸破了一角", "骨架有点歪"],
    "雪粒": ["打在石头上", "钻进缝里"],
    "雾气": ["散不开", "把声音压得很近"],
    "浪头": ["撞在石壁上", "翻起白沫"],
}
PATIENT = {"wood", "rope", "plant", "water", "air"}
WIND = ["风", "雾", "雪", "夜", "雨"]
LOCATIVE_NOUNS = {"石缝", "门槛", "石壁", "石桥", "石台", "窗框", "棚柱",
                  "石径", "瓦檐"}


# predicate -> the noun must contain one of these characters (or must avoid
# them). Without this, the model is taught "石碑上塞着雪" and "铜锁边角卷起".
PRED_NEEDS = {
    "边角翘起": "门板框箱桶台阶",
    "边角磨散了": "布纸帘帆绳",
    "边角结着霜": "阶台板堆径桥壁",
    "边上结了霜": "水洼溪水",
    "边上露出黑土": "草",
    "边上有碎冰": "水冰",
    "边角卷起": "布纸帘帆",
    "边上塌了一块": "堆台阶墙径",
    "边角磨圆了": "阶板台径",
    "湿得发亮": "阶板径桥壁台",
    "颜色比别处深": "阶板径台壁",
    "结着一层薄冰": "阶板径台桥水洼",
    "冻得发脆": "阶板径台木枝草铜铁",
    "摸上去冰凉": "链环铃皮锁",
    "摸上去扎手": "草布绳",
    "颜色发灰": "布绳帆帘",
    "颜色发黄": "草枝",
    "漆皮": "门板框",
    "合页": "门板框",
    "推起来发涩": "门板框",
    "横档": "梯",
    "踩上去会晃": "梯",
    "搭着一块旧布": "栏桩柱框",
    "蒙着一层灰": "框板箱梯柱",
    "蒙着一层霜": "帘布绳",
    "盖着一层白灰": "盆火",
    "落了一层灰": "盆火",
    "浮着薄冰": "水洼溪水",
    "边上有碎冰": "水洼溪水冰面",
    "裂开一道缝": "冰板台壁",
    "薄得能看见水": "冰",
    "有一道裂痕": "冰",
    "水位很低": "溪水",
    "碎成一小片": "水洼溪水",
    "泛着冷光": "冰水",
    "盖着一层雪": "水冰草枝",
    "压着一层雪": "草枝",
    "蒙着薄霜": "草枝",
    "从雪里支出来": "草枝",
    "草根冻在土里": "草",
    "边上露出黑土": "草",
    "火苗很小": "灯火",
    "灯芯烧黑了": "灯火",
    "偶尔炸出一声轻响": "炭火",
    "照出一圈暖光": "灯火",
    "糊纸破了一角": "灯笼",
    "骨架有点歪": "灯笼",
    "铃舌被绳子系住": "铃",
    "内壁发黑": "铃",
    "打在石头上": "雪粒浪头",
    "钻进缝里": "雪粒",
    "翻起白沫": "浪头",
    "撞在石壁上": "浪头",
    "散不开": "雾气",
    "把声音压得很近": "雾气",
    "一角垂在地上": "布绳帘",
    "一头垂在地上": "绳布",
    "绳结冻硬了": "绳",
    "合页松了": "门板框",
    "塞着": "缝", "卷起": "布纸帘帆", "塌了": "堆台阶墙径",
    "磨圆": "阶板台径", "踩上去": "阶板径桥台", "裂了一级": "梯",
    "合页": "门板框", "漆皮": "门板框箱", "铃舌": "铃", "内壁": "铃",
    "灯芯": "灯火灯", "糊纸": "灯笼窗纸", "骨架": "灯笼",
    "横档": "梯", "包着铁皮": "箱", "垫着石头": "柱",
    "一环扣着一环": "链",
}
PRED_AVOIDS = {
    "结了霜": "霜冰",
    "结着霜": "霜冰",
    "结了霜": "霜冰", "盖着一层白灰": "冰水", "冒着白汽": "冰雪",
    "裂开一道缝": "草", "碎成一小片": "草枝",
}


def pred_fits(pred, noun):
    for key, need in PRED_NEEDS.items():
        if key in pred and not any(ch in noun for ch in need):
            return False
    for key, avoid in PRED_AVOIDS.items():
        if key in pred and any(ch in noun for ch in avoid):
            return False
    return True


def clean(s):
    if not (10 <= len(s) <= 40):
        return False
    if re.search(r"[0-9０-９]", s):
        return False
    if re.search(r"(\S{2,4})的\1", s):
        return False
    gs = [s[i:i + 2] for i in range(len(s) - 1)]
    return not any(gs.count(g) >= 3 for g in set(gs))


def build_input(noun, loc, scene):
    return (
        "场景短句。\n"
        f"地点={loc}\n"
        f"场景={scene}\n"
        f"现象={noun}\n"
        "要求：围绕现象写一到两句环境描写；只引用现象与场景给的东西；"
        "不写人物动作、任务、数值、时长；不新增人物、物品、地点。\n"
        "短句："
    )


def main():
    rows, seen = [], set()
    scenes = ["清晨；雪，横风；高；灰白", "傍晚；雪；低；炭火",
              "夜；雾；中；油灯", "午后；雨；低；灰光",
              "黎明；雾，湿冷；中；船灯", "入夜；小雨；低；纸灯笼",
              "清晨；晴，薄冰；低；冷光", "夜里；雪停；高；月光"]
    for noun, mat in NOUNS.items():
        locs = LOCS[mat]
        pools = POOLS[mat]
        for fid in FRAMES:
            unseen_frame = fid in HOLDOUT_FRAMES
            unseen_noun = noun in HOLDOUT_NOUNS
            if unseen_frame and unseen_noun:
                continue
            split = ("holdout_frame" if unseen_frame else
                     "holdout_noun" if unseen_noun else "train")
            frame, kinds = FRAMES[fid]
            pool_list = list(pools.get(kinds.pop() if False else list(kinds)[0], []))
            for kind in kinds:
                cands = list(pools.get(kind, [])) + (
                    NOUN_EXTRA.get(noun, []) if kind == "state" else [])
                for pred in cands:
                    if not pred_fits(pred, noun):
                        continue
                    for i, loc in enumerate(locs):
                        scene = scenes[len(rows) % len(scenes)]
                        N = ("{L}的" + noun) if noun in LOCATIVE_NOUNS else noun
                        sent = frame.format(
                            N=N.format(L=loc), P=pred, W=WIND[len(rows) % len(WIND)],
                            L=loc, N2=N.format(L=loc),
                            P2=pools["state"][(len(rows) + 1)
                                              % len(pools["state"])])
                        if not clean(sent):
                            continue
                        key = (noun, sent)
                        if key in seen:
                            continue
                        seen.add(key)
                        rows.append({
                            "pairId": "sg:" + hashlib.sha256(
                                f"{noun}|{sent}".encode()).hexdigest()[:12],
                            "noun": noun, "material": mat, "frame": fid,
                            "kind": kind, "predicate": pred,
                            "input": build_input(noun, loc, scene),
                            "target": sent, "split": split,
                        })
    train = [r for r in rows if r["split"] == "train"]
    hf = [r for r in rows if r["split"] == "holdout_frame"]
    hn = [r for r in rows if r["split"] == "holdout_noun"]
    hf = [r for i, r in enumerate(hf) if i % max(1, len(hf) // 300) == 0][:300]
    hn = [r for i, r in enumerate(hn) if i % max(1, len(hn) // 300) == 0][:300]
    dev = train[::20]
    train = [r for r in train if r not in dev]
    for out, part in ((OUT_TRAIN, train), (OUT_DEV, dev),
                      (OUT_HF, hf), (OUT_HN, hn)):
        body = chr(10).join(json.dumps(r, ensure_ascii=False)
                            for r in part) + chr(10)
        out.write_text(body, encoding="utf-8", newline=chr(10))
    print(f"train {len(train)} dev {len(dev)} "
          f"holdout_frame {len(hf)} holdout_noun {len(hn)}")
    print("unseen nouns", HOLDOUT_NOUNS)
    print("unseen frames", sorted(HOLDOUT_FRAMES))
    print("unique sentences", len({r["target"] for r in rows}))


if __name__ == "__main__":
    main()
