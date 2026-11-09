"""Author/check one fixed demonstration asset; never called during gameplay.

No model, network, randomness, or runtime world generation is used. The shipped
JSON is the existing WorldState type, including its existing initial projection.
Run with --write to publish the authored snapshot; default mode checks it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.world.canonical import parse_json
from app.schemas.world.contracts import WorldInitialState, WorldState
from app.services.world.state import build_initial_state, state_digest

OUTPUT = ROOT / "data/worlds/dragon-raja-free-day.world.json"


def authored_world() -> WorldState:
    locations, characters, items = {}, {}, {}

    def slots(*pairs):
        return [{"id": key if key.startswith("slot_") else f"slot_{key}", "label": label}
                for key, label in pairs]

    def location(key, name, parent, appearance, *positions):
        locations[key] = {
            "id": key, "name": name, "parentLocationId": parent,
            "initialAppearance": appearance, "slots": slots(*positions),
        }

    def position(container, slot=None, relative=None):
        return {
            "containerId": container,
            "slotId": (slot if slot.startswith("slot_") else f"slot_{slot}") if slot else None,
            "relativeTo": ({"entityId": relative[0], "relation": relative[1]}
                           if relative else None),
        }

    def person(key, name, room, appearance, personality, sanity, goals, slot=None):
        tasks = {}
        for goal in goals:
            task_key, parent, text, *status = goal
            task_id = f"task_{key}_{task_key}"
            tasks[task_id] = {
                "id": task_id, "ownerId": key,
                "parentTaskId": f"task_{key}_{parent}" if parent else None,
                "goal": text, "status": status[0] if status else "pending",
            }
        characters[key] = {
            "id": key, "name": name, "initialPosition": position(room, slot),
            "initialAppearance": appearance, "initialPersonality": personality,
            "initialSanity": sanity, "tasks": tasks,
            "slots": slots(("left_hand", "左手"), ("right_hand", "右手"),
                           ("body", "身上"), ("waist", "腰侧"), ("pocket", "衣袋")),
        }

    def item(key, name, container, appearance, slot=None, relative=None, storage=()):
        items[key] = {
            "id": key, "name": name,
            "initialPosition": position(container, slot, relative),
            "initialAppearance": appearance, "slots": slots(*storage),
        }

    location("campus", "卡塞尔学院演习区", None,
             "自由一日的演习边界用黄黑绳围定，范围包括钟楼、中央庭院、两侧回廊和西侧器材区；北侧医护通道悬白旗，不属于交火区。场内使用弗里嘉演习弹，实弹与攻击医护人员均被禁止。")
    location("west", "西侧器材区", "campus",
             "器材棚、服务巷和西侧集结点围成一条后勤线；从服务巷可到庭院西口，也能绕进检修通道。运送伤员可沿白线到医护附楼，不必穿越庭院。")
    location("lane", "西侧服务巷", "west",
             "巷口的黄黑绳已放下，进入即算踏入演习区。右墙贴着赛区图，器材棚门敞开；巷子尽头的低墙挡住庭院视线，墙角留下新鲜的演习弹红痕。",
             ("wall", "低墙后的掩蔽处"), ("entry", "器材棚门外"))
    location("shed", "器材棚", "west",
             "推拉门可回服务巷。领用台与带锁器材笼分处两侧，中间留有担架能通过的宽度；备用弹药箱已开盖，笼门的挂锁仍扣着。",
             ("counter", "领用台前"), ("slot_cage", "器材笼外"))
    location("cage", "器材笼内", "shed",
             "金属网笼内只有一架折叠梯、一卷安全绳和一副担架；网眼容手指穿过，整件器材只能从笼门搬出。挂锁钥匙由器材值班员保管。")
    location("yard", "中央庭院", "campus",
             "喷泉池沿把庭院分成东西两片射界。红方从东侧集结点接近，蓝布带挂在西回廊口；钟楼正门在北面。露天横穿最短，但要同时暴露给两边的窗口。",
             ("south_cover", "南端石花槽后"), ("east_cover", "东侧倒放长椅后"))
    location("fountain", "停水喷泉池", "yard",
             "水泵已关，池底残水没过鞋底。靠钟楼一侧的池沿有缺口，可低身钻出；东侧雕像基座能遮住上半身，却挡不住来自高处的射线。",
             ("basin", "池底"), ("north_gap", "北侧池沿缺口"))
    location("west_arcade", "西回廊", "campus",
             "廊柱连接器材区与钟楼西门，腰高石栏可作掩体。第三根廊柱脚下有一条折断的蓝布带；钟楼方向的石板湿滑，不能直接奔跑过去。",
             ("pillar3", "第三根廊柱后"), ("tower_door", "钟楼西门旁"))
    location("east_arcade", "东回廊", "campus",
             "两扇低窗分别朝庭院和钟楼阶梯。南端通红方集结点，北端是跨溪小桥；拉下窗内的帆布遮光帘能藏住身影，也会失去观察庭院的视线。",
             ("window", "庭院侧低窗内"), ("north", "通小桥的廊口"))
    location("bridge", "跨溪小桥", "campus",
             "小桥连接东回廊和钟楼东侧，护栏中段松动。桥下排水沟不足以站人，但可匍匐经过；桥头的白色标牌指出北侧支路直达医护附楼。",
             ("east_end", "东回廊一侧桥头"), ("west_end", "钟楼一侧桥头"))
    location("tower", "钟楼", "campus",
             "钟楼正门朝庭院，西门接西回廊，检修口接地下通道。楼内从门厅经下层楼梯、二层平台到顶层旗台；演习信号旗位于顶层外廊。")
    location("foyer", "钟楼门厅", "tower",
             "正门半开，木门背后有弹着痕。西门向外推开，地下检修门则从里面插着门闩；下层楼梯入口被翻倒的长桌挡住一半。",
             ("front_door", "正门内侧"), ("stairs", "楼梯口"))
    location("lower_stairs", "钟楼下层楼梯", "tower",
             "石阶只容两人错身，内侧扶手完好。第七级边缘崩落，携担架上行需两人配合；转角看不到二层平台，声音却能沿楼梯传下来。")
    location("landing", "钟楼二层平台", "tower",
             "平台窗口能看见庭院喷泉，窗下留有一段射击盲区。通顶层的楼梯口拉着蓝色识别带，平台另一端的小门通向空的值钟间。",
             ("window", "朝庭院的窗口旁"), ("slot_upper_stairs", "上层楼梯前"))
    location("bell_room", "值钟间", "tower",
             "窄门只通二层平台；木工作台固定在墙边，墙上的机械检修图标出了旗台锁扣的人工释放方向。这里没有通往塔顶的捷径。")
    location("upper_stairs", "钟楼上层楼梯", "tower",
             "铁制旋梯绕过钟摆井，踏板一人通过时轻响，两人并上会明显摇晃；顶部出口的蓝布带垂到栏杆内侧。外廊旗台必须经顶层才能到达。")
    location("top", "钟楼顶层", "tower",
             "钟摆机构用铁网隔开，南窗可观察庭院。东侧玻璃门通外廊，门把手缠着一道蓝布带；门仍可打开，识别带不是封锁锁具。",
             ("south_window", "南窗下"), ("balcony_door", "外廊门旁"))
    location("balcony", "钟楼旗台外廊", "tower",
             "外廊只容两人并肩，护栏齐腰，旗台底座固定在墙上。中立白旗卡在底座锁扣里，侧面的手动释放杆可见；强拽旗杆会把人带离护栏内侧。",
             ("flag_base", "旗台底座前"), ("door", "顶层玻璃门外"))
    location("red_rally", "红方集结点", "campus",
             "红布系在雨棚梁上，折叠地图桌面朝庭院。这里能经东回廊绕到小桥，也能直接进庭院；一只备用电池盒放在地图桌下，箱盖没有锁。")
    location("blue_rally", "蓝方集结点", "campus",
             "蓝色篷布下摆着伤员标记板与一张空折叠椅。补给可沿西回廊送往钟楼；医护白线路径就在后方，撤出这条线的人不再参与射击。")
    location("tunnel", "地下检修通道", "campus",
             "通道一端接服务巷地面的检修盖，另一端到钟楼地下门；尽头没有出口到其他建筑。灯只亮了一半，地面有浅水，推运器材会发出明显回声。")
    location("hatch", "服务巷检修口", "west",
             "方形检修盖虚掩，拉环朝上。盖下短梯能到地下检修通道，携枪下行需腾出一只手；检修口边的器材筐有绝缘手电。")
    location("annex", "医护附楼", "campus",
             "白旗与白线将附楼连到两侧回廊，进门必须收起演习枪。走廊一端是处置室，另一端是休息区；已撤出的人员不能从这里重新绕回交火区。")
    location("aid", "演习医护处置室", "annex",
             "两张诊疗床之间有移动屏风，门口登记夹分开记录演习中弹与实际扭伤。运送伤员的担架可直接推到空床旁，医护箱已打开。",
             ("empty_bed", "空床侧"), ("desk", "登记台前"))
    location("rest", "医护休息区", "annex",
             "靠墙长椅留有一处空位，饮水机和保温毯都在触手可及处。门外的白线划定退出区，休息者可以提供已见情况，但不能再回场替队伍争旗。")
    location("control", "演习观察席", "campus",
             "观察席高于庭院半层，红蓝旗台指示灯都未亮。模拟终端显示停赛时间15:45，广播台能发布安全暂停；观察员不替任何一方提供战术情报。")

    person("lu", "路明非", "lane",
           "校服领口松着，膝盖沾了灰；护目镜挂在胸前，右手还空着，身上没有红蓝识别带。听见远处枪声会下意识缩肩。",
           "习惯先用一句玩笑替自己解围，真见到有人受伤又很难装作没看见。认识诺诺和室友芬格尔，对楚子航有同校旧识的熟悉感，却还没答应加入任何一方；很想证明自己不是只能被别人保护的人。",
           43, [
               ("match", None, "在自由一日结束前作出自己的参赛选择，并完成一次能由在场人确认的有效行动后安全离场"),
               ("choice", "match", "向诺诺问清当前红蓝两方局势和自己是否可以保持中立"),
               ("kit", "match", "在进入交火区前拿到可用的护目镜与演习装备"),
               ("goggles", "kit", "把胸前护目镜戴好并确认镜片没有裂纹"),
               ("route", "match", "在庭院正路、西回廊和地下检修通道之间选择一条有掩护的路线"),
               ("ally", "match", "得到至少一名在场者明确同意的协作，不替他人擅自承诺"),
               ("rules", "match", "读过服务巷规则牌，知道医护白线内禁止交火", "achieved"),
           ], "wall")
    person("nono", "诺诺", "lane",
           "红发用发圈束在脑后，红色识别带缠在左臂；右袖的红痕是扶过弹着石墙时蹭上的，身上没有本场命中标记，手里的短枪枪口压向地面。",
           "看人时比听解释更有耐心，开玩笑尖锐却会在危险前把人拉住。属于凯撒的红方，愿意给路明非提示，但不愿替他选阵营；知道西回廊有蓝方伤员，尚不知道伤势是否真实。",
           58, [
               ("squad", None, "让红方的旗台行动有可执行的掩护，而不把路明非当诱饵"),
               ("lu", "squad", "问清路明非的参赛意愿并说明三条接近钟楼的路线"),
               ("battery", "squad", "把故障短讯机恢复到能与凯撒联络的状态"),
               ("wounded", "squad", "确认西回廊的蓝方伤员是否需要真正的医护帮助"),
               ("signal", "squad", "与凯撒约定可被双方看见的进攻信号，再决定何时离开服务巷"),
           ], "entry")
    person("fingel", "芬格尔", "shed",
           "头盔歪扣着，食指蹭了油；旧相机挂在脖子上，左臂没有阵营布带。护膝一边扣紧、一边还敞着。",
           "愿意把每一条小道说成独家情报，能赚钱或换饭时尤其热心；并不愿真把同伴带进死路。与路明非同住，知道检修通道通向钟楼地下门，也知道门闩在钟楼里面。",
           51, [
               ("deal", None, "在自己不被淘汰的前提下用路线情报换到演习照片的拍摄机会"),
               ("map", "deal", "把检修门从里面插闩这件事告诉准备走地下路线的人"),
               ("camera", "deal", "换上相机备用电池，拍到有辨识度的争旗场面"),
               ("help", "deal", "若路明非求助，给出可验证的器材或路线帮助，而不是空口保证安全"),
               ("soup", "deal", "保住自己腰包里的饭票，不拿别人的补给抵债"),
           ], "counter")
    person("chu", "楚子航", "landing",
           "蓝色识别带贴着上臂，黑色袖口扣紧；护目镜遮住眼睛，左手扶在窗口下沿，右手持枪但手指离开扳机。",
           "决定一旦作出就很少解释第二遍，习惯先确认撤离路线再谈胜负。带领蓝方守钟楼，与凯撒竞争而尊重对方；知道路明非不是熟练参赛者。已收到林亦舟受伤的短讯，尚未确定他能否自行撤离。",
           72, [
               ("hold", None, "守住钟楼旗台，同时让蓝方真正受伤的人安全撤离"),
               ("lin", "hold", "查明林亦舟的扭伤是否妨碍行走，并决定是否派人接应"),
               ("su", "hold", "与苏茜确认东回廊的射界，避免两人同时离开防线"),
               ("hatch", "hold", "检查钟楼地下检修门的门闩，不能把地下路线当成不存在"),
               ("flag", "hold", "在红方进入顶层前安排旗台的持守与撤退信号"),
               ("line", "hold", "约定蓝方听见安全暂停广播就停止射击", "achieved"),
           ], "window")
    person("caesar", "凯撒", "red_rally",
           "金发被护目镜带压出一道痕，红色识别带整齐缠在左臂；手套指节处擦白，地图桌上的笔尖正压着东回廊。",
           "自信且喜欢让计划听起来毫不费力，但不接受用真实伤势换胜利。带领红方，与楚子航争夺旗台；信任诺诺的现场判断，不把未收到的回报当作已经执行成功。",
           76, [
               ("win", None, "在15:45停赛前让红方取得可确认的旗台控制权"),
               ("contact", "win", "恢复与诺诺的联络，确认她是否愿意负责服务巷方向"),
               ("bridge", "win", "查明跨溪小桥是否仍能通行，不让小队在松动护栏处挤作一团"),
               ("tang", "win", "让唐骁报告庭院火力位置，再决定正面吸引还是撤换路线"),
               ("flag", "win", "安排登旗台的人携带可识别的红方旗，不以口头宣布代替实际占领"),
           ])
    person("su", "苏茜", "east_arcade",
           "蓝色识别带外又绕了一圈黑色胶带，长枪架在低窗内的软垫上；左手虎口磨红，护目镜右侧附着一小点漆。",
           "观察与报告比争论快，愿意替楚子航补上他没有说出口的细节。蓝方成员，负责东侧警戒；不肯向医护白线内追射，看到对手停火救人时会先核实而不是立即开枪。",
           67, [
               ("watch", None, "守住东回廊对钟楼的接近线，并保持蓝方信息可信"),
               ("report", "watch", "向楚子航报告跨溪小桥的实际人员和松动护栏"),
               ("reload", "watch", "在当前弹匣打空前确认身后的备用弹匣属于自己"),
               ("lin", "watch", "核实西回廊求助是否为真实伤情，在必要时配合停火"),
               ("exit", "watch", "保留从低窗退到北廊口的路线，不把长枪留在窗外"),
           ], "window")
    person("lin", "林亦舟", "west_arcade",
           "蓝色识别带沾着灰，左脚踝在鞋帮上方肿起；背靠第三根廊柱坐着，演习枪已经放到右手碰不到的地面。说话正常，没法独自站稳。",
           "蓝方低年级队员，怕被看成拖累，一开始只报了位置而没有讲清伤势。与同队的苏茜说得上话，信任楚子航会来接应；不愿用假装中弹的方式掩盖真实扭伤。",
           29, [
               ("leave", None, "在不加重脚踝伤势的情况下到达演习医护处置室"),
               ("call", "leave", "向能听见的人说明是实际扭伤，不是弗里嘉弹造成的暂时失能"),
               ("safe", "leave", "把自己的演习枪交给可信的人或移出医护搬运路线"),
               ("carry", "leave", "得到明确愿意帮忙的搬运者，并沿白线撤离"),
               ("sent", "leave", "用蓝方短讯机发出自己位于第三根廊柱的求助", "achieved"),
           ], "pillar3")
    person("tang", "唐骁", "yard",
           "红色识别带勒在肩上，衣襟有上回演习未洗净的两处旧红斑，本场尚未被命中；半蹲在倒放长椅后，空弹匣扔在脚边，护目镜完好。",
           "红方推进队员，动作快但不喜欢等，容易把短暂安静误认成对手离开。听凯撒指挥，却认为自己也有必要争一次首功；知道医护白线的禁射规则。",
           38, [
               ("push", None, "为红方接近钟楼正门提供真实有效的掩护"),
               ("ammo", "push", "在再次探身前更换空弹匣，不把空枪当成掩护火力"),
               ("report", "push", "向凯撒报告自己能确认的窗口位置，不能把猜测报成已压制"),
               ("pause", "push", "遇见真实伤员撤离时停火，并把停火原因通知同队"),
               ("fallback", "push", "被两处射界夹住时保留退到南端花槽的机会"),
           ], "east_cover")
    person("zhou", "周映", "balcony",
           "蓝色头盔边缘蹭破了一块漆，右手戴着半指手套；人站在旗台底座内侧，安全绳还没有扣上腰带。",
           "蓝方旗台守备员，想让自己的表现被队长看见，却清楚外廊护栏外不能冒险。知道白旗锁扣有些卡，但尚未使用释放杆；若有人明确承担掩护，会愿意配合移旗或撤退。",
           46, [
               ("guard", None, "守住旗台，并在需要时安全操作信号旗"),
               ("rope", "guard", "在靠近外廊边缘前把安全绳扣好并确认另一端固定"),
               ("latch", "guard", "弄清白旗锁扣的释放方向，不强拽旗杆"),
               ("warn", "guard", "将锁扣卡滞和未固定安全绳的情况告知楚子航"),
               ("retreat", "guard", "若守不住外廊，从玻璃门退回顶层而不是翻护栏"),
           ], "flag_base")
    person("qin", "秦越", "shed",
           "灰色器材背心套在校服外，胸前挂着领用牌；右膝护具扣好，手里的记号笔没有笔帽，器材笼钥匙扣在腰环上。",
           "中立器材值班员，宁可得罪参赛者也不愿器材去向不明；真实伤员的救助优先于补签。认得芬格尔拿器材不登记的习惯，愿意在有人说清用途和归还责任时开笼。",
           61, [
               ("gear", None, "让演习器材可追溯地发放，并优先保证伤员搬运"),
               ("stretcher", "gear", "在接到真实扭伤报告后开笼放行担架并登记搬运者"),
               ("ladder", "gear", "问清折叠梯用途，不放行把梯子架到禁入护栏外的方案"),
               ("battery", "gear", "确认短讯机电池与相机电池型号不同，避免拿错"),
               ("return", "gear", "在停赛后核回安全绳、担架与领用牌"),
           ], "slot_cage")
    person("doctor", "顾岚", "aid",
           "白色医护外套没有阵营标记，听诊器收到衣袋；站在空床旁，手套尚未戴上，登记夹摊在桌面。",
           "本场值班校医，先问症状再决定处置，不把演习胜负看得比真实伤情重要。与负责安抚和分流的富山雅史配合；不会仅因伤员所属阵营改变处理顺序。",
           81, [
               ("treat", None, "完成实际受伤人员的接诊并让医护区保持中立"),
               ("prepare", "treat", "为可能送来的脚踝扭伤者留出空床与冷敷材料"),
               ("triage", "treat", "询问并核实伤者能否负重，避免把真实伤势误作演习淘汰"),
               ("signal", "treat", "需要时请求演习观察席安排白线通道停火"),
               ("rest", "treat", "核对医护休息区已退出者，不允许他们带枪重新回场"),
           ], "empty_bed")
    person("shen", "沈澄", "rest",
           "红色识别带已经拆下放在长椅旁，胸口护具留着演习弹痕；中弹后已醒来，现坐着喝水，右手指尖仍有轻微麻感，演习枪不在身边。",
           "红方已退出队员，对提前离场不甘心但认同医护中立。亲眼看过唐骁在庭院换位，可以讲自己当时看到的路线；没有亲眼看到钟楼内部，不会把传闻当作实时位置。",
           41, [
               ("recover", None, "在医护休息区恢复并提供不违反退出规则的帮助"),
               ("symptom", "recover", "向顾岚说明手指麻感是否减轻"),
               ("account", "recover", "若被询问，只说明退出前亲眼看见的庭院路线"),
               ("stay", "recover", "在获准离开医护区前不重新加入争旗"),
               ("checked", "recover", "放下演习枪并按要求拆下红色识别带", "achieved"),
           ])
    person("tomiyama", "富山雅史", "rest",
           "胸牌写着心理辅导，外套上没有红蓝标记；手中拿着一只未拆的纸杯，与沈澄隔着一人距离坐着，没有挡住医护通路。",
           "学院心理辅导教员，本场负责退出人员的安抚与分流，实际伤情交给顾岚处理。善于让紧张的学生先把眼前事实说清，不把输掉演习说成人的失败；不向参赛者传递休息者未同意公开的谈话。",
           79, [
               ("support", None, "让退出演习的学生稳定下来，并把实际伤情及时交给顾岚"),
               ("shen", "support", "询问沈澄醒来后的状态，听清她担心的是麻感还是拖累队友"),
               ("refer", "support", "若沈澄的麻感没有减轻，协助她向顾岚说明而不是自行认定无事"),
               ("boundary", "support", "说明退出不等于失去价值，同时守住不能回场参战的边界"),
               ("help", "support", "有人来求援时帮助传达真实伤情，不把医疗求助改成战术情报"),
           ])
    person("manstein", "曼施坦因", "control",
           "眼镜架在鼻梁低处，观察员白袖标盖住外套袖口；广播话筒放在右手边，桌上的事故记录单还是空白。",
           "厌恶学生把演习当成不必负责的混乱，安全规则比裁定输赢优先；不向任何队伍泄露对方位置。只有核实需要时才发布暂停，停赛后要求报告能对应记录而不是互相甩锅。",
           84, [
               ("order", None, "让自由一日按中立规则结束，真实伤情得到处置"),
               ("clock", "order", "在15:45发布停赛通知并核对旗台最终状态"),
               ("injury", "order", "核实西回廊伤情，必要时广播局部停火而不是偏袒某队"),
               ("radio", "order", "让短讯机故障用可核对的方式报修，不能私改计分"),
               ("log", "order", "把实际安全违规与普通战术失败分开记录"),
           ])

    item("rules", "演习规则牌", "lane", "牌面写明：使用弗里嘉演习弹；护目镜必须戴好；医护白线禁射；退出者不得返场；15:45停赛。夺旗须取下中立白旗、把本队旗插入底座并由现场确认，携带自己的旗不算占领。")
    item("map", "赛区路线图", "lane", "图上画出庭院、东西回廊、跨溪小桥、钟楼与白线撤离路；地下检修通道用虚线标注，未标门闩状态。")
    item("goggles_lu", "路明非的护目镜", "lu", "镜片无裂纹，镜带松着，现挂在胸前而非戴在眼前。", "body")
    item("jacket_lu", "路明非的演习背心", "lu", "背心前襟完好，没有演习弹痕；胸袋能放一只弹匣，肩上没有阵营识别带。", "body", storage=(("chest", "胸袋"),))
    item("pistol_nono", "诺诺的演习短枪", "nono", "枪上有黄色演习标记，弹匣内剩3发弗里嘉演习弹，保险合上，枪口向下。", "right_hand")
    item("radio_nono", "诺诺的故障短讯机", "nono", "电量灯不亮，电池盖扣牢；机身标注需要R型短讯电池，屏幕停在尚未发出的联络请求。", "waist")
    item("red_band_nono", "诺诺的红色识别带", "nono", "系在左臂，结头朝外，完整且尚未被拆下。", "body")
    item("camera", "芬格尔的相机", "fingel", "镜头盖已经取下，电池图标只剩一格；存储卡仍在机内，能拍照但随时可能断电。", "body")
    item("meal_tickets", "芬格尔的饭票夹", "fingel", "透明夹内有两张当晚食堂饭票，夹口扣紧，没有其他人的借条。", "pocket")
    item("camera_battery", "相机备用电池", "fingel", "C型相机电池，满电封签未拆；触点形状与R型短讯电池不同。", "pocket")
    item("rifle_chu", "楚子航的演习枪", "chu", "枪身有黄色演习标记，弹匣内剩7发，保险合上；背带能让双手短暂腾空。", "right_hand")
    item("blue_radio", "楚子航的蓝方短讯机", "chu", "电量足，最近收到的消息只写着林亦舟在第三根廊柱、需要帮助，未说明伤情类型。", "waist")
    item("blue_band_chu", "楚子航的蓝色识别带", "chu", "蓝布贴着左上臂，边缘干燥，是蓝方指挥识别。", "body")
    item("red_map_desk", "红方地图桌", "red_rally", "桌脚稳固，桌上压着庭院平面图；桌下空间能容一只电池盒。", storage=(("top", "桌面"), ("under", "桌下")))
    item("caesar_map", "凯撒的庭院平面图", "red_map_desk", "图上标出正门进攻线与东回廊绕行线；两条都只是待选计划，没有执行成功的记录。", "top")
    item("rifle_caesar", "凯撒的演习枪", "caesar", "弹匣内有10发演习弹，保险合上，背带斜挂在肩上。", "body")
    item("red_flag", "红方信号旗", "caesar", "红布折在旗杆旁，底端接口与钟楼旗台底座相配；目前仍由凯撒携带，尚未占旗台。", "left_hand")
    item("red_band_caesar", "凯撒的红色识别带", "caesar", "红布整齐系在左臂，没有退出标记。", "body")
    item("radio_caesar", "凯撒的红方短讯机", "caesar", "电量足，红方频道正常；与诺诺的联络请求尚未收到回复，不能显示她已执行任何路线。", "waist")
    item("rifle_su", "苏茜的演习长枪", "su", "枪托压在软垫上，弹匣内剩2发，枪口收在窗内，保险未合。", "right_hand")
    item("radio_su", "苏茜的蓝方短讯机", "su", "电量足，蓝方频道可用；当前没有关于林亦舟实际伤势的详细报告。", "waist")
    item("su_magazine", "苏茜的备用弹匣", "east_arcade", "蓝色胶带标着苏茜的名字，装有8发演习弹，放在低窗内侧而非窗外。")
    item("window_pad", "低窗软垫", "east_arcade", "软垫铺在窗内石沿，靠走廊一侧已经压扁，移动长枪时可以一并收回。")
    item("canvas_blind", "东回廊遮光帘", "east_arcade", "帆布卷在窗框上方，拉绳垂到腰高；放下后遮住庭院视线，也挡住窗内轮廓。")
    item("lin_gun", "林亦舟放下的演习枪", "west_arcade", "枪躺在第三根廊柱旁，保险合上，弹匣内剩4发；与坐着的林亦舟相隔一臂，已离开他的手。", relative=("lin", "beside"))
    item("lin_radio", "林亦舟的短讯机", "lin", "电量两格，已发送求助；发送记录只有位置与请求帮助，没有写明脚踝扭伤。", "waist")
    item("broken_blue_band", "折断的蓝布带", "west_arcade", "蓝布带一端压在第三根廊柱脚下，断口散开，不能证明佩戴者已被演习淘汰。")
    item("rifle_tang", "唐骁的演习枪", "tang", "枪机停在后位，当前没有弹匣；换入可用弹匣前无法射击。", "right_hand")
    item("tang_magazine", "唐骁的满弹匣", "tang", "红胶带缠在底部，装有6发演习弹，卡榫完好。", "waist")
    item("empty_magazine", "庭院空弹匣", "yard", "弹匣已空，红胶带上有泥，落在东侧倒放长椅后。")
    item("bench_cover", "倒放长椅", "yard", "长椅倒扣，木背板能挡住低处射线，两端仍然暴露；一条腿折断，无法承受再站一个人。")
    item("flower_box", "南端石花槽", "yard", "石壁齐腰，内侧有可蹲下的位置；与喷泉之间隔着两步无遮挡石地。")
    item("flag_base", "钟楼旗台底座", "balcony", "底座与墙固定，锁扣夹着中立白旗的杆脚；侧面有向内压的手动释放杆，杆脚未松开前强拽不能取旗。", storage=(("socket", "旗杆锁扣"), ("anchor", "内侧固定环")))
    item("white_flag", "中立白旗", "flag_base", "白布挂在短旗杆上，没有红蓝标记；杆脚被锁扣卡住，未被任何一方取下。", "socket")
    item("flag_rope", "旗台短安全绳", "zhou", "两头锁扣都没有扣上，一端搭在周映腰带边，另一端仍盘在手边。", "waist")
    item("blue_flag", "蓝方信号旗", "top", "蓝布与短杆靠在南窗下，底端接口与旗台相配；尚未安装，不能据此认定蓝方已取得最终控制。")
    item("balcony_door", "顶层玻璃门", "top", "门合着但未锁，门把缠一道蓝布；向外推开可到外廊，玻璃完整。")
    item("maintenance_chart", "旗台机械检修图", "bell_room", "图上画明：先向内压释放杆，再垂直提起旗杆；更换时另一人需控制杆身，禁止向护栏外横拉。")
    item("bench_work", "值钟间工作台", "bell_room", "工作台与墙连接，台面能平放一副旗杆；下方没有暗门或通道。")
    item("foyer_table", "门厅翻倒长桌", "foyer", "长桌斜挡楼梯口，现有空隙够一人侧身，担架过不去；挪桌需要先腾开桌腿压住的位置。")
    item("hatch_door", "钟楼地下检修门", "foyer", "铁门关闭，内侧门闩插在槽里；门外是地下检修通道，外面没有能直接开闩的把手。")
    item("hatch_cover", "服务巷检修盖", "hatch", "铁盖虚掩，拉环可握，重量需要稳定提起；盖沿不宜放枪和松散弹匣。")
    item("flashlight", "绝缘手电", "hatch", "开关处于关闭，电量指示三格；灯头绝缘圈完整，附腕绳。")
    item("bridge_rail", "小桥松动护栏", "bridge", "中段两枚固定螺母退松，轻推就能看见摆动；桥面本身没有断裂，不能倚着这段护栏搬重物。")
    item("white_sign", "医护通道标牌", "bridge", "白底黑箭头指向医护附楼，牌下写着收枪、慢行、不得借医护区重新绕回战场。")
    item("supply_counter", "器材领用台", "shed", "台上夹着领用簿，笔尖尚湿；台下留有放备用护具的位置。", storage=(("top", "台面"), ("shelf", "台下搁层")))
    item("checkout_book", "器材领用簿", "supply_counter", "当前页已登记各队演习枪；担架、安全绳和折叠梯的领取栏仍空，需写用途与领用人。", "top")
    item("spare_gun", "未领用演习短枪", "supply_counter", "黄色演习标记清楚，空弹匣已卸下，保险合上；枪套与背带放在一起。", "shelf")
    item("spare_goggles", "备用护目镜", "supply_counter", "镜片完好，弹力带可以调节，还没有分配领用人。", "shelf")
    item("spare_red_band", "备用红色识别带", "supply_counter", "完整红布带与别针放在一起，没有领用人；佩戴前应先得到红方接纳，拿在手里不等于已经入队。", "top")
    item("spare_blue_band", "备用蓝色识别带", "supply_counter", "完整蓝布带与别针放在一起，没有领用人；佩戴前应先得到蓝方接纳，不能同时冒用两方身份。", "top")
    item("ammo_box", "开盖演习弹药箱", "shed", "箱内两只已装填的通用短枪弹匣各有8发弗里嘉演习弹；黄色封套上写明不得与实弹混用。", storage=(("left", "左侧弹匣槽"), ("right", "右侧弹匣槽")))
    item("spare_mag1", "通用短枪弹匣甲", "ammo_box", "装有8发弗里嘉演习弹，无阵营标记，可装入未领用演习短枪。", "left")
    item("spare_mag2", "通用短枪弹匣乙", "ammo_box", "装有8发弗里嘉演习弹，无阵营标记，卡榫与诺诺的演习短枪相配。", "right")
    item("cage_lock", "器材笼挂锁", "shed", "挂锁扣住笼门插销，锁眼朝外，锁梁完整；器材笼钥匙能开。")
    item("cage_key", "器材笼钥匙", "qin", "钥匙挂着与挂锁同号的金属牌，扣在秦越腰环上，并未交给芬格尔。", "waist")
    item("stretcher", "折叠担架", "cage", "担架折起，帆布与锁脚完好；展开并扣稳后需两名搬运者配合，侧边有固定带。")
    item("ladder", "折叠梯", "cage", "两节梯身折在一起，撑杆完好；展开长度够到普通回廊窗沿，远不足以直接登上钟楼外廊。")
    item("safety_rope", "备用安全绳", "cage", "绳身无磨损，两端有闭合锁扣；需要接到可靠固定环，不能只由人手攥住就称为固定。")
    item("radio_battery_case", "短讯机电池盒", "red_map_desk", "盒内有两枚满电R型短讯电池，盖子打开，盒面写着短讯机专用。", "under", storage=(("cell1", "第一格"), ("cell2", "第二格")))
    item("radio_battery1", "R型短讯电池甲", "radio_battery_case", "满电封签完好，触点与诺诺的故障短讯机相配。", "cell1")
    item("radio_battery2", "R型短讯电池乙", "radio_battery_case", "满电封签完好，是备用电池，并未承诺分给任何人。", "cell2")
    item("medical_case", "医护箱", "aid", "箱盖打开，可见冷敷袋、弹力绷带与检查手套；医护用品不按阵营分配。", storage=(("cold", "冷敷格"), ("wrap", "绷带格"), ("gloves", "检查手套格")))
    item("cold_pack", "未启用冷敷袋", "medical_case", "封口完整，未揉开制冷层；外套布袋可以避免直接贴在皮肤上。", "cold")
    item("bandage", "弹力绷带", "medical_case", "绷带干净卷好，尚未用于固定任何人的脚踝。", "wrap")
    item("gloves", "检查手套", "medical_case", "一副检查手套装在纸套中，纸套未拆。", "gloves")
    item("empty_bed", "医护空床", "aid", "床面空着，制动轮已锁，侧边留着担架靠拢的距离。")
    item("triage_clipboard", "伤情登记夹", "aid", "登记表分成演习中弹与实际受伤两栏；沈澄记在前一栏，林亦舟尚未登记。")
    item("shen_band", "沈澄拆下的红色识别带", "rest", "红布带叠在长椅旁，已脱离沈澄身体，和她退出演习的登记相符。")
    item("water", "休息区饮水杯", "shen", "杯内还有半杯温水，杯沿未破。", "right_hand")
    item("blanket", "保温毯", "rest", "毯子折在长椅空位旁，干燥，可供退出后怕冷的人使用。")
    item("broadcast", "安全广播话筒", "control", "通话键未按，连着只发布赛务与安全通知的扩音线路；不能借它伪造某方已夺旗。")
    item("score_panel", "旗台状态面板", "control", "红蓝两盏指示灯都未亮，停赛时间显示15:45；面板当前不承认任何一方完成最终占领。")
    item("incident_form", "安全事件记录单", "control", "表格尚空，列有时间、地点、证人和采取的安全措施，没有预先认定责任人。")

    initial = WorldInitialState.model_validate({
        "engineVersion": "world-engine-v1", "schemaVersion": 1,
        "worldId": "world_dragon_raja_free_day",
        "protagonistId": "lu",
        "initialTime": {"calendar": "gregorian", "dateTime": "2009-10-17T15:20:00", "instantOrdinal": 0},
        "locations": locations, "items": items, "characters": characters,
    })
    return build_initial_state(initial)


def validate_snapshot(raw: str) -> WorldState:
    state = WorldState.model_validate(parse_json(raw))
    rebuilt = build_initial_state(state.initial)
    if state.model_dump(mode="json") != rebuilt.model_dump(mode="json"):
        raise ValueError("static opening must equal S0 reconstructed from its initial state")
    entities = [*state.initial.locations.values(), *state.initial.items.values(), *state.initial.characters.values()]
    names = [entry.name for entry in entities]
    if len(names) != len(set(names)):
        raise ValueError("ambiguous duplicate display name")
    entity_ids = {entry.id for entry in entities}
    for entry in entities:
        if any(slot.id in entity_ids for slot in entry.slots):
            raise ValueError(f"demo slot ID collides with an entity ID: {entry.id}")
    for person in state.initial.characters.values():
        roots = [task for task in person.tasks.values() if task.parentTaskId is None]
        if not roots or not any(task.status == "pending" for task in roots):
            raise ValueError(f"no active root goal: {person.name}")
        for task in person.tasks.values():
            if task.status == "pending" and task.parentTaskId:
                if person.tasks[task.parentTaskId].status == "achieved":
                    raise ValueError(f"pending task under achieved parent: {task.id}")
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="explicitly rebuild the authored static JSON")
    args = parser.parse_args()
    authored = authored_world()
    text = json.dumps(authored.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    validate_snapshot(text)
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    existing = OUTPUT.read_text(encoding="utf-8")
    actual = validate_snapshot(existing)
    if actual.model_dump(mode="json") != authored.model_dump(mode="json"):
        raise ValueError("snapshot differs from authored source; review before rebuilding")
    print(json.dumps({
        "path": OUTPUT.relative_to(ROOT).as_posix(),
        "format": "WorldState", "schemaVersion": actual.schemaVersion,
        "locations": len(actual.locations), "characters": len(actual.characters),
        "items": len(actual.items),
        "tasks": sum(len(person.tasks) for person in actual.characters.values()),
        "completedTasks": sum(task.status == "achieved" for person in actual.characters.values() for task in person.tasks.values()),
        "fileSha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        "stateDigest": state_digest(actual), "validation": "passed",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
