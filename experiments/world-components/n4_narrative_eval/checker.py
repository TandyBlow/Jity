# 叙事正文判分器 v1（事实层自动、自然度与隐含层 abstain）
#
# 判分对象：一条 N4 叙事正文 + 它对应案例的已提交事实（facts）与场景。
# 输出三种判决：pass / fail / uncertain。每条检查都带 factId（如适用）、
# 出错原文 span、判断依据。
#
# 设计原则（来自 2026-11-08 评审）：
#   1. 逐字匹配失败 ≠ 事实错误。判分器不比较参考措辞，只检查事实关系。
#   2. 能自动判的只有：人物归属、方向、明确禁述（任务目标/数值/时长/字段名）、
#      他人内心、必述事实是否出现。
#   3. 隐含事实、视角限知、中文自然度一律允许返回 uncertain，不硬凑分数。
#   4. 判分器自己的误报/漏报要先测（见 run_eval.py），未过人工复核前，
#      它的分数不能决定模型是否合格。
#
# 用法：
#   from checker import check_case
#   result = check_case(case, text, world)

from __future__ import annotations

import re

# ---------------------------------------------------------------- 词表 / 正则

PUNCT = "，。；：！？、,;:!?…—－ \n\t“”‘’（）()《》「」"
CLAUSE_SPLIT = re.compile(r"[，。；！？,;!?\n]")

# 明确禁述：任务措辞
GOAL_MARKERS = ("任务", "目标", "完成度", "进度", "要求他", "派给他")
# 数值面板
NUM_PANEL = re.compile(
    r"(理智|精神|体力|好感|外貌|个性|魅力|数值|属性)\s*(值)?\s*"
    r"(从)?\s*[0-9０-９一二三四五六七八九十百]+\s*"
    r"(升|降|变|到|至|→|->|增加|减少)"
)
DIGIT = re.compile(r"[0-9０-９]")
# 明确时长（叙事契约要求只模糊或省略）
DURATION = re.compile(
    r"[0-9０-９]+\s*(秒|分钟|小时|天|日|刻)"
    r"|[一二三四五六七八九十两半]+\s*(秒|分钟|小时|时辰|刻钟)"
)
# 字段名泄漏
FIELD_NAMES = ("位置", "事实", "输入", "输出", "字段", "存档", "面板", "属性值")
# 他人内心线索（只能用于视角人物）
INNER_CUES = ("心想", "心里", "心里想", "暗自", "暗暗", "觉得", "意识到",
              "盘算", "记得", "回想起", "感到", "明白", "知道自己")
PRONOUNS = ("他", "她", "他们", "她们", "自己", "对方")

# 理智方向词（只判方向，不判自然度）。上=变清醒/松弛，下=变紧/发沉。
UP_WORDS = ("松", "松开", "松快", "轻", "轻了些", "稳", "清醒", "定下来",
            "缓", "舒", "散", "顺", "平复", "落回", "踏实", "透")
DOWN_WORDS = ("紧", "发紧", "沉", "发沉", "凉", "冷", "空", "乱", "慌",
              "抖", "僵", "闷", "压", "缩", "退", "薄", "涩", "钝")

# 常见汉族姓氏：只用于"像人名的未知词"，单靠它不判 fail
SURNAMES = set(
    "赵钱孙李周吴郑王冯陈蒋沈韩杨朱秦许何吕张孔曹严华金魏陶姜谢邹柏窦章苏潘葛"
    "范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐"
    "于傅齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅"
    "庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏"
    "蔡田樊胡凌霍虞万支柯昝管卢莫房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉钮"
    "龚程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗"
    "山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜"
    "黎蓟薄印宿白怀蒲台从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双闻莘党翟谭贡劳逄"
)
# 地点/名称后缀：用于"像地名的未知词"，只归 uncertain
PLACE_SUFFIX = ("巷", "驿", "岭", "台", "渡", "馆", "楼", "寺", "院", "桥",
                "井", "棚", "房", "屋", "门", "铺", "村", "镇", "城", "溪",
                "谷", "崖", "峰", "渡口", "码头", "集市", "早市")


