# -*- coding: utf-8 -*-
"""Event-level info examples from settled facts (program-verified).

Positive: a protagonist fact that names an information action and is not an
explicit refusal. Negative: an NPC-only fact, a movement/transfer fact, or an
explicit no-answer. This is a separate export for the existence head; the
turn-level gate stays the product acceptance."""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = HERE / 'real-semantic.jsonl'
OUT = HERE / 'semantic-info-events.jsonl'
INFO = re.compile('问|打听|询问|请教|读|看|查看|观察|检查|确认|核对|发现|听见|听到|告诉|回答|说明|报告|念|搜索|翻找')
NO_ANSWER = re.compile('没有答|没答|未答|拒绝回答|没有说|没说|问不出|没有回应|没有找到|没有看到')


def main():
    rows = [json.loads(line) for line in DATASET.read_text(encoding='utf8').splitlines() if line.strip()]
    samples = []
    for row in rows:
        if row.get('source') != 'semantic':
            continue
        for index, fact in enumerate(row.get('settled') or []):
            if fact.get('task') != 'results' or not fact.get('text'):
                continue
            text = str(fact['text'])
            if '环境=' in text:
                continue
            protagonist = row.get('protagonistId') or 'lu'
            name = row.get('protagonistName') or '路明非'
            owned = fact.get('key') == protagonist or name in text
            if not owned:
                label = False
            elif NO_ANSWER.search(text) or not INFO.search(text):
                label = False
            else:
                label = True
            samples.append({'id': f"{row['id']}#i{index}", 'field': 'info', 'text': text,
                            'label': label, 'rowId': row['id'], 'class': row.get('class')})
    OUT.write_text(''.join(json.dumps(sample, ensure_ascii=False) + '\n' for sample in samples), encoding='utf8')
    pos = sum(1 for sample in samples if sample['label'])
    print(json.dumps({'samples': len(samples), 'pos': pos, 'neg': len(samples) - pos}, ensure_ascii=False))


if __name__ == '__main__':
    main()
