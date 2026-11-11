"""Tests for transform legality, case assembly and the constructed-row pipeline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from fixtures import small_world  # noqa: E402
from tools import cases, schema, transforms  # noqa: E402

LABELS_FILE = Path("D:/others/Jity/.local/parallel-local-game/results/action-dataset-20261111/labels-v1.json")


def test_move_validates_container_slot_and_cycles():
    state = small_world()
    moved, records = transforms.apply_transforms(
        state, [{"op": "move", "entityId": "ann", "containerId": "yard", "slotId": None}]
    )
    assert moved["characters"]["ann"]["position"]["containerId"] == "yard"
    assert records[0]["op"] == "move"

    with pytest.raises(transforms.TransformError):
        transforms.apply_transforms(state, [{"op": "move", "entityId": "ann", "containerId": "nowhere"}])
    with pytest.raises(transforms.TransformError):
        transforms.apply_transforms(state, [{"op": "move", "entityId": "ann", "containerId": "hall", "slotId": "slot_x"}])
    with pytest.raises(transforms.TransformError):
        transforms.apply_transforms(state, [{"op": "move", "entityId": "bag", "containerId": "note"}])


def test_task_and_description_transforms_are_checked():
    state = small_world()
    moved, _ = transforms.apply_transforms(
        state,
        [
            {"op": "achieveTask", "ownerId": "ann", "taskId": "task_ann_a"},
            {"op": "appearance", "entityId": "ann", "text": "外套扣好了"},
            {"op": "sanity", "entityId": "ann", "value": 70},
        ],
    )
    assert moved["characters"]["ann"]["tasks"]["task_ann_a"]["status"] == "achieved"
    assert moved["characters"]["ann"]["appearanceChanges"][0]["text"] == "外套扣好了"
    assert moved["characters"]["ann"]["sanity"] == 70

    with pytest.raises(transforms.TransformError):
        transforms.apply_transforms(state, [{"op": "achieveTask", "ownerId": "ann", "taskId": "task_bo_a"}])
    with pytest.raises(transforms.TransformError):
        transforms.apply_transforms(state, [{"op": "achieveTask", "ownerId": "bo", "taskId": "task_bo_a"}, {"op": "achieveTask", "ownerId": "bo", "taskId": "task_bo_a"}])
    with pytest.raises(transforms.TransformError):
        transforms.apply_transforms(state, [{"op": "sanity", "entityId": "ann", "value": 120}])
    with pytest.raises(transforms.TransformError):
        transforms.apply_transforms(state, [{"op": "appearance", "entityId": "key", "text": ""}])


def test_supersede_deactivates_the_previous_change():
    state = small_world()
    moved, _ = transforms.apply_transforms(
        state,
        [
            {"op": "appearance", "entityId": "ann", "text": "外套扣好了"},
        ],
    )
    change_id = moved["characters"]["ann"]["appearanceChanges"][0]["id"]
    moved2, _ = transforms.apply_transforms(
        moved, [{"op": "appearance", "entityId": "ann", "text": "外套被扯开", "supersedes": [change_id]}]
    )
    changes = moved2["characters"]["ann"]["appearanceChanges"]
    assert [change["active"] for change in changes] == [False, True]


def test_events_are_room_scoped_and_factual():
    state = small_world()
    moved, records = transforms.apply_transforms(
        state,
        [
            {"op": "move", "entityId": "bo", "containerId": "yard", "slotId": None},
            {"op": "achieveTask", "ownerId": "cy", "taskId": "task_cy_a"},
        ],
    )
    events = transforms.events_from_transforms(moved, records)
    by_kind = {event["kind"]: event for event in events}
    assert by_kind["position"]["roomId"] == "yard"
    assert "博到了庭院" in by_kind["position"]["text"]
    assert set(by_kind) == {"position"}, "engine state changes (tasks, sanity) never become scene sentences"
    # the actor in the hall must not receive either event
    x = __import__("tools.project_x", fromlist=["project_x"]).project_x(moved, "ann", events=events)
    assert x["recent"] == []


def test_verify_constructed_state_detects_a_dangling_position():
    state = small_world()
    state["characters"]["ann"]["position"]["containerId"] = "ghost_room"
    result = transforms.verify_constructed_state(state)
    assert not result["ok"]
    assert any("position container missing" in problem for problem in result["problems"])


def test_build_case_rejects_actor_goals_outside_the_allowed_list():
    case = {"caseId": "x", "base": "s0", "actor": "ann", "transforms": [], "steps": [], "rationale": "r"}
    with pytest.raises(cases.CaseError):
        cases.build_case(case, Path("."), Path("."), allowed_goals={"task_bo_a"})


def test_build_case_produces_a_verified_record(tmp_path):
    root = tmp_path
    (root / "data" / "worlds").mkdir(parents=True)
    world = small_world()
    (root / "data" / "worlds" / "dragon-raja-free-day.world.json").write_text(
        json.dumps(world, ensure_ascii=False), encoding="utf-8"
    )
    case = {
        "caseId": "case-1",
        "base": "s0",
        "actor": "ann",
        "transforms": [{"op": "achieveTask", "ownerId": "ann", "taskId": "task_ann_a"}],
        "steps": [{"action": "观察", "object": "key"}],
        "rationale": "task_ann_b 要求确认钥匙归属，铜钥匙就在门厅",
        "judgmentBasis": ["goal", "scene"],
        "goalsReferenced": ["task_ann_b"],
        "seed": 7,
    }
    built = cases.build_case(case, root, tmp_path / "snapshots", allowed_goals={"task_ann_a", "task_ann_b"})
    record = built["provenance"]
    assert record["source"] == "constructed"
    assert record["base"]["kind"] == "world-s0"
    assert record["verification"]["ok"] is True
    assert record["transformCount"] == 1
    assert record["seed"] == 7
    row = {
        "rowId": "train13-0001",
        "source": "constructed",
        "worldId": built["state"]["worldId"],
        "characterId": "ann",
        "x": built["x"],
        "y": {"steps": case["steps"]},
        "yGroup": schema.group_of_action(schema.load_labels(LABELS_FILE), "观察"),
        "yRationale": case["rationale"],
        "labelSource": "builder-judgment",
        "skipReason": None,
    }
    assert schema.validate_row(row, schema.load_labels(LABELS_FILE)) == []
