"""Tests for the short-pair derivation: index arithmetic, conflict gate, build/check.

The serializer is a test double written into a temp file; it exists only to
exercise the build/check plumbing. The real text comes from 04's
`experiments/action-next-step/pairwise_serialize.py` and is never copied here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "short_pairs"))

import build_pairs  # noqa: E402
import pair_index  # noqa: E402

ROWS = HERE / "rows" / "train13-full-candidates.jsonl"
LABELS = Path("D:/others/Jity/.local/parallel-local-game/results/action-dataset-20261111/labels-v1.json")
RESOLUTION = Path(
    "D:/others/Jity/.local/parallel-local-game/results/action-short-pairs-20261111/13/proposed-resolution.json"
)

pytestmark = pytest.mark.skipif(
    not (ROWS.exists() and LABELS.exists() and RESOLUTION.exists()),
    reason="frozen rows, labels or the proposed resolution are not present",
)


def run_index(tmp_path: Path, resolution: Path | None) -> int:
    argv = [
        "--rows", str(ROWS),
        "--labels", str(LABELS),
        "--out-dir", str(tmp_path),
    ]
    if resolution:
        argv += ["--resolution", str(resolution)]
    return pair_index.main(argv)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


STUB = '''
VERSION = "stub-pairwise"
ALL_GROUPS = ["感知", "移动", "战斗", "援助", "请求", "胁迫", "言语", "算计", "情绪", "物品", "身体", "立场", "不动"]


def short_context(row):
    x = row["x"]
    context = {
        "tasks": "|".join(goal.split("：", 1)[-1][:18] for goal in x["goals"]),
        "place": x["place"],
        "present": [entry["name"] for entry in x["present"][:3]],
        "items": [entry["name"] for entry in x["items"][:3]],
        "recent": "；".join(x["recent"][-2:]),
    }
    omitted = {"goalsClipped": 0, "presentOmitted": x["present"][3:], "itemsOmitted": x["items"][3:], "recentTotal": len(x["recent"])}
    return context, omitted


def render_pair(context, group, *, prior=None):
    lines = [
        f"任务：{context['tasks']}",
        f"所见：{context['place']}；在场：{'，'.join(context['present']) or '（无）'}；物品：{'，'.join(context['items']) or '（无）'}",
        f"刚见：{context['recent'] or '（无）'}",
    ]
    if prior:
        lines.append(f"已做：{prior['group']}（{prior.get('object') or '无'}）")
    lines.append(f"动作：{group}")
    return "\\n".join(lines)
'''


def write_stub(tmp_path: Path, *, collapse: bool = False) -> Path:
    source = STUB if not collapse else STUB.replace(
        '"recent": "；".join(x["recent"][-2:]),', '"recent": "",'
    ).replace('"place": x["place"],', '"place": "同一处",')
    path = tmp_path / "stub_pairwise.py"
    path.write_text(source, encoding="utf-8")
    return path


def test_conflicts_are_the_four_frozen_groups(tmp_path: Path) -> None:
    code = run_index(tmp_path, resolution=None)
    assert code == 2
    report = json.loads((tmp_path / "index-report.json").read_text(encoding="utf-8")) if (tmp_path / "index-report.json").exists() else None
    assert report is None  # refusal writes nothing
    # the refusal message names every conflicting row
    rows = {row["rowId"] for row in read_jsonl(ROWS)}
    assert {"train13r-0003", "b2-0010", "train13r-0004", "b2-0030"} <= rows


def test_index_counts_with_resolution(tmp_path: Path) -> None:
    assert run_index(tmp_path, RESOLUTION) == 0
    report = json.loads((tmp_path / "index-report.json").read_text(encoding="utf-8"))
    counts = report["counts"]
    assert counts["rowsInFile"] == 300
    assert counts["rowsExcluded"] == 5
    assert counts["rowsUsed"] == 295
    assert counts["decisions"] == 295 + 30
    assert counts["pairs"] == 13 * counts["decisions"] == 4225
    assert counts["positives"] == counts["decisions"]


def test_every_decision_has_thirteen_pairs_and_one_positive(tmp_path: Path) -> None:
    assert run_index(tmp_path, RESOLUTION) == 0
    pairs = read_jsonl(tmp_path / "pairs-index.jsonl")
    by_decision: dict[tuple[str, int], list[dict]] = {}
    for pair in pairs:
        by_decision.setdefault((pair["rowId"], pair["stepIndex"]), []).append(pair)
    for group in by_decision.values():
        assert len(group) == 13
        assert sum(1 for pair in group if pair["positive"]) == 1


def test_skip_rows_are_the_thirteenth_candidate(tmp_path: Path) -> None:
    assert run_index(tmp_path, RESOLUTION) == 0
    rows = {row["rowId"]: row for row in read_jsonl(ROWS)}
    pairs = read_jsonl(tmp_path / "pairs-index.jsonl")
    skips = {(pair["rowId"], pair["stepIndex"]) for pair in pairs if rows[pair["rowId"]]["y"]["steps"] == []}
    assert skips
    for pair in pairs:
        if (pair["rowId"], pair["stepIndex"]) in skips and pair["positive"]:
            assert pair["candidateGroup"] == "不动"
            assert pair["action"] is None


def test_second_step_carries_the_first_step_only(tmp_path: Path) -> None:
    assert run_index(tmp_path, RESOLUTION) == 0
    pairs = read_jsonl(tmp_path / "pairs-index.jsonl")
    second = [pair for pair in pairs if pair["stepIndex"] == 1]
    assert {pair["rowId"] for pair in second} == {
        row["rowId"] for row in read_jsonl(ROWS) if len(row["y"]["steps"]) == 2
    }
    for pair in second:
        assert pair["doneGroup"] is not None
        assert pair["doneGroup"] != pair["labelGroup"] or pair["doneGroup"] == pair["labelGroup"]
        assert pair["positive"] == (pair["candidateGroup"] == pair["labelGroup"])


def test_build_refuses_short_texts_shared_by_two_decisions(tmp_path: Path) -> None:
    assert run_index(tmp_path, RESOLUTION) == 0
    stub = write_stub(tmp_path, collapse=True)
    with pytest.raises(SystemExit) as error:
        build_pairs.main([
            "--rows", str(ROWS),
            "--index", str(tmp_path / "pairs-index.jsonl"),
            "--serializer", str(stub),
            "--out-dir", str(tmp_path / "out"),
        ])
    assert "short X strings" in str(error.value)


def test_build_and_check_roundtrip_with_a_stub_serializer(tmp_path: Path) -> None:
    assert run_index(tmp_path, RESOLUTION) == 0
    stub = write_stub(tmp_path)
    out = tmp_path / "out"
    assert build_pairs.main([
        "--rows", str(ROWS),
        "--index", str(tmp_path / "pairs-index.jsonl"),
        "--serializer", str(stub),
        "--out-dir", str(out),
    ]) == 0
    report = json.loads((out / "build-report.json").read_text(encoding="utf-8"))
    assert report["pairs"] == 4225
    assert report["serializer"]["version"] == "stub-pairwise"

    import check_pairs

    assert check_pairs.main([
        "--rows", str(ROWS),
        "--pairs", str(out / "pairs.jsonl"),
        "--serializer", str(stub),
        "--tokenizer-dir", "D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot",
        "--max-len", "512",
        "--out", str(out / "check.json"),
    ]) == 0
    check = json.loads((out / "check.json").read_text(encoding="utf-8"))
    assert check["ok"] is True
    assert check["tokens"]["overMaxLen"] == 0


def test_check_catches_a_tampered_text(tmp_path: Path) -> None:
    assert run_index(tmp_path, RESOLUTION) == 0
    stub = write_stub(tmp_path)
    out = tmp_path / "out"
    assert build_pairs.main([
        "--rows", str(ROWS),
        "--index", str(tmp_path / "pairs-index.jsonl"),
        "--serializer", str(stub),
        "--out-dir", str(out),
    ]) == 0
    pairs = read_jsonl(out / "pairs.jsonl")
    pairs[0]["text"] = pairs[0]["text"].replace("动作：", "动作： ")
    (out / "pairs.jsonl").write_text(
        "\n".join(json.dumps(pair, ensure_ascii=False) for pair in pairs) + "\n", encoding="utf-8", newline="\n"
    )

    import check_pairs

    assert check_pairs.main([
        "--rows", str(ROWS),
        "--pairs", str(out / "pairs.jsonl"),
        "--serializer", str(stub),
        "--tokenizer-dir", "D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot",
        "--out", str(out / "check.json"),
    ]) == 1
    check = json.loads((out / "check.json").read_text(encoding="utf-8"))
    assert check["ok"] is False
    assert any("differs from a fresh render" in problem for problem in check["problems"])
