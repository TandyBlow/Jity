# Preview the real N2 -> N3 -> N4-input path on the approved 12 cases.
#
# The earlier input preview rendered the raw approved facts directly. This
# one runs the actual component chain:
#   approved facts (N1-shaped, with `outcome` as the surface action result)
#     -> N2 classify_facts(may_policy="select", visible_other_actions=True)
#     -> N3 plan_v3 + check_plan_v3
#     -> N4 formal input renderer (render_plan_input, strict)
# and reports every dropped fact, group/plan refusal and token length.
#
# `visible_other_actions` is a new opt-in narrative selection arm (feeds
# N5): another
# character's visible move/outcome/appearance at the same place is a `may`
# fact; their task goal/status and inner state stay invisible. The old v2
# arm keeps the flag off, so its behaviour is unchanged.
#
# No model call, no training.

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
sys.path.insert(0, str(WC))
sys.path.insert(0, str(HERE))

import n2_perspective as n2  # noqa: E402
import n3_organize as n3  # noqa: E402
import n4_input_renderer as n4r  # noqa: E402

DOC = REPO / "design" / "world-engine-reports" / "components" / \
    "n4-narrative-pipeline-input-preview.md"
OUT = HERE / "pipeline_preview.json"


def selftest_n2():
    facts = [
        {"factId": "f0", "kind": "outcome", "entityId": "a", "name": "沈砚",
         "at": "L", "resultText": "x"},
        {"factId": "f1", "kind": "outcome", "entityId": "b", "name": "阿棠",
         "at": "L", "resultText": "y"},
        {"factId": "f2", "kind": "moved", "entityId": "b", "name": "顾行舟",
         "from": "R", "to": "L", "at": "L"},
        {"factId": "f3", "kind": "sanity_changed", "entityId": "b",
         "name": "阿棠", "from": 1, "to": 2, "at": "L"},
        {"factId": "f4", "kind": "task_achieved", "entityId": "b",
         "name": "阿棠", "goal": "g", "at": "L"},
        {"factId": "f5", "kind": "time", "amount": 1, "unit": "minute"},
    ]
    persp = {"type": "protagonist", "entityId": "a", "at": "L"}
    rows = []
    for flag in (False, True):
        r = n2.classify_facts(facts, persp, may_policy="select",
                              visible_other_actions=flag)
        rows.append({"flag": flag, "selected": r["selectedFactIds"],
                     "decisions": [(d["factId"], d["class"], d["ground"],
                                    d["selected"]) for d in r["decisions"]]})
    # assertions: self outcome must; other visible outcome/move may only with
    # the flag; other inner state and task goal stay invisible either way
    old, new = rows
    assert old["selected"] == ["f0", "f5"], old
    assert new["selected"] == ["f0", "f1", "f2", "f5"], new
    assert ("f3", "invisible", "inner-state-private", False) in new["decisions"]
    assert ("f4", "invisible", "only-others", False) in new["decisions"]
    return rows


