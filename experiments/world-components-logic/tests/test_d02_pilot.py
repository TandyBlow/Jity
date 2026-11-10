"""Pilot data integrity tests; assistant-draft labels are not ground truth."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import short_d02_checkers as checkers

DATA = HERE / 'data' / 'd02-checkers' / 'pilot-v1'


class PilotDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DATA / 'manifest.json').read_text())
        cls.rows = [json.loads(line) for line in (DATA / 'samples.jsonl').read_text().splitlines()]
        cls.worlds = json.loads((DATA / 'worlds.json').read_text())

    def test_counts_and_split_discipline(self):
        self.assertEqual(self.manifest['groupCount'], 20)
        self.assertEqual(self.manifest['sampleCount'], 120)
        self.assertEqual(self.manifest['targetedCount'], 100)
        self.assertEqual(self.manifest['naturalApiCount'], 20)
        self.assertEqual(self.manifest['splitCounts'],
                         {'train': 72, 'development': 12, 'calibration': 12, 'sealed': 24})
        by_group = {}
        seen = {}
        for row in self.rows:
            group = row['scenarioGroup']
            self.assertIn(row['split'], ('train', 'development', 'calibration', 'sealed'))
            self.assertEqual(seen.setdefault(group, row['split']), row['split'], group)
            by_group.setdefault(row['split'], set()).add(group)
        self.assertEqual({split: len(rows) for split, rows in by_group.items()},
                         {'train': 12, 'development': 2, 'calibration': 2, 'sealed': 4})

    def test_every_expected_decision_matches_the_program_check(self):
        for row in self.rows:
            result = checkers.check_once(row['text'], row['steps'], row['roleAudit'],
                                         row['expressionAudit'], self.worlds[row['worldId']],
                                         row['actorId'])
            self.assertEqual(result.decision, row['expected']['combined'], row['sampleId'])
            codes = {issue['code'] for issue in result.issues}
            for tag in row['tags']:
                if tag.endswith('_requires_review'):
                    self.assertIn(tag, codes, row['sampleId'])

    def test_natural_stratum_is_separated_and_not_called_gold(self):
        natural = [row for row in self.rows if row['source'] == 'api_first_output']
        self.assertEqual(len(natural), 20)
        for row in natural:
            self.assertEqual(row['annotationStatus'], 'assistant_draft_pending_human')
            self.assertTrue(row['apiMeta']['usage'])
            self.assertIn('非金标准', row['reviewNote'])
        for row in self.rows:
            self.assertEqual(row['annotationStatus'], 'assistant_draft_pending_human')

    def test_each_group_has_five_targeted_variants(self):
        groups = {}
        for row in self.rows:
            if row['source'] == 'assistant_authored_targeted':
                groups.setdefault(row['scenarioGroup'], set()).add(row['sampleId'].split(':', 1)[1])
        self.assertEqual(len(groups), 20)
        for group, suffixes in groups.items():
            self.assertEqual(suffixes, {'clean', 'actor-swap', 'result', 'special', 'role'}, group)

    def test_manifest_hashes_and_contamination_marker(self):
        for name, expected in self.manifest['sha256'].items():
            actual = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, name)
        self.assertEqual(self.manifest['sealedUse'],
                         'opened_by_pilot_api_proxy_not_reusable_as_sealed_test')
        self.assertFalse(self.manifest['trainingAuthorized'])


if __name__ == '__main__':
    unittest.main()
