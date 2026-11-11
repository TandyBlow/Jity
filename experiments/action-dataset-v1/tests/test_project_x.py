"""Tests for the nine-slot own-character projection in the loader's X shape."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from fixtures import small_world  # noqa: E402
from tools import state_view  # noqa: E402
from tools.project_x import (  # noqa: E402
    X_SLOT_ORDER,
    ProjectionError,
    candidate_ids,
    goal_ids,
    project_x,
    validate_x_shape,
)


def test_room_and_slot_labels_come_from_world_data():
    state = small_world()
    assert state_view.room_of(state, "ann") == "hall"
    assert state_view.room_of(state, "note") == "hall"  # note -> bag -> ann -> hall
    assert state_view.room_of(state, "cy") == "yard"
    assert state_view.position_label(state, "bo") == "门厅/门口"
    assert state_view.position_label(state, "note") == "背包（在门厅）/内部"


def test_held_items_are_listed_on_the_character():
    state = small_world()
    held = state_view.held_items(state, "ann")
    assert held == [{"id": "bag", "name": "背包"}]


def test_projection_has_the_nine_frozen_slots_in_order():
    x = project_x(small_world(), "ann")
    assert tuple(x) == X_SLOT_ORDER
    assert validate_x_shape(x) == []
    assert x["character"]["id"] == "ann"
    assert goal_ids(x) == ["task_ann_a", "task_ann_b"]
    assert x["goals"] == ["task_ann_a：把桌上的钥匙收好", "task_ann_b：确认钥匙属于谁"]
    assert [entry["id"] for entry in x["present"]] == ["bo"]
    assert [entry["id"] for entry in x["items"]] == ["key", "note"]
    assert candidate_ids(x) == ["bo", "bag", "key", "note"]
    assert x["recent"] == []
    assert isinstance(x["sanity"], int)


def test_remote_room_entities_never_appear():
    x = project_x(small_world(), "ann")
    ids = set(candidate_ids(x))
    assert "cy" not in ids, "character in another room leaked into candidates"
    assert "shovel" not in ids, "item in another room leaked into candidates"
    dumped = json.dumps(x, ensure_ascii=False)
    assert "希" not in dumped
    assert "铁铲" not in dumped
    assert "庭院" not in x["place"], "another room's name must not appear"


def test_held_items_are_candidates_but_not_room_objects():
    x = project_x(small_world(), "ann")
    assert "bag" in candidate_ids(x), "a label must be able to name the item the actor is holding"
    assert "bag" not in [entry["id"] for entry in x["items"]]
    assert x["character"]["holds"] == [{"id": "bag", "name": "背包"}]


def test_events_are_room_scoped_ordered_and_perceivable():
    state = small_world()
    events = [
        {"seq": 2, "kind": "position", "roomId": "hall", "text": "博到了门口"},
        {"seq": 1, "kind": "appearance", "roomId": "yard", "text": "希的外套湿了"},
    ]
    x = project_x(state, "ann", events=events)
    assert x["recent"] == ["博到了门口"]


def test_event_validation_rejects_engine_logs_and_bad_shapes():
    state = small_world()
    with pytest.raises(ProjectionError):
        project_x(state, "ann", events=[{"seq": 1, "kind": "nonsense", "roomId": "hall", "text": "x"}])
    with pytest.raises(ProjectionError):
        project_x(state, "ann", events=[{"seq": 1, "kind": "position", "roomId": "hall", "text": "a\nb"}])
    clipped = project_x(state, "ann", events=[{"seq": 1, "kind": "position", "roomId": "hall", "text": "长" * 200}])
    assert clipped["recent"][0].endswith("…")
    with pytest.raises(ProjectionError):
        project_x(state, "ann", events=[{"seq": 1, "kind": "position", "roomId": "hall", "text": "博移动到门口"}])
    with pytest.raises(ProjectionError):
        project_x(state, "ann", events=[{"seq": 1, "kind": "task", "roomId": "hall", "text": "任务完成"}])
    with pytest.raises(ProjectionError):
        project_x(state, "nobody")


def test_projection_is_deterministic():
    first = json.dumps(project_x(small_world(), "ann"), ensure_ascii=False, sort_keys=True)
    second = json.dumps(project_x(copy.deepcopy(small_world()), "ann"), ensure_ascii=False, sort_keys=True)
    assert first == second


def test_loader_serializer_accepts_the_row_shape():
    """No second serializer: 04's frozen serializer must render this X as-is."""
    here = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(here))
    from tools import loader

    if not loader.DEFAULT_SERIALIZER.is_file():
        pytest.skip("04 serializer worktree not present")
    module = loader.load_serializer()
    rendered = loader.render_row(module, {"rowId": "test", "x": project_x(small_world(), "ann")})
    assert rendered["chars"] > 0
    assert rendered["candidateIds"] == ["bo", "bag", "key", "note"]
    assert "铜钥匙" in rendered["text"]
    for marker in ("角色：", "目标：", "地点：", "在场：", "物品：", "刚才：", "精神：", "个性：", "候选："):
        assert marker in rendered["text"]
