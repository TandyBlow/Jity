"""Deterministic campaign-ending selection.

The LLM writes the prose, but it does not choose whether or which ending fires.
That decision is made from explicit player intent configured on each route,
from exhausted survival stats for the campaign's bad ending, or from the
whole-campaign turn budget so a run always closes inside its allocation.
"""

import re
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


def select_budget_ending(
    campaign: Any,
    progress: Any,
    state: dict,
    max_turns: int,
    player_action: str = "",
):
    """Ending forced by the whole-campaign turn budget.

    Fires on the budget's last turn (turns_total == max_turns - 1 before this
    turn commits), so the ending is presented within the allocation instead of
    truncating the story mid-air.

    Route choice is evidence-checked, not category-blinded: a configured route
    only qualifies when its requirements appear in what the player actually
    reached (completed quest names/objectives, confirmed facts, revealed
    anchors). Trigger phrases cannot waive unmet requirements. A dead state
    still takes the bad/dark route from survival stats alone. When nothing
    qualifies, the run closes with the synthesized unfinished ending instead
    of a route whose story conditions never happened.
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
        for route in routes:
            if route.category in ("bad", "dark"):
                return route
        return _synthesized_budget_route("failure")

    evidence = _budget_evidence(campaign, progress, state)
    quests = state.get("quests", []) or []
    done_marks = {"completed", "done", "achieved", "finished", "完成", "已完成"}
    completed = sum(
        1 for quest in quests
        if isinstance(quest, dict) and str(quest.get("status", "")).strip().lower() in done_marks
    )
    revealed = len(getattr(progress, "revealed_anchors", []) or [])
    outcome = "success" if completed >= 1 else ("incomplete" if revealed >= 1 else "failure")

    for categories in _BUDGET_CATEGORIES[outcome]:
        for route in routes:
            if (route.category in categories
                    and _route_requirements_met(route, state, progress)
                    and _route_qualifies(route, evidence, player_action)):
                return route
    return _synthesized_budget_route("incomplete" if outcome != "failure" else "failure")


def _budget_evidence(campaign: Any, progress: Any, state: dict) -> str:
    """Text a route's requirements are checked against: quests the player
    completed, world facts learned, and the anchors actually revealed."""
    parts: list[str] = []
    for quest in state.get("quests", []) or []:
        if isinstance(quest, dict) and str(quest.get("status", "")).strip().lower() in {
            "completed", "done", "achieved", "finished", "完成", "已完成",
        }:
            parts.append(str(quest.get("name", "")))
            parts.append(str(quest.get("objective", "")))
    for fact in state.get("world_facts", []) or []:
        if isinstance(fact, dict) and str(fact.get("status", "known")).strip().casefold() in {
            "known", "confirmed", "verified", "已知", "已确认",
        }:
            parts.append(str(fact.get("name", "")))
            parts.append(str(fact.get("description", "")))
    revealed = set(getattr(progress, "revealed_anchors", []) or [])
    try:
        for arc in campaign.arcs:
            for session in arc.sessions:
                for anchor in session.anchor_events or []:
                    if anchor.id in revealed:
                        parts.append(str(anchor.name))
                        parts.append(str(getattr(anchor, "description", "") or ""))
    except AttributeError:
        pass
    return "\n".join(part for part in parts if part)


def _route_qualifies(route: Any, evidence: str, player_action: str) -> bool:
    requirements = [r.strip().casefold() for r in (route.requirements or []) if r.strip()]
    if requirements:
        return all(requirement in evidence.casefold() for requirement in requirements)
    action = (player_action or "").casefold()
    # A route with no requirements needs an explicit action to qualify;
    # its category alone is not evidence.
    return bool(action) and any(
        phrase.strip() and _is_affirmative_match(action, phrase.casefold())
        for phrase in (route.trigger_phrases or [])
    )


def _synthesized_budget_route(outcome: str) -> EndingRoute:
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
        f"判定依据：后端根据本回合行动与已保存的进度选定路线。参考条件：{requirements}\n"
        f"必须在本回合完整呈现结局收束：{route.resolution}\n"
        f"尾声：{route.epilogue}\n"
        "必须返回 game_over=true、options=[]，game_over_reason 以结局名称开头。"
    )
