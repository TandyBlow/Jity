"""Context window management strategy (HARD-01).

Defines the ContextStrategy protocol and a SimpleTruncationStrategy
implementation that uses tiktoken cl100k_base for token counting and
progressive per-section truncation for budget management.

Intra-section truncation reduces content within sections before dropping
them entirely: rag_chunks keeps fewer chunks, messages keeps fewer
recent lines, and text sections are head-truncated. This prevents the
"all or nothing" problem where a single large section would force
dropping every lower-priority section.

cl100k_base overestimates Chinese by ~68% — this is a deliberate
safety margin so we never accidentally exceed the real context window.
"""

import logging
import re
from typing import Protocol

import tiktoken

logger = logging.getLogger(__name__)

# Drop priority: lowest (leftmost) gets reduced/dropped first
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

# Sections that must never be dropped or reduced
PROTECTED_SECTIONS = {"system_prompt", "player_action"}

# Per-section truncation levels (progressive, applied in order)
# For rag_chunks: number of top-scored chunks to keep
# For messages: number of most-recent messages to keep
# For text sections: fraction of characters to retain (head + tail)
SECTION_TRUNCATION_LEVELS: dict[str, list[float]] = {
    "rag_chunks":       [3, 1, 0],
    "messages":         [7, 5, 3, 1, 0],
    "health_guidance":  [0.75, 0.50, 0.25, 0.0],
    "narrative_memory": [0.75, 0.50, 0.25, 0.0],
    "campaign_context": [0.75, 0.50, 0.25, 0.0],
    "recap":            [0.75, 0.50, 0.25, 0.0],
}

# Default for sections not explicitly listed above
_DEFAULT_TEXT_LEVELS = [0.75, 0.50, 0.25, 0.0]

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
        """Reduce sections to fit within token budget.

        Truncates sections in priority order, progressively reducing content
        within each section before moving to the next:
        - rag_chunks: top-5 → top-3 → top-1 → none
        - messages:   10 → 7 → 5 → 3 → 1 → none (most-recent kept)
        - text:       head+tail at 75% → 50% → 25% → none

        Protected sections (system_prompt, player_action) are never modified.

        Args:
            sections: Dict of section_name -> section_text

        Returns:
            Combined string with truncated sections joined by newlines.
        """
        # Fast path: everything fits
        combined = "\n\n".join(sections.values())
        if self.count_tokens(combined) <= self.budget_limit:
            return combined

        # Per-section truncation index: -1 = full, 0..N = level index
        trun_index: dict[str, int] = {k: -1 for k in sections}
        reduced: set[str] = set()

        # Progressive truncation on non-protected sections
        for section_name in TRUNCATION_PRIORITY:
            if section_name not in sections:
                continue
            if section_name in PROTECTED_SECTIONS:
                continue

            levels = SECTION_TRUNCATION_LEVELS.get(
                section_name, _DEFAULT_TEXT_LEVELS
            )
            for idx, level in enumerate(levels):
                trun_index[section_name] = idx
                truncated = self._build_truncated(sections, trun_index)
                combined = "\n\n".join(truncated.values())
                if self.count_tokens(combined) <= self.budget_limit:
                    if reduced:
                        logger.info("Truncation reduced: %s", reduced)
                    return combined
                if level <= 0.0:
                    reduced.add(section_name)

        if reduced:
            logger.info("Truncation dropped sections: %s", reduced)
        return combined

    def _build_truncated(
        self, sections: dict[str, str], trun_index: dict[str, int]
    ) -> dict[str, str]:
        """Apply current truncation levels and return truncated sections.

        trun_index: -1 = full, >=0 = index into the section's truncation levels.
        """
        result: dict[str, str] = {}
        for name, text in sections.items():
            idx = trun_index.get(name, -1)
            if idx < 0:
                result[name] = text
                continue
            levels = SECTION_TRUNCATION_LEVELS.get(name, _DEFAULT_TEXT_LEVELS)
            if idx >= len(levels):
                idx = len(levels) - 1
            level = levels[idx]
            if level <= 0.0:
                continue
            if name == "rag_chunks":
                result[name] = self._truncate_rag_chunks(text, int(level))
            elif name == "messages":
                result[name] = self._truncate_messages(text, int(level))
            else:
                result[name] = self._truncate_text_head_tail(text, level)
        return result

    # ── Targeted truncation methods ────────────────────────────────

    @staticmethod
    def _truncate_rag_chunks(text: str, keep_n: int) -> str:
        """Keep the top-N RAG chunks (highest relevance first).

        Chunk format (from PromptBuilder._build_knowledge):
          RAG 检索到的相关知识：
          [source_type] title
          content...

          [source_type] title
          content...

        Chunks are separated by double-newlines after the header line.
        """
        if keep_n <= 0:
            return ""

        # Separate header from chunk body
        lines = text.split("\n", 1)
        header = lines[0]
        body = lines[1] if len(lines) > 1 else ""

        if not body.strip():
            return text

        # Split chunks by double newline
        raw_chunks = body.split("\n\n")
        kept = [c for c in raw_chunks if c.strip()][:keep_n]
        return header + "\n" + "\n\n".join(kept)

    @staticmethod
    def _truncate_messages(text: str, keep_n: int) -> str:
        """Keep the most-recent N messages.

        Message format (from PromptBuilder._build_messages):
          ## 最近对话历史
          [玩家]: content...
          [主持人]: content...
          ...
        """
        if keep_n <= 0:
            return ""

        lines = text.split("\n")
        header_lines: list[str] = []
        msg_lines: list[str] = []

        for line in lines:
            is_msg = line.startswith("[玩家]") or line.startswith("[主持人]")
            if is_msg:
                msg_lines.append(line)
            elif not msg_lines:
                header_lines.append(line)
            else:
                msg_lines.append(line)

        # Filter out trailing empty lines from msg_lines count
        msg_lines = [l for l in msg_lines if l.strip()]

        if len(msg_lines) <= keep_n:
            return text

        # Keep most recent N messages
        kept_msg_lines = msg_lines[-keep_n:]
        return "\n".join(header_lines + kept_msg_lines) + "\n…"

    @staticmethod
    def _truncate_text_head_tail(text: str, fraction: float) -> str:
        """Keep head + tail proportionally (60% head, 40% tail of allowed chars)."""
        if fraction >= 1.0:
            return text

        max_chars = max(1, int(len(text) * fraction))
        if len(text) <= max_chars:
            return text

        head_chars = int(max_chars * 0.6)
        tail_chars = max_chars - head_chars

        return text[:head_chars] + "\n…\n" + text[-tail_chars:]
