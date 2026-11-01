# Fix-round 1c41587 amendment to the formal freeze record (batch-5fix).
# Three reviewer-mandated corrections, applied with prior-value assertions
# so re-running on an amended record fails loudly:
#
#   1. approval downgrade — the recorded "owner approved greedy/512" is an
#      implementer assertion without a reviewer-verifiable primary record
#      (review §审批核查). APPROVED -> PENDING-TRACEABLE-OWNER-CONFIRMATION;
#      the real-inference gate stays closed until the owner confirms in a
#      traceable form.
#   2. runner re-bind — the pause gate moved into precheck_real (review:
#      effective BEFORE model loading), which changes the runner bytes; the
#      previously signed sha (7189e233, signoff-f9c1190) no longer matches.
#      status EXECUTABLE -> PENDING-REVIEW with the new sha; re-pinning to
#      EXECUTABLE is the reviewer's re-verification act.
#   3. status line reflects both.
#
# The prior pinned values are preserved IN this record (previouslyPinned*)
# for lineage; v1 registration and all archived evidence stay untouched
# (see n3-freeze-amendment-r1.json for the registration rebinding).

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
RECORD = HERE.parent.parent.parent / "artifacts" / "world-components" / "d2-n3-prompt-freeze.json"
RUNNER = HERE / "run_n3_arm.py"

SIGNED_RUNNER_SHA = "7189e233d93c870e459696ca609e04e9f26d8730a52400231e12123ee8bac0a2"


def sha_file(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main() -> int:
    d = json.loads(RECORD.read_text(encoding="utf-8"))
    problems = []
    dc = d.get("decodingConfig") or {}
    runner = d.get("runner") or {}
    if dc.get("approval") != "APPROVED":
        problems.append(f"unexpected approval {dc.get('approval')!r}")
    if runner.get("status") != "EXECUTABLE" or \
            runner.get("sha256") != SIGNED_RUNNER_SHA:
        problems.append(f"unexpected runner block {runner.get('status')!r}/"
                        f"{str(runner.get('sha256'))[:16]}")
    if dc.get("modelId") is not None:
        problems.append("modelId unexpectedly pinned")
    if problems:
        for p in problems:
            print("AMENDMENT REFUSED:", p)
        return 2

    dc["approval"] = "PENDING-TRACEABLE-OWNER-CONFIRMATION"
    dc["approvalNote"] = (
        "FIX ROUND 1c41587 DOWNGRADE (2026-11-02): the previous APPROVED "
        "state recorded an implementer-asserted owner approval (greedy / "
        "maxNewTokens 512, coordinating channel, 2026-11-01) for which no "
        "reviewer-verifiable primary record exists (review section 审批和"
        "运行记录核查). The gate stays CLOSED until the owner confirms in "
        "a traceable form. No N3 model arm ran in this batch; no run "
        "archive exists for one.")
    dc["approvalProvenance"] = {
        "assertedBy": "implementer session, via the coordinating channel",
        "assertedAt": "2026-11-01",
        "verifiablePrimaryRecord": False,
        "reviewFinding": "c-review-1c41587 审批和运行记录核查",
    }
    runner["previouslyPinned"] = {
        "sha256": SIGNED_RUNNER_SHA,
        "signoff": "signoff-f9c1190.md (implementation review passed)",
        "note": "bytes superseded by the fix-round precheck change; the "
                "reviewed diff is reproducible from the repository history",
    }
    runner["status"] = "PENDING-REVIEW"
    runner["sha256"] = sha_file(RUNNER)
    runner["changeReason"] = ("fix round 1c41587 #4/#6: the 0.6B pause gate "
                              "moved into precheck_real (before any model "
                              "or library loading); awaiting reviewer "
                              "re-verification before EXECUTABLE")
    d["status"] = ("PROMPT-FROZEN / DECODE-APPROVAL-PENDING-TRACEABLE-"
                   "CONFIRMATION / RUNNER-BYTES-PENDING-REVIEW / "
                   "MODELID-UNPINNED-PAUSE")

    RECORD.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
    print("amended:", RECORD.name)
    print("approval:", dc["approval"])
    print("runner:", runner["status"], runner["sha256"][:16],
          "(was", SIGNED_RUNNER_SHA[:16] + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
