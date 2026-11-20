"""Process-exit evidence recovery; synthetic cases only, no model execution."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import experiment as runtime


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'events.jsonl';self.sha='synthetic-plan-sha'
        self.slots=[{'arm':'append','caseId':'synthetic','repeat':i,'status':'not_started'} for i in range(2)]
        start={**self.slots[0],'status':'started','startedMonotonicNs':time.monotonic_ns()}
        window={**start,'status':'running','eventId':0,'forwardIndex':0,'windowIndex':0,
                'inputIds':[101,102],'tokenTypeIds':[0,0],'factSpans':[]}
        result={**start,'status':'complete','probabilities':[.25],'decoded':{'kind':'skip'}}
        settled={'arm':'append','caseId':'synthetic','repeat':0,'resultJournalMs':1.,'snapshotEndMs':0.,'elapsedThroughResultMs':2.}
        self.rows=[('begin',{'runId':'synthetic','slots':self.slots}),('attempt_start',start),
                   ('window',window),('window',{**window,'status':'complete'}),
                   ('attempt_result',result),('attempt_settled',settled)]

    def report(self):
        return {'runId':'synthetic','planSha256':self.sha,'status':'running','attemptSlots':copy.deepcopy(self.slots),
                'attempts':[],'forwardAttempts':[],'activeAttempt':None,'stages':[]}

    def write(self,rows=None):
        with runtime.AppendJournal(self.path,self.sha) as journal:
            for kind,data in self.rows if rows is None else rows:journal.append(kind,data)

    def replay(self):
        before=self.path.read_bytes();report=self.report();runtime.reconcile_journal(report,self.path,'synthetic_exit')
        self.assertEqual(self.path.read_bytes(),before);self.assertEqual(report['journalRecovery']['modelCallsDuringReplay'],0)
        return report

    def test_real_child_exit_at_each_persistence_boundary(self):
        # Child exits without a final report or context-manager close. Parent
        # recovers only what was actually written, never recomputes a result.
        code="""import sys,json,os
sys.path.insert(0,sys.argv[1])
from experiment import AppendJournal
j=AppendJournal(sys.argv[2],sys.argv[3])
for kind,data in json.loads(sys.argv[4]):j.append(kind,data)
os._exit(17)
"""
        for count in range(1,len(self.rows)+1):
            with self.subTest(events=count):
                if self.path.exists():self.path.unlink()
                result=subprocess.run([sys.executable,'-c',code,str(BASE),str(self.path),self.sha,json.dumps(self.rows[:count])],capture_output=True)
                self.assertEqual(result.returncode,17,result.stderr.decode());r=self.replay()
                self.assertEqual(r['unexecutedAttempts'],2 if count==1 else 1)
                if count>1:self.assertEqual(r['attempts'][0]['status'],'complete' if count==6 else 'result_saved_timing_incomplete' if count==5 else 'interrupted')
                if count==3:self.assertEqual(r['forwardAttempts'][0]['status'],'interrupted')
                if count>=5:self.assertEqual(r['attempts'][0]['decoded'],{'kind':'skip'})
                if count==6:self.assertFalse(r['attempts'][0]['exactTelemetryTimingAvailable'])

    def test_partial_utf8_tail_keeps_previous_results_and_original_bytes(self):
        self.write()
        with self.path.open('ab') as stream:stream.write(b'{"partial":"\xe4\xb8')
        r=self.replay();self.assertGreater(r['journalRecovery']['partialTailBytes'],0)
        self.assertEqual(r['attempts'][0]['decoded'],{'kind':'skip'});self.assertEqual(r['status'],'stopped_incomplete')

    def test_complete_line_damage_wrong_plan_reordering_and_duplicate_are_rejected(self):
        self.write();original=self.path.read_bytes();lines=original.splitlines(keepends=True)
        variants=[b'bad-json\n'+b''.join(lines[1:]),b''.join(lines[:2]+[lines[2],lines[2]]+lines[3:]),
                  b''.join([lines[1],lines[0]]+lines[2:]),original.replace(b'"skip"',b'"act"')]
        for raw in variants:
            self.path.write_bytes(raw)
            with self.assertRaises((ValueError,KeyError)):self.replay()
        self.path.write_bytes(original)
        with self.assertRaisesRegex(ValueError,'identity'):runtime.read_journal(self.path,'wrong-plan')

    def test_valid_hashes_do_not_allow_duplicate_or_out_of_order_transitions(self):
        variants=[self.rows+[self.rows[1]],self.rows[:2]+[self.rows[-1]],
                  self.rows[:3]+[self.rows[2]],self.rows[:1]+[self.rows[3]],
                  self.rows[:2]+[('attempt_start',{**self.rows[1][1],'caseId':'unknown'})],
                  self.rows[:1]+[('unknown',{})]]
        for rows in variants:
            if self.path.exists():self.path.unlink()
            self.write(rows)
            with self.assertRaises(ValueError):self.replay()

    def test_existing_log_is_never_overwritten(self):
        self.write();original=self.path.read_bytes()
        with self.assertRaises(FileExistsError):runtime.AppendJournal(self.path,self.sha)
        self.assertEqual(original,self.path.read_bytes())

    def test_attempt_boundaries_fsync_and_window_events_flush(self):
        with mock.patch.object(runtime.os,'fsync') as sync:
            self.write()
        self.assertEqual(sync.call_count,4) # begin/start/result/settled, not window pairs
        self.assertEqual(len(runtime.read_journal(self.path,self.sha)[0]),6)

    def test_snapshot_keeps_exact_telemetry_only_when_result_and_timing_match(self):
        self.write();r=self.report()
        r['attempts']=[{**self.rows[-2][1],**self.rows[-1][1],'telemetryJournalMs':.2,'elapsedIncludingTelemetryMs':2.2}]
        runtime.reconcile_journal(r,self.path,'exit')
        self.assertEqual(r['attempts'][0]['elapsedIncludingTelemetryMs'],2.2)
        r=self.report();r['attempts']=[{**self.rows[-2][1],**self.rows[-1][1],'decoded':{'kind':'act'},'elapsedIncludingTelemetryMs':0.}]
        runtime.reconcile_journal(r,self.path,'exit')
        self.assertNotIn('elapsedIncludingTelemetryMs',r['attempts'][0]);self.assertEqual(r['attempts'][0]['decoded'],{'kind':'skip'})

    def test_compressed_archive_prevents_accidental_rerun(self):
        out=Path(self.temp.name)/'record.json';out.with_suffix('.json.gz').write_bytes(b'prior archive')
        plan=Path(self.temp.name)/'plan.json';plan.write_text('{"runId":"synthetic"}')
        with mock.patch.object(runtime.subprocess,'Popen') as launch:
            with self.assertRaises(FileExistsError):
                runtime.execute_plan(plan,paths=lambda _: (plan,out),verify=lambda _:None,worker_script=Path('unused'),settle_stages=lambda *_:None,arms=('append',))
            launch.assert_not_called()


if __name__=='__main__':unittest.main()
