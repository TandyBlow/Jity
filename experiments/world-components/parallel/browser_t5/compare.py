"""c9 comparison across every probe run in runs/.

Two families of run share the same output shape on purpose:

  page runs    runs/*/browser-result.json   (run_probe.mjs, model in the page)
  worker runs  runs/*/worker-result.json    (run_worker_probe.mjs, model in a
                                             DedicatedWorker so terminate() can
                                             be tried as a release mechanism)

Each is tagged fp32 or int8 by the driver. The gate differs by variant:

  fp32  token identity against the offline ORT-python loop (strict)
  int8  token identity is NOT required (documented int8 contract: activation
        noise shifts argmax); every difference is listed instead of gated

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


def variant_of(archive: dict) -> str:
    env = archive.get("environment", {})
    return env.get("graphs") or env.get("graphVariant") or "fp32"


def kind_of(archive: dict) -> str:
    return "worker" if "worker" in pathlib.Path(archive["_file"]).name else "page"


def create_ms(archive: dict) -> float | None:
    r = archive["result"]
    if "workerA" in r:
        return r["workerA"].get("stages", {}).get("workerCreateMs")
    st = r.get("stages") or {}
    return st.get("createTotalMs")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(RUNS / "comparison.json"))
    args = ap.parse_args()

    assets = load(RUNS / "assets.json")
    offline = load(RUNS / "offline-reference.json")
    offline_by_name = {c["name"]: c for c in offline["cases"]}
    # int8 needs its own ORT-python reference: comparing browser-int8 against
    # fp32 mixes two questions (quantisation delta vs browser/offline drift)
    offline_int8_p = RUNS / "offline-reference-int8.json"
    offline_int8 = load(offline_int8_p) if offline_int8_p.exists() else None
    offline_int8_by_name = ({c["name"]: c for c in offline_int8["cases"]}
                            if offline_int8 else {})

    runs = []
    for f in sorted(RUNS.glob("*/browser-result.json")) + sorted(RUNS.glob("*/worker-result.json")):
        archive = load(f)
        archive["_file"] = str(f)
        runs.append((f.parent.name, archive))

    per_run = []
    for name, archive in runs:
        r = archive["result"]
        variant = variant_of(archive)
        kind = kind_of(archive)
        cases = []
        parity_all = True
        for c in r.get("cases", []):
            ref = offline_by_name.get(c["name"])
            ref_same = (offline_int8_by_name.get(c["name"])
                        if variant == "int8" else ref)
            match = ref is not None and c["ids"] == ref["ids"]
            match_same = ref_same is not None and c["ids"] == ref_same["ids"]
            if variant == "fp32":
                parity_all = parity_all and match
            else:
                parity_all = parity_all and match_same
            cases.append({
                "tokensMatchOfflineSameGraph": match_same,
                "name": c["name"],
                "steps": c["timings"]["steps"],
                "meanStepMs": c["timings"]["meanStepMs"],
                "encoderMs": c["timings"]["encoderMs"],
                "offlineSteps": ref["steps"] if ref else None,
                "offlineMeanStepMs": ref["meanStepMs"] if ref else None,
                "tokensMatchOffline": match,
                "tokensMatchOfflineFp32": match,
                "tokensMatchStoredFixture": c["tokenMatchVsBakedReference"],
                "text": c["text"],
                "offlineText": ref["text"] if ref else None,
                "sameAsWorkerACase0": c.get("sameAsWorkerACase0"),
            })
        mem = r.get("memory") or {}
        entry = {
            "run": name,
            # an --rss run samples the OS process tree from the driver every
            # second; that starves the browser of CPU and inflates load times,
            # so its memory/RSS evidence counts but its timings do not
            "timingUsable": archive.get("rss") is None,
            "kind": kind,
            "variant": variant,
            "deepMemoryPass": archive["environment"].get("deepMemoryPass"),
            "wallMs": archive["wallMs"],
            "servedMiB": round(archive["transfer"]["bytes"] / 1048576, 1),
            "browser": archive["environment"]["browser"]["version"],
            "createMs": create_ms(archive),
            "stages": (r.get("workerA", {}).get("stages") if kind == "worker"
                       else r.get("stages")),
            "tokenizerStages": r.get("tokenizer", {}).get("stages")
                               if kind == "worker" else None,
            "cold": r.get("cold"),
            "warm": r.get("warm"),
            "cancel": r.get("cancel"),
            "cases": cases,
            "tokensAllMatchOffline": parity_all if cases else False,
            "memory": mem if mem else None,
            "terminate": r.get("terminate"),
            "rebuiltWorkerTokens": (
                all(c["sameAsWorkerACase0"] is not False for c in cases)
                if kind == "worker" else None),
        }
        per_run.append(entry)

    # --- summaries -----------------------------------------------------------
    def stat(vals):
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        return {"values": [round(v, 1) for v in vals],
                "median": round(statistics.median(vals), 1),
                "min": round(min(vals), 1), "max": round(max(vals), 1), "n": len(vals)}

    timing = {
        "createMs": {f"{k}-{v}": stat([x["createMs"] for x in per_run
                                       if x["kind"] == k and x["variant"] == v
                                       and x["timingUsable"]])
                     for k in ("page", "worker") for v in ("fp32", "int8")},
        "stepMs": {v: stat([c["meanStepMs"] for x in per_run
                            if x["variant"] == v and x["kind"] == "page"
                            and x["timingUsable"] for c in x["cases"]])
                   for v in ("fp32", "int8")},
        "offlineStepMs": stat([c["meanStepMs"] for c in offline["cases"]]),
        "encoderMs": {v: stat([c["encoderMs"] for x in per_run
                               if x["variant"] == v and x["kind"] == "page"
                               and x["timingUsable"] for c in x["cases"]])
                      for v in ("fp32", "int8")},
    }

    mem_summary = {}
    for x in per_run:
        if not x["deepMemoryPass"] or not x["memory"]:
            continue
        samples = {s["label"]: s for s in x["memory"].get("samples", [])}
        iso = {k: v.get("isolatedBytes") for k, v in samples.items()}
        entry = {"run": x["run"], "kind": x["kind"], "variant": x["variant"],
                 "isolatedBytesByLabel": iso}
        if x["kind"] == "page":
            entry["afterCreateMiB"] = round(
                (iso.get("after-create") or 0) / 1048576, 1) if iso.get("after-create") else None
            entry["afterReleaseMiB"] = round(
                (iso.get("after-release") or 0) / 1048576, 1) if iso.get("after-release") else None
        else:
            entry["afterWorkerInitMiB"] = round(
                (iso.get("after-A-init") or 0) / 1048576, 1) if iso.get("after-A-init") else None
            entry["reclaimedMiB"] = round((x["terminate"] or {}).get("reclaimedBytes", 0) / 1048576, 1)
            entry["postTerminateSamplesMiB"] = [
                round(s["isolatedBytes"] / 1048576, 1) for s in
                (x["terminate"] or {}).get("samples", []) if s.get("isolatedBytes")]
        mem_summary[x["run"]] = entry

    cancel_summary = []
    for x in per_run:
        c = x["cancel"] or {}
        if x["kind"] == "page":
            if c.get("timerAbort"):
                cancel_summary.append({
                    "run": x["run"], "variant": x["variant"], "kind": "page",
                    "mode": "timer(120ms)", "threw": c["timerAbort"]["threw"],
                    "completedSteps": c["timerAbort"].get("completedSteps"),
                    "issueToThrowMs": c["timerAbort"].get("issueToThrowMs")})
            if c.get("stepAbort"):
                cancel_summary.append({
                    "run": x["run"], "variant": x["variant"], "kind": "page",
                    "mode": "step-boundary(5)", "threw": c["stepAbort"]["threw"],
                    "completedSteps": c["stepAbort"].get("completedSteps"),
                    "issueToThrowMs": c["stepAbort"].get("issueToThrowMs")})
        else:
            cancel_summary.append({
                "run": x["run"], "variant": x["variant"], "kind": "worker",
                "mode": "postMessage at 120ms",
                "threw": (c.get("outcome") or {}).get("type") == "cancelled",
                "completedSteps": (c.get("outcome") or {}).get("completedSteps"),
                "issueToThrowMs": c.get("issueToThrowMs")})

    int8_same_graph_failures = []
    int8_diffs = []
    for x in per_run:
        if x["variant"] != "int8":
            continue
        for c in x["cases"]:
            if not c["tokensMatchOfflineSameGraph"]:
                int8_same_graph_failures.append({"run": x["run"], "case": c["name"]})
            if not c["tokensMatchOfflineFp32"]:
                int8_diffs.append({
                    "run": x["run"], "kind": x["kind"], "case": c["name"],
                    "browser": c["text"], "offline": c["offlineText"],
                    "browserSteps": c["steps"], "offlineSteps": c["offlineSteps"]})
    # deduplicate the same case diff across runs (it was stable)
    seen = set()
    int8_distinct = []
    for d in int8_diffs:
        key = (d["case"], d["browser"])
        if key in seen:
            continue
        seen.add(key)
        int8_distinct.append(d)

    comparison = {
        "purpose": "c9 round-2 verdict: worker-hosted runtime memory release, "
                   "cancel latency measured from the abort call, and the int8 "
                   "graph set measured against fp32 on size/load/step/memory/tokens",
        "gate": {
            "fp32": "token identity against the fresh ORT-python reference",
            "int8": "no token-identity requirement; differences are listed",
        },
        "assets": {
            "graphs_fp32": {k: v.get("sha256") for k, v in assets["graphs"].items()
                            if k != "decoder_step.onnx"},
            "graphs_int8": {k: v.get("sha256") for k, v in assets["graphs_int8"].items()},
            "spiece": assets["checkpoint"]["spiece"].get("sha256"),
            "params": assets["checkpoint"]["params"],
            "fixture": assets["fixture"].get("sha256"),
        },
        "offline": {"environment": offline["environment"],
                    "sessionLoadMs": offline["sessionLoadMs"],
                    "allMatchStoredReference": offline["allMatchStoredReference"]},
        "runs": per_run,
        "timingSummary": timing,
        "memorySummary": mem_summary,
        "cancelSummary": cancel_summary,
        "int8TokenDiffsDistinct": int8_distinct,
        "int8SameGraphFailures": int8_same_graph_failures,
        "verdict": {
            "fp32TokenParityAllPageRuns": all(
                x["tokensAllMatchOffline"] for x in per_run
                if x["variant"] == "fp32" and x["kind"] == "page"),
            "fp32TokenParityWorkerRuns": all(
                x["tokensAllMatchOffline"] for x in per_run
                if x["variant"] == "fp32" and x["kind"] == "worker"),
            "workerTerminateReleasesMemory": all(
                (x["terminate"] or {}).get("reclaimedBytes", 0) > 500 * 1048576
                for x in per_run if x["kind"] == "worker" and x["deepMemoryPass"]),
            "rebuiltWorkerReproduces": all(
                x["rebuiltWorkerTokens"] is not False
                for x in per_run if x["kind"] == "worker"),
            "int8SameGraphParity": not int8_same_graph_failures and any(
                x["variant"] == "int8" for x in per_run),
            "int8SameGraphFailures": int8_same_graph_failures,
            "int8TokenIdenticalToFp32": sum(
                1 for x in per_run if x["variant"] == "int8"
                for c in x["cases"] if c["tokensMatchOfflineFp32"]),
        },
    }
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(comparison, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("wrote", out)
    print("runs:", [(x["run"], x["kind"], x["variant"]) for x in per_run])
    print("verdict:", json.dumps(comparison["verdict"], ensure_ascii=False))
    print("create:", json.dumps(timing["createMs"], ensure_ascii=False))
    print("step:", json.dumps({k: (v or {}).get("median") for k, v in timing["stepMs"].items()}))
    print("int8 diffs (distinct):", len(int8_distinct))
    for d in int8_distinct:
        print("  ", d["case"], "|", d["browser"], "|", d["offline"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
