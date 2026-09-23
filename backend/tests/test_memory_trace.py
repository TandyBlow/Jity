"""The memory trace reports what each turn declared against what state kept.

The trace exists so a 270-turn run can be audited for memory loss. It is only
worth reading if it describes the same merge apply_output performed, so these
tests pin the shared fold order rather than the endpoint's formatting.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.database import Database
from app.schemas import StoryOutput
from app.schemas.game.memory import ItemMemory, MemoryUpdates, WorldFactMemory
from app.services.game_state import GameStateManager
from app.services.game_state.defaults import MAX_WORLD_FACTS


def _manager(tmp_path) -> GameStateManager:
    return GameStateManager(Database(tmp_path / "trace.sqlite3"))


def _story(**overrides) -> StoryOutput:
    base = {"narration": "门后是走廊", "options": ["继续"], "current_location": "走廊"}
    base.update(overrides)
    return StoryOutput(**base)


def _state(**overrides) -> dict:
    base = {
        "turn": 1,
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
    base.update(overrides)
    return base


def test_declared_and_held_are_both_reported(tmp_path):
    manager = _manager(tmp_path)
    output = _story(
        items_gained=[{"name": "旧通行卡", "description": "来自任务奖励"}],
        memory_updates=MemoryUpdates(npcs_upserted=[{"name": "诺诺", "relationship": "引路人"}]),
    )

    next_state = manager.apply_output(_state(), "拿卡", output)
    entry = manager.memory_trace_entry(output.model_dump(), next_state)

    assert entry["items"]["declared"] == ["旧通行卡"]
    assert entry["items"]["held"] == ["旧通行卡"]
    assert entry["npcs"]["declared"] == ["诺诺"]
    assert entry["npcs"]["held"] == ["诺诺"]


def test_legacy_fields_are_folded_in_memory_updates_order(tmp_path):
    """apply_output merges items_gained before memory_updates, so memory wins."""
    manager = _manager(tmp_path)
    output = _story(
        items_gained=[{"name": "旧通行卡", "description": "来自 items_gained"}],
        memory_updates=MemoryUpdates(
            items_upserted=[ItemMemory(name="旧通行卡", description="来自 memory_updates")]
        ),
    )

    next_state = manager.apply_output(_state(), "拿卡", output)
    entry = manager.memory_trace_entry(output.model_dump(), next_state)

    assert next_state["items"][0]["description"] == "来自 memory_updates"
    # Folded, not listed twice.
    assert entry["items"]["declared"] == ["旧通行卡"]


def test_a_declaration_the_cap_dropped_is_reported_as_declared(tmp_path):
    """The failure this whole surface exists to make visible."""
    manager = _manager(tmp_path)
    full = [{"name": f"既有事实{i}", "description": "d"} for i in range(MAX_WORLD_FACTS)]
    output = _story(
        memory_updates=MemoryUpdates(
            world_facts_upserted=[WorldFactMemory(name="第 16 条新事实", description="d")]
        )
    )

    next_state = manager.apply_output(_state(world_facts=full), "观察", output)
    entry = manager.memory_trace_entry(output.model_dump(), next_state)

    assert len(next_state["world_facts"]) == MAX_WORLD_FACTS
    assert "第 16 条新事实" in entry["world_facts"]["declared"]
    assert "第 16 条新事实" not in entry["world_facts"]["held"]


def test_nothing_declared_yields_empty_lists(tmp_path):
    manager = _manager(tmp_path)
    output = _story()

    next_state = manager.apply_output(_state(), "等待", output)
    entry = manager.memory_trace_entry(output.model_dump(), next_state)

    assert entry["items"] == {"declared": [], "held": []}
    assert entry["world_facts"] == {"declared": [], "held": []}


def test_route_returns_a_node_per_turn(tmp_path, monkeypatch):
    from app.routers import sessions

    db = Database(tmp_path / "trace.db")
    manager = GameStateManager(db)
    monkeypatch.setattr(sessions, "db", db)
    monkeypatch.setattr(sessions, "state_manager", manager)

    app = FastAPI()
    app.include_router(sessions.router)
    http = TestClient(app)

    session = manager.create_session("测试", "test")
    sid, root = session["session_id"], session["active_turn_id"]
    output = _story(items_gained=[{"name": "旧通行卡"}])
    db.commit_story_turn(
        session_id=sid, expected_parent_id=root, player_action="拿卡",
        output=output.model_dump(), state=manager.apply_output(_state(), "拿卡", output),
        campaign_progress=None, model="test", source="llm", model_output_id=None,
    )

    payload = http.get(f"/sessions/{sid}/memory-trace").json()

    assert payload["caps"]["world_facts"] == MAX_WORLD_FACTS
    # Root plus the one committed turn.
    assert len(payload["nodes"]) == 2
    turn = payload["nodes"][-1]
    assert turn["items"]["declared"] == ["旧通行卡"]
    assert turn["is_on_active_path"] is True


def test_node_detail_carries_the_same_folded_memory(tmp_path, monkeypatch):
    """The client renders node detail from this, so it must not have to fold."""
    from app.routers import sessions

    db = Database(tmp_path / "trace.db")
    manager = GameStateManager(db)
    monkeypatch.setattr(sessions, "db", db)
    monkeypatch.setattr(sessions, "state_manager", manager)

    app = FastAPI()
    app.include_router(sessions.router)
    http = TestClient(app)

    session = manager.create_session("测试", "test")
    sid, root = session["session_id"], session["active_turn_id"]
    output = _story(memory_updates=MemoryUpdates(npcs_upserted=[{"name": "诺诺"}]))
    node_id = db.commit_story_turn(
        session_id=sid, expected_parent_id=root, player_action="搭话",
        output=output.model_dump(), state=manager.apply_output(_state(), "搭话", output),
        campaign_progress=None, model="test", source="llm", model_output_id=None,
    )

    detail = http.get(f"/sessions/{sid}/timeline/{node_id}").json()

    assert detail["memory"]["npcs"] == {"declared": ["诺诺"], "held": ["诺诺"]}
    assert detail["memory"]["items"] == {"declared": [], "held": []}


def test_route_404s_for_unknown_session(tmp_path, monkeypatch):
    from app.routers import sessions

    monkeypatch.setattr(sessions, "db", Database(tmp_path / "trace.db"))
    monkeypatch.setattr(sessions, "state_manager", GameStateManager(sessions.db))

    app = FastAPI()
    app.include_router(sessions.router)

    assert TestClient(app).get("/sessions/nope/memory-trace").status_code == 404
