"""Independent SQL acceptance of server-owned rolls, IDs and admission.

Expected dice/eligibility are fixed by the tests; no browser or production
admission function computes the expected answers. Failures use real SQLite
transactions and reopen the store to check absence of partial changes.
"""
import copy
import sqlite3

import pytest

from app.database.world_judgment_repository import (
    LedgerMismatch, check_judgments, initialize_judgment_schema, save_allocations,
    validate_admission, validate_group_closure,
)
from app.database.world_store import SQLiteBaselineStore
from app.schemas.world.v2.requests import (
    AllocateIdsRequest, CloseGroupRequest, CreateRollsRequest, ExtendGroupRequest,
)
from app.services.world.control import ServiceRefusal, WorldService
from app.services.world.judgments import allocate_ids, create_rolls
from tests.test_world_control_service import (
    ORDER, TIME_ADVANCE, _claim_and_submit, _payload, initial_template, single_group,
)


def fixture(tmp_path, *, targets=True, result=15, prestage_target=False):
    path = tmp_path / 'judgments.sqlite3'
    store = SQLiteBaselineStore(path)
    with store.locked():
        initialize_judgment_schema(store._local.connection)
    service = WorldService(store)
    initial = initial_template()
    if prestage_target:
        initial['characters']['person_b']['initialSanity'] = 5
    created = service.execute('create_world', {
        'protocolVersion': 2, 'requestId': 'create_judgments', 'initial': initial})
    world, head, lease = (created['data']['worldId'], created['data']['rootPointId'], created['data']['lease'])
    _claim_and_submit(service, world, lease, head, 'root_judgments', '准备判断反应。')
    slots = [{'slotKey': kind, 'kind': kind, 'scope': None}
             for kind in ('advance', 'input', 'round', 'point', 'group', 'trigger')]
    if prestage_target:
        slots.append({'slotKey': 'prior_group', 'kind': 'group', 'scope': None})
    allocation = AllocateIdsRequest.model_validate(_payload(
        'allocate_judgments', world, lease, allocationKey='judgment_slots', slots=[
            *slots]))

    def install_allocations(record):
        before = copy.deepcopy(record)
        answer = allocate_ids(store, record, allocation)
        save_allocations(store._local.connection, before, record)
        return answer

    allocated = store.transact(world, install_allocations)
    ids = {item['slotKey']: item['id'] for item in allocated['allocations']}
    service.execute('checkpoint_start_advance', _payload(
        'start_judgments', world, lease, operation='start_advance', expectedPointId=head,
        expectedVersion=0, expectedCheckpointRevision=0,
        advanceId=ids['advance'], inputId=ids['input'], roundId=ids['round'],
        inputText='向 B 招手。', order=['person_b', 'person_a', *ORDER[2:]] if prestage_target else ORDER))
    service.execute('checkpoint_begin_point', _payload(
        'begin_judgments', world, lease, operation='begin_point', expectedPointId=head,
        expectedVersion=0, expectedCheckpointRevision=1,
        pointId=ids['point'], kind='normal', timeAdvance=TIME_ADVANCE))
    revision = 2
    if prestage_target:
        for operation, extra in [
            ('discover_group', {'initiatorId': 'person_b', 'actionText': 'B 先行动。', 'targetIds': None}),
            ('extend_group', {'sourceId': 'person_b', 'targets': [], 'admittedMember': None}),
            ('close_group', {}),
            ('stage_unit', {'candidates': single_group(['person_b'], ORDER, ids['prior_group']),
                            'results': {'person_b': 'B 已行动。'}}),
        ]:
            service.execute('checkpoint_' + operation, _payload(
                'prior_' + operation, world, lease, operation=operation, expectedPointId=head,
                expectedVersion=0, expectedCheckpointRevision=revision, pointId=ids['point'],
                groupId=ids['prior_group'], **extra))
            revision += 1
    service.execute('checkpoint_discover_group', _payload(
        'discover_judgments', world, lease, operation='discover_group', expectedPointId=head,
        expectedVersion=0, expectedCheckpointRevision=revision, pointId=ids['point'],
        groupId=ids['group'], initiatorId='person_a', actionText='向 B 招手。', targetIds=None))
    revision += 1
    if targets:
        service.execute('checkpoint_extend_group', _payload(
            'targets_judgments', world, lease, operation='extend_group', expectedPointId=head,
            expectedVersion=0, expectedCheckpointRevision=revision, pointId=ids['point'],
            groupId=ids['group'], sourceId='person_a',
            targets=[{'targetId': 'person_b', 'triggerKey': ids['trigger']}], admittedMember=None))
        revision += 1
    calls = []

    def rng():
        calls.append(True)
        return result

    store._roll_rng = rng
    request = _payload(
        'roll_judgments', world, lease, expectedPointId=head, expectedVersion=0,
        expectedCheckpointRevision=revision, rolls=[{
            'advanceId': ids['advance'], 'roundId': ids['round'], 'groupId': ids['group'],
            'sourceId': 'person_a', 'targetId': 'person_b', 'triggerKey': ids['trigger'],
            'ruleVersion': 'reaction-d20-v1', 'target': 11,
        }])
    return dict(path=path, store=store, service=service, world=world, head=head, lease=lease,
                ids=ids, revision=revision, request=request, calls=calls)


