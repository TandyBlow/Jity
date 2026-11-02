# Build the N4 scene-sentence corpus (environment + POV interiority only).
#
# One or two sentences per scene combo, hand-written: weather, light, props,
# and the POV holder's sensation. No character actions, no fact changes, no
# numbers, no task wording. The fact clauses come from the verbalizer; this
# step only supplies what surrounds them.
#
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/write_scene_corpus.py

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT_TRAIN = HERE / "scene_pairs.jsonl"
OUT_HOLDOUT = HERE / "scene_holdout.jsonl"

# key: locationId|time|weather|wind|light
SCENES = {
    "loc_lighthouse|夜|夜雾，海风|塔顶海风直吹|塔顶铜灯已点亮": [
        "夜雾把塔顶围住，铜灯的光只照到脚边。",
        "海风从塔顶直吹过来，灯罩在风里轻轻响。",
    ],
    "loc_ferry|黎明|低潮，海风，湿冷|河口风|天刚亮": [
        "天刚亮，潮水退到木桩以下，浅滩露了出来。",
        "河口风带着湿冷，栈桥的木板上还挂着水珠。",
    ],
    "loc_ferry|黄昏|雾，河面低|河口风|船灯": [
        "雾压着河面，船灯只剩一团模糊的黄。",
        "黄昏的河口风很轻，水汽贴着栈桥漫上来。",
    ],
    "loc_ferry|黄昏|雾，河面低|中（河口风）|船灯": [
        "雾从河面漫上栈桥，船灯在水汽里晃。",
        "黄昏的河风不大，木桩上缠着旧缆绳。",
    ],
    "loc_archive|午后|雨|无（室内）|铜灯": [
        "雨点落在天窗上，铜灯把长桌照出一圈暖光。",
        "屋里全是纸墨和潮气，雨声压在屋顶。",
    ],
    "loc_seawall|夜|大雾，浪高|迎海风|无（雾中）": [
        "大雾把石堤裹住，浪声从雾里一阵阵撞过来。",
        "夜里雾很重，白沫翻上堤面又退回去。",
    ],
    "loc_alley|夜|雨|低（室内）|蜡烛": [
        "雨声压在窗外，蜡烛的火苗只有一小截。",
        "屋里的潮气混着蜡油味，墙角照不到光。",
    ],
    "loc_archive|夜|雨渐匀|无（室内）|铜灯": [
        "雨声渐渐匀了，灯芯烧出一小截黑灰。",
        "铜灯的光落在纸页上，屋里只剩雨声。",
    ],
    "loc_market|清晨|潮湿，白汽|低（棚下）|棚下散光": [
        "清晨的早市全是白汽，鱼鳞在石板上闪成碎光。",
        "帆布棚下很潮，蒸汽把棚顶熏得发亮。",
    ],
    "loc_lighthouse|傍晚|海风|旋梯口海风|海光从窄窗照进来": [
        "傍晚的海光从窄窗照进旋梯，墙上的铜油痕发暗。",
        "旋梯口灌进海风，木梯踩上去有轻微的响声。",
    ],
    "loc_alley|夜|雨渐小|低（窄巷）|纸灯笼": [
        "雨小了些，纸灯笼的光落在湿石板上。",
        "巷子里只剩水声，灯笼一盏接一盏亮着。",
    ],
    "loc_seawall|夜|雾，风横，浪高|迎海风|警示灯": [
        "雾里只有警示灯亮着，风从堤面横着扫过去。",
        "浪头撞在石壁上，白沫被海风吹散。",
    ],
    "loc_ferry|夜|雾|河口风|船灯": [
        "夜里雾更重，船灯只剩一团模糊的黄。",
        "河风把雾推来推去，栈桥的木桩只剩影子。",
    ],
    "loc_alley|入夜|小雨，湿冷|低（窄巷挡风）|纸灯笼": [
        "入夜的雨很细，纸灯笼把水洼照出一圈光。",
        "窄巷挡住了风，湿冷从石板缝里透上来。",
    ],
    "loc_lighthouse|夜|海雾，海风|高（塔顶海风直吹）|铜框信号灯还亮着": [
        "海雾把塔顶围住，铜框信号灯还亮着。",
        "塔顶的海风很硬，灯罩被吹得嗡嗡响。",
    ],
    "loc_ferry|黎明|雾，低潮|中（河口风）|船灯": [
        "黎明前雾还没散，船灯在河面上晃。",
        "潮水退得很低，栈桥的木桩上挂着水珠。",
    ],
    "loc_ferry|黎明|低潮，海风，湿冷|中（河口风）|退潮后的冷光": [
        "退潮后的浅滩泛着一层冷光，泥腥味很重。",
        "黎明的水汽贴在脸上，滩面上留着水痕。",
    ],
    "loc_archive|午后|雨，天窗漏雨|无（室内）|铜灯": [
        "雨点密密地敲着天窗，铜灯把长桌照出一圈暖光。",
        "纸页和墨迹混着潮气，天窗的水滴落在石地上。",
    ],
    "loc_seawall|黄昏|雾，浪大|高（迎海风）|警示灯": [
        "黄昏的雾压着海堤，警示灯被风吹得发晃。",
        "浪头撞在石壁上，白沫还没退，风又扫过来。",
    ],
    "loc_market|清晨|白汽，人流|低（棚下）|帆布棚下": [
        "帆布棚下全是白汽，鱼鳞被鞋底踩得发亮。",
        "清晨的早市很挤，蒸汽混着鱼腥味。",
    ],
    "loc_alley|夜|雨，潮气重|低（窄巷挡风）|蜡烛": [
        "夜里的潮气很重，蜡烛的火苗照不亮墙角。",
        "雨声压在窗外，木桌的木头泛着潮。",
    ],
    "loc_seawall|夜|雾，海风|高（迎海风）|警示灯": [
        "雾里只有警示灯亮着，海风从石壁另一侧灌过来。",
        "夜里的浪声一阵接一阵，钟架在风里轻响。",
    ],
    "loc_market|上午|晴，白汽散了一半|低（棚下）|帆布棚下": [
        "上午的白汽散了一半，帆布棚下只剩几只空筐。",
        "日头照进早市，鱼鳞粘在石板上发亮。",
    ],
    "loc_lighthouse|夜|海雾，湿冷|高（塔顶海风直吹）|塔顶灯火": [
        "海雾贴着塔身，塔顶的灯火在雾里发白。",
        "夜里的海风又湿又冷，石阶上全是水光。",
    ],
    "loc_ferry|清晨|雾，水汽重|中（河口风）|船灯": [
        "清晨的雾还没散，船灯在水汽里透出一点黄。",
        "河口的水汽很重，栈桥的木板上滑得很。",
    ],
    "loc_archive|午后|雨刚停|无（室内）|铜灯": [
        "雨刚停，天窗上还挂着水珠，铜灯亮着。",
        "屋里的纸墨味更重了，门槛外还有滴水声。",
    ],
    "loc_ferry|夜|雾，水汽重|中（河口风）|船灯": [
        "夜里的水汽压在河面上，船灯只剩一点光。",
        "雾从河面漫上来，栈桥边的水很黑。",
    ],
    "loc_alley|入夜|小雨，湿冷|低（窄巷挡风）|纸灯笼": [
        "入夜的雨细得几乎没有声音，灯笼的光落在水沟里。",
        "巷子很窄，湿冷的风被石墙挡在外面。",
    ],
    "loc_alley|夜|雨，潮气重|低（窄巷挡风）|蜡烛": [
        "潮气从墙根漫上来，蜡烛烧得只剩半截。",
        "雨声不急不缓，屋里的木头泛着湿气。",
    ],
    "loc_lighthouse|黎明|海雾，湿冷|高（塔顶海风直吹）|雾里的塔身": [
        "黎明的海雾贴着石阶，塔身只剩一个轮廓。",
        "天刚亮，雾水把石阶打得湿滑，铁链冰凉。",
    ],
    "loc_lighthouse|夜|海雾，海风|高（塔顶海风直吹）|铜框信号灯": [
        "海雾把塔顶的轮廓磨淡了，铜框信号灯亮着。",
        "夜里的海风从塔顶灌下来，灯罩嗡嗡响。",
    ],
    "loc_lighthouse|黄昏|海雾，湿冷|高（塔顶海风直吹）|铜框窗": [
        "黄昏的雾从窄窗渗进来，旋梯里有股擦铜油的味道。",
        "海雾贴着石阶，铜框窗只透进一线灰光。",
    ],
    "loc_alley|午后|晴，石板半干|低（窄巷挡风）|纸灯笼": [
        "午后的光落在巷子里，石板还留着水痕。",
        "纸灯笼在墙上晃，水沟里的积水映着光。",
    ],
    "loc_archive|夜|雨渐匀|无（室内）|铜灯": [
        "夜里的雨声匀下来了，铜灯照着一桌纸页。",
        "天窗还在滴水，屋里的潮气没有散。",
    ],
    "loc_archive|午后|细雨，天窗漏雨|无（室内）|铜灯": [
        "细雨落在天窗上，铜灯的光晕里浮着一点灰尘。",
        "屋外的雨很细，天窗只漏下几滴水。",
    ],
    "loc_market|清晨|白汽，湿冷|低（棚下）|帆布棚下": [
        "清晨的湿冷混着白汽，帆布棚下全是水光。",
        "鱼鳞粘在石板上，棚布被蒸汽熏得发潮。",
    ],
    "loc_seawall|夜|雾，海风|高（迎海风）|警示灯": [
        "夜里的雾压着海堤，警示灯在风里发晃。",
        "海风从石壁另一侧灌过来，钟架轻轻响。",
    ],
    "loc_ferry|黎明|雾，低潮|中（河口风）|船灯": [
        "黎明前雾还没散，船灯在水汽里晃。",
        "低潮的栈桥露出湿泥，木桩上挂着水珠。",
    ],
}

