"""Verified dice results survive the real pipeline, prompts, and timeline commit."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.exceptions import ConcurrentModificationError
from app.schemas import ActionCheckResult, ActionCheckSubmission, GenerateRequest, OptionCheck, StoryOutput
from app.schemas.campaign import EndingRoute
from app.services.action_checks import ActionCheckError
from tests.test_turn_commit_consistency import Harness


def _set_narrator(h, **overrides):
    fields = dict(narration="门后传来脚步声，你记住了档案柜上的编号。", options=["等待"])
    fields.update(overrides)
    h.llm.generate = AsyncMock(side_effect=lambda *a, **k: (StoryOutput(**fields), 5))


async def _open_checked_scene(tmp_path, checked_action="搜索档案"):
    h = Harness(tmp_path)
    h.gen._build_prompt = AsyncMock(side_effect=lambda *a: (
        "当前场景：档案室。", SimpleNamespace(sections={}, final_prompt="", temperature=0.7), [], [], 0,
    ))
    _set_narrator(
        h, options=[checked_action, "观察门"],
        option_checks=[OptionCheck(name="档案检定", skill="侦查", difficulty="困难"), None],
    )
    opened = await h.gen.generate(h.session_id, GenerateRequest(player_action="进入大厅"))
    await h.gen._wait_memory(h.session_id)
    assert opened.output.action_check is None
    assert opened.output.option_checks[0].target == 16
    _set_narrator(h)
    h.llm.generate_json.reset_mock()
    h.llm.generate_text.reset_mock()
    h.gen._run_director_stage = AsyncMock(wraps=h.gen._run_director_stage)
    return h, opened.timeline_node_id


def _request(node, roll=None, action="搜索档案", index=0):
    return GenerateRequest(
        player_action=action, timeline_node_id=node,
        action_check=ActionCheckSubmission(roll=roll, option_index=index) if roll is not None else None,
    )


def _model_forgery():
    return ActionCheckResult(
        check=OptionCheck(name="伪造的模型检定", difficulty="容易"),
        roll=20, option_index=99, outcome="critical", degree="大成功",
    )


def _saved_output(h, response):
    return json.loads(h.db.get_story_turn(h.session_id, response.timeline_node_id)["output_json"])


@pytest.mark.asyncio
@pytest.mark.parametrize("roll,outcome,degree", [
    (1, "fumble", "大失败"), (11, "failure", "失败"),
    (16, "success", "成功"), (20, "critical", "大成功"),
])
async def test_resolved_check_reaches_director_narrator_and_saved_timeline(tmp_path, roll, outcome, degree):
    h, node = await _open_checked_scene(tmp_path)
    _set_narrator(h, action_check=_model_forgery())

    response = await h.gen.generate(h.session_id, _request(node, roll))
    await h.gen._wait_memory(h.session_id)

    result = response.output.action_check
    assert (result.roll, result.outcome, result.degree) == (roll, outcome, degree)
    assert result.option_index == 0
    assert result.check.target == 16
    assert result.check.name == "档案检定"
    assert _saved_output(h, response)["action_check"] == result.model_dump()
    model_output = h.db.get_model_output(response.model_output_id)
    assert json.loads(model_output["output_json"])["action_check"] == result.model_dump()

    ruling = h.gen._run_director_stage.await_args.args[2]
    assert ruling.permissibility.value == "permissible"
    assert f"骰面 {roll}/20，结果：{degree}" in ruling.constraints
    assert "未进行掷骰" not in ruling.constraints
    for rule in ruling.triggered_rules:
        if rule.rule_type == "skill_check":
            assert f"骰面 {roll}/20，结果：{degree}" in rule.rule_details
            assert "未进行掷骰" not in rule.rule_details
    director_prompt = next(
        call.kwargs["prompt"] for call in h.llm.generate_json.await_args_list
        if call.kwargs.get("purpose") == "campaign_director"
    )
    assert "- 可行性：permissible" in director_prompt
    assert f"骰面 {roll}/20，结果：{degree}" in director_prompt

    narrator_prompt = h.llm.generate.await_args.args[0]
    assert "[已结算行动判定]" in narrator_prompt
    assert f"骰面 {roll}/20，结果：{degree}" in narrator_prompt
    assert "未进行掷骰" not in narrator_prompt
    assert model_output["prompt_text"] == narrator_prompt
    assert f"结果：{degree}" in json.loads(model_output["prompt_sections_json"])["action_check"]
    if outcome in {"fumble", "failure"}:
        assert "不得把原行动写成成功" in narrator_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,error", [
    ("missing_roll", ActionCheckError), ("stale_node", ConcurrentModificationError),
    ("unbound_roll", ActionCheckError),
])
async def test_rejected_check_requests_do_not_advance_or_call_models(tmp_path, kind, error):
    h, node = await _open_checked_scene(tmp_path)
    before_state = h.state_manager.get_session_payload(h.session_id)
    before_progress = h.progress_row()
    before_nodes = h.db.list_story_turns(h.session_id)
    request = _request(node, 16)
    if kind == "missing_roll":
        request.action_check = None
    elif kind == "stale_node":
        request.timeline_node_id = node - 1
    else:
        request.timeline_node_id = None

    with pytest.raises(error):
        await h.gen.generate(h.session_id, request)

    assert h.state_manager.get_session_payload(h.session_id) == before_state
    assert h.progress_row() == before_progress
    assert h.db.list_story_turns(h.session_id) == before_nodes
    h.llm.generate.assert_not_awaited()
    h.llm.generate_json.assert_not_awaited()
    h.llm.generate_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_null_option_removes_pending_check_and_model_forgery(tmp_path):
    h, node = await _open_checked_scene(tmp_path)
    _set_narrator(h, action_check=_model_forgery())

    response = await h.gen.generate(h.session_id, _request(node, action="观察门"))
    await h.gen._wait_memory(h.session_id)

    ruling = h.gen._run_director_stage.await_args.args[2]
    assert ruling.permissibility.value == "permissible"
    assert not any(rule.rule_type == "skill_check" for rule in ruling.triggered_rules)
    assert "无需掷骰" in ruling.constraints
    narrator_prompt = h.llm.generate.await_args.args[0]
    assert "无需掷骰" in narrator_prompt
    assert "未进行掷骰" not in narrator_prompt
    assert "[已结算行动判定]" not in narrator_prompt
    assert response.output.action_check is None
    assert _saved_output(h, response)["action_check"] is None


@pytest.mark.asyncio
async def test_duplicate_option_text_uses_explicit_index_for_direct_action(tmp_path):
    h = Harness(tmp_path)
    _set_narrator(
        h, options=["观察门", "观察门"],
        option_checks=[OptionCheck(difficulty="困难"), None],
    )
    opened = await h.gen.generate(h.session_id, GenerateRequest(player_action="进入大厅"))
    await h.gen._wait_memory(h.session_id)
    _set_narrator(h)

    response = await h.gen.generate(h.session_id, GenerateRequest(
        player_action="观察门", timeline_node_id=opened.timeline_node_id, option_index=1,
    ))
    await h.gen._wait_memory(h.session_id)

    assert response.output.action_check is None
    assert _saved_output(h, response)["action_check"] is None
    assert response.parent_timeline_node_id == opened.timeline_node_id


@pytest.mark.asyncio
@pytest.mark.parametrize("action,skill", [("释放言灵", "血统稳定"), ("攻击木门", "战斗")])
async def test_custom_action_result_replaces_pending_sanity_and_combat_rules(tmp_path, action, skill):
    h, node = await _open_checked_scene(tmp_path)

    response = await h.gen.generate(h.session_id, _request(node, 11, action=action, index=None))
    await h.gen._wait_memory(h.session_id)

    result = response.output.action_check
    assert result.option_index is None
    assert result.check.skill == skill
    assert result.check.target == 12
    assert result.outcome == "failure"
    prompt = h.llm.generate.await_args.args[0]
    assert "通用 d20，1d20 ≥ 12，骰面 11/20，结果：失败" in prompt
    assert "1d100" not in prompt
    assert "未进行掷骰" not in prompt
    assert _saved_output(h, response)["action_check"] == result.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize("roll,ends", [(11, False), (16, True)])
async def test_failed_check_cannot_activate_success_ending_phrase(tmp_path, roll, ends):
    action = "搜索档案，然后决定关闭封印"
    h, node = await _open_checked_scene(tmp_path, checked_action=action)
    h.manager.campaign.ending_routes = [EndingRoute(
        id="sealed", name="封印已闭合", category="good", requirements=[],
        trigger_phrases=["关闭封印"], resolution="封印稳定下来，众人安全离开。",
    )]
    h.manager.progress.arc_index = len(h.manager.campaign.arcs) - 1
    h.manager.progress.session_index = len(h.manager.campaign.arcs[-1].sessions) - 1
    h.manager.progress.turn_in_session = 3
    h.manager.progress.turns_total = 36
    h.manager.save_progress()

    response = await h.gen.generate(h.session_id, _request(node, roll, action=action))
    await h.gen._wait_memory(h.session_id)

    assert response.output.game_over is ends
    assert response.output.action_check.roll == roll
    if ends:
        assert response.output.game_over_reason == "封印已闭合"
        ending_call, = [call for call in h.llm.generate_text.await_args_list
                       if call.kwargs.get("purpose") == "ending_narrative"]
        assert "骰面 16/20，结果：成功" in ending_call.args[0]
    else:
        assert response.output.game_over_reason == ""
        assert not any(call.kwargs.get("purpose") == "ending_narrative"
                       for call in h.llm.generate_text.await_args_list)


@pytest.mark.asyncio
async def test_budget_ending_rewrite_carries_failure_result_and_saved_consequence(tmp_path):
    h, node = await _open_checked_scene(tmp_path)
    h.manager.progress.turns_total = h.manager.resolve_max_turns_per_campaign() - 1
    h.manager.progress.turn_in_session = 4
    h.manager.save_progress()

    response = await h.gen.generate(h.session_id, _request(node, 1))
    await h.gen._wait_memory(h.session_id)

    assert response.output.game_over
    assert response.output.action_check.outcome == "fumble"
    ending_call, = [call for call in h.llm.generate_text.await_args_list
                   if call.kwargs.get("purpose") == "ending_narrative"]
    prompt = ending_call.args[0]
    assert "骰面 1/20，结果：大失败" in prompt
    assert "不得把原行动写成成功" in prompt
    material = json.loads(prompt.split("[STORY_MATERIAL_START]\n", 1)[1].split("\n[STORY_MATERIAL_END]", 1)[0])
    assert material["已结算行动判定"] == response.output.action_check.model_dump()
    assert _saved_output(h, response)["action_check"] == response.output.action_check.model_dump()


@pytest.mark.asyncio
async def test_transition_requires_saved_hard_check_even_when_old_scene_blocks_action(tmp_path):
    action = "在档案室搜索记录"
    h, node = await _open_checked_scene(tmp_path, checked_action=action)
    h.manager.progress.session_index = 1
    h.manager.progress.turn_in_session = 0
    h.manager.progress.turns_total = 1
    h.manager.campaign.arcs[0].sessions[1].entry_state = {"location": "档案室"}
    h.manager.save_progress()
    del h.gen._handle_opening_scene
    before = h.state_manager.get_session_payload(h.session_id)
    assert before["state"]["current_location"] != "档案室"

    with pytest.raises(ActionCheckError, match="先完成掷骰"):
        await h.gen.generate(h.session_id, _request(node, action=action))

    assert h.head() == node
    assert h.state_manager.get_session_payload(h.session_id) == before
    h.llm.generate.assert_not_awaited()
    h.llm.generate_json.assert_not_awaited()

    response = await h.gen.generate(h.session_id, _request(node, 16, action=action))
    await h.gen._wait_memory(h.session_id)

    assert response.source == "llm"
    assert response.state["current_location"] == "档案室"
    assert response.output.action_check.roll == 16
    assert response.output.action_check.check.target == 16
    assert response.output.action_check.outcome == "success"
    assert "骰面 16/20，结果：成功" in h.llm.generate.await_args.args[0]
    assert _saved_output(h, response)["action_check"] == response.output.action_check.model_dump()
