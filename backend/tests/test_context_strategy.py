"""Tests for context window strategy (HARD-01)."""

import pytest

from app.services.context_strategy import (
    ContextStrategy,
    SimpleTruncationStrategy,
    DEFAULT_BUDGET,
    PROTECTED_SECTIONS,
)


class TestSimpleTruncationStrategy:
    def test_count_tokens_positive(self):
        """count_tokens should return a positive integer."""
        s = SimpleTruncationStrategy()
        n = s.count_tokens("Hello, world!")
        assert n > 0
        assert isinstance(n, int)

    def test_should_truncate_below_budget(self):
        """should_truncate returns False when under budget."""
        s = SimpleTruncationStrategy(budget_limit=10000)
        assert s.should_truncate(5000) is False

    def test_should_truncate_above_budget(self):
        """should_truncate returns True when over budget."""
        s = SimpleTruncationStrategy(budget_limit=10000)
        assert s.should_truncate(15000) is True

    def test_count_chinese_text(self):
        """count_tokens works with Chinese text (cl100k_base overestimates)."""
        s = SimpleTruncationStrategy()
        n = s.count_tokens("这是一个中文测试句子。")
        assert n > 0

    def test_truncate_drops_rag_first(self):
        """truncate should drop rag_chunks first."""
        s = SimpleTruncationStrategy(budget_limit=100)
        sections = {
            "system_prompt": "You are a helpful assistant.",
            "player_action": "Look around.",
            "rag_chunks": "A" * 5000,  # large
        }
        result = s.truncate(sections)
        assert "helpful assistant" in result
        assert "Look around" in result
        # rag_chunks should be dropped
        assert "AAAA" not in result

    def test_truncate_preserves_protected(self):
        """truncate should never drop system_prompt or player_action."""
        s = SimpleTruncationStrategy(budget_limit=5)
        sections = {
            "system_prompt": "You are a GM.",
            "player_action": "Look.",
        }
        result = s.truncate(sections)
        assert "You are a GM" in result
        assert "Look" in result

    def test_custom_budget(self):
        """Constructor should accept custom budget limit."""
        s = SimpleTruncationStrategy(budget_limit=500)
        assert s.budget_limit == 500

    def test_protected_sections_are_system_and_player(self):
        """PROTECTED_SECTIONS should contain system_prompt and player_action."""
        assert "system_prompt" in PROTECTED_SECTIONS
        assert "player_action" in PROTECTED_SECTIONS

    def test_default_budget_is_102400(self):
        """Default budget should be 102400 (80% of 128K)."""
        assert DEFAULT_BUDGET == 102400
