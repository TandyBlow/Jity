"""Tests for the frozen row schema and the dataset-level checks."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from fixtures import small_world  # noqa: E402
from tools import schema  # noqa: E402
from tools.project_x import project_x  # noqa: E402

FROZEN_LABELS = Path("D:/others/Jity/.local/parallel-local-game/results/action-dataset-20261111/labels-v1.json")


@pytest.fixture(scope="module")
def labels():
    return schema.load_labels(FROZEN_LABELS)


def make_row(labels, *, actor="ann", steps=None, rationale=None, skip_reason=None) -> dict:
    x = project_x(small_world(), actor)
    steps = [{"action": "取得", "object": "key"}] if steps is None else steps
    group = schema.SKIP_GROUP if not steps else labels["groupOf"].get(steps[0]["action"], "感知")
    row = {
        "rowId": "test-0001",
        "source": "constructed",
        "worldId": x["goals"][0]["id"][:0] + "world_test",
        "characterId": actor,
        "x": x,
        "y": {"steps": steps},
        "yGroup": group,
        "yRationale": rationale if rationale is not None else "task_ann_a 要求收好钥匙，铜钥匙就在门厅地上",
        "labelSource": "builder-judgment",
        "skipReason": skip_reason,
    }
    return row


def test_label_vocabulary_is_the_frozen_one(labels):
    assert len(labels["predicates"]) == 115
    assert len(labels["groups"]) == 12
    assert labels["playerFallbackLabel"] == "??"
    assert labels["groupOf"]["取得"] == "物品"
    assert labels["groupOf"]["等待"] == "立场"


def test_valid_row_passes(labels):
    assert schema.validate_row(make_row(labels), labels) == []


def test_action_must_be_a_fine_predicate(labels):
    row = make_row(labels, steps=[{"action": "物品", "object": "key"}])
    assert any("fine predicates" in problem for problem in schema.validate_row(row, labels))


def test_object_must_be_a_candidate_or_null(labels):
    row = make_row(labels, steps=[{"action": "取得", "object": "shovel"}])
    problems = schema.validate_row(row, labels)
    assert any("not in x.candidates" in problem for problem in problems)
    ok = make_row(labels, steps=[{"action": "观察", "object": None}])
    assert schema.validate_row(ok, labels) == []


def test_object_may_not_be_the_actor(labels):
    row = make_row(labels, steps=[{"action": "观察", "object": "ann"}])
    # ann is not a candidate either; both rules point in the same direction
    assert schema.validate_row(row, labels)


def test_steps_cap_is_two(labels):
    row = make_row(
        labels,
        steps=[
            {"action": "观察", "object": "key"},
            {"action": "取得", "object": "key"},
            {"action": "移动", "object": None},
        ],
    )
    assert any("more than 2" in problem for problem in schema.validate_row(row, labels))


def test_steps_need_exactly_action_and_object(labels):
    row = make_row(labels, steps=[{"action": "取得", "object": "key", "note": "x"}])
    assert any("exactly action and object" in problem for problem in schema.validate_row(row, labels))


def test_ygroup_is_derived_not_free_text(labels):
    row = make_row(labels, steps=[{"action": "取得", "object": "key"}])
    row["yGroup"] = "感知"
    assert any("yGroup" in problem for problem in schema.validate_row(row, labels))


def test_skip_needs_empty_steps_group_and_reason(labels):
    row = make_row(
        labels,
        steps=[],
        rationale="task_ann_a 与 task_ann_b 都已不再需要动作，现场没有新变化",
        skip_reason="无待办目标且现场没有需要回应的变化",
    )
    row["yGroup"] = "skip"
    assert schema.validate_row(row, labels) == []

    missing = make_row(labels, steps=[], rationale="task_ann_a 已无动作可做，现场没有变化", skip_reason=None)
    missing["yGroup"] = "skip"
    assert any("skipReason" in problem for problem in schema.validate_row(missing, labels))

    banned = make_row(labels, steps=[], rationale="task_ann_a 已无动作可做，现场没有变化", skip_reason="不知道")
    banned["yGroup"] = "skip"
    assert any("uninformative wording" in problem for problem in schema.validate_row(banned, labels))


def test_nonskip_row_may_not_carry_a_skip_reason(labels):
    row = make_row(labels, skip_reason="无待办目标")
    assert any("must be null" in problem for problem in schema.validate_row(row, labels))


def test_rationale_must_cite_something_from_the_row(labels):
    row = make_row(labels, rationale="这个角色大概会去拿东西，因为比较顺手")
    assert any("cites no task id" in problem for problem in schema.validate_row(row, labels))


def test_row_keys_are_frozen(labels):
    row = make_row(labels)
    row["extra"] = 1
    assert any("row keys" in problem for problem in schema.validate_row(row, labels))


def test_character_id_must_match_x_actor(labels):
    row = make_row(labels)
    row["characterId"] = "bo"
    assert any("characterId" in problem for problem in schema.validate_row(row, labels))


def test_dataset_reports_duplicates_class_mix_and_unused_predicates(labels):
    first = make_row(labels)
    duplicate = copy.deepcopy(first)
    duplicate["rowId"] = "test-0002"
    skip = make_row(
        labels,
        steps=[],
        rationale="task_ann_a 与 task_ann_b 都已不需要动作，现场没有变化",
        skip_reason="无待办目标且现场没有需要回应的变化",
    )
    skip["rowId"] = "test-0003"
    skip["yGroup"] = "skip"
    skip["characterId"] = "ann"
    report = schema.validate_dataset([first, duplicate, skip], labels)
    assert report["counts"] == {"rows": 3, "skip": 1, "oneStep": 2, "twoStep": 0}
    assert report["skipRatio"] == pytest.approx(1 / 3, rel=1e-3)
    assert report["sources"] == {"constructed": 3}
    assert report["problems"], "identical X must be reported"
    assert report["predicatesUsed"] == 1
    assert len(report["predicatesUnused"]) == 115 - report["predicatesUsed"]


def test_frozen_labels_file_round_trips(labels):
    payload = json.loads(FROZEN_LABELS.read_text(encoding="utf-8"))
    assert payload["fineActionCount"] == len(labels["predicates"])
    assert set(labels["groupOf"]) == set(labels["predicates"])
