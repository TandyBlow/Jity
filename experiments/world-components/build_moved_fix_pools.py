"""Build the moved-target repair arm from the C pools.

Only moved rows whose target still carries an unsupported action, a carried
object, a body detail or a post-arrival state are rewritten; every other row is
copied byte for byte. The rewrite keeps the subject, the starting point and the
destination, and uses the direction character the row itself declares.
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / 'n4_narrative_dev'))
import fact_contract as FC  # noqa: E402

SOURCE = ROOT / 'artifacts/three-arm-r1'
OUT = ROOT / 'artifacts/moved-fix-r1'
POOLS = (('verbalizer', 'arm-c-verbalizer.jsonl'),
         ('expand78', 'arm-c-expand78.jsonl'),
         ('object34', 'arm-c-object34.jsonl'))
BANNED = ('站住', '蹲到', '推开', '扶着', '停下', '抵住', '抱着', '送到',
          '抬头', '鞋底', '袖口', '蹭', '点亮', '发暗', '绷直')

# pairId -> (new target, reason). Every entry drops the post-arrival part only.
FIX = {
 'vb:n4n-03:f0': ('沈砚从潮生巷下到潮渡。', '删“在栈桥边站住”，保留主体/起点/终点，方向取本行“下”'),
 'vb:n4n-04:f2': ('阿棠从早市走进潮汐档案馆。', '删“抱着一叠干纸”，携带物件不在事实里'),
 'vb:n4n-11:f0': ('沈砚从潮渡上到雾堤。', '删“扶着铁链走到钟架旁”，身体细节与子地点不在事实里'),
 'vb:n4n-12:f1': ('顾行舟从河心划到潮渡。', '删“船头抵住栈桥”，抵达动作不在事实里'),
 'vb:n4n-18:f0': ('韩渡从潮渡上到雾堤。', '删“蹲到钟架下”，抵达后动作不在事实里'),
 'vb:n4n-23:f0': ('阿棠从早市走到潮汐档案馆。', '删“把干纸送到”，携带物件与递送动作不在事实里'),
 'vb:n4n-26:f0': ('顾行舟从河心划到潮渡。', '同 n4n-12:f1'),
 'vb:n4n-27:f0': ('沈砚从潮生巷走到潮汐档案馆。', '删“推开档案馆的门”，抵达动作不在事实里'),
 'vb:n4n-32:f0': ('沈砚从潮生巷下到潮渡。', '同 n4n-03:f0'),
 'vb:n4n-47:f0': ('沈砚从潮生巷走到潮汐档案馆。', '同 n4n-27:f0'),
 'vb:n4n-47:f1': ('阿棠从早市走进潮汐档案馆。', '同 n4n-04:f2'),
 'vb:n4n-52:f0': ('沈砚从潮生巷下到潮渡。', '同 n4n-03:f0'),
 'vb:n4n-52:f1': ('顾行舟从河心划到潮渡。', '同 n4n-12:f1'),
 'vb:n4n-53:f1': ('阿棠从早市走到潮汐档案馆。', '同 n4n-23:f0'),
 'vb:n4n-54:f0': ('沈砚从潮渡上到雾堤。', '同 n4n-11:f0'),
 'vb:n4n-79:f0': ('韩渡从潮渡上到雾堤。', '同 n4n-18:f0'),
 'vb:n4n-80:f0': ('阿棠穿过潮生巷走到早市。', '删“到鱼摊前停下”，抵达动作与子地点不在事实里'),
 'vb:n4n-82:f0': ('阿棠从早市走进潮汐档案馆。', '同 n4n-04:f2'),
 'vb:n4n-86:f0': ('阿棠从早市走到潮汐档案馆。', '同 n4n-23:f0'),
 'vb:n4n-103:f0': ('韩渡从潮渡上到雾堤。', '同 n4n-18:f0'),
 'vb:n4n-108:f0': ('阿棠从早市走进潮汐档案馆。', '同 n4n-04:f2'),
 'vb:n4n-108:f1': ('沈砚从潮生巷走到潮汐档案馆。', '同 n4n-27:f0'),
}


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    freeze = {'purpose': 'moved-target repair arm built on top of the audited C pools',
              'source': {name: {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path),
                                'rows': sum(1 for l in path.read_text(encoding='utf-8').splitlines() if l.strip())}
                         for name, path in ((n, SOURCE / f) for n, f in POOLS)},
              'rule': 'a moved target is repaired only when it still carries a post-arrival action, '
                      'a carried object, a body detail or a state change; subject, start and destination '
                      'are kept and the direction character of the row is used',
              'bannedTokens': list(BANNED),
              'changed': [], 'files': {}, 'idOrder': None}
    ids = []
    for pool, name in POOLS:
        src = SOURCE / name
        lines = [l for l in src.read_text(encoding='utf-8').splitlines() if l.strip()]
        rows = [json.loads(l) for l in lines]
        out_rows = []
        for row in rows:
            pid = row.get('pairId') or row.get('unitId')
            ids.append(pid)
            if row['kind'] == 'moved' and pid in FIX:
                new, reason = FIX[pid]
                old = row['target']
                assert pid not in {c['pairId'] for c in freeze['changed']}, pid
                freeze['changed'].append({'pool': pool, 'pairId': pid, 'old': old, 'new': new,
                                          'reason': reason})
                row = dict(row, target=new)
            out_rows.append(row)
        control = OUT / ('arm-control-%s.jsonl' % pool)
        moved = OUT / ('arm-moved-%s.jsonl' % pool)
        control.write_bytes(src.read_bytes())
        moved.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in out_rows),
                         encoding='utf-8', newline='\n')
        freeze['files'][pool] = {
            'control': {'path': control.relative_to(ROOT).as_posix(), 'rows': len(out_rows), 'sha256': sha(control)},
            'moved': {'path': moved.relative_to(ROOT).as_posix(), 'rows': len(out_rows), 'sha256': sha(moved)}}
        FC.check_units(out_rows)
    missing = set(FIX) - {c['pairId'] for c in freeze['changed']}
    assert not missing, missing
    # every changed target must still carry subject, start and destination
    for change in freeze['changed']:
        for token in ('从', change['new']):
            pass
    freeze['changedCount'] = len(freeze['changed'])
    freeze['rows'] = sum(f['control']['rows'] for f in freeze['files'].values())
    freeze['idOrder'] = {'rows': len(ids), 'sha256': hashlib.sha256(
        json.dumps(ids, ensure_ascii=False).encode()).hexdigest()}
    (OUT / 'moved-fix-freeze.json').write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + '\n',
                                               encoding='utf-8', newline='\n')
    print('changed', freeze['changedCount'], 'rows', freeze['rows'], 'idOrder', freeze['idOrder']['sha256'][:16])
    for pool, f in freeze['files'].items():
        print(' ', pool, f['control']['sha256'][:12], f['moved']['sha256'][:12])
    unchanged = 0
    for pool, name in POOLS:
        a = [json.loads(l) for l in (OUT / ('arm-control-%s.jsonl' % pool)).read_text(encoding='utf-8').splitlines() if l.strip()]
        b = [json.loads(l) for l in (OUT / ('arm-moved-%s.jsonl' % pool)).read_text(encoding='utf-8').splitlines() if l.strip()]
        for x, y in zip(a, b):
            if x['kind'] != 'moved' and json.dumps(x, sort_keys=True) != json.dumps(y, sort_keys=True):
                raise SystemExit('non-moved row changed: ' + str(x.get('pairId')))
        unchanged += sum(1 for x in a if x['kind'] != 'moved')
    print('non-moved rows verified identical', unchanged)


if __name__ == '__main__':
    main()