def main() -> int:
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(
        str(WC / "n4_corpus_v2" / "ckpt-v2"), legacy=False)
    world = json.loads((HERE / "world.json").read_text(encoding="utf-8"))
    cases = [json.loads(l) for l in
             (HERE / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
             if l.strip()]
    names = {cid: ch["name"] for cid, ch in world["characters"].items()}
    selftest = selftest_n2()
    rows = []
    for c in cases:
        facts = [dict(f) for f in c["facts"]]
        for f in facts:
            if f.get("entityId") in world["characters"]:
                f["entityGroup"] = "characters"
        res = n2.classify_facts(
            facts, c["perspective"], may_policy="select",
            visible_other_actions=True)
        selected_ids = set(res["selectedFactIds"])
        selected = [f for f in facts if f["factId"] in selected_ids]
        plan = n3.plan_v3(selected, names, cross_group_guard=True)
        problems = ([] if "refusal" in plan
                    else n3.check_plan_v3(plan, selected, names))
        input_text = (n4r.render_plan_input(
            c, plan, world, strict=True,
            selected_fact_ids=res["selectedFactIds"])
            if "refusal" not in plan else "")
        target = c["narrative"]
        dropped = [f["factId"] for f in facts
                   if f["factId"] not in selected_ids]
        rows.append({
            "id": c["id"], "title": c["title"],
            "n2Status": res["status"], "n2Summary": res["summary"],
            "decisions": res["decisions"], "dropped": dropped,
            "plan": plan, "planProblems": problems,
            "input": input_text, "target": target,
            "inputTokens": len(tok(input_text).input_ids),
            "targetTokens": len(tok(target).input_ids),
        })
    OUT.write_text(json.dumps({"selftest": selftest, "cases": rows},
                              ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    max_in = max(r["inputTokens"] for r in rows)
    min_in = min(r["inputTokens"] for r in rows)
    max_out = max(r["targetTokens"] for r in rows)
    min_out = min(r["targetTokens"] for r in rows)
    lines = [
        "# N4 管线输入预览 v0（已审通过语料）",
        "",
        "日期：2026-11-02。语料已审通过；本文件验证 **N2 → N3 → N4 输入**"
        " 的真实链路，不训练、不调用模型。N1 的 `outcome/resultText` 已在"
        " `narrative_outcome=True` 下实现（缺 resultText 停机，见 "
        "`n4-narrative-runner.md`）；本预览仍用已审 facts 验证 N2/N3/旧句子输入。",
        "",
        "> **输入版本（2026-11-02）：** 本文是旧句子输入（legacy），仅供冻结"
        " v2/v3 模型与字节回归；当前 N4 输入契约是 N4.0 结构化记录，见"
        " `n4-narrative-input-packing-preview.md`。N4=生成模型，N5=核对。",
        "",
        "## 链路",
        "",
        "1. 已审 facts（N1 形状；`outcome` 是表面行动结果，不是任务 goal）；",
        "2. N2 `classify_facts(may_policy=select, visible_other_actions=True)`；",
        "3. N3 `plan_v3` + `check_plan_v3`；",
        "4. N4 `render_plan_input`。",
        "",
        "`visible_other_actions` 是新增的 N4 叙事选择臂：他人在同地的可见"
        "移动/行动结果/可见变化是 `may`；他人的任务 goal/status 和内心状态"
        "仍然不可见。旧 v2 臂不传此参数，行为不变。",
        "",
        "## N2 选择臂自检",
        "",
        "| flag | selected | 关键决策 |",
        "| --- | --- | --- |",
    ]
    for row in selftest:
        lines.append(f"| {row['flag']} | {', '.join(row['selected'])} | "
                     + "；".join(f"{a}:{b}/{c}/{'选' if d else '弃'}"
                                 for a, b, c, d in row["decisions"]) + " |")
    lines += [
        "",
        "断言：旧臂只选自己 outcome + time；新臂加入同地他人 outcome/move；"
        "他人 sanity 和 task_achieved 仍不可见。",
        "",
        "## 结果",
        "",
        f"- 输入 **{min_in}–{max_in}** tokens；目标 **{min_out}–{max_out}**。",
        "- 当前 v2 N4 `max_input=160` / `max_output=96` 不够；新训练建议"
        " `max_input≥384`、`max_output≥128`（T5 支持 512）。",
        "- 12 例是开发集；训练需扩样与冻结留出。",
        "",
        "## 汇总",
        "",
        "| 案例 | 输入 | 目标 | 丢弃 facts | N3 plan |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(f"| {r['id']} {r['title']} | {r['inputTokens']} | "
                     f"{r['targetTokens']} | "
                     f"{', '.join(r['dropped']) or '无'} | "
                     f"{'refusal' if 'refusal' in r['plan'] else 'ok'} |")
    lines += ["", "## 每例", ""]
    for r in rows:
        lines += [f"### {r['id']} · {r['title']}", "",
                  f"- N2: {r['n2Status']}；selected={r['n2Summary'].get('selected')}；"
                  f"must={r['n2Summary'].get('must')}；may={r['n2Summary'].get('may')}；"
                  f"invisible={r['n2Summary'].get('invisible')}",
                  f"- 丢弃：{', '.join(r['dropped']) or '无'}",
                  f"- N3 problems：{'; '.join(r['planProblems']) or '无'}",
                  f"- N3 plan：`{json.dumps(r['plan'], ensure_ascii=False)}`",
                  "", "**Input**", "", "```text", r["input"], "```", "",
                  f"**Target**（{r['targetTokens']} tokens）", "",
                  "> " + r["target"], ""]
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"pipeline inputs {min_in}-{max_in}; targets {min_out}-{max_out}; "
          f"dropped {[(r['id'], r['dropped']) for r in rows if r['dropped']]}; "
          f"-> {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
