# -*- coding: utf-8 -*-
"""Per-field, per-class label counts for the semantic scenario set."""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = HERE / 'real-semantic.jsonl'


def main():
    rows = [json.loads(line) for line in DATASET.read_text(encoding='utf8').splitlines() if line.strip()]
    by_class = {}
    split_counts = Counter()
    for row in rows:
        label = row.get('label') or {}
        key = (row.get('class') or row.get('source'), row.get('split'))
        for field, item in label.items():
            bucket = by_class.setdefault(key, {}).setdefault(field, Counter())
            bucket[item.get('status')] += 1
            if item.get('trainable'):
                split_counts[(field, 'pos' if item.get('target') is True else 'neg')] += 1
    print(json.dumps({'byClass': {f'{k[0]}/{k[1]}': {f: dict(c) for f, c in v.items()}
                                 for k, v in sorted(by_class.items())},
                      'trainable': {f'{f}:{b}': n for (f, b), n in sorted(split_counts.items())}},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
