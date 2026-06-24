"""Examiner Agent — evaluates player action feasibility and triggered rules.

Adapted from SENNA's Examiner agent (Jørgensen et al., ACM IUI 2026).
The Examiner does NOT generate narrative — it only judges permissibility
and identifies which game mechanics (sanity checks, skill rolls, combat)
should activate this turn.

Uses deepseek-v4-flash for low latency (~0.5s), temperature=0.1 for
deterministic rulings.
"""

import json
import logging
from typing import Any

from app.schemas.agent_io import ActionPermissibility, ActionRuling, TriggeredRule
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_EXAMINER_SYSTEM_PROMPT = """你是一个TRPG规则判定系统（Examiner）。你的唯一职责是判断玩家行动的可行性和触发的规则。

输入：
1. 玩家的行动
2. 当前游戏状态（地点、物品、NPC、任务等）
3. 相关的规则片段

输出格式（严格JSON）：
{
  "permissibility": "permissible|conditional|blocked",
  "triggered_rules": [
    {"rule_type": "...", "rule_name": "...", "rule_details": "..."}
  ],
  "constraints": "对Director的约束说明，如'玩家没有钥匙，无法开门'",
  "rejection_reason": "如果blocked，给出叙事内拒绝理由"
}

判定原则：
- permissible：行动完全合理，无需额外检定
- conditional：行动需要检定（SAN检定、技能检定等），在triggered_rules中说明
- blocked：行动在当前状态下不可能（缺少物品、NPC不在场、信息不足等）
- 只基于提供的游戏状态判断，不要编造不存在的物品或NPC
- 如果行动部分可行部分不可行，标记为conditional并说明约束"""

_EXAMINER_USER_TEMPLATE = """## 玩家行动
{player_action}

## 当前游戏状态
- 地点：{location}
- 血统稳定：{sanity}/100
- 体力：{health}/100
- 持有物品：{items}
- 在场NPC：{npcs}
- 活跃任务：{quests}
- 长期事实：{world_facts}

## 相关规则
{rules_text}

请判断此行动的可行性。严格返回JSON。"""


class ExaminerAgent:
    """Evaluates action feasibility and identifies triggered game rules."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def examine(
        self,
        player_action: str,
        game_state: dict[str, Any],
        rules_texts: list[str],
    ) -> ActionRuling:
        """Judge whether a player action is permissible and what rules it triggers.

        Args:
            player_action: The player's typed action.
            game_state: Current game state dict (location, items, npcs, etc.).
            rules_texts: Relevant rule snippets from L2 World Memory.

        Returns:
            ActionRuling with permissibility, triggered rules, and constraints.
        """
        rules_joined = "\n---\n".join(rules_texts) if rules_texts else "无特定规则匹配。"

        user_prompt = _EXAMINER_USER_TEMPLATE.format(
            player_action=player_action,
            location=game_state.get("current_location", "未知"),
            sanity=game_state.get("sanity", 80),
            health=game_state.get("health", 100),
            items=_compact_entities(game_state.get("items", [])),
            npcs=_compact_entities(game_state.get("npcs", [])),
            quests=_compact_entities(game_state.get("quests", [])),
            world_facts=_compact_entities(game_state.get("world_facts", [])),
            rules_text=rules_joined,
        )

        try:
            result = await self._llm.generate_json(
                prompt=f"{_EXAMINER_SYSTEM_PROMPT}\n\n{user_prompt}",
                model="deepseek-v4-flash",
                max_tokens=1000,
                temperature=0.1,
            )
            return _parse_ruling(result)
        except Exception:
            logger.warning("Examiner agent failed, defaulting to permissible", exc_info=True)
            return ActionRuling(permissibility=ActionPermissibility.PERMISSIBLE)


# ── Helpers ────────────────────────────────────────────────────────


def _compact_entities(entities: list[dict[str, Any]]) -> str:
    """Compress entity list to a brief summary for the prompt."""
    if not entities:
        return "无"
    parts = []
    for e in entities[:8]:
        name = e.get("name", "未命名")
        status = e.get("status") or e.get("disposition") or ""
        parts.append(f"{name}({status})" if status else name)
    return "；".join(parts)


def _parse_ruling(data: dict[str, Any]) -> ActionRuling:
    """Parse raw JSON dict into ActionRuling with graceful fallbacks."""
    perm_str = data.get("permissibility", "permissible")
    try:
        permissibility = ActionPermissibility(perm_str)
    except ValueError:
        permissibility = ActionPermissibility.PERMISSIBLE

    triggered_rules: list[TriggeredRule] = []
    for rd in data.get("triggered_rules", []):
        if isinstance(rd, dict) and rd.get("rule_type"):
            triggered_rules.append(TriggeredRule(
                rule_type=rd.get("rule_type", "unknown"),
                rule_name=rd.get("rule_name", ""),
                rule_details=rd.get("rule_details", ""),
            ))

    return ActionRuling(
        permissibility=permissibility,
        triggered_rules=triggered_rules,
        constraints=data.get("constraints", ""),
        rejection_reason=data.get("rejection_reason", ""),
    )
