"""Real SQLite sealed-prefix reservations, recovery and atomic promotion."""
import copy
import json
import sqlite3

import pytest

from app.database.world_repository import LedgerMismatch
from app.database.world_store import _load
from app.services.world.control import ServiceRefusal
from tests.test_world_control_service import ORDER,_claim_and_submit,_payload,single_group
from tests.test_world_sqlite_store import reopen as _reopen
from tests.test_world_work_store import staged

INSTANT = {'boundary':'instant','duration':{'amount':0,'unit':'second'}}


def clock():
    # These tests bind saved business work, not elapsed wall time. Authority
    # expiry and takeover have separate explicitly advanced-clock probes.
    return 1_792_617_600_000


def reopen(path):
    return _reopen(path,clock=clock)


def checkpoint(service,flow,operation,request_id,point_id=None,**fields):
    current = service.execute('get_context',{'worldId':flow['world_id']})
    return service.execute('checkpoint_'+operation,_payload(request_id,flow['world_id'],flow['lease'],
        operation=operation,expectedPointId=current['world']['head']['pointId'],
        expectedVersion=current['world']['head']['version'],
        expectedCheckpointRevision=current['control']['revision'],
        pointId=point_id or flow['point_id'],**fields))


def prepare_successor(path,*,unit='second'):
    service,flow,_ = staged(path,clock=clock)
    allocated = service.execute('allocate_ids',_payload('allocate_successor',flow['world_id'],flow['lease'],
        allocationKey='successor',slots=[{'slotKey':'point','kind':'point','scope':None},
            {'slotKey':'group','kind':'group','scope':flow.get('round_id','round_1')}]))
    identities = {item['slotKey']:item['id'] for item in allocated['data']['allocations']}
    flow.update(successor_point_id=identities['point'],successor_group_id=identities['group'])
    record = service.store.world(flow['world_id'])
    candidates = [unit['candidates'].model_dump(mode='json') for unit in record['work']['units']]
    preview = service.execute('preview_point',dict(protocolVersion=2,worldId=flow['world_id'],
        advanceId=record['advance']['advanceId'],roundId=record['round']['roundId'],pointId=flow['point_id'],
        expectedPointId=flow['root_id'],expectedVersion=0,
        expectedCheckpointRevision=record['control']['revision'],
        timeAdvance=record['work']['timeAdvance'],settlementGroups=candidates))
    time = dict(boundary='instant',duration=dict(amount=0,unit=unit))
    prepared = checkpoint(service,flow,'prepare_successor','prepare_successor',
        successorPointId=identities['point'],timeAdvance=time)
    return service,flow,preview,prepared


@pytest.mark.parametrize('unit',['second','minute','hour','day','month','year'])
def test_reserved_zero_time_preserves_each_legal_unit_through_reopen_and_promotion(tmp_path,unit):
    path=tmp_path/f'zero-{unit}.sqlite'
    service,flow,preview,prepared=prepare_successor(path,unit=unit)
    expected=dict(boundary='instant',duration=dict(amount=0,unit=unit))
    assert prepared['data']['successor']['timeAdvance']==expected
    service=reopen(path)
    before=service.store.world(flow['world_id'])
    assert before['work']['successor']['timeAdvance']==expected
    assert before['_successorWork']['timeAdvance']==expected
    commit_predecessor(service,flow,preview)
    after=reopen(path).store.world(flow['world_id'])
    assert after['work']['pointId']==flow['successor_point_id']
    assert after['work']['timeAdvance']==expected


def boundary_group(service,flow):
    checkpoint(service,flow,'discover_group','successor_discover',point_id=flow['successor_point_id'],
        groupId=flow['successor_group_id'],initiatorId='person_b',
        actionText='预约的行动原文\r\n向 C 招手。',targetIds=None)
    checkpoint(service,flow,'extend_group','successor_targets',point_id=flow['successor_point_id'],
        groupId=flow['successor_group_id'],sourceId='person_b',targets=[],admittedMember=None)


def commit_predecessor(service,flow,preview,request_id='commit_predecessor'):
    context = service.execute('get_context',{'worldId':flow['world_id']})
    record = service.store.world(flow['world_id'])
    request = _payload(request_id,flow['world_id'],flow['lease'],
        advanceId=record['advance']['advanceId'],roundId=record['round']['roundId'],
        pointId=flow['point_id'],expectedPointId=flow['root_id'],expectedVersion=0,
        expectedCheckpointRevision=context['control']['revision'],point=preview['data']['pointProjection'],
        settlementGroups=[unit['candidates'].model_dump(mode='json') for unit in record['work']['units']])
    return service.execute('commit_point',request),request


