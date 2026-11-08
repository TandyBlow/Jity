"""QA contracts use synthetic HTTP responses only, in disposable directories."""
import asyncio
import base64
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import httpx

from jity_eval import qa_pilot as qa
from jity_eval.capture.journal import BudgetLedger, CallJournal, BudgetExceeded, fingerprint
from jity_eval.storage import atomic_json, digest
from jity_eval.question_bank import read

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "question_banks/full-games-20261106-v1.2"
CONFIG = ROOT / "examples/qa-pilot-20261106.json"
JITY = ROOT.parent


def response(request, status=200, usage=True, content=None, finish="stop"):
    doc = {"model":"synthetic-test-model", "choices":[{"finish_reason":finish, "message":{"role":"assistant", "content":content or '{"answer":"测试回答_ONLY_MOCK","explanation":"离线夹具，不是模型实验"}'}}]}
    if usage:
        doc["usage"] = {"prompt_tokens":100, "completion_tokens":20, "total_tokens":120}
    return httpx.Response(status, json=doc, request=request)


class PilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="jity-qa-offline-fixtures-")
        cls.template = Path(cls.tmp.name) / "template"
        qa.prepare(BANK, CONFIG, cls.template, JITY)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jity-qa-case-")
        self.run = Path(self.temp.name) / "run"
        shutil.copytree(self.template, self.run, copy_function=shutil.copyfile)
        self.plan = read(self.run / "plan.json")
        self.network_guard = patch("httpx.AsyncHTTPTransport", side_effect=AssertionError("Real network transport forbidden in tests"))
        self.network_guard.start()

    def tearDown(self):
        self.network_guard.stop(); self.temp.cleanup()

    def approve(self, ids=None):
        review = read(self.run / "approval-templates/review.json")
        review.update(reviewer="synthetic test only", reviewed_at="2026-11-06", user_confirmation="OFFLINE FIXTURE; not human approval")
        for r in review["questions"]:
            if ids is None or r["id"] in ids:
                r.update(decision="approved", evidence_sufficient=True)
        auth = read(self.run / "approval-templates/budget.json")
        auth.update(decision="approved", confirmed_by="synthetic test only", confirmed_at="2026-11-06", user_confirmation="OFFLINE FIXTURE; no paid authorization")
        atomic_json(self.run / "test-review.json", review); atomic_json(self.run / "test-budget.json", auth)
        return self.run / "test-review.json", self.run / "test-budget.json"

    def execute(self, handler=response, max_samples=1, ids=None, test_key="offline-fixture-key"):
        review, auth = self.approve(ids)
        return qa.execute(self.run, review, auth, max_samples=max_samples, _test_upstream=httpx.MockTransport(handler), _test_key=test_key)

    def change_config(self, **changes):
        # New fixture run rather than editing a frozen plan.
        c = read(CONFIG)
        for k,v in changes.items():
            if k in c["limits"]: c["limits"][k] = v
            else: c[k] = v
        config = Path(self.temp.name)/"config.json"; atomic_json(config,c)
        self.run = Path(self.temp.name)/"new-run"
        qa.prepare(BANK,config,self.run,JITY); self.plan=read(self.run/"plan.json")

    def ledger(self):
        c=read(self.run/"inputs/config.json")
        return BudgetLedger(self.run/"budget.sqlite3",{k:v for k,v in c["limits"].items() if k!='max_attempts_per_sample'},c["prices"])

    def test_pending_review_blocks_before_credentials_and_transport(self):
        with patch.object(qa,"read_credentials",side_effect=AssertionError("credential read")):
            with self.assertRaises(qa.PilotBlocked):
                qa.execute(self.run,self.run/"approval-templates/review.json",self.run/"approval-templates/budget.json")
        self.assertFalse((self.run/"budget.sqlite3").exists())

    def test_new_budget_required_even_after_review(self):
        review,_=self.approve()
        with self.assertRaises(qa.PilotBlocked):
            qa.execute(self.run,review,self.run/"approval-templates/budget.json",_test_key="fake")

    def test_old_collection_authorization_rejected(self):
        review,auth=self.approve();a=read(auth);a.update(scope="game_capture",run_manifest_sha256="old-budget");atomic_json(auth,a)
        with self.assertRaises(qa.PilotBlocked):qa.execute(self.run,review,auth,_test_key="fake")

    def test_channels_question_and_checkpoints_are_shared(self):
        qa.verify(self.run)
        byq={}
        for s in self.plan:
            req=read(self.run/s['request_path']);body=req['body'];user=json.loads(body['messages'][1]['content'])
            self.assertEqual(set(user),{'question','records'})
            self.assertEqual(set(user['records']),qa.CHANNELS[s['mode']])
            self.assertEqual(user['question'],s['question'])
            self.assertEqual(len(user['records']['recent_context']),6)
            shared=(user['question'],user['records']['recent_context'],body['messages'][0],s['checkpoint'])
            if s['question_id'] in byq:self.assertEqual(byq[s['question_id']],shared)
            byq[s['question_id']]=shared
            self.assertNotIn('tools',body)
        self.assertEqual(len(byq),12)

    def test_randomized_counterbalanced_group_order(self):
        groups=[tuple(r['mode'] for r in self.plan[i:i+3]) for i in range(0,36,3)]
        from collections import Counter
        self.assertEqual(sorted(Counter(groups).values()),[2]*6)
        self.assertNotEqual([r['question_id'] for r in self.plan[::3]],sorted(r['question_id'] for r in self.plan[::3]))

    def test_tampered_private_or_future_input_rejected(self):
        s=self.plan[0];p=self.run/s['request_path'];req=read(p)
        req['body']['messages'].append({'role':'system','content':'PRIVATE_GOLD_SENTINEL future answer'})
        atomic_json(p,req)
        with self.assertRaisesRegex(ValueError,'Frozen file changed'):qa.verify(self.run)

    def test_send_boundary_rechecks_next_frozen_request(self):
        calls=[]
        def handler(request):
            calls.append(1)
            p=self.run/self.plan[1]['request_path'];r=read(p);r['body']['messages'][1]['content']='tampered';atomic_json(p,r)
            return response(request)
        with self.assertRaisesRegex(ValueError,'send boundary'):self.execute(handler,max_samples=2)
        self.assertEqual(len(calls),1)

    def test_answer_persisted_and_completed_sample_not_repeated(self):
        calls=[]
        def handler(request):calls.append(json.loads(request.content));return response(request)
        self.execute(handler,2)
        self.execute(handler,1)
        self.assertEqual(len(calls),3)
        self.assertTrue(all('测试回答_ONLY_MOCK' not in json.dumps(b,ensure_ascii=False) for b in calls))
        result=read(self.run/'results.json');answered=[s for s in result['samples'] if s['status']=='answered']
        self.assertEqual(len(answered),3)
        self.assertTrue(all(s['grade']['score'] is None and s['grade']['status']=='pending_human_review' for s in answered))
        for s in answered:
            r=read(self.run/s['response_path']);self.assertTrue(r['raw_text']);self.assertEqual(r['usage']['prompt_tokens'],100)

    def test_unknown_usage_keeps_cost_reservation(self):
        self.execute(lambda r:response(r,usage=False))
        usage=read(self.run/'results.json')['usage']
        self.assertEqual(usage['unknown_usage'],1);self.assertGreater(usage['cost_usd'],0)

    def test_four_budget_caps_stop_before_request(self):
        for key,value in [('max_input_tokens',1),('max_output_tokens',1),('max_cost_usd',.000001)]:
            with self.subTest(key=key):
                # Each configuration owns a distinct frozen fixture.
                self.run=Path(self.temp.name)/('unused-'+key)
                c=read(CONFIG);c['limits'][key]=value;p=Path(self.temp.name)/(key+'.json');atomic_json(p,c)
                qa.prepare(BANK,p,self.run,JITY);self.plan=read(self.run/'plan.json')
                calls=[];self.execute(lambda r:(calls.append(1),response(r))[1])
                self.assertFalse(calls)
                self.assertEqual(read(self.run/'results.json')['counts']['budget_blocked'],1)
        self.change_config(max_attempts=1)
        calls=[];self.execute(lambda r:(calls.append(1),response(r))[1],max_samples=3)
        self.assertEqual(len(calls),1)

    def test_one_attempt_no_retry_for_http_or_parse_error(self):
        calls=[]
        def handler(r):calls.append(1);return response(r,status=429)
        self.execute(handler);self.execute(handler)
        # Second run advances to another sample, never retries the first 429.
        self.assertEqual(len(calls),2)
        self.assertEqual(read(self.run/'results.json')['counts']['api_error'],2)

    def test_parse_error_separate_from_wrong_answer(self):
        self.execute(lambda r:response(r,content='not JSON'))
        s=next(s for s in read(self.run/'results.json')['samples'] if s['status']=='parse_error')
        self.assertIsNone(s['grade']['score']);self.assertEqual(s['grade']['status'],'not_answered')

    def test_complete_http_crash_recovered_without_key_or_resend(self):
        self.execute();s=self.plan[0]
        db=qa.connect(self.run)
        with db:db.execute("UPDATE samples SET status='running',attempts=0,response_path=NULL WHERE id=?",(s['id'],))
        db.close();(self.run/f"responses/{s['id']}.json").unlink()
        with patch.object(qa,'read_credentials',side_effect=AssertionError('must recover without key')):
            self.execute(lambda r:(_ for _ in ()).throw(AssertionError('duplicate request')),test_key=None)
        self.assertEqual(read(self.run/'results.json')['counts']['answered'],1)
        self.assertEqual(read(self.run/'results.json')['model_calls'],1)

    def test_pending_http_is_uncertain_not_resent(self):
        s=self.plan[0];req=read(self.run/s['request_path']);ledger=self.ledger()
        reservation=ledger.reserve(req['body'],{'operation_id':s['id']});ledger.close()
        j=CallJournal(self.run/'calls'/(s['id']+'.sqlite3'))
        j.start({'method':'POST','url':'https://api.deepseek.com/chat/completions','headers':[],'body':req['body']}, {'operation_id':s['id'],'input_sha256':s['source_input_sha256']},reservation);j.close()
        self.execute(lambda r:(_ for _ in ()).throw(AssertionError('must not resend')))
        result=read(self.run/'results.json');self.assertEqual(result['counts']['uncertain'],1);self.assertEqual(result['pending_http_outcome'],1)

    def test_orphan_reservation_is_not_a_new_call(self):
        s=self.plan[0];ledger=self.ledger();ledger.reserve(read(self.run/s['request_path'])['body'],{'operation_id':s['id']});ledger.close()
        self.execute(lambda r:(_ for _ in ()).throw(AssertionError('orphan resend')))
        result=read(self.run/'results.json');self.assertEqual(result['counts']['uncertain'],1);self.assertEqual(result['model_calls'],0);self.assertEqual(result['orphan_reservations'],1)

    def test_over_context_excludes_whole_question(self):
        self.change_config(context_budget_tokens=1500)
        calls=[];self.execute(lambda r:(calls.append(1),response(r))[1])
        r=read(self.run/'results.json');self.assertFalse(calls);self.assertEqual(r['counts']['context_blocked'],36);self.assertEqual(r['eligible_questions'],0)

    def test_approval_scope_is_frozen_after_start(self):
        qid=self.plan[0]['question_id'];self.execute(ids={qid})
        review,auth=self.approve()  # proposes expansion beyond frozen approval
        with self.assertRaisesRegex(ValueError,'Approval changed'):qa.execute(self.run,review,auth,_test_key='fake',_test_upstream=httpx.MockTransport(response))

    def test_model_side_effect_requests_are_not_executed(self):
        def handler(r):return httpx.Response(200,json={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'name':'advance_game'}]}}]},request=r)
        self.execute(handler)
        self.assertEqual(read(self.run/'results.json')['counts']['parse_error'],1)

    def test_missing_response_shapes_and_truncation_are_parse_errors(self):
        for doc in [{'choices':[None]}, {'choices':[{'finish_reason':'stop','message':None}]}, {'choices':[{'finish_reason':'length','message':{'content':'{}'}}]}]:
            raw=base64.b64encode(json.dumps(doc).encode()).decode()
            rec={'status':'complete','response':{'complete':True,'status_code':200,'headers':[],'body_base64':raw,'body_sha256':fingerprint(raw)}}
            self.assertEqual(qa.parse_record(rec)[0],'parse_error')

    def test_report_is_private_and_no_zero_accuracy_for_unrun(self):
        html=(self.run/'report.html').read_text()
        self.assertIn('未评分',html);self.assertIn('不',html)
        self.assertNotIn('<script src=',html)
        r=read(self.run/'results.json');self.assertEqual(r['model_calls'],0);self.assertTrue(all(s['grade']['score'] is None for s in r['samples']))

    def test_timeout_is_durable_uncertain_not_wrong_answer(self):
        def handler(r): raise httpx.ReadTimeout('offline timeout fixture',request=r)
        self.execute(handler)
        r=read(self.run/'results.json');self.assertEqual(r['counts']['uncertain'],1)
        self.assertEqual(r['usage']['unknown_usage'],1)
        self.assertEqual(r['model_calls'],1)

    def test_semantic_grades_require_reviewer_and_response_binding(self):
        self.execute()
        sample=next(s for s in read(self.run/'results.json')['samples'] if s['status']=='answered')
        g=deepcopy(sample['grade']);g.update(id=sample['id'],status='human_reviewed',response_sha256=qa.sha(self.run/sample['response_path']),score=sample['grade']['max_score'])
        for p in g['points']:p.update(status='correct',score=p['max_score'],reason='Synthetic grade contract test only')
        g['dimensions']={k:('correct' if v!='not_applicable' else v) for k,v in g['dimensions'].items()}
        doc={'run_manifest_sha256':qa.sha(self.run/'manifest.json'),'reviewer':'offline test fixture','reviewed_at':'2026-11-06','samples':[g]}
        path=self.run/'test-grades.json';atomic_json(path,doc);qa.import_grades(self.run,path)
        graded=read(self.run/'results.json')['samples'];self.assertEqual(sum(s['grade']['status']=='human_reviewed' for s in graded),1)
        p=self.run/sample['response_path'];r=read(p);r['parsed']['answer']='changed';atomic_json(p,r)
        with self.assertRaisesRegex(ValueError,'Graded response changed'):qa.export(self.run)

    def test_stopped_budget_does_not_prevent_paid_response_recovery(self):
        self.execute();s=self.plan[0]
        db=qa.connect(self.run)
        with db:db.execute("UPDATE samples SET status='running',attempts=0,response_path=NULL WHERE id=?",(s['id'],))
        db.close();ledger=self.ledger()
        with ledger.transaction() as conn:conn.execute("UPDATE budget_control SET stop_reason='fixture durable stop' WHERE id=1")
        ledger.close()
        self.execute(lambda r:(_ for _ in ()).throw(AssertionError('no network')))
        self.assertEqual(read(self.run/'results.json')['counts']['answered'],1)


if __name__ == '__main__':unittest.main()
