"""Run or verify the real page projection over the six committed cases.

`capability()` in build_candidates_fresh.py *predicts* whether the page
projection accepts each delta. This tool calls the real TypeScript function
(frontend/src/lib/world-engine/runtime/committed-narration.ts) on the committed
before/after records.

Two modes:
  (default)   run and write candidates-fresh/projection-check.json
  --verify    run into a temp file and compare with the saved result; nothing is
              written. Fails when the module hash, any case verdict, any leak
              fact or any control differs - this is what catches "someone
              changed the projection source but the saved result is stale".

No model is involved. The frontend dependencies are not needed: Node strips the
types itself (`--experimental-strip-types`), and the module's only import is
type-only.

Usage: python tools/run_projection_check.py [--verify] [--node PATH]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
SRC = OUT / "fresh/source"
DEST = OUT / "candidates-fresh"
SCRIPT = HERE / "projection_check.ts"
RESULT = DEST / "projection-check.json"
TS_MODULE = OUT.parents[2] / "frontend/src/lib/world-engine/runtime/committed-narration.ts"


def run(node: str, out: pathlib.Path) -> int:
    proc = subprocess.run(
        [node, "--experimental-strip-types", str(SCRIPT), str(SRC), str(out)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr[-2000:])
        print("投影实测未运行：Node 不可用或类型剥离失败。不得把未运行当作通过。")
        return proc.returncode or 1
    return 0


def summary(measured: dict) -> dict:
    verdicts = {c["id"]: c for c in measured["cases"]}
    pack = json.loads((DEST / "candidates.json").read_text(encoding="utf-8"))
    mismatches = [
        {"id": row["id"],
         "predicted": row["capability"]["stages"]["pageProjectionAcceptsDelta"],
         "measured": verdicts[row["id"]]["accepted"],
         "reason": verdicts[row["id"]].get("reason")}
        for row in pack["candidates"]
        if row["capability"]["stages"]["pageProjectionAcceptsDelta"]
        != verdicts[row["id"]]["accepted"]]
    return {"moduleSha256": measured["moduleSha256"], "node": measured["node"],
            "modelCalls": measured["modelCalls"],
            "predictedAccepted": sum(1 for r in pack["candidates"]
                                     if r["capability"]["stages"]["pageProjectionAcceptsDelta"]),
            "measuredAccepted": sum(1 for c in measured["cases"] if c["accepted"]),
            "mismatches": mismatches,
            "leaked": {c["id"]: c.get("leakedFactIds") for c in measured["cases"]},
            "controls": {c["name"]: {"expected": c["expected"], "observed": c["observed"],
                                     "ok": c["ok"]} for c in measured["controls"]}}


def compare(saved: dict, fresh: dict) -> list:
    """Machine-independent comparison: ignore the Node version string."""
    diffs = []
    for key in ("moduleSha256", "modelCalls"):
        if saved.get(key) != fresh.get(key):
            diffs.append(f"{key}: saved {saved.get(key)!r} != fresh {fresh.get(key)!r}")
    for key in ("cases", "controls", "summary"):
        if saved.get(key) != fresh.get(key):
            diffs.append(f"{key} differs")
            if key == "cases":
                old = {c["id"]: c for c in saved.get("cases", [])}
                for case in fresh.get("cases", []):
                    if old.get(case["id"]) != case:
                        diffs.append(f"  case {case['id']} differs")
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", default="node")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--result", default=None,
                        help="saved result to compare against (default: the committed one)")
    args = parser.parse_args()

    if not args.verify:
        code = run(args.node, RESULT)
        if code:
            return code
        measured = json.loads(RESULT.read_text(encoding="utf-8"))
        out = summary(measured)
        print(json.dumps(out, ensure_ascii=False))
        if out["mismatches"]:
            print("预测与实测不一致：先修 capability()，不要改实测。")
            return 1
        if not all(c["ok"] for c in out["controls"].values()):
            print("泄漏检测的自检失败：检测器本身不可信。")
            return 1
        return 0

    result_path = pathlib.Path(args.result) if args.result else RESULT
    if not result_path.exists():
        print("没有已保存的投影实测结果，先运行不带 --verify 的一次。")
        return 1
    tmp = pathlib.Path(tempfile.mkdtemp()) / "projection-check.json"
    code = run(args.node, tmp)
    if code:
        return code
    saved = json.loads(result_path.read_text(encoding="utf-8"))
    fresh = json.loads(tmp.read_text(encoding="utf-8"))
    diffs = compare(saved, fresh)
    saved_sha = saved.get("moduleSha256")
    current_sha = __import__("hashlib").sha256(TS_MODULE.read_bytes()).hexdigest()
    if saved_sha != current_sha:
        diffs.append(f"moduleSha256: saved {saved_sha} != current source {current_sha}")
    if diffs:
        print("投影实测已过期或与源码不一致：")
        for line in diffs:
            print(" -", line)
        return 1
    print(json.dumps({"verify": "ok", "moduleSha256": saved_sha,
                      "cases": len(saved["cases"]),
                      "leaked": {c["id"]: c.get("leakedFactIds") for c in saved["cases"]},
                      "controls": [c["name"] for c in saved["controls"]]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
