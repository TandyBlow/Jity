"""Constructed-scenario assembly and its recorded verification.

A *case* is one authored judgement plus the state it is judged in:

    {
      "caseId": "c-0001",
      "base": "s0" | "snapshot:<sha-prefix>",
      "actor": "chu",
      "transforms": [ ... ],
      "steps": [{"action": "...", "object": "..."}],
      "rationale": "...",
      "skipReason": null,
      "judgmentBasis": ["goal", "scene"]
    }

`build_case` turns that into the final state, the room-scoped `刚才` events and
a verification record. It never reads a label to build the state: an authored
step cannot influence X except through an explicit transform, and the
verification lists every transform that was applied.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import provenance, state_view, transforms
from .project_x import project_x

WORLD_RELATIVE = "data/worlds/dragon-raja-free-day.world.json"


class CaseError(ValueError):
    """Raised when an authored case cannot be built or verified."""


def load_world(worktree_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = worktree_root / WORLD_RELATIVE
    if not path.is_file():
        raise CaseError(f"world file missing: {path}")
    state = json.loads(path.read_text(encoding="utf-8"))
    meta = {
        "kind": "world-s0",
        "file": WORLD_RELATIVE,
        "sha256": provenance.sha256_file(path),
        "stateDigest": provenance.state_digest(state),
    }
    return state, meta


def load_snapshot(snapshot_dir: Path, prefix: str) -> tuple[dict[str, Any], dict[str, Any]]:
    matches = sorted(snapshot_dir.glob(f"{prefix}*.json"))
    matches = [path for path in matches if path.name != "index.json"]
    if len(matches) != 1:
        raise CaseError(f"snapshot prefix {prefix!r} matched {len(matches)} files")
    payload = provenance.read_json(matches[0])
    state = payload["state"]
    meta = {
        "kind": "snapshot",
        "file": f"snapshots/{matches[0].name}",
        "sha256": provenance.sha256_file(matches[0]),
        "stateDigest": provenance.state_digest(state),
        "episode": payload.get("provenance"),
        "snapshotSha256": payload.get("provenance", {}).get("snapshotSha256"),
        "copies": payload.get("copies") or [],
    }
    return state, meta


def resolve_base(case: dict[str, Any], worktree_root: Path, snapshot_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    base = str(case["base"])
    if base == "s0":
        return load_world(worktree_root)
    if base.startswith("snapshot:"):
        return load_snapshot(snapshot_dir, base.split(":", 1)[1])
    raise CaseError(f"unknown base {base!r} in case {case.get('caseId')}")


def events_from_committed_deltas(state: dict[str, Any], deltas: dict | None) -> list[dict[str, Any]]:
    """Perceivable happenings of the committed point that produced this state.

    A changed position becomes "X 换了位置，现在在<label>"; a changed appearance
    becomes "X：<visible description>". Task and sanity deltas are engine state,
    not scene happenings, so they are not turned into `刚才` lines. The room is
    the entity's room after the delta, so a character never learns about
    another room.
    """
    if not deltas:
        return []
    events: list[dict[str, Any]] = []
    seq = 0
    for entity_id in sorted(deltas):
        delta = deltas[entity_id] or {}
        seq += 1
        name = state_view.entity_name(state, entity_id)
        room_id = state_view.room_of(state, entity_id)
        if delta.get("positionSet"):
            if delta["positionSet"]["containerId"] in state["initial"]["locations"]:
                label = state_view.location_name(state, delta["positionSet"]["containerId"])
            else:
                label = state_view.position_label(state, entity_id)
            events.append(
                {
                    "seq": seq,
                    "kind": "position",
                    "roomId": room_id,
                    "text": f"{name}换了位置，现在在{label}",
                }
            )
        for change in delta.get("appearanceChanges") or []:
            if change.get("active", True) and change.get("text"):
                events.append(
                    {
                        "seq": seq,
                        "kind": "appearance",
                        "roomId": room_id,
                        "text": f"{name}：{change['text']}",
                    }
                )
    return events


def project_case_state(
    base_state: dict[str, Any],
    base_meta: dict[str, Any],
    actor: str,
    transform_list: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply transforms and build the events list, deterministically.

    Shared by `build_case` and the independent checker, so replaying a row is
    the same computation that produced it.
    """
    state, records = transforms.apply_transforms(base_state, transform_list)
    committed = events_from_committed_deltas(state, (base_meta.get("episode") or {}).get("entityDeltas"))
    later = transforms.events_from_transforms(state, records)
    offset = max((event["seq"] for event in committed), default=0)
    combined = committed + [
        {"seq": event["seq"] + offset, "kind": event["kind"], "roomId": event["roomId"], "text": event["text"]}
        for event in later
    ]
    return state, records, combined


def build_case(case: dict[str, Any], worktree_root: Path, snapshot_dir: Path, allowed_goals: set[str]) -> dict[str, Any]:
    base_state, base_meta = resolve_base(case, worktree_root, snapshot_dir)
    state, records, events = project_case_state(
        base_state, base_meta, case["actor"], case.get("transforms") or []
    )
    verification = transforms.verify_constructed_state(state)
    actor = case["actor"]
    if actor not in state["characters"]:
        raise CaseError(f"case {case['caseId']}: unknown actor {actor}")
    x = project_x(state, actor, events=events)

    actor_goals = [str(goal).split("：", 1)[0] for goal in x["goals"]]
    outside = [goal for goal in actor_goals if goal not in allowed_goals]
    if outside:
        raise CaseError(f"case {case['caseId']}: actor goals outside the allowed TRAIN list: {outside}")
    referenced = [goal for goal in case.get("goalsReferenced") or [] if goal not in allowed_goals]
    if referenced:
        raise CaseError(f"case {case['caseId']}: rationale references held-out goals: {referenced}")
    for goal in case.get("goalsReferenced") or []:
        if goal not in actor_goals:
            raise CaseError(f"case {case['caseId']}: references goal {goal} not pending for {actor}")

    has_transforms = bool(records)
    if base_meta["kind"] == "snapshot":
        source = "evidence-snapshot"
        derivation = "committed-snapshot+transforms" if has_transforms else "committed-snapshot"
    else:
        source = "constructed"
        derivation = "world-s0+transforms"
    provenance_record = {
        "caseId": case["caseId"],
        "source": source,
        "derivation": derivation,
        "base": base_meta,
        "seed": case.get("seed"),
        "transformCount": len(records),
        "transformsInput": case.get("transforms") or [],
        "transforms": records,
        "verification": {
            "ok": verification["ok"],
            "problems": verification["problems"],
            "checks": [
                "transform legality (entities, containers, slots, task ownership)",
                "container graph has no cycles and every entity resolves to a location",
                "sanity within 0..100 and task parent links intact",
                "actor's pending goals all inside the allowed TRAIN list",
            ],
        },
        "labelCheck": {
            "candidates": [entry["id"] for entry in x["candidates"]],
            "goalIds": actor_goals,
        },
        "x": {
            "sha256": hashlib.sha256(
                json.dumps(x, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        },
        "judgmentBasis": case.get("judgmentBasis") or ["goal"],
        "goalsReferenced": case.get("goalsReferenced") or [],
        "actorRoom": state_view.room_of(state, actor),
        "roomName": state_view.location_name(state, state_view.room_of(state, actor)),
        "judgedFromFacts": case.get("facts") or [],
    }
    if not verification["ok"]:
        raise CaseError(f"case {case['caseId']} failed verification: {verification['problems']}")
    return {"state": state, "x": x, "provenance": provenance_record}
