# int8 dynamic quantization of the exported N4 graphs (batch 3), with the
# mandatory quality comparison (runtime plan §2: "int8 后做且必须做量化前后
# 质量对照"). The quantized graphs are a SIZE/LOAD optimization candidate;
# the fp32 graphs stay the reference. The gate for int8 is judge-clean text
# on the frozen probe cases (token-exact vs fp32 is NOT required — int8
# activation noise shifts argmax), plus per-case diff reporting.

import argparse
import hashlib
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

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

SRC = HERE.parent / "assets" / "n4-onnx" / "r3-direction"
DST = HERE.parent / "assets" / "n4-onnx" / "r3-direction-int8"
GRAPHS = ["encoder.onnx", "decoder_kv.onnx"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    if not args.verify_only:
        from onnxruntime.quantization import quantize_dynamic, QuantType
        DST.mkdir(parents=True, exist_ok=True)
        for g in GRAPHS:
            quantize_dynamic(str(SRC / g), str(DST / g), weight_type=QuantType.QInt8)
            print("quantized:", g)

    import numpy as np
    import onnxruntime as ort
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    import torch

    CK = HERE.parent / "assets" / "n4-finetune" / "r3-direction"
    tok = T5Tokenizer.from_pretrained(str(CK), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(CK), dtype=torch.float32)
    model.eval()

    from export_n4_onnx import ort_greedy_kv
    from bake_probe_inputs import load_rows, synthetic_plan
    from n4_render import render_input
    import corpus_check

    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    enc32 = ort.InferenceSession(str(SRC / "encoder.onnx"), so, providers=["CPUExecutionProvider"])
    dec32 = ort.InferenceSession(str(SRC / "decoder_kv.onnx"), so, providers=["CPUExecutionProvider"])
    enc8 = ort.InferenceSession(str(DST / "encoder.onnx"), so, providers=["CPUExecutionProvider"])
    dec8 = ort.InferenceSession(str(DST / "decoder_kv.onnx"), so, providers=["CPUExecutionProvider"])
    cfg = model.config

    rows = load_rows()
    picks, seen = [], set()
    for r in rows:
        k = r["sourceGroupId"].rsplit("-", 1)[0]
        if k not in seen:
            seen.add(k)
            picks.append(r)
        if len(picks) >= 4:
            break
    cases = [{"name": r["sourceGroupId"], "plan": r["plan"], "scope": "frozen-holdout"}
             for r in picks]
    cases.append({"name": "synthetic-ext-1",
                  "plan": synthetic_plan(40, "second", [picks[0]["plan"][0]]),
                  "scope": "batch1-extension"})

    results = []
    for c in cases:
        text_in = render_input(c["plan"])
        enc_in = tok(text_in, return_tensors="np")
        ids32, ms32 = ort_greedy_kv(enc32, dec32, enc_in["input_ids"],
                                    enc_in["attention_mask"], tok.eos_token_id,
                                    tok.pad_token_id, cfg.num_heads, cfg.d_kv)
        ids8, ms8 = ort_greedy_kv(enc8, dec8, enc_in["input_ids"],
                                  enc_in["attention_mask"], tok.eos_token_id,
                                  tok.pad_token_id, cfg.num_heads, cfg.d_kv)
        t32 = tok.decode(ids32, skip_special_tokens=True)
        t8 = tok.decode(ids8, skip_special_tokens=True)
        # judge both outputs against the plan (eval-judge ref expansion)
        verdicts = {}
        for tag, t in (("fp32", t32), ("int8", t8)):
            sentences = [s for s in t.split("。") if s.strip()]
            all_refs = [e["ref"] for e in c["plan"] if "ref" in e]
            if not all_refs:
                all_refs = list(range(len(c["plan"])))
            fails, reviews = corpus_check.check_narration(
                c["plan"], t, [all_refs for _ in sentences], list(all_refs))
            verdicts[tag] = {"fails": fails, "reviews": reviews,
                             "clean": not fails}
        results.append({
            "name": c["name"], "scope": c["scope"],
            "tokenExact": ids32 == ids8,
            "fp32Text": t32, "int8Text": t8,
            "verdicts": verdicts,
            "meanStepMs": {"fp32": round(sum(ms32) / max(len(ms32), 1), 1),
                           "int8": round(sum(ms8) / max(len(ms8), 1), 1)},
        })
        print(c["name"], "exact" if ids32 == ids8 else "diff",
              "| fp32:", t32[:34], "| int8:", t8[:34])

    sizes = {g: {"fp32": (SRC / g).stat().st_size, "int8": (DST / g).stat().st_size}
             for g in GRAPHS}
    all_clean = all(r["verdicts"]["int8"]["clean"] and r["verdicts"]["fp32"]["clean"]
                    for r in results)
    archive = {
        "purpose": "int8 dynamic quantization of the exported N4 graphs with "
                   "the mandatory before/after quality comparison (runtime "
                   "plan §2); fp32 remains the reference graphs",
        "graphs": GRAPHS, "sizes": sizes,
        "qualityGate": "both fp32 and int8 outputs judge-clean on every "
                       "case; token-exactness NOT required across dtypes",
        "results": results,
        "pass": all_clean,
    }
    (HERE.parent / "browser_probe" / "int8_quality.json").write_text(
        json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print("int8 quality:", "PASS" if all_clean else "FAIL")
    return 0 if all_clean else 1


if __name__ == "__main__":
    sys.exit(main())
