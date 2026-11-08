"""The adapter must read the predecessor point, never the head, and must not guess a missing origin."""
import json
import os
import sqlite3
import tempfile
import unittest

import adapt_facts

DB = 'artifacts/next-runs/adapt-r1/record.db'
BACKEND = adapt_facts.DEFAULT_BACKEND


class AdapterCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = adapt_facts.connect(DB)
        cls.names = adapt_facts.labels(cls.db, 'world_1')

    def facts(self, point, world='world_1'):
        names = adapt_facts.labels(self.db, world)
        facts, gaps, unshown = adapt_facts.adapt_point(self.db, world, point, names, BACKEND)
        return facts, gaps, unshown

    def test_origin_comes_from_the_predecessor_not_the_head(self):
        facts, _, _ = self.facts('p1')
        moved = [f for f in facts if f['kind'] == 'moved'][0]
        sanity = [f for f in facts if f['kind'] == 'sanity_changed'][0]
        # the head of this world is p7, where the character is back in the corridor at sanity 3
        self.assertEqual(moved['sentence'], '林川从走廊到门厅。')
        self.assertEqual(moved['provenance']['previousPointId'], 'root_fx')
        self.assertEqual(sanity['sentence'], '林川的理智下降（10→7）。')

    def test_missing_checkpoint_is_recovered_by_replay(self):
        facts, gaps, _ = self.facts('p2')
        self.assertEqual(gaps, [])
        sanity = [f for f in facts if f['kind'] == 'sanity_changed'][0]
        self.assertEqual(sanity['sentence'], '周宁的理智下降（10→0）。')
        self.assertEqual(sanity['provenance']['stateSource'], 'replay')
        self.assertIsNone(sanity['provenance']['replayAgreesWithCheckpoint'])

    def test_missing_checkpoint_no_longer_blocks_the_origin(self):
        facts, gaps, _ = self.facts('p3')
        moved = [f for f in facts if f['kind'] == 'moved'][0]
        self.assertEqual(moved['sentence'], '周宁从走廊到门厅。')
        self.assertEqual(moved['provenance']['previousStateSource'], 'replay')

    def test_zero_is_read_as_a_value(self):
        facts, _, _ = self.facts('p5')
        sanity = [f for f in facts if f['kind'] == 'sanity_changed'][0]
        self.assertEqual(sanity['from'], 0)
        self.assertEqual(sanity['sentence'], '周宁的理智上升（0→4）。')

    def test_bad_chain_with_a_matching_checkpoint_is_still_refused(self):
        facts, gaps, _ = self.facts('t2', world='world_3')
        self.assertEqual(facts, [])
        self.assertEqual(len(gaps), 1)
        self.assertIn('not used to mask', gaps[0]['gap'])
        self.assertTrue(gaps[0]['checkpointFound'])
        self.assertTrue(gaps[0]['checkpointDigestMatchesPoint'])
        self.assertEqual(gaps[0]['replayFailure'], 'ledger')

    def test_replay_unavailable_falls_back_to_the_checkpoint(self):
        facts, gaps, _ = self.facts('u1', world='world_4')
        self.assertEqual(gaps, [])
        sanity = [f for f in facts if f['kind'] == 'sanity_changed'][0]
        self.assertEqual(sanity['sentence'], '林川的理智下降（10→8）。')
        self.assertEqual(sanity['provenance']['stateSource'], 'checkpoint')
        self.assertFalse(sanity['provenance']['replayOk'])

    def test_unknown_replay_failure_never_falls_back_to_the_checkpoint(self):
        original = adapt_facts.resolve_state

        def fake_resolve(db, world_id, point_id, backend):
            return {'state': None, 'source': 'withheld: replay failed for an unrecognised reason',
                    'checkpointFound': True, 'checkpointDigestMatchesPoint': True, 'replayOk': False,
                    'replayFailure': 'unknown', 'replayAgreesWithCheckpoint': None,
                    'replayError': 'RuntimeError: something new', 'replayedDigest': None,
                    'checkpointDigest': 'x'}
        adapt_facts.resolve_state = fake_resolve
        try:
            facts, gaps, _ = self.facts('u1', world='world_4')
        finally:
            adapt_facts.resolve_state = original
        self.assertEqual(facts, [])
        self.assertIn('unrecognised', gaps[0]['gap'])

    def test_classification_defaults_to_the_strict_bucket(self):
        class LedgerMismatch(Exception):
            pass
        self.assertEqual(adapt_facts.classify_replay_failure(LedgerMismatch('something new')), 'unknown')
        self.assertEqual(adapt_facts.classify_replay_failure(RuntimeError('boom')), 'unknown')
        self.assertEqual(adapt_facts.classify_replay_failure(
            LedgerMismatch('Committed point has no round')), 'unavailable')
        self.assertEqual(adapt_facts.classify_replay_failure(
            LedgerMismatch('Replayed state differs from the committed digest')), 'ledger')

    def test_empty_delta_with_a_failed_recovery_is_still_a_gap(self):
        facts, gaps, _ = self.facts('u3', world='world_4')
        self.assertEqual(facts, [])
        self.assertTrue(any(g['gap'] == 'state not recoverable' for g in gaps))

    def test_unrecoverable_state_is_a_gap_not_a_guess(self):
        # replay cannot run and the checkpoint is gone, so there is nothing to show and nothing to guess
        facts, gaps, _ = self.facts('u2', world='world_4')
        self.assertEqual(facts, [])
        self.assertTrue(any(g['gap'] == 'state not recoverable' for g in gaps))

    def test_task_achieved_reads_the_goal_from_the_committed_state(self):
        facts, gaps, unshown = self.facts('p6')
        self.assertEqual([f['kind'] for f in facts], ['task_achieved'])
        self.assertEqual(facts[0]['sentence'], '林川达成任务：留在走廊守门，不碰盒子。')
        self.assertEqual(facts[0]['taskId'], 'task_watch')
        self.assertIn('tasks.task_watch.goal', facts[0]['provenance']['fieldsRead'])
        self.assertEqual(gaps, [])
        self.assertEqual(unshown, [])


    def test_empty_delta_is_scoped_to_its_point(self):
        facts, _, _ = self.facts('p4')
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['scope'], 'point')
        self.assertEqual(facts[0]['sentence'], '第4点没有实体变化。')

    def test_two_worlds_do_not_read_each_other(self):
        facts, _, _ = self.facts('q1', world='world_2')
        moved = [f for f in facts if f['kind'] == 'moved'][0]
        self.assertEqual(moved['sentence'], '林川从走廊到门厅。')
        self.assertEqual(moved['provenance']['worldId'], 'world_2')
        self.assertEqual(moved['provenance']['previousPointId'], 'root_w2')

    def test_missing_field_in_the_predecessor_is_a_gap(self):
        original = adapt_facts.resolve_state
        state = {'characters': {'person_a': {'id': 'person_a', 'position': {'containerId': 'corridor'}}},
                 'items': {}, 'locations': {'corridor': {'id': 'corridor'}, 'hall': {'id': 'hall'}}}

        def fake_resolve(db, world_id, point_id, backend):
            return {'state': state, 'source': 'fixture', 'checkpointFound': True,
                    'checkpointDigestMatchesPoint': True, 'replayOk': True,
                    'replayAgreesWithCheckpoint': True, 'replayError': None,
                    'replayedDigest': None, 'checkpointDigest': 'x'}
        adapt_facts.resolve_state = fake_resolve
        try:
            facts, gaps, _ = self.facts('p1')
        finally:
            adapt_facts.resolve_state = original
        self.assertTrue(any('no sanity' in g['gap'] for g in gaps))

    def test_digest_and_replay_are_reported_separately(self):
        facts, _, _ = self.facts('p1')
        for fact in facts:
            provenance = fact['provenance']
            self.assertIn('currentDigestMatchesPoint', provenance)
            self.assertIn('replayOk', provenance)
            self.assertIn('replayAgreesWithCheckpoint', provenance)
            for key in ('worldId', 'pointId', 'previousPointId', 'fieldsRead', 'adapted'):
                self.assertIn(key, provenance)


