#!/usr/bin/env python3
"""Validate the Jity experiment data index and the artifacts it points at.

Checks:
  malformed        JSON/JSONL that does not parse (truncation, bad encoding)
  empty_dataset    zero-row jsonl/json files with a data role
  key_drift        jsonl records missing fields present in the first record
  duplicate_content  same sha256 under two paths
  large_tracked    tracked files above --large-mb (weights/logs should stay local)
  missing_ref      report backtick paths that do not exist in the repo

Run after data_index.py. Exit code 1 when a fail-level check trips.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCHEMA = "jity-data-validation/1"
DATA_ROLES = {"train", "test", "dev", "labels", "cache", "input", "fixture"}
REF_PREFIXES = ("artifacts/", "design/", "frontend/", "backend/", "scripts/",
                "experiments/", "data/", "docs/", "resources/")
REF_EXTS = {".json", ".jsonl", ".csv", ".md", ".py", ".mjs", ".js", ".ts",
            ".tsx", ".onnx", ".gguf", ".png"}
BACKTICK = re.compile(r"`([^`\n]{1,240})`")
LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
SHA_DIGEST = re.compile(r"\b([0-9a-f]{64})\b")
SEMANTIC_MANIFEST = "real-semantic-manifest.json"
SEMANTIC_PARTS = {"raw": "real-semantic.jsonl", "train": "real-semantic-train.jsonl",
                  "test": "real-semantic-test.jsonl"}
SEMANTIC_ROWS = {"raw": "rawRows", "train": "trainRows", "test": "testRows"}


def check_malformed(files: list[dict]) -> list[dict]:
    out = []
    for e in files:
        if "parseError" not in e.get("format", {}):
            continue
        # Vendored model metadata fetched as error text is tracked junk, not data drift.
        vendored = e["path"].startswith("experiments/narration-model-search/sources/")
        out.append({"path": e["path"], "error": e["format"]["parseError"], "blocking": not vendored})
    return out


def check_empty_datasets(files: list[dict]) -> list[dict]:
    out = []
    for e in files:
        if e["ext"] == ".jsonl":
            if (e.get("format") or {}).get("lineCount") == 0:
                out.append({"path": e["path"], "role": e["role"]})
        elif e["ext"] == ".json" and e["role"] in DATA_ROLES:
            if (e.get("format") or {}).get("entryCount") == 0:
                out.append({"path": e["path"], "role": e["role"]})
    return out


def check_key_drift(files: list[dict]) -> list[dict]:
    out = []
    strict_roles = {"train", "test", "dev", "labels", "cache", "input", "fixture"}
    for e in files:
        if e["ext"] != ".jsonl" or e["role"] not in strict_roles:
            continue
        keys = (e.get("format") or {}).get("keys") or []
        if not keys:
            continue
        path = e["_repo"] / e["path"]
        first = None
        missing = defaultdict(int)
        try:
            with path.open(encoding="utf-8-sig", errors="replace") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    if first is None:
                        first = set(rec)
                        continue
                    for key in first - set(rec):
                        missing[key] += 1
        except OSError:
            continue
        if missing and first:
            out.append({
                "path": e["path"],
                "firstKeys": sorted(first)[:20],
                "missingCounts": dict(sorted(missing.items(), key=lambda kv: -kv[1])[:10]),
            })
    return out


def check_duplicates(files: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for e in files:
        if e.get("sha256") and e["bytes"] >= 16 and e["ext"] in (".json", ".jsonl", ".csv", ".txt"):
            groups[e["sha256"]].append(e)
    dupes = []
    for digest, group in groups.items():
        if len(group) > 1:
            dupes.append({
                "sha256": digest,
                "bytes": group[0]["bytes"],
                "count": len(group),
                "paths": sorted(e["path"] for e in group)[:10],
            })
    return sorted(dupes, key=lambda d: -d["bytes"])


def check_large_tracked(files: list[dict], limit_bytes: int) -> list[dict]:
    return [
        {"path": e["path"], "bytes": e["bytes"], "sha256": e.get("sha256")}
        for e in files if e["tracked"] and e["bytes"] > limit_bytes
    ]


def _resolve(repo: Path, base: Path, token: str) -> bool:
    token = token.strip()
    if not token or token.startswith(("http", "/", "~")):
        return True
    for cand in (repo / token, base / token):
        if cand.exists():
            return True
    return False


def check_missing_refs(files: list[dict], repo: Path, max_findings: int = 200) -> list[dict]:
    findings = []
    seen = set()
    for e in files:
        if e["ext"] != ".md" or not e["path"].startswith(("design/", "artifacts/goal/")):
            continue
        path = repo / e["path"]
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:2_000_000]
        except OSError:
            continue
        for token in BACKTICK.findall(text):
            token = LINE_SUFFIX.sub("", token.strip())
            if " " in token or not token.startswith(REF_PREFIXES):
                continue
            if Path(token).suffix.lower() not in REF_EXTS:
                continue
            if any(ch in token for ch in "*<>{}…$"):
                continue
            if _resolve(repo, path.parent, token):
                continue
            key = (e["path"], token)
            if key in seen:
                continue
            seen.add(key)
            findings.append({"report": e["path"], "missing": token})
            if len(findings) >= max_findings:
                return findings
    return findings


def check_sidecar_hashes(files: list[dict], repo: Path) -> list[dict]:
    """Verify sha256sum-style sidecars (<name>.sha256) against their target."""
    out = []
    for e in files:
        if not e["path"].endswith(".sha256"):
            continue
        sidecar = repo / e["path"]
        try:
            text = sidecar.read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError:
            continue
        match = SHA_DIGEST.search(text)
        if not match:
            out.append({"path": e["path"], "error": "no sha256 digest"})
            continue
        target = sidecar.with_suffix("")
        fields = text.split()
        if len(fields) > 1:
            named = sidecar.parent / fields[1].lstrip("*")
            if named.exists():
                target = named
        if not target.exists():
            # convention here: <name>.sha256 freezes <name>.json
            alt = target.with_suffix(".json")
            if alt.exists():
                target = alt
        if not target.exists():
            out.append({"path": e["path"], "error": "target missing", "target": target.name})
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != match.group(1):
            out.append({"path": e["path"], "target": target.name,
                        "declared": match.group(1)[:12], "actual": actual[:12]})
    return out


def check_semantic_manifests(files: list[dict], repo: Path) -> list[dict]:
    """Verify real-semantic-manifest.json hashes and row counts.

    The manifest hashes raw by file bytes but train/test by canonical JSON of
    the parsed rows; both conventions are checked here explicitly.
    """
    out = []
    for e in files:
        if Path(e["path"]).name != SEMANTIC_MANIFEST:
            continue
        base = (repo / e["path"]).parent
        try:
            manifest = json.loads((repo / e["path"]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            out.append({"manifest": e["path"], "error": str(exc)[:160]})
            continue
        for key, filename in SEMANTIC_PARTS.items():
            part = base / filename
            if not part.exists():
                out.append({"manifest": e["path"], "key": key, "error": "file missing"})
                continue
            if key == "raw":
                actual = hashlib.sha256(part.read_bytes()).hexdigest()
                count = len([ln for ln in part.read_text(encoding="utf-8").splitlines() if ln.strip()])
            else:
                rows = [json.loads(ln) for ln in part.read_text(encoding="utf-8").splitlines() if ln.strip()]
                actual = hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()
                count = len(rows)
            if manifest.get(key) != actual:
                out.append({"manifest": e["path"], "key": key,
                            "declared": str(manifest.get(key))[:12], "actual": actual[:12]})
            if manifest.get(SEMANTIC_ROWS[key]) != count:
                out.append({"manifest": e["path"], "key": SEMANTIC_ROWS[key],
                            "declared": manifest.get(SEMANTIC_ROWS[key]), "actual": count})
    return out


def check_referenced_evidence(files: list[dict], repo: Path) -> list[dict]:
    """Rows that point at an evidence file must point at one present and tracked."""
    tracked = {e["path"]: e["tracked"] for e in files}
    out = []
    for e in files:
        if e["ext"] != ".jsonl" or "evidence" not in ((e.get("format") or {}).get("keys") or []):
            continue
        counts: dict[str, int] = defaultdict(int)
        try:
            with (repo / e["path"]).open(encoding="utf-8-sig", errors="replace") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    name = rec.get("evidence") if isinstance(rec, dict) else None
                    if isinstance(name, str) and name:
                        counts[name] += 1
        except OSError:
            continue
        for name, rows in counts.items():
            matches = [p for p in tracked if p == name or p.endswith("/" + name)]
            if not matches:
                out.append({"path": e["path"], "evidence": name, "status": "missing", "rows": rows})
            elif not any(tracked[p] for p in matches):
                out.append({"path": e["path"], "evidence": name, "status": "untracked", "rows": rows})
    return out


def validate(index: dict, repo: Path, large_mb: float = 5.0) -> dict:
    repo = Path(repo).resolve()
    files = []
    for entry in index["files"]:
        entry = dict(entry)
        entry["_repo"] = repo
        files.append(entry)

    checks = {
        "malformed": {"level": "fail", "findings": check_malformed(files)},
        "empty_dataset": {"level": "warn", "findings": check_empty_datasets(files)},
        "key_drift": {"level": "warn", "findings": check_key_drift(files)},
        "duplicate_content": {"level": "warn", "findings": check_duplicates(files)},
        "large_tracked": {"level": "warn", "findings": check_large_tracked(files, int(large_mb * 1024 * 1024))},
        "missing_ref": {"level": "warn", "findings": check_missing_refs(files, repo)},
        "sidecar_hash": {"level": "fail", "findings": check_sidecar_hashes(files, repo)},
        "semantic_manifest": {"level": "fail", "findings": check_semantic_manifests(files, repo)},
        "evidence_ref": {"level": "warn", "findings": check_referenced_evidence(files, repo)},
    }
    for check in checks.values():
        check["count"] = len(check["findings"])
        blocking = any(f.get("blocking", True) for f in check["findings"])
        if not check["findings"]:
            check["status"] = "pass"
        elif check["level"] == "fail" and blocking:
            check["status"] = "fail"
        else:
            check["status"] = "warn"
    return {
        "schema": SCHEMA,
        "headCommit": index.get("headCommit"),
        "checks": checks,
        "summary": {name: {"status": c["status"], "count": c["count"]} for name, c in checks.items()},
        "failed": any(c["status"] == "fail" for c in checks.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--index", default="artifacts/goal/platform/data-index.json")
    parser.add_argument("--out", default="artifacts/goal/platform/data-validation.json")
    parser.add_argument("--large-mb", type=float, default=5.0)
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    index = json.loads((repo / args.index).read_text(encoding="utf-8"))
    report = validate(index, repo, args.large_mb)
    out = repo / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, summary in report["summary"].items():
        print(f"{summary['status']:5} {name:18} {summary['count']}")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
