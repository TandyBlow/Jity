"""Assemble the committed c9 evidence file from the raw runs.

Raw runs stay under runs/ (large, machine-local). This writes one JSON with
everything a reader needs to re-check the conclusions: input hashes, decode
params, per-run stage timings, cancel outcomes, memory samples, token parity
flags, and the wllama assessment inputs.

Usage:
  D:/software/Anaconda/python.exe distill.py [--out <path>]
"""

from __future__ import annotations

import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RUNS = HERE / "runs"
WT = HERE.parents[3]


def load(p: pathlib.Path):
    return json.loads(p.read_text(encoding="utf-8"))


def cli_error(name: str) -> str | None:
    p = RUNS / f"wllama-arch-cli-{name}.txt"
    if not p.exists():
        return None
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if "error loading model" in line:
            return line.split("error loading model: ", 1)[-1].strip()
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(
        WT / "artifacts" / "world-components" / "browser-t5-runtime-r1.json"))
    args = ap.parse_args()

    assets = load(RUNS / "assets.json")
    offline = load(RUNS / "offline-reference.json")
    comparison = load(RUNS / "comparison.json")

    wllama_runs = {}
    for d in sorted(RUNS.glob("wllama*")):
        f = d / "wllama-result.json"
        if f.exists():
            wllama_runs[d.name] = load(f)["result"]

    evidence = {
        "task": {
            "id": "c9",
            "branch": "exp/c-browser-t5",
            "exclusive_dir": "experiments/world-components/parallel/browser_t5/",
            "question": "can the existing 77M T5 encoder-decoder run in a real "
                        "browser: load, inference, cancel, memory, and identical "
                        "results versus the offline loop",
            "out_of_scope": ["quality of the generated text", "training",
                             "int8 quantisation", "wiring into the world page",
                             "wllama end-to-end (see wllamaAssessment)"],
        },
        "model": {
            "checkpoint": "Randeng-T5-77M fine-tune r3-direction",
            "params": assets["checkpoint"]["params"],
            "config": {k: assets["decode_params"][k] for k in
                       ("num_heads", "d_kv", "d_model", "vocab_size",
                        "num_layers", "num_decoder_layers",
                        "eos_token_id", "pad_token_id",
                        "decoder_start_token_id")},
            "graphs": {k: {"sha256": v.get("sha256"), "bytes": v.get("bytes")}
                       for k, v in assets["graphs"].items() if v.get("exists")},
            "exportManifestMatchesDisk": all(
                assets["export_manifest_content"]["graphs"].get(k) == v.get("sha256")
                for k, v in assets["graphs"].items() if v.get("exists")),
            "spiece": {"sha256": assets["checkpoint"]["spiece"].get("sha256"),
                       "bytes": assets["checkpoint"]["spiece"].get("bytes")},
            "decode": assets["decode_params"],
        },
        "fixtures": {
            "file": assets["fixture"]["path"],
            "sha256": assets["fixture"]["sha256"],
            "cases": assets["fixture_cases"],
        },
        "offlineReference": offline,
        "browserRuns": [
            {
                "run": r["run"],
                "deepMemoryPass": r["deepMemoryPass"],
                "wallMs": r["wallMs"],
                "servedMiB": r["transferMiB"],
                "browser": r["browserVersion"],
                "stages": r["stages"],
                "cold": r["cold"],
                "warm": r["warm"],
                "noYield": r["noYield"],
                "tokenizerIdMatch": r["tokenizerMatch"],
                "cancel": r["cancel"],
                "cases": [{k: c[k] for k in
                           ("name", "browserSteps", "browserMeanStepMs",
                            "browserEncoderMs", "offlineSteps",
                            "offlineMeanStepMs", "offlineEncoderMs",
                            "tokensMatchOffline", "textMatchOffline",
                            "tokensMatchStoredFixture", "text")}
                          for c in r["cases"]],
                "memory": r["memory"],
            }
            for r in comparison["runs"]
        ],
        "timingSummary": comparison["timingSummary"],
        "memorySummary": comparison["memorySummary"],
        "verdict": comparison["verdict"],
        "wllamaAssessment": {
            "status": "undetermined for end-to-end; blocked on a real T5 GGUF",
            "whatWasRun": {
                "syntheticGguf": "three minimal GGUF v3 headers differing only "
                                 "in general.architecture ('t5', 't5encoder', "
                                 "'notanarch'), fed to wllama 3.8.1 loadModel() "
                                 "then createCompletion() in headless Edge",
                "runs": wllama_runs,
                "llamaCppCli": {
                    "binary": ".local/llama-cpp/llama-cli.exe",
                    "t5": cli_error("t5"),
                    "t5encoder": cli_error("t5encoder"),
                    "notanarch": cli_error("notanarch"),
                },
            },
            "reading": [
                "llama.cpp itself registers both 't5' and 't5encoder': the "
                "loader asks for t5.context_length rather than rejecting the "
                "arch, so a T5 GGUF is a known file format for that family.",
                "the same synthetic files fail identically in wllama "
                "(RuntimeError: Invalid typed array length) for the bogus arch "
                "too, so wllama's load result says nothing about arch support "
                "— it does not reach the native loader with a file this thin.",
                "no T5 GGUF exists in this repository and no HF->GGUF converter "
                "is vendored here, so the end-to-end question could not be run.",
            ],
            "nextStep": "convert the r3-direction (or base 77M) checkpoint to "
                        "GGUF with a converter that supports the t5 arch, then "
                        "repeat loadModel + one generation in the browser",
        },
        "openItems": [
            "wllama end-to-end T5 generation (needs a real T5 GGUF)",
            "int8 graphs in the browser (separate quantisation question)",
            "load time at network-realistic transfer (all numbers here are "
            "localhost, 388 MiB served without throttling)",
            "whether the 973 MB browser footprint is acceptable in the world "
            "page alongside the rest of the app",
            "Firefox/Safari runtimes (only Edge was exercised)",
        ],
    }

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("wrote", out)
    print("verdict:", json.dumps(evidence["verdict"], ensure_ascii=False))
    print("model sha ok:", evidence["model"]["exportManifestMatchesDisk"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
