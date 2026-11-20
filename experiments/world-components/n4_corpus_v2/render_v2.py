# N4 v2 renderer: the SINGLE renderer for the grouped interface (commit 2).
# Training inputs and runtime N4 prompts must be byte-identical shapes, so
# both sides import this module. The v2 input carries exactly what the task
# brief demands the model actually receive and USE:
#   - ordered sentence GROUPS (第N组) with their fact numbering,
#   - each group's time attribution (时间：约五分钟 | 无),
#   - each group's APPELLATION grants (称谓：顾北汀=他) — the only place a
#     pronoun is licensed; a name fallback grants nothing and the segment
#     is omitted, so the ablation (dropping 称谓) is a pure input change.
#
# Fact LINES reuse n4_render.render_entry unchanged — the same fact
# vocabulary the frozen flat model was trained on, so the frozen corpus
# renderings stay byte-identical (n4_units_regression.py).

import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
N4_DIR = HERE.parent / "n4_corpus"
for p in (str(HERE), str(N4_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from n4_render import num_cn, UNIT_CN, render_entry  # noqa: E402  (shared fact lines)


def render_group_header(group: dict) -> str:
    time_part = "无"
    t = group.get("time")
    if t and t.get("amount") is not None:
        time_part = f"约{num_cn(t['amount'])}{UNIT_CN.get(t['unit'], t['unit'])}"
    grants = group.get("coreference") or []
    if grants:
        app = "；称谓：" + "，".join(
            f"{g.get('name') or g['mention']}={g['pronoun']}" for g in grants)
    else:
        app = ""
    return f"第{group['index'] + 1}组（时间：{time_part}{app}）"


def render_input_v2(plan: list, facts: list) -> str:
    """plan: ordered groups [{index, factIds, coreference: [{mention,
    refersTo, pronoun}], time: {amount, unit}|None, headerPrefix}].
    facts: the flat fact entries (render_entry vocabulary) — lines are
    numbered by their plan order across groups."""
    by_id = {f["factId"]: f for f in facts}
    lines = ["叙事生成任务。"]
    counter = 0
    for group in plan["sentences"]:
        lines.append(render_group_header(group))
        for fid in group["factIds"]:
            counter += 1
            lines.append(f"{counter}. {render_entry(by_id[fid])}")
    lines.append("正文：")
    return "\n".join(lines)


def render_input_v2_ablated(plan: dict, facts: list) -> str:
    """The ablation arm: the SAME groups and time attribution with the
    称谓 grants stripped — everything else byte-identical. A model whose
    output does not move between this and the full input is not using the
    coreference information."""
    stripped = {**plan, "sentences": [
        {**g, "coreference": []} for g in plan["sentences"]]}
    return render_input_v2(stripped, facts)
