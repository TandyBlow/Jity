"""Snapshot provenance: where a row's world state actually came from.

Two source kinds are recorded, and they are never mixed up:

`evidence-snapshot`
    The state was taken from a real product run's committed point state
    (`results/product/evidence/*.json` -> `snapshotAfterTurn.transport`).
    Provenance keeps the evidence file path, its sha256, the JSON pointer to
    the point state, the product's point/round ids and the product's own
    `stateDigest`, plus the sha256 of the extracted snapshot this experiment
    stores. A verifier can re-extract from the evidence file and compare.

`constructed`
    The state was derived from the committed static world (`data/worlds/
    dragon-raja-free-day.world.json`) by an explicit transform sequence.
    Provenance keeps the base file hash, the ordered transforms with an RNG
    seed and the verification results. It is never labelled `replay`.

Nothing here claims a human review: `builder-judgment` labels stay marked as
such until 01 audits them.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from .state_view import canonical_bytes

EPISODE_SCHEMA = "action-dataset-episode-v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def state_digest(state: dict[str, Any]) -> str:
    """This experiment's digest of a snapshot (stable byte form above)."""
    return sha256_bytes(canonical_bytes(state))


def _pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def resolve_pointer(document: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return document
    node = document
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            node = node[int(token)]
        else:
            node = node[token]
    return node


def iter_transports(document: Any, pointer: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield every transport record (a dict with pointStates/points) in a doc."""
    if isinstance(document, dict):
        if isinstance(document.get("pointStates"), dict) and isinstance(document.get("points"), dict):
            yield pointer or "/", document
            return
        for key, value in document.items():
            yield from iter_transports(value, f"{pointer}/{_pointer_token(str(key))}")
    elif isinstance(document, list):
        for index, value in enumerate(document):
            yield from iter_transports(value, f"{pointer}/{index}")


def _narration_texts(transport: dict[str, Any]) -> list[str]:
    narrations = transport.get("narrations")
    if not isinstance(narrations, dict):
        return []
    texts = []
    for entry in narrations.values():
        if isinstance(entry, dict) and isinstance(entry.get("text"), str):
            texts.append(entry["text"])
    return texts


def extract_episodes(evidence_dir: Path) -> list[dict[str, Any]]:
    """Every committed point state in every evidence file, deduplicated.

    The first occurrence wins; later duplicates are recorded as `alsoIn`.
    """
    episodes: dict[str, dict[str, Any]] = {}
    for path in sorted(evidence_dir.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        file_hash = sha256_file(path)
        for transport_pointer, transport in iter_transports(document):
            point_states = transport.get("pointStates") or {}
            points = transport.get("points") or {}
            narrations = _narration_texts(transport)
            for point_id in sorted(point_states):
                record = point_states[point_id]
                state = record.get("state")
                if not isinstance(state, dict) or "characters" not in state:
                    continue
                digest = state_digest(state)
                point = points.get(point_id) or {}
                base = {
                    "sourceKind": "evidence-snapshot",
                    "evidenceFile": f"evidence/{path.name}",
                    "evidenceSha256": file_hash,
                    "pointer": f"{transport_pointer}/pointStates/{_pointer_token(point_id)}",
                    "transportPointer": transport_pointer,
                    "pointId": point_id,
                    "pointSequence": point.get("sequence"),
                    "pointKind": point.get("kind"),
                    "pointTrigger": point.get("trigger"),
                    "roundId": point.get("roundId"),
                    "advanceId": point.get("advanceId"),
                    "timeAdvance": point.get("timeAdvance"),
                    "entityDeltas": point.get("entityDeltas"),
                    "recordedStateDigest": record.get("stateDigest"),
                    "worldId": state.get("worldId"),
                    "protagonistId": state.get("protagonistId"),
                    "time": (state.get("time") or {}).get("dateTime"),
                    "snapshotSha256": digest,
                    "transportHealth": {
                        "points": len(points),
                        "pointStates": len(point_states),
                        "narrations": len(narrations),
                    },
                }
                existing = episodes.get(digest)
                if existing is None:
                    episodes[digest] = {
                        "schema": EPISODE_SCHEMA,
                        "provenance": base,
                        "alsoIn": [],
                        "state": state,
                        # Transient: used for the prose-leak check, then dropped
                        # before the snapshot is written to disk.
                        "narrationTexts": narrations,
                    }
                else:
                    existing["alsoIn"].append(
                        {"evidenceFile": base["evidenceFile"], "pointer": base["pointer"], "pointId": point_id}
                    )
    return [episodes[key] for key in sorted(episodes)]


def _state_windows(state: dict[str, Any], window: int) -> set[str]:
    """Every short string window that already exists in the snapshot itself."""
    windows: set[str] = set()
    stack: list[Any] = [state]
    while stack:
        value = stack.pop()
        if isinstance(value, str):
            for start in range(max(0, len(value) - window + 1)):
                windows.add(value[start : start + window])
        elif isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return windows


def string_values(value: Any) -> list[str]:
    """Every string inside a JSON value, in traversal order."""
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for key, item in node.items():
                parts.append(str(key))
                walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return parts


def narration_leak_check(
    texts: list[str],
    values: list[str],
    state: dict[str, Any] | None = None,
    window: int = 8,
) -> dict[str, Any]:
    """Report whether narration-only wording survived into a rendered X.

    Narration is generated *from* the state, so plain string overlap is
    expected (a location's own description reappears in prose). Only a window
    that exists in the narration but nowhere in the snapshot counts: that is
    what copying prior prose would look like. This still does not prove the
    absence of all prose, only the absence of narration-only wording.
    """
    if not texts:
        return {"narrations": 0, "window": window, "overlap": 0, "sample": None, "stateOnlyWindows": True}
    joined = "\n".join(texts)
    known = _state_windows(state or {}, window)
    suspect = {
        joined[start : start + window]
        for start in range(max(0, len(joined) - window + 1))
        if joined[start : start + window] not in known
    }
    for value in values:
        for start in range(max(0, len(value) - window + 1)):
            fragment = value[start : start + window]
            if fragment not in suspect:
                continue
            return {
                "narrations": len(texts),
                "window": window,
                "overlap": 1,
                "sample": fragment,
                "stateOnlyWindows": False,
            }
    return {"narrations": len(texts), "window": window, "overlap": 0, "sample": None, "stateOnlyWindows": False}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
