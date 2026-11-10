# -*- coding: utf-8 -*-
"""Extract per-architecture model/tensor support from the shipped wllama wasm.

Why: an `llama_model_qwen35` symbol proves the arch is registered, but not that
its tensors are implemented. The wasm also embeds the llama.cpp model source
paths and the tensor-name format strings. This script records those strings for
the architectures lane 11 cares about, without loading a model or running wasm.

It is necessary evidence only; the real load test is the HPC preflight and lane
09's browser run.

Usage:
    python -X utf8 src/wllama_features.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
WASM = ROOT.parent.parent / "frontend/node_modules/@wllama/wllama/src/wasm/wllama.wasm"
OUT = ROOT / "models/wllama-features.json"
WANTED = ("qwen2", "qwen3", "qwen35", "internlm2", "chatglm", "hunyuan-dense", "gemma3", "minicpm")


def strings_of(data: bytes) -> list[str]:
    return [match.decode("latin1") for match in re.findall(rb"[ -~]{3,}", data)]


def main() -> int:
    if not WASM.exists():
        print(f"missing wasm: {WASM}", file=sys.stderr)
        return 2
    data = WASM.read_bytes()
    values = strings_of(data)
    arch_symbols = sorted(set(re.findall(r"llama_model_([a-z0-9_]+)", "\n".join(values))))
    model_sources: dict[str, list[str]] = {}
    for value in values:
        match = re.search(r"/source/llama\.cpp/src/models/([a-z0-9_-]+)\.cpp", value)
        if match:
            model_sources.setdefault(match.group(1), []).append(value)
    tensor_names = set()
    for value in values:
        for pattern in (r"blk\.%d\.([a-z0-9_]+)", r"blk\.\\d\*\.([a-z0-9_]+)"):
            tensor_names.update(re.findall(pattern, value))
    result = {
        "wasm": str(WASM),
        "wasmBytes": len(data),
        "wasmSha256": __import__("hashlib").sha256(data).hexdigest(),
        "method": "printable strings in the shipped wasm; model source paths and "
                  "llama.cpp tensor format strings",
        "wanted": {},
        "architectureSymbols": arch_symbols,
        "allModelSources": sorted(model_sources),
        "tensorNameCount": len(tensor_names),
        "note": "necessary, not sufficient: a real load/generation is still required",
    }
    for arch in WANTED:
        key = arch.replace("-", "_")
        files = sorted(set(model_sources.get(arch, []) + model_sources.get(key, [])))
        prefix = arch.split("-")[0]
        related = sorted({name for name in model_sources if name.startswith(prefix)})
        result["wanted"][arch] = {
            "archSymbolPresent": key in arch_symbols,
            "modelSourceFiles": files,
            "modelSourcePresent": bool(files),
            "relatedModelSources": related,
        }
    result["tensorNames"] = sorted(tensor_names)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({arch: result["wanted"][arch] for arch in WANTED}, ensure_ascii=False, indent=1))
    print(f"tensor names: {len(tensor_names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
