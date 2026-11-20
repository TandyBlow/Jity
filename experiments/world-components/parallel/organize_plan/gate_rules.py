# -*- coding: utf-8 -*-
"""Gate decision rules, kept in one pure function so they can be tested.

The gate has exactly four values. The important rule is the second one: a
sign-off whose `signerKind` is not `human` never opens a gate that requires a
human sign-off. An AI sign-off is kept as audit material, not as authorisation.

    PROVISIONAL_AI_REVIEW_ONLY   only the AI review exists (or the sign-off was
                                 filled by something other than a human)
    BLOCKED_PENDING_HUMAN_SIGNOFF no sign-off record at all
    BLOCKED_REVIEW_INCOMPLETE    a human signed, but verdicts are missing or
                                 an off-contract value would decide a row
    OPEN                         a human signed and every row is decided

Usage:
    python -X utf8 test_gate_rules.py    # runs the regression cases below
"""

from __future__ import annotations

OPEN = "OPEN"
PROVISIONAL_AI_REVIEW_ONLY = "PROVISIONAL_AI_REVIEW_ONLY"
BLOCKED_PENDING_HUMAN_SIGNOFF = "BLOCKED_PENDING_HUMAN_SIGNOFF"
BLOCKED_REVIEW_INCOMPLETE = "BLOCKED_REVIEW_INCOMPLETE"

REQUIRED_SIGNER_KIND = "human"

# Strings that identify an agent rather than a person. A signer whose identity
# carries one of these cannot be treated as a human sign-off, even if the
# record claims signerKind="human": editing one field is not a sign-off.
AGENT_IDENTITY_MARKERS = ("AI", "ai代理", "代理", "Codex", "Claude", "GPT",
                          "assistant", "harness", "bot", "机器人")

# The human has to state explicitly that they went through the rows. The flag
# exists so that "signerKind=human" alone is not enough.
ATTESTATION_FIELD = "iReviewedEachRow"


def decide_gate(
    *,
    signoff: dict | None,
    reviewer_kind: str | None,
    all_rows_decided: bool,
    deviations: list[str],
) -> dict:
    """-> {"gate", "satisfiesHumanSignoff", "reason"}."""
    signed = bool(signoff) and signoff.get("signed") is True
    if not signed:
        gate = PROVISIONAL_AI_REVIEW_ONLY if reviewer_kind == "ai" else BLOCKED_PENDING_HUMAN_SIGNOFF
        return {
            "gate": gate,
            "satisfiesHumanSignoff": False,
            "reason": "no sign-off record; the gate stays closed",
        }

    kind = signoff.get("signerKind")
    if kind != REQUIRED_SIGNER_KIND:
        return {
            "gate": PROVISIONAL_AI_REVIEW_ONLY,
            "satisfiesHumanSignoff": False,
            "reason": (f"signerKind={kind!r}: this record is audit material only and cannot satisfy a "
                       f"human sign-off requirement; a human signer is still required"),
        }

    # A human sign-off needs a person's identity, a date, the reviewed version,
    # and an explicit statement that every row was read. Changing signerKind to
    # "human" is not any of those.
    missing = [f for f in ("signer", "date", "reviewedCommit") if not str(signoff.get(f) or "").strip()]
    if missing:
        return {
            "gate": BLOCKED_REVIEW_INCOMPLETE,
            "satisfiesHumanSignoff": False,
            "reason": f"human sign-off lacks {missing}",
        }
    signer = str(signoff.get("signer") or "")
    hit = [m for m in AGENT_IDENTITY_MARKERS if m in signer]
    if hit:
        return {
            "gate": PROVISIONAL_AI_REVIEW_ONLY,
            "satisfiesHumanSignoff": False,
            "reason": (f"signer identity {signer!r} carries an agent marker {hit}: a sign-off by an "
                       f"agent cannot satisfy a human requirement, whatever the declared kind"),
        }
    if signoff.get(ATTESTATION_FIELD) is not True:
        return {
            "gate": BLOCKED_REVIEW_INCOMPLETE,
            "satisfiesHumanSignoff": False,
            "reason": (f"{ATTESTATION_FIELD} is not true: the signer must state that every row was "
                       f"confirmed or rewritten; declaring a human kind alone is not a sign-off"),
        }

    if deviations:
        return {
            "gate": BLOCKED_REVIEW_INCOMPLETE,
            "satisfiesHumanSignoff": True,
            "reason": f"{len(deviations)} blocking deviation(s)",
        }
    if not all_rows_decided:
        return {
            "gate": BLOCKED_REVIEW_INCOMPLETE,
            "satisfiesHumanSignoff": True,
            "reason": "some review row has no usable verdict",
        }
    return {
        "gate": OPEN,
        "satisfiesHumanSignoff": True,
        "reason": "human sign-off present and every review row decided",
    }


