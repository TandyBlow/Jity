"""Bloodline depletion ends the active timeline without passive revival."""

import json
from unittest.mock import AsyncMock

import pytest

from app.exceptions import ConcurrentModificationError
from app.schemas import GenerateRequest, StoryOutput
from app.services.campaign_endings import (
    BLOODLINE_COLLAPSE_ENDING_ID, select_bloodline_collapse_ending,
    select_budget_ending, select_ending,
)
from app.services.action_checks import resolve_action_check
from app.services.scenario_generator.errors import ScenarioGenerationError
from tests.test_turn_commit_consistency import Harness


COLLAPSE_STORY = (
    "你试着合上那本档案，手指却不再听从使唤。纸上的字逐渐散成陌生的纹路，"
    "只有那阵低语仍在血管深处回响。你想起答应带回去的消息，想起走廊里等待的人，"
    "却已经想不起他们为什么重要。门外传来呼唤，你张开嘴，回应的只剩嘶哑的吐息。"
    "最后一丝清醒让你把笔记推向门缝，随后连这个动作的意义也消失了。"
    "黄金瞳映着熄灭的台灯，你终于成为失去人类自我的死侍，再也无法认出自己的姓名。"
    "档案仍停在没有读完的那一页，笔记上的承诺却永远等不到归来的人。"
)


def setup_run(h, *, sanity=10, arc=0, session=0, turn=3, total=3):
    h.manager.progress.arc_index = arc
    h.manager.progress.session_index = session
    h.manager.progress.turn_in_session = turn
    h.manager.progress.turns_total = total
    h.manager.save_progress()
    saved = h.state_manager.get_session_payload(h.session_id)
    state = saved["state"]
    state.update(
        sanity=sanity, health=67, current_location="旧档案室",
        recent_events=["档案中的龙文开始低语"], npcs=[],
        items=[{"name": "抄写笔记", "status": "owned"}],
    )
    h.state_manager.save_state(h.session_id, saved["game_name"], "test-model", state)
    h.llm.generate_text = AsyncMock(return_value=COLLAPSE_STORY)
    h.llm.generate = AsyncMock(side_effect=lambda *a, **kw: (StoryOutput(
        narration="档案中的龙文开始侵蚀你的意识。", sanity_delta=-10,
        current_location="旧档案室", options=["继续调查"],
    ), 1))
    return state


def ending_calls(h):
    return [call for call in h.llm.generate_text.await_args_list
            if call.kwargs.get("purpose") == "ending_narrative"]


@pytest.mark.parametrize("before,delta,after", [
    (10, -10, 0), (1, -1, 0), (10, -20, 0),
    (0, 0, 0), (0, 50, 0), (-1, 100, 0),
    (10, -9, 2), (80, 0, 81),
])
def test_zero_precedes_recovery_and_cannot_be_healed(tmp_path, before, delta, after):
    h = Harness(tmp_path)
    state = setup_run(h, sanity=before)
    result = h.state_manager.apply_output(state, "继续", StoryOutput(
        narration="你望向那本档案。", sanity_delta=delta,
    ))
    assert result["sanity"] == after
    assert state["sanity"] == before


@pytest.mark.asyncio
@pytest.mark.parametrize("arc,session,turn,total", [
    (0, 0, 3, 3), (1, 0, 9, 25), (2, 1, 9, 49),
])
async def test_zero_ends_this_turn_in_every_chapter(tmp_path, arc, session, turn, total):
    h = Harness(tmp_path)
    setup_run(h, arc=arc, session=session, turn=turn, total=total)

    response = await h.generate()
    await h.gen._wait_memory(h.session_id)

    assert response.state["sanity"] == 0
    assert response.state["health"] == 67
    assert response.output.game_over
    assert response.output.game_over_reason == "龙血失控"
    assert response.output.narration == COLLAPSE_STORY
    assert 180 <= len(response.output.narration) <= 260
    assert response.output.options == response.output.option_checks == []
    assert "死侍" in response.state["player_status"]["condition"]
    assert response.campaign_progress["turns_total"] == total + 1
    assert h.manager.progress.arc_index == arc
    assert h.manager.progress.session_index == session
    assert h.progress_row()["fsm_state"] == "campaign_end"
    node = h.db.get_story_turn(h.session_id, response.timeline_node_id)
    assert json.loads(node["output_json"])["narration"] == COLLAPSE_STORY
    prompt = ending_calls(h)[0].args[0]
    assert "旧档案室" in prompt and "抄写笔记" in prompt
    assert "档案中的龙文开始侵蚀你的意识" in prompt
    assert "临界血限" in prompt and "死侍" in prompt
    assert "镜像人格夺取玩家身份" not in prompt
    with pytest.raises(ConcurrentModificationError, match="already ended"):
        await h.generate()


@pytest.mark.asyncio
@pytest.mark.parametrize("turn,total", [(0, 0), (0, 15), (3, 20)])
async def test_existing_zero_bypasses_opening_and_normal_action(tmp_path, turn, total):
    h = Harness(tmp_path)
    setup_run(h, sanity=0, turn=turn, total=total)

    result = await h.gen.generate(h.session_id, GenerateRequest(player_action="休息并治疗血统失控"))
    await h.gen._wait_memory(h.session_id)

    assert result.output.game_over and result.state["sanity"] == 0
    assert result.state["current_location"] == "旧档案室"
    h.gen._handle_opening_scene.assert_not_awaited()
    h.gen._build_prompt.assert_not_awaited()
    h.llm.generate.assert_not_awaited()
    assert len(ending_calls(h)) == 1


