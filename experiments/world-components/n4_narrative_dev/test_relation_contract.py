import sys
from relation_contract import validate, elapsed_between

# 真实时间线片段（来自 world.db：world_13 的两个已提交点，各推进 1 秒）
POINTS = [
    {"id":"root_15","worldId":"world_13","sequence":0,"previousPointId":None,"time":None},
    {"id":"point_20","worldId":"world_13","sequence":1,"previousPointId":"root_15",
     "time":{"boundary":"elapsed","duration":{"amount":1,"unit":"second"}}},
    {"id":"point_23","worldId":"world_13","sequence":2,"previousPointId":"point_20",
     "time":{"boundary":"elapsed","duration":{"amount":1,"unit":"second"}}},
    {"id":"point_x","worldId":"world_13","sequence":3,"previousPointId":"point_23",
     "time":{"boundary":"instant","duration":{"amount":0,"unit":"second"}}},
]
FE = {"f2":["point_20"], "f10":["point_23"], "f11":["point_x"]}
fails=[]
def case(name, rels, want_ok, facts=None):
    p=validate(rels, facts or {"f2","f10","f11"}, FE, POINTS)
    ok = not p
    if ok != want_ok: fails.append(f"{name}: 期望{'通过' if want_ok else '拒绝'}，得到 {p}")

case("真实先后证据", [{"type":"before","fromFactId":"f2","toFactId":"f10",
                     "evidenceEventIds":["point_20","point_23"]}], True)
case("自指", [{"type":"before","fromFactId":"f2","toFactId":"f2",
               "evidenceEventIds":["point_20"]}], False)
case("引用不存在的事实", [{"type":"before","fromFactId":"f9","toFactId":"f10",
                        "evidenceEventIds":["point_20","point_23"]}], False)
case("证据追溯不到", [{"type":"before","fromFactId":"f2","toFactId":"f10",
                     "evidenceEventIds":["point_99"]}], False)
case("零时长不构成先后", [{"type":"before","fromFactId":"f10","toFactId":"f11",
                        "evidenceEventIds":["point_23","point_x"]}], False)
case("成环", [{"type":"before","fromFactId":"f2","toFactId":"f10","evidenceEventIds":["point_20","point_23"]},
              {"type":"before","fromFactId":"f10","toFactId":"f2","evidenceEventIds":["point_20","point_23"]}], False)
case("暂不允许因果", [{"type":"causes","fromFactId":"f2","toFactId":"f10",
                     "evidenceEventIds":["point_20","point_23"]}], False)
print("elapsed_between(point_20,point_23) =", elapsed_between("point_20","point_23",POINTS))
print("elapsed_between(point_23,point_20) =", elapsed_between("point_23","point_20",POINTS))
print("失败", len(fails))
for f in fails: print("  ", f)
sys.exit(1 if fails else 0)
