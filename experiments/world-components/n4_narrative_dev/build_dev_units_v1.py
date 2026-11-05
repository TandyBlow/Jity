"""Freeze the full-workflow dev units (formal-dev only) for route-split selection."""
from __future__ import annotations
import hashlib, json, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
UNITS = HERE / 'verbalizer_pairs.jsonl'
MANIFEST = ROOT / 'artifacts' / 'world-components' / 'n4-two-arm-manifest-r1.json'
OUT = HERE / 'dev-units-v1.jsonl'
FREEZE = ROOT / 'artifacts' / 'world-components' / 'route-split-dev-freeze-v1.json'


def rows(p):
    return [json.loads(l) for l in pathlib.Path(p).read_text(encoding='utf-8').splitlines()
            if l.strip()]


def parse_fact(inp, kind, name):
    m = re.search(r'事实=([^\n]+)', inp or '')
    line = m.group(1) if m else ''
    parts = [p for p in line.split('｜')]
    if kind == 'moved':
        mv = re.search(r'(.+?)→(.+)$', parts[-1]) if parts else None
        return {'kind': 'moved', 'name': parts[0] if parts else name,
                'from': mv.group(1) if mv else '', 'to': mv.group(2) if mv else ''}
    if kind == 'no_change':
        return {'kind': 'no_change', 'name': None}
    return {'kind': kind, 'name': parts[0] if parts else name,
            'text': parts[-1] if parts else '',
            'resultText': parts[-1] if parts else ''}


def main():
    man = json.loads(MANIFEST.read_text(encoding='utf-8'))
    split = {s['sourceId']: s['split'] for s in man['sources']}
    dev = [u for u in rows(UNITS) if split.get(u['sourceId']) == 'formal-dev']
    out = []
    for u in dev:
        m = re.search(r'视角=([^；\n]+)', u['input'])
        name = m.group(1).strip() if m else ''
        out.append({'id': u['pairId'], 'sourceId': u['sourceId'], 'kind': u['kind'],
                    'name': name, 'fact': parse_fact(u['input'], u['kind'], name),
                    'input': u['input']})
    with OUT.open('w', encoding='utf-8') as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    kinds = {}
    for r in out:
        kinds[r['kind']] = kinds.get(r['kind'], 0) + 1
    doc = {'version': 'route-split-dev-v1', 'created': '2026-11-05',
           'source': str(UNITS.relative_to(HERE)), 'out': str(OUT.relative_to(HERE)),
           'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
           'units': len(out), 'kinds': kinds,
           'routing': {'act': sum(v for k, v in kinds.items() if k in ('moved', 'outcome')),
                       'state': sum(v for k, v in kinds.items()
                                    if k in ('appearance_changed', 'sanity_changed',
                                             'personality_changed')),
                       'no_change': kinds.get('no_change', 0)},
           'use': 'full-workflow dev for checkpoint-pair selection only; '
                  'the 215 diagnostic units and the 10 real rounds are reporting-only'}
    FREEZE.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(doc, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    raise SystemExit(main())
