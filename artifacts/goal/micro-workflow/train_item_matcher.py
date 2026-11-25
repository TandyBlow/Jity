# -*- coding: utf-8 -*-
"""Item matcher: MiniRBT pair scorer over (action/mention, candidate item).

Positives are registered items named by the action; negatives are other items
and curated unregistered mentions (水壶/外套/…) which must score as no-match.
The test split holds out whole items, so a match is name/description driven.
"""
import json
import os
import random
from collections import Counter, defaultdict
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path(os.environ.get('JITY_HPC_ROOT', 'D:/others/Jity'))
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
OUT = ROOT / '.local/micro-heads'
MAXLEN = 128
EXPORT = os.environ.get('ITEM_EXPORT', '1') != '0'


class PairScorer(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.head = nn.Linear(self.bert.config.hidden_size, 1)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.head(cls).squeeze(-1)


def main():
    random.seed(20261125)
    torch.manual_seed(20261125)
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    rows = [json.loads(line) for line in open(PUB / 'matcher-pairs.jsonl', encoding='utf8')]
    feats = []
    for row in rows:
        enc = tok(row['context'], row['candidate'], truncation=True, max_length=MAXLEN)
        feats.append({
            'split': row['split'], 'label': float(row['label']), 'mention': row['mention'],
            'itemId': row['itemId'], 'context': row['context'],
            'ids': torch.tensor([enc['input_ids']]), 'mask': torch.tensor([enc['attention_mask']]),
        })
    train = [f for f in feats if f['split'] == 'train']
    model = PairScorer().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([4.0], device=device))
    model.train()
    for _ in range(40):
        random.shuffle(train)
        for f in train:
            opt.zero_grad()
            lossf(model(f['ids'].to(device), f['mask'].to(device)), torch.tensor([f['label']], device=device)).backward()
            opt.step()
    model.eval()

    def score(f):
        with torch.no_grad():
            return float(model(f['ids'].to(device), f['mask'].to(device))[0])

    test = [f for f in feats if f['split'] == 'test']
    confusion = Counter()
    for f in test:
        pred = 1 if score(f) > 0 else 0
        confusion[f"{int(f['label'])}->{pred}"] += 1
    groups = defaultdict(list)
    for f in test:
        groups[(f['context'], f['mention'])].append(f)
    top1 = Counter()
    for (_context, _mention), items in groups.items():
        truth = [f['itemId'] for f in items if f['label'] > 0]
        if len(truth) != 1:
            continue
        best = max(items, key=score)
        top1['correct' if best['itemId'] == truth[0] and score(best) > 0 else 'wrong'] += 1
    unregistered = defaultdict(list)
    for f in test:
        if f['mention'] in ('水壶', '外套', '电台', '头盔', '钥匙串', '地图册', '长柄手电'):
            unregistered[f['mention']].append(score(f))
    no_match = {mention: {'rows': len(scores), 'max_score': round(max(scores), 3), 'no_match': max(scores) <= 0}
                for mention, scores in unregistered.items()}
    sizes = {}
    if EXPORT:
        sample = feats[0]
        path = OUT / 'item-matcher.onnx'
        torch.onnx.export(model.cpu().eval(), (sample['ids'], sample['mask']), path,
                          input_names=['input_ids', 'attention_mask'], output_names=['score'],
                          dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                        'attention_mask': {0: 'batch', 1: 'len'}},
                          opset_version=17)
        from onnxruntime.quantization import QuantType, quantize_dynamic
        int8 = OUT / 'item-matcher-int8.onnx'
        quantize_dynamic(str(path), str(int8), weight_type=QuantType.QInt8)
        sizes = {'bytes': path.stat().st_size, 'int8_bytes': int8.stat().st_size}
    else:
        pt = OUT / 'item-matcher.pt'
        torch.save(model.state_dict(), pt)
        sizes = {'pt_bytes': pt.stat().st_size}
    lengths = sorted(len(tok(r['context'], r['candidate'])['input_ids']) for r in rows)
    report = {
        'rows': len(rows), 'train': len(train), 'test': len(test),
        'labels': dict(Counter(str(int(r['label'])) for r in rows)),
        'pair_confusion': dict(confusion),
        'top1_groups': dict(top1),
        'unregistered': no_match,
        'input_tokens_median': lengths[len(lengths) // 2], 'input_tokens_max': lengths[-1],
        **sizes,
    }
    (PUB / 'item-matcher-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
