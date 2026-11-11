"""Tests for provenance extraction, hashing and the prose-leak guard."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from fixtures import small_world  # noqa: E402
from tools import provenance  # noqa: E402
from tools.project_x import project_x, serialize_x  # noqa: E402


def test_canonical_digest_is_key_order_independent():
    first = {"b": 1, "a": [1, 2, {"c": "文字"}]}
    second = {"a": [1, 2, {"c": "文字"}], "b": 1}
    assert provenance.sha256_bytes(provenance.canonical_bytes(first)) == provenance.sha256_bytes(
        provenance.canonical_bytes(second)
    )


def test_pointer_resolution_escapes():
    document = {"a/b": {"c~d": [10, 20]}}
    assert provenance.resolve_pointer(document, "/a~1b/c~0d/1") == 20


def _write_evidence(directory: Path, world: dict, narrations: list[str]) -> Path:
    transport = {
        "worldId": world["worldId"],
        "state": world,
        "points": {
            "point_root": {"worldId": world["worldId"], "id": "point_root", "sequence": 0, "kind": "root", "trigger": "player"},
        },
        "pointStates": {"point_root": {"version": 0, "state": world, "stateDigest": "d0"}},
        "narrations": {f"n{index}": {"status": "ready", "text": text} for index, text in enumerate(narrations)},
    }
    document = {"turns": [{"snapshotAfterTurn": {"transport": transport}}]}
    path = directory / "run-1.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def test_extract_episodes_records_provenance_and_dedupes(tmp_path):
    world = small_world()
    path = _write_evidence(tmp_path, world, ["安在门厅里看着长桌。"])
    first = provenance.extract_episodes(tmp_path)
    assert len(first) == 1
    episode = first[0]
    assert episode["schema"] == provenance.EPISODE_SCHEMA
    assert episode["provenance"]["evidenceFile"] == "evidence/run-1.json"
    assert episode["provenance"]["evidenceSha256"] == provenance.sha256_file(path)
    assert episode["provenance"]["pointer"].endswith("/pointStates/point_root")
    assert episode["provenance"]["recordedStateDigest"] == "d0"
    assert episode["provenance"]["snapshotSha256"] == provenance.state_digest(world)
    assert episode["narrationTexts"] == ["安在门厅里看着长桌。"]

    second_dir = tmp_path / "copy"
    second_dir.mkdir()
    _write_evidence(second_dir, world, [])
    episodes = provenance.extract_episodes(tmp_path)
    assert len(episodes) == 1, "two evidence dirs are not scanned at once; one dir dedupes by state digest"
    assert episodes[0]["alsoIn"] == []


def test_extract_episodes_dedupes_two_files(tmp_path):
    world = small_world()
    _write_evidence(tmp_path, world, [])
    duplicate = tmp_path / "run-2.json"
    duplicate.write_text((tmp_path / "run-1.json").read_text(encoding="utf-8"), encoding="utf-8")
    episodes = provenance.extract_episodes(tmp_path)
    assert len(episodes) == 1
    assert len(episodes[0]["alsoIn"]) == 1


def test_leak_check_ignores_state_derived_overlap_and_flags_narration_only(tmp_path):
    world = small_world()
    x = project_x(world, "ann")
    state_phrase = world["initial"]["locations"]["hall"]["initialAppearance"]  # "门厅里有一张长桌。"
    values = provenance.string_values(x)
    clean = provenance.narration_leak_check([f"他看了看。{state_phrase}"], values, world)
    assert clean["overlap"] == 0

    leaked = provenance.narration_leak_check(["他低声说这里没有人会来"], values + ["他低声说这里没有人会来"], world)
    assert leaked["overlap"] == 1
    assert leaked["sample"] == "他低声说这里没有"


def test_string_values_walks_nested_structures():
    values = provenance.string_values({"a": ["x", {"b": "y"}], "c": 1})
    assert values == ["a", "x", "b", "y", "c"]


def test_snapshot_round_trip_hash(tmp_path):
    world = small_world()
    payload = {"schema": provenance.EPISODE_SCHEMA, "state": world, "provenance": {}, "alsoIn": []}
    path = tmp_path / "snap.json"
    provenance.write_json(path, payload)
    restored = provenance.read_json(path)
    assert provenance.state_digest(restored["state"]) == provenance.state_digest(world)


@pytest.mark.parametrize("pointer", ["", "/", "/turns/0/snapshotAfterTurn/transport"])
def test_pointer_forms(pointer):
    document = {"turns": [{"snapshotAfterTurn": {"transport": {"pointStates": {}}}}]}
    value = provenance.resolve_pointer(document, pointer) if pointer else document
    assert isinstance(value, dict)
