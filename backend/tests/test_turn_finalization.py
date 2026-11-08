"""Opening and narrated turns share persistence and retry guarantees."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from app.exceptions import ConcurrentModificationError
from app.schemas import GenerateRequest
from app.schemas.agent_io import OpeningOptions
from tests.test_turn_commit_consistency import Harness


@pytest.fixture(params=["scripted", "llm"])
def turn_runtime(tmp_path, request):
    h = Harness(tmp_path)
    if request.param == "scripted":
        del h.gen._handle_opening_scene
        h.gen._generate_opening_options = AsyncMock(return_value=OpeningOptions(
            options=["观察大厅", "向接待员询问", "检查随身物品"],
            option_checks=[None, None, None],
        ))
    h.expected_source = request.param
    return h


@pytest.mark.asyncio
async def test_turn_response_matches_committed_state_and_history(turn_runtime):
    h = turn_runtime
    parent = h.head()
    h.stage_pending_anchor()

    response = await h.generate()
    await h.gen._wait_memory(h.session_id)

    node = h.db.get_story_turn(h.session_id, response.timeline_node_id)
    state = json.loads(node["state_json"])
    stored_output = h.db.get_model_output(response.model_output_id)
    progress = json.loads(node["campaign_progress_json"])
    assert response.source == node["source"] == stored_output["source"] == h.expected_source
    assert response.parent_timeline_node_id == node["parent_turn_id"] == parent
    assert h.head() == response.timeline_node_id and h.node_count() == 2
    assert node["model_output_id"] == response.model_output_id
    assert json.loads(node["output_json"]) == json.loads(stored_output["output_json"]) == response.output.model_dump()
    assert h.state_manager.sanitize_state(dict(state)) == response.state
    assert h.state_manager.get_session_payload(h.session_id)["state"] == state
    assert response.state["turn"] == 1
    assert len(state["_memory_controller"]["nsb"]["turn_buffer"]) == 1
    assert response.memory == h.state_manager.memory_trace_entry(response.output.model_dump(), response.state)
    assert response.campaign_progress == h.manager.campaign_view(response.state)
    assert progress["turns_total"] == progress["turn_in_session"] == 1
    assert progress["revealed_anchors"] == h.progress_row()["revealed_anchors"]
    assert ("dynamic-test-anchor" in json.loads(progress["revealed_anchors"])) is (h.expected_source == "llm")
    messages = h.db.get_recent_messages(h.session_id)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert json.loads(messages[1]["content"]) == response.output.model_dump()
    assert stored_output["word_count"] == len(response.output.narration)
    assert stored_output["option_count"] == len(response.output.options)

    # A replay with the old parent cannot create another node or advance pacing.
    with pytest.raises(ConcurrentModificationError):
        await h.gen.generate(h.session_id, GenerateRequest(player_action="重试", timeline_node_id=parent))
    assert h.node_count() == 2 and h.progress_row()["turns_total"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["record", "snapshot", "commit", "cancel"])
async def test_failed_turn_retries_without_leaking_state_or_memory(turn_runtime, monkeypatch, stage):
    h = turn_runtime
    parent = h.head()
    original_state = h.state_manager.get_session_payload(h.session_id)["state"]
    h.stage_pending_anchor()
    error = asyncio.CancelledError if stage == "cancel" else RuntimeError

    def fail(*args, **kwargs):
        raise error("injected finalization failure")

    with monkeypatch.context() as patch:
        if stage == "record":
            patch.setattr(h.db, "add_model_output", fail)
        elif stage == "commit":
            patch.setattr(h.db, "commit_story_turn", fail)
        else:
            # Snapshot assembly happens after in-memory advancement, before commit.
            patch.setattr(h.gen, "_campaign_progress_snapshot", fail)
        with pytest.raises(error):
            await h.generate()

    assert h.head() == parent and h.node_count() == 1
    assert h.state_manager.get_session_payload(h.session_id)["state"] == original_state
    assert h.db.get_recent_messages(h.session_id) == []
    assert h.progress_row()["turns_total"] == h.manager.progress.turns_total == 0
    assert h.progress_row()["revealed_anchors"] == "[]"
    assert h.manager._pending_npc_relations is None
    assert h.session_id not in h.gen._memory_controllers
    assert not h.gen._memory_jobs and not h.gen._memory_tasks

    response = await h.generate()
    await h.gen._wait_memory(h.session_id)
    assert response.source == h.expected_source
    assert response.state["turn"] == h.progress_row()["turns_total"] == 1
    assert h.node_count() == 2 and h.head() == response.timeline_node_id
    assert len(h.db.get_recent_messages(h.session_id)) == 2
    state = h.state_manager.get_session_payload(h.session_id)["state"]
    assert len(state["_memory_controller"]["nsb"]["turn_buffer"]) == 1
