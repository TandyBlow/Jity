# -*- coding: utf-8 -*-
"""Negative tests for the acceptance gate itself (the user's requirement)."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pipeline = load('real_semantic_data')
gate = load('validate_real_semantic')


def row(identity, split='train', version='v2'):
    item = {'id': identity, 'split': split, 'input': '我走向门口。', 'text': '他走到门口。',
            'settled': [{'task': 'targets', 'text': '门口'}], 'stateDiff': {'known': True, 'added': [],
                                                                              'removed': [], 'changed': [], 'env': []},
            'label': {'info': {'status': 'absent', 'target': False, 'trainable': True, 'content': '',
                               'support': '', 'proposed': False, 'evidence': ''},
                      'env': {'status': 'insufficient', 'target': None, 'trainable': False, 'content': '',
                              'support': '', 'proposed': False, 'evidence': ''}}}
    item['labelMeta'] = {'promptVersion': version, 'inputHash': gate.input_hash(item),
                         'labelModel': 'm', 'evidence': {'info': 'settled', 'env': 'state'}}
    return item


def train_export(identity):
    return {'id': identity, 'split': 'train', 'input': '我走向门口。', 'text': '他走到门口。',
            'settled': [], 'stateDiff': {}, 'labels': {'info': {'target': False, 'trainable': True}}}


def valid_sets():
    raw = [row('t1'), row('t2'), row('s1', split='test')]
    train = [train_export('t1'), train_export('t2')]
    test = [{'id': 's1', 'labels': {}}]
    return raw, train, test


def test_environment_keys_ignores_unchanged_item_in_location():
    before = {'item:box': {'position': {'containerId': 'yard'}, 'appearance': {}}}
    after = {'item:box': {'position': {'containerId': 'yard'}, 'appearance': {}}}
    assert pipeline.environment_keys(before, after, {'yard'}) == []


def test_environment_keys_detects_item_moved_into_location():
    before = {'item:box': {'position': {'containerId': 'lu'}, 'appearance': {}}}
    after = {'item:box': {'position': {'containerId': 'yard'}, 'appearance': {}}}
    assert pipeline.environment_keys(before, after, {'yard'}) == ['item:box']


def test_env_absent_requires_explicit_negative():
    diff = {'known': True, 'added': [], 'removed': [], 'changed': [], 'env': []}
    item = {'present': False}
    assert pipeline.classify('env', item, {}, diff, '', '', '', '') == 'insufficient'
    assert pipeline.classify('env', item, {}, diff, '', '', '', '没有变化') == 'absent'


def test_gate_accepts_valid_sets():
    raw, train, test = valid_sets()
    failures = gate.validate(raw, train, test, [], {'t1', 't2'}, {'s1'}, {'s1'})
    assert failures == []


def test_gate_rejects_missing_coverage():
    raw, train, test = valid_sets()
    failures = gate.validate(raw, train, test, [], {'t1', 't2', 't3'}, {'s1'}, {'s1'})
    assert any('missing train input t3' in item for item in failures)


def test_gate_rejects_model_label_without_metadata():
    raw, train, test = valid_sets()
    raw[0]['labelMeta'] = {}
    failures = gate.validate(raw, train, test, [], {'t1', 't2'}, {'s1'}, {'s1'})
    assert any('promptVersion' in item for item in failures)


def test_gate_rejects_old_version():
    raw, train, test = valid_sets()
    raw[0] = row('t1', version='v1')
    failures = gate.validate(raw, train, test, [], {'t1', 't2'}, {'s1'}, {'s1'})
    assert any('promptVersion != v2' in item for item in failures)


def test_gate_rejects_untrainable_training_export():
    raw, train, test = valid_sets()
    train[0]['labels']['env'] = {'target': None, 'trainable': False}
    failures = gate.validate(raw, train, test, [], {'t1', 't2'}, {'s1'}, {'s1'})
    assert any('untrainable field' in item for item in failures)


def test_gate_rejects_intent_echo():
    raw, train, test = valid_sets()
    raw[0]['settled'] = [{'task': 'action', 'text': raw[0]['input']}]
    failures = gate.validate(raw, train, test, [], {'t1', 't2'}, {'s1'}, {'s1'})
    assert any('intent echo' in item for item in failures)


def test_gate_rejects_scenario_in_train():
    raw, train, test = valid_sets()
    train[0]['id'] = 's1'
    failures = gate.validate(raw, train, test, [], {'t1', 't2'}, {'s1'}, {'s1'})
    assert any('scenario ids in training export' in item for item in failures)


def test_gate_rejects_test_not_scenario():
    raw, train, test = valid_sets()
    test[0]['id'] = 't1'
    failures = gate.validate(raw, train, test, [], {'t1', 't2'}, {'s1'}, {'s1'})
    assert any('test export ids' in item for item in failures)


def test_field_counts_and_training_threshold():
    train = [train_export('t1'), train_export('t2')]
    counts = gate.field_counts(train)
    assert counts == {'info': {'pos': 0, 'neg': 2}}
    assert gate.training_ready(counts) == {'info': False}
    full = [{'labels': {'env': {'target': True}}} for _ in range(50)]
    full += [{'labels': {'env': {'target': False}}} for _ in range(50)]
    counts = gate.field_counts(full)
    assert counts == {'env': {'pos': 50, 'neg': 50}}
    assert gate.training_ready(counts) == {'env': True}
