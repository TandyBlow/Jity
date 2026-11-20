# Generate the scene-sentence corpus (v3): wider noun/locative/scene/frame space.
#
# Constraints that keep sentences grammatical and collocation-safe:
#   noun  -> material class, allowed locations
#   pred  -> grammatical shape pool (state / on / clause / motion / caused)
#   pred x noun -> PRED_NEEDS / PRED_AVOIDS compatibility table
#   frame -> which shape pool it accepts
# Holdout: 8 nouns never seen, and 2 frames never seen.
#
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/gen_scene_corpus.py

import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

OUT = {
    "train": HERE / "scenegen_pairs.jsonl",
    "dev": HERE / "scenegen_dev.jsonl",
    "holdout_noun": HERE / "scenegen_holdout_noun.jsonl",
    "holdout_frame": HERE / "scenegen_holdout_frame.jsonl",
}

LOCS = {
    "stone": ["堤上", "桥头", "巷口", "塔下", "院墙外", "栈桥边", "旧码头",
              "石级上", "井台边", "堤角", "渡口", "山口", "驿道旁", "墙根",
              "坡下", "门洞外"],
    "wood": ["驿站", "棚下", "塔下", "院墙外", "栈桥边", "渡口", "门廊里",
             "客房", "灶间", "柴房", "廊下", "柜台后", "铺面里", "耳房",
             "楼上", "院中"],
    "metal": ["桥头", "塔下", "棚下", "栈桥边", "渡口", "旧码头", "门廊里",
              "灶间", "井台边", "廊下", "柜台后", "院墙外", "楼上", "柴房",
              "铺面里", "耳房"],
    "rope": ["驿站", "棚下", "院墙外", "渡口", "门廊里", "柴房", "廊下",
             "铺面里", "客房", "灶间", "院中", "柜台后"],
    "water": ["堤上", "桥头", "溪边", "栈桥边", "石级上", "堤角", "渡口",
              "旧码头", "坡下", "墙根", "井台边", "驿道旁"],
    "plant": ["溪边", "院墙外", "堤上", "巷口", "旧码头", "坡下", "墙根",
              "驿道旁", "院中", "山口", "桥头", "堤角"],
    "fire": ["驿站", "棚下", "门廊里", "客房", "灶间", "廊下", "柜台后",
             "铺面里", "耳房", "楼上"],
    "air": ["堤上", "桥头", "溪边", "巷口", "山口", "旧码头", "坡下",
            "驿道旁", "栈桥边", "院内"],
}

NOUNS = {
    # stone
    "石阶": "stone", "石壁": "stone", "石桥": "stone", "石堆": "stone",
    "石台": "stone", "石缝": "stone", "石板": "stone", "门槛": "stone",
    "石墙": "stone", "石栏": "stone", "石柱": "stone", "石像": "stone",
    "石井": "stone", "石槽": "stone", "石墩": "stone", "井台": "stone",
    # wood
    "木门": "wood", "木梯": "wood", "木栏": "wood", "门板": "wood",
    "木箱": "wood", "木桩": "wood", "棚柱": "wood", "窗框": "wood",
    "木梁": "wood", "木柱": "wood", "木凳": "wood", "木桌": "wood",
    "木板": "wood", "木栅": "wood", "木匣": "wood", "木架": "wood",
    "木杆": "wood", "木檐": "wood", "柴门": "wood", "草棚": "wood",
    # metal
    "铁链": "metal", "铜环": "metal", "铜铃": "metal", "灯罩": "metal",
    "铁皮": "metal", "铁门": "metal", "铁栏": "metal", "铁钩": "metal",
    "铁钉": "metal", "铜盆": "metal", "铜壶": "metal", "铁环": "metal",
    "灯座": "metal", "铁锁": "metal", "铜钉": "metal",
    # rope / cloth / paper
    "麻绳": "rope", "草帘": "rope", "帆布": "rope", "窗纸": "rope",
    "布帘": "rope", "油布": "rope", "麻袋": "rope", "绳网": "rope",
    "草席": "rope", "布幌": "rope", "纸灯罩": "rope",
    # water / ice / snow
    "冰面": "water", "冰棱": "water", "水洼": "water", "溪水": "water",
    "雪堆": "water", "霜花": "water", "水面": "water", "冰层": "water",
    "积雪": "water", "雪面": "water", "水沟": "water", "溪岸": "water",
    "冰锥": "water",
    # plants
    "枯草": "plant", "干草": "plant", "苔藓": "plant", "树枝": "plant",
    "草垛": "plant", "草根": "plant", "树皮": "plant", "枝叶": "plant",
    "芦苇": "plant", "苔痕": "plant",
    # fire / light
    "炭火": "fire", "炭盆": "fire", "油灯": "fire", "马灯": "fire",
    "纸灯笼": "fire", "火苗": "fire", "灯火": "fire", "烛火": "fire",
    "炉火": "fire", "火盆": "fire", "炭灰": "fire",
    # weather
    "雪粒": "air", "雾气": "air", "浪头": "air", "风雪": "air",
    "雪花": "air", "浪花": "air",
}
HOLDOUT_NOUNS = ["石碑", "石径", "木桶", "瓦檐", "铜锁", "旧布", "草绳",
                 "霜凌"]
