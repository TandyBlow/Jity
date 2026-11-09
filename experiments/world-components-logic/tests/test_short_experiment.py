"""Engineering/data counterexamples. No fake provider is scored as a model."""
import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import experiment
import short_experiment as run
from short_training import (LocalSemanticProvider,validate_rows,task_specs,complete_tokens,training_schedule,input_text,
                            compose_narrow,mention_candidates)
from short_contracts import result,incomplete
from run_pilot import digest


class PacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rows=run.load_rows()
    def test_actual_new_packet_is_grouped_and_not_human_signed(self):
        summary=validate_rows(self.rows)
        self.assertEqual(summary['sourceGroups'],12)
        self.assertEqual(summary['humanReviewed'],0)
        self.assertEqual(summary['splitGroups'],{'development':2,'test':2,'train':8})
        self.assertEqual(summary['sourceVerified'],0)
        tasks={r['component'].split('.')[0] for r in self.rows}
        self.assertTrue({'D01','D02','D03','D04','D05','D06','D07','D08'}<=tasks)
    def test_source_group_cannot_cross_splits_by_renaming_example(self):
        rows=copy.deepcopy(self.rows[:2]);rows[1]['split']='test';rows[1]['exampleId']='renamed'
        rows[1]['contentSha256']=digest({k:v for k,v in rows[1].items() if k!='contentSha256'})
        with self.assertRaisesRegex(ValueError,'crosses splits'):validate_rows(rows,require_all_splits=False)
    def test_content_changes_cannot_reuse_annotation_identity(self):
        rows=copy.deepcopy(self.rows[:1]);rows[0]['target']='changed'
        with self.assertRaisesRegex(ValueError,'hash mismatch'):validate_rows(rows,require_all_splits=False)
    def test_all_generator_training_targets_are_short_not_json_codecs(self):
        texts=[r for r in self.rows if r['kind']=='text']
        self.assertTrue(texts)
        self.assertTrue(all(r['outputCodec'] in ('text','fragment_or_end','fact_or_end') for r in texts))
        self.assertTrue(any(r['kind']=='annotation_only' for r in self.rows))
    def test_true_task_specs_include_codec(self):
        self.assertEqual(task_specs([next(r for r in self.rows if r['component']=='D02.2.text')])['D02.2.text']['outputCodec'],'text')
    def test_future_gold_alias_is_rejected_without_banning_valid_slot_label(self):
        row=copy.deepcopy(next(r for r in self.rows if r['component']=='D02.1'))
        row['input']['GoldLabel']='act';row['contentSha256']=digest({k:v for k,v in row.items() if k!='contentSha256'})
        with self.assertRaisesRegex(ValueError,'leakage'):validate_rows([row],require_all_splits=False)
    def test_token_limit_does_not_truncate(self):
        class Tokenizer:
            eos_token_id=1
            def encode(self,text,**kw):
                self.kw=kw;return [2,3,1]
        t=Tokenizer()
        with self.assertRaisesRegex(ValueError,'no truncation'):complete_tokens(t,'full',2)
        self.assertFalse(t.kw['truncation'])
        with self.assertRaisesRegex(ValueError,'vocabulary'):complete_tokens(t,'full',3,vocab_size=3)
    def test_runtime_catalog_keeps_zero_example_tasks_visible(self):
        sys.path.insert(0,str(run.DATA))
        from project_primitives import runtime_catalog,catalog_coverage
        catalog=runtime_catalog()
        self.assertEqual(len(catalog),76)
        self.assertNotIn('D02.3.subject',catalog)
        for task in ('D01.2.relation','U1.2.slot','U1.2.relative_entity','U1.2.relation','U5.1.record'):
            self.assertIn(task,catalog)
        coverage=catalog_coverage([])
        self.assertEqual(len(coverage['untrainedMissingTasks']),76)
        self.assertFalse(coverage['allRuntimeTasksHaveTrainingRows'])
    def test_authored_audit_counterexamples_keep_full_sources_and_metadata_separate(self):
        sys.path.insert(0,str(run.DATA))
        from project_primitives import authored_audit_counterexamples
        drafts=authored_audit_counterexamples(self.rows)
        self.assertTrue(drafts)
        validate_rows(drafts,require_all_splits=False)
        originals={r['exampleId']:r for r in self.rows}
        for draft in drafts:
            original=originals[draft['exampleId'].removesuffix(':authored-audit-reject')]
            self.assertEqual(draft['sourceGroup'],original['sourceGroup'])
            self.assertEqual(draft['input']['originalPayload'],original['input']['originalPayload'])
            self.assertNotIn('authorRationale',draft['input'])
            self.assertEqual(draft['target'],'reject')


