"""Small numerical/contract fixtures, never a game-model capability test."""
import copy
import tempfile
import time
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import short_qwen_training as q


class TokenizerFixture:
    eos_token_id=9
    def __len__(self):self.length_calls=getattr(self,'length_calls',0)+1;return 128
    def apply_chat_template(self,messages,**kwargs):
        self.messages=messages;self.options=kwargs;return [1,2,3,4]
    def encode(self,text,**kwargs):self.encode_options=kwargs;return [5,6]


class QwenContractTests(unittest.TestCase):
    def row(self):return {'exampleId':'x','component':'D02.2.text','sourceGroup':'source','split':'train','input':{'context':{'actorId':'a','world':{'fact':'完整世界'}}},'target':'尝试拿起刷子。'}
    def test_training_has_complete_prompt_non_thinking_and_response_eos(self):
        tokenizer=TokenizerFixture();row=self.row();r=q.tokenize_row(tokenizer,row,q.CONFIG)
        self.assertEqual(r['promptIds'],[1,2,3,4]);self.assertEqual(r['targetIds'],[5,6,9])
        self.assertFalse(tokenizer.options['enable_thinking']);self.assertTrue(tokenizer.options['add_generation_prompt'])
        self.assertFalse(tokenizer.encode_options['truncation'])
        self.assertEqual(tokenizer.length_calls,1)
        self.assertNotIn(row['target'],str(tokenizer.messages));self.assertIn('完整世界',str(tokenizer.messages))
    def test_oversized_complete_prompt_or_target_is_rejected(self):
        config={**q.CONFIG,'maxInputTokens':3}
        with self.assertRaisesRegex(ValueError,'complete_context'):q.tokenize_row(TokenizerFixture(),self.row(),config)
        config={**q.CONFIG,'maxTargetTokens':2}
        with self.assertRaisesRegex(ValueError,'complete_target'):q.tokenize_row(TokenizerFixture(),self.row(),config)
    def test_14_tasks_and_full_budget_are_registered(self):
        self.assertEqual(len(q.TASKS),14);self.assertEqual(q.CONFIG['steps'],112)
        self.assertEqual(q.CONFIG['adapterPrecision'],'float32')
        self.assertFalse(q.CONFIG['enableThinking']);self.assertEqual(q.CONFIG['retries'],0)
    def test_time_repair_has_two_training_tasks_and_full_regression(self):
        config=q.configuration('time_repair')
        self.assertEqual(config['steps'],32);self.assertEqual(config['trainingComponents'],list(q.TIME_COMPONENTS))
        units=q.execution_units(list(range(128)),list(range(32)),config,list(range(8)))
        self.assertEqual(sum(len(u['exampleIds']) for u in units if u['arm']=='qwen_baseline'),8)
        self.assertEqual(sum(len(u['exampleIds']) for u in units if u['arm']=='qwen_after'),128)
    def test_registered_alternative_eos_is_preserved(self):
        from types import SimpleNamespace
        model=SimpleNamespace(generation_config=SimpleNamespace(eos_token_id=[151645,151643]))
        self.assertEqual(q.legal_eos_ids(model,TokenizerFixture()),[151645,151643])
        model.generation_config.eos_token_id=[True]
        with self.assertRaises(ValueError):q.legal_eos_ids(model,TokenizerFixture())
    def test_process_partition_preserves_every_registered_case_and_step_once(self):
        evaluation=[f'e{x}' for x in range(35)];schedule=[f't{x}' for x in range(112)]
        units=q.execution_units(evaluation,schedule,q.CONFIG)
        for arm in ('qwen_baseline','qwen_after'):
            self.assertEqual([key for u in units if u['arm']==arm for key in u['exampleIds']],evaluation)
        self.assertEqual([key for u in units if u['arm']=='qwen_train' for key in u['exampleIds']],schedule)
        self.assertEqual(len({u['unitId'] for u in units}),len(units))
        self.assertTrue(all(len(u['exampleIds'])<=8 for u in units if u['arm']=='qwen_train'))
    def test_failed_attempt_has_complete_replayable_timing_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'record.json';journal_path=Path(tmp)/'journal.jsonl'
            slot={'arm':'qwen_train','caseId':'x','repeat':0,'status':'not_started'}
            record={'runId':'fixture','attempts':[],'attemptSlots':[slot],'activeAttempt':None,'status':'failed','checkpointStorage':q.common.CHECKPOINT_STORAGE,'planSha256':'test-plan'}
            attempt={**slot,'status':'failed','startedMonotonicNs':time.monotonic_ns(),'checkpoints':[]}
            with q.common.AppendJournal(journal_path,'test-plan') as journal:
                journal.append('begin',{'runId':'fixture','slots':[slot],'checkpointStorage':q.common.CHECKPOINT_STORAGE})
                journal.append('attempt_start',{**attempt,'status':'started'})
                q.settle_timing(journal,attempt,record,path)
            q.common.reconcile_journal(record,journal_path,'worker_exit')
            self.assertEqual(record['attempts'][0]['status'],'failed')
            self.assertIn('snapshotEndMs',record['attempts'][0])


class QwenNumericalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import torch
            from transformers import Qwen3Config,Qwen3ForCausalLM
        except ImportError:raise unittest.SkipTest('tiny numerical fixture dependency unavailable')
        cls.torch=torch;cls.Config=Qwen3Config;cls.Model=Qwen3ForCausalLM;torch.set_num_threads(1)
    def model(self):
        self.torch.manual_seed(42)
        config=self.Config(vocab_size=128,hidden_size=16,intermediate_size=32,num_hidden_layers=1,num_attention_heads=2,num_key_value_heads=1,head_dim=8,max_position_embeddings=128,attention_dropout=0.0)
        return self.Model(config).eval()
    def example(self):return {'promptIds':[1,2,3,4],'targetIds':[5,6,7]}
    def test_selected_response_logits_equal_full_masked_causal_loss(self):
        torch=self.torch;model=self.model();example=self.example();narrow=q.response_loss(torch,model,example,'cpu')
        ids=example['promptIds']+example['targetIds'];labels=[-100]*len(example['promptIds'])+example['targetIds']
        full=model(input_ids=torch.tensor([ids]),labels=torch.tensor([labels]),use_cache=False).loss
        self.assertTrue(torch.allclose(narrow,full,atol=1e-6))
    def test_lora_real_gradient_keeps_base_then_merges_numerically(self):
        torch=self.torch;model=self.model();base=q.tensor_digest(torch,model.state_dict());modules=q.install_lora(torch,model,q.CONFIG)
        self.assertEqual(len(modules),2);params=[p for p in model.parameters() if p.requires_grad]
        self.assertTrue(all(p.dtype==torch.float32 for p in params));optimizer=torch.optim.AdamW(params,lr=.01)
        loss=q.response_loss(torch,model,self.example(),'cpu');loss.backward()
        self.assertGreater(sum(float(p.grad.abs().sum()) for p in params),0);optimizer.step()
        from plan_training import base_state
        self.assertEqual(base,q.tensor_digest(torch,base_state(model)))
        tensors,_=q.causal_batch(torch,self.example(),'cpu')
        with torch.no_grad():before=model(**tensors).logits
        q.merge_lora(torch,model)
        with torch.no_grad():after=model(**tensors).logits
        self.assertTrue(torch.allclose(before,after,atol=1e-5))
        self.assertFalse(any('lora_' in n for n,_ in model.named_parameters()))
    def test_tensor_identity_supports_bfloat16(self):
        torch=self.torch;a=torch.tensor([1,2],dtype=torch.bfloat16)
        self.assertEqual(q.tensor_digest(torch,{'w':a}),q.tensor_digest(torch,{'w':a.clone()}))
        self.assertNotEqual(q.tensor_digest(torch,{'w':a}),q.tensor_digest(torch,{'w':a+1}))
    def test_resource_failure_records_raw_then_stops_without_second_call(self):
        torch=self.torch;events=[]
        class Model:
            calls=0
            def eval(self):return self
            def generate(self,**kwargs):
                self.calls+=1
                return torch.cat([kwargs['input_ids'],torch.tensor([[5,9]])],dim=1)
        class Tok:
            eos_token_id=9
            def decode(self,ids,**kwargs):return 'fixture tokens'
        model=Model();row=QwenContractTests().row();row.update(split='development')
        second=copy.deepcopy(row);second['exampleId']='second'
        encoded={r['exampleId']:{'promptIds':[1,2,3]} for r in (row,second)}
        config={**q.CONFIG,'device':'cpu','maxMpsDriverMiB':1}
        def capture(name,payload):events.append((name,copy.deepcopy(payload)));return {'fixture':True}
        with patch.object(q,'sync'),patch.object(torch.mps,'empty_cache'),patch.object(torch.mps,'current_allocated_memory',return_value=8),patch.object(torch.mps,'driver_allocated_memory',side_effect=[0,2097152,0]):
            with self.assertRaisesRegex(MemoryError,'frozen_mps_driver'):q.predictions(torch,model,Tok(),[row,second],encoded,config,capture)
        self.assertEqual(model.calls,1)
        finished=[payload for name,payload in events if name=='qwen_generation_finished']
        self.assertEqual(len(finished),1);self.assertEqual(finished[0]['rawTokenIds'],[5,9])
        self.assertTrue(finished[0]['fatalResourceFailure']);self.assertEqual(finished[0]['status'],'incomplete')
    def test_saved_optimizer_adapter_rng_resume_equals_continuous_training(self):
        torch=self.torch;config={**q.CONFIG,'device':'cpu','steps':4}
        examples={f'e{i}':{**self.example(),'component':'D02.2.text','inputSha256':f'input{i}'} for i in range(4)}
        examples['e2']['targetIds']=[6,5,7]
        schedule={'exampleIds':list(examples)};plan={'config':config,'trainingSchedule':schedule}
        capture=lambda name,payload:None
        with tempfile.TemporaryDirectory() as tmp,patch.object(q,'TASKS',{'D02.2.text'}),patch.object(q,'memory',return_value={}),patch.object(q,'sync'):
            root=Path(tmp)
            whole=q.train_chunk(torch,self.model(),examples,plan,{'offset':0,'exampleIds':list(examples)},capture,root/'whole')
            first=q.train_chunk(torch,self.model(),examples,plan,{'offset':0,'exampleIds':['e0','e1']},capture,root/'first')
            resume=torch.load(first['resumeState']['path'],map_location='cpu',weights_only=True)
            second=q.train_chunk(torch,self.model(),examples,plan,{'offset':2,'exampleIds':['e2','e3']},capture,root/'second',resume)
            continuous=torch.load(whole['resumeState']['path'],map_location='cpu',weights_only=True)
            restored=torch.load(second['resumeState']['path'],map_location='cpu',weights_only=True)
            self.assertEqual(whole['checkpoint']['tensorSha256'],second['checkpoint']['tensorSha256'])
            self.assertEqual(whole['losses'],second['losses']);self.assertEqual(restored['nextSchedulePosition'],4)
            self.assertTrue(torch.equal(continuous['cpuRngState'],restored['cpuRngState']))
            for key,state in continuous['optimizer']['state'].items():
                for name,value in state.items():
                    self.assertTrue(torch.equal(value,restored['optimizer']['state'][key][name]))
            self.assertEqual(second['componentNonzeroDataGradientSteps']['D02.2.text'],4)
            with self.assertRaisesRegex(ValueError,'schedule mismatch'):
                q.train_chunk(torch,self.model(),examples,plan,{'offset':1,'exampleIds':['e2']},capture,root/'bad',resume)
    def test_new_repair_schedule_inherits_real_optimizer_history(self):
        torch=self.torch;config={**q.CONFIG,'device':'cpu','steps':4,'trainingComponents':['D02.2.text']}
        examples={f'e{i}':{**self.example(),'component':'D02.2.text','inputSha256':f'input{i}'} for i in range(4)}
        examples['e2']['targetIds']=[6,5,7];capture=lambda *_:None
        with tempfile.TemporaryDirectory() as tmp,patch.object(q,'TASKS',{'D02.2.text'}),patch.object(q,'memory',return_value={}),patch.object(q,'sync'):
            root=Path(tmp);whole_plan={'config':config,'trainingSchedule':{'exampleIds':list(examples)}}
            whole=q.train_chunk(torch,self.model(),examples,whole_plan,{'offset':0,'exampleIds':list(examples)},capture,root/'whole')
            parent_plan={'runId':'parent','config':{**config,'steps':2},'trainingSchedule':{'exampleIds':['e0','e1']}}
            parent=q.train_chunk(torch,self.model(),examples,parent_plan,{'offset':0,'exampleIds':['e0','e1']},capture,root/'parent')
            state=torch.load(parent['resumeState']['path'],map_location='cpu',weights_only=True)
            repair_plan={'runId':'repair','config':{**config,'steps':2},'trainingSchedule':{'exampleIds':['e2','e3']},'inheritedModel':{'parentOptimizerSteps':2}}
            repaired=q.train_chunk(torch,self.model(),examples,repair_plan,{'offset':0,'exampleIds':['e2','e3']},capture,root/'repair',state)
            self.assertEqual(repaired['steps'],2);self.assertEqual(repaired['parentOptimizerSteps'],2)
            self.assertEqual(repaired['optimizerCumulativeSteps'],4)
            self.assertEqual(repaired['losses'],whole['losses'][2:])
            self.assertEqual(repaired['checkpoint']['tensorSha256'],whole['checkpoint']['tensorSha256'])
            self.assertEqual(repaired['componentNonzeroDataGradientSteps'],{'D02.2.text':2})


if __name__=='__main__':unittest.main()
