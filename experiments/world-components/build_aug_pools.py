"""Build the shape-augmentation arms on top of the moved pools.

Both arms append 12 rows with the same ids at the same positions, so the sampler
sees the same id sequence. The experiment rows use the location-reference shape;
the control rows use the shapes the pools already teach (part-whole and plain
predicate). Inputs and targets differ, so this is a shape augmentation contrast,
not a label-only contrast.
"""
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))
import fact_contract as FC  # noqa: E402

BASE = ROOT / 'artifacts/moved-fix-r1'
OUT = ROOT / 'artifacts/aug-r1'
POOLS = ('verbalizer', 'expand78', 'object34')
DOUBLE_DE = re.compile('的[^，。！？的]{1,6}的')

# Manual read of every new target, done row by row before freezing.
MANUAL = {
 'aug:01': ('location-reference', '绕', 'ok', 'ok', '缆绳绕在桩上再断，关系在'),
 'aug:02': ('location-reference', '绞', 'ok', 'ok', '绞在桩上，关系在'),
 'aug:03': ('location-reference', '压', 'ok', 'ok', '压在长桌上面，关系在'),
 'aug:04': ('location-reference', '靠', 'ok', 'ok', '靠在桌沿，关系在'),
 'aug:05': ('location-reference', '搁', 'ok', 'ok', '搁在罩边，关系在'),
 'aug:06': ('location-reference', '绕', 'ok', 'ok', '绕在铁链上，关系在'),
 'aug:07': ('location-reference', '压', 'ok', 'ok', '压在筐底，关系在'),
 'aug:08': ('location-reference', '绕', 'ok', 'ok', '绕在筐边，关系在'),
 'aug:09': ('location-reference', '绞', 'ok', 'ok', '绞在绳头，关系在'),
 'aug:10': ('location-reference', '堵', 'ok', 'ok', '堵在沟口，关系在'),
 'aug:11': ('location-reference', '摆', 'ok', 'ok', '摆在案板上，关系在'),
 'aug:12': ('location-reference', '夹', 'ok', 'ok', '夹在簿子里，关系在'),
}
MANUAL_CTL = {
 'aug:01': ('possessor-part', 'ok', 'ok', '名称的+部件，与现有 30 条同形'),
 'aug:02': ('subject-predicate', 'ok', 'ok', '名称作谓语主语'),
 'aug:03': ('possessor-part', 'ok', 'ok', '名称的+部件'),
 'aug:04': ('subject-predicate', 'ok', 'ok', '名称作主语'),
 'aug:05': ('possessor-part', 'ok', 'ok', '名称的+部件'),
 'aug:06': ('subject-predicate', 'ok', 'ok', '名称作主语'),
 'aug:07': ('possessor-part', 'ok', 'ok', '名称的+部件'),
 'aug:08': ('subject-predicate', 'ok', 'ok', '名称作主语'),
 'aug:09': ('possessor-part', 'ok', 'ok', '名称的+部件'),
 'aug:10': ('possessor-part', 'ok', 'ok', '名称的+部件'),
 'aug:11': ('subject-predicate', 'ok', 'ok', '名称作主语'),
 'aug:12': ('possessor-part', 'ok', 'ok', '名称的+部件'),
}


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def main():
    exp = [json.loads(l) for l in (OUT / 'aug-exp.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    ctl = [json.loads(l) for l in (OUT / 'aug-ctl.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    assert len(exp) == len(ctl) == 12
    freeze = {'purpose': 'shape augmentation from the moved weights: 12 location-reference rows versus '
                         '12 rows in shapes the pools already teach',
              'contrast': 'shape augmentation, not label-only: inputs and targets differ between arms',
              'base': {'ckpt': 'moved (bd5434b3)', 'pools': 'artifacts/moved-fix-r1/arm-moved-*.jsonl'},
              'rowsPerArm': 12, 'positions': 'appended to the verbalizer pool in the same 12 slots',
              'manualRead': {'exp': MANUAL, 'ctl': MANUAL_CTL},
              'thresholds': {
                'improvement': 'on the 10 frozen frame probes the experiment passes at least 4/10 and at '
                               'least 3 more than both the start and the control arm',
                'largeFailure': 'the experiment passes 2/10 or fewer, or attribution errors reach 7/10',
                'factRegression': 'machine S below 85/76/24 on cf24/final24/moved24, or human-final below the '
                                  'start arm',
                'addedRegression': 'added text above the start arm total of 2',
                'languageRegression': 'language defects above the start arm count on cf24',
                'note': 'any regression blocks an overall pass even if the frame column improves'},
              'files': {}, 'idOrder': None, 'mechanicalCheck': {}}
    ids = []
    for pool in POOLS:
        src = BASE / ('arm-moved-%s.jsonl' % pool)
        base_rows = [json.loads(l) for l in src.read_text(encoding='utf-8').splitlines() if l.strip()]
        extra = exp if pool == 'verbalizer' else []
        extra_ctl = ctl if pool == 'verbalizer' else []
        for tag, rows in (('exp', extra), ('ctl', extra_ctl)):
            extra_rows = []
            for r in rows:
                row = {k: v for k, v in r.items() if not k.startswith('_')}
                row['input'] = r['_input']
                extra_rows.append(row)
            out_rows = list(base_rows) + extra_rows
            path = OUT / ('pool-%s-%s.jsonl' % (tag, pool))
            path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in out_rows),
                            encoding='utf-8', newline='\n')
            freeze['files'].setdefault(tag, {})[pool] = {
                'path': path.relative_to(ROOT).as_posix(), 'rows': len(out_rows), 'sha256': sha(path)}
        if pool == 'verbalizer':
            ids = [r.get('pairId') or r['unitId'] for r in base_rows] + [r['pairId'] for r in exp]
    freeze['idOrder'] = {'rows': len(ids), 'sha256': hashlib.sha256(
        json.dumps(ids, ensure_ascii=False).encode()).hexdigest()}
    # mechanical self-check of the 24 new targets
    for tag, rows, meta in (('exp', exp, MANUAL), ('ctl', ctl, MANUAL_CTL)):
        for r in rows:
            name = [l[3:] for l in r['_input'].splitlines() if l.startswith('事实=')][0].split('｜')[0]
            t = r['target']
            double = bool(DOUBLE_DE.search(t))
            dup = t.count(name) >= 2
            role_flip = (name + '的') in t
            shape = MANUAL[r['pairId']][0] if tag == 'exp' else MANUAL_CTL[r['pairId']][0]
            expected_possessive = shape == 'possessor-part'
            shape_ok = role_flip == expected_possessive
            freeze['mechanicalCheck'].setdefault(tag, {})[r['pairId']] = {
                'shape': shape, 'doubleDe': double, 'duplicateName': dup,
                'namePossessive': role_flip, 'shapeMatches': shape_ok,
                'pass': not double and not dup and shape_ok}
    bad = [k for tag in freeze['mechanicalCheck'].values() for k, v in tag.items() if not v['pass']]
    assert not bad, bad
    # non-aug rows must be byte identical between arms
    for pool in POOLS:
        a = (OUT / ('pool-exp-%s.jsonl' % pool)).read_text(encoding='utf-8').splitlines()
        b = (OUT / ('pool-ctl-%s.jsonl' % pool)).read_text(encoding='utf-8').splitlines()
        n = len(a) - (12 if pool == 'verbalizer' else 0)
        assert a[:n] == b[:n], pool
    (OUT / 'aug-freeze.json').write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + '\n',
                                         encoding='utf-8', newline='\n')
    print('rows', freeze['idOrder']['rows'], 'idOrder', freeze['idOrder']['sha256'][:16])
    for tag in ('exp', 'ctl'):
        for pool in POOLS:
            f = freeze['files'][tag][pool]
            print(' ', tag, pool, f['sha256'][:12], f['rows'])


if __name__ == '__main__':
    main()
