"""Ending prose is a complete, contextual story before the turn can commit.

Exercise the real generate/finalize path with a real database and campaign.
Only model responses and prompt construction use the shared offline harness.
"""

import json
from unittest.mock import AsyncMock

import pytest

from app.schemas import GenerateRequest, StoryOutput
from app.services.llm_client import LLMRequestError
from app.services.scenario_generator.errors import ScenarioGenerationError
from tests.test_turn_commit_consistency import ENDING_STORY, Harness


def _set_state(h, **changes):
    session = h.state_manager.get_session_payload(h.session_id)
    state = session["state"]
    state.update(changes)
    h.state_manager.save_state(h.session_id, session["game_name"], "test-model", state)
    return state


def _set_narrator(h, narration="你离开了这里。", **changes):
    fields = dict(narration=narration, current_location="旧档案室", options=["继续调查"])
    fields.update(changes)
    # A fresh output is needed on a failed turn's retry: generation may mutate it.
    h.llm.generate = AsyncMock(side_effect=lambda *a, **k: (StoryOutput(**fields), 5))


def _stage_budget(h, *, has_clue=True):
    h.manager.progress.turns_total = h.manager.resolve_max_turns_per_campaign() - 1
    h.manager.progress.turn_in_session = 4
    h.manager.progress.revealed_anchors = ["anchor-invitation"] if has_clue else []
    h.manager.save_progress()


def _stage_finale(h):
    h.manager.progress.arc_index = 2
    h.manager.progress.session_index = 1
    h.manager.progress.turn_in_session = 3
    h.manager.progress.turns_total = 36
    h.manager.save_progress()
    _set_state(h, current_location="钟楼地下封印室",
               items=[{"name": "黄铜钥匙", "status": "owned"}])


def _ending_calls(h):
    return [call for call in h.llm.generate_text.await_args_list
            if call.kwargs.get("purpose") == "ending_narrative"]


def _assert_story_ending(response, title):
    assert response.output.game_over is True
    assert response.output.game_over_reason == title
    assert 180 <= len("".join(response.output.narration.split())) <= 260
    assert response.output.options == response.output.option_checks == response.output.dialogue == []
    for forbidden in ("回合预算耗尽", "这一局到此结束", "game_over", "血条", "生命值", "稳定度"):
        assert forbidden not in response.output.narration


@pytest.mark.asyncio
@pytest.mark.parametrize("has_clue,title", [(True, "未竟的追寻"), (False, "无声的终章")])
async def test_unfinished_and_failed_runs_write_current_story_then_commit(tmp_path, has_clue, title):
    h = Harness(tmp_path)
    _stage_budget(h, has_clue=has_clue)
    _set_state(h, current_location="旧档案室", health=63, sanity=42,
               recent_events=["门锁已经被学院的人更换"],
               quests=[{"name": "寻找失踪者", "status": "active"}],
               world_facts=[{"name": "蓝色封蜡", "description": "信封尚未拆开", "status": "known"}])
    h.db.add_message(h.session_id, "assistant", "走廊中只剩下陈旧唱片的声音。")
    h.manager.store_recap("此前在礼堂发现了半张旧照片。")
    _set_narrator(h)
    action = "将那封没有寄出的信收好，然后离开档案室"

    response = await h.gen.generate(h.session_id, GenerateRequest(player_action=action))

    _assert_story_ending(response, title)
    assert response.output.narration == ENDING_STORY
    assert response.state["health"] == 63
    assert response.output.sanity_delta == 0
    assert response.state["sanity"] == 43  # Existing per-turn passive recovery.
    assert response.campaign_progress["turns_total"] == 50
    assert h.progress_row()["fsm_state"] == "campaign_end"
    call, = _ending_calls(h)
    prompt = call.args[0]
    for evidence in ("旧档案室", "蓝色封蜡", "门锁已经被学院的人更换", "寻找失踪者",
                     "陈旧唱片", "半张旧照片", action):
        assert evidence in prompt
    assert call.kwargs["context"]["session_id"] == h.session_id
    assert "180" in prompt and "260" in prompt
    assert "空座位" not in prompt and "镜像人格夺取玩家身份" not in prompt
    committed = h.db.get_story_turn(h.session_id, response.timeline_node_id)
    assert json.loads(committed["output_json"])["narration"] == ENDING_STORY


