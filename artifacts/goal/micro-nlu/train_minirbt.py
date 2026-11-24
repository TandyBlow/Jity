# -*- coding: utf-8 -*-
"""Fine-tune MiniRBT-H256 (10.4M) for the targets head; export + int8 ONNX."""
import json
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
DATA = ROOT / 'artifacts/goal/micro-nlu/datasets/targets.jsonl'
OUT = ROOT / '.local/micro-nlu'
MAXLEN = 512


class Small(nn.Module):
    def __init__(self, labels):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.head = nn.Linear(self.bert.config.hidden_size, labels)

    def forward(self, ids, mask):
        out = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.head(out)


def main():
    rows = [json.loads(line) for line in open(DATA, encoding='utf8')]
    vocab = sorted({t['targetId'] for row in rows
                    for t in (row.get('parsed') or {}).get('targets') or []})
    print('vocab', vocab, 'rows', len(rows))
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    enc = [tok(row['prompt'], truncation=True, max_length=MAXLEN, return_tensors='pt') for row in rows]
    ys = [torch.tensor([1.0 if tid in {t['targetId'] for t in (row.get('parsed') or {}).get('targets') or []}
                        else 0.0 for tid in vocab]) for row in rows]
    turns = sorted({row['turn'] for row in rows})
    groups = {turn: i % 4 for i, turn in enumerate(turns)}
    hits = total = 0
    for fold in range(4):
        train = [i for i, row in enumerate(rows) if groups[row['turn']] != fold]
        test = [i for i, row in enumerate(rows) if groups[row['turn']] == fold]
        if not train or not test:
            continue
        model = Small(len(vocab))
        opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
        lossf = nn.BCEWithLogitsLoss()
        model.train()
        for _ in range(20):
            for i in train:
                opt.zero_grad()
                logits = model(enc[i]['input_ids'], enc[i]['attention_mask'])
                lossf(logits, ys[i].unsqueeze(0)).backward()
                opt.step()
        model.eval()
        for i in test:
            with torch.no_grad():
                pred = (model(enc[i]['input_ids'], enc[i]['attention_mask']) > 0).float()
            hits += int(torch.equal(pred, ys[i].unsqueeze(0)))
            total += 1
    print('cv exact-match', hits, '/', total)

    model = Small(len(vocab))
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.BCEWithLogitsLoss()
    model.train()
    for _ in range(20):
        for i in range(len(rows)):
            opt.zero_grad()
            lossf(model(enc[i]['input_ids'], enc[i]['attention_mask']), ys[i].unsqueeze(0)).backward()
            opt.step()
    model.eval()
    ids = enc[0]['input_ids']
    mask = enc[0]['attention_mask']
    path = OUT / 'minirbt-targets.onnx'
    torch.onnx.export(model, (ids, mask), path, input_names=['input_ids', 'attention_mask'],
                      output_names=['logits'], dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                                             'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    print('exported', path, 'tokens', ids.shape)
    (OUT / 'minirbt-sample-ids.json').write_text(json.dumps({'ids': ids[0].tolist()}, ensure_ascii=False), encoding='utf8')


if __name__ == '__main__':
    main()
