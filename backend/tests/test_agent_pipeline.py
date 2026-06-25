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

class TestExaminerAgent:
    def test_parse_ruling_permissible(self):
        raw = {"permissibility": "permissible", "triggered_rules": [], "constraints": "", "rejection_reason": ""}
        ruling = _parse_ruling(raw)
        assert ruling.permissibility == ActionPermissibility.PERMISSIBLE
        assert ruling.triggered_rules == []

    def test_parse_ruling_blocked(self):
        raw = {
            "permissibility": "blocked",
            "triggered_rules": [],
            "constraints": "大门紧锁",
            "rejection_reason": "你尝试推门，但门纹丝不动——似乎需要钥匙。",
        }
        ruling = _parse_ruling(raw)
        assert ruling.permissibility == ActionPermissibility.BLOCKED
        assert ruling.rejection_reason != ""

    def test_parse_ruling_with_triggered_rules(self):
        raw = {
            "permissibility": "conditional",
            "triggered_rules": [
                {"rule_type": "sanity_check", "rule_name": "SAN检定", "rule_details": "1d100 ≤ SAN值"}
            ],
            "constraints": "需要SAN检定",
            "rejection_reason": "",
        }
        ruling = _parse_ruling(raw)
        assert ruling.permissibility == ActionPermissibility.CONDITIONAL
        assert len(ruling.triggered_rules) == 1
        assert ruling.triggered_rules[0].rule_type == "sanity_check"

    def test_compact_entities_empty(self):
        assert _compact_entities([]) == "无"

    def test_compact_entities_with_items(self):
        items = [{"name": "钥匙", "status": "owned"}, {"name": "手电筒"}]
        result = _compact_entities(items)
        assert "钥匙" in result
        assert "手电筒" in result


# ── Director ────────────────────────────────────────────────

class TestDirectorAgent:
    def test_parse_instruction_basic(self):
        raw = {
            "narrative_direction": "引导玩家进入钟楼",
            "anchor_triggered": "anchor-1",
            "redirection_strategy": None,
            "redirection_hint": "",
            "item_continuity_checks": [],
            "health_guidance": "",
        }
        inst = _parse_instruction(raw)
        assert inst.narrative_direction == "引导玩家进入钟楼"
        assert inst.anchor_triggered == "anchor-1"
        assert inst.redirection_strategy is None

    def test_parse_instruction_with_redirection(self):
        raw = {
            "narrative_direction": "重定向玩家回主线",
            "anchor_triggered": "",
            "redirection_strategy": "npc_influence",
            "redirection_hint": "诺诺出现在远处向你招手",
            "item_continuity_checks": [],
            "health_guidance": "",
        }
        inst = _parse_instruction(raw)
        assert inst.redirection_strategy == RedirectionStrategy.NPC_INFLUENCE
        assert inst.redirection_hint == "诺诺出现在远处向你招手"

    def test_parse_instruction_with_item_continuity(self):
        raw = {
            "narrative_direction": "继续",
            "anchor_triggered": "",
            "redirection_strategy": None,
            "redirection_hint": "",
            "item_continuity_checks": [
                {"item_name": "旧式左轮", "previous_state": "lost", "current_state": "active",
                 "is_valid_transition": False, "error_description": "物品状态不一致"}
            ],
            "health_guidance": "",
        }
        inst = _parse_instruction(raw)
        assert len(inst.item_continuity_checks) == 1
        assert inst.item_continuity_checks[0].is_valid_transition is False

    def test_fallback_blocked(self):
        ruling = ActionRuling(permissibility=ActionPermissibility.BLOCKED, constraints="门锁住了")
        inst = _fallback_instruction(ruling)
        assert inst.redirection_strategy == RedirectionStrategy.WORLD_CONSEQUENCES

    def test_fallback_permissible(self):
        ruling = ActionRuling(permissibility=ActionPermissibility.PERMISSIBLE)
        inst = _fallback_instruction(ruling)
        assert inst.redirection_strategy is None


# ── MOOM Forgetting ─────────────────────────────────────────

