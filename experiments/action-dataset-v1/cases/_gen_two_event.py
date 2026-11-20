"""One-off authoring aid for cases/05-two-step.jsonl and 06-event.jsonl.

05: two ordered steps inside one room (e.g. look, then act; take, then equip).
06: a committed in-room event (someone's appearance/state changed, an item
    arrived, a task just finished) and the actor's response to it.
"""
import json
from pathlib import Path

S0 = "snapshot:3f65452daf35"

TWO = [
    # (cid, actor, room, slot, present, steps, rationale, goals, facts)
    ("f-001", "zhou", "balcony", None, [], [
        {"action": "观察", "object": "flag_base"}, {"action": "操作", "object": "flag_base"}],
     "task_zhou_latch 要先看清锁扣再动手：旗台底座的释放杆在侧面，他先确认夹住的位置，然后向内压杆",
     ["task_zhou_latch"], ["物品=钟楼旗台底座"]),
    ("f-002", "zhou", "balcony", "slot_door", [], [
        {"action": "检查", "object": "flag_rope"}, {"action": "装备", "object": "flag_rope"}],
     "task_zhou_rope 要求靠近外廊边缘前把安全绳扣好；短绳在腰侧，他先检查锁扣再挂到身上",
     ["task_zhou_rope"], ["随身=旗台短安全绳"]),
    ("f-003", "lu", "shed", "slot_counter", [], [
        {"action": "取得", "object": "spare_goggles"}, {"action": "装备", "object": "spare_goggles"}],
     "task_lu_kit 要拿到能用的护目镜；领用台下的备用护目镜先取出来，再戴上确认弹力带能调",
     ["task_lu_kit"], ["物品=备用护目镜"]),
    ("f-004", "lu", "foyer", None, [], [
        {"action": "观察", "object": "foyer_table"}, {"action": "移动", "object": "foyer_table"}],
     "task_lu_route 要走楼梯就得先腾开通道；长桌斜挡楼梯口，他先看桌腿压住哪一边，再把桌子挪开",
     ["task_lu_route"], ["物品=门厅翻倒长桌"]),
    ("f-005", "lin", "west_arcade", "slot_pillar3", [], [
        {"action": "观察", "object": "lin_gun"}, {"action": "取得", "object": "lin_gun"}],
     "task_lin_safe 要把枪移出搬运路线；枪在一臂之外，先看清位置再伸手把它够过来",
     ["task_lin_safe"], ["物品=林亦舟放下的演习枪"]),
    ("f-006", "su", "east_arcade", None, [], [
        {"action": "检查", "object": "su_magazine"}, {"action": "装备", "object": "su_magazine"}],
     "task_su_reload 要先确认备用弹匣属于自己的再换；她先查胶带上的名字，然后把它换上",
     ["task_su_reload"], ["物品=苏茜的备用弹匣"]),
    ("f-007", "tang", "yard", "slot_south_cover", [], [
        {"action": "观察", "object": "flower_box"}, {"action": "移动", "object": None}],
     "task_tang_fallback 要留退路；他先看清花槽内侧能蹲下，再往那个方向挪过去",
     ["task_tang_fallback"], ["物品=南端石花槽"]),
    ("f-008", "tang", "yard", "slot_east_cover", [], [
        {"action": "装备", "object": "tang_magazine"}, {"action": "观察", "object": None}],
     "task_tang_ammo 要求换好弹匣再探身；他先把满弹匣装上，然后才从长椅边缘看一眼",
     ["task_tang_ammo"], ["随身=唐骁的满弹匣"]),
    ("f-009", "chu", "foyer", "slot_stairs", [], [
        {"action": "观察", "object": "foyer_table"}, {"action": "移动", "object": "foyer_table"}],
     "task_chu_hatch 要下到地下门；长桌挡住楼梯口，先看清桌腿再腾开能过担架的位置",
     ["task_chu_hatch"], ["物品=门厅翻倒长桌"]),
    ("f-010", "chu", "landing", None, [], [
        {"action": "查看", "object": "blue_radio"}, {"action": "联络", "object": "blue_radio"}],
     "task_chu_lin 要先看全收到的消息再回话；他查完记录便用蓝方短讯机追问林亦舟伤情",
     ["task_chu_lin"], ["随身=楚子航的蓝方短讯机"]),
    ("f-011", "nono", "shed", "slot_counter", [], [
        {"action": "观察", "object": "checkout_book"}, {"action": "记录", "object": "checkout_book"}],
     "task_nono_wounded 要担架就得按领用簿登记；她先看清要填哪几栏，再把用途和领用人写上",
     ["task_nono_wounded"], ["物品=器材领用簿"]),
    ("f-012", "manstein", "control", None, [], [
        {"action": "查看", "object": "score_panel"}, {"action": "记录", "object": "incident_form"}],
     "task_manstein_log 要按面板状态写记录；他先看两盏旗台灯与停赛时间，再把安全事项写进记录单",
     ["task_manstein_log"], ["物品=旗台状态面板", "物品=安全事件记录单"]),
    ("f-013", "su", "west_arcade", "slot_pillar3", ["lin"], [
        {"action": "核实", "object": "lin"}, {"action": "搀扶", "object": "lin"}],
     "task_su_lin 要先核实再动手；她确认是实际扭伤后，把林亦舟扶到柱后更安全的位置",
     ["task_su_lin"], ["在场=林亦舟"]),
    ("f-014", "caesar", "shed", "slot_cage", ["qin"], [
        {"action": "请求", "object": "qin"}, {"action": "观察", "object": "cage_lock"}],
     "task_caesar_win 要折叠梯就得先开笼；他向秦越开口后，先看挂锁怎么被打开，避免事后说不清",
     ["task_caesar_win"], ["在场=秦越", "物品=器材笼挂锁"]),
    ("f-015", "caesar", "balcony", "slot_flag_base", ["tang"], [
        {"action": "交接", "object": "red_flag"}, {"action": "观察", "object": "flag_base"}],
     "task_caesar_flag 要先交旗再核对底座；把红方旗交给唐骁后，他看清锁扣是否还卡着白旗",
     ["task_caesar_flag"], ["随身=红方信号旗", "物品=钟楼旗台底座"]),
    ("f-016", "lu", "cage", None, [], [
        {"action": "观察", "object": "stretcher"}, {"action": "取得", "object": "stretcher"}],
     "task_lu_match 要做一次能被确认的行动；先看担架锁脚完好，再把它从笼里拖出来",
     ["task_lu_match"], ["物品=折叠担架"]),
    ("f-017", "nono", "red_rally", None, [], [
        {"action": "取得", "object": "radio_battery1"}, {"action": "装备", "object": "radio_battery1"}],
     "task_nono_battery 要恢复短讯机；她先从桌下电池盒取出满电电池，再装进故障短讯机",
     ["task_nono_battery"], ["物品=R型短讯电池甲", "随身=诺诺的故障短讯机"]),
    ("f-018", "zhou", "top", None, [], [
        {"action": "观察", "object": "blue_flag"}, {"action": "取得", "object": "blue_flag"}],
     "task_zhou_guard 要把蓝方旗带到旗台；先确认旗和杆完好，再把它拿起来",
     ["task_zhou_guard"], ["物品=蓝方信号旗"]),
    ("f-019", "tang", "west_arcade", None, ["lin"], [
        {"action": "观察", "object": "lin"}, {"action": "支援", "object": "lin"}],
     "task_tang_pause 要先判断再停火；他看清林亦舟确实站不起来，便过去搭手把人挪到廊柱后",
     ["task_tang_pause"], ["在场=林亦舟"]),
    ("f-020", "lu", "bridge", "slot_east_end", [], [
        {"action": "检查", "object": "bridge_rail"}, {"action": "后退", "object": None}],
     "task_lu_route 要把小桥当候选或否掉；他先检查松动护栏，看清后立刻退回桥头",
     ["task_lu_route"], ["物品=小桥松动护栏"]),
    ("f-021", "lu", "hatch", None, [], [
        {"action": "取得", "object": "flashlight"}, {"action": "钻入", "object": None}],
     "task_lu_route 要走地下通道先得有灯；他取下绝缘手电，然后低头钻进检修口",
     ["task_lu_route"], ["物品=绝缘手电"]),
    ("f-022", "su", "bridge", "slot_west_end", [], [
        {"action": "检查", "object": "bridge_rail"}, {"action": "后退", "object": None}],
     "task_su_report 要报告护栏状况；她看清螺母退松后先退回桥头，避免自己踩在松动段上",
     ["task_su_report"], ["物品=小桥松动护栏"]),
    ("f-023", "manstein", "bridge", "slot_west_end", [], [
        {"action": "观察", "object": "bridge_rail"}, {"action": "后退", "object": None}],
     "task_manstein_order 要按安全规则结束演习；他先看清松动护栏，再退回桥头，不让学生踩在隐患上",
     ["task_manstein_order"], ["物品=小桥松动护栏"]),
    ("f-024", "tang", "red_rally", None, [], [
        {"action": "观察", "object": "red_map_desk"}, {"action": "观察", "object": "caesar_map"}],
     "task_tang_report 要报可确认的位置；他先看清桌面，再对着平面图核对自己看到的那扇窗",
     ["task_tang_report"], ["物品=红方地图桌", "物品=凯撒的庭院平面图"]),
    ("f-025", "lu", "lane", "slot_entry", [], [
        {"action": "查看", "object": "map"}, {"action": "移动", "object": None}],
     "task_lu_route 要在三条线里选一条；他看完路线图，便按图上标注往选定的方向走",
     ["task_lu_route"], ["物品=赛区路线图"]),
    ("f-026", "su", "east_arcade", "slot_window", [], [
        {"action": "观察", "object": "canvas_blind"}, {"action": "操作", "object": "canvas_blind"}],
     "task_su_watch 要在藏身与观察之间取舍；她先看帘子遮住多少，再决定拉下还是留着",
     ["task_su_watch"], ["物品=东回廊遮光帘"]),
    ("f-027", "chu", "foyer", "slot_front_door", [], [
        {"action": "观察", "object": "hatch_door"}, {"action": "后退", "object": None}],
     "task_chu_hatch 要判断地下门能否从外侧打开；他看清门闩插在槽里，便退回门厅另想办法",
     ["task_chu_hatch"], ["物品=钟楼地下检修门"]),
    ("f-028", "caesar", "bridge", "slot_west_end", [], [
        {"action": "观察", "object": "white_sign"}, {"action": "移动", "object": None}],
     "task_caesar_bridge 要记下医护线限制再回队；他看完标牌便转身往回走",
     ["task_caesar_bridge"], ["物品=医护通道标牌"]),
    ("f-029", "nono", "west_arcade", "slot_pillar3", ["lin"], [
        {"action": "检查", "object": "lin"}, {"action": "告知", "object": "lin"}],
     "task_nono_wounded 要先判断再表态；她看清是实际扭伤后，告诉林亦舟会去叫人来抬",
     ["task_nono_wounded"], ["在场=林亦舟"]),
    ("f-030", "lin", "west_arcade", "slot_tower_door", ["su"], [
        {"action": "请求", "object": "su"}, {"action": "取得", "object": "lin_gun"}],
     "task_lin_safe 要把枪移出搬运路线；他先请苏茜把枪递过来，自己再把枪收到手边",
     ["task_lin_safe"], ["在场=苏茜", "物品=林亦舟放下的演习枪"]),
    ("f-031", "manstein", "west_arcade", "slot_tower_door", ["lin"], [
        {"action": "核实", "object": "lin"}, {"action": "告知", "object": "lin"}],
     "task_manstein_injury 要核实后给出处理；他确认是实际扭伤，便告诉林亦舟必须走白线撤出",
     ["task_manstein_injury"], ["在场=林亦舟"]),
    ("f-032", "zhou", "balcony", "slot_flag_base", [], [
        {"action": "观察", "object": "white_flag"}, {"action": "观察", "object": "flag_base"}],
     "task_zhou_guard 要先看清白旗怎么卡住、底座哪侧能动手；两处都看清才敢去碰",
     ["task_zhou_guard"], ["物品=中立白旗", "物品=钟楼旗台底座"]),
    ("f-033", "tang", "fountain", "slot_north_gap", [], [
        {"action": "观察", "object": None}, {"action": "钻入", "object": None}],
     "task_tang_push 要从缺口换位；他先看清缺口外有没有射界，再低身钻出去",
     ["task_tang_push"], ["地点=停水喷泉池"]),
    ("f-034", "lu", "shed", "slot_cage", ["qin"], [
        {"action": "请求", "object": "qin"}, {"action": "取得", "object": "spare_goggles"}],
     "task_lu_kit 要按规矩领装备；他先请秦越登记，再从台下取出备用护目镜",
     ["task_lu_kit"], ["在场=秦越", "物品=备用护目镜"]),
    ("f-035", "su", "east_arcade", "slot_north", [], [
        {"action": "观察", "object": "su_magazine"}, {"action": "移动", "object": "rifle_su"}],
     "task_su_exit 要带走能带走的东西；她先确认弹匣留在窗内，再把长枪一并收回",
     ["task_su_exit"], ["物品=苏茜的备用弹匣", "随身=苏茜的演习长枪"]),
    ("f-036", "nono", "lane", "slot_wall", [], [
        {"action": "查看", "object": "rules"}, {"action": "告知", "object": "lu"}],
     "task_nono_lu 要先按规则说明底线；她看完规则牌上的白线与停赛时间，再把三条路线讲给路明非",
     ["task_nono_lu"], ["物品=演习规则牌", "在场=路明非"]),
    ("f-037", "chu", "landing", "slot_window", ["su"], [
        {"action": "询问", "object": "su"}, {"action": "观察", "object": None}],
     "task_chu_su 要先问清射界再定防线；他问过苏茜后，从窗口复核她能覆盖的那一段",
     ["task_chu_su"], ["在场=苏茜"]),
    ("f-038", "caesar", "red_rally", None, ["tang"], [
        {"action": "提问", "object": "tang"}, {"action": "观察", "object": "caesar_map"}],
     "task_caesar_tang 要先听报告再对照地图；他问完唐骁，便把窗口位置标到平面图上",
     ["task_caesar_tang"], ["在场=唐骁", "物品=凯撒的庭院平面图"]),
    ("f-039", "manstein", "landing", "slot_window", [], [
        {"action": "观察", "object": None}, {"action": "记录", "object": None}],
     "task_manstein_log 要先看清现场再记录；他从平台窗口确认双方站位，然后把情况记下来",
     ["task_manstein_log"], ["地点=钟楼二层平台"]),
    ("f-040", "lin", "west_arcade", "slot_pillar3", ["qin"], [
        {"action": "请求", "object": "qin"}, {"action": "移动", "object": "lin_gun"}],
     "task_lin_safe 要清开搬运路线；他请秦越帮忙，把枪挪到廊柱内侧不挡担架的位置",
     ["task_lin_safe"], ["在场=秦越", "物品=林亦舟放下的演习枪"]),
]

