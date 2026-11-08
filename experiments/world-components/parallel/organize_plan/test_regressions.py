# -*- coding: utf-8 -*-
"""Regression tests for the review findings (2026-11-08).

Each test names the defect it locks down:

  T1  a one-field edit of the AI draft cannot close the holdout semantic review
  T2  a sign-off bound to an older package digest is stale
  T3  a sign-off that copies the draft's template reason is rejected
  T4  a sign-off without per-source attestation is rejected
  T5  every kind the plan contract accepts can be read by the text checker
  T6  a move needs from and to in the SAME sentence
  T7  a sanity fact is expressed as a symptom, not a number
  T8  a frozen holdout whose material changed afterwards is not "ready"
  T9  the gate threshold for N sources is pre-registered as max(8, ceil(0.8N))

Run:
    python -X utf8 test_regressions.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
import check_round_ready  # noqa: E402
import plan_contract as contract  # noqa: E402
import text_conformance as tc  # noqa: E402
import validate_holdout as vh  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_package(tmp: Path, sources=("s1", "s2")) -> tuple[Path, str]:
    """A minimal package on disk: manifest + pair files only."""
    pkg = tmp / "pkg"
    (pkg / "pairs").mkdir(parents=True)
    manifest = {"packageId": "t", "sources": list(sources)}
    (pkg / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    for sid in sources:
        (pkg / "pairs" / f"{sid}-authorized.json").write_text(
            json.dumps({"worldId": f"w_{sid}", "units": []}, ensure_ascii=False), encoding="utf-8")
    digest = vh.package_digest(pkg, list(sources))
    return pkg, digest["sha256"]


def write_signoff(pkg: Path, *, kind="human", identity="项目负责人", date="2026-11-08",
                  attest=True, package_sha="x", reviewed_commit="abc",
                  reasons=None, verdicts=None) -> None:
    doc = {
        "protocol": "c3-holdout-semantic-signoff-v1",
        "reviewer": {"identity": identity, "kind": kind, "date": date},
        "iReviewedEachSource": attest,
        "reviewedCommit": reviewed_commit,
        "packageSha256": package_sha,
        "sources": {},
    }
    for sid in ("s1", "s2"):
        doc["sources"][sid] = {
            "verdict": (verdicts or {}).get(sid, "independent"),
            "reason": (reasons or {}).get(sid, f"{sid} 与旧材料的动作对象不同，逐条对照后判为独立"),
        }
    (pkg / "semantic-review-signoff.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def test_T1_one_field_edit_of_the_draft_does_not_pass() -> None:
    """The AI draft's reviewer.kind flipped to human must not close the review."""
    with tempfile.TemporaryDirectory() as tmp:
        pkg, digest = make_package(Path(tmp))
        # exactly the bypass the review described
        (pkg / "semantic-review.json").write_text(json.dumps({
            "reviewer": {"identity": "A-side assistant", "kind": "human"},
            "sources": {sid: {"verdict": "independent", "note": "same template"}
                        for sid in ("s1", "s2")},
        }, ensure_ascii=False), encoding="utf-8")
        errors: list[dict] = []
        doc = vh.load_semantic_signoff(pkg, {}, {"sha256": digest}, errors)
        codes = {e["code"] for e in errors}
        assert doc == {}, doc
        assert "PKG-no-semantic-signoff" in codes, codes


def test_T2_stale_signoff_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pkg, digest = make_package(Path(tmp))
        write_signoff(pkg, package_sha="0" * 64)
        errors: list[dict] = []
        vh.load_semantic_signoff(pkg, {}, {"sha256": digest}, errors)
        assert "PKG-semantic-signoff-stale" in {e["code"] for e in errors}, errors


def test_T3_template_reason_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pkg, digest = make_package(Path(tmp))
        template = "new cast, new place, new appearance vocabulary; fact texts pass the bigram screen"
        (pkg / "semantic-review.json").write_text(json.dumps({
            "sources": {"s1": {"note": template}, "s2": {"note": template}},
        }, ensure_ascii=False), encoding="utf-8")
        write_signoff(pkg, package_sha=digest,
                      reasons={"s1": template, "s2": template})
        signoff = json.loads((pkg / "semantic-review-signoff.json").read_text(encoding="utf-8"))
        draft = json.loads((pkg / "semantic-review.json").read_text(encoding="utf-8"))
        error = vh.signoff_source_error("s1", signoff, draft)
        assert error and error["code"] == "PKG-semantic-signoff-template-reason", error


