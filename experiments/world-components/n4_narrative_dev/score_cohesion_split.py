"""协同拆分对照的评分：事实保持、未授权新增、重复、以及盲评用的清单。"""
import json
import pathlib
import random
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / 'artifacts' / 'cohesion-split'

REST_OK = set('的着了也，。、；上下里外把到从过再又还向在是有没有')

FACT_NOISE = ('随后', '然后', '接着', '此时', '这时', '于是', '而', '便')


SPLIT = '的了也把在被着得，。、；'


def fragments(text):
    pieces, buffer = [], ''
    for char in text:
        if char in SPLIT or not ('一' <= char <= '鿿'):
            if len(buffer) >= 2:
                pieces.append(buffer)
            buffer = ''
        else:
            buffer += char
    if len(buffer) >= 2:
        pieces.append(buffer)
    return [w for w in pieces if w not in FACT_NOISE]


def fact_tokens(sentence):
    """事实内容的最小判据：姓名 + 内容里 2 字以上的片段（去重）。

    用词级包含而不是整句连续匹配——改写措辞不算丢事实。
    """
    body = sentence.rstrip('。')
    tokens = []
    seen = set()
    for piece in fragments(body):
        if piece in seen:
            continue
        seen.add(piece)
        tokens.append(piece)
    return tokens


def check(source, text):
    result = {'support': True, 'missing': [], 'repeat': False, 'extra': ''}
    for fact in source['facts']:
        missing = [piece for piece in fact_tokens(fact['u240'])
                   if piece not in text]
        if missing:
            result['support'] = False
            result['missing'].append({'factId': fact['factId'], 'missing': missing})
    result['repeat'] = bool(re.search(r'(.{2,6})[,，]\1', text.replace(',', '，')))

    residue = text
    for fact in source['facts']:
        residue = residue.replace(fact['u240'].rstrip('。'), '')
        residue = residue.replace(fact['name'], '')
    for token in fragments(source['visible']) + fragments(source['scene']):
        residue = residue.replace(token, '')
    for char in REST_OK:
        residue = residue.replace(char, '')
    result['extra'] = residue.strip()
    return result


def main():
    payload = json.loads((OUT / 'results.json').read_text(encoding='utf-8'))
    rows, blind = [], []
    rng = random.Random(20261104)
    for source in payload['sources']:
        a = check(source, source['A']['text'])
        b = check(source, source['B']['text'])
        b['text'] = source['B']['text']
        rows.append({'sourceId': source['sourceId'],
                     'A': {**a, 'text': source['A']['text']},
                     'B': {**b, 'text': source['B']['text'],
                           'seconds': source['B']['seconds']},
                     'facts': source['facts'], 'relations': source['relations']})
        flip = rng.random() < 0.5
        first, second = (('B', b['text']), ('A', source['A']['text'])) if flip \
            else (('A', source['A']['text']), ('B', b['text']))
        blind.append({'sourceId': source['sourceId'], 'flip': flip,
                      'order': [first[0], second[0]],
                      'text1': first[1], 'text2': second[1]})

    summary = {
        'sources': len(rows),
        'A': {'support': sum(1 for r in rows if r['A']['support']),
              'repeat': sum(1 for r in rows if r['A']['repeat']),
              'extra': sum(1 for r in rows if r['A']['extra'])},
        'B': {'support': sum(1 for r in rows if r['B']['support']),
              'repeat': sum(1 for r in rows if r['B']['repeat']),
              'extra': sum(1 for r in rows if r['B']['extra'])},
        'Bseconds': {'total': round(sum(r['B'].get('seconds', 0) for r in rows), 2),
                     'mean': round(sum(r['B'].get('seconds', 0) for r in rows)
                                   / max(len(rows), 1), 2)},
    }
    (OUT / 'scores.json').write_text(json.dumps({'summary': summary, 'rows': rows},
                                                ensure_ascii=False, indent=1),
                                     encoding='utf-8')
    (OUT / 'blind.json').write_text(json.dumps(blind, ensure_ascii=False, indent=1),
                                    encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for row in rows:
        if not row['B']['support'] or row['B']['extra'] or row['B']['repeat']:
            print(row['sourceId'], '| 缺失', [m['missing'] for m in row['B']['missing']],
                  '| 重复', row['B']['repeat'], '| 残余', row['B']['extra'][:40])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