class ProviderTests(unittest.TestCase):
    def manifest(self):
        return {'schema':'jity-d-short-trained-provider-v1','datasetSha256':'fixture','codeSha256':{'fixture':'fixture'},
                'models':{},'tasks':{},'config':{}}
    def test_missing_trained_component_is_incomplete_without_importing_torch(self):
        provider=LocalSemanticProvider(self.manifest())
        with patch.object(provider,'_load',side_effect=AssertionError('no model should load')):
            self.assertEqual(provider('not-trained',{}).status,'incomplete')
    def test_retired_generator_cannot_load_or_fallback(self):
        m=self.manifest();m['tasks']={'D02.2.text':{'kind':'text','outputCodec':'text'}}
        provider=LocalSemanticProvider(m)
        with patch.object(provider,'_load',side_effect=AssertionError('retired model must not load')):
            self.assertEqual(provider('D02.2.text',{}).reason,'retired_randeng_backend:qwen_webgpu_required')
        with self.assertRaisesRegex(ValueError,'retired_randeng'):provider._load('generator')
    def test_missing_primitive_never_becomes_empty_targets(self):
        provider=LocalSemanticProvider(self.manifest())
        self.assertEqual(provider('D03.1',{'candidateIds':['a','b']}).status,'incomplete')
    def test_weight_decay_change_without_data_gradient_is_not_a_trained_head(self):
        m=self.manifest();task={'kind':'label','labels':['act','skip'],'outputCodec':'scalar'}
        m['tasks']={'D02.1':task};m['models']={'encoder':{'trainingSteps':1,'trainedComponents':['D02.1'],
          'taskSpecs':{'D02.1':task},'componentNonzeroDataGradientSteps':{'D02.1':0}}}
        provider=LocalSemanticProvider(m)
        with patch.object(provider,'_load',side_effect=AssertionError('must not load an untrained head')):
            self.assertIn('no_nonzero_data_gradient',provider('D02.1',{}).reason)
    def test_streamed_observations_do_not_accumulate_raw_payloads(self):
        m=self.manifest();task={'kind':'label','labels':['act','skip'],'outputCodec':'scalar'}
        m['tasks']={'D02.1':task};m['models']={'encoder':{'trainingSteps':1,'trainedComponents':['D02.1'],
          'taskSpecs':{'D02.1':task},'componentNonzeroDataGradientSteps':{'D02.1':1}}}
        events=[];provider=LocalSemanticProvider(m,retain_observations=False,checkpoint=lambda name,value:events.append((name,value)))
        payload={'world':{'complete':'input'}}
        with patch.object(provider,'_load',side_effect=ValueError('synthetic missing checkpoint for engineering test')):
            self.assertEqual(provider.predict_many([('D02.1',payload)])[0].status,'incomplete')
        self.assertEqual(provider.observations,[])
        self.assertEqual(events[-1][1]['primitiveCalls'],1)
        self.assertEqual(next(v for name,v in events if name=='semantic_call_finished')['input'],payload)
    def test_sequence_end_does_not_invoke_generator_and_missing_label_is_incomplete(self):
        calls=[];payload={'context':{'world':{'entire':'world'}}}
        def fixture(task,value):
            calls.append((task,value));return result('end')
        self.assertEqual(compose_narrow(fixture,'D02.2',payload),{'kind':'end'})
        self.assertEqual([task for task,_ in calls],['D02.2.next'])
        self.assertEqual(calls[0][1]['context'],payload['context'])
        provider=LocalSemanticProvider(self.manifest())
        self.assertEqual(provider('D05.3',payload).status,'incomplete')
    def test_generation_executor_binding_uses_reactor_not_threat_source(self):
        payload={'context':{'actorId':'a','world':{'initial':{'characters':{'a':{'name':'甲'},'b':{'name':'乙'}}}}},'memberId':'b'}
        header,body=input_text('D04.1.text',payload).split('\n',1)
        self.assertEqual(json.loads(header)['currentExecutor'],{'id':'b','name':'乙','role':'reactor'})
        self.assertEqual(json.loads(body)['context'],payload)
        payload['context']['actorId']='b';payload['memberId']='a'
        self.assertEqual(json.loads(input_text('D02.2.text',payload).split('\n',1)[0])['currentExecutor']['id'],'b')
    def test_joint_semantic_abstention_retains_every_attempt_before_return(self):
        events=[];provider=LocalSemanticProvider(self.manifest(),checkpoint=lambda name,value:events.append((name,value)))
        joint={'judgments':[{'attemptId':'a1','label':'achieved'},{'attemptId':'b1','label':'incomplete'},
                            {'attemptId':'b2','label':'incomplete'}]}
        with patch('short_training.compose_narrow',return_value=joint):answer=provider('D05.2',{'all':'input'})
        self.assertEqual(answer.reason,'semantic_incomplete:D05.2:b1,b2')
        self.assertIsNone(answer.value)
        self.assertEqual(events[-1][1]['judgments'],joint['judgments'])
    def test_disposition_abstention_is_not_an_action_or_skip_string(self):
        try:import torch
        except ImportError:self.skipTest('local numerical fixture dependency unavailable')
        m=self.manifest();task={'kind':'label','labels':['act','skip','incomplete'],'outputCodec':'scalar'}
        m['tasks']={'D02.1':task};m['models']={'encoder':{'trainingSteps':1,'trainedComponents':['D02.1'],
          'taskSpecs':{'D02.1':task},'componentNonzeroDataGradientSteps':{'D02.1':1}}}
        events=[];provider=LocalSemanticProvider(m,checkpoint=lambda name,value:events.append((name,value)))
        with patch.object(provider,'_load',return_value=(torch,None,None,{'D02.1':None})), \
             patch('short_training.encode_complete',return_value=torch.zeros(1)), \
             patch('short_training.head_logits',return_value=torch.tensor([[0.,0.,1.]])):
            answer=provider('D02.1',{'world':'complete engineering fixture'})
        self.assertEqual(answer.reason,'semantic_incomplete:D02.1');self.assertIsNone(answer.value)
        self.assertEqual(events[-1][1]['rawLabel'],'incomplete')
    def test_mutating_model_or_vocab_identity_rejects_stale_loaded_cache(self):
        provider=LocalSemanticProvider(self.manifest());provider.manifest['config']['precision']='changed'
        self.assertEqual(provider('D02.1',{}).reason,'provider_identity_changed_recreate_required')
    def test_json_generation_fallback_is_not_accepted(self):
        m=self.manifest();m['tasks']={'D05.1':{'kind':'text','outputCodec':'json'}}
        with self.assertRaisesRegex(ValueError,'JSON'):LocalSemanticProvider(m)
    def test_checkpoint_label_order_must_equal_provider_vocabulary(self):
        m=self.manifest();m['tasks']={'D02.1':{'kind':'label','labels':['act','skip'],'outputCodec':'scalar'}}
        m['models']={'encoder':{'trainedComponents':['D02.1'],'taskSpecs':{'D02.1':{'kind':'label','labels':['skip','act'],'outputCodec':'scalar'}}}}
        with self.assertRaisesRegex(ValueError,'identity mismatch'):LocalSemanticProvider(m)
    def test_narrow_joint_judgments_keep_complete_group_payload(self):
        observed=[]
        payload={'context':{'world':{'kept':'all'},'group':{'memberIds':['a','b']}},'attempts':[{'attemptId':'a1'},{'attemptId':'b1'}]}
        def fixture(component,value):
            observed.append(value)
            return result('not_achieved' if value['semanticQuery']['attemptId']=='a1' else 'achieved')
        out=compose_narrow(fixture,'D05.2',payload)
        self.assertEqual(out['judgments'],[{'attemptId':'a1','label':'not_achieved'},{'attemptId':'b1','label':'achieved'}])
        self.assertTrue(all(x['context']==payload['context'] for x in observed))
    def test_later_missing_member_cannot_be_omitted(self):
        calls=[]
        def fixture(component,payload):
            calls.append(payload)
            return result('target') if len(calls)==1 else incomplete('timeout')
        with self.assertRaisesRegex(ValueError,'timeout'):compose_narrow(fixture,'D03.1',{'candidateIds':['a','b']})


