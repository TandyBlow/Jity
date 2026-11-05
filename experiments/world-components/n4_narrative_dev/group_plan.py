"""Build the human-plan group arm material for all 118 shared sources.

Plan rule (fixed before any target text is written):
  * merge consecutive facts that share the same subject — that is the "same
    local event" case; a subject change always starts a new group
  * a group may be the whole source, so the paragraph reference is reused
  * singleton groups reuse the human-written per-fact target
  * merged groups that are not the whole source get a new standalone target

Every target has to stand alone: the subject is named at first mention, no
pronoun points at the previous group.
"""
import json, pathlib, re
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "artifacts" / "world-components" / "n4-group-plan-r1.json"
EXCLUDE = {"n4n-03", "n4n-15"}

# 16 个“同主体、非整源”的合并组：新写的独立目标
MERGED = {
 "n4n-23:f1+f2": "沈砚把潮汐簿的缺页对齐，照着旧墨迹一笔一笔补完，最后一笔落下时，袖口也蹭上了一道墨。",
 "n4n-32:f2+f3": "沈砚在潮渡的栈桥边等了很久，终于等到最后一班船靠过来，那口一直提着的气才慢慢松下去。",
 "n4n-04:f2+f3": "阿棠从早市过来，推门进了档案馆，把一叠干纸放在桌角，鞋底在门槛上蹭了两下。",
 "n4n-09:f0+f1": "沈砚从潮渡上到旧灯塔，本来想好的客气话到了嘴边，这一次没有咽回去，直接问了出来。",
 "n4n-11:f2+f4": "沈砚把被风吹歪的警示灯扶正，掌心被铁皮冰得发麻，心里那点紧却一直没有松开。",
 "n4n-99:f1+f2": "沈砚从潮生巷上到旧灯塔塔顶，本来想像往常那样把话咽回去，却先开口问灯芯还够不够用。",
 "n4n-100:f1+f2": "沈砚走进旧灯塔，没有再像往常那样沉默，先开口问叶知微，铜油还够不够。",
 "n4n-101:f1+f2": "沈砚从潮生巷走到潮渡的栈桥边，先开了口，问渡船是不是还要再等一班。",
 "n4n-102:f1+f2": "沈砚从潮生巷进了潮汐档案馆，没有像往常那样把话咽回去，先把想问的说了出来。",
 "n4n-103:f1+f2": "沈砚从潮渡上到雾堤，先开口问韩渡，钟绳还在不在钟架上。",
 "n4n-104:f1+f2": "沈砚从潮生巷走进早市，没有再把话咽回去，先问阿棠鱼价怎么算。",
 "n4n-105:f1+f2": "沈砚从潮生巷上到旧灯塔，先开口问叶知微，灯芯还够不够用。",
 "n4n-106:f1+f2": "沈砚走进旧灯塔，没有再像往常那样沉默，先问叶知微铜油还够不够。",
 "n4n-107:f1+f2": "沈砚从潮生巷走到潮渡，先开口问顾行舟，船是不是还要再等一班。",
 "n4n-108:f1+f2": "沈砚从潮生巷进了潮汐档案馆，没有再把话咽回去，先问阿棠干纸带够没有。",
 "n4n-109:f1+f2": "沈砚从潮渡上到雾堤，本来想把话咽回去，却先开口问韩渡，钟绳还够不够长。",
}


def rows(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding="utf-8")
            .splitlines() if l.strip()]


def pack_group(paragraph_input, fact_ids):
    head = paragraph_input.split("事实：")[0]
    facts_block = paragraph_input.split("事实：")[1].split("分组：")[0].strip()
    keep = [ln for ln in facts_block.splitlines()
            if ln.split("｜")[0] in fact_ids]
    tail = paragraph_input.split("视角：", 1)[1]
    return (head + "事实：\n" + "\n".join(keep) + "\n分组：\n"
            f"G1｜{' '.join(fact_ids)}｜组后时间=过去了一会儿\n视角：" + tail)


