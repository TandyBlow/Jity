"""Judge the explicit-input probes, and pair each against its archived original run.

The original variants are not re-run here: their outputs already exist in eval-r7 and
are read from there, so the comparison is between the same arm on the two input forms.
"""
import json
import pathlib
import re

ROOT = pathlib.Path('.')
ARMS = ('moved', 'ctl', 'mix')
DOUBLE_DE = re.compile('的[^，。！？的]{1,6}的')
REL = ('压', '靠', '堆', '插', '搭')
# the state each location member must keep (the value after the comma in the explicit form)
LOC_STATE = {'rp1': '滑开了', 'rp2': '退了半尺', 'rp3': '露出来',
             'rp4': '歪了', 'rp5': '歪了', 'rp6': '垂到堤面'}


def judge_row(p, text):
    name, part, other, rel = p['name'], p['part'], p['other'], p['relation']
    name_kept = name in text
    entity = part if p['role'] == 'possessor' else other
    entity_kept = entity in text
    state_tokens = [p['predicate']] if p['role'] == 'possessor' else [LOC_STATE[p['pair']]]
    state_kept = any(t in text for t in state_tokens)
    inverted = bool(re.search(name + '(压|靠|堆|插|搭)着', text))
    if p['role'] == 'possessor':
        if not entity_kept and name_kept:
            direction = 'replaced'
        elif not entity_kept:
            direction = 'missing'
        else:
            direction = 'ok'
        relation = 'n/a'
    else:
        if not name_kept:
            direction = 'missing'
        elif inverted:
            direction = 'inverted'
        else:
            direction = 'ok'
        flip = (name + '的') in text and text.split(name + '的', 1)[1].startswith((other, rel))
        if flip:
            direction = 'flip'
        if rel in text:
            relation = 'kept'
        else:
            relation = 'dropped'
    dup = text.count(name) >= 2
    syntax = 'broken' if (dup or DOUBLE_DE.search(text)) else 'ok'
    passed = (name_kept and entity_kept and state_kept and direction == 'ok'
              and relation in ('kept', 'n/a') and syntax == 'ok')
    return {'nameKept': name_kept, 'entityKept': entity_kept, 'stateKept': state_kept,
            'direction': direction, 'relation': relation, 'syntax': syntax, 'duplicate': dup,
            'pass': passed}


def main():
    probes = {}
    for line in (ROOT / 'artifacts/next-inputs/world-components/n4-explicit-r1.jsonl').read_text(
            encoding='utf-8').splitlines():
        if line.strip():
            p = json.loads(line)
            probes[p['unitId']] = p
    out = {'arms': {}, 'summary': {}}
    for arm in ARMS:
        new = json.loads((ROOT / ('artifacts/next-runs/eval-r8/explicit-%s/explicit-baseline.json' % arm))
                         .read_text(encoding='utf-8'))['rows']
        old = {r['unitId']: r for r in json.loads(
            (ROOT / ('artifacts/next-runs/eval-r7/rolepair-%s/rolepair-baseline.json' % arm))
            .read_text(encoding='utf-8'))['rows']}
        rows = []
        for r in new:
            p = probes[r['unitId']]
            orig = old[p['explicitOf']]
            a = judge_row(p, orig['text'])
            b = judge_row(p, r['text'])
            rows.append({'unitId': r['unitId'], 'pair': p['pair'], 'role': p['role'],
                         'originalText': orig['text'], 'explicitText': r['text'],
                         'original': a, 'explicit': b,
                         'originalValue': p['originalValue'], 'explicitValue': p['factValue'],
                         'originalChars': len(p['originalValue']), 'explicitChars': len(p['factValue'])})
        out['arms'][arm] = rows
        def agg(key):
            v = [r[key] for r in rows]
            return {'pass': sum(1 for x in v if x['pass']),
                    'directionErrors': sum(1 for x in v if x['direction'] in ('inverted', 'flip', 'replaced')),
                    'nameMissing': sum(1 for x in v if not x['nameKept']),
                    'entityMissing': sum(1 for x in v if not x['entityKept']),
                    'stateMissing': sum(1 for x in v if not x['stateKept']),
                    'syntaxBroken': sum(1 for x in v if x['syntax'] != 'ok')}
        out['summary'][arm] = {'original': agg('original'), 'explicit': agg('explicit')}
        print('== %-6s original pass %d/12 dir %d | explicit pass %d/12 dir %d nameMiss %d entityMiss %d '
              'stateMiss %d syn %d'
              % (arm, out['summary'][arm]['original']['pass'],
                 out['summary'][arm]['original']['directionErrors'],
                 out['summary'][arm]['explicit']['pass'],
                 out['summary'][arm]['explicit']['directionErrors'],
                 out['summary'][arm]['explicit']['nameMissing'],
                 out['summary'][arm]['explicit']['entityMissing'],
                 out['summary'][arm]['explicit']['stateMissing'],
                 out['summary'][arm]['explicit']['syntaxBroken']))
        for r in rows:
            flag = '' if r['explicit']['pass'] else '  <<' + ','.join(
                k for k, v in (('dir:' + r['explicit']['direction'], r['explicit']['direction'] != 'ok'),
                               ('name', not r['explicit']['nameKept']),
                               ('entity', not r['explicit']['entityKept']),
                               ('state', not r['explicit']['stateKept']),
                               ('rel:' + r['explicit']['relation'],
                                r['explicit']['relation'] not in ('kept', 'n/a')),
                               ('syntax', r['explicit']['syntax'] != 'ok')) if v)
            print('  %-10s %-18s | %-16s -> %s%s' % (r['unitId'], r['role'], r['explicitValue'],
                                                     r['explicitText'], flag))
    target = ROOT / 'artifacts/next-runs/eval-r8/explicit-judged.json'
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    (ROOT / 'artifacts/next-runs/eval-r8/explicit-summary.json').write_text(
        json.dumps(out['summary'], ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('->', target)


if __name__ == '__main__':
    main()