class EntrypointTests(unittest.TestCase):
    def test_legacy_run_commands_are_retired_but_not_deleted(self):
        for args in (['prepare','some-id'],['execute','some-plan'],['realizer-slots','--prepare']):
            with self.subTest(args=args),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as cm:
                experiment.main(args)
            self.assertEqual(cm.exception.code,2)
        self.assertTrue((run.BASE/'realizer_slots.py').exists())
    def test_active_status_is_new_scheme_without_models(self):
        with contextlib.redirect_stdout(io.StringIO()) as capture:
            self.assertEqual(experiment.main(['status']),0)
        self.assertIn('short_semantics_only',capture.getvalue())
    def test_blocked_preflight_retains_both_planned_unstarted_arms(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan={'runId':'test-preflight','readiness':'blocked','blockers':['missing_model'],
                  'cases':[{'caseId':'training'}],'config':{'attemptsPerCase':1}}
            path=Path(tmp)/'p.json';path.write_text(json.dumps(plan))
            with patch.object(run,'ART',Path(tmp)),patch.object(run,'verify',return_value=[]),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run.execute(path),2)
                out=json.loads((Path(tmp)/'test-preflight.record.json').read_text())
                self.assertEqual(out['unexecutedAttempts'],2)
                self.assertEqual(out['trainingSteps'],0)
                self.assertEqual(out['modelCalls'],0)
                self.assertEqual([s['status'] for s in out['attemptSlots']],['not_started','not_started'])
                with self.assertRaises(FileExistsError):run.execute(path)


