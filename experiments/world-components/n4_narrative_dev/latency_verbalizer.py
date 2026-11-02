# Per-call latency for the split narrative pipeline (verbalizer only).
#
# Measures one fact -> one clause, greedy, on the HPC GPU as a lower bound,
# then projects the per-turn cost for 2-4 fact calls. The slot scene arm has
# no model call. Usage (HPC): python latency_verbalizer.py --ckpt ckpt-verbalizer2
# Output: latency-report.json

import argparse
import json
import pathlib
import statistics
import time

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
MAX_INPUT, MAX_OUTPUT = 256, 48
WARMUP = 3


def load(name):
    return [json.loads(l) for l in
            (HERE / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ckpt", default="ckpt-verbalizer2")
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(args.ckpt, legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(
        args.ckpt, torch_dtype=torch.float32).to(device)
    model.eval()

    rows = load("verbalizer_holdout.jsonl")
    # warmup
    for r in rows[:WARMUP]:
        enc = tok(r["input"], return_tensors="pt", truncation=True,
                  max_length=MAX_INPUT).to(device)
        with torch.no_grad():
            model.generate(**enc, max_new_tokens=MAX_OUTPUT, num_beams=1,
                           do_sample=False)

    times, tokens = [], []
    for _ in range(args.repeats):
        for r in rows:
            enc = tok(r["input"], return_tensors="pt", truncation=True,
                      max_length=MAX_INPUT).to(device)
            t0 = time.perf_counter()
            with torch.no_grad():
                gen = model.generate(**enc, max_new_tokens=MAX_OUTPUT,
                                     num_beams=1, do_sample=False)
            times.append((time.perf_counter() - t0) * 1000)
            tokens.append(int((gen[0] != tok.pad_token_id).sum()))

    times.sort()
    def pct(p):
        return round(times[min(len(times) - 1, int(len(times) * p))], 1)

    report = {
        "purpose": "per-call latency of the fact verbalizer (GPU lower bound)",
        "ckpt": "ckpt-verbalizer2",
        "device": torch.cuda.get_device_name(0) if device == "cuda" else device,
        "calls": len(times),
        "ms": {"mean": round(statistics.mean(times), 1),
               "p50": pct(0.5), "p95": pct(0.95), "max": round(max(times), 1)},
        "outputTokens": {"mean": round(statistics.mean(tokens), 1)},
        "projection": {
            "turns": {str(n): round(statistics.mean(times) * n / 1000, 2)
                      for n in (1, 2, 3, 4)},
            "note": "GPU lower bound; browser (wllama/ORT) is slower and "
                    "must be measured separately. Scene arm adds no call.",
        },
    }
    pathlib.Path("latency-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + chr(10),
        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
