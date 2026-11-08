"""生成盲评包：每题已提交事实背景 + 甲/乙/丙 文本 + 空选票行。

不读 order.json，不写臂名、判分结果或预判结论。
输出：step5/review-packet.md

用法（仓库根）：
  /d/software/Anaconda/envs/nndl_proj/python.exe -X utf8 \
    experiments/world-components/parallel/scene_expression/build_packet.py
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
STEP4 = HERE / "step4"
STEP5 = HERE / "step5"
SAMPLES = HERE / "step1/narration-split-samples.export.json"
INPUTS = HERE / "frozen/inputs.json"

CN = {1: "一", 2: "两", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八",
      9: "九", 10: "十"}
UNIT = {"second": "秒", "minute": "分钟", "hour": "小时", "day": "天"}


def background(sample):
    st = sample["after"]
    ini = st["initial"]
    proto = st["protagonistId"]
    place = st["characters"][proto]["position"]["containerId"]
    lines = [f"- 地点：{ini['locations'][place]['name']}（当前视角人物所在处）",
             f"- 时间：{st['time']['dateTime'].replace('T', ' ')}"]
    present = [c for c in st["characters"].values()
               if (c.get("position") or {}).get("containerId") == place]
    names = "、".join(ini["characters"][c["id"]]["name"] for c in present)
    lines.append(f"- 在场人物：{names}")
    items = [i for i in st["items"].values()
             if (i.get("position") or {}).get("containerId") == place]
    if items:
        lines.append("- 可见物品：" + "、".join(ini["items"][i["id"]]["name"] for i in items))
    ta = sample["timeAdvance"]["duration"]
    lines.append(f"- 本点时间推进：约{CN.get(ta['amount'], ta['amount'])}{UNIT[ta['unit']]}")
    facts = [f"{f['phrase']}" for f in sample["requiredFacts"]]
    lines.append("- 已提交、必须表达的事实：" + "；".join(facts))
    goals = []
    for c in st["characters"].values():
        for t in c.get("tasks", {}).values():
            if t.get("status") != "achieved":
                goals.append(f"{ini['characters'][c['id']]['name']}→{t['goal']}")
    if goals:
        lines.append("- 背景任务（尚未完成，不表示完成）：" + "；".join(goals))
    return "\n".join(lines)


def main():
    samples = {s["id"]: s for s in
               json.loads(SAMPLES.read_text(encoding="utf-8"))["samples"]}
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    ballot = json.loads((STEP4 / "ballot/ballot.json").read_text(encoding="utf-8"))

    out = ["# 自然度盲评包（十题）", "",
           f"问题：{ballot['question']}", "",
           f"每题从 甲/乙/丙 中选一份，或选「{ballot['optionNoDifference']}」。可以写一句理由。",
           "这是盲评：这里不显示臂名，也不提供任何自动评分结果。评审结束前请不要查看 `step4/ballot/order.json`。",
           "四题标了“仅程序输出”的，三份文本完全相同（该点没有模型句）；照常记录你的选择即可，汇总时它们不计入有效配对。", ""]

    for item in ballot["items"]:
        sid = item["sampleId"]
        out += [f"## {sid}" + ("（仅程序输出）" if item["programOnly"] else ""), "",
                "背景（已提交状态）：", background(samples[sid]), ""]
        for opt in item["options"]:
            out += [f"**{opt['label']}**：{opt['text']}", ""]
        out += ["选择：______　　理由（可选）：", "", "---", ""]

    STEP5.mkdir(exist_ok=True)
    (STEP5 / "review-packet.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("items", len(ballot["items"]), "out", STEP5 / "review-packet.md")


if __name__ == "__main__":
    main()