class ExposureTests(unittest.TestCase):
    def test_time_repair_preserves_six_labels_without_claiming_missing_classes(self):
        config=run.configuration('encoder_time_repair')
        self.assertEqual(config['repairComponents'],['D08.1.unit','D08.2.time.unit'])
        self.assertEqual(config['steps'],32);self.assertEqual(run.training_arms('encoder_time_repair'),('encoder_train',))
        labels=['second','minute','hour','day','month','year'];component='D08.1.unit'
        trained={'specs':{component:{'labels':labels}},'componentLabelDataGradientExposures':{component:{label:int(label in ('second','minute')) for label in labels}}}
        rows=[{'component':component,'split':'train','target':label} for label in ('second','minute')]
        run.validate_observed_label_training(trained,rows,[component])
        trained['componentLabelDataGradientExposures'][component]={'second':1,'minute':1}
        normalized=run.validate_observed_label_training(trained,rows,[component])
        self.assertEqual(normalized[component],dict(zip(labels,[1,1,0,0,0,0])))
        self.assertEqual(trained['componentLabelDataGradientExposures'][component],{'second':1,'minute':1})
        trained['componentLabelDataGradientExposures'][component]['minute']=0
        with self.assertRaisesRegex(ValueError,'positive-label'):run.validate_observed_label_training(trained,rows,[component])
    def test_source_representation_identity_binds_bytes_not_directory(self):
        source={'modelId':'M01','revision':'pinned','registrySha256':'registry','directory':'first',
                'files':[{'path':'weights','expectedBytes':7,'observedSha256':'original'}]}
        relocated=copy.deepcopy(source);relocated['directory']='second'
        self.assertEqual(run.source_model_identity(source),run.source_model_identity(relocated))
        for key in ('revision','registrySha256'):
            changed=copy.deepcopy(source);changed[key]='different'
            self.assertNotEqual(run.source_model_identity(source),run.source_model_identity(changed))
        changed=copy.deepcopy(source);changed['files'][0]['observedSha256']='different'
        self.assertNotEqual(run.source_model_identity(source),run.source_model_identity(changed))
    def test_reference_head_exposes_existing_multiple_candidate_training_rows(self):
        rows=[{'exampleId':'single','component':'pointer','kind':'reference','target':'x','input':{'candidates':[{'id':'x'}]},'sourceGroup':'first','split':'train'},
              {'exampleId':'multiple','component':'pointer','kind':'reference','target':'y','input':{'candidates':[{'id':'x'},{'id':'y'}]},'sourceGroup':'first','split':'train'}]
        selected=training_schedule(rows,{'steps':1,'batchSize':2})
        self.assertEqual(set(selected['exampleIds']),{'single','multiple'})
    def test_repair_plan_has_only_encoder_work_and_preserves_other_tensor_values(self):
        try:import torch
        except ImportError:self.skipTest('local numerical fixture dependency unavailable')
        self.assertEqual(run.training_arms('encoder_repair'),('encoder_train',))
        self.assertEqual(run.configuration('encoder_repair')['steps'],48)
        original={'unchanged':{'weight':torch.tensor([[7.]])},'repair':{'weight':torch.tensor([[1.]])}}
        replacement={'repair':{'weight':torch.tensor([[2.]])}}
        merged,proof=run.merge_repaired_head_states(torch,original,replacement,('repair',))
        self.assertTrue(torch.equal(merged['unchanged']['weight'],original['unchanged']['weight']))
        self.assertTrue(torch.equal(merged['repair']['weight'],replacement['repair']['weight']))
        self.assertEqual(float(original['repair']['weight'].item()),1.)
        self.assertEqual(set(proof),{'unchanged'})
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint=Path(tmp)/'nested-heads.pt';torch.save(merged,checkpoint)
            restored=torch.load(checkpoint,weights_only=True)
            self.assertEqual(run.head_collection_hashes(restored),run.head_collection_hashes(merged))
            restored['repair']['weight'].add_(1)
            self.assertNotEqual(run.head_collection_hashes(restored),run.head_collection_hashes(merged))
        with self.assertRaises(ValueError):run.merge_repaired_head_states(torch,original,replacement,('missing',))
    def test_late_negative_and_second_source_are_really_scheduled(self):
        rows=[{'exampleId':str(i),'component':'audit','kind':'label','target':'pass',
               'sourceGroup':'first','split':'train'} for i in range(100)]
        rows.extend([{'exampleId':'late-negative','component':'audit','kind':'label','target':'reject','sourceGroup':'second','split':'train'},
                     {'exampleId':'second-pass','component':'audit','kind':'label','target':'pass','sourceGroup':'second','split':'train'}])
        schedule=training_schedule(rows,{'steps':2,'batchSize':2})
        self.assertIn('late-negative',schedule['exampleIds'])
        self.assertIn('second-pass',schedule['exampleIds'])
        self.assertEqual(schedule['observedLabelExposures']['audit'],{'pass':2,'reject':2})
        with self.assertRaisesRegex(ValueError,'untrained'):training_schedule(rows,{'steps':1,'batchSize':1})
    def test_small_generator_task_and_end_both_receive_budget(self):
        rows=[{'exampleId':str(i),'component':'many','kind':'text','target':'sentence',
               'sourceGroup':'first','split':'train'} for i in range(100)]
        rows.extend([{'exampleId':'one','component':'rare','kind':'text','target':'short','sourceGroup':'first','split':'train'},
                     {'exampleId':'end','component':'many','kind':'text','target':'【结束】','sourceGroup':'first','split':'train'}])
        schedule=training_schedule(rows,{'steps':2,'batchSize':2})
        self.assertIn('one',schedule['exampleIds']);self.assertIn('end',schedule['exampleIds'])
        self.assertEqual(schedule['taskExposures'],{'many':2,'rare':2})

    def test_checkpointed_microbatches_match_full_batch_target_weighting(self):
        # Random tiny T5 is a numerical training-loop test, never a capability
        # experiment or a source of claimed model scores/checkpoints.
        try:
            import torch
            from transformers import T5Config,T5ForConditionalGeneration
        except ImportError:self.skipTest('local neural dependencies unavailable')
        from plan_training import fit_encoded_adapter
        torch.set_num_threads(1);torch.manual_seed(912)
        config=T5Config(vocab_size=32,d_model=16,d_ff=32,d_kv=8,num_layers=1,
          num_decoder_layers=1,num_heads=2,dropout_rate=0.1,decoder_start_token_id=0,pad_token_id=0,eos_token_id=1)
        baseline=T5ForConditionalGeneration(config);checkpointed=copy.deepcopy(baseline)
        examples=[{'annotationId':'one','sourceGroup':'one','inputIds':[2,3,1],'labels':[4,5,1]},
                  {'annotationId':'two','sourceGroup':'two','inputIds':[6,1],'labels':[7,1]}]
        controls={'steps':1,'batchSize':2,'learningRate':0.0001,'weightDecay':0.0,'maxGradNorm':1.,
          'seed':4,'allowGroupedExamples':True,'exampleSchedule':['one','two']}
        events=[]
        first=fit_encoded_adapter(torch,baseline,examples,0,controls,lambda *_:None)
        second=fit_encoded_adapter(torch,checkpointed,examples,0,{**controls,'microbatchSize':1,
          'gradientCheckpointing':True,'gradientCheckpointingReentrant':False,'trainingDropout':0.0},
          lambda name,value:events.append((name,value)))
        self.assertAlmostEqual(first[0],second[0],places=5)
        self.assertFalse(checkpointed.training);self.assertFalse(checkpointed.is_gradient_checkpointing)
        self.assertTrue(checkpointed.config.use_cache)
        self.assertTrue(all(m.p==0.1 for m in checkpointed.modules() if isinstance(m,torch.nn.Dropout)))
        self.assertTrue(all(m.dropout==0.1 for m in checkpointed.modules() if type(getattr(m,'dropout',None)) is float))
        self.assertEqual(sum(name=='training_microbatch_started' for name,_ in events),2)
        for key,value in baseline.state_dict().items():
            self.assertTrue(torch.allclose(value,checkpointed.state_dict()[key],atol=0.00003,rtol=0.00001),key)

if __name__=='__main__':unittest.main()
