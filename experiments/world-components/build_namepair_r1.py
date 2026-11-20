"""Build the paired probes: the same proposition stated with and without the
reference name inside the fact value.

Both members of a pair share the name, the relation and the other entity; only
the frame that carries the name differs. Whether the name is in the value is the
single manipulated property.
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))
import fact_contract as FC  # noqa: E402

OUT = ROOT / 'artifacts/next-inputs/world-components'
BASE = {'潮渡>栈桥': 't04:f0', '潮渡>浅滩': 't22:f0', '雾堤>堤面': 't05:f0',
        '旧灯塔>塔顶': 't03:f0', '潮生巷': 't06:f0', '潮汐档案馆': 't01:f0'}

# name, base unit, relation, other entity, predicate, with-name value, without-name value
PAIRS = [
 ('木桩', '潮渡>栈桥', '靠', '渡船', '晃了',
  '靠在木桩上的渡船晃了', '靠着的渡船晃了'),
 ('系泊绳', '潮渡>浅滩', '绕', '缆绳', '松了',
  '绕在系泊绳上的缆绳松了', '绕着的缆绳松了'),
 ('钟架', '雾堤>堤面', '搭', '钟绳', '滑下来',
  '搭在钟架上的钟绳滑下来', '搭着的钟绳滑下来'),
 ('铜灯罩', '旧灯塔>塔顶', '压', '抹布', '滑下来',
  '压在铜灯罩上的抹布滑下来', '压着的抹布滑下来'),
 ('石板', '潮生巷', '压', '油纸伞', '歪了',
  '压在石板上的油纸伞歪了', '压着的油纸伞歪了'),
 ('门槛', '潮汐档案馆', '压', '干纸', '滑开了',
  '压在门槛上的干纸滑开了', '压着的干纸滑开了'),
]


def load(path):
    return {json.loads(l)['unitId']: json.loads(l)
            for l in path.read_text(encoding='utf-8').splitlines() if l.strip()}


def main():
    units = {}
    for s in ('cf24', 'final24', 'moved24'):
        units.update(load(ROOT / ('artifacts/next-inputs/world-components/n4-%s-contract.jsonl' % s)))
    probes = []
    for i, (name, loc, rel, other, pred, with_name, without) in enumerate(PAIRS, 1):
        base = units[BASE[loc]]
        visible = [l[3:] for l in base['input'].splitlines() if l.startswith('地点可见=')][0]
        for token in (name, other):
            assert token in visible, (loc, token, visible)
        for variant, value in (('with-name', with_name), ('without-name', without)):
            assert (name in value) == (variant == 'with-name'), (variant, value)
            assert rel in value and other in value and pred in value, value
            lines = []
            for line in base['input'].splitlines():
                if line.startswith('事实='):
                    lines.append('事实=%s｜外貌变化｜%s' % (name, value))
                elif line.startswith('方向='):
                    continue
                else:
                    lines.append(line)
            text = '\n'.join(lines) + '\n'
            probes.append({'unitId': 'p-np%d%s' % (i, 'a' if variant == 'with-name' else 'b'),
                           'pair': 'np%d' % i, 'variant': variant, 'baseUnit': BASE[loc],
                           'name': name, 'relation': rel, 'other': other, 'predicate': pred,
                           'kind': 'appearance_changed', 'factValue': value,
                           'fact': {'kind': 'appearance_changed', 'name': name, 'text': value},
                           'inputChars': len(text), 'factChars': len(value),
                           'input': text})
    # collision guard: no probe input may equal an existing unit's input
    seen = {u['input'] for u in units.values()}
    for extra in ('n4-relation-r1.jsonl', 'aug-exp.jsonl', 'aug-ctl.jsonl'):
        p = ROOT / 'artifacts/next-inputs/world-components' / extra
        if not p.is_file():
            p = ROOT / 'artifacts/aug-r1' / extra
        if p.is_file():
            for l in p.read_text(encoding='utf-8').splitlines():
                if l.strip():
                    r = json.loads(l)
                    if r.get('input'):
                        seen.add(r['input'])
    for p in probes:
        assert p['input'] not in seen, ('collision', p['unitId'])
    FC.check_units(probes)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'n4-namepair-r1.jsonl').write_text(
        ''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in probes), encoding='utf-8', newline='\n')
    print('probes', len(probes))
    for p in probes:
        print(' %-8s %-7s %-12s chars=%2d fact=%2d | %s' % (p['unitId'], p['pair'], p['variant'],
                                                          p['inputChars'], p['factChars'], p['factValue']))


if __name__ == '__main__':
    main()
