# -*- coding: utf-8 -*-
"""Evaluate fp32 vs int8 ONNX on the per-task holdout rows."""
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
DATA = ROOT / 'artifacts/goal/micro-redesign/labels.jsonl'
OUT = ROOT / 'artifacts/goal/micro-quant'
MODELS = {
    'fp32': ROOT / '.local/micro-quant/shared-split.onnx',
    'int8': ROOT / '.local/micro-quant/shared-split-int8.onnx',
}
TASKS = json.loads((ROOT / '.local/micro-quant/tasks.json').read_text(encoding='utf8'))
SPLITS = json.loads((ROOT / '.local/micro-quant/split.json').read_text(encoding='utf8'))
ORDER = ['targets', 'position', 'intent', 'judgment']
MAXLEN = 128


def main():
    rows = [json.loads(line) for line in open(DATA, encoding='utf8')]
    by_task = {task: [r for r in rows if r['task'] == task] for task in TASKS}
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    sessions = {name: ort.InferenceSession(str(path), providers=['CPUExecutionProvider']) for name, path in MODELS.items()}

    def predict(name, task, i):
        row = by_task[task][i]
        enc = tok(row['input'], truncation=True, max_length=MAXLEN)
        feeds = {
            'input_ids': np.array(enc['input_ids'], dtype=np.int64)[None, :],
            'attention_mask': np.array(enc['attention_mask'], dtype=np.int64)[None, :],
        }
        logits = sessions[name].run(None, feeds)[ORDER.index(task)][0]
        return [TASKS[task][j] for j, v in enumerate(logits) if v > 0]

    def expected(label):
        return set(label) if isinstance(label, list) else {label}

    result = {}
    for name in MODELS:
        result[name] = {}
        for task in ORDER:
            hits = 0
            for i in SPLITS[task]['test']:
                hits += int(set(predict(name, task, i)) == expected(by_task[task][i]['label']))
            result[name][task] = f'{hits}/{len(SPLITS[task]["test"])}'
    agree = total = 0
    for task in ORDER:
        for i in SPLITS[task]['test']:
            agree += int(predict('fp32', task, i) == predict('int8', task, i))
            total += 1
    result['agreement'] = f'{agree}/{total}'
    (OUT / 'accuracy.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
