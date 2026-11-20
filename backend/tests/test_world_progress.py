"""R1 recovery facts from real SQLite transitions, independent expected DFS.

These tests never infer the expected parent edge from member or response order.
The examples pre-roll two relations, accept through a child subtree, and verify
both forms of reuse without changing any previously finalized admission.
"""
import copy
import json
import sqlite3

import pytest

from app.database.world_store import SQLiteBaselineStore
from app.schemas.world.canonical import canonical_digest
from app.services.world.control import ServiceRefusal, WorldService
from tests.test_world_control_service import _payload
from tests.test_world_judgments import fixture


def scenario(tmp_path):
    flow = fixture(tmp_path, targets=False, result=20)
    now = flow['store'].world(flow['world'])['lease']['expiresAtEpochMilli'] - 60_000
    flow['store']._clock = lambda: now
    flow['now'] = now
    flow['counter'] = 0
    return flow


def checkpoint(flow, operation, **extra):
    flow['counter'] += 1
    record = flow['store'].world(flow['world'])
    return flow['service'].execute('checkpoint_' + operation, _payload(
        f"progress_{flow['counter']}", flow['world'], flow['lease'], operation=operation,
        expectedPointId=flow['head'], expectedVersion=0,
        expectedCheckpointRevision=record['control']['revision'], pointId=flow['ids']['point'],
        groupId=flow['ids']['group'], **extra))


def targets(flow, source, members):
    flow['counter'] += 1
    allocated = flow['service'].execute('allocate_ids', _payload(
        f"progress_alloc_{flow['counter']}", flow['world'], flow['lease'],
        allocationKey=f"progress_targets_{flow['counter']}",
        slots=[dict(slotKey=member, kind='trigger', scope=flow['ids']['group']) for member in members]))
    ids = {item['slotKey']: item['id'] for item in allocated['data']['allocations']}
    specs = [dict(targetId=member, triggerKey=ids[member]) for member in members]
    checkpoint(flow, 'extend_group', sourceId=source, targets=specs, admittedMember=None)
    return specs


def rolls(flow, source, specs):
    flow['counter'] += 1
    record = flow['store'].world(flow['world'])
    return flow['service'].execute('create_rolls', _payload(
        f"progress_roll_{flow['counter']}", flow['world'], flow['lease'],
        expectedPointId=flow['head'], expectedVersion=0,
        expectedCheckpointRevision=record['control']['revision'], rolls=[dict(
            advanceId=flow['ids']['advance'], roundId=flow['ids']['round'], groupId=flow['ids']['group'],
            sourceId=source, **spec, ruleVersion='reaction-d20-v1', target=11) for spec in specs]))['data']['rolls']


def accept(flow, outcome, text=None):
    return checkpoint(flow, 'extend_group', sourceId=outcome['sourceId'], targets=None,
        admittedMember=dict(memberId=outcome['targetId'], actionText=text or f"{outcome['targetId']} 原文\r\n",
            rollRefs=[{key: outcome[key] for key in ('sourceId', 'targetId', 'triggerKey', 'rollId')}]))


def recovery(flow):
    return flow['service'].execute('get_context', dict(worldId=flow['world'], includeRecovery=True,
        leaseToken=flow['lease']['leaseToken'], fenceEpoch=flow['lease']['fenceEpoch']))['recovery']['current']


def facts(flow):
    return recovery(flow)['groups'][0]


def threat(outcome, status, disposition=None):
    result = {key: outcome[key] for key in ('sourceId', 'targetId', 'triggerKey', 'rollId')}
    result.update(status=status, reactionMemberId=outcome['targetId'] if disposition in ('created', 'reused') else None)
    if disposition:
        result['actionDisposition'] = disposition
    return result


