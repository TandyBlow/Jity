"""Judge the relation probes with the rule frozen in n4-relation-r1-rule.json.

Retention is decided by the declared token only; the frozen cf24 scorer decides
fact coverage separately. A third column records whether the sentence is
well-formed, because the rule did not predict a malformed frame - that column is
secondary and labelled as such.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))
from score_cf24_baseline import judge  # noqa: E402

ROOT = pathlib.Path('.')
RUNS = ('c', 'control', 'moved')
ATTACH = ('缠', '挂', '系', '套', '搭')


def main():
    probes = {}
    for line in (ROOT / 'artifacts/next-inputs/world-components/n4-relation-r1.jsonl').read_text(
            encoding='utf-8').splitlines():
        if line.strip():
            p = json.loads(line)
            probes[p['unitId']] = p
    out = {'arms': {}}
    for arm in RUNS:
        report = json.loads((ROOT / ('artifacts/next-runs/eval-r3/relation-%s/relation-baseline.json' % arm))
                            .read_text(encoding='utf-8'))
        rows = []
        for row in report['rows']:
            p = probes[row['unitId']]
            text = row['text']
            verdict, note, _ = judge(p, text)
            if p['family'] == 'relation':
                if p['relation'] in text:
                    rel = 'retained'
                elif any(t in text for t in ATTACH) or any(t in text for t in ('盖', '插', '卡')):
                    rel = 'distorted'
                else:
                    rel = 'dropped'
            else:
                rel = 'invented' if any(t in text for t in p['forbidden']) else 'clean'
            malformed = ('的' + p['relation'] in text) or (p['fact']['name'] in text and
                                                           text.count(p['fact']['name']) > 1)
            rows.append({'unitId': row['unitId'], 'family': p['family'], 'relation': p['relation'],
                         'text': text, 'retention': rel, 'fact': verdict,
                         'malformedFrame': malformed, 'note': note})
        out['arms'][arm] = rows
        kept = sum(1 for r in rows if r['family'] == 'relation' and r['retention'] == 'retained')
        drop = sum(1 for r in rows if r['family'] == 'relation' and r['retention'] == 'dropped')
        dist = sum(1 for r in rows if r['family'] == 'relation' and r['retention'] == 'distorted')
        ctl = sum(1 for r in rows if r['family'] == 'control' and r['retention'] == 'invented')
        mal = sum(1 for r in rows if r['malformedFrame'])
        print('== %s  relation kept %d/8  dropped %d  distorted %d | controls invented %d/2 | malformed frame %d'
              % (arm, kept, drop, dist, ctl, mal))
        for r in rows:
            print('  %-7s %-9s %-6s %s%s' % (r['unitId'], r['retention'], r['fact'], r['text'],
                                            '  <<MALFORMED' if r['malformedFrame'] else ''))
    target = ROOT / 'artifacts/next-runs/eval-r3/relation-judged.json'
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('->', target)


if __name__ == '__main__':
    main()