NOUNS.update({"石碑": "stone", "石径": "stone", "木桶": "wood",
              "瓦檐": "wood", "铜锁": "metal", "旧布": "rope",
              "草绳": "rope", "霜凌": "water"})

STATES = {
    "stone": ["湿得发亮", "结着一层薄冰", "边角结着霜", "冻得发脆",
              "边缘磨圆了", "边上塌了一块", "颜色比别处深", "蒙着一层灰",
              "表面起了白霜", "摸上去冰凉", "缝里长着苔藓", "一块块垒着",
              "被雪水浸得发暗", "棱角磨平了", "泛着灰白的光",
              "石面干了一半", "底下的土被冲开", "有一道浅槽",
              "接缝处塞着泥", "冻得合了缝"],
    "wood": ["冻住了", "合页松了", "边角翘起", "磨得发亮", "推起来发涩",
             "搭着一块旧布", "蒙着一层灰", "漆皮掉了大半", "木纹裂开",
             "摸上去发凉", "被熏得发黑", "关不严", "露出朽掉的边",
             "木色发暗", "接缝处裂开", "还带着树皮的痕", "被雪压得发弯",
             "底下垫着石头", "角上包着铁皮", "横档松了一级"],
    "metal": ["冻得发脆", "边上锈了一圈", "冻在一起", "摸上去冰凉",
              "表面起了白霜", "被磨得发亮", "蒙着水汽", "边角卷起",
              "挂钩松了", "内壁发黑", "锁舌卡住了", "提手磨得发亮",
              "锈成了褐色", "接缝处渗着水", "冻在木头上", "被雪压得发沉",
              "表面起了一层雾", "还留着油痕", "边沿磨薄了", "扣不严"],
    "rope": ["冻得发硬", "被雪水浸透", "边角磨散了", "绷得很紧",
             "垂在一边", "起了毛边", "颜色发灰", "摸上去扎手",
             "松了半圈", "结着霜", "绳股散开", "挂着冰碴",
             "被拉得发长", "一头垂在地上", "绳结冻硬了", "边沿脱了线",
             "蒙着一层白霜", "浸得发沉", "磨出了毛", "系成死结"],
    "water": ["结着一层薄冰", "边上有碎冰", "裂开一道缝",
              "反着灰白的光", "冻得发白", "泛着冷光", "水位很低",
              "碎成一小片", "盖着一层雪", "底下的水还在流",
              "凉气往上冒", "冰层薄得透明", "边沿冻住了", "一圈圈荡开",
              "映着灰白的天", "表面起了皱", "冻成一块", "边走边渗",
              "化了一半", "冒白汽"],
    "plant": ["被雪压弯", "颜色发黄", "冻得发脆", "边上露出黑土",
              "贴着地面", "枯了一半", "结着霜", "摸上去扎手",
              "草茎发白", "根须露在外面", "被踩得贴地", "挂着冰碴",
              "长到齐膝", "叶面卷起", "颜色发暗", "一丛丛立着",
              "草尖朝下", "被风吹得贴地", "底下是湿土", "折了几根"],
    "fire": ["压得很低", "烧透了一半", "只剩一点暗红", "冒着白汽",
             "火苗很稳", "烧得发响", "暗下去", "亮着", "映得墙上发红",
             "偶尔炸出一声轻响", "照出一圈暖光", "边缘结了炭花",
             "火舌舔着盆沿", "红光晃在墙上", "快熄了", "烧出细响",
             "盆沿烫手", "灰积了半寸", "火势很小", "跳了一下"],
    "air": ["散不开", "一阵紧一阵松", "压在石面上", "很密",
            "发白", "冷得刺骨", "看不清远处", "贴着地面",
            "横着扫过来", "一阵接一阵", "扑在脸上", "把声音压得很近",
            "卷着雪沫", "落在肩上", "慢慢飘", "越下越大", "细得像沙",
            "在光里发亮", "打在身上", "一片白"],
}