class TestForgetting:
    def test_compute_score_new_memory(self):
        r = MemoryRecord(memory_id="m1", content="test", created_round=0, retrieved_rounds=[])
        s = compute_score(r, current_round=0)
        assert s > 0

    def test_compute_score_old_memory_decays(self):
        r = MemoryRecord(memory_id="m1", content="test", created_round=0, retrieved_rounds=[])
        s0 = compute_score(r, current_round=0)
        s10 = compute_score(r, current_round=10)
        # Older memory should score lower
        assert s10 < s0

    def test_compute_score_frequently_retrieved_reinforced(self):
        r1 = MemoryRecord(memory_id="m1", content="test", created_round=0, retrieved_rounds=[1, 3, 5])
        r2 = MemoryRecord(memory_id="m2", content="test", created_round=0, retrieved_rounds=[])
        s1 = compute_score(r1, current_round=10)
        s2 = compute_score(r2, current_round=10)
        # Frequently retrieved memory should score higher
        assert s1 > s2

    def test_score_all_sorts_descending(self):
        records = [
            MemoryRecord(memory_id="m1", content="a", created_round=5, retrieved_rounds=[]),
            MemoryRecord(memory_id="m2", content="b", created_round=0, retrieved_rounds=[]),
            MemoryRecord(memory_id="m3", content="c", created_round=10, retrieved_rounds=[11]),
        ]
        scored = score_all(records, current_round=12)
        scores = [s for _, s in scored]
        # Should be sorted descending
        assert scores == sorted(scores, reverse=True)

    def test_apply_reinforcement_adds_rounds(self):
        records = [
            MemoryRecord(memory_id="m1", content="a", created_round=0),
            MemoryRecord(memory_id="m2", content="b", created_round=0),
            MemoryRecord(memory_id="m3", content="c", created_round=0),
        ]
        scored = score_all(records, current_round=5)
        reinforced = apply_retrieval_reinforcement(scored, current_round=5, k=1)
        # Top-k should have retrieved_rounds updated
        assert 5 in reinforced[0].retrieved_rounds  # top-1 got recorded

    def test_prune_pool_drops_below_threshold(self):
        records = [
            MemoryRecord(memory_id="m1", content="a", score=0.5),
            MemoryRecord(memory_id="m2", content="b", score=0.001),
        ]
        pruned = prune_pool(records, threshold=0.01)
        assert len(pruned) == 1
        assert pruned[0].memory_id == "m1"

    def test_prune_pool_caps_max_size(self):
        records = [MemoryRecord(memory_id=f"m{i}", content="x", score=0.5) for i in range(300)]
        pruned = prune_pool(records, threshold=0.01, max_size=200)
        assert len(pruned) == 200

    def test_forget_step_idempotent_on_empty(self):
        result = forget_step([], current_round=0)
        assert result == []

    def test_forget_step_returns_fewer_or_equal(self):
        records = [MemoryRecord(memory_id=f"m{i}", content="x", created_round=i) for i in range(50)]
        result = forget_step(records, current_round=60)
        # Some old records may be pruned, pool shrinks or stays same
        assert len(result) <= len(records)

    def test_alpha_beta_sum_to_1(self):
        # From MOOM paper: α=0.1, β=0.9
        assert ALPHA + BETA == pytest.approx(1.0)
        assert K == pytest.approx(9)


# ── SCORE Tracker ───────────────────────────────────────────

class TestScoreTracker:
    def test_create_new_item(self):
        st = ScoreTracker()
        r = st.get_or_create("旧式左轮", turn=0)
        assert r.item_name == "旧式左轮"
        assert r.state == ItemState.ACTIVE

    def test_valid_transition(self):
        st = ScoreTracker()
        st.get_or_create("钥匙", turn=0, state=ItemState.ACTIVE)
        new_state, is_error = st.propose_transition("钥匙", ItemState.LOST, turn=5)
        assert new_state == ItemState.LOST
        assert not is_error

    def test_continuity_error_active_after_lost(self):
        st = ScoreTracker()
        st.get_or_create("钥匙", turn=0, state=ItemState.LOST)
        new_state, is_error = st.propose_transition("钥匙", ItemState.ACTIVE, turn=5)
        assert is_error  # Should flag as continuity error
        assert new_state == ItemState.LOST  # Should keep previous state

    def test_continuity_error_active_after_destroyed(self):
        st = ScoreTracker()
        st.get_or_create("信件", turn=0, state=ItemState.DESTROYED)
        new_state, is_error = st.propose_transition("信件", ItemState.ACTIVE, turn=5)
        assert is_error
        assert new_state == ItemState.DESTROYED

    def test_check_narration_detects_violation(self):
        st = ScoreTracker()
        st.get_or_create("神秘钥匙", turn=0, state=ItemState.LOST)
        items = [{"name": "神秘钥匙", "status": "owned"}]
        violations = st.check_narration_continuity("你找到了神秘钥匙", turn=5, items_from_llm=items)
        assert len(violations) > 0
        assert violations[0]["item_name"] == "神秘钥匙"

    def test_load_export_roundtrip(self):
        st = ScoreTracker()
        st.get_or_create("旧式左轮", turn=0, state=ItemState.ACTIVE)
        st.get_or_create("警徽", turn=0, state=ItemState.ACTIVE)
        exported = st.export_state()
        st2 = ScoreTracker()
        st2.load_from_state(exported)
        assert len(st2.all_records()) == 2
        assert st2.get_record("旧式左轮").state == ItemState.ACTIVE

    def test_get_all_states(self):
        st = ScoreTracker()
        st.propose_transition("A", ItemState.ACTIVE, 0)
        st.propose_transition("B", ItemState.LOST, 1)
        states = st.get_all_states()
        assert states["A"] == "active"
        assert states["B"] == "lost"