def test_reservation_is_independent_sql_work_and_binds_predicted_predecessor_state(tmp_path):
    path = tmp_path/'reservation.sqlite'
    service,flow,preview,prepared = prepare_successor(path)
    record = reopen(path).store.world(flow['world_id'])
    current,reserved = record['work'],record['_successorWork']
    summary = prepared['data']['successor']
    assert current['sealed'] and current['prefixDigest'] == summary['prefixDigest']
    assert record['version'] == 0 and record['headPointId'] == flow['root_id']
    assert summary['expectedPredecessorVersion'] == 1
    assert summary['expectedPredecessorStateDigest'] == preview['data']['workingStateDigest']
    assert reserved['baseline'] == dict(headPointId=flow['point_id'],version=1,
                                      stateDigest=preview['data']['workingStateDigest'])
    assert reserved['predecessorWorkDigest'] == current['prefixDigest']
    assert reserved['_predecessorPointId'] == current['pointId']
    assert reserved['working'].actedIds == ['person_a'] and reserved['working'].settledUnitIds == []
    assert reserved['timeLocked'] and reserved['timeAdvance'] == INSTANT
    with sqlite3.connect(path) as connection:
        rows = connection.execute('SELECT point_id,status,predecessor_point_id FROM world_point_work ORDER BY point_id').fetchall()
        assert {row[0] for row in rows} == {flow['point_id'],flow['successor_point_id']}
        assert all(row[1]=='active' for row in rows)
        snapshot = _load(connection.execute('SELECT record_json FROM world_snapshots').fetchone()[0])
        assert 'work' not in snapshot and '_successorWork' not in snapshot
        assert snapshot['_reservedWorkPointId'] == flow['successor_point_id']
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []


def test_boundary_group_persists_and_recovers_without_moving_current_point(tmp_path):
    path = tmp_path/'boundary.sqlite'
    service,flow,_,_ = prepare_successor(path)
    before = service.store.world(flow['world_id'])
    boundary_group(service,flow)
    record = reopen(path).store.world(flow['world_id'])
    assert record['work'] == before['work']
    assert record['state'] == before['state'] and record['version']==0
    assert record['control']['phase'] == 'select_actor'
    assert record['_successorWork']['phase'] == 'build_group'
    assert record['_successorWork']['pendingGroup']['actionTexts']['person_b'] == '预约的行动原文\r\n向 C 招手。'
    recovered = reopen(path).execute('get_context',_payload('unused',flow['world_id'],flow['lease'],includeRecovery=True))
    assert recovered['recovery']['current']['work']['pointId']==flow['point_id']
    successor = recovered['recovery']['successor']
    assert successor['work']['pointId']==flow['successor_point_id']
    assert successor['work']['predecessorWorkDigest']==before['work']['prefixDigest']
    assert successor['groups'][0]['members'][0]['actionText']=='预约的行动原文\r\n向 C 招手。'
    assert successor['groups'][0]['members'][0]['targets']==[]


@pytest.mark.parametrize('operation,fields',[
    ('close_group',{}),
    ('record_skip',{'slotActorId':'person_b'}),
    ('set_point_time',{'timeAdvance':INSTANT}),
    ('stage_time_scan',{'candidates':single_group([],ORDER,None).model_dump(mode='json')}),
    ('seal_point',{}),
])
def test_reservation_cannot_progress_beyond_boundary_work_before_predecessor_commit(tmp_path,operation,fields):
    path=tmp_path/'boundary-permission.sqlite'
    service,flow,_,_=prepare_successor(path)
    boundary_group(service,flow)
    before=service.store.world(flow['world_id'])
    if operation=='close_group':
        fields=dict(fields,groupId=flow['successor_group_id'])
    with pytest.raises(ServiceRefusal) as refusal:
        checkpoint(service,flow,operation,'forbidden_'+operation,
                   point_id=flow['successor_point_id'],**fields)
    assert refusal.value.code=='phase_invalid'
    assert reopen(path).store.world(flow['world_id'])==before


