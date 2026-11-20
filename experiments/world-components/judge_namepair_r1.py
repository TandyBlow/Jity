"""Judge the name-pair probes with the rule frozen in n4-namepair-r1-rule.json."""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))
from score_cf24_baseline import judge  # noqa: E402

ROOT = pathlib.Path('.')
ARMS = ('moved', 'ctl', 'exp')
DOUBLE_DE = re.compile('的[^，。！？的]{1,6}的')


def checks(p, text):
    name, rel, other = p['name'], p['relation'], p['other']
    ref = 'kept' if name in text else 'dropped'
    if rel in text:
        relv = 'kept'
    else:
        relv = 'distorted' if any(t in text for t in ('挂着', '挂', '缠', '系着', '套', '搭', '卡', '盖')) else 'dropped'
    dup = text.count(name) >= 2
    flip = False
    if name + '的' in text:
        after = text.split(name + '的', 1)[1]
        flip = after.startswith(other) or after.startswith(rel)
    syntax = 'broken' if (dup or DOUBLE_DE.search(text)) else 'ok'
    return {'reference': ref, 'relation': relv, 'syntax': syntax,
            'roleFlip': flip, 'duplicate': dup}


def main():
    probes = {}
    for line in (ROOT / 'artifacts/next-inputs/world-components/n4-namepair-r1.jsonl').read_text(
            encoding='utf-8').splitlines():
        if line.strip():
            p = json.loads(line)
            probes[p['unitId']] = p
    pairs = {}
    for p in probes.values():
        pairs.setdefault(p['pair'], []).append(p['unitId'])
    out = {'rule': 'namepair-r1', 'arms': {}}
    for arm in ARMS:
        report = json.loads((ROOT / ('artifacts/next-runs/eval-r5/namepair-%s/namepair-baseline.json' % arm))
                            .read_text(encoding='utf-8'))
        rows = []
        for row in report['rows']:
            p = probes[row['unitId']]
            c = checks(p, row['text'])
            verdict, note, _ = judge(p, row['text'])
            rows.append(dict(unitId=row['unitId'], pair=p['pair'], variant=p['variant'],
                             text=row['text'], fact=verdict, note=note, **c))
        out['arms'][arm] = rows
        by = {r['unitId']: r for r in rows}
        ref_keep = sum(1 for r in rows if r['reference'] == 'kept')
        rel_keep = sum(1 for r in rows if r['relation'] == 'kept')
        syn_broken = sum(1 for r in rows if r['syntax'] == 'broken')
        divergent = []
        for pid, ids in sorted(pairs.items()):
            a = by[ids[0]]
            b = by[ids[1]]
            if a['reference'] != b['reference']:
                divergent.append({'pair': pid,
                                  'withName': a['reference'], 'withoutName': b['reference'],
                                  'textA': a['text'], 'textB': b['text']})
        out.setdefault('summary', {})[arm] = {
            'referenceKept': '%d/12' % ref_keep, 'relationKept': '%d/12' % rel_keep,
            'syntaxBroken': syn_broken, 'pairsDivergent': len(divergent),
            'divergence': divergent}
        print('== %-6s reference kept %2d/12  relation kept %2d/12  syntax broken %d  pairs divergent %d/6'
              % (arm, ref_keep, rel_keep, syn_broken, len(divergent)))
        for r in rows:
            print('  %-8s %-7s %-12s ref=%-7s rel=%-8s syn=%-6s %-4s | %s'
                  % (r['unitId'], r['pair'], r['variant'], r['reference'], r['relation'],
                     r['syntax'], r['fact'], r['text']))
    target = ROOT / 'artifacts/next-runs/eval-r5/namepair-judged.json'
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('->', target)


if __name__ == '__main__':
    main()
