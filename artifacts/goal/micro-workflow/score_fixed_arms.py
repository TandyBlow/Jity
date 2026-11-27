# -*- coding: utf-8 -*-
"""Score the existence heads on their route holdouts, torch and ONNX side by side.

Arms available offline:
  rules      -- 环境=/信息= tag present in the raw settled facts (abstain = no tag)
  heads      -- MiniRBT existence head on the tag-stripped turn text (torch)
  heads-onnx -- the shipped int8 ONNX file on the same text (parity check)
Prints per-field accuracy/confusion and whether torch and ONNX agree.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from transformers import BertConfig, BertModel, BertTokenizer
from head_io import load_head

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODELS = ROOT / '.local/micro-semantic'
ONNX = ROOT / '.local/micro-heads'
MAXLEN = 256
MARKER = re.compile('；?(?:去向|环境|信息|涉及)=[^；。]*')
TAG = {'env': re.compile('环境[=＝]'), 'info': re.compile('信息[=＝]')}


class Heads(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        hidden = self.bert.config.hidden_size
        self.info = nn.Linear(hidden, 2)
        self.env = nn.Linear(hidden, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.info(cls), self.env(cls)


def field_rows(field, holdout):
    rows = [json.loads(line) for line in (HERE / 'semantic-existence.jsonl').read_text(encoding='utf8').splitlines()
            if line.strip()]
    return [row for row in rows if row['field'] == field and str(row['rowId']).startswith(holdout)]


def raw_tag(row, field):
    dataset = json.loads(next(line for line in (HERE / 'real-semantic.jsonl').read_text(encoding='utf8').splitlines()
                              if json.loads(line)['id'] == row['rowId']))
    facts = [str(item.get('text') or '') for item in dataset.get('settled') or [] if item.get('task') == 'results']
    return any(TAG[field].search(text) for text in facts)


def main():
    fields = [('env', 'sm6-'), ('info', 'sm10-')]
    tok = BertTokenizer.from_pretrained(SNAP)
    report = {}
    for field, holdout in fields:
        model = load_head(MODELS / f'semantic-heads-{field}.pt', SNAP)
        model.eval()
        rows = field_rows(field, holdout)
        if not rows:
            continue
        session = None
        import onnxruntime as ort
        session = ort.InferenceSession(str(ONNX / f'existence-{field}-int8.onnx'), providers=['CPUExecutionProvider'])
        confusion = {'rules': {}, 'heads': {}, 'onnx': {}}
        agree = 0
        for row in rows:
            label = bool(row['label'])
            enc = tok(row['text'], truncation=True, max_length=MAXLEN)
            ids = torch.tensor([enc['input_ids']])
            mask = torch.tensor([enc['attention_mask']])
            with torch.no_grad():
                logits = model(ids, mask)[0 if field == 'info' else 1][0]
            pred = int(logits.argmax().item()) == 1
            out = session.run(None, {'input_ids': ids.numpy().astype(np.int64),
                                     'attention_mask': mask.numpy().astype(np.int64)})[0][0]
            onnx_pred = int(np.argmax(out)) == 1
            agree += int(pred == onnx_pred)
            guesses = {'rules': raw_tag(row, field), 'heads': pred, 'onnx': onnx_pred}
            for arm, guess in guesses.items():
                cell = ('tp' if guess else 'fn') if label else ('fp' if guess else 'tn')
                confusion[arm][cell] = confusion[arm].get(cell, 0) + 1
        report[field] = {'rows': len(rows), 'parity': f'{agree}/{len(rows)}', 'confusion': confusion}
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
