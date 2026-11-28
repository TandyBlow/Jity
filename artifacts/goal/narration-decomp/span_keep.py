# -*- coding: utf-8 -*-
"""Edit decoder v1: a char-level keep/delete tagger over the selected clauses.
The output is by construction a subsequence of the facts (no invention), which
is what E33 failed at. Trained on oracle plans, grouped holdout by facts hash;
scored on charF1 and fidelity (plan coverage / inventions)."""
import hashlib
import json
import random
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import torch
import torch.nn as nn

ROOT = Path('D:/others/Jity')
HERE = Path(__file__).resolve().parent
PLAN = HERE / 'planning-examples-v2.jsonl'
SRC = ROOT / '.local/narr-train/sft-v13.jsonl'
PAD = '\u0000'


def strip_prefix(clause: str) -> str:
    body = re.sub(r'^玩家这回合.*?做的事：', '', clause)
    body = re.sub(r'^这一回合的结算结果：', '', body)
    body = re.sub(r'^[\u4e00-\u9fa5]{1,4}[：:]', '', body)
    return body.strip()


def char_f1(a: str, b: str) -> float:
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    if not common:
        return 0.0
    precision = common / max(1, len(a))
    recall = common / max(1, len(b))
    return 2 * precision * recall / (precision + recall)


def keep_mask(source: str, target: str):
    mask = [0] * len(source)
    for block in SequenceMatcher(None, source, target, autojunk=False).get_matching_blocks():
        if block.size <= 0:
            continue
        for offset in range(block.size):
            mask[block.a + offset] = 1
    return mask


def main():
    plans = {str(json.loads(l)['id']): json.loads(l) for l in PLAN.read_text(encoding='utf8').splitlines() if l.strip()}
    targets = {}
    for line in SRC.read_text(encoding='utf8').splitlines():
        if line.strip():
            row = json.loads(line)
            targets[str(row['id'])] = row['target']
    samples = []
    for rid, plan in plans.items():
        target = targets.get(rid)
        if not target:
            continue
        source = '。'.join(strip_prefix(plan['clauses'][i]) for i in plan['selected'])[:600]
        mask = keep_mask(source, target)
        samples.append((rid, source, target, mask))
    vocab = [PAD] + sorted({ch for _, s, _, _ in samples for ch in s})
    stoi = {ch: i for i, ch in enumerate(vocab)}
    n = len(vocab)
    group = [hashlib.sha256(s.encode('utf8')).hexdigest()[:10] for _, s, _, _ in samples]
    random.seed(20261128); torch.manual_seed(20261128)
    unique = sorted(set(group))
    hold = set(unique[-max(1, len(unique) // 5):])
    train = [x for x, g in zip(samples, group) if g not in hold]
    test = [x for x, g in zip(samples, group) if g in hold]

    d_model, heads, layers, max_len = 96, 4, 3, 620
    class Tagger(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = nn.Embedding(n, d_model)
            self.pos = nn.Embedding(max_len, d_model)
            layer = nn.TransformerEncoderLayer(d_model, heads, 4 * d_model, dropout=0.1, batch_first=True)
            self.body = nn.TransformerEncoder(layer, layers)
            self.out = nn.Linear(d_model, 1)
        def forward(self, x):
            pos = torch.arange(x.size(1)).unsqueeze(0)
            h = self.body(self.emb(x) + self.pos(pos))
            return self.out(h).squeeze(-1)

    net = Tagger()
    print('params', sum(p.numel() for p in net.parameters()))
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3)
    lossf = nn.BCEWithLogitsLoss()
    for epoch in range(40):
        net.train(); random.shuffle(train); total = 0.0
        for _, source, target, mask in train:
            ids = torch.tensor([[stoi[ch] for ch in source]])
            y = torch.tensor([mask], dtype=torch.float32)
            logits = net(ids)
            loss = lossf(logits, y)
            opt.zero_grad(); loss.backward(); opt.step()
            total += float(loss)
        if epoch % 10 == 0:
            print(json.dumps({'epoch': epoch, 'loss': round(total / max(1, len(train)), 3)}))
    net.eval()
    scores, cov, inv = [], [], []
    samples_out = []
    with torch.no_grad():
        for rid, source, target, mask in test:
            ids = torch.tensor([[stoi[ch] for ch in source]])
            probs = torch.sigmoid(net(ids))[0]
            kept = ''.join(ch for ch, p in zip(source, probs) if float(p) >= 0.5)
            scores.append(char_f1(kept, target))
            plan_chars = set(source)
            cov.append(sum(1 for ch in set(kept) if ch in plan_chars) / max(1, len(set(kept))))
            inv.append(sum(1 for ch in kept if ch not in plan_chars))
            if len(samples_out) < 3:
                samples_out.append({'source': source[:120], 'kept': kept[:160], 'target': target[:160]})
    summary = {
        'samples': len(samples), 'train': len(train), 'test': len(test),
        'params': sum(p.numel() for p in net.parameters()),
        'charF1Mean': round(sum(scores) / max(1, len(scores)), 3),
        'charF1Min': round(min(scores), 3), 'charF1Max': round(max(scores), 3),
        'coverageMean': round(sum(cov) / max(1, len(cov)), 3),
        'inventionCharsMean': round(sum(inv) / max(1, len(inv)), 1),
        'floors': {'program': 0.208, 'selection': 0.265, 'oracle': 0.29, 'freeGen': 0.332},
    }
    (HERE / 'span-keep-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))
    for row in samples_out:
        print('SRC:', row['source']); print('KEPT:', row['kept']); print('REF:', row['target']); print('---')


if __name__ == '__main__':
    main()
