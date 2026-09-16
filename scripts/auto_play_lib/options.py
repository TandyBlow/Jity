"""Automatic option selection strategy."""

import random
from typing import Any

from auto_play_lib.config import PASSIVE_KEYWORDS, PROGRESSION_KEYWORDS


def choose_option(
    options: list[str],
    selected_recent: list[str],
    rng: random.Random,
    goals: list[str] | None = None,
) -> tuple[int | None, str, int]:
    clean_options = [option.strip() for option in options if option.strip()]
    if not clean_options:
        return None, "继续沿着当前最明确的线索推进调查，并主动询问在场 NPC 下一步应该做什么。", 0

    # Score options with a small seeded jitter so ties do not always pick the first button.
    scored = []
    for index, option in enumerate(clean_options, start=1):
        score = score_option(option, goals or [])
        if option in selected_recent:
            score -= 5
        score += rng.randint(0, 2)
        scored.append((score, -index, index, option))

    best_score, _, best_index, best_option = max(scored)
    return best_index, best_option, best_score


def score_option(option: str, goals: list[str] | None = None) -> int:
    score = 0
    for keyword, weight in PROGRESSION_KEYWORDS.items():
        if keyword in option:
            score += weight
    for keyword, weight in PASSIVE_KEYWORDS.items():
        if keyword in option:
            score += weight
    if "？" in option or "?" in option:
        score += 2
    if "：" in option or ":" in option:
        score += 1
    score += goal_relevance_score(option, goals or [])
    return score


def goal_relevance_score(option: str, goals: list[str]) -> int:
    """Reward choices that share meaningful Chinese phrases with active goals."""
    normalized_option = _normalized(option)
    if not normalized_option:
        return 0

    score = 0
    for goal in goals:
        normalized_goal = _normalized(goal)
        if not normalized_goal:
            continue
        # Character n-grams work better than whitespace tokenization for Chinese.
        phrases = {
            normalized_goal[index:index + size]
            for size in (4, 3, 2)
            for index in range(max(0, len(normalized_goal) - size + 1))
        }
        matches = [phrase for phrase in phrases if phrase in normalized_option]
        score += min(18, sum(len(phrase) - 1 for phrase in matches))
    return score


def active_goals_from_state(state: dict[str, Any]) -> list[str]:
    goals: list[str] = []
    current_goal = str((state.get("player_status") or {}).get("current_goal") or "").strip()
    if current_goal:
        goals.append(current_goal)
    for quest in state.get("quests") or []:
        status = str(quest.get("status") or "").lower()
        if status in {"completed", "complete", "done", "已完成", "完成"}:
            continue
        objective = str(quest.get("objective") or quest.get("description") or "").strip()
        if objective and objective not in goals:
            goals.append(objective)
    return goals


def _normalized(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())
