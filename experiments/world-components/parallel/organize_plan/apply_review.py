# -*- coding: utf-8 -*-
"""Apply the manual-review verdicts to the frozen probe results.

Program output alone is not acceptance: a probe with no hard finding but with a
review item is only decided after a human verdict. This script joins

    freeze/criteria-v<N>.json         what the verdict values and gate are
    runs/r<N>/tamper-probes.json      the program's hard findings per probe
    runs/r<N>/manual-review.json      the filled-in verdicts per review row

and writes runs/r<N>/acceptance.json: one outcome per probe, the counts, every
deviation from the frozen criteria, and the gate status.

Outcome per probe (first match wins):
    rejected-hard    the program found a hard violation
    rejected-review  no hard finding, but a review row was judged new-content-fail
    pending-review   no hard finding, and some review row is unsure or unfilled
    accepted         no hard finding and every review row is paraphrase-ok

Gate status:
    BLOCKED_PENDING_HUMAN_SIGNOFF   verdicts exist but humanSignoff != "signed"
    PROVISIONAL_AI_REVIEW_ONLY      same thing, said plainly, when reviewer.kind == "ai"
    OPEN                            the gate can be used for a model round

Usage:
    python -X utf8 apply_review.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gate_rules  # noqa: E402
import pins as pins_mod  # noqa: E402

def newest_criteria() -> Path:
    found = sorted((HERE / "freeze").glob("criteria-v[0-9]*.json"))
    return found[-1] if found else HERE / "freeze" / "criteria-v2.json"


RUN = HERE / "runs" / "r4"
CRITERIA = newest_criteria()
PROBES = RUN / "tamper-probes.json"
REVIEW = RUN / "manual-review.json"
SIGNOFF = RUN / "signoff.json"
OUT = RUN / "acceptance.json"

# The frozen criteria allow three verdict values. Archived-output rows that
# already fail hard were labelled "fail"; that value is accepted ONLY for rows
# whose code is archived-output-hard-fail, and the use is recorded as a
# deviation instead of being folded into the frozen definition.
ALIAS = {"fail": ("new-content-fail", "archived-output-hard-fail")}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalise(verdict: str, code: str, allowed: list[str]) -> tuple[str | None, str | None]:
    """-> (normalisedVerdict, deviationNoteOrNone)."""
    if verdict in allowed:
        return verdict, None
    if verdict in ALIAS:
        target, only_for_code = ALIAS[verdict]
        if code == only_for_code:
            return target, f"verdict {verdict!r} used for {code!r}; treated as {target!r}"
        return None, f"verdict {verdict!r} is not allowed for code {code!r}"
    return None, f"verdict {verdict!r} is not one of {allowed}"


def main() -> int:
    criteria = json.loads(CRITERIA.read_text(encoding="utf-8"))
    allowed = criteria["manualReview"]["verdictValues"]
    probes = json.loads(PROBES.read_text(encoding="utf-8"))["rows"]
    review_doc = json.loads(REVIEW.read_text(encoding="utf-8"))
    rows = review_doc["rows"]
    reviewer = review_doc.get("reviewer") or {}

    # A signed record, when present, is authoritative for the rows it covers.
    # The AI verdict is kept beside it, never replaced.
    signoff = None
    human_by_id: dict[str, str] = {}
    if SIGNOFF.exists():
        signoff = json.loads(SIGNOFF.read_text(encoding="utf-8"))
        human_by_id = {r["queueId"]: r["humanVerdict"] for r in signoff.get("rows", [])
                       if r.get("humanVerdict")}

    deviations: list[str] = []
    notes: list[str] = []
    by_probe: dict[str, list[dict]] = {}
    normalised_rows = []
    for row in rows:
        ai_verdict, note = normalise(row.get("verdict"), row.get("code", ""), allowed)
        human_verdict = human_by_id.get(row["queueId"])
        if note:
            # An off-contract AI value matters only while it would decide the
            # row. Once a human verdict exists, the alias is history: record it
            # as a note, not as a blocking deviation.
            (deviations if human_verdict is None else notes).append(f"{row['queueId']}: {note}")
        if ai_verdict is None:
            deviations.append(f"{row['queueId']}: unreadable verdict, treated as pending")
        human = human_verdict
        if human is not None and human not in allowed:
            deviations.append(f"{row['queueId']}: signed verdict {human!r} is off-contract")
            human = None
        effective = human if human is not None else ai_verdict
        if row.get("probeId"):
            by_probe.setdefault(row["probeId"], []).append(
                {**row, "ai": ai_verdict, "human": human, "normalised": effective})
        normalised_rows.append({**row, "ai": ai_verdict, "human": human, "normalised": effective})

    outcomes = []
    for p in probes:
        pid = p["probeId"]
        rrows = by_probe.get(pid, [])
        verdicts = [r["normalised"] for r in rrows]
        if p["actualHardCodes"]:
            outcome = "rejected-hard"
            reason = "program hard finding(s): " + ", ".join(p["actualHardCodes"])
        elif any(v == "new-content-fail" for v in verdicts):
            outcome = "rejected-review"
            reason = "review judged new content"
        elif not rrows:
            outcome = "pending-review"
            reason = "no hard finding and no review row exists (should not happen)"
            deviations.append(f"{pid}: no review row for a probe without hard findings")
        elif any(v != "paraphrase-ok" for v in verdicts):
            outcome = "pending-review"
            reason = "review left unsure or unfilled"
        else:
            outcome = "accepted"
            reason = "no hard finding and every review row is paraphrase-ok"
        outcomes.append({
            "probeId": pid,
            "expectedVerdict": p["expectedVerdict"],
            "hardCodes": p["actualHardCodes"],
            "reviewRuns": p["actualReviewRuns"],
            "reviewVerdicts": verdicts,
            "outcome": outcome,
            "reason": reason,
        })

    counts = {
        "probes": len(outcomes),
        "rejectedHard": sum(1 for o in outcomes if o["outcome"] == "rejected-hard"),
        "rejectedReview": sum(1 for o in outcomes if o["outcome"] == "rejected-review"),
        "pendingReview": sum(1 for o in outcomes if o["outcome"] == "pending-review"),
        "accepted": sum(1 for o in outcomes if o["outcome"] == "accepted"),
    }
    program_only = {
        "acceptedWithoutReview": sum(1 for p in probes if not p["actualHardCodes"]),
        "detail": "probes the v2 program alone would let through (no hard finding)",
    }

    # The gate rule lives in gate_rules.py so the "an AI sign-off cannot open a
    # human sign-off gate" case can be regression-tested on its own.
    decision = gate_rules.decide_gate(
        signoff=signoff,
        reviewer_kind=reviewer.get("kind"),
        all_rows_decided=all(r["normalised"] is not None for r in normalised_rows),
        deviations=deviations,
    )
    gate = decision["gate"]

    identity = pins_mod.acceptance_identity(CRITERIA, PROBES, REVIEW)
    doc = {
        # no wall-clock timestamp: the file is meant to be byte-stable across
        # re-runs so two reviewers can diff it. Identity is derived from inputs.
        "identitySha256": identity,
        "criteria": pins_mod.pin(CRITERIA, contractVersion=criteria["checker"]["contractVersion"]),
        "inputs": {
            "probes": pins_mod.pin(PROBES),
            "manualReview": pins_mod.pin(REVIEW),
        },
        "reviewer": reviewer,
        "signoff": None if not signoff else {
            "file": pins_mod.rel(SIGNOFF), "sha256": sha256(SIGNOFF),
            "signer": signoff.get("signer"),
            "signerKind": signoff.get("signerKind"),
            "iReviewedEachRow": signoff.get("iReviewedEachRow") is True,
            "date": signoff.get("date"),
            "reviewedCommit": signoff.get("reviewedCommit"),
            "humanCounts": signoff.get("humanCounts"),
            "satisfiesHumanSignoff": decision["satisfiesHumanSignoff"],
            "auditOnly": not decision["satisfiesHumanSignoff"],
        },
        "gateReason": decision["reason"],
        "openItems": [o["probeId"] for o in outcomes if o["outcome"] == "pending-review"],
        "counts": counts,
        "programOnly": program_only,
        "gateStatus": gate,
        "gateMeaning": {
            "PROVISIONAL_AI_REVIEW_ONLY":
                "verdicts are AI review; human sign-off is still pending, so this cannot be used as "
                "the acceptance gate for a model round yet",
            "OPEN": "a HUMAN sign-off sealed the review; openItems (e.g. an 'unsure' probe) remain "
                    "not-passing. Note: an open gate still does not start a model round — "
                    "check_round_ready.py decides that",
            "BLOCKED_PENDING_HUMAN_SIGNOFF": "reviewer did not sign",
            "BLOCKED_REVIEW_INCOMPLETE": "some review row is unsure/unfilled or a verdict is off-contract",
            "OPEN": "review sealed; the gate may be used",
        }[gate],
        "deviations": deviations,
        "notes": notes,
        "outcomes": outcomes,
        "rows": [{"queueId": r["queueId"], "code": r["code"], "verdict": r.get("verdict"),
                  "normalised": r["normalised"], "note": r.get("reviewerNote", "")}
                 for r in normalised_rows],
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"wrote {OUT}")
    print(f"  gate: {gate}")
    print(f"  probes: {counts}")
    print(f"  program alone would accept {program_only['acceptedWithoutReview']}")
    for o in outcomes:
        print(f"  {o['probeId']:32s} {o['outcome']:16s} {o['reason'][:60]}")
    if deviations:
        print("  deviations:")
        for d in deviations:
            print("   -", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
