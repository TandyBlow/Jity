"""D/W 两臂评分：以权威事实为准（u240 短句不是标准答案）。"""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / 'artifacts' / 'cohesion-split'
SPLIT = '的了也把在被着得，。、；'
SPECULATION = ('仿佛', '似乎', '显然', '为了', '因为', '像是', '可能', '也许', '好像')
TEMPORAL = ('随后', '接着', '然后', '于是', '随着', '之后')


def fragments(text):
    pieces, buffer = [], ''
    for char in text:
        if char in SPLIT or not ('\u4e00' <= char <= '\u9fff'):
            if len(buffer) >= 2:
                pieces.append(buffer)
            buffer = ''
        else:
            buffer += char
    if len(buffer) >= 2:
        pieces.append(buffer)
    return pieces


def fact_tokens(fact):
    """事实内容的最小判据：去掉姓名后，按 2 字以上片段查在不在输出里。"""
    body = fact['factText'].replace('→', '，')
    tokens = [t for t in fragments(body)]
    return tokens


def score(source, text):
    result = {'support': True, 'missing': [], 'repeat': False,
              'orderViolation': False, 'relationViolation': [], 'speculation': [],
              'temporalWords': [], 'extra': ''}
    positions = []
    for fact in source['facts']:
        missing = [t for t in fact_tokens(fact) if t not in text]
        if missing:
            result['support'] = False
            result['missing'].append({'factId': fact['factId'], 'missing': missing})
        tokens = [t for t in fact_tokens(fact) if t in text]
        if tokens:
            positions.append((fact['factId'], text.index(tokens[0])))
    if any(positions[i][1] > positions[i + 1][1] for i in range(len(positions) - 1)):
        result['orderViolation'] = True

    allowed_pairs = {tuple(pair) for pair in source['relations']}
    words = [w for w in TEMPORAL if w in text]
    result['temporalWords'] = words
    if words and not allowed_pairs:
        result['relationViolation'].append('无授权却使用先后词')
    elif words and allowed_pairs:
        result['relationViolation'].append('有授权但未核对位置')

    result['speculation'] = [w for w in SPECULATION if w in text]
    result['repeat'] = bool(re.search(r'(.{2,6})[,，]\1', text.replace(',', '，')))

    residue = text
    for fact in source['facts']:
        for token in fact_tokens(fact):
            residue = residue.replace(token, '')
        if fact.get('name'):
            residue = residue.replace(fact['name'], '')
    for token in fragments(source['visible']) + fragments(source['scene']):
        residue = residue.replace(token, '')
    for char in '的了也把在被着得，。、；上下里外到从过再又还向在是有没有':
        residue = residue.replace(char, '')
    result['extra'] = residue.strip()
    return result


def main():
    payload = json.loads((OUT / 'dw-results.json').read_text(encoding='utf-8'))
    rows = []
    for source in payload['sources']:
        row = {'sourceId': source['sourceId'], 'facts': source['facts'],
               'relations': source['relations']}
        for arm in ('D', 'W'):
            row[arm] = {'text': source[arm]['body'], 'seconds': source[arm]['seconds'],
                        'promptChars': source[arm]['promptChars'],
                        **score(source, source[arm]['body'])}
        rows.append(row)

    summary = {}
    for arm in ('D', 'W'):
        summary[arm] = {
            'support': sum(1 for r in rows if r[arm]['support']),
            'missingSources': [r['sourceId'] for r in rows if not r[arm]['support']],
            'orderViolation': [r['sourceId'] for r in rows if r[arm]['orderViolation']],
            'relationViolation': [r['sourceId'] for r in rows if r[arm]['relationViolation']],
            'speculation': [r['sourceId'] for r in rows if r[arm]['speculation']],
            'repeat': [r['sourceId'] for r in rows if r[arm]['repeat']],
            'extraSources': sum(1 for r in rows if r[arm]['extra']),
            'seconds': round(sum(r[arm]['seconds'] for r in rows), 1),
            'promptChars': round(sum(r[arm]['promptChars'] for r in rows) / len(rows)),
        }
    (OUT / 'dw-scores.json').write_text(json.dumps({'summary': summary, 'rows': rows},
                                                   ensure_ascii=False, indent=1),
                                        encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for row in rows:
        for arm in ('D', 'W'):
            item = row[arm]
            if (not item['support']) or item['orderViolation'] or item['relationViolation'] \
                    or item['speculation']:
                print(row['sourceId'], arm,
                      '缺失' if not item['support'] else '',
                      '乱序' if item['orderViolation'] else '',
                      item['relationViolation'], item['speculation'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