def test_consume_only_predecessor_groups_and_promote_saved_successor_atomically(tmp_path):
    path=tmp_path/'promote.sqlite'
    service,flow,preview,_=prepare_successor(path)
    boundary_group(service,flow)
    before=service.store.world(flow['world_id'])
    committed,request=commit_predecessor(service,flow,preview)
    assert committed['data']['version']==1
    after=reopen(path).store.world(flow['world_id'])
    assert after['headPointId']==flow['point_id'] and after['version']==1
    assert after['work']['pointId']==flow['successor_point_id']
    assert '_successorWork' not in after and '_predecessorPointId' not in after['work']
    assert after['work']['pendingGroup']==before['_successorWork']['pendingGroup']
    assert after['work']['baseline']==before['_successorWork']['baseline']
    assert after['control']['gate']['status']=='pending'
    assert not committed['control']['canCompute']
    replay=reopen(path).execute('commit_point',request)
    assert replay['replayed'] and replay['data']==committed['data']
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT status FROM world_groups WHERE id=?',(flow['group_id'],)).fetchone()==('consumed',)
        assert connection.execute('SELECT status FROM world_groups WHERE id=?',(flow['successor_group_id'],)).fetchone()==('open',)
        assert connection.execute('SELECT predecessor_point_id FROM world_point_work WHERE point_id=?',
            (flow['successor_point_id'],)).fetchone()==(None,)
        assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
    _claim_and_submit(service,flow['world_id'],flow['lease'],flow['point_id'],'ready_p1','前驱叙事就绪。')
    checkpoint(service,flow,'close_group','close_promoted',point_id=flow['successor_point_id'],
               groupId=flow['successor_group_id'])
    checkpoint(service,flow,'stage_unit','stage_promoted',point_id=flow['successor_point_id'],
        groupId=flow['successor_group_id'],candidates=single_group(['person_b'],ORDER,flow['successor_group_id']),
        results={'person_b':'预约行动已完成。'})
    final=reopen(path).store.world(flow['world_id'])
    assert final['work']['working'].actedIds==['person_a','person_b']


@pytest.mark.parametrize('table',['world_point_work','world_work_details','world_work_reservations'])
def test_prepare_sql_failure_rolls_back_seal_reservation_revision_and_replay(tmp_path,table):
    path=tmp_path/'prepare-fault.sqlite'
    service,flow,_=staged(path,clock=clock)
    allocation=service.execute('allocate_ids',_payload('allocate_fault',flow['world_id'],flow['lease'],
        allocationKey='fault',slots=[{'slotKey':'point','kind':'point','scope':None}]))
    point=allocation['data']['allocations'][0]['id']
    before=service.store.world(flow['world_id'])
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TRIGGER fault BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'prepare fault'); END")
    with pytest.raises(sqlite3.IntegrityError,match='prepare fault'):
        checkpoint(service,flow,'prepare_successor','prepare_fault',successorPointId=point,timeAdvance=INSTANT)
    assert reopen(path).store.world(flow['world_id'])==before
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM world_point_work').fetchone()==(1,)
        assert connection.execute("SELECT count(*) FROM world_submissions WHERE request_id='prepare_fault'").fetchone()==(0,)


def test_promotion_sql_failure_rolls_back_predecessor_state_and_preserves_reserved_group(tmp_path):
    path=tmp_path/'promotion-fault.sqlite'
    service,flow,preview,_=prepare_successor(path)
    boundary_group(service,flow)
    before=service.store.world(flow['world_id'])
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER fault BEFORE UPDATE ON world_point_work WHEN NEW.status='consumed' BEGIN SELECT RAISE(ABORT,'promotion fault'); END")
    with pytest.raises(sqlite3.IntegrityError,match='promotion fault'):
        commit_predecessor(service,flow,preview)
    assert reopen(path).store.world(flow['world_id'])==before
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM world_points WHERE kind<>'root'").fetchone()==(0,)
        assert connection.execute("SELECT count(*) FROM world_submissions WHERE request_id='commit_predecessor'").fetchone()==(0,)
        assert connection.execute("SELECT count(*) FROM world_point_work WHERE status='active'").fetchone()==(2,)