def roll(flow, request=None):
    parsed = CreateRollsRequest.model_validate(request or flow['request'])
    return flow['store'].transact(flow['world'], lambda record:
        create_rolls(flow['store'], record, parsed))


def admission(flow, outcome, **changes):
    reference = {key: outcome[key] for key in ('sourceId', 'targetId', 'triggerKey', 'rollId')}
    payload = _payload('admit_judgments', flow['world'], flow['lease'],
        operation='extend_group', expectedPointId=flow['head'], expectedVersion=0,
        expectedCheckpointRevision=flow['revision'], pointId=flow['ids']['point'],
        groupId=flow['ids']['group'], sourceId='person_a', targets=None,
        admittedMember={'memberId': 'person_b', 'actionText': 'B 回应。', 'rollRefs': [reference]})
    payload.update(changes)
    return ExtendGroupRequest.model_validate(payload)


def test_final_roll_is_one_insert_and_business_retry_never_resamples(tmp_path):
    flow = fixture(tmp_path)
    before = flow['store'].world(flow['world'])
    first = roll(flow)['rolls'][0]
    retry = copy.deepcopy(flow['request'])
    retry['requestId'] = 'another_request_same_judgment'
    assert roll(flow, retry)['rolls'][0] == first
    assert first['result'] == 15 and first['target'] == 11
    assert first['eligible'] is True and first['admitted'] is True
    assert len(flow['calls']) == 1
    reopened = SQLiteBaselineStore(flow['path']).world(flow['world'])
    assert reopened['control']['revision'] == before['control']['revision']
    assert reopened['work'] == before['work']
    with sqlite3.connect(flow['path']) as db:
        assert db.execute('SELECT result,eligible,admitted FROM world_rolls').fetchall() == [(15, 1, 1)]
        assert db.execute('SELECT count(*) FROM world_roll_baselines').fetchone() == (1,)
        check_judgments(db, reopened)
        with pytest.raises(sqlite3.IntegrityError, match='roll_is_final'):
            db.execute('UPDATE world_rolls SET result=20')


