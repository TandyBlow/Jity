"""Campaign opening options: what the model returns, and how failures surface.

The opening narration is authored, so only the choices are generated.  A failed
generation must surface as a retryable error and must not consume the turn.
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.schemas.agent_io import ActionPermissibility, ActionRuling, DirectorInstruction
from app.services.agents.director import DirectorAgent
from app.services.agents.examiner import ExaminerAgent
from app.services.campaign_manager import CampaignManager
from app.services.game_state import GameStateManager
from app.services.llm_client import LLMOutputParseError, LLMRequestError
from app.services.prompt_builder import PromptBuilder
from app.services.scenario_generator import ScenarioGenerator

CAMPAIGNS = Path(__file__).resolve().parents[1] / "data" / "campaigns"
CAMPAIGN = "龙族Ⅰ_火之晨曦_campaign.json"

GOOD_PAYLOAD = {
    "options": ["环顾四周确认处境", "向在场的人搭话", "检查随身物品"],
    "option_checks": [
        None,
        {
            "requires_check": True,
            "name": "观察检定",
            "skill": "调查",
            "system": "通用 d20",
            "normal_target": 12,
            "difficulty": "困难",
            "stakes": "成功看出异常，失败引起注意。",
        },
        None,
    ],
}


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    from app.routers import generate as generate_router
    from app.routers import sessions

    db = Database(tmp_path / "opening-options.db")
    states = GameStateManager(db)
    managers = {}

    def build_manager():
        return CampaignManager(db=db, campaigns_dir=CAMPAIGNS, scripted_story=MagicMock())

    monkeypatch.setattr(sessions, "db", db)
    monkeypatch.setattr(sessions, "state_manager", states)
    monkeypatch.setattr(sessions, "settings", SimpleNamespace(campaigns_dir=CAMPAIGNS, llm_model="test"))
    monkeypatch.setattr(sessions, "build_campaign_manager", build_manager)
    monkeypatch.setattr(sessions, "campaign_manager_cache", SimpleNamespace(
        put=lambda sid, slot, manager: managers.__setitem__(sid, manager)))

    llm = MagicMock()
    llm.generate = AsyncMock()
    llm.settings = SimpleNamespace(deepseek_api_key="test")
    llm.generate_json = AsyncMock(return_value=dict(GOOD_PAYLOAD))

    retriever = SimpleNamespace(retrieve_async=AsyncMock(return_value=[]))
    generator = ScenarioGenerator(db, states, retriever, PromptBuilder(), llm, MagicMock(), "test",
                                  campaign_manager_provider=lambda sid, slot: managers[sid])
    memory = MagicMock()
    memory.assemble_context_async = AsyncMock(side_effect=lambda *args, **kw: kw["campaign_context"])
    memory.export_state.return_value = {}
    memory.maintain = AsyncMock()
    monkeypatch.setattr(generator, "_get_memory_controller", lambda *args: memory)
    monkeypatch.setattr(ExaminerAgent, "examine", AsyncMock(return_value=ActionRuling(
        permissibility=ActionPermissibility.PERMISSIBLE)))
    monkeypatch.setattr(DirectorAgent, "direct", AsyncMock(return_value=DirectorInstruction(
        narrative_direction="承接当前场景，回应玩家。")))

    app = FastAPI()
    app.include_router(sessions.router)
    app.include_router(generate_router.router)
    monkeypatch.setattr(generate_router, "knowledge_service",
                        SimpleNamespace(scenario_generator=generator))

    return SimpleNamespace(app=app, db=db, states=states, managers=managers,
                           generator=generator, llm=llm, retriever=retriever)


async def _open_session(client) -> str:
    response = await client.post("/sessions", json={"campaign_filename": CAMPAIGN})
    assert response.status_code == 200
    return response.json()["session_id"]


async def _generate(client, sid):
    return await client.post(f"/sessions/{sid}/generate", json={"player_action": "入场"})


def _turn_output(payload):
    return payload["output"]


@pytest.mark.asyncio
async def test_opening_options_come_from_the_model(runtime):
    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        sid = await _open_session(client)
        response = await _generate(client, sid)

    assert response.status_code == 200
    output = _turn_output(response.json())
    assert output["options"] == GOOD_PAYLOAD["options"]
    # The check is index aligned and its threshold is derived on the way out:
    # a hard check on skill 12 must land on 6.
    assert output["option_checks"][0] is None
    assert output["option_checks"][1]["target"] == 6
    assert output["option_checks"][1]["expression"] == "1d20 ≤ 6"
    assert len(output["option_checks"]) == len(output["options"])
    assert response.json()["source"] == "scripted"


@pytest.mark.asyncio
async def test_opening_prompt_carries_the_scene_and_the_contract(runtime):
    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        sid = await _open_session(client)
        opened = await client.get(f"/sessions/{sid}")
        location = opened.json()["state"]["current_location"]
        await _generate(client, sid)

    call = runtime.llm.generate_json.call_args.kwargs
    prompt = call["prompt"]
    assert location in prompt
    assert "option_checks" in prompt
    assert "normal_target" in prompt
    # The opening must not fall back to the default 50000 / 0.35.
    assert call["max_tokens"] == 1000
    assert call["temperature"] == 0.3


@pytest.mark.asyncio
async def test_request_error_returns_502_and_leaves_the_turn_uncommitted(runtime):
    runtime.llm.generate_json = AsyncMock(side_effect=LLMRequestError("超时", 0, "timeout", 7))

    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        sid = await _open_session(client)
        response = await _generate(client, sid)
        assert response.status_code == 502
        assert "开场行动选项生成失败" in response.json()["detail"]

        history = (await client.get(f"/sessions/{sid}/history")).json()["messages"]
        state = (await client.get(f"/sessions/{sid}")).json()["state"]

    assert history == []
    assert state["turn"] == 0
    assert runtime.managers[sid].progress.turn_in_session == 0


@pytest.mark.asyncio
async def test_parse_error_returns_502(runtime):
    runtime.llm.generate_json = AsyncMock(
        side_effect=LLMOutputParseError("bad json", "{oops", "{oops", 3)
    )

    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        sid = await _open_session(client)
        response = await _generate(client, sid)
        history = (await client.get(f"/sessions/{sid}/history")).json()["messages"]

    assert response.status_code == 502
    assert history == []


@pytest.mark.asyncio
async def test_contract_violation_returns_502_not_a_default_check(runtime):
    runtime.llm.generate_json = AsyncMock(return_value={
        "options": ["环顾四周", "搭话"],
        # Missing normal_target/difficulty would otherwise default to target 12.
        "option_checks": [None, {"requires_check": True, "name": "观察检定"}],
    })

    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        sid = await _open_session(client)
        response = await _generate(client, sid)

    assert response.status_code == 502
    assert "开场行动选项生成失败" in response.json()["detail"]


@pytest.mark.asyncio
async def test_missing_api_key_returns_503(runtime):
    runtime.llm.settings = SimpleNamespace(deepseek_api_key="")

    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        sid = await _open_session(client)
        response = await _generate(client, sid)

    assert response.status_code == 503
    assert "DEEPSEEK_API_KEY" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_failed_opening_can_be_retried(runtime):
    """The retry must still land on turn 0 and replay the authored opening."""
    runtime.llm.generate_json = AsyncMock(side_effect=LLMRequestError("超时", 0, "timeout", 7))

    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        sid = await _open_session(client)
        assert (await _generate(client, sid)).status_code == 502

        runtime.llm.generate_json = AsyncMock(return_value=dict(GOOD_PAYLOAD))
        retried = await _generate(client, sid)

        assert retried.status_code == 200
        payload = retried.json()
        assert payload["source"] == "scripted"
        assert payload["output"]["options"] == GOOD_PAYLOAD["options"]
        assert payload["state"]["turn"] == runtime.managers[sid].progress.turn_in_session == 1
        if runtime.generator._memory_tasks:
            await asyncio.gather(*runtime.generator._memory_tasks)
