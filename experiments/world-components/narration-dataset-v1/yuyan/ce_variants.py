"""Does the training loss separate a correct narration from a wrong one?

For every test row we compute the same per-token cross entropy that training
reports, on five versions of the target:

  reference        the human narration (what training optimises against)
  swap_actors      the same text with two character names exchanged
  add_event        the same text plus one sentence about an event that never
                   happened in this round
  drop_last_para   the same text with the final paragraph removed
  self_greedy      the model's own greedy output

If reference is not clearly below swap_actors / add_event, then dev loss can
only rank epochs, never judge whether a narration is right. That is the claim
this script is built to test, and it reports the raw numbers either way.

Usage (cluster):
  python -X utf8 ce_variants.py --data rows-yuyan.jsonl --split splits/v1.json \
      --base checkpoint_best.pt --dict dict.txt \
      --adapter yu-split-6ep/lora_adapter.pt --out ce-variants.json
"""
import argparse
import io
import json
import os
import statistics

import torch

import train_yuyan as T

INVENTED = "那天夜里，他把一把钥匙沉进了院子的井里，第二天谁也没提起。"


def per_token_ce(model, prompt_len, target_ids, device, vocab):
    ids = target_ids
    x = torch.tensor([ids[:-1]], device=device)
    labels = torch.tensor([[-100] * (prompt_len - 1) + ids[prompt_len:]], device=device)
    with torch.no_grad():
        logits = model(x)[0].float()
    mask = labels[0] != -100
    if int(mask.sum()) == 0:
        return None
    logp = torch.log_softmax(logits[mask], dim=-1)
    picked = logp.gather(1, labels[0][mask].unsqueeze(1)).squeeze(1)
    return float(-picked.mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="rows-yuyan.jsonl")
    ap.add_argument("--split", default="splits/v1.json")
    ap.add_argument("--base", default="checkpoint_best.pt")
    ap.add_argument("--dict", default="dict.txt")
    ap.add_argument("--adapter", default="")
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--out", default="ce-variants.json")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokens = T.load_vocab(args.dict)
    index = {c: i for i, c in enumerate(tokens)}
    eos = index["</s>"]

    ck = T.load_checkpoint(args.base)
    model, shape = T.build_from_state(ck["model"], heads=20)
    del ck
    model = model.to(device)
    if args.adapter:
        model = T.apply_lora(model, args.rank, args.alpha).to(device)
        adapter = torch.load(args.adapter, map_location="cpu", weights_only=True)
        own = dict(model.named_parameters())
        with torch.no_grad():
            for name, tensor in adapter.items():
                own[name].copy_(tensor.to(device))
        print(f"adapter {len(adapter)} tensors", flush=True)
    model.eval()

    rows = [json.loads(line) for line in io.open(args.data, encoding="utf-8")]
    split = json.load(io.open(args.split, encoding="utf-8"))
    test_ids = set(split["test"])
    picked = [r for r in rows if r["id"] in test_ids]
    print(f"test rows: {len(picked)}", flush=True)

    def encode(text):
        return T.encode(text.replace("\n\n", T.PARA_MARK).replace("\n", ""), index)

    results = []
    for row in picked:
        state = json.loads(row["xJson"])
        people = list(state["上回合状态"]["人物"])
        prompt = T.encode(row["xProse"], index)
        reference = row["yMarked"]

        a, b = (people + people[:1])[:2]
        swapped = reference.replace(a, "\u0000").replace(b, a).replace("\u0000", b)

        paras = reference.split(T.PARA_MARK)
        dropped = T.PARA_MARK.join(paras[:-1]) if len(paras) > 1 else reference
        invented = reference + T.PARA_MARK + INVENTED

        variants = {
            "reference": reference,
            "swap_actors": swapped,
            "add_event": invented,
            "drop_last_para": dropped,
        }
        scores = {}
        for name, text in variants.items():
            target = encode(text) + [eos]
            ce = per_token_ce(model, len(prompt), prompt + target, device, shape["vocab"])
            scores[name] = None if ce is None else round(ce, 4)

        greedy = generate(model, prompt, tokens, index, eos, 260, device)
        self_ids = encode(greedy) + [eos]
        ce = per_token_ce(model, len(prompt), prompt + self_ids, device, shape["vocab"])
        scores["self_greedy"] = None if ce is None else round(ce, 4)
        scores["self_chars"] = len(greedy)

        results.append({"id": row["id"], "scores": scores})
        print(f"{row['id']}: " + "  ".join(f"{k} {v}" for k, v in scores.items()), flush=True)

    names = ["reference", "swap_actors", "add_event", "drop_last_para", "self_greedy"]
    summary = {}
    for name in names:
        values = [r["scores"][name] for r in results if r["scores"].get(name) is not None]
        summary[name] = {"mean": round(statistics.mean(values), 4),
                         "median": round(statistics.median(values), 4),
                         "n": len(values)}
    wins = {
        "reference_below_swap": sum(
            1 for r in results
            if r["scores"]["reference"] is not None
            and r["scores"]["swap_actors"] is not None
            and r["scores"]["reference"] < r["scores"]["swap_actors"]),
        "reference_below_add_event": sum(
            1 for r in results
            if r["scores"]["reference"] is not None
            and r["scores"]["add_event"] is not None
            and r["scores"]["reference"] < r["scores"]["add_event"]),
        "reference_below_drop": sum(
            1 for r in results
            if r["scores"]["reference"] is not None
            and r["scores"]["drop_last_para"] is not None
            and r["scores"]["reference"] < r["scores"]["drop_last_para"]),
        "total": len(results),
    }
    payload = {"rows": results, "summary": summary, "wins": wins}
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
    print("\nsummary", json.dumps(summary, ensure_ascii=False))
    print("wins", json.dumps(wins, ensure_ascii=False))


def generate(model, prompt, tokens, index, eos, max_new, device):
    x = torch.tensor([prompt], device=device)
    with torch.no_grad():
        for _ in range(max_new):
            logits = model(x[:, -2048:])[0, -1].clone()
            logits[eos] = -1e9
            nxt = int(logits.argmax())
            x = torch.cat([x, torch.tensor([[nxt]], device=device)], dim=1)
    return "".join(tokens[i] for i in x[0, len(prompt):].tolist())


if __name__ == "__main__":
    main()