def test_public_roll_business_replay_and_authorized_expansion_survive_reopen(tmp_path):
    flow = fixture(tmp_path)
    service = flow['service']
    first = service.execute('create_rolls', flow['request'])
    replay = service.execute('create_rolls', flow['request'])
    assert replay['replayed'] and replay['data'] == first['data']
    new_request = dict(flow['request'], requestId='same_business_new_request')
    same = service.execute('create_rolls', new_request)
    assert not same['replayed'] and same['data'] == first['data']
    assert len(flow['calls']) == 1
    outcome = first['data']['rolls'][0]
    reopened = WorldService(SQLiteBaselineStore(flow['path']))
    added = reopened.execute('checkpoint_extend_group', admission(flow, outcome).model_dump(mode='json'))
    assert added['data']['memberIds'] == ['person_a', 'person_b']
    targets_b = _payload('b_confirmed_empty', flow['world'], flow['lease'], operation='extend_group',
        expectedPointId=flow['head'], expectedVersion=0,
        expectedCheckpointRevision=added['control']['revision'], pointId=flow['ids']['point'],
        groupId=flow['ids']['group'], sourceId='person_b', targets=[], admittedMember=None)
    confirmed = reopened.execute('checkpoint_extend_group', targets_b)
    closed = reopened.execute('checkpoint_close_group', _payload(
        'all_judgments_closed', flow['world'], flow['lease'], operation='close_group',
        expectedPointId=flow['head'], expectedVersion=0,
        expectedCheckpointRevision=confirmed['control']['revision'], pointId=flow['ids']['point'],
        groupId=flow['ids']['group']))
    assert closed['data']['closed'] and closed['control']['phase'] == 'settle_group'


def test_group_cycle_uses_fixed_eligibility_and_does_not_readmit_existing_member(tmp_path):
    flow = fixture(tmp_path, result=20)
    first = flow['service'].execute('create_rolls', flow['request'])['data']['rolls'][0]
    added = flow['service'].execute('checkpoint_extend_group', admission(flow, first).model_dump(mode='json'))
    trigger = flow['service'].execute('allocate_ids', _payload(
        'allocate_cycle', flow['world'], flow['lease'], allocationKey='cycle',
        slots=[{'slotKey': 'b_to_a', 'kind': 'trigger', 'scope': flow['ids']['group']}]))['data']['allocations'][0]['id']
    confirmed = flow['service'].execute('checkpoint_extend_group', _payload(
        'cycle_targets', flow['world'], flow['lease'], operation='extend_group',
        expectedPointId=flow['head'], expectedVersion=0,
        expectedCheckpointRevision=added['control']['revision'], pointId=flow['ids']['point'],
        groupId=flow['ids']['group'], sourceId='person_b',
        targets=[{'targetId': 'person_a', 'triggerKey': trigger}], admittedMember=None))
    request = copy.deepcopy(flow['request'])
    request.update(requestId='cycle_roll', expectedCheckpointRevision=confirmed['control']['revision'])
    request['rolls'][0].update(sourceId='person_b', targetId='person_a', triggerKey=trigger)
    cycle = flow['service'].execute('create_rolls', request)['data']['rolls'][0]
    assert cycle['eligible'] and cycle['admitted']
    assert flow['store'].world(flow['world'])['work']['pendingGroup']['memberIds'] == ['person_a', 'person_b']
    flow['service'].execute('checkpoint_close_group', _payload(
        'cycle_closed', flow['world'], flow['lease'], operation='close_group',
        expectedPointId=flow['head'], expectedVersion=0,
        expectedCheckpointRevision=confirmed['control']['revision'], pointId=flow['ids']['point'],
        groupId=flow['ids']['group']))
    with sqlite3.connect(flow['path']) as db:
        assert db.execute('SELECT count(*) FROM world_rolls').fetchone() == (2,)


@pytest.mark.parametrize('result,eligible,admitted', [(1, True, False), (11, True, True), (20, True, True)])
def test_d20_threshold_and_tie_are_server_owned(tmp_path, result, eligible, admitted):
    flow = fixture(tmp_path, result=result)
    outcome = roll(flow)['rolls'][0]
    assert (outcome['result'], outcome['eligible'], outcome['admitted']) == (result, eligible, admitted)


