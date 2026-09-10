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


class TestTargetedTruncation:
    """Tests for per-section targeted truncation methods."""

    def test_truncate_rag_keeps_top_n_chunks(self):
        """_truncate_rag_chunks keeps top-N chunks, drops rest."""
        s = SimpleTruncationStrategy()
        text = (
            "RAG 检索到的相关知识：\n"
            "[npc] 诺诺\n"
            "红发学姐，负责接应新生。\n\n"
            "[location] 报到处大厅\n"
            "卡塞尔学院新生报到大厅。\n\n"
            "[quest] 入学调查\n"
            "完成三个预备任务。\n\n"
            "[rule] 基础规则\n"
            "SAN值检定规则。\n\n"
            "[lore] 学院历史\n"
            "卡塞尔学院成立于...\n"
        )
        result = s._truncate_rag_chunks(text, keep_n=2)
        assert "诺诺" in result
        assert "报到处大厅" in result
        assert "入学调查" not in result
        assert "基础规则" not in result
        assert "学院历史" not in result

    def test_truncate_rag_keep_none_returns_empty(self):
        """_truncate_rag_chunks with keep_n=0 returns empty string."""
        s = SimpleTruncationStrategy()
        text = "RAG 检索到的相关知识：\n[npc] 诺诺\ncontent\n"
        result = s._truncate_rag_chunks(text, keep_n=0)
        assert result == ""

    def test_truncate_messages_keeps_most_recent_n(self):
        """_truncate_messages keeps most-recent N messages."""
        s = SimpleTruncationStrategy()
        text = (
            "## 最近对话历史\n"
            "[玩家]: 第一轮\n"
            "[主持人]: 回复1\n"
            "[玩家]: 第二轮\n"
            "[主持人]: 回复2\n"
            "[玩家]: 第三轮\n"
            "[主持人]: 回复3\n"
            "[玩家]: 第四轮\n"
            "[主持人]: 回复4\n"
        )
        result = s._truncate_messages(text, keep_n=2)
        assert "第一轮" not in result
        assert "回复1" not in result
        assert "第四轮" in result
        assert "回复4" in result

    def test_truncate_messages_keep_none_returns_empty(self):
        """_truncate_messages with keep_n=0 returns empty string."""
        s = SimpleTruncationStrategy()
        text = "## 最近对话历史\n[玩家]: hello\n[主持人]: hi\n"
        result = s._truncate_messages(text, keep_n=0)
        assert result == ""

    def test_truncate_text_head_tail_preserves_structure(self):
        """_truncate_text_head_tail keeps head and tail with ellipsis marker."""
        s = SimpleTruncationStrategy()
        text = "A" * 100 + "\nMIDDLE TEXT\n" + "B" * 100
        result = s._truncate_text_head_tail(text, fraction=0.5)
        # ~50% of chars kept, split 60/40 head/tail
        assert "…" in result
        assert result.startswith("A" * 50)
        assert result.endswith("B" * 30)

    def test_truncate_text_full_fraction_returns_full(self):
        """_truncate_text_head_tail with fraction=1.0 returns full text."""
        s = SimpleTruncationStrategy()
        text = "hello world"
        result = s._truncate_text_head_tail(text, fraction=1.0)
        assert result == text

    def test_truncate_rag_progressive_in_budget(self):
        """truncate() progressively reduces RAG chunks before dropping."""
        s = SimpleTruncationStrategy(budget_limit=80)
        # Many RAG chunks + small protected sections
        chunks = []
        for i in range(10):
            chunks.append(f"[npc] NPC{i}\n{'X' * 200}")
        rag_text = "RAG 检索到的相关知识：\n" + "\n\n".join(chunks)
        sections = {
            "system_prompt": "You are a helpful GM.",
            "player_action": "Look around.",
            "rag_chunks": rag_text,
        }
        result = s.truncate(sections)
        # RAG should be progressively reduced, not fully dropped if it fits
        assert "RAG 检索到的相关知识" in result
        # Top chunks kept, later ones dropped
        assert "NPC0" in result
        assert "NPC9" not in result
