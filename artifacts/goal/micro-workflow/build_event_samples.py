# -*- coding: utf-8 -*-
"""Event-level env samples from settled facts (program-verified).

Positive: the fact carries `环境=`. Negative: no env verb anywhere in the fact.
A fact that mentions an env verb without a recorded tag stays unlabeled.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = HERE / 'real-semantic.jsonl'
OUT = HERE / 'semantic-events.jsonl'
# 结构化标记是标签本身，训练输入不能带
MARKER = re.compile(r'；?(?:去向|环境|信息|涉及)=[^；。]*')
ENV_ACTION = re.compile('提开|掀开|翻开|拉开|推开|推|挪动|挪开|拖动|拖到|拖开|拖走|移开|让出|固定|释放|扣好|放下|放倒|关上|搬到|摆到|挂到|插进|拔出|扶正|撕下|踢开|推倒|拉下|盖上|盖回|擦净|清理')


def main():
    rows = [json.loads(line) for line in DATASET.read_text(encoding='utf8').splitlines() if line.strip()]
    sys.path.insert(0, str(HERE))
    from real_semantic_data import read_env_hints
    samples = []
    for row in rows:
        if row.get('source') != 'semantic':
            continue
        for index, fact in enumerate(row.get('settled') or []):
            if fact.get('task') != 'results' or not fact.get('text'):
                continue
            text = fact['text']
            if read_env_hints([text]):
                label = True
            elif not ENV_ACTION.search(text):
                label = False
            else:
                continue
            samples.append({'id': f"{row['id']}#{index}", 'field': 'env', 'text': MARKER.sub('', text),
                            'label': label, 'rowId': row['id'], 'class': row.get('class')})
    OUT.write_text(''.join(json.dumps(sample, ensure_ascii=False) + '\n' for sample in samples), encoding='utf8')
    counts = {'pos': sum(1 for sample in samples if sample['label']),
              'neg': sum(1 for sample in samples if not sample['label'])}
    print(json.dumps({'samples': len(samples), **counts}, ensure_ascii=False))


if __name__ == '__main__':
    main()
