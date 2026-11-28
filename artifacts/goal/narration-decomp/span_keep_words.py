# -*- coding: utf-8 -*-
"""Edit decoder v2: word-level keep/delete pointers over the selected clauses.
Words stay intact (E35 showed char masks scramble word order); kept words are
joined in order with rule-based punctuation. Scored on charF1, order-sensitive
wordRatio, plan coverage and inventions."""
import hashlib
import json
import random
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import jieba
import torch
import torch.nn as nn

ROOT = Path('D:/others/Jity')
HERE = Path(__file__).resolve().parent
PLAN = HERE / 'planning-examples-v2.jsonl'
SRC = ROOT / '.local/narr-train/sft-v13.jsonl'
PAD = '<pad>'
PUNCT = set('，。！？；：、')


def strip_prefix(clause: str) -> str:
    body = re.sub(r'^玩家这回合.*?做的事：', '', clause)
    body = re.sub(r'^这一回合的结算结果：', '', body)
    body = re.sub(r'^[\u4e00-\u9fa5]{1,4}[：:]', '', body)
    return body.strip()


def tokens(text: str):
    return [w for w in jieba.lcut(text) if w.strip()]


def char_f1(a: str, b: str) -> float:
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    if not common:
        return 0.0
    precision = common / max(1, len(a))
    recall = common / max(1, len(b))
    return 2 * precision * recall / (precision + recall)


def main():
    plans = {str(json.loads(l)['id']): json.loads(l) for l in PLAN.read_text(encoding='utf8').splitlines() if l.strip()}
    targets = {}
    for line in SRC.read_text(encoding='utf8').splitlines():
        if line.strip():
            row = json.loads(line)
            targets[str(row['id'])] = row['target']
    samples = []
    vocab = Counter()
    for rid, plan in plans.items():
        target = targets.get(rid)
        if not target:
            continue
        clauses = [tokens(strip_prefix(plan['clauses'][i])) for i in plan['selected']]
        for clause in clauses:
            vocab.update(clause)
        samples.append((rid, clauses, [tokens(target)]))
    stoi = {word: index for index, (word, _) in enumerate([(PAD, 0)] + vocab.most_common())}
    n = len(stoi)
    prepared = []
    for rid, clauses, target_tokens in samples:
        flat, mask, clause_ids = [], [], []
        for clause_index, clause in enumerate(clauses):
            target_seq = target_tokens[0]
            matcher = SequenceMatcher(None, clause, target_seq, autojunk=False)
            keep = set()
            for block in matcher.get_matching_blocks():
                for offset in range(block.size):
                    keep.add(block.a + offset)
            for position, word in enumerate(clause):
                flat.append(word); mask.append(1 if position in keep else 0); clause_ids.append(clause_index)
        prepared.append((rid, flat, mask, clause_ids, target_tokens[0]))
    group = [hashlib.sha256(' '.join(flat).encode('utf8')).hexdigest()[:10] for _, flat, _, _, _ in prepared]
    random.seed(20261128); torch.manual_seed(20261128)
    unique = sorted(set(group))
    hold = set(unique[-max(1, len(unique) // 5):])
    train = [x for x, g in zip(prepared, group) if g not in hold]
    test = [x for x, g in zip(prepared, group) if g in hold]

    d_model, heads, layers, max_len = 96, 4, 3, 220
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
        for _, flat, mask, _, _ in train:
            ids = torch.tensor([[stoi[w] for w in flat[:max_len]]])
            y = torch.tensor([mask[:max_len]], dtype=torch.float32)
            loss = lossf(net(ids), y)
            opt.zero_grad(); loss.backward(); opt.step()
            total += float(loss)
        if epoch % 10 == 0:
            print(json.dumps({'epoch': epoch, 'loss': round(total / max(1, len(train)), 3)}))
    net.eval()
    char_scores, word_scores, coverage, inventions = [], [], [], []
    examples = []
    with torch.no_grad():
        for rid, flat, mask, clause_ids, target_seq in test:
            ids = torch.tensor([[stoi[w] for w in flat[:max_len]]])
            probs = torch.sigmoid(net(ids))[0]
            kept_words = []
            last_clause = None
            for word, clause_index, prob in zip(flat, clause_ids, probs):
                if float(prob) < 0.5:
                    continue
                if last_clause is not None and clause_index != last_clause and word not in PUNCT:
                    kept_words.append('，')
                kept_words.append(word)
                last_clause = clause_index
            text = ''.join(kept_words)
            char_scores.append(char_f1(text, ''.join(target_seq)))
            word_scores.append(SequenceMatcher(None, kept_words, target_seq, autojunk=False).ratio())
            coverage.append(sum(1 for w in set(kept_words) if w in flat) / max(1, len(set(kept_words))))
            inventions.append(sum(1 for w in kept_words if w not in flat))
            if len(examples) < 3:
                examples.append({'kept': text[:160], 'ref': ''.join(target_seq)[:160]})
    summary = {
        'samples': len(prepared), 'train': len(train), 'test': len(test),
        'params': sum(p.numel() for p in net.parameters()),
        'charF1Mean': round(sum(char_scores) / max(1, len(char_scores)), 3),
        'wordRatioMean': round(sum(word_scores) / max(1, len(word_scores)), 3),
        'coverageMean': round(sum(coverage) / max(1, len(coverage)), 3),
        'inventionWordsMean': round(sum(inventions) / max(1, len(inventions)), 1),
    }
    (HERE / 'span-keep-words-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))
    for row in examples:
        print('KEPT:', row['kept']); print('REF :', row['ref']); print('---')


if __name__ == '__main__':
    main()
