# -*- coding: utf-8 -*-
"""Train the shared MiniRBT + four heads on batches v1-v4; v5 stays as test."""
import argparse
import json
import random
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
LABELS = ROOT / 'artifacts/goal/micro-redesign'
OUT = ROOT / '.local/micro-joint'
MAXLEN = 128
TASKS = {
    'targets': ['lu', 'nono', 'fingel', 'lin', 'qin'],
    'position': ['西侧服务巷', '器材棚', '西回廊', '钟楼', '钟楼门厅', '二层平台', '顶层旗台',
                 '庭院', '地下通道', '医护附楼', '跨溪小桥'],
    'intent': ['act', 'skip'],
    'judgment': ['achieved', 'partial', 'not_achieved', 'blocked', 'no_change'],
}


class Shared(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        hidden = self.bert.config.hidden_size
        self.heads = nn.ModuleDict({task: nn.Linear(hidden, len(labels)) for task, labels in TASKS.items()})

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return {task: head(cls) for task, head in self.heads.items()}


def load_batch(n):
    return [json.loads(line) for line in open(LABELS / f'labels-v{n}.jsonl', encoding='utf8')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--order', choices=['fixed', 'shuffled'], default='shuffled')
    ap.add_argument('--train-len', type=int, default=0)
    ap.add_argument('--epochs', type=int, default=40)
    ap.add_argument('--seed', type=int, default=20261124)
    ap.add_argument('--name', required=True)
    args = ap.parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    train_rows = [row for n in (1, 2, 3, 4) for row in load_batch(n)]
    test_rows = load_batch(5)
    (OUT / 'test.json').write_text(json.dumps(test_rows, ensure_ascii=False), encoding='utf8')
    limit = args.train_len or MAXLEN

    def encode(row):
        enc = tok(row['input'], truncation=True, max_length=limit)
        label = torch.tensor([1.0 if v in row['label'] else 0.0 for v in TASKS[row['task']]])
        return {'task': row['task'], 'ids': torch.tensor([enc['input_ids']]),
                'mask': torch.tensor([enc['attention_mask']]), 'label': label}

    train = [encode(row) for row in train_rows]
    model = Shared().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.BCEWithLogitsLoss()
    model.train()
    for _ in range(args.epochs):
        order = list(range(len(train)))
        if args.order == 'shuffled':
            random.shuffle(order)
        for i in order:
            f = train[i]
            opt.zero_grad()
            lossf(model(f['ids'].to(device), f['mask'].to(device))[f['task']],
                  f['label'].to(device).unsqueeze(0)).backward()
            opt.step()
    model.eval()
    stats = {}
    for task in TASKS:
        rows = [f for f in train if f['task'] == task]
        hits = sum(int(torch.equal((model(f['ids'].to(device), f['mask'].to(device))[task] > 0).float().cpu(),
                                   f['label'].unsqueeze(0))) for f in rows)
        stats[task] = f'{hits}/{len(rows)}'
    print('train exact', stats)
    sample = train[0]
    path = OUT / f'{args.name}.onnx'
    torch.onnx.export(model.cpu().eval(), (sample['ids'], sample['mask']), path,
                      input_names=['input_ids', 'attention_mask'],
                      output_names=['targets', 'position', 'intent', 'judgment'],
                      dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                    'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    (OUT / 'tasks.json').write_text(json.dumps(TASKS, ensure_ascii=False, indent=1), encoding='utf8')
    print('exported', path)


if __name__ == '__main__':
    main()
