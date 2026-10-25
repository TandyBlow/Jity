"""Actual SQLite accepted-work and takeover recovery fault tests.

Repository tests deliberately call the copy inside BEGIN IMMEDIATE.  HTTP
tests cover lease/revision/requestId authority at the WorldService boundary.
"""
import copy
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app.database.world_frozen_repository import (
    FrozenWorkError, active_sources, check_frozen_work, collect_terminal_frozen,
    confirmed_targets, initialize_frozen_schema, require_current_payload,
    restore_group_work, save_frozen_work,
)
from app.schemas.world.canonical import canonical_digest
from app.services.world.control import _work_view
from app.services.world.recovery import recovery_view
from tests.test_world_control_service import ORDER, _payload, begin_work, single_group
from tests.test_world_sqlite_store import reopen
from tests.test_world_work_store import discover, staged


def prepare(path, completed=True):
    result = staged(path) if completed else discover(path)
    service, flow = result[:2]
    with service.store.locked():
        connection = service.store._local.connection
        initialize_frozen_schema(connection)
        record = service.store.world(flow['world_id'])
        save_frozen_work(connection, None, record)
        check_frozen_work(connection, record)
    return service, flow, record


def db(path):
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    connection.execute('PRAGMA foreign_keys=ON')
    return connection


def context(connection, record):
    return recovery_view(connection, record, _work_view(record))['current']


def new_owner(record, epoch=None):
    changed = copy.deepcopy(record)
    changed['lease']['fenceEpoch'] = epoch or record['lease']['fenceEpoch'] + 1
    changed['lease']['leaseToken'] = 'lease_new_owner'
    return changed


def request(source, request_id='restore'):
    return SimpleNamespace(**source, requestId=request_id)


def test_confirmation_persists_independent_text_and_candidate_hashes(tmp_path):
    path = tmp_path / 'accepted.sqlite'
    _, flow, record = prepare(path)
    with db(path) as connection:
        recovered = context(connection, record)
        group = recovered['groups'][0]
        member, source = group['members'][0], group['acceptedSources'][0]
        assert member['actionText'].encode() == '原文\r\n走向讲台。'.encode()
        assert member['resultText'].encode() == '结果\r\n已经走上讲台。'.encode()
        assert member['targets'] == []
        assert source['actionContentHash'] == hashlib.sha256('原文\r\n走向讲台。'.encode()).hexdigest()
        assert source['resultContentHash'] == hashlib.sha256('结果\r\n已经走上讲台。'.encode()).hexdigest()
        assert source['targetsContentHash'] == hashlib.sha256(b'[]').hexdigest()
        expected = single_group(['person_a'], ORDER, flow['group_id'])
        assert group['candidates'] == expected.model_dump(mode='json')
        assert source['candidatesContentHash'] == canonical_digest(expected.model_dump(mode='json'))
        assert connection.execute('SELECT count(*) FROM world_accepted_work').fetchone()[0] >= 1
        assert connection.execute('SELECT count(*) FROM world_frozen_work').fetchone()[0] >= 1
        assert connection.execute('SELECT count(*) FROM world_work_refs').fetchone()[0] == 1


def test_unconfirmed_targets_are_not_replaced_by_empty_confirmed_targets(tmp_path):
    path = tmp_path / 'unconfirmed.sqlite'
    _, _, record = prepare(path, completed=False)
    with db(path) as connection:
        before = context(connection, record)['groups'][0]
        assert before['members'][0]['targets'] is None
        assert before['acceptedSources'][0]['targetsContentHash'] is None
        changed = new_owner(record)
        source = active_sources(connection, record['worldId'], record['work']['pointId'])[0]
        restore_group_work(connection, changed, request(source))
        after = context(connection, changed)['groups'][0]
        assert after == before


