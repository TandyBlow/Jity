"""Action collaboration boundary tests; no model loading or inference."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import action_chain as chain
import experiment
from fact_windows import restore

class ActionChainTests(unittest.TestCase):
    def test_instruction_preserves_all_four_inputs_and_full_roster(self):
        from pilot_codec import unpack
        for c in chain.dataset()[0]:
            messages,value=chain.instruction_prompt(c)
            self.assertEqual(value,c['input'])
            packed=json.loads(messages[1]['content'].split('完整世界工作态（无损表格编码）：',1)[1])
            self.assertEqual(unpack(packed),c['input'])
            self.assertEqual([m['role'] for m in messages],['system','user'])

    def test_instruction_does_not_include_review_labels_or_action_gold(self):
        c=chain.dataset()[0][0];messages,value=chain.instruction_prompt(c)
        raw=json.dumps(messages,ensure_ascii=False)
        self.assertNotIn('mustRespect',raw);self.assertNotIn('draftExpected',raw)
        self.assertEqual(value,chain.build_model_input(c))

    def test_derived_targets_use_the_exact_generated_utf8_and_full_roster(self):
        c=chain.dataset()[0][0];text='我尝试推开门。\n保留换行。'
        target=chain.target_case(c,text)
        self.assertEqual(target['input']['source']['actionText'].encode(),text.encode())
        self.assertEqual(target['input']['confirmedGroup']['members'][-1]['actionText'],text)
        self.assertEqual(target['input']['world'],c['input']['world'])
        self.assertEqual(target['input']['candidateIds'],[p['id'] for p in c['input']['world']['characters']])
        self.assertEqual(target['input']['knownPriorJudgments'],[])
        self.assertEqual(target['sourceGroup'],c['sourceGroup']);self.assertFalse(target['anchorCase'])
        self.assertTrue(chain.guard_case(target)['shouldCall'])

    def test_missing_frozen_text_is_rejected_not_treated_as_empty_targets(self):
        with self.assertRaises(ValueError):chain.target_case(chain.dataset()[0][0],'')

    def test_action_checkpoint_survives_process_exit_without_recomputing(self):
        slot={'arm':'qa','caseId':'case','repeat':0,'status':'not_started'}
        start={**slot,'status':'started','checkpoints':[]}
        checkpoint={'arm':'qa','caseId':'case','repeat':0,'name':'candidate_frozen_for_diagnostic',
                    'payload':{'actionText':'我尝试推门。','semanticApproved':False}}
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'j.jsonl'
            with experiment.AppendJournal(p,'test-sha') as j:
                j.append('begin',{'runId':'test','slots':[slot]});j.append('attempt_start',start);j.append('attempt_checkpoint',checkpoint)
            raw=p.read_bytes();r={'runId':'test','planSha256':'test-sha','attemptSlots':[slot], 'attempts':[],'status':'running'}
            experiment.reconcile_journal(r,p,'synthetic_exit')
            self.assertEqual(r['attempts'][0]['checkpoints'][0],checkpoint)
            self.assertEqual(r['attempts'][0]['status'],'interrupted')
            self.assertEqual(r['journalRecovery']['modelCallsDuringReplay'],0);self.assertEqual(raw,p.read_bytes())

    def test_checkpoint_outside_attempt_is_rejected(self):
        slot={'arm':'qa','caseId':'case','repeat':0,'status':'not_started'}
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'j.jsonl'
            with experiment.AppendJournal(p,'test-sha') as j:
                j.append('begin',{'runId':'test','slots':[slot]})
                j.append('attempt_checkpoint',{'arm':'qa','caseId':'case','repeat':0,'name':'bad','payload':{}})
            r={'runId':'test','planSha256':'test-sha','attemptSlots':[slot], 'attempts':[],'status':'running'}
            with self.assertRaisesRegex(ValueError,'outside active'):experiment.reconcile_journal(r,p,'exit')

class ActorFocusTests(unittest.TestCase):
    def test_focus_repeats_the_actual_actor_all_fields_without_selecting_actions(self):
        for c in chain.dataset()[0]:
            before=copy.deepcopy(c);focus=chain.actor_context(c)
            actor=next(p for p in c['input']['world']['characters'] if p['id']==c['input']['actorId'])
            self.assertEqual(focus['actor'],actor);self.assertEqual(focus['advance'],c['input']['advance'])
            self.assertEqual(c,before)
        npc=chain.dataset()[0][-1]
        self.assertEqual(chain.actor_context(npc)['actor']['id'],'p2')
        self.assertIn('秤盘',chain.actor_context(npc)['actor']['tasks'][0]['text'])

    def test_focus_and_int8_have_identical_complete_inputs_and_prompts(self):
        from pilot_codec import unpack
        for c in chain.dataset()[0]:
            a,value=chain.instruction_prompt(c,'focus');b,other=chain.instruction_prompt(c,'focus_int8')
            self.assertEqual(a,b);self.assertEqual(value,other);self.assertEqual(value,c['input'])
            packed=a[1]['content'].split('完整世界工作态（无损表格编码）：')[1].split('\n本次行动者')[0]
            self.assertEqual(unpack(json.loads(packed)),c['input'])
            repeated=a[1]['content'].split('本次行动者原始资料（从上文逐字段复制）：')[1].split('\n只决定')[0]
            self.assertEqual(unpack(json.loads(repeated)),chain.actor_context(c))
            self.assertNotIn('mustRespect',json.dumps(a));self.assertNotIn('draftExpected',json.dumps(a))

    def test_original_prompt_stays_equal_to_last_batch(self):
        for c in chain.dataset()[0]:self.assertEqual(chain.instruction_prompt(c,'original'),chain.instruction_prompt(c))

    def test_precision_blocks_preserve_every_slot_and_do_not_switch_back(self):
        plan=json.loads((chain.ART/'action-focus-dev42-20261104-r1.plan.json').read_bytes())
        slots=experiment.planned_slots(plan,plan['arms'])
        self.assertEqual(len(slots),36);self.assertTrue(all(s['arm']!='focus_int8' for s in slots[:24]))
        self.assertTrue(all(s['arm']=='focus_int8' for s in slots[24:]))
        self.assertEqual(len({(s['arm'],s['caseId'],s['repeat']) for s in slots}),36)
        self.assertEqual([s['arm'] for s in slots[8:10]],['focus','original'])

    def test_invalid_blocks_rejected_before_execution(self):
        for blocks in ([['original'],['focus_int8']], [['original','focus'],['focus']], [[],list(chain.ARMS)]):
            plan={'cases':chain.dataset()[0],'config':{**chain.CONFIG,'armBlocks':blocks}}
            with self.assertRaisesRegex(ValueError,'arm blocks'):experiment.planned_slots(plan,chain.ARMS)

class ReadableInputTests(unittest.TestCase):
    def test_readable_full_input_and_actor_roundtrip_without_tables_or_refs(self):
        from pilot_codec import readable,restore_readable
        for c in chain.dataset()[0]:
            value=c['input'];encoded=readable(value)
            self.assertEqual(restore_readable(encoded),value)
            self.assertIsInstance(encoded['世界']['人物'],list)
            self.assertEqual(len(encoded['世界']['人物']),len(value['world']['characters']))
            messages,_=chain.instruction_prompt(c,'readable')
            full=messages[1]['content'].split('完整世界工作态（逐字段JSON，无表格和同文引用）：')[1].split('\n当前行动者')[0]
            self.assertEqual(restore_readable(json.loads(full)),value)
            self.assertNotIn('mustRespect',json.dumps(messages));self.assertNotIn('draftExpected',json.dumps(messages))

    def test_consumed_text_is_preserved_with_state_translation_not_a_new_command(self):
        c=chain.dataset()[0][2];messages,_=chain.instruction_prompt(c,'readable')
        text=messages[1]['content'];self.assertIn(c['input']['advance']['inputText'],text)
        self.assertIn('已经消费的旧输入',text);self.assertIn('不重新执行',text)

    def test_unknown_keys_missing_null_and_special_characters_roundtrip(self):
        from pilot_codec import readable,restore_readable
        value={'strange':{'text':'换行\n\"和引号','extra':None},'list':[True,False,0,{},[]]}
        self.assertEqual(restore_readable(readable(value)),value)
        with self.assertRaises(ValueError):readable({'id':'p1','编号':'p2'})

class ChainEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gzip
        import m01_shared_report as report
        cls.report=report
        cls.plan=json.loads((report.DATA/(report.CHAIN_PREFIX+'r3.plan.json')).read_bytes())
        cls.record=report.read_archive(report.DATA/(report.CHAIN_PREFIX+'r3.record.json.gz'))
        cls.baseline=report.read_archive(report.DATA/'m01-event-dev42-20261102-r1.record.json.gz')
        cls.journal=gzip.decompress((report.DATA/(report.CHAIN_PREFIX+'r3.record.journal.jsonl.gz')).read_bytes())

    def validate(self,record,plan=None,replay=True):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'j.jsonl';p.write_bytes(self.journal)
            if replay:return self.report.validate_chain_run(plan or self.plan,record,p,'r3',self.baseline)
            # Isolate later semantic/coverage checks from the earlier hash-chain check.
            with mock.patch.object(experiment,'reconcile_journal'):
                return self.report.validate_chain_run(plan or self.plan,record,p,'r3',self.baseline)

    def test_real_archive_replays_and_counts_calls_without_models(self):
        counts=self.validate(copy.deepcopy(self.record))
        self.assertEqual(counts,{'skipNoDownstream':1,'generationCalls':3,'targetCalls':3,
                                 'encoderForwardWindows':28,'decoderForwardAttempts':27})

    def test_skip_cannot_be_reported_as_empty_target_inference(self):
        r=copy.deepcopy(self.record);r['attempts'][1]['targets']={'decoded':{'targets':[]}}
        with self.assertRaisesRegex(ValueError,'skip unexpectedly'):self.validate(r,replay=False)

    def test_modified_generated_text_cannot_be_handed_to_targets(self):
        r=copy.deepcopy(self.record);r['attempts'][0]['targets']['case']['input']['source']['actionText']='伪造动作'
        with self.assertRaisesRegex(ValueError,'faithfully handed'):self.validate(r,replay=False)

    def test_missing_roster_probability_is_rejected(self):
        r=copy.deepcopy(self.record);r['attempts'][0]['targets']['probabilities'].pop()
        with self.assertRaisesRegex(ValueError,'target output/probability'):self.validate(r,replay=False)

    def test_stage_handoff_cost_cannot_be_omitted_from_total(self):
        r=copy.deepcopy(self.record);r['attempts'][0]['elapsedIncludingTelemetryMs']=1
        with self.assertRaisesRegex(ValueError,'timing omitted'):self.validate(r,replay=False)

    def test_summary_does_not_turn_empty_targets_or_one_candidate_into_pass(self):
        summary,_=self.report.build_chain()
        self.assertEqual(summary['fullRequest500msStatus'],'unverified')
        self.assertFalse(summary['local50msHardGate']);self.assertFalse(summary['semanticQualityApproved'])
        self.assertEqual([r['counts']['generationCalls'] for r in summary['runs']],[18,18,3])
        self.assertEqual([r['quality']['generatedSemanticFailuresObserved'] for r in summary['runs']],[18,18,2])
        self.assertTrue(all(not r['quality']['formalSemanticPass'] for r in summary['runs']))


class GenerationProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import m01_shared_report as report
        cls.report=report
        cls.record=report.read_archive(report.DATA/'action-focus-dev42-20261104-r1.record.json.gz')

    def sample(self):return copy.deepcopy(next(a for a in self.record['attempts'] if 'generation' in a))

    def test_actual_forward_events_cover_prefill_and_every_generated_token(self):
        a=self.sample();self.report.validate_generation_forwards(a['generation'],a['checkpoints'])
        rows=a['generation']['forwardTimings'];self.assertEqual(rows[0]['phase'],'prefill')
        self.assertEqual(rows[0]['inputTokens'],a['generation']['context']['inputTokens'])
        self.assertTrue(all(r['inputTokens']==1 for r in rows[1:]))
        self.assertEqual(len(rows),len(a['generation']['outputTokenIds']))

    def test_missing_or_misclassified_full_input_prefill_is_rejected(self):
        for change in ('drop','phase','tokens'):
            a=self.sample();g=a['generation']
            if change=='drop':g['forwardTimings'].pop(0)
            elif change=='phase':g['forwardTimings'][0]['phase']='decode'
            else:g['forwardTimings'][0]['inputTokens']=1
            with self.assertRaisesRegex(ValueError,'coverage/count'):self.report.validate_generation_forwards(g,a['checkpoints'])

    def test_forward_completion_or_cost_cannot_be_invented(self):
        a=self.sample();a['checkpoints']=[c for c in a['checkpoints'] if c['name']!='generator_forward_settled']
        with self.assertRaisesRegex(ValueError,'hooks not paired'):self.report.validate_generation_forwards(a['generation'],a['checkpoints'])
        a=self.sample();a['generation']['generationMs']=0
        with self.assertRaisesRegex(ValueError,'time omitted'):self.report.validate_generation_forwards(a['generation'],a['checkpoints'])

    def test_actual_quantized_variant_has_all_linear_weights_and_stays_stable(self):
        self.report.validate_quantized_identity(self.record)
        q=self.record['generatorVariants']['qint8']['before']
        self.assertEqual(len(q['quantizedModules']),169)
        self.assertGreater(q['quantizedWeightElements'],q['residualParameterElements'])
        broken=copy.deepcopy(self.record);broken['generatorVariants']['qint8']['after']['quantizedModules'].pop()
        with self.assertRaisesRegex(ValueError,'weights drift'):self.report.validate_quantized_identity(broken)

    def test_all_failed_directions_are_present_and_not_promoted_to_pass(self):
        summary,_=self.report.build_focus()
        qualities=[q for r in summary['runs'] for q in r['quality']]
        self.assertEqual(sum(q['generatedAttempts'] for q in qualities),36)
        self.assertEqual(sum(q['obviousTaskActorOrMetaFailures'] for q in qualities),27)
        self.assertTrue(all(not q['formalSemanticPass'] for q in qualities))
        self.assertEqual(summary['fullRequest500msStatus'],'unverified')
        self.assertFalse(summary['local50msHardGate'])

class FetchIdentityTests(unittest.TestCase):
    def spec(self,raw,kind):
        import hashlib
        h=hashlib.sha256(raw).hexdigest() if kind=='sha256_of_fetched_bytes' else hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        return {'path':'config.json','size_bytes':len(raw),kind:h}

    def test_registered_git_blob_is_verified_and_sha256_registered(self):
        from fetch_model import fetch_verified
        import hashlib
        raw=b'{"original":true}\n'
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'config.json';p.write_bytes(raw)
            got=fetch_verified(self.spec(raw,'git_blob_sha1'),p)
            self.assertTrue(got['cacheHit']);self.assertEqual(got['sha256'],hashlib.sha256(raw).hexdigest())

    def test_same_length_tampering_is_rejected_without_overwrite(self):
        from fetch_model import fetch_verified
        raw=b'{"original":true}\n';tampered=raw.replace(b'true',b'null')
        for kind in ('git_blob_sha1','sha256_of_fetched_bytes'):
            with tempfile.TemporaryDirectory() as t:
                p=Path(t)/'config.json';p.write_bytes(tampered)
                with self.assertRaisesRegex(ValueError,'local payload differs'):fetch_verified(self.spec(raw,kind),p)
                self.assertEqual(p.read_bytes(),tampered)

    def test_original_sha256_path_remains_supported(self):
        from fetch_model import fetch_verified
        raw=b'{"original":true}\n'
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'config.json';p.write_bytes(raw)
            self.assertEqual(fetch_verified(self.spec(raw,'sha256_of_fetched_bytes'),p)['bytes'],len(raw))

if __name__=='__main__':unittest.main()
