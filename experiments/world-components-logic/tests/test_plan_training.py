"""Training isolation, data identity and actual synthetic autograd checks."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import plan_training as trainer
from lab import guard_case


class Tokenizer:
    eos_token_id=1;pad_token_id=0
    def __init__(self):self.calls=[]
    def encode(self,text,**kwargs):
        self.calls.append((text,kwargs));return [2+ord(c)%97 for c in text]+[1]


class TrainingPreparationTests(unittest.TestCase):
    def setUp(self):self.rows=trainer.candidate_rows()
    def claims(self):
        return {'schema':'jity-d-realizer-training-review-v1','batchId':trainer.BATCH,
            'packetSha256':trainer.packet_identity(self.rows),'reviewer':'synthetic test receipt, no actual review',
            'decisions':[{'annotationId':r['annotationId'],'annotationSha256':trainer.digest(r),
                          'decision':'agree','note':'unit fixture only'} for r in self.rows]}

    def test_twelve_new_groups_are_disjoint_and_cover_each_cell_on_both_sides(self):
        self.assertEqual(len(self.rows),12);self.assertEqual(len({r['sourceGroup'] for r in self.rows}),12)
        for coverage in {r['coverage'] for r in self.rows}:
            self.assertEqual({r['role'] for r in self.rows if r['coverage']==coverage},{'train_candidate','development_candidate'})
            self.assertEqual(sum(r['coverage']==coverage for r in self.rows),2)
        self.assertTrue(all(not r['trainingEligible'] and r['sourceIndependence']=='unverified' for r in self.rows))

    def test_all_authored_worlds_and_typed_plans_are_structurally_valid(self):
        for r in self.rows:
            self.assertTrue(guard_case(r['sourceCase'])['shouldCall'])
            check=trainer.contract.validate_candidate(r['sourceCase'],r['planDraft'])
            self.assertFalse(check['semanticApproved']);self.assertEqual(check['sourceInputSha256'],r['sourceInputSha256'])
            self.assertEqual(trainer.digest(r['expressionDraft']),r['expressionSha256'])

    def test_realizer_input_contains_plan_facts_but_not_reference_sentence(self):
        for r in self.rows:
            x=trainer.input_text(r);self.assertNotIn(r['expressionDraft'],x)
            self.assertNotIn('expressionDraft',x);self.assertNotIn('sourceIndependence',x)
            payload=trainer.realizer_payload(r)
            self.assertEqual(len(payload['计划']),len(r['planDraft']['steps']))
            for a,b in zip(payload['计划'],r['planDraft']['steps']):self.assertEqual(a['动作'],b['verb'])

    def test_no_reviews_cannot_create_a_training_plan_or_load_models(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'claims.json';p.write_text('null')
            with mock.patch.object(trainer,'observe_m02') as model,mock.patch.object(trainer.old,'paths') as paths:
                with self.assertRaisesRegex(ValueError,'not fully reviewed'):trainer.training_plan('never-created',p)
                model.assert_not_called();paths.assert_not_called()

    def test_old_reviews_and_old_plan_reviews_are_rejected(self):
        for schema in ('jity-d-user-review-claims-v1','jity-d-action-plan-review-claims-v1'):
            claims=self.claims();claims['schema']=schema
            with self.assertRaisesRegex(ValueError,'batch drift'):trainer.reconcile_reviews(self.rows,claims)

    def test_packet_changed_reference_or_split_invalidates_review(self):
        claims=self.claims()
        for field in ('expressionDraft','role'):
            rows=copy.deepcopy(self.rows);rows[0][field]='changed'
            with self.assertRaisesRegex(ValueError,'batch drift'):trainer.reconcile_reviews(rows,claims)
        claims=self.claims();claims['decisions'][0]['annotationSha256']='changed'
        with self.assertRaisesRegex(ValueError,'identity drift'):trainer.reconcile_reviews(self.rows,claims)

    def test_partial_duplicate_and_uncertain_reviews_do_not_open_training(self):
        claims=self.claims();claims['decisions'].pop();self.assertFalse(trainer.reconcile_reviews(self.rows,claims)['trainingDataReady'])
        claims=self.claims();claims['decisions'].append(claims['decisions'][0])
        with self.assertRaisesRegex(ValueError,'identity drift'):trainer.reconcile_reviews(self.rows,claims)
        claims=self.claims();claims['decisions'][0].update(decision='uncertain',note='needs checking')
        self.assertFalse(trainer.reconcile_reviews(self.rows,claims)['trainingDataReady'])

    def test_assistant_cannot_self_sign_labels(self):
        c=self.claims();c['reviewer']='assistant'
        with self.assertRaisesRegex(ValueError,'human reviewer'):trainer.reconcile_reviews(self.rows,c)

    def test_complete_synthetic_claims_preserve_six_train_six_dev_only(self):
        train,dev=trainer.reviewed_data(self.claims())
        self.assertEqual(len(train),6);self.assertEqual(len(dev),6)
        self.assertFalse({r['sourceGroup'] for r in train}&{r['sourceGroup'] for r in dev})
        self.assertFalse(trainer.reconcile_reviews(self.rows,self.claims())['formalEvaluationAllowed'])

    def test_tokenization_retains_complete_separate_input_and_target(self):
        tokenizer=Tokenizer();row=self.rows[0]
        encoded=trainer.tokenize_example(tokenizer,row,{**trainer.CONFIG,'maxInputTokens':10000,'maxTargetTokens':10000})
        self.assertEqual([x[0] for x in tokenizer.calls],[trainer.input_text(row),row['expressionDraft']])
        self.assertTrue(all(x[1]=={'add_special_tokens':True,'truncation':False} for x in tokenizer.calls))
        self.assertEqual(encoded['labels'][-1],1);self.assertEqual(encoded['sourceGroup'],row['sourceGroup'])

    def test_source_target_overflow_and_missing_eos_fail_without_truncation(self):
        for key in ('maxInputTokens','maxTargetTokens'):
            config={**trainer.CONFIG,'maxInputTokens':10000,'maxTargetTokens':10000,key:2}
            with self.assertRaisesRegex(ValueError,'exceeds'):trainer.tokenize_example(Tokenizer(),self.rows[0],config)
        tok=Tokenizer();tok.eos_token_id=999
        with self.assertRaisesRegex(ValueError,'EOS'):trainer.tokenize_example(tok,self.rows[0],{**trainer.CONFIG,'maxInputTokens':10000,'maxTargetTokens':10000})

    def test_inspection_never_counts_as_project_training(self):
        result=trainer.observed_inspection();self.assertEqual(result['sourceModelForwardCalls'],0)
        self.assertEqual(result['sourceParameters'],77440384);self.assertEqual(result['adapterModules'],48)
        self.assertEqual(result['trainableAdapterParameters'],172032)
        self.assertEqual(result['totalInferenceParameters'],77612416)
        self.assertEqual(result['syntheticNumericCheck']['projectModelTrainingSteps'],0)

    def test_training_verify_rejects_scope_before_dependencies(self):
        with self.assertRaisesRegex(ValueError,'scope/config'):trainer.verify_training({'purpose':'unreviewed','config':{},'formalEvaluationAllowed':False})

    def test_current_materials_have_zero_eligible_labels_and_no_business_model_calls(self):
        summary,files=trainer.build_materials()
        self.assertEqual(summary['review']['missingReviews'],12);self.assertFalse(summary['review']['trainingDataReady'])
        self.assertEqual(summary['trainingSteps'],0);self.assertEqual(summary['businessInferenceCalls'],0)
        self.assertFalse(summary['plannerModelImplemented']);self.assertFalse(summary['realizerTrained'])
        self.assertTrue(summary['realizerTrainerImplemented']);self.assertEqual(len(files),4)

    def test_original_candidate_materials_remain_exact_after_trainer_extension(self):
        _,files=trainer.build_materials()
        for path,raw in files.items():self.assertEqual(path.read_bytes(),raw,str(path))

    def test_smoke_plan_freezes_only_two_numeric_fixtures_and_no_business_labels(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'plan.json'
            with mock.patch.object(trainer.old,'paths',return_value=(path,Path(d)/'record.json')),mock.patch.object(trainer,'observe_m02',return_value={'allSixFilesFullyRehashedAndVerified':True}),mock.patch.object(trainer,'observe_environment',return_value={'registeredVersionsMatch':True}):
                trainer.inspection_plan('unit-fixture',smoke=True);plan=json.loads(path.read_text())
                trainer.verify_inspection(plan)
        self.assertEqual(plan['syntheticExamples'],list(trainer.SYNTHETIC_EXAMPLES));self.assertEqual(plan['config']['steps'],2)
        self.assertEqual(plan['businessSourceGroups'],0);self.assertEqual(plan['businessTrainingSteps'],0)
        self.assertEqual(plan['businessInferenceCalls'],0);self.assertNotIn('reviewClaims',plan)

    def test_changed_synthetic_tokens_or_business_counts_fail_before_model_verification(self):
        plan={'purpose':'real_m02_synthetic_training_save_reload_only','config':trainer.SMOKE_CONFIG,
              'formalEvaluationAllowed':False,'protocolSha256':trainer.sha256_file(trainer.SMOKE_PROTOCOL),
              'syntheticExamples':copy.deepcopy(list(trainer.SYNTHETIC_EXAMPLES)),'syntheticExamplesSha256':trainer.digest(list(trainer.SYNTHETIC_EXAMPLES)),
              'syntheticOptimizerSteps':2,'businessSourceGroups':0,'businessTrainingSteps':0,'businessInferenceCalls':0,
              'adapterScope':'disposable_synthetic_fixture_never_business_inference','schema':'jity-d-realizer-smoke-plan-v1',
              'arms':['smoke'],'cases':[{'caseId':'m02-synthetic-training-smoke'}]}
        for key,value in (('businessTrainingSteps',1),('businessInferenceCalls',1),('arms',['fit']),('syntheticOptimizerSteps',80)):
            bad=copy.deepcopy(plan);bad[key]=value
            with mock.patch.object(trainer,'observe_m02') as model:
                with self.assertRaisesRegex(ValueError,'scope drift'):trainer.verify_inspection(bad)
                model.assert_not_called()
        bad=copy.deepcopy(plan);bad['syntheticExamples'][0]['labels'][0]=999
        with self.assertRaisesRegex(ValueError,'scope drift'):trainer.verify_inspection(bad)

    def test_missing_historical_source_is_not_silently_accepted(self):
        with mock.patch.object(trainer.subprocess,'check_output',return_value=''):
            with self.assertRaisesRegex(ValueError,'unavailable'):trainer.verify_historical_file(trainer.BASE/'does-not-exist.py','0'*64)

    def test_smoke_entry_uses_same_supervised_path_without_review_export(self):
        import experiment
        from contextlib import redirect_stdout
        import io
        with mock.patch.object(trainer,'inspection_plan',return_value=Path('/tmp/unit.json')) as prepare,redirect_stdout(io.StringIO()):
            self.assertEqual(experiment.main(['train-smoke','--prepare','unit-only']),0)
            prepare.assert_called_once_with('unit-only',smoke=True)
        with mock.patch.object(trainer,'execute_inspection',return_value=3) as execute:
            self.assertEqual(experiment.main(['train-smoke','--execute','unit.json']),3)
            execute.assert_called_once_with(Path('unit.json'))

    def test_real_smoke_archive_reconstructs_every_forward_and_never_becomes_business_training(self):
        summary=trainer.observed_smoke();check=summary['realModelSyntheticCheck']
        self.assertEqual(check['syntheticOptimizerSteps'],2)
        self.assertEqual(sum(summary['forwardPhaseCounts'].values()),check['modelTopForwardCalls'])
        self.assertEqual(summary['businessTrainingSteps'],0);self.assertEqual(summary['businessInferenceCalls'],0)
        self.assertFalse(summary['realizerTrained']);self.assertFalse(summary['semanticQualityApproved'])
        self.assertEqual(summary['fullRequest500msStatus'],'unverified')
        self.assertEqual(summary['review']['missingReviews'],12)

    def test_synthetic_step_count_and_semantic_claim_tampering_are_rejected(self):
        _,path=trainer.old.paths(trainer.SMOKE_RUN);original=trainer.run.read_json
        for mode in ('steps','semantic'):
            record=original(path)
            if mode=='steps':record['syntheticOptimizerSteps']=1
            else:record['attempts'][0]['syntheticFullModelCheck']['semanticQualityApproved']=True
            def read(p):return copy.deepcopy(record) if p==path else original(p)
            with mock.patch.object(trainer.run,'read_json',side_effect=read):
                with self.assertRaises(ValueError):trainer.observed_smoke()


class NumericImplementationTests(unittest.TestCase):
    def test_complete_t5_forward_backward_disk_reload_and_token_equivalence_on_random_tiny_model(self):
        # Random tiny T5, not the pretrained M02 and not a business source.
        python=trainer.ROOT/'.local/world-components-logic/venv/bin/python'
        code=r'''
import sys,tempfile,json
from pathlib import Path
from unittest import mock
sys.path.insert(0,sys.argv[1])
import torch
from transformers import T5Config,T5ForConditionalGeneration
import plan_training as t
torch.set_num_threads(1);torch.manual_seed(42)
model=T5ForConditionalGeneration(T5Config(vocab_size=64,d_model=8,d_kv=4,d_ff=16,num_layers=8,num_decoder_layers=8,num_heads=2,dropout_rate=0.,decoder_start_token_id=0,eos_token_id=1,pad_token_id=0)).eval()
events=[]
with tempfile.TemporaryDirectory() as directory,mock.patch.object(t,'ROOT',Path(directory)):
 result=t.real_model_smoke(torch,model,{'runId':'unit-tiny','syntheticExamples':list(t.SYNTHETIC_EXAMPLES),'config':t.SMOKE_CONFIG},lambda n,p:events.append((n,p.copy())))
 path=Path(directory)/result['checkpoint']['path']
 assert path.exists() and t.sha256_file(path)==result['checkpoint']['sha256']
 state=torch.load(path,weights_only=True)
 assert len(state)==96 and all(n.endswith(('.lora_A','.lora_B')) for n in state)
 with torch.no_grad():
  for p in model.parameters():
   if p.requires_grad:p.zero_()
 before=t.old.tensor_hash(t.adapter_state(model))
 try:t.save_reload_adapter(torch,model,path.parent,result['checkpoint']['sourceTensorSha256'],lambda *_:None);raise AssertionError('overwrote checkpoint')
 except FileExistsError:pass
 assert t.old.tensor_hash(t.adapter_state(model))==before
assert result['sourceParameters']<100000 and result['adapterModules']==48 and result['syntheticOptimizerSteps']==2
assert result['sourceBaseUnchanged'] and result['reloadedLogitsExact'] and result['reloadedGeneratedTokensExact']
assert sum(n=='training_step_started' for n,p in events)==2 and sum(n=='training_step_settled' for n,p in events)==2
assert sum(n=='model_forward_started' for n,p in events)==result['modelTopForwardCalls']
assert sum(n=='model_forward_settled' for n,p in events)==result['modelTopForwardCalls']
assert result['businessTrainingSteps']==0 and result['businessInferenceCalls']==0
print(json.dumps({'fullTinyT5SmokePassed':True,'syntheticOptimizerSteps':2,'pretrainedModelUsed':False}))
'''
        result=subprocess.run([str(python),'-c',code,str(BASE)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['fullTinyT5SmokePassed'])

    def test_actual_autograd_freeze_padding_fit_loop_and_checkpoint_reload(self):
        # Uses a tiny numeric module, not M02 or any business scenario/label.
        python=trainer.ROOT/'.local/world-components-logic/venv/bin/python'
        code=r'''
import sys,json,types
sys.path.insert(0,sys.argv[1])
import torch
from unittest import mock
import plan_training as t
torch.set_num_threads(1)
check=t.synthetic_gradient_check(torch)
class Toy(torch.nn.Module):
 def __init__(self):
  super().__init__();self.embedding=torch.nn.Embedding(10,8)
  for p in self.embedding.parameters():p.requires_grad_(False)
  self.output=t.lora_linear(torch,torch.nn.Linear(8,10),2,4)
 def forward(self,input_ids,attention_mask,labels):
  x=(self.embedding(input_ids)*attention_mask.unsqueeze(-1)).sum(1)/attention_mask.sum(1,keepdim=True)
  logits=self.output(x).unsqueeze(1).expand(-1,labels.shape[1],-1)
  return types.SimpleNamespace(loss=torch.nn.functional.cross_entropy(logits.reshape(-1,10),labels.reshape(-1),ignore_index=-100))
model=Toy();before=t.old.tensor_hash(t.base_state(model))
rows=[{'sourceGroup':'synthetic-a'},{'sourceGroup':'synthetic-b'}];events=[]
def tokens(tok,row,config):return {'inputIds':[2,3] if row['sourceGroup'].endswith('a') else [4], 'labels':[5,1], 'sourceGroup':row['sourceGroup']}
with mock.patch.object(t,'tokenize_example',side_effect=tokens):
 loss=t.fit_adapter(torch,model,types.SimpleNamespace(pad_token_id=0),rows,{**t.CONFIG,'steps':3},lambda n,p:events.append((n,p)))
assert len(loss)==3 and len(events)==6 and before==t.old.tensor_hash(t.base_state(model))
batch=t.collate(torch,[{'inputIds':[2,3],'labels':[5,1]},{'inputIds':[4],'labels':[1]}],0)
assert batch['labels'].tolist()==[[5,1],[1,-100]] and batch['attention_mask'].tolist()==[[1,1],[1,0]]
s=t.adapter_state(model);wrong=dict(s);wrong.pop(next(iter(wrong)))
try:t.restore_adapter(model,wrong);raise AssertionError('missing state accepted')
except ValueError:pass
print(json.dumps({'numeric':check,'syntheticFitLoopSteps':len(loss),'paddingAndMaskVerified':True,'baseFrozen':True,'businessModelUsed':False}))
'''
        r=subprocess.run([str(python),'-c',code,str(BASE)],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr);result=json.loads(r.stdout)
        self.assertTrue(result['numeric']['checkpointReloadExact']);self.assertEqual(result['syntheticFitLoopSteps'],3)
        self.assertTrue(result['baseFrozen']);self.assertFalse(result['businessModelUsed'])

if __name__=='__main__':unittest.main()
