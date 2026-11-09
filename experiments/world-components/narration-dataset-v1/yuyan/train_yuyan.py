# -*- coding: utf-8 -*-
"""Fine-tune YuYan-700M on the narration rows, full parameters or LoRA.

The checkpoint is a fairseq TransformerDecoder; there is no HuggingFace model
for it, so the module below is written out by hand from the shapes the
converter printed (36 layers, d_model 1280, 20 heads, ffn 5120, pre-norm,
GELU, sinusoidal positions, embeddings scaled by sqrt(d_model), separate
output projection).

Training shape: one sequence per row

  xProse  +  yMarked  +  </s>

with the loss taken only on yMarked and the end token, so the model learns
"given this state, write this narrative" rather than "continue anything".

  python train_yuyan.py --mode lora|full --epochs 6 --out run-lora
"""

import argparse
import io
import json
import math
import os
import pickle
import random
import time

import torch
import torch.nn as nn
import torch.nn.functional as F

SPECIAL = ["<s>", "<pad>", "</s>", "<unk>"]
PARA_MARK = "※"


# ---------------------------------------------------------------- checkpoint

class _Stub:
    def __init__(self, *a, **k):
        pass

    def __setstate__(self, state):
        if isinstance(state, dict):
            self.__dict__.update(state)


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module.split(".")[0] in ("fairseq", "omegaconf"):
            return type(name, (_Stub,), {})
        return super().find_class(module, name)


class _PickleModule:
    Unpickler = _Unpickler

    @staticmethod
    def load(handle, **kwargs):
        return _Unpickler(handle).load()


def load_checkpoint(path):
    return torch.load(path, map_location="cpu", weights_only=False,
                      pickle_module=_PickleModule)


def load_vocab(path):
    with io.open(path, encoding="utf-8") as handle:
        entries = [line.split(" ")[0] for line in handle.read().split("\n") if line.strip()]
    return SPECIAL + entries


# ------------------------------------------------------------------- module

def sinusoidal_positions(length, dim, device):
    half = dim // 2
    rate = math.log(10000) / (half - 1)
    rate = torch.exp(torch.arange(half, dtype=torch.float32, device=device) * -rate)
    pos = torch.arange(length, dtype=torch.float32, device=device).unsqueeze(1) * rate.unsqueeze(0)
    emb = torch.cat([torch.sin(pos), torch.cos(pos)], dim=1)
    if dim % 2:
        emb = torch.cat([emb, torch.zeros(length, 1, device=device)], dim=1)
    return emb


class Block(nn.Module):
    def __init__(self, dim, heads, ffn):
        super().__init__()
        self.heads = heads
        self.head_dim = dim // heads
        self.attn_norm = nn.LayerNorm(dim, eps=1e-5)
        self.q = nn.Linear(dim, dim)
        self.k = nn.Linear(dim, dim)
        self.v = nn.Linear(dim, dim)
        self.o = nn.Linear(dim, dim)
        self.ffn_norm = nn.LayerNorm(dim, eps=1e-5)
        self.fc1 = nn.Linear(dim, ffn)
        self.fc2 = nn.Linear(ffn, dim)

    def forward(self, x, mask):
        batch, length, dim = x.shape
        h = self.attn_norm(x)
        q = self.q(h).view(batch, length, self.heads, self.head_dim).transpose(1, 2)
        k = self.k(h).view(batch, length, self.heads, self.head_dim).transpose(1, 2)
        v = self.v(h).view(batch, length, self.heads, self.head_dim).transpose(1, 2)
        attn = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
        attn = attn.transpose(1, 2).reshape(batch, length, dim)
        x = x + self.o(attn)
        h = self.ffn_norm(x)
        return x + self.fc2(F.gelu(self.fc1(h)))


