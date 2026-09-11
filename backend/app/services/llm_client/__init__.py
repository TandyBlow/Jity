"""LLMClient package — DeepSeek client with parse/repair fallbacks.

Modules:
  - errors:            MissingAPIKeyError, LLMRequestError, LLMOutputParseError
  - client:            LLMClient core (chat calls, generate/generate_json)
  - repair:            JSON cleaning and repair helpers
  - output_normalizer: StoryOutput payload normalization
"""

from app.services.llm_client.client import LLMClient
from app.services.llm_client.errors import (
    LLMOutputParseError,
    LLMRequestError,
    MissingAPIKeyError,
)

__all__ = [
    "LLMClient",
    "MissingAPIKeyError",
    "LLMRequestError",
    "LLMOutputParseError",
]
