"""Role-contrast probes: the same name plays possessor in one member and location reference
in the other.

Both members of a pair omit the name from the fact value, so the name has to be inserted in
both; only the role of the name differs. Each member records the nouns, relation and state
that must not be deleted or replaced.
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
BASE = {'潮汐档案馆': 't01:f0', '潮渡>栈桥': 't04:f0', '早市': 't02:f0',
        '旧灯塔>塔顶': 't03:f0', '潮生巷': 't06:f0', '雾堤>堤面': 't05:f0'}

# pair, name, location, part noun (possessor member), other object (location member)
PAIRS = [
 ('rp1', '潮汐簿', '潮汐档案馆', '缺页', '干纸'),
 ('rp2', '木桩', '潮渡>栈桥', '桩身', '渡船'),
 ('rp3', '鱼筐', '早市', '筐底', '银鳞鱼'),
 ('rp4', '铜灯罩', '旧灯塔>塔顶', '罩口', '灯芯'),
 ('rp5', '石板', '潮生巷', '边角', '油纸伞'),
 ('rp6', '钟架', '雾堤>堤面', '横木', '钟绳'),
]

# pair -> (partValue, partPredicate, relation, locationValue)
FACTS = {
 'rp1': ('缺页卷了边', '卷了边', '压', '压着的干纸滑开了'),
 'rp2': ('桩身裂了一道缝', '裂了一道缝', '靠', '靠着的渡船退了半尺'),
 'rp3': ('筐底渗了水', '渗了水', '堆', '堆着的银鳞鱼露出来'),
 'rp4': ('罩口积了铜绿', '积了铜绿', '插', '插着的灯芯歪了'),
 'rp5': ('边角崩了一小块', '崩了一小块', '靠', '靠着的油纸伞歪了'),
 'rp6': ('横木磨出了毛边', '磨出了毛边', '搭', '搭着的钟绳垂到堤面'),
}


def load(path):
    return {json.loads(l)['unitId']: json.loads(l)
            for l in path.read_text(encoding='utf-8').splitlines() if l.strip()}


def main():
    units = {}
    for s in ('cf24', 'final24', 'moved24'):
        units.update(load(ROOT / ('artifacts/next-inputs/world-components/n4-%s-contract.jsonl' % s)))
    probes = []
    for pair, name, loc, part, other in PAIRS:
        base = units[BASE[loc]]
        visible = [l[3:] for l in base['input'].splitlines() if l.startswith('地点可见=')][0]
        assert name in visible and other in visible, (loc, name, other)
        part_value, part_pred, rel, loc_value = FACTS[pair]
        for variant, value, role, required, forbidden in (
                ('possessor', part_value, 'possessor', [part, part_pred], []),
                ('location', loc_value, 'locationReference', [other, rel], [])):
            assert name not in value, ('value must not carry the name', pair, variant)
            for token in required:
                assert token in value, (pair, variant, token)
            lines = []
            for line in base['input'].splitlines():
                if line.startswith('事实='):
                    lines.append('事实=%s｜外貌变化｜%s' % (name, value))
                elif line.startswith('方向='):
                    continue
                else:
                    lines.append(line)
            text = '\n'.join(lines) + '\n'
            probes.append({'unitId': 'p-%s%s' % (pair, 'a' if variant == 'possessor' else 'b'),
                           'pair': pair, 'variant': variant, 'role': role,
                           'baseUnit': BASE[loc], 'name': name, 'part': part, 'other': other,
                           'relation': rel, 'predicate': part_pred,
                           'required': required, 'forbidden': forbidden,
                           'factValue': value, 'factChars': len(value), 'inputChars': len(text),
                           'kind': 'appearance_changed',
                           'fact': {'kind': 'appearance_changed', 'name': name, 'text': value},
                           'input': text})
    seen = {u['input'] for u in units.values()}
    for extra, base_dir in (('n4-relation-r1.jsonl', 'artifacts/next-inputs/world-components'),
                            ('n4-namepair-r1.jsonl', 'artifacts/next-inputs/world-components')):
        p = ROOT / base_dir / extra
        if p.is_file():
            for l in p.read_text(encoding='utf-8').splitlines():
                if l.strip():
                    seen.add(json.loads(l)['input'])
    for p in probes:
        assert p['input'] not in seen, ('collision', p['unitId'])
    FC.check_units(probes)
    out = OUT / 'n4-rolepair-r1.jsonl'
    out.write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in probes),
                   encoding='utf-8', newline='\n')
    print('probes', len(probes), 'sha', hashlib.sha256(out.read_bytes()).hexdigest()[:24])
    for p in probes:
        print(' %-8s %-12s %-6s chars=%2d/%2d | %s | 必须保留 %s'
              % (p['unitId'], p['variant'], p['name'], p['factChars'], p['inputChars'],
                 p['factValue'], '+'.join(p['required'])))


if __name__ == '__main__':
    main()
