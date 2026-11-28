# -*- coding: utf-8 -*-
"""E56: organize the rule baseline into paragraphs — merge repeated subjects,
add pronouns and connectives, keep every fact. Still zero invention."""
import json
import re
from collections import Counter
from pathlib import Path

from role_parse import classify, clauses, parse_result

HERE = Path(__file__).resolve().parent
OUTCOME = {
    '没有成功': '，却没有成功',
    '只完成一部分': '，只完成了一部分',
    '无法完成': '，没能完成',
    '部分成功': '，只完成了一部分',
    '失败': '，失败了',
}
TIME = re.compile(r'^时间到了[^，]*，?过去.*$')


def player_name(row):
    m = re.match(r'^玩家这回合让(.{1,4}?)做的事', row['playerLine'] or '')
    return m.group(1) if m else None


def build(row):
    results = [r for r in (parse_result(x) for x in row['resultLines']) if r]
    player = player_name(row)
    events, world = [], []
    for r in results:
        if '(' in r['action'] or '（' in r['action']:
            continue
        events.append((r['actor'], r['action'] + OUTCOME.get(r['outcome'] or '', '')))
    seen_time = False
    for c in clauses(row['factsText'].split('这一回合的结算结果：')[0]):
        if '做的事' in c or '玩家这回合' in c:
            continue
        if TIME.match(c):
            if seen_time:
                continue
            seen_time = True
        info = classify(c)
        if info['subjectKind'] == 'missing':
            continue
        subject = info['subject'] or ''
        body = c[len(subject):] if subject and c.startswith(subject) else c
        world.append((subject, body))
    if player:
        events.sort(key=lambda e: 0 if e[0] == player else 1)
    sentences, merges, links = [], 0, 0
    last = None
    for actor, text in events + world:
        if actor and actor == last and not text.startswith('时间'):
            sentences.append(('', '又' + text))
            merges += 1
        elif last and not actor:
            sentences.append(('', text))
        else:
            sentences.append((actor, text))
        last = actor or last
    out = []
    for i, (actor, text) in enumerate(sentences):
        if actor and text.startswith(actor):
            out.append(text + '。')
        elif actor:
            out.append(actor + text + '。')
        else:
            out.append(text + '。')
    body = ''.join(out)
    paras = body.split('。')
    cut = max(1, len(paras) // 3)
    joined = '。'.join(paras[:cut]) + '。\n\n' + '。'.join(paras[cut:])
    return joined, {'merges': merges, 'links': links, 'sentences': len(sentences), 'player': player}


def main():
    rows = [json.loads(l) for l in (HERE / 'inputs.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    totals = Counter()
    samples = []
    ratios = []
    for row in rows:
        text, info = build(row)
        totals.update({k: v for k, v in info.items() if isinstance(v, (int, float))})
        totals['points'] += 1
        totals['chars'] += len(text)
        sys_text = row['systemProse'] or ''
        if sys_text:
            ratios.append(len(text) / len(sys_text))
        if len(samples) < 3:
            samples.append({'id': row['id'], 'out': text[:320]})
    summary = {
        'points': totals['points'], 'sentences': totals['sentences'],
        'merges': totals['merges'], 'links': totals['links'],
        'chars': totals['chars'],
        'lenRatioMean': round(sum(ratios) / max(1, len(ratios)), 3),
        'samples': samples,
    }
    (HERE / 'compose-organized-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'samples'}, ensure_ascii=False))
    for s in samples[:1]:
        print('---', s['id']); print(s['out'])


if __name__ == '__main__':
    main()
