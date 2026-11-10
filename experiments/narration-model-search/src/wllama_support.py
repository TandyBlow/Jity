# -*- coding: utf-8 -*-
"""Record which GGUF architectures the shipped wllama build knows about.

The browser does not run a general-purpose llama.cpp binary; it runs the
WebAssembly module that `frontend/node_modules/@wllama/wllama` ships. A model
whose `general.architecture` string is absent from that module cannot be
expected to load, no matter what a model card says.

This script scans the shipped wasm for the `llama_model_<arch>` symbols that the
llama.cpp model loader dispatches on, stores their sorted list next to the wasm
sha256, and is deliberately described as *necessary, not sufficient* evidence:
the real load/生成 test still happens through the HPC preflight and lane 09.

Usage:
    python -X utf8 src/wllama_support.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
WORKTREE = ROOT.parent.parent
WASM = WORKTREE / "frontend/node_modules/@wllama/wllama/src/wasm/wllama.wasm"
PACKAGE = WORKTREE / "frontend/node_modules/@wllama/wllama/package.json"
OUT = ROOT / "models/wllama-support.json"


def main() -> int:
    if not WASM.exists():
        print(f"missing shipped wasm: {WASM}", file=sys.stderr)
        return 2
    data = WASM.read_bytes()
    strings = [s.decode("ascii") for s in re.findall(rb"[ -~]{4,}", data)]
    models = sorted({
        match.group(1)
        for text in strings
        for match in [re.search(r"(?:^|\d)llama_model_([a-z0-9_]+)$", text)]
        if match
    })
    version = json.loads(PACKAGE.read_text(encoding="utf-8")).get("version") if PACKAGE.exists() else None
    report = {
        "wllamaVersion": version,
        "wasmPath": str(WASM.relative_to(WORKTREE)).replace("\\", "/"),
        "wasmBytes": len(data),
        "wasmSha256": hashlib.sha256(data).hexdigest(),
        "method": r"ASCII strings matching /(?:^|\d)llama_model_([a-z0-9_]+)$/ in the shipped wasm "
                  "(the leading digits are the C++ mangled-name length prefix)",
        "architectureModels": models,
        "limits": [
            "Presence of an architecture symbol is necessary but not sufficient: "
            "tensor types, chat-template rendering and the actual WebGPU/WASM "
            "backend still need a real load and generation test.",
            "The wasm in this worktree is the one the browser serves; a different "
            "frontend/node_modules copy is different evidence.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("wllamaVersion", "wasmSha256", "wasmBytes")}, indent=1))
    print(f"{len(models)} architectures -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
