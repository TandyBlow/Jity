# -*- coding: utf-8 -*-
"""Score the 0.6B arm against the 300-row eval set."""
import json
import statistics
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-eval'
TAGS = ['unknown_person', 'unknown_place', 'multi_turn', 'compound', 'implicit', 'context']


def main():
    rows = [json.loads(line) for line in open(PUB / 'dataset.jsonl', encoding='utf8')]
    by_id = {r['id']: r for r in rows}
    preds, times = {}, []
    starts = []
    for line in open(PUB / 'eval-06b.log', encoding='utf8'):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not rec.get('ok'):
            continue
        starts.append(rec.get('start'))
        for row in rec['rows']:
            preds[row['id']] = row['pred']
            times.append(row['ms'])
    stats = {'n': len(rows), 'parsed': 0, 'targets': 0, 'destination': 0, 'negated': 0, 'all': 0}
    by_tag = {t: {'n': 0, 'targets': 0, 'destination': 0, 'negated': 0, 'all': 0} for t in TAGS}
    for r in rows:
        p = preds.get(r['id'])
        if not isinstance(p, dict):
            continue
        stats['parsed'] += 1
        pt = p.get('targets') if isinstance(p.get('targets'), list) else []
        pt = [str(x) for x in pt]
        pdest = p.get('destination')
        pneg = p.get('negated')
        t = sorted(pt) == sorted(r['expect']['targets'])
        d = pdest == r['expect']['destination']
        n = pneg is r['expect']['negated'] if isinstance(pneg, bool) else False
        stats['targets'] += t
        stats['destination'] += d
        stats['negated'] += n
        stats['all'] += t and d and n
        for tag in r['tags']:
            if tag in by_tag:
                by_tag[tag]['n'] += 1
                by_tag[tag]['targets'] += t
                by_tag[tag]['destination'] += d
                by_tag[tag]['negated'] += n
                by_tag[tag]['all'] += t and d and n
    print('starts', starts)
    times.sort()
    stats['ms_p50'] = statistics.median(times) if times else None
    stats['ms_p95'] = times[int(len(times) * 0.95)] if times else None
    out = {'overall': stats, 'by_tag': by_tag}
    (PUB / 'results-06b.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
