"""Shared-window scope, group identity and interruption regression checks."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import m01_shared as shared
import experiment
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


class ExperimentEntryTests(unittest.TestCase):
    def test_status_and_default_do_not_import_models_or_write_plans(self):
        with mock.patch.dict(sys.modules,{'torch':None,'transformers':None}),mock.patch.object(shared,'prepare') as prepare,mock.patch.object(shared,'execute') as execute:
            for args in ([],['status']):
                output=io.StringIO()
                with redirect_stdout(output):self.assertEqual(experiment.main(args),0)
                status=json.loads(output.getvalue());self.assertFalse(status['modelExecutionPerformed'])
                self.assertEqual(status['latestRun'],'m01-shared-dev42-20261102-r3')
            prepare.assert_not_called();execute.assert_not_called()

    def test_prepare_and_execute_delegate_to_the_current_model(self):
        with mock.patch.object(shared,'prepare',return_value=Path('/tmp/new-plan.json')) as prepare,redirect_stdout(io.StringIO()):
            self.assertEqual(experiment.main(['prepare','new-id']),0);prepare.assert_called_once_with('new-id')
        with mock.patch.object(shared,'execute',return_value=3) as execute:
            self.assertEqual(experiment.main(['execute','new-plan.json']),3);execute.assert_called_once_with(Path('new-plan.json'))

    def test_check_stops_on_failure_without_executing_model(self):
        with mock.patch.object(experiment.subprocess,'run',return_value=mock.Mock(returncode=7)) as run,mock.patch.object(shared,'execute') as execute:
            self.assertEqual(experiment.check(),7);self.assertEqual(run.call_count,1);execute.assert_not_called()

    def test_check_runs_only_tests_and_report_verification(self):
        with mock.patch.object(experiment.subprocess,'run',return_value=mock.Mock(returncode=0)) as run,redirect_stdout(io.StringIO()):
            self.assertEqual(experiment.check(),0)
        self.assertEqual(run.call_count,4)
        for call in run.call_args_list:
            args=call.args[0]
            self.assertNotIn('--execute',args);self.assertNotIn('--prepare',args)
            self.assertEqual(call.kwargs['env']['PYTHONDONTWRITEBYTECODE'],'1')


class CommonExecutionTests(unittest.TestCase):
    def setup_plan(self,directory):
        root=Path(directory);path=root/'plan.json';out=root/'record.json'
        plan={'runId':'test-only','config':{'attemptsPerCase':1,'maxResidentMiB':2,'processWallSeconds':120},
              'cases':[{'caseId':'case'}],'environment':{'venvExecutableRelativePath':'test-metadata-only'}}
        path.write_text(json.dumps(plan))
        return plan,path,out

    def execute(self,path,out,**kwargs):
        return experiment.execute_plan(path,paths=lambda run_id:(path,out),verify=kwargs.get('verify',lambda p:None),
             worker_script=Path('/test-metadata-only.py'),settle_stages=kwargs.get('settle_stages',mock.Mock()),arms=('legacy','shared'))

    def child(self):
        child=mock.Mock();child.pid=987654321;child.returncode=-15;child.poll.return_value=None
        child.wait.side_effect=lambda **kwargs:setattr(child.poll,'return_value',child.returncode)
        return child

    def test_stage_exception_is_saved_with_failure_and_elapsed_time(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'stage.json';report={'stages':[]}
            def fail():raise ValueError('synthetic stage failure')
            with self.assertRaisesRegex(ValueError,'synthetic'):
                experiment.record_stage(report,out,'load',fail)
            stage=json.loads(out.read_text())['stages'][0]
            self.assertEqual(stage['status'],'failed');self.assertEqual(stage['error']['type'],'ValueError')
            self.assertGreaterEqual(stage['elapsedMs'],0)

    def test_existing_evidence_is_not_overwritten_or_launched(self):
        with tempfile.TemporaryDirectory() as t:
            _,path,out=self.setup_plan(t);out.write_bytes(b'original evidence');verify=mock.Mock()
            with mock.patch.object(experiment.subprocess,'Popen') as launch:
                with self.assertRaises(FileExistsError):self.execute(path,out,verify=verify)
            self.assertEqual(out.read_bytes(),b'original evidence');verify.assert_not_called();launch.assert_not_called()

    def test_preflight_failure_is_recorded_before_launch(self):
        with tempfile.TemporaryDirectory() as t:
            _,path,out=self.setup_plan(t)
            with mock.patch.object(experiment.subprocess,'Popen') as launch:
                with self.assertRaisesRegex(ValueError,'identity'):
                    self.execute(path,out,verify=mock.Mock(side_effect=ValueError('identity drift')))
            self.assertEqual(json.loads(out.read_text())['status'],'failed_preflight');launch.assert_not_called()

    def test_launch_failure_preserves_every_unstarted_arm(self):
        with tempfile.TemporaryDirectory() as t:
            _,path,out=self.setup_plan(t)
            with mock.patch.object(experiment.subprocess,'Popen',side_effect=OSError('synthetic launch failure')):
                self.assertEqual(self.execute(path,out),1)
            record=json.loads(out.read_text());self.assertEqual(record['status'],'failed_process_launch')
            self.assertEqual(record['unexecutedAttempts'],2)
            self.assertEqual({s['arm'] for s in record['attemptSlots']},{'legacy','shared'})

    def test_success_retains_isolated_single_thread_environment(self):
        with tempfile.TemporaryDirectory() as t:
            plan,path,out=self.setup_plan(t);child=self.child();child.returncode=0;child.poll.return_value=0
            def launched(*args,**kwargs):
                slots=experiment.planned_slots(plan,('legacy','shared'))
                for slot in slots:slot['status']='complete'
                out.write_text(json.dumps({'status':'diagnostic_completed','attempts':slots,'attemptSlots':slots,'activeAttempt':None,'stages':[]}))
                return child
            with mock.patch.object(experiment.subprocess,'Popen',side_effect=launched) as launch,redirect_stdout(io.StringIO()):
                self.assertEqual(self.execute(path,out),0)
            env=launch.call_args.kwargs['env']
            for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):self.assertEqual(env[key],'1')
            self.assertEqual(env['HF_HUB_OFFLINE'],'1');self.assertTrue(launch.call_args.kwargs['start_new_session'])
            self.assertEqual(json.loads(out.read_text())['supervisor']['exitCode'],0)

    def test_memory_cap_stops_child_and_counts_unstarted_slots(self):
        with tempfile.TemporaryDirectory() as t:
            _,path,out=self.setup_plan(t);child=self.child();settle=mock.Mock()
            with mock.patch.object(experiment.subprocess,'Popen',return_value=child),mock.patch.object(experiment.subprocess,'run',return_value=mock.Mock(returncode=0,stdout='3072')),mock.patch.object(experiment.os,'killpg') as kill,redirect_stdout(io.StringIO()):
                self.assertEqual(self.execute(path,out,settle_stages=settle),1)
            record=json.loads(out.read_text());self.assertEqual(record['supervisor']['stopReason'],'resident_memory_limit')
            self.assertEqual(record['unexecutedAttempts'],2);kill.assert_called_once_with(child.pid,experiment.signal.SIGTERM)
            settle.assert_called_once()

    def test_wall_clock_cap_still_applies(self):
        with tempfile.TemporaryDirectory() as t:
            _,path,out=self.setup_plan(t);child=self.child()
            with mock.patch.object(experiment.subprocess,'Popen',return_value=child),mock.patch.object(experiment.subprocess,'run',return_value=mock.Mock(returncode=0,stdout='1024')),mock.patch.object(experiment.time,'monotonic',side_effect=[0,121,122]),mock.patch.object(experiment.os,'killpg'),redirect_stdout(io.StringIO()):
                self.assertEqual(self.execute(path,out),1)
            self.assertEqual(json.loads(out.read_text())['supervisor']['stopReason'],'process_wall_limit')

    def test_monitor_error_is_not_recorded_as_model_success(self):
        with tempfile.TemporaryDirectory() as t:
            _,path,out=self.setup_plan(t);child=self.child()
            with mock.patch.object(experiment.subprocess,'Popen',return_value=child),mock.patch.object(experiment.subprocess,'run',side_effect=PermissionError('synthetic ps denial')),mock.patch.object(experiment.os,'killpg'),redirect_stdout(io.StringIO()):
                self.assertEqual(self.execute(path,out),1)
            record=json.loads(out.read_text());self.assertEqual(record['supervisor']['stopReason'],'supervisor_failure')
            self.assertEqual(record['unexecutedAttempts'],2)

    def test_non_exiting_child_is_force_stopped(self):
        with tempfile.TemporaryDirectory() as t:
            _,path,out=self.setup_plan(t);child=self.child();child.returncode=-9
            child.wait.side_effect=[experiment.subprocess.TimeoutExpired('synthetic child',3),None]
            with mock.patch.object(experiment.subprocess,'Popen',return_value=child),mock.patch.object(experiment.subprocess,'run',return_value=mock.Mock(returncode=0,stdout='3072')),mock.patch.object(experiment.os,'killpg') as kill,redirect_stdout(io.StringIO()):
                self.assertEqual(self.execute(path,out),1)
            self.assertEqual(kill.call_args_list,[mock.call(child.pid,experiment.signal.SIGTERM),mock.call(child.pid,experiment.signal.SIGKILL)])


if __name__=='__main__':unittest.main()
