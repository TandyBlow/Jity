"""Source-card engineering checks; synthetic opinions never become approval."""
import contextlib
import copy
import io
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import prepare_round1 as source
import prepare_review
import review_io
from test_review import packet, claims


def synthetic_source_packet():
    value = packet()
    value['materialKind'] = 'source_card_draft'
    for c in value['cases']:
        c['split'] = 'sealed_candidate'
        c['task'] = 'CHAIN'
        c['input'] = {'sourceCard': {'title': '工程夹具', 'facts': '仅合成场景，非实际题目。', 'question': '只检查页面逻辑。'}}
        c['guard'] = {'reason': 'source_card_not_executable'}
        c['review']['draftExpected'] = {'mustRespect': ['合成约束'], 'forbidden': ['不得代签']}
    return value


class SourceCardsTests(unittest.TestCase):
    def test_four_member_card_has_a_complete_admission_path(self):
        inputs, _ = source.build_cards()
        card = next(c for c in inputs if c['caseId'] == 'r1-sealed-d05-02')
        facts = card['input']['sourceCard']['facts']
        # Read the actual published fixture's relations, not a separate copy of
        # the desired rolls. This is a narrow regression, not a prose evaluator.
        edges = [(a, b, int(roll), int(threshold)) for a, b, roll, threshold
                 in re.findall(r'([甲乙丙丁])→([甲乙丙丁])=?(\d+)/(\d+)', facts)]
        members = set('甲乙丙丁')
        self.assertEqual(len(edges), 4)
        reachable_by_root = {}
        for root in members:
            seen = {root}
            while True:
                expanded = seen | {b for a, b, roll, threshold in edges if a in seen and roll >= threshold}
                if expanded == seen:
                    break
                seen = expanded
            reachable_by_root[root] = seen
        self.assertTrue(any(seen == members for seen in reachable_by_root.values()),
                        f'No single initiator can admit the declared four members: {reachable_by_root}')
        declared = re.search(r'([甲乙丙丁])发起', facts)
        self.assertIsNotNone(declared, 'Card must identify its initiator')
        frozen = {declared.group(1)}
        reused = []
        for actor, target, roll, threshold in edges:
            self.assertIn(actor, frozen, 'Source must be frozen before its relation is judged')
            self.assertEqual(threshold, 11)
            self.assertIn(roll, range(1, 21))
            if target in frozen:
                reused.append((actor, target))
            elif roll >= threshold:
                frozen.add(target)
        self.assertEqual(frozen, members)
        self.assertEqual(reused, [('乙', '丙')])
        self.assertIn('eligible=false、admitted=false', facts)
        self.assertIn('丙的目标为空', facts)

    def test_revision_only_changes_the_affected_card_and_its_rubric(self):
        inputs, reviews = source.build_cards()
        files, _ = source.build_files()
        manifest = json.loads(files[source.DATA/'source-manifest.json'])
        for name, current in (('source-cards.jsonl', inputs), ('rubric-drafts.jsonl', reviews)):
            raw = subprocess.check_output(['git', 'show', f'{source.PREVIOUS_COMMIT}:experiments/world-components-logic/data/round1/{name}'], cwd=source.ROOT)
            previous = {c['caseId']: c for c in map(json.loads, raw.splitlines())}
            current = {c['caseId']: c for c in current}
            self.assertEqual(current.keys(), previous.keys())
            self.assertEqual([key for key in current if current[key] != previous[key]], [source.REVISED_CARD])
            self.assertEqual(current[source.REVISED_CARD]['sourceGroup'], previous[source.REVISED_CARD]['sourceGroup'])
            self.assertEqual(manifest['revisionRecord']['previousFileSha256'][name], source.digest(raw))
        self.assertEqual(manifest['revision'], 2)
        self.assertEqual(manifest['revisionRecord']['changedCardIds'], [source.REVISED_CARD])

    def test_previous_source_batch_cannot_approve_revised_material(self):
        old_claim = claims(synthetic_source_packet())  # QA-only IDs, no real opinions.
        for claim_key, filename in (('inputFileSha256', 'source-cards.jsonl'),
                                    ('reviewDraftFileSha256', 'rubric-drafts.jsonl'),
                                    ('provenanceFileSha256', 'source-manifest.json')):
            raw = subprocess.check_output(['git', 'show', f'{source.PREVIOUS_COMMIT}:experiments/world-components-logic/data/round1/{filename}'], cwd=source.ROOT)
            old_claim[claim_key] = source.digest(raw)
        with self.assertRaisesRegex(ValueError, '批次不匹配'):
            review_io.reconcile_claims(old_claim, source.build_packet())

    def test_current_artifacts_are_reproducible_and_unapproved(self):
        files, summary = source.build_files()
        for path, content in files.items():
            self.assertEqual(path.read_bytes(), content, path.name)
        self.assertEqual((summary['developmentGroups'], summary['sealedCandidateGroups']), (44, 46))
        self.assertIsNone(summary['runtimeCaseCount'])
        self.assertFalse(summary['executableInputsBuilt'])
        self.assertFalse(summary['modelExecutionAuthorized'])
        self.assertFalse(summary['formalEvaluationAllowed'])

    def test_rebalanced_cross_split_and_shared_source_do_not_pass(self):
        inputs, reviews = source.build_cards()
        a, b = inputs[0], inputs[10]
        a['sourceGroup'] = b['sourceGroup']
        reviews[0]['sourceGroup'] = b['sourceGroup']
        with self.assertRaisesRegex(ValueError, '来源组重复'):
            source.validate_cards(inputs, reviews)
        inputs, reviews = source.build_cards()
        inputs[0]['split'] = 'sealed_candidate'
        with self.assertRaisesRegex(ValueError, '配额'):
            source.validate_cards(inputs, reviews)

    def test_missing_required_coverage_rejected_with_counts_unchanged(self):
        inputs, reviews = source.build_cards()
        for r in reviews:
            r['coverageTags'] = [t for t in r['coverageTags'] if t != 'skipped_not_acted']
        with self.assertRaisesRegex(ValueError, 'skipped_not_acted'):
            source.validate_cards(inputs, reviews)

    def test_guard_cannot_inflate_semantic_denominator(self):
        inputs, reviews = source.build_cards()
        guard = next(r for r in reviews if r['caseId'] == 'r1-dev-d04-07')
        guard['draftExpected']['expectedCall'] = True
        with self.assertRaisesRegex(ValueError, '分母'):
            source.validate_cards(inputs, reviews)

    def test_draft_must_not_promote_to_human_truth_or_model_input(self):
        for field in ('human', 'input'):
            inputs, reviews = source.build_cards()
            if field == 'human':
                reviews[0]['humanReview'] = 'approved'
            else:
                inputs[0]['input']['expectedAnswer'] = 'gold'
            with self.assertRaises(ValueError):
                source.validate_cards(inputs, reviews)

    def test_old_review_cannot_be_reused_for_new_batch(self):
        old = json.loads((source.ARTIFACTS/'reviews/l3-review-5db17d61-2026-10-30T19-04-59-780Z.json').read_text())
        with self.assertRaisesRegex(ValueError, '批次不匹配'):
            review_io.reconcile_claims(old, source.build_packet())

    def test_write_new_refuses_existing_different_file_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            existing, new = Path(directory)/'old.json', Path(directory)/'new.json'
            existing.write_bytes(b'KEEP')
            with mock.patch.object(sys, 'argv', ['prepare_round1.py', '--write-new']), \
                 mock.patch.object(source, 'build_files', return_value=({new: b'NEW', existing: b'REPLACE'}, {})):
                with self.assertRaisesRegex(ValueError, '不能覆盖'):
                    source.main()
            self.assertEqual(existing.read_bytes(), b'KEEP')
            self.assertFalse(new.exists())

    def test_shared_ui_synthetic_source_roundtrip_and_escaping(self):
        value = synthetic_source_packet()
        value['cases'][0]['input']['sourceCard']['facts'] = '</script><script>BAD</script>'
        html = prepare_review.render_source_cards(value)
        self.assertNotIn('</script><script>BAD', html)
        self.assertIn('封存候选，尚未正式封存', html)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory)/'synthetic.html'
            file.write_text(html, encoding='utf-8')
            result = subprocess.run(['node', str(Path(__file__).with_name('review_ui_probe.js')), str(file)],
                                    input=json.dumps(value), text=True, capture_output=True, check=True)
        probe = json.loads(result.stdout)
        self.assertEqual(probe['checks'], 7)
        for exported in probe['exports']:
            record = review_io.reconcile_claims(exported, value)
            self.assertFalse(record['formalEvaluationAllowed'])
            self.assertFalse(record['modelExecutionAuthorized'])

    def test_explicit_batch_cli_uses_source_packet_without_changing_default(self):
        value = synthetic_source_packet()
        with tempfile.TemporaryDirectory() as directory:
            file, out = Path(directory)/'qa.json', Path(directory)/'qa-result.json'
            file.write_text(json.dumps(claims(value)))
            with mock.patch.object(sys, 'argv', ['review_io.py', 'reconcile', str(file), '--batch', 'round1-source-cards', '--out', str(out)]), \
                 mock.patch.object(source, 'build_packet', return_value=value), \
                 mock.patch.object(review_io, 'build_packet', side_effect=AssertionError('wrong batch')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(review_io.main(), 0)
            self.assertFalse(json.loads(out.read_text())['humanSemanticApproval'])

    def test_original_page_and_packet_remain_same(self):
        old_packet = review_io.build_packet()
        embedded = source.canonical_bytes(old_packet).decode().replace('<', '\\u003c')
        self.assertEqual(prepare_review.OUT.read_text(), prepare_review.HTML.replace('__PACKET__', embedded))
        self.assertEqual(len(old_packet['cases']), 42)


if __name__ == '__main__':
    unittest.main()
