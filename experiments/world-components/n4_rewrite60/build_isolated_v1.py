# 生成 v1 隔离集：三组样本，每组一正一错成对。
#
# 标签是构造出来的，不是判据算出来的：ok 文本按事实写，bad 文本按错误类型改。
# 生成后先做格式自检（数字/半角/长度/结尾），再冻结标签，最后才跑判据。
import json, pathlib

HERE = pathlib.Path(__file__).parent
OUT = HERE / "isolated-v1" / "isolated-v1.jsonl"

# ---------------------------------------------------------------- 世界
WORLDS = {
    "same-world": None,                        # 默认世界（world.json）
    "new-people-places": "isolated-v1/world-b.json",
    "new-world": "isolated-v1/world-c.json",
}

# ---------------------------------------------------------------- 样本
# 每条：(id, 组, 正确稿, 事实, 错误稿, 错误类型, 错在哪些 factId, 说明)
CASES = [
    # ---------------- A 组：同世界，新的事实组合（不复用 corpus140 的正文）
    ("a01", "same-world",
     "潮渡的木桩上还留着昨夜退水的水痕。叶知微从潮生巷过来，把系泊绳在木桩上绕了三圈，绳头压在最上面那一圈底下。风从水面推过来，绳身绷了一下，没有松。",
     [{"factId": "f0", "kind": "moved", "name": "叶知微", "entityGroup": "characters",
       "from": "潮生巷", "to": "潮渡"},
      {"factId": "f1", "kind": "outcome", "name": "叶知微", "entityGroup": "characters",
       "resultText": "把系泊绳在木桩上绕了三圈"}],
     "潮渡的木桩上还留着昨夜退水的水痕。韩渡从潮生巷过来，把系泊绳在木桩上绕了三圈，绳头压在最上面那一圈底下。风从水面推过来，绳身绷了一下，没有松。叶知微在巷口看着。",
     ["subject-swap"], ["f1"], "把完成动作的人从叶知微换成韩渡"),

    ("a02", "same-world",
     "石阶上积着一层细雾。顾行舟从塔顶下来，在钟架前站住，把松脱的钟绳重新绕在钟架上，绕完又按了按绳结。下面有人咳嗽，他没有回头。",
     [{"factId": "f0", "kind": "moved", "name": "顾行舟", "entityGroup": "characters",
       "from": "塔顶", "to": "石阶"},
      {"factId": "f1", "kind": "outcome", "name": "顾行舟", "entityGroup": "characters",
       "resultText": "把松脱的钟绳重新绕在钟架上"}],
     "石阶上积着一层细雾。顾行舟从石阶回到塔顶，在钟架前站住，把松脱的钟绳重新绕在钟架上，绕完又按了按绳结。",
     ["direction"], ["f0"], "把移动方向写反"),

    ("a03", "same-world",
     "早市的帆布棚刚拉开一半。阿棠蹲在案板边，把银鳞鱼按大小分开装进两只鱼筐，袖口沾着鱼鳞，她随手在围裙上抹了一下。棚外的雾还没散。",
     [{"factId": "f0", "kind": "outcome", "name": "阿棠", "entityGroup": "characters",
       "resultText": "把银鳞鱼按大小分开装进两只鱼筐"},
      {"factId": "f1", "kind": "appearance_changed", "name": "阿棠",
       "entityGroup": "characters", "text": "袖口沾着鱼鳞"}],
     "早市的帆布棚刚拉开一半。阿棠蹲在案板边，把鱼筐往案板底下推了推，袖口沾着鱼鳞，她随手在围裙上抹了一下。棚外的雾还没散。",
     ["omission"], ["f0"], "删掉结果里的关键动作，只留相关小动作"),

    ("a04", "same-world",
     "档案馆的长桌上还摊着没合上的干纸。沈砚从桌边起身，穿过门槛，把备用钥匙塞进油布包的内层，系口的时候手停了停。巷口的灯已经灭了。",
     [{"factId": "f0", "kind": "moved", "name": "沈砚", "entityGroup": "characters",
       "from": "潮汐档案馆", "to": "潮生巷"},
      {"factId": "f1", "kind": "outcome", "name": "沈砚", "entityGroup": "characters",
       "resultText": "把备用钥匙塞进油布包的内层"}],
     "档案馆的长桌上还摊着没合上的干纸。沈砚从桌边起身，没有把备用钥匙塞进油布包的内层，只把它攥在手里。巷口的灯已经灭了。",
     ["negation"], ["f1"], "把已经完成的结果写成没完成"),

    ("a05", "same-world",
     "长桌上的铜灯和冷茶都还摆着。叶知微把抹布搭在桌角，左耳后有一道新划痕，被灯照得发亮，她自己像是没察觉。窗外的雾顺着天窗缝往里渗。",
     [{"factId": "f0", "kind": "outcome", "name": "叶知微", "entityGroup": "characters",
       "resultText": "把抹布搭在桌角"},
      {"factId": "f1", "kind": "appearance_changed", "name": "叶知微",
       "entityGroup": "characters", "text": "左耳后有一道新划痕"}],
     "长桌上的铜灯和冷茶都还摆着。叶知微把抹布搭在桌角，左耳后有一道新划痕。石青靠在门边看了一会儿，没有说话。",
     ["added-entity"], ["f1"], "加入世界册和输入里都没有的具名人物"),

    ("a06", "same-world",
     "雾压得很低，堤面上的铁链被风推得一下一下响。沈砚抓住钟绳，把雾警钟敲响，钟声撞进雾里又折回来。心里那点火气退下去，反倒更冷了。",
     [{"factId": "f0", "kind": "outcome", "name": "沈砚", "entityGroup": "characters",
       "resultText": "把雾警钟敲响"},
      {"factId": "f1", "kind": "sanity_changed", "name": "沈砚",
       "entityGroup": "characters", "from": 12, "to": 9}],
     "雾压得很低，堤面上的铁链被风推得一下一下响。沈砚抓住钟绳，把雾警钟敲响，钟声撞进雾里又折回来。他的理智掉到了九。",
     ["added-number"], ["f1"], "把理智写成数值"),

    ("a07", "same-world",
     "浅滩的水退下去一截。顾行舟从栈桥那头过来，把渡船推离木桩；韩渡从塔顶下来，在石阶口停住。两个人都没有先开口。",
     [{"factId": "f0", "kind": "moved", "name": "顾行舟", "entityGroup": "characters",
       "from": "栈桥", "to": "浅滩"},
      {"factId": "f1", "kind": "moved", "name": "韩渡", "entityGroup": "characters",
       "from": "塔顶", "to": "石阶"}],
     "浅滩的水退下去一截。顾行舟从石阶那头过来，把渡船推离木桩；韩渡从栈桥下来，在浅滩停住。两个人都没有先开口。",
     ["subject-swap", "direction"], ["f0", "f1"], "把两个人的出发地互换"),

    ("a08", "same-world",
     "棚外的雾还没散。阿棠把鱼筐搬到摊棚外，顾行舟跟在她后头，肩上的外袍裂了口子，他本人像是没察觉。案板上的水迹还没有干。",
     [{"factId": "f0", "kind": "outcome", "name": "阿棠", "entityGroup": "characters",
       "resultText": "把鱼筐搬到摊棚外"},
      {"factId": "f1", "kind": "appearance_changed", "name": "顾行舟",
       "entityGroup": "characters", "text": "肩上的外袍裂了口子"}],
     "棚外的雾还没散。韩渡把鱼筐搬到摊棚外，顾行舟跟在他后头，肩上的外袍裂了口子，他本人像是没察觉。阿棠站在案板后面看着。",
     ["subject-swap"], ["f0"], "只换动作句的主语，别处仍点名原主体"),

    # ---------------- B 组：新人物、新地点（石青/阿洛/盐仓/渡口棚）
    ("b01", "new-people-places",
     "盐仓的木梯上落着一层白。石青从盐仓里出来，把盐袋拖到渡口棚下，袋子在石墩上蹭出一道白印。草棚的顶漏了一点光。",
     [{"factId": "f0", "kind": "moved", "name": "石青", "entityGroup": "characters",
       "from": "盐仓", "to": "渡口棚"},
      {"factId": "f1", "kind": "outcome", "name": "石青", "entityGroup": "characters",
       "resultText": "把盐袋拖到渡口棚下"}],
     "盐仓的木梯上落着一层白。阿洛从盐仓里出来，把盐袋拖到渡口棚下，袋子在石墩上蹭出一道白印。石青在仓门口看着。",
     ["subject-swap"], ["f1"], "把拖盐袋的人从石青换成阿洛"),

    ("b02", "new-people-places",
     "仓门的木闩上结着一层盐霜。阿洛搬来木梯，把提灯挂在仓门的钉子上，灯罩里的火苗歪了一下又直起来。仓里没有人应声。",
     [{"factId": "f0", "kind": "outcome", "name": "阿洛", "entityGroup": "characters",
       "resultText": "把提灯挂在仓门的钉子上"}],
     "仓门的木闩上结着一层盐霜。阿洛搬来木梯，提灯还在手里，没能挂到仓门的钉子上，灯罩里的火苗歪了一下又直起来。",
     ["negation"], ["f0"], "把挂灯写成没挂上"),

    ("b03", "new-people-places",
     "石青在盐堆边上站了一会儿，肩上落了一层盐霜，连睫毛上都白。他没有拍，只把手在裤腿上擦了擦，转身又去搬下一袋。",
     [{"factId": "f0", "kind": "appearance_changed", "name": "石青",
       "entityGroup": "characters", "text": "肩上落了一层盐霜"}],
     "阿洛在盐堆边上站了一会儿，肩上落了一层盐霜，连睫毛上都白。他没有拍，只把手在裤腿上擦了擦。石青在仓门口看着。",
     ["subject-swap"], ["f0"], "把落盐霜的人从石青换成阿洛"),

    ("b04", "new-people-places",
     "渡口棚的草顶被风掀起一角。阿洛把湿了的盐袋搬到仓门口，一袋一袋码在门边的石墩上，码到第三袋才直起腰。石青在仓里应了一声。",
     [{"factId": "f0", "kind": "moved", "name": "阿洛", "entityGroup": "characters",
       "from": "渡口棚", "to": "盐仓"},
      {"factId": "f1", "kind": "outcome", "name": "阿洛", "entityGroup": "characters",
       "resultText": "把湿了的盐袋搬到仓门口"}],
     "渡口棚的草顶被风掀起一角。阿洛从盐仓回到渡口棚，把湿了的盐袋搬到仓门口，一袋一袋码在门边的石墩上。",
     ["direction"], ["f0"], "把回仓写成回渡口棚，方向反了"),

    ("b05", "new-people-places",
     "草棚底下堆着几捆麻绳。石青从盐仓出来，把麻绳在石墩上系紧，绳结压在两圈底下。风把草顶掀起一角又落下。",
     [{"factId": "f0", "kind": "moved", "name": "石青", "entityGroup": "characters",
       "from": "盐仓", "to": "渡口棚"},
      {"factId": "f1", "kind": "outcome", "name": "石青", "entityGroup": "characters",
       "resultText": "把麻绳在石墩上系紧"}],
     "草棚底下堆着几捆麻绳。石青从盐仓出来，把麻绳抱在怀里站了一会儿。风把草顶掀起一角又落下。",
     ["omission"], ["f1"], "把系绳换成抱着绳站着，结果没发生"),

    ("b06", "new-people-places",
     "早市的摊棚底下挤着人。阿棠把鱼筐挪到案板边，石青蹲下来看筐里的银鳞鱼，伸手拨了拨，又把手缩回去。两个人都没有谈价。",
     [{"factId": "f0", "kind": "outcome", "name": "阿棠", "entityGroup": "characters",
       "resultText": "把鱼筐挪到案板边"},
      {"factId": "f1", "kind": "outcome", "name": "石青", "entityGroup": "characters",
       "resultText": "伸手拨了拨筐里的银鳞鱼"}],
     "早市的摊棚底下挤着人。石青把鱼筐挪到案板边，阿棠蹲下来看筐里的银鳞鱼，伸手拨了拨，又把手缩回去。",
     ["subject-swap"], ["f0", "f1"], "把两个人的动作互换"),

    ("b07", "new-people-places",
     "盐仓的木梯斜靠在仓梁上。顾行舟扶着梯子，阿洛一级一级往上爬，把提灯放到仓梁的横木上。光散开来，盐堆的边沿亮了一圈。",
     [{"factId": "f0", "kind": "outcome", "name": "阿洛", "entityGroup": "characters",
       "resultText": "把提灯放到仓梁的横木上"}],
     "盐仓的木梯斜靠在仓梁上。顾行舟扶着梯子，阿洛没能把提灯放到仓梁的横木上，只举到一半就停了。",
     ["negation"], ["f0"], "把放灯写成没放上去"),

    ("b08", "new-people-places",
     "渡口棚的石墩上摆着两只空盐袋。叶知微把麻绳收成一卷，石青把空盐袋叠起来压在麻绳上，两个人各做各的。雾从水面慢慢过来。",
     [{"factId": "f0", "kind": "outcome", "name": "叶知微", "entityGroup": "characters",
       "resultText": "把麻绳收成一卷"},
      {"factId": "f1", "kind": "outcome", "name": "石青", "entityGroup": "characters",
       "resultText": "把空盐袋叠起来压在麻绳上"}],
     "渡口棚的石墩上摆着两只空盐袋。叶知微把空盐袋叠起来压在麻绳上，石青把麻绳收成一卷，两个人各做各的。",
     ["subject-swap"], ["f0", "f1"], "把两个人的活互换"),

    # ---------------- C 组：全新世界（青石渡/旧仓/风口岭/望雪台）
    ("c01", "new-world",
     "青石阶上还留着昨夜的水线。秦望从旧仓过来，把竹篙横在渡桩上，手在衣角上按了一按。对岸的油灯还亮着，看不出有没有人。",
     [{"factId": "f0", "kind": "moved", "name": "秦望", "entityGroup": "characters",
       "from": "旧仓", "to": "青石渡"},
      {"factId": "f1", "kind": "outcome", "name": "秦望", "entityGroup": "characters",
       "resultText": "把竹篙横在渡桩上"}],
     "青石阶上还留着昨夜的水线。柳七从旧仓过来，把竹篙横在渡桩上，手在衣角上按了一按。秦望在阶下看着。",
     ["subject-swap"], ["f1"], "把横竹篙的人从秦望换成柳七"),

    ("c02", "new-world",
     "渡口棚的草顶上积着一层薄霜。柳七把油灯挂在棚柱的钉子上，灯苗跳了两下才稳住。秦望在阶下等，没有催。",
     [{"factId": "f0", "kind": "outcome", "name": "柳七", "entityGroup": "characters",
       "resultText": "把油灯挂在棚柱的钉子上"}],
     "渡口棚的草顶上积着一层薄霜。柳七没有把油灯挂上，只把它放在石墩上，灯苗跳了两下才稳住。",
     ["negation"], ["f0"], "把挂灯写成没挂上"),

    ("c03", "new-world",
     "旧仓的木梯断了一级。陆行从风口岭下来，把缆索在仓门边盘好，盘完用脚踩了踩。仓里一股霉味，没有人。",
     [{"factId": "f0", "kind": "moved", "name": "陆行", "entityGroup": "characters",
       "from": "风口岭", "to": "旧仓"},
      {"factId": "f1", "kind": "outcome", "name": "陆行", "entityGroup": "characters",
       "resultText": "把缆索在仓门边盘好"}],
     "旧仓的木梯断了一级。陆行从旧仓回到风口岭，把缆索在仓门边盘好，盘完用脚踩了踩。",
     ["direction"], ["f0"], "把下岭写成回岭，方向反了"),

    ("c04", "new-world",
     "望雪台的风比岭口大。祁婶把盐袋在木栏边码好，一袋压一袋，压到最上面那袋时手抖了一下。雪线又往上退了一截。",
     [{"factId": "f0", "kind": "outcome", "name": "祁婶", "entityGroup": "characters",
       "resultText": "把盐袋在木栏边码好"}],
     "望雪台的风比岭口大。祁婶把盐袋在木栏边码好。任云川站在木栏外看了一会儿，没有说话。",
     ["added-entity"], ["f0"], "加入新世界里不存在的具名人物"),

    ("c05", "new-world",
     "岭口的经幡被风扯得直响。秦望和陆行把石堆往风口那侧挪，挪到一半停下喘气。两个人都没有提山下的事。",
     [{"factId": "f0", "kind": "outcome", "name": "秦望", "entityGroup": "characters",
       "resultText": "把石堆往风口那侧挪"},
      {"factId": "f1", "kind": "moved", "name": "陆行", "entityGroup": "characters",
       "from": "岭口", "to": "风口岭"}],
     "岭口的经幡被风扯得直响。秦望把石堆往风口那侧挪，挪到一半停下喘气，陆行从风口岭下来接他。",
     ["subject-swap"], ["f1"], "把陆行写成本来就在岭上，移动没发生"),

    ("c06", "new-world",
     "雪线退下去以后，木栏上留下几道湿痕。祁婶把马灯点在望台的角上，火苗贴着灯罩。她坐下来，把手拢在袖子里。",
     [{"factId": "f0", "kind": "outcome", "name": "祁婶", "entityGroup": "characters",
       "resultText": "把马灯点在望台的角上"}],
     "雪线退下去以后，木栏上留下几道湿痕。祁婶没有点着马灯，只在角上坐了一会儿，把手拢在袖子里。",
     ["negation"], ["f0"], "把点灯写成没点着"),

    ("c07", "new-world",
     "旧仓的门闩上了冻。柳七从渡口棚过来，把门推开一条缝，伸手把里面的油灯提出来。仓里的霉味跟着扑出来。",
     [{"factId": "f0", "kind": "moved", "name": "柳七", "entityGroup": "characters",
       "from": "渡口棚", "to": "旧仓"},
      {"factId": "f1", "kind": "outcome", "name": "柳七", "entityGroup": "characters",
       "resultText": "把油灯从仓里提出来"}],
     "旧仓的门闩上了冻。秦望把门推开一条缝，伸手把里面的油灯提出来。柳七站在渡口棚边上看着。",
     ["subject-swap"], ["f1"], "只换动作句主语，别处仍点名柳七"),

    ("c08", "new-world",
     "风口岭的石堆被雪压塌了一角。陆行把缆索从石堆底下抽出来，抖了抖上面的雪，绕在肩上。秦望在岭口等着，没有走近。",
     [{"factId": "f0", "kind": "outcome", "name": "陆行", "entityGroup": "characters",
       "resultText": "把缆索从石堆底下抽出来"}],
     "风口岭的石堆被雪塌了一角。陆行在石堆边上站了一会儿，抖了抖肩上的雪，往岭口走。秦望在岭口等着。",
     ["omission"], ["f0"], "把抽缆索换成站着抖雪，结果没发生"),
]


