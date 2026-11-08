# -*- coding: utf-8 -*-
"""Build the human sign-off form for the r2 review round.

The form is generated from what is already on disk, so the signer does not have
to retype hashes. Every row keeps the AI verdict as a separate field: the human
verdict is added next to it, never over it.

    runs/r2/signoff-form.json   -> the file the project owner fills in
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

HERE = Path(__file__).resolve().parent
def newest_criteria() -> Path:
    found = sorted((HERE / "freeze").glob("criteria-v[0-9]*.json"))
    return found[-1] if found else HERE / "freeze" / "criteria-v2.json"


RUN = HERE / "runs" / "r4"
FORM = RUN / "signoff-form.json"

CRITERIA = newest_criteria()
PROBES = HERE / "freeze" / "tamper-probes.json"
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
        "pinnedInputs": {
            "criteria": {"file": "freeze/criteria-v2.json", "sha256": sha256(CRITERIA),
                         "checkerVersion": criteria["checker"]["contractVersion"]},
            "checker": {"file": "text_conformance.py", "sha256": criteria["checker"]["sha256"]},
            "tamperProbes": {"file": "freeze/tamper-probes.json", "sha256": sha256(PROBES)},
            "manualReview": {"file": "runs/r2/manual-review.json", "sha256": sha256(REVIEW)},
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