HOLDOUT = {
    "loc_inn|傍晚|雪，屋檐挂冰凌|低（石墙挡风）|炭火": [
        "云关驿的屋檐挂满冰凌，门里透出炭火的暖光。",
    ],
    "loc_inn|傍晚|雪|低（石墙挡风）|炭火": [
        "雪落在石墙上，大堂里的炭盆烧得正旺。",
    ],
    "loc_pass|夜|风，雪粒|高（山口横风）|马灯": [
        "风把雪粒吹成横线，马棚里黑得很快。",
    ],
    "loc_tower|黄昏|雪，风|高（台顶直风）|灰白天色": [
        "黄昏的天色发白，台顶的风把铃绳吹得乱响。",
    ],
    "loc_inn|夜|风，窗纸轻响|低（石墙挡风）|油灯": [
        "风让窗纸轻轻响，客房里的油灯很小。",
    ],
    "loc_brook|清晨|雪，溪面结冰|中（溪谷风）|灰白": [
        "清晨的溪面结着薄冰，灰白的光从桥下透出来。",
    ],
    "loc_pass|清晨|雪，横风|高（山口横风）|灰白": [
        "清晨的横风把经幡吹得笔直，雪粒打在石堆上。",
    ],
    "loc_pass|午后|风，雪粒|高（山口横风）|门缝的光": [
        "门缝里透进一线光，干草堆在角落里。",
    ],
    "loc_pass|夜|风，雪|高（山口横风）|马灯": [
        "风把雪吹进门缝，马灯的光落在干草上。",
    ],
    "loc_inn|夜|雪|低（石墙挡风）|炭火": [
        "夜里的雪很静，炭盆的火只剩一点暗红。",
    ],
    "loc_inn|傍晚|雪停|低（石墙挡风）|炭火": [
        "雪停在傍晚，屋檐不再滴水，炭盆还亮着。",
    ],
}


