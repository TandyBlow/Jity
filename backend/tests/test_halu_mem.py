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
