"""The adapter must read the predecessor point, never the head, and must not guess a missing origin."""
import unittest

import adapt_facts

DB = 'artifacts/next-runs/adapt-r1/record.db'


class AdapterCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = adapt_facts.connect(DB)
        cls.names = adapt_facts.labels(cls.db, 'world_1')

    def facts(self, point):
        facts, gaps = adapt_facts.adapt_point(self.db, 'world_1', point, self.names)
        return facts, gaps

    def test_origin_comes_from_the_predecessor_not_the_head(self):
        facts, _ = self.facts('p1')
        moved = [f for f in facts if f['kind'] == 'moved'][0]
        sanity = [f for f in facts if f['kind'] == 'sanity_changed'][0]
        # the head of this world is p5, where the character is back in the corridor at sanity 4
        self.assertEqual(moved['sentence'], '林川从走廊到门厅。')
        self.assertEqual(moved['provenance']['previousPointId'], 'root_fx')
        self.assertEqual(sanity['sentence'], '林川的理智下降（10→7）。')

    def test_zero_is_read_as_a_value(self):
        facts, _ = self.facts('p5')
        sanity = [f for f in facts if f['kind'] == 'sanity_changed'][0]
        self.assertEqual(sanity['from'], 0)
        self.assertEqual(sanity['sentence'], '周宁的理智上升（0→4）。')

    def test_missing_predecessor_is_a_gap_not_an_origin(self):
        facts, gaps = self.facts('p3')
        self.assertFalse([f for f in facts if f['kind'] == 'moved'])
        self.assertTrue(any('predecessor' in g['gap'] for g in gaps))

    def test_missing_current_checkpoint_blocks_every_fact(self):
        facts, gaps = self.facts('p2')
        self.assertEqual(facts, [])
        self.assertTrue(any('current checkpoint missing' in g['gap'] for g in gaps))

    def test_empty_delta_is_scoped_to_its_point(self):
        facts, _ = self.facts('p4')
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['scope'], 'point')
        self.assertEqual(facts[0]['sentence'], '第4点没有实体变化。')

    def test_every_fact_carries_provenance(self):
        for point in ('p1', 'p4', 'p5'):
            facts, _ = self.facts(point)
            for fact in facts:
                provenance = fact['provenance']
                for key in ('worldId', 'pointId', 'previousPointId', 'fieldsRead', 'adapted'):
                    self.assertIn(key, provenance)
                self.assertTrue(provenance['currentDigestMatchesPoint'])


if __name__ == '__main__':
    unittest.main()
