"""Checks for the target audit, the moved set and the two scorer fixes."""
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import audit_decisions
import audit_targets
import freeze_moved_set
import score_cf24_baseline

WORKTREE = HERE.parents[1]
UNITS = WORKTREE / 'artifacts/next-inputs/world-components/n4-moved24-contract.jsonl'


def unit(kind, name='沈砚', **fact):
    body = {'kind': kind, 'name': name}
    body.update(fact)
    return {'unitId': 'x:f0', 'kind': kind, 'fact': body,
            'input': '地点=潮汐档案馆\n地点可见=潮汐簿、铜灯、干纸、墨、天窗、长桌、门槛\n'
                     '场景=夜；小雨；铜灯'}


class ScorerFixes(unittest.TestCase):
    def test_alias_covers_canonical_name(self):
        verdict, note, flags = score_cf24_baseline.judge(
            unit('moved', **{'from': '潮渡', 'to': '旧灯塔'}), '沈砚从渡口到了灯塔。')
        self.assertEqual(verdict, 'S', note)
        self.assertEqual(flags, [])

    def test_visible_prop_and_sublocation_are_authorised(self):
        verdict, note, flags = score_cf24_baseline.judge(
            unit('no_change'), '长桌上的东西都还在原处，屋里没有新的变化。')
        self.assertEqual(verdict, 'S', note)
        self.assertEqual(flags, [])

    def test_missing_start_still_fails(self):
        verdict, _, _ = score_cf24_baseline.judge(
            unit('moved', **{'from': '潮渡', 'to': '旧灯塔'}), '沈砚到了旧灯塔。')
        self.assertEqual(verdict, 'O')


class TargetAudit(unittest.TestCase):
    def test_every_flagged_target_has_a_decision(self):
        places, children = audit_targets.world()
        table = {original for original, *_ in audit_decisions.DECISIONS}
        missing = set()
        for pool, path in audit_targets.POOLS:
            for pair in audit_targets.load(path):
                record = audit_targets.audit(pair, places, children)
                if record['flags'] and pair['target'] not in table:
                    missing.add(pair['target'])
        self.assertEqual(missing, set())

    def test_rewrites_do_not_drop_fact_coverage(self):
        for original, verdict, revised, _ in audit_decisions.DECISIONS:
            if revised is None:
                continue
            self.assertNotEqual(original, revised)
            self.assertGreater(len(revised), 0)
            self.assertIn(verdict, {'extra-action', 'restatement', 'quantity', 'qualifier', 'start'})

    def test_audited_pools_parse_and_cover(self):
        for pool in ('verbalizer', 'expand78', 'object34'):
            path = WORKTREE / 'artifacts/target-audit-r1' / (pool + '-audited.jsonl')
            rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
            self.assertGreater(len(rows), 0)
            for row in rows:
                self.assertTrue(row['target'].strip())


class MovedSet(unittest.TestCase):
    def test_routes_do_not_repeat_existing_signatures(self):
        existing = freeze_moved_set.existing_signatures()
        self.assertEqual([route for route in freeze_moved_set.ROUTES if route in existing], [])
        self.assertEqual(len(freeze_moved_set.ROUTES), 24)
        self.assertEqual(len(set(freeze_moved_set.ROUTES)), 24)

    def test_frozen_file_matches_routes(self):
        rows = [json.loads(line) for line in UNITS.read_text(encoding='utf-8').splitlines() if line.strip()]
        self.assertEqual(len(rows), 24)
        routes = [(row['fact']['name'], row['fact']['from'], row['fact']['to']) for row in rows]
        self.assertEqual(routes, list(freeze_moved_set.ROUTES))
        for row in rows:
            verdict, note, flags = score_cf24_baseline.judge(row, row['referenceTarget'])
            self.assertEqual((verdict, flags), ('S', []), (row['unitId'], note))


if __name__ == '__main__':
    unittest.main()
