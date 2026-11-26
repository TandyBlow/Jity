# -*- coding: utf-8 -*-
"""Turn-level existence examples for the info/env heads.

One row per field and turn: the player action and the settled facts, with the
binary label from the verified export. The state diff is deliberately not in
the text: printing 环境差分 would hand the head its own label."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRAIN = HERE / 'real-semantic-train.jsonl'
OUT = HERE / 'semantic-existence.jsonl'


def main():
    rows = [json.loads(line) for line in TRAIN.read_text(encoding='utf8').splitlines() if line.strip()]
    samples = []
    for row in rows:
        facts = ' '.join(str(item.get('text') or '') for item in row.get('settled') or []
                         if item.get('task') == 'results')[:900]
        text = f"玩家：{row.get('input') or ''}\n事实：{facts}"[:1200]
        for field, label in (row.get('labels') or {}).items():
            if label.get('target') not in (True, False):
                continue
            samples.append({'id': f"{row['id']}:{field}", 'rowId': row['id'], 'field': field, 'text': text,
                            'label': bool(label['target']), 'class': row.get('class')})
    OUT.write_text(''.join(json.dumps(sample, ensure_ascii=False) + '\n' for sample in samples), encoding='utf8')
    counts = {}
    for sample in samples:
        key = f"{sample['field']}:{'pos' if sample['label'] else 'neg'}"
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({'samples': len(samples), **counts}, ensure_ascii=False))


if __name__ == '__main__':
    main()
