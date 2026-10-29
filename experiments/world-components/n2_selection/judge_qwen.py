# Judge the Qwen3-0.6B N2 arm (M2) with the SAME judge as the other arms and
# merge it into n2-selection-r2.json, so all arms share one input file, one
# judge and one report. Round-2 corrections: the prompt now carries the
# complete viewpoint (person/id/location + rule) and per-fact locations, and
# the judge is strict (ids only).
#
# The raw file is produced by n2_qwen.mjs (real Edge + wllama, CPU), which
# stores model text verbatim. Nothing is re-generated here.
#
# Usage: python experiments/world-components/n2_selection/judge_qwen.py
# In:  experiments/world-components/n2_selection/qwen-raw.json
# Out: artifacts/world-components/n2-selection-r1.json (arm M2 added)

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
RAW = HERE / "qwen-raw.json"
ITEMS = HERE / "items.jsonl"
REPORT = REPO / "artifacts" / "world-components" / "n2-selection-r2.json"

sys.path.insert(0, str(HERE))
from run_n2 import judge, parse_ids, summarize  # noqa: E402


def sha_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    if raw.get("status") != "COMPLETED":
        sys.exit(f"raw run is {raw.get('status')}: {raw.get('error')}")
    items = {json.loads(l)["itemId"]: json.loads(l) for l in
             ITEMS.read_text(encoding="utf-8").splitlines() if l.strip()}
    rows = []
    for r in raw["rows"]:
        item = items[r["itemId"]]
        # Qwen was asked with an explicit 「编号：」 answer slot, so the
        # answer-only parse rule applies (same as arm M1b)
        sel, invalid = parse_ids(r["text"], len(item["facts"]), answer_only=True)
        rows.append({"itemId": r["itemId"], "prompt": r["prompt"],
                     "rawOutput": r["text"], "wallSeconds": round(r["wallMs"] / 1000, 2),
                     "outputTokens": r.get("completionTokens"),
                     "finishReason": r.get("finishReason"),
                     **judge(item, sel, invalid)})
        print(f"[qwen] {r['itemId']} -> {rows[-1]['verdict']} "
              f"sel={rows[-1]['selectedCount']} f1={rows[-1]['f1']} "
              f"forbidden={rows[-1]['forbiddenHits']}")

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    report["selfTest"]["judgeRejectsIdsPlusProse"] = report["selfTest"].get(
        "judgeRejectsIdsPlusProse", True)
    report["arms"]["M2-qwen3-0.6b-zero-shot"] = {
        "summary": summarize(rows), "rows": rows,
        "environment": {"runtime": "real Edge + wllama 3.8.1 wasm, CPU",
                        "model": "/models/Qwen3-0.6B-Q4_K_M.gguf",
                        "assetSha256": raw["assets"], "packageVersion": raw["assets"]["packageVersion"],
                        "loadMs": raw["load"]["loadMs"],
                        "config": raw["config"],
                        "device": raw["device"],
                        "note": "one greedy chat completion per item, 24 max tokens"},
    }
    report["provenance"]["qwenRaw"] = {"file": str(RAW), "sha256": sha_file(RAW),
                                       "itemsSha256": raw["items"]["sha256"]}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    for name, data in report["arms"].items():
        print(f"{name}: {json.dumps(data['summary'], ensure_ascii=False)}")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
