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
CORPUS = HERE / "corpus60.jsonl"
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


# ---------------------------------------------------------------- 世界名字表
def load_world_names():
    w = json.loads(WORLD.read_text(encoding="utf-8"))
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
    return {"locs": locs, "subs": subs, "chars": chars, "items": items,
            "names": sorted(n for n in names if n)}


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
def check_row(row, world, cfg):
    text = row["target"]
    facts = row["facts"]
    inp = row["input"]
    n_text, n_inp = norm(text), norm(inp)
    V, W, P = [], [], []          # violation / 未表达 / 待人工

    in_names = {n for n in world["names"] if norm(n) in n_inp}
    char_names = {n for n in world["chars"].values() if norm(n) in n_inp}

    # ---- 第一层：硬格式
    if DIGIT_RE.search(text):
        V.append({"layer": 1, "code": "digit", "detail": "正文出现阿拉伯数字"})
    if "「" in text or "」" in text:
        V.append({"layer": 1, "code": "bracket", "detail": "出现书名号任务原文"})
    for tmpl in ("移动｜", "结果｜", "理智｜", "事实：", "分组：", "正文：", "｜"):
        if tmpl in text:
            V.append({"layer": 1, "code": "template", "detail": f"输入模板残留 {tmpl}"})
            break
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
            rev = re.findall(r"从([^，。；]{1,8}?)(?:回到|来到|走到|走到|到|回)([^，。；]{1,8}?)",
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

    # ---- 第五层：主体归属（只报可疑，不判违规）
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
    ok = not V and not must_missed
    return {"id": row["id"], "pass": ok, "violations": V, "unexpressed": W,
            "pending": P}


def tamper(text, facts, world):
    """把人工稿改坏，检查器必须抓到。"""
    out = []
    t = json.loads(json.dumps(text, ensure_ascii=False))
    out.append(("加数字时长", t.rstrip("。") + "，过了八分钟。"))
    out.append(("加书名号", t.rstrip("。") + "他办妥了任务「换灯芯」。"))
    out.append(("加世界册人名", t.replace("沈砚", "韩渡", 1)))
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
    return out


def main() -> int:
    # 阈值来自人工参考答案的实测下界（见 calibrate 输出）：
    #   outcome 最低 0.20 → 取 0.20；appearance 最低 0.00（有一条只写"擦过的地方
    #   亮得能照见人"）→ 取 0.0 太松，改判软项；personality 金标准中位 0.00
    #   （写的是行为，不是原文）→ 该指标无效，判软项；subtask 最低 1.00 → 0.8
    # KNOWN BLIND SPOTS（写进冻结记录，不假装能查）：
    #   1. 删掉结果里的一句细节（其余句仍与原文重合）查不出
    #   2. 把主体换成一个同样在输入里出现的人物，只报"待人工"，不判违规
    #      —— 代词指代无法在程序里解析
    #   3. 文笔、心理是否可信、比喻是否误导，一律不查
    cfg = {"minChars": 60, "copyRun": 8,
           "contentMin": {"outcome": 0.20, "task_achieved": 0.20,
                          "subtask_added": 0.80},
           # 以下三项的上界也来自人工稿：最长重复片段 5 字、同一 4 字串最多 2 次、
           # 单句最长 49 字。超过就说明在复读或句子已经拼接崩了。
           "maxRepeatedSpan": 8, "max4gram": 2, "maxSentence": 65}
    world = load_world_names()
    rows = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines()
            if l.strip()]

    print(f"校准：人工参考答案 {len(rows)} 条")
    fails = []
    for r in rows:
        res = check_row(r, world, cfg)
        if not res["pass"]:
            fails.append(res)
    print(f"  通过 {len(rows) - len(fails)}/{len(rows)}")
    for f in fails[:12]:
        print("   ✗", f["id"],
              "违规:", [(v["code"], v.get("detail")) for v in f["violations"]][:2],
              "未表达:", [(u["kind"], u.get("why")) for u in f["unexpressed"]][:2],
              "待人工:", [p["why"] for p in f["pending"]][:1])

    # 篡改：用第一条构造，逐个字段改坏，要求全部被抓
    base = rows[0]
    caught = 0
    print("\n篡改探针：")
    for label, text in tamper(base["target"], base["facts"], world):
        probe = dict(base, target=text)
        res = check_row(probe, world, cfg)
        hit = not res["pass"]
        caught += hit
        print(f"   {'抓到' if hit else '漏掉'}  {label}")
    print(f"  篡改捕获 {caught}/{len(tamper(base['target'], base['facts'], world))}")

    total = len(tamper(base["target"], base["facts"], world))
    if "--freeze" in sys.argv and len(fails) == 0 and caught == total:
        src = pathlib.Path(__file__).read_bytes()
        rec = {"checker": "checker.py v2",
               "v2Adds": ["repeated-span", "repeated-4gram",
                          "sentence-runaway", "impossible-space"],
               "v2Why": "v1 只查'不犯什么错'，放过了复读与崩裂的输出；"
                        "四项阈值取自人工稿上界（重复片段 5 字 / 4 字串 2 次 / "
                        "单句 49 字）",
               "sha256": hashlib.sha256(src).hexdigest(),
               "world": str(WORLD.name),
               "worldNames": len(world["names"]),
               "thresholds": cfg,
               "calibration": {"rows": len(rows), "pass": len(rows) - len(fails)},
               "tamper": {"cases": total, "caught": caught},
               "registeredBeforeAnyModelRun": True}
        (HERE / "checker-v2-freeze.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\n已冻结：checker-v2-freeze.json")
    return 0 if not fails and caught == 6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
