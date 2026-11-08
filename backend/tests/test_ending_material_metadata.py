"""Ending prompts preserve narrative facts without database row metadata."""

from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.schemas import GenerateRequest, StoryOutput
from app.schemas.campaign import EndingRoute
from app.schemas.game.action_checks import ActionCheckResult, OptionCheck
from app.services.scenario_generator.check_guidance import check_instruction
from app.services.scenario_generator.ending_narrative import (
    EndingNarrativeMixin,
    ending_narrative_issue,
)


ENDING_PROSE = (
    "你把旧信折好，放回那只被雨水浸湿的衣袋，门外已经没有人等候。"
    "走廊尽头的灯忽明忽暗，照着墙边留下的泥印，也照着你缠住手腕的布条。"
    "你没有再碰那扇紧闭的门，只记住同伴离开时说过的话，将钥匙轻轻握在掌心。"
    "窗外传来清晨第一阵钟声，惊起停在檐角的鸟，灰色天空终于露出了一线微光。"
    "许多问题仍没有答案，但你知道那些已经发生的事情，不会随着天亮而消失。"
    "你沿着来时的台阶慢慢走下去，衣袋里的信纸贴着胸口，像一段尚未说完的告别。"
)


@pytest.mark.asyncio
@pytest.mark.parametrize("force_rewrite", [False, True])
async def test_ending_material_excludes_row_metadata_and_preserves_settled_facts(force_rewrite):
    assert ending_narrative_issue(ENDING_PROSE) == ""
    messages = [
        {"id": 81, "role": "user", "content": "  我收好旧信。\n保留这里的换行与空格。  ",
         "created_at": "2026-11-06T01:02:03Z", "session_id": "storage-session-only",
         "campaign_session_index": 4, "turn_node_id": 19},
        {"id": 82, "role": "assistant", "content": "你握紧钥匙，门仍然关着。",
         "created_at": "2026-11-06T01:02:05Z", "session_id": "storage-session-only",
         "campaign_session_index": 4, "turn_node_id": 20},
    ]
    messages_before = deepcopy(messages)
    state = {
        "current_location": "旧档案室", "health": 63, "sanity": 42,
        "player_status": {"condition": "手腕受伤", "danger_level": "low", "current_goal": "离开档案室"},
        "items": [{"name": "黄铜钥匙", "status": "owned"}],
        "npcs": [{"name": "诺诺", "status": "alive"}],
        "quests": [{"name": "追查旧信", "status": "active"}],
        "world_facts": [{"name": "档案室的门", "description": "门锁已经更换"}],
        "recent_events": ["交涉失败，同伴没有透露线索"], "turn": 42,
    }
    state_before = deepcopy(state)
    check = ActionCheckResult(
        check=OptionCheck(name="交涉检定", difficulty="困难", stakes="失败则对方保持沉默。"),
        roll=3, option_index=1, outcome="failure", degree="失败",
    )
    request = GenerateRequest(player_action="收好旧信，离开档案室")
    request._resolved_action_check = check
    output = StoryOutput(
        narration="你收好信，离开了。", current_location="旧档案室",
        dialogue=[{"speaker": "诺诺", "text": "别忘记那封信。"}],
        health_delta=-7, sanity_delta=-3, items_lost=[{"name": "用过的绷带"}],
        items_gained=[{"name": "黄铜钥匙", "status": "owned"}], action_check=check,
        game_over=True, game_over_reason="未竟的追寻",
    )
    output_before = output.model_dump()
    route = EndingRoute(id="ending-unfinished-test", name="未竟的追寻", resolution="你带着旧信离开，疑问仍未解开。")
    generator = EndingNarrativeMixin()
    generator.db = SimpleNamespace(get_recent_messages=Mock(return_value=messages))
    generator.llm_client = SimpleNamespace(generate_text=AsyncMock(return_value=ENDING_PROSE))
    generator._store_error = Mock(side_effect=AssertionError("valid prose must not enter error storage"))
    meta = SimpleNamespace(sections={})
    recap = "此前在礼堂找到旧信。"
    collapse_trigger = {"本回合原叙事草稿": "你握住门把手。", "血统稳定损失": -3, "血条变化": -7}

    await generator._ensure_ending_narrative(
        output, route, force_rewrite=force_rewrite, session_id="test-session", request=request,
        model="test-model", state=state,
        campaign_manager=SimpleNamespace(_load_recap_compressed=lambda: recap), meta=meta,
        retrieved_for_storage=[], campaign_session_index=4, collapse_trigger=collapse_trigger,
    )

    generator.db.get_recent_messages.assert_called_once_with("test-session", limit=4, campaign_session_index=4)
    generator.llm_client.generate_text.assert_awaited_once()
    call = generator.llm_client.generate_text.await_args
    prompt = call.args[0]
    material = json.loads(prompt.split("[STORY_MATERIAL_START]\n", 1)[1].split("\n[STORY_MATERIAL_END]", 1)[0])
    assert material["最近剧情"] == [{"role": row["role"], "content": row["content"]} for row in messages_before]
    for field in ("created_at", "id", "session_id", "campaign_session_index", "turn_node_id"):
        assert all(field not in row for row in material["最近剧情"])
        assert '"' + field + '"' not in prompt
    assert "2026-11-06T01:02:03Z" not in prompt
    assert "storage-session-only" not in prompt
    assert messages == messages_before
    assert state == state_before
    assert material["当前状态"] == {key: value for key, value in state_before.items() if key != "turn"}
    assert material["已结算行动判定"] == check.model_dump()
    assert check_instruction(check) in prompt
    assert material["玩家最后的行动"] == request.player_action
    assert material["前情回顾"] == recap
    assert material["失控缘由参考"] == collapse_trigger
    assert material["待改写正文"] == ("" if force_rewrite else output_before["narration"])
    assert material["本回合对话"] == ([] if force_rewrite else output_before["dialogue"])
    assert call.kwargs == {"model": "test-model", "max_tokens": 1200, "temperature": 0.35,
                           "purpose": "ending_narrative",
                           "context": {"session_id": "test-session", "turn": 42, "ending_id": route.id}}
    assert meta.sections["ending_narrative"] == prompt
    assert output.narration == ENDING_PROSE
    assert output.dialogue == []
    assert output.model_dump(exclude={"narration", "dialogue"}) == {
        key: value for key, value in output_before.items() if key not in {"narration", "dialogue"}
    }
