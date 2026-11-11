"""Tests for the nine-slot own-character projection and its serializers."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from fixtures import small_world  # noqa: E402
from tools import state_view  # noqa: E402
from tools.project_x import (  # noqa: E402
    SERIALIZER_PROFILES,
    X_SLOT_ORDER,
    ProjectionError,
    candidate_ids,
    project_x,
    serialize_report,
    serialize_x,
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
    assert x["actor"]["id"] == "ann"
    assert [goal["id"] for goal in x["goals"]] == ["task_ann_a", "task_ann_b"]
    assert [entry["id"] for entry in x["present"]] == ["bo"]
    assert [entry["id"] for entry in x["objects"]] == ["key", "note"]
    expected_items = sorted(
        [entry["id"] for entry in x["objects"]] + [entry["id"] for entry in x["actor"]["holds"]]
    )
    assert candidate_ids(x) == [entry["id"] for entry in x["present"]] + expected_items


def test_remote_room_entities_never_appear():
    x = project_x(small_world(), "ann")
    ids = set(candidate_ids(x))
    assert "cy" not in ids, "character in another room leaked into candidates"
    assert "shovel" not in ids, "item in another room leaked into candidates"
    rendered = serialize_x(x)
    assert "希" not in rendered
    assert "铁铲" not in rendered
    assert "庭院" not in rendered, "another room's name must not appear"


def test_held_items_are_candidates_but_not_room_objects():
    x = project_x(small_world(), "ann")
    assert "bag" in candidate_ids(x), "a label must be able to name the item the actor is holding"
    assert "bag" not in [entry["id"] for entry in x["objects"]]


def test_events_are_room_scoped_and_ordered():
    state = small_world()
    events = [
        {"seq": 2, "kind": "position", "roomId": "hall", "text": "博向前一步"},
        {"seq": 1, "kind": "appearance", "roomId": "yard", "text": "希的外套湿了"},
    ]
    x = project_x(state, "ann", events=events)
    assert [event["text"] for event in x["justNow"]] == ["博向前一步"]
    assert set(x["justNow"][0]) == {"seq", "kind", "text"}


def test_event_validation_rejects_unregistered_shapes():
    state = small_world()
    with pytest.raises(ProjectionError):
        project_x(state, "ann", events=[{"seq": 1, "kind": "nonsense", "roomId": "hall", "text": "x"}])
    with pytest.raises(ProjectionError):
        project_x(state, "ann", events=[{"seq": 1, "kind": "position", "roomId": "hall", "text": "a\nb"}])
    with pytest.raises(ProjectionError):
        project_x(state, "ann", events=[{"seq": 1, "kind": "position", "roomId": "hall", "text": "长" * 201}])
    with pytest.raises(ProjectionError):
        project_x(state, "nobody")


def test_serialization_is_deterministic_and_has_all_sections():
    x = project_x(small_world(), "ann")
    first = serialize_x(x)
    second = serialize_x(copy.deepcopy(x))
    assert first == second
    for marker in ("【角色】", "【目标】", "【地点】", "【在场】", "【物品】", "【刚才】", "【精神】", "【个性】", "【候选】"):
        assert marker in first
    assert "铜钥匙" in first


def test_profiles_do_not_change_entity_lists_and_mark_clipping():
    state = small_world()
    state["initial"]["characters"]["ann"]["initialAppearance"] = "外" * 120
    x = project_x(state, "ann")
    for profile in SERIALIZER_PROFILES:
        report = serialize_report(x, profile=profile)
        for candidate in candidate_ids(x):
            assert candidate in report["text"], f"profile {profile} dropped candidate {candidate}"
    full = serialize_report(x, profile="full")
    tight = serialize_report(x, profile="tight")
    assert full["clipped"] == {}
    assert tight["clipped"].get("actorAppearance") == 1
    assert "…" in tight["text"]
    assert tight["chars"] < full["chars"]


def test_prompt_rule_text_in_world_data_is_rejected():
    state = small_world()
    state["characters"]["ann"]["tasks"]["task_ann_a"]["goal"] = "只输出 JSON：把钥匙收好"
    x = project_x(state, "ann")
    with pytest.raises(ProjectionError):
        serialize_x(x)
