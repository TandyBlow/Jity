"""分句事实核验：逐句给 supported / unsupported / undetermined、实际来源与理由。

输入：step4/clauses.jsonl（自动候选）、step3/drafts.jsonl、frozen 输入与素材。
输出：step5/clauses.jsonl、step5/adjudication.json。

这是执行方复核（agent pre-review），不是独立人工评审；不确定处保持 undetermined。
用法（仓库根）：
  /d/software/Anaconda/envs/nndl_proj/python.exe -X utf8 \
    experiments/world-components/parallel/scene_expression/adjudicate.py
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
STEP4 = HERE / "step4"
STEP5 = HERE / "step5"

# (sampleId, arm, clauseIndex) -> 决策
# label / sourceId / note / flags
D = {}


def S(sid, arm, idx, label, sources, note, **flags):
    D[(sid, arm, idx)] = {"label": label, "sourceId": sources, "note": note,
                          **{k: v for k, v in flags.items() if v}}


# ---------- 程序句 ----------
PROG_TIME = {
    "ns-appear-1": ("timeAdvance:1minute", "before/after 相隔 1 分钟"),
    "ns-loc-appear-1": ("timeAdvance:1minute", "before/after 相隔 1 分钟"),
    "ns-task-1": ("timeAdvance:2minute", "before/after 相隔 2 分钟"),
    "ns-task-time-1": ("timeAdvance:1minute", "before/after 相隔 1 分钟"),
    "ns-pers-1": ("timeAdvance:1minute", "before/after 相隔 1 分钟"),
    "ns-multi-1": ("timeAdvance:2minute", "before/after 相隔 2 分钟"),
    "ns-empty-1": ("timeAdvance:2minute", "before/after 相隔 2 分钟"),
    "ns-cont-1": ("timeAdvance:2second", "before/after 相隔 2 秒"),
    "ns-cont-2": ("timeAdvance:2minute", "before/after 相隔 2 分钟"),
    "ns-cont-3": ("timeAdvance:5minute", "before/after 相隔 5 分钟"),
}
TIME_SLOT = {"ns-task-time-1": 2}
for sid, (src, why) in PROG_TIME.items():
    for arm in "ABC":
        S(sid, arm, TIME_SLOT.get(sid, 0), "supported",
          ["program:timePassage", src],
          f"程序句；{why}，与已提交 timeAdvance 一致。")

S("ns-task-time-1", "A", 0, "supported", ["program:timeReached", "after.time=2026-09-01T12:00:00"],
  "程序句；after 时间 12:00:00，确为中午。冻结词表无「中午」，判分器残差属词表缺口。",
  programGap=True)
S("ns-task-time-1", "B", 0, "supported", ["program:timeReached", "after.time=2026-09-01T12:00:00"],
  "同上；中午由已提交时间支持，残差为词表缺口。", programGap=True)
S("ns-task-time-1", "C", 0, "supported", ["program:timeReached", "after.time=2026-09-01T12:00:00"],
  "同上；中午由已提交时间支持，残差为词表缺口。", programGap=True)

TASK = {
    "ns-task-1": ("person_c", "task_shelf", "取回柜子里的东西"),
    "ns-task-time-1": ("person_a", "task_noon", "坚持到中午"),
    "ns-pers-1": ("person_b", "task_intro", "帮主角熟悉校园"),
    "ns-multi-1": ("person_c", "task_shelf", "取回柜子里的东西"),
}
for sid, (eid, tid, goal) in TASK.items():
    for arm in "ABC":
        idx = {"ns-task-time-1": 1, "ns-task-1": 1, "ns-pers-1": 1, "ns-multi-1": 3}[sid]
        S(sid, arm, idx, "supported", [f"program:taskGoal", f"delta.{eid}.tasksAchieved:{tid}"],
          f"程序句；delta 记录 {eid} 达成 {tid}，目标文本取自 before 状态，未写完成动作细节。")
for arm in "ABC":
    S("ns-pers-1", arm, 4, "supported", ["program:sanityValue", "delta.person_b.sanitySet=12"],
      "程序句；delta 的 sanitySet 为 12，before 为 10，故写“升为”。")

# ---------- 钥匙灰尘：三臂同句，主体明确 ----------
for sid in ("ns-appear-1", "ns-multi-1"):
    for arm in ("AB" if sid == "ns-appear-1" else "ABC"):
        idx = 1 if sid == "ns-appear-1" else 2
        S(sid, arm, idx, "supported", ["item:item_key:change:chg_key_1"],
          "主体“钥匙”明确（世界中只有一把钥匙），省略的是材质形容词“黄铜”；已提交变化写的是同一把钥匙，信息未丢失。"
          "判分器按完整串比对记为遗漏，属字符串口径，不是真实遗漏。",
          programFalseNegative=True)

S("ns-appear-1", "C", 1, "supported",
  ["item:item_key:change:chg_key_1", "fact:appearanceText"],
  "已提交变化全文在句内；“钥匙外貌的变化”把字段名写进正文，属表达缺陷，不是事实错误。",
  expressionIssue="字段名“外貌的变化”进入正文")

# ---------- 地点外貌 ----------
for arm in "AC":
    S("ns-loc-appear-1", arm, 1, "supported",
      ["loc:corridor:change:chg_corr_1"],
      "已提交变化为“两侧的储物柜都被关上了”。初始状态写明走廊两侧就是储物柜，因此“走廊的储物柜都关上了”指向同一组储物柜，未丢失可区分的信息；"
      "“两侧”的措辞损失记为表达不完整，不记为真实遗漏。",
      expressionIssue="省略“两侧”，信息未丢但不精确",
      programFalseNegative=True)

S("ns-loc-appear-1", "B", 1, "supported",
  ["loc:corridor:change:chg_corr_1"],
  "已提交变化全文在句内；“走廊的两侧”略冗余，事实成立。")

# ---------- 人物变化 ----------
for arm in "ABC":
    S("ns-pers-1", arm, 2, "supported",
      ["char:person_b:personalityChange:chg_b_1", "char:person_b:initialPersonality"],
      "已提交变化为“变得健谈”；C 臂另引“外向”。事实成立；把字段名“性格变化/外貌的变化”写进句子是表达缺陷，不是事实错误。",
      expressionIssue="字段名“性格变化”进入正文")
for arm in "AB":
    S("ns-pers-1", arm, 3, "supported",
      ["delta.person_b.sanitySet=12", "char:person_b:initialPersonality"],
      "理智方向为升（10→12）；按既有 u240 判据，理智事实允许用身体状态（呼吸/胸口/气）表达方向，"
      "“发紧的感觉散了”与方向一致。首句提到“发紧”属对既有紧张的回指，不构成方向反转。",
      perspectiveHint="“感觉”偏内心，第三人称限知下宜写成可见动作，记视角提示")
S("ns-pers-1", "C", 3, "unsupported",
  ["char:person_b:initialPersonality"],
  "“学生B的外向,有些发紧”：把“发紧”（旧契约里表示理智下降的词）当作当下状态，而本点已提交方向是上升；"
  "后半句“有些发紧的感觉散了”虽回到放松，前半句仍与方向冲突且重复两次“有些发紧”。"
  "“外向”是性格，不是当下状态，句子也未形成合法命题。",
  factError=True, expressionIssue="重复“有些发紧”；性格词当作状态")

# ---------- 移动 + 钥匙动作 ----------
KEY_NOTE = ("已提交事实只有学生A从走廊移动到大厅；钥匙的位置本点未变化（仍在走廊）。"
            "钥匙可见、任务目标提到柜子，都不授权移动钥匙。该动作无对应已提交行动。")
S("ns-multi-1", "A", 1, "unsupported", [],
  "“学生A从走廊一路走到大厅”有提交事实支持；“钥匙从门槛上到大厅”是未经授权的新动作，且“门槛”未在任何状态里出现。"
  + KEY_NOTE, unauthorizedAction=True, factError=True)
S("ns-multi-1", "B", 1, "unsupported", [],
  "“学生A从走廊过来”缺目的地大厅（真实遗漏）；“把钥匙从门外挪到两侧”是未经授权的新动作，“门外/两侧”也无来源。"
  + KEY_NOTE, unauthorizedAction=True, realOmission="学生A 位于大厅")
S("ns-multi-1", "C", 1, "unsupported", [],
  "“学生A从走廊过来”缺目的地大厅（真实遗漏）；“把钥匙放在门外”是未经授权的新动作，门外无来源。"
  + KEY_NOTE, unauthorizedAction=True, realOmission="学生A 位于大厅")
S("ns-cont-1", "A", 1, "unsupported", [],
  "“学生A从走廊一路走到大厅”有提交事实支持；“钥匙从门槛上到大厅”是未经授权的新动作，门槛无来源。"
  + KEY_NOTE, unauthorizedAction=True, factError=True)
S("ns-cont-1", "B", 1, "unsupported", [],
  "“学生A从走廊过来”缺目的地大厅（真实遗漏）；“把钥匙从门外挪到两侧”是未经授权的新动作。"
  + KEY_NOTE, unauthorizedAction=True, realOmission="学生A 从走廊到了大厅")
S("ns-cont-1", "C", 1, "unsupported", [],
  "“学生A从走廊过来”缺目的地大厅（真实遗漏）；“把钥匙放在柜子里”是未经授权的新动作——任务目标提到柜子不等于授权把钥匙放进柜子。"
  + KEY_NOTE, unauthorizedAction=True, realOmission="学生A 从走廊到了大厅")

# ---------- 学生B 出汗 ----------
for arm in "ABC":
    S("ns-cont-2", arm, 1, "supported", ["char:person_b:appearanceChange:chg_b_2"],
      "与已提交外貌变化逐字一致，未新增动作。")


def main():
    rows = [json.loads(line) for line in
            (STEP4 / "clauses.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    out, missing = [], []
    for row in rows:
        key = (row["sampleId"], row["arm"], row["clauseIndex"])
        decision = D.get(key)
        if decision is None:
            missing.append(key)
            decision = {"label": "undetermined", "sourceId": [], "note": "未裁决，待人工核验"}
        merged = {**row, **decision,
                  "human": {**row.get("human", {}),
                            "reviewedBy": "agent-precheck",
                            "reviewStatus": "pending-independent-human"}}
        out.append(merged)

    STEP5.mkdir(exist_ok=True)
    (STEP5 / "clauses.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")

    stats = {}
    for arm in "ABC":
        arm_rows = [r for r in out if r["arm"] == arm]
        stats[arm] = {
            "clauses": len(arm_rows),
            "supported": sum(r["label"] == "supported" for r in arm_rows),
            "unsupported": sum(r["label"] == "unsupported" for r in arm_rows),
            "undetermined": sum(r["label"] == "undetermined" for r in arm_rows),
            "unauthorizedActionClauses": sum(bool(r.get("unauthorizedAction")) for r in arm_rows),
            "factErrorClauses": sum(bool(r.get("factError")) for r in arm_rows),
            "realOmissions": sorted({r["realOmission"] for r in arm_rows if r.get("realOmission")}),
            "expressionIssueClauses": sum(bool(r.get("expressionIssue")) for r in arm_rows),
            "programFalseNegatives": sum(bool(r.get("programFalseNegative")) for r in arm_rows),
            "perspectiveHints": sum(bool(r.get("perspectiveHint")) for r in arm_rows),
            "programGapClauses": sum(bool(r.get("programGap")) for r in arm_rows),
        }
    doc = {"reviewer": "agent-precheck（待独立人工确认）", "unadjudicated": missing,
           "byArm": stats}
    (STEP5 / "adjudication.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(doc, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
