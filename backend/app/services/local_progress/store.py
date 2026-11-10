"""Storage kernel for browser progress sync.

This module stores an opaque payload and its lineage metadata in its own SQLite
file. It never imports the world engine and never interprets, validates or
rewrites game state. The only checks are protocol checks: identifiers, byte
size, parent existence, lineage shape, revision/head CAS and idempotent replay.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.schemas.local_progress import SelectHeadRequest, SnapshotUploadRequest

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS progress_worlds (
  world_id TEXT PRIMARY KEY,
  head_snapshot_id TEXT,
  revision INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS progress_snapshots (
  world_id TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  parent_snapshot_ids_json TEXT NOT NULL,
  content_digest TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (world_id, snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_progress_snapshots_world
  ON progress_snapshots(world_id, created_at);

CREATE TABLE IF NOT EXISTS progress_requests (
  world_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (world_id, request_id)
);
"""

DEFAULT_MAX_PAYLOAD_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_SNAPSHOTS = 5000
DEFAULT_MAX_PARENTS = 64
DEFAULT_IDEMPOTENCY_TTL_DAYS = 30


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    """Canonical JSON used for content identity and request identity.

    This is serialisation, not game semantics. Sorting keys makes the digest
    independent of object key order; allow_nan=False keeps the stored document
    valid JSON.
    """
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProgressError(
            "request_malformed",
            400,
            f"payload is not a JSON value: {exc}",
        ) from exc


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_identity(payload: Any) -> tuple[str, str, int, str]:
    """Return (canonical payload, digest, byte size, snapshot id)."""
    payload_json = canonical_json(payload)
    encoded = payload_json.encode("utf-8")
    digest = sha256_hex(payload_json)
    return payload_json, digest, len(encoded), f"snap_{digest}"


