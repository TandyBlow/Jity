"""Branch creation, path isolation, and exact snapshot restoration."""

import json

import pytest

from app.database import Database
from app.exceptions import ConcurrentModificationError
from app.services.game_state import GameStateManager


def _output(text: str, option: str) -> dict:
    return {
        "narration": text,
        "dialogue": [],
        "scene_prompt": "",
        "sanity_delta": 0,
        "health_delta": 0,
        "options": [option],
        "game_over": False,
        "game_over_reason": "",
        "current_location": "测试地点",
        "items_gained": [],
        "items_lost": [],
        "npcs_encountered": [],
        "quests_updated": [],
        "memory_updates": {},
        "npc_relations_delta": None,
    }


def _commit(db: Database, sid: str, parent: int, turn: int, action: str, text: str) -> int:
    state = {
        "turn": turn,
        "health": 100 - turn,
        "sanity": 80,
        "current_location": "测试地点",
        "items": [],
        "npcs": [],
        "quests": [],
        "world_facts": [],
        "player_status": {},
        "recent_events": [text],
        "_memory_controller": {"nsb": {"turns": [text]}},
    }
    return db.commit_story_turn(
        session_id=sid,
        expected_parent_id=parent,
        player_action=action,
        output=_output(text, "继续"),
        state=state,
        campaign_progress=None,
        model="test",
        source="llm",
        model_output_id=None,
    )


def test_rewind_creates_sibling_and_filters_history(tmp_path):
    db = Database(tmp_path / "timeline.sqlite3")
    manager = GameStateManager(db)
    session = manager.create_session("test", "test")
    sid = session["session_id"]
    root = session["active_turn_id"]

    first = _commit(db, sid, root, 1, "打开门", "门后是走廊")
    abandoned = _commit(db, sid, first, 2, "向左走", "左侧是档案室")

    restored = db.activate_story_turn(sid, first)
    assert restored is not None
    branch = _commit(db, sid, first, 2, "向右走", "右侧是楼梯")

    nodes = db.list_story_turns(sid)
    assert {row["id"] for row in nodes} == {root, first, abandoned, branch}
    assert [row["parent_turn_id"] for row in nodes if row["id"] in (abandoned, branch)] == [first, first]

    history = db.get_messages(sid)
    contents = [message["content"] for message in history]
    assert "打开门" in contents
    assert "向右走" in contents
    assert "向左走" not in contents
    assert not any("档案室" in content for content in contents)


def test_restore_recovers_internal_state_and_campaign_progress(tmp_path):
    db = Database(tmp_path / "timeline.sqlite3")
    manager = GameStateManager(db)
    session = manager.create_session("test", "test")
    sid = session["session_id"]
    root = session["active_turn_id"]
    progress = {
        "campaign_id": sid,
        "slot_name": "default",
        "arc_index": 1,
        "session_index": 2,
        "turn_in_session": 4,
        "fsm_state": "active/session_active",
        "revealed_anchors": json.dumps(["anchor-a"]),
        "completed_arcs": json.dumps([0]),
        "recap_compressed": "本分支摘要",
        "recap_full": "本分支完整摘要",
        "npc_relations": json.dumps([{"name": "路明非", "affinity": 2}]),
    }
    state = dict(session["state"])
    state["turn"] = 7
    state["_memory_controller"] = {"score_tracker": [{"name": "钥匙"}]}
    node = db.commit_story_turn(
        session_id=sid,
        expected_parent_id=root,
        player_action="保存现场",
        output=_output("快照剧情", "继续"),
        state=state,
        campaign_progress=progress,
        model="test",
        source="scripted",
        model_output_id=None,
    )

    db.write_campaign_progress(sid, 9, 9, 9, "campaign_end", slot_name="default")
    restored = db.activate_story_turn(sid, node)
    assert restored is not None
    assert restored["state"]["_memory_controller"] == state["_memory_controller"]
    row = db.read_campaign_progress(sid, "default")
    assert row["arc_index"] == 1
    assert row["session_index"] == 2
    assert row["revealed_anchors"] == json.dumps(["anchor-a"])
    assert row["head_turn_id"] == node


def test_stale_parent_and_cross_session_are_rejected(tmp_path):
    db = Database(tmp_path / "timeline.sqlite3")
    manager = GameStateManager(db)
    first_session = manager.create_session("one", "test")
    second_session = manager.create_session("two", "test")
    first = _commit(
        db,
        first_session["session_id"],
        first_session["active_turn_id"],
        1,
        "继续",
        "第一步",
    )

    with pytest.raises(ConcurrentModificationError):
        _commit(
            db,
            first_session["session_id"],
            first_session["active_turn_id"],
            2,
            "过期操作",
            "不应写入",
        )
    assert db.activate_story_turn(second_session["session_id"], first) is None