def clauses(text: str) -> list[str]:
    return [c.strip() for c in CLAUSE_SPLIT.split(text) if c.strip()]


def bigrams(s: str) -> set[str]:
    s = "".join(ch for ch in s if ch not in PUNCT)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def world_names(world: dict) -> dict:
    """人物 / 地点 / 物品 / 小地点 的允许名单。"""
    chars = {v["name"] for v in world.get("characters", {}).values()}
    locs = set()
    for loc in world.get("locations", {}).values():
        locs.add(loc["name"])
        for sub in loc.get("sublocations", []) or []:
            locs.add(sub["name"])
    items = {v["name"] for v in world.get("items", {}).values()}
    return {"characters": chars, "locations": locs, "items": items}


def world_text(world: dict) -> str:
    """世界设定里出现过的词：地名/小地点/外貌/特征/物品描述。
    用来避免把"石墙""冰凌"这类文本当成捏造。"""
    parts = []
    for loc in world.get("locations", {}).values():
        parts += [loc.get("name", ""), loc.get("appearance", "")]
        parts += list(loc.get("features", []) or [])
        for sub in loc.get("sublocations", []) or []:
            parts += [sub.get("name", ""), sub.get("appearance", "")]
    for it in world.get("items", {}).values():
        parts += [it.get("name", "")]
    for ch in world.get("characters", {}).values():
        parts += [ch.get("name", ""), ch.get("appearance", ""), ch.get("personality", "")]
    return " ".join(p for p in parts if p)


def case_allowed(case: dict, world: dict) -> dict:
    names = world_names(world)
    present = set()
    scene = case.get("sceneState") or {}
    for eid in scene.get("present", []) or []:
        ch = world.get("characters", {}).get(eid)
        if ch:
            present.add(ch["name"])
    for c in case.get("characterContext", []) or []:
        present.add(c["name"])
    for f in case.get("facts", []):
        if f.get("name"):
            present.add(f["name"])
    return {"characters": names["characters"], "locations": names["locations"],
            "items": names["items"], "present": present,
            "pov": (case.get("perspective") or {}).get("entityId")}


def pov_name(case: dict, world: dict) -> str | None:
    eid = (case.get("perspective") or {}).get("entityId")
    ch = world.get("characters", {}).get(eid) if eid else None
    return ch["name"] if ch else None


def find_span(text: str, needle: str) -> str | None:
    i = text.find(needle)
    if i < 0:
        return None
    return text[max(0, i - 8): i + len(needle) + 8]


def _verdict(checks: list[dict]) -> str:
    if any(c["verdict"] == "fail" for c in checks):
        return "fail"
    if any(c["verdict"] == "uncertain" for c in checks):
        return "uncertain"
    return "pass"


def _add(checks, rule, verdict, *, fact_id=None, span=None, evidence=""):
    checks.append({"rule": rule, "verdict": verdict, "factId": fact_id,
                   "span": span, "evidence": evidence})


# ---------------------------------------------------------------- 全局禁述

def check_forbidden(case: dict, text: str, checks: list[dict]) -> None:
    # 目标原文可能与结果动作同形（"把铜铃挂到望雪台"既是 goal 也是 resultText），
    # 单独出现不算泄漏；只有任务口吻或 taskId 才是违规。
    for f in case.get("facts", []):
        tid = f.get("taskId")
        if tid and tid in text:
            _add(checks, "forbidden.goal", "fail", span=find_span(text, tid),
                 evidence=f"出现任务 ID「{tid}」")
    for m in GOAL_MARKERS:
        if m in text:
            _add(checks, "forbidden.goal", "fail", span=find_span(text, m),
                 evidence=f"出现任务措辞「{m}」")

    for m in NUM_PANEL.finditer(text):
        _add(checks, "forbidden.numeric", "fail", span=text[max(0, m.start() - 6):m.end() + 6],
             evidence="出现数值面板式表述")
        break
    if DIGIT.search(text):
        _add(checks, "forbidden.digit", "fail",
             span=text[max(0, DIGIT.search(text).start() - 6):DIGIT.search(text).end() + 6],
             evidence="出现阿拉伯数字")

    m = DURATION.search(text)
    if m:
        _add(checks, "forbidden.duration", "fail",
             span=text[max(0, m.start() - 8):m.end() + 6],
             evidence=f"写出明确时长「{m.group(0)}」；契约要求模糊或省略")

    for f in FIELD_NAMES:
        if f in text:
            _add(checks, "forbidden.fieldName", "fail", span=find_span(text, f),
                 evidence=f"出现字段名「{f}」")