TAILS = [
    "雾在石面上慢慢散开。",
    "风把水汽推到岸边，又退回去。",
    "远处传来一声水响，随即没了。",
    "天色比刚才暗了一层。",
    "脚下的石板凉得透人。",
    "空气里有一股湿味散不掉。",
]


def extend(text, seed):
    """补到 66 字以上。只用不带人名的写景句，避免改变事实或把别人拉进正文。"""
    i = sum(ord(c) for c in seed) % len(TAILS)
    while len(text) < 74:
        text += TAILS[i % len(TAILS)]
        i += 1
    return text


def load_world(rel):
    import sys
    sys.path.insert(0, str(HERE))
    import checker as C
    return C.load_world_names(HERE / rel if rel else None)


def render_input(facts, world, text):
    """拼一份最小输入：事实行 + 在场 + 可见。正文里出现的合法名字都要进输入，
    否则第 3 层会把它们当成新增实体。"""
    lines = []
    for f in facts:
        k = f["kind"]
        if k == "moved":
            lines.append(f"移动｜{f['name']}｜{f['from']}到{f['to']}")
        elif k == "outcome":
            lines.append(f"结果｜{f['name']}｜{f['resultText']}")
        elif k == "appearance_changed":
            lines.append(f"外貌｜{f['name']}｜{f['text']}")
        elif k == "sanity_changed":
            lines.append(f"理智｜{f['name']}｜{f['from']}到{f['to']}")
    chars = [c for c in world["chars"].values()
             if any(c in t for t in [text] + [str(v) for f in facts
                                              for v in f.values()])]
    lines.append("在场：" + "、".join(chars))
    seen = [n for n in world["names"] if n in text and n not in chars]
    if seen:
        lines.append("可见：" + "、".join(seen))
    lines.append("视角：第三人称限知，只写视角人物内心")
    return "\n".join(lines)


