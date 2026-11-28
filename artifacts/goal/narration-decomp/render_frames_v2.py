# -*- coding: utf-8 -*-
"""Frame v2: pattern id + slots that must be verbatim spans of the facts.

The renderer contributes only function words (把/在/低声说……). Any slot that is
not a contiguous substring of the joined facts is a labelling error and is
reported, so a frame can never invent content.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# pattern -> (template over slot names, required slots)
PATTERNS = {
    'S+V1': ('{S}{V}。', ['S', 'V']),
    'S+把+O+V1': ('{S}把{O}{V}。', ['S', 'O', 'V']),
    'S+V': ('{S}{V}。', ['S', 'V']),
    'S+V1，V2': ('{S}{V1}，{V2}。', ['S', 'V1', 'V2']),
    'S+V1，V2，V3': ('{S}{V1}，{V2}，{V3}。', ['S', 'V1', 'V2', 'V3']),
    'S+在+L+V': ('{S}在{L}{V}。', ['S', 'L', 'V']),
    'S+在+L+V1，V2': ('{S}在{L}{V1}，{V2}。', ['S', 'L', 'V1', 'V2']),
    'S+把+O+V': ('{S}把{O}{V}。', ['S', 'O', 'V']),
    'S+把+O+V1，V2': ('{S}把{O}{V1}，{V2}。', ['S', 'O', 'V1', 'V2']),
    'S+把+O+V1，让+X+V2': ('{S}把{O}{V1}，让{X}{V2}。', ['S', 'O', 'V1', 'X', 'V2']),
    'S+V1，没有+V2': ('{S}{V1}，没有{V2}。', ['S', 'V1', 'V2']),
    'S+没有+V': ('{S}没有{V}。', ['S', 'V']),
    'L+没有+S': ('{L}没有{S}。', ['L', 'S']),
    'S+想+V1，C+却+V2': ('{S}想{V1}，{C}却{V2}。', ['S', 'V1', 'C', 'V2']),
    'S+V1，C+却+没有+O': ('{S}{V1}，{C}却没有{O}。', ['S', 'V1', 'C', 'O']),
    'S+V1，因为+F': ('{S}{V1}，因为{F}。', ['S', 'V1', 'F']),
    'S+V1，所以+V2': ('{S}{V1}，所以{V2}。', ['S', 'V1', 'V2']),
    'F，所以+S+V': ('{F}，所以{S}{V}。', ['F', 'S', 'V']),
    'S+因为+F，V': ('{S}因为{F}{V}。', ['S', 'F', 'V']),
    'S+V1，才+V2': ('{S}{V1}，才{V2}。', ['S', 'V1', 'V2']),
    'S+V1，便+V2': ('{S}{V1}，便{V2}。', ['S', 'V1', 'V2']),
    'S+V1，后来+V2': ('{S}{V1}，后来{V2}。', ['S', 'V1', 'V2']),
    'S+先+V1，后来+V2': ('{S}先{V1}，后来{V2}。', ['S', 'V1', 'V2']),
    'S+V1，于是+V2': ('{S}{V1}，于是{V2}。', ['S', 'V1', 'V2']),
    'S+低声说：Q': ('{S}低声说：‘{Q}’', ['S', 'Q']),
    'S+V1，低声说：Q': ('{S}{V1}，低声说：‘{Q}’', ['S', 'V1', 'Q']),
    'S+把+O+V1，低声说：Q': ('{S}把{O}{V1}，低声说：‘{Q}’', ['S', 'O', 'V1', 'Q']),
    'S+V1；X+V2': ('{S}{V1}；{X}{V2}。', ['S', 'V1', 'X', 'V2']),
    'S+V1，X+却+V2': ('{S}{V1}，{X}却{V2}。', ['S', 'V1', 'X', 'V2']),
    'A+从+B+经+C+到+D': ('{A}从{B}经{C}到{D}。', ['A', 'B', 'C', 'D']),
    'A+接+B，C+通+D': ('{A}接{B}，{C}通{D}。', ['A', 'B', 'C', 'D']),
    'X的O+在+L+M': ('{X}的{O}在{L}{M}。', ['X', 'O', 'L', 'M']),
    'S+V1，等+O，看+Cl': ('{S}{V1}，等{O}，看{Cl}。', ['S', 'V1', 'O', 'Cl']),
    'S+向+O+V1，想+V2': ('{S}向{O}{V1}，想{V2}。', ['S', 'O', 'V1', 'V2']),
    'S+V1，又+V2': ('{S}{V1}，又{V2}。', ['S', 'V1', 'V2']),
    'S+沿+O+V，M': ('{S}沿{O}{V}，{M}。', ['S', 'O', 'V', 'M']),
    'S+V1，确认+V2': ('{S}{V1}，确认{V2}。', ['S', 'V1', 'V2']),
    'S+在+L+V+O': ('{S}在{L}{V}{O}。', ['S', 'L', 'V', 'O']),
    'S+把+O+V1，但+C+V2': ('{S}把{O}{V1}，但{C}{V2}。', ['S', 'O', 'V1', 'C', 'V2']),
    'S+从+A+V+到+B': ('{S}从{A}{V}{B}。', ['S', 'A', 'V', 'B']),
    'S+V1，V2；X+在+L': ('{S}{V1}，{V2}；{X}在{L}。', ['S', 'V1', 'V2', 'X', 'L']),
    'S+V1，又+V2；X+V3': ('{S}{V1}，又{V2}；{X}{V3}。', ['S', 'V1', 'V2', 'X', 'V3']),
    'S+V1，C+却+V2': ('{S}{V1}，{C}却{V2}。', ['S', 'V1', 'C', 'V2']),
    'S+V1，但+C+V2': ('{S}{V1}，但{C}{V2}。', ['S', 'V1', 'C', 'V2']),
    'S+V1，X+也+在+L': ('{S}{V1}，{X}也在{L}。', ['S', 'V1', 'X', 'L']),
    'S+V1，X+和+Y+都+在+L': ('{S}{V1}，{X}和{Y}都在{L}。', ['S', 'V1', 'X', 'Y', 'L']),
    'X+和+S+都+在+L': ('{X}和{S}都在{L}。', ['X', 'S', 'L']),
    'S+V1，V2；X+V3': ('{S}{V1}，{V2}；{X}{V3}。', ['S', 'V1', 'V2', 'X', 'V3']),
    'S+V1；X+V2；Y+V3': ('{S}{V1}；{X}{V2}；{Y}{V3}。', ['S', 'V1', 'X', 'V2', 'Y', 'V3']),
    'S+不+V1，等+O': ('{S}不{V1}，等{O}。', ['S', 'V1', 'O']),
}


def render(frame):
    if frame['pattern'] not in PATTERNS:
        raise ValueError('unknown pattern ' + frame['pattern'])
    tpl, required = PATTERNS[frame['pattern']]
    missing = [r for r in required if not frame['slots'].get(r)]
    if missing:
        raise ValueError('missing slots ' + ','.join(missing))
    return tpl.format(**frame['slots']).replace('.', '')


def check_spans(frame):
    """Every slot must be a contiguous substring of the joined facts."""
    joined = ''.join(frame['facts'])
    bad = []
    for role, text in frame['slots'].items():
        if text not in joined:
            bad.append((role, text))
    return bad


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / 'frames-v2-1.jsonl'
    rows = [json.loads(l) for l in path.read_text(encoding='utf8').splitlines() if l.strip()]
    facts_path = HERE / 'frames-v2-facts.jsonl'
    if facts_path.exists():
        by_key = {r['key']: r['facts'] for r in
                  (json.loads(l) for l in facts_path.read_text(encoding='utf8').splitlines() if l.strip())}
        for row in rows:
            if row.get('factKey') and not row.get('facts'):
                row['facts'] = by_key[row['factKey']]
    out, bad = [], []
    for row in rows:
        problems = check_spans(row)
        if problems:
            bad.append({'id': row['id'], 'problems': problems})
            continue
        try:
            text = render(row)
        except ValueError as ex:
            bad.append({'id': row['id'], 'problems': [str(ex)]})
            continue
        out.append({'id': row['id'], 'tags': row.get('tags', []), 'pattern': row['pattern'],
                    'text': text, 'ref': row.get('ref'), 'chars': len(text)})
        print(row['id'], row['pattern'], '|', text)
    summary = {
        'file': path.name, 'frames': len(rows), 'rendered': len(out), 'bad': bad,
        'patternsUsed': len({r['pattern'] for r in out}),
        'tags': {},
        'charsMean': round(sum(r['chars'] for r in out) / max(1, len(out)), 1),
    }
    from collections import Counter
    c = Counter(t for r in out for t in r['tags'])
    summary['tags'] = dict(c)
    (HERE / (path.stem + '-summary.json')).write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'bad'}, ensure_ascii=False))
    if bad:
        print('BAD', json.dumps(bad, ensure_ascii=False)[:800])


if __name__ == '__main__':
    main()
