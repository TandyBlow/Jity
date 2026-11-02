# Write the 20-case N4 narrative review corpus (v1).
#
# Same world as the approved 12 cases (`n4n-fog-harbor`); no new named
# characters, items or locations. Targets are drafted for user review, not
# trained on yet. Run:
#   python -X utf8 experiments/world-components/n4_narrative_dev/write_corpus_v1.py

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
WORLD = json.loads((HERE / "world.json").read_text(encoding="utf-8"))
OUT_JSONL = HERE / "corpus_v1.jsonl"
OUT_DOC = (HERE.parent.parent.parent / "design" / "world-engine-reports" /
           "components" / "n4-narrative-dev-v1.md")


def fact_moved(fid, eid, frm, to, at):
    return {"factId": fid, "kind": "moved", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "from": frm, "to": to,
            "at": at, "source": {"field": "positionSet"}}


def fact_outcome(fid, eid, task_id, at):
    task = WORLD["tasks"][task_id]
    return {"factId": fid, "kind": "outcome", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "taskId": task_id,
            "goal": task["goal"], "resultText": task["resultText"], "at": at,
            "source": {"field": "tasksAchieved", "taskId": task_id}}


def fact_sanity(fid, eid, frm, to, at):
    return {"factId": fid, "kind": "sanity_changed", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "from": frm, "to": to,
            "at": at, "source": {"field": "sanitySet"}}


def fact_appearance(fid, eid, text, at):
    return {"factId": fid, "kind": "appearance_changed", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "text": text, "at": at,
            "source": {"field": "appearanceChanges"}}


def fact_personality(fid, eid, text, at):
    return {"factId": fid, "kind": "personality_changed", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "text": text, "at": at,
            "source": {"field": "personalityChanges"}}


def fact_no_change(fid):
    return {"factId": fid, "kind": "no_change", "entityId": None,
            "name": None, "scope": "全局", "source": {"noChange": True}}


def fact_time(fid, amount, unit="minute"):
    return {"factId": fid, "kind": "time", "entityId": None, "name": None,
            "amount": amount, "unit": unit, "source": {"timeAdvance": True}}


def g(detail, source, value):
    return {"detail": detail, "source": source, "value": value}


