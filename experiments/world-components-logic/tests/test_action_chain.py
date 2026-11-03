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
