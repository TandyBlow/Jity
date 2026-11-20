"""Synthetic runtime doubles; no real inference or project opinions here."""
import contextlib
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import run_pilot as pilot
import pilot_codec
import review_io


class Tensor:
    shape = (1, 40)
    def tolist(self): return [0, 8, 1]


class Tokenizer:
    def __init__(self, raw='{"kind":"skip"}', size=40): self.raw, self.size = raw, size
    def __call__(self, prompt, **kwargs):
        assert kwargs['truncation'] is False
        return {'input_ids': SimpleNamespace(shape=(1, self.size))}
    def decode(self, output, **kwargs): return self.raw


class Model:
    generation_config = SimpleNamespace(eos_token_id=1)
    def __init__(self): self.calls = 0
    def generate(self, **kwargs):
        self.calls += 1
        return [Tensor()]


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.case = pilot.select_cases()[0][0]
        self.plan = {'runId': 'qa-only', 'configSha256': 'qa-only', 'model': {'modelId': 'QA_SYNTHETIC', 'revision': 'qa'},
                     'instructions': pilot.INSTRUCTIONS,
                     'config': {'maxInputTokens': 512, 'softGenerationSeconds': 3,
                                'maxNewTokens': {'D02': 128}}}
        self.ns = {'torch': SimpleNamespace(inference_mode=contextlib.nullcontext),
                   'StoppingCriteriaList': list, 'MaxTimeCriteria': lambda **kwargs: kwargs}

    def test_real_selection_matches_previously_received_user_review(self):
        cases, review = pilot.select_cases()
        self.assertEqual({c['task'] for c in cases}, {'D02','D03','D04','D05'})
        self.assertEqual(review['recorded'], 42)
        self.assertTrue(all(c['split'] == 'development' for c in cases))
        self.assertFalse(review['reviewerIdentityAuthenticated'])

    def test_overflow_never_truncates_or_calls_model(self):
        model = Model()
        result = pilot.run_attempt(self.case, self.plan, self.ns, Tokenizer(size=900), model, 0)
        self.assertEqual(result['status'], 'input_overflow')
        self.assertEqual(model.calls, 0)
        self.assertFalse(result['generationPerformed'])
        self.assertEqual(result['inputTokens'], 900)
        self.assertIn('elapsedMs', result)
        for person in self.case['input']['world']['characters']:
            self.assertIn(person['name'], result['prompt'])
        self.assertEqual(result['semanticReview'], 'pending_not_automatically_approved')

    def test_raw_invalid_model_answer_and_time_are_retained(self):
        raw = '不符合JSON的原始回答'
        result = pilot.run_attempt(self.case, self.plan, self.ns, Tokenizer(raw), Model(), 0)
        self.assertEqual(result['status'], 'invalid_output')
        self.assertEqual(result['raw'], raw)
        self.assertIn('parseError', result)
        self.assertIn('generateMs', result)
        self.assertFalse(result['fullRequestMeasured'])

    def test_valid_shape_does_not_approve_semantics(self):
        result = pilot.run_attempt(self.case, self.plan, self.ns, Tokenizer(), Model(), 0)
        self.assertEqual(result['structureStatus'], 'valid')
        self.assertEqual(result['parsed'], {'kind': 'skip'})
        self.assertEqual(result['semanticReview'], 'pending_not_automatically_approved')

    def test_guarded_input_never_enters_tokenizer_or_model(self):
        case = copy.deepcopy(self.case);case['input']['advance']['inputText'] = None
        tokenizer, model = mock.Mock(), Model()
        result = pilot.run_attempt(case, self.plan, self.ns, tokenizer, model, 0)
        self.assertEqual(result['status'], 'guarded')
        tokenizer.assert_not_called();self.assertEqual(model.calls, 0)

    def test_incomplete_output_never_becomes_valid(self):
        class Unfinished(Tensor):
            def tolist(self): return [0,8,9]
        model = Model();model.generate = lambda **kwargs: [Unfinished()]
        result = pilot.run_attempt(self.case, self.plan, self.ns, Tokenizer(), model, 0)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['structureStatus'], 'not_evaluated')

    def test_preflight_failure_leaves_evidence_before_model_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, record = Path(tmp)/'plan.json', Path(tmp)/'record.json'
            plan.write_text(json.dumps({'runId': 'qa-only'}))
            with mock.patch.object(pilot, 'paths', return_value=(plan, record)), mock.patch.object(
                    pilot, 'verify_plan', side_effect=ValueError('identity changed')):
                with self.assertRaisesRegex(ValueError, 'identity changed'):
                    pilot.execute(plan)
            value = json.loads(record.read_text())
            self.assertEqual(value['status'], 'failed_preflight')
            self.assertEqual(value['generationCalls'], 0)
            self.assertEqual(value['attempts'], [])

    def test_existing_evidence_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'record.json'
            pilot.exclusive(path, {'original': True})
            with self.assertRaises(FileExistsError): pilot.exclusive(path, {'original': False})
            self.assertEqual(json.loads(path.read_text()), {'original': True})

    def test_lossless_codec_keeps_all_42_inputs_and_their_order(self):
        for case in review_io.build_packet()['cases']:
            value = case['input']
            packed = pilot_codec.pack(value)
            self.assertEqual(pilot_codec.unpack(packed), value)
            self.assertEqual(pilot.digest(pilot_codec.unpack(packed)), pilot.digest(value))

    def test_codec_preserves_null_missing_boolean_and_repeated_facts(self):
        value = {'world': [{'id': 'a', 'text': '共用的完整句子不能因重复就被删掉。', 'eligible': False, 'parentId': None},
                           {'id': 'b', 'text': '共用的完整句子不能因重复就被删掉。', 'eligible': True, 'parentId': None}],
                 'source': {'actionText': ''}, 'judgments': [], 'alreadyActedIds': ['b','a']}
        self.assertEqual(pilot_codec.unpack(pilot_codec.pack(value)), value)
        self.assertNotIn('parentId', pilot_codec.unpack(pilot_codec.pack(value))['source'])
        self.assertEqual(value['alreadyActedIds'], ['b','a'])

    def test_codec_rejects_damaged_table_and_shared_reference(self):
        for bad in ({'格式': '无损表格1', '共用文本': [], '资料': {'同文': 0}},
                    {'格式': '无损表格1', '共用文本': [], '资料': {'列': ['编号','正文'], '行': [['a']]}}):
            with self.assertRaises(ValueError): pilot_codec.unpack(bad)

    def test_packed_attempt_binds_full_input_and_uses_its_own_prompt(self):
        self.plan['config']['serialization'] = 'lossless_chinese_tables_v1'
        result = pilot.run_attempt(self.case, self.plan, self.ns, Tokenizer(), Model(), 0)
        self.assertTrue(result['losslessRoundTripMatched'])
        self.assertEqual(result['modelInputSha256'], pilot.digest(self.case['input']))
        self.assertNotIn('draftExpected', result['prompt'])
        self.assertIn('无损表格1', result['prompt'])

    def test_generation_exception_is_still_a_started_call_with_timing(self):
        model = Model()
        def fail(**kwargs):
            model.calls += 1
            raise RuntimeError('QA synthetic generation failure')
        model.generate = fail
        result = pilot.run_attempt(self.case, self.plan, self.ns, Tokenizer(), model, 0)
        self.assertEqual(model.calls, 1)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['generationStarted'])
        self.assertTrue(result['generationPerformed'])
        self.assertFalse(result['generationCompleted'])
        self.assertGreaterEqual(result['generateMs'], 0)
        self.assertIn('settledAt', result)

    def test_killed_active_attempt_is_retained_and_settled_only_after_exit(self):
        plan = {'cases': [self.case], 'config': {'attemptsPerCase': 5}}
        start = time.monotonic_ns()-2_000_000
        active = {'caseId': self.case['caseId'], 'repeat': 0, 'status': 'started',
                  'startedAt': 'qa-only', 'startedMonotonicNs': start,
                  'generationStarted': True, 'generationCompleted': False,
                  'generationStartedMonotonicNs': start+1_000_000, 'activeStage': 'generate'}
        report = {'attempts': [], 'attemptSlots': pilot.planned_slots(plan), 'activeAttempt': active}
        pilot.settle_interrupted(report, plan, 'resident_memory_limit')
        self.assertEqual(len(report['attempts']), 1)
        self.assertEqual(report['attempts'][0]['status'], 'interrupted')
        self.assertEqual(report['attempts'][0]['stopReason'], 'resident_memory_limit')
        self.assertEqual(report['generationCalls'], 1)
        self.assertEqual(report['notStartedAttempts'], 4)
        self.assertEqual(report['attemptSlots'][0], report['attempts'][0])
        self.assertGreater(report['attempts'][0]['settledElapsedMs'], 0)
        pilot.settle_interrupted(report, plan, 'resident_memory_limit')
        self.assertEqual(len(report['attempts']), 1)

    def test_decode_interruption_preserves_completed_generation_time(self):
        plan = {'cases': [self.case], 'config': {'attemptsPerCase': 1}}
        active = {'caseId': self.case['caseId'], 'repeat': 0, 'status': 'started',
                  'startedMonotonicNs': time.monotonic_ns()-10_000_000,
                  'generationStartedMonotonicNs': time.monotonic_ns()-9_000_000,
                  'generationStarted': True, 'generationCompleted': True, 'generateMs': 3.0}
        report = {'attempts': [], 'activeAttempt': active}
        pilot.settle_interrupted(report, plan, 'process_wall_limit')
        self.assertTrue(report['attempts'][0]['generationCompleted'])
        self.assertEqual(report['attempts'][0]['generateMs'], 3.0)

    def test_environment_change_is_rejected_before_model_or_case_rechecks(self):
        config = {'device': 'cpu', 'threads': 1, 'concurrency': 1, 'truncation': False,
                  'doSample': False, 'attemptsPerCase': 5, 'processWallSeconds': 120, 'maxResidentMiB': 2048}
        plan = {'authorization': {'status': 'explicit_user_instruction'}, 'formalEvaluationAllowed': False,
                'config': config, 'configSha256': pilot.digest(config), 'instructions': {},
                'instructionSha256': pilot.digest({}), 'code': {}, 'environment': {'venvExecutableRelativePath': 'qa-original'}}
        with mock.patch.object(pilot, 'observe_environment', return_value={'venvExecutableRelativePath': 'qa-changed'}), mock.patch.object(pilot, 'observe_m02') as model:
            with self.assertRaisesRegex(ValueError, 'environment/interpreter'):
                pilot.verify_plan(plan)
            model.assert_not_called()


if __name__ == '__main__': unittest.main()
