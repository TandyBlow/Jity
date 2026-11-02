# Preview the N4.0 structured input on the approved 12 cases.
#
# Chain: approved facts -> N2 -> N3 plan -> N4.0 pack_narrative_input.
# The pack carries records (ids/kinds/fields), not pre-written sentences.
# No model call, no training, no tokenizer-free claims.

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
    "n4-narrative-input-packing-preview.md"
OUT = HERE / "pack_preview.json"


def main() -> int:
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(
        str(WC / "n4_corpus_v2" / "ckpt-v2"), legacy=False)
    world = json.loads((HERE / "world.json").read_text(encoding="utf-8"))
    cases = [json.loads(line) for line in
             (HERE / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    names = {cid: ch["name"] for cid, ch in world["characters"].items()}
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
        packed = n4r.pack_narrative_input(
            c, plan, world, selected_fact_ids=res["selectedFactIds"])
        assert packed["status"] == "ok", (c["id"], packed)
        rows.append({
            "id": c["id"], "title": c["title"],
            "n2Summary": res["summary"], "planProblems": problems,
            "plan": plan, "input": packed["input"],
            "inputVersion": packed["version"], "target": c["narrative"],
            "inputTokens": len(tok(packed["input"]).input_ids),
            "targetTokens": len(tok(c["narrative"]).input_ids),
        })
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    max_in = max(r["inputTokens"] for r in rows)
    min_in = min(r["inputTokens"] for r in rows)
    max_out = max(r["targetTokens"] for r in rows)
    min_out = min(r["targetTokens"] for r in rows)
    lines = [
        "# N4.0 结构化输入预览 v1（已审通过语料）",
        "",
        "日期：2026-11-02。当前编号：**N4=叙事生成模型、N4.0=程序输入装配、"
        "N5=核对**。本文件验证 N4.0 的输出，不训练、不调用模型。",
        "",
        "与旧文本输入的区别：不再预写“沈砚从潮生巷来到旧灯塔。”这类完整"
        "事实句；N4.0 输出的是**带 id/kind 的结构化记录**，句子由 N4 生成"
        "模型自己写。旧句子格式仅保留给冻结的 v2/v3 模型与字节回归。",
        "",
        f"- 输入 **{min_in}–{max_in}** tokens；目标 **{min_out}–{max_out}**。",
        "- 旧 v2 模型 `max_input=160` / `max_output=96` 不适用；N4 新训练"
        "建议 `max_input≥448`（推荐 512）、`max_output≥128`。",
        "- 12 例是开发集；训练需扩样与冻结留出。",
        "",
        "## 汇总",
        "",
        "| 案例 | 输入 | 目标 | N2 选集 | N3 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        s = r["n2Summary"]
        lines.append(f"| {r['id']} {r['title']} | {r['inputTokens']} | "
                     f"{r['targetTokens']} | selected={s['selected']} | "
                     f"{'ok' if not r['planProblems'] else 'problems'} |")
    lines += ["", "## 每例", ""]
    for r in rows:
        lines += [f"### {r['id']} · {r['title']}", "", "**Input**", "",
                  "```text", r["input"], "```", "",
                  "**Target**", "", "> " + r["target"]]
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"pack inputs {min_in}-{max_in}; targets {min_out}-{max_out}; "
          f"-> {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