@pytest.mark.asyncio
async def test_zero_bypasses_old_option_roll_and_cannot_be_saved_by_critical_success(tmp_path):
    h = Harness(tmp_path)
    setup_run(h, sanity=21)
    living = await h.generate()
    await h.gen._wait_memory(h.session_id)
    saved = h.state_manager.get_session_payload(h.session_id)
    state = saved["state"]
    state["sanity"] = 0
    h.state_manager.save_state(h.session_id, saved["game_name"], "test-model", state)
    preview = await resolve_action_check(
        "继续调查", state, {"options": ["继续调查"], "option_checks": [{"name": "侦查"}]}, 0,
    )
    assert preview.check is None
    h.llm.generate.reset_mock()
    result = await h.gen.generate(h.session_id, GenerateRequest(
        player_action="继续调查", timeline_node_id=living.timeline_node_id,
        action_check={"roll": 20, "option_index": 0},
    ))
    await h.gen._wait_memory(h.session_id)
    assert result.output.game_over and result.state["sanity"] == 0
    assert result.output.action_check is None
    h.llm.generate.assert_not_awaited()


def test_collapse_overrides_good_choice_budget_and_missing_routes(tmp_path):
    h = Harness(tmp_path)
    setup_run(h, sanity=0, arc=2, session=1, total=49)
    state = {"sanity": 0, "health": 50, "items": [{"name": "黄铜钥匙", "status": "owned"}]}
    for budget in (1, 50, 100):
        selected = select_budget_ending(h.manager.campaign, h.manager.progress, state, budget, "继承封印")
        assert selected.id == BLOODLINE_COLLAPSE_ENDING_ID
    h.manager.campaign.ending_routes = []
    h.manager.progress.arc_index = h.manager.progress.session_index = 0
    assert select_ending(h.manager.campaign, h.manager.progress, state, "继承封印").id == BLOODLINE_COLLAPSE_ENDING_ID
    assert select_bloodline_collapse_ending({"sanity": 1}) is None


@pytest.mark.asyncio
async def test_last_positive_point_can_recover_without_ending(tmp_path):
    h = Harness(tmp_path)
    setup_run(h, sanity=11)
    result = await h.generate()
    await h.gen._wait_memory(h.session_id)
    assert result.state["sanity"] == 2
    assert not result.output.game_over
    assert not ending_calls(h)


@pytest.mark.asyncio
async def test_collapse_retains_the_scene_and_cost_of_the_triggering_action(tmp_path):
    h = Harness(tmp_path)
    setup_run(h)
    h.llm.generate = AsyncMock(return_value=(StoryOutput(
        narration="你在地下书库读完龙文，抄写笔记被火焰吞没，意识开始崩溃。",
        sanity_delta=-10, current_location="地下书库",
        items_lost=[{"name": "抄写笔记", "status": "destroyed"}],
    ), 1))
    result = await h.generate()
    await h.gen._wait_memory(h.session_id)
    assert result.output.game_over
    assert result.state["current_location"] == "地下书库"
    assert not any(item["name"] == "抄写笔记" for item in result.state["items"])
    prompt = ending_calls(h)[0].args[0]
    assert '"current_location": "地下书库"' in prompt
    assert "抄写笔记被火焰吞没" in prompt


@pytest.mark.asyncio
async def test_failed_ending_keeps_positive_parent_and_retry_closes_once(tmp_path):
    h = Harness(tmp_path)
    before_state = setup_run(h)
    before_progress, before_head = h.progress_row(), h.head()
    h.llm.generate_text = AsyncMock(return_value="你失去了意识。")
    with pytest.raises(ScenarioGenerationError):
        await h.generate()
    assert h.state_manager.get_session_payload(h.session_id)["state"] == before_state
    assert h.progress_row() == before_progress
    assert h.node_count() == 1 and h.head() == before_head

    h.llm.generate_text = AsyncMock(return_value=COLLAPSE_STORY)
    result = await h.generate()
    await h.gen._wait_memory(h.session_id)
    assert result.output.game_over and result.state["sanity"] == 0
    assert h.node_count() == 2 and result.campaign_progress["turns_total"] == 4


@pytest.mark.asyncio
async def test_correction_addresses_length_and_missing_collapse_together(tmp_path):
    h = Harness(tmp_path)
    setup_run(h)
    h.llm.generate_text = AsyncMock(side_effect=["你暂时失去意识。", COLLAPSE_STORY])
    result = await h.generate()
    await h.gen._wait_memory(h.session_id)
    calls = ending_calls(h)
    assert result.output.game_over and len(calls) == 2
    assert "需要 180–260 字" in calls[1].args[0]
    assert "成为死侍" in calls[1].args[0]


@pytest.mark.asyncio
async def test_restoring_pre_collapse_node_restores_living_state(tmp_path):
    h = Harness(tmp_path)
    setup_run(h, sanity=21)
    living = await h.generate()
    assert living.state["sanity"] == 12
    h.llm.generate = AsyncMock(return_value=(StoryOutput(
        narration="龙文再次响起。", sanity_delta=-12,
    ), 1))
    ended = await h.generate()
    await h.gen._wait_memory(h.session_id)
    assert ended.output.game_over

    h.db.activate_story_turn(h.session_id, living.timeline_node_id)
    h.manager.reload_runtime_state()
    h.gen.invalidate_timeline_caches(h.session_id, "default")
    h.llm.generate = AsyncMock(return_value=(StoryOutput(narration="你合上档案。"), 1))
    continued = await h.generate()
    await h.gen._wait_memory(h.session_id)
    assert continued.state["sanity"] == 13
    assert not continued.output.game_over
