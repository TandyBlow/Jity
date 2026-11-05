# 生成语义核对样本：semantic_probes.jsonl
#
# 每条 = 一条人工参考答案 + 一次定向改动 + 它应有的判决。
#   fail   —— 事实被改错、被否定、被换人，或出现世界册外的具名人物
#   review —— 规则看不出来，必须交给人；这一档不能算通过
#   pass   —— 写法不同但事实完全正确
#
# 替换串不存在会直接报错，不会悄悄生成一条和原稿一样的“样本”。
import json, pathlib
from collections import Counter

HERE = pathlib.Path(__file__).parent
CORPUS = HERE / "corpus140.jsonl"
OUT = HERE / "semantic_probes.jsonl"


def sub(text, old, new, times=-1):
    if old not in text:
        raise SystemExit(f"替换串不存在：{old[:30]}")
    return text.replace(old, new, times)


def build():
    rows = {json.loads(l)["id"]: json.loads(l)
            for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()}
    t = rows["r01"]["target"]
    t02 = rows["r02"]["target"]
    p = []

    def add(pid, base, category, expect, text, why):
        p.append({"id": pid, "baseId": base, "category": category,
                  "expect": expect, "text": text, "why": why})

    # ---------------- 必须判失败：事实被改坏
    add("p01", "r01", "actor-swap", "review", sub(t, "沈砚", "韩渡"),
        "把完成动作的人从沈砚换成同样在输入里的韩渡（全篇再没点沈砚）")
    add("p02", "r01", "negated-result", "fail",
        sub(t, "他抓住灯杆，把灯掰回灯座里",
            "他没抓住灯杆，警示灯始终没能掰回灯座里"),
        "把已经完成的结果写成没完成")
    add("p03", "r01", "outsider-name", "fail",
        t + "任云川站在钟架另一头，一直没有过来。任云川看了他一眼，把话咽了回去。",
        "加入世界册和输入里都没有的具名人物，出现两次")
    add("p04", "r01", "direction-reversed", "fail",
        "沈砚从旧灯塔回到潮声巷，一路上没有停。" + t,
        "把移动方向写反")
    add("p05", "r01", "dropped-result", "review",
        sub(t, "把灯掰回灯座里", "扶着灯杆站了一会儿"),
        "删掉结果里的关键动作，只留一个相关小动作；词面对不起来，只能进复核")
    add("p06", "r01", "copied-input", "fail",
        t + "移动｜沈砚｜旋梯到堤面。",
        "把输入的事实记录行原样搬进正文")
    add("p07", "r01", "contradiction-same-object", "fail",
        t + "钟架旁的灯灭了，过了一会儿钟架旁的灯还亮着。",
        "同一个物体先写灭、后写亮")
    add("p08", "r01", "sanity-number", "fail", t + "他的理智降到了七。",
        "把理智写成数值")

    # ---------------- 必须进复核：规则判不了，不能算通过
    add("p09", "r01", "actor-unnamed", "review", sub(t, "沈砚", "他"),
        "全篇只用代词指代视角人物，一次也没点过名，无法确认是谁做的")
    add("p10", "r01", "partial-result", "review",
        sub(t, "把灯掰回灯座里", "把灯往上抬了抬"),
        "结果只对上一部分，规则无法确认细节是否完整")

    # ---------------- 必须通过：写得不一样，事实完全正确
    # p11 的替换会连“警示灯”一起改坏，所以这里只替换第一次出现的手背描写
    add("p11", "r01", "cold-hot-coexist", "pass",
        sub(t, "手背在铁皮上擦破一块", "手背冰凉，灯的铁皮发烫，擦破一块"),
        "不同物体一冷一热同时存在")
    add("p12", "r01", "two-lamps", "pass", t + "远处的灯灭了，警示灯还亮着。",
        "远处的灯灭了，眼前这盏还亮")
    add("p13", "r01", "pronoun-only", "pass",
        t.replace("沈砚低头看自己的手", "他低头看自己的手"),
        "第二次提到视角人物用代词")
    add("p14", "r01", "reordered", "pass",
        "\n\n".join(reversed([x for x in t.split("\n\n") if x.strip()])),
        "段落顺序调换")
    add("p15", "r01", "added-dialogue", "pass",
        t + "韩渡说：雾再大一点，船就不敢进港了。",
        "加入不改变事实的对话")

    # ---------------- 2026-11-04 用户复跑抓到的五条，锁成回归样本
    add("p16", "r01", "local-actor-swap", "review",
        sub(t, "他抓住灯杆", "韩渡抓住灯杆"),
        "只换动作句的主语，别处仍点名沈砚；全篇点过名不能证明这一句归属正确")
    add("p17", "r02", "origin-crossed", "review",
        sub(sub(t02, "叶知微从旋梯口下来", "叶知微从栈桥那头绕过来"),
            "顾行舟是从栈桥那头绕过来的", "顾行舟是从旋梯口下来的"),
        "把两个人的出发地互换，名字都还在")
    add("p18", "r01", "outsider-once", "fail",
        t + "任云川靠在铁链旁，低头看了看海面。",
        "册外人物只出现一次")
    add("p19", "r01", "near-far-lamps", "pass", t + "近处的灯灭了，远处的灯还亮着。",
        "近处和远处各有一盏灯，一灭一亮")
    add("p20", "r01", "other-negation", "pass", t + "韩渡没有抓住灯杆。",
        "否定的主语是另一个人，视角人物的事实没有被否定")
    return p


if __name__ == "__main__":
    probes = build()
    OUT.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in probes)
                   + "\n", encoding="utf-8")
    print(f"写出 {len(probes)} 条 → {OUT.name}")
    print(Counter(x["expect"] for x in probes))