class YuYan(nn.Module):
    def __init__(self, layers, dim, heads, ffn, vocab):
        super().__init__()
        self.dim = dim
        self.embed = nn.Embedding(vocab, dim)
        self.blocks = nn.ModuleList(Block(dim, heads, ffn) for _ in range(layers))
        self.norm = nn.LayerNorm(dim, eps=1e-5)
        self.head = nn.Linear(dim, vocab, bias=False)

    def forward(self, tokens):
        length = tokens.shape[1]
        x = self.embed(tokens) * math.sqrt(self.dim)
        x = x + sinusoidal_positions(length, self.dim, tokens.device)
        mask = torch.ones(length, length, dtype=torch.bool, device=tokens.device).tril()
        for block in self.blocks:
            x = block(x, mask)
        return self.head(self.norm(x))


def build_from_state(state, heads=None):
    vocab = state["decoder.embed_tokens.weight"].shape[0]
    index = 0
    while f"decoder.layers.{index}.self_attn.q_proj.weight" in state:
        index += 1
    dim = state["decoder.embed_tokens.weight"].shape[1]
    ffn = state["decoder.layers.0.fc1.weight"].shape[0]
    heads = heads or 20
    model = YuYan(index, dim, heads, ffn, vocab)
    with torch.no_grad():
        model.embed.weight.copy_(state["decoder.embed_tokens.weight"])
        model.norm.weight.copy_(state["decoder.layer_norm.weight"])
        model.norm.bias.copy_(state["decoder.layer_norm.bias"])
        model.head.weight.copy_(state["decoder.output_projection.weight"])
        for i, block in enumerate(model.blocks):
            p = f"decoder.layers.{i}."
            block.attn_norm.weight.copy_(state[p + "self_attn_layer_norm.weight"])
            block.attn_norm.bias.copy_(state[p + "self_attn_layer_norm.bias"])
            block.q.weight.copy_(state[p + "self_attn.q_proj.weight"])
            block.q.bias.copy_(state[p + "self_attn.q_proj.bias"])
            block.k.weight.copy_(state[p + "self_attn.k_proj.weight"])
            block.k.bias.copy_(state[p + "self_attn.k_proj.bias"])
            block.v.weight.copy_(state[p + "self_attn.v_proj.weight"])
            block.v.bias.copy_(state[p + "self_attn.v_proj.bias"])
            block.o.weight.copy_(state[p + "self_attn.out_proj.weight"])
            block.o.bias.copy_(state[p + "self_attn.out_proj.bias"])
            block.ffn_norm.weight.copy_(state[p + "final_layer_norm.weight"])
            block.ffn_norm.bias.copy_(state[p + "final_layer_norm.bias"])
            block.fc1.weight.copy_(state[p + "fc1.weight"])
            block.fc1.bias.copy_(state[p + "fc1.bias"])
            block.fc2.weight.copy_(state[p + "fc2.weight"])
            block.fc2.bias.copy_(state[p + "fc2.bias"])
    return model, {"layers": index, "dim": dim, "heads": heads, "ffn": ffn, "vocab": vocab}


# ---------------------------------------------------------------------- LoRA

class LoRALinear(nn.Module):
    def __init__(self, base, rank, alpha):
        super().__init__()
        self.base = base
        for parameter in self.base.parameters():
            parameter.requires_grad = False
        self.down = nn.Linear(base.in_features, rank, bias=False)
        self.up = nn.Linear(rank, base.out_features, bias=False)
        nn.init.kaiming_uniform_(self.down.weight, a=math.sqrt(5))
        nn.init.zeros_(self.up.weight)
        self.scale = alpha / rank

    def forward(self, x):
        return self.base(x) + self.up(self.down(x)) * self.scale


def apply_lora(model, rank, alpha, targets=("q", "k", "v", "o", "fc1", "fc2")):
    # Freeze the WHOLE backbone first: embeddings, output projection and every
    # LayerNorm stay untouched. Only the injected down/up matrices train.
    for parameter in model.parameters():
        parameter.requires_grad = False
    for block in model.blocks:
        for name in targets:
            module = getattr(block, name)
            setattr(block, name, LoRALinear(module, rank, alpha))
    return model


# -------------------------------------------------------------------- tokens