@pytest.mark.parametrize('fault',['prefix','version','state','time','predecessor'])
def test_successor_prefix_binding_corruption_cannot_promote_or_commit(tmp_path,fault):
    path=tmp_path/'binding.sqlite'
    service,flow,_,_=prepare_successor(path)
    with sqlite3.connect(path) as connection:
        raw=connection.execute('SELECT successor_json FROM world_work_details WHERE point_id=?',
                               (flow['point_id'],)).fetchone()[0]
        summary=json.loads(raw)
        if fault=='prefix':summary['prefixDigest']='0'*64
        elif fault=='version':summary['expectedPredecessorVersion']+=1
        elif fault=='state':summary['expectedPredecessorStateDigest']='0'*64
        elif fault=='time':summary['timeAdvance']={'boundary':'instant','duration':{'amount':1,'unit':'second'}}
        else:summary['predecessorPointId']=flow['root_id']
        connection.execute('UPDATE world_work_details SET successor_json=? WHERE point_id=?',
                           (json.dumps(summary),flow['point_id']))
    with pytest.raises((LedgerMismatch,ValueError)):
        reopen(path).store.world(flow['world_id'])
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM world_points WHERE kind<>'root'").fetchone()==(0,)
        assert connection.execute("SELECT count(*) FROM world_point_work WHERE status='active'").fetchone()==(2,)


def test_cancel_abandons_current_and_reserved_groups_without_consuming_either(tmp_path):
    path=tmp_path/'cancel-reserved.sqlite'
    service,flow,_,_=prepare_successor(path)
    boundary_group(service,flow)
    before=service.store.world(flow['world_id'])
    result=service.execute('round_conclusion_cancel',_payload('cancel_both',flow['world_id'],flow['lease'],
        operation='cancel',advanceId=before['advance']['advanceId'],roundId=before['round']['roundId'],
        expectedPointId=flow['root_id'],expectedVersion=0,
        expectedCheckpointRevision=before['control']['revision'],cancelReason='取消预约'))
    assert result['data']['abandonedGroupIds']==[flow['successor_group_id']]
    after=reopen(path).store.world(flow['world_id'])
    assert after['work'] is None and '_successorWork' not in after
    assert after['state']==before['state'] and after['version']==0
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM world_point_work WHERE status='abandoned'").fetchone()==(2,)
        assert connection.execute("SELECT count(*) FROM world_groups WHERE status='abandoned'").fetchone()==(2,)


def test_reserved_preview_uses_future_baseline_once_and_preserves_current_world(tmp_path):
    from app.schemas.world.canonical import canonical_digest
    service, flow, _, _ = prepare_successor(tmp_path / 'reserved-preview.sqlite')
    before = service.store.world(flow['world_id'])
    request = dict(protocolVersion=2, worldId=flow['world_id'],
        advanceId=flow['advance_id'], roundId=flow['round_id'], pointId=flow['successor_point_id'],
        expectedPointId=flow['root_id'], expectedVersion=0,
        expectedCheckpointRevision=before['control']['revision'], timeAdvance=INSTANT, settlementGroups=[])
    preview = service.execute('preview_point', request)
    expected = before['state'].model_dump(mode='json')
    expected['time'].update(dateTime='2026-01-01T11:59:02', instantOrdinal=1)
    assert preview['data']['workingState'] == expected
    assert preview['data']['workingStateDigest'] == canonical_digest(expected)
    assert preview['data']['pointProjection']['sequence'] == 2
    assert preview['data']['pointProjection']['previousPointId'] == flow['point_id']
    assert preview['world']['head']['pointId'] == flow['root_id']
    assert service.store.world(flow['world_id']) == before


def test_reserved_member_reaction_is_refused_before_predecessor_commit(tmp_path):
    service, flow, _, _ = prepare_successor(tmp_path / 'reserved-reaction.sqlite')
    boundary_group(service, flow)
    before = service.store.world(flow['world_id'])
    with pytest.raises(ServiceRefusal) as error:
        checkpoint(service, flow, 'extend_group', 'forbidden_reserved_reaction',
            point_id=flow['successor_point_id'], groupId=flow['successor_group_id'], sourceId='person_b',
            targets=None, admittedMember={'memberId': 'person_c', 'actionText': '前驱提交前不得生成反应。',
                'rollRefs': [{'sourceId': 'person_b', 'targetId': 'person_c',
                              'triggerKey': 'unaccepted_trigger', 'rollId': 'unaccepted_roll'}]})
    assert error.value.code == 'phase_invalid'
    assert service.store.world(flow['world_id']) == before
