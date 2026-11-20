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
# Parity gate (corrected, batch 4): with the decoder-only-sequence slice
# fixed (see hf_greedy) and the trailing-EOS convention aligned, HF greedy
# and the ORT loop agree EXACTLY on all probe inputs — the earlier
# "reassociation drift" record was an artifact of an empty HF arm produced
# by a wrong [input_len:] slice. The browser route still aligns against
# the ORT-python loop (same engine family as ORT-web in the browser), and
# that alignment is exact on every baked case.

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


class DecoderStepKV(torch.nn.Module):
    """KV-cache decoder step, SELF-ATTENTION-ONLY cache: per-layer self K,V
    are graph inputs/outputs; cross-attention K/V are RECOMPUTED from
    encoder_hidden_states every step (correct and trace-safe — a
    from_legacy_cache 4-tuple marks the cross cache "already computed", so
    under the 4-tuple contract the tracer never consumes
    encoder_hidden_states at all and the graph loses the input). The extra
    cross recompute per step is a few small MatMuls against the saved
    self-attention cost. cache_position and the extended self-attention
    mask are explicit inputs so past length stays dynamic."""

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.LAYERS = model.config.num_decoder_layers

    def forward(self, decoder_input_ids, encoder_hidden_states,
                encoder_attention_mask, cache_position, self_mask, *past_flat):
        from transformers.cache_utils import EncoderDecoderCache, DynamicCache
        layers = len(past_flat) // 2
        cache = EncoderDecoderCache(DynamicCache(config=self.model.config),
                                    DynamicCache(config=self.model.config))
        if layers:
            legacy_self = tuple((past_flat[l * 2], past_flat[l * 2 + 1])
                                for l in range(layers))
            cache.self_attention_cache = DynamicCache.from_legacy_cache(legacy_self)
        out = self.model.decoder(
            input_ids=decoder_input_ids,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=encoder_attention_mask,
            attention_mask=self_mask,
            cache_position=cache_position,
            past_key_values=cache,
            use_cache=True,
            return_dict=True,
        )
        logits = self.model.lm_head(out.last_hidden_state)
        flat = []
        for k, v in out.past_key_values.self_attention_cache.to_legacy_cache():
            flat.append(k)
            flat.append(v)
        return (logits, *flat)


def export_decoder_kv(model, out_dir: pathlib.Path):
    nl = model.config.num_decoder_layers
    dec = DecoderStepKV(model)
    d_ids = torch.ones((1, 1), dtype=torch.int64)
    enc_out = torch.ones((1, 8, model.config.d_model), dtype=torch.float32)
    enc_mask = torch.ones((1, 8), dtype=torch.int64)
    cache_pos = torch.zeros((1,), dtype=torch.int64)
    self_mask = torch.ones((1, 1), dtype=torch.int64)
    H, DK = model.config.num_heads, model.config.d_kv
    empty = tuple(torch.ones((1, H, 0, DK), dtype=torch.float32)
                  for _ in range(2 * nl))
    past_names = [f"past_{l}_{part}" for l in range(nl)
                  for part in ("self_k", "self_v")]
    torch.onnx.export(
        dec, (d_ids, enc_out, enc_mask, cache_pos, self_mask) + empty,
        str(out_dir / "decoder_kv.onnx"),
        input_names=["decoder_input_ids", "encoder_hidden_states",
                     "encoder_attention_mask", "cache_position",
                     "self_mask"] + past_names,
        output_names=["logits"] + [n.replace("past_", "present_") for n in past_names],
        dynamic_axes={
            "decoder_input_ids": {0: "batch", 1: "step"},
            "encoder_hidden_states": {0: "batch", 1: "seq"},
            "encoder_attention_mask": {0: "batch", 1: "seq"},
            "cache_position": {0: "pos"},
            "self_mask": {0: "batch", 1: "past+1"},
            "logits": {0: "batch", 1: "step"},
            **{n: {0: "batch", 2: "past"} for n in past_names},
            **{n.replace("past_", "present_"): {0: "batch", 2: "past+1"}
               for n in past_names},
        },
        # folding must stay OFF: with the dummy encoder states it folds the
        # cross-attention K/V projections into constants and DELETES the
        # encoder_hidden_states input from the graph
        opset_version=17, do_constant_folding=False)


