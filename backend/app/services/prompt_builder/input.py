"""Prompt input/output dataclasses."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptMeta:
    """Metadata returned alongside the prompt string for downstream consumers."""
    # 2026-10-11 用户裁决：回合默认温度定为 0.35（保留温度参数修复前的
    # 生产行为）；显式传入其他值仍然生效（LLMClient.generate 传值即用）。
    temperature: float = 0.35
    sanity_multiplier: float = 1.0
    clue_style: str = ""
    # Named sections the prompt was assembled from, kept for replay.
    sections: dict[str, str] = field(default_factory=dict)
    # The exact string handed to the LLM, director block included.
    final_prompt: str = ""


@dataclass
class PromptInput:
    """Structured input for PromptBuilder.build()."""

    player_action: str
    game_state: dict[str, Any]
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    style: str = "horror"
    constraints: str = ""
    campaign_context: str = ""  # Reserved for Phase 2 (CAMP-03)
    recent_messages: list[dict[str, str]] = field(default_factory=list)
    style_anchor: str = ""
