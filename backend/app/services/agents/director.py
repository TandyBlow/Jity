"""Director Agent — produces narrative direction, anchor triggers, redirection strategy.

Combines SENNA's Navigator (DAG anchor evaluation + deviation detection + 6
redirection strategies) with CoDi's Director (goal-driven instruction types)
and SCORE's item continuity validation.

Uses deepseek-v4-flash for low latency (~1s), temperature=0.3 for
consistent but not rigid direction.
"""

import logging
from typing import Any

from app.schemas.agent_io import (
    ActionRuling,
    DirectorInstruction,
    ItemContinuityCheck,
    RedirectionStrategy,
)
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_DIRECTOR_SYSTEM_PROMPT = """你是一个TRPG叙事导演系统（Director）。你根据Examiner的判定和当前战役状态，为Narrator生成叙事方向指令。

你的输出不是叙事正文，而是对Narrator的指导——告诉它故事应该往哪个方向发展、是否触发锚点、是否需要重定向。

输入：
1. Examiner的行动判定（可行性 + 触发规则）
2. 叙事记忆上下文（之前的场景摘要、因果链）
3. 锚点状态（进度、候选触发器）
4. 关键物品状态连续性检查结果

输出格式（严格JSON）：
{
  "narrative_direction": "对Narrator的叙事方向指令，如'引导玩家进入钟楼，揭示第二个线索'",
  "anchor_triggered": "触发的锚点ID，若无则为空字符串",
  "redirection_strategy": "more_information|world_consequences|npc_influence|environmental_cue|dramatic_timing|hard_denial|null",
  "redirection_hint": "具体提示文本，如'远处的钟声再次响起'，无需重定向时为空",
  "item_continuity_checks": [
    {"item_name": "...", "previous_state": "...", "current_state": "...", "is_valid_transition": true, "error_description": ""}
  ],
  "health_guidance": "叙事健康引导文本（仅叙事内提示），无引导时为空"
}

导演原则：
- 如果Examiner判定为blocked，给出叙事内拒绝策略（redirection_strategy + redirection_hint）
- 如果Examiner判定为conditional，在narrative_direction中说明需要什么检定
- 检查锚点触发条件：如果玩家状态满足某个锚点的trigger_conditions，设置anchor_triggered
- 如果连续3+回合无锚点触发，标记为偏差并选择重定向策略
- 物品状态连续性：物品不能从lost/destroyed直接变为active，标记为invalid
- 叙事健康引导只在检测到节奏问题时使用（参见CAMP-09指标）"""

_DIRECTOR_USER_TEMPLATE = """## Examiner判定
- 可行性：{permissibility}
- 触发规则：{triggered_rules}
- 约束条件：{constraints}

## 叙事记忆（L1）
{narrative_context}

## 锚点状态
- 当前进度：{anchor_progress}
- 候选触发器：{candidate_anchors}
- 偏差检测：{deviation_status}

## 物品状态
{item_states}

## 玩家行动
{player_action}

请生成导演指令。严格返回JSON。"""


class DirectorAgent:
    """Produces narrative direction, evaluates anchors, and manages redirection."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def direct(
        self,
        player_action: str,
        ruling: ActionRuling,
        narrative_context: str,
        anchor_progress: str,
        candidate_anchors: str,
        deviation_status: str,
        item_states: str,
    ) -> DirectorInstruction:
        """Generate director instruction for the Narrator.

        Args:
            player_action: The player's typed action.
            ruling: Examiner verdict on permissibility.
            narrative_context: L1 narrative memory summary.
            anchor_progress: e.g. "3/12 已揭示"
            candidate_anchors: Anchor candidates this turn.
            deviation_status: e.g. "偏差：连续4回合无锚点触发" or "正常"
            item_states: SCORE item state summary.

        Returns:
            DirectorInstruction with narrative direction, anchor triggers, etc.
        """
        triggered_summary = "；".join(
            f"{r.rule_name}({r.rule_details})" for r in ruling.triggered_rules
        ) or "无"

        user_prompt = _DIRECTOR_USER_TEMPLATE.format(
            permissibility=ruling.permissibility.value,
            triggered_rules=triggered_summary,
            constraints=ruling.constraints or "无",
            narrative_context=narrative_context or "暂无前序叙事记忆",
            anchor_progress=anchor_progress,
            candidate_anchors=candidate_anchors,
            deviation_status=deviation_status,
            item_states=item_states,
            player_action=player_action,
        )

        try:
            result = await self._llm.generate_json(
                prompt=f"{_DIRECTOR_SYSTEM_PROMPT}\n\n{user_prompt}",
                model="deepseek-v4-flash",
                max_tokens=1500,
                temperature=0.3,
            )
            return _parse_instruction(result)
        except Exception:
            logger.warning("Director agent failed, using fallback instruction", exc_info=True)
            return _fallback_instruction(ruling)


# ── Helpers ────────────────────────────────────────────────────────


def _parse_instruction(data: dict[str, Any]) -> DirectorInstruction:
    """Parse raw JSON into DirectorInstruction with graceful fallbacks."""
    strategy = data.get("redirection_strategy")
    redirect: RedirectionStrategy | None = None
    if strategy and strategy != "null":
        try:
            redirect = RedirectionStrategy(strategy)
        except ValueError:
            redirect = None

    continuity: list[ItemContinuityCheck] = []
    for ic in data.get("item_continuity_checks", []):
        if isinstance(ic, dict) and ic.get("item_name"):
            continuity.append(ItemContinuityCheck(
                item_name=ic["item_name"],
                previous_state=ic.get("previous_state", ""),
                current_state=ic.get("current_state", ""),
                is_valid_transition=ic.get("is_valid_transition", True),
                error_description=ic.get("error_description", ""),
            ))

    return DirectorInstruction(
        narrative_direction=data.get("narrative_direction", "继续当前叙事"),
        anchor_triggered=data.get("anchor_triggered", ""),
        redirection_strategy=redirect,
        redirection_hint=data.get("redirection_hint", ""),
        item_continuity_checks=continuity,
        health_guidance=data.get("health_guidance", ""),
    )


def _fallback_instruction(ruling: ActionRuling) -> DirectorInstruction:
    """Minimal instruction when the Director LLM call fails."""
    if ruling.permissibility.value == "blocked":
        return DirectorInstruction(
            narrative_direction="玩家的行动不可行，通过叙事逻辑拒绝",
            redirection_strategy=RedirectionStrategy.WORLD_CONSEQUENCES,
            redirection_hint="世界自然地阻止了不合理的行动",
            constraints=ruling.constraints,
        )
    return DirectorInstruction(
        narrative_direction="继续推进当前叙事，回应玩家行动",
        constraints=ruling.constraints,
    )
