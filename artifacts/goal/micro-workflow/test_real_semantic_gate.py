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


def test_read_env_hints_parses_micro_tag():
    hints = pipeline.read_env_hints(['路明非把盖子提开（只完成一部分）；环境=hatch_cover:已被部分提开；涉及=nono'])
    assert hints == [{'entityId': 'hatch_cover', 'text': '已被部分提开'}]


def test_env_hint_and_record_are_hard_evidence():
    def snap(app=''):
        changes = [{'id': 'a1', 'text': app, 'supersedes': [], 'sourcePointId': 'p',
                    'sourceSequence': 1, 'active': True}] if app else []
        return {'transport': {'state': {
            'characters': {}, 'locations': {'room': {'id': 'room', 'appearanceChanges': []}},
            'items': {'box': {'id': 'box', 'position': {'containerId': 'room'},
                              'appearanceChanges': changes}}}}}
    row_ = {'id': 'x', 'text': '路明非把盒子提开。',
            'settled': [{'task': 'results', 'key': 'lu',
                         'text': '路明非把盒子提开（达到目的）；环境=box:已被提开'}],
            'structured': [{'key': 'lu', 'text': '路明非把盒子提开。'}],
            'snapshotBefore': snap(), 'snapshot': snap('已被提开')}
    result = pipeline.verify(row_, {'env': {'present': False, 'content': '', 'support': ''}})
    assert result['fields']['env']['status'] == 'present'
    assert result['fields']['env']['target'] is True


def test_read_info_hints_parses_micro_tag():
    hints = pipeline.read_info_hints(['路明非读规则牌（达到目的）；信息=rules:医护白线禁射；涉及=nono'])
    assert hints == [{'entityId': 'rules', 'text': '医护白线禁射'}]


def info_row(prior=''):
    return {'id': 'x', 'text': '路明非读服务巷规则牌。',
            'settled': [{'task': 'results', 'key': 'lu',
                         'text': '路明非读服务巷规则牌（达到目的）；信息=rules:医护白线禁射'}],
            'structured': [{'key': 'lu', 'text': '路明非读服务巷规则牌。'}],
            'priorText': prior, 'snapshotBefore': {}, 'snapshot': {}}


def test_info_hint_is_hard_evidence_with_content():
    result = pipeline.verify(info_row(), {'info': {'present': False, 'content': '', 'support': ''}})
    info = result['fields']['info']
    assert info['status'] == 'present' and info['target'] is True
    assert info['content'] == '医护白线禁射' and info['support'] == '医护白线禁射'


def test_info_hint_known_in_prior_is_absent():
    result = pipeline.verify(info_row(prior='……医护白线禁射……'), {'info': {'present': False, 'content': '', 'support': ''}})
    assert result['fields']['info']['status'] == 'absent'


def info_proposal_row(fact, content, support):
    return {'id': 'x', 'text': '路明非问诺诺红方控制哪个方向。',
            'settled': [{'task': 'results', 'key': 'lu', 'text': fact}],
            'structured': [{'key': 'lu', 'text': '我问诺诺红方控制哪个方向。'}],
            'protagonistId': 'lu', 'protagonistName': '路明非', 'priorText': ''}


def test_info_present_needs_actual_content():
    row_ = info_proposal_row('路明非读检修图，把旗台结构记住了。（只完成一部分）',
                             '路明非把旗台结构记住了', '路明非读检修图，把旗台结构记住了')
    result = pipeline.verify(row_, {'info': {'present': True, 'content': '路明非把旗台结构记住了',
                                             'support': '路明非读检修图，把旗台结构记住了'}})
    assert result['fields']['info']['status'] == 'insufficient'


def test_info_answer_from_fact_is_present():
    row_ = info_proposal_row('诺诺告知红方控制西侧。（达到目的）',
                             '红方控制西侧', '诺诺告知红方控制西侧')
    result = pipeline.verify(row_, {'info': {'present': True, 'content': '红方控制西侧',
                                             'support': '诺诺告知红方控制西侧'}})
    assert result['fields']['info']['status'] == 'present'


def test_info_narration_only_support_is_insufficient():
    row_ = info_proposal_row('路明非查看对方左臂识别带的颜色。（只完成一部分）',
                             '唐骁左臂识别带为黑色', '唐骁的识别带是黑色的，路明非把颜色记下来')
    result = pipeline.verify(row_, {'info': {'present': True, 'content': '唐骁左臂识别带为黑色',
                                             'support': '唐骁的识别带是黑色的，路明非把颜色记下来'}})
    assert result['fields']['info']['status'] == 'insufficient'