ONS = {
    "stone": ["落着一层雪", "积着雪", "塞着化了一半的雪", "盖着薄雪",
              "蒙着一层白霜", "铺着一层沙", "淌着水", "覆着薄冰"],
    "wood": ["结着一层霜", "积着雪", "搭着一块旧布", "蒙着一层灰",
             "盖着薄雪", "挂着草帘", "贴着旧纸", "落着雪"],
    "metal": ["挂着一层霜", "积着雪", "盖着薄雪", "落着霜",
              "缠着一圈麻绳", "挂着铃舌", "结着冰碴"],
    "rope": ["挂着一层霜", "积着雪", "蒙着一层霜", "搭在柱子上",
             "挂着冰碴", "结着薄冰", "压着雪"],
    "water": ["落着雪", "积着雪", "盖着一层雪", "浮着薄冰",
              "结着薄冰", "漂着碎冰"],
    "plant": ["挂着一层霜", "积着雪", "压着一层雪", "蒙着薄霜",
              "挂着冰碴", "落着雪"],
    "fire": ["落了一层灰", "盖着一层白灰", "积着炭灰", "蒙着薄灰"],
    "air": ["落着一层雪", "积着雪", "蒙着白汽", "飘着雪沫"],
}

# motion: only for nouns that plausibly move; used by 在{W}里 and 把 frames
MOTION = {
    "草帘": ["在风里乱甩", "被风掀起"], "帆布": ["在风里鼓起来", "被风掀起"],
    "布帘": ["在风里摆", "被风掀起"], "布幌": ["在风里晃", "打着旋"],
    "麻绳": ["在风里晃", "轻轻响"], "草绳": ["晃", "摆"],
    "绳网": ["晃", "垂着"], "油布": ["被风掀起一角", "翻卷"],
    "草席": ["被风掀起", "卷起一角"], "纸灯罩": ["在风里转", "晃"],
    "树枝": ["在风里晃", "抖"], "枝叶": ["在风里晃", "沙沙响"],
    "芦苇": ["在风里倒向一边", "晃"], "枯草": ["在风里抖", "伏下去"],
    "干草": ["被风吹散", "翻起"], "草垛": ["被风吹散一角"],
    "浪头": ["撞上石壁", "翻起白沫"], "浪花": ["溅起来", "散开"],
    "雪粒": ["被吹成一条线", "打在脸上"], "雪花": ["斜着落", "打着旋"],
    "风雪": ["横着扫过来", "灌进来"], "雾气": ["慢慢移过去", "贴着地面走"],
    "火苗": ["晃", "被吹得歪向一边"], "灯火": ["晃", "跳了一下"],
    "烛火": ["晃", "被吹灭又亮起"], "炉火": ["跳了一下", "暗下去"],
    "纸灯笼": ["晃", "转"], "草根": ["被风扯动"],
}

FRAMES = {
    "F1": ("{N}{P}", "state"),
    "F2": ("{N}上{P}", "on"),
    "F3": ("{L}的{N}{P}", "state"),
    "F5": ("{N}在{W}里{P}", "motion"),
    "F6": ("{N}{P}，{L}的{N2}{P2on}", "state"),
    "F7": ("{L}的{N}上{P}", "on"),
    "F8": ("{W}把{N}{P}", "motion"),
}
HOLDOUT_FRAMES = {"F6", "F7"}

