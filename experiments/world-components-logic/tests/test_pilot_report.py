"""Read-only checks on preserved evidence, plus synthetic rendering probes."""
import copy
from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import pilot_report


class PilotReportTests(unittest.TestCase):
    def test_all_four_runs_and_failed_attempts_are_in_the_report(self):
        report, _ = pilot_report.build()
        self.assertEqual(len(report['runs']), 4)
        self.assertEqual(report['businessGenerationsTotal'], 40)
        self.assertEqual([r['generationCalls'] for r in report['runs']], [0,0,20,20])
        self.assertTrue(all(sum(t['attempts'] for t in r['tasks']) == 20 for r in report['runs']))
        self.assertFalse(report['formalEvaluationAllowed'])
        self.assertFalse(report['semanticQualityApproved'])
        self.assertFalse(report['fullRequestMeasured'])

    def test_timing_summary_keeps_slow_and_invalid_attempts(self):
        rows = [{'caseId': 'qa', 'elapsedMs': value, 'inputTokens': 1,
                 'status': 'invalid_output', 'structureStatus': 'invalid', 'raw': 'QA only'}
                for value in (1.,2.,3.,4.,200.)]
        result = pilot_report.summary(rows)[0]
        self.assertEqual(result['p50Ms'], 3.)
        self.assertEqual(result['p95Ms'], 200.)
        self.assertTrue(result['localBudgetExceeded'])
        self.assertEqual(result['structureValid'], 0)
        self.assertEqual(result['performanceSampleStatus'], 'insufficient_n_for_formal_acceptance')

    def test_runtime_versions_and_historical_limitations_are_separate(self):
        report, _ = pilot_report.build()
        self.assertTrue(all(r['actualRuntime'] is None for r in report['runs'][:3]))
        current = report['runs'][-1]['actualRuntime']
        self.assertEqual(current['torchThreads'], 1)
        self.assertEqual(current['torchInteropThreads'], 1)
        self.assertTrue(current['environmentReverifiedBeforeImport'])

    def test_model_text_is_escaped_in_view_page(self):
        report, _ = pilot_report.build()
        value = copy.deepcopy(report)
        value['runs'][-1]['tasks'][0]['uniqueRawOutputs'] = ['<script>QA_ONLY</script>']
        html = pilot_report.render(value)
        self.assertNotIn('<script>QA_ONLY</script>', html)
        self.assertIn('&lt;script&gt;QA_ONLY&lt;/script&gt;', html)


if __name__ == '__main__': unittest.main()