def encode(text, vocab_index):
    ids = []
    for char in text:
        if char not in vocab_index:
            raise SystemExit(f"character not in vocabulary: {char!r} in {text[:40]!r}")
        ids.append(vocab_index[char])
    return ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="rows-yuyan.jsonl")
    parser.add_argument("--base", required=True, help="checkpoint_best.pt")
    parser.add_argument("--dict", required=True, help="dict.txt")
    parser.add_argument("--out", required=True)
    parser.add_argument("--mode", choices=("lora", "full"), default="lora")
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--alpha", type=int, default=32)
    parser.add_argument("--max-len", type=int, default=2048)
    parser.add_argument("--holdout", default="row-0010,row-0017")
    parser.add_argument("--split-file", default="",
                        help="frozen train/dev/test split from make_split.py; dev picks the "
                             "epoch and test is scored once at the end")
    parser.add_argument("--dev-limit", type=int, default=0,
                        help="cap the dev rows evaluated per epoch (0 = all)")
    parser.add_argument("--seed", type=int, default=20261109)
    parser.add_argument("--sample-every", type=int, default=2)
    parser.add_argument("--save", action="store_true",
                        help="write the LoRA adapter or the full state dict")
    parser.add_argument("--retention-file", default="",
                        help="a plain-prose prompt; generated before and after training "
                             "to see whether the base narrative ability survived")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    if not torch.cuda.is_available():
        raise SystemExit("no CUDA device")
    device = "cuda"
    torch.manual_seed(args.seed)
    random.seed(args.seed)

    tokens = load_vocab(args.dict)
    index = {char: i for i, char in enumerate(tokens)}
    eos = index["</s>"]

    started = time.time()
    checkpoint = load_checkpoint(args.base)
    config = checkpoint.get("cfg", {}).get("model", {}) or {}
    model, shape = build_from_state(checkpoint["model"],
                                    heads=config.get("decoder_attention_heads"))
    del checkpoint
    model = model.to(device)
    params = sum(p.numel() for p in model.parameters())
    print(f"loaded: {shape} params={params/1e6:.1f}M "
          f"({round(time.time() - started, 1)}s)", flush=True)

    if args.mode == "lora":
        model = apply_lora(model, args.rank, args.alpha).to(device)
        trainable = [p for p in model.parameters() if p.requires_grad]
    else:
        trainable = [p for p in model.parameters() if p.requires_grad]
    trainable_params = sum(p.numel() for p in trainable)
    print(f"mode={args.mode} trainable={trainable_params/1e6:.2f}M", flush=True)

    rows = [json.loads(line) for line in io.open(args.data, encoding="utf-8")]
    if args.split_file:
        split = json.load(io.open(args.split_file, encoding="utf-8"))
        dev_ids, test_ids = set(split["dev"]), set(split["test"])
        train_rows = [r for r in rows if r["id"] in set(split["train"])]
        dev_rows = [r for r in rows if r["id"] in dev_ids]
        test_rows = [r for r in rows if r["id"] in test_ids]
        hold_rows = dev_rows
        print(f"split: train {len(train_rows)} dev {len(dev_rows)} "
              f"test {len(test_rows)}", flush=True)
    else:
        holdout = {v.strip() for v in args.holdout.split(",")}
        train_rows = [r for r in rows if r["id"] not in holdout]
        hold_rows = [r for r in rows if r["id"] in holdout]
        dev_rows, test_rows = hold_rows, []

    def pack(row):
        """Causal LM: the label at position i is the token at i+1, never the token
        the model was just handed. Getting this wrong lets the model copy its own
        input and the loss falls to zero without learning anything."""
        prompt = encode(row["xProse"], index)
        target = encode(row["yMarked"], index) + [eos]
        ids = (prompt + target)[:args.max_len + 1]
        labels = [-100] * (len(prompt) - 1) + ids[len(prompt):]
        return ids[:-1], labels

    optimizer = torch.optim.AdamW(trainable, lr=args.lr, weight_decay=0.0)

    def evaluate(subset):
        model.eval()
        total, count = 0.0, 0
        with torch.no_grad():
            for row in subset:
                ids, labels = pack(row)
                x = torch.tensor([ids], device=device)
                y = torch.tensor([labels], device=device)
                logits = model(x)[0]
                loss = F.cross_entropy(logits.view(-1, shape["vocab"]), y.view(-1),
                                       ignore_index=-100, reduction="sum")
                tokens_seen = int((y != -100).sum())
                total += loss.item()
                count += tokens_seen
        model.train()
        return round(total / max(count, 1), 4)

    def generate_text(prompt, max_new, temperature, seed):
        """Free-form continuation, used for the retention check."""
        print(f"  retention: generating {max_new} tokens", flush=True)
        torch.manual_seed(seed)
        ids = encode(prompt, index)
        x = torch.tensor([ids], device=device)
        model.eval()
        with torch.no_grad():
            for step in range(max_new):
                if step and step % 20 == 0:
                    print(f"    {step}/{max_new}", flush=True)
                logits = model(x[:, -args.max_len:])[0, -1].clone()
                logits[eos] = -1e9
                if temperature == 0:
                    nxt = int(logits.argmax())
                else:
                    probs = torch.softmax(logits / temperature, dim=-1)
                    nxt = int(torch.multinomial(probs, 1))
                x = torch.cat([x, torch.tensor([[nxt]], device=device)], dim=1)
        model.train()
        return "".join(tokens[i] for i in x[0, len(ids):].tolist())

    def generate(row, max_new=400, temperature=0.0, min_new=16):
        model.eval()
        ids = encode(row["xProse"], index)
        x = torch.tensor([ids], device=device)
        with torch.no_grad():
            for _ in range(max_new):
                logits = model(x[:, -args.max_len:])[0, -1].clone()
                produced = x.shape[1] - len(ids)
                if produced < min_new:
                    logits[eos] = -1e9
                if temperature == 0:
                    nxt = int(logits.argmax())
                else:
                    probs = torch.softmax(logits / temperature, dim=-1)
                    nxt = int(torch.multinomial(probs, 1))
                if nxt == eos:
                    break
                x = torch.cat([x, torch.tensor([[nxt]], device=device)], dim=1)
        text = "".join(tokens[i] for i in x[0, len(ids):].tolist())
        model.train()
        return text.replace(PARA_MARK, "\n\n")

    retention = {"prompt": "", "before": "", "after": ""}
    if args.retention_file:
        retention["prompt"] = io.open(args.retention_file, encoding="utf-8").read().strip()
        retention["before"] = generate_text(retention["prompt"], 80, 0.8, 42)
        print(f"retention before: {retention['before'][:80]}", flush=True)

    print("  evaluating holdout and 20 training rows", flush=True)
    print(f"before training: holdout {evaluate(hold_rows)} "
          f"train20 {evaluate(train_rows[:20])} "
          f"(random would be ln(13672)={math.log(shape['vocab']):.2f})", flush=True)

    history = []
    best = {"devLoss": float("inf"), "epoch": 0, "state": None}
    for epoch in range(1, args.epochs + 1):
        random.shuffle(train_rows)
        total, steps = 0.0, 0
        batch_ids, batch_labels = [], []

        def flush():
            nonlocal total, steps, batch_ids, batch_labels
            if not batch_ids:
                return
            width = max(len(item) for item in batch_ids)
            x = torch.full((len(batch_ids), width), index["<pad>"], device=device)
            y = torch.full((len(batch_ids), width), -100, device=device)
            for row, (ids, labels) in enumerate(zip(batch_ids, batch_labels)):
                x[row, :len(ids)] = torch.tensor(ids, device=device)
                y[row, :len(labels)] = torch.tensor(labels, device=device)
            logits = model(x)
            loss = F.cross_entropy(logits.view(-1, shape["vocab"]), y.view(-1),
                                   ignore_index=-100)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            total += loss.item()
            steps += 1
            batch_ids, batch_labels = [], []

        for row in train_rows:
            ids, labels = pack(row)
            batch_ids.append(ids)
            batch_labels.append(labels)
            if len(batch_ids) == args.batch:
                flush()
        flush()
        evaluate_rows = dev_rows if not args.dev_limit else dev_rows[:args.dev_limit]
        dev_loss = evaluate(evaluate_rows)
        entry = {"epoch": epoch, "loss": round(total / max(steps, 1), 4),
                 "holdoutLoss": dev_loss,
                 "devLoss": dev_loss,
                 "trainLoss": evaluate(train_rows[:20]),
                 "peakMb": round(torch.cuda.max_memory_allocated() / 1048576)}
        history.append(entry)
        if dev_loss < best["devLoss"]:
            best = {"devLoss": dev_loss, "epoch": epoch,
                    "state": {name: tensor.detach().clone()
                              for name, tensor in model.named_parameters()
                              if tensor.requires_grad}}
        print(f"epoch {epoch} loss {entry['loss']} dev {dev_loss} "
              f"train20 {entry['trainLoss']} peak {entry['peakMb']}MB "
              f"({round(time.time() - started, 1)}s)"
              + ("  <= best" if best["epoch"] == epoch else ""), flush=True)
        if epoch % args.sample_every == 0 or epoch == args.epochs:
            for row in hold_rows[:1]:
                text = generate(row)
                print(f"  sample {row['id']} ({len(text)} chars): {text[:120]}", flush=True)

    if best["state"] and best["epoch"] < args.epochs:
        own = dict(model.named_parameters())
        with torch.no_grad():
            for name, tensor in best["state"].items():
                own[name].copy_(tensor)
        print(f"reloaded epoch {best['epoch']} weights (best dev {best['devLoss']})",
              flush=True)
    test_loss = evaluate(test_rows) if test_rows else None
    print(f"best dev {best['devLoss']} @ epoch {best['epoch']} | test {test_loss}",
          flush=True)

    if args.retention_file:
        retention["after"] = generate_text(retention["prompt"], 80, 0.8, 42)
        print(f"retention after: {retention['after'][:80]}", flush=True)

    if args.save:
        if args.mode == "lora":
            # Save every tensor that actually trained, whatever its name, so the
            # file on disk can reproduce the model that was evaluated.
            adapter = {name: tensor.detach().cpu()
                       for name, tensor in model.named_parameters()
                       if tensor.requires_grad}
            torch.save(adapter, os.path.join(args.out, "lora_adapter.pt"))
            print(f"saved {len(adapter)} adapter tensors "
                  f"({sum(t.numel() for t in adapter.values())/1e6:.2f}M)", flush=True)
        else:
            torch.save(model.state_dict(), os.path.join(args.out, "full_state.pt"))
            print("saved full_state.pt", flush=True)

    samples = []
    for row in hold_rows[:3] + test_rows[:2] + train_rows[:1]:
        greedy = generate(row)
        sampled = generate(row, temperature=0.8)
        samples.append({"id": row["id"], "trainedOnThisRow": row in train_rows,
                        "targetChars": len(row["yMarked"]),
                        "greedy": greedy, "sampled": sampled})
        io.open(os.path.join(args.out, "samples.txt"), "w", encoding="utf-8").write(
            "\n\n".join(f"=== {s['id']} trained={s['trainedOnThisRow']} "
                        f"target={s['targetChars']}\n-- greedy --\n{s['greedy']}\n"
                        f"-- sampled --\n{s['sampled']}" for s in samples))

    report = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": args.mode, "shape": shape, "params": params,
        "trainableParams": trainable_params,
        "hyper": {k: v for k, v in vars(args).items() if k != "base"},
        "rows": len(rows), "trainRows": len(train_rows),
        "holdout": sorted(dev_ids) if args.split_file else sorted(holdout),
        "devRows": len(dev_rows), "testRows": len(test_rows),
        "bestDev": best["devLoss"], "bestEpoch": best["epoch"],
        "testLoss": test_loss,
        "history": history, "samples": samples, "retention": retention,
        "seconds": round(time.time() - started, 1),
    }
    with io.open(os.path.join(args.out, "report.json"), "w", encoding="utf-8",
                 newline="\n") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"mode": args.mode, "bestDev": best["devLoss"], "bestEpoch":
                      best["epoch"], "testLoss": test_loss,
                      "seconds": report["seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
