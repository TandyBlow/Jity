# -*- coding: utf-8 -*-
"""Rule state tracker for the key-transfer scenarios (upper bound)."""
import json
import re
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-reasoning'
CHARS = ['路明非', '诺诺', '芬格尔', '林亦舟', '秦越', '阿豹']
GIVE = re.compile(r'^(?P<giver>[^把]+?)把钥匙交给(?P<rec>[^，。]+?)。$')
COMPOUND = re.compile(r'^(?P<giver>[^把]+?)把钥匙交给(?P<rec>[^，。]+?)，又把钥匙拿了回来。$')
BLOCKED = re.compile(r'^(?P<giver>[^把]+?)想把钥匙交给(?P<rec>[^，。]+?)，被拦住了。$')
NEGATED = re.compile(r'^(?P<giver>[^把]+?)没有把钥匙交给(?P<rec>[^，。]+?)。$')


def parse(text):
    for pattern, kind in ((COMPOUND, 'compound'), (BLOCKED, 'blocked'), (NEGATED, 'negated'), (GIVE, 'give')):
        m = pattern.match(text)
        if m:
            return kind, m.group('giver'), m.group('rec')
    raise ValueError(text)


def track(scenario):
    holder = scenario['initial']
    for fact in scenario['facts']:
        kind, giver, rec = parse(fact['text'])
        giver = holder if giver == '他' else giver
        if kind == 'give':
            holder = rec
        elif kind == 'compound':
            holder = giver
    return holder


def main():
    rows = [json.loads(line) for line in open(PUB / 'test.jsonl', encoding='utf8')]
    hits = sum(int(track(r) == r['answer']) for r in rows)
    print('rules', hits, '/', len(rows))


if __name__ == '__main__':
    main()
