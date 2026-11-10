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
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = pathlib.Path("D:/others/Jity/.local/parallel-local-game/results/product/hpc-requests")
CANDIDATES = ROOT / "models/candidates.json"
DEV_PACKAGE = pathlib.Path("D:/others/Jity/.local/parallel-local-game/results/quality/dev-package-v1")


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
        "expectedArchitecture": candidate["operatorEvidence"].get("expectedArchitecture"),
        "architectureKnownToShippedWasm": candidate["operatorEvidence"].get("architectureKnownToShippedWasm"),
        "wllamaWasmSha256": candidate["operatorEvidence"]["wllamaWasmSha256"],
        "chatTemplateKwargs": candidate.get("chatTemplateKwargs") or {},
        "ggufEvidence": {
            "actualArchitecture": candidate["operatorEvidence"].get("expectedArchitecture"),
            "actualQuantization": candidate["operatorEvidence"].get("actualQuantization"),
            "chatTemplateSha256": candidate["operatorEvidence"].get("chatTemplateSha256"),
            "textOnlyGguf": candidate["operatorEvidence"].get("textOnlyGguf"),
            "source": candidate["operatorEvidence"].get("source"),
        },
        "note": "GGUF architecture/quant/template come from a bounded HTTP range read of the "
                "pinned file (models/remote-heads/); the real load proof is still this preflight "
                "and lane 09.",
    }


