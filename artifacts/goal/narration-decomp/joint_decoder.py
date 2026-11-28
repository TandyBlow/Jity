# -*- coding: utf-8 -*-
"""Joint edit decoder v1: a word-level seq2seq from the plan to the prose.
One decoder makes copy/paraphrase/glue decisions together (E37), in contrast
to the independent tagger + translator. Scored on charF1, order-sensitive
wordRatio, plan coverage and invented words."""
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

ROOT = Path('D:/others/Jity')
HERE = Path(__file__).resolve().parent
PLAN = HERE / os.environ.get('NARR_PLAN', 'planning-examples-v2.jsonl')
SRC = ROOT / '.local/narr-train' / os.environ.get('NARR_DATA', 'sft-v13.jsonl')
TAG = os.environ.get('NARR_TAG', '')
HOLD_FROM = os.environ.get('NARR_HOLD_FROM', '')
SKIP = set(json.loads(os.environ['NARR_SKIP'])) if os.environ.get('NARR_SKIP') else set()
BOS, EOS, PAD = '<s>', '</s>', '<p>'


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


def main():
    plans = {str(json.loads(l)['id']): json.loads(l) for l in PLAN.read_text(encoding='utf8').splitlines() if l.strip()}
    targets = {}
    for line in SRC.read_text(encoding='utf8').splitlines():
        if line.strip():
            row = json.loads(line)
            targets[str(row['id'])] = row['target']
    data = []
    vocab_words = Counter()
    for rid, plan in plans.items():
        target = targets.get(rid)
        if not target:
            continue
        source = '|'.join(strip_prefix(plan['clauses'][i]) for i in plan['selected'])
        src_words = tok(source)[:120]
        dst_words = tok(target)[:120]
        vocab_words.update(src_words); vocab_words.update(dst_words)
        data.append((rid, src_words, dst_words))
    words = [PAD, BOS, EOS] + [w for w, _ in vocab_words.most_common(4000)]
    stoi = {w: i for i, w in enumerate(words)}
    n = len(words)
    group = [hashlib.sha256(' '.join(src).encode('utf8')).hexdigest()[:10] for _, src, _ in data]
    random.seed(20261128); torch.manual_seed(20261128)
    if HOLD_FROM:
        hold = set(json.loads(Path(HOLD_FROM).read_text(encoding='utf8')))
    else:
        keys = sorted(set(group))
        hold = set(keys[-max(1, len(keys) // 5):])
    pairs = [(x, g) for x, g in zip(data, group) if x[0] not in SKIP]
    train = [x for x, g in pairs if g not in hold]
    test = [x for x, g in pairs if g in hold]

    d_model, heads = 128, 4
    max_src, max_dst = 140, 120
    class Joint(nn.Module):
        def __init__(self):
            super().__init__()
            self.src_e = nn.Embedding(n, d_model)
            self.dst_e = nn.Embedding(n, d_model)
            self.pos = nn.Embedding(160, d_model)
            enc = nn.TransformerEncoderLayer(d_model, heads, 4 * d_model, batch_first=True, dropout=0.1)
            dec = nn.TransformerDecoderLayer(d_model, heads, 4 * d_model, batch_first=True, dropout=0.1)
            self.encoder = nn.TransformerEncoder(enc, 3)
            self.decoder = nn.TransformerDecoder(dec, 3)
            self.out = nn.Linear(d_model, n)
        def forward(self, src, tgt):
            pos = torch.arange(src.size(1)).unsqueeze(0)
            memory = self.encoder(self.src_e(src) + self.pos(pos))
            pos2 = torch.arange(tgt.size(1)).unsqueeze(0)
            mask = torch.triu(torch.ones(tgt.size(1), tgt.size(1)), diagonal=1).bool()
            h = self.decoder(self.dst_e(tgt) + self.pos(pos2), memory, tgt_mask=mask)
            return self.out(h)

    net = Joint()
    print('params', sum(p.numel() for p in net.parameters()))
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3)
    lossf = nn.CrossEntropyLoss(ignore_index=stoi[PAD])
    for epoch in range(40):
        net.train(); random.shuffle(train); total = 0.0
        for _, src, dst in train:
            src_ids = torch.tensor([[stoi.get(w, stoi[PAD]) for w in src[:max_src]]])
            tgt_ids = [stoi[BOS]] + [stoi.get(w, stoi[PAD]) for w in dst[:max_dst - 1]] + [stoi[EOS]]
            tgt = torch.tensor([tgt_ids])
            logits = net(src_ids, tgt[:, :-1])
            loss = lossf(logits.reshape(-1, n), tgt[:, 1:].reshape(-1))
            opt.zero_grad(); loss.backward(); opt.step()
            total += float(loss)
        if epoch % 10 == 0:
            print(json.dumps({'epoch': epoch, 'loss': round(total / max(1, len(train)), 3)}))
    net.eval()
    inv = {v: k for k, v in stoi.items()}
    char_s, word_s, cov_s, inv_s = [], [], [], []
    examples = []
    with torch.no_grad():
        for _, src, dst in test:
            src_ids = torch.tensor([[stoi.get(w, stoi[PAD]) for w in src[:max_src]]])
            memory = net.encoder(net.src_e(src_ids) + net.pos(torch.arange(src_ids.size(1)).unsqueeze(0)))
            out = [stoi[BOS]]
            for _ in range(max_dst):
                tgt = torch.tensor([out])
                pos2 = torch.arange(tgt.size(1)).unsqueeze(0)
                mask = torch.triu(torch.ones(tgt.size(1), tgt.size(1)), diagonal=1).bool()
                logits = net.out(net.decoder(net.dst_e(tgt) + net.pos(pos2), memory, tgt_mask=mask))
                nxt = int(logits[0, -1].argmax())
                if nxt == stoi[EOS]:
                    break
                out.append(nxt)
            gen = [inv.get(i, PAD) for i in out[1:]]
            text = ''.join(gen)
            char_s.append(char_f1(text, ''.join(dst)))
            word_s.append(SequenceMatcher(None, gen, dst, autojunk=False).ratio())
            cov_s.append(sum(1 for w in set(gen) if w in src) / max(1, len(set(gen))))
            inv_s.append(sum(1 for w in gen if w not in src))
            if len(examples) < 3:
                examples.append((text[:160], ''.join(dst)[:160]))
    summary = {'samples': len(data), 'train': len(train), 'test': len(test),
               'params': sum(p.numel() for p in net.parameters()),
               'charF1Mean': round(sum(char_s) / max(1, len(char_s)), 3),
               'wordRatioMean': round(sum(word_s) / max(1, len(word_s)), 3),
               'coverageMean': round(sum(cov_s) / max(1, len(cov_s)), 3),
               'inventionWordsMean': round(sum(inv_s) / max(1, len(inv_s)), 1)}
    (HERE / ('joint-summary%s.json' % TAG)).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))
    for gen, ref in examples:
        print('GEN:', gen); print('REF:', ref); print('---')


if __name__ == '__main__':
    main()
