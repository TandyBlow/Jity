# -*- coding: utf-8 -*-
"""Pointer editor v2: copy source words + insert a fixed connective set +
choose a replacement from a corpus-derived rewrite vocabulary. No free text,
so every emitted word is either a fact word, a connective, or an attested
rewrite. Same fixed holdout as E38/E43/E45."""
import hashlib
import json
import os
import random
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import jieba
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
CONN = list('的了着过地得是在把被将让给向从对与和及而却便就都也还很更最又再才只随后接着于是这时同时然后但可已经仍')
REPL_LIMIT = 200


def strip_prefix(clause: str) -> str:
    body = re.sub(r'^玩家这回合.*?做的事：', '', clause)
    body = re.sub(r'^这一回合的结算结果：', '', body)
    body = re.sub(r'^[\u4e00-\u9fa5]{1,4}[：:]', '', body)
    return body.strip()


def tok(text):
    return [w for w in jieba.lcut(text) if w.strip()]


def char_f1(a, b):
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    if not common:
        return 0.0
    p = common / max(1, len(a)); r = common / max(1, len(b))
    return 2 * p * r / (p + r)


def load_replacements():
    pairs = [json.loads(l) for l in (HERE / 'replace-pairs-ctx.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    counts = Counter()
    for p in pairs:
        dst = p['dst']
        if 1 <= len(dst) <= 4 and dst not in CONN:
            counts[dst] += 1
    return [dst for dst, _ in counts.most_common(REPL_LIMIT)]


def main():
    replacements = load_replacements()
    repl_set = set(replacements)
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
        src = tok('|'.join(strip_prefix(plan['clauses'][i]) for i in plan['selected']))[:120]
        dst = tok(row['target'])[:120]
        if not src or not dst:
            continue
        matched = {}
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, src, dst, autojunk=False).get_opcodes():
            if tag == 'equal':
                for k in range(i2 - i1):
                    matched[j1 + k] = i1 + k
        actions = []
        for j, word in enumerate(dst):
            if j in matched:
                actions.append(('copy', matched[j]))
            elif word in repl_set:
                actions.append(('repl', replacements.index(word)))
            elif word in CONN:
                actions.append(('conn', CONN.index(word)))
        if not actions:
            continue
        vocab.update(src)
        data.append((rid, src, actions, dst))
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

    def action_index(act, src_len):
        kind, value = act
        if kind == 'copy':
            return value
        if kind == 'conn':
            return src_len + value
        return src_len + len(CONN) + value

    def eos_index(src_len):
        return src_len + len(CONN) + len(replacements)

    d_model, max_src, max_dst = 128, 120, 120
    class Pointer2(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = nn.Embedding(n, d_model, padding_idx=0)
            self.enc = nn.GRU(d_model, d_model, batch_first=True, bidirectional=True)
            self.proj = nn.Linear(2 * d_model, d_model)
            self.dec = nn.GRUCell(d_model, d_model)
            self.att = nn.Linear(d_model, d_model, bias=False)
            self.start = nn.Parameter(torch.zeros(d_model))
            self.out_vocab = n + len(CONN) + len(replacements)
            self.emit = nn.Linear(d_model, self.out_vocab + 1)
        def encode(self, src_ids):
            h, _ = self.enc(self.emb(src_ids))
            return self.proj(h)
        def step(self, prev_input, hidden, h):
            q = self.dec(prev_input, hidden)
            copy = torch.bmm(self.att(q).unsqueeze(1), h.transpose(1, 2)).squeeze(1)
            extra = self.emit(q)
            logits = torch.cat([copy, extra], dim=1)[0]
            return logits, q

    net = Pointer2()
    print('params', sum(p.numel() for p in net.parameters()), 'repl', len(replacements))
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3)
    lossf = nn.CrossEntropyLoss()
    for epoch in range(EPOCHS):
        net.train(); random.shuffle(train); total = 0.0
        for _, src, actions, _ in train:
            src_ids = torch.tensor([[stoi.get(w, 0) for w in src[:max_src]]])
            h = net.encode(src_ids)
            hidden = net.start.unsqueeze(0)
            prev_input = net.start.unsqueeze(0)
            targets = [action_index(a, len(src)) for a in actions][:max_dst] + [eos_index(len(src))]
            loss = 0.0
            for step, target in enumerate(targets):
                logits, hidden = net.step(prev_input, hidden, h)
                loss = loss + lossf(logits.unsqueeze(0), torch.tensor([min(target, logits.size(0) - 1)]))
                if step < len(targets) - 1:
                    kind, value = actions[step]
                    if kind == 'copy' and value < len(src):
                        prev_input = net.emb(src_ids[:, value])
                    else:
                        prev_input = net.start.unsqueeze(0)
            opt.zero_grad(); (loss / max(1, len(targets))).backward(); opt.step()
            total += float(loss) / max(1, len(targets))
        if epoch % 10 == 0:
            print(json.dumps({'epoch': epoch, 'loss': round(total / max(1, len(train)), 3)}))
    net.eval()
    char_s, word_s, recall_s, inv_s = [], [], [], []
    examples = []
    with torch.no_grad():
        for _, src, actions, dst in test:
            src_ids = torch.tensor([[stoi.get(w, 0) for w in src[:max_src]]])
            h = net.encode(src_ids)
            hidden = net.start.unsqueeze(0)
            prev_input = net.start.unsqueeze(0)
            out = []
            for _ in range(max_dst):
                logits, hidden = net.step(prev_input, hidden, h)
                nxt = int(logits.argmax())
                if nxt == eos_index(len(src)):
                    break
                if nxt < len(src):
                    out.append(src[nxt])
                    prev_input = net.emb(src_ids[:, nxt])
                    continue
                extra = nxt - len(src)
                if extra < len(CONN):
                    out.append(CONN[extra])
                elif extra < len(CONN) + len(replacements):
                    out.append(replacements[extra - len(CONN)])
                prev_input = net.start.unsqueeze(0)
            text = ''.join(out)
            char_s.append(char_f1(text, ''.join(dst)))
            word_s.append(SequenceMatcher(None, out, dst, autojunk=False).ratio())
            recall_s.append(sum((Counter(out) & Counter(dst)).values()) / max(1, len(dst)))
            allowed = set(src) | set(CONN) | set(replacements)
            inv_s.append(sum(1 for w in out if w not in allowed))
            if len(examples) < 3:
                examples.append((text[:160], ''.join(dst)[:160]))
    summary = {'samples': len(data), 'train': len(train), 'test': len(test),
               'params': sum(p.numel() for p in net.parameters()), 'repl': len(replacements),
               'charF1Mean': round(sum(char_s) / max(1, len(char_s)), 3),
               'wordRatioMean': round(sum(word_s) / max(1, len(word_s)), 3),
               'targetRecallMean': round(sum(recall_s) / max(1, len(recall_s)), 3),
               'inventionWordsMean': round(sum(inv_s) / max(1, len(inv_s)), 1)}
    (HERE / ('pointer2-summary%s.json' % TAG)).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))
    for gen, ref in examples:
        print('GEN:', gen); print('REF:', ref); print('---')


if __name__ == '__main__':
    main()
