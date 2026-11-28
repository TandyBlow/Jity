# -*- coding: utf-8 -*-
"""Replacement layer: a tiny char-level seq2seq over local rewrite pairs
(E34's 22.6% replace operation). Held-out split by source hash; exact match
and charF1; the model is the second block of the edit pipeline."""
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn

HERE = Path(__file__).resolve().parent
PAIRS = HERE / 'replace-pairs-local.jsonl'
BOS, EOS, PAD = '\u0001', '\u0003', '\u0000'


def char_f1(a: str, b: str) -> float:
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    if not common:
        return 0.0
    precision = common / max(1, len(a))
    recall = common / max(1, len(b))
    return 2 * precision * recall / (precision + recall)


def main():
    pairs = [json.loads(l) for l in PAIRS.read_text(encoding='utf8').splitlines() if l.strip()]
    vocab = sorted({ch for p in pairs for ch in p['src'] + p['dst']})
    stoi = {ch: i for i, ch in enumerate([PAD, BOS, EOS] + vocab)}
    n = len(stoi)
    random.seed(20261128); torch.manual_seed(20261128)
    buckets = {}
    for p in pairs:
        key = hashlib.sha256(p['src'].encode('utf8')).hexdigest()[:8]
        buckets.setdefault(key, []).append(p)
    keys = sorted(buckets)
    hold = set(keys[:max(1, len(keys) // 5)])
    train = [p for k in keys if k not in hold for p in buckets[k]]
    test = [p for k in keys if k in hold for p in buckets[k]]

    d_model, heads = 64, 4
    max_src, max_dst = 12, 12
    class Seq2Seq(nn.Module):
        def __init__(self):
            super().__init__()
            self.src = nn.Embedding(n, d_model)
            self.tgt = nn.Embedding(n, d_model)
            self.pos = nn.Embedding(24, d_model)
            enc = nn.TransformerEncoderLayer(d_model, heads, 4 * d_model, batch_first=True, dropout=0.1)
            dec = nn.TransformerDecoderLayer(d_model, heads, 4 * d_model, batch_first=True, dropout=0.1)
            self.encoder = nn.TransformerEncoder(enc, 2)
            self.decoder = nn.TransformerDecoder(dec, 2)
            self.out = nn.Linear(d_model, n)
        def forward(self, src, tgt):
            pos = torch.arange(src.size(1)).unsqueeze(0)
            memory = self.encoder(self.src(src) + self.pos(pos))
            pos2 = torch.arange(tgt.size(1)).unsqueeze(0)
            mask = torch.triu(torch.ones(tgt.size(1), tgt.size(1)), diagonal=1).bool()
            h = self.decoder(self.tgt(tgt) + self.pos(pos2), memory, tgt_mask=mask)
            return self.out(h)

    net = Seq2Seq()
    print('params', sum(p.numel() for p in net.parameters()))
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3)
    lossf = nn.CrossEntropyLoss(ignore_index=stoi[PAD])
    for epoch in range(40):
        net.train(); random.shuffle(train); total = 0.0
        for p in train:
            src = torch.tensor([[stoi[ch] for ch in p['src'][:max_src]]])
            tgt = torch.tensor([[stoi[BOS]] + [stoi[ch] for ch in p['dst'][:max_dst - 1]] + [stoi[EOS]]])
            logits = net(src, tgt[:, :-1])
            loss = lossf(logits.reshape(-1, n), tgt[:, 1:].reshape(-1))
            opt.zero_grad(); loss.backward(); opt.step()
            total += float(loss)
        if epoch % 10 == 0:
            print(json.dumps({'epoch': epoch, 'loss': round(total / max(1, len(train)), 3)}))
    net.eval()
    exact, f1s = 0, []
    samples = []
    with torch.no_grad():
        for p in test:
            src = torch.tensor([[stoi[ch] for ch in p['src'][:max_src]]])
            memory = net.encoder(net.src(src) + net.pos(torch.arange(src.size(1)).unsqueeze(0)))
            out = [stoi[BOS]]
            for _ in range(max_dst):
                tgt = torch.tensor([out])
                pos2 = torch.arange(tgt.size(1)).unsqueeze(0)
                mask = torch.triu(torch.ones(tgt.size(1), tgt.size(1)), diagonal=1).bool()
                logits = net.out(net.decoder(net.tgt(tgt) + net.pos(pos2), memory, tgt_mask=mask))
                nxt = int(logits[0, -1].argmax())
                if nxt == stoi[EOS]:
                    break
                out.append(nxt)
            text = ''.join(k for k, v in stoi.items() if False) or ''.join(sorted(stoi)[0] for _ in [])
            inv = {v: k for k, v in stoi.items()}
            text = ''.join(inv.get(i, '') for i in out[1:])
            if text == p['dst']:
                exact += 1
            f1s.append(char_f1(text, p['dst']))
            if len(samples) < 8:
                samples.append((p['src'], p['dst'], text))
    summary = {'pairs': len(pairs), 'train': len(train), 'test': len(test),
               'params': sum(p.numel() for p in net.parameters()),
               'exactMatch': round(exact / max(1, len(test)), 3),
               'charF1Mean': round(sum(f1s) / max(1, len(f1s)), 3)}
    (HERE / 'rewrite-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))
    for src, dst, got in samples:
        print(f'{src} => {dst} | got {got}')


if __name__ == '__main__':
    main()
