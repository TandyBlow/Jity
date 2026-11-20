"""HPC smoke for the full-sequence, no-length-cap training path.

Runs a few real optimizer steps on the longest rows, saves and reloads the
checkpoint, decodes to EOS, and checks that a model which never emits EOS is
stopped by the timeout and marked incomplete. No truncation anywhere: batch
size is what gives way on OOM, never the text.

Writes one JSON report. Does not touch the base weights on disk.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import time

import torch
from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
from transformers.models.t5.tokenization_t5 import T5Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sequence_policy import (encode_training_batch, generate_greedy, rethrow_oom)

TARGET_LEN = 200     # corpus140 max
INPUT_LEN = 574      # corpus140 max


def sha16(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


class NoEos:
    def __init__(self, eos_id):
        self.eos_id = eos_id

    def __call__(self, ids, scores):
        scores[:, self.eos_id] = -float("inf")
        return scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=20.0)
    args = ap.parse_args()

    torch.manual_seed(20261104)
    report = {"purpose": "HPC smoke: full-length training + EOS/timeout decoding",
              "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "host": sys.platform, "python": sys.version.split()[0],
              "torch": torch.__version__,
              "transformers": __import__("transformers").__version__,
              "cuda": torch.cuda.is_available(),
              "deviceName": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
              "base": {"path": args.base,
                       "configSha16": sha16(pathlib.Path(args.base) / "config.json"),
                       "weightsSha16": sha16(pathlib.Path(args.base) / "model.safetensors")},
              "corpusSha16": sha16(args.corpus)}
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(args.base, legacy=False, local_files_only=True)

    rows = [json.loads(l) for l in pathlib.Path(args.corpus)
            .read_text(encoding="utf-8").splitlines() if l.strip()]

    def n_in(r):
        return len(tok(r["input"], truncation=False).input_ids)

    def n_tg(r):
        return len(tok(r["target"], truncation=False).input_ids)

    longest_in = max(rows, key=n_in)
    longest_tg = max(rows, key=n_tg)
    report["encoding"] = {
        "rows": len(rows),
        "maxInput": {"id": longest_in["id"], "tokens": n_in(longest_in)},
        "maxTarget": {"id": longest_tg["id"], "tokens": n_tg(longest_tg)},
        "maxTargetIsExpected200": n_tg(longest_tg) == TARGET_LEN,
        "maxInputIsExpected574": n_in(longest_in) == INPUT_LEN,
    }

    model = T5ForConditionalGeneration.from_pretrained(args.base,
                                                       torch_dtype=torch.float32)
    model.to(device)
    report["modelLoaded"] = True
    model.eval()

    # ---- generate to EOS
    short = min(rows, key=n_in)
    enc1 = tok(short["input"], return_tensors="pt", truncation=False).to(device)
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    gen, meta = generate_greedy(model, enc1, args.timeout)
    report["generateEosOnBase"] = {"rowId": short["id"], "stopReason": meta["stopReason"],
                             "complete": meta["complete"],
                             "newTokens": meta["newTokens"],
                             "seconds": meta["seconds"],
                             "text": tok.decode(gen[0], skip_special_tokens=True)[:200]}

    # ---- never emits EOS -> timeout, incomplete
    part, meta2 = generate_greedy(model, enc1, 3.0,
                                  logits_processor=NoEos(tok.eos_token_id))
    report["timeoutOnBase"] = {"stopReason": meta2["stopReason"],
                         "complete": meta2["complete"],
                         "newTokens": meta2["newTokens"],
                         "countedAsSuccess": meta2["complete"]}

    model.train()

    # ---- the batch deliberately mixes the longest target with the longest input
    pool = [longest_tg, longest_in]
    pool += [r for r in rows if r not in pool and r["split"] == "train"]
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
    model.train()
    steps, tried, batch_size = [], [], 8
    while True:
        try:
            for i in range(args.steps):
                batch = pool[(i * batch_size) % len(pool):][:batch_size]
                if len(batch) < batch_size:
                    batch = pool[:batch_size]
                enc, labels = encode_training_batch(tok, batch)
                enc = {k: v.to(device) for k, v in enc.items()}
                lab = labels.input_ids.to(device)
                if torch.cuda.is_available():
                    torch.cuda.reset_peak_memory_stats()
                t = time.perf_counter()
                try:
                    out = model(**enc, labels=lab)
                except torch.cuda.OutOfMemoryError as exc:
                    rethrow_oom(exc, enc, lab)
                opt.zero_grad()
                out.loss.backward()
                opt.step()
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                steps.append({"step": i + 1, "batch": batch_size,
                              "inputTokens": int(enc["input_ids"].shape[1]),
                              "targetTokens": int(lab.shape[1]),
                              "targetIds": [r["id"] for r in batch],
                              "loss": round(float(out.loss), 4),
                              "seconds": round(time.perf_counter() - t, 3),
                              "peakAllocatedGB": round(
                                  torch.cuda.max_memory_allocated() / 1024 ** 3, 3)
                              if torch.cuda.is_available() else None})
            break
        except RuntimeError as exc:
            if "out of memory" not in str(exc).lower():
                raise
            tried.append({"batch": batch_size, "oom": True})
            torch.cuda.empty_cache()
            batch_size //= 2
            if batch_size < 1:
                report["trainSteps"] = {"steps": steps, "oomAt": tried,
                                        "status": "no batch size fits"}
                pathlib.Path(args.out).write_text(
                    json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
                return 2
    report["trainSteps"] = {"steps": steps, "oomAt": tried,
                            "batchSizeUsed": batch_size}

    # ---- save, reload, compare one step
    ck = pathlib.Path(args.out).with_suffix(".ckpt")
    model.save_pretrained(str(ck))
    tok.save_pretrained(str(ck))
    ref = {k: v.detach().clone() for k, v in model.state_dict().items()}
    model2 = T5ForConditionalGeneration.from_pretrained(str(ck),
                                                        torch_dtype=torch.float32).to(device)
    same = all(torch.equal(ref[k], model2.state_dict()[k]) for k in ref)
    model2.eval()
    batch = pool[:batch_size or 1]
    enc, labels = encode_training_batch(tok, batch)
    enc = {k: v.to(device) for k, v in enc.items()}
    with torch.inference_mode():
        loss_reload = float(model2(**enc, labels=labels.input_ids.to(device)).loss)
    model.eval()
    with torch.inference_mode():
        loss_same = float(model(**enc, labels=labels.input_ids.to(device)).loss)
    report["saveReload"] = {"path": str(ck), "weightsBitEqual": same,
                            "lossReloaded": round(loss_reload, 4),
                            "lossInMemory": round(loss_same, 4),
                            "lossDelta": round(abs(loss_reload - loss_same), 6)}

    # ---- generate again after the smoke steps (may or may not reach EOS)
    enc1 = tok(short["input"], return_tensors="pt", truncation=False).to(device)
    after, meta3 = generate_greedy(model, enc1, args.timeout)
    report["generateAfterSteps"] = {"stopReason": meta3["stopReason"],
                                    "complete": meta3["complete"],
                                    "newTokens": meta3["newTokens"],
                                    "seconds": meta3["seconds"],
                                    "text": tok.decode(after[0], skip_special_tokens=True)[:160]}

    # ---- the base on disk must still be untouched
    fresh = T5ForConditionalGeneration.from_pretrained(args.base,
                                                       torch_dtype=torch.float32)
    k0 = next(iter(fresh.state_dict()))
    report["baseUntouched"] = {
        "key": k0,
        "matchesDisk": torch.equal(fresh.state_dict()[k0],
                                   T5ForConditionalGeneration.from_pretrained(
                                       args.base).state_dict()[k0]),
        "weightsSha16": sha16(pathlib.Path(args.base) / "model.safetensors"),
    }

    pathlib.Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ("encoding", "trainSteps", "saveReload", "generateEosOnBase",
                       "timeoutOnBase", "generateAfterSteps", "baseUntouched")},
                     ensure_ascii=False)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
