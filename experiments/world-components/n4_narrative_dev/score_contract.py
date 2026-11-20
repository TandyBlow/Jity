"""对契约格式诊断集的输出做逐事实初筛（机械规则），并列出需要人工复核的项。"""
import json, pathlib, re, sys
HERE=pathlib.Path(__file__).resolve().parent
ART=HERE.parents[2]/"artifacts"/"world-components"
PUNCT=re.compile(r"[\s，,。．.；;：:！!？?、…—－\-\"'“”‘’（）()《》「」]")
def n(s): return PUNCT.sub("",s or "")
def bg(s): s=n(s); return {s[i:i+2] for i in range(len(s)-1)}
def cov(k,h):
    b=bg(k); return len(b&bg(h))/len(b) if b else 1.0
UP=["匀","松","散","落回","慢下来","稳","缓"]
DOWN=["发紧","发闷","重","不听使唤","冷汗","屏","抖"]
def judge(kind,fact,text):
    t=n(text); name=fact.get("name") or ""
    if kind=="no_change":
        ok=re.search(r"(没有新的变化|没有新的事情|什么也没有再发生|没有别的动静|没有动静|没有动)",text)
        return ("S" if ok else "O"),""
    ALIAS={"潮汐档案馆":["档案馆"],"潮渡":["渡口","栈桥"],"旧灯塔":["灯塔"],"雾堤":["堤面","堤上"],
           "潮生巷":["巷子"],"早市":["集市"]}
    def seen(place):
        if not place: return False
        return place in text or any(x in text for x in ALIAS.get(place,[]))
    if kind=="moved":
        a,b=fact.get("from"),fact.get("to")
        ok=seen(a) and seen(b)
        return ("S" if ok else "O"), ("" if ok else f"起点{'' if seen(a) else '缺'} 终点{'' if seen(b) else '缺'}")
    if kind=="sanity_changed":
        up=fact["to"]>fact["from"]
        cue=any(w in text for w in (UP if up else DOWN))
        bare=re.search(rf"({re.escape(name)})(放松|发紧|上升|下降)",text)
        if bare: return "O","值词直写"
        return ("S" if cue else "O"), ("" if cue else "无方向")
    key=fact.get("resultText") or fact.get("text") or ""
    if name and name not in text: return "A",f"主体缺失({name})"
    c=cov(key,text)
    if c>=0.5: return "S",f"覆盖{c:.2f}"
    if c>=0.25: return "REVIEW",f"覆盖{c:.2f}"
    return "O",f"覆盖{c:.2f}"
out={}
import sys
ARMS=sys.argv[1:] or ["base","422","431"]
for arm in ARMS:
    d=json.loads((ART/f"n4-ce-{arm}.json").read_text(encoding="utf-8"))
    rows=[]
    for setname in ("object18","expand36","final24","cf24"):
        units={}
        fn={"object18":"n4-object18-contract.jsonl","expand36":"n4-expand36-contract.jsonl",
            "final24":"n4-final24-contract.jsonl","cf24":"n4-cf24-contract.jsonl"}[setname]
        for l in (ART/fn).read_text(encoding="utf-8").splitlines():
            if l.strip():
                u=json.loads(l); units[u["unitId"]]=u
        per_src={}
        for r in d[setname]:
            u=units[r["unitId"]]
            v,note=judge(r["kind"],u["fact"],r["text"])
            per_src.setdefault(r.get("sourceId") or r["unitId"].split(":")[0],[]).append(
                {"unitId":r["unitId"],"factId":u["fact"].get("factId"),
                 "kind":r["kind"],"verdict":v,"note":note,"text":r["text"]})
        for sid,items in per_src.items():
            rows.append({"set":setname,"sourceId":sid,"items":items})
    out[arm]=rows
(ART/"n4-ce-screen.json").write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding="utf-8")
for arm in ARMS:
    for setname in ("object18","expand36","final24","cf24"):
        sub=[r for r in out[arm] if r["set"]==setname]
        facts=[i for r in sub for i in r["items"]]
        from collections import Counter
        c=Counter(i["verdict"] for i in facts)
        clean=sum(1 for r in sub if all(i["verdict"]=="S" for i in r["items"]))
        print(f'{arm:5} {setname:9} facts {c} cleanSrc {clean}/{len(sub)}')
