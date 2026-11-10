#!/usr/bin/env python
"""Build browser-kernel differential fixtures from the pinned Python reference.

The reference kernel lives in commit ``fc60a603c7e0b57805fffea0458192bcfebf6ffc``
on the ``world-server`` line. This script extracts that commit's ``backend/app``
into a temporary directory, imports it, and writes the expected merge/apply/
replay/digest values used by ``state.test.ts``, ``canonical.test.ts`` and
``world-loader.test.ts``. It never imports the worktree's own backend.

Run from the repository root:

    python -X utf8 frontend/scripts/parallel-kernel/build-kernel-fixtures.py

The output is deterministic for a fixed reference commit and world file.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REFERENCE_COMMIT = "fc60a603c7e0b57805fffea0458192bcfebf6ffc"
FIXTURE_OUTPUT = Path(__file__).resolve().parent / "fixtures" / "kernel-differential.json"
WORLD_PATH = ROOT / "data" / "worlds" / "dragon-raja-free-day.world.json"

REFERENCE_FILES = (
    "backend/app/schemas/world/canonical.py",
    "backend/app/schemas/world/contracts.py",
    "backend/app/schemas/world/v2/work.py",
    "backend/app/services/world/apply.py",
    "backend/app/services/world/merge.py",
    "backend/app/services/world/preview.py",
    "backend/app/services/world/replay.py",
    "backend/app/services/world/state.py",
    "backend/app/services/world/timing.py",
    "backend/app/services/world/units.py",
    "backend/app/services/world/violations.py",
)


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def reference_hashes() -> list[dict]:
    return [{"path": path, "sha256": hashlib.sha256(git("show", f"{REFERENCE_COMMIT}:{path}")).hexdigest()}
            for path in REFERENCE_FILES]


def extract_reference() -> Path:
    target = Path(tempfile.mkdtemp(prefix="world-kernel-reference-"))
    archive = git("archive", REFERENCE_COMMIT, "backend/app")
    subprocess.run(["tar", "-x", "-C", str(target)], input=archive, check=True)
    return target


def reference_json(path: str) -> dict:
    return json.loads(git("show", f"{REFERENCE_COMMIT}:{path}").decode("utf-8"))


def read_trace(name: str) -> dict:
    return reference_json(f"design/world-protocol/v2/traces/{name}.json")


def instantiate(node, values):
    if isinstance(node, dict):
        if set(node) == {"$var"}:
            return values[node["$var"]]
        return {key: instantiate(item, values) for key, item in node.items()}
    if isinstance(node, list):
        return [instantiate(item, values) for item in node]
    return node


def main() -> int:
    reference = extract_reference()
    sys.path.insert(0, str(reference / "backend"))
    from app.schemas.world.canonical import canonical_bytes, canonical_digest, parse_json  # type: ignore
    from app.schemas.world.contracts import (  # type: ignore
        EntityDelta, TimeAdvance, TimelinePoint, WorldInitialState, WorldState, WorldTime,
    )
    from app.schemas.world.v2.work import SettlementGroup  # type: ignore
    from app.services.world.apply import apply_point  # type: ignore
    from app.services.world.merge import point_entity_deltas  # type: ignore
    from app.services.world.preview import preview_point  # type: ignore
    from app.services.world.replay import replay_world  # type: ignore
    from app.services.world.state import build_initial_state, state_digest  # type: ignore
    from app.services.world.timing import advance_time  # type: ignore
    from app.services.world.violations import KernelViolation  # type: ignore

    creation = read_trace("T01")["steps"][0]["request"]["initial"]
    school_initial = {"worldId": "world_school", **creation}
    school_state = build_initial_state(WorldInitialState.model_validate(school_initial))
    t01 = read_trace("T01")
    values = t01["samples"][0]["values"]
    commit = next(step for step in t01["steps"]
                  if step.get("operation") == "commit_point" and step.get("responseKind") == "success")
    commit_request = instantiate(commit["request"], values)
    normal_groups = [SettlementGroup.model_validate(group) for group in commit_request["settlementGroups"]]
    normal_point = TimelinePoint.model_validate(commit_request["point"])
    normal_merged = point_entity_deltas(normal_groups, None)
    normal_after = apply_point(school_state, normal_point)

    preview_step = next(step for step in t01["steps"] if step["id"] == "s16")
    preview_request = instantiate(preview_step["request"], values)
    preview_groups = [SettlementGroup.model_validate(group) for group in preview_request["settlementGroups"]]
    preview_response = instantiate(preview_step["response"], values)
    preview = preview_point(school_state,
                            TimelinePoint.model_validate(preview_response["data"]["pointProjection"]),
                            preview_groups)

    fixture_initial = reference_json("backend/tests/fixtures/world/pure-removal.json")["initial"]
    fixture_state = build_initial_state(WorldInitialState.model_validate(fixture_initial))

    multi_initial = json.loads(json.dumps(fixture_initial, ensure_ascii=False))
    multi_initial["locations"]["room_b"] = {
        "id": "room_b", "name": "B 房间", "parentLocationId": None,
        "initialAppearance": "另一间", "slots": [],
    }
    multi_initial["items"]["item_b"] = {
        "id": "item_b", "name": "石凳",
        "initialPosition": {"containerId": "room_b", "slotId": None, "relativeTo": None},
        "initialAppearance": "冰冷", "slots": [],
    }
    multi_state = build_initial_state(WorldInitialState.model_validate(multi_initial))

    def point(state, point_id, sequence, advance, deltas, kind="normal", previous="p_prev"):
        return TimelinePoint.model_validate({
            "worldId": state.worldId, "id": point_id, "sequence": sequence, "kind": kind,
            "previousPointId": "root_0" if sequence == 1 else previous,
            "roundId": "round_f", "advanceId": "advance_f", "trigger": "player",
            "linkedFromPointId": None if kind == "normal" else "root_0",
            "timeAdvance": advance,
            "entityDeltas": deltas,
        })

    def elapsed(amount):
        return {"boundary": "elapsed", "duration": {"amount": amount, "unit": "second"}}

    def outcome(initial, apply, deltas):
        entry = {"initial": initial, "deltas": deltas}
        try:
            final = apply(deltas)
        except KernelViolation as error:
            entry["expected"] = {"refused": error.kind.value}
        except Exception as error:  # pydantic ValidationError
            entry["expected"] = {"refused": "schema", "detail": str(error).splitlines()[0]}
        else:
            entry["expected"] = {"stateDigest": state_digest(final)}
        return entry

    def position_case(name, initial, state, deltas):
        return {"name": name, **outcome(
            initial,
            lambda value: apply_point(state, point(state, "p1", 1, elapsed(1), value)),
            deltas)}

    position_cases = [
        position_case("unknown_container", fixture_initial, fixture_state,
                      {"person_a": {"entityId": "person_a",
                                    "positionSet": {"containerId": "room_missing", "slotId": None, "relativeTo": None}}}),
        position_case("slot_outside_container", fixture_initial, fixture_state,
                      {"person_a": {"entityId": "person_a",
                                    "positionSet": {"containerId": "room_a", "slotId": "nope", "relativeTo": None}}}),
        position_case("unknown_relative", fixture_initial, fixture_state,
                      {"person_a": {"entityId": "person_a",
                                    "positionSet": {"containerId": "room_a", "slotId": None,
                                                    "relativeTo": {"entityId": "ghost", "relation": "beside"}}}}),
        position_case("cross_room_relative", multi_initial, multi_state,
                      {"person_a": {"entityId": "person_a",
                                    "positionSet": {"containerId": "room_a", "slotId": None,
                                                    "relativeTo": {"entityId": "item_b", "relation": "beside"}}}}),
        position_case("self_container_cycle", fixture_initial, fixture_state,
                      {"person_a": {"entityId": "person_a",
                                    "positionSet": {"containerId": "person_a", "slotId": None, "relativeTo": None}}}),
        position_case("mixed_relative_container_cycle", multi_initial, multi_state, {
            "person_a": {"entityId": "person_a",
                         "positionSet": {"containerId": "room_a", "slotId": None,
                                         "relativeTo": {"entityId": "item_a", "relation": "beside"}}},
            "item_a": {"entityId": "item_a",
                       "positionSet": {"containerId": "person_a", "slotId": None, "relativeTo": None}},
        }),
        position_case("same_room_relative_accepted", fixture_initial, fixture_state,
                      {"person_a": {"entityId": "person_a",
                                    "positionSet": {"containerId": "room_a", "slotId": None,
                                                    "relativeTo": {"entityId": "item_a", "relation": "beside"}}}}),
        position_case("relative_reference_moves_with_target", multi_initial, multi_state, {
            "person_a": {"entityId": "person_a",
                         "positionSet": {"containerId": "room_b", "slotId": None,
                                         "relativeTo": {"entityId": "item_a", "relation": "beside"}}},
            "item_a": {"entityId": "item_a",
                       "positionSet": {"containerId": "room_b", "slotId": None, "relativeTo": None}},
        }),
    ]

    person_move = {"entityId": "person_a", "positionSet": {
        "containerId": "room_b", "slotId": None,
        "relativeTo": {"entityId": "item_a", "relation": "beside"}}}
    item_move = {"entityId": "item_a", "positionSet": {
        "containerId": "room_b", "slotId": None, "relativeTo": None}}
    joint_orders = []
    for deltas in ({"person_a": person_move, "item_a": item_move},
                   {"item_a": item_move, "person_a": person_move}):
        final = apply_point(multi_state, point(multi_state, "p1", 1, elapsed(1), deltas))
        joint_orders.append({"deltas": deltas, "stateDigest": state_digest(final)})

    relative_settled = apply_point(multi_state, point(multi_state, "p1", 1, elapsed(1), {
        "person_a": {"entityId": "person_a", "positionSet": {
            "containerId": "room_b", "slotId": None,
            "relativeTo": {"entityId": "item_a", "relation": "beside"}}},
        "item_a": {"entityId": "item_a", "positionSet": {
            "containerId": "room_b", "slotId": None, "relativeTo": None}},
    }))
    dangling = outcome(multi_initial,
                       lambda value: apply_point(relative_settled,
                                                 point(relative_settled, "p2", 2, elapsed(1), value)),
                       {"item_a": {"entityId": "item_a", "positionSet": {
                           "containerId": "room_a", "slotId": None, "relativeTo": None}}})

    collapse_trace = read_trace("T03-collapse")
    collapse = next(step for step in collapse_trace["steps"]
                    if step.get("operation") == "commit_point" and step.get("responseKind") == "success")
    collapse_request = instantiate(collapse["request"], collapse_trace["samples"][0]["values"])
    collapse_groups = [SettlementGroup.model_validate(group) for group in collapse_request["settlementGroups"]]
    collapse_merged = point_entity_deltas(collapse_groups, None)

    hierarchy_added = [
        {"id": "task_child", "ownerId": "person_a", "parentTaskId": "task_parent",
         "goal": "子任务", "status": "pending"},
        {"id": "task_parent", "ownerId": "person_a", "parentTaskId": "task_a",
         "goal": "父任务", "status": "pending"},
        {"id": "task_grandchild", "ownerId": "person_a", "parentTaskId": "task_child",
         "goal": "孙任务", "status": "pending"},
    ]
    hierarchy_group = SettlementGroup.model_validate({
        "groupId": "group_hierarchy", "actorIds": ["person_a"], "positions": {},
        "appearances": {}, "tasksAchieved": {"person_a": ["task_grandchild"]},
        "subtasksAdded": {"person_a": hierarchy_added}, "personalities": {}, "sanities": {},
        "taskCoverageIds": ["person_a"], "personalityCoverageIds": [],
    })
    hierarchy_merged = point_entity_deltas([hierarchy_group], None)
    hierarchy_state = apply_point(fixture_state,
                                  point(fixture_state, "p1", 1, elapsed(1), hierarchy_merged))

    def group(added=(), achieved=(), appearances=None, personalities=None, sanities=None,
              group_id="group_case"):
        return SettlementGroup.model_validate({
            "groupId": group_id, "actorIds": ["person_a"], "positions": {},
            "appearances": appearances or {},
            "tasksAchieved": {"person_a": list(achieved)} if achieved else {},
            "subtasksAdded": {"person_a": list(added)} if added else {},
            "personalities": personalities or {}, "sanities": sanities or {},
            "taskCoverageIds": ["person_a"],
            "personalityCoverageIds": ["person_a"] if personalities else [],
        })

    def merge_refusal(units):
        try:
            point_entity_deltas(units, None)
        except Exception as error:  # pydantic ValidationError or KernelViolation
            kind = getattr(error, "kind", None)
            return {"refused": getattr(kind, "value", "schema"),
                    "detail": str(error).splitlines()[0]}
        raise AssertionError("expected the merge to be refused")

    cycle_group = group(added=[
        {"id": "t_a", "ownerId": "person_a", "parentTaskId": "t_b", "goal": "a", "status": "pending"},
        {"id": "t_b", "ownerId": "person_a", "parentTaskId": "t_a", "goal": "b", "status": "pending"},
    ])
    duplicate_group = group(added=[
        {"id": "t_a", "ownerId": "person_a", "parentTaskId": "task_a", "goal": "a", "status": "pending"},
        {"id": "t_a", "ownerId": "person_a", "parentTaskId": "task_a", "goal": "b", "status": "pending"},
    ])
    task_cases = [
        {"name": "hierarchy_level_order", "groups": [hierarchy_group.model_dump(mode="json")],
         "expected": {"merged": {key: delta.model_dump(mode="json")
                                 for key, delta in hierarchy_merged.items()},
                      "stateDigest": state_digest(hierarchy_state)}},
        {"name": "cycle_refused", "groups": [cycle_group.model_dump(mode="json")],
         "expected": merge_refusal([cycle_group])},
        {"name": "duplicate_added_refused", "groups": [duplicate_group.model_dump(mode="json")],
         "expected": merge_refusal([duplicate_group])},
    ]

    pure_removal = reference_json("backend/tests/fixtures/world/pure-removal.json")
    pure_removal_points = []
    for entry in pure_removal["points"]:
        deltas = {key: EntityDelta.model_validate(delta) for key, delta in entry["deltas"].items()}
        pure_removal_points.append(point(
            fixture_state, entry["pointId"], entry["sequence"],
            TimeAdvance.model_validate(entry["timeAdvance"]), deltas).model_dump(mode="json"))
    pure_removal_final = replay_world(
        fixture_state, [TimelinePoint.model_validate(entry) for entry in pure_removal_points])

    same_point_groups = [
        group(appearances={"person_a": [{"id": "ch_x", "text": "第一句", "supersedes": []}]},
              group_id="g1"),
        group(appearances={"person_a": [{"id": "ch_y", "text": "第二句", "supersedes": ["ch_x"]}]},
              group_id="g2"),
    ]
    same_point = merge_refusal(same_point_groups)
    empty_removal_group = SettlementGroup.model_construct(
        groupId="group_empty_removal", actorIds=["person_a"], positions={},
        appearances={"person_a": [{"id": "ch_x", "text": None, "supersedes": []}]},
        tasksAchieved={}, subtasksAdded={}, personalities={}, sanities={},
        taskCoverageIds=["person_a"], personalityCoverageIds=[])
    try:
        point_entity_deltas([empty_removal_group], None)
    except Exception as error:
        pure_removal_without_supersedes = {"refused": "schema",
                                           "detail": str(error).splitlines()[0]}
    else:
        raise AssertionError("pure removal without supersedes must be refused")

    try:
        apply_point(fixture_state, point(fixture_state, "p1", 1, elapsed(1), {
            "item_a": {"entityId": "item_a",
                       "appearanceChanges": [{"id": "ch_2", "text": None, "supersedes": ["ch_1"]}]},
        }))
    except KernelViolation as error:
        unknown_supersede = {"refused": error.kind.value}
    else:
        raise AssertionError("superseding an unknown active change must be refused")

    month_end = reference_json("backend/tests/fixtures/world/month-end-cases.json")["cases"]
    time_cases = []
    for case in month_end:
        at = WorldTime.model_validate({"calendar": "gregorian", "dateTime": case["from"],
                                       "instantOrdinal": 5})
        advanced = advance_time(at, TimeAdvance.model_validate(case["advance"]))
        time_cases.append({"from": case["from"], "advance": case["advance"],
                           "expected": {"dateTime": advanced.dateTime,
                                        "ordinal": advanced.instantOrdinal}})

    world_bytes = WORLD_PATH.read_bytes().replace(b"\r\n", b"\n")
    world_text = world_bytes.decode("utf-8")
    world = WorldState.model_validate(parse_json(world_text))
    world_s0 = build_initial_state(world.initial)
    assert world.model_dump(mode="json") == world_s0.model_dump(mode="json")

    canonical_samples = [
        {"value": {"b": 1, "a": [True, None, "中文"]}},
        {"value": {"\u0001": 1, "\u007f": 2}},
        {"value": "quote\" backslash\\ control\u0001 tab\t newline\n \u2028 \U0001F600"},
        {"value": [0, -0, 9007199254740991, -9007199254740991]},
    ]
    for sample in canonical_samples:
        sample["canonical"] = canonical_bytes(sample["value"]).decode("utf-8")
        sample["sha256"] = canonical_digest(sample["value"])

    fixture = {
        "format": "parallel-kernel-differential-v1",
        "source": {
            "referenceCommit": REFERENCE_COMMIT,
            "generator": "frontend/scripts/parallel-kernel/build-kernel-fixtures.py",
            "files": reference_hashes(),
            "world": {
                "path": WORLD_PATH.relative_to(ROOT).as_posix(),
                "textSha256Lf": hashlib.sha256(world_bytes).hexdigest(),
                "rawSha256": hashlib.sha256(WORLD_PATH.read_bytes()).hexdigest(),
                "stateDigest": state_digest(world),
                "initialDigest": canonical_digest(world.initial.model_dump(mode="json")),
                "counts": {
                    "locations": len(world.locations),
                    "items": len(world.items),
                    "characters": len(world.characters),
                    "tasks": sum(len(character.tasks) for character in world.characters.values()),
                },
            },
        },
        "worlds": {
            "school": school_initial,
            "fixture": fixture_initial,
            "multi": multi_initial,
        },
        "canonical": canonical_samples,
        "normal": {
            "initial": school_initial,
            "stateDigestBefore": state_digest(school_state),
            "groups": [group.model_dump(mode="json") for group in normal_groups],
            "point": normal_point.model_dump(mode="json"),
            "mergedEntityDeltas": {key: delta.model_dump(mode="json")
                                   for key, delta in normal_merged.items()},
            "stateAfter": normal_after.model_dump(mode="json"),
            "stateDigestAfter": state_digest(normal_after),
        },
        "preview": {
            "initial": school_initial,
            "pointProjection": preview["pointProjection"],
            "mergedEntityDeltas": preview["mergedEntityDeltas"],
            "workingStateDigest": preview["workingStateDigest"],
            "pointProjectionDigest": preview["pointProjectionDigest"],
            "workingState": preview["workingState"],
        },
        "positions": {
            "fixtureInitial": fixture_initial,
            "multiInitial": multi_initial,
            "cases": position_cases,
            "jointOrders": joint_orders,
            "dangling": dangling,
        },
        "tasks": {
            "fixtureInitial": fixture_initial,
            "collapse": {
                "groups": [group.model_dump(mode="json") for group in collapse_groups],
                "mergedEntityDeltas": {key: delta.model_dump(mode="json")
                                       for key, delta in collapse_merged.items()},
            },
            "cases": task_cases,
        },
        "supersedes": {
            "fixtureInitial": fixture_initial,
            "points": pure_removal_points,
            "finalState": pure_removal_final.model_dump(mode="json"),
            "finalStateDigest": state_digest(pure_removal_final),
            "samePointRefused": same_point,
            "samePointGroups": [entry.model_dump(mode="json") for entry in same_point_groups],
            "pureRemovalWithoutSupersedes": pure_removal_without_supersedes,
            "emptyRemovalGroups": [empty_removal_group.model_dump(mode="json")],
            "unknownSupersede": unknown_supersede,
        },
        "time": {"cases": time_cases},
    }
    FIXTURE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_OUTPUT.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")
    print(json.dumps({"fixture": FIXTURE_OUTPUT.relative_to(ROOT).as_posix(),
                      "bytes": FIXTURE_OUTPUT.stat().st_size,
                      "sha256": hashlib.sha256(FIXTURE_OUTPUT.read_bytes()).hexdigest()},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