def test_working_acted_members_are_ineligible_even_if_committed_round_has_not_advanced(tmp_path):
    flow = fixture(tmp_path, result=20, prestage_target=True)
    record = flow['store'].world(flow['world'])
    assert record['round']['actedIds'] == []
    assert record['work']['working'].actedIds == ['person_b']
    outcome = roll(flow)['rolls'][0]
    assert outcome['result'] == 20
    assert outcome['eligible'] is False and outcome['admitted'] is False


def test_unconfirmed_targets_cannot_roll_or_consume_randomness(tmp_path):
    flow = fixture(tmp_path, targets=False)
    before = flow['store'].world(flow['world'])
    with pytest.raises(ServiceRefusal, match='request_malformed'):
        roll(flow)
    assert flow['calls'] == []
    assert flow['store'].world(flow['world']) == before


@pytest.mark.parametrize('change', [
    {'targetId': 'person_c'}, {'sourceId': 'person_c'}, {'groupId': 'unknown_group'},
    {'triggerKey': 'browser_invented_trigger'},
])
def test_unconfirmed_or_forged_judgment_identity_is_rejected(tmp_path, change):
    flow = fixture(tmp_path)
    request = copy.deepcopy(flow['request'])
    request['rolls'][0].update(change)
    with pytest.raises(ServiceRefusal):
        roll(flow, request)
    assert flow['calls'] == []
    with sqlite3.connect(flow['path']) as db:
        assert db.execute('SELECT count(*) FROM world_rolls').fetchone() == (0,)


def test_invalid_later_roll_in_batch_discards_earlier_insert(tmp_path):
    flow = fixture(tmp_path)
    before = flow['store'].world(flow['world'])
    request = copy.deepcopy(flow['request'])
    extra = dict(request['rolls'][0], targetId='person_c')
    request['rolls'].append(extra)
    with pytest.raises(ServiceRefusal, match='confirmed complete target'):
        roll(flow, request)
    assert flow['store'].world(flow['world']) == before
    with sqlite3.connect(flow['path']) as db:
        assert db.execute('SELECT count(*) FROM world_rolls').fetchone() == (0,)
        assert db.execute('SELECT count(*) FROM world_roll_baselines').fetchone() == (0,)


def test_fixed_business_judgment_cannot_change_rule_or_threshold(tmp_path):
    flow = fixture(tmp_path)
    original = roll(flow)
    changed = copy.deepcopy(flow['request'])
    changed['requestId'] = 'changed_rule'
    changed['rolls'][0].update(ruleVersion='reaction-fixture-v1', target=1)
    with pytest.raises(ServiceRefusal, match='fixed judgment'):
        roll(flow, changed)
    assert roll(flow) == original and len(flow['calls']) == 1


def test_fixture_rule_requires_private_server_configuration(tmp_path):
    flow = fixture(tmp_path)
    request = copy.deepcopy(flow['request'])
    request['rolls'][0].update(ruleVersion='reaction-fixture-v1', target=17)
    with pytest.raises(ServiceRefusal, match='fixture rule'):
        roll(flow, request)
    spec = request['rolls'][0]
    key = (flow['world'], spec['roundId'], spec['groupId'], spec['sourceId'], spec['targetId'], spec['triggerKey'])
    flow['store']._roll_fixtures = {key: {'target': 17, 'result': 18}}
    outcome = roll(flow, request)['rolls'][0]
    assert outcome['result'] == 18 and outcome['target'] == 17 and outcome['admitted']
    assert flow['calls'] == []


