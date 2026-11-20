# Export the v2 grouped-interface checkpoint (commit 3) to ONNX and bake the
# browser probe cases with Python references:
#
#   encoder.onnx + decoder_kv.onnx  (same self-KV contract as batch 3:
#       cross K/V recomputed per step inside the graph)
#
# Cross-check: for every baked case the ORT-python KV greedy loop is baked
# as the BROWSER parity target; the HF greedy loop is recorded alongside.
# HF exactness is NOT a hard gate for v2: fp32 reassociation between the
# exported KV graph and the HF full-prefix path shifts logits by ~1e-5 and
# can flip a near-tie token (3/8 cases here). That drift is reported per
# case, not papered over; the browser is compared against ORT-python, the
# same engine family (batch-3 contract).
#
# Baked cases: eight frozen family-C holdout rows, one per interface shape
# (pronoun cross-reference, same-name, gender-unknown, conflict, new
# relative/subtask kinds, no-change, co-presence). The grouped input is
# produced by the SAME render_v2 the training and runtime use.
#
# The co-presence case comes from the HISTORICAL v2 corpus (old N1 auto
# roster scan). Current N1 no longer emits positioned_at without an explicit
# observation source; the case remains a MODEL capability probe, not current
# pipeline evidence. gender_hints used by the pronoun cases are likewise
# experimental inputs, not a world-state field.

import importlib.machinery
import json
import pathlib
import sys
import types

try:
    import pyarrow  # noqa: F401
except Exception:
    _stub = types.ModuleType("pyarrow")
    _stub.__version__ = "16.1.0"
    _stub.__path__ = []
    sys.modules["pyarrow"] = _stub
_tf = types.ModuleType("tensorflow")
_tf.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
_tf.__path__ = []
sys.modules.setdefault("tensorflow", _tf)

import torch  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(WC / "n4_corpus"))

import export_n4_onnx as base  # noqa: E402
from render_v2 import render_input_v2  # noqa: E402

CKPT = HERE / "ckpt-v2"
OUT_DIR = WC / "assets" / "n4-onnx" / "v2-grouped"
CASES = [
    "v2-c-salt:cross-reference-8minute:v0",
    "v2-c-salt:same-name:v0",
    "v2-c-salt:gender-unknown-7minute:v0",
    "v2-c-salt:conflict-shared-goal:v0",
    "v2-c-salt:new-relative:v0",
    "v2-c-salt:new-subtask:v0",
    "v2-c-salt:no-change-0:v0",
    "v2-c-salt:co-presence:v0",
]
PROBE = WC / "browser_probe" / "v2_probe_cases.json"
ARCHIVE = REPO / "artifacts" / "world-components" / "n4-v2-browser-parity-python.json"


def sha_file(path) -> str:
    h = __import__("hashlib").sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(str(CKPT), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(CKPT),
                                                       torch_dtype=torch.float32)
    model.eval()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base.export_encoder(model, OUT_DIR)
    base.export_decoder_kv(model, OUT_DIR)
    manifest = {
        "checkpoint": "experiments/world-components/n4_corpus_v2/ckpt-v2",
        "checkpointSha256": sha_file(CKPT / "model.safetensors"),
        "opset": 17, "dtype": "fp32",
        "graphs": {p.name: sha_file(p) for p in sorted(OUT_DIR.glob("*.onnx"))},
        "torch": torch.__version__,
        "contract": "encoder + self-KV decoder step; cross K/V recomputed "
                    "inside each step (batch-3 F26)",
    }
    (OUT_DIR / "export_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    print("exported:", list(manifest["graphs"]))

    import numpy as np
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    enc_sess = ort.InferenceSession(str(OUT_DIR / "encoder.onnx"), so,
                                    providers=["CPUExecutionProvider"])
    dec_sess = ort.InferenceSession(str(OUT_DIR / "decoder_kv.onnx"), so,
                                    providers=["CPUExecutionProvider"])
    cfg = model.config

    rows = {json.loads(l)["rowId"]: json.loads(l) for l in
            (HERE / "corpus_v2" / "holdout-v2.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()}
    cases, exact = [], True
    for row_id in CASES:
        row = rows[row_id]
        text = render_input_v2(row["plan"], row["facts"])
        enc_in = tok(text, return_tensors="np")
        ort_ids, step_ms = base.ort_greedy_kv(
            enc_sess, dec_sess, enc_in["input_ids"],
            enc_in["attention_mask"], tok.eos_token_id, tok.pad_token_id,
            cfg.num_heads, cfg.d_kv, max_new_tokens=128)
        hf_ids = base.hf_greedy(model, tok, text, max_new_tokens=128)
        match = ort_ids == hf_ids
        exact &= match
        cases.append({
            "rowId": row_id, "renderText": text,
            "inputIds": enc_in["input_ids"][0].tolist(),
            "referenceIds": ort_ids,
            "referenceText": tok.decode(ort_ids, skip_special_tokens=True),
            "hfIds": hf_ids, "ortMatchesHf": match,
            "stepMs": [round(x, 2) for x in step_ms],
            "totalModelMs": round(sum(step_ms), 1),
        })
        print(("EXACT" if match else "DRIFT"), row_id, "->",
              cases[-1]["referenceText"][:60])
    probe = {
        "purpose": "N4 v2 browser probe (commit 3): grouped interface through "
                   "the committed N4 adapter; Python reference = ORT KV loop",
        "checkpointSha256": manifest["checkpointSha256"],
        "onnx": manifest["graphs"],
        "cases": cases,
    }
    PROBE.write_text(json.dumps(probe, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8", newline="\n")
    archive = {
        "purpose": "N4 v2 ONNX export + Python reference bake (commit 3)",
        "manifest": manifest,
        "cases": cases,
        "hfExact": {"cases": sum(1 for c in cases if c["ortMatchesHf"]),
                    "total": len(cases),
                    "note": "fp32 reassociation drift (~1e-5 logits) flips "
                            "near-tie tokens; the browser parity target is "
                            "the ORT-python loop, not HF"},
        "pass": bool(cases) and all(c["referenceIds"] for c in cases),
    }
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8", newline="\n")
    print("python parity:", exact)
    return 0 if exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
