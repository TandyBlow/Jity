"""Tests for multi-agent pipeline: examiner, director, forgetting, SCORE tracker, NSB, PCB."""

import math
import pytest

from app.schemas.agent_io import (
    ActionPermissibility,
    ActionRuling,
    DirectorInstruction,
    EpisodeSummary,
    HallucinationFinding,
    HallucinationType,
    ItemState,
    ItemStateRecord,
    MemoryRecord,
    PersonaSnapshot,
    PersonaValue,
    RedirectionStrategy,
    TriggeredRule,
)
from app.services.agents.director import DirectorAgent, _parse_instruction, _fallback_instruction
from app.services.agents.examiner import ExaminerAgent, _parse_ruling, _compact_entities
from app.services.memory.forgetting import (
    compute_score,
    score_all,
    apply_retrieval_reinforcement,
    prune_pool,
    forget_step,
    ALPHA,
    BETA,
    GAMMA,
    K,
)
from app.services.memory.score_tracker import ScoreTracker
from app.services.memory.nsb import NarrativeSummarizationBranch
from app.services.memory.pcb import PersonaConstructionBranch, _approx_equal
from app.services.memory.memory_controller import MemoryController


# ── Examiner ────────────────────────────────────────────────

class TestMemoryControllerUnit:
    def test_creates_subsystems(self):
        mc = MemoryController(llm_client=None, db=None, session_id="test-1")
        assert mc.score_tracker is not None
        assert mc.nsb is not None
        assert mc.pcb is not None

    def test_export_load_roundtrip(self):
        mc = MemoryController(llm_client=None, db=None, session_id="test-1")
        mc.nsb.add_turn("行动", "叙事", turn=0)
        mc.score_tracker.get_or_create("钥匙", turn=0)
        state = mc.export_state()
        mc2 = MemoryController(llm_client=None, db=None, session_id="test-1")
        mc2.load_state(state)
        assert len(mc2.score_tracker.all_records()) == 1
        assert len(mc2.nsb._turn_buffer) == 1


class TestSimilarity:
    def test_jaccard_same(self):
        from app.services.memory.similarity import _jaccard_matrix
        result = _jaccard_matrix(["寿司"], ["寿司"])
        assert result[0, 0] == pytest.approx(1.0)

    def test_jaccard_different(self):
        from app.services.memory.similarity import _jaccard_matrix
        result = _jaccard_matrix(["寿司"], ["拉面"])
        assert result[0, 0] < 0.5

    def test_top_k_similar_empty(self):
        import asyncio
        async def run():
            from app.services.memory.similarity import top_k_similar
            results = await top_k_similar("query", [], embedding_client=None)
            assert results == []
        asyncio.run(run())

    def test_pcb_merge_with_embedding_constructor(self):
        """PCB accepts embedding_client parameter."""
        pcb = PersonaConstructionBranch(llm_client=None, embedding_client=None)
        assert pcb._embedding is None


# ── DB add_knowledge_chunk ─────────────────────────────────────


class TestDatabaseKnowledgeChunk:
    def test_add_knowledge_chunk(self, tmp_path):
        from app.database import Database
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.add_knowledge_chunk(
            chunk_id="test-ep-1",
            source_type="narrative_memory",
            title="测试摘要",
            content="这是一个测试摘要内容",
            keywords=["测试", "摘要"],
            importance=4,
        )
        # Should not raise
        assert db_path.exists()


# ── Full integration: forget + track + store ────────────────────


class TestMemoryIntegration:
    """End-to-end test: forgetting pipeline feeding into SCORE tracker."""

    def test_forget_then_track_continuity_works_together(self):
        # Create narrative memories
        records: list[MemoryRecord] = []
        for i in range(20):
            records.append(MemoryRecord(
                memory_id=f"m{i}",
                content=f"第{i}回合的叙事记忆",
                created_round=i,
                retrieved_rounds=[i - 1] if i > 0 else [],
            ))
        # Forget step
        survived = forget_step(records, current_round=25)

        # Track items from narrative context
        st = ScoreTracker()
        st.propose_transition("旧式左轮", ItemState.ACTIVE, 0)
        st.propose_transition("弹药", ItemState.ACTIVE, 5)
        st.propose_transition("旧式左轮", ItemState.LOST, 10)

        # Both should work correctly side by side
        assert len(survived) > 0
        assert st.get_record("旧式左轮").state == ItemState.LOST

    def test_nsb_pcb_lifecycle(self):
        """NSB and PCB co-evolve across simulated turns."""
        nsb = NarrativeSummarizationBranch(llm_client=None, theta1=6)
        pcb = PersonaConstructionBranch(llm_client=None, interval=10)

        for turn in range(25):
            nsb.add_turn(f"行动{turn}", f"叙事{turn}", turn=turn)
            pcb.on_turn()

        assert nsb.should_summarize_level1()  # 25 >= 6, should trigger
        assert pcb.should_extract()  # 25 >= 10, should trigger

        # Level-1 summaries buffer
        for i in range(5):
            nsb.accept_level1(EpisodeSummary(
                episode_id=f"ep1_{i}", turn_start=i*6, turn_end=i*6+5,
                summary=f"摘要{i}",
            ))
        assert nsb.should_summarize_level2()
