# -*- coding: utf-8 -*-
"""Write the 11-model-search semantic-probe HPC request.

Separate from the prose-quality batch: two 73-task cases, 0.6B + five
candidates, structural+expected scoring. Lane 10 remains the only submitter.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = pathlib.Path("D:/others/Jity/.local/parallel-local-game/results/product/hpc-requests")
CANDIDATES = ROOT / "models/candidates.json"
CASES = ROOT / "evidence/semantic-cases"
PREREG = ROOT / "semantic-probes/preregistration.v2.json"
RELEASE = ROOT / "semantic-probes/tasks-73-release.pack.jsonl"
PROMPTS = ROOT / "evidence/semantic-prompts-v2/prompts.jsonl"
PROMPT_MANIFEST = ROOT / "evidence/semantic-prompts-v2/prompts.manifest.json"
SCHEMA = ROOT / "semantic-probes/schemas/tasks.schema.json"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def commit() -> str:
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                       text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def main() -> int:
    registry = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    passing = [row for row in registry["candidates"] if row["preInferenceGate"]["passed"]]
    models = [{
        "id": "qwen3-0.6b", "role": "page-semantic-baseline", "source": "product-page-blob",
        "file": "Qwen3-0.6B-Q4_K_M.gguf", "bytes": 396705472,
        "sha256": "ac2d97712095a558e31573f62f466a3f9d93990898b0ec79d7c974c1780d524a",
        "localPath": "D:/others/Jity/.local/world-narration-worktree/frontend/public/models/Qwen3-0.6B-Q4_K_M.gguf",
        "architecture": "qwen3", "license": "apache-2.0",
        "chatTemplateKwargs": {"enable_thinking": False},
    }]
    for row in passing:
        gguf = row["gguf"]
        models.append({
            "id": row["id"], "role": "candidate-narration-model-semantic-probe",
            "repo": gguf["repo"], "publisher": gguf.get("publisher"),
            "revision": gguf["revision"], "file": gguf["file"],
            "bytes": gguf["bytes"], "sha256": gguf["lfsSha256"],
            "architecture": row.get("operatorEvidence", {}).get("expectedArchitecture"),
            "license": (row.get("license") or {}).get("spdx"),
            "chatTemplateKwargs": row.get("chatTemplateKwargs") or {},
        })
    code = {name: sha(ROOT / "src" / name) for name in
            ("screen.py", "semantic_validate.py", "prepare_semantic_prompts.py",
             "collect.py", "verify_preflight.py", "build_semantic_case_from_state.py")}
    request = {
        "lane": "11-model-search",
        "requestId": "11-model-search-semantic-001",
        "id": "11-model-search-semantic-001",
        "from": "11-model-search",
        "to": "10-training",
        "kind": "structured-semantic-probe",
        "batchId": "semantic-73-two-cases-1",
        "priority": "small exploratory probe (12 calls, 6 model loads); below product blockers "
                    "and can reuse the preflight downloads; no training",
        "requestedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "purpose": "Run 04's corrected per-character task prompt on the page's Qwen3-0.6B and the "
                   "five narration candidates over two 14-character/73-task cases. Check full "
                   "coverage, actual task marking, and whether copying the all-empty skeleton passes "
                   "the positive case. This is not a prose-quality or product gate.",
        "preregistrationPath": str(PREREG),
        "preregistrationSha256": sha(PREREG),
        "contractCommit": "117befcfa068fd340c1f1e581eccdab1feed8762",
        "frozenPromptPack": {"manifest": str(PROMPT_MANIFEST), "manifestSha256": sha(PROMPT_MANIFEST),
                             "prompts": str(PROMPTS), "promptsSha256": sha(PROMPTS),
                             "promptCount": 2, "frozen": True},
        "inputOrDataSha256": {
            "releasePack": sha(RELEASE), "prompts": sha(PROMPTS),
            "promptsManifest": sha(PROMPT_MANIFEST),
            "noChangeCase": sha(CASES / "tasks-free-day-real-73-no-change.json"),
            "oneAchievedCase": sha(CASES / "tasks-free-day-real-73-one-achieved.json"),
            "jsonSchema": sha(SCHEMA),
            "sourceState": "33010db02d5ff6488dece53c8b04cc63287379cb27da56de9ef03e54cd071aa9",
        },
        "rubricPath": str(PREREG), "rubricSha256": sha(PREREG),
        "rubricKind": "semantic-expected: two cases, expected decisions frozen in the prereg/pack; no prose RUBRIC",
        "codeSha256": code,
        "modelSource": models,
        "estimatedResources": {"calls": 12, "models": len(models), "callsTotal": 12,
                               "loads": len(models),
                               "perCall": "520 max tokens; prompt ~3.4-4.4k tokens estimated; expect "
                                          "10-120 s on GPU depending on model",
                               "wall": "~15-45 min including six loads; one GPU; no training",
                               "gpu": 1,
                               "cost": "existing authorised cluster resources only; no paid capacity"},
        "outputDir": "results/product/hpc-results/11-model-search-semantic-001/",
        "runRecipe": [
            "use the preflight model files; for qwen3-0.6b upload/use the product blob with sha256 "
            "ac2d9771...; do not download a second copy",
            "for each model: llama-server --jinja with its own GGUF, then python -X utf8 src/screen.py "
            "--prompts <upload>/evidence/semantic-prompts-v2/prompts.jsonl --prompt-manifest "
            "<upload>/evidence/semantic-prompts-v2/prompts.manifest.json --json-schema "
            "<upload>/semantic-probes/schemas/tasks.schema.json --model-id <id> --model-path <file> "
            "--expect-sha256 <sha> --llama-server <build>/llama-server --ngl 99 "
            "--template-kwargs '{\"enable_thinking\":false}' --out <out>/<id>",
            "screen.py omits the system message when system is empty, matching 04's page call; "
            "the schema makes response_format json_schema strict like 04's callJson",
            "for each model: python -X utf8 src/semantic_validate.py --pack "
            "<upload>/semantic-probes/tasks-73-release.pack.jsonl --run-dir <out>/<id> "
            "--out <out>/<id>/semantic-report.json --expected",
            "fetch every per-case JSON, run-manifest.json, llama-server.log and semantic-report.json; "
            "preserve empty/error responses",
        ],
        "outputLayout": "<out>/<id>/<caseId>.json + run-manifest.json + llama-server.log + semantic-report.json",
        "openQuestions": [
            "With 04's copyable skeleton, does Qwen3-0.6B now answer all 14 characters?",
            "Does it mark task_lu_goggles in the positive case, or copy the all-empty skeleton?",
            "Do any of the five candidates cover 14/14 and make the task decision without inventing "
            "other achievements?",
            "Is the 0.6B still the limiting component, or was the 1/14/12-of-73 failure primarily "
            "prompt organization?",
        ],
        "deliverBack": ["raw per-case outputs, semantic reports, model template/kwargs, load and "
                        "generation timings; no quality claim"],
        "notAQualityGate": True,
        "qualityGateClaim": "none: semantic capability probe, not the narration RUBRIC gate",
        "expectedConfirmation": "the no-change expected is mechanically derived from a move-only "
                                "result; the positive expected is lane-11's constructed result. "
                                "Results are exploratory until 03/04 confirm.",
        "sharedPackage": "not used for this probe; 01's narration dev package remains unused here",
        "branch": "goal/local-11-model-search", "worktree": "worktrees/11-model-search",
        "commit": commit(),
        "scriptsToUpload": ["experiments/narration-model-search/src/screen.py",
                            "experiments/narration-model-search/src/semantic_validate.py",
                            "experiments/narration-model-search/evidence/semantic-prompts-v2/",
                            "experiments/narration-model-search/semantic-probes/tasks-73-release.pack.jsonl",
                            "experiments/narration-model-search/semantic-probes/schemas/tasks.schema.json"],
        "readyToSubmit": True,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "11-model-search-semantic-001.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(request, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

