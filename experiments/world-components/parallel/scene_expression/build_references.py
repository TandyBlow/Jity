"""三题参照段落的分句来源表；逐条校验来源路径在冻结样本里真实存在。

只读：step1/narration-split-samples.export.json。
只写：step6/references/reference-clauses.jsonl。

用法（仓库根）：
  /d/software/Anaconda/envs/nndl_proj/python.exe -X utf8 \
    experiments/world-components/parallel/scene_expression/build_references.py
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SAMPLES = HERE / "step1/narration-split-samples.export.json"
OUT = HERE / "step6/references/reference-clauses.jsonl"

CLAUSES = [
    # ns-loc-appear-1
    ("ns-loc-appear-1", 0, "大约一分钟过去", ["timeAdvance.duration"], False,
     "Δ 时间推进 1 分钟"),
    ("ns-loc-appear-1", 1, "走廊两侧的储物柜都关上了",
     ["after.characters.person_c.position.containerId",
      "delta.corridor.appearanceChanges.chg_corr_1.text"], False,
     "视角人物在走廊；本点唯一变化原文"),
    ("ns-loc-appear-1", 2, "学生A谨慎地站在一边",
     ["initial.characters.person_a.initialPersonality",
      "after.characters.person_a.position.containerId"], False,
     "个性与在场位置"),
    ("ns-loc-appear-1", 3, "学生B仍靠着窗",
     ["initial.characters.person_b.initialAppearance"], False,
     "初始外貌原文“靠窗站着”"),
    ("ns-loc-appear-1", 4, "那把黄铜钥匙还搁在走廊里",
     ["initial.items.item_key.initialAppearance",
      "after.items.item_key.position.containerId"], False,
     "物品外貌与位置；本点无位置变化"),
    ("ns-loc-appear-1", 5, "主角要取回柜子里的东西",
     ["after.characters.person_c.tasks.task_shelf.goal"], False,
     "待办任务，写作待办，不带完成含义"),

    # ns-multi-1
    ("ns-multi-1", 0, "两分钟过去", ["timeAdvance.duration"], False,
     "Δ 时间推进 2 分钟"),
    ("ns-multi-1", 1, "学生A从走廊去了大厅",
     ["delta.person_a.positionSet.from", "delta.person_a.positionSet.to"], False,
     "位置事实，起点与终点都在 状态/Δ 里"),
    ("ns-multi-1", 2, "走廊里那把黄铜钥匙没有动",
     ["after.items.item_key.position.containerId",
      "initial.items.item_key.initialAppearance"], False,
     "位置未变是可核对事实，不是编造“没动”的动作"),
    ("ns-multi-1", 3, "表面却蒙上了一层灰尘",
     ["delta.item_key.appearanceChanges.chg_key_1.text"], False,
     "外貌变化原文"),
    ("ns-multi-1", 4, "主角已经把柜子里的东西取回来了",
     ["delta.person_c.tasksAchieved", "before.characters.person_c.tasks.task_shelf.goal"],
     False, "任务达成；不写完成方式与时间"),

    # ns-pers-1
    ("ns-pers-1", 0, "一分钟过去", ["timeAdvance.duration"], False,
     "Δ 时间推进 1 分钟"),
    ("ns-pers-1", 1, "学生B变得健谈起来",
     ["delta.person_b.personalityChanges.chg_b_1.text"], False,
     "个性变化原文"),
    ("ns-pers-1", 2, "话一句接一句", [], True,
     "由“变得健谈”展开的行为描述，非新事件；允许删除而不影响必述"),
    ("ns-pers-1", 3, "人也松快了些",
     ["delta.person_b.sanitySet", "before.characters.person_b.sanity"], False,
     "理智方向上升的允许身体表达；数值不入正文"),
    ("ns-pers-1", 4, "他帮主角熟悉校园这件事，到这儿算完成了",
     ["delta.person_b.tasksAchieved", "before.characters.person_b.tasks.task_intro.goal"],
     False, "任务达成，目标文本作标识"),

    # 面板冲突登记（不是段落分句，单独一行）
    ("ns-pers-1", None, "（面板项）理智值 12",
     ["delta.person_b.sanitySet"], False,
     "必述要求句内出现数值，但与故事文体冲突；建议留在状态面板，判分器口径需改"),
]


def resolve(sample, path):
    """支持：initial./after. 点路径、delta.<eid>.<field>、delta.<eid>.<list>.<id>.<field>、
    delta.<eid>.positionSet.from/to、timeAdvance.duration。"""
    cur = sample
    parts = path.split(".")
    head = parts[0]
    if head in ("initial", "after", "before"):
        cur = {"initial": sample["before"]["initial"], "before": sample["before"],
               "after": sample["after"]}[head]
        for part in parts[1:]:
            cur = cur[part]
        return cur
    if head == "timeAdvance":
        cur = sample["timeAdvance"]
        for part in parts[1:]:
            cur = cur[part]
        return cur
    if head == "delta":
        cur = sample["delta"]
        eid, field = parts[1], parts[2]
        cur = cur[eid]
        if field == "positionSet" and len(parts) > 3:
            # 起点在 before，终点在 after
            if parts[3] == "from":
                return sample["before"]["characters"][eid]["position"]["containerId"]
            return sample["after"]["characters"][eid]["position"]["containerId"]
        cur = cur[field]
        if isinstance(cur, list) and len(parts) > 3:
            target = parts[3]
            for item in cur:
                if item.get("id") == target:
                    return item[parts[4]]
            raise KeyError(f"{path}: 列表里没有 {target}")
        return cur
    raise KeyError(path)


def main():
    doc = json.loads(SAMPLES.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in doc["samples"]}
    rows = []
    for sid, idx, clause, sources, inference, note in CLAUSES:
        sample = by_id[sid]
        for path in sources:
            resolve(sample, path)
        rows.append({"sampleId": sid, "clauseIndex": idx, "clause": clause,
                     "sources": sources, "inference": inference, "note": note,
                     "author": "executor-reference（非模型输出）"})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                   encoding="utf-8")
    print(f"{len(rows)} 条，来源路径全部可解析 -> {OUT}")


if __name__ == "__main__":
    main()
