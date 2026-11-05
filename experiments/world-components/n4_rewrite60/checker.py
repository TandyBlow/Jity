# 叙事目标检查器 v1（五层）
#
# 设计约束：每一层都必须先通过**人工参考答案**（60/60）。过不了就改规则或
# 补别名表，绝不放宽到"模型能过"。
#
# 用法：
#   python -X utf8 checker.py            # 校准：人工参考答案 60/60 + 篡改测试
#   python -X utf8 checker.py --freeze   # 校准通过后冻结（写哈希与阈值）
import hashlib, json, pathlib, re, sys

HERE = pathlib.Path(__file__).parent
CORPUS = HERE / "corpus140.jsonl"
WORLD = HERE.parent / "n4_narrative_dev" / "world.json"

# ---------------------------------------------------------------- 基础词表
FUNC = set("的了着过是在把被他她它我你又有没无不要会能可就都也还很太更最和与及"
           "而从到向往对于因为所以但是而且如果虽然这那哪些个之其并再才已经"
           "上下里外中间前后东西南北来去出进起回过去来自"
           "一二三四五六七八九十几两半每各某")
PUNCT = re.compile(r"[\s，,。．.；;：:！!？?、…—－\-\"'“”‘’（）()《》「」]")

# 理智方向词（手工）：只用来判"有没有表达方向"，不作为硬门
UP_WORDS = ["清醒", "清亮", "稳", "松下来", "松开", "不那么急", "踏实", "定",
            "排开", "安静", "亮起来", "放心"]
DOWN_WORDS = ["空了一块", "空了一下", "发紧", "发冷", "凉", "漏掉", "攥", "乱",
              "薄了一层", "薄下去", "沉下去", "退下去", "沉进", "压人", "不安",
              "抖", "磨掉", "磨掉一层", "磨", "漏", "退", "沉", "冷"]

# 时间数值：阿拉伯数字或中文数字 + 时长单位
DURATION_RE = re.compile(
    r"[0-9０-９]+\s*(秒|分钟|小时|天|日|刻)"
    r"|[一二三四五六七八九十两半]+\s*(秒|分钟|小时|时辰|刻钟?)")
DIGIT_RE = re.compile(r"[0-9０-９]")
PRONOUNS = ("他", "她", "我", "自己")
NEG_RE = re.compile(r"(并没有|并没有把|没有|没能|没把|没|未能|未|无法|不曾|并未)")

# 常见汉族姓氏。只用来发现“人名形状的未知词”，单靠这一条不判违规：
# 还必须重复出现且输入里没有（见 _unknown_names）。
SURNAMES = set(
    "赵钱孙李周吴郑王冯陈蒋沈韩杨朱秦许何吕张孔曹严华金魏陶姜谢邹柏窦章苏潘葛"
    "范彭郎鲁韦马苗凤花方俞任袁柳唐薛雷贺倪汤罗毕郝安常于傅齐康伍余顾孟平黄穆"
    "萧尹姚邵汪毛米贝戴谈宋庞熊纪舒项祝董梁杜阮蓝闵席季贾路娄江童颜郭梅盛林钟"
    "徐邱骆高夏蔡田樊胡凌霍万卢莫房裘解丁宣邓郁单杭洪包左石崔吉龚程邢裴陆荣翁"
    "荀羊惠甄曲封储靳段富焦巴牧山谷车侯班仲伊宫宁仇甘厉祖武符刘景詹龙叶黎薄印"
    "宿白怀蒲鄂索赖卓屠蒙池乔闻党翟谭劳姬申扶冉雍桑桂牛通边燕尚农温庄晏柴阎"
    "慕连茹艾容向古易慎戈廖衡步耿满弘匡国寇广文欧沃利蔚越隆师巩聂晁融冷辛简饶"
    "曾沙养鞠丰巢关查荆红游权盖益桓")
# 人名后面常见的谓语开头：用来确认这个未知词是“人”，不是普通名词
NAME_FOLLOW = ("说", "道", "问", "答", "站", "坐", "蹲", "走", "跑", "进",
               "退", "抬", "低", "转", "伸", "看", "笑", "把", "将", "没",
               "不", "也", "就", "却", "便", "又",
               "皱", "叹", "摇", "点", "靠", "贴", "扶", "拉", "推", "提", "拎",
               "握", "攥", "盯", "望", "听", "摸", "背", "弯", "跪", "趴", "侧",
               "回", "停", "应", "笑", "愣", "怔")
# 常见词尾巴，避免把“石头/白雾/冷风”当成名字
NOT_NAME_TAIL = set("雾雨雪风潮水面边声音色影子时候里外头上下前后中间光气火土木石铁水天云山路船门窗墙")
# 名字里不会出现的虚词。第二/第三个字是这些，说明是“姓+词”的巧合，
# 比如“越是看”“冷得”“沈砚先”。
NOT_NAME_MID = set("是不的了着过在和与把被就都也又才很太更最得地之其而且并再向从对为以于"
                   "先正半声撞来去看望听想")


