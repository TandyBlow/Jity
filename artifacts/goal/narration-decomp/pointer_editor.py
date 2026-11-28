# -*- coding: utf-8 -*-
"""Sentence-level joint editor v1: a pointer decoder that writes the target by
copying source words in a learned order. Zero invention by construction (the
output vocabulary is the fact clause), so it isolates ordering/selection from
wording. Training targets are the human target's copyable subsequence, aligned
by SequenceMatcher. Same fixed holdout as E38/E43 for comparability."""
import hashlib
import json
import os
import random
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import torch
import torch.nn as nn

ROOT = Path(os.environ.get('NARR_ROOT', 'D:/others/Jity'))
HERE = Path(__file__).resolve().parent
PLAN = HERE / os.environ.get('NARR_PLAN', 'planning-examples-v14.jsonl')
SRC = Path(os.environ['NARR_SRC']) if os.environ.get('NARR_SRC') else ROOT / '.local/narr-train' / os.environ.get('NARR_DATA', 'sft-v14.jsonl')
HOLD_FROM = os.environ.get('NARR_HOLD_FROM', '')
SKIP = set(json.loads(os.environ['NARR_SKIP'])) if os.environ.get('NARR_SKIP') else set()
TAG = os.environ.get('NARR_TAG', '')
EPOCHS = int(os.environ.get('NARR_EPOCHS', '40'))


def strip_prefix(clause: str) -> str:
    body = re.sub(r'^玩家这回合.*?做的事：', '', clause)
    body = re.sub(r'^这一回合的结算结果：', '', body)
    body = re.sub(r'^[\u4e00-\u9fa5]{1,4}[：:]', '', body)
    return body.strip()


import jieba


def tok(text):
    return [w for w in jieba.lcut(text) if w.strip()]


def char_f1(a, b):
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    if not common:
        return 0.0
    p = common / max(1, len(a)); r = common / max(1, len(b))
    return 2 * p * r / (p + r)


def align_positions(src_words, dst_words):
    """Target word index -> source position for matched words."""
    out = []
    matcher = SequenceMatcher(None, src_words, dst_words, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                out.append((j1 + k, i1 + k))
    return out


def main():
    plans = {str(json.loads(l)['id']): json.loads(l) for l in PLAN.read_text(encoding='utf8').splitlines() if l.strip()}
    rows = {}
    for line in SRC.read_text(encoding='utf8').splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row['id'])] = row
    data, vocab = [], Counter()
    for rid, plan in plans.items():
        row = rows.get(rid)
        if not row:
            continue
        src_words = tok('。'.join(strip_prefix(plan['clauses'][i]) for i in plan['selected']))[:140]
        dst_words = tok(row['target'])[:120]
        if not src_words or not dst_words:
            continue
        pairs = align_positions(src_words, dst_words)
        seq = [pos for _, pos in sorted(pairs)]
        if not seq:
            continue
        vocab.update(src_words)
        data.append((rid, src_words, seq, dst_words))
    words = ['<pad>', '<eos>'] + [w for w, _ in vocab.most_common(4000)]
    stoi = {w: i for i, w in enumerate(words)}
    n = len(words)

    group = [hashlib.sha256(' '.join(src).encode('utf8')).hexdigest()[:10] for _, src, _, _ in data]
    random.seed(20261128); torch.manual_seed(20261128)
    if HOLD_FROM:
        hold = set(json.loads(Path(HOLD_FROM).read_text(encoding='utf8')))
    else:
        keys = sorted(set(group))
        hold = set(keys[-max(1, len(keys) // 5):])
    pairs = [(x, g) for x, g in zip(data, group) if x[0] not in SKIP]
    train = [x for x, g in pairs if g not in hold]
    test = [x for x, g in pairs if g in hold]

    d_model, max_src, max_dst = 128, 140, 120
    class Pointer(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = nn.Embedding(n, d_model, padding_idx=0)
            self.enc = nn.GRU(d_model, d_model, batch_first=True, bidirectional=True)
            self.proj = nn.Linear(2 * d_model, d_model)
            self.dec = nn.GRUCell(d_model, d_model)
            self.att = nn.Linear(d_model, d_model, bias=False)
            self.start = nn.Parameter(torch.zeros(d_model))
            self.eos = nn.Parameter(torch.zeros(1))
        def encode(self, src_ids):
            h, _ = self.enc(self.emb(src_ids))
            return self.proj(h)
        def step(self, prev_input, hidden, h):
            q = self.dec(prev_input, hidden)
            scores = torch.bmm(self.att(q).unsqueeze(1), h.transpose(1, 2)).squeeze(1)
            logits = torch.cat([scores[0], self.eos])[:h.size(1) + 1]
            return logits, q

    net = Pointer()
    print('params', sum(p.numel() for p in net.parameters()))
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3)
    lossf = nn.CrossEntropyLoss()
    for epoch in range(EPOCHS):
        net.train(); random.shuffle(train); total = 0.0
        for _, src, seq, _ in train:
            src_ids = torch.tensor([[stoi.get(w, 0) for w in src[:max_src]]])
            h = net.encode(src_ids)
            hidden = net.start.unsqueeze(0)
            prev_input = net.start.unsqueeze(0)
            loss = 0.0
            targets = seq + [len(src)]  # copy positions, EOS points past the source
            for target in targets[:max_dst]:
                logits, hidden = net.step(prev_input, hidden, h)
                loss = loss + lossf(logits.unsqueeze(0), torch.tensor([min(target, len(src))]))
                prev_input = net.emb(src_ids[:, min(target, len(src) - 1)]).unsqueeze(1).squeeze(1) if target < len(src) else net.start.unsqueeze(0)
                prev_input = prev_input.view(1, -1)
            opt.zero_grad(); (loss / max(1, len(targets))).backward(); opt.step()
            total += float(loss) / max(1, len(targets))
        if epoch % 10 == 0:
            print(json.dumps({'epoch': epoch, 'loss': round(total / max(1, len(train)), 3)}))
    net.eval()
    char_s, word_s, cov_s = [], [], []
    examples = []
    with torch.no_grad():
        for _, src, seq, dst in test:
            src_ids = torch.tensor([[stoi.get(w, 0) for w in src[:max_src]]])
            h = net.encode(src_ids)
            hidden = net.start.unsqueeze(0)
            prev_input = net.start.unsqueeze(0)
            out = []
            for _ in range(max_dst):
                logits, hidden = net.step(prev_input, hidden, h)
                nxt = int(logits.argmax())
                if nxt >= len(src):
                    break
                out.append(src[nxt])
                prev_input = net.emb(src_ids[:, nxt]).unsqueeze(1).squeeze(1).view(1, -1)
            text = ''.join(out)
            char_s.append(char_f1(text, ''.join(dst)))
            word_s.append(SequenceMatcher(None, out, dst, autojunk=False).ratio())
            cov_s.append(sum(1 for w in set(out) if w in src) / max(1, len(set(out))))
            if len(examples) < 3:
                examples.append((text[:160], ''.join(dst)[:160]))
    summary = {'samples': len(data), 'train': len(train), 'test': len(test),
               'params': sum(p.numel() for p in net.parameters()),
               'charF1Mean': round(sum(char_s) / max(1, len(char_s)), 3),
               'wordRatioMean': round(sum(word_s) / max(1, len(word_s)), 3),
               'coverageMean': round(sum(cov_s) / max(1, len(cov_s)), 3),
               'inventionWordsMean': 0.0}
    (HERE / ('pointer-summary%s.json' % TAG)).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))
    for gen, ref in examples:
        print('GEN:', gen); print('REF:', ref); print('---')


if __name__ == '__main__':
    main()