def test_unconfirmed_empty_targets_and_pending_roll_are_distinct_across_reopen(tmp_path):
    flow = scenario(tmp_path)
    initial = facts(flow)
    assert initial['rolls'] == []
    assert initial['progress'] == dict(sourceStack=['person_a'], threats=[])
    assert initial['members'][0]['targets'] is None
    specs = targets(flow, 'person_a', ['person_b'])
    pending = facts(flow)
    assert pending['progress'] == dict(sourceStack=['person_a'], threats=[dict(
        sourceId='person_a', **specs[0], status='pending_roll', rollId=None, reactionMemberId=None)])
    reopened = SQLiteBaselineStore(flow['path'], clock=lambda: flow['now'])
    flow.update(store=reopened, service=WorldService(reopened))
    assert facts(flow) == pending


def test_confirmed_empty_targets_persists_empty_stack_and_closes_without_roll(tmp_path):
    flow = scenario(tmp_path)
    checkpoint(flow, 'extend_group', sourceId='person_a', targets=[], admittedMember=None)
    assert facts(flow)['progress'] == dict(sourceStack=[], threats=[])
    assert facts(flow)['members'][0]['targets'] == []
    assert checkpoint(flow, 'close_group')['data']['closed']
    assert facts(flow)['rolls'] == [] and flow['calls'] == []


def test_created_child_retains_waiting_ancestor_but_frontier_only_unfinished_sources(tmp_path):
    flow = scenario(tmp_path)
    outcome = rolls(flow, 'person_a', targets(flow, 'person_a', ['person_b']))[0]
    assert facts(flow)['progress'] == dict(sourceStack=['person_a'], threats=[threat(outcome, 'reaction_pending')])
    answer = accept(flow, outcome)
    assert answer['data']['frontierIds'] == ['person_b']
    assert facts(flow)['progress'] == dict(sourceStack=['person_b', 'person_a'], threats=[threat(outcome, 'handled', 'created')])
    checkpoint(flow, 'extend_group', sourceId='person_b', targets=[], admittedMember=None)
    assert facts(flow)['progress']['sourceStack'] == []


def test_pre_rolled_parent_threat_reuses_child_accepted_action_without_flipping_admitted(tmp_path):
    flow = scenario(tmp_path)
    parent = rolls(flow, 'person_a', targets(flow, 'person_a', ['person_b', 'person_c']))
    assert all(item['admitted'] for item in parent)
    accept(flow, parent[0])
    child = rolls(flow, 'person_b', targets(flow, 'person_b', ['person_c']))[0]
    accept(flow, child)
    view = facts(flow)
    assert view['progress']['sourceStack'] == ['person_c', 'person_b', 'person_a']
    assert view['progress']['threats'] == [threat(parent[0], 'handled', 'created'),
        threat(parent[1], 'handled', 'reused'), threat(child, 'handled', 'created')]
    assert view['rolls'] == [*parent, child]
    assert {m['memberId']: len(m['rollRefs']) for m in view['members']} == dict(person_a=2, person_b=1, person_c=0)
    assert flow['store'].world(flow['world'])['work']['pendingGroup']['frontierIds'] == ['person_c']
    checkpoint(flow, 'extend_group', sourceId='person_c', targets=[], admittedMember=None)
    assert facts(flow)['progress']['sourceStack'] == []
    assert checkpoint(flow, 'close_group')['data']['closed']
    assert facts(flow)['rolls'] == [*parent, child]


def test_first_roll_after_child_acceptance_is_ineligible_and_still_saved(tmp_path):
    flow = scenario(tmp_path)
    specs = targets(flow, 'person_a', ['person_b', 'person_c'])
    parent_b = rolls(flow, 'person_a', specs[:1])[0]
    accept(flow, parent_b)
    child = rolls(flow, 'person_b', targets(flow, 'person_b', ['person_c']))[0]
    accept(flow, child)
    checkpoint(flow, 'extend_group', sourceId='person_c', targets=[], admittedMember=None)
    assert facts(flow)['progress']['sourceStack'] == ['person_a']
    late = rolls(flow, 'person_a', specs[1:])[0]
    assert late['result'] == 20 and not late['eligible'] and not late['admitted']
    assert facts(flow)['progress']['sourceStack'] == []
    assert facts(flow)['progress']['threats'] == [threat(parent_b, 'handled', 'created'),
        threat(late, 'handled', 'none'), threat(child, 'handled', 'created')]
    assert len(flow['calls']) == 3