EVENT = [
    # (cid, actor, room, slot, transforms-extra, steps, rationale, goals, facts)
    ("g-001", "chu", "landing", "slot_window", [{"op": "move", "entityId": "lin", "containerId": "landing", "slotId": None}],
     [{"action": "检查", "object": "lin"}],
     "刚才林亦舟被扶到平台上，task_chu_lin 要查明扭伤是否妨碍行走；人已经在眼前，先检查",
     ["task_chu_lin"], ["刚才=林亦舟移动到钟楼二层平台"]),
    ("g-002", "su", "east_arcade", "slot_window", [
        {"op": "move", "entityId": "lin", "containerId": "east_arcade", "slotId": None},
        {"op": "appearance", "entityId": "lin", "text": "脚踝肿到鞋帮外，站起时明显吃不住力"}],
     [{"action": "检查", "object": "lin"}],
     "刚才林亦舟被带到低窗旁、脚踝肿得更明显，task_su_lin 要核实是否真实伤情；先看清伤处",
     ["task_su_lin"], ["刚才=林亦舟移动到东回廊", "刚才=脚踝肿到鞋帮外"]),
    ("g-003", "lu", "lane", "slot_wall", [
        {"op": "move", "entityId": "tang", "containerId": "lane", "slotId": None}],
     [{"action": "后退", "object": None}],
     "刚才红方推进队员唐骁进了服务巷，他身上没有识别带也没答应任何一方；先退到低墙后避开",
     ["task_lu_match"], ["刚才=唐骁移动到西侧服务巷"]),
    ("g-004", "nono", "lane", "slot_entry", [
        {"op": "appearance", "entityId": "lu", "text": "袖口被弹着石墙蹭破，手背有红痕"}],
     [{"action": "检查", "object": "lu"}],
     "刚才路明非的手背蹭出红痕，task_nono_lu 要讲清路线也得先确认他能不能继续走；先看伤处",
     ["task_nono_lu"], ["刚才=路明非的外观出现变化"]),
    ("g-005", "caesar", "red_rally", None, [
        {"op": "appearance", "entityId": "radio_caesar", "text": "频道指示灯亮起，显示一条未读回报"}],
     [{"action": "查看", "object": "radio_caesar"}],
     "刚才红方短讯机指示灯亮起、有未读回报，task_caesar_contact 要恢复联络；先读出这条回报",
     ["task_caesar_contact"], ["刚才=红方短讯机外观出现变化"]),
    ("g-006", "zhou", "balcony", None, [
        {"op": "move", "entityId": "chu", "containerId": "balcony", "slotId": None}],
     [{"action": "告知", "object": "chu"}],
     "刚才楚子航到了旗台外廊，task_zhou_warn 要把锁扣卡滞和未固定安全绳报告给他；先当面说",
     ["task_zhou_warn"], ["刚才=楚子航移动到钟楼旗台外廊"]),
    ("g-007", "manstein", "control", None, [
        {"op": "sanity", "entityId": "manstein", "value": 70}],
     [{"action": "记录", "object": "incident_form"}],
     "刚才他自己的理智从84降到70，说明这轮观察让他不安；task_manstein_log 要求把违规与战术失败分开记，先写下来",
     ["task_manstein_log"], ["刚才=曼施坦因的理智变为70"]),
    ("g-008", "tang", "yard", "slot_east_cover", [
        {"op": "appearance", "entityId": "bench_cover", "text": "椅背被一发演习弹打中，木屑溅到地上"}],
     [{"action": "观察", "object": "bench_cover"}],
     "刚才长椅被打中、木屑落在脚边，说明对面已经注意到这个掩体；task_tang_fallback 要先判断还能不能留在这里",
     ["task_tang_fallback"], ["刚才=倒放长椅的外观出现变化"]),
    ("g-009", "lin", "west_arcade", None, [
        {"op": "appearance", "entityId": "lin", "text": "脚踝的肿处已经发亮，鞋带被他自己松开"}],
     [{"action": "观察", "object": "lin_radio"}],
     "刚才脚踝肿得发亮，他够不到别人的频道，只能用短讯机再补充一句伤情；先看设备还剩多少电",
     ["task_lin_call"], ["刚才=林亦舟的外观出现变化"]),
    ("g-010", "su", "east_arcade", "slot_north", [
        {"op": "appearance", "entityId": "canvas_blind", "text": "帆布被风掀起一角，露出窗内轮廓"}],
     [{"action": "操作", "object": "canvas_blind"}],
     "刚才遮光帘被风掀起、窗内轮廓露了出去；task_su_watch 要保持信息可信，先把帘子按回原位",
     ["task_su_watch"], ["刚才=东回廊遮光帘的外观出现变化"]),
    ("g-011", "chu", "foyer", "slot_front_door", [
        {"op": "appearance", "entityId": "hatch_door", "text": "门闩被人从内侧敲了一下，铁门发出回声"}],
     [{"action": "检查", "object": "hatch_door"}],
     "刚才地下门闩被从内侧敲过，说明通道里有人；task_chu_hatch 要先检查门闩与门框是否还完整",
     ["task_chu_hatch"], ["刚才=钟楼地下检修门的外观出现变化"]),
    ("g-012", "lu", "lane", "slot_entry", [
        {"op": "appearance", "entityId": "rules", "text": "规则牌上新贴了一张白纸，写着停赛时间可能提前"}],
     [{"action": "查看", "object": "rules"}],
     "刚才规则牌上多了一张白纸，写着停赛时间可能提前；task_lu_route 的路线选择要按新时间重算，先看清",
     ["task_lu_route"], ["刚才=演习规则牌的外观出现变化"]),
    ("g-013", "nono", "lane", "slot_wall", [
        {"op": "achieveTask", "ownerId": "lu", "taskId": "task_lu_goggles"}],
     [{"action": "观察", "object": "lu"}],
     "刚才路明非把护目镜戴好（他的 task_lu_goggles 已完成），说明他已经准备进交火区；先观察他下一步意图",
     ["task_nono_lu"], ["刚才=路明非的任务task_lu_goggles已完成"]),
    ("g-014", "caesar", "red_rally", None, [
        {"op": "move", "entityId": "radio_battery1", "containerId": "caesar", "slotId": None},
        {"op": "appearance", "entityId": "radio_caesar", "text": "电量图标变满"}],
     [{"action": "联络", "object": "radio_caesar"}],
     "刚才电池装进短讯机、电量图标变满，task_caesar_contact 就是恢复与诺诺的联络；先发一次呼唤",
     ["task_caesar_contact"], ["刚才=R型短讯电池甲移动到凯撒身上", "刚才=红方短讯机的外观出现变化"]),
    ("g-015", "zhou", "balcony", None, [
        {"op": "appearance", "entityId": "flag_rope", "text": "一端已经扣在旗台固定环上"}],
     [{"action": "装备", "object": "flag_rope"}],
     "刚才安全绳一端已扣上固定环，task_zhou_rope 就剩把另一端扣到自己腰带上；先穿好",
     ["task_zhou_rope"], ["刚才=旗台短安全绳的外观出现变化"]),
    ("g-016", "manstein", "bridge", "slot_east_end", [
        {"op": "appearance", "entityId": "bridge_rail", "text": "中段护栏又向外歪了一指，螺母露出更多"}],
     [{"action": "记录", "object": None}],
     "刚才护栏又外歪、螺母露出更多，属于实际安全隐患；task_manstein_log 要求把安全违规与战术失败分开记录，先记下",
     ["task_manstein_log"], ["刚才=小桥松动护栏的外观出现变化"]),
    ("g-017", "tang", "yard", "slot_south_cover", [
        {"op": "appearance", "entityId": "flower_box", "text": "石沿被演习弹打出一个小缺口"}],
     [{"action": "观察", "object": "flower_box"}],
     "刚才花槽石沿被打出缺口，task_tang_fallback 要判断这里还能不能当退路；先看缺口对面的射线",
     ["task_tang_fallback"], ["刚才=南端石花槽的外观出现变化"]),
    ("g-018", "su", "west_arcade", "slot_tower_door", [
        {"op": "move", "entityId": "lin", "containerId": "west_arcade", "slotId": "slot_pillar3"},
        {"op": "achieveTask", "ownerId": "lin", "taskId": "task_lin_sent"}],
     [{"action": "检查", "object": "lin"}],
     "刚才林亦舟已经被挪到第三根廊柱后（他的求助任务已完成），task_su_lin 要在必要时配合停火；先检查伤处",
     ["task_su_lin"], ["刚才=林亦舟移动到第三根廊柱后", "刚才=林亦舟的任务task_lin_sent已完成"]),
    ("g-019", "lu", "shed", "slot_counter", [
        {"op": "appearance", "entityId": "spare_goggles", "text": "弹力带被上一位领用人调短了"}],
     [{"action": "检查", "object": "spare_goggles"}],
     "刚才备用护目镜的弹力带被别人调短，task_lu_kit 要拿到可用的护目镜；先检查能不能调到合适",
     ["task_lu_kit"], ["刚才=备用护目镜的外观出现变化"]),
    ("g-020", "chu", "landing", "slot_upper_stairs", [
        {"op": "appearance", "entityId": "blue_radio", "text": "屏幕跳出一条新消息：西回廊有人动不了"}],
     [{"action": "查看", "object": "blue_radio"}],
     "刚才蓝方短讯机跳出新消息说西回廊有人动不了，task_chu_lin 就在这一步；先把消息读完",
     ["task_chu_lin"], ["刚才=楚子航的蓝方短讯机的外观出现变化"]),
    ("g-021", "caesar", "yard", "slot_east_cover", [
        {"op": "appearance", "entityId": "tang", "text": "肩头多了一道演习弹红痕，弹匣袋空了"}],
     [{"action": "检查", "object": "tang"}],
     "刚才唐骁肩上多了红痕、弹匣袋空了，task_caesar_tang 要他报告再定路线；先看清他是不是被命中",
     ["task_caesar_tang"], ["刚才=唐骁的外观出现变化"]),
    ("g-022", "nono", "west_arcade", "slot_pillar3", [
        {"op": "appearance", "entityId": "lin", "text": "把枪推到离自己更远的地面"}],
     [{"action": "检查", "object": "lin"}],
     "刚才林亦舟把枪推远，说明他不想被当成威胁；task_nono_wounded 要先确认他的伤是不是真的",
     ["task_nono_wounded"], ["刚才=林亦舟的外观出现变化"]),
    ("g-023", "manstein", "west_arcade", "slot_tower_door", [
        {"op": "appearance", "entityId": "lin", "text": "自己把伤脚抬到石栏上，明显吃不住力"}],
     [{"action": "核实", "object": "lin"}],
     "刚才林亦舟把伤脚抬上石栏、站不起来，task_manstein_injury 要核实后决定是否广播局部停火；先当面核实",
     ["task_manstein_injury"], ["刚才=林亦舟的外观出现变化"]),
    ("g-024", "zhou", "bell_room", None, [
        {"op": "appearance", "entityId": "maintenance_chart", "text": "图上多了一行铅笔字：锁扣需两人配合"}],
     [{"action": "查看", "object": "maintenance_chart"}],
     "刚才检修图上多了一行铅笔字说锁扣要两人配合，task_zhou_latch 要弄清释放方向；先看清新写的部分",
     ["task_zhou_latch"], ["刚才=旗台机械检修图的外观出现变化"]),
    ("g-025", "tang", "west_arcade", "slot_pillar3", [
        {"op": "appearance", "entityId": "broken_blue_band", "text": "断口被踩进泥里，旁边多了一串拖拽痕"}],
     [{"action": "观察", "object": "broken_blue_band"}],
     "刚才蓝布带断口被踩进泥里、旁边有拖拽痕，task_tang_pause 要先判断这里是否发生过撤离；先看清痕迹方向",
     ["task_tang_pause"], ["刚才=折断的蓝布带的外观出现变化"]),
    ("g-026", "su", "east_arcade", "slot_window", [
        {"op": "appearance", "entityId": "su_magazine", "text": "胶带松了，名字露出”茜”字"}],
     [{"action": "检查", "object": "su_magazine"}],
     "刚才备用弹匣的胶带松了、露出名字，task_su_reload 要求确认弹匣属于自己；先核对",
     ["task_su_reload"], ["刚才=苏茜的备用弹匣的外观出现变化"]),
    ("g-027", "lu", "foyer", "slot_stairs", [
        {"op": "appearance", "entityId": "foyer_table", "text": "桌腿被人挪过，空隙变大了一点"}],
     [{"action": "观察", "object": "foyer_table"}],
     "刚才长桌被挪过、空隙变大，task_lu_route 要走这条楼梯得先确认能不能过；先看清空隙",
     ["task_lu_route"], ["刚才=门厅翻倒长桌的外观出现变化"]),
    ("g-028", "lin", "west_arcade", "slot_tower_door", [
        {"op": "achieveTask", "ownerId": "lin", "taskId": "task_lin_safe"}],
     [{"action": "观察", "object": "lin_radio"}],
     "刚才他把枪挪出了搬运路线（task_lin_safe 已完成），剩下的 task_lin_call 需要再说清伤情；先看短讯机",
     ["task_lin_call"], ["刚才=林亦舟的任务task_lin_safe已完成"]),
    ("g-029", "caesar", "balcony", "slot_door", [
        {"op": "appearance", "entityId": "white_flag", "text": "旗杆被风推得晃了一下，锁扣仍卡着"}],
     [{"action": "观察", "object": "white_flag"}],
     "刚才白旗被风推得晃动但锁扣仍卡着，task_caesar_flag 要知道旗台现在算什么状态；先看清",
     ["task_caesar_flag"], ["刚才=中立白旗的外观出现变化"]),
    ("g-030", "nono", "shed", "slot_cage", [
        {"op": "appearance", "entityId": "cage_lock", "text": "锁梁上多了一道新划痕"}],
     [{"action": "观察", "object": "cage_lock"}],
     "刚才笼锁上多了新划痕，task_nono_squad 需要器材却拿不到；先看清是被人试过还是钥匙不合",
     ["task_nono_squad"], ["刚才=器材笼挂锁的外观出现变化"]),
    ("g-031", "chu", "balcony", "slot_flag_base", [
        {"op": "appearance", "entityId": "flag_base", "text": "底座锁扣被压出一道新痕"}],
     [{"action": "观察", "object": "flag_base"}],
     "刚才底座锁扣出现新痕，说明有人动过旗；task_chu_flag 要判断红方是否已经试过，先看清",
     ["task_chu_flag"], ["刚才=钟楼旗台底座的外观出现变化"]),
    ("g-032", "su", "east_arcade", "slot_north", [
        {"op": "appearance", "entityId": "window_pad", "text": "软垫被压出一个新坑，位置偏了一掌"}],
     [{"action": "观察", "object": "window_pad"}],
     "刚才软垫位置被挪动，说明有人在这里架过枪；task_su_watch 要保持信息可信，先看清是不是蓝方自己的位置",
     ["task_su_watch"], ["刚才=低窗软垫的外观出现变化"]),
    ("g-033", "tang", "red_rally", None, [
        {"op": "appearance", "entityId": "red_flag", "text": "旗杆底端被擦亮，接口露出金属色"}],
     [{"action": "观察", "object": "red_flag"}],
     "刚才红方旗底端被擦亮，说明有人检查过接口；task_tang_report 要报能确认的事实，先看清旗的状态",
     ["task_tang_report"], ["刚才=红方信号旗的外观出现变化"]),
    ("g-034", "zhou", "top", "slot_south_window", [
        {"op": "appearance", "entityId": "blue_flag", "text": "短杆底端被擦净，接口露出来"}],
     [{"action": "观察", "object": "blue_flag"}],
     "刚才蓝方旗短杆被擦净，说明有人准备安装；task_zhou_guard 要守住并安全操作信号旗，先确认旗可用",
     ["task_zhou_guard"], ["刚才=蓝方信号旗的外观出现变化"]),
    ("g-035", "manstein", "control", None, [
        {"op": "appearance", "entityId": "score_panel", "text": "蓝方指示灯闪了一下又灭"}],
     [{"action": "查看", "object": "score_panel"}],
     "刚才蓝方指示灯闪了一下又灭，说明旗台状态可能变化；task_manstein_clock 要核对最终状态，先看清面板",
     ["task_manstein_clock"], ["刚才=旗台状态面板的外观出现变化"]),
    ("g-036", "lu", "shed", "slot_counter", [
        {"op": "move", "entityId": "spare_gun", "containerId": "supply_counter", "slotId": "slot_top"}],
     [{"action": "观察", "object": "spare_gun"}],
     "刚才有人把未领用短枪放到了台面上，task_lu_kit 要拿到可用装备；先看清它有没有弹匣",
     ["task_lu_kit"], ["刚才=未领用演习短枪移动到器材领用台台面"]),
    ("g-037", "nono", "hatch", None, [
        {"op": "appearance", "entityId": "hatch_cover", "text": "盖沿被撬开一指，露出下面的短梯"}],
     [{"action": "观察", "object": "hatch_cover"}],
     "刚才检修盖被撬开一指、露出短梯，task_nono_squad 要给红方找路线；先看清入口能否带枪通过",
     ["task_nono_squad"], ["刚才=服务巷检修盖的外观出现变化"]),
    ("g-038", "lin", "west_arcade", "slot_pillar3", [
        {"op": "appearance", "entityId": "lin_gun", "text": "枪被推到廊柱内侧，离他更远"}],
     [{"action": "观察", "object": "lin_gun"}],
     "刚才枪被推到廊柱内侧，task_lin_safe 要说清它的位置；先确认它不会挡到担架路线",
     ["task_lin_safe"], ["刚才=林亦舟放下的演习枪的外观出现变化"]),
    ("g-039", "chu", "top", "slot_south_window", [
        {"op": "move", "entityId": "zhou", "containerId": "top", "slotId": None},
        {"op": "appearance", "entityId": "zhou", "text": "手一直扶着旗杆，没有松开的迹象"}],
     [{"action": "提问", "object": "zhou"}],
     "刚才周映带着旗上了顶层，task_chu_flag 要在红方进顶层前安排持守；先问清他打算怎么守",
     ["task_chu_flag"], ["刚才=周映移动到钟楼顶层", "刚才=周映的外观出现变化"]),
    ("g-040", "su", "bridge", "slot_east_end", [
        {"op": "move", "entityId": "tang", "containerId": "bridge", "slotId": None}],
     [{"action": "观察", "object": "tang"}],
     "刚才唐骁上了桥、离她的射击线更近，task_su_watch 要保持信息可信；先看清他是否带枪过去",
     ["task_su_watch"], ["刚才=唐骁移动到跨溪小桥"]),
]


