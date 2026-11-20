"""Measure what the holdout loss actually measures.

For one holdout row we compute the per-token cross entropy (the number every
training run reports as "holdout loss") under the fine-tuned model for:

  1. the human reference narration,
  2. the model's own generated narration (judged readable by us),
  3. the same narration with one actor swapped (a hard factual error),
  4. the same narration with one extra invented event.

If (2) is not clearly better than (3) and (4), then the holdout loss cannot
rank "good narration" above "wrong narration", and every epoch decision based
on it has been unfounded.

Usage:
  python -X utf8 ce_probe.py --adapter D:/others/Jity/.local/yuyan/lora_6ep.pt \
      --row row-0017
"""
import argparse
import io
import json
import math
import os
import sys

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import train_yuyan as T  # noqa: E402


def per_token_ce(model, ids, prompt_len, device):
    """Cross entropy of the target part only, same masking as training."""
    x = torch.tensor([ids[:-1]], device=device)
    labels = torch.tensor([[-100] * (prompt_len - 1) + ids[prompt_len:]], device=device)
    with torch.no_grad():
        logits = model(x)
    shift_logits = logits[0].float()
    shift_labels = labels[0]
    mask = shift_labels != -100
    if mask.sum() == 0:
        return float("nan"), 0
    logp = torch.log_softmax(shift_logits[mask], dim=-1)
    picked = logp.gather(1, shift_labels[mask].unsqueeze(1)).squeeze(1)
    return float(-picked.mean()), int(mask.sum())


def build_ids(vocab_index, prompt, target, eos):
    p = T.encode(prompt, vocab_index)
    t = T.encode(target, vocab_index)
    return p + t + [eos], len(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="D:/others/Jity/.local/yuyan/checkpoint_best.pt")
    ap.add_argument("--dict", default="D:/others/Jity/.local/yuyan/dict.txt")
    ap.add_argument("--adapter", default="D:/others/Jity/.local/yuyan/lora_6ep.pt")
    ap.add_argument("--rows", default="yuyan/rows-yuyan.jsonl")
    ap.add_argument("--row", default="row-0017")
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokens = T.load_vocab(args.dict)
    vocab_index = {c: i for i, c in enumerate(tokens)}
    eos = vocab_index["</s>"]

    ck = T.load_checkpoint(args.base)
    model, _ = T.build_from_state(ck["model"], heads=20)
    del ck
    model = model.to(device)
    if args.adapter:
        model = T.apply_lora(model, args.rank, args.alpha).to(device)
        adapter = torch.load(args.adapter, map_location="cpu", weights_only=True)
        own = dict(model.named_parameters())
        missing = [n for n in adapter if n not in own]
        if missing:
            raise SystemExit(f"adapter keys not found in model: {missing[:3]}")
        with torch.no_grad():
            for name, tensor in adapter.items():
                own[name].copy_(tensor.to(device))
        print(f"loaded adapter {len(adapter)} tensors "
              f"({sum(t.numel() for t in adapter.values())/1e6:.2f}M)", flush=True)
    model.eval()

    rows = {json.loads(line)["id"]: json.loads(line)
            for line in io.open(args.rows, encoding="utf-8")}
    row = rows[args.row]
    prompt = row["xProse"]
    reference = row["yMarked"]

    names = list(json.loads(row["xJson"])["上回合状态"]["人物"])
    a, b = names[0], names[1] if len(names) > 1 else names[0]
    swapped = reference.replace(a, "\u0000").replace(b, a).replace("\u0000", b)
    invented = reference.rstrip().rstrip("」") + "「那一年冬天，他把钥匙沉进了井里。」"

    samples = []
    probe = os.path.join(os.path.dirname(HERE), "hpc", "runs", "report-250367.json")
    if os.path.exists(probe):
        report = json.load(io.open(probe, encoding="utf-8"))
        for entry in report.get("samples", []):
            if entry["id"] == args.row:
                samples.append(("模型自己写的·贪心", entry["greedy"]))
                samples.append(("模型自己写的·采样", entry["sampled"]))

    cases = [("人工参照（训练时比的就是它）", reference),
             ("人物对调（事实错误）", swapped),
             ("硬加一件没发生的事（事实错误）", invented)]
    cases += samples

    print(f"\nrow {args.row}  参照 {len(reference)} 字")
    for label, text in cases:
        # generated samples come back with real newlines; the vocab has none
        norm = text.replace("\n\n", T.PARA_MARK).replace("\n", "")
        try:
            ids, plen = build_ids(vocab_index, prompt, norm, eos)
        except KeyError as exc:
            print(f"  {label}: 字符不在词表 {exc}")
            continue
        ce, n = per_token_ce(model, ids, plen, device)
        print(f"  {label}: CE {ce:.4f}  （{n} 个目标 token，{len(norm)} 字）", flush=True)


if __name__ == "__main__":
    main()
