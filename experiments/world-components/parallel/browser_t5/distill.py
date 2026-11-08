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
        WT / "artifacts" / "world-components" / "browser-t5-runtime-r2.json"))
    args = ap.parse_args()

    assets = load(RUNS / "assets.json")
    offline = load(RUNS / "offline-reference.json")
    comparison = load(RUNS / "comparison.json")

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
        "round": 2,
        "supersedes": "browser-t5-runtime-r1.json (round 1: fp32 page runs only)",
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
            "tokenDiffsDistinct": comparison["int8TokenDiffsDistinct"],
            "reading": "int8 changes the wording of one clause on 2 of 7 cases "
                       "(same facts, different phrase); token identity is not "
                       "required by the documented int8 contract, and quality is "
                       "out of scope for c9",
        },
        "verdict": comparison["verdict"],
        "corrections": [
            {
                "claimInRound1": "release() 之后 300 ms 内存未下降，说明只能重载页面",
                "status": "收紧",
                "whatTheDataShows": "page 侧 release() 后 300 ms 确实未下降"
                                    "(973.9 MB)，但把运行时放进 DedicatedWorker 后 "
                                    "terminate() 在 +103 ms 就把可归因内存从 973.3 MB "
                                    "降到 4.46 MB，并在 +88 s 内保持；重建 worker 再跑 7 "
                                    "个用例，输出与离线参照逐 token 相同",
                "remainingClaim": "页面内 release() 不回收 wasm 内存；"
                                  "回收要靠终止承载它的 worker",
            },
            {
                "claimInRound1": "最大取消延迟为 35–72 ms（单步耗时）",
                "status": "撤回（口径错误）",
                "whatTheDataShows": "round 1 记的是从开始生成到抛错的总时长；"
                                    "本轮按 abort() 调用时刻到 AbortError 的间隔测："
                                    "page 内 52.9–97.2 ms，worker 内 93–266.5 ms。"
                                    "上界不是一步耗时，而是取消到达时正在执行的"
                                    "那次 ORT 调用的剩余时间——落在解码步上约 50–100 ms，"
                                    "落在 encoder 上可到 266 ms",
                "remainingClaim": "取消粒度是一步；延迟 = 在飞调用剩余时间 + 让出宏任务 + 检查",
            },
        ],
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
