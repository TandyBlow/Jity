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
# Batch-1 unit extension (rendering must accept every legal TimeAdvance
# unit, not only the two units the frozen corpus happens to cover): the six
# units and their renderings mirror the frontend narration-split UNIT_CN
# table (frontend/src/lib/world-engine/runtime/narration-split.ts). The
# frozen corpus uses only minute/hour, so this table extension is
# byte-identical on every frozen rendering — proven by
# n4_units_regression.py before anything is re-judged.
UNIT_CN = {"second": "秒", "minute": "分钟", "hour": "小时",
           "day": "天", "month": "个月", "year": "年"}

# Commit-1 vocabulary extension: the five NEW fact kinds the pipeline now
# extracts (n2_perspective.RELATION_CN is the classification-side table; a
# unit test in narration_pipeline asserts the two tables stay equal, because
# this module must stay importable without the n2_selection tree on sys.path).
RELATION_CN = {"under": "下方", "above": "上方", "beside": "旁边",
               "in_front_of": "前方", "behind": "后方"}


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
    """SINGLE numeric formatter for 0..99 (v8: the old fixed table missed
    2/6/15/20/45/90 and broke 210 renderings). 个位 2 reads 两 in duration
    contexts (两分钟); 十位 reads standard 二十 — the recognizer's cn_to_int
    maps both back to 2. Shared by the corpus builder's rendered fields and
    the train/inference renderer.
    Batch-1 legal-input extension: 0 is a legal duration amount (瞬时点,
    non-negative per the time contract) and renders 零 — it used to raise
    ValueError. Amounts ≥ 100 render as Arabic digits (deterministic; the
    recognizer's cn_to_int accepts \\d+); they used to raise too. The frozen
    corpus covers 1..99 only, so those spaces stay byte-identical."""
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        raise ValueError(f"num_cn out of range: {amount}")
    if amount == 0:
        return "零"
    if amount > 99:
        return str(amount)
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
        # round 13 single-variable arm: the plan carries from/to, so the
        # direction is program-computed and stated explicitly in the shared
        # renderer (r2-large left it implicit and the model produced wrong
        # direction verbs on chain rows).
        direction = ("上升" if e["to"] > e["from"]
                     else "下降" if e["to"] < e["from"] else "不变")
        return f"理智：{e['name']} {e['from']}→{e['to']}（{direction}）"
    if kind == "appearance_changed":
        return f"外貌：{e['name']} {e['text']}"
    if kind == "positioned_at":
        return f"现状：{e['name']} 已在{e['at']}"
    if kind == "time":
        return f"时间推进：约{num_cn(e['amount'])}{UNIT_CN[e['unit']]}"
    if kind == "no_change":
        return "无变化"
    # ---- commit-1 kinds (not yet in the frozen model's trained vocabulary;
    # the frozen chain stops with kind-awaiting-model-track before rendering
    # these — the entries exist so the N3->N4 interface and the commit-2
    # model track can consume them without changing any frozen rendering)
    if kind == "position_relative":
        rel = RELATION_CN.get(e.get("relation"), e.get("relation"))
        if e.get("op") == "removed":
            return f"相对位置：{e['name']} 不再在{e['targetName']}{rel}"
        return f"相对位置：{e['name']} 现在在{e['targetName']}{rel}"
    if kind == "slot_changed":
        if e.get("op") == "removed":
            return f"槽位：{e['name']} 不再位于{e['at']}的{e['slotLabel']}"
        return f"槽位：{e['name']} 现在位于{e['at']}的{e['slotLabel']}"
    if kind == "appearance_removed":
        return f"外貌移除：{e['name']} 不再保有「{e['text']}」"
    if kind == "personality_removed":
        return f"个性移除：{e['name']} 不再保有「{e['text']}」"
    if kind == "subtask_added":
        parent = f"（隶属「{e['parentGoal']}」）" if e.get("parentGoal") else ""
        return f"新任务：{e['name']} 接到「{e['goal']}」{parent}"
    raise ValueError(f"unknown plan kind {kind}")


def render_input(plan: list) -> str:
    lines = [f"{i + 1}. {render_entry(e)}" for i, e in enumerate(plan)]
    return "叙事生成任务。\n事实：\n" + "\n".join(lines) + "\n正文："
