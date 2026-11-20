# Fix-round 1c41587 #4: build the r2 rule-arm registration that binds the
# CURRENT consumed bytes (the v1 registration pins pre-fix-round bytes and
# stays untouched at its original path), then the amendment evidence is
# assembled by the caller. Everything is derived from the files on disk so
# the registration cannot drift from what actually runs.

import copy
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
V1 = REPO / "artifacts" / "world-components" / "n3-rulearm-registration.json"
R2 = REPO / "artifacts" / "world-components" / "n3-rulearm-registration-r2.json"


def sha(p) -> str:
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def main() -> int:
    v1 = json.loads(V1.read_text(encoding="utf-8"))
    d = copy.deepcopy(v1)

    # rebind the two entries whose bytes the fix round legitimately changed
    d["dependencies"]["run_n3_arm"]["sha256"] = sha(HERE / "run_n3_arm.py")
    freeze_rel = "artifacts/world-components/d2-n3-prompt-freeze.json"
    d["freezeRecord"] = {"file": freeze_rel, "sha256": sha(REPO / freeze_rel)}

    # everything else must STILL match the v1 pins — a drifted unexpected
    # dependency is a stop, not a silent rebind
    rechecked = {}
    for label, rel, want in (
        ("ruleArm", v1["ruleArm"]["file"], v1["ruleArm"]["sha256"]),
        ("d2_metrics", v1["dependencies"]["d2_metrics"]["file"],
         v1["dependencies"]["d2_metrics"]["sha256"]),
        ("n3_plan", v1["dependencies"]["n3_plan"]["file"],
         v1["dependencies"]["n3_plan"]["sha256"]),
        ("gate8Items", v1["inputs"]["gate8Items"]["file"],
         v1["inputs"]["gate8Items"]["sha256"]),
        ("gold", v1["gold"]["file"], v1["gold"]["sha256"]),
    ):
        got = sha(REPO / rel)
        rechecked[label] = {"file": rel, "sha256": got, "matchesV1": got == want}
        if got != want:
            print(f"UNEXPECTED DRIFT in {label} ({rel}): refusing to rebind "
                  "silently - review required")
            return 2

    d["purpose"] = (
        "Fix-round 1c41587 r2 registration for the N3 rule arm: binds the "
        "CURRENT consumed bytes after the review-mandated changes (runner "
        "pause gate moved into precheck_real; freeze record approval "
        "downgrade + runner re-bind). The v1 registration stays untouched "
        "at n3-rulearm-registration.json and remains the record of the "
        "pre-fix-round world; it refuses against current bytes by design.")
    d["status"] = "REGISTERED-PRE-RUN"
    d["registeredAt"] = "2026-11-02"
    d["lineage"] = {
        "supersedes": "n3-rulearm-registration.json (v1, sha256 "
                      f"{sha(V1)}) — kept byte-identical at its path",
        "v1FreezeRecordPin": v1["freezeRecord"]["sha256"],
        "v1FreezeRecordReproducible": (
            "git show 2ef930e:artifacts/world-components/"
            "d2-n3-prompt-freeze.json | sha256sum  -> the v1 pin "
            "(the freeze record was amended only by the review-prescribed "
            "pinning commit b5e041e and this fix round)"),
        "changedSinceV1": [
            "run_n3_arm.py: 0.6B pause gate moved into precheck_real "
            "(review #6; before any model or library loading)",
            "d2-n3-prompt-freeze.json: approval downgraded to "
            "PENDING-TRACEABLE-OWNER-CONFIRMATION (review #5), runner "
            "re-bound to the new bytes with status PENDING-REVIEW",
        ],
        "unchangedSinceV1": rechecked,
    }

    R2.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n",
                  encoding="utf-8")
    print("wrote", R2.name)
    print("run_n3_arm:", d["dependencies"]["run_n3_arm"]["sha256"][:16])
    print("freezeRecord:", d["freezeRecord"]["sha256"][:16])
    return 0


if __name__ == "__main__":
    sys.exit(main())
