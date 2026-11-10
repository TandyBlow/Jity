"""Integrity tests for the assistant-draft scale-v2 batch; no quality claim."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import short_d02_checkers as checkers

DATA = HERE / 'data' / 'd02-checkers' / 'scale-v2'


class ScaleDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DATA / 'manifest.json').read_text())
        cls.rows = [json.loads(line) for line in (DATA / 'samples.jsonl').read_text().splitlines()]
        cls.worlds = json.loads((DATA / 'worlds.json').read_text())

    def test_counts_splits_and_group_discipline(self):
        self.assertEqual(self.manifest['groupCount'], 40)
        self.assertEqual(self.manifest['sampleCount'], 480)
        self.assertEqual(self.manifest['splitCounts'],
                         {'train': 288, 'development': 48, 'calibration': 48, 'sealed': 96})
        self.assertEqual(self.manifest['sealedUse'], 'unopened_pending_final_freeze')
        self.assertFalse(self.manifest['trainingAuthorized'])
        seen, by_split = {}, defaultdict(set)
        for row in self.rows:
            self.assertEqual(seen.setdefault(row['scenarioGroup'], row['split']), row['split'])
            by_split[row['split']].add(row['scenarioGroup'])
        self.assertEqual({k: len(v) for k, v in by_split.items()},
                         {'train': 24, 'development': 4, 'calibration': 4, 'sealed': 8})

    def test_twelve_variants_per_group(self):
        variants = defaultdict(set)
        for row in self.rows:
            variants[row['scenarioGroup']].add(row['sampleId'].split(':', 1)[1])
        self.assertEqual(len(variants), 40)
        expected = {'clean', 'actor-swap', 'result', 'special', 'role',
                    'multi', 'condition', 'quote', 'result2', 'actor-pronoun',
                    'unknown-object', 'ambiguous-object'}
        for group, names in variants.items():
            self.assertEqual(names, expected, group)

    def test_every_expected_decision_matches_program_checks(self):
        for row in self.rows:
            result = checkers.check_once(row['text'], row['steps'], row['roleAudit'],
                                         row['expressionAudit'], self.worlds[row['worldId']],
                                         row['actorId'])
            self.assertEqual(result.decision, row['expected']['combined'], row['sampleId'])

    def test_sources_and_status_are_honest(self):
        self.assertEqual({row['source'] for row in self.rows}, {'assistant_authored_scale_v2'})
        self.assertEqual({row['annotationStatus'] for row in self.rows},
                         {'assistant_draft_pending_human'})
        self.assertEqual(self.manifest['humanReview']['status'], 'pending')
        self.assertEqual(self.manifest['humanReview']['reviewedSamples'], 0)

    def test_manifest_hashes(self):
        for name, expected in self.manifest['sha256'].items():
            actual = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, name)


if __name__ == '__main__':
    unittest.main()
