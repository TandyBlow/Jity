# -*- coding: utf-8 -*-
"""Generate multi-hop key-transfer scenarios with deterministic answers."""
import json
import random
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-reasoning'
CHARS = ['路明非', '诺诺', '芬格尔', '林亦舟', '秦越', '阿豹']
KS = [2, 3, 4, 6, 8, 12, 16]


def gen(idx, rng):
    k = rng.choice(KS)
    holder = rng.choice(CHARS)
    initial = holder
    facts, tags = [], set()
    for _ in range(k):
        rec = rng.choice([c for c in CHARS if c != holder])
        pronoun = rng.random() < 0.25
        giver = '他' if pronoun else holder
        if pronoun:
            tags.add('pronoun')
        roll = rng.random()
        if roll < 0.55:
            text = f'{giver}把钥匙交给{rec}。'
            kind, new = 'give', rec
        elif roll < 0.7:
            text = f'{giver}想把钥匙交给{rec}，被拦住了。'
            kind, new = 'blocked', holder
            tags.add('blocked')
        elif roll < 0.85:
            text = f'{giver}没有把钥匙交给{rec}。'
            kind, new = 'negated', holder
            tags.add('negation')
        else:
            text = f'{giver}把钥匙交给{rec}，又把钥匙拿了回来。'
            kind, new = 'compound', holder
            tags.add('compound')
        facts.append({'text': text, 'kind': kind, 'giver': giver, 'recipient': rec})
        holder = new
    tags.add('long' if k >= 8 else 'short')
    return {'id': f'r{idx:03d}', 'initial': initial, 'facts': facts, 'answer': holder, 'k': k, 'tags': sorted(tags)}


def main():
    rng = random.Random(20261124)
    dev = [gen(i, rng) for i in range(1, 61)]
    test = [gen(i, rng) for i in range(61, 181)]
    (PUB / 'dev.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in dev), encoding='utf8')
    (PUB / 'test.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in test), encoding='utf8')
    print('dev', len(dev), 'test', len(test), 'ks', sorted({r['k'] for r in test}))


if __name__ == '__main__':
    main()
