# -*- coding: utf-8 -*-
"""Write the eval rows (inputs only) for the 0.6B browser arm."""
import json
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-eval'
OUT = ROOT / '.local/probe-transformers/models/eval-rows.json'


def main():
    rows = [json.loads(line) for line in open(PUB / 'dataset.jsonl', encoding='utf8')]
    slim = [{k: r[k] for k in ('id', 'action', 'present', 'current', 'candidates', 'dice')} for r in rows]
    OUT.write_text(json.dumps(slim, ensure_ascii=False), encoding='utf8')
    print('rows', len(slim))


if __name__ == '__main__':
    main()
