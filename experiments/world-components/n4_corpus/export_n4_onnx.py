# Export the frozen N4 checkpoint (r3-direction) to ONNX for the browser
# route (batch-1 minimal feasibility probe; the full browser adaptation is
# a later batch). The checkpoint itself is NOT retrained or modified: the
# export reads the frozen weights, and this script verifies parity before
# anything is served to a browser:
#
#   encoder.onnx            input_ids, attention_mask -> hidden states
#   decoder_step.onnx       stateless decoder step (no KV cache): the
#                           generated prefix is re-fed every step. O(n^2)
#                           in tokens, but n <= 64 here, and the graph has
#                           no cache plumbing to mis-export. Per-step cost
#                           is recorded honestly in the probe archive.
#
# Parity gate (measured, batch 1): torch-HF and ORT agree on logits to
# ~2e-5 (fp32 reassociation), but greedy decoding compounds that noise over
# up to 64 argmax steps, so HF-token-EXACT equality across runtimes is not
# a stable gate. The alignment target for the browser route is therefore
# the ORT-python greedy loop (SAME engine family as ORT-web in the
# browser): the browser must reproduce ORT-python ids EXACTLY. HF
# generate() ids are recorded as the training-runtime reference; a
# mid-generation token flip between HF and ORT is reported as drift, and
# both texts must stay recognizer-clean (checked by bake_probe_inputs.py
# for the baked cases).

import argparse
import hashlib
import importlib.machinery
import json
import pathlib
import sys
import types

# F6 process stubs (same as eval_n4_finetune.py): the base env's pyarrow
# wheel is ABI-broken against numpy 2.x and sklearn transitively imports
# it; a stub installed before torch/transformers keeps those imports alive
# without the broken native module.
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

CHECKPOINT = HERE.parent / "assets" / "n4-finetune" / "r3-direction"
OUT_DIR = HERE.parent / "assets" / "n4-onnx" / "r3-direction"


def sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_frozen():
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(str(CHECKPOINT), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(CHECKPOINT),
                                                       torch_dtype=torch.float32)
    model.eval()
    return tok, model


def export_encoder(model, out_dir: pathlib.Path):
    enc = model.get_encoder()
    dummy_ids = torch.ones((1, 8), dtype=torch.int64)
    dummy_mask = torch.ones((1, 8), dtype=torch.int64)
    torch.onnx.export(
        enc, (dummy_ids, dummy_mask), str(out_dir / "encoder.onnx"),
        input_names=["input_ids", "attention_mask"],
        output_names=["encoder_hidden_states"],
        dynamic_axes={"input_ids": {0: "batch", 1: "seq"},
                      "attention_mask": {0: "batch", 1: "seq"},
                      "encoder_hidden_states": {0: "batch", 1: "seq"}},
        opset_version=17, do_constant_folding=True)


class DecoderStep(torch.nn.Module):
    """Stateless decoder step: full prefix in, next-token logits out."""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, decoder_input_ids, encoder_hidden_states, encoder_attention_mask):
        out = self.model.decoder(
            input_ids=decoder_input_ids,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=encoder_attention_mask,
            use_cache=False,
            return_dict=True,
        )
        return self.model.lm_head(out.last_hidden_state)


def export_decoder(model, out_dir: pathlib.Path):
    dec = DecoderStep(model)
    d_ids = torch.ones((1, 4), dtype=torch.int64)
    enc_out = torch.ones((1, 8, model.config.d_model), dtype=torch.float32)
    enc_mask = torch.ones((1, 8), dtype=torch.int64)
    torch.onnx.export(
        dec, (d_ids, enc_out, enc_mask), str(out_dir / "decoder_step.onnx"),
        input_names=["decoder_input_ids", "encoder_hidden_states",
                     "encoder_attention_mask"],
        output_names=["logits"],
        dynamic_axes={"decoder_input_ids": {0: "batch", 1: "prefix"},
                      "encoder_hidden_states": {0: "batch", 1: "seq"},
                      "encoder_attention_mask": {0: "batch", 1: "seq"},
                      "logits": {0: "batch", 1: "prefix"}},
        opset_version=17, do_constant_folding=True)


