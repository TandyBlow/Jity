#!/usr/bin/env python3
"""Index Jity experiment data files into one JSON manifest.

Stdlib only. Records size, sha256, git provenance, format hints, inferred
role and family so audits and the evaluation harness can enumerate data
without ad-hoc scripts.

shortcut: files above --max-parse-mb are not parsed and above --max-hash-mb
not hashed (size only); raise the caps when auditing a specific family.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "jity-data-index/1"
DEFAULT_ROOTS = ("artifacts/goal", "experiments", "results", "data/worlds")

SKIP_DIRS = {
    "__pycache__", ".git", "node_modules", ".next", ".next-dev",
    ".pytest_cache", ".mypy_cache", "test-results", ".visual-out",
    "pi-gate-profile",
}

MODEL_EXT = {".onnx", ".gguf", ".bin", ".pt", ".pth", ".safetensors", ".pb", ".h5"}
CODE_EXT = {".py", ".mjs", ".js", ".ts", ".tsx", ".sh", ".ps1"}
DATA_EXT = {".json", ".jsonl", ".csv"}
LOG_EXT = {".log", ".out", ".err"}


def _git(repo: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "-c", "core.quotepath=false", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def _zsplit(text: str) -> list[str]:
    return [p for p in text.split("\0") if p]


def git_state(repo: Path, roots: list[str], with_last_commit: bool) -> dict:
    state = {"head": None, "blobs": {}, "dirty": set(), "untracked": set(), "lastCommit": {}}
    head = _git(repo, "rev-parse", "HEAD")
    if head is None:
        return state
    state["head"] = head.strip()
    for chunk in _zsplit(_git(repo, "ls-files", "-s", "-z") or ""):
        meta, _, path = chunk.partition("\t")
        parts = meta.split()
        if len(parts) >= 2 and path:
            state["blobs"][path] = parts[1]
    state["dirty"] = set(_zsplit(_git(repo, "diff", "--name-only", "-z") or ""))
    state["untracked"] = set(_zsplit(_git(repo, "ls-files", "-o", "--exclude-standard", "-z") or ""))
    if with_last_commit:
        log = _git(repo, "log", "--format=@@%H", "--name-only", "--root", "--", *roots)
        commit = None
        for line in (log or "").splitlines():
            if line.startswith("@@"):
                commit = line[2:].strip()
            elif line.strip() and commit:
                state["lastCommit"].setdefault(line.strip(), commit)
    return state


def infer_role(name: str, ext: str) -> str:
    low = name.lower()
    if ext in MODEL_EXT:
        return "weights"
    if ext == ".md":
        return "report"
    if ext in CODE_EXT:
        return "code"
    if ext in LOG_EXT:
        return "log"
    if "evidence" in low or re.search(r"run-?\d", low):
        return "run-record"
    if "cache" in low:
        return "cache"
    if "label" in low:
        return "labels"
    if "holdout" in low or re.search(r"(^|[-_.])test([-_.]|$)", low):
        return "test"
    if re.search(r"(^|[-_.])train([-_.]|$)", low):
        return "train"
    if re.search(r"(^|[-_.])dev([-_.]|$)", low):
        return "dev"
    if "scenario" in low:
        return "fixture"
    if "input" in low or "bundle" in low:
        return "input"
    if "manifest" in low:
        return "manifest"
    if any(k in low for k in ("summary", "report", "conclusion", "result")):
        return "result"
    return "data"


def _json_hint(data) -> dict:
    hint: dict = {"topType": type(data).__name__}
    if isinstance(data, dict):
        hint["topKeys"] = list(data)[:30]
        lists = {k: len(v) for k, v in data.items() if isinstance(v, list)}
        if lists:
            hint["listLengths"] = dict(sorted(lists.items(), key=lambda kv: -kv[1])[:5])
        for key in ("runId", "kind", "intent", "model", "modelId", "promptVersion"):
            val = data.get(key)
            if isinstance(val, (str, int, float)):
                hint[key] = val
    elif isinstance(data, list):
        hint["entryCount"] = len(data)
        if data and isinstance(data[0], dict):
            hint["itemKeys"] = list(data[0])[:20]
    return hint


def describe_text(ext: str, raw: bytes) -> dict:
    text = raw.decode("utf-8-sig", errors="replace")
    if ext == ".json":
        try:
            return _json_hint(json.loads(text))
        except json.JSONDecodeError as exc:
            return {"parseError": f"{exc.msg} (line {exc.lineno})"}
    if ext == ".jsonl":
        lines = text.splitlines()
        nonempty = [ln for ln in lines if ln.strip()]
        hint: dict = {"lineCount": len(nonempty)}
        errors, keys, ids = [], set(), 0
        for idx, line in enumerate(nonempty, 1):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                if len(errors) < 3:
                    errors.append({"line": idx, "error": exc.msg})
                continue
            if isinstance(rec, dict):
                keys.update(rec)
                if "id" in rec:
                    ids += 1
        if errors:
            hint["parseErrors"] = errors
        if keys:
            hint["keys"] = sorted(keys)[:30]
        if ids:
            hint["recordsWithId"] = ids
        return hint
    if ext == ".csv":
        rows = list(csv.reader(io.StringIO(text)))
        hint = {"rowCount": max(0, len(rows) - 1)}
        if rows:
            hint["columns"] = rows[0][:30]
        return hint
    if ext == ".md":
        for line in text.splitlines():
            if line.startswith("#"):
                return {"title": line.lstrip("# ").strip()[:120]}
        return {}
    return {}


def _sha256_stream(path: Path, cap: int) -> str | None:
    digest = hashlib.sha256()
    read = 0
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            digest.update(chunk)
            read += len(chunk)
            if read > cap:
                return None
    return digest.hexdigest()


def build_index(
    repo_root: Path,
    roots: list[str],
    max_parse_mb: float = 8,
    max_hash_mb: float = 64,
    with_last_commit: bool = True,
) -> dict:
    repo_root = Path(repo_root).resolve()
    max_parse = int(max_parse_mb * 1024 * 1024)
    max_hash = int(max_hash_mb * 1024 * 1024)
    git = git_state(repo_root, roots, with_last_commit)
    entries: dict[str, dict] = {}

    for root in roots:
        root_path = repo_root / root
        if not root_path.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                full = Path(dirpath) / name
                rel = full.relative_to(repo_root).as_posix()
                try:
                    stat = full.stat()
                except OSError:
                    continue
                ext = full.suffix.lower()
                rel_to_root = full.relative_to(root_path)
                family = rel_to_root.parts[0] if len(rel_to_root.parts) > 1 else "(root)"
                entry = {
                    "path": rel,
                    "family": family,
                    "role": infer_role(name, ext),
                    "ext": ext,
                    "bytes": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "tracked": rel in git["blobs"],
                    "gitBlob": git["blobs"].get(rel),
                    "dirty": rel in git["dirty"],
                    "untracked": rel in git["untracked"],
                    "ignored": rel not in git["blobs"] and rel not in git["untracked"],
                    "lastCommit": git["lastCommit"].get(rel),
                    "sha256": None,
                    "format": {},
                }
                if stat.st_size <= max_parse:
                    try:
                        raw = full.read_bytes()
                    except OSError:
                        raw = b""
                    entry["sha256"] = hashlib.sha256(raw).hexdigest()
                    if ext in DATA_EXT:
                        entry["format"] = describe_text(ext, raw)
                elif stat.st_size <= max_hash:
                    entry["sha256"] = _sha256_stream(full, max_hash)
                entries[rel] = entry

    by_ext = Counter(e["ext"] or "(none)" for e in entries.values())
    by_role = Counter(e["role"] for e in entries.values())
    by_family: dict[str, dict] = {}
    for e in entries.values():
        slot = by_family.setdefault(e["family"], {"files": 0, "bytes": 0})
        slot["files"] += 1
        slot["bytes"] += e["bytes"]
    total_bytes = sum(e["bytes"] for e in entries.values())
    largest = sorted(entries.values(), key=lambda e: -e["bytes"])[:10]
    return {
        "schema": SCHEMA,
        "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
        "headCommit": git["head"],
        "roots": roots,
        "limits": {"maxParseMB": max_parse_mb, "maxHashMB": max_hash_mb},
        "summary": {
            "fileCount": len(entries),
            "totalBytes": total_bytes,
            "tracked": sum(1 for e in entries.values() if e["tracked"]),
            "dirty": sum(1 for e in entries.values() if e["dirty"]),
            "hashed": sum(1 for e in entries.values() if e["sha256"]),
            "parseErrors": sum(1 for e in entries.values() if "parseError" in e["format"]),
            "byExt": dict(by_ext.most_common(25)),
            "byRole": dict(by_role.most_common()),
            "byFamily": dict(sorted(by_family.items(), key=lambda kv: -kv[1]["bytes"])[:30]),
            "largestFiles": [{"path": e["path"], "bytes": e["bytes"]} for e in largest],
        },
        "files": [entries[p] for p in sorted(entries)],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--root", action="append", dest="roots", help="repeatable, relative to repo")
    parser.add_argument("--out", default="artifacts/goal/platform/data-index.json")
    parser.add_argument("--max-parse-mb", type=float, default=8)
    parser.add_argument("--max-hash-mb", type=float, default=64)
    parser.add_argument("--no-last-commit", action="store_true")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    roots = args.roots or list(DEFAULT_ROOTS)
    index = build_index(repo, roots, args.max_parse_mb, args.max_hash_mb, not args.no_last_commit)
    out = repo / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    summary = index["summary"]
    print(f"indexed {summary['fileCount']} files, {summary['totalBytes'] / 1e6:.1f} MB -> {args.out}")
    print(f"tracked {summary['tracked']}, dirty {summary['dirty']}, hashed {summary['hashed']}, parse errors {summary['parseErrors']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
