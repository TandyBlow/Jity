"""Prompt input/output dataclasses."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptMeta:
    """Metadata returned alongside the prompt string for downstream consumers."""
    temperature: float = 0.7
    sanity_multiplier: float = 1.0
    clue_style: str = ""


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
