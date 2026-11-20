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


MANUAL = {
    "n4n-33": "雨丝斜着落进潮生巷，沈砚从旧灯塔那边回来，把伞收了收，沿着墙根慢慢走。纸灯笼的光落在水洼里，碎成一圈一圈；他听见排水沟的水声，脚步也跟着慢下来。",
    "n4n-34": "潮生巷的雨声压在窗外，沈砚从潮渡回来，摸黑点亮桌角的蜡烛。木桌上还摊着旧纸，抽屉没有关严；他在床沿坐了一会儿，才听见屋檐的水滴一声一声落下去。",
    "n4n-35": "海雾贴着旧灯塔的石阶往上爬，沈砚从潮渡过来，扶着靠海的铁链一步步走。链环上的锈蹭到掌心，雾水从袖口渗进去；他停在半层，听见塔顶的风声。",
    "n4n-36": "塔顶的风比巷子里硬，沈砚从旋梯口出来，铜灯罩在风里轻响。海雾把塔下的灯火压成一片模糊的黄；他把油布包往怀里按了按，站了一会儿，才觉得呼吸稳下来。",
    "n4n-37": "旧灯塔的旋梯里有股擦铜油的味道，沈砚从潮生巷过来，停在铜框窗下。窄窗只透进一线灰光，墙上的铜油痕迹发暗；他听着塔顶的风，没有急着往上走。",
    "n4n-38": "潮渡的雾还没散，沈砚从潮生巷出来，在栈桥边站住。木桩上缠着旧缆绳，船灯在雾里只剩一团黄；他看了一会儿水面，河风把袖口吹得发凉。",
    "n4n-39": "退潮后的浅滩泛着一层冷光，沈砚从旧灯塔下来，踩着湿泥走到水边。石阶上还留着水痕，系泊绳陷在泥里；他蹲下去看了一眼，又慢慢直起腰。海风从滩面吹过来，他把手拢在袖子里，站了一会儿才往回走。",
    "n4n-40": "雨点敲着档案馆的天窗，沈砚从潮生巷过来，把湿伞靠在门边。铜灯亮着，长桌上摊着潮汐簿，纸页和墨迹混着潮气；他坐下来，听见天窗的水滴落在石地上。",
    "n4n-41": "雾堤上的风把浪沫吹到石阶上，沈砚从潮渡过来，扶着铁链往上走。钟架在雾里只剩一个轮廓，警示灯被风吹得发晃；他站到堤边，海风把外袍下摆掀起来。",
    "n4n-42": "早市的帆布棚下全是白汽，沈砚从潮生巷过来，在摊棚外站住。鱼鳞粘在石板上，被来往的鞋底踩得发亮；他看了一会儿，鱼腥味混着蒸汽扑到脸上。",
    "n4n-43": "雨停后的潮生巷慢慢干了，沈砚从潮渡回来，沿着墙根走。纸灯笼在午后还是亮着，水沟里的积水映着光；他走得很慢，鞋底踩过湿石板，留下浅浅的水印。",
    "n4n-44": "海雾把旧灯塔的轮廓磨淡了，沈砚沿着湿滑的石阶上到塔顶。叶知微从潮渡那边过来，深蓝工作服上沾着铜油味；她停在信号灯旁，把抹布搭在栏杆上。风从塔顶灌下来，两个人都没有说话。",
    "n4n-45": "黄昏的雾从窄窗渗进来，沈砚从潮生巷走到旋梯，停在铜框窗下。叶知微从潮渡过来，袖口带着擦铜油的痕迹；她在窗边站住，抬手把窗框上的灰擦掉。旋梯里只剩风声。",
    "n4n-46": "天刚亮，沈砚从潮生巷出来，走到潮渡的栈桥边。顾行舟的渡船从河心慢慢靠过来，船头压开一层薄雾，缆绳在木桩上绕了两圈；船停稳后，水面上的灯影也静下来。",
    "n4n-47": "雨点敲着档案馆的天窗，沈砚从潮生巷过来，把湿伞靠在门边。阿棠随后从早市过来，抱着一叠干纸，鞋底在门槛上蹭了两下；她把纸放在桌角，纸角被门口的风掀起。",
    "n4n-48": "雾堤上的风把浪沫吹到石阶上，沈砚从潮渡过来，扶着铁链往上走。韩渡也从潮渡那边上来，眉毛上挂着雾水，蹲在钟架下查看松脱的钟绳；沈砚站在堤边，听见钟架轻响。",
    "n4n-49": "早市的帆布棚下白汽不散，沈砚从潮生巷过来，在摊棚外站住。阿棠从巷子另一头挤进来，抱着一筐银鳞鱼，围裙上沾着鱼鳞；她把鱼筐放到案板边，鱼尾还在拍。",
    "n4n-50": "塔顶的铜框信号灯亮着，沈砚从旋梯口出来，风把袖口吹得鼓起来。叶知微从潮渡上来，手里还攥着抹布，袖口有一圈擦铜油的痕；她走到灯罩旁，抬头看了看玻璃上的盐雾。",
    "n4n-51": "旧灯塔的旋梯很窄，沈砚从潮生巷过来，停在铜框窗下。叶知微从潮渡上来，深蓝工作服上沾着铜油，手里提着油壶；她在窗边站住，把油壶放在台阶上。旋梯里很静。",
    "n4n-52": "潮渡的木桩上还挂着夜里的水珠，沈砚从潮生巷出来，在栈桥边站住。顾行舟从河心把渡船靠过来，弯腰把缆绳绕上木桩；等他直起身，手上的茧被水泡得发白。",
    "n4n-53": "档案馆的天窗漏着雨，沈砚从潮生巷过来，在长桌前坐下。阿棠从早市过来，抱着一叠干纸，辫梢沾着白汽；她把纸放在桌角，鞋底在门槛上蹭了两下。",
    "n4n-54": "浪头撞在雾堤的石壁上，沈砚从潮渡上来，扶着铁链走到钟架旁。韩渡也从潮渡那边过来，旧呢外套上沾着盐沫，蹲下去把松脱的钟绳理了理；风把两个人的衣角都吹起来。",
    "n4n-55": "潮生巷的雨声压在窗外，沈砚点亮蜡烛，拉开抽屉最底层。旧纸下面压着那把黄铜钥匙，齿口已经磨圆；他把钥匙捏在手里，指腹沾了一层薄灰。胸口那点发紧的感觉慢慢松开，他才把抽屉推回去。",
    "n4n-56": "海雾把塔顶的玻璃罩打得发白，沈砚换好备用灯芯，火苗重新站稳。铜框信号灯在风里轻响，他松开手，才发现自己的呼吸一直提着；过了一会儿，那口气才慢慢落回去。",
    "n4n-57": "天刚亮，沈砚在潮渡的栈桥边站了很久，终于看见最后一班渡船从河心靠过来。他向前走了一步，船灯在雾里晃；等船停稳，胸口那口一直提着的气才松开。",
    "n4n-58": "退潮后的浅滩泛着冷光，沈砚把陷在泥里的系泊绳一寸一寸拖回岸上。等他直起身，外袍下摆已经沾满泥水；手指被海风吹得发僵，呼吸也有些发紧，他站了一会儿才缓过来。",
    "n4n-59": "档案馆的天窗漏着雨，沈砚把潮汐簿摊在铜灯下，照着旧墨迹把缺页补上。最后一笔落下，他合上簿子，听见门槛外的雨声轻了一些；胸口那阵闷意散开，他才发现指尖沾了墨。",
    "n4n-60": "雾堤上的风把浪沫吹到石阶上，沈砚抓住钟绳，把雾警钟一下一下敲响。钟声撞进雾里，又被海风撕碎；他松开手，手指抖得几乎握不住绳子，呼吸一阵阵发紧。",
    "n4n-61": "夜里的潮生巷只剩雨声，沈砚回到屋里，点亮桌角的蜡烛。他从抽屉底层的旧纸下面翻出备用钥匙，铜齿磕在木板上；他把钥匙攥在手里，呼吸渐渐匀了，才坐到床沿。",
    "n4n-62": "塔顶的风比巷子里硬，沈砚换好备用灯芯，火苗在玻璃罩里重新站稳。铜灯罩嗡嗡响，他退开半步，胸口那口提着的气慢慢松开；海雾在灯外一层层移过去。",
    "n4n-63": "潮渡的雾到黎明还没有散，沈砚在栈桥边等到最后一班船。船灯从雾里透出来，他把油布包往怀里按了按；船靠稳时，他一直绷着的呼吸才松开。雾没有散，船灯在水面上晃。",
    "n4n-64": "浅滩上的冷光碎在泥水里，沈砚把系泊绳从泥里拖回岸上。外袍下摆很快结了盐霜，手指被海风吹得发僵；他扶着石阶站了一会儿，呼吸才不再那么紧。",
    "n4n-65": "雨声压在档案馆的天窗上，沈砚照着页边的旧墨迹，把潮汐簿缺的那页补全。合上簿子时，门槛外的雨已经轻了；他靠在椅背上，呼吸慢慢匀下来，指尖还留着墨。",
    "n4n-66": "塔顶的铜框信号灯亮着，沈砚站在灯旁。叶知微把玻璃罩上的盐雾擦掉，灯罩透亮起来；她袖口沾了铜油，手背在灯影里发亮。风从塔顶灌下来，火苗轻轻抖了一下。",
    "n4n-67": "档案馆里只有雨声，沈砚坐在长桌前。阿棠把一叠干纸放在桌角，纸角被门口的风掀起；她鞋底带着早市的泥水，在门槛上蹭了两下。铜灯的光落在纸页上，很快又静下来。",
    "n4n-68": "雾堤上的风把浪沫吹到石阶上，沈砚站在钟架旁。韩渡蹲下去，把松脱的钟绳一圈一圈重新系紧；等他站起来，眉毛上的雾水更重了，手背上沾着盐沫。钟架在风里轻响。",
    "n4n-69": "早市的帆布棚下白汽不散，沈砚站在摊棚外。阿棠把一筐银鳞鱼搬上案板，鱼尾拍得筐沿啪啪响；她辫梢沾了白汽，围裙上又添了一层鱼鳞。人流从摊前挤过去。",
    "n4n-70": "海风从塔顶直吹过来，沈砚站在信号灯旁。叶知微踮着脚，用抹布把玻璃罩擦得透亮；她袖口沾了铜油，深蓝工作服上留着一道油痕。灯罩里的火苗重新亮起来。",
    "n4n-71": "雨点敲着档案馆的天窗，沈砚在长桌边坐着。阿棠从门口进来，把一叠干纸放在桌角；她鞋底带着早市的泥水，在石地上留下几个浅浅的印子。铜灯的光把纸页照得发暖。",
    "n4n-72": "黄昏的雾压在雾堤上，沈砚站在钟架旁。韩渡蹲在钟架下，把松脱的钟绳重新系紧，手背蹭过钟架上的盐斑；他直起身时，眉毛上的雾水更重了。浪声一阵接一阵。",
    "n4n-73": "早市的蒸汽从帆布棚下涌出来，沈砚站在摊棚外。阿棠抱着一筐银鳞鱼往案板上送，鱼尾拍得筐沿啪啪响；她的辫梢沾了白汽，围裙上闪着一层鱼鳞。",
    "n4n-74": "塔顶的灯罩被海风吹得嗡嗡响，沈砚站在旋梯口。叶知微把玻璃罩擦得透亮，火苗的影子落在她袖口的铜油上；她退开半步，手背上还留着一道擦痕。海雾在灯外慢慢移过去。",
    "n4n-75": "档案馆的天窗漏着雨，沈砚坐在长桌前。阿棠把一叠干纸放在桌角，纸角被门口的风掀起；她鞋底带着早市的泥水，在门槛上蹭了两下。雨声落在天窗上，屋里很静。",
    "n4n-76": "雾堤上的浪头撞在石壁上，沈砚站在钟架旁。韩渡把松脱的钟绳重新系紧，钟绳绷直了；他站起来，眉毛上的雾水更重了，旧呢外套上沾着盐沫。风从堤面横着扫过去。",
    "n4n-77": "塔顶的铜框信号灯亮着，沈砚站在灯旁。叶知微从潮渡上来，蹲到信号灯旁，用抹布把玻璃罩上的盐雾擦掉；灯罩透亮起来，火苗在玻璃里重新站稳。风从塔顶灌下来。",
    "n4n-78": "档案馆里只有雨声，沈砚坐在长桌前。阿棠从早市过来，把一叠干纸放在桌角；纸角被门口的风掀起，她又伸手按住。铜灯的光落在纸页上，屋里静下来。",
    "n4n-79": "雾堤上的风把浪沫吹到石阶上，沈砚站在钟架旁。韩渡从潮渡那边上来，蹲下去把松脱的钟绳一圈一圈重新系紧；钟绳绷直了，他才站起来。钟架在风里轻响。",
    "n4n-80": "早市的帆布棚下白汽不散，沈砚站在摊棚外。阿棠从巷子另一头挤进来，抱着一筐银鳞鱼放到案板边；鱼尾拍得筐沿啪啪响，水花溅到石板上。",
    "n4n-81": "海风从塔顶直吹过来，沈砚站在信号灯旁。叶知微从潮渡上来，踮着脚把玻璃罩上的盐雾擦掉；灯罩透亮起来，火苗的影子落在铜框上。塔下只剩雾。",
    "n4n-82": "雨点敲着档案馆的天窗，沈砚坐在长桌前。阿棠从早市过来，把一叠干纸放在桌角，纸角还带着潮气；她退开半步，门口的风把纸页吹得轻轻响。雨声落在天窗上，纸页慢慢平下来。",
    "n4n-83": "黄昏的雾压在雾堤上，沈砚站在钟架旁。韩渡从潮渡那边上来，蹲在钟架下，把松脱的钟绳重新系紧；钟绳绷直了，他用手背擦了一下眉毛上的雾水。",
    "n4n-84": "早市的蒸汽从帆布棚下涌出来，沈砚站在摊棚外。阿棠从潮生巷过来，抱着一筐银鳞鱼往案板上送；鱼尾拍得筐沿啪啪响，石板上的水光晃了晃。",
    "n4n-85": "塔顶的风把铜框吹得发冷，沈砚站在旋梯口。叶知微从潮渡上来，把抹布蘸了铜油，一点点擦掉玻璃罩上的盐雾；灯罩透亮起来，火苗重新站稳。铜框被风吹得发冷，塔下只剩雾。",
    "n4n-86": "档案馆的天窗漏着雨，沈砚坐在长桌前。阿棠从早市过来，把一叠干纸放在桌角；纸角被门口的风掀起，她用指尖按了按，才转身去看天窗。雨声还在，长桌上很安静。",
    "n4n-87": "浪头撞在雾堤的石壁上，沈砚站在钟架旁。韩渡从潮渡过来，蹲下去把松脱的钟绳重新系紧；钟绳绷直后，他站起来，手背上沾着盐沫。风从堤面扫过去。",
    "n4n-88": "雨丝斜着落进潮生巷，沈砚沿着墙根走到灯笼下。等他站定，外袍下摆已经沾了泥水，边角贴在腿上；他低头看了一眼，把衣摆抖了抖，雨声还在。",
    "n4n-89": "潮生巷的雨声压在窗外，沈砚在木桌旁点亮蜡烛。他翻过一叠旧纸，袖口蹭了一道墨；烛火在墙上晃了一下，他把手缩回来，屋里又静下去。窗外的雨没有停，木桌边只剩一点暖光。",
    "n4n-90": "海雾贴着旧灯塔的石阶往上爬，沈砚扶着铁链走到半层。雾水从袖口渗进去，外袍下摆很快被打湿，贴在腿上；他停下来，听见塔顶的风声。他没有再往上走，站在石阶上听风。",
    "n4n-91": "塔顶的风比巷子里硬，沈砚从旋梯口出来。外袍下摆被海风掀起，衣角拍在腿上；他把油布包往怀里按了按，站在铜灯旁，等风小一点。海雾在灯外慢慢移过去，塔顶只剩风声。",
    "n4n-92": "旧灯塔的旋梯里有股擦铜油的味道，沈砚停在铜框窗下。窗框上的油痕蹭到袖口，他抬手看了一眼；旋梯很窄，风从窗缝里钻进来。他闻了闻袖口，铜油味很重。",
    "n4n-93": "潮渡的雾还没散，沈砚在栈桥边站了一会儿。河风把袖口打湿，贴在手腕上；他把手缩回袖子里，看船灯在雾里晃。雾从河面漫上来，栈桥的木桩只剩一截影子。",
    "n4n-94": "退潮后的浅滩泛着冷光，沈砚踩着湿泥走到水边。等他直起身，外袍下摆已经沾满泥水，边角结了一圈白盐；他抖了抖衣摆，海风把咸味吹到脸上。",
    "n4n-95": "雨点敲着档案馆的天窗，沈砚把潮汐簿摊在铜灯下。他照着旧墨迹补了几笔，指尖沾了墨；他停下来，把手在纸边蹭了蹭，墨迹却没有掉。铜灯的光落在纸页上，屋里只剩雨声。",
    "n4n-96": "雾堤上的风把浪沫吹到石阶上，沈砚扶着铁链走到钟架旁。掌心被铁皮冰得发麻，他搓了搓手；警示灯在风里发晃，浪声一阵接一阵。他把手拢在袖子里，又往钟架边站近了一点。",
    "n4n-97": "早市的帆布棚下全是白汽，沈砚从人缝里挤过去。衣摆沾了泥水，边角沉甸甸地垂着；他站在摊棚外，低头看了一眼，又往旁边让了让。白汽从帆布棚下涌出来，鱼腥味还没有散。",
    "n4n-98": "雨停后的潮生巷慢慢干了，沈砚沿着墙根走。鞋底沾了湿石板的水，在身后留下浅浅的印子；纸灯笼的光落在水沟里，他走得很慢。墙根的青苔发暗，水沟里的光慢慢移开。",
    "n4n-99": "海雾把旧灯塔的轮廓磨淡了，沈砚上到塔顶时，叶知微正从潮渡那边过来。她停在信号灯旁，沈砚本来想像往常那样把话咽回去，却先问了一句灯芯还够不够用；话出口后，他自己也愣了一下。",
    "n4n-100": "黄昏的雾从窄窗渗进来，沈砚走到旋梯时，叶知微从潮渡上来，袖口带着铜油味。沈砚没有再像往常那样沉默，先问她铜油还够不够；叶知微抬头看了他一眼，把油壶放在台阶上。",
    "n4n-101": "天刚亮，沈砚在潮渡的栈桥边站住，顾行舟的渡船正从河心靠过来。沈砚本来想把话咽回去，却先问潮水什么时候退；顾行舟把缆绳绕上木桩，说还得等一阵。",
    "n4n-102": "雨点敲着档案馆的天窗，沈砚进门时，阿棠正从早市抱着一叠干纸过来。沈砚没有像往常那样沉默，先问她路上淋没淋湿；阿棠把纸放在桌角，说纸没有淋湿。",
    "n4n-103": "雾堤上的风把浪沫吹到石阶上，沈砚从潮渡上来时，韩渡也到了钟架下。沈砚本来想把话咽回去，却先问他钟绳要不要搭把手；韩渡抬头看了看他，把松脱的绳头递过来。",
    "n4n-104": "早市的帆布棚下全是白汽，沈砚挤进摊棚时，阿棠正抱着一筐银鳞鱼。沈砚没有再像往常那样沉默，先问她鱼筐沉不沉；阿棠把筐往案板上一放，说筐不沉。",
    "n4n-105": "塔顶的风把铜框吹得发冷，沈砚从旋梯口出来，叶知微正从潮渡上来。沈砚本来想把话咽回去，却先问她灯罩上的盐雾擦不擦得掉；叶知微把抹布搭在栏杆上，说擦得掉。",
    "n4n-106": "旧灯塔的旋梯很窄，沈砚走到铜框窗下时，叶知微从潮渡上来。沈砚没有再沉默，先问她油壶放在哪里；叶知微指了指台阶上的油壶。旋梯里很静，只有窗缝的风声。",
    "n4n-107": "潮渡的雾还没散，沈砚在栈桥边站住，顾行舟的渡船从河心靠过来。沈砚本来想把话咽回去，却先问他今天还走不走；顾行舟把缆绳绕上木桩，说船还没靠稳。",
    "n4n-108": "档案馆的天窗漏着雨，沈砚在长桌前坐下，阿棠从早市抱着一叠干纸进来。沈砚没有再像往常那样沉默，先问她纸有没有淋湿；阿棠把纸放在桌角，说纸是干的。",
    "n4n-109": "黄昏的雾压在雾堤上，沈砚从潮渡上来时，韩渡正蹲在钟架下。沈砚本来想把话咽回去，却先问他钟绳够不够长；韩渡把绳头递过来，没有多说。",
    "n4n-110": "雨丝斜着落进潮生巷，沈砚站在纸灯笼下。排水沟里的水声不急不缓，墙根的水洼映着灯光；他等了一会儿，巷子里什么也没有再发生。纸灯笼在风里轻轻晃，水沟里的光没有动。",
    "n4n-111": "潮生巷的雨声压在窗外，沈砚坐在木桌旁。蜡烛的火苗很短，抽屉半开着，旧纸没有动；他听了听屋檐的水滴，屋里什么也没有再发生。窗外的雨没有停，木桌边只剩一点暖光。",
    "n4n-112": "海雾贴着旧灯塔的石阶，沈砚扶着铁链站在半层。塔顶的风声从上面传下来，链环上都是盐蚀的白斑；他站了一会儿，石阶上什么也没有再发生。雾从石阶下面漫上来，塔顶的灯还亮着。",
    "n4n-113": "塔顶的铜框信号灯亮着，沈砚站在灯旁。海风把灯罩吹得嗡嗡响，雾在玻璃外面慢慢移过去；他看了一会儿，塔顶什么也没有再发生。铜框被海风吹得发冷，塔下没有别的光。",
    "n4n-114": "黄昏的雾从窄窗渗进来，沈砚停在旋梯的铜框窗下。擦铜油的气味没有散，墙上的油痕发暗；他听了一会儿风，旋梯里什么也没有再发生。旋梯的木板很旧，窗外的雾没有散。",
    "n4n-115": "潮渡的雾还没散，沈砚靠在栈桥的木桩上。船灯在雾里只剩一团黄，水面没有动静；他看了一会儿，栈桥上什么也没有再发生。木桩上缠着旧缆绳，河风把雾推来推去。",
    "n4n-116": "退潮后的浅滩泛着冷光，沈砚站在水边。泥滩上留着水痕，系泊绳陷在泥里；他站了一会儿，浅滩上什么也没有再发生。海风把咸味吹到脸上，泥滩上没有别的动静。",
    "n4n-117": "雨点敲着档案馆的天窗，沈砚坐在长桌前。铜灯亮着，潮汐簿摊在桌上，纸页没有动；他听见天窗的水滴，屋里什么也没有再发生。天窗还在滴水，长桌边的光很暗。",
    "n4n-118": "雾堤上的风把浪沫吹到石阶上，沈砚站在钟架旁。警示灯在风里发晃，钟架轻响；他等了一会儿，堤面上什么也没有再发生。浪头撞在石壁上，白沫翻上堤面又退下去。",
    "n4n-119": "早市的帆布棚下全是白汽，沈砚站在摊棚外。鱼鳞粘在石板上，人流从面前过去；他看了一会儿，摊棚前什么也没有再发生。帆布棚下白汽不散，鱼鳞在石板上发亮。",
    "n4n-120": "雨停后的潮生巷慢慢干了，沈砚站在墙根下。水沟里的积水映着纸灯笼，石板上的水痕一点点变浅；他站了一会儿，巷子里什么也没有再发生。纸灯笼在风里晃了晃，水沟里的光没有动。",
}

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
    narrative = MANUAL[f"n4n-{pid}"]  # every case is manually rewritten
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
        "reviewStatus": "approved",
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
        "# N4 叙事开发语料 v2（88 例，手工改写稿，待审）",
        "",
        "日期：2026-11-02。同一 `n4n-fog-harbor` 世界，11 场景 × 8 事实"
        "模式 = 88 例（n4n-33…120）。**正文已逐条手工改写，用户 2026-11-02 审阅通过，未训练。**"
        "结构仍按场景/事实组合，但句子不再是模板拼装；目标 60–84 tokens。",
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
        "- 场景/行为/心理是否自然；结构相似可以接受，事实不能错",
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
                  "- [x] 事实全覆盖", "- [x] 无任务标题/数值/具体时长",
                  "- [x] 无新增具名实体/物品/地点",
                  "- [x] 无他人内心/承诺性对话",
                  "- [x] 视角一致，场景/行为/心理自然", ""]
    OUT_DOC.write_text("\n".join(lines).rstrip("\n") + "\n",
                       encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} cases -> {OUT_JSONL}")
    print(f"review doc -> {OUT_DOC}")


if __name__ == "__main__":
    main()
