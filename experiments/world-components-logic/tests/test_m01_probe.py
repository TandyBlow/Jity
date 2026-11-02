"""Window, split and identity checks; never fit or load a real model here."""
import copy
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import fact_windows as fw
import m01_probe as probe
import review_io
from lab import canonical_bytes


class Tokenizer:
    def encode(self,text,**kwargs):return list(text.encode('utf-8'))
    def num_special_tokens_to_add(self,pair):return 3
    def build_inputs_with_special_tokens(self,a,b):return [101]+a+[102]+b+[102]
    def create_token_type_ids_from_sequences(self,a,b):return [0]*(len(a)+2)+[1]*(len(b)+1)


class FactWindowTests(unittest.TestCase):
    def test_all_original_42_inputs_restore_with_exact_bytes(self):
        for case in review_io.build_packet()['cases']:
            facts=fw.flatten(case['input'])
            self.assertEqual(canonical_bytes(fw.restore(facts)),canonical_bytes(case['input']))

    def test_null_empty_container_boolean_and_order_survive(self):
        value={'a':[None,False,{},[],{'x':True}],'b':{'empty':[]}}
        self.assertEqual(fw.restore(fw.flatten(value)),value)

    def test_windows_keep_every_whole_fact_and_all_tokens(self):
        value={'text':['字段内容'+str(i) for i in range(12)],'flag':False}
        tok=Tokenizer();prefix='当前候选=a';facts,windows=fw.make_windows(value,tok,prefix,150)
        self.assertGreater(len(windows),1)
        self.assertEqual([i for w in windows for i in w['factIds']],list(range(len(facts))))
        for w in windows:
            self.assertLessEqual(w['totalTokens'],150)
            expected=[token for i in w['factIds'] for token in tok.encode(fw.fact_text(facts[i]))]
            self.assertEqual(w['inputIds'][len(tok.encode(prefix))+2:-1],expected)
            self.assertEqual(len(w['inputIds']),len(w['tokenTypeIds']))

    def test_one_long_fact_is_rejected_instead_of_cut(self):
        with self.assertRaisesRegex(ValueError,'atomic fact'):
            fw.make_windows({'text':'长原文'*100},Tokenizer(),'p',100)

    def test_prefix_overflow_is_not_hidden(self):
        with self.assertRaisesRegex(ValueError,'prefix'):
            fw.make_windows({'a':1},Tokenizer(),'p'*100,50)

    def test_duplicate_missing_and_overlapping_fact_paths_are_rejected(self):
        for facts in ([{'path':['a'],'value':1},{'path':['a'],'value':2}],
                      [{'path':['a',1],'value':'gap'}],
                      [{'path':['a'],'value':[]},{'path':['a',0],'value':1}]):
            with self.assertRaises(ValueError):fw.restore(facts)


