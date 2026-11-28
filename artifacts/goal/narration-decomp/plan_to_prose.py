# -*- coding: utf-8 -*-
"""Plan-to-prose v0: a tiny char-level transformer (~1M) writes the narration
from the human plan (selected clauses in human order). Grouped holdout by the
facts hash. Compared against the E31 floors (program 0.208 / selection 0.265 /
oracle 0.290 charF1)."""
import hashlib
import json
import math
import random
import re
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn

ROOT = Path('D:/others/Jity')
HERE = Path(__file__).resolve().parent
PLAN = HERE / 'planning-examples-v2.jsonl'
SRC = ROOT / '.local/narr-train/sft-v13.jsonl'
BOS, SEP, EOS, PAD = '\u0001', '\u0002', '\u0003', '\u0000'


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


def main():
    plans = {str(json.loads(line)['id']): json.loads(line) for line in PLAN.read_text(encoding='utf8').splitlines() if line.strip()}
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
        chosen = plan['selected']
        plan_text = '|'.join(f"{plan['types'][i]}" + strip_prefix(plan['clauses'][i]) for i in chosen)[:420]
        samples.append((rid, plan_text, target[:220]))
    vocab = [PAD, BOS, SEP, EOS] + sorted({ch for _, p, t in samples for ch in p + t})
    stoi = {ch: i for i, ch in enumerate(vocab)}
    n = len(vocab)
    seqs = []
    for rid, plan_text, target in samples:
        ids = [stoi[BOS]] + [stoi.get(ch or ' ', 4) for ch in plan_text] + [stoi[SEP]] + [stoi.get(ch or ' ', 4) for ch in target] + [stoi[EOS]]
        seqs.append((rid, ids, len([stoi.get(ch or ' ', 4) for ch in plan_text])))
    groups = [hashlib.sha256(plan.encode('utf8')).hexdigest()[:10] for _, plan, _ in samples]
    random.seed(20261128)
    torch.manual_seed(20261128)
    unique = sorted(set(groups))
    hold = set(unique[-max(1, len(unique) // 5):])
    train = [row for row, group in zip(seqs, groups) if group not in hold]
    test = [row for row, group in zip(seqs, groups) if group in hold]

    d_model, heads, layers, max_len = 128, 4, 3, 700
    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = nn.Embedding(n, d_model)
            self.pos = nn.Embedding(max_len, d_model)
            layer = nn.TransformerEncoderLayer(d_model, heads, 4 * d_model, dropout=0.1, batch_first=True)
            self.body = nn.TransformerEncoder(layer, layers)
            self.out = nn.Linear(d_model, n)
        def forward(self, x):
            pos = torch.arange(x.size(1)).unsqueeze(0)
            h = self.body(self.emb(x) + self.pos(pos))
            return self.out(h)

    net = Net()
    print('params', sum(p.numel() for p in net.parameters()))
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3)
    lossf = nn.CrossEntropyLoss(ignore_index=stoi[PAD])
    pad = stoi[PAD]
    for epoch in range(60):
        net.train()
        random.shuffle(train)
        total = 0.0
        for _, ids, prefix_len in train:
            x = torch.tensor([ids[:-1]])[: , :max_len]
            y = torch.tensor([ids[1:]])[:, :max_len]
            if x.size(1) < 2:
                continue
            mask = torch.triu(torch.ones(x.size(1), x.size(1)), diagonal=1).bool()
            logits = net(x)
            loss = lossf(logits.reshape(-1, n), y.reshape(-1))
            opt.zero_grad(); loss.backward(); opt.step()
            total += float(loss)
        if epoch % 10 == 0:
            print(json.dumps({'epoch': epoch, 'loss': round(total / max(1, len(train)), 3)}))
    net.eval()
    scores = []
    with torch.no_grad():
        for _, ids, prefix_len in test:
            plan_ids = ids[:prefix_len + 1]
            out = list(plan_ids)
            for _ in range(220):
                x = torch.tensor([out[-max_len:]])
                logits = net(x)
                nxt = int(logits[0, -1].argmax())
                if nxt == stoi[EOS]:
                    break
                out.append(nxt)
            text = ''.join(vocab[i] for i in out[prefix_len + 1:])
            target = ''.join(vocab[i] for i in ids[prefix_len + 1:] if i != stoi[EOS])
            plan_text = ''.join(vocab[i] for i in ids[1:prefix_len])
            score = char_f1(text, target)
            scores.append(score)
            audit = globals().setdefault('AUDIT', [])
            audit.append({'plan': plan_text[:160], 'generated': text[:200], 'target': target[:200],
                          'charF1': round(score, 3)})
    summary = {
        'samples': len(samples), 'train': len(train), 'test': len(test),
        'params': sum(p.numel() for p in net.parameters()),
        'holdoutCharF1Mean': round(sum(scores) / max(1, len(scores)), 3),
        'floors': {'program': 0.208, 'selection': 0.265, 'oracle': 0.29},
    }
    (HERE / 'plan-to-prose-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    audit = globals().get('AUDIT', [])
    lines = [json.dumps(row, ensure_ascii=False) for row in audit]
    (HERE / 'plan-to-prose-samples.jsonl').write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf8')
    if audit:
        ordered = sorted(audit, key=lambda row: row['charF1'])
        summary['charF1Min'] = ordered[0]['charF1']
        summary['charF1Median'] = ordered[len(ordered) // 2]['charF1']
        summary['charF1Max'] = ordered[-1]['charF1']
    (HERE / 'plan-to-prose-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))
    for index in range(0, len(audit), max(1, len(audit) // 5)):
        row = audit[index]
        print('PLAN:', row['plan'])
        print('GEN :', row['generated'])
        print('REF :', row['target'])
        print('---')


if __name__ == '__main__':
    main()