def test_takeover_hides_all_bytes_until_controlled_copy_then_preserves_original_sources(tmp_path):
    path = tmp_path / 'takeover.sqlite'
    _, _, record = prepare(path)
    with db(path) as connection:
        before = context(connection, record)
        changed = new_owner(record)
        hidden = context(connection, changed)
        assert hidden['payloadStatus'] == 'restore_required'
        assert hidden['groups'] == [] and hidden['timeScanCandidates'] is None
        assert hidden['work'] == before['work']
        source = hidden['restoreSources'][0]
        with pytest.raises(FrozenWorkError) as refusal:
            require_current_payload(connection, changed)
        assert refusal.value.code == 'frozen_work_missing'
        assert refusal.value.details['reason'] == 'restore_required'
        initial = copy.deepcopy(changed)
        data = restore_group_work(connection, changed, request(source))
        assert changed == initial  # no phase/revision/time/cursor mutation
        after = context(connection, changed)
        assert after['payloadStatus'] == 'available' and after['restoreSources'] == []
        assert after['groups'] == before['groups']
        assert data['attempt'] > source['sourceAttempt']
        row = connection.execute('''SELECT action_bytes,result_bytes,candidates_json,source_epoch,source_attempt
            FROM world_frozen_work WHERE epoch=? AND attempt=?''',
            (changed['lease']['fenceEpoch'], data['attempt'])).fetchone()
        assert row[0] == '原文\r\n走向讲台。'.encode()
        assert row[1] == '结果\r\n已经走上讲台。'.encode()
        assert json.loads(row[2]) == before['groups'][0]['candidates']
        assert row[3:] == (source['sourceEpoch'], source['sourceAttempt'])
        require_current_payload(connection, changed)


def test_business_deduplication_survives_new_request_id_and_connection(tmp_path):
    path = tmp_path / 'business.sqlite'
    _, _, record = prepare(path)
    changed = new_owner(record)
    with db(path) as connection:
        source = active_sources(connection, record['worldId'], record['work']['pointId'])[0]
        first = restore_group_work(connection, changed, request(source, 'first_request'))
    with db(path) as connection:
        second = restore_group_work(connection, changed, request(source, 'second_request'))
        assert second == first
        assert connection.execute('SELECT count(*) FROM world_copy_results').fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM world_frozen_work WHERE epoch=?',
            (changed['lease']['fenceEpoch'],)).fetchone()[0] == 1


def test_concurrent_copies_allocate_one_attempt_inside_sqlite_transaction(tmp_path):
    path = tmp_path / 'concurrent.sqlite'
    _, _, record = prepare(path)
    changed = new_owner(record)
    with db(path) as connection:
        source = active_sources(connection, record['worldId'], record['work']['pointId'])[0]

    def copy_from_other_process_like_connection(index):
        with db(path) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                result = restore_group_work(connection, changed, request(source, f'concurrent_{index}'))
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(copy_from_other_process_like_connection, range(4)))
    assert all(result == results[0] for result in results)
    with db(path) as connection:
        assert connection.execute('SELECT count(*) FROM world_copy_results').fetchone()[0] == 1


@pytest.mark.parametrize('table', ['world_accepted_work', 'world_frozen_work', 'world_copy_results'])
def test_sql_copy_fault_rolls_back_all_accepted_payload_and_result_rows(tmp_path, table):
    path = tmp_path / 'rollback.sqlite'
    _, _, record = prepare(path)
    changed = new_owner(record)
    with db(path) as connection:
        source = active_sources(connection, record['worldId'], record['work']['pointId'])[0]
        tables = ('world_accepted_work','world_frozen_work','world_work_refs','world_copy_results')
        before = {name: connection.execute(f'SELECT * FROM {name}').fetchall() for name in tables}
        connection.execute(f'''CREATE TRIGGER copy_fault BEFORE INSERT ON {table}
            BEGIN SELECT RAISE(ABORT,'injected copy fault'); END''')
        connection.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.IntegrityError, match='injected copy fault'):
            try:
                restore_group_work(connection, changed, request(source))
            finally:
                connection.rollback()
        assert {name:connection.execute(f'SELECT * FROM {name}').fetchall() for name in tables} == before
        connection.execute('DROP TRIGGER copy_fault')
        assert context(connection, changed)['restoreSources'] == [source]
        assert restore_group_work(connection, changed, request(source))['attempt'] > source['sourceAttempt']


