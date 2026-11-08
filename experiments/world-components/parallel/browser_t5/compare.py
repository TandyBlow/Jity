"""c9 comparison: browser ids vs the offline ORT-python reference, and a
distilled summary of every probe run in runs/.

The gate is token identity on the same 7 registered inputs. Text is compared
as a secondary read (same sentencepiece decode on both sides) because a
token-identical output must also render identically.

Usage:
  D:/software/Anaconda/python.exe compare.py [--out runs/comparison.json]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
RUNS = HERE / "runs"


def load(p: pathlib.Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RUNS / "comparison.json"))
    args = ap.parse_args()

    assets = load(RUNS / "assets.json")
    offline = load(RUNS / "offline-reference.json")
    offline_by_name = {c["name"]: c for c in offline["cases"]}

    runs = []
    for d in sorted(p for p in RUNS.iterdir() if p.is_dir()):
        f = d / "browser-result.json"
        if not f.exists():
            continue
        runs.append((d.name, load(f)))

    per_run = []
    all_parity = True
    for name, archive in runs:
        r = archive["result"]
        cases = []
        for c in r.get("cases", []):
            ref = offline_by_name.get(c["name"])
            match = ref is not None and c["ids"] == ref["ids"]
            all_parity = all_parity and match
            cases.append({
                "name": c["name"],
                "browserSteps": c["timings"]["steps"],
                "browserMeanStepMs": c["timings"]["meanStepMs"],
                "browserEncoderMs": c["timings"]["encoderMs"],
                "offlineSteps": ref["steps"] if ref else None,
                "offlineMeanStepMs": ref["meanStepMs"] if ref else None,
                "offlineEncoderMs": ref["encoderMs"] if ref else None,
                "stepsMatchOffline": (ref["steps"] == c["timings"]["steps"]) if ref else None,
                "tokensMatchOffline": match,
                "textMatchOffline": (c["text"] == ref["text"]) if ref else None,
                "tokensMatchStoredFixture": c["tokenMatchVsBakedReference"],
                "text": c["text"],
            })
        per_run.append({
            "run": name,
            "deepMemoryPass": archive["environment"].get("deepMemoryPass"),
            "browserVersion": archive["environment"]["browser"]["version"],
            "wallMs": archive["wallMs"],
            "transferMiB": round(archive["transfer"]["bytes"] / 1048576, 1),
            "stages": r.get("stages"),
            "cold": r.get("cold", {}).get("timings"),
            "warm": r.get("warm", {}).get("timings"),
            "noYield": r.get("noYield", {}).get("timings"),
            "tokenizerMatch": all(t["matchesBakedIds"] for t in r.get("tokenizer", [])),
            "cancel": r.get("cancel"),
            "cases": cases,
            "memory": r.get("memory"),
        })

    # aggregate the timing questions the task asks
    stage_keys = ["ortImportMs", "tokenizerFetchMs", "spLoadMs",
                  "encoderCreateMs", "decoderCreateMs", "createTotalMs"]
    timing_summary = {}
    for k in stage_keys:
        vals = [x["stages"][k] for x in per_run if x.get("stages")]
        timing_summary[k] = {"values": vals,
                             "median": round(statistics.median(vals), 1) if vals else None,
                             "min": min(vals) if vals else None,
                             "max": max(vals) if vals else None}
    warm_steps = [c["browserMeanStepMs"] for x in per_run for c in x["cases"]]
    timing_summary["browserMeanStepMsAllCases"] = {
        "median": round(statistics.median(warm_steps), 1),
        "min": min(warm_steps), "max": max(warm_steps), "n": len(warm_steps)}
    off_steps = [c["meanStepMs"] for c in offline["cases"] if c["meanStepMs"]]
    timing_summary["offlineMeanStepMsAllCases"] = {
        "median": round(statistics.median(off_steps), 1),
        "min": min(off_steps), "max": max(off_steps), "n": len(off_steps)}

    mem_run = next((x for x in per_run if x["deepMemoryPass"]), None)
    memory_summary = None
    if mem_run:
        s = {x["label"]: x for x in mem_run["memory"]["samples"]}
        memory_summary = {
            "run": mem_run["run"],
            "isolatedBytesBeforeCreate": s["before-create"].get("isolatedBytes"),
            "isolatedBytesAfterCreate": s["after-create"].get("isolatedBytes"),
            "isolatedBytesAfterWarm": s["after-warm"].get("isolatedBytes"),
            "isolatedBytesBeforeRelease": s["before-release"].get("isolatedBytes"),
            "isolatedBytesAfterRelease": s["after-release"].get("isolatedBytes"),
            "jsHeapAfterCreate": s["after-create"].get("jsHeapUsedBytes"),
            "jsHeapSteadyState": s["case-n4h-chain-01"].get("jsHeapUsedBytes"),
            "releasedReclaimedMiB": round((
                s["before-release"]["isolatedBytes"] -
                s["after-release"]["isolatedBytes"]) / 1048576, 1),
            "note": "isolated bytes = performance.measureUserAgentSpecificMemory "
                    "under COOP/COEP; includes the fetched graph bytes and the "
                    "wasm linear memory, i.e. the whole page's attributable "
                    "footprint, not the model alone",
        }

    comparison = {
        "purpose": "c9 verdict: does the 77M T5 encoder-decoder run in a real "
                   "browser, at what cost, and does it produce the same tokens "
                   "as the offline ORT-python loop on identical input",
        "assets": {
            "graphs": {k: v.get("sha256") for k, v in assets["graphs"].items()},
            "spiece": assets["checkpoint"]["spiece"].get("sha256"),
            "params": assets["checkpoint"]["params"],
            "fixture": assets["fixture"].get("sha256"),
            "fixtureCases": [c["name"] for c in assets["fixture_cases"]],
        },
        "offline": {
            "environment": offline["environment"],
            "sessionLoadMs": offline["sessionLoadMs"],
            "allMatchStoredReference": offline["allMatchStoredReference"],
        },
        "runs": per_run,
        "timingSummary": timing_summary,
        "memorySummary": memory_summary,
        "verdict": {
            "browserRunsModel": bool(per_run) and all(x["cold"] for x in per_run),
            "tokenParityVsOfflineAllRuns": all_parity,
            "tokenizerParity": all(x["tokenizerMatch"] for x in per_run),
            "cancelWorks": all(
                x["cancel"]["timerAbort"]["threw"] and
                x["cancel"]["stepAbort"]["threw"] for x in per_run),
            "sessionUsableAfterCancel": all(
                x["cancel"]["reuseAfterAbort"]["sameIdsAsCold"] for x in per_run),
        },
    }
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(comparison, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("wrote", out)
    print("runs:", [x["run"] for x in per_run])
    print("verdict:", json.dumps(comparison["verdict"], ensure_ascii=False))
    print("timing:", json.dumps(timing_summary["createTotalMs"]))
    print("browser step ms:", json.dumps(
        timing_summary["browserMeanStepMsAllCases"]))
    print("offline step ms:", json.dumps(
        timing_summary["offlineMeanStepMsAllCases"]))
    for x in per_run:
        bad = [c["name"] for c in x["cases"] if not c["tokensMatchOffline"]]
        print(f"{x['run']:8s} parity={'ok' if not bad else 'DIFF ' + ','.join(bad)}")
    return 0 if all_parity else 1


if __name__ == "__main__":
    sys.exit(main())