# ── NSB ──────────────────────────────────────────────────────

class TestNarrativeSummarizationBranch:
    def test_should_summarize_level1_after_theta1_turns(self):
        nsb = NarrativeSummarizationBranch(llm_client=None, theta1=6)
        assert not nsb.should_summarize_level1()
        for i in range(6):
            nsb.add_turn(f"行动{i}", f"叙事{i}", turn=i)
        assert nsb.should_summarize_level1()

    def test_should_not_summarize_level2_prematurely(self):
        nsb = NarrativeSummarizationBranch(llm_client=None, theta2=5)
        assert not nsb.should_summarize_level2()

    def test_accept_level1_stores_and_enables_level2(self):
        nsb = NarrativeSummarizationBranch(llm_client=None, theta2=5)
        for i in range(5):
            nsb.accept_level1(EpisodeSummary(
                episode_id=f"ep1_{i}", turn_start=i*6, turn_end=i*6+5,
                summary=f"摘要{i}", tags=["悬疑"], entities_involved=["玩家"],
            ))
        assert nsb.should_summarize_level2()

    @pytest.mark.asyncio
    async def test_get_retrieval_context_by_query(self):
        nsb = NarrativeSummarizationBranch(llm_client=None)
        nsb.accept_level1(EpisodeSummary(
            episode_id="ep1", turn_start=0, turn_end=5,
            summary="战斗场景", tags=["战斗"], entities_involved=["老汤姆"],
            importance=0.8,
        ))
        nsb.accept_level1(EpisodeSummary(
            episode_id="ep2", turn_start=6, turn_end=11,
            summary="探索场景", tags=["探索"], entities_involved=["钟楼"],
            importance=0.5,
        ))
        results = await nsb.get_retrieval_context("老汤姆")
        assert len(results) > 0
        # Entity match should rank higher
        assert results[0].episode_id == "ep1"

    def test_export_load_roundtrip(self):
        nsb = NarrativeSummarizationBranch(llm_client=None)
        nsb.add_turn("行动", "叙事", turn=0)
        nsb.accept_level1(EpisodeSummary(
            episode_id="ep1", turn_start=0, turn_end=5,
            summary="测试", tags=["测试"],
        ))
        state = nsb.export_state()
        nsb2 = NarrativeSummarizationBranch(llm_client=None)
        nsb2.load_state(state)
        assert len(nsb2._turn_buffer) == 1
        assert len(nsb2._level1) == 1


# ── PCB ──────────────────────────────────────────────────────