class CommittedStateCases(unittest.TestCase):
    """A task or appearance sentence may only restate what the committed point actually holds."""

    names = {'person_a': '林川', 'person_c': '周宁'}

    def state(self, tasks=None, appearance=None, items=None):
        return {'characters': {'person_c': {'id': 'person_c', 'tasks': tasks or {},
                                            'appearanceChanges': appearance or []}},
                'items': items or {}, 'locations': {}}

    def adapt(self, delta, state):
        path = os.path.join(tempfile.mkdtemp(), 'fixture.db')
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE worlds (id TEXT, initial_json TEXT)')
        db.execute('CREATE TABLE world_points (world_id TEXT, id TEXT, sequence INTEGER, kind TEXT, '
                   'previous_point_id TEXT, delta_json TEXT, linked_from_point_id TEXT)')
        db.execute("INSERT INTO worlds VALUES ('w', '{}')")
        db.execute("INSERT INTO world_points VALUES ('w', 'p1', 1, 'turn', NULL, ?, NULL)",
                   (json.dumps(delta, ensure_ascii=False),))
        db.commit()
        db.close()

        original = adapt_facts.resolve_state

        def fake_resolve(db, world_id, point_id, backend):
            return {'state': state, 'source': 'fixture', 'checkpointFound': True,
                    'checkpointDigestMatchesPoint': True, 'replayOk': True,
                    'replayAgreesWithCheckpoint': True, 'replayError': None,
                    'replayedDigest': None, 'checkpointDigest': 'x'}
        adapt_facts.resolve_state = fake_resolve
        try:
            return adapt_facts.adapt_point(adapt_facts.connect(path), 'w', 'p1', self.names)
        finally:
            adapt_facts.resolve_state = original

    def test_achieved_task_uses_the_committed_goal_verbatim(self):
        tasks = {'task_pressure': {'id': 'task_pressure', 'ownerId': 'person_c', 'parentTaskId': None,
                                   'goal': '完成压力试验', 'status': 'achieved'}}
        facts, gaps, unshown = self.adapt({'person_c': {'entityId': 'person_c',
                                                        'tasksAchieved': ['task_pressure']}}, self.state(tasks))
        self.assertEqual([f['sentence'] for f in facts], ['周宁达成任务：完成压力试验。'])
        self.assertEqual(gaps, [])
        self.assertEqual(unshown, [])

    def test_delta_claiming_a_pending_task_is_a_gap(self):
        tasks = {'task_pressure': {'id': 'task_pressure', 'ownerId': 'person_c', 'parentTaskId': None,
                                   'goal': '完成压力试验', 'status': 'pending'}}
        facts, gaps, _ = self.adapt({'person_c': {'entityId': 'person_c',
                                                  'tasksAchieved': ['task_pressure']}}, self.state(tasks))
        self.assertEqual(facts, [])
        self.assertIn('says pending', gaps[0]['gap'])

    def test_delta_naming_an_unknown_task_is_a_gap(self):
        facts, gaps, _ = self.adapt({'person_c': {'entityId': 'person_c', 'tasksAchieved': ['task_ghost']}},
                                    self.state({}))
        self.assertEqual(facts, [])
        self.assertIn('no such task', gaps[0]['gap'])

    def test_new_subtask_names_its_committed_parent(self):
        tasks = {
            'task_pressure': {'id': 'task_pressure', 'ownerId': 'person_c', 'parentTaskId': None,
                              'goal': '完成压力试验', 'status': 'pending'},
            'task_recover': {'id': 'task_recover', 'ownerId': 'person_c', 'parentTaskId': 'task_pressure',
                             'goal': '完成恢复练习', 'status': 'pending'},
        }
        delta = {'person_c': {'entityId': 'person_c', 'subtasksAdded': [
            {'id': 'task_recover', 'ownerId': 'person_c', 'parentTaskId': 'task_pressure',
             'goal': '完成恢复练习', 'status': 'pending'}]}}
        facts, gaps, _ = self.adapt(delta, self.state(tasks))
        self.assertEqual([f['sentence'] for f in facts],
                         ['周宁新增小任务：完成恢复练习（上级：完成压力试验）。'])
        self.assertEqual(facts[0]['parentTaskId'], 'task_pressure')
        self.assertEqual(gaps, [])

    def appearance_delta(self, change_id='ac_smile', text='面带微笑'):
        return {'person_c': {'entityId': 'person_c', 'appearanceChanges': [
            {'id': change_id, 'text': text, 'supersedes': []}]}}

    def stored(self, change_id='ac_smile', text='面带微笑', **overrides):
        entry = {'id': change_id, 'text': text, 'supersedes': [], 'active': True,
                 'sourcePointId': 'p1', 'sourceSequence': 1}
        entry.update(overrides)
        return entry

    def test_appearance_text_and_source_come_from_the_committed_state(self):
        facts, gaps, unshown = self.adapt(self.appearance_delta(), self.state(appearance=[self.stored()]))
        self.assertEqual([f['kind'] for f in facts], ['appearance_changed'])
        self.assertEqual(facts[0]['sentence'], '周宁：面带微笑。')
        self.assertEqual(facts[0]['changeId'], 'ac_smile')
        self.assertIn('appearanceChanges.ac_smile.sourcePointId', facts[0]['provenance']['fieldsRead'])
        self.assertEqual(gaps, [])
        self.assertEqual(unshown, [])

    def test_appearance_from_another_point_is_a_gap(self):
        facts, gaps, _ = self.adapt(self.appearance_delta(),
                                    self.state(appearance=[self.stored(sourcePointId='p0')]))
        self.assertEqual(facts, [])
        self.assertIn('differs from the delta', gaps[0]['gap'])

    def test_appearance_text_that_differs_from_the_committed_state_is_a_gap(self):
        facts, gaps, _ = self.adapt(self.appearance_delta(text='脸色苍白'),
                                    self.state(appearance=[self.stored()]))
        self.assertEqual(facts, [])
        self.assertIn('differs from the delta', gaps[0]['gap'])

    def test_appearance_missing_from_the_committed_state_is_a_gap(self):
        facts, gaps, _ = self.adapt(self.appearance_delta(), self.state(appearance=[]))
        self.assertEqual(facts, [])
        self.assertIn('has 0 such entries', gaps[0]['gap'])

    def test_inactive_appearance_is_a_gap(self):
        facts, gaps, _ = self.adapt(self.appearance_delta(),
                                    self.state(appearance=[self.stored(active=False)]))
        self.assertEqual(facts, [])
        self.assertIn('differs from the delta', gaps[0]['gap'])

    def test_item_appearance_is_read_from_the_item_record(self):
        items = {'box': {'id': 'box', 'appearanceChanges': [self.stored(change_id='ac_box', text='盒盖半开')]}}
        delta = {'box': {'entityId': 'box', 'appearanceChanges': [
            {'id': 'ac_box', 'text': '盒盖半开', 'supersedes': []}]}}
        facts, gaps, _ = self.adapt(delta, self.state(items=items))
        self.assertEqual([f['sentence'] for f in facts], ['box：盒盖半开。'])
        self.assertEqual(gaps, [])

    def test_subtask_whose_committed_goal_differs_is_a_gap(self):
        tasks = {
            'task_pressure': {'id': 'task_pressure', 'ownerId': 'person_c', 'parentTaskId': None,
                              'goal': '完成压力试验', 'status': 'pending'},
            'task_recover': {'id': 'task_recover', 'ownerId': 'person_c', 'parentTaskId': 'task_pressure',
                             'goal': '另一件不同的事', 'status': 'pending'},
        }
        delta = {'person_c': {'entityId': 'person_c', 'subtasksAdded': [
            {'id': 'task_recover', 'ownerId': 'person_c', 'parentTaskId': 'task_pressure',
             'goal': '完成恢复练习', 'status': 'pending'}]}}
        facts, gaps, _ = self.adapt(delta, self.state(tasks))
        self.assertEqual(facts, [])
        self.assertIn('differs from the delta', gaps[0]['gap'])


if __name__ == '__main__':
    unittest.main()
