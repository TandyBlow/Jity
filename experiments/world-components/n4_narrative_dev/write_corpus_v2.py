# Write the 88-case N4 narrative corpus v2 (matrix draft).
#
# Same n4n-fog-harbor world. 11 scenes x 8 fact patterns = 88 cases.
# Targets are assembled from scene-specific openings/closings and
# fact-specific fragments. This is a review draft for scale, not a claim of
# literary quality; every concrete noun is grounded in world.json or the
# case facts. Run:
#   python -X utf8 experiments/world-components/n4_narrative_dev/write_corpus_v2.py

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
WORLD = json.loads((HERE / "world.json").read_text(encoding="utf-8"))
OUT_JSONL = HERE / "corpus_v2.jsonl"
OUT_DOC = (HERE.parent.parent.parent / "design" / "world-engine-reports" /
           "components" / "n4-narrative-dev-v2.md")


def item(name):
    return next(i for i, v in WORLD["items"].items() if v["name"] == name)


def fact_moved(fid, eid, frm, to, at):
    return {"factId": fid, "kind": "moved", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "from": frm, "to": to,
            "at": at, "source": {"field": "positionSet"}}


def fact_outcome(fid, eid, task_id, at):
    t = WORLD["tasks"][task_id]
    return {"factId": fid, "kind": "outcome", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "taskId": task_id,
            "goal": t["goal"], "resultText": t["resultText"], "at": at,
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


def fact_time(fid, amount):
    return {"factId": fid, "kind": "time", "entityId": None, "name": None,
            "amount": amount, "unit": "minute",
            "source": {"timeAdvance": True}}


SCENES = [
    dict(
        key="alley_night", path=["loc_alley", "loc_alley_street"],
        time="入夜", weather="小雨，湿冷", wind="低（窄巷挡风）",
        light="纸灯笼", atmosphere="水声细密，巷子空着",
        origin="旧灯塔", shen_task=None,
        other=None,
        visible=["item_umbrella", "item_coat"],
        open_arrive=[
            "雨把潮生巷的纸灯笼打得发亮，沈砚从旧灯塔那边回来，沿着墙根慢慢走。",
            "潮生巷的雨不大，沈砚从巷口走进来，鞋底踩过水洼。",
        ],
        open_present=[
            "雨把潮生巷的纸灯笼打得发亮，沈砚站在巷子中间。",
            "潮生巷的排水沟响着，沈砚靠在墙根，袖口沾着潮气。",
        ],
        close=[
            "排水沟里的水声不急不缓，巷子还是老样子。",
            "灯影晃了晃又稳住，雨丝斜着落下来。",
            "墙根的水洼映着灯笼，路上没有别人。",
        ],
        appearance=["外袍下摆沾了泥水", "袖口被雨打湿"],
        appearance_other=[], personality=[],
        sanity=[(10, 12), (11, 9)],
        no_change=["巷子里什么也没有再发生。", "他站了一会儿，没有新的动静。"],
    ),
    dict(
        key="room_night", path=["loc_alley", "loc_alley_room"],
        time="夜", weather="雨，潮气重", wind="低（窄巷挡风）",
        light="蜡烛", atmosphere="窗外雨声，屋里安静",
        origin="潮渡", shen_task="task_key",
        other=None,
        visible=["item_candle", "item_oldpaper", "item_key",
                 "item_umbrella", "item_coat"],
        open_arrive=[
            "沈砚从潮渡回来，摸黑进了屋子，点亮桌角的蜡烛。",
            "雨声压在窗外，沈砚推门进屋，把湿伞靠在门边。",
        ],
        open_present=[
            "潮生巷的雨声压在窗外，沈砚坐在木桌旁。",
            "屋里只点着半截蜡烛，沈砚拉开抽屉。",
        ],
        close=[
            "烛火在墙上晃了一下，屋里又静下来。",
            "窗外的雨还在下，木桌边只剩一点暖光。",
            "他把东西收好，听见屋檐水滴在石板上。",
        ],
        appearance=["指腹沾了薄灰", "袖口蹭了一道墨"],
        appearance_other=[], personality=[],
        sanity=[(9, 11), (12, 10)],
        no_change=["屋里没有别的变化。", "抽屉还开着，什么也没有再发生。"],
    ),
    dict(
        key="stairs_dawn", path=["loc_lighthouse", "loc_lighthouse_stairs"],
        time="黎明", weather="海雾，湿冷", wind="高（塔顶海风直吹）",
        light="雾里的塔身", atmosphere="石阶湿滑，铁链冰凉",
        origin="潮渡", shen_task=None,
        other=None,
        visible=["item_oilcloth", "item_coat", "item_umbrella"],
        open_arrive=[
            "海雾贴着旧灯塔的石阶往上爬，沈砚从潮渡过来，扶着铁链一步步走。",
            "天刚亮，沈砚走到旧灯塔脚下，湿滑的石阶没入雾里。",
        ],
        open_present=[
            "海雾贴着石阶，沈砚扶着靠海的铁链站住。",
            "旧灯塔的石阶被雾水打湿，沈砚停在半层。",
        ],
        close=[
            "链环上的锈蹭到掌心，风从塔身侧面灌下来。",
            "雾没有散，石阶上只剩他的脚步声。",
            "他抬头看了看旋梯口，海风把衣角吹得发凉。",
        ],
        appearance=["外袍下摆被雾水打湿", "掌心蹭了铁链的锈"],
        appearance_other=[], personality=[],
        sanity=[(10, 12), (9, 11)],
        no_change=["石阶上什么也没有再发生。", "他站了一会儿，雾还是那样。"],
    ),
    dict(
        key="top_night", path=["loc_lighthouse", "loc_lighthouse_stairs",
                               "loc_lighthouse_spiral", "loc_lighthouse_top"],
        time="夜", weather="海雾，海风", wind="高（塔顶海风直吹）",
        light="铜框信号灯", atmosphere="灯罩嗡嗡响，海风直吹",
        origin="潮生巷", shen_task="task_lamp",
        other=dict(eid="char_ye", frm="潮渡", task="task_wipe"),
        visible=["item_oilcloth", "item_wick", "item_lamp_cover",
                 "item_rag", "item_copper_oil"],
        open_arrive=[
            "海雾把旧灯塔的轮廓磨淡了，沈砚沿着湿滑的石阶上到塔顶。",
            "塔顶的风比巷子里硬，沈砚从旋梯口出来，铜灯罩在风里轻响。",
        ],
        open_present=[
            "塔顶的铜框信号灯亮着，沈砚站在灯旁。",
            "海风从塔顶直吹过来，沈砚把油布包往怀里按了按。",
        ],
        close=[
            "火苗重新站稳，风把袖口吹得鼓起来。",
            "灯罩嗡嗡响，海雾在玻璃外面慢慢移过去。",
            "他看了一会儿，塔顶只剩风声。",
        ],
        appearance=["袖口沾了灯油", "外袍下摆被海风掀起"],
        appearance_other=["袖口沾了铜油", "手背上留着一道擦痕"],
        personality=["开始愿意先开口", "不再把话咽回去"],
        sanity=[(10, 12), (8, 10)],
        no_change=["塔顶没有别的变化。", "灯还亮着，风也没有停。"],
    ),
    dict(
        key="spiral_evening", path=["loc_lighthouse", "loc_lighthouse_stairs",
                                    "loc_lighthouse_spiral"],
        time="黄昏", weather="海雾，湿冷", wind="高（塔顶海风直吹）",
        light="铜框窗", atmosphere="擦铜油味，旋梯狭窄",
        origin="潮生巷", shen_task=None,
        other=dict(eid="char_ye", frm="潮渡", task=None),
        visible=["item_rag", "item_copper_oil", "item_oilcan"],
        open_arrive=[
            "旧灯塔的旋梯里有股擦铜油的味道，沈砚从潮生巷过来，停在铜框窗下。",
            "黄昏的雾从窄窗渗进来，沈砚沿着旋梯走到一半。",
        ],
        open_present=[
            "旋梯里全是擦铜油的气味，沈砚靠在铜框窗边。",
            "旧灯塔的旋梯很窄，沈砚站在窗下听风。",
        ],
        close=[
            "铜框窗透进一点灰蓝的光，旋梯里很静。",
            "油味没有散，风从窗缝里钻进来。",
            "他抬头看了看塔顶，灯罩的影子落在墙上。",
        ],
        appearance=["袖口沾了铜油", "外袍下摆蹭了墙灰"],
        appearance_other=["深蓝工作服上沾了铜油", "袖口有擦铜油的痕迹"],
        personality=["开始愿意先开口", "不再把话咽回去"],
        sanity=[(9, 11), (11, 9)],
        no_change=["旋梯里没有别的变化。", "他站了一会儿，油味还是那样。"],
    ),
    dict(
        key="pier_dawn", path=["loc_ferry", "loc_ferry_pier"],
        time="黎明", weather="雾，低潮", wind="中（河口风）",
        light="船灯", atmosphere="水汽重，栈桥湿滑",
        origin="潮生巷", shen_task="task_wait",
        other=dict(eid="char_gu", frm="河心", task=None),
        visible=["item_ferry", "item_boat_light", "item_mooring_rope",
                 "item_oilcloth", "item_coat"],
        open_arrive=[
            "天刚亮，沈砚从潮生巷出来，走到潮渡的栈桥边。",
            "潮渡的雾还没散，沈砚从巷子那边过来，在木桩旁站住。",
        ],
        open_present=[
            "潮渡的船灯在雾里只剩一团黄，沈砚靠在栈桥的木桩上。",
            "雾从河面漫上栈桥，沈砚站在木桩旁边。",
        ],
        close=[
            "船停稳了，水面上的灯影也静下来。",
            "缆绳轻轻碰着木桩，河风把雾推来推去。",
            "他看了一会儿水面，船灯在雾里晃。",
        ],
        appearance=["外袍下摆沾了水汽", "袖口被河风打湿"],
        appearance_other=["手上的茧被水泡得发白", "短褂下摆沾了水"],
        personality=["开始愿意先开口", "开始愿意多等一会儿"],
        sanity=[(8, 10), (10, 8)],
        no_change=["栈桥上没有别的变化。", "船没有来，水面也没有动静。"],
    ),
    dict(
        key="shoal_lowtide", path=["loc_ferry", "loc_ferry_stairs",
                                   "loc_ferry_shoal"],
        time="黎明", weather="低潮，海风，湿冷", wind="中（河口风）",
        light="退潮后的冷光", atmosphere="泥腥味重，滩面湿滑",
        origin="旧灯塔", shen_task="task_rope",
        other=None,
        visible=["item_rope", "item_coat", "item_oilcloth",
                 "item_umbrella"],
        open_arrive=[
            "退潮后的浅滩泛着一层冷光，沈砚从旧灯塔下来，踩着湿泥走到水边。",
            "天刚亮，沈砚从灯塔那边绕到潮渡，沿着石阶下到浅滩。",
        ],
        open_present=[
            "浅滩上泛着冷光，沈砚踩着湿泥站在水边。",
            "退潮后的泥滩很滑，沈砚弯下腰。",
        ],
        close=[
            "海风把咸味吹到脸上，滩面上只剩水声。",
            "他抖了抖衣摆，冷光在泥水里晃。",
            "潮水退得很低，脚印很快被泥水填平。",
        ],
        appearance=["外袍下摆沾满泥水，边角结了一圈白盐",
                    "袖口沾了湿泥"],
        appearance_other=[], personality=[],
        sanity=[(9, 11), (11, 9)],
        no_change=["浅滩上没有别的变化。", "潮水没有再退，泥滩很静。"],
    ),
    dict(
        key="archive_rain", path=["loc_archive", "loc_archive_desk"],
        time="午后", weather="雨，天窗漏雨", wind="无（室内）",
        light="铜灯", atmosphere="纸墨味重，雨声压在屋顶",
        origin="潮生巷", shen_task="task_log",
        other=dict(eid="char_atang", frm="早市", task="task_paper"),
        visible=["item_tidebook", "item_paper", "item_ink", "item_brush",
                 "item_archive_lamp", "item_tea", "item_umbrella"],
        open_arrive=[
            "档案馆的天窗漏着雨，沈砚从潮生巷过来，把湿伞靠在门边。",
            "雨点敲着档案馆的天窗，沈砚推门进来，在长桌边坐下。",
        ],
        open_present=[
            "铜灯把长桌照出一圈暖光，沈砚把潮汐簿摊开。",
            "档案馆里只有雨声，沈砚坐在长桌前。",
        ],
        close=[
            "他合上簿子，听见门槛外的雨声轻了一些。",
            "铜灯的光落在纸页上，屋里只剩笔尖的轻响。",
            "天窗还在滴水，长桌上很安静。",
        ],
        appearance=["袖口蹭了一道墨", "指尖沾了墨"],
        appearance_other=["围裙上沾了墨点", "鞋底带着早市的泥水"],
        personality=["开始愿意先开口", "不再把话咽回去"],
        sanity=[(9, 11), (11, 9)],
        no_change=["档案馆里没有别的变化。", "雨声还在，纸页没有动。"],
    ),
    dict(
        key="seawall_dusk", path=["loc_seawall", "loc_seawall_top"],
        time="黄昏", weather="雾，浪大", wind="高（迎海风）",
        light="警示灯", atmosphere="白沫翻上堤面，钟架轻响",
        origin="潮渡", shen_task="task_bell",
        other=dict(eid="char_han", frm="潮渡", task="task_bell_rope"),
        visible=["item_bell", "item_bell_rope", "item_warning_lamp",
                 "item_coat"],
        open_arrive=[
            "雾堤上的风把浪沫吹到石阶上，沈砚从潮渡过来，扶着铁链往上走。",
            "黄昏的雾压着雾堤，沈砚从石阶下上来，钟架在风里轻响。",
        ],
        open_present=[
            "雾堤上的风很硬，沈砚站在钟架旁。",
            "浪头撞在石壁上，沈砚把外袍拢了拢。",
        ],
        close=[
            "钟声撞进雾里，又被海风撕碎。",
            "他松开钟绳，才发现呼吸一直提着。",
            "白沫翻上堤面，风从石壁另一侧灌过来。",
        ],
        appearance=["掌心被铁皮冰得发麻", "外袍下摆被浪沫打湿"],
        appearance_other=["眉毛上的雾水更重了", "手背上沾了盐沫"],
        personality=["开始愿意先开口", "不再把话咽回去"],
        sanity=[(8, 10), (10, 8)],
        no_change=["雾堤上没有别的变化。", "钟架还响着，浪也没有停。"],
    ),
    dict(
        key="market_morning", path=["loc_market", "loc_market_stalls"],
        time="清晨", weather="白汽，人流", wind="低（棚下）",
        light="帆布棚下", atmosphere="鱼鳞反光，泥水湿滑",
        origin="潮生巷", shen_task=None,
        other=dict(eid="char_atang", frm="潮生巷", task="task_fish"),
        visible=["item_fish", "item_fishbasket", "item_paper",
                 "item_coat", "item_umbrella"],
        open_arrive=[
            "早市的帆布棚下白汽不散，沈砚从潮生巷过来，在摊棚外站住。",
            "天刚亮，沈砚走进早市，鱼鳞在石板上闪成细碎的光。",
        ],
        open_present=[
            "早市的帆布棚下全是白汽，沈砚站在摊棚外。",
            "鱼鳞粘在石板上，沈砚从人缝里挤过去。",
        ],
        close=[
            "鱼尾拍得筐沿啪啪响，白汽还没有散。",
            "他侧身让开，鞋底踩过湿滑的石板。",
            "人流慢慢移开，鱼摊前只剩水声。",
        ],
        appearance=["袖口沾了鱼腥水", "衣摆沾了泥水"],
        appearance_other=["围裙上又添了一层银亮鱼鳞",
                           "辫梢沾了白汽"],
        personality=["开始愿意先开口", "不再把话咽回去"],
        sanity=[(10, 12), (9, 11)],
        no_change=["早市上没有别的变化。", "摊棚前人来人往，什么也没有再发生。"],
    ),
    dict(
        key="alley_afternoon", path=["loc_alley", "loc_alley_street"],
        time="午后", weather="晴，石板半干", wind="低（窄巷挡风）",
        light="纸灯笼", atmosphere="巷子安静，水沟里还有积水",
        origin="潮渡", shen_task=None,
        other=None,
        visible=["item_umbrella", "item_coat"],
        open_arrive=[
            "雨停后的潮生巷慢慢干了，沈砚从潮渡回来，沿着墙根走。",
            "午后的光落在潮生巷，沈砚从巷口进来，石板还留着水痕。",
        ],
        open_present=[
            "潮生巷的石板半干，沈砚站在墙根下。",
            "午后的巷子很静，沈砚把伞收在手里。",
        ],
        close=[
            "排水沟里的水声慢下来，灯笼在墙上晃了晃。",
            "他站了一会儿，巷子里只有远处的脚步声。",
            "水洼映着纸灯笼，光慢慢移过石板。",
        ],
        appearance=["鞋底沾了湿石板的水", "袖口蹭了墙灰"],
        appearance_other=[], personality=[],
        sanity=[(10, 12), (11, 9)],
        no_change=["巷子里什么也没有再发生。", "他站了一会儿，水声还是那样。"],
    ),
]


TEXTURE = {
    "alley_night": ["石板缝里积着水，灯笼的光落在上面，碎成一小片。",
                    "墙根的水洼映着灯笼，雨丝斜着落进去。"],
    "room_night": ["木桌边堆着旧纸，蜡烛的火苗很短，照不亮墙角。",
                   "抽屉半开着，木头的潮气混着蜡油味。"],
    "stairs_dawn": ["铁链贴着石壁，链环上都是盐蚀的白斑。",
                    "雾从石阶下面漫上来，鞋底踩出一层水痕。"],
    "top_night": ["玻璃罩上有一层盐雾，火苗在里面轻轻抖。",
                  "铜框被海风吹得发冷，塔下只剩雾。"],
    "spiral_evening": ["窄窗只透进一线灰光，墙上的铜油痕迹发暗。",
                       "旋梯的木板很旧，踩上去有轻微的响声。"],
    "pier_dawn": ["木桩上缠着旧缆绳，水面的雾一层压着一层。",
                  "栈桥边的水很黑，船灯的影子在里面晃。"],
    "shoal_lowtide": ["泥滩上留着退潮的水痕，冷光在浅水里碎开。",
                      "石阶通向滩面，鞋底带起一小片泥水。"],
    "archive_rain": ["长桌靠窗，纸页和墨迹混着铜灯的气味。",
                     "天窗的水滴落在石地上，声音很轻。"],
    "seawall_dusk": ["石壁上的白沫还没退，钟架被海盐蚀出白斑。",
                     "浪声一阵接一阵，风从堤面横着扫过去。"],
    "market_morning": ["帆布棚下全是白汽，鱼筐边沿沾着亮鳞。",
                       "石板上的泥水被鞋底踩开，又慢慢聚回去。"],
    "alley_afternoon": ["水沟里的积水还没干，纸灯笼的影子落在石板上。",
                        "午后的光从巷口照进来，墙根的青苔发暗。"],
}
GENERIC_CLOSE = {
    "alley_night": ["排水沟里的水声不急不缓，巷子还是老样子。",
                    "他站了一会儿，雨声没有停。"],
    "room_night": ["烛火在墙上晃了一下，屋里又静下来。",
                   "他合上抽屉，听见屋檐水滴在石板上。"],
    "stairs_dawn": ["链环上的锈蹭到掌心，风从塔身侧面灌下来。",
                    "雾没有散，石阶上只剩他的脚步声。"],
    "top_night": ["灯罩嗡嗡响，海雾在玻璃外面慢慢移过去。",
                  "他看了一会儿，塔顶只剩风声。"],
    "spiral_evening": ["铜框窗透进一点灰蓝的光，旋梯里很静。",
                       "油味没有散，风从窗缝里钻进来。"],
    "pier_dawn": ["水面上的灯影晃着，河风把雾推来推去。",
                  "木桩上的水珠落进河里，栈桥很静。"],
    "shoal_lowtide": ["海风把咸味吹到脸上，滩面上只剩水声。",
                      "他直起腰，冷光在泥水里晃。"],
    "archive_rain": ["铜灯的光落在纸页上，屋里只剩雨声。",
                     "天窗还在滴水，长桌很安静。"],
    "seawall_dusk": ["白沫翻上堤面，风从石壁另一侧灌过来。",
                    "钟架在风里轻响，浪声没有停。"],
    "market_morning": ["白汽在棚下浮着，石板上的水光慢慢移开。",
                       "人流从摊棚前过去，鱼腥味还没有散。"],
    "alley_afternoon": ["排水沟里的水声慢下来，灯笼在墙上晃了晃。",
                        "他站了一会儿，巷子里只有远处的脚步声。"],
}


def case(pid, scene, pattern, variant, seq):
    root = scene["path"][0]
    root_name = WORLD["locations"][root]["name"]
    other = scene["other"]
    present = ["char_shen"] + ([other["eid"]] if other and pattern in "BDEG" else [])
    facts = []
    frags = []
    if pattern == "A":
        facts = [fact_moved("f0", "char_shen", scene["origin"], root_name, root_name),
                 fact_time("f1", 5 + seq % 8)]
        frags = [scene["open_arrive"][variant % len(scene["open_arrive"])]]
        frags.append(scene["close"][variant % len(scene["close"])])
    elif pattern == "B":
        facts = [fact_moved("f0", "char_shen", scene["origin"], root_name, root_name),
                 fact_moved("f1", other["eid"], other["frm"], root_name, root_name),
                 fact_time("f2", 6 + seq % 7)]
        frags = [scene["open_arrive"][variant % len(scene["open_arrive"])],
                 f"{WORLD['characters'][other['eid']]['name']}从{other['frm']}那边过来，"
                 f"在{root_name}停下。",
                 GENERIC_CLOSE[scene["key"]][variant % len(GENERIC_CLOSE[scene["key"]])]]
    elif pattern == "C":
        facts = [fact_outcome("f0", "char_shen", scene["shen_task"], root_name),
                 fact_sanity("f1", "char_shen", *scene["sanity"][variant % len(scene["sanity"])], root_name),
                 fact_time("f2", 8 + seq % 8)]
        sf, st = scene["sanity"][variant % len(scene["sanity"])]
        sanity_text = ("他的呼吸比刚才顺了一些。" if st > sf
                       else "他的呼吸有些发紧。")
        frags = [scene["open_arrive"][variant % len(scene["open_arrive"])],
                 f"他{WORLD['tasks'][scene['shen_task']]['resultText']}，"
                 f"{sanity_text}",
                 GENERIC_CLOSE[scene["key"]][variant % len(GENERIC_CLOSE[scene["key"]])]]
    elif pattern == "D":
        text = scene["appearance_other"][variant % len(scene["appearance_other"])]
        facts = [fact_outcome("f0", other["eid"], other["task"], root_name),
                 fact_appearance("f1", other["eid"], text, root_name),
                 fact_time("f2", 7 + seq % 9)]
        frags = [scene["open_present"][variant % len(scene["open_present"])],
                 f"{WORLD['characters'][other['eid']]['name']}"
                 f"{WORLD['tasks'][other['task']]['resultText']}，{text}。",
                 GENERIC_CLOSE[scene["key"]][variant % len(GENERIC_CLOSE[scene["key"]])]]
    elif pattern == "E":
        facts = [fact_moved("f0", other["eid"], other["frm"], root_name, root_name),
                 fact_outcome("f1", other["eid"], other["task"], root_name),
                 fact_time("f2", 6 + seq % 8)]
        frags = [scene["open_present"][variant % len(scene["open_present"])],
                 f"{WORLD['characters'][other['eid']]['name']}从{other['frm']}过来，"
                 f"{WORLD['tasks'][other['task']]['resultText']}。",
                 GENERIC_CLOSE[scene["key"]][variant % len(GENERIC_CLOSE[scene["key"]])]]
    elif pattern == "F":
        text = scene["appearance"][variant % len(scene["appearance"])]
        facts = [fact_appearance("f0", "char_shen", text, root_name),
                 fact_time("f1", 5 + seq % 8)]
        frags = [scene["open_present"][variant % len(scene["open_present"])],
                 f"等沈砚站定，{text}。",
                 GENERIC_CLOSE[scene["key"]][variant % len(GENERIC_CLOSE[scene["key"]])]]
    elif pattern == "G":
        text = scene["personality"][variant % len(scene["personality"])]
        facts = [fact_moved("f0", other["eid"], other["frm"], root_name, root_name),
                 fact_moved("f1", "char_shen", scene["origin"], root_name, root_name),
                 fact_personality("f2", "char_shen", text, root_name),
                 fact_time("f3", 6 + seq % 7)]
        frags = [scene["open_arrive"][variant % len(scene["open_arrive"])],
                 f"{WORLD['characters'][other['eid']]['name']}从{other['frm']}那边过来。",
                 f"沈砚本来想像往常那样把话咽回去，这次却{text.replace('开始愿意', '愿意').replace('不再', '没有')}。",
                 GENERIC_CLOSE[scene["key"]][variant % len(GENERIC_CLOSE[scene["key"]])]]
    else:  # H
        facts = [fact_no_change("f0"), fact_time("f1", 6 + seq % 8)]
        frags = [scene["open_present"][variant % len(scene["open_present"])],
                 scene["no_change"][variant % len(scene["no_change"])],
                 GENERIC_CLOSE[scene["key"]][variant % len(GENERIC_CLOSE[scene["key"]])]]
    close = GENERIC_CLOSE[scene["key"]][variant % len(GENERIC_CLOSE[scene["key"]])]
    texture = TEXTURE[scene["key"]][variant % len(TEXTURE[scene["key"]])]
    frags = frags[:-1] + [texture, close]
    if pattern == "A":
        frags.insert(-1, "他没有急着离开。")
    elif pattern == "H":
        frags.insert(-1, "他听着，没有动。")
    narrative = "".join(frags)
    # Add needed items to visible.
    visible = list(scene["visible"])
    for f in facts:
        if f["kind"] == "outcome":
            tid = f["taskId"]
            add = {
                "task_key": ["item_key", "item_oldpaper", "item_candle"],
                "task_lamp": ["item_wick", "item_lamp_cover"],
                "task_rope": ["item_rope"],
                "task_log": ["item_tidebook", "item_ink", "item_brush"],
                "task_bell": ["item_bell", "item_bell_rope"],
                "task_warnlamp": ["item_warning_lamp"],
                "task_wait": ["item_ferry", "item_boat_light"],
                "task_wipe": ["item_lamp_cover", "item_rag", "item_copper_oil"],
                "task_paper": ["item_paper"],
                "task_fish": ["item_fish", "item_fishbasket"],
                "task_bell_rope": ["item_bell_rope"],
            }.get(tid, [])
            for iid in add:
                if iid not in visible:
                    visible.append(iid)
    characters = []
    for eid in present:
        ch = WORLD["characters"][eid]
        characters.append({"entityId": eid, "name": ch["name"],
                           "personality": ch["personality"],
                           "appearance": ch["appearance"],
                           "inventory": ch["inventory"], "use": "read"})
    grounding = [
        {"detail": root_name, "source": root,
         "value": WORLD["locations"][root]["appearance"]},
        {"detail": "场景条件", "source": "scene",
         "value": "；".join([scene["time"], scene["weather"], scene["wind"],
                            scene["light"], scene["atmosphere"]])},
    ]
    for f in facts:
        if f["kind"] == "outcome":
            grounding.append({"detail": f["resultText"], "source": f"fact {f['factId']}",
                              "value": f["taskId"]})
        elif f["kind"] in ("appearance_changed", "personality_changed"):
            grounding.append({"detail": f["text"], "source": f"fact {f['factId']}",
                              "value": f["name"]})
        elif f["kind"] == "moved":
            grounding.append({"detail": f"{f['name']}：{f['from']}→{f['to']}",
                              "source": f"fact {f['factId']}",
                              "value": "position"})
    scene_state = {
        "locationId": root, "locationPath": scene["path"],
        "time": scene["time"], "weather": scene["weather"],
        "wind": scene["wind"], "light": scene["light"],
        "present": present, "visibleItems": visible,
        "atmosphere": scene["atmosphere"],
    }
    return {
        "worldId": WORLD["worldId"], "id": f"n4n-{pid}",
        "title": f"{scene['key']}-{pattern}", "facts": facts,
        "sceneBrief": {"locationId": root,
                       "location": "·".join(
                           WORLD["locations"][x]["name"]
                           if x in WORLD["locations"] else
                           next(s["name"] for l in WORLD["locations"].values()
                                for s in l["sublocations"] if s["id"] == x)
                           for x in scene["path"]),
                       "time": scene["time"], "weather": scene["weather"],
                       "present": present, "props": [WORLD["items"][x]["name"] for x in visible],
                       "atmosphere": scene["atmosphere"],
                       "allowedElaboration": ["weather", "sensory", "gesture",
                                              "interiority"],
                       "hiddenMotivation": [f["taskId"] for f in facts
                                            if f["kind"] == "outcome"]},
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": root_name},
        "narrative": narrative, "annotations": [],
        "sceneState": scene_state, "grounding": grounding,
        "timeNarrative": "vague", "characterContext": characters,
        "personalityUse": [f"{f['name']}：{f['text']}；正文体现"
                           for f in facts if f["kind"] == "personality_changed"],
        "contract": "n4-narrative-v0", "split": "dev-review",
        "reviewStatus": "pending",
    }


# 11 scenes x 8 patterns = 88 cases. Each pattern cycles its compatible
# scenes; repeated scenes get a different variant / task / appearance text.
PATTERN_SCENES = {
    "A": [s for s in SCENES],
    "B": [s for s in SCENES if s["other"]],
    "C": [s for s in SCENES if s["shen_task"]],
    "D": [s for s in SCENES if s["other"] and s["other"].get("task")
          and s["appearance_other"]],
    "E": [s for s in SCENES if s["other"] and s["other"].get("task")],
    "F": [s for s in SCENES],
    "G": [s for s in SCENES if s["other"] and s["personality"]],
    "H": [s for s in SCENES],
}


def main():
    rows = []
    pid = 33
    for pattern in "ABCDEFGH":
        scenes = PATTERN_SCENES[pattern]
        for i in range(11):
            scene = scenes[i % len(scenes)]
            rows.append(case(pid, scene, pattern, i, i))
            pid += 1
    assert pid == 121, pid
    OUT_JSONL.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8", newline="\n")
    lines = [
        "# N4 叙事开发语料 v2（88 例，矩阵稿，待审）",
        "",
        "日期：2026-11-02。同一 `n4n-fog-harbor` 世界，11 场景 × 8 事实"
        "模式 = 88 例（n4n-33…120）。**矩阵稿，待审，未训练。** 正文由场景"
        "开头/收束和事实片段拼装，目标是扩样与事实覆盖；不是逐条手写的文学"
        "定稿。",
        "",
        "> **环境字段：** time/weather/wind/light/atmosphere 已并入"
        " `地点外貌`；当前值是审阅夹具，生产应由 `LocationState.appearance`"
        " 提供，缺失即省略并记诊断。",
        "",
        "## 审阅点",
        "",
        "- 事实是否全覆盖，归属/方向/结果是否被改写",
        "- 是否出现任务标题/数值/具体时长/字段名",
        "- 是否新增具名实体/物品/地点、他人内心、承诺性对话",
        "- 场景/行为/心理是否自然；矩阵稿允许重复结构，但不能事实错",
        "",
        "## 校验汇总",
        "",
        "| id | 模式 | 事实 | 输入 token | 目标 token | pack |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    val_path = HERE / "corpus_v2_validation.json"
    val = ({r["id"]: r for r in json.loads(val_path.read_text(encoding="utf-8"))}
           if val_path.exists() else {})
    for r in rows:
        v = val.get(r["id"], {})
        lines.append(f"| {r['id']} | {r['title'].split('-')[-1]} | "
                     f"{len(r['facts'])} | {v.get('inputTokens', '—')} | "
                     f"{v.get('targetTokens', '—')} | "
                     f"{v.get('packStatus', '—')} |")
    lines += [
        "",
        "## 案例",
        "",
    ]
    for r in rows:
        lines += [f"### {r['id']} · {r['title']}", "",
                  f"- 场景：`{' → '.join(r['sceneBrief']['location'].split('·'))}`；"
                  f"时间：{r['sceneBrief']['time']}；天气：{r['sceneBrief']['weather']}",
                  "", "**Facts**", "",
                  "| id | kind | 内容 |", "| --- | --- | --- |"]
        for f in r["facts"]:
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
        lines += ["", "**Narrative**", "", "> " + r["narrative"], "",
                  "- [ ] 事实全覆盖", "- [ ] 无任务标题/数值/具体时长",
                  "- [ ] 无新增具名实体/物品/地点",
                  "- [ ] 无他人内心/承诺性对话",
                  "- [ ] 视角一致，场景/行为/心理自然", ""]
    OUT_DOC.write_text("\n".join(lines).rstrip("\n") + "\n",
                       encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} cases -> {OUT_JSONL}")
    print(f"review doc -> {OUT_DOC}")


if __name__ == "__main__":
    main()
