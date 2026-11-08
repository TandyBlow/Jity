# -*- coding: utf-8 -*-
"""Turn a filled sign-off form into runs/r2/signoff.json.

Refuses to produce a signed record unless every required field is present and
every row carries a verdict from the frozen value list. The AI verdicts are
copied into the signed record so the two layers stay distinguishable; the
human verdict is what decides, and `unsure` never counts as passing.

Usage:
    python -X utf8 apply_signoff.py            # writes signoff.json if complete
    python -X utf8 apply_signoff.py --show     # print what is still missing
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "runs" / "r2"
FORM = RUN / "signoff-form.json"
OUT = RUN / "signoff.json"
CRITERIA = HERE / "freeze" / "criteria-v2.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    if not FORM.exists():
        print(f"{FORM} does not exist; run build_signoff_form.py first")
        return 1
    form = json.loads(FORM.read_text(encoding="utf-8"))
    criteria = json.loads(CRITERIA.read_text(encoding="utf-8"))
    allowed = criteria["manualReview"]["verdictValues"]

    missing: list[str] = []
    for field in ("signer", "date", "reviewedCommit"):
        if not str(form.get(field, "")).strip():
            missing.append(field)
    for row in form.get("rows", []):
        if row.get("humanVerdict") not in allowed:
            missing.append(f"{row['queueId']}: humanVerdict")

    # pinned inputs must still describe the files on disk
    pins = form.get("pinnedInputs", {})
    drift = []
    checks = [
        ("criteria", HERE / "freeze" / "criteria-v2.json"),
        ("tamperProbes", HERE / "freeze" / "tamper-probes.json"),
        ("manualReview", HERE / "runs" / "r2" / "manual-review.json"),
    ]
    for key, path in checks:
        want = pins.get(key, {}).get("sha256")
        if want and path.exists() and want != sha256(path):
            drift.append(f"{path.relative_to(HERE)} changed since the form was generated")
    checker_pin = pins.get("checker", {}).get("sha256")
    actual_checker = sha256(HERE / "text_conformance.py")
    if checker_pin and checker_pin != actual_checker:
        drift.append("text_conformance.py changed since the form was generated")

    if args.show or missing or drift:
        print(json.dumps({
            "status": "incomplete" if (missing or drift) else "complete",
            "missing": missing,
            "drift": drift,
            "rows": len(form.get("rows", [])),
        }, ensure_ascii=False, indent=1))
        return 0 if not (missing or drift) else 1

    counts = {"paraphrase-ok": 0, "new-content-fail": 0, "unsure": 0}
    for row in form["rows"]:
        counts[row["humanVerdict"]] += 1

    doc = {
        "formVersion": form["formVersion"],
        "signed": True,
        "signer": form["signer"],
        "signerRole": form.get("signerRole", "project-owner"),
        "date": form["date"],
        "reviewedCommit": form["reviewedCommit"],
        "pinnedInputs": pins,
        "driftAtSignoff": drift,
        "humanCounts": counts,
        "rows": [
            {"queueId": r["queueId"], "code": r["code"], "aiVerdict": r.get("aiVerdict"),
             "humanVerdict": r["humanVerdict"], "humanNote": r.get("humanNote", "")}
            for r in form["rows"]
        ],
        "identitySha256": hashlib.sha256(
            json.dumps(form, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(json.dumps({"signer": doc["signer"], "humanCounts": counts}, ensure_ascii=False, indent=1))
    print("now re-run apply_review.py to recompute the gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