def main() -> int:
    registry = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    passing = [row for row in registry["candidates"] if row["preInferenceGate"]["passed"]]
    prompts_dir = ROOT / "evidence/prompts-dev-v2-full15"
    prompt_manifest = json.loads((prompts_dir / "prompts.manifest.json").read_text(encoding="utf-8"))
    prompt_count = int(prompt_manifest.get("promptCount") or 0)
    arm_count = len(passing) + 2
    pinned_preregistration = ROOT / "preregistration.v3.json"
    if not pinned_preregistration.exists():
        pinned_preregistration = ROOT / "preregistration.v1.json"
    pinned_status = None
    if pinned_preregistration.exists():
        try:
            pinned_status = json.loads(pinned_preregistration.read_text(encoding="utf-8")).get("status")
        except ValueError:
            pinned_status = None
    quality_ready = bool(pinned_status and pinned_status.startswith("pinned"))
    pinned_doc = json.loads(pinned_preregistration.read_text(encoding="utf-8")) if pinned_preregistration.exists() else {}
    batch_id = pinned_doc.get("batchId") or "batch-3-full15"
    quality_blocked = (
        "None: 01 published dev-package-v1.1 with all 15 cases serializable; this is the full "
        "15-case batch. Lane 11 still does not score; 01 owns RUBRIC review."
        if quality_ready else
        "No pinned preregistration: run finalize/pin before submitting."
    )
    preregistration_path = pinned_preregistration if pinned_preregistration.exists() else ROOT / "preregistration.draft.json"

    preflight = {
        "requestId": "11-model-search-preflight-001",
        "from": "11-model-search",
        "to": "10-training",
        "requestedAt": now(),
        "kind": "model-preflight",
        "readyToSubmit": True,
        "qualityBatch": False,
        "priority": "parallel-safe offline preflight; no dev-package generation and no GPU required, "
                    "so it can run alongside the product blockers without delaying them",
        "parallelSafe": True,
        "gpuOptional": True,
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
        "environmentPlan": {
            "existingBuild": "first check for an existing llama-server (and llama-gguf) on the cluster; "
                             "record its version/commit and use it if it loads the models",
            "ifMissing": "build ggml-org/llama.cpp from source with cmake: "
                         "git clone https://github.com/ggml-org/llama.cpp && cmake -B build "
                         "-DGGML_CUDA=ON -DLLAMA_CURL=ON && cmake --build build -j --target "
                         "llama-server llama-quantize. CPU-only (no -DGGML_CUDA) is enough for the "
                         "preflight; record the exact commit and the llama.cpp version banner.",
            "whyNotTransformers": "the offline batch must apply the GGUF's own chat template through "
                                  "llama-server --jinja; a transformers run would be a different "
                                  "template path and is not comparable to the browser run",
        },
        "resourceEstimate": {
            "downloadBytes": sum(row["gguf"]["bytes"] for row in passing),
            "downloadBytesHuman": "~5.7 GB",
            "disk": "~5.8 GB scratch",
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
            "candidates beyond the listed passing set",
        ],
    }

    quality = {
        "requestId": "11-model-search-quality-001",
        "from": "11-model-search",
        "to": "10-training",
        "requestedAt": now(),
        "kind": "frozen-prompt-batch",
        "priority": "below current product blockers; 105 short calls with one load per arm, "
                    "no training, can share a GPU window",
        "batchId": batch_id,
        "subsetOnly": False,
        "qualityGateClaim": "full 15-case RUBRIC gate is available; lane 11 will not score it and 01 owns the review",
        "readyToSubmit": quality_ready,
        "submitCondition": "Ready for all 15 cases: 01's v1.1 package serializes 15/15 and the frozen "
                           "prompts are rebuilt from it. Do not mix any old 12-case output into this batch.",
        "blockedBy": quality_blocked,
        "preregistration": {
            "path": str(preregistration_path),
            "sha256": sha(preregistration_path),
            "status": pinned_status or "draft",
        },
        "prompts": {
            "full15": {"path": str(prompts_dir / "prompts.jsonl"), "sha256": sha(prompts_dir / "prompts.jsonl"), "promptCount": prompt_count},
            "manifest": {"path": str(prompts_dir / "prompts.manifest.json"), "sha256": sha(prompts_dir / "prompts.manifest.json")},

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
            "templateKwargs": "pass each model's chatTemplateKwargs (Hunyuan and Qwen3.5: enable_thinking=false; Qwen3 baseline: enable_thinking=false)",
            "sampling": {"temperature": 0.0, "top_k": 1, "top_p": 1.0, "seed": 42,
                         "max_tokens": 320, "context": 8192},
            "perModelOneServer": True,
            "cpuFallback": "if no GPU is free, CPU with -t <cores> is acceptable for the batch; record "
                           "the actual tok/s so the browser-latency decision is not based on GPU numbers alone",
            "templateKwargsFallback": "llama-server must accept per-request chat_template_kwargs "
                                      "(Hunyuan and Qwen3.5 need enable_thinking=false). If this build "
                                      "does not, stop and report the version; do not run either model "
                                      "with thinking on.",
        },
        "resourceEstimate": {
            "calls": prompt_count,
            "arms": arm_count,
            "callsTotal": prompt_count * arm_count,
            "perCall": "~320 max tokens; expect 5-60 s on GPU depending on model",
            "wall": "~10-50 min generation plus one load per arm; record actual tok/s",
            "gpu": 1,
            "cost": "existing authorised cluster resources only",
        },
        "runRecipe": [
            "create <scratch>/11-model-search/models/ and download every models[] entry there; "
            "verify byte size and sha256 before loading",
            "upload experiments/narration-model-search/ and 01's shared package; run "
            "src/verify_preflight.py --model-id <id> --path <file> --smoke-json <saved response> for each candidate",
            "for each candidate, run one llama-server and 15 cases: python -X utf8 src/screen.py "
            "--prompts <upload>/evidence/prompts-dev-v2-full15/prompts.jsonl --prompt-manifest "
            "<upload>/evidence/prompts-dev-v2-full15/prompts.manifest.json --model-id <id> "
            "--model-path <file> --expect-sha256 <sha> --llama-server <build>/llama-server --ngl 99 "
            "--out <out>/<id>",
            "run the qwen3-1.7b-instruct baseline the same way (existing HPC copy if present); "
            "run product-narr-qwen25-1.5b only if 10 already has it, otherwise record it as skipped",
            "python -X utf8 src/collect.py --run <out>/<candidate> ... --out-dir <out>/summary",
            "fetch every <out>/<arm>/*.json, run-manifest.json, llama-server.log, and summary/",
        ],
        "outputLayout": "<out>/<modelId>/<caseId>.json plus run-manifest.json and llama-server.log; <out>/summary/{summary.json,summary.md}",
        "deliverBack": [
            "per-case JSON from screen.py",
            "run-manifest.json per model (load time, server log, model sha)",
            "mechanical summary from src/collect.py (no quality decisions)",
        ],
        "hardConstraints": [
            "Run only after readyToSubmit=true and the preregistration pin matches the prompt manifest.",
            "This is the full 15-case batch on 01's v1.1 package. Keep every output; do not merge "
            "any old 12-case output into this batch.",
            "Do not change sampling, max tokens, stop strings or prompts; any change is a new batch id.",
            "Do not skip a case; if a prompt file is missing or a call errors, report it.",
            "Do not judge quality; lane 01 reviews the raw texts.",
            "Keep all raw outputs, including failures and empty texts.",
            "Record the exact llama.cpp version/commit. Template rendering differences from the "
            "browser's wllama build are a known limitation; lane 09's browser run is authoritative.",
        ],
    }

    # 10's queue policy lists required fields. Keep the rich request bodies and
    # add the same facts in that flat envelope so the request cannot be refused
    # for a missing hash or an unnamed output directory.
    code_hashes = {name: sha(ROOT / "src" / name) for name in
                   ("screen.py", "collect.py", "make_review_input.py", "build_prompts.py",
                    "semantic_validate.py", "prepare_semantic_prompts.py")}
    data_hashes = {
        "manifest.json": sha(DEV_PACKAGE / "manifest.json"),
        "cases.jsonl": sha(DEV_PACKAGE / "cases.jsonl"),
        "prompts.jsonl": sha(prompts_dir / "prompts.jsonl"),
        "prompts.manifest.json": sha(prompts_dir / "prompts.manifest.json"),
    }
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    script_paths = ("screen.py", "collect.py", "make_review_input.py",
                    "verify_preflight.py", "build_prompts.py", "semantic_validate.py",
                    "prepare_semantic_prompts.py")
    scripts = [{"path": f"experiments/narration-model-search/src/{name}",
                "sha256": sha(ROOT / "src" / name)} for name in script_paths]
    shared_package = {
        "path": "results/quality/dev-package-v1/",
        "manifestSha256": data_hashes["manifest.json"],
        "casesSha256": data_hashes["cases.jsonl"],
        "rubricSha256": sha(DEV_PACKAGE / "RUBRIC.md"),
    }
    model_source = [{
        "id": row["id"],
        "repo": row["gguf"]["repo"],
        "revision": row["gguf"]["revision"],
        "file": row["gguf"]["file"],
        "bytes": row["gguf"]["bytes"],
        "sha256": row["gguf"]["lfsSha256"],
        "license": row["license"]["spdx"],
    } for row in passing]
    for request, output_dir, purpose, questions in (
        (preflight, "results/product/hpc-results/11-model-search-preflight-001/",
         "Download, hash, read GGUF metadata and smoke-load five candidate GGUFs. No dev-package generation, no quality judgement.",
         ["Is llama-server present or buildable on the cluster, and which llama.cpp commit results?",
          "Does each GGUF load, and does Qwen3.5-2B load through the text-only qwen35 path?",
          "Does the server accept per-request chat_template_kwargs (Hunyuan/Qwen3.5 need enable_thinking=false)?"]),
        (quality, "results/product/hpc-results/11-model-search-batch-3-full15/",
         "Offline full 15-case comparison of five candidate GGUFs against the Qwen3-1.7B baseline (and the product LoRA if present).",
         ["Is the product LoRA GGUF available to 10? If not, skip that reference arm and say so.",
          "Did every arm use its own GGUF template through llama-server --jinja, with the pinned sampling?",
          "Which cases failed to load or produced an empty/truncated response?"]),
    ):
        request["lane"] = "11-model-search"
        request["id"] = request["requestId"]
        request["purpose"] = purpose
        request["preregistrationPath"] = str(pinned_preregistration)
        request["preregistrationSha256"] = sha(pinned_preregistration)
        request["inputOrDataSha256"] = data_hashes
        request["rubricSha256"] = sha(DEV_PACKAGE / "RUBRIC.md")
        request["codeSha256"] = code_hashes
        request["modelSource"] = model_source
        request["estimatedResources"] = request.get("resourceEstimate")
        request["outputDir"] = output_dir
        request["openQuestions"] = questions
        request["branch"] = "goal/local-11-model-search"
        request["worktree"] = "worktrees/11-model-search"
        request["commit"] = commit
        request["candidateRegistry"] = {
            "path": "experiments/narration-model-search/models/candidates.json",
            "sha256": sha(CANDIDATES),
        }
        request["scriptsToUpload"] = scripts
        request["sharedPackage"] = shared_package

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
