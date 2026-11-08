"""Run the real page projection over the six committed cases and record it.

`capability()` in build_candidates_fresh.py *predicts* whether the page
projection accepts each delta. This tool calls the real TypeScript function
(frontend/src/lib/world-engine/runtime/committed-narration.ts) on the committed
before/after records, writes candidates-fresh/projection-check.json, and fails
if the prediction and the measurement disagree.

No model is involved. The frontend dependencies are not needed: Node strips the
types itself (`--experimental-strip-types`), and the module's only import is
type-only.

Usage: python tools/run_projection_check.py [--node PATH]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
SRC = OUT / "fresh/source"
DEST = OUT / "candidates-fresh"
SCRIPT = HERE / "projection_check.ts"
RESULT = DEST / "projection-check.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    proc = subprocess.run(
        [args.node, "--experimental-strip-types", str(SCRIPT), str(SRC), str(RESULT)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr[-2000:])
        print("投影实测未运行：Node 不可用或类型剥离失败。不得把未运行当作通过。")
        return proc.returncode or 1

    measured = json.loads(RESULT.read_text(encoding="utf-8"))
    pack = json.loads((DEST / "candidates.json").read_text(encoding="utf-8"))
    verdicts = {c["id"]: c for c in measured["cases"]}
    mismatches = []
    for row in pack["candidates"]:
        got = verdicts[row["id"]]
        predicted = row["capability"]["stages"]["pageProjectionAcceptsDelta"]
        if predicted != got["accepted"]:
            mismatches.append((row["id"], predicted, got["accepted"],
                               got.get("reason")))
    # The perspective item must be rejected by our expectation even though the
    # projection accepts the delta: check that it really narrates the withheld
    # actor, otherwise the P5 flag would be folklore.
    leaks = {cid: c["projectionNarratesWithheld"] for cid, c in verdicts.items()}
    result = {"moduleSha256": measured["moduleSha256"], "node": measured["node"],
              "modelCalls": 0,
              "predictedAccepted": sum(1 for r in pack["candidates"]
                                       if r["capability"]["stages"]["pageProjectionAcceptsDelta"]),
              "measuredAccepted": sum(1 for c in measured["cases"] if c["accepted"]),
              "mismatches": mismatches, "narratesWithheld": leaks}
    print(json.dumps(result, ensure_ascii=False))
    if mismatches:
        print("预测与实测不一致：先修 capability()，不要改实测。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
