"""把训练池的事实行规范化到唯一契约（只改事实行），并逐条记录差异。"""
import json, pathlib, sys
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import fact_contract as FC
ART=HERE.parents[2]/"artifacts"/"world-components"
TARGETS=[("expand78",ART/"n4-expand-train80-clean.jsonl"),
         ("object34",ART/"n4-object-train40-clean.jsonl")]
def fact_from_line(kind, line):
    """把旧格式事实行还原成 fact 字典（只用 kind 判断，不依赖顺序）。"""
    parts=[x for x in line.split("｜") if x!=""]
    if kind=="no_change":
        return {"kind":"no_change"}
    tag=parts[0] if parts[0] in ("移动","结果","外观","外貌变化","理智","状态变化","性格变化") else parts[1]
    if tag=="移动":
        name = parts[1] if parts[0]=="移动" else parts[0]
        frm,to=parts[2].split("→") if parts[0]=="移动" else parts[1].split("→")
        return {"kind":"moved","name":name,"from":frm,"to":to}
    name = parts[1] if parts[0]==tag else parts[0]
    val = parts[2] if parts[0]==tag else parts[1]
    if tag in ("结果",):
        return {"kind":"outcome","name":name,"text":val}
    if tag in ("外观","外貌变化"):
        return {"kind":"appearance_changed","name":name,"text":val}
    if tag=="性格变化":
        return {"kind":"personality_changed","name":name,"text":val}
    if tag in ("理智","状态变化"):
        up = val in ("上升","放松")
        return {"kind":"sanity_changed","name":name,"from":(9 if up else 12),"to":(12 if up else 9)}
    raise SystemExit(f"无法解析：{line}")

diffs=[]; out_rows={}
for name,path in TARGETS:
    rows=[json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    fixed=[]
    for u in rows:
        old=[l for l in u["input"].splitlines() if l.startswith("事实=")][0][3:]
        want=FC.serialize_fact(fact_from_line(u.get("kind"), old))
        if old!=want:
            diffs.append({"pool":name,"unitId":u["unitId"],"before":old,"after":want})
        new_input=u["input"].replace("事实="+old,"事实="+want)
        nu=dict(u, input=new_input)
        fixed.append(nu)
    # 语义不变检查：目标、划分、unitId、pairKey 逐条相同
    for a,b in zip(rows,fixed):
        assert a["unitId"]==b["unitId"] and a["target"]==b["target"] and a["split"]==b["split"]
        assert a.get("pairKey")==b.get("pairKey")
    FC.check_units(fixed)
    out_rows[name]=fixed
    (ART/f"n4-{name}-unified.jsonl").write_text(
        "\n".join(json.dumps(x,ensure_ascii=False) for x in fixed)+"\n",encoding="utf-8")
    print(f'{name}: {len(fixed)} 单元，改动事实行 {sum(1 for d in diffs if d["pool"]==name)} 条，目标/划分/ID 全部不变')
(ART/"n4-training-unified-diff.json").write_text(json.dumps(diffs,ensure_ascii=False,indent=1),encoding="utf-8")
from collections import Counter
print("改动类型：")
for (b,a),n in Counter((d["before"].split("｜")[0], d["after"].split("｜")[1]) for d in diffs).items():
    print(f"   {b} → {a}: {n} 条")
print("样例：", diffs[0], diffs[-1])
