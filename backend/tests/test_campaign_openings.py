"""Campaign opening and first continuation regressions, with no paid API calls."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.schemas import GenerateRequest, StoryOutput
from app.schemas.agent_io import ActionRuling, ActionPermissibility, DirectorInstruction
from app.services.agents.director import DirectorAgent
from app.services.agents.examiner import ExaminerAgent
from app.services.campaign_manager import CampaignManager
from app.services.game_state import GameStateManager
from app.services.prompt_builder import PromptBuilder
from app.services.scenario_generator import ScenarioGenerator


CAMPAIGNS = Path(__file__).resolve().parents[1] / "data" / "campaigns"
FILES = ["default_campaign.json", "龙族Ⅰ_火之晨曦_campaign.json",
         "龙族Ⅱ_悼亡者之瞳_campaign.json", "龙族Ⅲ_黑月之潮_campaign.json"]
LOCATIONS = ["卡塞尔学院大门前", "婶婶家中的卧室", "苏菲拉德披萨馆包间", "黑天鹅港走廊"]

# The opening narration stays authored; only the choices come from the model.
OPENING_OPTIONS = ["环顾四周确认处境", "向在场的人搭话", "低头检查随身物品"]
OPENING_CHECKS = [
    None,
    {
        "requires_check": True,
        "name": "观察检定",
        "skill": "调查",
        "system": "通用 d20",
        "normal_target": 12,
        "difficulty": "普通",
        "stakes": "成功看清周围细节，失败引起旁人注意。",
    },
    None,
]


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    from app.routers import sessions

    db = Database(tmp_path / "opening.db")
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
    app = FastAPI()
    app.include_router(sessions.router)

    llm = MagicMock()
    llm.generate = AsyncMock()
    llm.settings = SimpleNamespace(deepseek_api_key="test")
    llm.generate_json = AsyncMock(return_value={
        "options": list(OPENING_OPTIONS),
        "option_checks": [dict(check) if check else None for check in OPENING_CHECKS],
    })
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
    return SimpleNamespace(app=app, db=db, states=states, managers=managers, generator=generator,
                           llm=llm, retriever=retriever)


@pytest.mark.asyncio
@pytest.mark.parametrize("filename,location", list(zip(FILES, LOCATIONS)))
async def test_opening_then_continue_uses_selected_campaign(runtime, filename, location):
    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        response = await client.post("/sessions", json={"campaign_filename": filename})
        assert response.status_code == 200
        session = response.json()
        sid = session["session_id"]
        assert session["campaign_filename"] == filename
        assert session["state"]["current_location"] == location
        assert session["state"]["turn"] == 0

        opened = await runtime.generator.generate(sid, GenerateRequest(player_action="（入场）环顾四周。"))
        manager = runtime.managers[sid]
        opening = manager.get_opening_scene()
        assert opened.source == "scripted"
        assert opened.output.narration == opening.replace("——", "，").replace("—", "，")
        assert opened.output.options == OPENING_OPTIONS
        assert opened.output.option_checks[0] is None
        assert opened.output.option_checks[1].name == "观察检定"
        assert opened.state["turn"] == manager.progress.turn_in_session == 1
        # The opening asks for options only, so the Narrator is still never called.
        runtime.llm.generate_json.assert_awaited_once()
        runtime.llm.generate.assert_not_awaited()
        runtime.retriever.retrieve_async.assert_not_awaited()

        runtime.llm.generate.return_value = (StoryOutput(
            narration="你停在原地，仔细观察眼前的动静。", current_location=location,
            options=["观察"]), 1)
        continued = await runtime.generator.generate(sid, GenerateRequest(player_action="继续"))
        assert continued.source == "llm"
        assert continued.state["turn"] == manager.progress.turn_in_session == 2
        prompt = runtime.llm.generate.call_args.args[0]
        assert manager.campaign.title in prompt
        assert opening in prompt
        assert location in prompt
        assert "诺诺前来接应" not in prompt
        assert "卡塞尔学院报到处大厅" not in prompt
        assert "不要跳出当前入学调查" not in prompt
        if filename != FILES[0]:
            assert "完成卡塞尔学院入学报到" not in prompt
            assert "接路明非报到" not in prompt

        # Refresh retrieves campaign identity and history without replaying a turn.
        restored = (await client.get(f"/sessions/{sid}")).json()
        assert restored["campaign_filename"] == filename
        assert restored["state"]["turn"] == 2
        messages = (await client.get(f"/sessions/{sid}/history")).json()["messages"]
        assert len(messages) == 4
        if runtime.generator._memory_tasks:
            await asyncio.gather(*runtime.generator._memory_tasks)


def timeline_entries():
    return [(filename, ai, si) for filename in FILES
            for ai, arc in enumerate(json.loads((CAMPAIGNS / filename).read_text())["arcs"])
            for si in range(len(arc["sessions"]))]


@pytest.mark.asyncio
@pytest.mark.parametrize("filename,ai,si", timeline_entries())
async def test_every_timeline_entry_starts_in_its_own_scene(runtime, filename, ai, si):
    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        session = (await client.post("/sessions", json={
            "campaign_filename": filename, "arc_index": ai, "session_index": si,
        })).json()
    result = await runtime.generator.generate(session["session_id"], GenerateRequest(player_action="入场"))
    scene = runtime.managers[session["session_id"]].campaign.arcs[ai].sessions[si]
    assert result.source == "scripted"
    assert result.output.narration == scene.opening_scene.replace("——", "，").replace("—", "，")
    assert result.state["current_location"] == scene.entry_state["location"]
    assert "诺诺前来接应" not in str(result.state)
    runtime.llm.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_next_chapter_uses_local_turn_and_survives_reload(runtime):
    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        session = (await client.post("/sessions", json={"campaign_filename": FILES[1]})).json()
    sid = session["session_id"]
    manager = runtime.managers[sid]
    await runtime.generator.generate(sid, GenerateRequest(player_action="入场"))
    state = runtime.states.get_session_payload(sid)["state"]
    state.update(
        turn=30,
        health=67,
        items=[{"name": "纪念物", "status": "owned"}],
        npcs=[
            {"name": "婶婶", "status": "present", "current_location": "婶婶家中的卧室"},
            {"name": "堂弟", "status": "present", "current_location": "婶婶家中的卧室"},
        ],
        recent_events=["你猛地从旧卧室的噩梦中惊醒，婶婶催你下楼洗碗。"],
        _memory_controller={"nsb": {"level1_episodes": ["上一幕短期记忆"]}},
    )
    runtime.states.save_state(sid, session["game_name"], "test", state)
    await manager.advance_session()
    result = await runtime.generator.generate(sid, GenerateRequest(player_action="继续"))
    assert result.source == "scripted"
    assert result.state["turn"] == 31
    assert result.state["health"] == 67
    assert result.state["current_location"] == "芝加哥火车站候车大厅"
    assert any(i["name"] == "纪念物" for i in result.state["items"])
    assert result.state["npcs"] == []
    assert all("旧卧室" not in event and "婶婶" not in event for event in result.state["recent_events"])
    assert "_memory_controller" not in runtime.states.get_session_payload(sid)["state"]

    runtime.llm.generate.return_value = (StoryOutput(
        narration="你在芝加哥火车站睁开眼，芬格尔仍坐在旁边。",
        current_location="芝加哥火车站候车大厅",
        options=["询问芬格尔"],
    ), 1)
    continued = await runtime.generator.generate(sid, GenerateRequest(player_action="继续"))
    assert continued.source == "llm"
    prompt = runtime.llm.generate.call_args.args[0]
    first_opening = manager.campaign.arcs[0].sessions[0].opening_scene
    next_opening = manager.campaign.arcs[0].sessions[1].opening_scene
    assert next_opening in prompt
    assert first_opening not in prompt
    assert "婶婶" not in prompt
    assert "堂弟" not in prompt
    assert "旧卧室" not in prompt
    director_context = DirectorAgent.direct.call_args.kwargs["narrative_context"]
    assert "当前幕固定开场（最高优先级" in director_context
    assert "芝加哥火车站候车大厅" in director_context
    assert next_opening in director_context

    reloaded = CampaignManager(db=runtime.db, campaigns_dir=CAMPAIGNS, scripted_story=MagicMock())
    active_slot = runtime.db.get_session(sid)["active_slot_name"]
    reloaded.load(CAMPAIGNS / FILES[1], campaign_id=sid, slot_name=active_slot)
    runtime.managers[sid] = reloaded
    assert reloaded.progress.turn_in_session == 2
    payload = runtime.states.get_session_payload(sid)
    assert await runtime.generator._handle_opening_scene(
        sid, GenerateRequest(player_action="观察"), payload, payload["state"], "test", reloaded, 1
    ) is None


@pytest.mark.asyncio
async def test_continue_after_next_opening_cannot_be_blocked_by_examiner(runtime, monkeypatch):
    """The generic UI continuation must reach Narrator after a sparse entry_state."""
    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        session = (await client.post("/sessions", json={
            "campaign_filename": FILES[2], "session_index": 1,
        })).json()
    sid = session["session_id"]
    opened = await runtime.generator.generate(sid, GenerateRequest(player_action="推进到下一幕"))
    assert opened.source == "scripted"
    assert "陈雯雯" in opened.output.narration

    blocked = AsyncMock(return_value=ActionRuling(
        permissibility=ActionPermissibility.BLOCKED,
        rejection_reason="当前没有正在进行的事件或对话可供继续。",
    ))
    monkeypatch.setattr(ExaminerAgent, "examine", blocked)
    runtime.llm.generate.return_value = (StoryOutput(
        narration="你看见陈雯雯坐在烛光里，她抬头望向你。",
        current_location="湖园一号餐厅",
        options=["坐下交谈"],
    ), 1)

    continued = await runtime.generator.generate(sid, GenerateRequest(player_action="继续"))

    assert continued.source == "llm"
    assert "陈雯雯" in continued.output.narration
    blocked.assert_not_awaited()


def test_explicit_empty_starting_state_clears_free_play_memory(runtime):
    from app.services.game_state.defaults import default_state
    campaign = SimpleNamespace(starting_state={"sanity": 0, "npcs": [], "items": [], "recent_events": [],
                                               "player_status": {"notes": "陌生的环境"}},
        arcs=[SimpleNamespace(goal="寻找出口", sessions=[SimpleNamespace(name="陌生房间", entry_state=None)])])
    base = default_state()
    state = runtime.states.merge_entry_state(base, campaign, 0, 0, initialize=True)
    assert state["sanity"] == 0
    assert state["npcs"] == state["items"] == state["recent_events"] == []
    assert state["current_location"] == "陌生房间"
    assert state["player_status"]["current_goal"] == "寻找出口"
    assert state["player_status"]["condition"] == "正常"
    assert base["npcs"][0]["name"] == "诺诺"


@pytest.mark.asyncio
async def test_free_play_keeps_original_defaults(runtime):
    async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://test") as client:
        session = (await client.post("/sessions", json={})).json()
    assert session["campaign_filename"] is None
    assert session["state"]["current_location"] == "卡塞尔学院报到处大厅"
