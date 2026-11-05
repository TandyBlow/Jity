"""Locate where the group arm starts repeating, and check the decode path.

For every selected cf24 source it runs the same group composition as the arm,
but records the chosen token and the top-5 logits at every step. It then:
  * marks the first step whose 4-token window already occurred earlier
  * re-runs the same decoder prefix without cache and compares the next-token
    distribution with the cached step
  * records the EOS rank before and after the onset
  * checks whether the looped text occurs in any training target
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


def generate_traced(model, tok, encoded, budget, max_steps=400):
    cfg = model.generation_config
    start = cfg.decoder_start_token_id if cfg.decoder_start_token_id is not None \
        else model.config.decoder_start_token_id
    eos = cfg.eos_token_id if cfg.eos_token_id is not None else model.config.eos_token_id
    started = time.perf_counter()
    cur = torch.full((1, 1), start, dtype=torch.long,
                     device=encoded["input_ids"].device)
    toks, steps, past = [start], [], None
    reason = "timeout"
    with torch.inference_mode():
        enc_out = model.get_encoder()(**encoded, return_dict=True)
        while time.perf_counter() - started < budget and len(toks) < max_steps:
            out = model(encoder_outputs=enc_out,
                        attention_mask=encoded.get("attention_mask"),
                        decoder_input_ids=cur, past_key_values=past,
                        use_cache=True, return_dict=True)
            logits = out.logits[0, -1]
            top = torch.topk(logits, 5)
            nxt = int(top.indices[0])
            eos_rank = int((logits > logits[eos]).sum()) + 1
            steps.append({"step": len(toks), "token": nxt,
                          "top5": [int(x) for x in top.indices],
                          "eosLogit": round(float(logits[eos]), 3),
                          "eosRank": eos_rank})
            past = out.past_key_values
            cur = torch.tensor([[nxt]], device=cur.device)
            toks.append(nxt)
            if nxt == eos:
                reason = "eos"
                break
    return toks, steps, reason, enc_out


def first_repeat(tokens, k=4):
    seen = {}
    for i in range(len(tokens) - k + 1):
        win = tuple(tokens[i:i + k])
        if win in seen:
            return seen[win], i
        seen[win] = i
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--sources", default="all")
    ap.add_argument("--deep", default="t01,t16,t20,t24,t05,t19")
    ap.add_argument("--budget", type=float, default=20.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tok = T5Tokenizer.from_pretrained(args.ckpt, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(
        args.ckpt, torch_dtype=torch.float32)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()

    plan = json.loads(pathlib.Path(args.plan).read_text(encoding="utf-8"))
    targets = [u["target"] for u in plan["units"] if u["target"]]
    groups = {}
    for u in plan["cf24Groups"]:
        groups.setdefault(u["sourceId"], []).append(u)
    picked = sorted(groups) if args.sources == "all" else args.sources.split(",")
    deep = set(args.deep.split(","))

    rows = []
    for sid in picked:
        src = groups[sid]
        started = time.perf_counter()
        text, all_steps, per_group = [], [], []
        for g in src:
            enc = tok(g["input"], return_tensors="pt", truncation=False).to(device)
            toks, steps, reason, enc_out = generate_traced(
                model, tok, enc, args.budget - (time.perf_counter() - started))
            piece = tok.decode(toks[1:], skip_special_tokens=True)
            first, second = first_repeat([t for t in toks[1:-1]] or toks[1:])
            rec = {"groupId": g["groupId"], "factIds": g["factIds"],
                   "tokens": len(toks) - 1, "stopReason": reason,
                   "firstRepeatStarts": first, "repeatsAt": second,
                   "text": piece}
            if sid in deep and second is not None:
                # second 是 produced 列表里的下标；产生它的那一步输入是
                # [start] + produced[:second]，两路前向必须用同一个输入。
                prefix = toks[:second + 1]
                dec = torch.tensor([prefix], device=device)
                with torch.inference_mode():
                    full = model(encoder_outputs=enc_out,
                                 attention_mask=enc.get("attention_mask"),
                                 decoder_input_ids=dec, use_cache=False,
                                 return_dict=True)
                # 同一输入，一路带缓存、一路不带
                with torch.inference_mode():
                    o2 = model(encoder_outputs=enc_out,
                               attention_mask=enc.get("attention_mask"),
                               decoder_input_ids=dec, use_cache=True,
                               return_dict=True)
                cached_logits = o2.logits[0, -1]
                nc = full.logits[0, -1]
                rec["decodeCheck"] = {
                    "position": second,
                    "top1Same": int(cached_logits.argmax()) == int(nc.argmax()),
                    "maxAbsLogitDiff": round(float((cached_logits - nc).abs().max()), 5),
                    "cachedTop1": int(cached_logits.argmax()),
                    "nocacheTop1": int(nc.argmax()),
                    "eosRankCached": int((cached_logits > cached_logits[tok.eos_token_id]).sum()) + 1,
                    "eosRankNocache": int((nc > nc[tok.eos_token_id]).sum()) + 1,
                }
                loop_text = tok.decode(prefix[second - 3:second + 5],
                                       skip_special_tokens=True)
                rec["loopText"] = loop_text
                rec["loopInTrainingTarget"] = any(loop_text and loop_text in t
                                                  for t in targets)
            per_group.append(rec)
            text.append(piece)
            all_steps.append(steps)
        first_onset = min([g["firstRepeatStarts"] for g in per_group
                           if g["firstRepeatStarts"] is not None], default=None)
        rows.append({"sourceId": sid, "groups": per_group, "output": "".join(text),
                     "seconds": round(time.perf_counter() - started, 3),
                     "firstOnsetStep": first_onset})
        print(f"{sid} groups={len(per_group)} onset={first_onset} "
              f"secs={rows[-1]['seconds']}", flush=True)

    out = {"checkpoint": args.ckpt, "budget": args.budget, "rows": rows}
    pathlib.Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print("->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
