"""Durable clock-input recovery with strict HTTP replay and mock responses."""
import asyncio
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

import httpx

from jity_eval.capture import clocks as clock
from jity_eval.capture.journal import MissingCapture, UncertainCapture
from jity_eval.capture.journal import CallJournal
from jity_eval.capture.transport import CaptureTransport, capture_scope
from jity_eval.capture.safety import capture_network_guard


class DB:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.execute('CREATE TABLE session_messages(id INTEGER PRIMARY KEY,session_id TEXT,turn_node_id INTEGER,role TEXT,content TEXT,campaign_session_index INTEGER,created_at TEXT)')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path)
        db.row_factory=sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()


class FakeRuntime:
    def __init__(self, database, evidence, mode, created_at, prefix=()):
        self.db=DB(database)
        self.config={'message_clock_path':str(evidence)}
        self.session_id='fixture'
        self.transport=SimpleNamespace(mode=mode,_prefix=list(prefix),fatal=None)
        self.created_at=created_at
        self.events=[]

    def _event(self, kind, payload):
        self.events.append((kind,payload))

    async def start(self):
        return {'started':True}

    async def generate(self,payload):
        if payload.get('ending_request'):
            # Historical ending material included complete DB rows. Keep this
            # fixture shape even when future Jity prompts select fewer fields.
            with self.db.connect() as db:
                rows=clock.rows_from_connection(db,self.session_id)
            material={'最近剧情':[{key:row[key] for key in
                ('id','role','content','campaign_session_index','created_at')} for row in rows]}
            prompt='[STORY_MATERIAL_START]\n'+json.dumps(material,ensure_ascii=False)+'\n[STORY_MATERIAL_END]'
            async with httpx.AsyncClient(transport=self.transport) as client:
                with capture_scope(game_id=self.session_id,operation_id='fixture:turn-3',turn=3,purpose='ending_narrative'):
                    response=await client.post('https://clock-fixture.invalid/chat/completions',json={
                        'model':'fixture','messages':[{'role':'user','content':prompt}],
                        'temperature':.4,'max_tokens':100})
                    self.ending=response.json()['choices'][0]['message']['content']
        with self.db.connect() as db:
            count=db.execute('SELECT COUNT(*) FROM session_messages').fetchone()[0]
            for offset,role in ((1,'user'),(2,'assistant')):
                db.execute('INSERT INTO session_messages VALUES(?,?,?,?,?,?,?)',
                  (count+offset,'fixture',count//2+2,role,payload['content'],0,self.created_at))
        if payload.get('fail_after_commit'):
            raise ValueError('simulated postcommit observer error')
        return {'turn':count//2+1}

    async def reload(self):
        return {'reloaded':True}


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='clock-adapter-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.path=self.root/'message-clocks.json'
        self.handle=clock.install_clock_adapter(FakeRuntime)
        self.addCleanup(self.handle.uninstall)

    def runtime(self,name,mode='record',timestamp='2026-11-06 01:02:03',prefix=()):
        return FakeRuntime(self.root/(name+'.sqlite3'),self.path,mode,timestamp,prefix)

    def test_new_record_fsync_before_return_and_replay_restores_only_clock(self):
        async def go():
            runtime=self.runtime('record')
            await runtime.start()
            await runtime.generate({'content':'same exact original message'})
            saved=json.loads(self.path.read_text())
            self.assertEqual(len(saved['entries']),2)
            before=self.path.read_bytes()
            replay=self.runtime('replay','replay','2099-12-31 23:59:59')
            await replay.start()
            await replay.generate({'content':'same exact original message'})
            await replay.reload()
            with replay.db.connect() as db:
                rows=clock.rows_from_connection(db,'fixture')
            self.assertTrue(all(row['created_at']=='2026-11-06 01:02:03' for row in rows))
            self.assertTrue(all(row['content']=='same exact original message' for row in rows))
            self.assertEqual(before,self.path.read_bytes())
            self.assertEqual(sum(kind=='message_clock_restored' for kind,payload in replay.events),2)
        asyncio.run(go())

    def test_committed_error_still_persists_clock_and_recovery_reuses_it(self):
        async def go():
            record=self.runtime('interrupted')
            await record.start()
            with self.assertRaisesRegex(ValueError,'postcommit'):
                await record.generate({'content':'persist once','fail_after_commit':True})
            self.assertEqual(len(json.loads(self.path.read_text())['entries']),2)
            resumed=self.runtime('resumed','record','2099-01-01 00:00:00',prefix=[{'known_raw_reply':True}])
            await resumed.start()
            await resumed.generate({'content':'persist once'})
            with resumed.db.connect() as db:
                rows=clock.rows_from_connection(db,'fixture')
            self.assertTrue(all(row['created_at']=='2026-11-06 01:02:03' for row in rows))
        asyncio.run(go())

    def test_unknown_legacy_prefix_requires_seed_and_replay_missing_fails(self):
        async def go():
            for name,mode,prefix in [('legacy','record',[1]),('missing','replay',[])]:
                runtime=self.runtime(name,mode,prefix=prefix)
                with self.assertRaises(MissingCapture):
                    await runtime.start()
                self.assertFalse(self.path.exists())
        asyncio.run(go())

    def test_content_mismatch_does_not_substitute_message_or_accept_replay(self):
        async def go():
            record=self.runtime('record')
            await record.start()
            await record.generate({'content':'original'})
            replay=self.runtime('mismatch','replay')
            await replay.start()
            with self.assertRaises(UncertainCapture):
                await replay.generate({'content':'different'})
            with replay.db.connect() as db:
                self.assertEqual(db.execute('SELECT content FROM session_messages WHERE id=1').fetchone()[0],'different')
            self.assertIsInstance(replay.transport.fatal,UncertainCapture)
        asyncio.run(go())

    def test_missing_message_clock_and_unused_tail_fail_explicitly(self):
        async def go():
            record=self.runtime('record')
            await record.start()
            await record.generate({'content':'first'})
            await record.generate({'content':'second'})
            replay=self.runtime('short','replay')
            await replay.start()
            await replay.generate({'content':'first'})
            with self.assertRaises(UncertainCapture):
                await replay.reload()
            document=json.loads(self.path.read_text());del document['entries']['2']
            clock.atomic_json(self.path,document)
            missing=self.runtime('missing','replay')
            await missing.start()
            with self.assertRaises(MissingCapture):
                await missing.generate({'content':'first'})
        asyncio.run(go())

    def test_ending_material_reuses_recorded_clocks_with_exact_http_matching(self):
        async def go():
            journal=CallJournal(self.root/'calls.sqlite3')
            self.addCleanup(journal.close)
            requests=[]
            def upstream(request):
                requests.append(json.loads(request.content))
                return httpx.Response(200,json={'model':'fixture','choices':[
                    {'message':{'role':'assistant','content':'原始结局'},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':20,'completion_tokens':4,'total_tokens':24}})
            record=self.runtime('http-record')
            record.transport=CaptureTransport(journal,httpx.MockTransport(upstream))
            await record.start()
            for content in ('最初的线索','最后的决定'):
                await record.generate({'content':content})
            await record.generate({'content':'结束','ending_request':True})
            recorded_clocks=self.path.read_bytes()
            self.assertEqual(len(requests),1)
            material=json.loads(requests[0]['messages'][0]['content'].split('\n',1)[1].rsplit('\n',1)[0])
            self.assertEqual(len(material['最近剧情']),4)
            self.assertTrue(all(row['created_at']=='2026-11-06 01:02:03' for row in material['最近剧情']))

            replay=self.runtime('http-replay','replay','2099-12-31 23:59:59')
            replay.transport=CaptureTransport(journal,mode='replay')
            with capture_network_guard():
                await replay.start()
                for content in ('最初的线索','最后的决定'):
                    await replay.generate({'content':content})
                await replay.generate({'content':'结束','ending_request':True})
                await replay.reload()
                self.assertEqual(replay.transport.assert_consumed()['network_attempts'],0)
            self.assertEqual(replay.ending,record.ending)
            self.assertEqual(self.path.read_bytes(),recorded_clocks)
            self.assertEqual(len(requests),1)
            self.assertEqual(len(journal.records()),1)

            # A timestamp mismatch remains fatal at the original matcher.
            changed=deepcopy(requests[0])
            changed['messages'][0]['content']=changed['messages'][0]['content'].replace(
                '2026-11-06 01:02:03','2099-12-31 23:59:59')
            transport=CaptureTransport(journal,mode='replay')
            async with httpx.AsyncClient(transport=transport) as client:
                with capture_scope(game_id='fixture',operation_id='fixture:turn-3',turn=3,purpose='ending_narrative'):
                    with self.assertRaises(MissingCapture):
                        await client.post('https://clock-fixture.invalid/chat/completions',json=changed)
        asyncio.run(go())

    def test_evidence_from_different_manifest_fails(self):
        async def go():
            game=self.root/'fixture'
            game.mkdir()
            self.path=game/'message-clocks.json'
            manifest=self.root/'manifest.json'
            manifest.write_text(json.dumps({'config':{'version':1}}))
            record=self.runtime('manifest-record')
            await record.start()
            manifest.write_text(json.dumps({'config':{'version':2}}))
            replay=self.runtime('manifest-replay','replay')
            with self.assertRaisesRegex(UncertainCapture,'different frozen manifest'):
                await replay.start()
        asyncio.run(go())


if __name__=='__main__':
    unittest.main()
