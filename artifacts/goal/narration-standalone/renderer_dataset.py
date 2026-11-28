# -*- coding: utf-8 -*-
"""N10 data: fragment sequences and sentence-boundary labels from the 51
exact point pairs. A fragment is a unit the rules already selected (action,
settlement result, fact sentence); the label says whether the 1.7B reference
started a new sentence before it."""
import json
import re
from collections import Counter
from pathlib import Path

import cluster_events as ce
import evaluate_narration as ev
from role_parse import parse_result

HERE = Path(__file__).resolve().parent
OUTCOME = {
    '没有成功': '，却没有成功', '只完成一部分': '，只完成了一部分',
    '无法完成': '，没能完成', '部分成功': '，只完成了一部分', '失败': '，失败了',
}
ACTION = re.compile(r'^玩家这回合让(.{1,4}?)做的事[：:](.+)$')
THRESHOLD = 0.35


def fragments(row):
    out = []
    m = ACTION.match(row['playerLine'] or '')
    if m:
        body = m.group(2).strip().rstrip('。')
        if body:
            out.append(('action', body if body.startswith(m.group(1)) else m.group(1) + body))
    for line in row['resultLines']:
        p = parse_result(line)
        if not p:
            continue
        out.append(('result', f"{p['actor']}{p['action']}{OUTCOME.get(p['outcome'] or '', '')}"))
    for part in re.split(r'[。；]', row['factsText']):
        part = ce.clean(part)
        if len(part) < 6 or part.startswith('玩家这回合') or part.startswith('时间到了'):
            continue
        out.append(('fact', part))
    return out


def best_sentence(fragment, sentences):
    fg = ev.bigrams(fragment)
    best, score = None, 0.0
    for idx, sentence in enumerate(sentences):
        sg = ev.bigrams(sentence)
        if not fg:
            continue
        value = len(fg & sg) / len(fg)
        if value > score:
            best, score = idx, value
    return best, score


def main():
    rows = [json.loads(l) for l in (HERE / 'pairs.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    data, stats = [], Counter()
    for row in rows:
        prose = row.get('pointProse') or ''
        sentences = ev.sentences(prose)
        if not sentences:
            continue
        frags = fragments(row)
        aligned = []
        for kind, text in frags:
            idx, score = best_sentence(text, sentences)
            aligned.append({'kind': kind, 'text': text, 'sentence': idx if score >= THRESHOLD else None,
                            'score': round(score, 3)})
            stats['fragments'] += 1
            if score < THRESHOLD:
                stats['unaligned'] += 1
        pairs = []
        for i, (a, b) in enumerate(zip(aligned, aligned[1:])):
            if a['sentence'] is None or b['sentence'] is None:
                continue
            prev = aligned[i - 1]['text'] if i > 0 else ''
            nxt = aligned[i + 2]['text'] if i + 2 < len(aligned) else ''
            pairs.append({'textA': a['text'], 'kindA': a['kind'],
                          'textB': b['text'], 'kindB': b['kind'],
                          'prev': prev, 'next': nxt,
                          'boundary': int(a['sentence'] != b['sentence'])})
            stats['pairs'] += 1
            stats['boundary'] += int(a['sentence'] != b['sentence'])
        data.append({'id': row['id'], 'evidence': row['evidence'], 'sentences': len(sentences),
                     'fragments': aligned, 'pairs': pairs})
    summary = {
        'points': len(data),
        'fragments': stats['fragments'],
        'unaligned': stats['unaligned'],
        'pairs': stats['pairs'],
        'boundary': stats['boundary'],
        'boundaryRate': round(stats['boundary'] / max(1, stats['pairs']), 3),
        'sentencesMean': round(sum(d['sentences'] for d in data) / max(1, len(data)), 2),
        'fragmentsMean': round(sum(len(d['fragments']) for d in data) / max(1, len(data)), 2),
    }
    (HERE / 'renderer-dataset.json').write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf8')
    (HERE / 'renderer-dataset-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))
    for d in data[:2]:
        print('---', d['id'], 'sentences', d['sentences'])
        for a in d['fragments']:
            print('   ', a['kind'], a['sentence'], a['score'], a['text'][:44])


if __name__ == '__main__':
    main()
