"""Deterministic offered-option policies; no player model or outcome forcing."""
from __future__ import annotations

import random
from ..storage import digest

STRATEGIES = {
    "mission": ("任务", "前往", "推进", "报到", "跟随", "提交", "接受", "完成", "主线", "调查"),
    "explore": ("询问", "交谈", "观察", "查看", "搜索", "探索", "了解", "检查", "痕迹", "档案"),
    "items": ("使用", "消耗", "服用", "交给", "递交", "拾取", "收下", "获取", "拿取", "装备", "通行卡", "物品"),
    "risk": ("冒险", "强行", "潜入", "拒绝", "独自", "挑战", "质问", "追踪", "突破", "战斗", "真相"),
}


def choose(checkpoint: dict, strategy: str, seed: int, turn: int, history=()):
    if strategy not in STRATEGIES:
        raise ValueError("Unknown strategy: " + strategy)
    output = checkpoint.get("output") or {}
    options = output.get("options") or []
    rng = random.Random(int(digest({"seed": seed, "turn": turn, "purpose": "action_policy"})[:16], 16))
    # Separate dice seed: selecting a riskier option never selects a desired die.
    die = random.Random(int(digest({"seed": seed, "turn": turn, "purpose": "d20"})[:16], 16)).randint(1, 20)
    if not options:
        return {"action": "开始游戏" if turn == 1 else "继续前进", "option_index": None,
                "roll": die, "policy": strategy, "seed": seed, "scores": [],
                "reason": "No offered options; passive continuation is resolved by Jity."}
    checks = output.get("option_checks") or []
    scores = []
    for i, option in enumerate(options):
        score = sum(3 for word in STRATEGIES[strategy] if word in option)
        if strategy == "risk" and i < len(checks) and checks[i] and checks[i].get("requires_check", True):
            score += 4
        # Avoid endlessly repeating an offered action, without inventing facts.
        score -= 4 * sum(1 for old in list(history)[-4:] if old == option)
        scores.append({"index": i, "action": option, "score": score, "tie_break": rng.random()})
    selected = max(scores, key=lambda row: (row["score"], row["tie_break"]))
    return {"action": selected["action"], "option_index": selected["index"], "roll": die,
            "policy": strategy, "seed": seed, "scores": scores,
            "reason": "Highest keyword/check score among current offered actions; seeded tie-break."}


def coverage(checkpoints: list[dict], calls=()):
    """Report observed structured evidence, never infer successful coverage from policy."""
    observed = {}
    previous = None
    previous_progress = {}
    for checkpoint in checkpoints:
        turn = checkpoint.get("turn")
        state = checkpoint.get("state") or {}
        output = checkpoint.get("output") or {}
        def add(name, evidence):
            observed.setdefault(name, []).append({"turn": turn, "evidence": evidence})
        if output.get("dialogue"):
            add("npc_dialogue", [v.get("speaker") for v in output["dialogue"]])
        check = output.get("action_check")
        if check:
            add("action_checks", check)
            if check.get("outcome") in ("failure", "fumble"):
                add("failed_checks", check)
        if previous:
            if state.get("current_location") != previous.get("current_location"):
                add("location_changes", state.get("current_location"))
            for field in ("health", "sanity"):
                if state.get(field) != previous.get(field):
                    add("status_changes", {field: [previous.get(field), state.get(field)]})
            old = {v.get("name") for v in previous.get("items", [])}
            new = {v.get("name") for v in state.get("items", [])}
            if new - old:
                add("item_gains", sorted(new - old))
            if old - new:
                add("item_removals", sorted(old - new))
        tracker = (state.get("_memory_controller") or {}).get("score_tracker", [])
        # SCORE exports vary; retain actual state evidence instead of lexical claims.
        consumed = [item for item in tracker if isinstance(item, dict) and item.get("state") == "consumed"] if isinstance(tracker, list) else []
        if consumed:
            add("consumed_item_state", consumed)
        progress = checkpoint.get("progress") or {}
        stage = {key: progress.get(key) for key in ("arc_index", "session_index")}
        old_stage = {key: previous_progress.get(key) for key in ("arc_index", "session_index")}
        if stage != old_stage:
            add("campaign_stages", stage)
        import json
        anchors = progress.get("revealed_anchors", [])
        old_anchors = previous_progress.get("revealed_anchors", [])
        if isinstance(anchors, str):
            anchors = json.loads(anchors)
        if isinstance(old_anchors, str):
            old_anchors = json.loads(old_anchors)
        added_anchors = sorted(set(anchors) - set(old_anchors))
        if added_anchors:
            add("anchors", added_anchors)
        previous_progress = progress
        if output.get("game_over"):
            add("ending", output.get("game_over_reason"))
        previous = state
    for row in calls:
        scope = row.get("scope", row.get("context", row.get("metadata", {})))
        purpose = scope.get("purpose", row.get("purpose", ""))
        if "summary" in purpose:
            observed.setdefault("summary_calls", []).append({"purpose": purpose, "sequence": row.get("sequence", row.get("id"))})
    targets = ("npc_dialogue", "location_changes", "status_changes", "item_gains", "item_removals", "consumed_item_state", "failed_checks", "summary_calls", "ending")
    return {"observed": observed, "uncovered": [name for name in targets if name not in observed],
            "notes": ["Policy intent is not evidence of coverage.", "Different endings/branches are reported across games; no state was forced."]}
