# -*- coding: utf-8 -*-
"""Train the two pilot heads on the hand-authored balanced sets.

Labels are the reviewer's (`source: authored`), not model outputs; these heads
do not replace any product call. 5-fold cross-validation is by row index with a
fixed seed; the exported model is trained on all rows.
"""
import json
import os
import random
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path(os.environ.get('JITY_HPC_ROOT', 'D:/others/Jity'))
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
OUT = ROOT / '.local/micro-heads'
MAXLEN = 192
# The cluster env has torch/transformers but no onnx; export there is off.
EXPORT = os.environ.get('PILOT_EXPORT', '1') != '0'


class Head(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.out = nn.Linear(self.bert.config.hidden_size, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls)


def encode(tok, text):
    enc = tok(text, truncation=True, max_length=MAXLEN)
    return torch.tensor([enc['input_ids']]), torch.tensor([enc['attention_mask']])


def run_one(name, rows, tok, device):
    random.seed(20261125)
    torch.manual_seed(20261125)
    def label_of(row):
        if isinstance(row['label'], int):
            return row['label']
        return 1 if row['label'] == 'skip' else 0

    feats = [(encode(tok, r['input'])[0], encode(tok, r['input'])[1], label_of(r)) for r in rows]
    folds = [[f for i, f in enumerate(feats) if i % 5 == fold] for fold in range(5)]
    cv = {'correct': 0, 'total': 0, 'confusion': Counter()}
    for fold in range(5):
        test = folds[fold]
        train = [f for i, f in enumerate(feats) if i % 5 != fold]
        model = Head().to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
        lossf = nn.CrossEntropyLoss()
        model.train()
        for _ in range(40):
            random.shuffle(train)
            for ids, mask, label in train:
                opt.zero_grad()
                lossf(model(ids.to(device), mask.to(device)), torch.tensor([label], device=device)).backward()
                opt.step()
        model.eval()
        for ids, mask, label in test:
            with torch.no_grad():
                pred = int(model(ids.to(device), mask.to(device)).argmax(1).item())
            cv['total'] += 1
            cv['correct'] += int(pred == label)
            cv['confusion'][f'{label}->{pred}'] += 1
    # Final model on every row, exported for the browser probe.
    model = Head().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.CrossEntropyLoss()
    model.train()
    for _ in range(40):
        random.shuffle(feats)
        for ids, mask, label in feats:
            opt.zero_grad()
            lossf(model(ids.to(device), mask.to(device)), torch.tensor([label], device=device)).backward()
            opt.step()
    lengths = sorted(len(tok(r['input'])['input_ids']) for r in rows)
    sizes = {}
    if EXPORT:
        sample = feats[0]
        path = OUT / f'{name}.onnx'
        torch.onnx.export(model.cpu().eval(), (sample[0], sample[1]), path,
                          input_names=['input_ids', 'attention_mask'], output_names=['logits'],
                          dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                        'attention_mask': {0: 'batch', 1: 'len'}},
                          opset_version=17)
        from onnxruntime.quantization import QuantType, quantize_dynamic
        int8 = OUT / f'{name}-int8.onnx'
        quantize_dynamic(str(path), str(int8), weight_type=QuantType.QInt8)
        sizes = {'bytes': path.stat().st_size, 'int8_bytes': int8.stat().st_size}
    else:
        pt = OUT / f'{name}.pt'
        torch.save(model.state_dict(), pt)
        sizes = {'pt_bytes': pt.stat().st_size}
    return {
        'rows': len(rows), 'labels': dict(Counter(str(r['label']) for r in rows)),
        'cv_accuracy': round(cv['correct'] / cv['total'], 3),
        'cv_confusion': dict(cv['confusion']),
        'input_tokens_median': lengths[len(lengths) // 2], 'input_tokens_max': lengths[-1],
        **sizes,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    act = [json.loads(line) for line in open(PUB / 'pilot-act.jsonl', encoding='utf8')]
    look = [json.loads(line) for line in open(PUB / 'pilot-appearance.jsonl', encoding='utf8')]
    result = {
        'act_skip': run_one('act-skip-head', act, tok, device),
        'appearance': run_one('appearance-head', look, tok, device),
        'labels': 'authored by the reviewer; not model outputs',
    }
    (PUB / 'pilot-training-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
