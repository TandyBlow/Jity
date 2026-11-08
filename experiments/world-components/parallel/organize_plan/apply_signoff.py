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
def newest_criteria() -> Path:
    found = sorted((HERE / "freeze").glob("criteria-v[0-9]*.json"))
    return found[-1] if found else HERE / "freeze" / "criteria-v2.json"


RUN = HERE / "runs" / "r4"
FORM = RUN / "signoff-form.json"
OUT = RUN / "signoff.json"
CRITERIA = newest_criteria()


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
    # A human sign-off must also attest that each row was read. AI/audit records
    # are allowed to omit it; the gate treats them as audit-only anyway.
    if form.get("signerKind") == "human" and form.get("iReviewedEachRow") is not True:
        missing.append("iReviewedEachRow")
    for field in ("signer", "signerRole", "signerKind", "date", "reviewedCommit"):
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

    is_human = form["signerKind"] == "human"
    doc = {
        "formVersion": form["formVersion"],
        "signed": True,
        # "signed" only means the form was completed. Whether that can satisfy
        # a human sign-off requirement is a separate, explicit field.
        "signoffClass": "human" if is_human else "audit-only",
        "satisfiesHumanSignoff": is_human,
        "auditOnly": not is_human,
        "signer": form["signer"],
        "signerRole": form["signerRole"],
        "signerKind": form["signerKind"],
        "iReviewedEachRow": form.get("iReviewedEachRow") is True,
        "delegationNote": form.get("delegationNote", ""),
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
    print(json.dumps({"signer": doc["signer"], "signerKind": doc["signerKind"],
                      "signoffClass": doc["signoffClass"],
                      "satisfiesHumanSignoff": doc["satisfiesHumanSignoff"],
                      "humanCounts": counts}, ensure_ascii=False, indent=1))
    if not is_human:
        print("NOTE: signerKind is not 'human', so this record is audit material only; "
              "the gate will stay PROVISIONAL_AI_REVIEW_ONLY until a human signs.")
    print("now re-run apply_review.py to recompute the gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
