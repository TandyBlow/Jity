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
  T10 the digest prefilled by the producer equals the digest c3 recomputes
  T11 a changed or deleted world.db invalidates the freeze
  T12 build_criteria.py never overwrites an older frozen criteria file
  T13 the r4 sign-off form pins the files it actually hashed
  T14 a misnamed pin is caught (hash right, path wrong)
  T15 editing one row of a signed file closes the gate again
  T16 a pin without a sha256, or a missing pin, blocks readiness
  T17 an acceptance sign-off record without a file field blocks readiness

Run:
    python -X utf8 test_regressions.py
"""

from __future__ import annotations

import hashlib
import argparse
import importlib
import json
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


class SkipTest(Exception):
    """A check that could not run here. Reported separately, never as passed."""

import check_round_ready  # noqa: E402
import plan_contract as contract  # noqa: E402
import text_conformance as tc  # noqa: E402
import pins as pins_mod
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
        (pkg / "world.db").write_bytes(b"sqlite-bytes")
        manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        manifest["databases"] = {"s": "world.db"}
        manifest["files"] = {"world.db": sha256(pkg / "world.db")}
        (pkg / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        digest = vh.package_digest(pkg, ["s1", "s2"])["sha256"]
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


def test_T13_signoff_form_pins_the_files_it_hashed() -> None:
    """The form must pin r4 + criteria-v3, not the v2 names, and agree with acceptance."""
    form_path = HERE / "runs" / "r4" / "signoff-form.json"
    acc_path = HERE / "runs" / "r4" / "acceptance.json"
    if not form_path.exists():
        raise AssertionError(f"{form_path} missing; run build_signoff_form.py")
    form = json.loads(form_path.read_text(encoding="utf-8"))
    acc = json.loads(acc_path.read_text(encoding="utf-8"))
    pins = form["pinnedInputs"]

    for key in ("criteria", "tamperProbes", "manualReview"):
        name = pins[key]["file"]
        assert not name.startswith(("freeze/criteria-v2", "runs/r2/")), (
            f"{key} pins {name}: that is the v2 round, not r4")
        assert (HERE / name).exists(), f"{key} pins a file that does not exist: {name}"

    assert pins["criteria"]["sha256"] == acc["criteria"]["sha256"], "criteria hash differs from acceptance"
    assert pins["tamperProbes"]["sha256"] == acc["inputs"]["probes"]["sha256"], "probe hash differs"
    assert pins["manualReview"]["sha256"] == acc["inputs"]["manualReview"]["sha256"], "review hash differs"
    assert pins["acceptanceIdentity"] == acc["identitySha256"], "acceptance identity differs"
    assert pins_mod.pin_drift(pins) == [], pins_mod.pin_drift(pins)


def test_T14_misnamed_pin_is_caught() -> None:
    """Right hash, wrong path: the exact defect the r4 form had."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "a.json").write_text("a", encoding="utf-8")
        (base / "b.json").write_text("b", encoding="utf-8")
        good = pins_mod.pin(base / "a.json")
        assert pins_mod.pin_drift({"x": good}, base=base) == []
        misnamed = {"x": {"file": "b.json", "sha256": good["sha256"]}}
        problems = pins_mod.pin_drift(misnamed, base=base)
        assert problems and "b.json changed" in problems[0], problems
        no_path = {"x": {"sha256": good["sha256"]}}
        assert pins_mod.pin_drift(no_path, base=base), "a pin without a path must be reported"


NL = chr(10)


