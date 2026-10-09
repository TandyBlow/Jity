"""Budget and failed-turn cases that exercise the real campaign services."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.exceptions import ConcurrentModificationError
from app.schemas import GenerateRequest
from app.schemas.agent_io import OpeningOptions
from app.schemas.campaign import EndingRoute
from app.services.campaign_endings import select_budget_ending
from tests.test_turn_commit_consistency import Harness


def test_session_allocation_stays_fixed_until_its_boundary(tmp_path):
    h = Harness(tmp_path)
    for turn in (0, 1, 5, 9, 10):
        h.manager.progress.turn_in_session = turn
        h.manager.progress.turns_total = turn
        assert h.manager.resolve_max_turns() == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("cap", [1, 5, 50])
async def test_real_openings_do_not_consume_the_ending_turn(tmp_path, cap):
    h = Harness(tmp_path)
    h.manager.campaign.max_turns_per_campaign = cap
    del h.gen._handle_opening_scene
    h.gen._generate_opening_options = AsyncMock(return_value=OpeningOptions(
        options=["观察环境", "与同伴交谈", "检查物品"], option_checks=[None, None, None],
    ))
    openings = []
    for turn in range(1, cap + 1):
        position = (h.manager.progress.arc_index, h.manager.progress.session_index)
        assert position[0] < len(h.manager.campaign.arcs)
        response = await h.generate()
        assert response.campaign_progress["turns_total"] == turn
        if response.source == "scripted":
            openings.append(position)
        if response.output.game_over:
            break
    assert response.output.game_over
    assert response.output.options == []
    assert response.campaign_progress["turns_total"] == cap
    if cap == 50:
        assert openings == [(0, 0), (0, 1), (1, 0), (2, 0), (2, 1)]
        assert (h.manager.progress.arc_index, h.manager.progress.session_index) == (2, 1)
    with pytest.raises(ConcurrentModificationError):
        await h.generate()


@pytest.mark.asyncio
async def test_short_final_session_closes_without_advancing_past_campaign(tmp_path):
    h = Harness(tmp_path)
    h.manager.campaign.max_turns_per_campaign = 7
    h.manager.campaign.max_turns_per_session = 1
    for _ in range(7):
        response = await h.generate()
        assert h.manager.progress.arc_index < len(h.manager.campaign.arcs)
        if response.output.game_over:
            break
    assert response.output.game_over
    assert response.campaign_progress["turns_total"] == 5
    assert (h.manager.progress.arc_index, h.manager.progress.session_index) == (2, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["snapshot", "finalize", "cancel"])
async def test_failure_before_node_commit_discards_all_runtime_changes(tmp_path, monkeypatch, stage):
    h = Harness(tmp_path)
    h.set_narration_delta([{"name": "同伴", "sentiment": "positive"}])
    root = h.head()
    error = asyncio.CancelledError if stage == "cancel" else RuntimeError
    with monkeypatch.context() as patch:
        if stage == "snapshot":
            def fail_snapshot(*args):
                raise error("injected snapshot failure")
            patch.setattr(h.gen, "_campaign_progress_snapshot", fail_snapshot)
        else:
            original = h.gen._record_and_finalize
            async def fail_finalize(*args, **kwargs):
                await original(*args, **kwargs)
                raise error("injected finalize failure")
            patch.setattr(h.gen, "_record_and_finalize", fail_finalize)
        with pytest.raises(error):
            await h.generate()
    assert h.head() == root
    assert h.progress_row()["turns_total"] == 0
    assert h.manager.progress.turns_total == 0
    assert h.manager._pending_npc_relations is None
    response = await h.generate()
    assert response.campaign_progress["turns_total"] == 1
    assert json.loads(h.progress_row()["npc_relations"])[0]["affinity"] == 1


@pytest.mark.asyncio
async def test_memory_maintenance_starts_after_a_successful_node_commit(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    memory = h.gen._get_memory_controller.return_value

    async def maintain(*args):
        assert h.progress_row()["turns_total"] == 1
        assert h.node_count() == 2
    memory.maintain = AsyncMock(side_effect=maintain)

    original = h.gen._record_and_finalize
    with monkeypatch.context() as patch:
        async def fail_finalize(*args, **kwargs):
            await original(*args, **kwargs)
            await asyncio.sleep(0)
            raise RuntimeError("injected failure before node commit")
        patch.setattr(h.gen, "_record_and_finalize", fail_finalize)
        with pytest.raises(RuntimeError):
            await h.generate()
    await asyncio.sleep(0)
    memory.maintain.assert_not_awaited()

    await h.generate()
    if h.gen._memory_tasks:
        await asyncio.gather(*h.gen._memory_tasks)
    memory.maintain.assert_awaited_once()


@pytest.mark.asyncio
async def test_closing_turn_reaches_narrator_for_a_blocked_action(tmp_path, monkeypatch):
    from app.schemas.agent_io import ActionPermissibility, ActionRuling
    from app.services.agents.examiner import ExaminerAgent

    h = Harness(tmp_path)
    h.manager.progress.turns_total = 49
    h.manager.save_progress()
    monkeypatch.setattr(ExaminerAgent, "examine", AsyncMock(return_value=ActionRuling(
        permissibility=ActionPermissibility.BLOCKED, rejection_reason="该行动无法完成。",
    )))
    response = await h.gen.generate(
        h.session_id, GenerateRequest(player_action="让整个宇宙消失"),
    )
    assert response.source == "llm"
    assert response.output.game_over
    assert response.output.narration != "该行动无法完成。"
    assert response.campaign_progress["turns_total"] == 50


@pytest.mark.asyncio
async def test_failed_anchor_commit_does_not_suppress_retry(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    h.stage_pending_anchor()
    with monkeypatch.context() as patch:
        def fail_commit(*args, **kwargs):
            raise ConcurrentModificationError("injected")
        patch.setattr(h.db, "commit_story_turn", fail_commit)
        with pytest.raises(ConcurrentModificationError):
            await h.generate()
    assert h.manager._check_cooldown("dynamic-test-anchor", 0)
    assert h.manager._anchors.pending_anchor_triggers == []


@pytest.mark.asyncio
async def test_arc_boundary_generates_and_stores_one_recap(tmp_path):
    h = Harness(tmp_path)
    h.manager.progress.session_index = 1
    h.manager.progress.turn_in_session = 9
    h.manager.progress.turns_total = 19
    h.manager.save_progress()
    h.db.update_npc_relations(
        h.manager.progress.campaign_id, '[{"name": "同伴", "affinity": 3}]'
    )
    h.manager._recap.generate_recap = AsyncMock(return_value="章节提要。")

    response = await h.generate()

    h.manager._recap.generate_recap.assert_awaited_once()
    row = h.progress_row()
    assert row["arc_index"] == 1 and row["session_index"] == 0
    assert row["recap_full"].count("章节提要。") == 1
    assert json.loads(row["npc_relations"])[0]["affinity"] == 2
    node = h.db.get_story_turn(h.session_id, response.timeline_node_id)
    snapshot = json.loads(node["campaign_progress_json"])
    assert snapshot["recap_full"] == row["recap_full"]
    assert snapshot["npc_relations"] == row["npc_relations"]


def test_manual_campaign_end_preserves_whole_campaign_counter(tmp_path):
    h = Harness(tmp_path)
    h.manager.progress.turns_total = 12
    h.manager.save_progress()
    h.manager.end_campaign()
    assert h.progress_row()["turns_total"] == 12


@pytest.mark.parametrize("facts,action", [
    ([{"name": "封印已解除"}], ""),
    ([], "与同伴离开"),
    ([{"name": "封印已解除", "status": "suspected"}, {"name": "同伴已获救"}], "与同伴离开"),
])
def test_budget_route_requires_all_confirmed_conditions(facts, action):
    route = EndingRoute(
        id="saved", name="共同离开", category="good",
        requirements=["封印已解除", "同伴已获救"], trigger_phrases=["与同伴离开"],
        resolution="两人离开。",
    )
    campaign = SimpleNamespace(arcs=[], ending_routes=[route])
    progress = SimpleNamespace(turns_total=49, revealed_anchors=[])
    state = {"quests": [{"name": "完成报到", "status": "completed"}], "world_facts": facts}
    selected = select_budget_ending(campaign, progress, state, 50, action)
    assert selected.id == "budget-incomplete"


def test_budget_route_accepts_all_confirmed_conditions():
    route = EndingRoute(
        id="saved", name="共同离开", category="good",
        requirements=["封印已解除", "同伴已获救"], trigger_phrases=["与同伴离开"],
        resolution="两人离开。",
    )
    campaign = SimpleNamespace(arcs=[], ending_routes=[route])
    progress = SimpleNamespace(turns_total=49, revealed_anchors=[])
    state = {
        "quests": [{"name": "完成报到", "status": "completed"}],
        "world_facts": [
            {"name": "封印已解除", "status": "confirmed"},
            {"name": "同伴已获救", "status": "known"},
        ],
    }
    assert select_budget_ending(campaign, progress, state, 50, "与同伴离开").id == "saved"


@pytest.mark.asyncio
async def test_budget_turn_does_not_bypass_conditions_via_regular_ending(tmp_path):
    h = Harness(tmp_path)
    h.manager.progress.arc_index = 2
    h.manager.progress.session_index = 1
    h.manager.progress.turn_in_session = 9
    h.manager.progress.turns_total = 49
    h.manager.save_progress()
    response = await h.gen.generate(
        h.session_id, GenerateRequest(player_action="选择继承封印"),
    )
    assert response.output.game_over
    assert response.output.game_over_reason.startswith("回合预算耗尽")
