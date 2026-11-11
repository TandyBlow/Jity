"""Configuration helpers for the standalone progress-sync service."""

from __future__ import annotations

import os
from pathlib import Path

from app.services.local_progress.store import (
    DEFAULT_MAX_PARENTS,
    DEFAULT_MAX_PAYLOAD_BYTES,
    DEFAULT_MAX_SNAPSHOTS,
    LocalProgressStore,
)


def database_path() -> Path:
    return Path(os.environ.get("LOCAL_PROGRESS_DB", "data/local_progress.sqlite3"))


def access_token() -> str | None:
    token = os.environ.get("LOCAL_PROGRESS_TOKEN", "").strip()
    return token or None


def cors_origins() -> list[str]:
    raw = os.environ.get(
        "LOCAL_PROGRESS_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _positive_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def build_store() -> LocalProgressStore:
    return LocalProgressStore(
        database_path(),
        max_payload_bytes=_positive_env("LOCAL_PROGRESS_MAX_PAYLOAD_BYTES", DEFAULT_MAX_PAYLOAD_BYTES),
        max_snapshots=_positive_env("LOCAL_PROGRESS_MAX_SNAPSHOTS", DEFAULT_MAX_SNAPSHOTS),
        max_parents=_positive_env("LOCAL_PROGRESS_MAX_PARENTS", DEFAULT_MAX_PARENTS),
    )