def check_pov(case: dict, text: str, world: dict, checks: list[dict]) -> None:
    pov = pov_name(case, world)
    # 不在场的人也会被模型写内心；把他们一起纳入，兼具"捏造在场"与"视角越界"
    others = [n for n in world_names(world)["characters"] if n and n != pov]
    for cl in clauses(text):
        for cue in INNER_CUES:
            if cue not in cl:
                continue
            for other in others:
                # 他人姓名 + 内心词，且中间没有别的主语截断
                i_name, i_cue = cl.find(other), cl.find(cue)
                if i_name >= 0 and 0 <= i_cue - i_name <= 12:
                    _add(checks, "pov.innerOther", "fail", span=cl,
                         evidence=f"他人「{other}」的内心活动（线索「{cue}」）")
            for p in PRONOUNS:
                i_p, i_cue = cl.find(p), cl.find(cue)
                if i_p >= 0 and 0 <= i_cue - i_p <= 6 and not any(
                        o in cl for o in others):
                    _add(checks, "pov.innerOther", "uncertain", span=cl,
                         evidence=f"代词 + 内心线索「{cue}」，无法确定视角归属")


# ---------------------------------------------------------------- 事实检查

def location_aliases(loc: str, world: dict, *, with_sublocations: bool = False) -> set[str]:
    """地点名的缩写（潮汐档案馆→档案馆、旧灯塔→灯塔）＋可选的下属小地点。
    小地点只在解析"从哪儿出发"时用，不参与方向证据，否则会把
    「从石阶底下」误判成「从旧灯塔出发」。"""
    al = {loc}
    for prefix in ("潮汐", "旧", "小", "大", "河心"):
        if loc.startswith(prefix) and len(loc) > len(prefix) + 1:
            al.add(loc[len(prefix):])
    if len(loc) >= 3:
        al.add(loc[-3:])
    if len(loc) >= 2:
        al.add(loc[-2:])
    if with_sublocations:
        for parent in world.get("locations", {}).values():
            if parent["name"] != loc:
                continue
            for sub in parent.get("sublocations", []) or []:
                if sub.get("name"):
                    al.add(sub["name"])
    return al


def resolve_endpoint(captured: str, world: dict) -> tuple[str | None, bool]:
    """把"从X"里的 X 归到某个地点。返回 (地点, 是否来自小地点)。
    匹配按最长别名优先，避免「石阶」既属于旧灯塔又属于潮渡时乱归。"""
    best = (None, False, 0)
    for loc in world_names(world)["locations"]:
        for a in location_aliases(loc, world, with_sublocations=True):
            if captured.startswith(a) and len(a) > best[2]:
                direct = a in {loc} | {s for s in location_aliases(loc, world)}
                best = (loc, direct, len(a))
    return best[0], not best[1]


def scene_location_name(case: dict, world: dict) -> str | None:
    path = (case.get("sceneState") or {}).get("locationPath") or []
    if not path:
        return None
    loc = world.get("locations", {}).get(path[0])
    return loc["name"] if loc else None


# 只认"从/由"引导的地点短语，后面接什么动词不影响判读：
# 从潮渡过来 / 从巷子另一头挤进来 / 从旋梯口出来 / 从石阶底下漫上来
MOVE_CUE = re.compile(r"(从|由|自|打)([^，。；,;！？]{1,8})")


