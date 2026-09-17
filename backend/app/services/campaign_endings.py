"""Deterministic campaign-ending selection.

The LLM writes the prose, but it does not choose whether or which ending fires.
That decision is made from explicit player intent configured on each route, or
from exhausted survival stats for the campaign's bad ending.
"""

from typing import Any


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
