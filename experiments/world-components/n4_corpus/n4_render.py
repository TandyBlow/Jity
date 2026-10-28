# N4 fact-plan rendering: the SINGLE renderer shared by training and
# inference (finetune round). Training inputs and runtime N4 prompts must be
# byte-identical shapes, so the renderer lives here and both sides import
# it. The rendering is deterministic from the plan; `rendered` (the seed
# builder's hint field) is deliberately NOT used here — value+unit are
# converted through the same table the recognizer accepts, keeping one
# numeric vocabulary across train/eval/check.

CN = {1: "一", 3: "三", 8: "八", 12: "十二", 25: "二十五", 40: "四十"}
UNIT_CN = {"minute": "分钟", "hour": "小时"}


def num_cn(amount: int) -> str:
    if amount in CN:
        return CN[amount]
    if 10 < amount < 20:
        return "十" + CN[amount - 10]
    if amount % 10 == 0 and amount // 10 in CN:
        return CN[amount // 10] + "十"
    raise ValueError(f"no Chinese numeral mapping for {amount} — extend CN")


def render_entry(e: dict) -> str:
    kind = e["kind"]
    if kind == "moved":
        return f"位置：{e['name']} 从{e['from']}到{e['to']}"
    if kind == "task_achieved":
        return f"任务达成：{e['name']}「{e['goal']}」"
    if kind == "personality_changed":
        return f"个性：{e['name']}{e['text']}"
    if kind == "sanity_changed":
        return f"理智：{e['name']} {e['from']}→{e['to']}"
    if kind == "appearance_changed":
        return f"外貌：{e['name']} {e['text']}"
    if kind == "positioned_at":
        return f"现状：{e['name']} 已在{e['at']}"
    if kind == "time":
        return f"时间推进：约{num_cn(e['amount'])}{UNIT_CN[e['unit']]}"
    if kind == "no_change":
        return "无变化"
    raise ValueError(f"unknown plan kind {kind}")


def render_input(plan: list) -> str:
    lines = [f"{i + 1}. {render_entry(e)}" for i, e in enumerate(plan)]
    return "叙事生成任务。\n事实：\n" + "\n".join(lines) + "\n正文："