@pytest.mark.parametrize('failure', ['baseline', 'snapshot'])
def test_judgment_sql_failure_rolls_back_roll_baseline_identity_and_snapshot(tmp_path, failure):
    flow = fixture(tmp_path)
    before = flow['store'].world(flow['world'])
    with sqlite3.connect(flow['path']) as db:
        if failure == 'baseline':
            db.execute("CREATE TRIGGER fail_judgment BEFORE INSERT ON world_roll_baselines BEGIN SELECT RAISE(ABORT,'test failure'); END")
        else:
            db.execute("CREATE TRIGGER fail_judgment BEFORE UPDATE ON world_snapshots BEGIN SELECT RAISE(ABORT,'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='test failure'):
        roll(flow)
    assert SQLiteBaselineStore(flow['path']).world(flow['world']) == before
    with sqlite3.connect(flow['path']) as db:
        assert db.execute('SELECT count(*) FROM world_rolls').fetchone() == (0,)
        assert db.execute('SELECT count(*) FROM world_roll_baselines').fetchone() == (0,)


def test_admission_uses_server_row_and_rejects_browser_invented_success(tmp_path):
    flow = fixture(tmp_path)
    outcome = roll(flow)['rolls'][0]
    with flow['store'].locked():
        connection = flow['store']._local.connection
        record = flow['store'].world(flow['world'])
        validate_admission(connection, record, admission(flow, outcome))
        forged = copy.deepcopy(outcome)
        forged['rollId'] = 'roll_browser_invented'
        with pytest.raises(ServiceRefusal, match='does not exist'):
            validate_admission(connection, record, admission(flow, forged))
        forged = copy.deepcopy(outcome)
        forged['triggerKey'] = 'different_trigger'
        with pytest.raises(ServiceRefusal, match='does not authorize'):
            validate_admission(connection, record, admission(flow, forged))


def test_failed_roll_cannot_authorize_membership(tmp_path):
    flow = fixture(tmp_path, result=10)
    outcome = roll(flow)['rolls'][0]
    with flow['store'].locked(), pytest.raises(ServiceRefusal, match='does not authorize'):
        validate_admission(flow['store']._local.connection,
                           flow['store'].world(flow['world']), admission(flow, outcome))


def test_close_requires_all_judgments_and_successful_membership(tmp_path):
    flow = fixture(tmp_path)
    close = CloseGroupRequest.model_validate(_payload(
        'close_judgments', flow['world'], flow['lease'], operation='close_group',
        expectedPointId=flow['head'], expectedVersion=0, expectedCheckpointRevision=flow['revision'],
        pointId=flow['ids']['point'], groupId=flow['ids']['group']))
    with flow['store'].locked(), pytest.raises(ServiceRefusal, match='every confirmed relation'):
        validate_group_closure(flow['store']._local.connection,
                               flow['store'].world(flow['world']), close)
    roll(flow)
    with flow['store'].locked(), pytest.raises(ServiceRefusal, match='admitted member'):
        validate_group_closure(flow['store']._local.connection,
                               flow['store'].world(flow['world']), close)


def test_allocation_replays_same_slot_and_rejects_changed_kind_or_scope(tmp_path):
    flow = fixture(tmp_path)
    record = flow['store'].world(flow['world'])
    original = record['_allocationMetadata']['judgment_slots']['trigger']['id']
    for kind, scope, succeeds in [('trigger', None, True), ('point', None, False), ('trigger', 'other_group', False)]:
        request = AllocateIdsRequest.model_validate(_payload('retry_allocation', flow['world'], flow['lease'],
            allocationKey='judgment_slots', slots=[{'slotKey': 'trigger', 'kind': kind, 'scope': scope}]))

        def execute(record):
            before = copy.deepcopy(record)
            result = allocate_ids(flow['store'], record, request)
            save_allocations(flow['store']._local.connection, before, record)
            return result

        if succeeds:
            assert flow['store'].transact(flow['world'], execute)['allocations'][0]['id'] == original
        else:
            before = flow['store'].world(flow['world'])
            with pytest.raises(ServiceRefusal, match='immutable'):
                flow['store'].transact(flow['world'], execute)
            assert flow['store'].world(flow['world']) == before


def test_public_allocation_rejects_old_credentials_before_reserving_any_slot(tmp_path):
    flow = fixture(tmp_path)
    before = flow['store'].world(flow['world'])
    forged = dict(flow['lease'], leaseToken='lease_not_issued_by_server')
    with pytest.raises(ServiceRefusal, match='lease_invalid'):
        flow['service'].execute('allocate_ids', _payload(
            'invalid_authority_alloc', flow['world'], forged,
            allocationKey='must_not_exist', slots=[{'slotKey': 'point', 'kind': 'point', 'scope': None}]))
    assert flow['store'].world(flow['world']) == before


def test_allocation_sql_failure_rolls_back_identity_counter_slot_and_success_record(tmp_path):
    flow = fixture(tmp_path)
    before = flow['store'].world(flow['world'])
    with sqlite3.connect(flow['path']) as db:
        sequence = db.execute('SELECT sequence FROM world_snapshot_meta').fetchone()
        db.execute("CREATE TRIGGER fail_id_slot BEFORE INSERT ON world_id_allocations BEGIN SELECT RAISE(ABORT,'id slot failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='id slot failure'):
        flow['service'].execute('allocate_ids', _payload(
            'failed_new_slot', flow['world'], flow['lease'], allocationKey='new_slot',
            slots=[{'slotKey': 'change', 'kind': 'change', 'scope': None}]))
    assert flow['store'].world(flow['world']) == before
    with sqlite3.connect(flow['path']) as db:
        assert db.execute('SELECT sequence FROM world_snapshot_meta').fetchone() == sequence
        assert db.execute("SELECT count(*) FROM world_id_allocations WHERE allocation_key='new_slot'").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM world_submissions WHERE request_id='failed_new_slot'").fetchone() == (0,)


@pytest.mark.parametrize('table', ['world_rolls', 'world_roll_baselines', 'world_id_allocations'])
def test_missing_judgment_or_allocation_ledger_fails_closed(tmp_path, table):
    flow = fixture(tmp_path)
    roll(flow)
    record = flow['store'].world(flow['world'])
    # External corruption probe disables referential checks deliberately.
    with sqlite3.connect(flow['path']) as db:
        db.execute(f'DELETE FROM {table}')
        with pytest.raises(LedgerMismatch):
            check_judgments(db, record)


def test_tampered_final_result_fails_closed_even_when_it_still_passes_the_threshold(tmp_path):
    flow = fixture(tmp_path)
    roll(flow)
    record = flow['store'].world(flow['world'])
    with sqlite3.connect(flow['path']) as db:
        db.execute('DROP TRIGGER roll_immutable')
        db.execute('UPDATE world_rolls SET result=19')
        with pytest.raises(LedgerMismatch, match='outcome hashes'):
            check_judgments(db, record)


def test_admitted_member_without_action_survives_takeover_and_can_confirm_once(tmp_path):
    scenario = fixture(tmp_path, result=20)
    service, world, lease = scenario['service'], scenario['world'], scenario['lease']
    outcome = service.execute('create_rolls', scenario['request'])['data']['rolls'][0]
    incoming = admission(scenario, outcome).model_dump(mode='json')
    incoming['admittedMember']['actionText'] = None
    accepted = service.execute('checkpoint_extend_group', incoming)
    revision = accepted['control']['revision']
    raw = service.store.world(world)['work']['pendingGroup']
    assert raw['actionTexts']['person_b'] is None and raw['frontierIds'] == ['person_b']
    service.execute('lease_release', _payload('pending_release', world, lease))
    lease = service.execute('lease_acquire', {'protocolVersion': 2, 'requestId': 'pending_acquire',
        'worldId': world, 'holderId': 'new_tab'})['data']
    query = {'worldId': world, 'includeRecovery': True,
             'leaseToken': lease['leaseToken'], 'fenceEpoch': lease['fenceEpoch']}
    hidden = service.execute('get_context', query)['recovery']['current']
    assert hidden['payloadStatus'] == 'restore_required'
    for index, source in enumerate(hidden['restoreSources']):
        service.execute('checkpoint_restore_group_work', _payload(
            f'pending_restore_{index}', world, lease, operation='restore_group_work',
            expectedPointId=scenario['head'], expectedVersion=0,
            expectedCheckpointRevision=revision, **source))
    recovered = service.execute('get_context', query)['recovery']['current']['groups'][0]
    members = {member['memberId']: member for member in recovered['members']}
    assert members['person_a']['actionText'] == '向 B 招手。'
    assert members['person_b']['actionText'] is None and members['person_b']['targets'] is None
    assert {source['memberId'] for source in recovered['acceptedSources']} == {'person_a'}
    confirmation = copy.deepcopy(incoming)
    confirmation.update(requestId='confirm_pending_action', leaseToken=lease['leaseToken'],
                        fenceEpoch=lease['fenceEpoch'], expectedCheckpointRevision=revision)
    confirmation['admittedMember']['actionText'] = 'B 的首次确认反应。\r\n'
    filled = service.execute('checkpoint_extend_group', confirmation)
    assert filled['control']['revision'] == revision + 1
    before = service.store.world(world)
    changed = copy.deepcopy(confirmation)
    changed.update(requestId='overwrite_pending_action', expectedCheckpointRevision=revision + 1)
    changed['admittedMember']['actionText'] = '改写已确认行动。'
    with pytest.raises(ServiceRefusal, match='already a group member'):
        service.execute('checkpoint_extend_group', changed)
    assert service.store.world(world) == before


def test_server_freezes_sanity_order_instead_of_trusting_request_order(tmp_path):
    service = WorldService(SQLiteBaselineStore(tmp_path / 'order.sqlite'))
    initial = initial_template()
    for actor, sanity in zip(ORDER, (60, 10, 10, 40, 50, 60)):
        initial['characters'][actor]['initialSanity'] = sanity
    created = service.execute('create_world', {
        'protocolVersion': 2, 'requestId': 'ordered_world', 'initial': initial})
    world, head, lease = created['data']['worldId'], created['data']['rootPointId'], created['data']['lease']
    _claim_and_submit(service, world, lease, head, 'ordered_ready', '开始。')
    allocation = service.execute('allocate_ids', _payload('ordered_alloc', world, lease,
        allocationKey='ordered_chain', slots=[{'slotKey': kind, 'kind': kind, 'scope': None}
            for kind in ('advance', 'input', 'round')]))
    ids = {item['slotKey']: item['id'] for item in allocation['data']['allocations']}
    answer = service.execute('checkpoint_start_advance', _payload('ordered_start', world, lease,
        operation='start_advance', expectedPointId=head, expectedVersion=0, expectedCheckpointRevision=0,
        advanceId=ids['advance'], inputId=ids['input'], roundId=ids['round'], inputText='开始行动。',
        order=list(reversed(ORDER))))
    assert answer['world']['round']['order'] == ['person_b', 'person_c', 'person_d', 'person_e', 'person_a', 'person_f']


def test_unallocated_group_is_refused_without_consuming_request_or_mutating_work(tmp_path):
    from tests.test_world_control_service import begin_work
    service = WorldService(SQLiteBaselineStore(tmp_path / 'identity.sqlite'))
    flow = begin_work(service)
    before = service.store.world(flow['world_id'])
    request = _payload('unallocated_group', flow['world_id'], flow['lease'], operation='discover_group',
        expectedPointId=flow['root_id'], expectedVersion=0, expectedCheckpointRevision=flow['revision'],
        pointId=flow['point_id'], groupId='client_generated_group', initiatorId='person_a',
        actionText='未经分配的组。', targetIds=[])
    with pytest.raises(ServiceRefusal, match='not allocated'):
        service.execute('checkpoint_discover_group', request)
    assert service.store.world(flow['world_id']) == before
