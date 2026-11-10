"""c9 asset registration: locate the existing 77M T5 weights, tokenizer and
the registered probe fixtures, hash them, and write one provenance file.

Source of truth is NOT this script's output — the files themselves are. This
only records where they are and what bytes the run consumed, so a later
reader can re-hash and compare.

Usage:
  D:/software/Anaconda/python.exe assets.py [--out runs/assets.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WT = HERE.parents[3]    # this worktree (.../.local/parallel/c-browser-t5)
REPO = HERE.parents[6]  # the main checkout (.../Jity)

# Read-only inputs, all of them pre-existing (c9 does not create weights):
#   graphs          exported fp32 ONNX of the r3-direction fine-tune
#   checkpoint      the fine-tune itself (config + tokenizer)
#   fixture         batch-1 registered probe inputs (baked ids + references)
#   base_snapshot   the untuned 77M base weights, for the parameter count
GRAPH_DIR_INT8 = REPO / ".local" / "world-components-worktree" / "experiments" /     "world-components" / "assets" / "n4-onnx" / "r3-direction-int8"
GRAPH_DIR = REPO / ".local" / "world-components-worktree" / "experiments" / \
    "world-components" / "assets" / "n4-onnx" / "r3-direction"
CKPT_DIR = REPO / ".local" / "world-components-worktree" / "experiments" / \
    "world-components" / "assets" / "n4-finetune" / "r3-direction"
FIXTURE = WT / "experiments" / "world-components" / "browser_probe" / \
    "probe_inputs.json"
BASE_SNAPSHOT = REPO / ".local" / "models"


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def describe(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False}
    return {
        "path": str(path.relative_to(REPO)),
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def param_count(safetensors: pathlib.Path) -> int:
    from safetensors import safe_open

    with safe_open(str(safetensors), "pt") as f:
        return sum(t.numel() for t in (f.get_tensor(k) for k in f.keys()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "runs" / "assets.json"))
    args = ap.parse_args()

    cfg = json.loads((CKPT_DIR / "config.json").read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest = json.loads(
        (GRAPH_DIR / "export_manifest.json").read_text(encoding="utf-8"))

    base_ckpt = BASE_SNAPSHOT / "model.safetensors"
    ft_ckpt = CKPT_DIR / "model.safetensors"
    record = {
        "purpose": "c9 browser T5 runtime probe - inputs actually consumed",
        "graphs": {
            name: describe(GRAPH_DIR / name)
            for name in ("encoder.onnx", "decoder_kv.onnx", "decoder_step.onnx")
        },
        "graphs_int8": {
            name: describe(GRAPH_DIR_INT8 / name)
            for name in ("encoder.onnx", "decoder_kv.onnx")
        },
        "export_manifest": describe(GRAPH_DIR / "export_manifest.json"),
        "export_manifest_content": manifest,
        "checkpoint": {
            "config": describe(CKPT_DIR / "config.json"),
            "spiece": describe(CKPT_DIR / "spiece.model"),
            "safetensors": describe(ft_ckpt),
            "params": param_count(ft_ckpt) if ft_ckpt.exists() else None,
        },
        "base_snapshot_77m": {
            "config": describe(BASE_SNAPSHOT / "config.json"),
            "spiece": describe(BASE_SNAPSHOT / "spiece.model"),
            "safetensors": describe(base_ckpt),
            "params": param_count(base_ckpt) if base_ckpt.exists() else None,
        },
        "fixture": describe(FIXTURE),
        "fixture_cases": [
            {"name": c["name"], "scope": c["scope"],
             "inputTokens": len(c["inputIds"]),
             "referenceTokens": len(c["referenceIds"]),
             "referenceIdsSha256": hashlib.sha256(
                 ",".join(str(x) for x in c["referenceIds"]).encode()
             ).hexdigest()}
            for c in fixture["cases"]
        ],
        "decode_params": {
            "strategy": "greedy (argmax per step, no sampling, no beam)",
            "max_new_tokens": 64,
            "eos_token_id": cfg["eos_token_id"],
            "pad_token_id": cfg["pad_token_id"],
            "decoder_start_token_id": cfg["decoder_start_token_id"],
            "num_heads": cfg["num_heads"],
            "d_kv": cfg["d_kv"],
            "d_model": cfg["d_model"],
            "vocab_size": cfg["vocab_size"],
            "num_layers": cfg["num_layers"],
            "num_decoder_layers": cfg["num_decoder_layers"],
            "kv_cache": "self-attention KV only; cross-attention K/V recomputed "
                        "inside decoder_kv.onnx each step",
            "input_truncation": "adapter returns unsupported above 128 real "
                                "tokens (ids include the appended </s>=1)",
            "note": "max_input 128 / max_output 64 are the r3-direction "
                    "training contract; the adapter does not pad or truncate "
                    "below the gate",
        },
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    missing = [k for k, v in record["graphs"].items() if not v["exists"]]
    print("wrote", out)
    print("encoder sha:", record["graphs"]["encoder.onnx"].get("sha256"))
    print("params:", record["checkpoint"]["params"],
          "fixture cases:", len(record["fixture_cases"]))
    if missing:
        print("MISSING GRAPHS:", missing)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
