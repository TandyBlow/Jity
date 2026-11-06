"""Build a record fixture through the production apply path, for the adapter replay.

The local corpus carries ten committed points across five worlds and every one of them has an empty
delta, so no fact path can be exercised on it. This writes a small chain into a copy of that database:
each point is applied with the production `apply_point`, each digest is recomputed with the production
`state_digest`, and each checkpoint is written the way the ledger writes it. The result is a record the
production reader accepts, but it is a fixture - not a player's history - and every report says so.
"""
import json
import pathlib
import shutil
import sqlite3
import sys

BACKEND = pathlib.Path('D:/others/Jity/.local/agent-worktree/backend')
sys.path.insert(0, str(BACKEND))
from app.database.world_repository import apply_point, build_initial_state, state_digest  # noqa: E402
from app.schemas.world.contracts import TimelinePoint, WorldInitialState, WorldState  # noqa: E402

SOURCE = pathlib.Path('D:/others/Jity/.local/world.db')
TARGET = pathlib.Path('artifacts/next-runs/adapt-r1/record.db')
WORLD = 'world_1'


def projection(state, identity, sequence, kind, previous, delta, linked=None):
    return TimelinePoint.model_validate(dict(
        worldId=WORLD, id=identity, sequence=sequence, kind=kind, previousPointId=previous,
        roundId='round_fixture', advanceId='advance_fixture', linkedFromPointId=linked,
        trigger='player', timeAdvance={'boundary': 'elapsed', 'duration': {'amount': 1, 'unit': 'second'}},
        entityDeltas=delta))


def write_point(db, identity, sequence, previous, delta, state, linked=None):
    digest = state_digest(state)
    db.execute('INSERT INTO world_points (world_id,id,sequence,kind,previous_point_id,round_id,advance_id,'
               'linked_from_point_id,time_json,delta_json,state_digest,narration_status,generation,claim_token,'
               'claim_mode,claim_epoch,issued_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (WORLD, identity, sequence, 'normal', previous, 'round_fixture', 'advance_fixture', linked,
                json.dumps({'boundary': 'elapsed', 'duration': {'amount': 1, 'unit': 'second'}}),
                json.dumps(delta, ensure_ascii=False), digest, 'ready', 1, 'claim_fixture', 'head', 1,
                1, 2))
    db.execute('INSERT OR REPLACE INTO world_state_checkpoints (world_id,point_id,canonical_version,'
               'state_json,state_digest) VALUES (?,?,?,?,?)',
               (WORLD, identity, 'world-canonical-v1', state.model_dump_json(), digest))
    return digest


def main():
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, TARGET)
    db = sqlite3.connect(TARGET)
    db.row_factory = sqlite3.Row
    db.execute("DELETE FROM world_points WHERE world_id=?", (WORLD,))
    db.execute("DELETE FROM world_state_checkpoints WHERE world_id=?", (WORLD,))
    db.execute("DELETE FROM world_points WHERE world_id='world_2'")
    db.execute("DELETE FROM world_state_checkpoints WHERE world_id='world_2'")
    db.execute("INSERT OR REPLACE INTO world_advances (world_id,id,input_id,input_text,intent_status,ended) "
               "VALUES (?,?,?,?,?,?)",
               (WORLD, 'advance_fixture', 'input_fixture', None, 'consumed', 1))
    db.execute("INSERT OR REPLACE INTO world_rounds (world_id,id,advance_id,trigger,intent_status,phase,"
               "order_json,cursor,acted_json,visited_json,conclusion_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
               (WORLD, 'round_fixture', 'advance_fixture', 'automatic', 'consumed', 'complete',
               '[]', 0, '[]', '[]', json.dumps({'kind': 'handback', 'closedBy': 'model', 'cancelReason': None})))
    initial_raw = db.execute('SELECT initial_json FROM worlds WHERE id=?', (WORLD,)).fetchone()[0]
    initial = WorldInitialState.model_validate_json(initial_raw)
    root_state = build_initial_state(initial)
    root_digest = state_digest(root_state)
    db.execute('DELETE FROM world_points WHERE world_id=?', (WORLD,))
    db.execute('INSERT INTO world_points (world_id,id,sequence,kind,previous_point_id,round_id,advance_id,'
               'linked_from_point_id,time_json,delta_json,state_digest,narration_status,generation,claim_token,'
               'claim_mode,claim_epoch,issued_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (WORLD, 'root_fx', 0, 'root', None, None, None, None, None, None, root_digest,
                'ready', 1, 'claim_fixture', 'head', 1, 1, 2))
    db.execute('INSERT OR REPLACE INTO world_state_checkpoints (world_id,point_id,canonical_version,'
               'state_json,state_digest) VALUES (?,?,?,?,?)',
               (WORLD, 'root_fx', 'world-canonical-v1', root_state.model_dump_json(), root_digest))

    # p1: a move with a recorded origin, and a sanity drop
    p1_delta = {'person_a': {'entityId': 'person_a',
                             'positionSet': {'containerId': 'hall', 'slotId': None, 'relativeTo': None},
                             'sanitySet': 7}}
    s1 = apply_point(root_state, projection(root_state, 'p1', 1, 'normal', 'root_fx', p1_delta))
    d1 = write_point(db, 'p1', 1, 'root_fx', p1_delta, s1)

    # p2: an appearance change and a sanity set to zero - the falsy boundary; its checkpoint is removed
    p2_delta = {'person_c': {'entityId': 'person_c',
                             'appearanceChanges': [{'id': 'ac_1', 'text': '袖口沾了水', 'supersedes': []}],
                             'sanitySet': 0}}
    s2 = apply_point(s1, projection(s1, 'p2', 2, 'normal', 'p1', p2_delta))
    d2 = write_point(db, 'p2', 2, 'p1', p2_delta, s2)

    # p3: a move whose predecessor checkpoint is gone - the adapter must report a gap, not guess an origin
    p3_delta = {'person_c': {'entityId': 'person_c',
                             'positionSet': {'containerId': 'hall', 'slotId': None, 'relativeTo': None}}}
    s3 = apply_point(s2, projection(s2, 'p3', 3, 'normal', 'p2', p3_delta))
    d3 = write_point(db, 'p3', 3, 'p2', p3_delta, s3)

    # p4: empty delta - the only signal a quiet point leaves
    s4 = apply_point(s3, projection(s3, 'p4', 4, 'normal', 'p3', {}))
    d4 = write_point(db, 'p4', 4, 'p3', {}, s4)

    # p5: sanity raised from zero, which only works if zero is read as a value
    p5_delta = {'person_c': {'entityId': 'person_c', 'sanitySet': 4}}
    s5 = apply_point(s4, projection(s4, 'p5', 5, 'normal', 'p4', p5_delta))
    d5 = write_point(db, 'p5', 5, 'p4', p5_delta, s5)
    db.execute('DELETE FROM world_state_checkpoints WHERE world_id=? AND point_id=?', (WORLD, 'p2'))
    db.execute('UPDATE worlds SET active_point_id=?, version=5, active_round_id=? WHERE id=?',
               ('p5', 'round_fixture', WORLD))
    db.commit()
    db.close()
    print('fixture', TARGET, 'digests', d1[:12], d2[:12], d3[:12], d4[:12], d5[:12])


if __name__ == '__main__':
    main()
