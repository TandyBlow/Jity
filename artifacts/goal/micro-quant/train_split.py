# -*- coding: utf-8 -*-
"""Train the shared MiniRBT + four heads on the ladder split; export fp32 ONNX."""
import json
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
DATA = ROOT / 'artifacts/goal/micro-redesign/labels.jsonl'
OUT = ROOT / '.local/micro-quant'
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


def main():
    torch.manual_seed(20261124)
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    rows = [json.loads(line) for line in open(DATA, encoding='utf8')]
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    splits, feats = {}, []
    for task in TASKS:
        data = [row for row in rows if row['task'] == task]
        adversarial = [i for i, row in enumerate(data) if '铜哨' in row['input'] or '医护附楼' in row['input']]
        test = [i for i in range(len(data)) if i % 5 == 0 and i not in adversarial][:15]
        splits[task] = {'train': [i for i in range(len(data)) if i not in test], 'test': test}
        for i, row in enumerate(data):
            enc = tok(row['input'], truncation=True, max_length=MAXLEN, return_tensors='pt')
            label = torch.tensor([1.0 if v in row['label'] else 0.0 for v in TASKS[task]])
            feats.append({'task': task, 'index': i, 'ids': enc['input_ids'], 'mask': enc['attention_mask'], 'label': label})
    model = Shared().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.BCEWithLogitsLoss()
    train_feats = [f for f in feats if f['index'] in splits[f['task']]['train']]
    model.train()
    for _ in range(8):
        for f in train_feats:
            opt.zero_grad()
            lossf(model(f['ids'].to(device), f['mask'].to(device))[f['task']],
                  f['label'].to(device).unsqueeze(0)).backward()
            opt.step()
    model.eval()
    hits = sum(int(torch.equal((model(f['ids'].to(device), f['mask'].to(device))[f['task']] > 0).float().cpu(),
                               f['label'].unsqueeze(0))) for f in train_feats)
    print('train rows', len(train_feats), 'exact', hits)
    sample = feats[0]
    path = OUT / 'shared-split.onnx'
    torch.onnx.export(model.cpu().eval(), (sample['ids'], sample['mask']), path,
                      input_names=['input_ids', 'attention_mask'],
                      output_names=['targets', 'position', 'intent', 'judgment'],
                      dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                    'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    (OUT / 'shared-split-sample.json').write_text(json.dumps({'ids': sample['ids'][0].tolist()}), encoding='utf8')
    (OUT / 'split.json').write_text(json.dumps(splits, ensure_ascii=False, indent=1), encoding='utf8')
    (OUT / 'tasks.json').write_text(json.dumps(TASKS, ensure_ascii=False, indent=1), encoding='utf8')
    print('exported', path, 'tokens', sample['ids'].shape)


if __name__ == '__main__':
    main()
