# -*- coding: utf-8 -*-
"""Write the lane-11 HPC request files from the candidate registry.

Lane 10 is the only submitter. This script only prepares JSON; it never calls a
cluster. Two requests are produced:

  * preflight-001: download/hash/GGUF-metadata/load-smoke. No dev-package
    inference, no quality claim.
  * quality-001: the frozen-prompt batch. `readyToSubmit` stays false until the
    dev package is pinned and 01 either fixes the three non-serializable cases
    or acknowledges the declared 12-case subset.

Usage:
    python -X utf8 src/make_requests.py
"""
from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = pathlib.Path("D:/others/Jity/.local/parallel-local-game/results/product/hpc-requests")
CANDIDATES = ROOT / "models/candidates.json"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def model_entry(candidate: dict) -> dict:
    gguf = candidate["gguf"]
    base = candidate["base"]
    return {
        "id": candidate["id"],
        "repo": gguf["repo"],
        "revision": gguf["revision"],
        "file": gguf["file"],
        "bytes": gguf["bytes"],
        "lfsSha256": gguf["lfsSha256"],
        "downloadUrl": f"https://huggingface.co/{gguf['repo']}/resolve/{gguf['revision']}/{gguf['file']}",
        "baseRepo": base["repo"],
        "baseRevision": base["revision"],
        "family": candidate["family"],
        "license": candidate["license"]["spdx"],
        "licenseDecisionRequired": candidate["license"]["decisionRequired"],
        "publisher": gguf["publisher"],
        "expectedArchitecture": None,
        "architectureKnownToShippedWasm": True,
        "wllamaWasmSha256": candidate["operatorEvidence"]["wllamaWasmSha256"],
        "note": "expectedArchitecture is filled from GGUF metadata during preflight; the wasm "
                "architecture list is necessary evidence only, not a load proof.",
    }


