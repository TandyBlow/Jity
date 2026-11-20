"""IF-03 static SQLite constraints; no production transactions are exercised."""
import json
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2] / 'design/world-protocol/v2'
HASH = 'a' * 64


def insert(db, table, **values):
    keys = ','.join(values)
    db.execute(f'INSERT INTO {table} ({keys}) VALUES ({",".join("?" for _ in values)})', tuple(values.values()))


def root(db, world='w', **overrides):
    insert(db, 'worlds', id=world, initial_json='{}')
    point = dict(world_id=world, id='root', sequence=0, kind='root', state_digest=HASH,
                 narration_status='ready', generation=1, claim_token='claim', claim_mode='head',
                 claim_epoch=7, issued_at=1000, expires_at=181000)
    point.update(overrides)
    insert(db, 'world_points', **point)
    db.execute('UPDATE worlds SET active_point_id=? WHERE id=?', ('root', world))


@pytest.fixture
def db():
    conn = sqlite3.connect(':memory:')
    conn.executescript((ROOT / 'storage-contract.sql').read_text(encoding='utf-8'))
    assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    yield conn
    conn.close()


def seed_work(db):
    root(db)
    insert(db, 'world_advances', world_id='w', id='a', input_id='i', input_text='input', intent_status='pending')
    insert(db, 'world_rounds', world_id='w', id='r', advance_id='a', trigger='player',
           intent_status='pending', phase='select_actor', order_json='["c","d"]', cursor=0,
           acted_json='[]', visited_json='[]')
    insert(db, 'world_point_work', world_id='w', point_id='p', round_id='r', advance_id='a',
           kind='normal', baseline_point_id='root', baseline_version=0, baseline_digest=HASH,
           time_json='{}', time_locked=1, sealed=0, phase='build_group', progress_json='{}', status='active')
    insert(db, 'world_groups', world_id='w', point_id='p', id='g', source_id='c', members_json='["c","d"]', status='open')
    insert(db, 'world_leases', world_id='w', holder_id='tab', token='lease', epoch=8, expires_at=999999)


def accepted(db, epoch=8, attempt=1, member='c', **changes):
    scope = dict(world_id='w', point_id='p', group_id='g', member_id=member, epoch=epoch, attempt=attempt)
    scope.update(changes)
    insert(db, 'world_accepted_work', **scope, input_projection_hash=HASH, hashes_json='{}')
    insert(db, 'world_frozen_work', **scope, action_bytes='推开 D'.encode('utf-8'))
    return scope


def test_environment_and_schema_load(db, record_property):
    record_property('python', sys.version)
    record_property('sqlite', sqlite3.sqlite_version)
    assert sqlite3.sqlite_version_info >= (3, 37)
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'world_point_work', 'world_work_refs', 'world_copy_results', 'world_gates'} <= tables


@pytest.mark.parametrize('changes', [
    {'generation': 0}, {'generation': 1.5}, {'sequence': -1}, {'sequence': 9007199254740992},
    {'round_id': 'r'}, {'previous_point_id': 'root'}, {'time_json': '{}'},
    {'claim_epoch': 0}, {'claim_mode': 'history'}, {'claim_token': None},
    {'expires_at': 999}, {'state_digest': 'z'*64},
])
def test_illegal_root_or_claim_is_rejected(db, changes):
    with pytest.raises(sqlite3.IntegrityError):
        root(db, **changes)


def test_history_claim_uses_null_epoch_and_root_is_unique(db):
    root(db, claim_mode='history', claim_epoch=None)
    with pytest.raises(sqlite3.IntegrityError):
        insert(db, 'world_points', world_id='w', id='root2', sequence=0, kind='root',
               state_digest=HASH, narration_status='ready', generation=1)


def test_root_gate_survives_v1_trigger_replacement_and_pause_is_independent(db):
    root(db, narration_status='pending')
    insert(db, 'world_advances', world_id='w', id='a', input_id='i', intent_status='pending')
    values = dict(world_id='w', id='r', advance_id='a', trigger='player', intent_status='pending',
                  phase='select_actor', order_json='["c"]', cursor=0, acted_json='[]', visited_json='[]')
    with pytest.raises(sqlite3.IntegrityError, match='head_narration_not_ready'):
        insert(db, 'world_rounds', **values)
    # Updating pause is allowed even with a pending root; no blanket ready trigger.
    db.execute('UPDATE worlds SET paused=1,revision=revision+1')
    assert db.execute('SELECT paused,revision FROM worlds').fetchone() == (1, 1)
    db.execute("UPDATE world_points SET narration_status='ready'")
    insert(db, 'world_rounds', **values)


@pytest.mark.parametrize('column,value', [('phase','paused'),('phase','await_narration'),
    ('trigger','automatic'),('cursor',3),('conclusion_json','{}')])
