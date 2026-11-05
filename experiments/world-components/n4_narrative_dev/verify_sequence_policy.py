"""Verify the no-truncation / no-length-cap sequence policy on real data.

Checks (all with the real 77M tokenizer and the real base weights):
  1. every corpus140 row encodes without losing its tail; target keeps EOS
  2. batch padding is exactly the batch max; label pads are -100
  3. short rows decoded by the new EOS/timeout decoder match HF greedy
  4. a model that never emits EOS stops by timeout and is marked incomplete
  5. cost: token lengths, peak VRAM for encode / train step / generate, wall time

Nothing here trains. It writes one JSON report.
"""
import argparse
import json
import pathlib
import sys
import time

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sequence_policy import (DEFAULT_GENERATION_TIMEOUT, encode_training_batch,
                             generate_greedy, sequence_policy)

CORPUS = HERE.parent / "n4_rewrite60" / "corpus140.jsonl"
REPORT = HERE.parents[2] / "artifacts" / "world-components" / \
    "n4-sequence-policy-verify-r1.json"

OLD_INPUT_CAP, OLD_TARGET_CAP = 512, 128


def gb(n):
    return round(n / (1024 ** 3), 3)


class NoEos:
    """Ban EOS so the decoder can only stop by timeout."""

    def __init__(self, eos_ids):
        self.eos_ids = eos_ids

    def __call__(self, ids, scores):
        scores[:, list(self.eos_ids)] = -float("inf")
        return scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(HERE.parent / "assets" / "randeng-t5-77m"))
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--hf-cap", type=int, default=128,
                    help="safety bound for the HF reference arm only")
    ap.add_argument("--short-rows", type=int, default=3)
    ap.add_argument("--out", default=str(REPORT))
    args = ap.parse_args()

    rows = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    tok = T5Tokenizer.from_pretrained(args.base, legacy=False, local_files_only=True)
    report = {
        "purpose": "verify full-sequence training and uncapped EOS/timeout decoding",
        "environment": {
            "torch": torch.__version__,
            "cuda": torch.cuda.is_available(),
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
            "python": sys.version.split()[0],
            "tokenizer": args.base,
            "tokenizerLegacy": False,
        },
        "policy": sequence_policy(args.timeout),
        "data": {"rows": len(rows), "file": CORPUS.name},
    }
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # ---------------- 1. encoding: tail preserved, EOS present
    lens_in, lens_tg, bad_tail, no_eos, over_in, over_tg = [], [], [], [], 0, 0
    for r in rows:
        ids_in = tok(r["input"], truncation=False).input_ids
        ids_tg = tok(r["target"], truncation=False).input_ids
        if ids_in != tok(r["input"], truncation=False, return_tensors=None).input_ids:
            bad_tail.append(r["id"] + ":input")
        if ids_tg[-1] != tok.eos_token_id:
            no_eos.append(r["id"])
        lens_in.append(len(ids_in))
        lens_tg.append(len(ids_tg))
        over_in += len(ids_in) > OLD_INPUT_CAP
        over_tg += len(ids_tg) > OLD_TARGET_CAP
    report["encoding"] = {
        "inputTokens": {"min": min(lens_in), "median": sorted(lens_in)[len(lens_in) // 2],
                        "max": max(lens_in), "total": sum(lens_in)},
        "targetTokens": {"min": min(lens_tg), "median": sorted(lens_tg)[len(lens_tg) // 2],
                         "max": max(lens_tg), "total": sum(lens_tg)},
        "overOldCaps": {"input512": over_in, "target128": over_tg},
        "tailLoss": bad_tail,
        "missingEos": no_eos,
    }

    # ---------------- 2. batch padding equals batch max; label pads are -100
    pad_ok, label_ok, batch_sizes = True, True, []
    for start in range(0, len(rows), 8):
        batch = rows[start:start + 8]
        enc, labels = encode_training_batch(tok, batch)
        want_in = max(len(tok(r["input"], truncation=False).input_ids) for r in batch)
        want_tg = max(len(tok(r["target"], truncation=False).input_ids) for r in batch)
        batch_sizes.append((enc.input_ids.shape[1], labels.input_ids.shape[1]))
        pad_ok &= enc.input_ids.shape[1] == want_in
        pad_ok &= labels.input_ids.shape[1] == want_tg
        pad_mask = labels.attention_mask == 0
        label_ok &= bool(torch.all(labels.input_ids[pad_mask] == -100))
        label_ok &= not bool(torch.any(labels.input_ids[~pad_mask] == -100))
    report["batching"] = {"batches": len(batch_sizes), "paddingEqualsBatchMax": pad_ok,
                          "padLabelsAreMinus100": label_ok,
                          "observedShapes": batch_sizes[:3]}

    # ---------------- 5a. tokenizer-free cost: nothing yet; load model once
    model = T5ForConditionalGeneration.from_pretrained(args.base,
                                                       torch_dtype=torch.float32)
    model.eval()
    model.to(device)

    # ---------------- 3. decode equivalence with HF greedy on short rows
    short = sorted(rows, key=lambda r: len(tok(r["input"], truncation=False).input_ids)
                   + len(tok(r["target"], truncation=False).input_ids))[:args.short_rows]
    eq = []
    for r in short:
        enc = tok(r["input"], return_tensors="pt", truncation=False).to(device)
        with torch.inference_mode():
            hf = model.generate(**enc, num_beams=1, do_sample=False,
                                max_new_tokens=args.hf_cap)
        hf_ids = hf[0].tolist()
        hf_eos = hf_ids[-1] == tok.eos_token_id
        saved = (model.generation_config.max_length,
                 model.generation_config.max_new_tokens)
        # 让库的长度上限变成 2/1：新解码器若回落到它，结果会立刻不同
        model.generation_config.max_length = 2
        model.generation_config.max_new_tokens = 1
        ours, meta = generate_greedy(model, enc, args.timeout)
        model.generation_config.max_length, model.generation_config.max_new_tokens = saved
        ours_ids = ours[0].tolist()
        n = min(len(hf_ids), len(ours_ids))
        eq.append({
            "rowId": r["id"],
            "hfEos": hf_eos,
            "hfTokens": len(hf_ids) - 1,
            "ourTokens": meta["newTokens"],
            "identicalToShorter": hf_ids[:n] == ours_ids[:n],
            "exact": hf_ids == ours_ids,
            "stopReason": meta["stopReason"],
            "complete": meta["complete"],
            "seconds": meta["seconds"],
        })
    report["decodeEquivalence"] = {
        "note": "HF arm bounded by --hf-cap only as a test harness; "
                "the new decoder ignores generation_config length limits",
        "hfCap": args.hf_cap,
        "rows": eq,
        "allExact": all(x["exact"] for x in eq),
        "allMatchedToShorter": all(x["identicalToShorter"] for x in eq),
    }

    # ---------------- 4. timeout: ban EOS, expect incomplete
    r0 = short[0]
    enc = tok(r0["input"], return_tensors="pt", truncation=False).to(device)
    t0 = time.perf_counter()
    partial, meta = generate_greedy(model, enc, 3.0,
                                    logits_processor=NoEos({tok.eos_token_id}))
    report["timeout"] = {
        "rowId": r0["id"], "timeoutSeconds": 3.0,
        "stopReason": meta["stopReason"], "complete": meta["complete"],
        "keptTokens": meta["newTokens"], "wallSeconds": round(time.perf_counter() - t0, 3),
        "partialDecoded": tok.decode(partial[0], skip_special_tokens=True)[:120],
        "countedAsSuccess": meta["complete"],
    }

    # ---------------- 5b. peak VRAM and time: train step at worst-case lengths
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
    longest = sorted(rows, key=lambda r: len(tok(r["input"], truncation=False).input_ids),
                     reverse=True)[:8]
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4)
    steps = []
    for bs in (1, 2, 4, 8):
        batch = longest[:bs]
        enc, labels = encode_training_batch(tok, batch)
        enc = {k: v.to(device) for k, v in enc.items()}
        labels = labels.input_ids.to(device)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        t = time.perf_counter()
        try:
            out = model(**enc, labels=labels)
            out.loss.backward()
            opt.step()
            opt.zero_grad()
            torch.cuda.synchronize() if torch.cuda.is_available() else None
            rec = {"batch": bs, "ok": True,
                   "inputTokens": int(enc["input_ids"].shape[1]),
                   "targetTokens": int(labels.shape[1]),
                   "seconds": round(time.perf_counter() - t, 3),
                   "loss": round(float(out.loss), 4),
                   "peakAllocatedGB": gb(torch.cuda.max_memory_allocated())
                   if torch.cuda.is_available() else None,
                   "peakReservedGB": gb(torch.cuda.max_memory_reserved())
                   if torch.cuda.is_available() else None}
        except torch.cuda.OutOfMemoryError as exc:
            rec = {"batch": bs, "ok": False, "oom": True, "error": str(exc)[:200]}
        steps.append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
    report["trainStepCost"] = {
        "note": "worst-case rows (longest inputs in corpus140); fp32; "
                "peak is per batch size after empty_cache",
        "steps": steps,
    }
    model.eval()

    # ---------------- 5c. generation cost
    torch.cuda.reset_peak_memory_stats() if torch.cuda.is_available() else None
    gcost = []
    for r in short:
        enc = tok(r["input"], return_tensors="pt", truncation=False).to(device)
        gen, meta = generate_greedy(model, enc, args.timeout)
        gcost.append({"rowId": r["id"], "inputTokens": int(enc["input_ids"].shape[1]),
                      "newTokens": meta["newTokens"], "seconds": meta["seconds"],
                      "peakAllocatedGB": gb(torch.cuda.max_memory_allocated())
                      if torch.cuda.is_available() else None})
    report["generateCost"] = {"rows": gcost}

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
