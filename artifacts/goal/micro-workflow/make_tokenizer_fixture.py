# -*- coding: utf-8 -*-
"""Generate Python-tokenizer ids for the browser tokenizer parity test."""
import json
from pathlib import Path

from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
TOK = BertTokenizer(vocab_file=str(ROOT / 'artifacts/benchmark/minirbt-h256-snapshot/vocab.txt'))
OUT = ROOT / 'frontend/src/lib/world-engine/local/micro/tokenizer-fixture.json'

TEXTS = [
    '路明非把护目镜递给林亦舟。',
    '我把水壶递给他。',
    '诺诺把短讯机按在路明非耳边。',
    '行动：路明非把钥匙扔给诺诺。\n在场：诺诺',
    '事实：路明非走进西回廊尽头的钟楼西门。\n当前：西回廊',
    '我没有犹豫，把钥匙递给诺诺。',
    '路明非 环顾四周, 然后停下.',
    'abc DEF 123 4.5',
    '第一个人和第二个人都到了。',
    '「谁在那儿？」路明非低声问。',
    '路明非朝配电房抬了抬下巴，示意沈砚过去。',
    'A: B; C!',
    '中文English混合test',
    '  空白  空格  ',
    '[CLS] 不是特殊词',
]
PAIRS = [
    ('路明非把护目镜递给林亦舟。', '林亦舟'),
    ('我把水壶递给他。', '诺诺'),
    ('行动：路明非把钥匙扔给诺诺。\n在场：诺诺', '诺诺'),
    ('事实：路明非走进西回廊尽头的钟楼西门。\n当前：西回廊', '钟楼'),
    ('路明非问秦越要弹匣。', '秦越'),
    ('路明非朝配电房抬了抬下巴，示意沈砚过去。', '沈砚'),
    ('abc DEF 123', 'ABC'),
    ('中文English混合test', 'English'),
]


def main():
    cases = []
    for text in TEXTS:
        cases.append({'text': text, 'ids': TOK(text, truncation=True, max_length=128)['input_ids']})
    pairs = []
    for a, b in PAIRS:
        enc = TOK(a, b, truncation=True, max_length=128)
        pairs.append({'a': a, 'b': b, 'ids': enc['input_ids']})
    OUT.write_text(json.dumps({'cases': cases, 'pairs': pairs}, ensure_ascii=False, indent=1), encoding='utf8')
    print('cases', len(cases), 'pairs', len(pairs))


if __name__ == '__main__':
    main()
