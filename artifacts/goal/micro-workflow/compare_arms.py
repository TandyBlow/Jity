# -*- coding: utf-8 -*-
"""Offline arm comparison for the env/info existence fields.

Arms measured here:
  rules      -- the program channel's own decision (环境=/信息= tag present)
  classifier -- the trained MiniRBT existence head on tag-stripped text
Generative / hybrid / LLM arms are page arms and are measured separately from
their own acceptance evidence. Labels are the verified four-state export."""
import json
import sys
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
DATASET = HERE / 'real-semantic.jsonl'
MODELS = ROOT / '.local/micro-semantic'
MAXLEN = 256
MARKERS = {
    'env': '环境[=＝]',
    'info': '信息[=＝]',
}


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


def strip_markers(text):
    import re
    return re.sub('；?(?:去向|环境|信息|涉及)=[^；。]*', '', text)


def main():
    field = sys.argv[1] if len(sys.argv) > 1 else 'env'
    holdout = sys.argv[2] if len(sys.argv) > 2 else ''
    rows = [json.loads(line) for line in DATASET.read_text(encoding='utf8').splitlines() if line.strip()]
    samples = []
    import re
    marker = re.compile(MARKERS[field])
    for row in rows:
        if row.get('source') != 'semantic':
            continue
        if holdout and not str(row.get('id', '')).startswith(holdout):
            continue
        label = ((row.get('label') or {}).get(field) or {})
        if label.get('target') not in (True, False) or not label.get('trainable'):
            continue
        facts = [str(item.get('text') or '') for item in row.get('settled') or [] if item.get('task') == 'results']
        text = strip_markers(' '.join(facts))[:1200]
        samples.append({'id': row['id'], 'text': text, 'label': bool(label['target']),
                        'rules': any(marker.search(fact) for fact in facts)})
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tok = BertTokenizer.from_pretrained(SNAP)
    model = torch.load(MODELS / f'semantic-heads-{field}.pt', map_location='cpu', weights_only=False)
    model.eval().to(device)
    totals = {arm: {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0} for arm in ('rules', 'classifier')}
    with torch.no_grad():
        for sample in samples:
            enc = tok(sample['text'], truncation=True, max_length=MAXLEN)
            ids = torch.tensor([enc['input_ids']], device=device)
            mask = torch.tensor([enc['attention_mask']], device=device)
            logits = model(ids, mask)[0 if field == 'info' else 1][0]
            pred = int(logits.argmax().item()) == 1
            for arm, guess in (('rules', sample['rules']), ('classifier', pred)):
                cell = ('tp' if guess else 'fn') if sample['label'] else ('fp' if guess else 'tn')
                totals[arm][cell] += 1
    report = {}
    for arm, cells in totals.items():
        pos = cells['tp'] + cells['fn']
        neg = cells['tn'] + cells['fp']
        report[arm] = {'accuracy': round((cells['tp'] + cells['tn']) / max(1, len(samples)), 3),
                       'precision': round(cells['tp'] / max(1, cells['tp'] + cells['fp']), 3),
                       'recall': round(cells['tp'] / max(1, pos), 3), 'pos': pos, 'neg': neg, **cells}
    print(json.dumps({'field': field, 'samples': len(samples), 'arms': report}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
