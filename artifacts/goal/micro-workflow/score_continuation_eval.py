# -*- coding: utf-8 -*-
"""Score a filled continuation eval sheet against rule labels and the heads.

Reads `continuation-assistant-spotcheck.json` by default; pass a human-filled
template with the same `rows` shape to use it instead. The model is not an
authority here: this prints where human, rule and model disagree.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODEL = ROOT / 'frontend/public/micro/continuation-heads-int8.onnx'
KEYS = ('novelty', 'unfinished', 'necessity', 'intervene')
THRESHOLDS = {'novelty': 0.5, 'unfinished': 0.4, 'necessity': 0.5, 'intervene': 0.5}


def overall(values, category, repeat):
    return bool(values['novelty'] and values['unfinished'] and values['necessity']
                and not values['intervene'] and category != 'wait' and repeat != 'same_world')


def main(path):
    filled = json.loads(Path(path).read_text(encoding='utf8'))
    labels = {(row['scenario'], row['candidate']): row
              for row in (json.loads(line) for line in open(PUB / 'continuation-data.jsonl', encoding='utf8'))}
    template = json.loads((PUB / 'continuation-human-eval-template.json').read_text(encoding='utf8'))
    blind = {row['id']: row for row in template['rows']}
    llm = {}
    llm_path = PUB / 'continuation-llm-arm.json'
    if llm_path.exists():
        llm = {row['id']: row['llm_continue'] for row in json.loads(llm_path.read_text(encoding='utf8'))['rows']}
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    session = ort.InferenceSession(str(MODEL), providers=['CPUExecutionProvider'])
    counts = Counter()
    detail = []
    for answer in filled['rows']:
        row = labels[(blind[answer['id']]['scenario'], blind[answer['id']]['candidate'])]
        human = {key: int(answer[key]) for key in KEYS}
        rule = {key: int(row[key]) for key in KEYS}
        enc = tok(row['context'], row['candidate'], truncation=True, max_length=160)
        logits = session.run(None, {
            'input_ids': np.array([enc['input_ids']], dtype=np.int64),
            'attention_mask': np.array([enc['attention_mask']], dtype=np.int64),
        })
        probabilities = {key: 1 / (1 + np.exp(-float(value[0]))) for key, value in zip(KEYS, logits)}
        probabilities['intervene'] = max(probabilities['intervene'], 0.75 if row['involves_protagonist'] else 0)
        model = {key: int(probabilities[key] >= THRESHOLDS[key]) for key in KEYS}
        human_overall = int(answer['overall_continue'])
        rule_overall = int(overall(rule, row['category'], row['repeat']))
        model_overall = int(overall(model, row['category'], row['repeat']))
        counts['rows'] += 1
        for key in KEYS:
            counts[f'human_rule_{key}'] += int(human[key] == rule[key])
            counts[f'human_model_{key}'] += int(human[key] == model[key])
        counts['human_rule_overall'] += int(human_overall == rule_overall)
        counts['human_model_overall'] += int(human_overall == model_overall)
        if answer['id'] in llm:
            counts['human_llm_overall'] += int(human_overall == llm[answer['id']])
            counts['llm_rows'] += 1
        if human_overall != rule_overall or human_overall != model_overall:
            detail.append({'id': answer['id'], 'scenario': row['scenario'], 'candidate': row['candidate'],
                           'human': human, 'rule': rule, 'model': model,
                           'overall': {'human': human_overall, 'rule': rule_overall, 'model': model_overall,
                                       'llm': llm.get(answer['id'])}})
    print(json.dumps({'summary': dict(counts), 'disagreements': detail}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else str(PUB / 'continuation-assistant-spotcheck.json'))