def test_round_invalid_combinations(db, column, value):
    seed_work(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(f'UPDATE world_rounds SET {column}=?', (value,))


@pytest.mark.parametrize('conclusion', [
    {'kind':'handback','closedBy':'model','cancelReason':None},
    {'kind':'handback','closedBy':'cancel','cancelReason':'stop'},
    {'kind':'continue','closedBy':'model','cancelReason':None,'candidateCharacterIds':['c'],'nextRoundId':'r2'},
])
def test_conclusion_sources_are_explicit(db, conclusion):
    seed_work(db)
    db.execute("UPDATE world_rounds SET phase='complete',conclusion_json=?", (json.dumps(conclusion),))


@pytest.mark.parametrize('conclusion', [
    {'kind':'handback','closedBy':'cancel','cancelReason':' '},
    {'kind':'handback','closedBy':'model','cancelReason':'stop'},
    {'kind':'continue','closedBy':'model','cancelReason':None,'candidateCharacterIds':[],'nextRoundId':'r2'},
])
def test_illegal_conclusion_sources(db, conclusion):
    seed_work(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE world_rounds SET phase='complete',conclusion_json=?", (json.dumps(conclusion),))


def test_cross_world_references_fail(db):
    seed_work(db)
    root(db, 'other')
    with pytest.raises(sqlite3.IntegrityError):
        insert(db, 'world_groups', world_id='other', point_id='p', id='cross', source_id='c', members_json='["c"]', status='open')
    with pytest.raises(sqlite3.IntegrityError):
        insert(db, 'world_work_refs', world_id='w', point_id='p', group_id='g', member_id='c', epoch=7, attempt=99)


def test_current_epoch_filter_precedes_maximum_attempt(db):
    seed_work(db)
    accepted(db, epoch=7, attempt=99)
    accepted(db, epoch=8, attempt=1)
    accepted(db, epoch=8, attempt=2)
    assert db.execute('SELECT epoch,attempt,action_bytes FROM visible_frozen_work').fetchall() == [(8,2,'推开 D'.encode())]
    db.execute("UPDATE world_groups SET status='abandoned'")
    assert db.execute('SELECT * FROM visible_frozen_work').fetchall() == []


@pytest.mark.parametrize('table', ['world_accepted_work','world_frozen_work'])
def test_accepted_work_is_immutable(db, table):
    seed_work(db)
    scope=accepted(db)
    insert(db, 'world_work_refs', **scope)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(f'UPDATE {table} SET attempt=2')
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('DELETE FROM world_accepted_work')


def roll(db, **changes):
    values=dict(world_id='w',id='roll',point_id='p',round_id='r',advance_id='a',group_id='g',
        source_id='c',target_id='d',trigger_key='threat',rule_version='reaction-d20-v1',result=15,target=11,
        eligibility_digest=HASH,eligible=1,admitted=1)
    values.update(changes)
    insert(db,'world_rolls',**values)


@pytest.mark.parametrize('changes', [{'eligible':None},{'admitted':None},{'admitted':0},{'target':10},
    {'result':21},{'result':1.5},{'point_id':'other'},{'group_id':'unknown'}])
def test_roll_is_one_final_bound_row(db, changes):
    seed_work(db)
    with pytest.raises(sqlite3.IntegrityError): roll(db,**changes)


def test_roll_identity_is_unique_and_final(db):
    seed_work(db)
    roll(db)
    with pytest.raises(sqlite3.IntegrityError): roll(db,id='new')
    with pytest.raises(sqlite3.IntegrityError): db.execute('UPDATE world_rolls SET result=16')


@pytest.mark.parametrize('key', ['inputText','activeInput','actionText','claimToken'])
def test_idempotency_cannot_store_private_payload(db, key):
    root(db)
    with pytest.raises(sqlite3.IntegrityError,match='private_payload'):
        insert(db,'world_submissions',world_id='w',request_id='req',operation='commit_point',
               request_hash=HASH,result_json=json.dumps({'nested':{key:'secret'}}))


def test_copy_deduplication_binds_source_manifest_and_target_epoch(db):
    seed_work(db)
    values=dict(world_id='w',point_id='p',group_id='g',target_epoch=8,source_epoch=7,source_attempt=1,
                manifest_hash=HASH,attempt=2)
    insert(db,'world_copy_results',**values)
    with pytest.raises(sqlite3.IntegrityError): insert(db,'world_copy_results',**{**values,'attempt':3})
    insert(db,'world_copy_results',**{**values,'target_epoch':9,'attempt':3})


def test_successor_reservation_can_reference_uncommitted_sealed_predecessor(db):
    seed_work(db)
    db.execute("UPDATE world_point_work SET sealed=1,prefix_digest=?,phase='select_actor' WHERE point_id='p'", (HASH,))
    assert not db.execute("SELECT 1 FROM world_points WHERE id='p'").fetchall()
    values = dict(world_id='w',point_id='next',round_id='r',advance_id='a',kind='instant',
        baseline_point_id='p',baseline_version=1,baseline_digest=HASH,time_json='{}',time_locked=1,
        sealed=0,phase='build_group',progress_json='{}',status='active',predecessor_point_id='p')
    insert(db,'world_point_work',**values)
    db.execute("UPDATE world_point_work SET successor_point_id='next' WHERE point_id='p'")
    db.commit()  # Deferred predecessor/successor FKs close without a committed P1.
    assert db.execute("SELECT baseline_point_id FROM world_point_work WHERE point_id='next'").fetchone() == ('p',)


@pytest.mark.parametrize('mutation',['missing','unsealed','wrong_world','mismatched','missing_predecessor'])
def test_work_baseline_rejects_unavailable_or_wrong_predecessor(db, mutation):
    seed_work(db)
    db.execute("UPDATE world_point_work SET sealed=1,prefix_digest=?,phase='select_actor' WHERE point_id='p'", (HASH,))
    if mutation=='unsealed': db.execute("UPDATE world_point_work SET sealed=0,prefix_digest=NULL WHERE point_id='p'")
    if mutation=='wrong_world': root(db,'other')
    values = dict(world_id='w',point_id='next',round_id='r',advance_id='a',kind='instant',
        baseline_point_id='p',baseline_version=1,baseline_digest=HASH,time_json='{}',time_locked=1,
        sealed=0,phase='build_group',progress_json='{}',status='active',predecessor_point_id='p')
    if mutation=='missing': values.update(predecessor_point_id=None,baseline_point_id='missing')
    if mutation=='wrong_world': values.update(world_id='other')
    if mutation=='mismatched': values.update(baseline_point_id='root')
    if mutation=='missing_predecessor': values.update(predecessor_point_id=None)
    with pytest.raises(sqlite3.IntegrityError): insert(db,'world_point_work',**values)
