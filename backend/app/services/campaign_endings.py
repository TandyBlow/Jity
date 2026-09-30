"""Deterministic campaign-ending selection.

The LLM writes the prose, but it does not choose whether or which ending fires.
That decision is made from explicit player intent configured on each route, or
from exhausted survival stats for the campaign's bad ending.
"""

import re
from typing import Any


_NEGATION = re.compile(r"(?:不想|不要|不愿|不能|不会|没有|没|拒绝|放弃|并非|不是|别)\s*$")
_HYPOTHETICAL = re.compile(r"(?:如果|假如|假设|倘若|要是|是否|会不会)")
_AFFIRMATION = re.compile(
    r"(?:选择|决定|我要|我将|我愿意|我接受|我来|我会|我打算|同时|并且|然后|再)\s*$"
)


def is_final_session(campaign: Any, progress: Any) -> bool:
    if campaign is None or progress is None or not campaign.arcs:
        return False
    last_arc_index = len(campaign.arcs) - 1
    arc_index = getattr(progress, "arc_index", None)
    session_index = getattr(progress, "session_index", None)
    if not isinstance(arc_index, int) or not isinstance(session_index, int):
        return False
    if arc_index < last_arc_index:
        return False
    if arc_index > last_arc_index:
        # Older runtimes could advance beyond the final arc after its turn
        # limit. Keep those persisted sessions eligible for a real ending.
        return True
    return session_index >= len(campaign.arcs[last_arc_index].sessions) - 1


def select_ending(campaign: Any, progress: Any, state: dict, player_action: str):
    """Return exactly one configured ending route, or None when play continues."""
    routes = getattr(campaign, "ending_routes", []) if campaign else []
    if not routes or not is_final_session(campaign, progress):
        return None

    if state.get("health", 100) <= 0 or state.get("sanity", 80) <= 0:
        return next((route for route in routes if route.category == "bad"), None)

    action = player_action.casefold()
    matched_routes = []
    for route in routes:
        if route.category == "bad" or not _route_requirements_met(route, state, progress):
            continue
        if any(_is_affirmative_match(action, phrase.casefold()) for phrase in route.trigger_phrases):
            matched_routes.append(route)

    # Ambiguous multi-route actions must be clarified instead of silently using
    # campaign JSON order as a tie-breaker.
    return matched_routes[0] if len(matched_routes) == 1 else None


def _route_requirements_met(route: Any, state: dict, progress: Any) -> bool:
    owned_items = {
        item.get("name", "")
        for item in state.get("items", [])
        if item.get("status", "owned") in {"owned", "active", "carried", "持有", "拥有"}
    }
    revealed_anchors = set(getattr(progress, "revealed_anchors", []))
    return (
        all(item_name in owned_items for item_name in route.required_items)
        and all(anchor_id in revealed_anchors for anchor_id in route.required_anchors)
    )


def _is_affirmative_match(action: str, phrase: str) -> bool:
    """Reject a phrase when its nearest clause explicitly negates that choice."""
    start = 0
    while True:
        index = action.find(phrase, start)
        if index < 0:
            return False
        clause_prefix = re.split(r"[，。；！？,;!?]", action[:index])[-1]
        stripped_prefix = clause_prefix.strip()
        # A labelled decision such as “我作出最终决定：共同关闭封印” is
        # still explicit. Remove only its trailing label separator, retaining
        # the words before it so a hypothetical “如果选择：...” stays rejected.
        stripped_prefix = stripped_prefix.rstrip("：:").rstrip()
        if _NEGATION.search(stripped_prefix) or _HYPOTHETICAL.search(stripped_prefix):
            start = index + len(phrase)
            continue
        if stripped_prefix in {"", "我", "玩家"} or _AFFIRMATION.search(stripped_prefix):
            return True
        start = index + len(phrase)


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
