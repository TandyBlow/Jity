# Fix round 11-02 re-review finding 2: unify the decoding-config approval
# state. Per the coordinator's ruling relayed with the re-review: neither
# the implementer-relayed assertion nor the 2026-11-02 in-channel owner
# confirmation is accepted as an approval basis — only a traceable owner
# original can serve, the state is unified to PENDING, and even a future
# approval does not lift the 0.6B inference pause. Prior values asserted.

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
RECORD = HERE.parent.parent.parent / "artifacts" / "world-components" / "d2-n3-prompt-freeze.json"


def main() -> int:
    d = json.loads(RECORD.read_text(encoding="utf-8"))
    dc = d.get("decodingConfig") or {}
    if dc.get("approval") != "APPROVED":
        print("REFUSED: expected the APPROVED state to unify, got",
              dc.get("approval"))
        return 2
    if not (dc.get("approvalProvenance") or {}).get("ownerConfirmation"):
        print("REFUSED: expected the recorded 2026-11-02 confirmation event")
        return 2

    dc["approval"] = "PENDING-TRACEABLE-OWNER-CONFIRMATION"
    dc["approvalProvenance"]["unifiedPending"] = {
        "date": "2026-11-02",
        "ruling": "coordinator directive relayed with the 11-02 re-review: "
                  "unify to pending — neither the implementer-relayed "
                  "assertion (2026-11-01) nor the in-channel owner "
                  "confirmation (2026-11-02) is accepted as an approval "
                  "basis; only a traceable owner original can serve; even "
                  "a future approval does NOT lift the 0.6B inference "
                  "pause",
        "eventKeptForProvenance": "the 2026-11-02 confirmation event is "
                                  "retained above as a recorded fact, not "
                                  "as an approval basis",
    }
    dc["approvalNote"] = (
        "PENDING (unified 2026-11-02 per coordinator ruling): no "
        "traceable owner original exists; see approvalProvenance. Real "
        "inference remains refused by this gate, the unpinned modelId "
        "(0.6B pause, independent of approval) and runner.status.")
    d["status"] = ("PROMPT-FROZEN / DECODE-APPROVAL-PENDING-UNIFIED / "
                   "RUNNER-BYTES-PENDING-REVIEW / MODELID-UNPINNED-PAUSE")

    RECORD.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
    print("unified: approval =", dc["approval"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
