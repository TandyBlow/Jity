"""Context window management strategy (HARD-01).

Defines the ContextStrategy protocol and a SimpleTruncationStrategy
implementation that uses tiktoken cl100k_base for token counting and
priority-ordered section dropping for truncation.

cl100k_base overestimates Chinese by ~68% — this is a deliberate
safety margin so we never accidentally exceed the real context window.
"""

import logging
import re
from typing import Protocol

import tiktoken

logger = logging.getLogger(__name__)

# Drop priority: lowest (leftmost) gets dropped first
TRUNCATION_PRIORITY = [
    "rag_chunks",
    "health_guidance",
    "narrative_memory",
    "campaign_context",
    "recap",
    "messages",
    "system_prompt",
    "player_action",
]

# Sections that must never be dropped
PROTECTED_SECTIONS = {"system_prompt", "player_action"}

DEFAULT_BUDGET = 102400  # 80% of assumed 128K context window


class _FallbackEncoding:
    """Offline-safe conservative token estimator.

    tiktoken downloads the cl100k_base vocabulary on first use. When that
    download is unavailable, this estimator keeps the backend and tests usable
    while deliberately over-counting Chinese text.
    """

    name = "cl100k_base"

    @staticmethod
    def encode(text: str) -> list[int]:
        pieces = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+|[^\s]", text)
        tokens: list[int] = []
        for piece in pieces:
            if re.fullmatch(r"[A-Za-z0-9_]+", piece):
                tokens.extend([0] * max(1, (len(piece) + 3) // 4))
            else:
                tokens.append(0)
        return tokens


def get_token_encoder(encoder_name: str = "cl100k_base"):
    """Return tiktoken's encoder, or a conservative offline fallback."""
    try:
        return tiktoken.get_encoding(encoder_name)
    except Exception as exc:
        logger.warning(
            "Unable to load %s tokenizer; using offline token estimator: %s",
            encoder_name,
            exc,
        )
        return _FallbackEncoding()


class ContextStrategy(Protocol):
    """Interface for context window management.

    Future strategies (hierarchical summarization in v2) implement this.
    """

    def count_tokens(self, text: str) -> int: ...

    def should_truncate(self, token_count: int) -> bool: ...

    def truncate(self, sections: dict[str, str]) -> str: ...


class SimpleTruncationStrategy:
    """Token-aware truncation using tiktoken cl100k_base.

    Drops prompt sections in priority order until the combined
    token count fits within the budget. Protected sections
    (system_prompt, player_action) are never dropped.
    """

    def __init__(
        self,
        budget_limit: int = DEFAULT_BUDGET,
        encoder_name: str = "cl100k_base",
    ) -> None:
        self.budget_limit = budget_limit
        self._encoder_name = encoder_name
        self._enc = None

    def _get_encoder(self):
        if self._enc is None:
            self._enc = get_token_encoder(self._encoder_name)
        return self._enc

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using the configured encoder."""
        enc = self._get_encoder()
        return len(enc.encode(text))

    def should_truncate(self, token_count: int) -> bool:
        """Return True if token_count exceeds the budget limit."""
        return token_count > self.budget_limit

    def truncate(self, sections: dict[str, str]) -> str:
        """Drop sections in priority order until within budget.

        Protected sections (system_prompt, player_action) are never dropped,
        even if they alone exceed the budget.

        Args:
            sections: Dict of section_name -> section_text

        Returns:
            Combined string with remaining sections joined by newlines
        """
        dropped: set[str] = set()

        # Drop lower-priority sections until the remaining prompt fits.
        for section_name in TRUNCATION_PRIORITY:
            if section_name not in sections:
                continue
            if section_name in PROTECTED_SECTIONS:
                continue

            # Try dropping this section
            remaining = {
                k: v for k, v in sections.items()
                if k not in dropped and k != section_name
            }
            combined = "\n\n".join(remaining.values())
            dropped.add(section_name)
            if self.count_tokens(combined) <= self.budget_limit:
                break

        # Assemble final result (protected sections always included)
        final_sections = {
            k: v for k, v in sections.items() if k not in dropped
        }

        if dropped:
            logger.info("Truncation dropped sections: %s", dropped)

        return "\n\n".join(final_sections.values())
