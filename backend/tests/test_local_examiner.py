"""Behavior and pipeline regressions for the network-free rule checker."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas import StoryOutput
from app.services.agents.examiner import ExaminerAgent
from app.services.scenario_generator.agent_pipeline import AgentPipelineMixin
from app.services.scenario_generator.post_generation import PostGenerationMixin
from app.services.game_state import GameStateManager


@pytest.fixture
def state():
    return {
        "current_location": "大厅", "health": 20, "sanity": 30,
        "items": [{"name": "钥匙", "status": "owned"}],
        "npcs": [{"name": "诺诺", "status": "present", "current_location": "大厅"}],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("action, verdict, rule", [
    ("用钥匙打开门", "permissible", "item_use"),
    ("使用手电筒照亮房间", "blocked", None),
    ("寻找手电筒", "permissible", None),
    ("向诺诺询问档案", "permissible", None),
    ("询问诺诺学院情况", "permissible", None),
    ("与诺诺交谈", "permissible", None),
    ("与路明非交谈", "blocked", None),
    ("在图书馆搜索档案", "blocked", "skill_check"),
    ("在大厅里搜索档案", "conditional", "skill_check"),
    ("前往图书馆，在图书馆搜索档案", "conditional", "skill_check"),
    ("使用言灵·君焰", "conditional", "sanity_check"),
    ("前往图书馆", "permissible", None),
    ("攻击诺诺", "conditional", "combat"),
    ("攻击木门", "conditional", "combat"),
    ("侦查四周", "conditional", "skill_check"),
    ("直视神话生物", "conditional", "sanity_check"),
    ("使用言灵", "conditional", "sanity_check"),
    ("不攻击诺诺", "permissible", None),
    ("不用钥匙开门", "permissible", None),
    ("用力推门", "permissible", None),
    ("不攻击诺诺，而是观察四周", "conditional", "skill_check"),
    ("继续", "permissible", None),
])
async def test_actions(state, action, verdict, rule):
    before = deepcopy(state)
    ruling = await ExaminerAgent().examine(action, state, ["SAN检定、技能检定和战斗规则"])
    assert ruling.permissibility.value == verdict
    if rule:
        assert rule in {r.rule_type for r in ruling.triggered_rules}
    else:
        assert not ruling.triggered_rules
    if verdict == "blocked":
        assert ruling.rejection_reason
    assert state == before


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["lost", "consumed", "destroyed", "dropped"])
async def test_unusable_item(state, status):
    state["items"][0]["status"] = status
    assert (await ExaminerAgent().examine("用钥匙开门", state)).permissibility.value == "blocked"


@pytest.mark.asyncio
@pytest.mark.parametrize("status, location, verdict", [
    ("away", "大厅", "blocked"), ("dead", "大厅", "blocked"),
    ("present", "图书馆", "blocked"), ("following", "图书馆", "permissible"),
])
async def test_npc_presence(state, status, location, verdict):
    state["npcs"][0].update(status=status, current_location=location)
    assert (await ExaminerAgent().examine("与诺诺交谈", state)).permissibility.value == verdict


@pytest.mark.asyncio
@pytest.mark.parametrize("field, action, value, verdict", [
    ("health", "奔跑", 0, "blocked"), ("health", "奔跑", 1, "conditional"),
    ("sanity", "发动言灵", 0, "blocked"), ("sanity", "发动言灵", 1, "conditional"),
    ("health", "休息", 0, "permissible"), ("sanity", "休息", 0, "permissible"),
    ("health", "继续", 0, "permissible"), ("sanity", "继续", 0, "permissible"),
])
async def test_resource_boundary(state, field, action, value, verdict):
    state[field] = value
    assert (await ExaminerAgent().examine(action, state)).permissibility.value == verdict


@pytest.mark.asyncio
async def test_blocked_action_never_reaches_llm(state):
    pipeline = AgentPipelineMixin()
    pipeline.llm_client = SimpleNamespace(generate=AsyncMock(), generate_json=AsyncMock())
    output, latency, source = await pipeline._execute_llm_or_scripted(
        "session", SimpleNamespace(player_action="使用手电筒"), "prompt", "model", None, [], 0,
        state=state, campaign_manager=SimpleNamespace(is_loaded=lambda: True),
    )
    assert source == "examiner_blocked"
    assert latency == 0
    assert output.health_delta == output.sanity_delta == 0
    pipeline.llm_client.generate.assert_not_awaited()
    pipeline.llm_client.generate_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_ruling_reaches_director_without_json_call(state):
    pipeline = AgentPipelineMixin()
    pipeline.llm_client = SimpleNamespace(generate_json=AsyncMock())
    pipeline._run_director_stage = AsyncMock(return_value="direction")
    pipeline._inject_direction = lambda prompt, direction, ruling: prompt
    pipeline._run_narrator_stage = AsyncMock(return_value=(StoryOutput(narration="回应"), 1, "llm"))
    await pipeline._execute_llm_or_scripted(
        "session", SimpleNamespace(player_action="攻击诺诺"), "prompt", "model", None, [], 0,
        state=state, campaign_manager=SimpleNamespace(is_loaded=lambda: True),
    )
    ruling = pipeline._run_director_stage.await_args.args[2]
    assert ruling.permissibility.value == "conditional"
    assert ruling.triggered_rules[0].rule_type == "combat"
    pipeline.llm_client.generate_json.assert_not_awaited()
    pipeline._run_narrator_stage.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("turn", [4, 9, 14])
async def test_no_periodic_fact_request_and_narrator_facts_preserved(state, turn):
    output = StoryOutput(narration="发现事实", memory_updates={
        "world_facts_upserted": [{"name": "密道", "description": "大厅后有密道"}],
    })
    manager = GameStateManager(None)
    next_state = manager.apply_output(state, "观察", output)
    campaign = SimpleNamespace(is_loaded=lambda: True, progress=SimpleNamespace(turn_in_session=turn),
                               extract_facts=AsyncMock(side_effect=AssertionError("No standalone API")))
    result = await PostGenerationMixin()._apply_post_generation(output, next_state, state, "s", {}, "m", campaign)
    assert any(f["name"] == "密道" for f in result["world_facts"])
    campaign.extract_facts.assert_not_awaited()