def scene_props(world, root_id):
    loc = world["locations"][root_id]
    props = list(loc.get("features", []))
    for sub in loc.get("sublocations", []):
        props.append(sub["name"])
        props.extend(sub.get("features", []))
    sub_ids = {s["id"] for s in loc.get("sublocations", [])} | {root_id}
    for it in world["items"].values():
        if it.get("position", {}).get("containerId") in sub_ids:
            props.append(it["name"])
    seen, out = set(), []
    for p in props:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def build_input(case, world):
    sc = case["sceneState"]
    root = sc["locationPath"][0]
    pov_id = case["perspective"]["entityId"]
    pov = world["characters"][pov_id]
    body = [
        "场景短句。",
        "地点=" + world["locations"][root]["name"],
        "地点可见=" + "、".join(scene_props(world, root)),
        "场景=" + "；".join([sc["time"], sc["weather"], sc["wind"],
                            sc["light"], sc.get("atmosphere", "")]).strip("；"),
        "视角=" + pov["name"] + "；性格=" + pov["personality"] +
        "；外貌=" + pov["appearance"],
        "要求：写一到两句环境或视角人物的感受；只引用地点可见与场景给的现象；"
        "不写人物动作、不写任务、不写数值和时长；不新增人物、物品、地点；"
        "不写任何事实变化。",
        "短句：",
    ]
    return chr(10).join(x for x in body if x) + chr(10)


def key_of(case):
    sc = case["sceneState"]
    return "|".join([sc["locationPath"][0], sc["time"], sc["weather"],
                     sc["wind"], sc["light"]])


def main():
    world = json.loads((HERE / "world.json").read_text(encoding="utf-8"))
    rows = []
    seen = {}
    for name in ("corpus.jsonl", "corpus_v1.jsonl", "corpus_v2.jsonl"):
        for line in (HERE / name).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            k = key_of(case)
            variants = SCENES.get(k)
            if not variants:
                raise SystemExit(f"missing scene variants for {k}")
            idx = seen.get(k, 0)
            seen[k] = idx + 1
            rows.append({
                "pairId": "sc:" + case["id"],
                "sourceId": case["id"], "key": k,
                "input": build_input(case, world),
                "target": variants[idx % len(variants)],
                "split": "sc-train",
            })
    OUT_TRAIN.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                  for r in rows) + "\n",
                         encoding="utf-8", newline="\n")

    hw = json.loads((HERE / "holdout_world.json").read_text(encoding="utf-8"))
    hrows = []
    for line in (HERE / "holdout_corpus.jsonl").read_text(
            encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        k = key_of(case)
        variants = HOLDOUT.get(k)
        if not variants:
            raise SystemExit(f"missing holdout scene variants for {k}")
        hrows.append({
            "pairId": "sch:" + case["id"],
            "sourceId": case["id"], "key": k,
            "input": build_input(case, hw),
            "target": variants[0],
            "split": "sc-holdout",
        })
    OUT_HOLDOUT.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                     for r in hrows) + "\n",
                           encoding="utf-8", newline="\n")
    print(f"scene pairs {len(rows)} (combos {len(seen)}) -> {OUT_TRAIN}")
    print(f"holdout pairs {len(hrows)} -> {OUT_HOLDOUT}")


if __name__ == "__main__":
    main()
