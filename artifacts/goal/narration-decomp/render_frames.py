# -*- coding: utf-8 -*-
"""Render hand-labelled frames with generic constructions and compare with the
human sentence. This measures expressiveness of the frame grammar, not a model."""
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def render(frame):
    s = frame['slots']
    p = frame['pattern']
    if p == 'S+贴沿+O+V，+M':
        return f"{s['S']}{s['贴沿']}{s['O']}{s['V']}，{s['M']}。"
    if p == 'S+在+L+V+O':
        return f"{s['S']}在{s['L']}{s['V']}{s['O']}。"
    if p == 'S+想+V1，再+V2，V3':
        return f"{s['S']}想{s['V1']}，再{s['V2']}，{s['V3']}。"
    if p == 'S+V，+没有+X':
        return f"{s['S']}{s['V']}，没有{s['X']}。"
    if p == 'S+想+V1，+C+却+没有+O':
        return f"{s['S']}想{s['V1']}，{s['C']}却没有{s['O']}。"
    if p == 'S+V1，又+V2':
        return f"{s['S']}{s['V1']}，又{s['V2']}。"
    if p == 'S+把+O+V':
        return f"{s['S']}把{s['O']}{s['V']}。"
    if p == 'S+V，+State':
        return f"{s['S']}{s['V']}，{s['State']}。"
    if p == 'S+没+V':
        return f"{s['S']}没{s['V']}。"
    if p == '没有+S+在':
        return f"没有{s['S']}在。"
    if p == 'S+V1，确认+V2':
        return f"{s['S']}{s['V1']}，确认{s['V2']}。"
    if p == 'S+把+O+V1，让+X+V2':
        return f"{s['S']}把{s['O']}{s['V1']}，让{s['X']}{s['V2']}。"
    if p == 'L+没有+S':
        return f"{s['L']}没有{s['S']}。"
    if p == 'S+V，没+V2':
        return f"{s['S']}{s['V']}，没{s['V2']}。"
    raise ValueError(p)


def cjk(text):
    return ''.join(c for c in text if '一' <= c <= '鿿')


def char_f1(a, b):
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    if not common:
        return 0.0
    p = common / max(1, len(a)); r = common / max(1, len(b))
    return 2 * p * r / (p + r)


def main():
    rows = [json.loads(l) for l in (HERE / 'frames-hand-10.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    out = []
    for row in rows:
        gen = render(row)
        out.append({'id': row['id'], 'gen': gen, 'ref': row['sentence'],
                    'charF1': round(char_f1(cjk(gen), cjk(row['sentence'])), 3),
                    'exact': gen == row['sentence']})
        print(row['id'], round(char_f1(cjk(gen), cjk(row['sentence'])), 3), '|', gen)
    summary = {'frames': len(out), 'exact': sum(1 for r in out if r['exact']),
               'charF1Mean': round(sum(r['charF1'] for r in out) / len(out), 3)}
    (HERE / 'render-frames-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
