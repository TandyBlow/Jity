# -*- coding: utf-8 -*-
"""Train the MiniRBT candidate scorer on pairs; export fp32 ONNX."""
import json
import random
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
OUT = ROOT / '.local/micro-generalize'
MAXLEN = 128


class PairScorer(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.head = nn.Linear(self.bert.config.hidden_size, 1)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.head(cls).squeeze(-1)


def main():
    random.seed(20261124)
    torch.manual_seed(20261124)
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    pairs = json.loads((OUT / 'pairs.json').read_text(encoding='utf8'))
    feats = []
    for p in pairs:
        enc = tok(p['text'], p['candidate'], truncation=True, max_length=MAXLEN)
        feats.append({'split': p['split'], 'task': p['task'], 'row': p['row'],
                      'candidate': p['candidate'],
                      'ids': torch.tensor([enc['input_ids']]),
                      'mask': torch.tensor([enc['attention_mask']]),
                      'label': torch.tensor([float(p['label'])])})
    train = [f for f in feats if f['split'] == 'train']
    model = PairScorer().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.BCEWithLogitsLoss()
    model.train()
    for _ in range(40):
        random.shuffle(train)
        for f in train:
            opt.zero_grad()
            lossf(model(f['ids'].to(device), f['mask'].to(device)), f['label'].to(device)).backward()
            opt.step()
    model.eval()

    def row_accuracy(split):
        stats = {}
        for task in ('position', 'targets'):
            rows = {}
            for f in feats:
                if f['split'] == split and f['task'] == task:
                    rows.setdefault(f['row'], []).append(f)
            hits = 0
            for row, items in rows.items():
                with torch.no_grad():
                    scores = {f['candidate']: float(model(f['ids'].to(device), f['mask'].to(device))[0])
                              for f in items}
                if task == 'position':
                    pred = {max(scores, key=scores.get)}
                else:
                    pred = {name for name, s in scores.items() if s > 0.0}
                truth = {f['candidate'] for f in items if f['label'].item() > 0}
                hits += int(pred == truth)
            stats[task] = f'{hits}/{len(rows)}'
        return stats

    print('train rows', len(train))
    print('seen', row_accuracy('seen'))
    print('held', row_accuracy('held'))
    sample = train[0]
    path = OUT / 'pair-scorer.onnx'
    torch.onnx.export(model.cpu().eval(), (sample['ids'], sample['mask']), path,
                      input_names=['input_ids', 'attention_mask'], output_names=['score'],
                      dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                    'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    print('exported', path)


if __name__ == '__main__':
    main()
