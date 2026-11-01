# Fix-round follow-up: record the owner's explicit re-confirmation of the
# decoding config (2026-11-02, coordination channel) into the freeze
# record. Honest provenance: the owner statement is dated and attributable
# but there is still no in-repository primary session message — the record
# says exactly that. No gate is weakened: real inference stays refused by
# runner.status=PENDING-REVIEW and the unpinned modelId regardless.

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
RECORD = HERE.parent.parent.parent / "artifacts" / "world-components" / "d2-n3-prompt-freeze.json"


def main() -> int:
    d = json.loads(RECORD.read_text(encoding="utf-8"))
    dc = d.get("decodingConfig") or {}
    if dc.get("approval") != "PENDING-TRACEABLE-OWNER-CONFIRMATION":
        print("REFUSED: expected the downgraded state, got",
              dc.get("approval"))
        return 2
    runner = d.get("runner") or {}
    if runner.get("status") != "PENDING-REVIEW":
        print("REFUSED: runner status changed unexpectedly",
              runner.get("status"))
        return 2

    dc["approval"] = "APPROVED"
    dc["approvalProvenance"] = {
        "ownerConfirmation": {
            "date": "2026-11-02",
            "channel": "coordination channel (owner answered the "
                       "implementer's direct question on the record of "
                       "this approval)",
            "statement": "owner confirmed the greedy / maxNewTokens=512 "
                         "decode configuration approval is valid and "
                         "chose to record it now",
            "primarySessionRecord": "none in the repository - the original "
                                    "2026-11-01 exchange lives outside "
                                    "reviewer-visible history; this entry "
                                    "is the owner's dated re-confirmation, "
                                    "not a link to it",
            "reviewerAction": "verify this round; the classification of "
                              "this evidence level is the reviewer's call",
        },
        "priorAssertion": {
            "date": "2026-11-01",
            "note": "the implementer-asserted approval the review flagged "
                    "(c-review-1c41587 审批和运行记录核查); superseded by "
                    "the dated owner confirmation above",
        },
    }
    dc["approvalNote"] = (
        "OWNER-CONFIRMED 2026-11-02 (see approvalProvenance). Real "
        "inference remains refused by the other gates: runner.status is "
        "PENDING-REVIEW and decodingConfig.modelId is unpinned (0.6B "
        "pause in force).")
    d["status"] = ("PROMPT-FROZEN / DECODE-APPROVED-PROVENANCE-RECORDED / "
                   "RUNNER-BYTES-PENDING-REVIEW / MODELID-UNPINNED-PAUSE")

    RECORD.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
    print("recorded: approval=APPROVED with dated owner provenance")
    print("gates still closed:", runner["status"],
          "| modelId:", dc.get("modelId"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
