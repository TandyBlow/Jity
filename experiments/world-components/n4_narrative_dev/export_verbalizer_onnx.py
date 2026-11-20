# Export the trained verbalizer to ONNX for a real-browser latency probe.
#
# Emits the same contract the existing N4 browser probe uses:
#   encoder.onnx       input_ids, attention_mask -> encoder_hidden_states
#   decoder_step.onnx  full-prefix decoder step   -> logits
# plus probe_inputs.json with pre-baked token ids so the browser needs no
# tokenizer for this measurement (tokenizer parity is a separate contract).
#
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/export_verbalizer_onnx.py

import importlib.util
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
OUT = pathlib.Path(os.environ.get(
    "N4_ONNX_OUT", REPO / "frontend" / "public" / "models" / "n4-verb-probe"))
BASE_EXPORT = pathlib.Path(os.environ.get(
    "N4_BASE_EXPORT", WC / "n4_corpus" / "export_n4_onnx.py"))
CKPT = pathlib.Path(os.environ.get(
    "N4_VERB_CKPT", WC / "assets" / "n4-finetune" / "ckpt-verbalizer2"))
MAX_STEPS = 48
N_CASES = 8


def load_base():
    spec = importlib.util.spec_from_file_location("base_export", BASE_EXPORT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["base_export"] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    ckpt = CKPT
    if not (ckpt / "config.json").exists():
        raise SystemExit(f"checkpoint not found: {ckpt}")
    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    base = load_base()
    tok = T5Tokenizer.from_pretrained(str(ckpt), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        str(ckpt), torch_dtype=torch.float32)
    model.eval()

    OUT.mkdir(parents=True, exist_ok=True)
    base.export_encoder(model, OUT)
    torch.onnx.export(
        base.DecoderStep(model),
        (torch.ones((1, 4), dtype=torch.int64),
         torch.ones((1, 8, model.config.d_model), dtype=torch.float32),
         torch.ones((1, 8), dtype=torch.int64)),
        str(OUT / "decoder_step.onnx"),
        input_names=["decoder_input_ids", "encoder_hidden_states",
                     "encoder_attention_mask"],
        output_names=["logits"],
        dynamic_axes={"decoder_input_ids": {0: "batch", 1: "dec_seq"},
                      "encoder_hidden_states": {0: "batch", 1: "enc_seq"},
                      "encoder_attention_mask": {0: "batch", 1: "enc_seq"},
                      "logits": {0: "batch", 1: "dec_seq"}},
        opset_version=17, do_constant_folding=True)

    rows = [json.loads(l) for l in
            (HERE / "verbalizer_holdout.jsonl").read_text(
                encoding="utf-8").splitlines() if l.strip()][:N_CASES]
    cases = []
    for r in rows:
        enc = tok(r["input"], return_tensors="pt", truncation=True,
                  max_length=256)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=MAX_STEPS,
                                 num_beams=1, do_sample=False)
        cases.append({
            "id": r["pairId"],
            "inputIds": enc["input_ids"][0].tolist(),
            "attentionMask": enc["attention_mask"][0].tolist(),
            "padId": tok.pad_token_id,
            "pythonIds": gen[0].tolist(),
            "pythonText": tok.decode(gen[0], skip_special_tokens=True),
        })
    (OUT / "probe_inputs.json").write_text(
        json.dumps({"maxSteps": MAX_STEPS, "cases": cases},
                   ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8", newline=chr(10))
    print(f"exported {OUT} with {len(cases)} cases")
    for c in cases:
        print(" ", c["id"], len(c["inputIds"]), "->", len(c["pythonIds"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
