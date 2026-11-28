# -*- coding: utf-8 -*-
"""Canonical human-written narration corpus: the union of every prompt/target
file under .local/narr-train, deduplicated by target text, with provenance."""
import hashlib
import json
from pathlib import Path

ROOT = Path('D:/others/Jity')
NARR = ROOT / '.local/narr-train'
OUT = Path(__file__).resolve().parent / 'narration-corpus.jsonl'


def main():
    rows, seen = [], set()
    for path in sorted(NARR.glob('*.jsonl')):
        for line in path.read_text(encoding='utf8').splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            target = str(row.get('target') or '').strip()
            prompt = str(row.get('prompt') or '')
            if not target or '事实：' not in prompt:
                continue
            key = hashlib.sha256(target.encode('utf8')).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            rows.append({'id': row.get('id'), 'prompt': prompt, 'target': target,
                         'file': path.name, 'hash': key[:12]})
    OUT.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf8')
    print(json.dumps({'corpus': len(rows), 'files': len(list(NARR.glob('*.jsonl')))}, ensure_ascii=False))


if __name__ == '__main__':
    main()
