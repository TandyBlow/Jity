"""Engineering counterexamples only; scripted providers are not model evidence.

Apply the proposed patch to a temporary copy, never to frozen runtime sources.
"""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'experiments/world-components-logic'))
from short_contracts import incomplete, result
from short_lifecycle import propose_time


def load_proposal():
    identity = json.loads((HERE / 'proposal.json').read_text())
    source = ROOT / identity['baseSource']
    raw = source.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == identity['baseSourceSha256'], 'frozen source drift'
    temporary = tempfile.TemporaryDirectory()
    target = Path(temporary.name) / identity['baseSource']
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    subprocess.run(['patch', '-p1', '-i', str(HERE / 'implementation.patch')],
                   cwd=temporary.name, check=True, capture_output=True, timeout=5)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == identity['proposedSourceSha256']
    spec = importlib.util.spec_from_file_location('time_choice_proposed_only', target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return temporary, module


class TimeChoiceProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary, cls.module = load_proposal()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def context(self):
        return {'world': {'initial': {'record': 'unchangeable'},
                         'characters': {'actor': {'tasks': {'waiting': 'five minutes'}}},
                         'time': 'original'},
                'frozenActions': [{'memberId': 'actor', 'actionText': 'test-only frozen action'}],
                'timeAdvance': None, 'timeLocked': False, 'pointId': 'point',
                'actualJudgments': [{'rollId': 'unchanged-roll'}]}

    def test_elapsed_uses_actual_unit_before_amount_and_full_context(self):
        for prefix in ('D08.1', 'D08.2.time'):
            with self.subTest(prefix=prefix):
                payload = self.context(); before = copy.deepcopy(payload); calls = []
                def provider(task, p):
                    calls.append((task, copy.deepcopy(p)))
                    return result('elapsed' if task.endswith('.boundary') else 'second' if task.endswith('.unit') else '300')
                answer = self.module.LifecycleHeads(provider).time(prefix, payload)
                self.assertEqual([n for n, _ in calls], [prefix+'.boundary', prefix+'.unit', prefix+'.amount'])
                self.assertEqual(calls[0][1], before)
                self.assertEqual(calls[1][1], dict(before, timeChoice={'boundary': 'elapsed'}))
                self.assertEqual(calls[2][1], dict(before, timeChoice={'boundary': 'elapsed', 'unit': 'second'}))
                self.assertEqual(answer, {'boundary': 'elapsed', 'duration': {'amount': 300, 'unit': 'second'}})
                self.assertEqual(payload, before)

    def test_d08_segment_preserves_prefix_and_passes_full_time_to_members(self):
        payload = self.context() | {'order': ['actor'], 'visitedIds': [], 'planningScope': 'initial'}
        calls = []
        def provider(task, p):
            calls.append((task, copy.deepcopy(p)))
            if task.endswith('.next_kind'): return result('normal' if not p['proposedSegments'] else 'end')
            if task.endswith('.boundary'): return result('elapsed')
            if task.endswith('.unit'): return result('minute')
            if task.endswith('.amount'): return result('5')
            if task.endswith('.actor'): return result('include')
            raise AssertionError(task)
        answer = self.module.LifecycleHeads(provider)('D08.2', payload)
        self.assertEqual(answer.status, 'result')
        amount = next(p for n, p in calls if n.endswith('.amount'))
        self.assertEqual(amount['proposedKind'], 'normal')
        self.assertEqual(amount['proposedSegments'], [])
        self.assertEqual(amount['world'], payload['world'])
        self.assertEqual(amount['timeChoice'], {'boundary': 'elapsed', 'unit': 'minute'})
        actor = next(p for n, p in calls if n.endswith('.actor'))
        self.assertEqual(actor['proposedTimeAdvance'], {'boundary': 'elapsed', 'duration': {'amount': 5, 'unit': 'minute'}})

    def test_instant_does_not_invoke_unit_or_amount(self):
        calls = []
        def provider(task, p): calls.append(task); return result('instant')
        answer = self.module.LifecycleHeads(provider)('D08.1', self.context())
        self.assertEqual(answer.value, {'boundary': 'instant', 'duration': {'amount': 0, 'unit': 'second'}})
        self.assertEqual(calls, ['D08.1.boundary'])

    def test_unit_failure_stops_before_amount(self):
        calls = []
        def provider(task, p):
            calls.append(task)
            return result('elapsed') if task.endswith('.boundary') else incomplete('untrained_unit')
        answer = self.module.LifecycleHeads(provider)('D08.1', self.context())
        self.assertEqual(answer.status, 'incomplete')
        self.assertIn('untrained_unit', answer.reason)
        self.assertEqual(calls, ['D08.1.boundary', 'D08.1.unit'])

    def test_amount_failure_is_not_zero(self):
        def provider(task, p):
            return result('elapsed') if task.endswith('.boundary') else result('minute') if task.endswith('.unit') else incomplete('timeout')
        answer = self.module.LifecycleHeads(provider)('D08.1', self.context())
        self.assertEqual(answer.status, 'incomplete')
        self.assertIsNone(answer.value)
        self.assertIn('timeout', answer.reason)

    def test_invalid_unit_does_not_reach_amount(self):
        calls = []
        def provider(task, p): calls.append(task); return result('elapsed' if task.endswith('.boundary') else 'millisecond')
        answer = self.module.LifecycleHeads(provider)('D08.1', self.context())
        self.assertEqual(answer.status, 'incomplete')
        self.assertEqual(calls, ['D08.1.boundary', 'D08.1.unit'])

    def test_invalid_and_overflow_amount_rejected_without_coercion(self):
        for raw in (True, 1.5, '2.5', '-1', '9007199254740992', '5 minute'):
            with self.subTest(raw=raw):
                def provider(task, p):
                    return result('elapsed' if task.endswith('.boundary') else 'minute' if task.endswith('.unit') else raw)
                answer = self.module.LifecycleHeads(provider)('D08.1', self.context())
                self.assertEqual(answer.status, 'incomplete')
                self.assertIsNone(answer.value)

    def test_upstream_failure_not_transformed_to_instant(self):
        calls = []
        def provider(task, p): calls.append(task); return incomplete('cancelled')
        answer = self.module.LifecycleHeads(provider)('D08.1', self.context())
        self.assertEqual(answer.status, 'incomplete')
        self.assertEqual(calls, ['D08.1.boundary'])

    def test_stale_time_choice_never_overrides_actual_selection(self):
        payload = self.context() | {'timeChoice': {'boundary': 'instant', 'unit': 'year'}}
        before = copy.deepcopy(payload); seen = []
        def provider(task, p):
            seen.append((task, p)); return result('elapsed' if task.endswith('.boundary') else 'second' if task.endswith('.unit') else '10')
        answer = self.module.LifecycleHeads(provider)('D08.1', payload)
        self.assertEqual(answer.value['duration'], {'amount': 10, 'unit': 'second'})
        self.assertEqual(seen[-1][1]['timeChoice'], {'boundary': 'elapsed', 'unit': 'second'})
        self.assertEqual(payload, before)

    def test_locked_time_remains_zero_call_reuse(self):
        class NoModel:
            def call(self, *args): raise AssertionError('locked time called model')
        value = {'boundary': 'elapsed', 'duration': {'amount': 5, 'unit': 'minute'}}
        answer = propose_time(NoModel(), self.context() | {'timeLocked': True, 'timeAdvance': value})
        self.assertEqual(answer.status, 'result')
        self.assertEqual(answer.value, value)


if __name__ == '__main__': unittest.main()
