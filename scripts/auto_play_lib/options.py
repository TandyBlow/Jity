"""Automatic option selection strategy."""

import random
from typing import Any

from auto_play_lib.config import PASSIVE_KEYWORDS, PROGRESSION_KEYWORDS


def choose_option(options: list[str], selected_recent: list[str], rng: random.Random) -> tuple[int | None, str, int]:
    clean_options = [option.strip() for option in options if option.strip()]
    if not clean_options:
        return None, "继续沿着当前最明确的线索推进调查，并主动询问在场 NPC 下一步应该做什么。", 0

    # Score options with a small seeded jitter so ties do not always pick the first button.
    scored = []
    for index, option in enumerate(clean_options, start=1):
        score = score_option(option)
        if option in selected_recent:
            score -= 5
        score += rng.randint(0, 2)
        scored.append((score, -index, index, option))

    best_score, _, best_index, best_option = max(scored)
    return best_index, best_option, best_score


def score_option(option: str) -> int:
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
    return score

