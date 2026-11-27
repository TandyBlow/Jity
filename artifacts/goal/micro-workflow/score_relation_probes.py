# -*- coding: utf-8 -*-
"""Negation/failure relation probes from existing verified turns.

Expected on a failure turn: no information item and no environment change.
Arms: rules (a 环境=/信息= tag present is a positive), existence head (argmax),
v2 event annotation (any novel item, info only). Success turns are controls for
recall. Existing rows only; no authored golds in this slice."""
import json
import re
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODELS = ROOT / '.local/micro-semantic'
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


def main():
    rows = [json.loads(line) for line in (HERE / 'real-semantic.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
    rows = [row for row in rows if row.get('source') == 'semantic']
    v2 = {}
    v2_path = HERE / 'semantic-info-events-v2.jsonl'
    if v2_path.exists():
        for line in v2_path.read_text(encoding='utf8').splitlines():
            if line.strip():
                entry = json.loads(line)
                v2[entry['id']] = entry
    tok = BertTokenizer.from_pretrained(SNAP)
    heads = {}
    for field, index in (('env', 1), ('info', 0)):
        model = torch.load(MODELS / f'semantic-heads-{field}.pt', map_location='cpu', weights_only=False)
        model.eval()
        heads[field] = (model, index)
    report = {}
    for field in ('env', 'info'):
        model, index = heads[field]
        cells = {arm: Counter() for arm in ('rules', 'head', 'v2')}
        classes = Counter()
        for row in rows:
            # 探针集合：失败类（期望无事件）与成功类（对照）
            klass = row.get('class') or ''
            if field == 'env' and klass not in ('env_failure', 'env_success'):
                continue
            if field == 'info' and klass not in ('info_failure', 'info_new'):
                continue
            facts = [str(item.get('text') or '') for item in row.get('settled') or [] if item.get('task') == 'results']
            text = MARKER.sub('', ' '.join(facts))[:1200]
            enc = tok(text, truncation=True, max_length=MAXLEN)
            with torch.no_grad():
                logits = model(torch.tensor([enc['input_ids']]), torch.tensor([enc['attention_mask']]))[index][0]
            guesses = {
                'rules': any(TAG[field].search(item) for item in facts),
                'head': int(logits.argmax().item()) == 1,
                'v2': bool(v2.get(row['id'], {}).get('items')) if field == 'info' else None,
            }
            label = ((row.get('label') or {}).get(field) or {})
            if label.get('target') not in (True, False) or not label.get('trainable'):
                continue
            golden = bool(label['target'])
            classes[klass] += 1
            for arm, guess in guesses.items():
                if guess is None:
                    continue
                ok = (guess == golden)
                cells[arm][f'{klass}:{"hit" if ok else "miss"}'] += 1
        summary = {}
        for arm, counter in cells.items():
            summary[arm] = dict(counter)
        report[field] = {'classes': dict(classes), 'arms': summary}
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