def main():
    cases, problems = [], []
    for cid, group, ok, facts, bad, etypes, wrong, why in CASES:
        world = load_world(WORLDS[group])
        ok = extend(ok, cid + "ok")
        bad = extend(bad, cid + "bad")
        for tag, text in (("ok", ok), ("bad", bad)):
            if len(text) < 60:
                problems.append(f"{cid}{tag}: 只有 {len(text)} 字")
            if any(ch.isdigit() for ch in text):
                problems.append(f"{cid}{tag}: 出现阿拉伯数字")
            if any(ch in text for ch in ",;:!?"):
                problems.append(f"{cid}{tag}: 出现半角标点")
            if "—" in text:
                problems.append(f"{cid}{tag}: 出现破折号")
            if not text.endswith("。"):
                problems.append(f"{cid}{tag}: 结尾不是句号")
        cases.append({"id": cid, "group": group, "world": WORLDS[group],
                      "text": ok, "input": render_input(facts, world, ok),
                      "facts": facts, "label": "pass", "labelSource": "human",
                      "pairId": cid + "-bad"})
        cases.append({"id": cid + "-bad", "group": group, "world": WORLDS[group],
                      "text": bad, "input": render_input(facts, world, ok + bad),
                      "facts": facts, "label": "fail", "labelSource": "human",
                      "pairId": cid, "errorTypes": etypes, "wrongFacts": wrong,
                      "note": why})
    if problems:
        print("格式自检没通过，没有写出：")
        for p in problems:
            print("  -", p)
        return 1
    OUT.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n",
                   encoding="utf-8")
    print(f"写出 {len(cases)} 条 → {OUT.name}")
    from collections import Counter
    print("按组：", dict(Counter(c["group"] for c in cases)))
    print("按标签：", dict(Counter(c["group"] + "/" + c["label"] for c in cases)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
