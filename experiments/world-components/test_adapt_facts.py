"""The adapter must read the predecessor point, never the head, and must not guess a missing origin."""
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

    def test_task_delta_is_not_displayed_and_not_a_quiet_point(self):
        facts, gaps, unshown = self.facts('p6')
        self.assertEqual([f['kind'] for f in facts], [])
        self.assertEqual(len(unshown), 1)
        self.assertTrue(unshown[0]['notAChange'])
        self.assertEqual(gaps, [])

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


if __name__ == '__main__':
    unittest.main()
