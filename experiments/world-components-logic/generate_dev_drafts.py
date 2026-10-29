#!/usr/bin/env python3
"""Rebuild D-only L3 development drafts; this does not create gold labels.

All scenario prose below was newly authored for this preparation batch. The
generator only builds frozen experiment inputs and separate review drafts; it
does not implement a game model, adjudicate semantics, or read B/C material.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

VERSION = "d-l3-dev-drafts-r1"
DATE = "2026-10-29"
BASE = Path(__file__).resolve().parent
STAGE_CUTS = {
    "D02": "actor_opportunity_before_action_confirmation",
    "D03": "source_frozen_before_current_targets_confirmation",
    "D04": "admission_decided_before_reaction_confirmation",
    "D05": "group_close_guard_before_joint_results",
}


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def actor(name: str, place: str, task: str, personality: str,
          status: str = "pending") -> dict:
    return {"name": name, "place": place, "task": task,
            "personality": personality, "status": status}


def world(outer: str, room_a: str, room_b: str, objects: list[tuple[str, str]],
          people: list[dict], time: str = "2031-04-18T10:20:00+08:00") -> dict:
    """Small experimental representation; not a new public world protocol."""
    return {
        "time": time,
        "places": [
            {"id": "loc_outer", "name": outer, "parentId": None},
            {"id": "loc_a", "name": room_a, "parentId": "loc_outer"},
            {"id": "loc_b", "name": room_b, "parentId": "loc_outer"},
        ],
        "items": [
            {"id": f"item_{i}", "name": name,
             "position": {"containerId": place, "slot": "可见位置"}}
            for i, (name, place) in enumerate(objects, 1)
        ],
        "characters": [
            {"id": f"p{i}", "name": f"{person['name']}（{'甲乙丙丁戊己'[i - 1]}）",
             "position": {"containerId": person["place"], "slot": "地面"},
             "appearance": "衣物完整，双手可自由活动，无已知伤势。",
             "tasks": [{"id": f"task_p{i}", "text": person["task"],
                        "status": person["status"], "parentId": None}],
             "personality": [person["personality"]], "sanity": 65}
            for i, person in enumerate(people, 1)
        ],
    }


def member(person: str, text: str) -> dict:
    return {"memberId": person, "actionText": text}


def roll(source: str, target: str, value: int, *, eligible: bool = True,
         suffix: str = "1") -> dict:
    passed = value >= 11
    return {"sourceId": source, "targetId": target,
            "rollId": f"roll_{source}_{target}_{suffix}",
            "ruleVersion": "reaction-d20-v1", "value": value,
            "threshold": 11, "passed": passed, "eligible": eligible,
            "admitted": passed and eligible}


def target(source: str, *targets: str) -> dict:
    return {"sourceId": source, "targetIds": list(targets)}


def build() -> tuple[list[dict], list[dict], dict[str, str]]:
    inputs: list[dict] = []
    reviews: list[dict] = []
    origins: dict[str, str] = {}

    def add(task: str, number: int, scene: str, payload: dict, tags: list[str],
            expected: dict, *, variant: str | None = None) -> None:
        anchor = f"dev-{task.lower()}-{number:02d}"
        case_id = anchor if variant is None else f"{anchor}-{variant}"
        group = f"d-origin-{task.lower()}-{number:02d}"
        origins[group] = scene
        inputs.append({
            "caseId": case_id, "sourceGroup": group,
            "anchorCase": variant is None,
            "derivedFrom": None if variant is None else anchor,
            "split": "development", "purpose": "exploratory_draft",
            "task": task, "stageCut": STAGE_CUTS[task], "input": payload,
        })
        reviews.append({
            "caseId": case_id, "sourceGroup": group,
            "coverageTags": tags, "draftExpected": expected,
            "humanReview": "pending", "author": "assistant",
            "sourceNote": scene,
            "reviewCaution": "AI起草的可接受约束，非人工真值；可修改并需记录修改依据。",
        })

    # D02: ten independently proposed anchor scenarios, not renamed copies.
    action_scenes = [
        ("展馆闭馆前，主角需推开已解锁侧门进入值班室交接钥匙。",
         world("旧城展馆", "侧廊，侧门已解锁且可推开", "值班室", [("交接钥匙", "p1"), ("侧门", "loc_a")], [
             actor("程青", "loc_a", "将交接钥匙送至值班室。", "守时，愿意按可行指令办事。"),
             actor("闻雪", "loc_b", "等待接收钥匙。", "耐心核对交接。"),
             actor("韩远", "loc_a", "核对墙上的闭馆清单。", "专注书面核查。")]),
         "p1", "pending", "推开侧门，进入值班室交钥匙。", "act",
         ["可以尝试推门并交接，但描述为行动意图，不能预先宣布交接成功。"],
         ["把钥匙交接已完成当作输入中自带事实。"], ["executable_input"]),
        ("渡口的主角要在开船前敲响身旁铜铃，船长仍在对岸等信号。",
         world("沙洲渡口", "上船台，铜铃在手边", "对岸系泊台", [("铜铃", "loc_a"), ("铃锤", "p1")], [
             actor("罗舟", "loc_a", "通知对岸的船长可以开始靠岸。", "谨慎且愿意主动沟通。"),
             actor("许栖", "loc_b", "听见明确通知后再准备靠岸。", "不凭猜测开船。"),
             actor("孔宁", "loc_a", "守住乘客排队边线。", "秩序感强。")]),
         "p1", "pending", "用铃锤敲响铜铃通知船长。", "act",
         ["生成敲铃或发出约定信号的尝试，不能提前移动对岸人物。"],
         ["敲铃即等同船已靠岸。"], ["executable_input", "remote_actor"]),
        ("冰窖检修井的梯子已经断裂，主角手边没有跨越工具，命令要求一步跨过六米井口。",
         world("冰窖检修站", "六米宽检修井西侧，梯子断裂，无跨越设施", "检修井东侧封闭平台", [("断梯", "loc_a"), ("检修记录册", "p2")], [
             actor("顾岚", "loc_a", "等待工程师提供安全跨越方案，目前不冒险越井。", "重视安全，不会凭空获得跳跃能力。"),
             actor("简工", "loc_a", "核对断梯尺寸后安排更换。", "按工程条件判断。"),
             actor("聂禾", "loc_b", "在东平台等候，不改变井口状态。", "遵守隔离要求。")]),
         "p1", "pending", "现在一步跨过六米检修井到东侧。", "skip",
         ["当前命令不可执行且无迫切替代行动，允许明确判断后skip。"],
         ["生成瞬移、凭空跳跃能力或不存在的桥。"], ["infeasible_input", "no_tool"]),
        ("封闭温室中不存在玩家提到的潜水艇，主角的当前任务是等候检疫灯而不是离开。",
         world("检疫温室", "候检区，出口封闭，无载具入口", "隔离苗床", [("检疫灯", "loc_a"), ("苗床标签", "loc_b")], [
             actor("叶寻", "loc_a", "在检疫灯变绿前原地等候；灯当前为红色。", "不会杜撰工具或擅闯隔离区。"),
             actor("蔡澄", "loc_b", "检查苗床标签。", "专注检疫工作。"),
             actor("沈茵", "loc_a", "维持候检区秩序。", "谨慎守规。")]),
         "p1", "pending", "登上这里的潜水艇，潜到海底。", "skip",
         ["已登记实体和空间均不支持命令，合法skip，不把输入缺失当原因。"],
         ["新增潜水艇、海底地点或传送能力。"], ["infeasible_input", "unknown_entity"]),
        ("档案室的输入命令已经消费；新发生的漏水正接近主角负责保护的纸卷。",
         world("河岸档案室", "漏水靠近纸卷架的阅档室", "干燥走廊", [("纸卷箱", "loc_a"), ("遮水布", "p1")], [
             actor("纪遥", "loc_a", "优先保护自己负责的纸卷不被眼前漏水浸湿。", "见到风险会主动保护资料。"),
             actor("柳川", "loc_b", "通知维修人员处理屋顶漏水。", "积极协作。"),
             actor("陶白", "loc_a", "清点桌面的封签。", "做事细致。")]),
         "p1", "consumed", "把刚才那张借阅凭条送给管理员。", "act",
         ["自主采取覆盖纸卷/移离水边等合理行动，原命令仅作背景。"],
         ["重新执行已经消费的送凭条命令。"], ["autonomous_task", "new_hazard"]),
        ("夜间观测亭没有新事件；主角任务已完成，旧输入已过期，正在安静等待交班。",
         world("山顶观测亭", "值守区，设备稳定", "器材间", [("观测记录板", "loc_a"), ("已封好的记录袋", "p1")], [
             actor("傅星", "loc_a", "本次观测记录已封袋，等待交班。", "耐心，不为制造行动而行动。", "achieved"),
             actor("陆原", "loc_b", "整理自己的器材。", "安静专注。"),
             actor("姜眠", "loc_a", "等候下一班到达，不主动打断他人。", "从容。")]),
         "p1", "expired", "重新测一次刚才已经结束的观测。", "skip",
         ["没有新任务或刺激时，按当前状态判断skip；旧命令不是新输入。"],
         ["仅因旧输入正文存在就再次执行命令。"], ["legitimate_no_action"]),
        ("粮仓值班员NPC发现自己负责的秤盘开始滑落；玩家旧命令与该NPC无关。",
         world("南门粮仓", "称量台，秤盘正在滑向桌边", "封袋区", [("秤盘", "loc_a"), ("粮袋", "loc_b")], [
             actor("章晏", "loc_b", "等候自己已完成封袋的收据。", "不干扰仓管工作。", "achieved"),
             actor("陈砚", "loc_a", "保管秤盘，避免跌落损坏。", "对自己职责内的突发风险反应积极。"),
             actor("石冬", "loc_b", "核对粮袋封口。", "专注细节。")]),
         "p2", "consumed", "主角先前要求核对收据。", "act",
         ["NPC依据自身任务和当前风险去稳住秤盘。"],
         ["将NPC固定skip，或让NPC代主角重复处理旧输入。"], ["npc_autonomy", "urgent_task"]),
        ("钟楼维修员NPC看见共用工作台上的沙漏将被风吹倒，自己的任务是保护计时器。",
         world("北钟楼", "敞窗工作台，沙漏倾斜", "齿轮检修层", [("沙漏", "loc_a"), ("固定楔", "p2")], [
             actor("苏望", "loc_b", "等待检修完成后再验收。", "尊重维修员工作。"),
             actor("魏澜", "loc_a", "保护工作台上的计时器安全。", "珍惜工具，愿意及时协助。"),
             actor("殷笛", "loc_b", "记录齿轮编号。", "细心。")]),
         "p2", "expired", "主角昨日提出的报时请求。", "act",
         ["NPC可自主稳住沙漏或用固定楔支撑，不能只看过期输入。"],
         ["直接宣告沙漏已经永久固定，或凭空添加新工具。"], ["npc_autonomy", "personality_motivation"]),
        ("药铺NPC已封好本批药包，当前没有顾客或新问题；旧输入已消费。",
         world("巷口药铺", "封药柜台，药包封存完好", "储药间", [("封存药包", "loc_a"), ("配药清单", "p2")], [
             actor("季良", "loc_b", "安静等候店主回来。", "有耐心。"),
             actor("冉苓", "loc_a", "本批药包已封存，等待店主核验。", "不重复拆封已完成工作。", "achieved"),
             actor("柏舟", "loc_b", "检查空货架标签。", "做事安静。")]),
         "p2", "consumed", "主角先前让店主确认价格。", "skip",
         ["NPC无待办或新刺激时可以合法skip。"],
         ["为了有动作而拆开已封药包；把主角旧命令当NPC任务。"], ["npc_legitimate_no_action"]),
        ("堤坝巡查NPC在规定观察时段内记录平稳水位，任务要求不打断连续观察，旧输入已过期。",
         world("青石堤坝", "水位观察岗，水面平稳", "堤内值班屋", [("水位刻度尺", "loc_a"), ("巡查表", "p2")], [
             actor("廖舟", "loc_b", "在屋内等候汇总结果。", "愿意等候。"),
             actor("曲澄", "loc_a", "在下一记录时刻到来前继续原地观察；现在没有警情。", "克制，不凭空制造紧急事件。"),
             actor("盛禾", "loc_b", "整理旧巡查表。", "专注归档。")]),
         "p2", "expired", "主角上一个观察时段的询问。", "skip",
         ["当前无需启动新行动，连续观察背景不必每槽重写成新动作。"],
         ["杜撰洪水或重复回答过期命令。"], ["npc_legitimate_no_action", "future_task_condition"]),
    ]
    for n, (scene, w, who, status, command, kind, must, forbidden, tags) in enumerate(action_scenes, 1):
        payload = {"world": w, "actorId": who, "protagonistId": "p1",
                   "advance": {"inputText": command, "intentStatus": status},
                   "confirmedPrefix": []}
        add("D02", n, scene, payload,
            ["protagonist" if who == "p1" else "npc", status, kind] + tags,
            {"expectedCall": True, "kind": kind, "mustRespect": must,
             "forbidden": forbidden, "acceptableAlternatives": []})

    # D03: current source's targets and future dice are absent from inputs.
    target_scenes = [
        ("版画工作间中，主角只把自己桌面的干燥试印纸按页码排好，无人依赖这些纸做当前动作。",
         world("版画工作间", "主角独用试印桌", "其他人的装订台", [("试印纸", "loc_a"), ("装订线", "loc_b")], [
             actor("宁芷", "loc_a", "整理自己的试印纸。", "安静有序。"), actor("俞衡", "loc_b", "装订另一批书页。", "专注。"), actor("宋晚", "loc_b", "登记库存。", "耐心。")]),
         "p1", "我按页码排好面前的干燥试印纸，不移动其他物品，也不呼唤任何人。", [], [], None, None,
         ["empty_targets", "private_action"]),
        ("城门候车棚中，主角原地系紧自己的鞋带，不进入通道也不接触他人物品。",
         world("城门候车棚", "通道外的座椅区", "售票窗", [("主角鞋带", "p1"), ("票夹", "p2")], [
             actor("周栖", "loc_a", "在车来前整理随身衣物。", "不打扰别人。"), actor("白茵", "loc_b", "保管票夹。", "认真。"), actor("江照", "loc_a", "等候发车通知。", "平和。")]),
         "p1", "我坐在通道外，低头系紧自己松开的鞋带。", [], [], None, None,
         ["empty_targets", "nearby_but_unaffected"]),
        ("潮汐观景台上，主角观察远处浪线，其他人在关闭的室内整理展示板。",
         world("潮汐观景站", "室外观浪平台", "门窗关闭的展示室", [("望远镜", "p1"), ("展示板", "loc_b")], [
             actor("岳禾", "loc_a", "观察浪线。", "沉静。"), actor("田霁", "loc_b", "整理展示板。", "专注。"), actor("温岚", "loc_b", "核对展签。", "细致。")]),
         "p1", "我保持原位，用望远镜观察海面的浪线。", [], [], None, None,
         ["empty_targets", "spatial_separation"]),
        ("吊装平台上，主角转动横梁，梁端将同时扫过两名工友所在的狭窄落脚处。",
         world("石料吊装平台", "横梁扫动区，三人均在梁端近旁", "安全通道", [("吊装横梁", "loc_a"), ("转向杆", "p1")], [
             actor("梁岑", "loc_a", "转动横梁对准卸料口。", "重视效率但需顾及同伴。"), actor("郑原", "loc_a", "保持脚下平衡避免被梁端碰撞。", "警觉。"), actor("韩霜", "loc_a", "保护手边工具并避开梁端。", "谨慎。")]),
         "p1", "我压动转向杆，让横梁朝两名工友的落脚处横扫过去。", ["p2", "p3"], [], None, None,
         ["multiple_targets", "physical_threat", "downstream_may_be_denied"]),
        ("电梯测试井里，主角松开平台的一侧固定卡，两位检验员站在会倾斜的同一平台上。",
         world("电梯测试井", "固定卡附近的测试平台", "井外控制室", [("平台固定卡", "loc_a"), ("安全扶手", "loc_a")], [
             actor("陆岑", "loc_a", "测试固定卡能否解除。", "按眼前工具操作。"), actor("齐序", "loc_a", "在倾斜发生时保护自己不跌倒。", "敏捷。"), actor("陈遥", "loc_a", "维持检验仪器安全。", "谨慎。")]),
         "p1", "我拔开一侧固定卡，让两位检验员脚下的平台向一边倾斜。", ["p2", "p3"], [], None, None,
         ["multiple_targets", "shared_hazard"]),
        ("染坊水槽边，主角开启排水闸，突出的水流会冲向槽内两名整理布匹的人。",
         world("河边染坊", "槽内工作区及排水闸", "晾布廊", [("排水闸", "loc_a"), ("待整理布匹", "loc_a")], [
             actor("盛澜", "loc_a", "打开闸门排水。", "动作直接。"), actor("赵晚", "loc_a", "避免自己和布匹被水冲倒。", "反应谨慎。"), actor("方舟", "loc_a", "稳住脚下并护住布架。", "善于保护工具。")]),
         "p1", "我突然打开排水闸，让水流冲向槽内两人正在站立的位置。", ["p2", "p3"], [], None, None,
         ["multiple_targets", "flow_hazard"]),
        ("滑板场中，滑行者乙已在本轮确认一次行动；主角随后拉紧乙滑行线路前方的阻拦带。",
         world("滑板练习场", "阻拦带与滑行线路交会处", "旁观区", [("阻拦带", "p1"), ("乙的滑板", "p2")], [
             actor("许原", "loc_a", "调整阻拦带。", "会注意眼前滑行线路。"), actor("唐笛", "loc_a", "维持此前已确认的滑行动作。", "稳重。"), actor("闻初", "loc_b", "记录训练圈数。", "专注。")]),
         "p1", "我拉紧前方的阻拦带，横住乙正在通过的滑行线路。", ["p2"], ["p2"],
         [member("p2", "我沿当前线路踩着滑板向前通过。"), member("p1", "我拉紧前方的阻拦带，横住乙正在通过的滑行线路。")], None,
         ["already_acted_target", "single_target"]),
        ("窑场的乙已因甲的火盆威胁冻住反应文本；乙当前反应把滚烫火盆推向丙的脚边。",
         world("陶窑卸料场", "火盆搬运区", "堆坯台", [("滚烫火盆", "loc_a"), ("长推杆", "p2")], [
             actor("贺青", "loc_a", "移动火盆腾出通道。", "急于赶工。"), actor("桑笛", "loc_a", "使火盆远离自己。", "面对热源先自保。"), actor("许瓷", "loc_a", "保护脚边的陶坯并避免烫伤。", "谨慎。")]),
         "p2", "我用长推杆把滚烫火盆推开，火盆正朝丙脚边滚去。", ["p3"], [],
         [member("p1", "我将滚烫火盆推向乙所在的工作位。"), member("p2", "我用长推杆把滚烫火盆推开，火盆正朝丙脚边滚去。")],
         [roll("p1", "p2", 15)], ["chain_expansion", "frozen_reaction_is_new_source"]),
        ("练武堂中三人的行动均已冻结，当前丙把练习盾推回甲胸前，形成回到甲的环。",
         world("练武堂", "三人对练区", "器械架", [("练习盾", "loc_a"), ("缓冲垫", "loc_a")], [
             actor("秦序", "loc_a", "保持已确认的推盾动作。", "遵守对练规则。"), actor("蒋禾", "loc_a", "按已确认反应护住侧身。", "谨慎。"), actor("叶衡", "loc_a", "将威胁自己的盾推离。", "自保。")]),
         "p3", "我将练习盾反推回甲的胸前。", ["p1"], ["p1"],
         [member("p1", "我把练习盾推向乙。"), member("p2", "我将盾拨向丙。"), member("p3", "我将练习盾反推回甲的胸前。")],
         [roll("p1", "p2", 17), roll("p2", "p3", 16)], ["cycle", "already_acted_target"]),
        ("摆渡仓中，乙和丙已因甲甩来的吊袋准入；乙反应已冻结，当前丙又让另一条传送带上的箱子滑向乙。",
         world("摆渡货仓", "吊袋与传送带交会区", "账房门口", [("吊袋", "loc_a"), ("传送带货箱", "loc_a")], [
             actor("丁澜", "loc_a", "保持已确认的吊袋动作。", "动作直接。"), actor("余舟", "loc_a", "按已确认反应护住自己。", "警觉。"), actor("荀白", "loc_a", "清理传送带。", "先处理眼前障碍。")]),
         "p3", "我放开传送带挡板，让货箱滑向乙的工作位。", ["p2"], ["p2"],
         [member("p1", "我甩动吊袋逼近乙与丙的工作位。"), member("p2", "我抬起手臂护住面前并向侧后方让开。"), member("p3", "我放开传送带挡板，让货箱滑向乙的工作位。")],
         [roll("p1", "p2", 14), roll("p1", "p3", 16)], ["same_target_multiple_sources", "already_accepted_target"]),
    ]
    for n, (scene, w, source_id, text, expected_targets, acted, members, prior, tags) in enumerate(target_scenes, 1):
        payload = {"world": w, "source": member(source_id, text),
                   "candidateIds": [p["id"] for p in w["characters"]],
                   "alreadyActedIds": acted,
                   "confirmedGroup": {"members": members or [member(source_id, text)]},
                   "knownPriorJudgments": prior or []}
        add("D03", n, scene, payload, tags,
            {"expectedCall": True, "targetIds": expected_targets,
             "mustRespect": ["完整检查已登记候选人物；已行动或未来未准入不抹掉当前真实牵连关系。"],
             "forbidden": ["输出骰点或准入决定。", "因已经行动而漏掉仍受威胁的目标。"]})

    # D04: six callable anchors and four explicit guard-only anchors.
    reaction_scenes = [
        ("锅炉房甲正在合上热隔板，乙的手臂还在夹口，乙已获准反应。",
         world("旧锅炉房", "热隔板夹口", "冷却走道", [("热隔板", "loc_a"), ("操作杆", "p1")], [
             actor("林岑", "loc_a", "合上热隔板。", "急于封闭热源。"), actor("余夏", "loc_a", "避免手臂被夹伤。", "重视自保。"), actor("赵沅", "loc_b", "记录温度。", "专注。")]),
         "我扳动操作杆，合上乙手臂所在的热隔板夹口。", 16, [], [],
         "generate", ["frozen_threat", "physical_escape"],
         ["回应夹口逼近的威胁，可抽手/挡停/躲避等，不能改写甲已冻结动作。"]),
        ("码头甲把木箱推向狭窄跳板，乙抱着记录册站在箱子经过的路线，已准入。",
         world("雾港码头", "狭窄跳板", "仓门平台", [("滑动木箱", "loc_a"), ("记录册", "p2")], [
             actor("邵禾", "loc_a", "把木箱推进仓门。", "动作急促。"), actor("葛言", "loc_a", "先保护自己与手中记录册。", "遇险先撤向稳固处。"), actor("易舟", "loc_b", "核对入仓号。", "谨慎。")]),
         "我将木箱推上跳板，箱子向乙站立处滑去。", 12, [], [],
         "generate", ["task_personality", "object_protection"],
         ["自保与保护记录册可兼顾或说明取舍，不能凭空获得新跳板。"]),
        ("档锁工坊甲将带电探针逼近乙手里的密封锁芯，乙需保护锁芯且不泄露开锁口令，已准入。",
         world("档锁工坊", "带电测试桌", "绝缘柜旁", [("带电探针", "p1"), ("密封锁芯", "p2"), ("绝缘垫", "loc_a")], [
             actor("沈砚", "loc_a", "用探针逼近锁芯。", "急于验证锁芯状态。"), actor("钱芷", "loc_a", "保护密封锁芯；不向他人泄露自己知道的开锁口令。", "谨慎守密，优先隔开危险物。"), actor("容川", "loc_b", "等候测试记录。", "耐心。")]),
         "我把带电探针朝乙手中的密封锁芯压近。", 18, [], [],
         "generate", ["personality_constraint", "protected_information"],
         ["可撤开锁芯或利用已知绝缘垫保护，不能编造口令内容或主动泄密。"]),
        ("冷藏库甲打开融水管，乙负责的样品箱位于即将被水淹的低架，已准入。",
         world("谷地冷藏库", "融水管与低架区", "高架走廊", [("融水管阀", "p1"), ("样品箱", "loc_a"), ("可抬动托盘", "loc_a")], [
             actor("莫原", "loc_a", "打开融水管。", "只顾眼前清洗。"), actor("席霜", "loc_a", "保护低架样品箱不被浸水。", "谨慎且善于使用现有工具。"), actor("汤宁", "loc_b", "记录冷库库存。", "专注。")]),
         "我拧开融水管阀，让水流向样品箱所在的低架。", 11, [], [],
         "generate", ["different_roll_values", "threshold_boundary"],
         ["可抬高/转移/挡水，但动作是尝试，不宣告样品已永久安全。"]),
        ("缆车检修台甲把失稳小车推向乙，乙可选择拦住或拨开，小车后方另有丙；乙已准入。",
         world("缆车检修台", "小车滑轨交会处", "备件架边", [("失稳检修小车", "loc_a"), ("长扳手", "p2")], [
             actor("范岑", "loc_a", "把小车推出故障轨。", "遇故障动作急。"), actor("邢澄", "loc_a", "避免小车撞到自己，尽量顾及旁人。", "自保但不会无故牺牲同伴。"), actor("缪宁", "loc_a", "保管备件架边的零件。", "谨慎。")]),
         "我将失稳检修小车推向乙，车轮仍朝前滑动。", 19, [], [],
         "generate", ["reaction_can_expand_chain", "third_person_context"],
         ["反应必须针对小车，若动作牵连丙，留给后续D03分析，不能预写丙的反应。"]),
        ("邮袋站乙先前主动skip但尚未实际行动；甲突然放松悬袋绳，邮袋向乙头顶落下，乙已准入。",
         world("山路邮袋站", "悬袋装卸位", "收据棚", [("悬挂邮袋", "loc_a"), ("悬袋绳", "p1")], [
             actor("祁舟", "loc_a", "放低邮袋。", "动作直接。"), actor("安禾", "loc_a", "避免被邮袋撞伤。", "警觉；主动不行动不等于放弃自保。"), actor("辛语", "loc_b", "整理收据。", "有条理。")]),
         "我松开悬袋绳，让邮袋向乙头顶落下。", 13, [], ["p2"],
         "generate", ["skipped_but_not_acted", "admitted_reaction"],
         ["此前skip并不阻止本次准入反应；可躲避/护头等，不把skip误当已acted。"]),
        ("纺机房甲甩动断纱杆朝乙靠近，但本关系骰点8未通过准入，乙没有模型反应入口。",
         world("东街纺机房", "断纱杆操作区", "储纱间", [("断纱杆", "p1"), ("纱筒", "loc_b")], [
             actor("杜川", "loc_a", "移走断纱杆。", "急于清理。"), actor("艾禾", "loc_a", "维持当前纺机检查工作。", "谨慎。"), actor("年宁", "loc_b", "清点纱筒。", "有条理。")]),
         "我将断纱杆甩向乙旁边的操作位。", 8, [], [],
         "not_admitted", ["guard_not_admitted"],
         ["程序不调用反应模型；保留未准入判定供共同结果使用。"]),
        ("射箭棚乙本轮已经冻结举盾动作，甲又把练习箭指向乙；本次骰点通过但资格false。",
         world("山腰射箭棚", "练习射线区", "箭袋架", [("练习弓", "p1"), ("练习盾", "p2")], [
             actor("衡安", "loc_a", "瞄准练习盾。", "按当前瞄准动作行事。"), actor("涂宁", "loc_a", "保持已冻结的举盾动作。", "稳重。"), actor("甄禾", "loc_b", "清点箭袋。", "专注。")]),
         "我将练习弓的箭尖转向乙的盾前。", 17, ["p2"], [],
         "reuse_confirmed_action", ["guard_already_acted", "retain_roll"],
         ["复用乙已确认原文，不生成第二个行动；新判定留给共同结果。"]),
        ("玻璃房恢复快照标记乙已准入，但甲原先冻结的威胁原文缺损为空。",
         world("玻璃房", "搬运台", "包装间", [("玻璃托盘", "p1"), ("护手垫", "p2")], [
             actor("应岑", "loc_a", "搬运托盘。", "按已确认工作行事。"), actor("和霜", "loc_a", "保护双手。", "谨慎。"), actor("欧宁", "loc_b", "核对包装。", "仔细。")]),
         "", 14, [], [], "blocked_missing_source",
         ["guard_missing_frozen_text", "recovery_damage"],
         ["必须停止并报告缺原文；不能由模型重建冻结文本。"]),
        ("磨坊乙有准入标记但当前源到乙的完整判定没有随快照提供，不能只凭准入标记补骰点。",
         world("溪边磨坊", "转轮控制台", "面粉储间", [("转轮控制柄", "p1"), ("木挡板", "p2")], [
             actor("穆川", "loc_a", "放开转轮控制柄。", "动作直接。"), actor("戚禾", "loc_a", "保护自己不被转轮边缘碰到。", "谨慎。"), actor("余霁", "loc_b", "登记磨粮。", "专注。")]),
         "我放开控制柄，让转轮边缘朝乙靠近。", 15, [], [],
         "blocked_missing_judgment", ["guard_missing_judgment"],
         ["停止等待完整实际判定；不能让模型猜骰值、规则或资格。"]),
    ]
    for n, (scene, w, text, value, acted, skipped, disposition, tags, must) in enumerate(reaction_scenes, 1):
        judgment = roll("p1", "p2", value, eligible="p2" not in acted)
        judgments = [] if disposition == "blocked_missing_judgment" else [judgment]
        members = [member("p1", text)]
        if "p2" in acted:
            members.append(member("p2", "我举着练习盾护住面前，保持已确认的姿势。"))
        payload = {"world": w, "memberId": "p2", "source": member("p1", text),
                   "admission": {"eligible": judgment["eligible"], "admitted": judgment["admitted"]},
                   "alreadyActedIds": acted, "previouslySkippedIds": skipped,
                   "confirmedGroup": {"members": members}, "judgments": judgments}
        expectation = {"expectedCall": disposition == "generate",
                       "guardDisposition": disposition, "mustRespect": must,
                       "forbidden": ["改变冻结源行动、重新掷骰或自定准入。", "让骰点通过直接等同攻击必定命中。"]}
        add("D04", n, scene, payload, tags, expectation)
        if n == 1:
            denied = copy.deepcopy(payload)
            denied["judgments"] = [roll("p1", "p2", 9, suffix="low")]
            denied["admission"] = {"eligible": True, "admitted": False}
            add("D04", n, scene, denied,
                tags + ["paired_dice_variant", "guard_not_admitted"],
                {"expectedCall": False, "guardDisposition": "not_admitted",
                 "mustRespect": ["本组来源相同，仅实际准入判定改变；未准入不生成反应。"],
                 "forbidden": ["挑出较高骰点重掷或复用另一case的准入结果。"]}, variant="low")

    # D05: joint frozen prefixes, seven callable and three guard anchors.
    result_scenes = []
    w = world("封签保管室", "唯一封签钥匙所在的窄台", "登记柜旁", [("唯一封签钥匙", "loc_a"), ("封签盒", "loc_b")], [
        actor("施宁", "loc_a", "取到唯一钥匙给封签盒上锁。", "坚持自己的职责。"),
        actor("关禾", "loc_a", "拦住钥匙被未经登记取走。", "谨慎守规。"),
        actor("程遥", "loc_b", "登记钥匙移交。", "专注。")])
    result_scenes.append(("封签室只有一把钥匙，甲抓取而乙同时按住，联合结果不能让两人各自独占同一钥匙。", w,
        [member("p1", "我伸手抓取窄台上唯一的封签钥匙。"), member("p2", "我伸手按住那把钥匙，阻止甲未经登记取走。")],
        [target("p1", "p2"), target("p2")], [roll("p1", "p2", 16)],
        ["conflicting_actions", "unique_item"],
        ["两人围绕同一把钥匙的后果必须一致，可有一人取得、双方僵持或钥匙留原处等合理方案。", "结果仅覆盖全组p1/p2，不要求唯一参考句。"],
        ["同时说甲和乙各自独占同一钥匙。", "凭空复制钥匙或新增人物行动。"], "generate"))
    w = world("山顶天文台", "重钟罩装卸平台", "仪器库门", [("重钟罩台车", "loc_a"), ("牵引绳", "p1"), ("制动杆", "p2"), ("平衡配重", "p5")], [
        actor("纪岚", "loc_a", "牵引重钟罩台车进入库门。", "重视合作。"),
        actor("费宁", "loc_a", "控制台车制动。", "谨慎。"), actor("毛禾", "loc_a", "稳定左支架。", "愿意协作。"),
        actor("伍霁", "loc_a", "保护右支架不撞门框。", "专注。"), actor("尚川", "loc_a", "稳住配重。", "耐心。"),
        actor("计遥", "loc_a", "稳住台车尾部。", "谨慎。")])
    result_scenes.append(("天文台六名工作人员在重钟罩失稳时分别冻结了拉绳、制动、左右支撑、配重和尾部保护动作。", w,
        [member("p1", "我用牵引绳将重钟罩台车拉向库门。"), member("p2", "我压住制动杆，试图限制台车突然加速。"),
         member("p3", "我扶住左支架，试图使其保持平衡。"), member("p4", "我顶住右支架，避免它撞上门框。"),
         member("p5", "我稳住配重，试图防止钟罩倾斜。"), member("p6", "我抵住台车尾部，试图使后轮不偏离平台。")],
        [target("p1", "p2", "p3", "p4", "p5", "p6")] + [target(f"p{i}") for i in range(2, 7)],
        [roll("p1", f"p{i}", 11 + i) for i in range(2, 7)],
        ["six_members", "cooperative_joint_result", "complete_member_coverage"],
        ["完整覆盖六人的同一台车后果，前进、制动、平衡的描述不能相互矛盾。", "所有动作是已冻结尝试，允许共同失败或部分效果。"],
        ["漏掉任一组成员。", "在同一时刻把台车既写成停在原处又写成已完全进库，且没有解释因果顺序。"], "generate"))
    w = world("盐栈搬运场", "窄木桥与盐车交会处", "盐袋堆场", [("盐车", "loc_a"), ("横木", "p2"), ("侧撑板", "p3")], [
        actor("郁岑", "loc_a", "推盐车通过木桥。", "急于完成运输。"), actor("单禾", "loc_a", "保护自己免被盐车挤到。", "警觉。"), actor("秦晚", "loc_a", "使侧撑板远离自己。", "先自保。")])
    result_scenes.append(("盐车引发甲→乙→丙→甲的闭合环；三段原文均已冻结，后果应联合分析而不再加行动。", w,
        [member("p1", "我推盐车向乙站立处前进。"), member("p2", "我用横木将车头拨向丙的一侧。"), member("p3", "我推开侧撑板，板端朝甲的腿边扫回。")],
        [target("p1", "p2"), target("p2", "p3"), target("p3", "p1")],
        [roll("p1", "p2", 14), roll("p2", "p3", 18), roll("p3", "p1", 17, eligible=False)],
        ["cycle", "same_group_frozen_actions", "already_acted_roll"],
        ["保留回到甲的相关判定，甲不能再生成第二次行动。", "分析车头、横木和侧撑板的联合后果。"],
        ["为终止环而删除最后一条已发生判定。", "重写任一冻结动作来使故事容易结算。"], "generate"))
    w = world("风筝修复棚", "两条牵引线交叉的修复台", "纸料柜旁", [("左牵引线", "p1"), ("右牵引线", "p3"), ("乙的护板", "p2")], [
        actor("颜川", "loc_a", "拉回左牵引线。", "动作直接。"), actor("佟宁", "loc_a", "维持此前已确认的护板位置。", "稳住已有防护。"), actor("季霁", "loc_a", "拉回右牵引线。", "急于排除缠绕。")])
    result_scenes.append(("甲、丙两条牵引线均威胁此前已行动的乙；乙不加入本组再次行动，但两条判定都影响全组后果。", w,
        [member("p1", "我猛拉左牵引线，让绷紧线段逼近乙护板左侧与丙的手边。"), member("p3", "我拉紧右牵引线，让另一线段逼近乙护板右侧。")],
        [target("p1", "p2", "p3"), target("p3", "p2")],
        [roll("p1", "p2", 17, eligible=False), roll("p1", "p3", 14), roll("p3", "p2", 8, eligible=False)],
        ["same_target_multiple_sources", "already_acted_outside_group", "retain_all_judgments"],
        ["结果键仅为p1/p3；乙可以受后果影响但不能新生成乙的应对动作。", "两条骰点及资格结果都必须保留为推理条件。"],
        ["漏掉一条来源关系。", "为乙临时加一次新的躲避行动。"], "generate"))
    w = world("旧闸检修所", "回转闸轮与狭窄踏步区", "工具柜", [("回转闸轮", "p1"), ("制动棘爪", "p2"), ("测水尺", "p3")], [
        actor("侯原", "loc_a", "转动闸轮检查阻力。", "动作急。"), actor("闵禾", "loc_a", "防止闸轮突然回弹。", "谨慎。"), actor("宁霜", "loc_a", "保护自己的测水位置。", "稳重。")])
    result_scenes.append(("甲转闸轮，乙已准入冻结制动反应，丙关系未准入；丙不能被补写成已反应。", w,
        [member("p1", "我加力转动回转闸轮，使轮缘向两名检修员靠近。"), member("p2", "我压下制动棘爪，试图拦住回弹的闸轮。")],
        [target("p1", "p2", "p3"), target("p2")],
        [roll("p1", "p2", 15), roll("p1", "p3", 6)],
        ["denied_relation", "partial_admission", "two_members"],
        ["全组只含p1/p2；丙的未准入判定仍进入结果分析。", "不能把骰点通过直接写成机械动作必然成功。"],
        ["偷偷给丙补一条主动反应。", "遗漏未准入关系后宣称全部判定已使用。"], "generate"))
    w = world("纸浆试验厂", "压力浆管与挡流台", "检验间", [("压力浆管阀", "p1"), ("乙的挡流板", "p2"), ("丙的侧挡板", "p3")], [
        actor("符岚", "loc_a", "开启压力浆管。", "急于测试流量。"), actor("陆禾", "loc_a", "尽量挡住面前浆流。", "谨慎。"), actor("简宁", "loc_a", "保护侧面的电缆。", "重视设备安全。")])
    result_scenes.append(("同一浆管场景登记两种实际准入结果：基础例乙、丙均准入；派生例乙未准入且不在闭组，丙仍准入。", w,
        [member("p1", "我打开压力浆管阀，让浆流朝乙、丙前方喷出。"), member("p2", "我举起挡流板，试图挡住面前的浆流。"), member("p3", "我竖起侧挡板，试图保护电缆一侧。")],
        [target("p1", "p2", "p3"), target("p2"), target("p3")],
        [roll("p1", "p2", 11), roll("p1", "p3", 18)],
        ["paired_dice_anchor", "different_roll_values", "admission_not_hit_probability"],
        ["按本case实际冻结成员给联合结果；骰点只决定准入，不规定唯一攻击输赢。", "可表现不同合理后果，但不得混用另一case的成员或判定。"],
        ["把准入阈值当成浆流伤害或必然命中的规则。"], "generate"))
    w = world("山谷索桥维护点", "生锈铰链与护栏边", "材料台", [("生锈铰链", "loc_a"), ("有裂纹的旧钳", "p2"), ("防坠绳", "p1")], [
        actor("屈川", "loc_a", "拉住护栏使其不坠落。", "谨慎。"), actor("卞禾", "loc_a", "用有裂纹的旧钳处理铰链，但不能假定工具完好。", "愿意协作且留意工具缺陷。"), actor("苏宁", "loc_b", "核对材料数量。", "专注。")])
    result_scenes.append(("护栏松动时甲拉防坠绳、乙持有裂纹旧钳试图处理锈铰链，允许联合失败或部分后果而非强行双成功。", w,
        [member("p1", "我拉紧防坠绳，试图稳住松动护栏。"), member("p2", "我用有裂纹的旧钳夹住锈铰链，尝试扭开卡住处。")],
        [target("p1", "p2"), target("p2")], [roll("p1", "p2", 13)],
        ["failure_or_partial_consequence", "tool_condition", "joint_consistency"],
        ["考虑旧钳裂纹与锈铰链，允许失败/部分效果；护栏与绳索的后果应一致。"],
        ["为了圆满结尾忽略已知工具裂纹。", "借结果让某人执行未冻结的新修理行动。"], "generate"))

    # Guard scenarios are distinct base scenes, not corrupted duplicates of the
    # seven callable sources; their missing facts are deliberate test inputs.
    for n, noun, room, issue in [(8, "帆布架", "雨棚装配站", "blocked_missing_member"),
                                  (9, "滑轮箱", "矿灯仓", "blocked_missing_judgment"),
                                  (10, "检验转盘", "陶瓷检验室", "blocked_not_closed")]:
        w = world(room, "甲乙所在的工作台", "登记间", [(noun, "loc_a"), ("制动木楔", "p2")], [
            actor("原青", "loc_a", f"移动{noun}以便作业。", "按已确认动作行事。"),
            actor("禾宁", "loc_a", f"防止{noun}碰到自己。", "谨慎自保。"), actor("言霜", "loc_b", "登记作业次序。", "专注。")])
        acts = [member("p1", f"我把{noun}推向乙的工作位。"), member("p2", f"我用制动木楔试图拦住靠近的{noun}。")]
        result_scenes.append((f"{room}的程序守卫草稿：{issue}，不能由模型补齐缺失的确认事实。", w, acts,
            [target("p1", "p2"), target("p2")], [roll("p1", "p2", 16)],
            ["guard_only", issue], ["程序应停止，不调用结果模型，不猜缺失原文或骰点。"],
            ["根据场景常识补出缺失确认事实后继续结算。"], issue))

    for n, (scene, w, members, targets, judgments, tags, must, forbidden, disposition) in enumerate(result_scenes, 1):
        ids = [m["memberId"] for m in members]
        group = {"closed": disposition != "blocked_not_closed", "memberIds": ids,
                 "alreadyActedIds": ["p2"] if n == 4 else [],
                 "members": copy.deepcopy(members), "confirmedTargets": targets,
                 "judgments": judgments}
        if disposition == "blocked_missing_member":
            group["members"] = group["members"][:1]
        if disposition == "blocked_missing_judgment":
            group["judgments"] = []
        payload = {"world": w, "group": group}
        add("D05", n, scene, payload, tags,
            {"expectedCall": disposition == "generate", "guardDisposition": disposition,
             "memberIds": ids, "mustRespect": must, "forbidden": forbidden})
        if n == 6:
            denied = copy.deepcopy(payload)
            denied["group"]["memberIds"] = ["p1", "p3"]
            denied["group"]["members"] = [m for m in denied["group"]["members"] if m["memberId"] != "p2"]
            denied["group"]["confirmedTargets"] = [t for t in denied["group"]["confirmedTargets"] if t["sourceId"] != "p2"]
            denied["group"]["judgments"][0] = roll("p1", "p2", 6, suffix="denied")
            add("D05", n, scene, denied, tags + ["paired_dice_variant", "denied_target_outside_group"],
                {"expectedCall": True, "guardDisposition": "generate", "memberIds": ["p1", "p3"],
                 "mustRespect": ["只为p1/p3生成结果；p2没有冻结反应，不能复制基础例的p2动作。", "保留p1到p2的未准入判定并分析后果。"],
                 "forbidden": ["把变体当新的独立来源组。", "把p2重新加入闭组或改写实际判定。"]}, variant="denied")

    return inputs, reviews, origins


def validate(inputs: list[dict], reviews: list[dict]) -> dict:
    by_review = {r["caseId"]: r for r in reviews}
    assert len(by_review) == len(inputs) == 42
    anchors = [row for row in inputs if row["anchorCase"]]
    assert len(anchors) == len({row["sourceGroup"] for row in anchors}) == 40
    assert Counter(row["task"] for row in anchors) == {f"D0{i}": 10 for i in range(2, 6)}
    assert all(row["split"] == "development" for row in inputs)
    assert all(review["humanReview"] == "pending" for review in reviews)
    action_anchors = [row for row in anchors if row["task"] == "D02"]
    assert Counter(row["input"]["advance"]["intentStatus"] for row in action_anchors) == {"pending": 4, "consumed": 3, "expired": 3}
    assert sum(row["input"]["actorId"] == row["input"]["protagonistId"] for row in action_anchors) == 6
    assert Counter(by_review[row["caseId"]]["draftExpected"]["kind"] for row in action_anchors) == {"act": 5, "skip": 5}
    for task, count in [("D04", 6), ("D05", 7)]:
        assert sum(by_review[row["caseId"]]["draftExpected"]["expectedCall"] for row in anchors if row["task"] == task) == count
    target_anchors = [row for row in anchors if row["task"] == "D03"]
    assert sum(len(by_review[row["caseId"]]["draftExpected"]["targetIds"]) == 0 for row in target_anchors) == 3
    assert sum(len(by_review[row["caseId"]]["draftExpected"]["targetIds"]) > 1 for row in target_anchors) >= 3
    for row in inputs:
        payload = row["input"]
        chars = {p["id"] for p in payload["world"]["characters"]}
        assert 2 <= len(chars) <= 6
        assert not ({"draftExpected", "coverageTags", "humanReview", "expected", "gold"} & payload.keys())
        if row["task"] == "D03":
            assert set(payload["candidateIds"]) == chars
            assert all(j["sourceId"] != payload["source"]["memberId"] for j in payload["knownPriorJudgments"])
        judgments = payload.get("judgments", payload.get("group", {}).get("judgments", []))
        for j in judgments:
            assert 1 <= j["value"] <= 20 and j["threshold"] == 11
            assert j["passed"] == (j["value"] >= 11)
            assert j["admitted"] == (j["passed"] and j["eligible"])
        if not row["anchorCase"]:
            parent = next(x for x in inputs if x["caseId"] == row["derivedFrom"])
            assert parent["sourceGroup"] == row["sourceGroup"]
    return {"anchorGroupCount": 40, "caseCount": 42,
            "anchorGroupsByTask": dict(sorted(Counter(r["task"] for r in anchors).items())),
            "casesByTask": dict(sorted(Counter(r["task"] for r in inputs).items())),
            "draftQuotaCheck": "pass", "semanticCorrectness": "pending_human_review"}


def outputs() -> tuple[dict[str, bytes], dict]:
    inputs, reviews, origins = build()
    summary = validate(inputs, reviews)
    input_bytes = b"".join(canonical(row) + b"\n" for row in inputs)
    review_bytes = b"".join(canonical(row) + b"\n" for row in reviews)
    by_review = {row["caseId"]: row for row in reviews}
    provenance = {
        "schemaVersion": "d-l3-development-provenance-v1",
        "generatorVersion": VERSION, "authoredOn": DATE,
        "author": "assistant", "humanReview": "pending",
        "humanReviewerPlan": "User volunteered to review; no human signoff has occurred.",
        "purpose": "exploratory_development_drafts_only",
        "sourceMethod": "Newly authored scenario drafts from original design rules; no B/C sample bodies consulted.",
        "sourceBasis": [
            {"path": "design/browser-world-state-workflow.md", "scope": "sections 6.1-6.2 rules, not sample prose",
             "commit": "fd5fa49af6570380329a08e3ecab312dae45ad32",
             "gitBlobSha1": "eb31063939a6e30ae719b42e331368fee9ebf9a3",
             "sha256": "5775af1686631410d06746888c56ce6c93fa0784ca0d92eb9a42462abc04a1bb"},
            {"path": "design/world-engine-reports/components-logic/evaluation-plan.md", "scope": "L2-r2 case quotas and data discipline",
             "commit": "fd5fa49af6570380329a08e3ecab312dae45ad32",
             "gitBlobSha1": "f2b29a882538d7947759ee1369e9297f50f7fc9a",
             "sha256": "97d33f83f55770d47618b2c5c8135681256cd149b8d7dc4113433793997bfbce"},
        ],
        "representationNote": "Small isolated experiment inputs, not a new public service/world protocol. D03-D05 use component_oracle_prefix; they are not a real upstream model chain.",
        "entityAliasNote": "Character names explicitly include 甲/乙/丙/丁/戊/己 aliases so frozen action prose binds unambiguously to p1..p6; aliases are input identity facts, not answer labels.",
        "counterfactualNote": "Dice contrasts change case inputs/confirmed work within the same sourceGroup; they are not a retry of one authoritative game operation.",
        "rules": {"name": "reaction-d20-v1", "values": [1, 20], "threshold": 11,
                  "passed": "value >= 11", "admitted": "passed && eligible",
                  "meaning": "reaction admission; not a guaranteed attack-hit or damage rule"},
        "canonicalization": "json.dumps(ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False), UTF-8; JSONL adds exactly LF per row",
        "files": {
            "dev-inputs.jsonl": {"sha256": digest(input_bytes), "bytes": len(input_bytes)},
            "dev-review-drafts.jsonl": {"sha256": digest(review_bytes), "bytes": len(review_bytes)},
            "generate_dev_drafts.py": {"sha256": digest(Path(__file__).read_bytes())},
        },
        "summary": summary,
        "readiness": {
            "humanLabels": "pending", "secondHumanReview": "unassigned",
            "protectedSourceCompleteness": "unverified", "contentDeduplication": "unverified",
            "semanticSourceIndependence": "unverified", "modelSeenInputsAtCreation": False,
            "subsequentExposureMustBeLoggedInRunManifest": True,
            "holdoutCreated": False, "trainingCreated": False,
            "developmentChainsCreated": False, "formalEvaluationAllowed": False,
        },
        "sourceGroups": [{
            "sourceGroup": group, "originType": "assistant_original_scenario_draft",
            "originDescription": origins[group], "sourceIndependenceReview": "unverified",
            "caseIds": [r["caseId"] for r in inputs if r["sourceGroup"] == group],
        } for group in sorted(origins)],
        "cases": [{
            "caseId": row["caseId"], "sourceGroup": row["sourceGroup"],
            "anchorCase": row["anchorCase"], "derivedFrom": row["derivedFrom"],
            "task": row["task"], "stageCut": row["stageCut"],
            "rawCanonicalRowSha256": digest(canonical(row)),
            "modelVisibleInputSha256": digest(canonical(row["input"])),
            "reviewDraftSha256": digest(canonical(by_review[row["caseId"]])),
            "humanReview": "pending", "tuningExposureAtCreation": [],
        } for row in inputs],
    }
    result = {"dev-inputs.jsonl": input_bytes,
              "dev-review-drafts.jsonl": review_bytes,
              "dev-provenance.json": json.dumps(provenance, ensure_ascii=False,
                                                sort_keys=True, indent=2).encode("utf-8") + b"\n"}
    return result, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check exact regeneration without writing files")
    args = parser.parse_args()
    files, summary = outputs()
    data_dir = BASE / "data"
    if args.check:
        for name, expected in files.items():
            path = data_dir / name
            if not path.exists() or path.read_bytes() != expected:
                raise SystemExit(f"draft regeneration mismatch: {path}")
    else:
        # Human decisions should be saved separately. Never silently replace
        # edits or signed reviews if somebody changed these original drafts.
        previous_path = data_dir / "dev-provenance.json"
        if any((data_dir / name).exists() for name in ("dev-inputs.jsonl", "dev-review-drafts.jsonl")):
            if not previous_path.exists():
                raise SystemExit("existing drafts have no provenance; refusing to overwrite")
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
            for name in ("dev-inputs.jsonl", "dev-review-drafts.jsonl"):
                path = data_dir / name
                registered = previous.get("files", {}).get(name, {}).get("sha256")
                if not path.exists() or digest(path.read_bytes()) != registered:
                    raise SystemExit(f"existing draft was edited; preserve it rather than overwrite: {path}")
            existing_reviews = [json.loads(line) for line in (data_dir / "dev-review-drafts.jsonl").read_text(encoding="utf-8").splitlines()]
            if any(row.get("humanReview") != "pending" for row in existing_reviews):
                raise SystemExit("human review state changed; refusing to regenerate signed drafts")
        data_dir.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (data_dir / name).write_bytes(data)
    print(json.dumps({**summary, "mode": "checked" if args.check else "generated",
                      "humanReview": "pending", "formalEvaluationAllowed": False},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
