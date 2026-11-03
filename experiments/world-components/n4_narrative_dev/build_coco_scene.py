# Build a generic scene-sentence corpus from COCO-CN (MIT).
#
# The component split this supports:
#   model  -> weather, sky, light, ground, distance (what COCO-CN teaches)
#   slots  -> the location's own props (what only the world data knows)
#
# Input is only place + scene conditions; no phenomenon name, so the model is
# never asked to invent predicates for an unseen object.
#
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/build_coco_scene.py

import collections
import json
import pathlib
import random
import re

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parent / "_ext" / "coco-cn-version1805v1.1" / \
    "imageid.human-written-caption.txt"
OUT_TRAIN = HERE / "coco_scene_pairs.jsonl"
OUT_DEV = HERE / "coco_scene_dev.jsonl"
OUT_EVAL = HERE / "coco_scene_eval.json"

BAN_PEOPLE = set("人男女老少孩他她你我咱众警运动员游客司机工农家学师婴娘婚侣庭友群")
BAN_WORDS = [
    "一只", "一条", "一头", "一匹", "一群", "一位", "一名",
    "狗", "猫", "马", "牛", "羊", "鸟", "鸡", "鸭", "鱼", "熊", "象",
    "鹿", "猴", "兔", "鼠", "狮", "虎", "豹", "企鹅", "海豚", "鲸",
    "蝴蝶", "昆虫", "海鸥",
    "车", "巴士", "飞机", "火车", "电脑", "手机", "电视", "相机",
    "自行车", "摩托", "滑板", "键盘", "屏幕", "广告牌", "电线",
    "床", "沙发", "柜", "行李", "花瓶", "食物", "碗", "盘", "杯",
    "穿着", "戴着", "拿着", "站着", "坐着", "躺着", "骑着", "抱着",
    "比赛", "运动员", "招牌",
]
SCENE_WORDS = [
    "雪", "雨", "雾", "风", "云", "天空", "水", "河", "湖", "海",
    "山", "树", "草", "花", "石", "木", "门", "窗", "墙", "桥",
    "路", "街", "灯", "光", "夜", "黄昏", "清晨", "冰", "霜", "沙",
    "土", "田", "林", "岸", "滩", "崖", "谷", "溪", "瀑", "屋",
    "房", "塔", "台阶", "栏杆", "棚", "帆", "绳", "铃",
]


def infer(text: str):
    weather = "晴"
    if "雪" in text:
        weather = "雪"
    elif "雨" in text:
        weather = "雨"
    elif "雾" in text:
        weather = "雾"
    elif "风" in text:
        weather = "风"
    time = "白天"
    if any(w in text for w in ("深夜", "晚上", "夜晚", "夜色", "夜空")):
        time = "夜"
    elif any(w in text for w in ("黄昏", "夕阳", "日落")):
        time = "黄昏"
    elif any(w in text for w in ("清晨", "早晨", "日出", "黎明")):
        time = "清晨"
    elif any(w in text for w in ("午后", "下午")):
        time = "午后"
    wind = "高" if any(w in text for w in ("大风", "狂风", "风暴")) else (
        "中" if "风" in text else "低")
    light = "灰光"
    if "月光" in text or "月亮" in text:
        light = "月光"
    elif "灯" in text:
        light = "灯火"
    elif any(w in text for w in ("阳光", "太阳", "日照", "晴空")):
        light = "日头"
    loc = "野外"
    for key, name in (("沙滩", "沙滩"), ("海滩", "海滩"), ("森林", "树林"),
                       ("树林", "树林"), ("街道", "街道"), ("城市", "街道"),
                       ("房间", "屋内"), ("屋子", "屋内"), ("湖", "湖边"),
                       ("河", "河边"), ("海", "海边"), ("山", "山里"),
                       ("田", "田边"), ("公园", "公园")):
        if key in text:
            loc = name
            break
    return time, weather, wind, light, loc


def build_input(loc, scene):
    parts = [
        "场景短句。",
        "地点=" + loc,
        "场景=" + scene,
        "要求：写一到两句这个场景里的环境；只写看得见的天光、天气、地面"
        "和远处的东西；不写人物、动物、车辆、室内家具；"
        "不写任务、数值、时长。",
        "短句：",
    ]
    return chr(10).join(parts) + chr(10)


def main():
    rows, seen = [], set()
    for line in SRC.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        _, text = line.split("\t", 1)
        text = text.strip()
        if not (8 <= len(text) <= 40):
            continue
        if any(c in text for c in BAN_PEOPLE):
            continue
        if any(w in text for w in BAN_WORDS):
            continue
        if not any(w in text for w in SCENE_WORDS):
            continue
        if re.search(r"[0-9０-９]", text):
            continue
        if text in seen:
            continue
        seen.add(text)
        time, weather, wind, light, loc = infer(text)
        scene = "；".join([time, weather, wind, light])
        rows.append({
            "id": "coco:" + str(len(rows)),
            "loc": loc, "time": time, "weather": weather,
            "wind": wind, "light": light,
            "scene": scene,
            "input": build_input(loc, scene),
            "target": text,
            "source": "COCO-CN (MIT), li-xirong/coco-cn",
        })
    random.seed(7)
    random.shuffle(rows)
    dev = rows[:120]
    train = rows[120:]
    for path, part in ((OUT_TRAIN, train), (OUT_DEV, dev)):
        body = chr(10).join(json.dumps(r, ensure_ascii=False) for r in part) + chr(10)
        path.write_text(body, encoding="utf-8", newline=chr(10))
    print(f"train {len(train)} dev {len(dev)}")
    print("weather", collections.Counter(r["weather"] for r in rows))
    print("time", collections.Counter(r["time"] for r in rows))
    print("loc", collections.Counter(r["loc"] for r in rows).most_common(8))


if __name__ == "__main__":
    main()
