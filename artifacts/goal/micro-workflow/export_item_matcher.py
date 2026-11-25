# -*- coding: utf-8 -*-
"""Export and quantize the item matcher fetched from the cluster."""
import json
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
FETCH = ROOT / '.local/item-fetch'
OUT = ROOT / '.local/micro-heads'
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
    report = json.loads((FETCH / 'item-matcher-report.json').read_text(encoding='utf8'))
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    row = json.loads(next(open(PUB / 'matcher-pairs.jsonl', encoding='utf8')))
    enc = tok(row['context'], row['candidate'], truncation=True, max_length=MAXLEN)
    ids = torch.tensor([enc['input_ids']])
    mask = torch.tensor([enc['attention_mask']])
    model = PairScorer()
    model.load_state_dict(torch.load(FETCH / 'item-matcher.pt', map_location='cpu'))
    model.eval()
    path = OUT / 'item-matcher.onnx'
    torch.onnx.export(model, (ids, mask), path,
                      input_names=['input_ids', 'attention_mask'], output_names=['score'],
                      dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                    'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = OUT / 'item-matcher-int8.onnx'
    quantize_dynamic(str(path), str(int8), weight_type=QuantType.QInt8)
    rows = [json.loads(line) for line in open(PUB / 'matcher-pairs.jsonl', encoding='utf8')]
    lengths = sorted(len(tok(r['context'], r['candidate'])['input_ids']) for r in rows)
    report.update({
        'bytes': path.stat().st_size, 'int8_bytes': int8.stat().st_size,
        'input_tokens_median': lengths[len(lengths) // 2], 'input_tokens_max': lengths[-1],
    })
    (PUB / 'item-matcher-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
