"""Assemble the committed round-2 c9 evidence file from the raw runs.

Round 2 answers three things round 1 could not:
  1. does terminating a DedicatedWorker holding the runtime return the memory
  2. what is the cancel latency measured from the abort() call itself, and
     what bounds it
  3. what do the existing int8 graphs cost in size / load / step / memory, and
     where do their tokens differ from fp32

Usage:
  D:/software/Anaconda/python.exe distill.py [--out <path>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RUNS = HERE / "runs"
WT = HERE.parents[3]


def load(p: pathlib.Path):
    return json.loads(p.read_text(encoding="utf-8"))


def file_sha(p: pathlib.Path) -> str | None:
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(
        WT / "artifacts" / "world-components" / "browser-t5-runtime-r3.json"))
    args = ap.parse_args()

    assets = load(RUNS / "assets.json")
    offline = load(RUNS / "offline-reference.json")
    offline_int8_p = RUNS / "offline-reference-int8.json"
    offline_int8 = load(offline_int8_p) if offline_int8_p.exists() else None
    comparison = load(RUNS / "comparison.json")

    rss_runs = []
    for d in sorted(RUNS.glob("*/worker-result.json")):
        archive = load(d)
        if not archive.get("rss"):
            continue
        r = archive["result"]
        after = archive["rss"].get("afterTerminate") or []
        rss_runs.append({
            "run": d.parent.name,
            "terminateWallClockMs": (r.get("terminate") or {}).get("terminateWallClockMs"),
            "beforeTerminateMiB": round((archive["rss"].get("atTerminate") or {}).get("bytes", 0) / 1048576, 1),
            "firstSamplesAfterTerminate": after[:6],
            "firstDropSample": archive["rss"].get("firstDropSample"),
            "pageReportedFirstSample": (r.get("terminate") or {}).get("firstSample"),
            "timingUsable": False,
            "note": "--rss runs sample the OS process tree every second from the "
                    "driver; that steals CPU from the browser, so load/inference "
                    "timings from these runs are excluded",
        })

    wllama_runs = {}
    for d in sorted(RUNS.glob("wllama*")):
        f = d / "wllama-result.json"
        if f.exists():
            wllama_runs[d.name] = load(f)["result"]

    page = [r for r in comparison["runs"] if r["kind"] == "page"]
    worker = [r for r in comparison["runs"] if r["kind"] == "worker"]

    def slim_page(r):
        return {
            "run": r["run"], "variant": r["variant"],
            "deepMemoryPass": r["deepMemoryPass"], "wallMs": r["wallMs"],
            "servedMiB": r["servedMiB"], "createMs": r["createMs"],
            "stages": r["stages"], "tokenizerStages": r["tokenizerStages"],
            "cold": r["cold"], "warm": r["warm"], "cancel": r["cancel"],
            "memory": r["memory"],
            "cases": [{k: c[k] for k in ("name", "steps", "meanStepMs",
                                         "encoderMs", "offlineSteps",
                                         "offlineMeanStepMs", "tokensMatchOffline",
                                         "tokensMatchStoredFixture", "text",
                                         "offlineText")} for c in r["cases"]],
        }

    def slim_worker(r):
        return {
            "run": r["run"], "variant": r["variant"],
            "deepMemoryPass": r["deepMemoryPass"], "wallMs": r["wallMs"],
            "servedMiB": r["servedMiB"], "createMs": r["createMs"],
            "stages": r["stages"], "tokenizerStages": r["tokenizerStages"],
            "memory": r["memory"], "terminate": r["terminate"],
            "cancel": r["cancel"], "rebuiltWorkerTokens": r["rebuiltWorkerTokens"],
            "cases": [{k: c[k] for k in ("name", "steps", "meanStepMs",
                                         "encoderMs", "tokensMatchOffline",
                                         "sameAsWorkerACase0", "text")}
                      for c in r["cases"]],
        }

    evidence = {
        "round": 3,
        "supersedes": "browser-t5-runtime-r2.json (round 2) and r1",
        "task": {
            "id": "c9", "branch": "exp/c-browser-t5",
            "exclusive_dir": "experiments/world-components/parallel/browser_t5/",
            "question": "release the runtime's memory by terminating a worker, "
                        "price the int8 graphs, and measure cancel latency from "
                        "the abort call instead of from the run start",
        },
        "model": {
            "checkpoint": "Randeng-T5-77M fine-tune r3-direction",
            "params": assets["checkpoint"]["params"],
            "config": {k: assets["decode_params"][k] for k in
                       ("num_heads", "d_kv", "d_model", "vocab_size", "num_layers",
                        "num_decoder_layers", "eos_token_id", "pad_token_id",
                        "decoder_start_token_id")},
            "graphs": {
                "fp32": {k: {"sha256": v.get("sha256"), "bytes": v.get("bytes")}
                         for k, v in assets["graphs"].items() if v.get("exists")},
                "int8": {k: {"sha256": v.get("sha256"), "bytes": v.get("bytes")}
                         for k, v in assets["graphs_int8"].items() if v.get("exists")},
            },
            "spiece": {"sha256": assets["checkpoint"]["spiece"].get("sha256"),
                       "bytes": assets["checkpoint"]["spiece"].get("bytes")},
            "decode": assets["decode_params"],
        },
        "fixtures": {"file": assets["fixture"]["path"],
                     "sha256": assets["fixture"]["sha256"],
                     "cases": assets["fixture_cases"]},
        "code": {
            "adapter": {"path": "experiments/world-components/parallel/browser_t5/t5_adapter.mjs",
                        "sha256": file_sha(HERE / "t5_adapter.mjs")},
            "worker": {"path": "experiments/world-components/parallel/browser_t5/t5_worker.mjs",
                       "sha256": file_sha(HERE / "t5_worker.mjs")},
            "pageProbe": {"path": "experiments/world-components/parallel/browser_t5/probe.html",
                          "sha256": file_sha(HERE / "probe.html")},
            "workerProbe": {"path": "experiments/world-components/parallel/browser_t5/worker_probe.html",
                            "sha256": file_sha(HERE / "worker_probe.html")},
        },
        "offlineReference": offline,
        "offlineReferenceInt8": offline_int8,
        "pageRuns": [slim_page(r) for r in page],
        "workerRuns": [slim_worker(r) for r in worker],
        "timingSummary": comparison["timingSummary"],
        "memorySummary": comparison["memorySummary"],
        "cancelSummary": comparison["cancelSummary"],
        "int8": {
            "graphBytes": {
                "fp32": sum(v["bytes"] for v in assets["graphs"].values()
                            if v.get("exists") and v["path"].endswith(
                                ("encoder.onnx", "decoder_kv.onnx"))),
                "int8": sum(v["bytes"] for v in assets["graphs_int8"].values()
                            if v.get("exists")),
            },
            "pageCreateMs": comparison["timingSummary"]["createMs"]["page-int8"]["values"],
            "fp32PageCreateMs": comparison["timingSummary"]["createMs"]["page-fp32"]["values"],
            "stepMsMedian": {"fp32": comparison["timingSummary"]["stepMs"]["fp32"]["median"],
                             "int8": comparison["timingSummary"]["stepMs"]["int8"]["median"]},
            "memoryMiB": {
                "fp32": [e.get("afterCreateMiB") for e in
                         comparison["memorySummary"].values()
                         if e["variant"] == "fp32" and e["kind"] == "page"],
                "int8": [e.get("afterCreateMiB") for e in
                         comparison["memorySummary"].values()
                         if e["variant"] == "int8" and e["kind"] == "page"],
            },
            "tokenDiffsDistinctVsFp32": comparison["int8TokenDiffsDistinct"],
            "browserVsOfflineSameGraph": comparison["verdict"]["int8SameGraphParity"],
            "browserVsOfflineSameGraphFailures": comparison["verdict"]["int8SameGraphFailures"],
            "reading": "browser-int8 reproduces ORT-python-int8 exactly on all "
                       "21 case-runs, so the browser adds no drift of its own. The "
                       "2/7 token differences versus fp32 are the quantisation "
                       "effect: one clause reworded, same facts. Token identity "
                       "is not required by the documented int8 contract, and "
                       "quality is out of scope for c9",
        },
        "verdict": comparison["verdict"],
        "corrections": [
            {
                "claimInRound1": "release() 之后 300 ms 内存未下降，说明只能重载页面",
                "status": "round 2 收紧",
                "whatTheDataShows": "把运行时放进 DedicatedWorker 后 terminate() "
                                    "把可归因内存从 973.3 MB 降到 4.46 MB，"
                                    "重建 worker 再跑 7 个用例与离线一致",
                "remainingClaim": "页面内 release() 不回收 wasm 内存；"
                                  "回收要靠终止承载它的 worker",
            },
            {
                "claimInRound1": "最大取消延迟为 35–72 ms（单步耗时）",
                "status": "round 2 撤回（口径错误）",
                "whatTheDataShows": "按 abort() 调用时刻到 AbortError 的间隔测："
                                    "page 内 52.9–97.2 ms，worker 内 93–266.5 ms。"
                                    "上界是取消到达时正在执行的那次 ORT 调用的剩余时间",
                "remainingClaim": "取消粒度是一步；延迟 = 在飞调用剩余时间 + "
                                  "让出宏任务 + 检查",
            },
            {
                "claimInRound2": "terminate() 在 +103 ms 就把内存还到 4.46 MB",
                "status": "撤回（时序口径错误）",
                "whatTheDataShows": "round 2 的时间戳是采样*开始*的时刻，"
                                    "而 performance.measureUserAgentSpecificMemory() "
                                    "本身要 13–60 s（它强制全量 GC）。所以那句话只能"
                                    "说明「以某个更晚时刻为准已经是 4.46 MB」，"
                                    "不能说明回收在 103 ms 内完成。"
                                    "补测：1 s 采样的浏览器进程树工作集在 terminate 后"
                                    "+0.19 s 仍为 1085.7 MB、+1.21 s 降到 378.6 MB"
                                    "（另一轮 +59 ms 仍 2014.8 MB、+1.13 s 降到 964.2 MB），"
                                    "即回收在约 1 s 内可观测，分辨率 1 s",
                "remainingClaim": "terminate() 是让内存回到基线的手段（973.3 → 4.46 MB，"
                                  "int8 713.1 → 4.46 MB，重建 worker 后输出一致）；"
                                  "回收耗时约 1 s 量级，但没能测到亚秒精度",
            },
            {
                "claimInRound2": "int8 与 fp32 离线参照有 2/7 用例 token 不同",
                "status": "补齐归因",
                "whatTheDataShows": "补跑同一份 int8 图的 ORT-python 参照"
                                    "（runs/offline-reference-int8.json），"
                                    "浏览器 int8 三轮 × 7 用例与它逐 token 全同（21/21）；"
                                    "那 2 处差异在离线 int8 上完全一样地出现，"
                                    "因此差异来自量化本身，不是浏览器",
                "remainingClaim": "int8 的浏览器/离线一致性成立；"
                                  "int8 与 fp32 的 2 处措辞差异是量化效应",
            },
        ],
        "rssRuns": rss_runs,
        "wllamaAssessment": {
            "status": "undetermined; unchanged from round 1",
            "runs": wllama_runs,
            "blocker": "no real T5 GGUF and no HF->GGUF converter in the tree",
        },
        "openItems": [
            "re-init cost after terminate: every terminate() needs a full reload "
            "(worker init 10.1-14.1 s measured), so terminate is a hard reset, "
            "not a cheap discard",
            "int8 quality on a judged holdout (c9 only compares tokens)",
            "network-realistic transfer (all runs are localhost)",
            "Firefox / Safari",
            "coexistence with the rest of the world page",
            "wllama end-to-end T5 (needs a real T5 GGUF)",
        ],
    }

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("wrote", out)
    print("verdict:", json.dumps(evidence["verdict"], ensure_ascii=False))
    print("graph bytes:", evidence["int8"]["graphBytes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