class ProgressError(Exception):
    def __init__(
        self,
        code: str,
        status: int,
        message: str,
        *,
        head: dict[str, Any] | None = None,
        branches: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
        self.head = head
        self.branches = branches or []


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


class LocalProgressStore:
    """Independent SQLite-backed progress store.

    Every mutating call runs under BEGIN IMMEDIATE, which serialises CAS
    writers. A retry carrying the same requestId is answered from the stored
    response before the CAS fields are examined, so a lost response cannot turn
    a successful save into a spurious conflict.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
        max_snapshots: int = DEFAULT_MAX_SNAPSHOTS,
        max_parents: int = DEFAULT_MAX_PARENTS,
        idempotency_ttl_days: int = DEFAULT_IDEMPOTENCY_TTL_DAYS,
    ) -> None:
        self.path = Path(path)
        self.max_payload_bytes = max_payload_bytes
        self.max_snapshots = max_snapshots
        self.max_parents = max_parents
        self.idempotency_ttl_days = idempotency_ttl_days
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # -- connection / schema -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.commit()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    # -- public reads --------------------------------------------------------

    def head(self, world_id: str) -> dict[str, Any]:
        _validate_world_id(world_id)
        with self._read() as connection:
            world = self._world(connection, world_id)
            if world is None:
                raise ProgressError("world_not_found", 404, f"world {world_id} has no saved progress")
            return _head_from_row(world)

    def read_snapshot(self, world_id: str, snapshot_id: str) -> dict[str, Any]:
        _validate_world_id(world_id)
        _validate_snapshot_id(snapshot_id)
        with self._read() as connection:
            if self._world(connection, world_id) is None:
                raise ProgressError("world_not_found", 404, f"world {world_id} has no saved progress")
            row = connection.execute(
                "SELECT * FROM progress_snapshots WHERE world_id = ? AND snapshot_id = ?",
                (world_id, snapshot_id),
            ).fetchone()
            if row is None:
                raise ProgressError("snapshot_not_found", 404, f"snapshot {snapshot_id} is not stored")
            return _snapshot_response(row)

    def graph(self, world_id: str) -> dict[str, Any]:
        _validate_world_id(world_id)
        with self._read() as connection:
            world = self._world(connection, world_id)
            if world is None:
                raise ProgressError("world_not_found", 404, f"world {world_id} has no saved progress")
            snapshots = self._snapshots(connection, world_id)
            children: dict[str, set[str]] = {snapshot_id: set() for snapshot_id in snapshots}
            for snapshot_id, node in snapshots.items():
                for parent in node["parentSnapshotIds"]:
                    children.setdefault(parent, set()).add(snapshot_id)
            branches = sorted(snapshot_id for snapshot_id, kids in children.items() if not kids)
            return {
                **_head_from_row(world),
                "nodes": [_summary(node) for node in snapshots.values()],
                "branches": branches,
            }

    def health(self) -> dict[str, Any]:
        with self._read() as connection:
            worlds = connection.execute("SELECT COUNT(*) FROM progress_worlds").fetchone()[0]
            snapshots = connection.execute("SELECT COUNT(*) FROM progress_snapshots").fetchone()[0]
        return {
            "status": "ok",
            "storage": str(self.path),
            "worlds": worlds,
            "snapshots": snapshots,
            "maxPayloadBytes": self.max_payload_bytes,
            "maxSnapshotsPerWorld": self.max_snapshots,
        }

    # -- public writes -------------------------------------------------------

    def upload(self, world_id: str, request: SnapshotUploadRequest) -> dict[str, Any]:
        _validate_world_id(world_id)
        _validate_request_id(request.requestId)
        if len(request.parentSnapshotIds) > self.max_parents:
            raise ProgressError(
                "request_malformed",
                400,
                f"at most {self.max_parents} parentSnapshotIds are allowed",
            )
        payload_json, digest, size_bytes, snapshot_id = content_identity(request.payload)
        if size_bytes > self.max_payload_bytes:
            raise ProgressError(
                "payload_too_large",
                413,
                f"payload is {size_bytes} bytes; limit is {self.max_payload_bytes}",
            )
        for parent in request.parentSnapshotIds:
            _validate_snapshot_id(parent)
        if request.expectedHead is not None:
            _validate_snapshot_id(request.expectedHead)

        request_hash = sha256_hex(
            canonical_json(
                {
                    "kind": "upload",
                    "activate": request.activate,
                    "contentDigest": digest,
                    "expectedHead": request.expectedHead,
                    "expectedRevision": request.expectedRevision,
                    "parentSnapshotIds": sorted(set(request.parentSnapshotIds)),
                }
            )
        )
        now = utc_now()

        with self._write() as connection:
            world = self._world(connection, world_id)
            if world is None:
                if request.expectedRevision != 0 or request.expectedHead is not None:
                    raise _conflict(
                        "revision_mismatch",
                        "world has no saved progress",
                        head=_head_values(world_id, None, 0, None),
                    )
                connection.execute(
                    "INSERT INTO progress_worlds "
                    "(world_id, head_snapshot_id, revision, created_at, updated_at) "
                    "VALUES (?, NULL, 0, ?, ?)",
                    (world_id, now, now),
                )
                world = self._world(connection, world_id)
                assert world is not None

            replay = self._idempotent_response(
                connection, world_id, request.requestId, request_hash, world
            )
            if replay is not None:
                return replay

            head = world["head_snapshot_id"]
            revision = world["revision"]
            if request.expectedRevision != revision:
                raise _conflict(
                    "revision_mismatch",
                    f"expected revision {request.expectedRevision}, current is {revision}",
                    head=_head_from_row(world),
                    branches=self._branches(connection, world_id),
                )
            if (request.expectedHead or None) != head:
                raise _conflict(
                    "head_mismatch",
                    f"expected head {request.expectedHead!r}, current is {head!r}",
                    head=_head_from_row(world),
                    branches=self._branches(connection, world_id),
                )

            if not request.activate and head is None:
                raise ProgressError(
                    "request_malformed",
                    400,
                    "the first upload for a world must be an activating upload",
                )

            snapshots = self._snapshots(connection, world_id)
            # Content identity means a payload is one node. A retry that names
            # the same node as its own parent is a no-op, not a self-cycle.
            parents = sorted(
                {
                    parent
                    for parent in request.parentSnapshotIds
                    if parent != snapshot_id
                }
            )
            missing = [parent for parent in parents if parent not in snapshots]
            if missing:
                raise ProgressError(
                    "parent_unknown",
                    400,
                    f"parent snapshots are not stored in this world: {', '.join(missing)}",
                )
            if request.activate and head is not None and head not in parents and snapshot_id != head:
                raise ProgressError(
                    "request_malformed",
                    400,
                    "an activating upload must name the current head as a parent",
                )
            if not request.activate and head is not None and not parents:
                raise ProgressError(
                    "request_malformed",
                    400,
                    "a fork upload must name at least one stored parent",
                )

            existing = snapshots.get(snapshot_id)
            created = False
            parents_changed = False
            if existing is None:
                if len(snapshots) >= self.max_snapshots:
                    raise ProgressError(
                        "snapshot_limit_reached",
                        413,
                        f"world already holds {len(snapshots)} snapshots; limit is {self.max_snapshots}",
                    )
                _assert_no_cycle(snapshots, snapshot_id, parents)
                connection.execute(
                    "INSERT INTO progress_snapshots "
                    "(world_id, snapshot_id, parent_snapshot_ids_json, content_digest, "
                    " payload_json, size_bytes, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        world_id,
                        snapshot_id,
                        canonical_json(parents),
                        digest,
                        payload_json,
                        size_bytes,
                        now,
                    ),
                )
                created = True
                stored_parents = parents
            else:
                stored_parents = sorted(set(existing["parentSnapshotIds"]) | set(parents))
                if stored_parents != existing["parentSnapshotIds"]:
                    _assert_no_cycle(snapshots, snapshot_id, stored_parents)
                    connection.execute(
                        "UPDATE progress_snapshots SET parent_snapshot_ids_json = ? "
                        "WHERE world_id = ? AND snapshot_id = ?",
                        (canonical_json(stored_parents), world_id, snapshot_id),
                    )
                    parents_changed = True

            new_head = head
            if request.activate:
                if head is None and parents:
                    raise ProgressError(
                        "request_malformed",
                        400,
                        "the first snapshot must not name parents",
                    )
                new_head = snapshot_id
            changed = created or parents_changed or new_head != head
            if changed:
                revision += 1
                connection.execute(
                    "UPDATE progress_worlds SET head_snapshot_id = ?, revision = ?, updated_at = ? "
                    "WHERE world_id = ?",
                    (new_head, revision, now, world_id),
                )

            response = {
                "worldId": world_id,
                "snapshotId": snapshot_id,
                "contentDigest": digest,
                "parentSnapshotIds": stored_parents,
                "headSnapshotId": new_head,
                "revision": revision,
                "created": created,
                "changed": changed,
                "idempotent": False,
            }
            self._remember(connection, world_id, request.requestId, request_hash, response, now)
            return response

    def select_head(self, world_id: str, request: SelectHeadRequest) -> dict[str, Any]:
        _validate_world_id(world_id)
        _validate_request_id(request.requestId)
        _validate_snapshot_id(request.snapshotId)
        if request.expectedHead is not None:
            _validate_snapshot_id(request.expectedHead)
        request_hash = sha256_hex(
            canonical_json(
                {
                    "kind": "select",
                    "snapshotId": request.snapshotId,
                    "expectedHead": request.expectedHead,
                    "expectedRevision": request.expectedRevision,
                }
            )
        )
        now = utc_now()

        with self._write() as connection:
            world = self._world(connection, world_id)
            if world is None:
                raise ProgressError("world_not_found", 404, f"world {world_id} has no saved progress")
            replay = self._idempotent_response(
                connection, world_id, request.requestId, request_hash, world
            )
            if replay is not None:
                return replay

            head = world["head_snapshot_id"]
            revision = world["revision"]
            if request.expectedRevision != revision:
                raise _conflict(
                    "revision_mismatch",
                    f"expected revision {request.expectedRevision}, current is {revision}",
                    head=_head_from_row(world),
                    branches=self._branches(connection, world_id),
                )
            if (request.expectedHead or None) != head:
                raise _conflict(
                    "head_mismatch",
                    f"expected head {request.expectedHead!r}, current is {head!r}",
                    head=_head_from_row(world),
                    branches=self._branches(connection, world_id),
                )

            snapshots = self._snapshots(connection, world_id)
            target = snapshots.get(request.snapshotId)
            if target is None:
                raise ProgressError(
                    "snapshot_not_found",
                    404,
                    f"snapshot {request.snapshotId} is not stored",
                    head=_head_from_row(world),
                    branches=self._branches(connection, world_id),
                )
            if request.snapshotId != head:
                children = [
                    node["snapshotId"]
                    for node in snapshots.values()
                    if request.snapshotId in node["parentSnapshotIds"]
                ]
                if children:
                    raise _conflict(
                        "not_branch_leaf",
                        f"snapshot {request.snapshotId} has children and is not a branch leaf: "
                        f"{', '.join(sorted(children))}",
                        head=_head_from_row(world),
                        branches=self._branches(connection, world_id),
                    )

            changed = request.snapshotId != head
            if changed:
                revision += 1
                connection.execute(
                    "UPDATE progress_worlds SET head_snapshot_id = ?, revision = ?, updated_at = ? "
                    "WHERE world_id = ?",
                    (request.snapshotId, revision, now, world_id),
                )
            response = {
                "worldId": world_id,
                "headSnapshotId": request.snapshotId,
                "previousHeadSnapshotId": head,
                "revision": revision,
                "changed": changed,
                "idempotent": False,
            }
            self._remember(connection, world_id, request.requestId, request_hash, response, now)
            return response

    # -- internals -----------------------------------------------------------

    def _world(self, connection: sqlite3.Connection, world_id: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM progress_worlds WHERE world_id = ?", (world_id,)
        ).fetchone()

    def _snapshots(self, connection: sqlite3.Connection, world_id: str) -> dict[str, dict[str, Any]]:
        rows = connection.execute(
            "SELECT * FROM progress_snapshots WHERE world_id = ?", (world_id,)
        ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            result[row["snapshot_id"]] = {
                "snapshotId": row["snapshot_id"],
                "parentSnapshotIds": json.loads(row["parent_snapshot_ids_json"]),
                "contentDigest": row["content_digest"],
                "sizeBytes": row["size_bytes"],
                "createdAt": row["created_at"],
            }
        return result

    def _branches(self, connection: sqlite3.Connection, world_id: str) -> list[str]:
        snapshots = self._snapshots(connection, world_id)
        parents: set[str] = set()
        for node in snapshots.values():
            parents.update(node["parentSnapshotIds"])
        return sorted(snapshot_id for snapshot_id in snapshots if snapshot_id not in parents)

    def _idempotent_response(
        self,
        connection: sqlite3.Connection,
        world_id: str,
        request_id: str,
        request_hash: str,
        world: sqlite3.Row,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM progress_requests WHERE world_id = ? AND request_id = ?",
            (world_id, request_id),
        ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise ProgressError(
                "request_id_reused",
                409,
                f"requestId {request_id} was already used with different content",
                head=_head_from_row(world),
                branches=self._branches(connection, world_id),
            )
        response = json.loads(row["response_json"])
        # The stored response belongs to the original operation. Report the
        # world's *current* head/revision so a delayed retry cannot move the
        # caller's cached sync point backwards.
        response.update(
            {
                "headSnapshotId": world["head_snapshot_id"],
                "revision": world["revision"],
                "changed": False,
                "idempotent": True,
            }
        )
        if "previousHeadSnapshotId" in response:
            response["previousHeadSnapshotId"] = world["head_snapshot_id"]
        return response

    def _remember(
        self,
        connection: sqlite3.Connection,
        world_id: str,
        request_id: str,
        request_hash: str,
        response: dict[str, Any],
        now: str,
    ) -> None:
        connection.execute(
            "INSERT INTO progress_requests "
            "(world_id, request_id, request_hash, response_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (world_id, request_id, request_hash, canonical_json(response), now),
        )
        if self.idempotency_ttl_days > 0:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=self.idempotency_ttl_days)
            ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            connection.execute(
                "DELETE FROM progress_requests WHERE world_id = ? AND created_at < ?",
                (world_id, cutoff),
            )


def _head_values(
    world_id: str,
    head_snapshot_id: str | None,
    revision: int,
    updated_at: str | None,
) -> dict[str, Any]:
    return {
        "worldId": world_id,
        "headSnapshotId": head_snapshot_id,
        "revision": revision,
        "updatedAt": updated_at,
    }


def _head_from_row(world: sqlite3.Row) -> dict[str, Any]:
    return _head_values(
        world["world_id"],
        world["head_snapshot_id"],
        world["revision"],
        world["updated_at"],
    )


def _summary(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshotId": node["snapshotId"],
        "parentSnapshotIds": node["parentSnapshotIds"],
        "contentDigest": node["contentDigest"],
        "sizeBytes": node["sizeBytes"],
        "createdAt": node["createdAt"],
    }


def _snapshot_response(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "snapshotId": row["snapshot_id"],
        "parentSnapshotIds": json.loads(row["parent_snapshot_ids_json"]),
        "contentDigest": row["content_digest"],
        "sizeBytes": row["size_bytes"],
        "createdAt": row["created_at"],
        "payload": json.loads(row["payload_json"]),
    }


def _conflict(
    code: str,
    message: str,
    *,
    head: dict[str, Any],
    branches: list[str] | None = None,
) -> ProgressError:
    return ProgressError(code, 409, message, head=head, branches=branches or [])


def _assert_no_cycle(
    snapshots: dict[str, dict[str, Any]],
    snapshot_id: str,
    parents: list[str],
) -> None:
    stack = list(parents)
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current == snapshot_id:
            raise ProgressError(
                "lineage_cycle",
                400,
                f"adding parents to {snapshot_id} would create a cycle",
            )
        if current in seen:
            continue
        seen.add(current)
        stack.extend(snapshots.get(current, {}).get("parentSnapshotIds", []))


def _validate_world_id(world_id: str) -> None:
    if not world_id or len(world_id) > 128 or any(
        not (char.isalnum() or char in "._:-") for char in world_id
    ):
        raise ProgressError(
            "request_malformed",
            400,
            "worldId must be 1-128 characters of letters, digits, dot, underscore, colon or dash",
        )


def _validate_snapshot_id(snapshot_id: str) -> None:
    if (
        not snapshot_id.startswith("snap_")
        or len(snapshot_id) != 69
        or any(char not in "0123456789abcdef" for char in snapshot_id[5:])
    ):
        raise ProgressError(
            "request_malformed",
            400,
            "snapshotId must be a content identity of the form snap_<sha256-hex>",
        )


def _validate_request_id(request_id: str) -> None:
    if not request_id or len(request_id) > 200:
        raise ProgressError("request_malformed", 400, "requestId must be 1-200 characters")