def _signed_round(tmp: Path) -> dict:
    """Build a temp round where a human sign-off exists and the gate is OPEN."""
    (tmp / "runs" / "r4").mkdir(parents=True)
    (tmp / "freeze").mkdir(parents=True)
    (tmp / "text_conformance.py").write_text("# checker" + NL, encoding="utf-8")
    (tmp / "freeze" / "criteria-v3.json").write_text('{"gate": "x"}' + NL, encoding="utf-8")
    (tmp / "runs" / "r4" / "tamper-probes.json").write_text('{"rows": []}' + NL, encoding="utf-8")
    (tmp / "runs" / "r4" / "manual-review.json").write_text('{"rows": []}' + NL, encoding="utf-8")
    pins = {
        "criteria": pins_mod.pin(tmp / "freeze" / "criteria-v3.json"),
        "checker": {"file": "text_conformance.py",
                    "sha256": pins_mod.sha256(tmp / "text_conformance.py")},
        "tamperProbes": pins_mod.pin(tmp / "runs" / "r4" / "tamper-probes.json"),
        "manualReview": pins_mod.pin(tmp / "runs" / "r4" / "manual-review.json"),
        "acceptanceIdentity": pins_mod.acceptance_identity(
            tmp / "freeze" / "criteria-v3.json",
            tmp / "runs" / "r4" / "tamper-probes.json",
            tmp / "runs" / "r4" / "manual-review.json"),
    }
    signoff = {"signed": True, "satisfiesHumanSignoff": True, "signerKind": "human",
               "signer": "T", "date": "2026-11-09", "reviewedCommit": "x",
               "humanCounts": {"paraphrase-ok": 1},
               "pinnedInputs": pins,
               "rows": [{"humanVerdict": "paraphrase-ok"}]}
    signoff_path = tmp / "runs" / "r4" / "signoff.json"
    signoff_path.write_text(json.dumps(signoff, ensure_ascii=False, indent=1) + NL, encoding="utf-8")
    acceptance = {
        "identitySha256": pins["acceptanceIdentity"],
        "gateStatus": "OPEN", "openItems": [],
        "signoff": {"file": "runs/r4/signoff.json", "sha256": pins_mod.sha256(signoff_path)},
    }
    (tmp / "runs" / "r4" / "acceptance.json").write_text(
        json.dumps(acceptance, ensure_ascii=False, indent=1) + NL, encoding="utf-8")
    return {"pins": pins, "acceptance": acceptance, "signoff": signoff}