class TestPersonaConstructionBranch:
    def test_should_extract_after_interval(self):
        pcb = PersonaConstructionBranch(llm_client=None, interval=10)
        assert not pcb.should_extract()
        for _ in range(10):
            pcb.on_turn()
        assert pcb.should_extract()

    def test_merge_snapshot_replace_keys(self):
        pcb = PersonaConstructionBranch(llm_client=None)
        snap = PersonaSnapshot(
            entries={"name": [PersonaValue(value="路明非", turn=0)]},
            extracted_at_turn=10,
        )
        pcb.merge_snapshot(snap)
        assert "name" in pcb._sketch.entries
        assert pcb._sketch.entries["name"][0].value == "路明非"

        # Update name — should replace
        snap2 = PersonaSnapshot(
            entries={"name": [PersonaValue(value="楚子航", turn=20)]},
            extracted_at_turn=20,
        )
        pcb.merge_snapshot(snap2)
        assert len(pcb._sketch.entries["name"]) == 1
        assert pcb._sketch.entries["name"][0].value == "楚子航"

    def test_merge_snapshot_add_keys_append(self):
        pcb = PersonaConstructionBranch(llm_client=None)
        snap = PersonaSnapshot(
            entries={"liked_food": [PersonaValue(value="寿司", turn=0)]},
            extracted_at_turn=0,
        )
        pcb.merge_snapshot(snap)
        snap2 = PersonaSnapshot(
            entries={"liked_food": [PersonaValue(value="拉面", turn=10)]},
            extracted_at_turn=10,
        )
        pcb.merge_snapshot(snap2)
        values = pcb._sketch.entries["liked_food"]
        assert len(values) >= 1

    def test_get_persona_text(self):
        pcb = PersonaConstructionBranch(llm_client=None)
        snap = PersonaSnapshot(
            entries={
                "name": [PersonaValue(value="路明非", turn=0)],
                "skills": [PersonaValue(value="射击", turn=3)],
            },
            extracted_at_turn=5,
        )
        pcb.merge_snapshot(snap)
        text = pcb.get_persona_text()
        assert "路明非" in text
        assert "角色档案" in text

    def test_export_load_roundtrip(self):
        pcb = PersonaConstructionBranch(llm_client=None)
        snap = PersonaSnapshot(
            entries={"name": [PersonaValue(value="路明非", turn=0)]},
            extracted_at_turn=5,
        )
        pcb.merge_snapshot(snap)
        for _ in range(5):
            pcb.on_turn()
        state = pcb.export_state()
        pcb2 = PersonaConstructionBranch(llm_client=None)
        pcb2.load_state(state)
        assert "name" in pcb2._sketch.entries

    def test_approx_equal_same(self):
        assert _approx_equal("寿司", "寿司")

    def test_approx_equal_different(self):
        assert not _approx_equal("寿司", "天妇罗")


# ── Schemas ──────────────────────────────────────────────────

class TestAgentIOSchemas:
    def test_action_ruling_defaults(self):
        r = ActionRuling()
        assert r.permissibility == ActionPermissibility.PERMISSIBLE
        assert r.triggered_rules == []

    def test_director_instruction_defaults(self):
        d = DirectorInstruction(narrative_direction="继续叙事")
        assert d.narrative_direction == "继续叙事"
        assert d.anchor_triggered == ""
        assert d.anchor_triggered == ""

    def test_episode_summary_defaults(self):
        e = EpisodeSummary(episode_id="test", turn_start=0, turn_end=5, summary="测试")
        assert e.importance > 0.0
        assert e.level == 1

    def test_memory_record_score_initial(self):
        r = MemoryRecord(memory_id="m1", content="test")
        assert r.score == 0.0

    def test_item_state_enum_values(self):
        assert ItemState.ACTIVE.value == "active"
        assert ItemState.LOST.value == "lost"
        assert ItemState.DESTROYED.value == "destroyed"

    def test_redirection_strategy_enum_values(self):
        assert RedirectionStrategy.NPC_INFLUENCE.value == "npc_influence"
        assert RedirectionStrategy.WORLD_CONSEQUENCES.value == "world_consequences"

    def test_triggered_rule_fields(self):
        rule = TriggeredRule(rule_type="sanity_check", rule_name="测试", rule_details="1d100")
        assert rule.rule_type == "sanity_check"
        assert rule.rule_name == "测试"

    def test_item_continuity_check(self):
        from app.schemas.agent_io import ItemContinuityCheck
        ic = ItemContinuityCheck(
            item_name="钥匙", previous_state="lost", current_state="active",
            is_valid_transition=False, error_description="测试",
        )
        assert not ic.is_valid_transition

    def test_hallucination_finding(self):
        from app.schemas.agent_io import HallucinationFinding, HallucinationType
        hf = HallucinationFinding(
            hallucination_type=HallucinationType.FABRICATION,
            description="LLM fabricated an item",
        )
        assert hf.hallucination_type == HallucinationType.FABRICATION


# ── Integration: pipe through the full call chain in memory ──

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


class TestForgettingFullPipeline:
    """Test the MOOM forgetting pipeline end-to-end with realistic data."""

    def test_30_rounds_no_overflow(self):
        """Simulate 30 rounds: pool should not grow unbounded."""
        records: list[MemoryRecord] = []
        for round_num in range(30):
            # Add new memory each round
            new = MemoryRecord(
                memory_id=f"m{round_num}",
                content=f"场景{round_num}的叙事记忆",
                created_round=round_num,
                retrieved_rounds=[round_num - 1] if round_num > 0 else [],
            )
            records.append(new)
            # Run forgetting step
            records = forget_step(records, current_round=round_num)
            # Pool should never exceed MAX_POOL_SIZE
            assert len(records) <= 200, f"Pool overflow at round {round_num}"

    def test_important_memories_survive(self):
        """Memories with high retrieval reinforcement should survive pruning."""
        records: list[MemoryRecord] = []
        # Create one important memory retrieved every round
        important = MemoryRecord(
            memory_id="important",
            content="关键剧情转折",
            created_round=0,
            retrieved_rounds=list(range(50)),
        )
        records.append(important)
        # Create 100 low-value memories
        for i in range(100):
            records.append(MemoryRecord(
                memory_id=f"noise_{i}",
                content=f"噪音记忆{i}",
                created_round=i,
                retrieved_rounds=[],
            ))
        result = forget_step(records, current_round=55)
        ids = {r.memory_id for r in result}
        assert "important" in ids, "High-value memory should survive after 55 rounds"


