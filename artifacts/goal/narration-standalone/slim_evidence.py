# -*- coding: utf-8 -*-
"""Shrink an acceptance evidence file to what can be checked independently:
per-turn prose, source, problems, engines, restore, regeneration, network."""
import json
import sys
from pathlib import Path


def slim(d):
    out = {
        'runId': d.get('runId'), 'status': d.get('status'), 'intent': d.get('intent'),
        'base': d.get('base'), 'turnsFile': d.get('turnsFile'),
        'startedAt': d.get('startedAt'), 'finishedAt': d.get('finishedAt'),
        'readyMs': d.get('readyMs'), 'models': d.get('models'),
        'programNarrationAccepted': d.get('programNarrationAccepted'),
        'failures': d.get('failures'), 'turnFailures': d.get('turnFailures'),
        'refreshRestore': {k: (d.get('refreshRestore') or {}).get(k) for k in
                           ('ms', 'entriesBefore', 'entriesAfter', 'historyStable', 'stateRestored',
                            'entriesRestored', 'overallRestored', 'pageSaysRestored')},
        'regeneration': d.get('regeneration'),
        'network': {
            'modelRequests': [r.get('url', '').split('/')[-1] for r in
                              (d.get('network') or {}).get('modelRequests', [])],
            'persistenceRequests': len((d.get('network') or {}).get('persistenceRequests', [])),
        },
        'harness': {k: (d.get('harness') or {}).get(k) for k in
                    ('viewport', 'mobileEmulated', 'profile', 'edgeVersion')},
        'turns': [],
    }
    for t in d.get('turns') or []:
        p = t.get('product') or {}
        calls = p.get('semanticCalls') or []
        narr = [c for c in calls if isinstance(c, dict) and c.get('task') == 'narration']
        out['turns'].append({
            'id': t.get('id'), 'input': t.get('input'), 'text': t.get('text'),
            'textSource': t.get('textSource'), 'problems': t.get('problems'),
            'timings': {k: (t.get('timings') or {}).get(k) for k in
                        ('doneMs', 'acceptedMs', 'firstReadableMs')},
            'historyDelta': t.get('historyDelta'),
            'narrationModel': p.get('narrationModel'), 'source': p.get('source'),
            'engines': [{'role': e.get('role'), 'modelId': e.get('modelId'), 'bytes': e.get('bytes')}
                        for e in (p.get('engines') or [])],
            'narrationCalls': len(narr),
            'narrationSources': sorted({c.get('source') for c in narr}),
            'semanticCalls': len(calls),
        })
    return out


def main():
    src = Path(sys.argv[1])
    dst = src.with_name(src.stem + '-slim.json')
    dst.write_text(json.dumps(slim(json.loads(src.read_text(encoding='utf-8-sig'))), ensure_ascii=False, indent=1),
                   encoding='utf8')
    print(dst, dst.stat().st_size)


if __name__ == '__main__':
    main()