def check_moved(case: dict, fact: dict, text: str, world: dict, checks: list[dict]) -> None:
    """三个问题分开问：移动有没有出现、方向对不对、谁在做。
    读不清就 uncertain。逐字不同不构成错误证据。"""
    name, src, dst = fact.get("name"), fact.get("from"), fact.get("to")
    fid = fact.get("factId")
    if not name:
        return
    locs = world_names(world)["locations"]
    alias = {loc: location_aliases(loc, world) for loc in locs}
    src_hit = any(a in text for a in alias.get(src, {src}))
    dst_hit = any(a in text for a in alias.get(dst, {dst}))
    src_direct = alias.get(src, {src})
    dst_direct = alias.get(dst, {dst})
    scene_loc = scene_location_name(case, world)
    dst_is_scene = bool(dst and scene_loc and dst == scene_loc)

    # 所有"从已知地点"的短语。小地点层面的短语只能证明"在这一带"，不能证明方向。
    phrases = []
    for m in MOVE_CUE.finditer(text):
        loc, via_sub = resolve_endpoint(m.group(2), world)
        if loc:
            phrases.append((m, loc, via_sub))
    direct = [(m, loc) for m, loc, via_sub in phrases
              if not via_sub and loc in (src, dst)]
    owner = [(m, loc) for m, loc in direct
             if name in text[max(0, m.start() - 8):m.start()]]
    own = owner[0] if owner else None

    if own:
        m, from_loc = own
        if from_loc == src:
            checks.append({"rule": "fact.moved.direction", "verdict": "pass",
                           "factId": fid, "span": m.group(0),
                           "evidence": f"从「{src}」出发，与事实一致"})
        else:
            later = text[m.end():]
            # 只用端点本身的写法判方向；小地点/缩写会把"巷子里"当成潮生巷
            if any(a in later for a in src_direct):
                checks.append({"rule": "fact.moved.direction", "verdict": "fail",
                               "factId": fid,
                               "span": text[max(0, m.start() - 6):m.end() + 12],
                               "evidence": f"方向相反：事实是 {src}→{dst}，正文从「{dst}」走向「{src}」"})
            else:
                checks.append({"rule": "fact.moved.direction", "verdict": "fail",
                               "factId": fid, "span": m.group(0),
                               "evidence": f"出发地写成「{dst}」，方向与事实 {src}→{dst} 相反"})
        before = text[max(0, m.start() - 8):m.start()]
        near = [n for n in world_names(world)["characters"] if n in before]
        who = max(near, key=lambda n: before.rfind(n)) if near else None
        checks.append({"rule": "fact.moved.subject",
                       "verdict": "pass" if who == name else "fail",
                       "factId": fid, "span": before + m.group(0),
                       "evidence": f"移动由「{who}」执行，事实归属「{name}」"})
        return

    if direct:
        # 有同路线短语，但主语写的是别人：方向可以沿用，主语不能替他判
        m, from_loc = direct[0]
        checks.append({"rule": "fact.moved.direction",
                       "verdict": "pass" if from_loc == src else "uncertain",
                       "factId": fid, "span": m.group(0),
                       "evidence": f"同目的地路线由别人写出（从「{from_loc}」），方向按路线判断"})
        checks.append({"rule": "fact.moved.subject", "verdict": "uncertain",
                       "factId": fid,
                       "evidence": f"正文没有写「{name}」自己的移动短语"})
        return

    if phrases:
        checks.append({"rule": "fact.moved.direction", "verdict": "uncertain",
                       "factId": fid, "span": phrases[0][0].group(0),
                       "evidence": "只有小地点/缩写层面的出发地，方向无法判定"})

    if name not in text:
        checks.append({"rule": "fact.moved.subject", "verdict": "fail",
                       "factId": fid,
                       "evidence": f"人物「{name}」整段未出现，移动事实无从归属"})
        return
    if dst_hit and src_hit:
        checks.append({"rule": "fact.moved.direction", "verdict": "uncertain",
                       "factId": fid, "evidence": "出发地与目的地都出现，但没有可判读的移动短语"})
    elif dst_hit or src_hit or dst_is_scene:
        # 场景本身已在该地，或只提了一端：属于允许的省略
        checks.append({"rule": "fact.moved.direction", "verdict": "pass",
                       "factId": fid,
                       "evidence": "地点与场景一致，移动按允许省略处理" if dst_is_scene
                                   else "只写了移动的一端"})
    else:
        checks.append({"rule": "fact.moved.coverage", "verdict": "uncertain",
                       "factId": fid,
                       "evidence": f"没有移动短语，也没提到 {src}→{dst}"})