@pytest.mark.asyncio
async def test_regular_ending_rewrite_retains_authorized_state_changes(tmp_path):
    h = Harness(tmp_path)
    _stage_finale(h)
    _set_narrator(h, health_delta=-7, sanity_delta=-3,
                  current_location="钟楼地下封印室",
                  items_gained=[{"name": "烧焦的封印碎片", "status": "owned"}],
                  dialogue=[{"speaker": "诺诺", "text": "这是不应重复显示的额外尾声。"}],
                  option_checks=[{"name": "继续检定"}])
    before = h.state_manager.get_session_payload(h.session_id)["state"]

    response = await h.gen.generate(h.session_id, GenerateRequest(player_action="我选择继承封印"))

    _assert_story_ending(response, "钟楼守望者")
    assert response.state["health"] == before["health"] - 7
    assert response.state["sanity"] == before["sanity"] - 3 + 1
    assert any(item["name"] == "烧焦的封印碎片" for item in response.state["items"])
    call, = _ending_calls(h)
    route = next(route for route in h.manager.campaign.ending_routes if route.name == "钟楼守望者")
    assert route.resolution in call.args[0] and route.epilogue in call.args[0]
    assert "破晓共犯" not in call.args[0]


@pytest.mark.asyncio
async def test_valid_existing_ending_does_not_request_another_story(tmp_path):
    h = Harness(tmp_path)
    _stage_budget(h)
    _set_narrator(h, ENDING_STORY)

    response = await h.generate()

    _assert_story_ending(response, "未竟的追寻")
    assert response.output.narration == ENDING_STORY
    assert _ending_calls(h) == []


@pytest.mark.asyncio
async def test_valid_narration_with_dialogue_merges_farewell_into_story(tmp_path):
    h = Harness(tmp_path)
    _stage_budget(h)
    farewell = "不要忘记我们来过这里。"
    _set_narrator(h, ENDING_STORY,
                  dialogue=[{"speaker": "诺诺", "text": farewell}])
    merged = ENDING_STORY.replace("你没有再去敲", f"诺诺说：‘{farewell}’你没有再去敲")
    h.llm.generate_text = AsyncMock(return_value=merged)

    response = await h.generate()

    _assert_story_ending(response, "未竟的追寻")
    assert farewell in response.output.narration
    call, = _ending_calls(h)
    assert farewell in call.args[0] and "诺诺" in call.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("narration", [
    "调查到这里暂时告一段落。",
    ENDING_STORY + ENDING_STORY,
    ENDING_STORY + "回合预算耗尽。",
    ENDING_STORY + "这一局到此结束。",
    ENDING_STORY + "game_over=true。",
    ENDING_STORY + "血条在视野边缘掉了一截，79变成71。",
    ENDING_STORY + "生命值从79降到了71。",
    ENDING_STORY + "稳定度归零了。",
    '{"narration": "' + ENDING_STORY + '"}',
    "```\n" + ENDING_STORY + "\n```",
    "# 结局\n" + ENDING_STORY,
    "以下是为你写的结局：" + ENDING_STORY,
    "根据你的要求，" + ENDING_STORY,
])
async def test_short_overlong_or_system_style_ending_is_rewritten(tmp_path, narration):
    h = Harness(tmp_path)
    _stage_budget(h)
    _set_narrator(h, narration)

    response = await h.generate()

    _assert_story_ending(response, "未竟的追寻")
    assert response.output.narration == ENDING_STORY
    assert len(_ending_calls(h)) == 1