PRED_NEEDS = {
    "缝": "缝", "塞着": "缝", "卷起": "布纸帘帆席", "塌了": "堆台阶墙径",
    "磨圆": "阶板台径沿", "踩上去": "阶板径桥台", "裂了一级": "梯",
    "横档": "梯", "合页": "门板框", "漆皮": "门板框", "铃舌": "铃",
    "内壁": "铃", "灯芯": "灯火灯", "糊纸": "灯笼窗纸", "骨架": "灯笼",
    "包着铁皮": "箱", "垫着石头": "柱", "扣着一环": "链",
    "边角翘起": "门板框箱桶台阶", "边角磨散了": "布纸帘帆席绳",
    "边角结着霜": "阶台板堆径桥壁", "边上结了霜": "水洼溪水",
    "边上露出黑土": "草根苔", "边上有碎冰": "水冰", "边角卷起": "布纸帘帆",
    "边上塌了一块": "堆台阶墙径", "边角磨圆了": "阶板台径沿",
    "湿得发亮": "阶板径桥壁台", "颜色比别处深": "阶板径台壁",
    "结着一层薄冰": "阶板径台桥水洼水面", "冻得发脆": "阶板径台木枝草铜铁",
    "摸上去冰凉": "链环铃皮锁钉柱", "摸上去扎手": "草布绳席",
    "颜色发灰": "布绳帆帘席", "颜色发黄": "草枝叶苇",
    "推起来发涩": "门板框", "踩上去会晃": "梯", "搭着一块旧布": "栏桩柱框",
    "蒙着一层灰": "框板箱梯柱梁凳桌匣架杆檐", "蒙着一层霜": "帘布绳席",
    "盖着一层白灰": "盆火", "落了一层灰": "盆火",
    "浮着薄冰": "水洼溪水水面", "漂着碎冰": "溪水水面水沟",
    "裂开一道缝": "冰板台壁层", "薄得透明": "冰", "有一道浅槽": "石板台",
    "水位很低": "溪水水沟", "碎成一小片": "水洼溪水", "泛着冷光": "冰水雪",
    "盖着一层雪": "水冰草枝", "压着一层雪": "草枝", "蒙着薄霜": "草枝",
    "火苗很小": "灯火", "灯芯烧黑了": "灯火", "偶尔炸出一声轻响": "炭火",
    "照出一圈暖光": "灯火", "糊纸破了一角": "灯笼", "骨架有点歪": "灯笼",
    "铃舌被绳子系住": "铃", "内壁发黑": "铃", "打在石头上": "雪粒浪头",
    "钻进缝里": "雪粒", "翻起白沫": "浪头", "撞在石壁上": "浪头",
    "散不开": "雾气", "把声音压得很近": "雾气", "一头垂在地上": "绳布",
    "绳结冻硬了": "绳", "锁舌卡住了": "锁", "提手磨得发亮": "壶盆",
    "挂钩松了": "钩", "锈成了褐色": "铁链钩钉环",
    "长到齐膝": "草苇", "根须露在外面": "草根", "一丛丛立着": "草苇",
    "草尖朝下": "草", "折了几根": "草枝", "叶面卷起": "枝叶",
    "灰积了半寸": "盆火", "盆沿烫手": "盆", "红光晃在墙上": "炉火炭火",
    "火舌舔着盆沿": "盆火", "边缘结了炭花": "炭火",
    "细得像沙": "雪粒", "在光里发亮": "雪花雪粒", "越下越大": "雪",
    "卷着雪沫": "风雪", "一片白": "风雪雪",
}
PRED_AVOIDS = {
    "结了霜": "霜冰", "结着霜": "霜冰", "盖着一层白灰": "冰水",
    "冒着白汽": "冰雪", "碎成一小片": "草枝",
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


SCENES = [
    "清晨；雪，横风；高；灰白", "傍晚；雪；低；炭火",
    "夜；雾；中；油灯", "午后；雨；低；灰光",
    "黎明；雾，湿冷；中；船灯", "入夜；小雨；低；纸灯笼",
    "清晨；晴，薄冰；低；冷光", "夜里；雪停；高；月光",
    "正午；晴；低；日头", "黄昏；风；高；斜阳",
    "夜里；风；高；灯火", "清晨；雾；中；晨光",
    "午后；雪；低；窗光", "傍晚；雨停；低；湿光",
    "夜；雪；高；灯影", "清晨；风；中；灰光",
]
WIND = ["风", "雾", "雪", "夜", "雨"]


def main():
    rows, seen = [], set()
    for noun, mat in NOUNS.items():
        locs = LOCS[mat]
        for fid, (frame, pool_name) in FRAMES.items():
            unseen_frame = fid in HOLDOUT_FRAMES
            unseen_noun = noun in HOLDOUT_NOUNS
            if unseen_frame and unseen_noun:
                continue
            split = ("holdout_frame" if unseen_frame else
                     "holdout_noun" if unseen_noun else "train")
            if pool_name == "motion" and noun not in MOTION:
                continue
            pool = (MOTION.get(noun, []) if pool_name == "motion"
                    else STATES[mat] if pool_name == "state"
                    else ONS[mat])
            for pred in pool:
                if not pred_fits(pred, noun):
                    continue
                for loc in locs:
                    for scene in SCENES:
                        N = noun
                        sent = frame.format(
                            N=N, P=pred, P2on=ONS[mat][(len(rows) + 3)
                                                       % len(ONS[mat])],
                            N2=noun, W=WIND[len(rows) % len(WIND)], L=loc)
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
                            "shape": pool_name, "predicate": pred,
                            "input": build_input(noun, loc, scene),
                            "target": sent, "split": split,
                        })
    parts = {k: [r for r in rows if r["split"] == k] for k in
             ("train", "holdout_frame", "holdout_noun")}
    for k in ("holdout_frame", "holdout_noun"):
        n = max(1, len(parts[k]) // 400)
        parts[k] = [r for i, r in enumerate(parts[k]) if i % n == 0][:400]
    dev = parts["train"][::25]
    parts["train"] = [r for r in parts["train"] if r not in dev]
    parts["dev"] = dev
    for k, out in OUT.items():
        body = chr(10).join(json.dumps(r, ensure_ascii=False)
                            for r in parts[k]) + chr(10)
        out.write_text(body, encoding="utf-8", newline=chr(10))
    print({k: len(v) for k, v in parts.items()})
    print("nouns", len(NOUNS), "unseen", HOLDOUT_NOUNS)
    print("frames", sorted(FRAMES), "unseen", sorted(HOLDOUT_FRAMES))
    print("unique sentences", len({r["target"] for r in rows}))


if __name__ == "__main__":
    main()