class FittingPlanTests(unittest.TestCase):
    def setUp(self):
        self.patches=[mock.patch.object(probe,'model_identity',return_value={'modelId':'QA_METADATA_ONLY'}),
                      mock.patch.object(probe,'observe_environment',return_value={'python':'QA_METADATA_ONLY'})]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()

    def test_existing_reviewed_groups_are_not_new_or_round1_groups(self):
        rows,review=probe.dataset()
        self.assertEqual(len(rows),20)
        self.assertEqual(len({r['case']['sourceGroup'] for r in rows}),20)
        for task in ('D02','D03'):
            selected=[r for r in rows if r['case']['task']==task]
            self.assertEqual(sum(r['role']=='fit' for r in selected),8)
            self.assertEqual(sum(r['role']=='retained_development' for r in selected),2)
        self.assertTrue(all(r['case']['caseId'].startswith('dev-') for r in rows))
        self.assertTrue(all('label' not in r['case']['input'] for r in rows))

    def test_candidate_labels_cover_the_complete_roster_without_filtering_acted(self):
        rows,_=probe.dataset()
        for row in rows:
            if row['case']['task']=='D03':
                self.assertEqual(len(probe.labels(row)),len(row['case']['input']['candidateIds']))
                self.assertEqual({p['id'] for p in row['case']['input']['world']['characters']},set(row['case']['input']['candidateIds']))

    def test_split_is_deterministic_and_has_no_group_overlap(self):
        a,_=probe.dataset();b,_=probe.dataset();self.assertEqual(a,b)
        fit={r['case']['sourceGroup'] for r in a if r['role']=='fit'}
        dev={r['case']['sourceGroup'] for r in a if r['role']!='fit'}
        self.assertFalse(fit&dev)

    def test_label_never_enters_prefix_or_fact_encoder(self):
        row=probe.dataset()[0][0];changed=copy.deepcopy(row);changed['label']='changed-only-in-supervision'
        self.assertEqual(probe.prefix(row['case']),probe.prefix(changed['case']))
        self.assertEqual(fw.flatten(row['case']['input']),fw.flatten(changed['case']['input']))

    def prepared(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'new.plan.json';out=Path(tmp)/'new.record.json'
            captured=[]
            with mock.patch.object(probe,'paths',return_value=(path,out)),mock.patch.object(probe,'exclusive',side_effect=lambda p,v:captured.append(v)):
                probe.prepare('qa-only')
            return captured[0]

    def test_new_training_and_threshold_claims_remain_unapproved(self):
        p=self.prepared()
        self.assertEqual(p['newIndependentTrainingGroups'],0)
        self.assertEqual(p['round1TrainingQuota'],0)
        self.assertFalse(p['formalEvaluationAllowed'])
        self.assertEqual(p['config']['threshold'],.5)
        self.assertFalse(p['config']['featureCacheForTiming'])
        self.assertEqual(len(p['cases']),4)

    def test_label_split_environment_or_scope_drift_is_rejected(self):
        p=self.prepared();probe.verify(p)
        bad=copy.deepcopy(p);bad['dataset'][0]['role']='retained_development'
        with self.assertRaisesRegex(ValueError,'data/label/split'):probe.verify(bad)
        bad=copy.deepcopy(p);bad['formalEvaluationAllowed']=True
        with self.assertRaisesRegex(ValueError,'scope'):probe.verify(bad)
        bad=copy.deepcopy(p);bad['cases']=[r['case'] for r in bad['dataset'] if r['role']=='fit'][:4]
        with self.assertRaisesRegex(ValueError,'retained development'):probe.verify(bad)
        with mock.patch.object(probe,'observe_environment',return_value={}):
            with self.assertRaisesRegex(ValueError,'environment'):probe.verify(p)

    def test_rehashed_policy_still_cannot_raise_caps_or_use_dev_selection(self):
        p=self.prepared()
        for key,value in {'concurrency':2,'processWallSeconds':3600,'maxResidentMiB':4096,
                          'attemptsPerCase':1000,'earlyStopping':True,'featureCacheForTiming':True}.items():
            bad=copy.deepcopy(p);bad['config'][key]=value;bad['configSha256']=probe.digest(bad['config'])
            with self.assertRaisesRegex(ValueError,'policy'):probe.verify(bad)

    def test_supervisor_settles_active_fit_stage_and_window_after_exit(self):
        started=time.monotonic_ns()-10_000_000
        forward={'status':'running','forwardIndex':0,'startedMonotonicNs':started}
        report={'stages':[{'stage':'fit','status':'running','startedMonotonicNs':started}],
                'forwardAttempts':[forward],'activeForward':forward}
        probe.settle_stages(report,'resident_memory_limit')
        self.assertEqual(report['stages'][0]['status'],'interrupted')
        self.assertEqual(report['forwardAttempts'][0]['status'],'interrupted')
        self.assertGreater(report['stages'][0]['elapsedMs'],0)
        self.assertIsNone(report['activeForward'])


if __name__=='__main__':unittest.main()
