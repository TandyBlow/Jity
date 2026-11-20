# Bake the N4 browser-probe inputs: the REAL spiece tokenizer (frozen
# checkpoint's own T5Tokenizer, legacy=False) turns rendered plans into
# token ids, and HF greedy decode produces the reference ids the browser
# must reproduce exactly. The browser probe never tokenizes text itself —
# JS sentencepiece is the later adaptation batch; this probe isolates the
# question "can the frozen T5 architecture run in the browser and decode
# the same tokens" from the tokenizer question.
#
# Inputs cover both the frozen space (minute/hour holdout plans) and the
# batch-1 legal-input extension (second / zero / day) — the extension space
# has no trained rows, so the model output there is whatever the frozen
# checkpoint generalizes; parity is about the GRAPH, not about quality.

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
_tf_stub = types.ModuleType("tensorflow")
_tf_stub.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
_tf_stub.__path__ = []
sys.modules.setdefault("tensorflow", _tf_stub)

import torch  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from n4_render import render_input  # noqa: E402

CHECKPOINT = HERE.parent / "assets" / "n4-finetune" / "r3-direction"
OUT = HERE.parent / "browser_probe" / "probe_inputs.json"


def load_rows():
    rows = []
    holdout = HERE.parent / "n4_holdout" / "holdout.jsonl"
    for line in holdout.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def synthetic_plan(amount, unit, kind_rows):
    """A plan outside the frozen corpus space (second/zero/day) built from
    holdout entry templates, for graph-parity only (no quality claim)."""
    plan = []
    for e in kind_rows:
        e = json.loads(json.dumps(e, ensure_ascii=False))
        e["ref"] = len(plan)
        plan.append(e)
    plan.append({"ref": len(plan), "kind": "time",
                 "amount": amount, "unit": unit,
                 "rendered": f"{amount}{unit}"})
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(str(CHECKPOINT), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(CHECKPOINT),
                                                       dtype=torch.float32)
    model.eval()

    from export_n4_onnx import ort_greedy
    import numpy as np
    import onnxruntime as ort
    onnx_dir = HERE.parent / "assets" / "n4-onnx" / "r3-direction"
    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    enc_sess = ort.InferenceSession(str(onnx_dir / "encoder.onnx"), so,
                                    providers=["CPUExecutionProvider"])
    dec_sess = ort.InferenceSession(str(onnx_dir / "decoder_step.onnx"), so,
                                    providers=["CPUExecutionProvider"])

    rows = load_rows()
    picks = []
    seen = set()
    for r in rows:
        key = r["sourceGroupId"].rsplit("-", 1)[0]
        if key not in seen:
            seen.add(key)
            picks.append(r)
        if len(picks) >= 4:
            break
    # plus one shared-regression row and synthetic extended-space plans
    synth = [
        synthetic_plan(40, "second", [picks[0]["plan"][0]]),   # moved + 40s
        synthetic_plan(0, "minute", []),                        # zero, empty
        synthetic_plan(3, "day", [e for e in picks[1]["plan"] if e["kind"] != "time"]),
    ]

    cases = []
    for r in picks + []:
        text = render_input(r["plan"])
        cases.append({"name": r["sourceGroupId"], "renderText": text,
                      "plan": r["plan"], "scope": "frozen-holdout"})
    for i, plan in enumerate(synth):
        cases.append({"name": f"synthetic-ext-{i + 1}",
                      "renderText": render_input(plan),
                      "plan": plan, "scope": "batch1-extension"})

    torch.manual_seed(0)
    for c in cases:
        enc = tok(c["renderText"], return_tensors="pt")
        with torch.no_grad():
            out = model.generate(**enc, do_sample=False, num_beams=1,
                                 max_new_tokens=64)
        # decoder-only sequences: drop the decoder_start token only; then
        # drop the trailing EOS so the convention matches the ORT loop
        # (ids exclude eos — texts are unaffected either way)
        ref = out[0, 1:].tolist()
        if ref and ref[-1] == tok.eos_token_id:
            ref = ref[:-1]
        # the browser's alignment target is the ORT-python greedy loop (the
        # same engine family as ORT-web in the browser); HF generate ids are
        # the training-runtime reference, kept for drift reporting
        ort_ids = ort_greedy(dec_sess, enc_sess, enc["input_ids"].numpy(),
                             enc["attention_mask"].numpy(),
                             tok.eos_token_id, tok.pad_token_id)
        c["inputIds"] = enc["input_ids"][0].tolist()
        c["attentionMask"] = enc["attention_mask"][0].tolist()
        c["referenceIds"] = ort_ids
        c["hfReferenceIds"] = ref
        c["hfMatchesOrt"] = ref == ort_ids
        c["referenceText"] = tok.decode(ort_ids, skip_special_tokens=True)
        c["hfReferenceText"] = tok.decode(ref, skip_special_tokens=True)
        c["eosId"] = tok.eos_token_id
        c["padId"] = tok.pad_token_id
        c["tokenizerHash"] = hashlib.sha256(
            (CHECKPOINT / "spiece.model").read_bytes()).hexdigest()

    payload = {
        "purpose": "N4 browser minimal-feasibility probe inputs; ids from "
                   "the frozen checkpoint's own T5Tokenizer (legacy=False); "
                   "referenceIds = ORT-python greedy loop (browser parity "
                   "target, same engine family as ORT-web); hfReferenceIds "
                   "= HF generate() (training runtime, drift-annotated)",
        "checkpoint": CHECKPOINT.name,
        "cases": cases,
    }
    pathlib.Path(args.out).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    for c in cases:
        print(c["name"], f"in{len(c['inputIds'])}",
              "hf==ort" if c["hfMatchesOrt"] else "hf-DRIFT", "->",
              c["referenceText"][:50])
    return 0


if __name__ == "__main__":
    sys.exit(main())
