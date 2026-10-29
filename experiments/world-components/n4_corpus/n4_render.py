# N4 fact-plan rendering: the SINGLE renderer shared by training and
# inference (finetune round). Training inputs and runtime N4 prompts must be
# byte-identical shapes, so the renderer lives here and both sides import
# it. The rendering is deterministic from the plan; `rendered` (the seed
# builder's hint field) is deliberately NOT used here — value+unit are
# converted through the same table the recognizer accepts, keeping one
# numeric vocabulary across train/eval/check.

import hashlib
import pathlib

CN_DIGITS = {0: "零", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六",
             7: "七", 8: "八", 9: "九"}
UNIT_CN = {"minute": "分钟", "hour": "小时"}


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def corpus_hashes() -> dict:
    """Run-record provenance (review round 9): corpus files and this
    renderer, hashed — training and eval reports both embed it so a report
    names exactly which bytes produced it."""
    here = pathlib.Path(__file__).resolve().parent
    out = {"n4_render.py": sha256_file(here / "n4_render.py")}
    for name in ("corpus.seeds.jsonl", "rewrites.jsonl"):
        out[name] = sha256_file(here / name)
    return out


def num_cn(amount: int) -> str:
    """SINGLE numeric formatter for 1..99 (v8: the old fixed table missed
    2/6/15/20/45/90 and broke 210 renderings). 个位 2 reads 两 in duration
    contexts (两分钟); 十位 reads standard 二十 — the recognizer's cn_to_int
    maps both back to 2. Shared by the corpus builder's rendered fields and
    the train/inference renderer."""
    if not (1 <= amount <= 99):
        raise ValueError(f"num_cn out of range: {amount}")
    tens, ones = divmod(amount, 10)
    if tens == 0:
        return "两" if amount == 2 else CN_DIGITS[amount]
    if tens == 1:
        return "十" + (CN_DIGITS[ones] if ones else "")
    head = CN_DIGITS[tens] + "十"
    return head if ones == 0 else head + CN_DIGITS[ones]


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