@pytest.mark.asyncio
async def test_route_changed_by_lethal_output_rewrites_even_long_initial_story(tmp_path):
    h = Harness(tmp_path)
    _stage_finale(h)
    _set_narrator(h, ENDING_STORY, health_delta=-100,
                  items_gained=[{"name": "错误路线奖励", "status": "owned"}],
                  memory_updates={"world_facts_upserted": [{"name": "错误好结局事实"}]},
                  npc_relations_delta=[{"name": "诺诺", "delta": 5}])
    replacement = ENDING_STORY.replace("你把湿透的笔记收进衣袋", "镜中的陌生人收起了笔记")
    h.llm.generate_text = AsyncMock(return_value=replacement)

    response = await h.gen.generate(h.session_id, GenerateRequest(player_action="继承封印"))

    _assert_story_ending(response, "空座位")
    assert response.output.narration == replacement
    assert response.state["health"] == 0
    assert not any(item["name"] == "错误路线奖励" for item in response.state["items"])
    assert not any(fact["name"] == "错误好结局事实" for fact in response.state["world_facts"])
    assert response.output.npc_relations_delta is None
    call, = _ending_calls(h)
    route = next(route for route in h.manager.campaign.ending_routes if route.name == "空座位")
    assert route.resolution in call.args[0] and route.epilogue in call.args[0]
    assert "错误路线奖励" not in call.args[0]


@pytest.mark.asyncio
async def test_invalid_rewrite_gets_one_corrective_attempt(tmp_path):
    h = Harness(tmp_path)
    _stage_budget(h)
    _set_narrator(h)
    h.llm.generate_text = AsyncMock(side_effect=["你离开了这里。", ENDING_STORY])

    response = await h.generate()

    _assert_story_ending(response, "未竟的追寻")
    assert len(_ending_calls(h)) == 2
    assert h.node_count() == 2
    assert h.progress_row()["turns_total"] == 50


@pytest.mark.asyncio
async def test_numeric_hud_in_auxiliary_ending_is_rewritten_before_commit(tmp_path):
    h = Harness(tmp_path)
    _stage_budget(h)
    _set_narrator(h)
    h.llm.generate_text = AsyncMock(side_effect=[
        ENDING_STORY + "血条在视野边缘掉了一截，79变成71。", ENDING_STORY,
    ])

    response = await h.generate()

    _assert_story_ending(response, "未竟的追寻")
    assert len(_ending_calls(h)) == 2
    assert "具体伤势" in _ending_calls(h)[1].args[0]
    committed = h.db.get_story_turn(h.session_id, response.timeline_node_id)
    assert json.loads(committed["output_json"])["narration"] == ENDING_STORY


@pytest.mark.asyncio
@pytest.mark.parametrize("responses", [
    ["过短的结局。", "回合预算耗尽。"],
    [LLMRequestError("unavailable", 503, "temporarily unavailable", 1)] * 2,
])
async def test_ending_generation_failure_rolls_back_and_retry_advances_once(tmp_path, responses):
    h = Harness(tmp_path)
    _stage_budget(h)
    h.stage_pending_anchor()
    _set_narrator(h, health_delta=-9,
                  items_gained=[{"name": "尚未提交的物品", "status": "owned"}])
    h.llm.generate_text = AsyncMock(side_effect=responses)
    before_state = h.state_manager.get_session_payload(h.session_id)["state"]
    before_progress = h.progress_row()
    root = h.head()

    with pytest.raises(ScenarioGenerationError):
        await h.generate()

    assert h.head() == root and h.node_count() == 1
    assert h.state_manager.get_session_payload(h.session_id)["state"] == before_state
    assert h.progress_row() == before_progress
    assert h.manager.progress.turns_total == 49
    assert "dynamic-test-anchor" not in h.manager.progress.revealed_anchors
    assert str(h.manager.fsm.state) != "campaign_end"
    assert 1 <= len(_ending_calls(h)) <= 2

    h.llm.generate_text = AsyncMock(return_value=ENDING_STORY)
    response = await h.generate()
    _assert_story_ending(response, "未竟的追寻")
    assert h.head() == response.timeline_node_id and h.node_count() == 2
    assert h.progress_row()["turns_total"] == 50
    assert response.state["health"] == before_state["health"] - 9


@pytest.mark.asyncio
async def test_non_ending_short_turn_stays_ordinary_prose(tmp_path):
    h = Harness(tmp_path)
    _set_narrator(h, "你推开了那扇门。")

    response = await h.generate()

    assert not response.output.game_over
    assert response.output.narration == "你推开了那扇门。"
    assert response.output.options == ["继续调查"]
    assert _ending_calls(h) == []
