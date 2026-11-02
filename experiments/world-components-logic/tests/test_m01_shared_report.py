"""Tamper checks on archived evidence only; never load model dependencies."""
import copy
import gzip
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import m01_shared_report as report


class SharedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data=report.DATA;run=report.PREFIX+'r3'
        cls.plan=json.loads((data/(run+'.plan.json')).read_bytes())
        cls.record=report.read_archive(data/(run+'.record.json.gz'))
        cls.events=[json.loads(x) for x in gzip.decompress((data/(run+'.record.windows.jsonl.gz')).read_bytes()).splitlines()]
        cls.baseline=report.read_archive(report.shared.OLD_RECORD)

    def check(self,plan=None,record=None,events=None):
        return report.validate_run(plan or self.plan,record or self.record,events or self.events,self.baseline)

    def test_complete_archives_rebuild_and_do_not_promote_scope(self):
        s,files=report.build()
        self.assertFalse(s['formalEvaluationAllowed']);self.assertFalse(s['semanticQualityApproved'])
        self.assertEqual(s['fullRequest500msStatus'],'unverified')
        self.assertEqual(s['runs'][-1]['quality']['D03']['retained_development'],
                         {'matched':1,'groups':2,'requiredTargets':2,'missedTargets':0,'extraTargets':2})
        self.assertEqual(s['firstStartFailure']['plannedUnstartedItems'],40)
        for path,raw in files.items():self.assertEqual(path.read_bytes(),raw)

    def test_duplicate_or_omitted_inference_slots_are_rejected(self):
        r=copy.deepcopy(self.record);r['attempts'][0]=copy.deepcopy(r['attempts'][1])
        with self.assertRaisesRegex(ValueError,'attempt identity'):self.check(record=r)

    def test_cached_timing_cannot_be_presented_as_fresh(self):
        r=copy.deepcopy(self.record);r['attempts'][0]['featureCacheUsed']=True
        with self.assertRaisesRegex(ValueError,'cached'):self.check(record=r)

    def test_changed_prediction_is_not_hidden_by_quality_summary(self):
        r=copy.deepcopy(self.record);r['attempts'][0]['probabilities']=[.123]
        with self.assertRaisesRegex(ValueError,'prediction changed'):self.check(record=r)

    def test_candidate_omission_is_rejected(self):
        c=copy.deepcopy(self.record['featureCoverage'][0]['coverage']);c['targets']=[]
        cid=self.record['featureCoverage'][0]['caseId'];case=next(r['case'] for r in self.plan['dataset'] if r['case']['caseId']==cid)
        with self.assertRaisesRegex(ValueError,'candidate coverage'):report.validate_coverage(case,c,'shared')

    def test_fact_span_gap_is_rejected(self):
        r=copy.deepcopy(self.record);r['featureCoverage'][0]['coverage']['windows'][0]['factSpans'][1]['start']+=1
        with self.assertRaisesRegex(ValueError,'span gap'):self.check(record=r)

    def test_unpaired_or_wrong_arm_forward_is_rejected(self):
        events=copy.deepcopy(self.events);events.pop()
        with self.assertRaisesRegex(ValueError,'forward events'):self.check(events=events)
        events=copy.deepcopy(self.events);events[0]['arm']='legacy'
        with self.assertRaisesRegex(ValueError,'forward scope'):self.check(events=events)

    def test_formal_scope_and_original_label_changes_are_rejected(self):
        p=copy.deepcopy(self.plan);p['formalEvaluationAllowed']=True
        with self.assertRaisesRegex(ValueError,'formal scope'):self.check(plan=p)
        r=copy.deepcopy(self.record);r['fitAndDevelopmentPredictions'][0]['label']='fake'
        with self.assertRaisesRegex(ValueError,'label/split'):self.check(record=r)

    def test_changed_current_source_uses_the_exact_executed_git_revision(self):
        name='experiments/world-components-logic/m01_shared.py';expected=self.plan['code'][name]
        raw=report.subprocess.check_output(['git','show',report.EXECUTED_COMMIT+':'+name],cwd=report.ROOT)
        with mock.patch.object(report,'sha256_file',return_value='changed-current-code'),mock.patch.object(report.subprocess,'check_output',return_value=raw) as git:
            report.executed_source(name,expected,'r3')
            self.assertEqual(git.call_args.args[0],['git','show',report.EXECUTED_COMMIT+':'+name])
        with mock.patch.object(report,'sha256_file',return_value='changed-current-code'),mock.patch.object(report.subprocess,'check_output',return_value=b'wrong historical bytes'):
            with self.assertRaisesRegex(ValueError,'identity mismatch'):report.executed_source(name,expected,'r3')

    def test_missing_git_history_is_explicit_and_never_accepted(self):
        error=report.subprocess.CalledProcessError(128,['git','show'])
        with mock.patch.object(report,'sha256_file',return_value='changed-current-code'),mock.patch.object(report.subprocess,'check_output',side_effect=error):
            with self.assertRaisesRegex(ValueError,'historical source unavailable'):
                report.executed_source('experiments/world-components-logic/m01_shared.py','expected','r3')


class EventDepthReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data=report.DATA;run=report.EVENT_RUN
        cls.plan=json.loads((data/(run+'.plan.json')).read_bytes())
        cls.record=report.read_archive(data/(run+'.record.json.gz'))
        cls.events=[json.loads(x) for x in gzip.decompress((data/(run+'.record.windows.jsonl.gz')).read_bytes()).splitlines()]
        cls.baseline=report.read_archive(report.EVENT_BASELINE_RECORD)

    def check(self,plan=None,record=None,events=None):
        return report.validate_event_run(plan or self.plan,record or self.record,events or self.events,self.baseline)

    def test_all_sixty_attempts_and_406_windows_validate_without_scope_promotion(self):
        self.assertEqual(self.check(),406)
        summary,files=report.build_event()
        self.assertFalse(summary['semanticQualityApproved']);self.assertFalse(summary['formalEvaluationAllowed'])
        self.assertEqual(summary['fullRequest500msStatus'],'unverified')
        for p,raw in files.items():self.assertEqual(p.read_bytes(),raw)

    def test_omitted_candidate_or_changed_action_anchor_is_rejected(self):
        for key,value in (('targets',[]),('eventAnchorFactIds',[])):
            r=copy.deepcopy(self.record);r['featureCoverage'][0]['coverage'][key]=value
            with self.assertRaises(ValueError):self.check(record=r)

    def test_omitted_end_journal_cost_is_rejected(self):
        r=copy.deepcopy(self.record);r['attempts'][0]['elapsedIncludingEndJournalMs']=r['attempts'][0]['elapsedMs']
        with self.assertRaisesRegex(ValueError,'inclusive timing'):self.check(record=r)

    def test_baseline_drift_cached_inference_and_dropped_arm_are_rejected(self):
        for mutate in (lambda r:r['attempts'].pop(),
                       lambda r:r['attempts'][0].update(featureCacheUsed=True),
                       lambda r:r['attempts'][0].update(probabilities=[.9])):
            r=copy.deepcopy(self.record);mutate(r)
            with self.assertRaises(ValueError):self.check(record=r)

    def test_wrong_depth_and_missing_training_steps_are_rejected(self):
        r=copy.deepcopy(self.record);r['encoderVariants']['event2']['layers']=1
        with self.assertRaisesRegex(ValueError,'layer count'):self.check(record=r)
        r=copy.deepcopy(self.record);r['fitLosses']['event2']['D03'].pop()
        with self.assertRaisesRegex(ValueError,'loss/step'):self.check(record=r)

    def test_relabeling_or_replacing_a_source_group_is_rejected(self):
        p=copy.deepcopy(self.plan);p['dataset'][0]['label']='changed'
        with self.assertRaisesRegex(ValueError,'source groups'):self.check(plan=p)

    def test_missing_or_changed_window_event_is_rejected(self):
        es=copy.deepcopy(self.events);es.pop()
        with self.assertRaisesRegex(ValueError,'event count'):self.check(events=es)
        es=copy.deepcopy(self.events);es[0]['inputIds']=[101,102]
        with self.assertRaisesRegex(ValueError,'payload'):self.check(events=es)

    def test_late_source_resolution_requires_matching_historical_bytes(self):
        with mock.patch.object(report,'sha256_file',return_value='new-code'),mock.patch.object(report.subprocess,'check_output',side_effect=['revision',b'not-the-executed-bytes']):
            with self.assertRaisesRegex(ValueError,'unavailable'):
                report.verify_event_source('experiments/world-components-logic/m01_shared.py','expected')


if __name__=='__main__':unittest.main()