def _unknown_names(text, n_inp, world):
    """找出“人名形状、输入里没有”的词：姓氏开头、2–3 字、至少重复两次，
    且至少一处后面跟着人常做的动作。返回 [(原词, 归一后)]。"""
    if not text:
        return []
    known = {norm(n) for n in world["names"]} | set()
    seen, out = {}, []
    # 标点换成 "|" 而不是直接删掉，否则判断不了“是不是句首”。
    nt = PUNCT.sub("|", text)
    for i, ch in enumerate(nt):
        if ch not in SURNAMES:
            continue
        for L in (3, 2):
            tok = nt[i:i + L]
            if len(tok) != L:
                continue
            if "|" in tok or tok in known or tok in n_inp:
                continue
            if tok[1] in NOT_NAME_MID or tok[-1] in NOT_NAME_MID:
                continue
            # 已知名字从同一位置开始（“沈砚先/韩渡正”），说明这是名字+后一个字
            if any(norm(nm).startswith(tok[:2]) for nm in known):
                continue
            if tok[-1] in NOT_NAME_TAIL:
                continue
            nxt = nt[i + L:i + L + 1]
            looks_like_person = nxt in NAME_FOLLOW
            # 只出现一次也算：但必须在句首（前一个字是句末标点或开头）。
            # 人名首次出现基本都在主语位置，名词很少这么用。
            clause_start = i == 0 or nt[i - 1] == "|"
            seen.setdefault(tok, [0, False, False])
            seen[tok][0] += 1
            seen[tok][1] = seen[tok][1] or looks_like_person
            seen[tok][2] = seen[tok][2] or (looks_like_person and clause_start)
    for tok, (cnt, verb, _start) in seen.items():
        if verb and (cnt >= 2 or seen[tok][2]):
            out.append((tok, tok))
    return out

# 他人内心确知的误写（软检查）
OMNISCIENT_RE = re.compile(
    r"(心里|心中|内心|心底)(很|也|却|都)?(知道|明白|清楚|觉得|想|认定|踏实)")


def norm(s):
    return PUNCT.sub("", s or "")


def content_bigrams(s):
    s = norm(s)
    out = set()
    for i in range(len(s) - 1):
        a, b = s[i], s[i + 1]
        if a in FUNC or b in FUNC:
            continue
        out.add(s[i:i + 2])
    return out


def coverage(needle, hay):
    """needle 的实词双字有多少出现在 hay 里。"""
    N = content_bigrams(needle)
    if not N:
        return 1.0
    return len(N & content_bigrams(hay)) / len(N)


def clauses(text):
    """按句末与逗号切成小句。矛盾判断必须落到小句，不能整句扫。"""
    out = []
    for sent in re.split(r"(?<=[。；！？])", text or ""):
        for cl in re.split(r"(?<=[，,、：])", sent):
            if cl.strip():
                out.append(cl.strip())
    return out


ADV_TAIL = re.compile(r"(已经|仍然|还|也|却|都|已|就|又|才|很|太|更|最|再|仍)+")
# 小句开头的时间/转折填充词，去掉后剩下的才是主语
LEAD_FILLER = re.compile(
    r"^(又过了一会儿|过了一会儿|过了好一会儿|隔了一会儿|过了片刻|半晌|片刻|"
    r"紧接着|后来|之后|随后|接着|然后|这时才|这时|忽然间|忽然)+")


def clause_head(clause, pred):
    """小句里谓词之前的主语（去掉副词尾和量词头，保留定语）。
    「近处的灯」/「远处的灯」必须保留区别，否则会把两盏灯判成同一盏。
    「钟架旁的灯还亮着」→「钟架旁的灯」。"""
    i = clause.find(pred)
    if i <= 0:
        return ""
    pre = ADV_TAIL.sub("", PUNCT.sub("", clause[:i]))
    return strip_classifier(LEAD_FILLER.sub("", pre))


CLASSIFIER_HEAD = re.compile(r"^(那|这|一|两|几|每|另|别的|别)?(盏|个|只|根|块|片|条|张|把|道|扇|间|座|支)")


def strip_classifier(w):
    return CLASSIFIER_HEAD.sub("", w or "")


def same_thing(a, b):
    """两个主语是否指同一物体：必须字面相同。
    后缀匹配会把「灯」「警示灯」「近处的灯」「远处的灯」混成一盏，
    而正文里到底几盏灯规则看不出来，所以只认字面相同。"""
    return bool(a) and a == b


# ---------------------------------------------------------------- 世界名字表
_WORLD_CACHE = {}