def test_loop_roll_records_rejection_to_existing_initiator_and_never_repeats_action(tmp_path):
    flow = scenario(tmp_path)
    parent = rolls(flow, 'person_a', targets(flow, 'person_a', ['person_b']))[0]
    accept(flow, parent)
    loop = rolls(flow, 'person_b', targets(flow, 'person_b', ['person_a']))[0]
    assert not loop['eligible'] and not loop['admitted']
    assert facts(flow)['progress']['sourceStack'] == []
    assert facts(flow)['progress']['threats'] == [threat(parent, 'handled', 'created'), threat(loop, 'handled', 'none')]
    assert len(facts(flow)['members']) == 2


def test_acceptance_cannot_skip_lexical_pending_threat_or_jump_to_waiting_parent(tmp_path):
    flow = scenario(tmp_path)
    specs = targets(flow, 'person_a', ['person_b', 'person_c'])
    second = rolls(flow, 'person_a', specs[1:])[0]
    before = flow['store'].world(flow['world'])
    with pytest.raises(ServiceRefusal, match='next fixed source threat'):
        accept(flow, second)
    assert flow['store'].world(flow['world']) == before
    first = rolls(flow, 'person_a', specs[:1])[0]
    accept(flow, first)
    before = flow['store'].world(flow['world'])
    with pytest.raises(ServiceRefusal, match='current persisted DFS source'):
        accept(flow, second)
    assert flow['store'].world(flow['world']) == before


