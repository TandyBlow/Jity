# -*- coding: utf-8 -*-
"""Read a GGUF file's metadata and tensor table without loading the weights.

Why: a model can be described as "Qwen2.5 1.5B Q4_K_M" in a README and still be
a different architecture or contain tensor types the browser's llama.cpp build
does not implement. This script prints what the file itself says:

  * the GGUF version and architecture string (`general.architecture`),
  * the embedded chat template (bytes + sha256), tokenizer model and vocabulary
    size, and the declared licence/size label,
  * every tensor type with the number of tensors and bytes, so an unsupported
    quantisation is visible before a browser run,
  * an estimated parameter count from the tensor dimensions.

No inference. Requirements: Python 3.10+, no third-party packages.

Usage:
    python -X utf8 src/gguf_probe.py path/to/model.gguf [--json out.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import struct
import sys

GGUF_MAGIC = b"GGUF"
# ggml_type enum, names as used by llama.cpp/gguf.
TENSOR_TYPES = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 4: "Q4_2", 5: "Q4_3",
    6: "Q5_0", 7: "Q5_1", 8: "Q8_0", 9: "Q8_1", 10: "Q2_K", 11: "Q3_K",
    12: "Q4_K", 13: "Q5_K", 14: "Q6_K", 15: "Q8_K", 16: "IQ2_XXS", 17: "IQ2_XS",
    18: "IQ3_XXS", 19: "IQ1_S", 20: "IQ4_NL", 21: "IQ3_S", 22: "IQ2_S",
    23: "IQ4_XS", 24: "I8", 25: "I16", 26: "I32", 27: "I64", 28: "F64",
    29: "IQ1_M", 30: "BF16", 31: "Q4_0_4_4", 32: "Q4_0_4_8", 33: "Q4_0_8_8",
    34: "TQ1_0", 35: "TQ2_0", 36: "IQ4_NL_4_4", 37: "IQ4_NL_4_8", 38: "IQ4_NL_8_8",
}
# Bytes per element for types whose size is exact; k-quants are block formats
# (the real file size is authoritative, this is only a sanity estimate).
DTYPE_BYTES = {0: 4, 1: 2, 24: 1, 25: 2, 26: 4, 27: 8, 28: 8, 30: 2}
# llama_ftype, as stored in `general.file_type`.
FILE_TYPES = {
    0: "ALL_F32", 1: "MOSTLY_F16", 2: "MOSTLY_Q4_0", 3: "MOSTLY_Q4_1",
    4: "MOSTLY_Q4_1_SOME_F16", 7: "MOSTLY_Q8_0", 8: "MOSTLY_Q5_0",
    9: "MOSTLY_Q5_1", 10: "MOSTLY_Q2_K", 11: "MOSTLY_Q3_K_S", 12: "MOSTLY_Q3_K_M",
    13: "MOSTLY_Q3_K_L", 14: "MOSTLY_Q4_K_S", 15: "MOSTLY_Q4_K_M",
    16: "MOSTLY_Q5_K_S", 17: "MOSTLY_Q5_K_M", 18: "MOSTLY_Q6_K",
}


class Reader:
    def __init__(self, handle):
        self.f = handle

    def read(self, count: int) -> bytes:
        data = self.f.read(count)
        if len(data) != count:
            raise ValueError(f"unexpected end of file: wanted {count}, got {len(data)}")
        return data

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.read(8))[0]

    def f32(self) -> float:
        return struct.unpack("<f", self.read(4))[0]

    def f64(self) -> float:
        return struct.unpack("<d", self.read(8))[0]

    def string(self) -> str:
        length = self.u64()
        return self.read(length).decode("utf-8", errors="replace")

    def value(self, vtype: int):
        if vtype == 0:
            return struct.unpack("<B", self.read(1))[0]
        if vtype == 1:
            return struct.unpack("<b", self.read(1))[0]
        if vtype == 2:
            return struct.unpack("<H", self.read(2))[0]
        if vtype == 3:
            return struct.unpack("<h", self.read(2))[0]
        if vtype == 4:
            return self.u32()
        if vtype == 5:
            return self.i32()
        if vtype == 6:
            return self.f32()
        if vtype == 7:
            return struct.unpack("<B", self.read(1))[0] != 0
        if vtype == 8:
            return self.string()
        if vtype == 9:
            item_type = self.u32()
            count = self.u64()
            # Arrays of tens of thousands of strings exist; keep them, the
            # caller decides what to serialize.
            return [self.value(item_type) for _ in range(count)]
        if vtype == 10:
            return self.u64()
        if vtype == 11:
            return self.i64()
        if vtype == 12:
            return self.f64()
        raise ValueError(f"unknown GGUF value type {vtype}")


def read_gguf(path: pathlib.Path) -> dict:
    size = path.stat().st_size
    with open(path, "rb") as handle:
        reader = Reader(handle)
        magic = reader.read(4)
        if magic != GGUF_MAGIC:
            raise ValueError(f"not a GGUF file: magic {magic!r}")
        version = reader.u32()
        tensor_count = reader.u64()
        kv_count = reader.u64()
        metadata = {}
        for _ in range(kv_count):
            key = reader.string()
            vtype = reader.u32()
            metadata[key] = reader.value(vtype)
        tensors = []
        for _ in range(tensor_count):
            name = reader.string()
            n_dims = reader.u32()
            dims = [reader.u64() for _ in range(n_dims)]
            ttype = reader.u32()
            offset = reader.u64()
            tensors.append({"name": name, "dims": dims, "type": ttype, "offset": offset})

    counts: dict[str, int] = {}
    params = 0
    for tensor in tensors:
        counts[TENSOR_TYPES.get(tensor["type"], f"unknown:{tensor['type']}")] = \
            counts.get(TENSOR_TYPES.get(tensor["type"], f"unknown:{tensor['type']}"), 0) + 1
        product = 1
        for dim in tensor["dims"]:
            product *= dim
        params += product

    template = metadata.get("tokenizer.chat_template")
    template_sha = hashlib.sha256(template.encode("utf-8")).hexdigest() if isinstance(template, str) else None
    summary = {
        "path": str(path),
        "bytes": size,
        "ggufVersion": version,
        "tensorCount": tensor_count,
        "metadataCount": kv_count,
        "architecture": metadata.get("general.architecture"),
        "name": metadata.get("general.name"),
        "sizeLabel": metadata.get("general.size_label"),
        "license": metadata.get("general.license"),
        "licenseName": metadata.get("general.license.name"),
        "licenseLink": metadata.get("general.license.link"),
        "quantization": metadata.get("general.file_type_names")
            or FILE_TYPES.get(metadata.get("general.file_type"), metadata.get("general.file_type")),
        "quantizedBy": metadata.get("general.quantized_by"),
        "tokenizerModel": metadata.get("tokenizer.ggml.model"),
        "vocabSize": len(metadata.get("tokenizer.ggml.tokens") or []) or None,
        "contextLength": metadata.get("general.context_length")
            or metadata.get(f"{metadata.get('general.architecture')}.context_length"),
        "chatTemplateChars": len(template) if isinstance(template, str) else None,
        "chatTemplateSha256": template_sha,
        "chatTemplateHead": template[:400] if isinstance(template, str) else None,
        "tensorTypes": counts,
        "estimatedParameters": params,
        "bytesPerParameter": round(size / params, 3) if params else None,
        "metadataKeys": sorted(metadata),
    }
    return {"summary": summary, "metadata": {k: v for k, v in metadata.items()
                                            if not isinstance(v, list) or len(v) < 64},
            "tensors": tensors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=pathlib.Path)
    parser.add_argument("--json", type=pathlib.Path, default=None,
                        help="write the full report here instead of printing it")
    parser.add_argument("--include-tensors", action="store_true")
    args = parser.parse_args()
    report = read_gguf(args.model)
    if not args.include_tensors:
        report.pop("tensors", None)
        report["summary"]["metadataKeys"] = report["summary"]["metadataKeys"][:40]
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
        print(json.dumps(report["summary"], ensure_ascii=False, indent=1))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