def load_world_names(path=None):
    """读一个世界的实体表。测试别的世界时必须显式传路径，
    否则判据会拿旧世界的名字表去核对，测到的是“表缺失”而不是核对能力。"""
    p = pathlib.Path(path) if path else WORLD
    key = str(p.resolve())
    if key in _WORLD_CACHE:
        return _WORLD_CACHE[key]
    w = json.loads(p.read_text(encoding="utf-8"))
    locs, subs = {}, {}
    for lid, L in w["locations"].items():
        locs[lid] = L["name"]
        subs[lid] = [s["name"] for s in L.get("sublocations") or []]
    chars = {cid: c["name"] for cid, c in w["characters"].items()}
    items = {iid: i["name"] for iid, i in w["items"].items()}
    features = []
    for L in w["locations"].values():
        features += L.get("features") or []
    names = set(locs.values()) | set(chars.values()) | set(items.values())
    for v in subs.values():
        names |= set(v)
    names |= set(features)
    out = {"locs": locs, "subs": subs, "chars": chars, "items": items,
           "names": sorted(n for n in names if n), "path": key}
    _WORLD_CACHE[key] = out
    return out


def world_for(row, base=None):
    """行里带 world 字段就用那一份，否则用默认世界。"""
    rel = (row or {}).get("world")
    if not rel:
        return load_world_names()
    base = pathlib.Path(base) if base else HERE
    return load_world_names(base / rel)


def world_ref_errors(row, world):
    """这一行的事实引用了世界实体表里没有的实体 → 数据错，不是判定结果。

    跨世界测试时这种错最容易被误读成“判据抓不到”，所以单独报。"""
    known = (set(world["chars"].values()) | set(world["items"].values())
             | set(world["locs"].values())
             | {x for v in world["subs"].values() for x in v})
    errs = []
    for f in (row or {}).get("facts") or []:
        nm = f.get("name")
        if nm and nm not in known:
            errs.append(f"{f.get('factId')}: 主体 {nm} 不在实体表")
        if f.get("kind") == "moved":
            for k in ("from", "to"):
                v = f.get(k)
                if isinstance(v, str) and v and v not in known:
                    errs.append(f"{f.get('factId')}: {k}={v} 不在实体表")
    return errs


def alias_set(loc_name, world):
    """一个地点名的合法替代表达：自己 + 子地点名 + 父地点名。
    「到了旧灯塔」可以替代「到了塔顶」；反过来「到了塔顶」不能替代
    「到了旧灯塔」——所以按方向加，不双向合并。"""
    subs = world["subs"]
    out = {loc_name}
    for lid, nm in world["locs"].items():
        if nm == loc_name:
            out |= set(subs.get(lid) or [])
        for sub in subs.get(lid) or []:
            if sub == loc_name:
                out.add(nm)
    return out


# ---------------------------------------------------------------- 检查
COVER_MIN = 0.35   # 小句算“在讲这条事实”的最低实词覆盖率


