"""Source-card engineering checks; synthetic opinions never become approval."""
import contextlib
import copy
import io
import json
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
