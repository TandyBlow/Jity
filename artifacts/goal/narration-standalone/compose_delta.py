# -*- coding: utf-8 -*-
"""N06: narration of the delta only. 82% of a point's fact clauses already sat
in the previous point's block; re-describing them is the repetition source.
Keep every settlement result, drop facts the previous point already carried."""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import cluster_events as ce
from role_parse import clauses

HERE = Path(__file__).resolve().parent


def fact_list(row):
    out = []
    for c in clauses(row['factsText']):
        c = ce.clean(c)
        if len(c) > 4 and '做的事' not in c and '玩家这回合' not in c:
            out.append(c)
    return out


def anchor(row, facts):
    name = ce.player_name(row)
    loc = next((c for c in facts if c.startswith(name) and '现在在' in c), None)
    return [loc] if loc else []


def main():
    rows = [json.loads(l) for l in (HERE / 'inputs.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    by = defaultdict(list)
    for r in rows:
        by[r['evidence']].append(r)
    prev_of = {}
    for ev, rs in by.items():
        prev = None
        for r in rs:
            prev_of[id(r)] = set(prev) if prev is not None else set()
            prev = fact_list(r)

    out_rows = []
    totals = Counter()
    turn_facts, turn_out = defaultdict(set), defaultdict(str)
    turn_prev = {}
    for r in rows:
        facts = fact_list(r)
        prev = prev_of[id(r)]
        fresh = [c for c in facts if c not in prev]
        kept = fresh if fresh else anchor(r, facts)
        fake = dict(r, factsText='。'.join(kept))
        text, stats, _ = ce.compose(fake)
        totals['points'] += 1
        totals['facts'] += len(facts)
        totals['fresh'] += len(fresh)
        totals['chars'] += len(text)
        totals['kept'] += len(kept)
        turn_facts[r['id'].rsplit(':', 1)[0]].update(facts)
        turn_out[r['id'].rsplit(':', 1)[0]] += text
        out_rows.append({'id': r['id'], 'fresh': len(fresh), 'facts': len(facts),
                         'chars': len(text), 'text': text})
    summary = {
        'points': totals['points'],
        'factClauses': totals['facts'],
        'freshClauses': totals['fresh'],
        'freshRate': round(totals['fresh'] / max(1, totals['facts']), 3),
        'keptClauses': totals['kept'],
        'chars': totals['chars'],
        'charsPerPoint': round(totals['chars'] / max(1, totals['points']), 1),
        'turnChars': round(sum(len(v) for v in turn_out.values()) / max(1, len(turn_out)), 1),
        'turns': len(turn_out),
        'samples': [r for r in out_rows[:3]],
    }
    (HERE / 'compose-delta-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    (HERE / 'compose-delta-rows.json').write_text(json.dumps(out_rows, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'samples'}, ensure_ascii=False))
    for s in summary['samples']:
        print('---', s['id'], f"fresh {s['fresh']}/{s['facts']}")
        print(s['text'][:260])


if __name__ == '__main__':
    main()
