"""PromptBuilder package — prompt section assembly and templates.

Modules:
  - input:    PromptInput / PromptMeta dataclasses
  - prompts:  RECAP_SYSTEM_PROMPT, CAMPAIGN_GEN_PROMPT, build_campaign_gen
  - builder:  PromptBuilder (section assembly)
  - helpers:  compact list/status formatting helpers
"""

from app.services.prompt_builder.builder import PromptBuilder
from app.services.prompt_builder.input import PromptInput, PromptMeta
from app.services.prompt_builder.prompts import (
    CAMPAIGN_GEN_PROMPT,
    RECAP_SYSTEM_PROMPT,
    build_campaign_gen,
)

__all__ = [
    "PromptBuilder",
    "PromptInput",
    "PromptMeta",
    "RECAP_SYSTEM_PROMPT",
    "CAMPAIGN_GEN_PROMPT",
    "build_campaign_gen",
]