def check_row(row, world, cfg):
    text = row["target"]
    facts = row["facts"]
    inp = row["input"]
    n_text, n_inp = norm(text), norm(inp)
    V, W, P = [], [], []          # violation / 未表达 / 待人工

    in_names = {n for n in world["names"] if norm(n) in n_inp}
    char_names = {n for n in world["chars"].values() if norm(n) in n_inp}
    text_chars = {c for c in char_names if norm(c) in n_text}
    R = []                        # 待复核：规则判不了，不算通过
    N = []                        # 提示：写法正常但规则对不上，不影响结论

    # ---- 第一层：硬格式
    if DIGIT_RE.search(text):
        V.append({"layer": 1, "code": "digit", "detail": "正文出现阿拉伯数字"})
    if "「" in text or "」" in text:
        V.append({"layer": 1, "code": "bracket", "detail": "出现书名号任务原文"})
    for tmpl in ("移动｜", "结果｜", "理智｜", "事实：", "分组：", "正文：", "｜"):
        if tmpl in text:
            V.append({"layer": 1, "code": "template", "detail": f"输入模板残留 {tmpl}"})
            break
    if "—" in text:
        V.append({"layer": 1, "code": "em-dash",
                  "detail": "正文出现破折号（用户要求禁用）"})
    half = re.findall(r"[,;:!?]|\.(?!\d)", text)
    if half:
        V.append({"layer": 1, "code": "halfwidth-punct",
                  "detail": f"正文出现半角标点：{''.join(sorted(set(half)))}"})
    if not re.search(r"[。！？…]$", text.strip()):
        V.append({"layer": 1, "code": "truncated", "detail": "结尾不是完整句"})
    if len(n_text) < cfg["minChars"]:
        V.append({"layer": 1, "code": "too-short",
                  "detail": f"正文只有 {len(n_text)} 字"})

    # ---- 第一层补：复读与句子崩裂
    flat = norm(text)
    if len(flat) > 12:
        worst, worst_span = 0, ""
        for L in range(4, len(flat) // 2 + 1):
            hit = next((flat[i:i + L] for i in range(len(flat) - L + 1)
                        if flat.count(flat[i:i + L]) >= 2), None)
            if hit:
                worst, worst_span = L, hit
        if worst > cfg["maxRepeatedSpan"]:
            V.append({"layer": 1, "code": "repeated-span",
                      "detail": f"连续 {worst} 字重复：{worst_span[:16]}"})
    from collections import Counter as _C
    c4 = _C(flat[i:i + 4] for i in range(max(0, len(flat) - 3)))
    over = [(k, v) for k, v in c4.items() if v > cfg["max4gram"]]
    if over:
        k, v = max(over, key=lambda kv: kv[1])
        V.append({"layer": 1, "code": "repeated-4gram",
                  "detail": f"「{k}」重复 {v} 次"})
    sents_all = [x for x in re.split(r"(?<=[。；！？])", text) if x.strip()]
    long_s = [x for x in sents_all if len(norm(x)) > cfg["maxSentence"]]
    if long_s:
        V.append({"layer": 1, "code": "sentence-runaway",
                  "detail": f"单句 {len(norm(long_s[0]))} 字，最长允许 {cfg['maxSentence']}"})
    # 把人物放进物品里（"站在木桌的抽屉里"）
    # 只查"人物"被放进物品里：动词前 6 个字内必须有人的名字或代词，
    # 否则"雨落在院子里的水沟里"这类写景会误判。
    for m in re.finditer(r"(站在|坐在|走进|进入|钻进|陷进)[^，。；]{0,10}的[^，。；]{0,4}(里|中)",
                         text):
        head = text[max(0, m.start() - 6):m.start()]
        if any(w in head for w in ("他", "她", "沈砚")) or any(
                n in head for n in char_names):
            V.append({"layer": 1, "code": "impossible-space",
                      "detail": f"人物被放进物品内部：{m.group(0)[:14]}"})
            break

    # ---- 第一层补：自相矛盾（按小句、比对象，只有同一物体才算）
    # v4 是整句扫两个词，于是「手背冰凉，灯的铁皮发烫」「远处的灯灭了，
    # 警示灯还亮着」都被误判。现在要求两处说的必须是同一个物体。
    def _sents(t):
        return [x for x in re.split(r"(?<=[。；！？])", t) if x.strip()]
    CONTRADICT = [
        ("lamp-out-lit", r"(灭了|熄了|熄灭)", r"(亮着|照亮|点着)"),
        ("nobody-somebody", r"(没有人|没有人影|空着)",
         r"(沈砚|顾行舟|叶知微|阿棠|韩渡)"),
        ("empty-occupied", r"空着", r"(站着|坐着|蹲着)"),
        ("cold-hot", r"(发冷|冰凉|冻得)", r"(发烫|烧得|滚热)"),
    ]
    for code, a, b in CONTRADICT:
        fired = False
        for sent in _sents(text):
            cls = [c for c in re.split(r"(?<=[，,、：])", sent) if c.strip()]
            for i, ci in enumerate(cls):
                ma = re.search(a, ci)
                if not ma:
                    continue
                ha = clause_head(ci, ma.group(0))
                for j in range(i, len(cls)):
                    mb = re.search(b, cls[j])
                    if not mb:
                        continue
                    hb = clause_head(cls[j], mb.group(0))
                    if same_thing(ha, hb):
                        fired = True
                        break
                if fired:
                    break
            if fired:
                break
        if fired:
            V.append({"layer": 1, "code": f"contradiction:{code}",
                      "detail": "同一物体同时写成对立状态"})

    # ---- 第二层：抄袭输入（只查事实记录行）
    # 世界外貌描述本来就该复用（“厚纸簿，缺一页，边缘毛糙”写给模型就是要它
    # 用来描写），所以只查事实行被原样搬进正文。
    for line in inp.split("\n"):
        if not re.match(r"^(f\d+｜|移动｜|结果｜|理智｜|外貌｜|行为倾向｜|"
                        r"相对位置｜|新任务｜|无变化｜|时间｜)", line):
            continue
        ln = norm(line)
        if len(ln) < cfg["copyRun"]:
            continue
        # 整行事实被原样搬进正文才算抄；片段复用（照应世界描述、引用结果
        # 原文里的词）是正常的，不判。
        if len(ln) >= 12 and ln[2:] in n_text:
            V.append({"layer": 2, "code": "copied-input",
                      "detail": f"照抄输入事实行：{line[:24]}"})
            break

    # ---- 第三层：新增具名实体
    strict_names = (set(world["chars"].values()) | set(world["locs"].values())
                    | {x for v in world["subs"].values() for x in v}
                    | {x for x in world["items"].values() if len(x) >= 3})
    for n in strict_names:
        nn = norm(n)
        if len(nn) < 2:
            continue
        if nn in n_text and n not in in_names:
            V.append({"layer": 3, "code": "new-entity",
                      "detail": f"新增世界册里的名字：{n}"})

    # ---- 第四层：逐条事实
    for f in facts:
        kind = f.get("kind")
        name = f.get("name")
        base = {"factId": f.get("factId"), "kind": kind}

        if kind == "no_change":
            continue  # 无变化的点允许正文完全不提，也不要求表达
        if kind == "time":
            if DURATION_RE.search(text):
                V.append({**base, "layer": 4, "code": "time-number",
                          "detail": "写出具体时长"})
            continue
        if kind == "sanity_changed":
            if DIGIT_RE.search(text) or "理智" in text or "精神值" in text:
                V.append({**base, "layer": 4, "code": "sanity-explicit",
                          "detail": "理智被直接写出来"})
                continue
            up = any(w in text for w in UP_WORDS)
            dn = any(w in text for w in DOWN_WORDS)
            want = "up" if f.get("to", 0) > f.get("from", 0) else "down"
            if not up and not dn:
                W.append({**base, "why": "没有可感的方向表达"})
            elif (want == "up" and dn and not up) or (want == "down" and up and not dn):
                W.append({**base, "why": f"方向词只在反面出现（应为{want}）",
                          "direction": want})
            continue

        # 其余种类都带主体
        is_char = f.get("entityGroup") == "characters" or name in char_names
        if name and norm(name) not in n_text:
            # 人物认不出来、物品不点名都是常态（只看见轮廓 / "灯芯" 没写名字），
            # 只记软项；真正要抓的是"写错人、写反方向"。
            W.append({**base, "why": f"主体 {name} 没有点名"})

        if kind == "moved":
            aliases = alias_set(f.get("to") or "", world)
            if not any(norm(a) in n_text for a in aliases if a):
                W.append({**base, "why": f"目的地「{f.get('to')}」没有点名"})
            # 反向检测：从<目的地><到某处>
            rev = re.findall(r"从([^，。；]{1,8}?)(?:回到|来到|走到|到|回)([^，。；]{1,10})",
                             text)
            for a, b in rev:
                if any(norm(x) in norm(a) for x in aliases if x) and \
                        norm(f.get("from") or "") in norm(b):
                    V.append({**base, "layer": 4, "code": "direction-reversed",
                              "detail": f"方向写反：从{a}到{b}"})
                    break
            continue

        if kind in ("outcome", "task_achieved"):
            key = f.get("resultText") or f.get("goal") or ""
            c = coverage(key, text)
            need = cfg["contentMin"].get(kind, 0.2)
            if c < need:
                W.append({**base, "why": f"结果内容覆盖 {c:.2f}（需 {need}）",
                          "coverage": round(c, 2), "mandatory": True})
            continue

        if kind in ("appearance_changed", "appearance_removed",
                    "personality_changed", "personality_removed"):
            key = f.get("text") or ""
            c = coverage(key, text)
            if c < max(cfg["contentMin"].get(kind, 0.0), 0.5):
                W.append({**base, "why": f"外观/性情内容覆盖 {c:.2f}",
                          "coverage": round(c, 2)})
            if kind.startswith("personality") and name and name != (
                    row.get("pov") or ""):
                for m in OMNISCIENT_RE.finditer(text):
                    seg = text[max(0, m.start() - 12):m.end() + 8]
                    if name in seg or "他" in seg or "她" in seg:
                        V.append({**base, "layer": 4, "code": "other-inner-certain",
                                  "detail": f"把他人的性情写成确知的内心：{seg}"})
                        break
            continue

        if kind == "position_relative":
            tgt = f.get("targetName") or ""
            rel = {"under": "下方", "above": "上方", "beside": "旁边",
                   "in_front_of": "前方", "behind": "后方"}.get(
                       f.get("relation"), "")
            if tgt and norm(tgt) not in n_text:
                W.append({**base, "why": f"目标 {tgt} 没出现"})
            elif rel and not any(w in text for w in
                                 (rel, "手边", "脚边", "边上", "身旁", "近旁")):
                W.append({**base, "why": f"关系词「{rel}」没出现"})
            continue

        if kind == "subtask_added":
            c = coverage(f.get("goal") or "", text)
            if c < cfg["contentMin"]["subtask_added"]:
                W.append({**base, "why": f"新任务内容覆盖 {c:.2f}",
                          "coverage": round(c, 2), "mandatory": True})
            continue

    # ---- 第四层补：词面覆盖分不出来的错（换主体、否定、新增无名人物）
    # 这些规则都是“有证据才报”：拿不准就进复核，绝不当通过。
    for f in facts:
        base = {"factId": f.get("factId"), "kind": f.get("kind")}
        name = f.get("name")
        key4 = f.get("resultText") or f.get("goal") or f.get("text") or ""
        if not (name and key4):
            continue
        if f.get("entityGroup") != "characters" and name not in char_names:
            continue
        # 只有“谁做了这件事”会改变事实的种类才查绑定；新任务/位置关系问的是内容
        # 和物件，跟主语无关。
        if f.get("kind") not in ("moved", "outcome", "appearance_changed",
                                 "appearance_removed", "personality_changed",
                                 "personality_removed"):
            continue
        covers = [cl for cl in clauses(text)
                  if len(norm(cl)) >= 4 and coverage(key4, cl) >= COVER_MIN]
        if not covers:
            continue
        # 主体绑定按「整句」判：汉语经常承前省主语，「他抓住灯杆…手背擦破一块」
        # 同一句里的后半段没有主语也算绑定。否定则要看局部，所以另用 covers。
        bound = any(norm(name) in norm(s) or any(p in s for p in PRONOUNS)
                    for s in _sents(text)
                    if any(cl in s for cl in covers))

        def _lead_actor(clause):
            """小句开头的主语是谁：返回 (角色名 或 None, 是否代词开头)。"""
            head = LEAD_FILLER.sub("", PUNCT.sub("", clause))
            for c in text_chars:
                if head.startswith(norm(c)):
                    return c, False
            return None, any(head.startswith(p) for p in PRONOUNS)

        # 两句人同在一句时，句级“出现过主体”不能证明这一小句的主语就是他。
        # 只在“承载动作的小句换了别的角色当主语”时降级为复核。
        mismatch = False
        for cl in covers:
            # 带否定词的小句是在说“某人没做”，不是把这条动作记到某人头上，
            # 交给下面的否定规则处理。
            if NEG_RE.search(cl):
                continue
            who, pron = _lead_actor(cl)
            if who and who != name:
                R.append({**base, "code": "actor-mismatch",
                          "why": f"讲这条事实的小句主语是 {who}，事实主体是 {name}"})
                mismatch = True
                break
        if not bound and not mismatch:
            # 「谁做的」规则判不了：中文可以承前省主语，也可以把患者写在前面
            # （“把人逼退到石阶口”写成“韩渡退到石阶口”）。所以这里只记复核，
            # 记下正文在这一句里点了谁，交给人工或语义核对。
            # 主语可能在上一个小句里（“韩渡从潮生巷过来，把系泊绳绕了三圈”），
            # 所以按“讲这条事实的整句”找别人，不只看动词那一小句。
            cover_sents = [s for s in _sents(text) if any(cl in s for cl in covers)]
            named_here = [c for c in text_chars if c != name
                          and any(norm(c) in norm(sn) for sn in cover_sents)]
            # 分两种：
            #   小句里点了别的角色 → 复核。“全篇别处点过名”不能证明这一句的
            #   动作归属正确，所以不能再降成提示。
            #   只用了身体部位/“两个人”这类指代、没有点名别人 → 正常写法，提示。
            why = f"讲这条事实的小句主语不是 {name}"
            if named_here:
                why += f"，而是 {'/'.join(named_here)}"
                R.append({**base, "code": "actor-unclear", "why": why})
            else:
                N.append({**base, "code": "actor-elided", "why": why})
        # 主体全篇没点名、正文却点名了别人 —— 不管这句有没有代词，都进复核。
        # 代词到底指谁，规则判不出来。
        if norm(name) not in n_text and (text_chars - {name}):
            R.append({**base, "code": "actor-unnamed",
                      "why": f"事实主体 {name} 全篇未点名，只用代词或身体部件指代，"
                             f"正文点名了 {'/'.join(sorted(text_chars - {name}))}"})
        # 否定：逐小句扫，且要求这句否定说的是事实主体。
        # 「韩渡没有抓住灯杆」不能算成沈砚的结果被否定。
        key_bg = content_bigrams(key4)
        for cl in covers:
            if any(c != name and norm(c) in norm(cl) for c in text_chars) and                     norm(name) not in norm(cl):
                continue
            hit = None
            for m in NEG_RE.finditer(cl):
                seg = PUNCT.sub("", cl[m.end():m.end() + 3])
                if any(b in seg for b in key_bg):
                    hit = seg
                    break
            if hit:
                V.append({**base, "layer": 4, "code": "negated-result",
                          "detail": f"结果被写成否定：{hit}"})
                break

    # ---- 第四层补：两个人的出发地写串了
    moved = [f for f in facts if f.get("kind") == "moved" and f.get("name")]
    from_owner, from_alias = {}, {}
    for f in moved:
        nm = f.get("name")
        al = {norm(a) for a in alias_set(f.get("from") or "", world) if a}
        from_alias[nm] = al
        for a in al:
            from_owner.setdefault(a, set()).add(nm)
    for f in moved:
        nm, F = f.get("name"), f.get("from") or ""
        if f.get("entityGroup") != "characters" and nm not in char_names:
            continue
        if norm(nm) not in n_text:
            continue
        for cl in clauses(text):
            if norm(nm) not in norm(cl) or "从" not in cl:
                continue
            for place, owners in from_owner.items():
                if owners == {nm} or place in from_alias.get(nm, set()):
                    continue
                if norm(F) in norm(cl) or place not in norm(cl):
                    continue
                R.append({"factId": f.get("factId"), "kind": "moved",
                          "code": "origin-crossed",
                          "why": f"{nm} 的出发地是 {F}，正文却写成从 {place}"
                                 f"（那是 {'/'.join(sorted(owners))} 的出发地）"})
                break
            else:
                continue
            break

    # ---- 第四层补：册外新人物（人名形状 + 重复出现 + 输入里没有）
    for tok, n_tok in _unknown_names(text, n_inp, world):
        V.append({"layer": 3, "code": "new-name-outsider",
                  "detail": f"出现不在输入也不在世界册的人名：{tok}"})

    # ---- 第四层补：结果只对上一半（不是错，但规则不能确认完整）
    for f in facts:
        if f.get("kind") not in ("outcome", "task_achieved"):
            continue
        key = f.get("resultText") or f.get("goal") or ""
        if not key:
            continue
        c = coverage(key, text)
        if cfg["contentMin"]["outcome"] <= c < cfg["reviewCoverage"]:
            R.append({"factId": f.get("factId"), "kind": f.get("kind"),
                      "code": "partial-outcome",
                      "why": f"结果内容只对上 {c:.2f}，无法确认细节完整"})

    # ---- 第四层补：结果的收尾没对上（可能是漏掉了最后一步）
    for f in facts:
        if f.get("kind") not in ("outcome", "task_achieved"):
            continue
        key = f.get("resultText") or f.get("goal") or ""
        bg = []
        for i in range(len(norm(key)) - 1):
            pair = norm(key)[i:i + 2]
            if pair[0] in FUNC or pair[1] in FUNC:
                continue
            if pair not in bg:
                bg.append(pair)
        if len(bg) < 3:
            continue
        if not any(b in n_text for b in bg[-2:]):
            R.append({"factId": f.get("factId"), "kind": f.get("kind"),
                      "code": "result-tail-missing",
                      "why": f"结果结尾 {bg[-2:]} 在正文里找不到"})

    # ---- 第五层：主体归属提示（只记录，不影响结论）
    # 主体绑定已由第四层的 actor-swap / subject-unbound 判，这一层只留下
    # 句级线索供人工复核时参考，避免同一件事报两遍。
    sentences = [s for s in re.split(r"(?<=[。；！？])", text) if s.strip()]
    for f in facts:
        name = f.get("name")
        if f.get("kind") not in ("moved", "outcome", "appearance_changed"):
            continue
        if f.get("entityGroup") != "characters" and f.get("name") not in char_names:
            continue  # 归属只对人物有意义
        key = (f.get("to") or "") + (f.get("resultText") or "") + (f.get("text") or "")
        kn = norm(key)
        for s in sentences:
            sn = norm(s)
            # 只检查确实在讲这条事实的句子
            if kn and not any(kn[i:i + 2] in sn for i in range(max(0, len(kn) - 1))):
                continue
            others = [c for c in char_names if c != name and c in s]
            if others and name not in s and ("他" in s or "她" in s):
                P.append({"factId": f.get("factId"), "kind": f.get("kind"),
                          "sentence": s.strip()[:40],
                          "why": f"句中只有 {others} 和代词，缺少主体 {name}"})
                break

    must_missed = [w for w in W if w.get("mandatory")]
    if V or must_missed:
        verdict = "fail"
    elif R:
        verdict = "review"
    else:
        verdict = "pass"
    return {"id": row["id"], "verdict": verdict, "pass": verdict == "pass",
            "violations": V, "unexpressed": W, "pending": P, "review": R,
            "notes": N}


def tamper(text, facts, world, base_in=""):
    """把人工稿改坏，检查器必须抓到。"""
    out = []
    t = json.loads(json.dumps(text, ensure_ascii=False))
    out.append(("加数字时长", t.rstrip("。") + "，过了八分钟。"))
    out.append(("加书名号", t.rstrip("。") + "他办妥了任务「换灯芯」。"))
    # 换成一个"输入里没有"的世界册人名，才是真的新增实体
    in_n = norm(base_in)
    # 只用"人物名"做替换探针：地名/物件名换成别的词也可能合法
    outsider = next((n for n in world["chars"].values()
                     if norm(n) not in in_n), None)
    if outsider:
        out.append(("加世界册人名", t.replace("沈砚", outsider, 1)))
    out.append(("抄输入", t + "移动｜沈砚｜潮声巷到旧灯塔。"))
    out.append(("截断", t[: max(6, len(t) // 2)]))
    out.append(("空串", ""))
    # 关键失败模式：把理智写成数值、把方向写反、漏掉结果
    out.append(("理智写成数值", t.rstrip("。") + "他的理智降到了七。"))
    out.append(("方向写反", "沈砚从旧灯塔回到潮生巷，一路上没有停。"))
    # 漏掉结果：把与"结果"原文重合最高的那句删掉
    sents = [x for x in re.split(r"(?<=[。；！？])", t) if x.strip()]
    key = next((f.get("resultText") or "" for f in facts
                if f.get("kind") in ("outcome", "task_achieved")), "")
    if sents and key:
        # 删掉所有与结果原文有交集的句子（单句细节删改检出不了，见 KNOWN BLIND SPOTS）
        keep = [x for x in sents if coverage(key, x) == 0]
        out.append(("结果整段缺失", "".join(keep)))
    out.append(("复读", t.rstrip("。") + "他站着，站着站着站着站着，站着站着站着站着。"))
    out.append(("放进抽屉", t.rstrip("。") + "他站在木桌的抽屉里。"))
    out.append(("破折号", t.rstrip("。") + "他停了一下——雾还没散。"))
    out.append(("半角逗号", t.rstrip("。") + "他停了一下,雾还没散。"))
    out.append(("自相矛盾", t + "灯灭了，灯还亮着。"))
    return out


DEFAULT_CFG = {
    "minChars": 60, "copyRun": 8,
    "contentMin": {"outcome": 0.20, "task_achieved": 0.20, "subtask_added": 0.80},
    # 结果覆盖落在 [0.20, 0.45) 时，规则不能确认细节完整 —— 进复核，不算通过。
    # 参考稿 outcome 覆盖下界 0.20、中位 0.71；结尾双字缺失率 3/36。
    "reviewCoverage": 0.45,
    # 上界取自人工稿：最长重复片段 5 字、同一 4 字串最多 2 次、单句最长 49 字。
    "maxRepeatedSpan": 8, "max4gram": 2, "maxSentence": 65,
}


def main() -> int:
    """校准：人工参考答案的判决分布 + 结构篡改探针。

    注意：这个脚本只负责“格式/结构/词面”这一半。语义样本与冻结在
    score_probes.py 里，冻结记录必须由它生成，不能只看这里的 140 条。
    """
    rows = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines()
            if l.strip()]

    print(f"校准：人工参考答案 {len(rows)} 条")
    bucket = {"pass": [], "review": [], "fail": []}
    data_err = []
    for r in rows:
        world = world_for(r)
        errs = world_ref_errors(r, world)
        if errs:
            data_err.append((r["id"], errs[:2]))
            continue
        res = check_row(r, world, DEFAULT_CFG)
        bucket[res["verdict"]].append(res)
    n_ok = sum(len(v) for v in bucket.values())
    print(f"  可判 {n_ok} 条：通过 {len(bucket['pass'])} / 待复核 {len(bucket['review'])} / "
          f"误判 {len(bucket['fail'])}   （待复核不算通过）")
    if data_err:
        print(f"  数据错 {len(data_err)} 条（事实引用了世界实体表里没有的实体，"
              f"不计入上面的比率）：")
        for rid, errs in data_err[:5]:
            print("     ", rid, errs)
    notes = {}
    for res in bucket["pass"]:
        for x in res.get("notes", []):
            notes[x["code"]] = notes.get(x["code"], 0) + 1
    if notes:
        print("  提示（不影响结论）：" +
              "，".join(f"{k} {v}" for k, v in sorted(notes.items(),
                                                     key=lambda kv: -kv[1])))
    for res in bucket["review"][:8]:
        print("   ?", res["id"], [(x["code"], x["why"][:34]) for x in res["review"]][:2])
    for res in bucket["fail"][:8]:
        print("   X", res["id"],
              [(v["code"], v.get("detail")) for v in res["violations"]][:2],
              [(w["kind"], w.get("why")) for w in res["unexpressed"]
               if w.get("mandatory")][:2])

    base = next(r for r in rows if not world_ref_errors(r, world_for(r)))
    world = world_for(base)
    cases = tamper(base["target"], base["facts"], world, base["input"])
    caught = 0
    print()
    print("结构篡改探针：")
    for label, text in cases:
        res = check_row(dict(base, target=text), world, DEFAULT_CFG)
        hit = not res["pass"]
        caught += hit
        print(f"   {'抓到' if hit else '漏掉'}  {label}")
    print(f"  篡改捕获 {caught}/{len(cases)}")
    return 1 if bucket["fail"] or caught != len(cases) else 0


if __name__ == "__main__":
    raise SystemExit(main())
