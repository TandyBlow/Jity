"""Master's forced story beats coexist with local checks and ending rules."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas import ActionCheckSubmission, GenerateRequest, OptionCheck, StoryOutput
from app.services.prompt_builder import PromptBuilder
from tests.test_turn_commit_consistency import Harness


async def _checked_hard_turn(tmp_path):
    h = Harness(tmp_path)
    # Exercise real context assembly and anchor staging, not the transaction
    # harness's prompt stub. Only retrieval and model responses are supplied.
    del h.gen._build_prompt
    h.gen.prompt_builder = PromptBuilder()
    h.gen.retriever = SimpleNamespace(retrieve_async=AsyncMock(return_value=[]))
    h.llm.generate = AsyncMock(side_effect=lambda *args, **kwargs: (StoryOutput(
        narration="你在大厅门边发现了一份档案。", current_location="报到处大厅",
        options=["搜索档案"], option_checks=[OptionCheck(difficulty="困难")],
    ), 1))
    opened = await h.gen.generate(h.session_id, GenerateRequest(player_action="入场"))
    await h.gen._wait_memory(h.session_id)
    h.manager.progress.revealed_anchors = []
    h.manager.progress.turn_in_session = h.manager.resolve_hard_turns() - 1
    h.manager.progress.turns_total = h.manager.progress.turn_in_session
    h.manager.save_progress()
    h.llm.generate = AsyncMock(side_effect=lambda *args, **kwargs: (StoryOutput(
        narration="档案被锁住了，但门边浮现的红色标记让事态发生了变化。",
        current_location="报到处大厅", options=["继续"],
    ), 1))
    request = GenerateRequest(
        player_action="搜索档案", timeline_node_id=opened.timeline_node_id,
        action_check=ActionCheckSubmission(roll=1, option_index=0),
    )
    return h, request


@pytest.mark.asyncio
@pytest.mark.parametrize("roll,outcome", [(1, "fumble"), (16, "success")])
async def test_hard_story_beat_preserves_roll_and_commits_one_core_anchor(tmp_path, roll, outcome):
    h, request = await _checked_hard_turn(tmp_path)
    request.action_check.roll = roll
    session = h.manager.campaign.arcs[0].sessions[0]
    before_total = h.manager.progress.turns_total

    response = await h.gen.generate(h.session_id, request)
    await h.gen._wait_memory(h.session_id)

    prompt = h.llm.generate.await_args.args[0]
    assert "核心剧情强制补完指令" in prompt
    assert f"骰面 {roll}/20" in prompt
    if outcome == "fumble":
        assert "不得把原行动写成成功" in prompt
    assert response.output.action_check.outcome == outcome
    assert not response.output.game_over
    assert h.manager.progress.revealed_anchors == [session.completion_anchors[0]]
    assert not h.manager.is_closing_pending()
    node = h.db.get_story_turn(h.session_id, response.timeline_node_id)
    progress = json.loads(node["campaign_progress_json"])
    assert progress["turns_total"] == before_total + 1
    assert json.loads(progress["revealed_anchors"]) == [session.completion_anchors[0]]
    assert json.loads(node["output_json"])["action_check"]["roll"] == roll


@pytest.mark.asyncio
async def test_failed_commit_rolls_back_forced_anchor_and_retries_same_roll(tmp_path, monkeypatch):
    h, request = await _checked_hard_turn(tmp_path)
    before_head, before_count, before_progress = h.head(), h.node_count(), h.progress_row()
    with monkeypatch.context() as patch:
        def fail_commit(**kwargs):
            raise RuntimeError("injected node commit failure")

        patch.setattr(h.db, "commit_story_turn", fail_commit)
        with pytest.raises(RuntimeError, match="injected node commit failure"):
            await h.gen.generate(h.session_id, request)

    assert h.head() == before_head and h.node_count() == before_count
    assert h.progress_row() == before_progress
    assert h.manager.progress.revealed_anchors == []
    assert h.manager._anchors.pending_anchor_triggers == []

    response = await h.gen.generate(h.session_id, request)
    await h.gen._wait_memory(h.session_id)
    assert response.output.action_check.roll == 1
    assert response.output.action_check.outcome == "fumble"
    assert h.node_count() == before_count + 1
    assert len(h.manager.progress.revealed_anchors) == 1


@pytest.mark.asyncio
async def test_hard_turn_budget_ending_keeps_failed_check_and_complete_prose(tmp_path):
    h, request = await _checked_hard_turn(tmp_path)
    h.manager.progress.turns_total = 49
    h.manager.save_progress()

    response = await h.gen.generate(h.session_id, request)
    await h.gen._wait_memory(h.session_id)

    assert response.output.game_over
    assert response.output.action_check.outcome == "fumble"
    assert response.output.options == response.output.option_checks == []
    assert 180 <= len(response.output.narration) <= 260
    assert response.campaign_progress["turns_total"] == 50
    assert h.progress_row()["fsm_state"] == "campaign_end"
    ending_call, = [call for call in h.llm.generate_text.await_args_list
                   if call.kwargs.get("purpose") == "ending_narrative"]
    assert "骰面 1/20，结果：大失败" in ending_call.args[0]
