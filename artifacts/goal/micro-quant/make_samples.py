# -*- coding: utf-8 -*-
"""Write 32/128/512-token probe samples from the 512-id semantic prompt sample."""
import json
from pathlib import Path

ROOT = Path('D:/others/Jity')
SRC = ROOT / '.local/micro-nlu/minirbt-sample-ids.json'
OUT = ROOT / '.local/probe-transformers/models'


def main():
    ids = json.loads(SRC.read_text(encoding='utf8'))['ids']
    for n in (32, 128, 512):
        part = ids[:n] if len(ids) >= n else ids + [0] * (n - len(ids))
        (OUT / f'quant-{n}.json').write_text(json.dumps({'ids': part}), encoding='utf8')
        print(n, len(part))


if __name__ == '__main__':
    main()
