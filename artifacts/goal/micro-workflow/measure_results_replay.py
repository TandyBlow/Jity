# -*- coding: utf-8 -*-
"""Fixed-input replay: run the results head on every recorded results prompt
and compare it with the LLM judgment recorded for the same call.

Same inputs both sides; no trajectory change. A call is replaceable only when
every member's softmax clears 0.45 (the browser port's threshold).
"""
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODEL = ROOT / '.local/micro-heads/task-heads-int8.onnx'
MEMBER = re.compile(r'^- (.+?)（id=([\w-]+)）行动：(.+)$', re.M)
ROLL = re.compile(r'目标(.+?)\(([\w-]+)\) 骰点=(\d+) 资格=(true|false) 准入=(true|false)')
RESULT = ['achieved', 'partial', 'not_achieved', 'blocked', 'no_change']


def main():
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    session = ort.InferenceSession(str(MODEL), providers=['CPUExecutionProvider'])
    rows = [json.loads(line) for line in open(PUB / 'records.jsonl', encoding='utf8')]

    def predict(text):
        enc = tok(text, truncation=True, max_length=64)
        ids = np.array([enc['input_ids']], dtype=np.int64)
        mask = np.array([enc['attention_mask']], dtype=np.int64)
        logits = session.run(['result'], {'input_ids': ids, 'attention_mask': mask})[0][0]
        exps = np.exp(logits - logits.max())
        p = float(exps.max() / exps.sum())
        return RESULT[int(logits.argmax())], p

    calls = replaceable = 0
    members = abstained = 0
    agree = Counter()
    per_run = Counter()
    for row in rows:
        if row['task'] != 'results':
            continue
        prompt = row['prompt']
        blocks = MEMBER.findall(prompt)
        if not blocks:
            continue
        try:
            raw = json.loads(row['raw'])
        except json.JSONDecodeError:
            continue
        truth = {j.get('memberId'): j.get('label') for j in raw.get('judgments') or []}
        calls += 1
        labels, ok = [], True
        for name, member_id, action in blocks:
            roll = ROLL.search(prompt[prompt.index(f'id={member_id}）行动'):][:400])
            text = f"角色：{name}；行动：{action[:80]}；骰点：{roll.group(3) if roll else '?'}；" \
                   f"资格：{roll.group(4) if roll else '?'}；准入：{roll.group(5) if roll else '?'}"
            label, p = predict(text)
            members += 1
            if p < 0.45:
                ok = False
                abstained += 1
                continue
            labels.append((member_id, label))
        if not ok:
            continue
        replaceable += 1
        for member_id, label in labels:
            expected = truth.get(member_id)
            if expected is None:
                continue
            agree['match' if label == expected else 'differ'] += 1
            per_run[f"{row['run']}:{'match' if label == expected else 'differ'}"] += 1
    result = {
        'results_calls': calls,
        'members': members,
        'micro_replaceable_calls': replaceable,
        'abstained_members': abstained,
        'label_agreement': dict(agree),
        'per_call_labels': dict(per_run),
    }
    (PUB / 'results-replay-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
