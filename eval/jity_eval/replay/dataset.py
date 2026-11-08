"""Freeze a Jity timeline through read-only SQLite access, without importing Jity.

The successful ``raw_output_text`` column in existing Jity saves contains the
committed, normalized StoryOutput. It is deliberately NOT a model call cassette.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


class DatasetError(ValueError):
    """A frozen replay source is missing, inconsistent, or has been changed."""


def _hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _decode(value: Any, field: str, expected_type: type = dict) -> Any:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError) as exc:
        raise DatasetError("Invalid JSON in %s" % field) from exc
    if not isinstance(parsed, expected_type):
        raise DatasetError("%s must be %s" % (field, expected_type.__name__))
    return parsed


def _readonly(source_db: Path) -> sqlite3.Connection:
    source_db = Path(source_db).resolve()
    if not source_db.is_file():
        raise DatasetError("Source database does not exist: %s" % source_db)
    # An active WAL must be included. When no WAL exists, immutable read-only
    # avoids SQLite trying to create SHM/WAL files merely to read a WAL-mode
    # header. Before/after file fingerprints detect a concurrently created WAL.
    options = "?mode=ro" if Path(str(source_db) + "-wal").is_file() else "?mode=ro&immutable=1"
    connection = sqlite3.connect(source_db.as_uri() + options, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"game_sessions", "story_turns"}.issubset(tables):
        connection.close()
        raise DatasetError("Source database has no Jity branching timeline")
    return connection


def _lineage(connection: sqlite3.Connection, session_id: str, head: int | None) -> list[dict]:
    if head is None:
        raise DatasetError("Session has no active timeline head")
    lineage = []
    seen = set()
    while head is not None:
        if head in seen:
            raise DatasetError("Timeline contains a parent cycle")
        seen.add(head)
        row = connection.execute("SELECT * FROM story_turns WHERE id=? AND session_id=?", (head, session_id)).fetchone()
        if row is None:
            raise DatasetError("Timeline parent %s is missing or belongs to another session" % head)
        item = dict(row)
        lineage.append(item)
        head = item["parent_turn_id"]
    lineage.reverse()
    for index, row in enumerate(lineage):
        if row.get("depth") != index:
            raise DatasetError("Timeline depth does not match its ancestor chain at node %s" % row["id"])
    return lineage


def _sessions(connection: sqlite3.Connection) -> list[dict]:
    result = []
    for row in connection.execute("SELECT id, game_name, active_turn_id FROM game_sessions ORDER BY id"):
        entry = dict(row)
        try:
            chain = _lineage(connection, row["id"], row["active_turn_id"])
            entry.update(active_turn_count=len(chain) - 1, replayable=True, error=None)
        except DatasetError as exc:
            entry.update(active_turn_count=0, replayable=False, error=str(exc))
        result.append(entry)
    return sorted(result, key=lambda item: (-item["active_turn_count"], item["id"]))


def discover_sessions(source_db: Path) -> list[dict]:
    """List active ancestor-chain lengths; never use max depth across branches."""
    connection = _readonly(Path(source_db))
    try:
        return _sessions(connection)
    finally:
        connection.close()


def _source_files(source_db: Path) -> dict[str, str]:
    # SHM is transient lock/index storage; only DB/WAL contain durable data.
    return {str(path): _hash(path) for path in (source_db, Path(str(source_db) + "-wal")) if path.is_file()}


def _model_output(connection: sqlite3.Connection, row_id: int | None, session_id: str) -> dict | None:
    if row_id is None:
        return None
    try:
        row = connection.execute("SELECT * FROM model_outputs WHERE id=?", (row_id,)).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return None
        raise
    if row is None:
        return None
    result = dict(row)
    if result.get("session_id") != session_id:
        raise DatasetError("Model output belongs to a different session")
    for raw, parsed, kind in (("output_json", "output", dict), ("retrieved_chunks_json", "retrieved_chunks", list), ("prompt_sections_json", "prompt_sections", dict)):
        default = "[]" if kind is list else "{}"
        result[parsed] = _decode(result.get(raw) or default, "model_outputs.%s" % raw, kind)
    result["raw_output_text_provenance"] = (
        "normalized_committed_output" if result.get("status") == "ok" else "error_record_not_a_successful_call_response"
    )
    result["usable_as_exact_model_response"] = False
    return result


def freeze_dataset(
    jity_root: Path,
    source_db: Path,
    session_id: str | None,
    output_dir: Path,
    head_turn_id: str | None = None,
) -> Path:
    """Create a new snapshot directory and its selected-branch ``dataset.json``.

    SQLite backup creates a consistent copy including committed WAL entries.
    A concurrent source write causes an explicit error rather than silently
    presenting before/after fingerprints as unchanged. No source writes occur.
    """
    jity_root, source_db, output_dir = Path(jity_root).resolve(), Path(source_db).resolve(), Path(output_dir).resolve()
    if output_dir == jity_root or jity_root in output_dir.parents:
        raise DatasetError("Replay output must be outside the original Jity checkout")
    if output_dir.exists():
        raise DatasetError("Refusing to overwrite an existing dataset directory")
    before = _source_files(source_db)
    source = _readonly(source_db)
    output_dir.mkdir(parents=True, exist_ok=False)
    snapshot_path = output_dir / "source.snapshot.sqlite3"
    try:
        destination = sqlite3.connect(snapshot_path)
        try:
            source.backup(destination)
            # The frozen copy must be self-contained. A backup from a WAL DB
            # can inherit WAL mode without sidecar files; normalize the COPY.
            destination.execute("PRAGMA journal_mode=DELETE")
        finally:
            destination.close()
    finally:
        source.close()
    after = _source_files(source_db)
    if before != after:
        raise DatasetError("Source database changed during freezing; retry into a new directory")

    connection = _readonly(snapshot_path)
    try:
        reason = "explicit_session_active_head" if session_id else "longest_active_ancestor_chain"
        if head_turn_id is not None:
            try:
                head = int(head_turn_id)
            except (TypeError, ValueError) as exc:
                raise DatasetError("head_turn_id must identify an integer timeline node") from exc
            head_row = connection.execute("SELECT session_id FROM story_turns WHERE id=?", (head,)).fetchone()
            if head_row is None:
                raise DatasetError("Requested head does not exist")
            if session_id is not None and head_row[0] != session_id:
                raise DatasetError("Requested head does not belong to selected session")
            session_id = head_row[0]
            reason = "explicit_timeline_head"
        elif session_id is None:
            available = [item for item in _sessions(connection) if item["replayable"]]
            if not available:
                raise DatasetError("No valid active timeline exists")
            session_id = available[0]["id"]
        row = connection.execute("SELECT * FROM game_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise DatasetError("Session does not exist: %s" % session_id)
        session = dict(row)
        if head_turn_id is None:
            head = session.get("active_turn_id")
        chain = _lineage(connection, session_id, head)
        root = chain[0]
        turns, missing_outputs = [], []
        for number, record in enumerate(chain[1:], 1):
            output = _decode(record.get("output_json"), "story_turns.output_json")
            model_output = _model_output(connection, record.get("model_output_id"), session_id)
            if model_output is None:
                missing_outputs.append(record["id"])
            turns.append({
                "turn": number, "turn_id": record["id"], "parent_turn_id": record["parent_turn_id"],
                "player_action": record["player_action"], "output": output,
                "state": _decode(record["state_json"], "story_turns.state_json"),
                "campaign_progress": _decode(record.get("campaign_progress_json") or "{}", "story_turns.campaign_progress_json"),
                "action_check": output.get("action_check"), "source": record.get("source", "unknown"),
                "model": record.get("model", ""), "model_output": model_output,
                "created_at": record.get("created_at"),
            })
        metadata = {
            "jity_root": str(jity_root), "database_path": str(source_db),
            "session_id": session_id, "game_name": session["game_name"], "head_turn_id": head,
            "original_active_turn_id": session.get("active_turn_id"), "selection_reason": reason,
            "campaign_id": session.get("campaign_id"), "campaign_filename": session.get("campaign_filename"),
            "active_slot_name": session.get("active_slot_name"), "model": session.get("model"),
            "snapshot_file": snapshot_path.name,
        }
        payload = {
            "schema_version": 2, "kind": "jity_replay",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": metadata,
            "initial": {"turn_id": root["id"], "state": _decode(root["state_json"], "root.state_json"),
                        "campaign_progress": _decode(root.get("campaign_progress_json") or "{}", "root.campaign_progress_json")},
            "turns": turns, "source_fingerprints": before, "source_unchanged_after_freeze": True,
            "call_records": [],
            "call_completeness": {
                "exact_replay_available": False, "recorded_calls": 0,
                "missing_model_output_turn_ids": missing_outputs,
                "known_missing_purposes": ["story_narrator_raw", "campaign_director", "memory_nsb_summary", "memory_pcb_extraction", "campaign_recap", "story_json_repair", "embeddings"],
                "explanation": "Successful model_outputs.raw_output_text is normalized committed output, not the raw model response. Auxiliary response calls were not persisted. PromptRecorder stores requests only. No call record has been fabricated from final state or story output.",
                "policy": "Missing requests must raise an offline replay error; never fall back to network or fabricated responses.",
            },
            "real_model_calls": 0,
        }
        assets = [snapshot_path]
        filename = session.get("campaign_filename")
        if filename:
            campaign_path = (jity_root / "backend/data/campaigns" / filename).resolve()
            campaign_root = (jity_root / "backend/data/campaigns").resolve()
            if campaign_root not in campaign_path.parents:
                raise DatasetError("Campaign filename escapes the campaign directory")
            if campaign_path.is_file():
                target = output_dir / "campaign.json"
                target.write_bytes(campaign_path.read_bytes())
                payload["source"]["campaign_asset"] = target.name
                payload["source_fingerprints"][str(campaign_path)] = _hash(campaign_path)
                assets.append(target)
            else:
                payload["source"]["campaign_asset"] = None
                payload["source"]["campaign_asset_error"] = "Campaign file absent in current checkout"
        dataset_path = output_dir / "dataset.json"
        _write_json(dataset_path, payload)
        assets.append(dataset_path)
        _write_json(output_dir / "manifest.json", {
            "schema_version": 2, "kind": "jity_replay_manifest",
            "files": {path.name: _hash(path) for path in assets},
            "source_fingerprints": payload["source_fingerprints"],
            "source_unchanged_after_freeze": True,
        })
    finally:
        connection.close()
    load_dataset(dataset_path)
    return dataset_path


def load_dataset(path: Path) -> dict:
    """Verify frozen files and ancestor structure; do not reopen the source DB."""
    path = Path(path).resolve()
    if path.is_dir():
        path = path / "dataset.json"
    try:
        manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 2 or manifest.get("kind") != "jity_replay_manifest":
            raise DatasetError("Unsupported replay manifest")
        files = manifest.get("files")
        if not isinstance(files, dict) or path.name not in files or "source.snapshot.sqlite3" not in files:
            raise DatasetError("Replay manifest is missing required file hashes")
        for name, expected in files.items():
            if Path(name).name != name or name in (".", ".."):
                raise DatasetError("Unsafe asset name in replay manifest")
            asset = path.parent / name
            if not asset.is_file() or asset.is_symlink() or _hash(asset) != expected:
                raise DatasetError("Frozen replay asset has changed or is missing: %s" % name)
        dataset = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetError("Cannot load frozen replay dataset: %s" % exc) from exc
    if dataset.get("schema_version") != 2 or dataset.get("kind") != "jity_replay":
        raise DatasetError("Unsupported replay dataset")
    if not isinstance(dataset.get("source"), dict) or not isinstance(dataset.get("initial"), dict) or not isinstance(dataset.get("turns"), list):
        raise DatasetError("Replay dataset is missing source, initial state or turns")
    if dataset.get("source_fingerprints") != manifest.get("source_fingerprints"):
        raise DatasetError("Source fingerprint metadata does not match manifest")
    initial = dataset["initial"]
    if not isinstance(initial.get("state"), dict) or not isinstance(initial.get("campaign_progress"), dict):
        raise DatasetError("Invalid initial snapshot")
    previous = initial.get("turn_id")
    seen = {previous}
    for index, turn in enumerate(dataset["turns"], 1):
        if not isinstance(turn, dict) or turn.get("turn") != index or turn.get("parent_turn_id") != previous or turn.get("turn_id") in seen:
            raise DatasetError("Replay turns are not a continuous ancestor chain")
        if not isinstance(turn.get("player_action"), str) or any(not isinstance(turn.get(key), dict) for key in ("output", "state", "campaign_progress")):
            raise DatasetError("Replay turn is missing action, output or state")
        if turn.get("action_check") != turn["output"].get("action_check"):
            raise DatasetError("Replay die record differs from its committed output")
        previous = turn["turn_id"]
        seen.add(previous)
    if previous != dataset["source"].get("head_turn_id"):
        raise DatasetError("Replay chain does not end at its selected head")
    if not isinstance(dataset.get("call_records"), list):
        raise DatasetError("Replay call_records must be explicit")
    return dataset
