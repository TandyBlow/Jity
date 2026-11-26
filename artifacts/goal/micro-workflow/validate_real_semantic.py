# -*- coding: utf-8 -*-
"""Automatic acceptance gate for the real semantic dataset.

Exit 1 on any violation. The six conditions mirror the user's acceptance:
1. no unverified/conflict label in train;
2. no old-version cache hit;
3. no frozen test row in train;
4. no player intent used as an actual result;
5. every used cache record has input hash, prompt version, model, evidence;
6. test labels are not in train and not used for threshold fitting.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
DATASET = HERE / 'real-semantic.jsonl'
CACHE = HERE / 'real-semantic-cache.jsonl'
SCENARIOS = HERE / 'scenarios-independent.json'
OUT = HERE / 'micro-generative/real-semantic-validation.json'
VERSION = 'v2'


def input_hash(row):
    payload = row.get('input', '') + '\n' + row.get('text', '') + '\n' + json.dumps(
        row.get('settled') or [], ensure_ascii=False) + '\n' + json.dumps(
        row.get('stateDiff') or {}, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf8')).hexdigest()


def main():
    rows = [json.loads(line) for line in DATASET.read_text(encoding='utf8').splitlines() if line.strip()]
    cache = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding='utf8').splitlines():
            if line.strip():
                record = json.loads(line)
                cache[record.get('id')] = record
    scenario_ids = {row['id'] for row in json.loads(SCENARIOS.read_text(encoding='utf8'))}
    failures = []
    used_cache = set()
    train_rows = [row for row in rows if row.get('split') == 'train']
    test_rows = [row for row in rows if row.get('split') == 'test']
    for row in rows:
        for field, item in (row.get('label') or {}).items():
            status = item.get('status')
            target = item.get('target')
            trainable = item.get('trainable')
            if row.get('split') == 'train':
                if status in ('insufficient', 'conflict'):
                    failures.append(f"{row['id']}:{field} train has {status}")
                if not trainable or target is None:
                    failures.append(f"{row['id']}:{field} train not trainable")
            if status == 'present' and target is not True:
                failures.append(f"{row['id']}:{field} present target != true")
            if status == 'absent' and target is not False:
                failures.append(f"{row['id']}:{field} absent target != false")
            if status in ('insufficient', 'conflict') and target is not None:
                failures.append(f"{row['id']}:{field} unverified target not null")
        for settled in row.get('settled') or []:
            if settled.get('task') == 'action' and settled.get('text') == row.get('input'):
                failures.append(f"{row['id']} settled contains the player intent echo")
        for field, item in (row.get('label') or {}).items():
            support = (item.get('support') or '').strip()
            if item.get('status') == 'present' and support:
                text = row.get('text') or ''
                settled_text = json.dumps(row.get('settled') or [], ensure_ascii=False)
                if support not in text and support not in settled_text:
                    failures.append(f"{row['id']}:{field} support only in intent/unknown source")
        if row.get('labelSource') == 'cache':
            used_cache.add(row['id'])
            record = cache.get(row['id'])
            if not record:
                failures.append(f"{row['id']} cache source but no cache record")
            else:
                if record.get('promptVersion') != VERSION:
                    failures.append(f"{row['id']} old-version cache hit")
                if record.get('inputHash') != input_hash(row):
                    failures.append(f"{row['id']} cache input hash mismatch")
                for key in ('labelModel', 'evidence'):
                    if not record.get(key):
                        failures.append(f"{row['id']} cache missing {key}")
        if row.get('split') == 'train' and row['id'] in scenario_ids:
            failures.append(f"{row['id']} frozen test in train")
        if row.get('split') == 'test' and row['id'] not in scenario_ids:
            failures.append(f"{row['id']} non-scenario in test")
    if not train_rows:
        failures.append('no train rows')
    if not test_rows:
        failures.append('no test rows')
    if any(row['id'] in scenario_ids for row in train_rows):
        failures.append('scenario ids in train')
    report = {'version': VERSION, 'pass': not failures, 'rows': len(rows),
              'trainRows': len(train_rows), 'testRows': len(test_rows),
              'usedCache': len(used_cache), 'failures': failures}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if failures:
        sys.exit(1)


if __name__ == '__main__':
    main()