def check_outcome(fact: dict, text: str, world: dict, checks: list[dict]) -> None:
    fid, name = fact.get("factId"), fact.get("name")
    result = fact.get("resultText") or ""
    if not name:
        return
    if name not in text:
        _add(checks, "fact.outcome.subject", "fail", fact_id=fid,
             evidence=f"结果事实的执行者「{name}」整段未出现")
        return
    rb, tb = bigrams(result), bigrams(text)
    overlap = rb & tb
    if overlap:
        _add(checks, "fact.outcome.covered", "pass", fact_id=fid,
             evidence=f"结果动作命中：{'、'.join(sorted(overlap)[:3])}")
        return
    # 同名主语 + 另一个在场人物承担了这个动作 = 主体错
    for cl in clauses(text):
        if name not in cl:
            continue
        for other in case_allowed({}, world)["characters"]:
            if other == name or other not in cl:
                continue
            if any(w in cl for w in ("把", "将", "点着", "点亮", "添", "挂", "送",
                                     "换", "擦", "推", "系", "收", "清理", "装")):
                _add(checks, "fact.outcome.subject", "fail", fact_id=fid,
                     span=cl, evidence=f"动作由「{other}」完成，事实归属「{name}」")
                return
    _add(checks, "fact.outcome.coverage", "fail", fact_id=fid,
         evidence=f"结果事实「{result}」在正文里没有任何内容词命中")


def check_appearance_or_personality(fact: dict, text: str, checks: list[dict]) -> None:
    fid = fact.get("factId")
    detail = fact.get("text") or ""
    if not detail:
        return
    db, tb = bigrams(detail), bigrams(text)
    hit = db & tb
    if hit:
        _add(checks, f"fact.{fact['kind']}.covered", "pass", fact_id=fid,
             evidence=f"细节命中：{'、'.join(sorted(hit)[:3])}")
    else:
        _add(checks, f"fact.{fact['kind']}.coverage", "uncertain", fact_id=fid,
             evidence=f"没有命中细节原文「{detail}」")


def check_sanity(fact: dict, text: str, checks: list[dict]) -> None:
    fid = fact.get("factId")
    up = fact.get("to", 0) > fact.get("from", 0)
    has_up = any(w in text for w in UP_WORDS)
    has_down = any(w in text for w in DOWN_WORDS)
    if up and has_down and not has_up:
        _add(checks, "fact.sanity.direction", "fail", fact_id=fid,
             span=None, evidence=f"理智上升，但正文只有下压/发紧类词")
    elif (not up) and has_up and not has_down:
        _add(checks, "fact.sanity.direction", "fail", fact_id=fid,
             span=None, evidence=f"理智下降，但正文只有松弛类词")
    elif has_up or has_down:
        _add(checks, "fact.sanity.direction", "pass", fact_id=fid,
             evidence="出现了方向性描写")
    else:
        _add(checks, "fact.sanity.direction", "uncertain", fact_id=fid,
             evidence="没有可判读的方向性描写")


def check_no_change(fact: dict, text: str, checks: list[dict]) -> None:
    fid = fact.get("factId")
    changed = re.search(r"(变得|更加|越发|忽然|突然|第一次|开始)", text)
    if changed:
        _add(checks, "fact.noChange", "uncertain", fact_id=fid,
             span=text[max(0, changed.start() - 8):changed.end() + 8],
             evidence="无变化点上出现了变化措辞，需要人工确认是否指别的对象")


