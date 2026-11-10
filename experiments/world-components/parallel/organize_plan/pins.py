# -*- coding: utf-8 -*-
"""Pinned-input helpers shared by the accept / sign / ready scripts.

A pin is a record of the form

    {"file": "runs/r4/manual-review.json", "sha256": "..."}

Two things can go wrong with a pin, and both must be caught:

1. the file changed      -> the recorded sha256 no longer matches the file
2. the recorded path lies -> the sha256 matches some file, but not the one the
   record names (this is what happened when runs/r4 pins kept saying
   "runs/r2/manual-review.json")

`pin_drift()` checks both: it hashes the file *named by the record*, so a record
that points at the wrong round can never verify against the round it lives in.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    """Repository-relative POSIX path, the only form we store in records."""
    try:
        return path.resolve().relative_to(HERE).as_posix()
    except ValueError:
        return path.as_posix()


def pin(path: Path, **extra) -> dict:
    entry = {"file": rel(path), "sha256": sha256(path)}
    entry.update(extra)
    return entry


def pin_drift(pins: dict, base: Path | None = None) -> list[str]:
    """Return one message per pin whose file is missing, changed, or misnamed.

    A pin without a `file` field is itself a defect: the reader can then only
    guess which file the hash was taken from.
    """
    base = base or HERE
    problems: list[str] = []
    for key, entry in (pins or {}).items():
        if key == "acceptanceIdentity" or not isinstance(entry, dict):
            continue
        want = entry.get("sha256")
        if not want:
            # An unhashed pin proves nothing: it would let a later edit pass.
            problems.append(f"{key}: pin has no sha256")
            continue
        name = entry.get("file")
        if not name:
            problems.append(f"{key}: pin has no file path, only a hash")
            continue
        path = (base / name)
        if not path.exists():
            problems.append(f"{key}: {name} is missing")
        elif sha256(path) != want:
            problems.append(f"{key}: {name} changed since the record was written")
    return problems


def acceptance_identity(*paths: Path) -> str:
    """Stable identity of an acceptance record: the hashes of its inputs."""
    joined = "".join(sha256(p) for p in paths)
    return hashlib.sha256(joined.encode("ascii")).hexdigest()
