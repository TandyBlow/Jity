"""Durable run state and atomic artifacts. All writes stay inside a run directory."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value) -> str:
    return digest_bytes(encode(value).encode("utf-8"))


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(encode(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def run_lock(path: Path):
    # flock is released by the OS even when the evaluator is killed.
    import fcntl
    with (path / ".run.lock").open("a") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("此任务正在另一个进程运行，请勿同时恢复。") from exc
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path / "run.sqlite3", timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE samples (
            id TEXT PRIMARY KEY, ordinal INTEGER UNIQUE NOT NULL,
            spec TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','running','passed','failed','adapter_error','grading_error')),
            attempts INTEGER NOT NULL DEFAULT 0,
            result TEXT, error TEXT, trace_path TEXT, updated_at TEXT NOT NULL
        );
        CREATE TABLE attempts (
            sample_id TEXT NOT NULL REFERENCES samples(id), attempt INTEGER NOT NULL,
            status TEXT NOT NULL, error TEXT, trace_path TEXT, started_at TEXT NOT NULL,
            finished_at TEXT, PRIMARY KEY(sample_id, attempt)
        );
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL,
            kind TEXT NOT NULL, detail TEXT NOT NULL
        );
    """)


def event(connection, kind: str, detail: dict) -> None:
    connection.execute("INSERT INTO events(time,kind,detail) VALUES(?,?,?)", (now(), kind, encode(detail)))