CASES = [
    dict(
        id="n4n-13", title="巷口的灯影",
        path=["loc_alley", "loc_alley_street"], time="入夜",
        weather="小雨，湿冷", wind="低（窄巷挡风）", light="纸灯笼",
        atmosphere="雨声细密，巷子里没有人",
        present=["char_shen"],
        visible=["item_umbrella", "item_coat"],
        facts=[fact_no_change("f0"), fact_time("f1", 6)],
        narrative="雨把潮生巷的纸灯笼打得发亮，沈砚沿着墙根慢慢走，鞋底踩过水洼，灯影晃了晃又稳住。排水沟里的水声不急不缓，巷子还是老样子；他站了一会儿，巷子里什么也没有再发生。",
        grounding=[
            g("雨", "scene.weather", "小雨，湿冷"),
            g("潮生巷", "loc_alley", "沿河窄巷"),
            g("纸灯笼", "loc_alley.features", "纸灯笼"),
            g("墙根", "loc_alley_street", "墙根"),
            g("水洼", "loc_alley_street", "水洼"),
            g("排水沟", "loc_alley.features", "排水沟"),
        ],
    ),
    dict(
        id="n4n-14", title="塔顶的风声",
        path=["loc_lighthouse", "loc_lighthouse_stairs",
              "loc_lighthouse_spiral", "loc_lighthouse_top"],
        time="夜", weather="海雾，海风", wind="高（塔顶海风直吹）",
        light="铜框信号灯还亮着", atmosphere="风硬，铁链轻响",
        present=["char_shen"],
        visible=["item_oilcloth", "item_wick", "item_lamp_cover"],
        facts=[fact_moved("f0", "char_shen", "潮生巷", "旧灯塔", "旧灯塔"),
               fact_time("f1", 10)],
        narrative="海雾把旧灯塔的轮廓磨淡了，沈砚沿着湿滑的石阶上到塔顶，铁链在风里轻轻碰着石壁。铜框信号灯还亮着，火苗被玻璃罩护住，没有灭；他看了一会儿，风把袖口吹得鼓起来。",
        grounding=[
            g("海雾", "scene.weather", "海雾，海风"),
            g("旧灯塔", "loc_lighthouse", "白色石塔，外壁盐蚀"),
            g("石阶", "loc_lighthouse_stairs", "湿滑石阶"),
            g("塔顶", "loc_lighthouse_top", "塔顶"),
            g("铁链", "loc_lighthouse_stairs", "靠海一侧有铁链"),
            g("铜框信号灯", "loc_lighthouse_top", "铜框信号灯"),
            g("玻璃罩", "item_lamp_cover", "铜框玻璃罩"),
            g("火苗", "item_lamp_cover.state.lit", "true"),
        ],
    ),
    dict(
        id="n4n-15", title="潮渡的早班船",
        path=["loc_ferry", "loc_ferry_pier"], time="黎明",
        weather="雾，低潮", wind="中（河口风）", light="船灯",
        atmosphere="水汽重，栈桥湿滑",
        present=["char_shen", "char_gu"],
        visible=["item_mooring_rope", "item_ferry", "item_boat_light",
                 "item_oilcloth", "item_coat"],
        facts=[fact_moved("f0", "char_shen", "潮生巷", "旧灯塔", "潮渡"),
               fact_moved("f1", "char_gu", "河心", "潮渡", "潮渡"),
               fact_time("f2", 7)],
        narrative="天刚亮，潮渡的木桩上还挂着夜里的水珠。沈砚从巷子出来，在栈桥边站住；顾行舟的渡船从河心慢慢靠过来，船头压开一层薄雾，缆绳在木桩上绕了两圈。船停稳了，水面上的灯影也静下来。",
        grounding=[
            g("天刚亮", "scene.time", "黎明"),
            g("潮渡", "loc_ferry", "木栈桥"),
            g("木桩", "loc_ferry_pier", "木桩"),
            g("栈桥", "loc_ferry_pier", "栈桥"),
            g("渡船", "item_ferry", "旧木船"),
            g("河心", "loc_ferry.sublocations", "水面"),
            g("薄雾", "scene.weather", "雾"),
            g("缆绳", "item_mooring_rope", "旧麻缆绳"),
            g("灯影", "item_boat_light", "黄铜船灯"),
        ],
    ),
    dict(
        id="n4n-16", title="浅滩的冷光",
        path=["loc_ferry", "loc_ferry_stairs", "loc_ferry_shoal"],
        time="黎明", weather="低潮，海风，湿冷", wind="中（河口风）",
        light="退潮后的冷光", atmosphere="泥腥味重，滩面湿滑",
        present=["char_shen"],
        visible=["item_rope", "item_coat", "item_oilcloth",
                 "item_umbrella"],
        facts=[fact_moved("f0", "char_shen", "旧灯塔", "潮渡", "潮渡"),
               fact_appearance("f1", "char_shen",
                               "外袍下摆沾满泥水，边角结了一圈白盐",
                               "潮渡"),
               fact_time("f2", 12)],
        narrative="退潮后的浅滩泛着一层冷光，沈砚踩着湿泥走到水边，弯腰摸了摸露出来的系泊绳。等他直起身，外袍下摆已经沾满泥水，边角结出一圈白盐；他抖了抖衣摆，海风把咸味吹到脸上。",
        grounding=[
            g("浅滩", "loc_ferry_shoal", "退潮后的泥滩"),
            g("冷光", "loc_ferry_shoal", "冷光"),
            g("湿泥", "loc_ferry_shoal", "退潮后的泥滩"),
            g("系泊绳", "item_rope", "粗麻绳，沾满泥和盐"),
            g("外袍", "item_coat", "青灰外袍，下摆容易沾泥水"),
            g("白盐", "item_rope", "沾满泥和盐"),
            g("海风", "scene.weather", "海风"),
        ],
    ),
    dict(
        id="n4n-17", title="档案馆的墨迹",
        path=["loc_archive", "loc_archive_desk"], time="午后",
        weather="雨，天窗漏雨", wind="无（室内）", light="铜灯",
        atmosphere="纸墨味重，雨声压在屋顶",
        present=["char_shen"],
        visible=["item_tidebook", "item_ink", "item_brush",
                 "item_archive_lamp", "item_paper", "item_tea"],
        facts=[fact_outcome("f0", "char_shen", "task_log", "潮汐档案馆"),
               fact_appearance("f1", "char_shen", "指尖沾了墨", "潮汐档案馆"),
               fact_time("f2", 15)],
        narrative="档案馆的天窗漏下一线雨光，沈砚把潮汐簿摊在铜灯下，照着页边的旧墨迹一笔一笔补。缺页终于接上了，他的指尖也沾了墨；他合上簿子，听见门槛外的雨声比刚才轻了一些。",
        grounding=[
            g("档案馆", "loc_archive", "低矮砖房"),
            g("天窗", "loc_archive.features", "天窗"),
            g("雨光", "scene.weather", "雨"),
            g("潮汐簿", "item_tidebook", "厚纸簿，缺一页"),
            g("铜灯", "item_archive_lamp", "铜座台灯"),
            g("旧墨迹", "item_tidebook", "页边有旧墨迹"),
            g("缺页", "item_tidebook", "缺一页"),
            g("指尖", "fact f1", "沾了墨"),
        ],
    ),
    dict(
        id="n4n-18", title="雾堤的钟绳",
        path=["loc_seawall", "loc_seawall_top"], time="黄昏",
        weather="雾，浪大", wind="高（迎海风）", light="警示灯",
        atmosphere="白沫翻上堤面，钟架轻响",
        present=["char_shen", "char_han"],
        visible=["item_bell", "item_bell_rope", "item_warning_lamp",
                 "item_coat"],
        facts=[fact_moved("f0", "char_han", "潮渡", "雾堤", "雾堤"),
               fact_outcome("f1", "char_han", "task_bell_rope", "雾堤"),
               fact_time("f2", 9)],
        narrative="雾堤上的风把浪沫吹到石阶上，韩渡从潮渡那边上来，蹲在钟架下，把松脱的钟绳一圈一圈重新系紧。钟绳绷直了，他才站起来，用手背擦了一下眉毛上的雾水；沈砚站在堤边，听见钟架在风里轻轻响。",
        grounding=[
            g("雾堤", "loc_seawall", "港口外侧石堤"),
            g("浪沫", "loc_seawall", "白沫翻上堤面"),
            g("石阶", "loc_seawall.features", "石阶"),
            g("韩渡", "char_han", "旧呢外套，眉毛被雾打湿"),
            g("潮渡", "loc_ferry", "河海交界"),
            g("钟架", "loc_seawall_top", "钟架"),
            g("钟绳", "item_bell_rope", "粗麻钟绳"),
            g("雾水", "char_han.appearance", "眉毛被雾打湿"),
        ],
    ),
    dict(
        id="n4n-19", title="早市的鱼筐",
        path=["loc_market", "loc_market_stalls"], time="清晨",
        weather="白汽，人流", wind="低（棚下）", light="帆布棚下",
        atmosphere="鱼鳞反光，泥水湿滑",
        present=["char_shen", "char_atang"],
        visible=["item_fish", "item_fishbasket", "item_paper",
                 "item_coat", "item_umbrella"],
        facts=[fact_moved("f0", "char_shen", "潮生巷", "早市", "早市"),
               fact_outcome("f1", "char_atang", "task_fish", "早市"),
               fact_appearance("f2", "char_shen", "袖口沾了鱼腥水", "早市"),
               fact_time("f3", 8)],
        narrative="早市的帆布棚下白汽不散，鱼鳞在石板上闪成细碎的光。沈砚从人缝里挤过去，正看见阿棠抱着一筐银鳞鱼往案板上送，鱼尾拍得筐沿啪啪响；他侧身让开，袖口还是沾了一点腥水。",
        grounding=[
            g("早市", "loc_market", "潮生巷尽头的鱼市"),
            g("帆布棚", "loc_market_stalls", "帆布棚"),
            g("白汽", "loc_market_stalls", "白汽"),
            g("鱼鳞", "loc_market_stalls", "鱼鳞"),
            g("石板", "loc_market_stalls", "石板"),
            g("阿棠", "char_atang", "十七岁，辫子"),
            g("银鳞鱼", "item_fish", "一筐银鳞鱼"),
            g("案板", "loc_market_stalls", "案板"),
            g("鱼腥水", "fact f2", "袖口沾了鱼腥水"),
        ],
    ),
    dict(
        id="n4n-20", title="潮渡的问话",
        path=["loc_ferry", "loc_ferry_pier"], time="黄昏",
        weather="雾，河面低", wind="中（河口风）", light="船灯",
        atmosphere="水声轻，栈桥湿",
        present=["char_shen", "char_gu"],
        visible=["item_ferry", "item_boat_light", "item_mooring_rope",
                 "item_oilcloth"],
        facts=[fact_moved("f0", "char_shen", "潮生巷", "潮渡", "潮渡"),
               fact_moved("f1", "char_gu", "河心", "潮渡", "潮渡"),
               fact_personality("f2", "char_shen", "开始愿意先开口", "潮渡"),
               fact_time("f3", 6)],
        narrative="雾从河面漫上栈桥，顾行舟把渡船系在木桩上。沈砚本来想像往常那样把话咽回去，却先开口问了潮水什么时候退；话出口后，他自己也愣了一下。顾行舟抬头看了看天，说还得等一阵。",
        grounding=[
            g("雾", "scene.weather", "雾"),
            g("河面", "loc_ferry_pier", "水面"),
            g("栈桥", "loc_ferry_pier", "栈桥"),
            g("顾行舟", "char_gu", "旧短褂"),
            g("渡船", "item_ferry", "旧木船"),
            g("木桩", "loc_ferry_pier", "木桩"),
            g("潮水", "loc_ferry", "河海交界"),
            g("开口", "fact f2", "开始愿意先开口"),
        ],
    ),
    dict(
        id="n4n-21", title="雨里的抽屉",
        path=["loc_alley", "loc_alley_room"], time="夜",
        weather="雨，潮气重", wind="低（窄巷挡风）", light="蜡烛",
        atmosphere="屋内安静，窗外雨声",
        present=["char_shen"],
        visible=["item_candle", "item_oldpaper", "item_key",
                 "item_umbrella", "item_coat"],
        facts=[fact_outcome("f0", "char_shen", "task_key", "潮生巷"),
               fact_appearance("f1", "char_shen", "指腹沾了薄灰", "潮生巷"),
               fact_time("f2", 5)],
        narrative="潮生巷的雨声压在窗外，沈砚点亮蜡烛，拉开抽屉最底层。旧纸下面压着那把黄铜钥匙，齿口已经磨圆；他把钥匙捏在手里，指腹沾了一层薄灰，烛火在墙上晃了一下。",
        grounding=[
            g("潮生巷", "loc_alley", "沿河窄巷"),
            g("雨声", "loc_alley_room", "窗外雨声"),
            g("蜡烛", "item_candle", "半截白蜡"),
            g("抽屉", "loc_alley_room", "抽屉"),
            g("旧纸", "item_oldpaper", "压抽屉底的一层旧纸"),
            g("黄铜钥匙", "item_key", "黄铜钥匙，齿口磨圆"),
            g("薄灰", "fact f1", "指腹沾了薄灰"),
        ],
    ),
    dict(
        id="n4n-22", title="雾堤的警示灯",
        path=["loc_seawall", "loc_seawall_top"], time="夜",
        weather="雾，海风", wind="高（迎海风）", light="警示灯",
        atmosphere="铁皮响，浪声闷",
        present=["char_shen"],
        visible=["item_warning_lamp", "item_bell", "item_bell_rope",
                 "item_coat"],
        facts=[fact_outcome("f0", "char_shen", "task_warnlamp", "雾堤"),
               fact_sanity("f1", "char_shen", 8, 10, "雾堤"),
               fact_time("f2", 7)],
        narrative="雾堤上的风比巷口硬得多，警示灯被吹得歪向一边，铁皮壳子哐哐响。沈砚伸手把它扳正，玻璃罩里的火苗晃了两下，才慢慢稳住；他松开手，才发现自己的呼吸一直提着，这会儿才落下去。",
        grounding=[
            g("雾堤", "loc_seawall", "港口外侧石堤"),
            g("风", "scene.weather", "海风"),
            g("警示灯", "item_warning_lamp", "铁皮警示灯"),
            g("铁皮壳子", "item_warning_lamp", "铁皮"),
            g("灯座", "item_warning_lamp", "铁皮警示灯"),
            g("玻璃罩", "item_warning_lamp", "玻璃罩"),
            g("火苗", "item_warning_lamp.state.lit", "true"),
            g("呼吸", "fact f1", "sanity 8→10"),
        ],
    ),
    dict(
        id="n4n-23", title="潮汐簿与干纸",
        path=["loc_archive", "loc_archive_desk"], time="午后",
        weather="雨，天窗漏雨", wind="无（室内）", light="铜灯",
        atmosphere="纸墨味，雨声零星",
        present=["char_shen", "char_atang"],
        visible=["item_tidebook", "item_paper", "item_ink", "item_brush",
                 "item_archive_lamp", "item_tea"],
        facts=[fact_moved("f0", "char_atang", "早市", "潮汐档案馆",
                           "潮汐档案馆"),
               fact_outcome("f1", "char_shen", "task_log", "潮汐档案馆"),
               fact_appearance("f2", "char_shen", "袖口蹭了一道墨",
                               "潮汐档案馆"),
               fact_time("f3", 12)],
        narrative="铜灯把长桌照出一圈暖光，沈砚把潮汐簿的缺页对齐，照着旧墨迹慢慢补。最后一笔落下，他袖口也蹭了一道墨；阿棠正好从早市过来，把一叠干纸放在桌角，鞋底在门槛上蹭了两下。",
        grounding=[
            g("铜灯", "item_archive_lamp", "铜座台灯"),
            g("长桌", "loc_archive_desk", "长桌"),
            g("潮汐簿", "item_tidebook", "厚纸簿，缺一页"),
            g("缺页", "item_tidebook", "缺一页"),
            g("旧墨迹", "item_tidebook", "页边有旧墨迹"),
            g("阿棠", "char_atang", "围裙上有鱼鳞"),
            g("早市", "loc_market", "潮生巷尽头的鱼市"),
            g("干纸", "item_paper", "一叠裁好的干纸"),
            g("门槛", "loc_archive.features", "门槛磨得发亮"),
        ],
    ),
    dict(
        id="n4n-24", title="早市的空筐",
        path=["loc_market", "loc_market_stalls"], time="上午",
        weather="晴，白汽散了一半", wind="低（棚下）",
        light="帆布棚下", atmosphere="摊棚半收，石板湿亮",
        present=["char_shen"],
        visible=["item_fishbasket", "item_fish", "item_coat",
                 "item_umbrella"],
        facts=[fact_no_change("f0"), fact_time("f1", 10)],
        narrative="早市的白汽散了一半，帆布棚下只剩几只空筐，鱼鳞粘在石板上，被来往的鞋底踩得发亮。沈砚在摊棚前站了一会儿，案板已经收了，人流慢慢稀下去，什么也没有再发生。",
        grounding=[
            g("早市", "loc_market", "潮生巷尽头的鱼市"),
            g("白汽", "loc_market_stalls", "白汽"),
            g("帆布棚", "loc_market_stalls", "帆布棚"),
            g("空筐", "item_fishbasket", "竹编鱼筐"),
            g("鱼鳞", "loc_market_stalls", "鱼鳞"),
            g("石板", "loc_market_stalls", "石板"),
            g("案板", "loc_market_stalls", "案板"),
            g("人流", "loc_market_stalls", "人流"),
        ],
    ),
    dict(
        id="n4n-25", title="灯塔的石阶",
        path=["loc_lighthouse", "loc_lighthouse_stairs",
              "loc_lighthouse_spiral", "loc_lighthouse_top"],
        time="夜", weather="海雾，湿冷", wind="高（塔顶海风直吹）",
        light="塔顶灯火", atmosphere="石阶湿滑，铁锈味",
        present=["char_shen"],
        visible=["item_coat", "item_oilcloth", "item_umbrella"],
        facts=[fact_moved("f0", "char_shen", "潮生巷", "旧灯塔", "旧灯塔"),
               fact_appearance("f1", "char_shen", "外袍下摆被雾水打湿",
                               "旧灯塔"),
               fact_time("f2", 8)],
        narrative="海雾贴着石阶往上爬，沈砚扶着靠海的铁链一步步走，链环上的锈蹭到掌心。他走到塔顶时，外袍下摆已经被雾水打湿，贴在腿上；风一吹，凉意顺着衣角钻上来。",
        grounding=[
            g("海雾", "scene.weather", "海雾"),
            g("石阶", "loc_lighthouse_stairs", "湿滑石阶"),
            g("铁链", "loc_lighthouse_stairs", "靠海一侧有铁链"),
            g("锈", "loc_lighthouse_stairs", "铁链"),
            g("塔顶", "loc_lighthouse_top", "塔顶"),
            g("外袍", "item_coat", "青灰外袍"),
            g("雾水", "fact f1", "外袍下摆被雾水打湿"),
        ],
    ),
    dict(
        id="n4n-26", title="潮渡的缆绳",
        path=["loc_ferry", "loc_ferry_pier"], time="清晨",
        weather="雾，水汽重", wind="中（河口风）", light="船灯",
        atmosphere="木桩湿滑，水声轻",
        present=["char_shen", "char_gu"],
        visible=["item_ferry", "item_mooring_rope", "item_boat_light",
                 "item_coat"],
        facts=[fact_moved("f0", "char_gu", "河心", "潮渡", "潮渡"),
               fact_appearance("f1", "char_gu", "手上的茧被水泡得发白",
                               "潮渡"),
               fact_time("f2", 7)],
        narrative="雾把潮渡的木桩藏了一半，顾行舟从河心把渡船靠过来，弯腰把缆绳绕上木桩。等他直起身，手上的茧被水泡得发白；他没有说话，只把船头又推正了一点。",
        grounding=[
            g("雾", "scene.weather", "雾"),
            g("潮渡", "loc_ferry", "河海交界"),
            g("木桩", "loc_ferry_pier", "木桩"),
            g("顾行舟", "char_gu", "手上有缆绳磨出的茧"),
            g("河心", "loc_ferry_pier", "水面"),
            g("渡船", "item_ferry", "旧木船"),
            g("缆绳", "item_mooring_rope", "旧麻缆绳"),
            g("茧", "fact f1", "手上的茧被水泡得发白"),
        ],
    ),
    dict(
        id="n4n-27", title="档案馆的门槛",
        path=["loc_archive", "loc_archive_desk"], time="午后",
        weather="雨刚停", wind="无（室内）", light="铜灯",
        atmosphere="门槛湿亮，屋里安静",
        present=["char_shen", "char_atang"],
        visible=["item_tidebook", "item_paper", "item_archive_lamp",
                 "item_umbrella", "item_fishbasket"],
        facts=[fact_moved("f0", "char_shen", "潮生巷", "潮汐档案馆",
                           "潮汐档案馆"),
               fact_moved("f1", "char_atang", "早市", "潮汐档案馆",
                           "潮汐档案馆"),
               fact_time("f2", 6)],
        narrative="雨停了一会儿，档案馆的门槛被鞋底磨得发亮。沈砚从潮生巷过来，把湿伞靠在门边；阿棠随后抱着一叠干纸进门，纸角被风掀起。两人都没有说话，长桌上的铜灯还亮着，雨声只剩天窗上零星几滴。",
        grounding=[
            g("档案馆", "loc_archive", "低矮砖房"),
            g("门槛", "loc_archive.features", "门槛磨得发亮"),
            g("沈砚", "char_shen", "青灰长衫"),
            g("潮生巷", "loc_alley", "沿河窄巷"),
            g("湿伞", "item_umbrella", "旧油纸伞"),
            g("阿棠", "char_atang", "十七岁，辫子"),
            g("干纸", "item_paper", "一叠裁好的干纸"),
            g("长桌", "loc_archive_desk", "长桌"),
            g("铜灯", "item_archive_lamp", "铜座台灯"),
            g("天窗", "loc_archive.features", "天窗"),
        ],
    ),
    dict(
        id="n4n-28", title="雾堤的白沫",
        path=["loc_seawall", "loc_seawall_top"], time="黄昏",
        weather="雾，浪大", wind="高（迎海风）", light="警示灯",
        atmosphere="白沫翻上堤面，风冷",
        present=["char_shen"],
        visible=["item_bell", "item_bell_rope", "item_warning_lamp",
                 "item_coat"],
        facts=[fact_moved("f0", "char_shen", "潮生巷", "雾堤", "雾堤"),
               fact_sanity("f1", "char_shen", 9, 11, "雾堤"),
               fact_time("f2", 9)],
        narrative="浪头撞在雾堤的石壁上，白沫翻上堤面，又被风撕碎。沈砚沿着石阶往上走，铁链在手里冰凉；他站到钟架旁，胸口那阵发紧的感觉慢慢松开了。",
        grounding=[
            g("浪头", "loc_seawall", "浪大时白沫翻上堤面"),
            g("雾堤", "loc_seawall", "港口外侧石堤"),
            g("石壁", "loc_seawall_top", "石壁"),
            g("白沫", "loc_seawall", "白沫"),
            g("石阶", "loc_seawall.features", "石阶"),
            g("铁链", "loc_seawall.features", "铁链"),
            g("钟架", "loc_seawall_top", "钟架"),
            g("胸口", "fact f1", "sanity 9→11"),
        ],
    ),
    dict(
        id="n4n-29", title="塔顶的玻璃罩",
        path=["loc_lighthouse", "loc_lighthouse_stairs",
              "loc_lighthouse_spiral", "loc_lighthouse_top"],
        time="夜", weather="海雾，海风", wind="高（塔顶海风直吹）",
        light="铜框信号灯", atmosphere="擦铜油味，灯罩发亮",
        present=["char_shen", "char_ye"],
        visible=["item_lamp_cover", "item_rag", "item_copper_oil",
                 "item_oilcan", "item_wick"],
        facts=[fact_moved("f0", "char_ye", "潮渡", "旧灯塔", "旧灯塔"),
               fact_outcome("f1", "char_ye", "task_wipe", "旧灯塔"),
               fact_time("f2", 10)],
        narrative="海风把塔顶的铜框吹得发冷，叶知微从潮渡上来，蹲在信号灯旁，用抹布把玻璃罩上的盐雾一圈圈擦掉。灯罩透亮起来，火苗的影子落在她袖口的铜油上；沈砚站在旋梯口，没有上前，只听见风从灯罩边缘擦过去。",
        grounding=[
            g("海风", "scene.weather", "海风"),
            g("塔顶", "loc_lighthouse_top", "塔顶"),
            g("铜框", "loc_lighthouse_top", "铜框信号灯"),
            g("叶知微", "char_ye", "深蓝工作服"),
            g("潮渡", "loc_ferry", "河海交界"),
            g("信号灯", "loc_lighthouse_top", "铜框信号灯"),
            g("抹布", "item_rag", "沾了擦铜油的软布"),
            g("玻璃罩", "item_lamp_cover", "铜框玻璃罩"),
            g("盐雾", "scene.weather", "海雾"),
            g("铜油", "item_copper_oil", "小罐铜油"),
            g("旋梯口", "loc_lighthouse_spiral", "旋梯"),
        ],
    ),
    dict(
        id="n4n-30", title="档案馆的呼吸",
        path=["loc_archive", "loc_archive_desk"], time="午后",
        weather="细雨，天窗漏雨", wind="无（室内）", light="铜灯",
        atmosphere="雨声低，纸页安静",
        present=["char_shen"],
        visible=["item_tidebook", "item_tea", "item_archive_lamp",
                 "item_umbrella"],
        facts=[fact_moved("f0", "char_shen", "潮生巷", "潮汐档案馆",
                           "潮汐档案馆"),
               fact_sanity("f1", "char_shen", 9, 11, "潮汐档案馆"),
               fact_time("f2", 6)],
        narrative="档案馆的天窗漏着细雨，沈砚把湿伞靠在门槛边，在长桌前坐下。铜灯的光落在摊开的潮汐簿上，他翻了两页，呼吸渐渐匀了；雨声还在，但不再催他。",
        grounding=[
            g("档案馆", "loc_archive", "低矮砖房"),
            g("天窗", "loc_archive.features", "天窗"),
            g("细雨", "scene.weather", "细雨"),
            g("湿伞", "item_umbrella", "旧油纸伞"),
            g("门槛", "loc_archive.features", "门槛磨得发亮"),
            g("长桌", "loc_archive_desk", "长桌"),
            g("铜灯", "item_archive_lamp", "铜座台灯"),
            g("潮汐簿", "item_tidebook", "厚纸簿"),
            g("呼吸", "fact f1", "sanity 9→11"),
        ],
    ),
    dict(
        id="n4n-31", title="早市的鱼鳞",
        path=["loc_market", "loc_market_stalls"], time="清晨",
        weather="白汽，湿冷", wind="低（棚下）", light="帆布棚下",
        atmosphere="鱼鳞反光，人流拥挤",
        present=["char_shen", "char_atang"],
        visible=["item_fish", "item_fishbasket", "item_paper",
                 "item_coat"],
        facts=[fact_moved("f0", "char_shen", "潮生巷", "早市", "早市"),
               fact_appearance("f1", "char_atang",
                               "围裙上又添了一层银亮鱼鳞", "早市"),
               fact_time("f2", 7)],
        narrative="早市的帆布棚下全是白汽，阿棠蹲在鱼筐边挑鱼，围裙上又添了一层银亮的鱼鳞。沈砚从潮生巷过来，在摊棚外站住；鱼尾拍起的水花溅到石板上，很快被来往的鞋底踩开。",
        grounding=[
            g("早市", "loc_market", "潮生巷尽头的鱼市"),
            g("帆布棚", "loc_market_stalls", "帆布棚"),
            g("白汽", "loc_market_stalls", "白汽"),
            g("阿棠", "char_atang", "围裙上有鱼鳞"),
            g("鱼筐", "item_fishbasket", "竹编鱼筐"),
            g("鱼鳞", "fact f1", "围裙上又添了一层银亮鱼鳞"),
            g("潮生巷", "loc_alley", "潮生巷"),
            g("摊棚", "loc_market_stalls", "摊棚"),
            g("石板", "loc_market_stalls", "石板"),
        ],
    ),
    dict(
        id="n4n-32", title="潮渡的最后一班船",
        path=["loc_ferry", "loc_ferry_pier"], time="夜",
        weather="雾，水汽重", wind="中（河口风）", light="船灯",
        atmosphere="船身轻晃，缆绳轻响",
        present=["char_shen", "char_gu"],
        visible=["item_ferry", "item_boat_light", "item_mooring_rope",
                 "item_coat"],
        facts=[fact_moved("f0", "char_shen", "潮生巷", "潮渡", "潮渡"),
               fact_moved("f1", "char_gu", "河心", "潮渡", "潮渡"),
               fact_outcome("f2", "char_shen", "task_wait", "潮渡"),
               fact_sanity("f3", "char_shen", 8, 10, "潮渡"),
               fact_time("f4", 12)],
        narrative="雾把潮渡的船灯压成一团黄，沈砚在栈桥边等了很久，终于看见顾行舟的渡船从河心靠过来。船靠稳时，他那口一直提着的气才松开；船身轻轻一晃，木桩上的缆绳也跟着响了一声。",
        grounding=[
            g("雾", "scene.weather", "雾"),
            g("潮渡", "loc_ferry", "河海交界"),
            g("船灯", "item_boat_light", "黄铜船灯"),
            g("栈桥", "loc_ferry_pier", "栈桥"),
            g("顾行舟", "char_gu", "旧短褂"),
            g("渡船", "item_ferry", "旧木船"),
            g("河心", "loc_ferry_pier", "水面"),
            g("木桩", "loc_ferry_pier", "木桩"),
            g("缆绳", "item_mooring_rope", "旧麻缆绳"),
            g("呼吸", "fact f3", "sanity 8→10"),
        ],
    ),
]


