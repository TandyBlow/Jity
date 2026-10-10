"""Offline acceptance probes: pure state plus SQLite only under pytest tmp_path.

Failures expose unmet acceptance criteria; they are intentionally not xfailed.
No application singletons, routers, environment settings or model clients load.
"""

from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace

import pytest

from app.database import Database
from app.schemas import StoryOutput
from app.schemas.agent_io import EpisodeSummary, ItemState
from app.schemas.game.memory import ItemMemory, MemoryUpdates
from app.services.agents.examiner import ExaminerAgent
from app.services.game_state import GameStateManager
from app.services.game_state.defaults import MAX_ITEMS, default_state
from app.services.memory.memory_controller import MemoryController
from app.services.memory.score_tracker import ScoreTracker


def chapter_transition():
    controller = MemoryController(None, None, "offline")
    controller.nsb.accept_level1(EpisodeSummary(
        episode_id="early-clue", turn_start=1, turn_end=6,
        summary="青铜钥匙要向左旋转三次才能开启密室", entities_involved=["青铜钥匙"],
        protected=True,
    ))
    controller.score_tracker.seed([{"name": "青铜钥匙"}], 6)
    state = default_state()
    state.update(items=[{"name": "青铜钥匙", "status": "owned"}],
                 world_facts=[{"name": "密室位置", "description": "钟楼地下", "status": "known"}],
                 _memory_controller=controller.export_state())
    original = deepcopy(state)
    chapter = SimpleNamespace(name="下一幕", entry_state={"location": "钟楼"})
    campaign = SimpleNamespace(arcs=[SimpleNamespace(goal="打开密室", sessions=[chapter])])
    result = GameStateManager(None).merge_entry_state(
        state, campaign, 0, 0, reset_scene_context=True,
    )
    assert state == original, "transition mutated its input"
    return result


def test_chapter_keeps_structured_fact_inventory_and_terminal_ledger():
    state = chapter_transition()
    assert state["items"][0]["name"] == "青铜钥匙"
    assert state["world_facts"][0]["description"] == "钟楼地下"
    assert state["_memory_controller"]["score_tracker"][0]["state"] == "active"


@pytest.mark.asyncio
async def test_chapter_keeps_unique_long_term_evidence_retrievable_and_injected():
    state = chapter_transition()
    assert state["_memory_controller"].get("nsb", {}).get("level1"), "transition/write stage deleted long-term evidence before retrieval"
    restored = MemoryController(None, None, "offline")
    restored.load_state(state["_memory_controller"])
    prompt = await restored.assemble_context_async(state, 100, player_action="使用青铜钥匙打开密室")
    assert any(hit.memory_id == "early-clue" for hit in restored.last_hits), "retrieval stage lost early evidence"
    assert "向左旋转三次" in prompt, "injection stage lost required evidence"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["青铜钥匙", "古钥匙"])
async def test_owned_item_is_usable_by_canonical_name_and_alias(name):
    state = default_state()
    state["items"] = [{"name": "青铜钥匙", "status": "owned", "aliases": ["古钥匙"]}]
    ruling = await ExaminerAgent().examine(f"使用{name}打开门", state)
    assert ruling.permissibility.value != "blocked", "owned identity was rejected by examiner"


@pytest.mark.asyncio
async def test_shared_alias_never_selects_one_of_two_distinct_items():
    state = default_state()
    state["items"] = [
        {"name": "青铜钥匙", "status": "owned", "aliases": ["古钥匙"]},
        {"name": "白银钥匙", "status": "owned", "aliases": ["古钥匙"]},
    ]
    tracker = ScoreTracker()
    tracker.seed(state["items"], 1)
    assert set(tracker.get_all_states()) == {"青铜钥匙", "白银钥匙"}
    removal = StoryOutput(narration="丢弃古钥匙", items_lost=[{"name": "古钥匙"}])
    tracker.validate_output(removal, 2)
    assert set(tracker.get_all_states().values()) == {"active"}
    ruling = await ExaminerAgent().examine("使用古钥匙打开门", state)
    assert ruling.permissibility.value == "blocked"
    assert "多个物品" in ruling.rejection_reason


@pytest.mark.parametrize("transition", ["", "recovered", "repaired"])
def test_consumed_identity_cannot_be_restored_after_serialization(transition):
    controller = MemoryController(None, None, "offline")
    controller.score_tracker.seed([{"name": "药剂", "aliases": ["红药水"]}], 1)
    output = StoryOutput(narration="喝完药剂", items_lost=[{"name": "红药水", "status": "consumed"}])
    controller.score_tracker.validate_output(output, 2)
    restored = MemoryController(None, None, "offline")
    restored.load_state(json.loads(json.dumps(controller.export_state())))
    revival = StoryOutput(narration="恢复药剂", memory_updates=MemoryUpdates(
        items_upserted=[ItemMemory(name="红药水", transition=transition)]))
    assert restored.score_tracker.validate_output(revival, 100)
    assert not revival.memory_updates.items_upserted
    assert restored.score_tracker.get_record("药剂").state == ItemState.CONSUMED


