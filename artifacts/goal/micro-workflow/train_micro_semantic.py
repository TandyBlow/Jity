# -*- coding: utf-8 -*-
"""Training entry gate: verify data hashes and the six-condition validator
before any micro task sees the training export. The three-task training is the
next step; this entry refuses to run if the gate fails."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / 'real-semantic.jsonl'
TRAIN = HERE / 'real-semantic-train.jsonl'
TEST = HERE / 'real-semantic-test.jsonl'
MANIFEST = HERE / 'real-semantic-manifest.json'


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]


def main():
    if not MANIFEST.exists():
        print('no manifest; run real_semantic_data.py first', file=sys.stderr)
        sys.exit(1)
    manifest = json.loads(MANIFEST.read_text(encoding='utf8'))
    if hashlib.sha256(RAW.read_bytes()).hexdigest() != manifest.get('raw'):
        print('raw hash mismatch', file=sys.stderr)
        sys.exit(1)
    train = read_jsonl(TRAIN)
    test = read_jsonl(TEST)
    if hashlib.sha256(json.dumps(train, ensure_ascii=False).encode('utf8')).hexdigest() != manifest.get('train'):
        print('train hash mismatch', file=sys.stderr)
        sys.exit(1)
    if hashlib.sha256(json.dumps(test, ensure_ascii=False).encode('utf8')).hexdigest() != manifest.get('test'):
        print('test hash mismatch', file=sys.stderr)
        sys.exit(1)
    from validate_real_semantic import main as validate
    validate()
    print(json.dumps({'trainRows': len(train), 'testRows': len(test),
                      'manifest': manifest}, ensure_ascii=False, indent=1))
    # The three task models (existence, specialized extraction, support) are
    # trained here in the next step; the gate above is mandatory.


if __name__ == '__main__':
    main()