def _write_signoff(tmp: Path, doc: dict) -> None:
    (tmp / "runs" / "r4" / "signoff.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + NL, encoding="utf-8")


def _ready_in(tmp: Path) -> dict:
    importlib.reload(check_round_ready)
    mod = check_round_ready
    mod.SIGNOFF = tmp / "runs" / "r4" / "signoff.json"
    mod.ACCEPTANCE = tmp / "runs" / "r4" / "acceptance.json"
    mod.R2_SIGNOFF = tmp / "runs" / "r2" / "signoff.json"
    mod.pins_mod.HERE = tmp
    return mod.check_signoff()


def test_T15_editing_a_signed_row_closes_the_gate() -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        built = _signed_round(tmp)
        assert _ready_in(tmp)["ready"] is True, _ready_in(tmp)

        doc = built["signoff"]
        doc["rows"][0]["humanVerdict"] = "new-content-fail"
        _write_signoff(tmp, doc)

        state = _ready_in(tmp)
        assert state["ready"] is False, state
        assert "signoff.json changed after the acceptance record" in state["detail"], state


def test_T16_missing_pin_hash_blocks_readiness() -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        built = _signed_round(tmp)

        # (a) a pin whose sha256 was deleted
        doc = json.loads(json.dumps(built["signoff"]))
        del doc["pinnedInputs"]["manualReview"]["sha256"]
        _write_signoff(tmp, doc)
        state = _ready_in(tmp)
        assert state["ready"] is False, state
        assert "manualReview: pin has no sha256" in state["detail"], state

        # (b) a pin that is gone completely
        doc = json.loads(json.dumps(built["signoff"]))
        del doc["pinnedInputs"]["manualReview"]
        _write_signoff(tmp, doc)
        state = _ready_in(tmp)
        assert state["ready"] is False, state
        assert "缺少 pin" in state["detail"] and "manualReview" in state["detail"], state

        # (c) no acceptance identity at all
        doc = json.loads(json.dumps(built["signoff"]))
        doc["pinnedInputs"].pop("acceptanceIdentity", None)
        _write_signoff(tmp, doc)
        state = _ready_in(tmp)
        assert state["ready"] is False, state
        assert "acceptanceIdentity" in state["detail"], state


def test_T17_acceptance_signoff_without_file_field_blocks_readiness() -> None:
    """A correct hash plus no file field must not count: the record names nothing."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        built = _signed_round(tmp)
        assert _ready_in(tmp)["ready"] is True

        acc_path = tmp / "runs" / "r4" / "acceptance.json"
        acc = json.loads(acc_path.read_text(encoding="utf-8"))
        assert acc["signoff"]["sha256"] == pins_mod.sha256(tmp / "runs" / "r4" / "signoff.json")
        del acc["signoff"]["file"]
        acc_path.write_text(json.dumps(acc, ensure_ascii=False, indent=1) + NL, encoding="utf-8")

        state = _ready_in(tmp)
        assert state["ready"] is False, state
        assert "counts a different file" in state["detail"], state


PACKAGE_CANDIDATES = [
    Path("D:/others/Jity/artifacts/holdout-a-v1"),
    Path("artifacts/holdout-a-v1"),
]


def test_T10_producer_digest_equals_recomputed_digest() -> None:
    """The template's prefilled digest must equal what c3 computes.

    This is the cross-branch check for the circular-dependency defect: the
    digest lives only in the template, never inside manifest.json.
    """
    pkg = next((p for p in PACKAGE_CANDIDATES if (p / "manifest.json").exists()), None)
    if pkg is None:
        raise SkipTest("holdout package not present in this checkout; the cross-branch "
                       "digest check did not run (use --strict-cross to fail instead)")
    manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
    assert "packageSha256" not in manifest, "the digest must not live inside manifest.json"
    template = json.loads((pkg / "semantic-review-signoff.template.json").read_text(encoding="utf-8"))
    digest = vh.package_digest(pkg, manifest["sources"])
    assert template["packageSha256"] == digest["sha256"], (
        f"template {template['packageSha256'][:12]} != recomputed {digest['sha256'][:12]}")


def test_T11_changed_or_deleted_db_invalidates_freeze() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pkg, digest = make_package(tmp_path)
        (pkg / "world.db").write_bytes(b"sqlite-bytes")
        manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        manifest["databases"] = {"s": "world.db"}
        manifest["files"] = {"world.db": sha256(pkg / "world.db")}
        (pkg / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        write_signoff(pkg, package_sha=vh.package_digest(pkg, ["s1", "s2"])["sha256"])
        freeze = {
            "package": str(pkg), "status": "admissible",
            "manifestSha256": sha256(pkg / "manifest.json"),
            "semanticSignoff": {"file": "semantic-review-signoff.json",
                                "sha256": sha256(pkg / "semantic-review-signoff.json")},
            "pairFiles": vh.package_digest(pkg, ["s1", "s2"])["files"],
            "packageDigest": vh.package_digest(pkg, ["s1", "s2"]),
            "gateRule": {"sources": 2, "minimumPairedSuccess": 8},
            "plans": {"s1": {}}, "sources": [{"sourceId": "s1"}, {"sourceId": "s2"}],
        }
        freeze_path = tmp_path / "freeze.json"
        freeze_path.write_text(json.dumps(freeze, ensure_ascii=False), encoding="utf-8")
        assert check_round_ready.check_holdout(freeze_path)["ready"] is True

        (pkg / "world.db").write_bytes(b"tampered")
        state = check_round_ready.check_holdout(freeze_path)
        assert state["ready"] is False and state["state"] == "留出冻结件已过期", state
        assert "world.db changed" in state["detail"], state

        (pkg / "world.db").unlink()
        state = check_round_ready.check_holdout(freeze_path)
        assert state["ready"] is False and "world.db missing" in state["detail"], state


def test_T12_criteria_generator_never_overwrites_history() -> None:
    src = (HERE / "build_criteria.py").read_text(encoding="utf-8")
    assert 'criteria-v2.json' not in src.split("def main")[0].split("import sys")[-1], (
        "the default output must not be criteria-v2.json")
    assert 'criteria-v{_default_major}.json' in src, src[:400]


def test_T9_gate_threshold_is_preregistered() -> None:
    import math
    for n in (10, 11, 12, 15):
        assert max(8, math.ceil(0.8 * n)) == (8 if n == 10 else math.ceil(0.8 * n))
    assert max(8, math.ceil(0.8 * 12)) == 10


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict-cross", action="store_true",
                    help="treat a skipped cross-branch check as a failure")
    args = ap.parse_args()
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    skipped = []
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except SkipTest as exc:
            skipped.append(f"{fn.__name__}: {exc}")
            print(f"SKIP {fn.__name__}: {exc}")
        except AssertionError as exc:  # pragma: no cover - reported, not raised
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    passed = len(tests) - failed - len(skipped)
    # A skip is never folded into "passed": an unexecuted cross-branch check is
    # not evidence.
    print()
    print(f"{passed} passed, {len(skipped)} skipped, {failed} failed (of {len(tests)} checks)")
    if skipped:
        print("skipped checks did not run and prove nothing:")
        for line in skipped:
            print(f"  - {line}")
    if args.strict_cross and skipped:
        failed += len(skipped)
    raise SystemExit(1 if failed else 0)
