"""Input-expression probes: the same role-contrast facts written twice.

Original variant = the frozen rolepair value (no name, relation without a location).
Explicit variant = the same fact stated in natural language with the direction made
plain: which object sits at which reference, or which part belongs to which whole.
The state is kept, no action or object is added, and the direction comes from the
source fact (the name is the location / the whole), not from any model output.
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

# (explicit value, original value) keyed by rolepair unit, direction taken from the fact
EXPLICIT = {
 'p-rp1a': ('缺页是潮汐簿的一部分，卷了边', '缺页卷了边'),
 'p-rp1b': ('干纸压在潮汐簿上，滑开了', '压着的干纸滑开了'),
 'p-rp2a': ('桩身是木桩的一部分，裂了一道缝', '桩身裂了一道缝'),
 'p-rp2b': ('渡船靠在木桩上，退了半尺', '靠着的渡船退了半尺'),
 'p-rp3a': ('筐底是鱼筐的一部分，渗了水', '筐底渗了水'),
 'p-rp3b': ('银鳞鱼堆在鱼筐底，露出来', '堆着的银鳞鱼露出来'),
 'p-rp4a': ('罩口是铜灯罩的一部分，积了铜绿', '罩口积了铜绿'),
 'p-rp4b': ('灯芯插在铜灯罩里，歪了', '插着的灯芯歪了'),
 'p-rp5a': ('边角是石板的一部分，崩了一小块', '边角崩了一小块'),
 'p-rp5b': ('油纸伞靠在石板上，歪了', '靠着的油纸伞歪了'),
 'p-rp6a': ('横木是钟架的一部分，磨出了毛边', '横木磨出了毛边'),
 'p-rp6b': ('钟绳搭在钟架上，垂到堤面', '搭着的钟绳垂到堤面'),
}


def main():
    src = OUT / 'n4-rolepair-r1.jsonl'
    probes = []
    for line in src.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        p = json.loads(line)
        explicit, original = EXPLICIT[p['unitId']]
        assert p['factValue'] == original, (p['unitId'], p['factValue'], original)
        # direction check: the explicit value must place the other object at the name
        if p['role'] == 'locationReference':
            assert p['name'] in explicit and p['other'] in explicit, p['unitId']
            assert explicit.index(p['other']) < explicit.index(p['name']), ('object must lead', p['unitId'])
        else:
            assert p['name'] in explicit and p['part'] in explicit, p['unitId']
            assert explicit.index(p['part']) < explicit.index(p['name']), ('part must lead', p['unitId'])
        for token in p['required']:
            assert token in explicit, (p['unitId'], token)
        lines = []
        for line in p['input'].splitlines():
            if line.startswith('事实='):
                lines.append('事实=%s｜外貌变化｜%s' % (p['name'], explicit))
            else:
                lines.append(line)
        text = '\n'.join(lines) + '\n'
        q = dict(p)
        q.update({'unitId': p['unitId'] + 'X', 'variant': p['variant'] + '-explicit',
                  'explicitOf': p['unitId'], 'originalValue': original, 'factValue': explicit,
                  'factChars': len(explicit), 'inputChars': len(text),
                  'fact': {'kind': 'appearance_changed', 'name': p['name'], 'text': explicit},
                  'input': text})
        probes.append(q)
    FC.check_units(probes)
    out = OUT / 'n4-explicit-r1.jsonl'
    out.write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in probes),
                   encoding='utf-8', newline='\n')
    print('probes', len(probes), 'sha', hashlib.sha256(out.read_bytes()).hexdigest()[:24])
    print('%-10s %-2s %-2s | %-16s -> %s' % ('id', 'orig', 'expl', 'original', 'explicit'))
    for p in probes:
        print('%-10s %2d %2d | %-16s -> %s' % (p['unitId'], len(p['originalValue']),
                                               len(p['factValue']), p['originalValue'], p['factValue']))


if __name__ == '__main__':
    main()