@pytest.mark.parametrize('fault,expected', [
    ('missing','frozen_work_missing'), ('action','frozen_work_corrupt'),
    ('result','frozen_work_corrupt'), ('candidates','frozen_work_corrupt'),
    ('targets','frozen_work_corrupt'),
])
def test_old_source_fault_preserves_metadata_and_explicitly_blocks_copy(tmp_path, fault, expected):
    path = tmp_path / 'corrupt.sqlite'
    _, _, record = prepare(path)
    changed = new_owner(record)
    with db(path) as connection:
        source = active_sources(connection, record['worldId'], record['work']['pointId'])[0]
        keys = (source['sourceEpoch'], source['sourceAttempt'])
        connection.execute('DROP TRIGGER frozen_work_immutable')
        connection.execute('DROP TRIGGER active_frozen_payload_retained')
        if fault == 'missing':
            connection.execute('DELETE FROM world_frozen_work WHERE epoch=? AND attempt=?', keys)
        else:
            column, value = {'action':('action_bytes',b'changed'), 'result':('result_bytes',b'changed'),
                'candidates':('candidates_json','{}'), 'targets':('targets_json','null')}[fault]
            connection.execute(f'UPDATE world_frozen_work SET {column}=? WHERE epoch=? AND attempt=?', (value,*keys))
        check_frozen_work(connection, changed)  # no old payload read
        hidden = context(connection, changed)
        assert hidden['restoreSources'] == [source] and hidden['groups'] == []
        with pytest.raises(FrozenWorkError) as refusal:
            restore_group_work(connection, changed, request(source))
        assert refusal.value.code == expected
        assert connection.execute('SELECT count(*) FROM world_copy_results').fetchone()[0] == 0
        assert context(connection, changed)['payloadStatus'] == 'restore_required'


