"""Opening options agent — proposes the choices shown on a campaign opening turn.

The opening narration is authored in the campaign file, so this agent only asks
the model for the options and their checks.  It deliberately has no fallback: an
opening that silently loses its choices is the bug this agent exists to fix, so
failures propagate to the caller and the player can retry the turn.
"""

import json
import logging
import time
from typing import Any

from pydantic import ValidationError

from app.schemas.agent_io import OpeningOptions
from app.schemas.campaign import AnchorEvent
from app.services.llm_client import LLMClient, LLMOutputParseError, MissingAPIKeyError
from app.services.prompt_builder.helpers import SectionHelpers
from app.services.prompt_builder.prompts import build_opening_options

logger = logging.getLogger(__name__)


class OpeningOptionsAgent(SectionHelpers):
    """Proposes the options for an authored opening scene."""

    MAX_TOKENS = 1000
    TEMPERATURE = 0.3

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def propose(
        self,
        *,
        opening: str,
        state: dict[str, Any],
        anchors: list[AnchorEvent] | None = None,
        constraints: str = "",
    ) -> OpeningOptions:
        """Return the opening's options, or raise so the caller can fail loudly."""
        if not self._llm.settings.deepseek_api_key:
            raise MissingAPIKeyError(
                "战役开场需要调用 LLM 生成行动选项，请在 backend/.env 配置 DEEPSEEK_API_KEY。"
            )

        prompt = build_opening_options(
            self._build_context(opening, state, anchors or [], constraints)
        )
        started = time.perf_counter()
        data = await self._llm.generate_json(
            prompt=prompt, max_tokens=self.MAX_TOKENS, temperature=self.TEMPERATURE
        )

        try:
            return OpeningOptions.model_validate(data)
        except ValidationError as exc:
            raise LLMOutputParseError(
                f"开场选项不符合约定：{exc}",
                raw_output=json.dumps(data, ensure_ascii=False),
                cleaned_output="",
                latency_ms=int((time.perf_counter() - started) * 1000),
            ) from exc

    # ── Context ────────────────────────────────────────────────────────────

    def _build_context(
        self,
        opening: str,
        state: dict[str, Any],
        anchors: list[AnchorEvent],
        constraints: str,
    ) -> str:
        """Render only what the choice designer needs.

        Sanity, health and turn counts are left out on purpose: they never change
        which actions make sense at the opening, and they only add noise.
        """
        lines = [
            "## 本幕开场白",
            opening,
            "",
            "## 当前已知信息",
            f"- 当前地点：{state.get('current_location') or '未知'}",
            f"- 玩家状态：{self._compact_player_status(state.get('player_status', {}))}",
            f"- 在场 NPC：{self._compact_list(state.get('npcs', []), kind='npc')}",
            f"- 持有物品：{self._compact_list(state.get('items', []), kind='item')}",
            f"- 已知任务：{self._compact_list(state.get('quests', []), kind='quest')}",
        ]

        if anchors:
            lines.append("")
            lines.append("## 本幕锚点")
            lines.append("（只用来判断哪些行动能推动剧情，不要把锚点本身写成选项）")
            for anchor in anchors:
                lines.append(f"- {anchor.name}：{anchor.description}")

        if constraints:
            lines.append("")
            lines.append("## 战役约束")
            lines.append(constraints)

        return "\n".join(lines)
