"""Freeze the short-pair deliverable.

Reads the built files, re-computes their hashes, and writes `freeze.json` in the
same directory. Refuses when the check report is not green, when the pair count
does not match the index, or when the serializer digest is not recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SNAPSHOT = Path("D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--rows", required=True)
    parser.add_argument("--exclusions", required=True)
    parser.add_argument("--serializer", default=None, help="defaults to the path recorded in build-report.json")
    args = parser.parse_args(argv)

    out = Path(args.out_dir)
    report_path = out / "build-report.json"
    check_path = out / "check.json"
    index_report_path = out / "index-report.json"
    for path in (report_path, check_path, index_report_path, out / "pairs.jsonl"):
        if not path.exists():
            raise SystemExit(f"missing build output: {path}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    check = json.loads(check_path.read_text(encoding="utf-8"))
    index_report = json.loads(index_report_path.read_text(encoding="utf-8"))
    if not check.get("ok"):
        raise SystemExit(f"check report is not green: {check.get('problems')}")
    if report["pairs"] != index_report["counts"]["pairs"]:
        raise SystemExit("build report and index disagree on the pair count")

    serializer_path = Path(args.serializer or report["serializer"]["path"])
    freeze = {
        "kind": "short-pair-13-way-freeze",
        "version": "action-pairwise-shortpairs-v1",
        "files": {
            name: sha(out / name)
            for name in ("pairs.jsonl", "pairs-index.jsonl", "rows-meta.jsonl", "build-report.json", "check.json", "index-report.json")
        },
        "pairs": report["pairs"],
        "decisions": report["decisions"],
        "positives": report["positives"],
        "perGroupPositive": report["perGroupPositive"],
        "indistinguishableTexts": report.get("indistinguishableTexts", 0),
        "labelConflictExclusions": json.loads(Path(args.exclusions).read_text(encoding="utf-8")),
        "serializer": {
            "path": str(serializer_path),
            "sha256": sha(serializer_path),
            "version": report["serializer"]["version"],
            "tracked": _tracked(serializer_path),
            "dirty": _dirty(serializer_path),
        },
        "rows": {"path": str(Path(args.rows)), "sha256": sha(Path(args.rows))},
        "model": {
            "dir": str(SNAPSHOT),
            "configSha256": sha(SNAPSHOT / "config.json"),
            "vocabSha256": sha(SNAPSHOT / "vocab.txt"),
            "maxPositionEmbeddings": json.loads((SNAPSHOT / "config.json").read_text(encoding="utf-8"))[
                "max_position_embeddings"
            ],
        },
        "tokens": check["tokens"],
        "omittedTotals": report.get("omittedTotals"),
        "notes": [
            "derived from the frozen 300-row file; that file and its freeze are unchanged",
            "excluded rows are absent from this derived set only; Y and the original rows are untouched",
            "the serializer file is lane 04's; this freeze pins its sha256",
            "same-label indistinguishable duplicates are listed in build-report.json",
            "this is a training-input freeze, not a model result",
        ],
    }
    (out / "freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"pairs": freeze["pairs"], "files": freeze["files"], "serializer": freeze["serializer"]}, ensure_ascii=False))
    return 0


def _dirty(path: Path) -> bool:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "-C", str(path.parent), "status", "--porcelain", "--", path.name],
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())
    except OSError:
        return True


def _tracked(path: Path) -> bool:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "-C", str(path.parent), "ls-files", "--error-unmatch", path.name],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except OSError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