@pytest.mark.parametrize('boundary', ['targets', 'roll', 'accept'])
def test_checkpoint_failure_rolls_back_targets_judgment_or_original_acceptance_atomically(tmp_path, boundary):
    flow = scenario(tmp_path)
    if boundary != 'targets':
        specs = targets(flow, 'person_a', ['person_b'])
    if boundary == 'accept':
        outcome = rolls(flow, 'person_a', specs)[0]
    before = flow['store'].world(flow['world'])
    with sqlite3.connect(flow['path']) as db:
        counts = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                  for table in ('world_rolls', 'world_roll_baselines', 'world_accepted_work', 'world_frozen_work')}
        db.execute("CREATE TRIGGER fail_progress BEFORE UPDATE ON world_group_progress BEGIN SELECT RAISE(ABORT,'progress transaction failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='progress transaction failure'):
        if boundary == 'targets':
            checkpoint(flow, 'extend_group', sourceId='person_a', targets=[], admittedMember=None)
        elif boundary == 'roll':
            rolls(flow, 'person_a', specs)
        else:
            accept(flow, outcome)
    assert flow['store'].world(flow['world']) == before
    with sqlite3.connect(flow['path']) as db:
        assert {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in counts} == counts


@pytest.mark.parametrize('corruption,code', [('missing_checkpoint', 'frozen_work_missing'),
    ('missing_roll', 'frozen_work_missing'), ('missing_baseline', 'frozen_work_missing'),
    ('wrong_trigger', 'frozen_work_corrupt'), ('stack', 'frozen_work_corrupt'),
    ('association', 'frozen_work_corrupt'), ('hash', 'frozen_work_corrupt')])
def test_corrupt_recovery_never_converts_saved_fact_to_unsampled_work(tmp_path, corruption, code):
    flow = scenario(tmp_path)
    outcome = rolls(flow, 'person_a', targets(flow, 'person_a', ['person_b']))[0]
    calls = len(flow['calls'])
    with sqlite3.connect(flow['path']) as db:
        if corruption == 'missing_checkpoint':
            db.execute('DELETE FROM world_group_progress')
        elif corruption == 'missing_roll':
            db.execute('DELETE FROM world_rolls')
        elif corruption == 'missing_baseline':
            db.execute('DELETE FROM world_roll_baselines')
        elif corruption == 'wrong_trigger':
            db.execute('DROP TRIGGER roll_immutable')
            db.execute("UPDATE world_rolls SET trigger_key='unrelated_trigger'")
        else:
            value = json.loads(db.execute('SELECT checkpoint_json FROM world_group_progress').fetchone()[0])
            if corruption == 'stack':
                value['progress']['sourceStack'] = []
            elif corruption == 'association':
                value['progress']['threats'][0]['rollId'] = 'unrelated_final_roll'
            else:
                value['progress']['threats'] = []
            digest = '0' * 64 if corruption == 'hash' else canonical_digest(value)
            db.execute('UPDATE world_group_progress SET checkpoint_json=?,checkpoint_digest=?', (json.dumps(value), digest))
    with pytest.raises(ServiceRefusal) as refusal:
        recovery(flow)
    assert refusal.value.code == code
    assert len(flow['calls']) == calls


def test_accepted_original_without_unique_created_edge_is_corrupt_not_reaction_pending(tmp_path):
    flow = scenario(tmp_path)
    outcome = rolls(flow, 'person_a', targets(flow, 'person_a', ['person_b']))[0]
    accept(flow, outcome)
    with sqlite3.connect(flow['path']) as db:
        value = json.loads(db.execute('SELECT checkpoint_json FROM world_group_progress').fetchone()[0])
        value['progress']['threats'][0]['actionDisposition'] = 'reused'
        db.execute('UPDATE world_group_progress SET checkpoint_json=?,checkpoint_digest=?',
                   (json.dumps(value), canonical_digest(value)))
    with pytest.raises(ServiceRefusal) as refusal:
        recovery(flow)
    assert refusal.value.code == 'frozen_work_corrupt'
    assert len(flow['calls']) == 1


def test_active_gc_preserves_checkpoint_and_terminal_gc_removes_only_short_term_progress(tmp_path):
    flow = scenario(tmp_path)
    outcome = rolls(flow, 'person_a', targets(flow, 'person_a', ['person_b']))[0]
    expected = facts(flow)
    assert flow['store'].collect_garbage(flow['world'])['world_group_progress'] == 0
    assert facts(flow) == expected
    record = flow['store'].world(flow['world'])
    flow['service'].execute('round_conclusion_cancel', _payload(
        'progress_cancel', flow['world'], flow['lease'], operation='cancel',
        advanceId=flow['ids']['advance'], roundId=flow['ids']['round'],
        expectedPointId=flow['head'], expectedVersion=0,
        expectedCheckpointRevision=record['control']['revision'], cancelReason='测试短期进度清理。'))
    assert flow['store'].collect_garbage(flow['world'])['world_group_progress'] == 1
    with sqlite3.connect(flow['path']) as db:
        assert db.execute('SELECT count(*) FROM world_group_progress').fetchone() == (0,)
        assert db.execute('SELECT id FROM world_rolls').fetchall() == [(outcome['rollId'],)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert flow['store'].world(flow['world'])['_groupProgress'] == {}


def test_takeover_restores_exact_rolls_progress_and_originals_without_sampling(tmp_path):
    flow = scenario(tmp_path)
    parent = rolls(flow, 'person_a', targets(flow, 'person_a', ['person_b', 'person_c']))
    accept(flow, parent[0])
    expected = facts(flow)
    revision = flow['store'].world(flow['world'])['control']['revision']
    flow['service'].execute('lease_release', _payload('progress_release', flow['world'], flow['lease']))
    flow['lease'] = flow['service'].execute('lease_acquire', dict(protocolVersion=2,
        requestId='progress_acquire', worldId=flow['world'], holderId='another_tab'))['data']
    hidden = recovery(flow)
    assert hidden['payloadStatus'] == 'restore_required' and hidden['groups'] == []
    for index, source in enumerate(hidden['restoreSources']):
        flow['service'].execute('checkpoint_restore_group_work', _payload(
            f'progress_restore_{index}', flow['world'], flow['lease'], operation='restore_group_work',
            expectedPointId=flow['head'], expectedVersion=0, expectedCheckpointRevision=revision, **source))
    actual = facts(flow)
    assert actual['progress'] == expected['progress'] and actual['rolls'] == expected['rolls']
    assert actual['members'] == expected['members']
    assert len(flow['calls']) == 2
