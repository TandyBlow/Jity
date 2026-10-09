"""Parametrized ground-truth tests for the Examiner corpus.

Each corpus case asserts one expected ruling. Cases flagged `known_bug` are
expected to fail against the current implementation: they xfail here, and the
flag must be removed from the JSON once the fix lands (a passing known_bug
case fails the suite on purpose).

The D (entry_integration) cases run merge_entry_state before examining; they
carry no known_bug flags — a regression there is always a hard failure.
"""

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from examiner_corpus_report import evaluate, load_corpus, run_case  # noqa: E402

CORPUS = load_corpus()
UNIT_CASES = [c for c in CORPUS["cases"] if "entry" not in c]
ENTRY_CASES = [c for c in CORPUS["cases"] if "entry" in c]


def _assert_case(case: dict) -> None:
    ruling = run_case(case, CORPUS["fixtures"])
    ok, kind, detail = evaluate(ruling, case["expected"])
    assert ok, f"{case['id']} [{case['category']}] {kind}: {detail}"


@pytest.mark.parametrize("case", UNIT_CASES, ids=lambda c: c["id"])
def test_examiner_corpus(case: dict) -> None:
    try:
        _assert_case(case)
    except AssertionError:
        if case.get("known_bug"):
            ruling = run_case(case, CORPUS["fixtures"])
            _, kind, detail = evaluate(ruling, case["expected"])
            pytest.xfail(f"known_bug {case['id']}: {kind}: {detail}")
        raise
    if case.get("known_bug"):
        pytest.fail(f"{case['id']} 标记 known_bug 但已通过——请从语料中删除该标志")


@pytest.mark.parametrize("case", ENTRY_CASES, ids=lambda c: c["id"])
def test_entry_integration(case: dict) -> None:
    _assert_case(case)