def _row(qid: str, human: str | None = None) -> dict:
    return {"queueId": qid, "humanVerdict": human}


def _signoff(kind: str, *, signer: str = "项目负责人", attest: bool = True) -> dict:
    return {"signed": True, "signerKind": kind, "signer": signer, "date": "2026-11-08",
            "reviewedCommit": "c", "iReviewedEachRow": attest, "rows": []}


def test_ai_signoff_cannot_open_the_gate() -> None:
    result = decide_gate(signoff=_signoff("ai"), reviewer_kind="ai",
                         all_rows_decided=True, deviations=[])
    assert result["gate"] == PROVISIONAL_AI_REVIEW_ONLY, result
    assert result["satisfiesHumanSignoff"] is False


def test_unknown_signer_kind_cannot_open_the_gate() -> None:
    for kind in ("unknown", "", None, "robot"):
        result = decide_gate(signoff=_signoff(kind), reviewer_kind="ai",
                             all_rows_decided=True, deviations=[])
        assert result["gate"] == PROVISIONAL_AI_REVIEW_ONLY, (kind, result)
        assert result["satisfiesHumanSignoff"] is False


def test_changing_signer_kind_alone_does_not_open_the_gate() -> None:
    """The handover rule: flipping one field is not a sign-off."""
    no_attestation = decide_gate(signoff=_signoff("human", attest=False), reviewer_kind="ai",
                                 all_rows_decided=True, deviations=[])
    assert no_attestation["gate"] == BLOCKED_REVIEW_INCOMPLETE, no_attestation
    assert no_attestation["satisfiesHumanSignoff"] is False

    agent_name = decide_gate(signoff=_signoff("human", signer="Codex (AI)"), reviewer_kind="ai",
                             all_rows_decided=True, deviations=[])
    assert agent_name["gate"] == PROVISIONAL_AI_REVIEW_ONLY, agent_name
    assert agent_name["satisfiesHumanSignoff"] is False

    blank_identity = decide_gate(signoff={**_signoff("human"), "signer": ""}, reviewer_kind="ai",
                                 all_rows_decided=True, deviations=[])
    assert blank_identity["gate"] == BLOCKED_REVIEW_INCOMPLETE, blank_identity


def test_human_signoff_opens_the_gate() -> None:
    result = decide_gate(signoff=_signoff("human"), reviewer_kind="ai",
                         all_rows_decided=True, deviations=[])
    assert result["gate"] == OPEN, result
    assert result["satisfiesHumanSignoff"] is True


def test_human_signoff_with_missing_verdict_stays_blocked() -> None:
    result = decide_gate(signoff=_signoff("human"), reviewer_kind="ai",
                         all_rows_decided=False, deviations=[])
    assert result["gate"] == BLOCKED_REVIEW_INCOMPLETE, result


def test_human_signoff_with_deviation_stays_blocked() -> None:
    result = decide_gate(signoff=_signoff("human"), reviewer_kind="ai",
                         all_rows_decided=True, deviations=["row X off-contract"])
    assert result["gate"] == BLOCKED_REVIEW_INCOMPLETE, result


def test_no_signoff_is_not_open() -> None:
    assert decide_gate(signoff=None, reviewer_kind="ai",
                       all_rows_decided=True, deviations=[])["gate"] == PROVISIONAL_AI_REVIEW_ONLY
    assert decide_gate(signoff=None, reviewer_kind=None,
                       all_rows_decided=True, deviations=[])["gate"] == BLOCKED_PENDING_HUMAN_SIGNOFF


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