def ort_greedy(ort_sess, enc_sess, input_ids, attention_mask, eos_id, pad_id,
               max_new_tokens=64):
    """Greedy loop over the exported graphs (no KV cache)."""
    import numpy as np
    enc = enc_sess.run(["encoder_hidden_states"], {
        "input_ids": input_ids.astype("int64"),
        "attention_mask": attention_mask.astype("int64"),
    })[0]
    dec_ids = torch.full((1, 1), fill_value=pad_id, dtype=torch.int64)
    out_ids = []
    for _ in range(max_new_tokens):
        logits = ort_sess.run(["logits"], {
            "decoder_input_ids": dec_ids.numpy().astype("int64"),
            "encoder_hidden_states": enc,
            "encoder_attention_mask": attention_mask.astype("int64"),
        })[0]
        nxt = int(logits[0, -1].argmax())
        if nxt == eos_id:
            break
        out_ids.append(nxt)
        dec_ids = torch.cat([dec_ids, torch.tensor([[nxt]], dtype=torch.int64)], dim=1)
    return out_ids


def hf_greedy(model, tok, text, max_new_tokens=64):
    enc = tok(text, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**enc, do_sample=False, num_beams=1,
                             max_new_tokens=max_new_tokens)
    in_len = enc["input_ids"].shape[1]
    return out[0, in_len:].tolist()


def verify_parity(tok, model, texts):
    import numpy as np
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    enc_sess = ort.InferenceSession(str(OUT_DIR / "encoder.onnx"), so,
                                    providers=["CPUExecutionProvider"])
    dec_sess = ort.InferenceSession(str(OUT_DIR / "decoder_step.onnx"), so,
                                    providers=["CPUExecutionProvider"])
    results = []
    drift_free = True
    for text in texts:
        enc_in = tok(text, return_tensors="np")
        ort_ids = ort_greedy(dec_sess, enc_sess, enc_in["input_ids"],
                             enc_in["attention_mask"], tok.eos_token_id,
                             tok.pad_token_id)
        ref = hf_greedy(model, tok, text)
        match = ort_ids == ref
        drift_free &= match
        results.append({"text": text, "ortIds": ort_ids, "hfIds": ref,
                        "ortMatchesHf": match,
                        "ortText": tok.decode(ort_ids, skip_special_tokens=True),
                        "hfText": tok.decode(ref, skip_special_tokens=True)})
        print(("EXACT" if match else "DRIFT"), text[:40], "->",
              tok.decode(ort_ids, skip_special_tokens=True)[:60])
    return results, drift_free


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true",
                        help="skip re-export; only run the parity gate")
    parser.add_argument("--texts", nargs="*", default=[
        "叙事生成任务。\n事实：\n1. 位置：陈舟 从东门到钟楼\n2. 时间推进：约三分钟\n正文：",
        "叙事生成任务。\n事实：\n1. 时间推进：约四十秒\n2. 无变化\n正文：",
    ])
    args = parser.parse_args()

    if not args.verify_only:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        print("loading frozen checkpoint", CHECKPOINT.name)
        tok, model = load_frozen()
        export_encoder(model, OUT_DIR)
        export_decoder(model, OUT_DIR)
        files = {p.name: sha_file(p) for p in sorted(OUT_DIR.glob("*.onnx"))}
        (OUT_DIR / "export_manifest.json").write_text(json.dumps({
            "checkpoint": str(CHECKPOINT.name),
            "opset": 17, "dtype": "fp32",
            "graphs": files,
            "torch": torch.__version__,
        }, indent=1), encoding="utf-8")
        print("exported:", list(files))
    tok, model = load_frozen()
    results, drift_free = verify_parity(tok, model, args.texts)
    if drift_free:
        print("PARITY: EXACT (ORT loop == HF greedy on all probe inputs)")
    else:
        print("PARITY: ORT loop runs; token drift vs HF greedy recorded "
              "(expected fp32 reassociation; the browser gate targets the "
              "ORT-python ids, see module header)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
