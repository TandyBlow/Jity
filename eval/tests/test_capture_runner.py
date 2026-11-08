"""Crash-window acceptance for the frozen CLI runner, using mock HTTP only."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


JITY_ROOT = Path(__file__).resolve().parents[2]

WORKER = r'''
import asyncio, json, sys
from pathlib import Path
import httpx
import jity_eval.capture.runner as runner

out, mode = Path(sys.argv[1]), sys.argv[2]
spec = runner.read_json(out / 'manifest.json')['games'][0]
network_calls = 0
async def mock_provider(request):
    global network_calls
    network_calls += 1
    body = json.loads(request.content)
    if request.url.path.endswith('/embeddings'):
        return httpx.Response(404, json={'error': {'message': 'fixture unsupported', 'type': 'not_found'}})
    prompt = body['messages'][0]['content']
    if prompt.startswith('你是TRPG叙事摘要系统'):
        result = {'summary': '你调查学院并记住了发生的事情。', 'tags': ['调查'], 'importance': .7}
    elif 'TRPG叙事导演系统（Director）' in prompt:
        result = {'narrative_direction': '继续当前调查', 'anchor_triggered': ''}
    elif '角色档案' in prompt and 'characters' in prompt and body['max_tokens'] == 2000:
        result = {'characters': {'player': {'entries': {'goals': ['调查学院']}}}}
    elif body.get('response_format') is None:
        return httpx.Response(200, json={'id':'fixture','object':'chat.completion','created':1,'model':body['model'],
          'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'你继续调查学院，记住途中获得的线索。'}}],
          'usage':{'prompt_tokens':100,'completion_tokens':30,'total_tokens':130}})
    else:
        result = {'narration': '你沿着学院的走廊继续调查，将每一处细节记在心里。',
          'current_location': '卡塞尔学院报到大厅', 'options': ['继续', '观察周围'], 'option_checks': [None, None],
          'memory_updates': {'key_event': '继续调查学院'}}
    return httpx.Response(200, json={'id':'fixture','object':'chat.completion','created':1,'model':body['model'],
      'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(result,ensure_ascii=False)}}],
      'usage':{'prompt_tokens':100,'completion_tokens':30,'total_tokens':130}})

if mode == 'before_checkpoint':
    original = runner.atomic_json
    def crash(path, value):
        if Path(path).parent.name == 'checkpoints' and Path(path).name == 'turn-0006.json':
            raise RuntimeError('injected crash after database commit before checkpoint file')
        return original(path, value)
    runner.atomic_json = crash
elif mode == 'after_checkpoint':
    original = runner._update_game
    def crash(out, spec, **fields):
        if fields.get('status') == 'recording' and fields.get('turns') == 6:
            raise RuntimeError('injected crash after checkpoint file before game metadata')
        return original(out, spec, **fields)
    runner._update_game = crash

try:
    result = asyncio.run(runner.execute_game(out, spec, replay=mode == 'replay',
        api_key=None if mode == 'replay' else 'fixture-credential',
        upstream=None if mode == 'replay' else httpx.MockTransport(mock_provider)))
except RuntimeError as exc:
    if mode not in ('before_checkpoint','after_checkpoint'):
        raise
    result = {'expected_interruption': str(exc)}
print(json.dumps({'result':result,'network_calls':network_calls},ensure_ascii=False))
'''


class CaptureRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.version_info < (3, 11) or not (JITY_ROOT / "backend/app").is_dir():
            raise unittest.SkipTest("Jity runtime requires Python 3.11 and the parent Jity checkout")
        for dependency in ("numpy", "pydantic_settings", "tiktoken", "openai", "json_repair", "httpx"):
            if importlib.util.find_spec(dependency) is None:
                raise unittest.SkipTest("Missing Jity dependency: " + dependency)

    def setUp(self):
        from jity_eval.capture.runner import create_dataset
        self.temp = tempfile.TemporaryDirectory(prefix="jity-capture-runner-test-")
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "dataset"
        create_dataset(JITY_ROOT, self.out, max_cost_usd=10, approval="Offline mock-only acceptance; no real API authorization")
        self.worker = Path(self.temp.name) / "worker.py"
        self.worker.write_text(WORKER, encoding="utf-8")

    def worker_run(self, mode):
        env = {**os.environ, "PYTHONPATH": str(self.out / "sources/evaluator"), "PYTHONDONTWRITEBYTECODE": "1"}
        env = {key: value for key, value in env.items() if not any(secret in key.upper() for secret in ("API_KEY", "SECRET", "PASSWORD"))}
        result = subprocess.run([sys.executable, str(self.worker), str(self.out), mode],
                                cwd=self.out, env=env, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def exercise_window(self, window):
        interrupted = self.worker_run(window)
        self.assertIn("expected_interruption", interrupted["result"])
        before = json.loads((self.out / "smoke/game.json").read_text())
        self.assertEqual(before["turns"], 5, interrupted)
        intent = (self.out / "smoke/intents/turn-0006.json").read_bytes()
        resumed = self.worker_run("resume")
        self.assertEqual(resumed["result"]["turns"], 8)
        self.assertEqual((self.out / "smoke/intents/turn-0006.json").read_bytes(), intent)
        # Only turns 7 and 8 require new Director/Narrator replies. The already
        # completed turn 6 and its NSB summary must be recovered from raw tape.
        self.assertEqual(resumed["network_calls"], 4)
        calls = json.loads((self.out / "smoke/calls.json").read_text())
        self.assertEqual(sum(c["context"].get("purpose") == "memory_nsb_summary" for c in calls), 1)
        replayed = self.worker_run("replay")
        self.assertEqual(replayed["network_calls"], 0)
        self.assertEqual(replayed["result"]["status"], "passed", replayed)
        self.assertEqual(replayed["result"]["turns"], 8)
        self.assertTrue(replayed["result"]["all_calls_consumed"])
        self.assertTrue((self.out / "report.html").is_file())

    def test_resume_after_commit_before_checkpoint(self):
        self.exercise_window("before_checkpoint")

    def test_resume_after_checkpoint_before_game_metadata(self):
        self.exercise_window("after_checkpoint")


if __name__ == "__main__":
    unittest.main()