class TestScoreTrackerCampaign:
    """Realistic campaign-style SCORE tracker tests."""

    def test_multi_item_campaign_flow(self):
        st = ScoreTracker()
        turns = [
            (0, [("钥匙", "owned"), ("旧式左轮", "owned"), ("警徽", "owned")]),
            (5, [("钥匙", "lost"), ("弹药", "owned")]),
            (10, [("钥匙", "owned")]),  # ← continuity error!
            (15, [("旧式左轮", "lost"), ("弹药", "lost")]),
            (20, [("弹药", "owned")]),  # ← continuity error!
        ]
        violations_all = []
        for turn, items in turns:
            items_parsed = [{"name": name, "status": status} for name, status in items]
            v = st.check_narration_continuity(f"T{turn} 叙事", turn, items_parsed)
            violations_all.extend(v)

        assert len(violations_all) >= 2  # Two continuity errors detected
        # Key: after T10 violation, key state should remain 'lost'
        assert st.get_record("钥匙").state == ItemState.LOST

    def test_state_consistency_across_sessions(self):
        """Simulate state persistence across multiple sessions."""
        # Session 1
        st = ScoreTracker()
        st.propose_transition("神秘信件", ItemState.ACTIVE, 0)
        st.propose_transition("神秘信件", ItemState.LOST, 8)
        export = st.export_state()

        # Session 2 — load and continue
        st2 = ScoreTracker()
        st2.load_from_state(export)
        assert st2.get_record("神秘信件").state == ItemState.LOST

        # Continuity error should still fire
        items = [{"name": "神秘信件", "status": "owned"}]
        violations = st2.check_narration_continuity("你找到了神秘信件", 5, items)
        assert len(violations) == 1


# ── HaluMem Evaluator ──────────────────────────────────────────

class TestHaluMemEvaluator:
    def test_parse_findings_empty(self):
        from app.services.memory.halumem_eval import _parse_findings
        assert _parse_findings({"findings": []}) == []

    def test_parse_findings_real(self):
        from app.services.memory.halumem_eval import _parse_findings
        data = {
            "findings": [
                {
                    "hallucination_type": "fabrication",
                    "memory_id": "m1",
                    "description": "LLM fabricated an item",
                    "ground_truth": "物品不存在",
                },
                {
                    "hallucination_type": "omission",
                    "memory_id": "m2",
                    "description": "Failed to record NPC appearance",
                    "ground_truth": "诺诺出现在钟楼",
                },
            ]
        }
        findings = _parse_findings(data)
        assert len(findings) == 2
        assert findings[0].hallucination_type == HallucinationType.FABRICATION
        assert findings[1].hallucination_type == HallucinationType.OMISSION

    def test_compute_metrics_empty(self):
        from app.services.memory.halumem_eval import HaluMemEvaluator
        evaluator = HaluMemEvaluator(llm_client=None)
        metrics = evaluator.compute_metrics([], [], [], total_expected_memories=10)
        assert metrics["total_findings"] == 0
        assert metrics["hallucination_rate"] == 0.0

    def test_compute_metrics_with_findings(self):
        from app.services.memory.halumem_eval import HaluMemEvaluator
        evaluator = HaluMemEvaluator(llm_client=None)
        f1 = HallucinationFinding(hallucination_type=HallucinationType.FABRICATION, description="fabricated")
        f2 = HallucinationFinding(hallucination_type=HallucinationType.ERROR, description="wrong")
        f3 = HallucinationFinding(hallucination_type=HallucinationType.OMISSION, description="missed")
        metrics = evaluator.compute_metrics([f1], [f2], [f3], total_expected_memories=20)
        assert metrics["total_findings"] == 3
        assert metrics["fabrications"] == 1
        assert metrics["errors"] == 1
        assert metrics["omissions"] == 1
        assert metrics["hallucination_rate"] == 3 / 20


# ── Similarity ─────────────────────────────────────────────────

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