def test_destroyed_identity_still_allows_explicit_repair():
    tracker = ScoreTracker()
    tracker.propose_transition("钥匙", ItemState.DESTROYED, 1)
    assert tracker.propose_transition("钥匙", ItemState.ACTIVE, 2, "repaired") == (ItemState.ACTIVE, False)


@pytest.mark.parametrize("status,terminal", [
    ("destroyed", ItemState.DESTROYED), ("lost", ItemState.LOST),
    ("consumed", ItemState.CONSUMED), ("discarded", ItemState.LOST),
])
@pytest.mark.parametrize("channel", ["legacy", "structured"])
def test_terminal_upsert_removes_inventory_and_survives_restore(status, terminal, channel):
    tracker = ScoreTracker()
    tracker.seed([{"name": "药剂"}], 1)
    output = StoryOutput(narration="药剂已经不可用")
    if channel == "legacy":
        output.items_gained = [{"name": "药剂", "status": status}]
    else:
        output.memory_updates = MemoryUpdates(items_upserted=[ItemMemory(name="药剂", status=status)])
    tracker.validate_output(output, 2)
    assert tracker.get_record("药剂").state == terminal, "state-validation stage treated terminal item as usable"
    state = default_state()
    state["items"] = [{"name": "药剂", "status": "owned"}]
    applied = GameStateManager(None).apply_output(state, "继续", output)
    assert applied["items"] == [], "inventory reducer retained terminal item"
    restored = ScoreTracker()
    restored.load_from_state(json.loads(json.dumps(tracker.export_state())))
    revival = StoryOutput(narration="凭空拿出药剂", items_gained=[{"name": "药剂"}])
    assert restored.validate_output(revival, 100), "restore stage allowed an implicit revival"
    assert revival.items_gained == []


@pytest.mark.parametrize("initial_count", [MAX_ITEMS - 1, MAX_ITEMS])
def test_capacity_boundary_does_not_silently_lose_new_key(initial_count):
    state = default_state()
    state["items"] = [{"name": f"杂物{i}", "status": "owned"} for i in range(initial_count)]
    tracker = ScoreTracker()
    tracker.seed(state["items"], 1)
    output = StoryOutput(narration="获得任务钥匙", items_gained=[{"name": "任务钥匙"}])
    tracker.validate_output(output, 2)
    applied = GameStateManager(None).apply_output(state, "领取钥匙", output)
    assert tracker.get_record("任务钥匙").state == ItemState.ACTIVE
    assert any(item["name"] == "任务钥匙" for item in applied["items"]), "inventory and terminal ledger disagree at capacity"


@pytest.fixture
def isolated_session(tmp_path):
    db = Database(tmp_path / "review-only.sqlite3")
    manager = GameStateManager(db)
    session = manager.create_session("offline-review", "offline")
    return db, manager, session


def commit(db, session, state):
    return db.commit_story_turn(
        session_id=session["session_id"], expected_parent_id=session["active_turn_id"],
        player_action="取得钥匙", output={"narration": "获得钥匙"}, state=state,
        campaign_progress=None, model="offline", source="llm", model_output_id=None,
    )


def test_committed_snapshot_survives_database_reopen_and_branch_restore(isolated_session):
    db, manager, session = isolated_session
    state = deepcopy(session["state"])
    tracker = ScoreTracker()
    tracker.seed([{"name": "钥匙"}], 1)
    tracker.propose_transition("钥匙", ItemState.DESTROYED, 2)
    state["_memory_controller"] = {"version": "v1", "score_tracker": tracker.export_state()}
    node = commit(db, session, state)
    reopened = Database(db.path)
    restored = reopened.activate_story_turn(session["session_id"], node)
    assert restored["state"] == state
    assert GameStateManager(reopened).get_session_payload(session["session_id"])["state"] == state
    tracker.load_from_state(restored["state"]["_memory_controller"]["score_tracker"])
    assert tracker.propose_transition("钥匙", ItemState.ACTIVE, 100)[1]
    reopened.activate_story_turn(session["session_id"], session["active_turn_id"])
    assert manager.get_session_payload(session["session_id"])["state"] == session["state"]


def test_failure_during_head_update_rolls_back_node_and_messages(isolated_session):
    db, manager, session = isolated_session
    sid = session["session_id"]
    before_nodes, before_messages = db.list_story_turns(sid), db.get_messages(sid)
    with db.connect() as connection:
        connection.execute("CREATE TRIGGER review_fail_head BEFORE UPDATE OF active_turn_id ON game_sessions BEGIN SELECT RAISE(ABORT, 'injected offline failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="injected offline failure"):
        commit(db, session, deepcopy(session["state"]))
    assert db.list_story_turns(sid) == before_nodes
    assert db.get_messages(sid) == before_messages
    assert manager.get_session_payload(sid)["active_turn_id"] == session["active_turn_id"]
