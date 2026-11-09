import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiment import process_tree_rss


class ResourceTests(unittest.TestCase):
    def test_models_and_grandchildren_count_but_other_work_does_not(self):
        resident, members = process_tree_rss('10 1 10 1024\n11 10 10 4096\n12 11 12 2048\n99 1 99 999999\n', 10)
        self.assertEqual(members, [10, 11, 12])
        self.assertEqual(resident, 7)

    def test_orphan_in_owned_group_stays_visible_after_controller_exit(self):
        resident, members = process_tree_rss('11 1 10 4096\n99 1 99 1024\n', 10)
        self.assertEqual(members, [11]); self.assertEqual(resident, 4)

    def test_broken_samples_cannot_be_recorded_as_zero_memory(self):
        for raw in ('10 1 10 -1', '10 1 10', 'x 1 10 20', '10 1 10 20\n10 1 10 30'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): process_tree_rss(raw, 10)
        self.assertEqual(process_tree_rss('99 1 99 1024', 10), (0, []))


if __name__ == '__main__': unittest.main()
