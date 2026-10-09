"""Deterministic campaign-ending selection.

The LLM writes the prose, but it does not choose whether or which ending fires.
That decision is made from explicit player intent configured on each route,
from exhausted survival stats for the campaign's bad ending, or from the
whole-campaign turn budget so a run always closes inside its allocation.
"""

from typing import Any

from app.schemas.campaign import EndingRoute

# Ending-category preference per budget outcome, best first. Campaign files
# use "true/good/normal/dark/bad"; the search falls through until a route
# matches, and a synthesized route covers campaigns with no routes at all.
_BUDGET_CATEGORIES = {
    "success": [("true", "good"), ("good", "normal"), ("normal",)],
    "incomplete": [("dark", "normal"), ("normal",), ("good", "dark")],
    "failure": [("bad",), ("dark",), ("normal",)],
}


def is_final_session(campaign: Any, progress: Any) -> bool:
    if campaign is None or progress is None or not campaign.arcs:
        return False
    last_arc_index = len(campaign.arcs) - 1
    return (
        progress.arc_index == last_arc_index
        and progress.session_index == len(campaign.arcs[last_arc_index].sessions) - 1
    )


def select_ending(campaign: Any, progress: Any, state: dict, player_action: str):
    """Return exactly one configured ending route, or None when play continues."""
    routes = getattr(campaign, "ending_routes", []) if campaign else []
    if not routes or not is_final_session(campaign, progress):
        return None

    if state.get("health", 100) <= 0 or state.get("sanity", 80) <= 0:
        return next((route for route in routes if route.category == "bad"), None)

    action = player_action.casefold()
    ranked: list[tuple[int, int, Any]] = []
    for index, route in enumerate(routes):
        matches = sum(1 for phrase in route.trigger_phrases if phrase.casefold() in action)
        if matches:
            ranked.append((matches, -index, route))
    return max(ranked, default=(0, 0, None), key=lambda item: (item[0], item[1]))[2]


def select_budget_ending(
    campaign: Any,
    progress: Any,
    state: dict,
    max_turns: int,
):
    """Ending forced by the whole-campaign turn budget.

    Fires on the budget's last turn (turns_total == max_turns - 1 before this
    turn commits), so the ending is presented within the allocation instead of
    truncating the story mid-air. Route chosen from what the player actually
    achieved — completed quests and revealed evidence put the outcome in the
    success band, a dead state in the failure band, anything else counts as
    incomplete.
    """
    if campaign is None or progress is None:
        return None
    try:
        budget = int(max_turns)
    except (TypeError, ValueError):
        return None
    if budget <= 0:
        return None
    try:
        turns_so_far = int(getattr(progress, "turns_total", 0))
    except (TypeError, ValueError):
        return None
    if turns_so_far < budget - 1:
        return None

    routes = list(getattr(campaign, "ending_routes", []) or [])
    if state.get("health", 100) <= 0 or state.get("sanity", 80) <= 0:
        outcome = "failure"
    else:
        quests = state.get("quests", []) or []
        done_marks = {"completed", "done", "achieved", "finished", "完成", "已完成"}
        completed = sum(
            1 for quest in quests
            if isinstance(quest, dict) and str(quest.get("status", "")).strip().lower() in done_marks
        )
        revealed = len(getattr(progress, "revealed_anchors", []) or [])
        if completed >= 1:
            outcome = "success"
        elif revealed >= 1:
            outcome = "incomplete"
        else:
            outcome = "failure"

    for categories in _BUDGET_CATEGORIES[outcome]:
        for route in routes:
            if route.category in categories:
                return route

    label = {"success": "预算内完成", "incomplete": "未完成的调查", "failure": "失败的调查"}[outcome]
    return EndingRoute(
        id=f"budget-{outcome}",
        name=f"回合预算耗尽·{label}",
        category={"success": "good", "incomplete": "normal", "failure": "bad"}[outcome],
        requirements=["整局回合预算耗尽"],
        resolution=(
            "回合预算已用尽。依据玩家已完成的任务与已掌握的证据收束故事："
            "说明当前进展停在何处、哪些线索仍然悬而未决，给出这一局的最终画面。"
        ),
        epilogue="这一局到此结束。",
    )


def ending_instruction(route: Any) -> str:
    requirements = "；".join(route.requirements) or "无额外条件"
    return (
        "## 后端已锁定本回合结局\n"
        f"结局：{route.name}（{route.id}）\n"
        f"判定依据：玩家明确选择了该路线。参考条件：{requirements}\n"
        f"必须在本回合完整呈现结局收束：{route.resolution}\n"
        f"尾声：{route.epilogue}\n"
        "必须返回 game_over=true、options=[]，game_over_reason 以结局名称开头。"
    )