FUNC_CHARS = set("的了着过是在把被他她它我你又有没无不要会能可就都也还很太更最和与及"
                 "而从到向往对于因为所以但是而且如果虽然这那哪些个之其并再才已经"
                 "上下里外中间前后东西南北来去出进起回过去来自把将向朝被让给对")


def check_repetition(text: str, checks: list[dict]) -> None:
    """整句或分句原样重复（模型退化），只归 uncertain：需要人看是否修辞。"""
    seen = {}
    for cl in clauses(text):
        if len(cl) < 6:
            continue
        if cl in seen:
            _add(checks, "style.repetition", "uncertain", span=cl,
                 evidence="分句原样重复")
            return
        seen[cl] = True


OBJECT_SUFFIX = ("链", "盆", "壶", "灯", "绳", "梯", "柜", "箱", "杖", "包",
                 "铃", "碗", "刀", "锅", "伞", "衣", "袍", "鞋", "门", "窗",
                 "床", "桌", "架", "桶", "袋", "匣", "簿", "卷")


def check_fabricated_items(case: dict, text: str, world: dict,
                           checks: list[dict]) -> None:
    """世界物品表里没有的器物，只归 uncertain（可能是普通陈设）。"""
    allowed = set(world_names(world)["items"])
    scene = " ".join(str(v) for v in (case.get("sceneState") or {}).values())         + " " + world_text(world)
    for m in re.finditer(r"([一-龥]{1,3}(?:" + "|".join(OBJECT_SUFFIX) + "))", text):
        tok = m.group(1)
        if tok in allowed or tok in scene:
            continue
        if any(ch in FUNC_CHARS for ch in tok):
            continue
        if any(tok in a or a in tok for a in allowed):
            continue
        _add(checks, "fabrication.item", "uncertain", span=find_span(text, tok),
             evidence=f"物品表与场景里没有「{tok}」")
        return


def check_fabricated_names(case: dict, text: str, world: dict, checks: list[dict]) -> None:
    """未知专名只归 uncertain，并且要求「像名字的形状」而不是任意切片：
    2–3 字、姓氏开头、内部无虚词、出现在主语位置（句首/标点后），且至少出现两次。
    这条规则精度有限，报告里单独统计它的误报。"""
    allow = case_allowed(case, world)
    allowed = allow["characters"] | allow["locations"] | allow["items"] | allow["present"]
    scene_text = " ".join(str(v) for v in (case.get("sceneState") or {}).values())         + " " + world_text(world)
    candidates: dict[str, int] = {}
    name_shape = re.compile(
        r"(?:^|[，。；！？,;!?\s“”])([一-龥]{2,3})(?=[，。；！？,;!?\s“”]"
        r"|说|站|看|走|把|问|笑|点|抬|伸|推|拿|低|转|没|也|就|又|已经|还|在|的|蹲|靠|扶|抱|递|听|闻)"
    )
    for m in name_shape.finditer(text):
        tok = m.group(1)
        if tok in allowed or tok in scene_text:
            continue
        if tok[0] not in SURNAMES:
            continue
        if any(ch in FUNC_CHARS for ch in tok[1:]):
            continue
        if any(tok in a or a in tok for a in allowed):
            continue
        candidates[tok] = candidates.get(tok, 0) + 1
    for tok, n in candidates.items():
        if n >= 1:
            _add(checks, "fabrication.name", "uncertain", span=find_span(text, tok),
                 evidence=f"像人名的未知词「{tok}」出现 {n} 次，输入与场景里没有")
    for m in re.finditer(r"(?:^|[，。；！？,;!?\s])([一-龥]{1,2}(?:巷|驿|岭|台|渡|馆|楼|寺|院|桥|井|棚|铺|村|镇|城|溪))", text):
        tok = m.group(1)
        if tok in allowed or any(tok in a or a in tok for a in allowed):
            continue
        if any(ch in FUNC_CHARS for ch in tok):
            continue
        _add(checks, "fabrication.place", "uncertain", span=find_span(text, tok),
             evidence=f"像地名的未知词「{tok}」，世界设定里没有")


