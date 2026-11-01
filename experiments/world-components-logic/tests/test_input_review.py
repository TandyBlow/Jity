"""Synthetic review claims test bookkeeping, never project approval."""
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
import prepare_input_review as page
import prepare_round1
import review_io
from test_review import packet, claims


def synthetic_packet():
    value = packet()
    value['materialKind'] = 'expanded_input_draft'
    for c in value['cases']:
        original = c['input']
        c['input'] = {'sourceCard': {'title': 'QA only', 'facts': '仅工程夹具', 'question': '测试保存'},
                      'taskCases': [{'case': {'caseId': c['caseId'], 'input': original},
                                     'supplement': {'assumptions': ['合成夹具']},
                                     'check': {'guard': {'reason': 'ready'}}}],
                      'chainPlans': [], 'auxiliaryProbes': []}
    return value


class InputReviewTests(unittest.TestCase):
    def test_each_source_card_binds_all_its_new_context(self):
        p = page.build_packet()
        self.assertEqual(len(p['cases']), 90)
        self.assertEqual(sum(len(c['input']['taskCases']) for c in p['cases']), 84)
        self.assertEqual(sum(len(c['input']['chainPlans']) for c in p['cases']), 10)
        self.assertEqual(sum(len(c['input']['auxiliaryProbes']) for c in p['cases']), 2)
        for c in p['cases']:
            self.assertEqual(c['inputSha256'], page.sha(c['input']))
            self.assertEqual(c['reviewSha256'], page.sha(c['review']))
        c = copy.deepcopy(p['cases'][0])
        c['input']['auxiliaryProbes'][0]['case']['input']['world']['time'] = 'changed'
        self.assertNotEqual(page.sha(c['input']), c['inputSha256'])
        self.assertFalse(p['modelExecutionAuthorized'])

    def test_old_card_batch_is_not_the_complete_input_batch(self):
        old, new = prepare_round1.build_packet(), page.build_packet()
        for key in ('inputSha256', 'reviewDraftSha256', 'provenanceSha256'):
            self.assertNotEqual(old[key], new[key])
        old_by_id = {c['caseId']: c for c in old['cases']}
        self.assertTrue(all(c['inputSha256'] != old_by_id[c['caseId']]['inputSha256'] for c in new['cases']))

    def test_changed_material_cannot_silently_generate_a_review_page(self):
        files, _ = page.inputs.build_files()
        path = page.inputs.DATA / 'chain-plans.jsonl'
        files[path] += b'changed'
        with mock.patch.object(page.inputs, 'build_files', return_value=(files, {})):
            with self.assertRaisesRegex(ValueError, '版本不匹配'):
                page.build_packet()

    def test_new_view_preserves_synthetic_save_and_export_behavior(self):
        p = synthetic_packet()
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp)/'qa.html'
            html.write_text(page.render(p), encoding='utf-8')
            result = subprocess.run(['node', str(BASE/'tests/review_ui_probe.js'), str(html)],
                                    input=json.dumps(p), capture_output=True, text=True, check=True)
        output = json.loads(result.stdout)
        self.assertEqual(output['checks'], 7)
        for claim in output['exports']:
            self.assertFalse(review_io.reconcile_claims(claim, p)['humanSemanticApproval'])

    def test_html_data_escapes_executable_markup(self):
        p = synthetic_packet()
        p['cases'][0]['input']['sourceCard']['facts'] = '</script><script>alert(1)</script>'
        html = page.render(p)
        self.assertNotIn('</script><script>alert(1)', html)
        self.assertIn('\\u003c/script>', html)

    def test_explicit_cli_batch_uses_the_complete_input_packet(self):
        p = synthetic_packet()
        with tempfile.TemporaryDirectory() as tmp:
            raw, out = Path(tmp)/'qa.json', Path(tmp)/'new.json'
            raw.write_text(json.dumps(claims(p)))
            args = ['review_io.py', 'reconcile', str(raw), '--batch', 'round1-inputs', '--out', str(out)]
            with mock.patch.object(sys, 'argv', args), mock.patch.object(page, 'build_packet', return_value=p), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(review_io.main(), 0)
            result = json.loads(out.read_text())
            self.assertFalse(result['modelExecutionAuthorized'])
            self.assertEqual(result['summary']['recorded'], 1)


if __name__ == '__main__':
    unittest.main()