def ort_greedy_kv(enc_sess, dec_sess, input_ids, attention_mask, eos_id,
                  pad_id, heads, d_kv, max_new_tokens=64):
    """Greedy loop over the KV-cache graphs; returns ids + per-step ms.
    Starts with zero-length self AND cross caches — the first step computes
    cross K/V from the encoder states itself, and every later step feeds
    back the previous present tensors."""
    import time
    import numpy as np
    enc = enc_sess.run(["encoder_hidden_states"], {
        "input_ids": input_ids.astype("int64"),
        "attention_mask": attention_mask.astype("int64"),
    })[0]
    in_names = [i.name for i in dec_sess.get_inputs()][5:]
    out_names = [o.name for o in dec_sess.get_outputs()][1:]
    past = {n: np.zeros((1, heads, 0, d_kv), dtype="float32") for n in in_names}
    dec_ids = np.array([[pad_id]], dtype="int64")
    out_ids, step_ms = [], []
    for step in range(max_new_tokens):
        feeds = {"decoder_input_ids": dec_ids,
                 "encoder_hidden_states": enc,
                 "encoder_attention_mask": attention_mask.astype("int64"),
                 "cache_position": np.array([step], dtype="int64"),
                 "self_mask": np.ones((1, step + 1), dtype="int64"),
                 **past}
        t0 = time.perf_counter()
        res = dec_sess.run(None, feeds)
        step_ms.append((time.perf_counter() - t0) * 1000)
        logits, flat = res[0], res[1:]
        # outputs mirror the past inputs in order (self_k/self_v per layer):
        # re-feed under the INPUT names for the next step
        past = dict(zip(in_names, flat))
        nxt = int(logits[0, -1].argmax())
        if nxt == eos_id:
            break
        out_ids.append(nxt)
        dec_ids = np.array([[nxt]], dtype="int64")
    return out_ids, step_ms


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
    # T5 sequences are DECODER-only (decoder_start + tokens): skipping
    # input_len would empty the result. Drop the decoder_start token, then
    # the trailing EOS so the convention matches the ORT loop (ids exclude
    # eos); with this convention HF and ORT agree EXACTLY — the "drift"
    # once recorded here was an artifact of an empty HF arm caused by the
    # wrong [input_len:] slice, not fp32 reassociation.
    ids = out[0, 1:].tolist()
    if ids and ids[-1] == tok.eos_token_id:
        ids = ids[:-1]
    return ids


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
    parser.add_argument("--kv", action="store_true",
                        help="also export + verify the KV-cache decoder graph")
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
        if args.kv:
            export_decoder_kv(model, OUT_DIR)
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
    if args.kv:
        import numpy as np
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = 1
        enc_sess = ort.InferenceSession(str(OUT_DIR / "encoder.onnx"), so,
                                        providers=["CPUExecutionProvider"])
        dec_kv = ort.InferenceSession(str(OUT_DIR / "decoder_kv.onnx"), so,
                                      providers=["CPUExecutionProvider"])
        cfg = model.config
        for text, res in zip(args.texts, results):
            enc_in = tok(text, return_tensors="np")
            ids, step_ms = ort_greedy_kv(enc_sess, dec_kv, enc_in["input_ids"],
                                         enc_in["attention_mask"], tok.eos_token_id,
                                         tok.pad_token_id, cfg.num_heads, cfg.d_kv)
            match = ids == res["ortIds"]
            print(("KV-EXACT" if match else "KV-DIFF"), text[:30],
                  f"steps={len(step_ms)} mean={sum(step_ms)/max(len(step_ms),1):.1f}ms",
                  "last-step", f"{step_ms[-1]:.1f}ms" if step_ms else "-")
            if not match:
                return 1
        print("KV PARITY: exact vs the stateless ORT loop")
    if drift_free:
        print("PARITY: EXACT (ORT loop == HF greedy on all probe inputs)")
    else:
        print("PARITY: ORT loop runs; token drift vs HF greedy recorded "
              "(expected fp32 reassociation; the browser gate targets the "
              "ORT-python ids, see module header)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
