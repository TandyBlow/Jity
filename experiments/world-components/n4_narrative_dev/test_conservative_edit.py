"""编辑层边界测试：顺序、所有格、回退、关系词。"""
import sys, json
from conservative_edit import edit_source, VERSION, SECURED

def U(fid, name, text): return (fid, name, text)
fails = []
def eq(got, want, msg):
    if got != want: fails.append(f"{msg}\n  got : {got}\n  want: {want}")

# T1 顺序按输入，不按编号字符串排序（f10 不能跑到 f2 前面）
r = edit_source([U("f2","沈砚","沈砚把铜灯挪到门槛边。"),
                 U("f10","沈砚","沈砚把干纸放在桌角。"),
                 U("f1","沈砚","沈砚把潮汐簿合上。")])
eq(r["edited"], "沈砚把铜灯挪到门槛边，把干纸放在桌角，把潮汐簿合上。", "T1 顺序保持输入顺序")
eq([o["factId"] for o in r["ops"] if o["op"]=="合句（逗号串联）"], ["f2"], "T1 合并锚点是首条 f2")

# T2 所有格：删“姓名＋的”，不是只删姓名
r = edit_source([U("f0","阿棠","阿棠把抹布塞进鱼筐底下。"),
                 U("f1","阿棠","阿棠的袖口沾了鱼鳞。")])
eq(r["edited"], "阿棠把抹布塞进鱼筐底下，袖口沾了鱼鳞。", "T2 所有格合并结果")
eq([o["op"] for o in r["ops"] if "op" in o and o["factId"]=="f1"], ["删姓名＋的"], "T2 操作类型")
eq(all(o.get("ownerRecoverable") for o in r["ops"] if o["factId"]=="f1"), True, "T2 所有者可恢复标记")

# T3 主体不明 → 回退原稿
r = edit_source([U("f0","沈砚","沈砚把铜灯挪到门槛边。"),
                 U("f1","沈砚","铜灯被挪到门槛边。")])
eq(r["edited"], r["original"], "T3 第二条不以姓名开头 → 原样")
eq(bool(r["fallbacks"]), True, "T3 记录回退")

# T4 非人物主体 → 原样
r = edit_source([U("f0","铜灯","铜灯的灯罩上积了灰。"),
                 U("f1","铜灯","铜灯的玻璃上蒙了盐雾。")])
eq(r["edited"], r["original"], "T4 物件主体不合并")

# T5 跨主体交替 → 原样
r = edit_source([U("f0","沈砚","沈砚把铜灯挪到门槛边。"),
                 U("f1","韩渡","韩渡把钟绳解开。"),
                 U("f2","沈砚","沈砚把干纸放在桌角。")])
eq(r["edited"], r["original"], "T5 跨主体不动")

# T6 反思句后不合并（R7）
r = edit_source([U("f0","沈砚","沈砚松开手，才发现那口气落回去了。"),
                 U("f1","沈砚","沈砚把渡船推离栈桥。")])
eq(r["edited"], r["original"], "T6 反思句后不并")

# T7 不新增关系词
r = edit_source([U("f0","韩渡","韩渡把松脱的钟绳重新系紧。"),
                 U("f1","韩渡","韩渡把雾警钟敲响。")])
eq(bool(SECURED.search(r["edited"]) and not SECURED.search(r["original"])), False, "T7 无新增关系词")

print("version", VERSION)
print("失败", len(fails))
for f in fails: print(f)
sys.exit(1 if fails else 0)