def main() -> int:
    registry = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    passing = [row for row in registry["candidates"] if row["preInferenceGate"]["passed"]]
    prompts_dir = ROOT / "evidence/prompts-dev-v1"
    quality_ready = False
    quality_blocked = (
        "3/15 dev cases use non-canonical 05 delta shapes and the reference serializer "
        "yuyan-prose-result-v2 refuses them; reported to 01 in "
        "results/11-model-search/requests/01-dev-package-canonical-delta.json. "
        "11 will not hand-edit 05's facts into a different shape."
    )
    pinned_preregistration = ROOT / "preregistration.v1.json"
    preregistration_path = pinned_preregistration if pinned_preregistration.exists() else ROOT / "preregistration.draft.json"

    preflight = {
        "requestId": "11-model-search-preflight-001",
        "from": "11-model-search",
        "to": "10-training",
        "requestedAt": now(),
        "kind": "model-preflight",
        "qualityBatch": False,
        "priority": "below current product blockers and below 12's first batch; download/load work only, can share a window",
        "purpose": "Download the pinned candidate GGUFs, verify sha256, read GGUF metadata "
                   "(architecture/quantisation/chat template) and prove llama.cpp can load and "
                   "generate one neutral smoke sentence. This is operator/load evidence only; it "
                   "is NOT a dev-pack quality comparison and must not be reported as quality.",
        "branch": "goal/local-11-model-search",
        "scripts": {
            "ggufProbe": {"path": str(ROOT / "src/gguf_probe.py"), "sha256": sha(ROOT / "src/gguf_probe.py")},
            "screen": {"path": str(ROOT / "src/screen.py"), "sha256": sha(ROOT / "src/screen.py")},
        },
        "models": [model_entry(row) for row in passing],
        "baselineIfPresent": {
            "id": "qwen3-1.7b-instruct",
            "note": "Do not re-download if the HPC already has it. The local product file sha256 is "
                    "b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897 and equals "
                    "unsloth/Qwen3-1.7B-GGUF Qwen3-1.7B-Q4_K_M.gguf.",
            "lfsRepo": "unsloth/Qwen3-1.7B-GGUF",
            "lfsRevision": "d7f544eead698dbd1f15126ef60b45a1e1933222",
        },
        "tasks": [
            "create a unique output dir per model id under the lane-10 scratch/models area",
            "download each file from the pinned revision URL; if HF asks for auth, stop and report the exact HTTP status (do not silently substitute a mirror)",
            "sha256 the downloaded file and compare with lfsSha256; on mismatch rename it corrupt-<sha> and report",
            "run src/gguf_probe.py on each file and keep the JSON (architecture, quantisation, tensor types, chat-template sha256, vocab, context)",
            "start llama-server with the model, --jinja, -c 8192, -ngl as available, --no-webui; wait for /health and record load seconds",
            "send ONE neutral smoke prompt (below); record raw text, finish_reason, timings and wall ms; stop the server",
            "record nvidia-smi (GPU name/memory/utilization) and the llama.cpp version/commit; if CPU only, say so",
        ],
        "smokePrompt": {
            "system": "你是中文叙事作者。",
            "user": "用一句话描写傍晚的院子。只写一句话。",
            "sampling": {"temperature": 0.0, "top_k": 1, "top_p": 1.0, "seed": 42, "max_tokens": 64},
            "whyNeutral": "Load test only; deliberately unrelated to the dev package so the output cannot be mistaken for a quality sample.",
        },
        "outputs": {
            "perModel": [
                "downloaded file sha256 + bytes",
                "gguf-probe.json",
                "load seconds",
                "smoke output text + timings",
                "nvidia-smi / backend evidence",
                "llama-server.log tail",
            ],
            "summary": "one JSON per model plus one summary JSON under the lane-10 results area; tell 11 the paths",
        },
        "resourceEstimate": {
            "downloadBytes": sum(row["gguf"]["bytes"] for row in passing),
            "downloadBytesHuman": "~4.4 GB",
            "disk": "~4.5 GB scratch",
            "gpu": "1 GPU if available, otherwise CPU is acceptable for a load/smoke test; record which",
            "loadSecondsPerModel": "expect 30-180 s depending on backend; record actual",
            "smokeSecondsPerModel": "expect 5-60 s for 64 tokens; record actual",
            "totalWallExcludingQueue": "~15-30 min",
            "cost": "existing authorised cluster resources only; no new paid resource",
        },
        "hardConstraints": [
            "Do not run the 01 dev package in this request; the quality batch is a separate request.",
            "Do not compare or rank the smoke outputs; they are not quality evidence.",
            "Do not quantise or modify the downloaded files; the pinned sha256 is the identity.",
            "Do not run a >2 GB model: the browser Blob store cap is ~2 GB (team-08 evidence).",
            "If a model fails to load, keep the log and report it as a failed candidate; do not retry with a different quantisation inside this request.",
        ],
        "notRequested": [
            "browser runs (lane 09)",
            "quality judgement (lane 01)",
            "training or quantisation",
            "candidates beyond the listed four",
        ],
    }

    quality = {
        "requestId": "11-model-search-quality-001",
        "from": "11-model-search",
        "to": "10-training",
        "requestedAt": now(),
        "kind": "frozen-prompt-batch",
        "readyToSubmit": quality_ready,
        "submitCondition": "01 either fixes the three cases the reference serializer refuses, or "
                           "explicitly acknowledges the declared 12-case subset; 11 then re-pins the "
                           "preregistration, reruns build_prompts.py and flips readyToSubmit to true.",
        "blockedBy": quality_blocked,
        "preregistration": {
            "path": str(preregistration_path),
            "sha256": sha(preregistration_path),
            "status": "pinned" if preregistration_path.name == "preregistration.v1.json" else "draft",
        },
        "prompts": {
            "subset12": {"path": str(prompts_dir / "prompts.jsonl"), "sha256": sha(prompts_dir / "prompts.jsonl")},
            "manifest": {"path": str(prompts_dir / "prompts.manifest.json"), "sha256": sha(prompts_dir / "prompts.manifest.json")},
            "subsetDeclaration": {"path": str(ROOT / "subset-declaration.json"), "sha256": sha(ROOT / "subset-declaration.json")},
        },
        "models": [model_entry(row) for row in passing],
        "baselineArms": [
            {
                "id": "qwen3-1.7b-instruct",
                "path": "existing HPC copy if present; otherwise unsloth/Qwen3-1.7B-GGUF @ "
                        "d7f544eead698dbd1f15126ef60b45a1e1933222 / Qwen3-1.7B-Q4_K_M.gguf",
                "lfsSha256": "b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897",
            },
            {
                "id": "product-narr-qwen25-1.5b",
                "path": "local-only training artifact; do not upload unless 10 already has it. Reference arm, not the rubric baseline.",
                "lfsSha256": "6ed2268db2e1277933094c8b3af3348c18d6c0689244679a393c2008a1af5a0b",
            },
        ],
        "runner": {
            "command": "python -X utf8 src/screen.py --prompts <prompts.jsonl> --prompt-manifest <prompts.manifest.json> "
                       "--model-id <id> --model-path <file> --expect-sha256 <sha> --llama-server <llama-server> "
                       "--ngl <n> --out <run dir>",
            "backend": "llama-server --jinja (the model's own GGUF chat template)",
            "sampling": {"temperature": 0.0, "top_k": 1, "top_p": 1.0, "seed": 42,
                         "max_tokens": 320, "context": 8192},
            "perModelOneServer": True,
        },
        "resourceEstimate": {
            "calls": 12,
            "arms": 6,
            "callsTotal": 72,
            "perCall": "~320 max tokens; expect 5-60 s on GPU depending on model",
            "wall": "~10-40 min generation plus 6 loads; record actual tok/s",
            "gpu": 1,
            "cost": "existing authorised cluster resources only",
        },
        "deliverBack": [
            "per-case JSON from screen.py",
            "run-manifest.json per model (load time, server log, model sha)",
            "mechanical summary from src/collect.py (no quality decisions)",
        ],
        "hardConstraints": [
            "Run only after readyToSubmit=true and the preregistration pin matches the prompt manifest.",
            "Do not change sampling, max tokens, stop strings or prompts; any change is a new batch id.",
            "Do not skip a case; if a prompt file is missing or a call errors, report it.",
            "Do not judge quality; lane 01 reviews the raw texts.",
            "Keep all raw outputs, including failures and empty texts.",
        ],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    for name, obj in (("11-model-search-preflight-001.json", preflight),
                      ("11-model-search-quality-001.json", quality)):
        path = OUT / name
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(path)
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
