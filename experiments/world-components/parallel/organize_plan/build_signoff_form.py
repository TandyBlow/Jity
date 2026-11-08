# -*- coding: utf-8 -*-
"""Build the human sign-off form for the current round (runs/r4).

The form is generated from what is already on disk, so the signer does not have
to retype hashes. Every row keeps the AI verdict as a separate field: the human
verdict is added next to it, never over it.

    runs/r4/signoff-form.json   -> the file the project owner fills in
    fields: signer, date, commit, rows[].humanVerdict / humanNote
    allowed humanVerdict: paraphrase-ok / new-content-fail / unsure
                         ("unsure" is allowed and does NOT count as passing)

Usage:
    python -X utf8 build_signoff_form.py          # refuses to overwrite once signed
    python -X utf8 build_signoff_form.py --force  # regenerate the blank form
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pins as pins_mod

HERE = Path(__file__).resolve().parent
def newest_criteria() -> Path:
    found = sorted((HERE / "freeze").glob("criteria-v[0-9]*.json"))
    return found[-1] if found else HERE / "freeze" / "criteria-v2.json"


RUN = HERE / "runs" / "r4"
FORM = RUN / "signoff-form.json"

CRITERIA = newest_criteria()
# The round's own probe results, not the frozen probe set: the acceptance
# identity is computed from these three files, so the form must pin exactly
# the same three or its pins can never match the record it signs.
PROBES = RUN / "tamper-probes.json"
REVIEW = RUN / "manual-review.json"
ACCEPTANCE = RUN / "acceptance.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if FORM.exists() and not args.force:
        existing = json.loads(FORM.read_text(encoding="utf-8"))
        if existing.get("signer") or any(r.get("humanVerdict") for r in existing.get("rows", [])):
            print(f"{FORM} already has sign-off content; refusing to overwrite. Use --force to reset.")
            return 1

    criteria = json.loads(CRITERIA.read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    acceptance = json.loads(ACCEPTANCE.read_text(encoding="utf-8"))

    rows = []
    for r in review["rows"]:
        rows.append({
            "queueId": r["queueId"],
            "code": r["code"],
            "run": r.get("run"),
            "text": r["text"],
            "aiVerdict": r.get("verdict"),
            "aiNote": r.get("reviewerNote", ""),
            "humanVerdict": None,
            "humanNote": "",
        })

    identity_now = pins_mod.acceptance_identity(CRITERIA, PROBES, REVIEW)
    if identity_now != acceptance.get("identitySha256"):
        print(json.dumps({
            "status": "refused",
            "reason": ("acceptance.json was built from different inputs than the ones on disk; "
                       "re-run apply_review.py before generating the form"),
            "acceptanceIdentity": acceptance.get("identitySha256"),
            "recomputed": identity_now,
        }, ensure_ascii=False, indent=1))
        return 1

    form = {
        "formVersion": "c3-signoff-v1",
        "purpose": ("项目负责人逐条核对原文、证据与 AI 理由后签认；签认前 gate 状态保持 "
                    "PROVISIONAL_AI_REVIEW_ONLY"),
        "signer": "",
        "signerRole": "",
        "signerKind": "",
        "iReviewedEachRow": False,
        "delegationNote": "",
        "date": "",
        "reviewedCommit": "",
        # Every pin names the file its hash was taken from. Hardcoding the v2
        # paths here is what made the r4 form unverifiable.
        "pinnedInputs": {
            "criteria": pins_mod.pin(CRITERIA, checkerVersion=criteria["checker"]["contractVersion"]),
            "checker": {"file": "text_conformance.py", "sha256": criteria["checker"]["sha256"]},
            "tamperProbes": pins_mod.pin(PROBES),
            "manualReview": pins_mod.pin(REVIEW),
            "acceptanceIdentity": acceptance["identitySha256"],
        },
        "instructions": [
            "逐行填写 humanVerdict：paraphrase-ok / new-content-fail / unsure",
            "unsure 合法，但该条不算通过（判据 manualReview.verdictValues）",
            "aiVerdict 与 aiNote 是原表内容，不得改写；不同意见写在 humanNote",
            "填完运行 python -X utf8 apply_signoff.py",
        ],
        "rows": rows,
    }
    FORM.write_text(json.dumps(form, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FORM} ({len(rows)} rows)")
    print(f"  pinned criteria {form['pinnedInputs']['criteria']['sha256'][:12]}")
    print(f"  pinned probes   {form['pinnedInputs']['tamperProbes']['sha256'][:12]}")
    print(f"  acceptance id   {form['pinnedInputs']['acceptanceIdentity'][:12]}")
    return 0


def review_sha(review_doc: dict) -> str:
    raw = json.dumps(review_doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
