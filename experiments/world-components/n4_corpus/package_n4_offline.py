# N4 offline package manifest (joint decision D3).
#
# Produces the archive B can retrieve and verify: checkpoint/base/corpus/
# renderer/judge hashes, decode and tokenizer pins, torch/cuda/cudnn/GPU
# versions, determinism flags, the frozen holdout archive hash, retrieval
# instructions and the reproducibility acceptance rule.
#
# The weights are NOT in git. B either copies the checkpoint directory from
# the coordinator/CI or rebuilds it with train_n4_sentence.py under a NEW
# run tag, then checks the hashes below. If a rebuild is bitwise identical,
# compare hashes; if not, re-running the frozen holdout is the acceptance
# (bitwise equality is not required).
#
# Usage: python experiments/world-components/n4_corpus/package_n4_offline.py
# Output: artifacts/world-components/n4-offline-package-r3-direction.json

import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

import torch

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
ASSETS = HERE.parent / "assets"
BASE = ASSETS / "randeng-t5-77m"
CKPT = ASSETS / "n4-finetune" / "r3-direction"
HOLDOUT = HERE.parent / "n4_holdout" / "holdout.jsonl"
FREEZE = HERE.parent / "n4_holdout" / "freeze-r3-direction.json"
HOLDOUT_ARCHIVE = REPO / "artifacts" / "world-components" / "n4-holdout-eval-r3-direction.json"
FREEZE_VERIFY = REPO / "artifacts" / "world-components" / "n4-holdout-freeze-verify-r3-direction.json"
OUT = REPO / "artifacts" / "world-components" / "n4-offline-package-r3-direction.json"

sys.path.insert(0, str(HERE))
from n4_render import corpus_hashes  # noqa: E402

# Pinned in n4-integration-package.md §3; a mismatch voids the package.
CKPT_PINS = {
    "model.safetensors": "baceebff5d33eacf",
    "config.json": "a35e9d4382657106",
    "generation_config.json": "691648bea8d35875",
    "special_tokens_map.json": "65d84a9271d68f12",
    "tokenizer_config.json": "553da19a6ed43c57",
    "spiece.model": "c65feffa65ff0378",
    "added_tokens.json": "a247922ac010bc17",
}
BASE_PINS = {
    "config.json": "9b2480c0a39fd09b",
    "model.safetensors": "5cdc572109cf2591",
    "special_tokens_map.json": "09059cedc26bc46b",
    "spiece.model": "c65feffa65ff0378",
    "tokenizer_config.json": "af072c7d91576727",
}
DECODE = {"greedy": True, "maxNewTokens": 64, "numBeams": 1,
          "tokenizerLegacy": False}


def sha_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_hashes(path: pathlib.Path) -> dict:
    return {f.name: sha_file(f)[:16] for f in sorted(path.iterdir()) if f.is_file()}


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                       text=True).strip()
    except Exception:
        return "unknown"


def driver_version() -> str:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            text=True, timeout=10)
        return out.strip().splitlines()[0]
    except Exception:
        return "unavailable"


def main() -> None:
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    ckpt = dir_hashes(CKPT)
    base = dir_hashes(BASE)
    problems = [f"checkpoint {k}: {ckpt.get(k)} != {v}"
                for k, v in CKPT_PINS.items() if ckpt.get(k) != v]
    problems += [f"base {k}: {base.get(k)} != {v}"
                 for k, v in BASE_PINS.items() if base.get(k) != v]
    if problems:
        for p in problems:
            print("PINNED HASH MISMATCH:", p)
        sys.exit(2)

    corpus = corpus_hashes()
    package = {
        "purpose": "N4 offline package (r3-direction) for B-side retrieval and verification; offline Python only",
        "status": "offline package, browser integration NOT started (D3)",
        "checkpoint": {"dir": str(CKPT), "filesSha256_16": ckpt,
                       "pinned": CKPT_PINS},
        "baseModel": {"dir": str(BASE), "filesSha256_16": base,
                      "hfId": "IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese",
                      "pinned": BASE_PINS},
        "corpus": {"renderer": corpus.get("n4_render.py"),
                   "judge": corpus.get("corpus_check.py"),
                   "seeds": corpus.get("corpus.seeds.jsonl"),
                   "rewrites": corpus.get("rewrites.jsonl"),
                   "all": corpus},
        "decode": dict(DECODE),
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "transformers": __import__("transformers").__version__,
            "cuda": torch.version.cuda,
            "cudnn": torch.backends.cudnn.version(),
            "deviceName": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "deviceCapability": (list(torch.cuda.get_device_capability(0))
                                 if torch.cuda.is_available() else None),
            "driver": driver_version(),
            "determinism": {
                "cudnnDeterministic": bool(torch.backends.cudnn.deterministic),
                "cudnnBenchmark": bool(torch.backends.cudnn.benchmark),
                "torchManualSeed": 0,
            },
        },
        "acceptance": {
            "offlineHoldoutArchive": {"file": str(HOLDOUT_ARCHIVE.relative_to(REPO)),
                                      "sha256": sha_file(HOLDOUT_ARCHIVE)},
            "freezeVerifyArchive": {"file": str(FREEZE_VERIFY.relative_to(REPO)),
                                    "sha256": sha_file(FREEZE_VERIFY)},
            "freezeManifest": {"file": str(FREEZE), "sha256": sha_file(FREEZE)},
            "holdout": {"file": str(HOLDOUT), "sha256": sha_file(HOLDOUT)},
            "rule": ("If a B-side re-run is bitwise identical, compare output "
                     "hashes. If not, re-running the frozen holdout is the "
                     "acceptance; bitwise equality is NOT required (D3)."),
            "label": "offline Python",
        },
        "retrieval": {
            "weightsInGit": False,
            "copy": "copy the n4-finetune/r3-direction directory from the coordinator/CI",
            "rebuild": ("python experiments/world-components/n4_corpus/train_n4_sentence.py "
                        "--tier large --run-tag <new-tag>  (never reuse r3-direction; "
                        "360 steps, batch 8, lr 1e-4, seed 20261029)"),
            "verify": ("python experiments/world-components/n4_corpus/package_n4_offline.py "
                       "against the copied/ rebuilt directory (edit CKPT first)"),
        },
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "generatedFromCommit": git_commit(),
        "disclaimers": [
            "offline Python only; no browser runtime, no JS sentencepiece, no page wiring",
            "the 297MB checkpoint is not committed; this manifest is the retrievable artifact",
            "the frozen holdout was not re-run by this script",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"package -> {OUT}")
    print(f"checkpoint/base hashes verified; environment torch={torch.__version__} "
          f"cuda={torch.version.cuda} cudnn={torch.backends.cudnn.version()}")


if __name__ == "__main__":
    main()