def loc_name(lid):
    if lid in WORLD["locations"]:
        return WORLD["locations"][lid]["name"]
    for loc in WORLD["locations"].values():
        for sub in loc.get("sublocations", []):
            if sub["id"] == lid:
                return sub["name"]
    raise KeyError(lid)


def build(case):
    present = case["present"]
    characters = []
    for eid in present:
        ch = WORLD["characters"][eid]
        characters.append({
            "entityId": eid, "name": ch["name"],
            "personality": ch["personality"],
            "appearance": ch["appearance"],
            "inventory": ch["inventory"], "use": "read",
        })
    scene_state = {
        "locationId": case["path"][0],
        "locationPath": case["path"],
        "time": case["time"], "weather": case["weather"],
        "wind": case["wind"], "light": case["light"],
        "present": present, "visibleItems": case["visible"],
        "atmosphere": case["atmosphere"],
    }
    task_ids = [f["taskId"] for f in case["facts"] if f["kind"] == "outcome"]
    return {
        "worldId": WORLD["worldId"], "id": case["id"],
        "title": case["title"], "facts": case["facts"],
        "sceneBrief": {
            "locationId": case["path"][0],
            "location": "·".join(loc_name(x) for x in case["path"]),
            "time": case["time"], "weather": case["weather"],
            "present": present,
            "props": [WORLD["items"][x]["name"] for x in case["visible"]],
            "atmosphere": case["atmosphere"],
            "allowedElaboration": ["weather", "sensory", "gesture",
                                   "interiority"],
            "hiddenMotivation": task_ids,
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": loc_name(case["path"][0])},
        "narrative": case["narrative"], "annotations": [],
        "sceneState": scene_state, "grounding": case["grounding"],
        "timeNarrative": "vague",
        "characterContext": characters,
        "personalityUse": [
            f"{f['name']}：{f['text']}；正文体现"
            for f in case["facts"] if f["kind"] == "personality_changed"
        ],
        "contract": "n4-narrative-v0", "split": "dev-review",
        "reviewStatus": "pending",
    }


def main():
    rows = [build(c) for c in CASES]
    OUT_JSONL.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8", newline="\n")
    val_path = HERE / "corpus_v1_validation.json"
    val = ({r["id"]: r for r in json.loads(val_path.read_text(encoding="utf-8"))}
           if val_path.exists() else {})
    lines = [
        "# N4 叙事开发语料 v1（20 例，待审）",
        "",
        "日期：2026-11-02。同一 `n4n-fog-harbor` 世界，新增 20 例；"
        "**待用户审阅，未训练**。当前 N4 生成模型未训练；N4.0 结构化输入"
        "在合并前输入上验证 9/9 训练拟合、0/3 check；环境条件并入 "
        "`地点外貌` 后需重跑，下一步是扩样。",
        "",
        "边界：不新增具名人物/物品/地点；task goal 只作隐藏动机，正文只用 "
        "`resultText`；时间只模糊/省略；理智用心理/生理表达；外貌/个性用"
        "可见细节与行为；他人只写可见动作；不写承诺性对话。",
        "",
        "> **环境字段来源：** 本文 `sceneState` 的 time/weather/wind/light/"
        "atmosphere 已并入 `地点外貌`，不是独立环境层；当前值是审阅夹具。"
        "生产应由 `LocationState.appearance`（initialAppearance + "
        "appearanceChanges）提供，wind 的静态依据是 `windExposure`；"
        "缺失条件省略并记 `environment-field-missing`。",
        "",
        "## 审阅点",
        "",
        "- 每条事实是否被正文覆盖，且没有改写归属/方向/结果",
        "- 是否出现任务标题/quest 措辞、数值、具体时长、字段名",
        "- 是否新增具名实体/物品/地点、他人内心、承诺性对话",
        "- 场景/行为/心理是否自然，视角是否一致",
        "",
        "## 校验汇总",
        "",
        "| id | 事实 | 选集 | 丢弃 | N3 | pack | 输入 token | 目标 token |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in CASES:
        r = val.get(c["id"], {})
        lines.append(
            f"| {c['id']} | {len(c['facts'])} | "
            f"{r.get('n2Summary', {}).get('selected', '—')} | "
            f"{','.join(r.get('dropped', [])) or '无'} | "
            f"{'ok' if not r.get('planProblems') else r.get('planProblems')} | "
            f"{r.get('packStatus', '—')} | {r.get('inputTokens', '—')} | "
            f"{r.get('targetTokens', '—')} |")
    lines += [
        "",
        "## 案例",
        "",
    ]
    for c in CASES:
        lines += [f"### {c['id']} · {c['title']}", "",
                  f"- 场景：`{' → '.join(loc_name(x) for x in c['path'])}`；"
                  f"时间：{c['time']}；天气：{c['weather']}",
                  f"- 在场：{'、'.join(WORLD['characters'][x]['name'] for x in c['present'])}",
                  "", "**Facts**", "",
                  "| id | kind | 内容 |", "| --- | --- | --- |"]
        for f in c["facts"]:
            body = f.get("text") or f.get("resultText") or ""
            if f["kind"] == "moved":
                body = f"{f['name']}：{f['from']}→{f['to']}"
            elif f["kind"] == "sanity_changed":
                body = f"{f['name']}：{f['from']}→{f['to']}"
            elif f["kind"] == "no_change":
                body = "全局无变化"
            elif f["kind"] == "time":
                body = f"{f['amount']} {f['unit']}（正文不写具体时长）"
            elif f["kind"] == "outcome":
                body = f"{f['name']}：{f['resultText']}"
            lines.append(f"| {f['factId']} | {f['kind']} | {body} |")
        lines += ["", "**Narrative**", "", "> " + c["narrative"], "",
                  "**Grounding**", "", "| 细节 | 来源 | 值 |",
                  "| --- | --- | --- |"]
        for item in c["grounding"]:
            lines.append(f"| {item['detail']} | {item['source']} | "
                         f"{item['value']} |")
        lines += ["", "- [ ] 事实全覆盖", "- [ ] 无任务标题/数值/具体时长",
                  "- [ ] 无新增具名实体/物品/地点",
                  "- [ ] 无他人内心/承诺性对话",
                  "- [ ] 视角一致，场景/行为/心理自然", ""]
    OUT_DOC.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8",
                       newline="\n")
    print(f"wrote {len(rows)} cases -> {OUT_JSONL}")
    print(f"review doc -> {OUT_DOC}")


if __name__ == "__main__":
    main()