def test_visibility_filters_current_epoch_before_considering_attempts(tmp_path):
    path = tmp_path / 'visibility.sqlite'
    _, _, record = prepare(path)
    changed = new_owner(record)
    with db(path) as connection:
        source = active_sources(connection, record['worldId'], record['work']['pointId'])[0]
        result = restore_group_work(connection, changed, request(source))
        accepted = connection.execute('SELECT * FROM world_accepted_work WHERE epoch=? AND attempt=?',
            (source['sourceEpoch'],source['sourceAttempt'])).fetchone()
        frozen = connection.execute('SELECT * FROM world_frozen_work WHERE epoch=? AND attempt=?',
            (source['sourceEpoch'],source['sourceAttempt'])).fetchone()
        # An unrelated old-epoch high attempt cannot supersede this owner's
        # accepted/copy-bound attempt, even though its numeric value is larger.
        old_high = (*accepted[:5], result['attempt'] + 100, *accepted[6:])
        connection.execute('INSERT INTO world_accepted_work VALUES(?,?,?,?,?,?,?,?)', old_high)
        connection.execute('INSERT INTO world_frozen_work VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (*frozen[:5], result['attempt'] + 100, b'UNACCEPTED VISIBLE PAYLOAD', *frozen[7:]))
        connection.execute('UPDATE world_leases SET epoch=?', (changed['lease']['fenceEpoch'],))
        visible = connection.execute('SELECT epoch,attempt,action_bytes FROM visible_frozen_work').fetchall()
        assert visible == [(changed['lease']['fenceEpoch'],result['attempt'],'原文\r\n走向讲台。'.encode())]
        assert context(connection,changed)['groups'][0]['members'][0]['actionText'] == '原文\r\n走向讲台。'


@pytest.mark.parametrize('change', ['member','hash','group','point'])
def test_copy_never_accepts_client_reconstructed_or_unreferenced_sources(tmp_path,change):
    path = tmp_path / 'untrusted-source.sqlite'
    _, _, record = prepare(path)
    with db(path) as connection:
        source = active_sources(connection,record['worldId'],record['work']['pointId'])[0]
        altered = copy.deepcopy(source)
        if change == 'member':
            altered['manifest'][0]['memberId'] = 'person_b'
        elif change == 'hash':
            altered['manifest'][0]['actionContentHash'] = '0' * 64
        elif change == 'group':
            altered['groupId'] = 'unreferenced_group'
        else:
            altered['pointId'] = record['rootPointId']
        with pytest.raises(FrozenWorkError) as refusal:
            restore_group_work(connection,new_owner(record),request(altered))
        assert refusal.value.code == 'frozen_work_missing'
        assert refusal.value.details['reason'] == 'source_not_active'
        assert connection.execute('SELECT count(*) FROM world_copy_results').fetchone()[0] == 0


def test_input_projection_metadata_tampering_is_detected_without_reading_old_bytes(tmp_path):
    path = tmp_path / 'input-binding.sqlite'
    _, _, record = prepare(path)
    with db(path) as connection:
        connection.execute('DROP TRIGGER accepted_work_immutable')
        connection.execute("UPDATE world_accepted_work SET input_projection_hash=?",('0' * 64,))
        with pytest.raises(FrozenWorkError) as refusal:
            check_frozen_work(connection,new_owner(record))
        assert refusal.value.code == 'frozen_work_corrupt'
        assert refusal.value.details['reason'] == 'input_projection_mismatch'


def test_active_references_survive_gc_and_terminal_sources_stop_being_restorable(tmp_path):
    path = tmp_path / 'retention.sqlite'
    service, flow, record = prepare(path)
    with db(path) as connection:
        source = active_sources(connection,record['worldId'],record['work']['pointId'])[0]
        assert all(count == 0 for count in collect_terminal_frozen(connection,record['worldId']).values())
        with pytest.raises(sqlite3.IntegrityError,match='active_frozen_payload_is_referenced'):
            connection.execute('DELETE FROM world_frozen_work')
    cancellation = _payload('cancel_for_gc',flow['world_id'],flow['lease'],operation='cancel',
        advanceId=flow.get('advance_id','advance_1'),roundId=flow.get('round_id','round_1'),expectedPointId=flow['root_id'],expectedVersion=0,
        expectedCheckpointRevision=flow['revision'],cancelReason='结束验收')
    service.execute('round_conclusion_cancel',cancellation)
    with db(path) as connection:
        with pytest.raises(FrozenWorkError) as refusal:
            restore_group_work(connection,new_owner(record),request(source))
        assert refusal.value.code == 'frozen_work_missing'
        assert refusal.value.details['reason'] == 'source_not_active'
        counts = collect_terminal_frozen(connection,record['worldId'])
        assert counts['world_frozen_work'] >= 1 and counts['world_accepted_work'] >= 1
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []


def test_pure_time_scan_recovers_after_owner_change_without_model_reconstruction(tmp_path):
    path = tmp_path / 'scan.sqlite'
    service = reopen(path)
    flow = begin_work(service)
    scan = single_group([],ORDER,None)
    service.execute('checkpoint_stage_time_scan',_payload('scan',flow['world_id'],flow['lease'],
        operation='stage_time_scan',expectedPointId=flow['root_id'],expectedVersion=0,
        expectedCheckpointRevision=flow['revision'],pointId=flow['point_id'],candidates=scan))
    record = reopen(path).store.world(flow['world_id'])
    with db(path) as connection:
        initialize_frozen_schema(connection)
        recovered = context(connection,new_owner(record))
        assert recovered['payloadStatus'] == 'available' and recovered['groups'] == []
        assert recovered['restoreSources'] == []
        assert recovered['work']['timeScanComplete']
        assert recovered['timeScanCandidates'] == scan.model_dump(mode='json')


def test_discover_nonempty_target_ids_allocate_once_and_recover_full_specs(tmp_path):
    path = tmp_path / 'discovery-targets.sqlite'
    service = reopen(path)
    flow = begin_work(service)
    service.execute('checkpoint_discover_group',_payload('discover_targets',flow['world_id'],flow['lease'],
        operation='discover_group',expectedPointId=flow['root_id'],expectedVersion=0,
        expectedCheckpointRevision=flow['revision'],pointId=flow['point_id'],groupId=flow['group_id'],
        initiatorId='person_a',actionText='向 B 招手。',targetIds=['person_b']))
    with service.store.locked():
        connection = service.store._local.connection
        initialize_frozen_schema(connection)
        record = service.store.world(flow['world_id'])
        save_frozen_work(connection,None,record)
        group = context(connection,record)['groups'][0]
        targets = group['members'][0]['targets']
        assert len(targets) == 1 and targets[0]['targetId'] == 'person_b'
        assert targets[0]['triggerKey'].startswith('trigger_')
        before_sequence = connection.execute('SELECT sequence FROM world_snapshot_meta').fetchone()[0]
        check_frozen_work(connection,record)
        assert confirmed_targets(connection,record['worldId'],record['work']['pointId'],
            record['work']['pendingGroup'],'person_a') == targets
        assert connection.execute('SELECT sequence FROM world_snapshot_meta').fetchone()[0] == before_sequence
        assert targets[0]['triggerKey'] in [entry['id'] for entry in record['_allocationMetadata']['_auto_targets'].values()]
        save_frozen_work(connection,None,record)
        assert connection.execute('SELECT count(*) FROM world_frozen_target_specs').fetchone()[0] == 1
