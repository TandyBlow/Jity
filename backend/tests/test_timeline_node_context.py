"""The node detail exposes what was injected into that turn's prompt.

Turns stored before the prompt was recorded still have a model_outputs row, so
"recorded" has to be decided by content, not by the row existing. Getting this
wrong would make an old turn look auditable when it carries nothing.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.database import Database
from app.services.game_state import GameStateManager


def _output() -> dict:
    return {
        "narration": "门后是走廊",
        "dialogue": [],
        "scene_prompt": "",
        "sanity_delta": 0,
        "health_delta": 0,
        "options": ["继续"],
        "game_over": False,
        "game_over_reason": "",
        "current_location": "走廊",
        "items_gained": [],
        "items_lost": [],
        "npcs_encountered": [],
        "quests_updated": [],
        "memory_updates": {},
        "npc_relations_delta": None,
    }


def _state(turn: int) -> dict:
    return {
        "turn": turn,
        "health": 100,
        "sanity": 80,
        "current_location": "走廊",
        "items": [],
        "npcs": [],
        "quests": [],
        "world_facts": [],
        "player_status": {},
        "recent_events": [],
    }


SECTIONS = {
    "campaign_context": "## 战役上下文\n第一幕\n",
    "system_prompt": "你是桌面 RPG 的中文 GM 辅助系统。",
    "rag_chunks": "RAG 检索到的相关知识：\n暂无额外知识。\n",
    "player_action": "打开门",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.routers import sessions

    db = Database(tmp_path / "context.db")
    manager = GameStateManager(db)
    monkeypatch.setattr(sessions, "db", db)
    monkeypatch.setattr(sessions, "state_manager", manager)

    app = FastAPI()
    app.include_router(sessions.router)
    return TestClient(app), db, manager


def _seed(client, db, manager):
    session = manager.create_session("测试", "test")
    return session["session_id"], session["active_turn_id"]


def test_context_is_returned_for_a_recorded_turn(client):
    http, db, manager = client
    sid, root = _seed(http, db, manager)

    output_id = db.add_model_output(
        session_id=sid, model="test", input_text="打开门", output=_output(),
        latency_ms=42, source="llm", token_count=1234, word_count=6,
        retrieved_chunks=[{"id": "c1", "title": "卡塞尔学院", "score": 0.9}],
        prompt_sections=SECTIONS, prompt_text="## 导演指令\n继续叙事\n",
    )
    node_id = db.commit_story_turn(
        session_id=sid, expected_parent_id=root, player_action="打开门",
        output=_output(), state=_state(1), campaign_progress=None,
        model="test", source="llm", model_output_id=output_id,
    )

    context = http.get(f"/sessions/{sid}/timeline/{node_id}").json()["context"]

    assert context["recorded"] is True
    assert context["prompt_sections"] == SECTIONS
    assert context["prompt_text"] == "## 导演指令\n继续叙事\n"
    assert context["token_count"] == 1234
    assert context["latency_ms"] == 42
    assert context["word_count"] == 6
    assert context["retrieved_chunks"][0]["title"] == "卡塞尔学院"


def test_turns_stored_before_the_prompt_existed_report_not_recorded(client):
    http, db, manager = client
    sid, root = _seed(http, db, manager)

    # A row that exists but predates the prompt columns.
    output_id = db.add_model_output(
        session_id=sid, model="test", input_text="打开门", output=_output(),
        latency_ms=10, source="llm",
    )
    node_id = db.commit_story_turn(
        session_id=sid, expected_parent_id=root, player_action="打开门",
        output=_output(), state=_state(1), campaign_progress=None,
        model="test", source="llm", model_output_id=output_id,
    )

    context = http.get(f"/sessions/{sid}/timeline/{node_id}").json()["context"]

    assert context["recorded"] is False
    assert context["prompt_text"] == ""
    assert context["prompt_sections"] == {}


def test_root_node_reports_not_recorded(client):
    http, db, manager = client
    sid, root = _seed(http, db, manager)

    context = http.get(f"/sessions/{sid}/timeline/{root}").json()["context"]

    assert context["recorded"] is False
    assert context["retrieved_chunks"] == []
