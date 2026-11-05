"""Materialise the three continuation arms and freeze the shared training plan.

  arm A  the targets exactly as the pools ship them today (control);
  arm B  conservative: keep every trailing clause, repair only a fact the target
         contradicts or drops (missing start, measure word, qualifier, or a field
         name used as a place);
  arm C  full audit: arm B plus deleting trailing clauses that state something the
         fact does not contain.

All three keep the same rows in the same order, so the step sampler draws the same
unit-id sequence; only the target strings differ. That is checked here, not
assumed: the three id lists are compared element by element.

Arm B does not isolate length. Restoring a start or a qualifier also changes the
sentence length, and arm C both repairs facts and deletes tails, so a difference
between B and C is "tail deletion on top of fact repair", not "length".

Outputs (artifacts/three-arm-r1/): arm-a.jsonl, arm-b.jsonl, arm-c.jsonl,
three-arm-freeze.json. No training is started here.
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WORKTREE = HERE.parents[1]
sys.path.insert(0, str(HERE))

import audit_decisions  # noqa: E402

OUT = WORKTREE / 'artifacts/three-arm-r1'
POOLS = audit_decisions.POOLS
BASE = {'model': 'D:/others/Jity/.local/models',
        'modelSha256': 'ab8a98264ee6b4f83eba17d624d7b92b23522c8eacef07d07a5be960e390184a'}
PLAN = {'steps': 240, 'batch': 8, 'learningRate': 0.0003, 'seed': 20261102, 'mix': [4, 3, 1],
        'epochsPerPoolFromMix': True,
        'note': 'Same steps, batch, learning rate, seed, mix and starting weights for all three arms.'}


def rows_of(pool_path):
    return [json.loads(line) for line in pool_path.read_text(encoding='utf-8').splitlines() if line.strip()]


def unit_id(row):
    return row.get('pairId') or row.get('unitId')


def target_for(arm, row):
    original = row['target']
    if arm == 'a':
        return original
    if arm == 'b':
        return audit_decisions.CONSERVATIVE.get(original, original)
    table = {original_: revised for original_, verdict, revised, _ in audit_decisions.DECISIONS
             if revised is not None}
    return table.get(original, original)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pools = {arm: [] for arm in 'abc'}
    changed = {'b': 0, 'c': 0}
    for pool, path in POOLS:
        source = rows_of(path)
        per_arm = {arm: [] for arm in 'abc'}
        for row in source:
            for arm in 'abc':
                copy = dict(row)
                copy['target'] = target_for(arm, row)
                copy['armPool'] = pool
                per_arm[arm].append(copy)
            if per_arm['b'][-1]['target'] != per_arm['a'][-1]['target']:
                changed['b'] += 1
            if per_arm['c'][-1]['target'] != per_arm['a'][-1]['target']:
                changed['c'] += 1
        for arm in 'abc':
            pools[arm].extend(per_arm[arm])
        # compare id order across arms within this pool
        assert [unit_id(r) for r in per_arm['a']] == [unit_id(r) for r in per_arm['b']] == \
               [unit_id(r) for r in per_arm['c']]
    record = {'plan': PLAN, 'base': BASE,
              'sourcePools': {name: str(path.relative_to(WORKTREE)) for name, path in POOLS},
              'files': {}, 'rows': {}, 'changedRows': {}, 'bundleSha256': {}}
    # One file per arm and per source pool, so --mix 4,3,1 keeps its meaning and the
    # three arms feed the sampler the same pool sizes in the same order.
    for arm in 'abc':
        files, digest = {}, hashlib.sha256()
        for name, _ in POOLS:
            rows = [row for row in pools[arm] if row['armPool'] == name]
            path = OUT / ('arm-%s-%s.jsonl' % (arm, name))
            text = ''.join(json.dumps(row, ensure_ascii=False) + chr(10) for row in rows)
            path.write_text(text, encoding='utf-8', newline=chr(10))
            body = path.read_bytes()
            files[name] = {'path': str(path.relative_to(WORKTREE)), 'rows': len(rows),
                           'sha256': hashlib.sha256(body).hexdigest()}
            digest.update(hashlib.sha256(body).digest())
        record['files'][arm] = files
        record['rows'][arm] = sum(item['rows'] for item in files.values())
        record['changedRows'][arm] = changed.get(arm, 0)
        record['bundleSha256'][arm] = digest.hexdigest()
    id_lists = {arm: [unit_id(row) for row in pools[arm]] for arm in 'abc'}
    assert id_lists['a'] == id_lists['b'] == id_lists['c']
    assert len(id_lists['a']) == len(set(id_lists['a']))
    record['idOrder'] = {'count': len(id_lists['a']),
                         'sha256': hashlib.sha256(chr(10).join(id_lists['a']).encode('utf-8')).hexdigest(),
                         'identicalAcrossArms': True}
    record['role'] = {'a': 'control: pool targets unchanged',
                      'b': 'fact repair only; trailing clauses kept',
                      'c': 'fact repair plus deletion of trailing clauses the fact does not support'}
    record['limits'] = ['Arm B does not isolate length: repairing a start or qualifier changes length too.',
                        'Arm C deletes tails and repairs facts together, so B vs C measures tail deletion '
                        'on top of fact repair, not length alone.',
                        'No padding is added to any arm to match a length distribution.']
    (OUT / 'three-arm-freeze.json').write_text(json.dumps(record, ensure_ascii=False, indent=1) + '\n',
                                               encoding='utf-8', newline='\n')
    print(json.dumps({k: record[k] for k in ('rows', 'changedRows', 'bundleSha256', 'idOrder')},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
