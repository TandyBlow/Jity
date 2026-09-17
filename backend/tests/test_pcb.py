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