def build(table, extra_key, out):
    world = json.loads(Path("../../data/worlds/dragon-raja-free-day.world.json").read_text(encoding="utf-8"))
    cases = []
    for row in table:
        cid, actor, room, slot = row[0], row[1], row[2], row[3]
        if extra_key == "present":
            present, steps, rationale, goals, facts = row[4], row[5], row[6], row[7], row[8]
            extra = []
        else:
            extra, steps, rationale, goals, facts = row[4], row[5], row[6], row[7], row[8]
            present = []
        transforms = []
        home = world["characters"][actor]["position"]
        if home["containerId"] != room or (slot is not None and home.get("slotId") != slot):
            transforms.append({"op": "move", "entityId": actor, "containerId": room, "slotId": slot})
        for other in present:
            transforms.append({"op": "move", "entityId": other, "containerId": room, "slotId": None})
        transforms.extend(extra)
        cases.append(
            dict(
                caseId=cid,
                base=S0,
                actor=actor,
                transforms=transforms,
                steps=steps,
                rationale=rationale,
                judgmentBasis=["goal", "event"] if extra_key == "extra" else ["goal", "scene"],
                goalsReferenced=goals,
                facts=facts,
                seed=20261111,
            )
        )
    with Path(__file__).with_name(out).open("w", encoding="utf-8") as handle:
        for entry in cases:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(out, len(cases))


if __name__ == "__main__":
    build(TWO, "present", "05-two-step.jsonl")
    build(EVENT, "extra", "06-event.jsonl")