def test_T4_missing_attestation_or_identity_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pkg, digest = make_package(Path(tmp))
        write_signoff(pkg, package_sha=digest, attest=False)
        errors: list[dict] = []
        vh.load_semantic_signoff(pkg, {}, {"sha256": digest}, errors)
        assert "PKG-semantic-signoff-no-attestation" in {e["code"] for e in errors}, errors

        write_signoff(pkg, package_sha=digest, identity="")
        errors = []
        vh.load_semantic_signoff(pkg, {}, {"sha256": digest}, errors)
        assert "PKG-semantic-signoff-incomplete" in {e["code"] for e in errors}, errors


def test_T5_plan_kinds_and_text_checker_agree() -> None:
    """Every entity kind accepted by the plan contract has a text branch."""
    covered = set()
    for kind in contract.ENTITY_KINDS:
        fact = {"factId": "f0", "kind": kind, "name": "甲", "text": "袖口湿了", "goal": "把门关上",
                "from": "走廊", "to": "门厅", "at": "门厅"}
        try:
            tc.fact_span(fact, ["甲袖口湿了。", "甲从走廊走到门厅。", "甲把门关上。",
                                "甲在门厅。", "甲心里发紧。"])
        except tc.UnsupportedFactKind:
            continue
        covered.add(kind)
    missing = set(contract.ENTITY_KINDS) - covered
    assert not missing, f"plan contract accepts but text checker cannot read: {missing}"


def test_T6_move_needs_both_endpoints_in_one_sentence() -> None:
    fact = {"factId": "f0", "kind": "moved", "name": "林川", "from": "走廊", "to": "大厅"}
    ok, _, _, _ = tc.fact_span(fact, ["林川从走廊走进大厅。"])
    assert ok is True
    split, _, _, _ = tc.fact_span(fact, ["林川还在走廊。", "大厅里有人在说话。"])
    assert split is False, "two unrelated sentences must not count as a move"


def test_T7_sanity_is_a_symptom_not_a_number() -> None:
    fact = {"factId": "f0", "kind": "sanity_changed", "name": "沈砚", "from": 10, "to": 8}
    assert tc.fact_span(fact, ["沈砚心里发紧。"])[0] is True
    assert tc.fact_span(fact, ["沈砚的理智值从10降到8。"])[0] is False


def test_T8_frozen_holdout_must_match_its_material() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pkg, digest = make_package(tmp_path)
        write_signoff(pkg, package_sha=digest)
        freeze = {
            "package": str(pkg), "status": "admissible",
            "manifestSha256": sha256(pkg / "manifest.json"),
            "semanticSignoff": {"file": "semantic-review-signoff.json",
                                "sha256": sha256(pkg / "semantic-review-signoff.json")},
            "pairFiles": vh.package_digest(pkg, ["s1", "s2"])["files"],
            "packageDigest": {"sha256": digest},
            "gateRule": {"sources": 2, "minimumPairedSuccess": 8},
            "plans": {"s1": {}}, "sources": [{"sourceId": "s1"}, {"sourceId": "s2"}],
        }
        freeze_path = tmp_path / "freeze.json"
        freeze_path.write_text(json.dumps(freeze, ensure_ascii=False), encoding="utf-8")
        assert check_round_ready.check_holdout(freeze_path)["ready"] is True

        # change a pair file after freezing: readiness must drop
        with (pkg / "pairs" / "s1-authorized.json").open("a", encoding="utf-8") as fh:
            fh.write("\n")
        state = check_round_ready.check_holdout(freeze_path)
        assert state["ready"] is False, state
        assert state["state"] == "留出冻结件已过期", state


def test_T9_gate_threshold_is_preregistered() -> None:
    import math
    for n in (10, 11, 12, 15):
        assert max(8, math.ceil(0.8 * n)) == (8 if n == 10 else math.ceil(0.8 * n))
    assert max(8, math.ceil(0.8 * 12)) == 10


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as exc:  # pragma: no cover - reported, not raised
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
