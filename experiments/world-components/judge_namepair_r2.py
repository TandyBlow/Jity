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
ROUND = 'eval-r6'
ARMS = ('moved', 'ctl', 'mix')
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
        report = json.loads((ROOT / ('artifacts/next-runs/%s/%s-namepair/namepair-baseline.json' % (ROUND, arm)))
                            .read_text(encoding='utf-8'))
        rows = []
        for row in report['rows']:
            p = probes[row['unitId']]
            c = checks(p, row['text'])
            verdict, note, _ = judge(p, row['text'])
            passed = (c['reference'] == 'kept' and c['relation'] == 'kept'
                      and c['syntax'] == 'ok' and not c['roleFlip'] and not c['duplicate'])
            rows.append(dict(unitId=row['unitId'], pair=p['pair'], variant=p['variant'],
                             text=row['text'], fact=verdict, note=note, pass4=passed, **c))
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
    target = ROOT / ('artifacts/next-runs/%s/namepair-judged.json' % ROUND)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    for arm, v in out['summary'].items():
        rows = out['arms'][arm]
        for variant in ('with-name', 'without-name'):
            sub = [r for r in rows if r['variant'] == variant]
            v['pass_' + variant] = '%d/%d' % (sum(1 for r in sub if r['pass4']), len(sub))
        v['pass_all'] = '%d/12' % sum(1 for r in rows if r['pass4'])
    (ROOT / ('artifacts/next-runs/%s/namepair-summary.json' % ROUND)).write_text(
        json.dumps(out['summary'], ensure_ascii=False, indent=1) + chr(10), encoding='utf-8', newline=chr(10))
    print('->', target)


if __name__ == '__main__':
    main()
