# Pin the reviewed N3 runner bytes and the owner-approved decoding config
# into the formal freeze record (batch 2, per signoff-f9c1190: "另做 runner
# 钉定提交，将已审查字节的 SHA-256 写入正式冻结记录，并更新 runner 状态" —
# the same signoff notes the pin "does not replace the owner's decode
# approval", which was obtained separately on 2026-11-01).
#
# modelId stays UNPINNED on purpose: the runner's gate contract refuses
# real inference without decodingConfig.modelId, which is exactly how the
# coordinator's standing 0.6B-inference pause is encoded in this record.
# When the pause is lifted, pinning modelId is a one-field update and the
# model arm runs; nothing else in this record changes.
#
# The script asserts every prior value before writing, so re-running on an
# already-pinned or drifted record fails loudly instead of double-pinning.

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
RECORD = HERE.parent.parent.parent / "artifacts" / "world-components" / "d2-n3-prompt-freeze.json"
RUNNER = HERE / "run_n3_arm.py"
SIGNOFF = HERE.parent.parent.parent / "artifacts" / "world-components" / "signoff-f9c1190.md"

SIGNED_RUNNER_SHA = "7189e233d93c870e459696ca609e04e9f26d8730a52400231e12123ee8bac0a2"


def sha_file(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main() -> int:
    record_bytes = RECORD.read_bytes()
    d = json.loads(record_bytes)
    problems = []
    if d.get("status") != "PROMPT-FROZEN / DECODING-CONFIG-PENDING-OWNER-APPROVAL":
        problems.append(f"unexpected record status {d.get('status')!r}")
    dc = d.get("decodingConfig") or {}
    if dc.get("approval") != "PENDING-OWNER-APPROVAL":
        problems.append(f"unexpected approval {dc.get('approval')!r}")
    runner = d.get("runner") or {}
    if runner.get("status") != "NOT-IMPLEMENTED" or runner.get("sha256") is not None:
        problems.append(f"unexpected runner block {runner.get('status')!r}/{runner.get('sha256')!r}")
    if dc.get("maxNewTokens") != 512:
        problems.append(f"unexpected maxNewTokens {dc.get('maxNewTokens')!r} "
                        f"(owner approved 512 on 2026-11-01)")
    if sha_file(RUNNER) != SIGNED_RUNNER_SHA:
        problems.append("runner bytes drifted from the reviewed sha256")
    if not SIGNOFF.exists():
        problems.append("signoff-f9c1190.md missing — it must be committed "
                        "in the same pinning commit")
    if problems:
        for p in problems:
            print("PIN REFUSED:", p)
        return 2

    dc["approval"] = "APPROVED"
    dc["approvalNote"] = ("owner approved greedy / maxNewTokens=512 on "
                          "2026-11-01 (an initial 256 proposal was withdrawn "
                          "after the 321-386-token gold measurement was "
                          "surfaced; no other field changed)")
    dc["modelId"] = None
    dc["modelIdNote"] = ("UNPINNED: the only gate-eligible generative "
                         "candidate is the 0.6B causal LM, whose inference "
                         "is paused by coordinator directive. The runner "
                         "refuses real inference on the missing modelId, "
                         "which encodes the pause. Pin modelId when the "
                         "pause is lifted; no other field changes.")
    runner["status"] = "EXECUTABLE"
    runner["sha256"] = SIGNED_RUNNER_SHA
    runner["pinnedAt"] = "2026-11-01"
    runner["signoff"] = "signoff-f9c1190.md (runner implementation review passed)"
    d["status"] = ("PROMPT-FROZEN / DECODING-CONFIG-APPROVED / RUNNER-PINNED / "
                   "MODELID-PENDING-PAUSE-LIFT")

    out = json.dumps(d, ensure_ascii=False, indent=1) + "\n"
    RECORD.write_text(out, encoding="utf-8", newline="\n")
    print("pinned:", RECORD.name)
    print("runner:", runner["status"], runner["sha256"][:16])
    print("approval:", dc["approval"], "| maxNewTokens:", dc["maxNewTokens"])
    print("modelId:", dc["modelId"], "(pause encoded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
