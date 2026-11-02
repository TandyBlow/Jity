# Render the approved N4 narrative cases and report input/target lengths.
# This is a contract preview, not training:
#   - input = render_narrative.render_input (scene + character personality +
#     visible items + facts; time internal/vague; no task goals/IDs);
#   - target = the approved narrative;
#   - token counts use the real T5Tokenizer from ckpt-v2 (legacy=False).
#
# The current v2 N4 training max input is 160; the new contract is longer.
# Report the actual max and recommend a larger max for the future training.

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
sys.path.insert(0, str(HERE))

import render_narrative  # noqa: E402

DOC = REPO / "design" / "world-engine-reports" / "components" / \
    "n4-narrative-input-preview.md"
OUT = HERE / "input_preview.json"


def main() -> int:
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(
        str(WC / "n4_corpus_v2" / "ckpt-v2"), legacy=False)
    world = render_narrative.load_world()
    cases = [json.loads(l) for l in
             (HERE / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
             if l.strip()]
    rows = []
    for c in cases:
        text = render_narrative.render_input(c, world)
        rows.append({
            "id": c["id"], "title": c["title"],
            "input": text, "target": c["narrative"],
            "inputTokens": len(tok(text).input_ids),
            "targetTokens": len(tok(c["narrative"]).input_ids),
        })
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    max_in = max(r["inputTokens"] for r in rows)
    min_out = min(r["targetTokens"] for r in rows)
    max_out = max(r["targetTokens"] for r in rows)
    lines = [
        "# N4 叙事输入预览 v0（已审通过语料）",
        "",
        "日期：2026-11-02。语料已由用户审阅通过；本文件只预览 **N4 输入"
        "契约**，不训练、不调用模型。",
        "",
        "输入包含：场景/地点外貌、天气、时间（只到时段）、可见物、在场人物"
        "的性格/外貌/随身物、这一拍的事实约束。任务 goal/ID 不进入输入；"
        "结果只写 `resultText`；理智只给方向（松/沉），不给数值；时间只写"
        "“过去了一会儿（不写具体时长）”；视角为沈砚第三人称限知，他人"
        "只写可见动作。",
        "",
        f"- 真实 tokenizer（ckpt-v2 T5Tokenizer legacy=False）统计："
        f"输入 **{min(r['inputTokens'] for r in rows)}–{max_in}** tokens，"
        f"目标 {min_out}–{max_out} tokens。",
        f"- 当前 v2 N4 训练 `max_input=160` / `max_output=96`；新契约超过"
        f"两者，训练时须提高（建议 `max_input≥384`、`max_output≥128`；"
        f"T5 支持 512 输入）。",
        "- 12 例是**开发/审阅集**，不是训练集；训练需要扩样与冻结留出。",
        "",
        "## 审阅点",
        "",
        "- 输入是否包含角色个性（读取，不要求正文体现）",
        "- 输入是否没有任务 goal/ID、没有理智数值、没有具体时长",
        "- 输入是否没有新增具名人物/物品/地点",
        "- 输入长度是否可接受（浏览器/训练成本）",
        "",
        "## 汇总",
        "",
        "| 案例 | 输入 tokens | 目标 tokens |",
        "| --- | --- | --- |",
    ]
    for r in rows:
        lines.append(f"| {r['id']} {r['title']} | {r['inputTokens']} | "
                     f"{r['targetTokens']} |")
    lines += ["", "## 每例输入与目标", ""]
    for r in rows:
        lines += [f"### {r['id']} · {r['title']}", "",
                  "**Input**", "", "```text", r["input"], "```", "",
                  f"**Target**（{r['targetTokens']} tokens）", "",
                  "> " + r["target"], ""]
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"input tokens {min(r['inputTokens'] for r in rows)}-{max_in}; "
          f"target {min_out}-{max_out}; -> {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
