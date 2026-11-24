# -*- coding: utf-8 -*-
"""Write 8/16/32/64/128-token probe samples from the 512-id semantic prompt sample."""
import json
from pathlib import Path

ROOT = Path('D:/others/Jity')
SRC = ROOT / '.local/micro-nlu/minirbt-sample-ids.json'
OUT = ROOT / '.local/probe-transformers/models'


def main():
    ids = json.loads(SRC.read_text(encoding='utf8'))['ids']
    for n in (8, 16, 32, 64, 128):
        part = ids[:n]
        (OUT / f'joint-{n}.json').write_text(json.dumps({'ids': part}), encoding='utf8')
        print(n, len(part))


if __name__ == '__main__':
    main()