def plan_for(facts):
    groups, cur = [], []
    for f in facts:
        if cur and f["name"] == cur[-1]["name"]:
            cur.append(f)
        else:
            if cur:
                groups.append(cur)
            cur = [f]
    if cur:
        groups.append(cur)
    return groups


def main():
    corpus = {r["id"]: r for r in rows(HERE / "corpus_v1.jsonl") + rows(HERE / "corpus.jsonl")
              + rows(HERE / "corpus_v2.jsonl")}
    para = {r["sourceId"]: r for r in rows(HERE / "formal_pairs.jsonl")}
    verb = {(r["sourceId"], r["factId"]): r for r in rows(HERE / "verbalizer_pairs.jsonl")}

    units, problems, sources = [], [], []
    for sid in sorted(corpus):
        if sid not in para or sid in EXCLUDE:
            continue
        facts = [f for f in corpus[sid]["facts"] if f["kind"] != "time"]
        groups = plan_for(facts)
        whole = len(groups) == 1
        gids = []
        for gi, g in enumerate(groups, 1):
            gid = f"{sid}:g{gi}"
            ids = [f["factId"] for f in g]
            if whole:
                target = para[sid]["target"]
            elif len(ids) == 1:
                target = verb[(sid, ids[0])]["target"]
            else:
                key = f"{sid}:{'+'.join(ids)}"
                target = MERGED.get(key)
                if not target:
                    problems.append(f"{key}: 缺合并组目标")
                    target = ""
            units.append({"groupId": gid, "sourceId": sid,
                          "split": para[sid]["split"], "factIds": ids,
                          "input": pack_group(para[sid]["input"], ids),
                          "target": target,
                          "targetSource": ("paragraph" if whole else
                                           "merged-new" if len(ids) > 1 else "verbalizer")})
            gids.append(gid)
        sources.append({"sourceId": sid, "split": para[sid]["split"],
                        "facts": [f["factId"] for f in facts], "groups": gids})

    for u in units:
        t = u["target"].strip()
        if not t:
            continue
        if not re.search(r"[。！？…]$", t):
            problems.append(f'{u["groupId"]}: 目标不是完整句')
        if re.match(r"^[他她它]", t):
            problems.append(f'{u["groupId"]}: 目标以代词开头，单独成组时无授权')
        if re.search(r"[0-9]", t):
            problems.append(f'{u["groupId"]}: 目标含数字')
    for s in sources:
        if len(s["facts"]) != len({f for u in units if u["sourceId"] == s["sourceId"]
                                   for f in u["factIds"]}):
            problems.append(f'{s["sourceId"]}: 事实没有恰好归属一组')

    # cf24：同一规则分组，只要输入，不需要目标
    mat = json.loads((ROOT / "artifacts" / "world-components" /
                      "n4-cf24-materials.json").read_text(encoding="utf-8"))
    cf24 = []
    for s in mat["sources"]:
        groups = plan_for(s["facts"])
        for gi, g in enumerate(groups, 1):
            ids = [f["factId"] for f in g]
            cf24.append({"groupId": f'{s["id"]}:g{gi}', "sourceId": s["id"],
                         "pattern": s["pattern"], "factIds": ids,
                         "input": pack_group(s["paragraphInput"], ids)})

    rec = {"purpose": "human-plan group arm material",
           "experimentName": "人工计划条件下的句组臂",
           "planRule": "same-subject consecutive facts merge; subject change splits",
           "counts": {"sources": len(sources), "groups": len(units),
                      "byTargetSource": dict(Counter(u["targetSource"] for u in units)),
                      "bySplit": dict(Counter(u["split"] for u in units)),
                      "groupsPerSource": dict(Counter(len(s["groups"]) for s in sources))},
           "sources": sources, "units": units, "cf24Groups": cf24,
           "problems": problems}
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rec["counts"], ensure_ascii=False))
    print("problems", len(problems), problems[:6])
    print("->", OUT)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
