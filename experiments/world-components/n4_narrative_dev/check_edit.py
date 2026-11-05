import json, re, pathlib, sys
HERE=pathlib.Path(__file__).resolve().parent; sys.path.insert(0,str(HERE))
from conservative_edit import NAMES, SECURED
ART=HERE.parents[2]/"artifacts"/"world-components"
NAMES_RE=re.compile(r"(沈砚|顾行舟|叶知微|阿棠|韩渡)")
def body_of(text):
    t=text.strip().rstrip("。")
    m=re.match(r"(%s)的?"%"|".join(NAMES), t)
    if m: return t[m.end():], m.group(1)
    return t, None
def _n(t): return (t or "").replace(",", "，").replace(";", "；")

def check(sid, units, edited):
    """units: [(fid,name,text)]；返回问题列表。"""
    probs=[]; cursor=0; edited=_n(edited)
    for fid,name,txt in units:
        body,nm=body_of(_n(txt))
        idx=edited.find(body, cursor)
        if idx<0:
            idx=edited.find(body)          # 允许未按位置，但下面记录
        if idx<0:
            probs.append((sid,fid,"取值丢失",body)); continue
        if nm:
            head=edited.rfind(nm, 0, idx)
            if head<0: probs.append((sid,fid,"主体在其内容之前未出现",nm))
        else:
            probs.append((sid,fid,"原文无句首主体（未参与合并）",body))
        cursor=max(cursor,idx)
    return probs
if __name__=="__main__":
    data=json.loads((ART/"n4-conservative-edit-48.json").read_text(encoding="utf-8"))
    units_by={}
    for fn in ("n4-final24-contract.jsonl","n4-cf24-contract.jsonl"):
        for l in (ART/fn).read_text(encoding="utf-8").splitlines():
            if l.strip():
                u=json.loads(l); units_by.setdefault(u["sourceId"],[]).append((u["fact"]["factId"],u["fact"].get("name")))
    blocks={}
    for sid,v in data.items():
        blocks[sid]=v
    # 从 screen 恢复原文分句（编辑稿里已被合并，故用契约单元的 fact 重新序列化不现实；直接用 screen 原文）
    screen=json.loads((ART/"n4-ce-screen.json").read_text(encoding="utf-8"))["u240"]
    txt={r["sourceId"]:[(i["factId"],i["text"]) for i in r["items"]] for r in screen if r["set"] in ("final24","cf24")}
    allp=[]
    for sid,v in data.items():
        units=[(fid,nm,t) for (fid,t),(fid2,nm) in zip(txt[sid],units_by[sid])]
        allp+=check(sid,units,v["edited"])
    print("事实复核问题：",len(allp))
    for p in allp[:12]: print("  ",p)
    json.dump(allp,open(ART/"n4-conservative-edit-check.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
