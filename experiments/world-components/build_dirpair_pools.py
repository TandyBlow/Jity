"""Direction-pair pools: replace the 12-row augmentation block with six direction pairs.

Each pair uses one relation and two entities. One row makes the named entity the place
where the other object sits; the other makes the named entity the actor. The two inputs
differ in the name field and in the value, so they are distinguishable on their own, and
the two targets differ in direction. Same pairIds as the block they replace, so the
sampler draws the same id sequence.
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))
import fact_contract as FC  # noqa: E402

SRC = ROOT / 'artifacts/mixed-r1'
OUT = ROOT / 'artifacts/dirpair-r1'
POOLS = ('verbalizer', 'expand78', 'object34')

# anchor, other, relation, state, location-of-input base, actor-of-input base
PAIRS = [
 ('石板', '油纸伞', '压', '滑开了', 't06:f0', 't06:f0'),
 ('木桩', '渡船', '靠', '退了半尺', 't04:f0', 't04:f0'),
 ('铜灯罩', '灯芯', '插', '歪了', 't03:f0', 't03:f0'),
 ('铁链', '抹布', '搭', '滑下来', 't03:f0', 't03:f0'),
 ('鱼筐', '银鳞鱼', '堆', '露出来', 't02:f0', 't02:f0'),
 ('钟架', '钟绳', '绕', '垂到堤面', 't05:f0', 't05:f0'),
]

# how the value reads when the named entity is the place, and when it is the actor
VALUES = {
 '石板': ('压着的油纸伞滑开了', '压着石板，滑开了', '压在石板上的油纸伞滑开了。', '油纸伞压着石板，滑开了。'),
 '木桩': ('靠着的渡船退了半尺', '靠着木桩，退了半尺', '靠在木桩上的渡船退了半尺。', '渡船靠着木桩，退了半尺。'),
 '铜灯罩': ('插着的灯芯歪了', '插在罩里，歪了', '插在铜灯罩里的灯芯歪了。', '灯芯插在铜灯罩里，歪了。'),
 '铁链': ('搭着的抹布滑下来', '搭在链上，滑下来', '搭在铁链上的抹布滑下来。', '抹布搭在铁链上，滑下来。'),
 '鱼筐': ('堆着的银鳞鱼露出来', '堆在筐底，露出来', '堆在鱼筐底的银鳞鱼露出来。', '银鳞鱼堆在鱼筐底，露出来。'),
 '钟架': ('绕着的钟绳垂到堤面', '绕在架上，垂到堤面', '绕在钟架上的钟绳垂到堤面。', '钟绳绕在钟架上，垂到堤面。'),
}


def load_units():
    units = {}
    for s in ('cf24', 'final24', 'moved24'):
        p = ROOT / ('artifacts/next-inputs/world-components/n4-%s-contract.jsonl' % s)
        for line in p.read_text(encoding='utf-8').splitlines():
            if line.strip():
                u = json.loads(line)
                units[u['unitId']] = u
    return units


def render(base_input, name, value):
    lines = []
    for line in base_input.splitlines():
        if line.startswith('事实='):
            lines.append('事实=%s｜外貌变化｜%s' % (name, value))
        elif line.startswith('方向='):
            continue
        else:
            lines.append(line)
    return '\n'.join(lines) + '\n'


def main():
    units = load_units()
    rows = []
    freeze = {'purpose': 'direction pairs replacing the augmentation block',
              'design': 'per pair the same two entities and the same relation; one row names the place, the '
                        'other names the actor; both targets keep both entities, the relation and the state',
              'pairs': [], 'files': {}, 'ids': None, 'targets': {}}
    idx = 1
    for anchor, other, rel, state, base_loc, base_act in PAIRS:
        loc_value, act_value, loc_target, act_target = VALUES[anchor]
        for role, value, target, base, name in (
                ('location', loc_value, loc_target, base_loc, anchor),
                ('actor', act_value, act_target, base_act, other)):
            visible = [l[3:] for l in units[base]['input'].splitlines() if l.startswith('地点可见=')][0]
            for token in (anchor, other):
                assert token in visible, (anchor, other, visible)
            for token in (rel, state):
                assert token in value or token == state, (role, token, value)
            row = {'pairId': 'aug:%02d' % idx, 'sourceId': 'dirpair-r1', 'factId': 'f%d' % idx,
                   'kind': 'appearance_changed', 'armPool': 'verbalizer',
                   'signature': ['appearance_changed'], 'split': 'vb-train',
                   'directionRole': role, 'pair': 'dp%d' % ((idx + 1) // 2),
                   'input': render(units[base]['input'], name, value), 'target': target}
            rows.append(row)
            idx += 1
        freeze['pairs'].append({'pair': 'dp%d' % len(freeze['pairs']) + '' if False else 'dp%d' % len(freeze['pairs'])
                                if False else 'dp%d' % (len(freeze['pairs']) + 1),
                                'anchor': anchor, 'other': other, 'relation': rel, 'state': state,
                                'locationRow': {'name': anchor, 'value': loc_value, 'target': loc_target},
                                'actorRow': {'name': other, 'value': act_value, 'target': act_target}})
    FC.check_units([dict(r, input=r['input']) for r in rows])
    # every pair must be distinguishable and must differ in direction
    for i in range(0, len(rows), 2):
        a, b = rows[i], rows[i + 1]
        assert a['input'] != b['input']
        assert a['target'] != b['target']
        assert a['target'].split('｜')[0] != b['target'].split('｜')[0]
    OUT.mkdir(parents=True, exist_ok=True)
    for pool in POOLS:
        src = (SRC / ('pool-ctl-%s.jsonl' % pool)).read_bytes()
        base = [json.loads(l) for l in src.decode('utf-8').splitlines() if l.strip()]
        kept = [r for r in base if not str(r.get('pairId', '')).startswith('aug:')]
        out_rows = list(kept) + (rows if pool == 'verbalizer' else [])
        path = OUT / ('pool-dir-%s.jsonl' % pool)
        path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in out_rows),
                        encoding='utf-8', newline='\n')
        (OUT / ('pool-ctl-%s.jsonl' % pool)).write_bytes(src)
        freeze['files'][pool] = {
            'control': {'path': (OUT / ('pool-ctl-%s.jsonl' % pool)).relative_to(ROOT).as_posix(),
                        'rows': len(base), 'sha256': hashlib.sha256(src).hexdigest()},
            'dir': {'path': path.relative_to(ROOT).as_posix(), 'rows': len(out_rows),
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}
    ctl_rows = [r for pool in POOLS for r in (json.loads(l) for l in
                (OUT / ('pool-ctl-%s.jsonl' % pool)).read_text(encoding='utf-8').splitlines() if l.strip())]
    dir_rows = [r for pool in POOLS for r in (json.loads(l) for l in
                (OUT / ('pool-dir-%s.jsonl' % pool)).read_text(encoding='utf-8').splitlines() if l.strip())]
    ctl_ids = [r.get('pairId') or r['unitId'] for r in ctl_rows]
    dir_ids = [r.get('pairId') or r['unitId'] for r in dir_rows]
    assert ctl_ids == dir_ids, 'id sequence must stay identical'
    freeze['ids'] = {'rows': len(ctl_ids), 'sha256': hashlib.sha256('\n'.join(ctl_ids).encode()).hexdigest()}
    freeze['targets'] = {'control': hashlib.sha256('\n'.join(r['target'] for r in ctl_rows).encode()).hexdigest(),
                         'dir': hashlib.sha256('\n'.join(r['target'] for r in dir_rows).encode()).hexdigest()}
    assert freeze['targets']['control'] != freeze['targets']['dir']
    # non-block rows must be byte identical
    for pool in POOLS:
        a = (OUT / ('pool-ctl-%s.jsonl' % pool)).read_text(encoding='utf-8').splitlines()
        b = (OUT / ('pool-dir-%s.jsonl' % pool)).read_text(encoding='utf-8').splitlines()
        n = len(a) - (12 if pool == 'verbalizer' else 0)
        assert a[:n] == b[:n], pool
    (OUT / 'dirpair-freeze.json').write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + '\n',
                                            encoding='utf-8', newline='\n')
    print('rows', len(ctl_ids), 'ids', freeze['ids']['sha256'][:16])
    print('targets differ:', freeze['targets']['control'][:12], freeze['targets']['dir'][:12])
    for r in rows:
        print(' %-7s %-8s %-6s | %-16s -> %s' % (r['pairId'], r['directionRole'], r['pair'],
                                                [l[3:] for l in r['input'].splitlines() if l.startswith('事实=')][0][:22],
                                                r['target']))


if __name__ == '__main__':
    main()
