# Export the trained N5 relation head (commit 3) to ONNX for the browser
# route, with a Python-side parity gate:
#
#   n5-encoder-head.onnx   input_ids, attention_mask -> 3 logits
#                          (MiniRBT encoder + mean pooling + linear head,
#                          fused into ONE graph so the browser computes
#                          exactly what Python computes)
#
# Parity gate: for a baked set of pairs, HF-python logits and onnxruntime
# logits must agree within 1e-4 max-abs (fp32). The baked inputs, outputs
# and the threshold table go into the archive; the browser parity check
# (commit 3) reuses the SAME baked cases against ORT-web.

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

import torch  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "n4_corpus_v2"))

CKPT = HERE / "n4_corpus_v2" / "ckpt-n5"
OUT_DIR = HERE / "n4_corpus_v2" / "onnx-n5"


class N5Wrapper(torch.nn.Module):
    """encoder + mean-pool + classifier, fused for export."""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask):
        out = self.model.encoder(input_ids=input_ids,
                                 attention_mask=attention_mask)
        mask = attention_mask.unsqueeze(-1).to(out.last_hidden_state.dtype)
        pooled = (out.last_hidden_state * mask).sum(1) / \
            mask.sum(1).clamp(min=1e-9)
        return self.model.classifier(self.model.dropout(pooled))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ckpt", default=str(CKPT))
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()
    ckpt = pathlib.Path(args.ckpt)
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    from transformers.models.bert.tokenization_bert import BertTokenizer
    from train_n5_head import RelationHead
    tok = BertTokenizer.from_pretrained(str(ckpt))
    model = RelationHead(str(ckpt))
    sd = torch.load(ckpt.parent / "head-n5.pt", map_location="cpu",
                    weights_only=True)
    model.classifier.load_state_dict(sd["classifier"])
    model.eval()
    wrapper = N5Wrapper(model)
    wrapper.eval()

    pairs = [json.loads(l) for l in
             (HERE / "n4_corpus_v2" / "corpus_v2" / "n5" / "test.jsonl")
             .read_text(encoding="utf-8").splitlines() if l.strip()][:24]
    from build_n5_pairs import fact_desc
    texts = [f"句子：{p['sentence']}事实：{fact_desc(p['fact'])}关系："
             for p in pairs]
    enc = tok(texts, padding=True, truncation=True, max_length=96,
              return_tensors="pt")
    with torch.no_grad():
        hf_logits = wrapper(enc.input_ids, enc.attention_mask)

    path = out_dir / "n5-encoder-head.onnx"
    torch.onnx.export(
        wrapper, (enc.input_ids[:1], enc.attention_mask[:1]), str(path),
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={"input_ids": {0: "batch", 1: "seq"},
                      "attention_mask": {0: "batch", 1: "seq"},
                      "logits": {0: "batch"}},
        opset_version=14, do_constant_folding=True)
    import onnxruntime as ort
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    import numpy as np
    drift = 0.0
    baked = []
    unpadded = tok(texts)
    for i, text in enumerate(texts):
        e = tok(text, padding="max_length", truncation=True,
                max_length=96, return_tensors="pt")
        ort_logits = sess.run(None, {
            "input_ids": e.input_ids.numpy(),
            "attention_mask": e.attention_mask.numpy()})[0]
        d = float(abs(ort_logits[0] - hf_logits[i].numpy()).max())
        drift = max(drift, d)
        baked.append({"sentence": pairs[i]["sentence"],
                      "factText": texts[i],
                      "factKind": pairs[i]["fact"]["kind"],
                      "label": pairs[i]["label"],
                      "tokenIds": list(unpadded["input_ids"][i]),
                      "attentionMask": list(unpadded["attention_mask"][i]),
                      "paddedTokenIds": e.input_ids[0].tolist(),
                      "paddedAttentionMask": e.attention_mask[0].tolist(),
                      "hfLogits": [round(x, 5) for x in
                                   hf_logits[i].tolist()],
                      "ortLogits": [round(float(x), 5) for x in
                                    ort_logits[0]]})
    archive = {
        "purpose": "N5 ONNX export with parity gate (commit 3)",
        "onnx": {"path": "experiments/world-components/n4_corpus_v2/"
                         "onnx-n5/n5-encoder-head.onnx",
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 "bytes": path.stat().st_size},
        "encoder": {"dir": ckpt.resolve().relative_to(HERE.parents[1])
                    .as_posix(),
                    "sha256": hashlib.sha256(
                        (ckpt / "model.safetensors").read_bytes()).hexdigest()},
        "head": {"sha256": hashlib.sha256(
            (ckpt.parent / "head-n5.pt").read_bytes()).hexdigest()},
        "tokenizer": {"files": ["vocab.txt", "tokenizer_config.json",
                                "special_tokens_map.json"]},
        "parity": {"maxAbsLogitDrift": drift, "bakedCases": len(baked),
                   "gate": 1e-4, "pass": drift <= 1e-4},
        "baked": baked,
        "pass": drift <= 1e-4,
    }
    (out_dir / "n5-export-report.json").write_text(
        json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps(archive["parity"], ensure_ascii=False))
    return 0 if archive["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
