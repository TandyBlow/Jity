"""Shared-window scope, group identity and interruption regression checks."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import m01_shared as shared
from fact_windows import fact_text,restore


class Tokenizer:
    def encode(self,text,**kwargs):return [ord(c) for c in text]
    def num_special_tokens_to_add(self,pair):return 3
    def build_inputs_with_special_tokens(self,a,b):return [101]+a+[102]+b+[102]
    def create_token_type_ids_from_sequences(self,a,b):return [0]*(len(a)+2)+[1]*(len(b)+1)


class SharedFactTests(unittest.TestCase):
    def test_all_twenty_inputs_have_exact_nonoverlapping_token_spans(self):
        for row in shared.old.dataset()[0]:
            case=row['case'];value,facts,windows=shared.pack(case,Tokenizer())
            self.assertEqual(restore(facts),case['input'])
            self.assertEqual([s['factIndex'] for w in windows for s in w['factSpans']],list(range(len(facts))))
            for w in windows:
                self.assertLessEqual(w['totalTokens'],512)
                for s in w['factSpans']:
                    self.assertEqual(w['inputIds'][s['start']:s['end']],Tokenizer().encode(fact_text(facts[s['factIndex']])))

    def test_candidate_identity_pools_include_every_character_field(self):
        for row in shared.old.dataset()[0]:
            c=row['case'];_,facts,_=shared.pack(c,Tokenizer());targets,anchor,pools=shared.pool_indices(c,facts)
            expected=[c['input']['actorId']] if c['task']=='D02' else c['input']['candidateIds']
            self.assertEqual(targets,expected)
            for target,indices in zip(targets,pools):
                ix=next(i for i,p in enumerate(c['input']['world']['characters']) if p['id']==target)
                self.assertEqual(indices,[i for i,f in enumerate(facts) if f['path'][:3]==['world','characters',ix]])

    def test_no_target_filtering_by_acted_status(self):
        c=next(r['case'] for r in shared.old.dataset()[0] if r['case']['task']=='D03')
        c=copy.deepcopy(c);c['input']['alreadyActedIds']=c['input']['candidateIds'].copy()
        _,facts,_=shared.pack(c,Tokenizer());targets,_,_=shared.pool_indices(c,facts)
        self.assertEqual(targets,c['input']['candidateIds'])

    def test_labels_never_change_input_windows_or_identity_pools(self):
        row=next(r for r in shared.old.dataset()[0] if r['case']['task']=='D03');other=copy.deepcopy(row)
        other['label']=[] if row['label'] else ['not-a-model-input']
        self.assertEqual(shared.pack(row['case'],Tokenizer()),shared.pack(other['case'],Tokenizer()))

    def test_single_long_fact_is_rejected_not_truncated(self):
        c=copy.deepcopy(shared.old.dataset()[0][0]['case']);c['input']['world']['characters'][0]['appearance']='长'*1000
        with self.assertRaisesRegex(ValueError,'atomic fact'):shared.pack(c,Tokenizer())

    def test_prefix_does_not_depend_on_current_candidate(self):
        c=next(r['case'] for r in shared.old.dataset()[0] if r['case']['task']=='D03')
        other=copy.deepcopy(c);other['input']['candidateIds'].reverse()
        self.assertEqual(shared.shared_prefix(c),shared.shared_prefix(other))


class SharedPlanTests(unittest.TestCase):
    def setUp(self):
        rows,_=shared.old.dataset();oldplan=shared.read_json(shared.OLD_PLAN)
        self.baseline={'datasetSha256':shared.digest(rows),'model':oldplan['model'],'checkpoint':{'sha256':'test-only'}}
        self.patches=[mock.patch.object(shared,'baseline_identity',side_effect=lambda:copy.deepcopy(self.baseline)),
                      mock.patch.object(shared.old,'model_identity',return_value=oldplan['model']),
                      mock.patch.object(shared,'observe_environment',return_value={'device':'metadata-only'})]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def plan(self):
        captured=[]
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(shared.old,'paths',return_value=(Path(t)/'p.json',Path(t)/'r.json')),mock.patch.object(shared,'exclusive',side_effect=lambda p,v:captured.append(v)):
                shared.prepare('qa-only')
        return captured[0]

    def test_exact_old_split_and_exposed_development_status_are_bound(self):
        p=self.plan();shared.verify(p)
        self.assertEqual(len(p['dataset']),20);self.assertEqual(len(p['cases']),4)
        self.assertTrue(p['retainedDevelopmentPreviouslyObserved']);self.assertFalse(p['formalEvaluationAllowed'])
        self.assertEqual(p['round1TrainingQuota'],0);self.assertEqual(p['newIndependentTrainingGroups'],0)

    def test_rehashed_resource_or_threshold_changes_are_rejected(self):
        for k,v in {'threads':2,'threshold':.1,'fusionWidth':64,'featureCacheForTiming':True,'processWallSeconds':3600}.items():
            p=self.plan();p['config'][k]=v;p['configSha256']=shared.digest(p['config'])
            with self.assertRaisesRegex(ValueError,'policy'):shared.verify(p)

    def test_baseline_and_case_substitution_are_rejected(self):
        p=self.plan();p['baseline']['checkpoint']['sha256']='bad'
        with self.assertRaisesRegex(ValueError,'baseline'):shared.verify(p)
        p=self.plan();p['cases']=[r['case'] for r in p['dataset'] if r['role']=='fit'][:4]
        with self.assertRaisesRegex(ValueError,'cases/arms'):shared.verify(p)

    def test_source_file_identity_cannot_be_omitted(self):
        p=self.plan();p['code'].pop(next(iter(p['code'])))
        with self.assertRaisesRegex(ValueError,'code identity'):shared.verify(p)


class SharedInterruptionTests(unittest.TestCase):
    def test_stop_before_child_journal_keeps_all_forty_unstarted_slots(self):
        plan={'config':{'attemptsPerCase':5},'cases':[{'caseId':str(i)} for i in range(4)]}
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'plan.json';p.write_text(json.dumps(plan))
            r=shared.unstarted_record(plan,p)
        self.assertEqual(len(r['attemptSlots']),40);self.assertEqual(r['unexecutedAttempts'],40)
        self.assertEqual(len({(x['arm'],x['caseId'],x['repeat']) for x in r['attemptSlots']}),40)

    def test_interrupted_shared_arm_does_not_replace_completed_legacy_slot(self):
        done={'arm':'legacy','caseId':'case','repeat':0,'status':'complete'}
        active={'arm':'shared','caseId':'case','repeat':0,'status':'started','startedMonotonicNs':time.monotonic_ns()-1000000}
        report={'attempts':[done.copy()],'attemptSlots':[done.copy(),active.copy()], 'activeAttempt':active}
        shared.settle_attempts(report,'supervisor_failure')
        self.assertEqual(len(report['attempts']),2)
        self.assertEqual(report['attemptSlots'][0],done)
        self.assertEqual(report['attemptSlots'][1]['status'],'interrupted')
        self.assertGreater(report['attemptSlots'][1]['elapsedMs'],0)

    def test_window_failure_stream_preserves_partial_line_and_settles_started_window(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'e.jsonl';event={'eventId':1,'status':'running','startedMonotonicNs':time.monotonic_ns()-1000000}
            path.write_text(json.dumps(event)+'\n{"partial":',encoding='utf-8');report={}
            shared.settle_events(report,path,'process_wall_limit')
            self.assertEqual(report['windowEventMalformedLines'],[1])
            self.assertIn('{"partial":',path.read_text())
            settled=json.loads(path.read_text().splitlines()[-1]);self.assertEqual(settled['status'],'interrupted')


if __name__=='__main__':unittest.main()
