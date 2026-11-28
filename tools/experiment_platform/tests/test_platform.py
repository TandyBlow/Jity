from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path
    _write(root / "artifacts/goal/fam/good.json", '{"runId": "r1", "items": [1, 2]}')
    _write(root / "artifacts/goal/fam/bad.json", '{"broken": ')
    _write(root / "artifacts/goal/fam/dup-a.jsonl", '{"id": 1, "text": "same"}\n')
    _write(root / "artifacts/goal/fam/dup-b.jsonl", '{"id": 1, "text": "same"}\n')
    _write(root / "artifacts/goal/fam/empty.jsonl", "")
    _write(root / "artifacts/goal/fam/train-drift.jsonl", '{"a": 1, "b": 2}\n{"a": 3}\n')
    _write(root / "design/x.md", "refs `artifacts/goal/fam/good.json` and `artifacts/goal/fam/missing.json`.\n")
    return root


def test_index_records_format_and_roles(tmp_path):
    from tools.experiment_platform.data_index import build_index

    repo = _fixture(tmp_path)
    index = build_index(repo, ["artifacts/goal", "design"], with_last_commit=False)
    files = {e["path"]: e for e in index["files"]}
    assert files["artifacts/goal/fam/good.json"]["format"]["runId"] == "r1"
    assert files["artifacts/goal/fam/good.json"]["family"] == "fam"
    assert "parseError" in files["artifacts/goal/fam/bad.json"]["format"]
    assert files["artifacts/goal/fam/dup-a.jsonl"]["format"]["lineCount"] == 1
    assert index["summary"]["fileCount"] == 7


def test_validator_finds_defects(tmp_path):
    from tools.experiment_platform.data_index import build_index
    from tools.experiment_platform.validate_data import validate

    repo = _fixture(tmp_path)
    index = build_index(repo, ["artifacts/goal", "design"], with_last_commit=False)
    report = validate(index, repo)
    checks = report["checks"]

    assert [f["path"] for f in checks["malformed"]["findings"]] == ["artifacts/goal/fam/bad.json"]
    assert checks["empty_dataset"]["count"] == 1
    assert checks["duplicate_content"]["count"] == 1
    assert checks["duplicate_content"]["findings"][0]["count"] == 2
    drift = checks["key_drift"]["findings"]
    assert len(drift) == 1 and drift[0]["missingCounts"] == {"b": 1}
    missing = {f["missing"] for f in checks["missing_ref"]["findings"]}
    assert "artifacts/goal/fam/missing.json" in missing
    assert "artifacts/goal/fam/good.json" not in missing
    assert report["failed"] is True


def test_integrity_sidecar_and_manifest(tmp_path):
    from tools.experiment_platform.data_index import build_index
    from tools.experiment_platform.validate_data import validate

    repo = tmp_path
    base = repo / "artifacts/goal/mw"
    raw = base / "real-semantic.jsonl"
    train = base / "real-semantic-train.jsonl"
    test = base / "real-semantic-test.jsonl"
    _write(raw, '{"id": "a"}\n')
    _write(train, '{"id": "a", "labels": {}}\n')
    _write(test, '{"id": "t"}\n')

    def canon(path: Path) -> str:
        rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()

    manifest = {"raw": hashlib.sha256(raw.read_bytes()).hexdigest(), "train": canon(train),
                "test": canon(test), "rawRows": 1, "trainRows": 1, "testRows": 1}
    _write(base / "real-semantic-manifest.json", json.dumps(manifest))

    frozen = base / "frozen.json"
    _write(frozen, "{}")
    _write(base / "frozen.json.sha256", hashlib.sha256(b"{}").hexdigest() + "  frozen.json\n")

    index = build_index(repo, ["artifacts/goal"], with_last_commit=False)
    report = validate(index, repo)
    assert report["checks"]["semantic_manifest"]["count"] == 0
    assert report["checks"]["sidecar_hash"]["count"] == 0

    _write(train, '{"id": "a", "labels": {"x": 1}}\n')
    index = build_index(repo, ["artifacts/goal"], with_last_commit=False)
    report = validate(index, repo)
    assert report["checks"]["semantic_manifest"]["count"] == 1
    assert report["checks"]["semantic_manifest"]["findings"][0]["key"] == "train"


def test_split_check_flags_overlap(tmp_path):
    from tools.experiment_platform.split_sets import check

    repo = tmp_path
    _write(repo / "data/train.jsonl", '{"id": "a"}\n{"id": "b"}\n')
    _write(repo / "data/eval.jsonl", '{"id": "b"}\n{"id": "c"}\n')
    _write(repo / "data/hold.json", '["a", "b", "x"]\n')
    registry = {
        "sets": [
            {"name": "train", "path": "data/train.jsonl", "key": "id"},
            {"name": "eval", "path": "data/eval.jsonl", "key": "id"},
            {"name": "hold", "path": "data/hold.json", "key": "list"},
        ],
        "pairs": [
            {"left": "train", "right": "eval", "expect": "disjoint"},
            {"left": "hold", "right": "train", "expect": "subset"},
            {"left": "hold", "right": "eval", "expect": "report"},
        ],
    }
    report = check(repo, registry)
    assert report["pairs"][0]["overlap"] == 1 and report["pairs"][0]["ok"] is False
    assert report["pairs"][1]["ok"] is False  # x is not in train
    assert report["pairs"][2]["ok"] is True
    assert report["failed"] is True


def test_evidence_refs_flagged(tmp_path):
    from tools.experiment_platform.data_index import build_index
    from tools.experiment_platform.validate_data import validate

    repo = tmp_path
    _write(repo / "artifacts/goal/fam/e.json", "{}")
    _write(repo / "artifacts/goal/fam/inputs.jsonl",
           '{"id": "x", "evidence": "e.json"}\n{"id": "y", "evidence": "missing.json"}\n')
    index = build_index(repo, ["artifacts/goal"], with_last_commit=False)
    findings = validate(index, repo)["checks"]["evidence_ref"]["findings"]
    statuses = {(f["evidence"], f["status"]) for f in findings}
    assert ("e.json", "untracked") in statuses
    assert ("missing.json", "missing") in statuses


def test_clean_tree_passes(tmp_path):
    from tools.experiment_platform.data_index import build_index
    from tools.experiment_platform.validate_data import validate

    repo = tmp_path
    _write(repo / "artifacts/goal/fam/train.jsonl", '{"id": 1}\n{"id": 2}\n')
    index = build_index(repo, ["artifacts/goal"], with_last_commit=False)
    report = validate(index, repo)
    assert report["summary"]["malformed"]["status"] == "pass"
    assert report["summary"]["duplicate_content"]["status"] == "pass"
    assert report["failed"] is False