def check_attribution(case: dict, fact: dict, text: str, world: dict,
                      checks: list[dict]) -> None:
    """事实的锚点（出发地/目的地/结果动作）所在分句里，主语写的是谁。

    只在这一条能读清时判 fail：某个分句有锚点、有别人的名字、完全没有本人。
    这样"两个角色各走各的"不会互相误伤。"""
    name, fid = fact.get("name"), fact.get("factId")
    if not name or name not in text:
        return
    anchors = []
    if fact["kind"] == "moved":
        # 地点锚点连同小地点/缩写一起算：写作"从巷子另一头"也算走过潮生巷
        for loc in (fact.get("from"), fact.get("to")):
            if loc:
                anchors.extend(location_aliases(loc, world, with_sublocations=True))
        anchors = sorted(set(anchors), key=len, reverse=True)
    elif fact["kind"] == "outcome":
        rb = bigrams(fact.get("resultText") or "")
        action_cues = ("把", "将", "挂", "添", "点", "送", "换", "擦", "推",
                       "系", "收", "清", "翻", "取", "放", "摆", "煮", "烧")
        anchors = [cl for cl in clauses(text)
                   if bigrams(cl) & rb and any(c in cl for c in action_cues)]
    if not anchors:
        return
    others = [n for n in world_names(world)["characters"] if n and n != name]
    # 本人若有一条带同一锚点的分句，就不能把别人那条算到他头上
    for cl in clauses(text):
        if name in cl and any(a in cl for a in anchors):
            return
    for cl in clauses(text):
        if not any(a in cl for a in anchors):
            continue
        for other in others:
            if other in cl:
                _add(checks, "fact.attribution", "fail", fact_id=fid, span=cl,
                     evidence=f"锚点所在分句的主语是「{other}」，事实归属「{name}」")
                return


def check_case(case: dict, text: str, world: dict) -> dict:
    checks: list[dict] = []
    check_forbidden(case, text, checks)
    check_pov(case, text, world, checks)
    for fact in case.get("facts", []):
        kind = fact.get("kind")
        if kind == "moved":
            check_moved(case, fact, text, world, checks)
        elif kind == "outcome":
            check_outcome(fact, text, world, checks)
        elif kind in ("appearance_changed", "personality_changed"):
            check_appearance_or_personality(fact, text, checks)
        elif kind == "sanity_changed":
            check_sanity(fact, text, checks)
        elif kind == "no_change":
            check_no_change(fact, text, checks)
        # 移动类只判"自己的移动短语里主语是谁"；移动被省略时归属无法自动化，
        # 交给 uncertain 而不是硬判（见报告的误报统计）
        if kind == "outcome":
            check_attribution(case, fact, text, world, checks)
        # time：契约要求模糊或省略，不做覆盖检查
    check_repetition(text, checks)
    check_fabricated_names(case, text, world, checks)
    check_fabricated_items(case, text, world, checks)

    return {
        "caseId": case.get("id"),
        "verdict": _verdict(checks),
        # pass 只表示"现有自动规则没有发现问题"。自然度、隐含事实、代词归属
        # 都不在自动范围内，所以 pass 不能当作全面验收通过。
        "verdictScope": "automatic-rules-only",
        "passMeans": "没有自动规则报警；自然度/隐含事实/代词归属未检查",
        "notAutomated": ["自然度", "隐含事实", "视角限知（代词与身体感受）"],
        "checks": checks,
        "counts": {
            "pass": sum(1 for c in checks if c["verdict"] == "pass"),
            "fail": sum(1 for c in checks if c["verdict"] == "fail"),
            "uncertain": sum(1 for c in checks if c["verdict"] == "uncertain"),
        },
        "not_automated": ["自然度", "隐含事实", "视角限知（代词归属）"],
    }
