"""Mixed exemplars: same 12 facts and byte-identical targets, six inputs without the name.

Control arm = the aug-r1 experiment pools unchanged (11 of 12 values carry the name,
one already does not). Experiment arm rewrites only the fact-value line of six of
them into a no-name form; the targets stay byte-identical, so insertion is required
and copying the name out of the value is impossible for those six.
"""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / 'artifacts/aug-r1'
OUT = ROOT / 'artifacts/mixed-r1'
POOLS = ('verbalizer', 'expand78', 'object34')

# pairId -> (old value, new value). Targets are not touched.
REWRITE = {
 'aug:01': ('绕在桩上的旧缆绳断成两截', '绕着的旧缆绳断成两截'),
 'aug:02': ('绞在桩上的缆绳松了', '绞着的缆绳松了'),
 'aug:06': ('绕在链上的抹布滑下来', '绕着的抹布滑下来'),
 'aug:07': ('压在筐底的银鳞鱼露出来', '压着的银鳞鱼露出来'),
 'aug:10': ('堵在沟口的石板松了', '堵着的石板松了'),
 'aug:12': ('夹在簿子里的干纸露出来', '夹着的干纸露出来'),
}


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_text(t):
    return hashlib.sha256(t.encode('utf-8')).hexdigest()


def value_of(row):
    for line in row['input'].splitlines():
        if line.startswith('事实='):
            parts = line[3:].split('｜', 2)
            return parts[2] if len(parts) == 3 else ''
    return ''


def set_value(row, new_value):
    name = value_of_name(row)
    out = []
    for line in row['input'].splitlines():
        out.append('事实=%s｜外貌变化｜%s' % (name, new_value) if line.startswith('事实=') else line)
    return '\n'.join(out) + '\n'


def value_of_name(row):
    for line in row['input'].splitlines():
        if line.startswith('事实='):
            return line[3:].split('｜', 2)[0]
    raise SystemExit('no fact line')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    freeze = {'purpose': 'mixed exemplars: six of the twelve inputs lose the name in the value, targets unchanged',
              'base': 'moved (bd5434b3)',
              'control': 'artifacts/aug-r1/pool-exp-*.jsonl, copied byte for byte',
              'rewrite': {k: {'oldValue': v[0], 'newValue': v[1]} for k, v in REWRITE.items()},
              'targetsPolicy': 'targets are byte-identical between arms; the previous "targets must differ" '
                               'assertion does not apply to this design',
              'files': {}, 'idOrder': None, 'inputOrder': {}, 'targetOrder': {}}
    for pool in POOLS:
        src = SRC / ('pool-exp-%s.jsonl' % pool)
        raw = src.read_bytes()
        (OUT / ('pool-ctl-%s.jsonl' % pool)).write_bytes(raw)
        rows = [json.loads(l) for l in raw.decode('utf-8').splitlines() if l.strip()]
        changed = 0
        for row in rows:
            pid = row.get('pairId')
            if pid in REWRITE:
                assert value_of(row) == REWRITE[pid][0], (pid, value_of(row))
                assert True
                row['input'] = set_value(row, REWRITE[pid][1])
                changed += 1
        (OUT / ('pool-mix-%s.jsonl' % pool)).write_text(
            ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8', newline='\n')
        ctl_b = (OUT / ('pool-ctl-%s.jsonl' % pool)).read_bytes()
        mix_b = (OUT / ('pool-mix-%s.jsonl' % pool)).read_bytes()
        freeze['files'][pool] = {
            'control': {'path': (OUT / ('pool-ctl-%s.jsonl' % pool)).relative_to(ROOT).as_posix(),
                        'rows': len(rows), 'sha256': sha_bytes(ctl_b)},
            'mix': {'path': (OUT / ('pool-mix-%s.jsonl' % pool)).relative_to(ROOT).as_posix(),
                    'rows': len(rows), 'sha256': sha_bytes(mix_b), 'rewritten': changed}}
        assert changed == (len(REWRITE) if pool == 'verbalizer' else 0), (pool, changed)
    # same ids, same targets, different inputs
    ctl_rows, mix_rows = [], []
    for pool in POOLS:
        ctl_rows += [json.loads(l) for l in (OUT / ('pool-ctl-%s.jsonl' % pool)).read_text(
            encoding='utf-8').splitlines() if l.strip()]
        mix_rows += [json.loads(l) for l in (OUT / ('pool-mix-%s.jsonl' % pool)).read_text(
            encoding='utf-8').splitlines() if l.strip()]
    ids_c = [r.get('pairId') or r['unitId'] for r in ctl_rows]
    ids_m = [r.get('pairId') or r['unitId'] for r in mix_rows]
    tgt_c = [r['target'] for r in ctl_rows]
    tgt_m = [r['target'] for r in mix_rows]
    inp_c = [r['input'] for r in ctl_rows]
    inp_m = [r['input'] for r in mix_rows]
    assert ids_c == ids_m
    assert tgt_c == tgt_m, 'targets must be byte-identical in this design'
    diff = [ids_c[i] for i in range(len(ids_c)) if inp_c[i] != inp_m[i]]
    assert diff == sorted(REWRITE), diff
    freeze['idOrder'] = {'rows': len(ids_c), 'sha256': sha_text('\n'.join(ids_c))}
    freeze['inputOrder'] = {'control': sha_text('\n'.join(inp_c)), 'mix': sha_text('\n'.join(inp_m)),
                            'differing': diff}
    freeze['targetOrder'] = {'control': sha_text('\n'.join(tgt_c)), 'mix': sha_text('\n'.join(tgt_m)),
                             'identical': True}
    # how many values carry the name in each arm
    def carried(rows):
        """Among the 12 augmented rows only: does the value carry the name or its short form."""
        n = 0
        for r in rows:
            if not str(r.get('pairId', '')).startswith('aug:'):
                continue
            value = value_of(r)
            name = value_of_name(r)
            if name in value or any(t in value for t in (name[-1], name[1:])):
                n += 1
        return n
    freeze['nameInsideValue'] = {'of': 12, 'control': carried(ctl_rows), 'mix': carried(mix_rows),
                                 'note': 'counted by name or its short form; aug:03 has no name in the value in '
                                         'either arm because that row already read 压在上面的干纸露出边角'}
    (OUT / 'mixed-freeze.json').write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + '\n',
                                           encoding='utf-8', newline='\n')
    print('rows', len(ids_c), 'idOrder', freeze['idOrder']['sha256'][:16])
    print('targets identical:', freeze['targetOrder']['control'] == freeze['targetOrder']['mix'])
    print('inputs differing on', len(diff), 'rows:', diff)
    print('name inside value', freeze['nameInsideValue'])
    for pool in POOLS:
        print(' ', pool, freeze['files'][pool]['control']['sha256'][:12],
              freeze['files'][pool]['mix']['sha256'][:12])


if __name__ == '__main__':
    main()
