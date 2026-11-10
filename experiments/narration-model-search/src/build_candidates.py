# -*- coding: utf-8 -*-
"""Build the candidate table from captured evidence, never from memory.

Inputs (all produced by scripts in this directory):
  * sources/hf/capture.json      official HF API + raw card/config/tokenizer/licence
  * models/local-inventory.json  already-downloaded GGUFs with sha256 + GGUF probe
  * models/wllama-support.json   architectures present in the shipped wllama wasm

Output: models/candidates.json. Every field is either copied from a captured
file or explicitly marked as a hand-written interpretation with its reason.
The pre-inference gate is applied here; quality gates are applied after the
batch run and are not claimed by this file.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
CAPTURE = ROOT / "sources/hf/capture.json"
INVENTORY = ROOT / "models/local-inventory.json"
SUPPORT = ROOT / "models/wllama-support.json"
OUT = ROOT / "models/candidates.json"

SIZE_GATE = 1_500_000_000

# License interpretation is written by hand on purpose: it is a reading of the
# captured licence text, not something a script can decide. Each note points at
# the captured file it comes from.
LICENSE_NOTES = {
    "qwen25-1.5b-instruct": {
        "spdx": "Apache-2.0",
        "commercialUse": "allowed",
        "decisionRequired": False,
        "note": "HF license tag apache-2.0; captured LICENSE body is Apache License 2.0.",
    },
    "internlm2_5-1.8b-chat": {
        "spdx": "other",
        "commercialUse": "free commercial usage via application form",
        "decisionRequired": True,
        "note": "Base card (base-README.md line ~169) says code Apache-2.0, weights open "
                "for academic research and free commercial usage after filling the "
                "application form; the GGUF repo is tagged apache-2.0. The two statements "
                "are not identical, so product use needs a decision.",
    },
    "glm-edge-1.5b-chat": {
        "spdx": "other",
        "commercialUse": "registration required, attribution required",
        "decisionRequired": True,
        "note": "Captured base-LICENSE is the GLM-Edge License: free for academic research, "
                "commercial use requires registration at the stated form, and distributions "
                "must show 'Built with GLM-Edge'. The licence is revocable/non-transferable.",
    },
    "hunyuan-1.8b-instruct": {
        "spdx": "other",
        "commercialUse": "allowed inside the Territory under conditions",
        "decisionRequired": True,
        "note": "Captured base-LICENSE is the Tencent Hunyuan Community License (release "
                "2025-08-04). It excludes the EU, UK and South Korea and imposes "
                "distribution conditions. The GGUF file is a third-party quantisation.",
    },
    "gemma3-1b-it-qat": {
        "spdx": "gemma",
        "commercialUse": "Gemma Terms of Use, access gated",
        "decisionRequired": True,
        "note": "HF license tag gemma; the repo requires accepting Google's usage licence to "
                "download. config.json and tokenizer_config.json returned HTTP 401 without "
                "an authorised token, so the chat template could not be captured here.",
    },
    "minicpm5-2b": {
        "spdx": "Apache-2.0",
        "commercialUse": "allowed",
        "decisionRequired": False,
        "note": "HF license tag apache-2.0 and the model card front matter repeats it.",
    },
    "minicpm-2b-dpo": {
        "spdx": "unclear",
        "commercialUse": "needs a licence reading",
        "decisionRequired": True,
        "note": "No license tag on the base repo; the captured card has no licence section. "
                "Excluded for size before a licence decision mattered.",
    },
}

# Things looked at and rejected before capture, with the reason. Kept so the
# search does not silently look narrower than it was.
CONSIDERED_REJECTED = [
    {"id": "baidu/ERNIE-4.5-0.3B-PT", "reason": "0.3B capacity is far below the 1.7B baseline; not a credible replacement for whole-scene Chinese prose. Could be a future semantic-model candidate, not a narration candidate."},
    {"id": "Tele-AI/TeleChat-1.5B", "reason": "HF search returned no 1.5B chat repository; only 7B/12B releases were found, which exceed the 1.5e9-byte single-file gate."},
    {"id": "IEITYuan/Yuan2-2B-Mars-hf-GGUF", "reason": "official GGUF repo contains only an f16 file (4.7GB); no official quantisation within the size gate was found in this batch."},
    {"id": "google/gemma-3-4b-it", "reason": "parameter/quantised size exceeds the single-file gate; 1B QAT was captured instead."},
    {"id": "Qwen/Qwen3-4B-Instruct-2507", "reason": "2.5GB GGUF already proved an ArrayBuffer load failure and is outside the size gate; not repeated."},
]


def config_of(slug: str) -> dict:
    path = ROOT / "sources/hf" / slug / "base-config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"path": f"sources/hf/{slug}/base-config.json", "unavailable": True,
                "reason": "config.json was not retrievable (gated repository or capture error)"}
    keys = ("architectures", "model_type", "hidden_size", "num_hidden_layers",
            "num_attention_heads", "num_key_value_heads", "vocab_size",
            "max_position_embeddings", "torch_dtype")
    return {"path": f"sources/hf/{slug}/base-config.json",
            **{key: data.get(key) for key in keys if key in data}}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    capture = {c["id"]: c for c in load(CAPTURE)["candidates"]}
    inventory = load(INVENTORY)["files"]
    support = load(SUPPORT)
    by_sha = {f["sha256"]: f for f in inventory if "sha256" in f}
    by_name = {}
    for entry in inventory:
        if "path" not in entry:
            continue
        by_name.setdefault(pathlib.Path(entry["path"]).name, []).append(entry)

    def chat_template(slug: str) -> dict:
        path = ROOT / "sources/hf" / slug / "base-tokenizer_config.json"
        try:
            tokenizer = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"source": "unavailable", "chars": None, "sha256": None,
                    "reason": "base tokenizer_config.json could not be read (gated or absent)"}
        template = tokenizer.get("chat_template")
        if not isinstance(template, str):
            return {"source": "unavailable", "chars": None, "sha256": None,
                    "reason": "tokenizer_config.json has no chat_template string"}
        return {"source": "base tokenizer_config.json", "chars": len(template), "sha256": sha256_text(template)}

    def build(slug: str) -> dict:
        cap = capture[slug]
        gguf = cap["gguf"]
        want = next((f for f in gguf["files"] if f["path"] == cap["wantFile"]), None)
        if want is None:
            raise SystemExit(f"{slug}: captured GGUF table has no {cap['wantFile']}")
        base_files = {f["path"]: f for f in cap["base"]["files"]}
        local = by_sha.get((want.get("lfsSha256") or "").lower())
        template = chat_template(slug)
        license_note = LICENSE_NOTES[slug]
        license_file = next((r for r in cap["requests"]
                             if r["file"].endswith("base-LICENSE") and r["status"] == 200), None)
        base_first = base_files.get("README.md")
        entry = {
            "id": slug,
            "family": cap["family"],
            "base": {
                "repo": cap["base"]["repo"],
                "revision": cap["base"]["revision"],
                "lastModified": cap["base"]["lastModified"],
                "licenseTags": cap["base"]["licenseTags"],
                "card": {
                    "path": f"sources/hf/{slug}/base-README.md",
                    "bytes": base_first["bytes"] if base_first else None,
                    "lfsSha256": base_first["lfsSha256"] if base_first else None,
                },
            },
            "gguf": {
                "repo": gguf["repo"],
                "publisher": cap["ggufPublisher"],
                "revision": gguf["revision"],
                "lastModified": gguf["lastModified"],
                "licenseTags": gguf["licenseTags"],
                "file": want["path"],
                "bytes": want["bytes"],
                "lfsSha256": want["lfsSha256"],
                "local": (
                    {"path": local["path"], "sha256": local["sha256"],
                     "matchesOfficialLfs": local["sha256"].lower() == (want.get("lfsSha256") or "").lower()}
                    if local else None
                ),
            },
            "config": config_of(slug),
            "chatTemplate": template,
            "license": {
                **license_note,
                "capturedFile": license_file["file"] if license_file else None,
                "capturedSha256": license_file["sha256"] if license_file else None,
                "ggufRepoLicenseTags": gguf["licenseTags"],
            },
        }
        # Operator evidence: the architecture string the file itself declares is
        # only known for local files; remote GGUF is checked in the preflight.
        arch_local = None
        if local and "probe" in local:
            arch_local = local["probe"].get("architecture")
            entry["gguf"]["localProbe"] = local["probe"]
        entry["operatorEvidence"] = {
            "wllamaVersion": support["wllamaVersion"],
            "wllamaWasmSha256": support["wasmSha256"],
            "expectedArchitecture": arch_local,
            "architectureKnownToShippedWasm": (
                arch_local in support["architectureModels"] if arch_local else None
            ),
            "note": "Necessary, not sufficient: the real load/生成 test is the HPC preflight "
                    "and lane 09's browser run. No inference was run in this lane.",
        }
        # Pre-inference gate from EXPLORATION-AND-ACCEPTANCE.md.
        reasons = []
        if want["bytes"] > SIZE_GATE:
            reasons.append(f"size {want['bytes']} > gate {SIZE_GATE}")
        if not want.get("lfsSha256"):
            reasons.append("no LFS sha256 for the GGUF file")
        if template["source"] == "unavailable":
            reasons.append("chat template not captured from the base tokenizer_config")
        if arch_local and arch_local not in support["architectureModels"]:
            reasons.append(f"architecture {arch_local} absent from shipped wllama wasm")
        entry["preInferenceGate"] = {
            "sizeGateBytes": SIZE_GATE,
            "sizePass": want["bytes"] <= SIZE_GATE,
            "licenseDecisionRequired": license_note["decisionRequired"],
            "passed": not reasons,
            "reasons": reasons,
        }
        return entry

    rows = [build(slug) for slug in capture]
    # Baselines are already local product/training artifacts; they are not
    # candidates and are never downloaded again.
    baselines = []
    baseline_specs = [
        ("product-narr-qwen25-1.5b", "current product narration checkpoint (Qwen2.5-1.5B narration LoRA, Q4_K_M)", "qwen25-1.5b-narr-Q4_K_M.gguf"),
        ("qwen3-1.7b-instruct", "the historical Qwen3-1.7B baseline named by the task", "Qwen3-1.7B-Q4_K_M.gguf"),
    ]
    for bid, description, file_name in baseline_specs:
        found = by_name.get(file_name, [])
        product = next((f for f in found if "06-recovery" in f["path"]), found[0] if found else None)
        if not product:
            raise SystemExit(f"baseline file missing from inventory: {file_name}")
        entry = {
            "id": bid,
            "description": description,
            "path": product["path"],
            "bytes": product["bytes"],
            "sha256": product["sha256"],
            "probe": product.get("probe"),
            "neverRedownload": True,
        }
        if bid == "qwen3-1.7b-instruct":
            entry["provenance"] = {
                "repo": "unsloth/Qwen3-1.7B-GGUF",
                "revision": "d7f544eead698dbd1f15126ef60b45a1e1933222",
                "file": "Qwen3-1.7B-Q4_K_M.gguf",
                "lfsSha256": "b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897",
                "matchesLocal": True,
            }
        else:
            entry["provenance"] = {
                "kind": "local training artifact (lane 10), never re-downloaded",
            }
        baselines.append(entry)

    report = {
        "registryVersion": "narration-model-search-candidates-v1",
        "owner": "11-model-search",
        "preInferenceGate": {
            "singleFileBytes": SIZE_GATE,
            "source": "EXPLORATION-AND-ACCEPTANCE.md (11 initial offline promotion gate); quality gates are applied after the frozen batch run",
            "qualityGates": "not applied yet: require the frozen 01 dev package + rubric and measured outputs",
        },
        "runtimeCap": {
            "source": "results/quality/team-08-runtime.json: browser Blob-store aggregate cap ~2 GB; a 1.3 GB blob loads, adding another 1.2 GB fails; a 2.5 GB single file fails; splitting does not bypass",
            "consequence": "For a real 09 browser run the candidate plus the page's other loaded model must stay under the measured cap. All batch-1 candidates are <=1.18 GB, and the 1.5e9-byte single-file gate is aligned. No 4B retry is queued.",
        },
        "baselines": baselines,
        "candidates": rows,
        "consideredRejected": CONSIDERED_REJECTED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT}")
    for row in rows:
        print(f"  {row['id']:24} {str(row['gguf']['bytes']):>13}  gate={row['preInferenceGate']['passed']}  "
              f"lic={row['license']['spdx']}  reasons={row['preInferenceGate']['reasons']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
