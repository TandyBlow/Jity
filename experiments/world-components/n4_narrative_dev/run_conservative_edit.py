import json, re, pathlib, sys
HERE=pathlib.Path(__file__).resolve().parent; sys.path.insert(0,str(HERE))
from conservative_edit import edit_source, NAMES, SECURED
ART=HERE.parents[2]/"artifacts"/"world-components"
screen=json.loads((ART/"n4-ce-screen.json").read_text(encoding="utf-8"))["u240"]
orig={}
for r in screen:
    if r["set"] not in ("final24","cf24"): continue
    orig[r["sourceId"]]={"set":r["set"],"facts":[i["factId"] for i in r["items"]],
                         "units":[(i["factId"], i["text"]) for i in r["items"]]}
# 主体来自契约单元里的 fact.name
names={}
for fn in ("n4-final24-contract.jsonl","n4-cf24-contract.jsonl"):
    for l in (ART/fn).read_text(encoding="utf-8").splitlines():
        if l.strip():
            u=json.loads(l); names[(u["sourceId"],u["fact"]["factId"])]=u["fact"].get("name")
out={}; problems=[]
for sid,d in orig.items():
    units=[(fid, names.get((sid,fid)), txt) for fid,txt in d["units"]]
    edited,ops=edit_source(units)
    original="".join(t for _,_,t in units)
    # 事实复核：每条事实的主体、取值、起终点必须仍在；顺序不得变
    for fid,txt in d["units"]:
        if txt.strip().rstrip("。") not in edited.replace("，","。").replace("。","。") and txt.strip() not in edited:
            if txt.strip().rstrip("。") not in edited:
                problems.append((sid,fid,"原文片段未在编辑稿中出现",txt))
    if SECURED.search(edited) and not SECURED.search(original):
        problems.append((sid,"-","新增关系词",SECURED.search(edited).group(1)))
    out[sid]={"set":d["set"],"original":original,"edited":edited,"ops":ops}
(ART/"n4-conservative-edit-48.json").write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding="utf-8")
changed=[k for k,v in out.items() if v["original"]!=v["edited"]]
print("48 源中发生改动的：",len(changed),"/",len(out))
print("操作总数：",sum(len(v["ops"]) for v in out.values()))
print("事实复核问题：",len(problems))
for p in problems[:10]: print("  ",p)
