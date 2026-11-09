"""Engineering counterexamples only: test providers are never model evidence."""
import copy
import contextlib
import gzip
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import experiment as common
import short_evaluation as evaluation
from short_contracts import ModelIdentity, ModelSession, digest, incomplete, result
from short_training import LocalSemanticProvider
from test_short_intent import canonical_context, Script, sequence, target_rows


def profiling_evidence_fixture(directory):
    """Small synthetic provenance for validator tests, never runtime performance evidence."""
    root = Path(directory); path = root / 'benchmark.record.json'
    workloads = [{'workloadId': name, 'input': {'fullContext': {'entities': ['a', 'b', 'off'],
                      'tasks': ['parent', 'child'], 'initial': {'records': ['original']}}}, 'completeInput': True}
                 for name in ('short', 'long')]
    for w in workloads: w['inputHash'] = digest(w['input'])
    cases = [{'caseId': w['workloadId'] + ':' + str(i), 'profilingMode': mode}
             for w in workloads for i, mode in enumerate(('default', 'off', 'default', 'off'))]
    plan = {'schema': 'jity-webgpu-profiling-comparison-plan-v1', 'runId': 'benchmark',
            'cases': cases, 'workloads': workloads, 'modelIdentity': 'engineering_fixture',
            'runtimeIdentity': 'engineering_fixture', 'config': {'attemptsPerCase': 1,
            'maxInputTokens': 8192, 'maxNewTokens': 128, 'callTimeoutMs': 120000}}
    plan_path = root / 'benchmark.plan.json';plan_path.write_text(json.dumps(plan))
    slots = common.planned_slots(plan, ('profiling_comparison',))
    attempts = [{**s, 'status': 'complete', 'completion': {'status': 'result', 'value': 'fixture'},
                 'profilingMode': cases[i]['profilingMode'], 'callAndCheckpointWallMs': 86000.0}
                for i, s in enumerate(slots)]
    journal = path.with_suffix('.journal.jsonl');journal.write_text('synthetic engineering fixture journal bytes\n')
    browser = path.with_suffix('.webgpu.jsonl');browser.write_text('synthetic engineering fixture browser bytes\n')
    record = {'schema': 'jity-webgpu-profiling-comparison-record-v1', 'runId': 'benchmark',
              'status': 'diagnostic_completed', 'planSha256': evaluation.sha256_file(plan_path),
              'activeAttempt': None, 'unexecutedAttempts': 0, 'attemptSlots': attempts,
              'attempts': attempts, 'supervisor': {'exitCode': 0, 'stopReason': None, 'error': None},
              'journalRecovery': {'partialTailBytes': 0, 'readOnlyReplay': True,
                                  'sha256': evaluation.sha256_file(journal)},
              'browserRawJournal': {'path': str(browser), 'sha256': evaluation.sha256_file(browser)}}
    path.write_text(json.dumps(record));return path


def row(split='test', group='scenario', target='act'):
    context = canonical_context()
    context['world']['worldId'] = group
    context['world']['initial']['worldId'] = group
    value = {'exampleId': group + ':D02.1', 'sourceGroup': group, 'split': split,
             'component': 'D02.1', 'kind': 'label', 'outputCodec': 'scalar',
             'labels': ['act', 'skip'], 'input': {'context': context}, 'target': target,
             'annotationStatus': 'assistant_draft', 'sourceStatus': 'unverified'}
    value['contentSha256'] = digest(value)
    return value


def manifest():
    return {'schema': 'jity-d-short-trained-provider-v1', 'runId': 'fixture_only',
            'datasetSha256': 'fixture', 'codeSha256': {'fixture': 'fixture'},
            'models': {}, 'tasks': {}, 'config': {'precision': 'float32'}}


def session(provider):
    return ModelSession(provider, binding={'fixture': 'engineering_only'},
                        identity=ModelIdentity('fixture', 'fixture', 'fixture', 'fixture', 'float32', 'fixture'))


def initialization_row(source):
    value = copy.deepcopy(source)
    value.update(exampleId=source['sourceGroup'] + ':D01.1', component='D01.1', kind='annotation_only',
                 input={'brief': '有一处库房和一名值守员。', 'draftId': 'authored-unused', 'revision': 0},
                 target='{"gold": "must never become live inventory"}')
    return value


def initial_provider(component, payload):
    """Engineering fixture; never imported by the experimental worker."""
    if component == 'D01.1':
        return result({'entities': [{'kind': 'locations', 'name': '模型库房'},
                                     {'kind': 'characters', 'name': '模型值守员'}], 'protagonistIndex': 1})
    world = payload['draft']
    location, person = next(iter(world['locations'])), next(iter(world['characters']))
    if component == 'D01.2': return result({location: None, person: {'containerId': location}})
    if component == 'D01.3': return result('衣袖干燥。' if payload['entityId'] == person else '窗边有灯。')
    if component == 'D01.4':
        return result({'kind': 'end'} if world['characters'][person]['tasks'] else
                      {'kind': 'task', 'goal': '保管钥匙', 'parentTaskId': None})
    if component == 'D01.5': return result('倾向先核对再交接。')
    if component == 'D01.6': return result(63)
    raise AssertionError('unregistered engineering fixture: ' + component)


class RegistrationTests(unittest.TestCase):
    def test_all_held_out_components_registered_and_train_excluded(self):
        rows = [row('train', 'train'), row('development', 'dev'), row('test', 'test')]
        for component in ('D01.6', 'D07.2', 'D08.1'):
            other = row('test', component)
            other.update(component=component, exampleId=component)
            rows.append(other)
        cases = evaluation.register_cases(rows)
        diagnostics = [c for c in cases if c['scope'] == 'diagnostic']
        self.assertEqual({c['component'] for c in diagnostics}, {'D01.6', 'D02.1', 'D07.2', 'D08.1'})
        self.assertNotIn('train', {c['sourceGroup'] for c in cases})
        self.assertEqual(cases[0]['scope'], 'live_upstream')
        self.assertEqual({c['representation'] for c in cases if c['scope'] == 'live_upstream'}, {'natural', 'references'})

    def test_live_registration_does_not_consult_target_or_scenario_gold(self):
        original = row()
        poisoned = copy.deepcopy(original)
        poisoned['target'] = {'goldSteps': 'Never execute this.'}
        poisoned['scenario'] = {'facts': ['Invented success.']}
        self.assertEqual(evaluation.register_cases([original]), evaluation.register_cases([poisoned]))

    def test_contract_scope_is_literal_and_all_scope_retains_primitive_rows(self):
        base = row()
        primitive = copy.deepcopy(base)
        primitive.update(exampleId='primitive', component='D02.3.subject')
        contracts = evaluation.register_cases([base, primitive], 'contracts')
        all_cases = evaluation.register_cases([base, primitive], 'all')
        self.assertEqual(len(all_cases), len(contracts) + 1)
        self.assertNotIn('primitive', {c['exampleId'] for c in contracts})
        primitive['target'] = 'different performance must not affect selection'
        self.assertEqual(evaluation.register_cases([base, primitive], 'all'), all_cases)

    def test_npc_variant_keeps_group_and_all_initial_context(self):
        first = row()
        npc = copy.deepcopy(first)
        npc['exampleId'] += ':npc'
        npc['input']['context']['advance'] = {'inputText': '等待。', 'intentStatus': 'consumed'}
        cases = [c for c in evaluation.register_cases([first, npc]) if c['scope'] == 'live_upstream']
        self.assertEqual(len(cases), 4)
        self.assertEqual({c['sourceGroup'] for c in cases}, {'scenario'})
        self.assertEqual(len({c['inputHash'] for c in cases}), 2)
        self.assertTrue(all(c['offlinePoint']['worldId'] == 'scenario' for c in cases))

    def test_preexisting_record_sequence_is_preserved_in_frozen_point(self):
        r = row()
        r['input']['context']['world']['items']['sheet']['appearanceChanges'] = [{'sourceSequence': 8}]
        cases = evaluation.register_cases([r])
        self.assertTrue(all(c['offlinePoint']['sequence'] == 9 for c in cases if c['scope'] == 'live_upstream'))

    def test_lifecycle_registration_uses_one_source_brief_and_initial_world_not_gold(self):
        source = row()
        brief = initialization_row(source)
        other = copy.deepcopy(source)
        other['exampleId'] += ':variant'
        other['input']['context']['advance']['inputText'] = '新的输入'
        rows = [source, brief, other]
        cases = evaluation.register_cases(rows)
        self.assertEqual(sum(c['scope'] == 'live_upstream' for c in cases), 4)
        self.assertEqual(sum(c['scope'] == 'live_initialization' for c in cases), 1)
        self.assertEqual(sum(c['scope'] == 'live_pure_time' for c in cases), 1)
        first_diagnostic = next(i for i, c in enumerate(cases) if c['scope'] == 'diagnostic')
        self.assertEqual(first_diagnostic, 6)
        for value in rows:
            value['target'] = 'poisoned target'
            value['scenario'] = {'steps': ['Invent a success.']}
        self.assertEqual(cases, evaluation.register_cases(rows))

    def test_provided_attempt_controls_are_registered_separately_but_not_fed_to_model(self):
        r = row()
        r['abstentionControl'] = 'act'
        r['input']['context']['advance']['inputText'] = '请完整执行以下尝试：安禾尝试用软刷清理图纸。'
        case = next(c for c in evaluation.register_cases([r]) if c['scope'] == 'live_upstream')
        self.assertEqual(case['inputKind'], 'provided_complete_attempt_control')
        calls = []
        def provider(component, payload):
            calls.append(copy.deepcopy(payload))
            return incomplete('stop_engineering_fixture')
        evaluation.live_case(session(provider), case, r, evaluation.CONFIG, lambda *_: None)
        self.assertTrue(calls)
        self.assertNotIn('inputKind', calls[0])
        self.assertNotIn('abstentionControl', calls[0])
        self.assertEqual(calls[0]['context'], r['input']['context'])


class InferenceTests(unittest.TestCase):
    def test_webgpu_direct_text_training_requires_actual_identity_steps_and_qualification(self):
        r = row();r.update(component='U4.2', kind='text', outputCodec='text', target='短目标')
        model = manifest();model['models'] = {'generator': {'trainedComponents': ['U4.2'], 'trainingSteps': 144}}
        model['textBackend'] = {'identity': {'trainedComponents': ['U4.2'],
            'trainingSteps': 144, 'qualification': 'task_finetuned'}}
        positive = evaluation.diagnostic_case(session(lambda *_: result('短目标')), r, model)
        self.assertTrue(positive['trainedDirectTask'])
        for mutation in [{'trainingSteps': 0}, {'trainingSteps': True}, {'trainingSteps': 1.0},
                         {'trainingSteps': '144'}, {'qualification': 'base_zero_shot'},
                         {'qualification': None}, {'trainedComponents': []}]:
            with self.subTest(mutation=mutation):
                invalid = copy.deepcopy(model);invalid['textBackend']['identity'].update(mutation)
                out = evaluation.diagnostic_case(session(lambda *_: result('短目标')), r, invalid)
                self.assertFalse(out['trainedDirectTask'])
                self.assertTrue(out['draftExactMatch'])  # Answer matching alone grants no training qualification.
        model['textBackend'].pop('identity')
        self.assertFalse(evaluation.diagnostic_case(session(lambda *_: result('短目标')), r, model)['trainedDirectTask'])

    def test_diagnostic_passes_only_full_input_then_scores(self):
        r = row(target='skip')
        calls = []
        def provider(component, payload):
            calls.append((component, copy.deepcopy(payload)))
            return result('act')
        out = evaluation.diagnostic_case(session(provider), r, manifest())
        self.assertEqual(calls, [('D02.1', r['input'])])
        self.assertFalse(out['draftExactMatch'])
        self.assertEqual(out['completion']['value'], 'act')
        self.assertEqual(out['semanticReview'], 'pending')

    def test_short_generation_end_is_scored_after_provider(self):
        r = row()
        r.update(component='D02.2', kind='text', outputCodec='fragment_or_end', target='【结束】')
        out = evaluation.diagnostic_case(session(lambda *_: result({'kind': 'end'})), r, manifest())
        self.assertTrue(out['draftExactMatch'])

    def test_untrained_real_provider_is_incomplete_and_not_scored_as_empty(self):
        provider = LocalSemanticProvider(manifest())
        for component in ('D01.6', 'D07.2', 'D08.1'):
            r = row()
            r['component'] = component
            out = evaluation.diagnostic_case(session(provider), r, manifest())
            self.assertEqual(out['completion']['status'], 'incomplete')
            self.assertFalse(out['trainedDirectTask'])
            self.assertFalse(out['draftExactMatch'])

    def test_semantic_abstention_scoring_requires_precise_component_and_attempt_refs(self):
        ordinary = row(target='incomplete')
        good = evaluation.diagnostic_case(session(lambda *_: incomplete('semantic_incomplete:D02.1')), ordinary, manifest())
        self.assertTrue(good['expectedSemanticIncomplete'])
        self.assertTrue(good['semanticAbstentionMatches'])
        self.assertFalse(good['draftExactMatch'])
        self.assertFalse(good['draftComparisonEligible'])
        for output in (incomplete('timeout'), incomplete('untrained_component:D02.1'), result('incomplete')):
            out = evaluation.diagnostic_case(session(lambda *_: output), ordinary, manifest())
            self.assertFalse(out['semanticAbstentionMatches'])
        joint = copy.deepcopy(ordinary)
        joint.update(component='D05.2', kind='annotation_only',
                     input={'attempts': [{'attemptId': 'a:fragment-1'}, {'attemptId': 'b:fragment-1'}]},
                     target=json.dumps({'judgments': [{'attemptId': 'a:fragment-1', 'label': 'achieved'},
                                                      {'attemptId': 'b:fragment-1', 'label': 'incomplete'}]}))
        for reason, matches in [('semantic_incomplete:D05.2:b:fragment-1', True),
                                ('semantic_incomplete:D05.2:a:fragment-1', False),
                                ('semantic_incomplete:D05.2', False)]:
            out = evaluation.diagnostic_case(session(lambda *_: incomplete(reason)), joint, manifest())
            self.assertEqual(out['semanticAbstentionMatches'], matches)
        primitive = copy.deepcopy(joint)
        primitive.update(component='D05.2.label', kind='label', target='incomplete')
        out = evaluation.diagnostic_case(session(lambda *_: result('incomplete')), primitive, manifest())
        self.assertFalse(out['expectedSemanticIncomplete'])
        self.assertTrue(out['draftExactMatch'])

    def test_first_failure_keeps_downstream_not_started_without_gold(self):
        r = row()
        r['target'] = 'GOLD MUST NOT DRIVE LIVE'
        case = evaluation.register_cases([r])[0]
        with patch('short_settlement.settle_joint', side_effect=AssertionError('downstream must not run')):
            out = evaluation.live_case(Script([('D02.1', incomplete('model_timeout'))]), case, r,
                                       evaluation.CONFIG, lambda *_: None)
        self.assertEqual(out['completion']['status'], 'incomplete')
        self.assertIn('model_timeout', out['completion']['reason'])
        self.assertEqual([s['status'] for s in out['stages']], ['incomplete', 'not_started', 'not_started'])

    def test_explicit_skip_is_completed_empty_and_not_failed_or_settled(self):
        r = row()
        out = evaluation.live_case(Script([('D02.1', result('skip'))]), evaluation.register_cases([r])[0],
                                   r, evaluation.CONFIG, lambda *_: None)
        self.assertEqual(out['completion']['status'], 'empty')
        self.assertEqual(out['stages'][1]['reason'], 'upstream_empty')

    def test_actual_frozen_action_reaches_joint_input_and_failure_blocks_updates(self):
        r = row()
        calls = sequence(['安禾尝试用软刷清理图纸。']) + target_rows([])
        fixture = Script(calls)
        captured = []
        def fail_joint(s, context, **kwargs):
            captured.append(copy.deepcopy(context))
            return incomplete('no_trained_joint_head')
        with patch('short_settlement.settle_joint', side_effect=fail_joint):
            out = evaluation.live_case(fixture, evaluation.register_cases([r])[0], r, evaluation.CONFIG,
                                       lambda *_: None, preview_factory=lambda *_: self.fail('preview cannot start'))
        self.assertEqual(captured[0]['group']['members'][0]['actionText'], '安禾尝试用软刷清理图纸。')
        self.assertEqual(captured[0]['world'], r['input']['context']['world'])
        self.assertEqual([s['status'] for s in out['stages']], ['result', 'incomplete', 'not_started'])

    def test_live_worker_path_uses_real_pinned_A_preview_for_all_six_stages(self):
        # All semantic answers are explicit fixtures; only the protocol and
        # original A preview implementation are under test here.
        try:
            import pydantic
            if not hasattr(pydantic.BaseModel, 'model_validate'):
                self.skipTest('Pydantic v2 required for original A kernel')
        except ImportError:
            self.skipTest('Pydantic v2 unavailable')
        from test_short_settlement import FixtureSession
        r = row()
        action = Script(sequence(['安禾尝试用软刷清理图纸。']) + target_rows([]))
        update = FixtureSession({
            'D05.1': result({'checkedActionIds': ['a'], 'relations': []}),
            'D05.3': lambda p: result({'kind': 'fact', 'text': '安禾没有拿起图纸。'}) if not p['candidates'] else result({'kind': 'end'}),
            'D05.4': result({'verdict': 'pass', 'checkedActionIds': ['a'], 'checkedFactIds': ['fact:1'], 'checkedRollIds': []}),
            'D05.5': result({'facts': [{'factId': 'fact:1', 'memberIds': ['a']}], 'checkedMemberIds': ['a']})})
        class CombinedFixture:
            def call(self, component, payload):
                return (action if action.rows else update).call(component, payload)
        events = []
        out = evaluation.live_case(CombinedFixture(), evaluation.register_cases([r])[0], r,
                                   evaluation.CONFIG, lambda name, payload: events.append((name, payload)))
        self.assertEqual(out['completion']['status'], 'result', out['completion']['reason'])
        previews = [value for name, value in events if name == 'offline_A_preview']
        self.assertEqual(len(previews), 6)
        self.assertTrue(previews[-1]['completeUnitValidated'])
        self.assertFalse(out['committed'])
        self.assertFalse(out['CConnected'])

    def test_real_offline_rolls_are_repeatable_and_acted_eligibility_is_explicit(self):
        context = row()['input']['context']
        context['confirmedPrefix'] = [{'memberId': 'c', 'actionText': '尝试等候。'}]
        class Source: actor_id = 'a'
        logs = []
        roll, receipts = evaluation.offline_roller(context, 'group', 1729, lambda *args: logs.append(args))
        first = roll(Source(), ('b', 'c'))
        again, _ = evaluation.offline_roller(context, 'group', 1729, lambda *_: None)
        self.assertEqual(first, again(Source(), ('b', 'c')))
        self.assertFalse(first[1]['eligible'])
        self.assertFalse(first[1]['admitted'])
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all(event[1]['productionReceipt'] is False for event in logs))


class ResourceProfileTests(unittest.TestCase):
    def test_default_values_remain_exact_and_complete_context_only_changes_time(self):
        for scope, wall, diagnostic in [('contracts', 1800, 30), ('all', 1800, 30),
                                         ('webgpu', 2400, 60), ('webgpu_text', 1200, 60)]:
            old = {**copy.deepcopy(evaluation.CONFIG), 'diagnosticScope': scope}
            if scope in ('webgpu', 'webgpu_text'): old['browserAttachSeconds'] = 300
            old['processWallSeconds'] = wall;old['caseDeadlineSeconds']['diagnostic'] = diagnostic
            self.assertEqual(evaluation.configuration(scope), old)
        default = evaluation.configuration('webgpu')
        expanded = evaluation.configuration('webgpu', 'webgpu_complete_context_v1')
        changed = {k for k in expanded if expanded[k] != default[k]}
        self.assertEqual(changed, {'processWallSeconds', 'caseDeadlineSeconds'})
        self.assertEqual(expanded['processWallSeconds'], 7200)
        self.assertEqual(expanded['caseDeadlineSeconds'], {'live_upstream': 600,
            'live_initialization': 600, 'live_pure_time': 600, 'diagnostic': 180})
        self.assertEqual(expanded['callTimeoutMs'], 120000)
        self.assertEqual(expanded['retries'], 0)
        self.assertEqual(expanded['representationSubarms'], ['natural', 'references'])
        self.assertEqual(evaluation.THRESHOLDS['fullRequestWallMs'], 500)

    def test_expanded_profile_rejects_every_other_scope_and_unknown_name(self):
        for scope in ('contracts', 'all', 'webgpu_text'):
            with self.assertRaisesRegex(ValueError, 'requires full webgpu scope'):
                evaluation.configuration(scope, 'webgpu_complete_context_v1')
        with self.assertRaisesRegex(ValueError, 'unknown.*resource profile'):
            evaluation.configuration('webgpu', 'unregistered')

    def test_evidence_rejects_unfinished_missing_slots_and_changed_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            path = profiling_evidence_fixture(directory)
            original = json.loads(path.read_text())
            mutations = [lambda r: r.update(status='running'),
                         lambda r: r.update(activeAttempt={'status': 'started'}),
                         lambda r: r.update(unexecutedAttempts=1),
                         lambda r: r['supervisor'].update(exitCode=None),
                         lambda r: r['attempts'].pop(),
                         lambda r: r['journalRecovery'].update(partialTailBytes=7)]
            for mutate in mutations:
                record = copy.deepcopy(original);mutate(record);path.write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError, 'resource benchmark'):
                    evaluation.resource_benchmark(path)
            path.write_text(json.dumps(original))
            evidence = evaluation.resource_benchmark(path)
            self.assertEqual(evidence['registeredCases'], 8)
            self.assertFalse(evidence['profilingPolicyChanged'])
            path.with_suffix('.webgpu.jsonl').write_text('changed raw')
            with self.assertRaisesRegex(ValueError, 'raw journal identity mismatch'):
                evaluation.resource_benchmark(path)

    def test_full_freeze_preserves_all_rows_inputs_provider_tokens_and_500ms_gate(self):
        import short_mixed_provider
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); evidence = profiling_evidence_fixture(root)
            values = [row('development', 'dev'), row('test', 'test'), row('train', 'train')]
            values += [initialization_row(values[0])]
            for value in values:
                value['contentSha256'] = digest({k: v for k, v in value.items() if k != 'contentSha256'})
            data = root / 'supervision.jsonl'
            data.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in values))
            model = manifest();model.update(datasetSha256=evaluation.sha256_file(data),
                textBackend={'maxInputTokens': 8192, 'maxNewTokens': 128, 'timeoutMs': 120000,
                    'identity': {'modelIdentity': 'engineering_fixture',
                        'runtime': {'identity': 'engineering_fixture'}, 'profilingMode': 'default'}})
            provider = root / 'provider.json';provider.write_text(json.dumps(model))
            (root / 'manifest.json').write_text('{}');(root / 'sources.jsonl').write_text('{}\n')
            authority = {'mode': 'engineering_fixture_only', 'sourceFiles': {}}
            with contextlib.ExitStack() as stack:
                for obj, name, value in [(evaluation, 'ART', root), (evaluation.training, 'ART', root),
                                          (evaluation.training, 'DATA', root)]:
                    stack.enter_context(patch.object(obj, name, value))
                stack.enter_context(patch.object(evaluation, '_code_files', return_value=['short_evaluation.py']))
                stack.enter_context(patch.object(evaluation, '_preview_authority', return_value=authority))
                stack.enter_context(patch.object(evaluation, 'LocalSemanticProvider'))
                stack.enter_context(patch.object(short_mixed_provider, 'verify_backend_artifacts'))
                stack.enter_context(patch.object(evaluation.importlib.metadata, 'version', return_value='fixture'))
                with self.assertRaisesRegex(ValueError, 'finished benchmark evidence'):
                    evaluation.freeze('no-evidence', provider, dataset=data, resource_profile='webgpu_complete_context_v1')
                path = evaluation.freeze('expanded', provider, dataset=data,
                    resource_profile='webgpu_complete_context_v1', benchmark_evidence=evidence)
                plan = json.loads(path.read_text()); actual_rows, actual_model = evaluation.verify(plan)
                self.assertEqual(actual_rows, values);self.assertEqual(actual_model, model)
                self.assertEqual(plan['cases'], evaluation.register_cases(values, 'webgpu'))
                self.assertEqual(plan['thresholds']['fullRequestWallMs'], 500)
                self.assertEqual(plan['retryPolicy']['maxRetries'], 0)
                self.assertEqual(plan['config']['callTimeoutMs'], 120000)
                self.assertEqual(plan['resourceProfile'], 'webgpu_complete_context_v1')
                self.assertEqual(set(plan['resourceBenchmarkSnapshots']), {'record', 'plan'})
                for change in [lambda p: p['config'].update(processWallSeconds=7201),
                               lambda p: p['config'].update(maxNewTasks=1),
                               lambda p: p['thresholds'].update(fullRequestWallMs=600000),
                               lambda p: p.update(resourceProfile='default')]:
                    drift = copy.deepcopy(plan);change(drift)
                    with self.assertRaisesRegex(ValueError, 'policy drift'):
                        evaluation.verify(drift)
                bad = copy.deepcopy(plan);bad['resourceBenchmark']['observations'][0]['callAndCheckpointWallMs'] = 1
                with self.assertRaisesRegex(ValueError, 'benchmark registration drift'):
                    evaluation.verify(bad)

    def test_resource_evidence_cannot_move_across_assets_runtime_tokens_or_profiling(self):
        backend = {'maxInputTokens': 8192, 'maxNewTokens': 128, 'timeoutMs': 120000,
                   'identity': {'modelIdentity': 'model', 'runtime': {'identity': 'runtime'}, 'profilingMode': 'default'}}
        evidence = {'modelIdentity': 'model', 'runtimeIdentity': 'runtime',
                    'inputLimits': {'maxInputTokens': 8192, 'maxNewTokens': 128, 'callTimeoutMs': 120000}}
        evaluation._verify_resource_backend(evidence, {'textBackend': backend})
        for mutate in [lambda b: b['identity'].update(modelIdentity='other'),
                       lambda b: b['identity']['runtime'].update(identity='other'),
                       lambda b: b['identity'].update(profilingMode='off'),
                       lambda b: b.update(maxInputTokens=4096), lambda b: b.update(maxNewTokens=64),
                       lambda b: b.update(timeoutMs=60000)]:
            altered = copy.deepcopy(backend);mutate(altered)
            with self.assertRaisesRegex(ValueError, 'resource benchmark.*mismatch'):
                evaluation._verify_resource_backend(evidence, {'textBackend': altered})

    def test_cli_explicit_profile_and_evidence_are_forwarded(self):
        with patch.object(evaluation, 'freeze', return_value=Path('/fixture/plan.json')) as freeze, contextlib.redirect_stdout(io.StringIO()):
            code = common.main(['short-eval-prepare', 'fixture', '--provider', '/fixture/provider.json',
                '--dataset', '/fixture/data.jsonl.gz', '--scope', 'webgpu',
                '--resource-profile', 'webgpu_complete_context_v1',
                '--benchmark-evidence', '/fixture/benchmark.record.json'])
        self.assertEqual(code, 0)
        self.assertEqual(freeze.call_args.kwargs['resource_profile'], 'webgpu_complete_context_v1')
        self.assertEqual(freeze.call_args.kwargs['benchmark_evidence'], Path('/fixture/benchmark.record.json'))


class EvidenceTests(unittest.TestCase):
    def test_allocated_ids_bind_both_hashes_within_actual_A_id_limit(self):
        try:
            from pydantic import TypeAdapter, ValidationError
        except ImportError:
            self.skipTest('Pydantic v2 required for actual A Id parser')
        from short_preview import _load_kernel
        Id = _load_kernel().contracts.Id
        value = evaluation.candidate_id('a' * 64, 'appearance', 'b' * 64)
        self.assertEqual(TypeAdapter(Id).validate_python(value), value)
        self.assertLessEqual(len(value), 128)
        self.assertNotEqual(value, evaluation.candidate_id('c' * 64, 'appearance', 'b' * 64))
        self.assertNotEqual(value, evaluation.candidate_id('a' * 64, 'appearance', 'c' * 64))
        with self.assertRaises(ValidationError):
            TypeAdapter(Id).validate_python('eval-appearance:' + 'a' * 64 + ':' + 'b' * 64)

    def test_frozen_data_provider_and_cases_reject_drift_without_model_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / 'supervision.jsonl'
            data.write_text('\n'.join(json.dumps(row(split, split), ensure_ascii=False) for split in ('train', 'development', 'test')))
            provider = root / 'provider.json'
            provider_value = manifest()
            provider_value['datasetSha256'] = evaluation.sha256_file(data)
            provider.write_text(json.dumps(provider_value))
            (root / 'manifest.json').write_text('{}')
            (root / 'sources.jsonl').write_text('{}\n')
            with patch.object(evaluation, 'ART', root), \
                 patch.object(evaluation.training, 'ART', root), \
                 patch.object(evaluation.training, 'DATA', root), \
                 patch.object(evaluation, '_code_files', return_value=['short_evaluation.py']), \
                 patch.object(evaluation.importlib.metadata, 'version', return_value='fixture_version'):
                plan_path = evaluation.freeze('fixture-freeze', provider, dataset=data)
                plan = json.loads(plan_path.read_text())
                rows, _ = evaluation.verify(plan)
                self.assertEqual(len(rows), 3)
                self.assertIn('pydantic', plan['environment']['versions'])
                snapshot = Path(plan['codeSnapshot']['directory']) / 'short_evaluation.py'
                self.assertEqual(snapshot.read_bytes(), (evaluation.BASE / 'short_evaluation.py').read_bytes())
                self.assertEqual(plan['cases'][0]['scope'], 'live_upstream')
                _, record_path = evaluation.paths('fixture-freeze')
                compressed = record_path.with_suffix(record_path.suffix + '.gz')
                compressed.write_bytes(gzip.compress(json.dumps({'planSha256': evaluation.sha256_file(plan_path),
                    'status': 'diagnostic_completed', 'attempts': []}).encode()))
                with patch.object(evaluation, 'BASE', root / 'different-current-checkout'):
                    historical = evaluation.report(plan_path)
                self.assertEqual(historical['status'], 'diagnostic_completed')
                self.assertTrue(historical['frozenEvidenceVerified'])
                self.assertEqual(historical['rerunStatus'], 'new_freeze_required')
                with self.assertRaises(FileExistsError):
                    evaluation.freeze('fixture-freeze', provider, dataset=data)
                provider.write_text(provider.read_text() + '\n')
                with self.assertRaisesRegex(ValueError, 'provider manifest drift'):
                    evaluation.verify(plan)

    def test_worker_uses_shared_journal_and_reconciles_every_first_output(self):
        r = row()
        case = next(c for c in evaluation.register_cases([r]) if c['scope'] == 'diagnostic')
        plan = {'runId': 'fixture', 'config': evaluation.CONFIG, 'cases': [case],
                'provider': {'identity': 'fixture'}, 'codeSha256': {'fixture': 'fixture'}}
        class FixtureProvider:
            def __init__(self, m, **options): self.checkpoint = None; self.observations = []
            def __call__(self, component, payload):
                self.checkpoint('semantic_call_started', {'component': component, 'input': payload})
                self.checkpoint('semantic_call_finished', {'component': component, 'rawText': 'skip', 'elapsedMs': 1.})
                return result('skip')
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory) / 'plan.json'
            record_path = Path(directory) / 'record.json'
            plan_path.write_text(json.dumps(plan))
            with patch.object(evaluation, 'verify', return_value=([r], manifest())), \
                 patch.object(evaluation, 'paths', return_value=(plan_path, record_path)), \
                 patch.object(evaluation, 'LocalSemanticProvider', FixtureProvider):
                self.assertEqual(evaluation.worker(plan_path), 0)
            record = json.loads(record_path.read_text())
            common.reconcile_journal(record, record_path.with_suffix('.journal.jsonl'), 'test_recovery')
            self.assertEqual(len(record['attempts']), 1)
            attempt = record['attempts'][0]
            self.assertEqual(attempt['outcome']['completion']['value'], 'skip')
            self.assertFalse(attempt['outcome']['draftExactMatch'])
            self.assertEqual(attempt['highLevelCalls'], 1)
            self.assertEqual(attempt['timing']['primitiveCalls'], 1)
            self.assertIsNone(attempt['timing']['fullRequestMs'])
            self.assertFalse(record['semanticQualityApproved'])
            self.assertEqual(record['unexecutedAttempts'], 0)

    def test_changed_resource_policy_rejected_before_neural_import(self):
        with self.assertRaisesRegex(ValueError, 'policy drift'):
            evaluation.verify({'schema': 'jity-d-short-evaluation-plan-v1', 'config': {**evaluation.CONFIG, 'retries': 1}, 'arms': list(evaluation.ARMS)})

    def test_summary_retains_missing_heads_and_does_not_claim_semantic_pass(self):
        r = row()
        out = evaluation.diagnostic_case(session(lambda *_: incomplete('untrained_component')), r, manifest())
        summary = evaluation.summarize([{'outcome': out}])
        self.assertEqual(summary['components']['D02.1']['incomplete'], 1)
        self.assertEqual(summary['components']['D02.1']['trainedDirect'], 0)
        self.assertFalse(summary['components']['D02.1']['semanticPassed'])
        self.assertEqual(summary['fullRequest500ms'], 'unmeasured')


class LifecycleWorkloadTests(unittest.TestCase):
    def test_initial_generation_uses_actual_outputs_then_pinned_A_candidate_validator(self):
        source = row()
        brief = initialization_row(source)
        case = next(c for c in evaluation.register_cases([source, brief]) if c['scope'] == 'live_initialization')
        calls, events = [], []
        def provider(component, payload):
            calls.append((component, copy.deepcopy(payload)))
            return initial_provider(component, payload)
        out = evaluation.initialization_case(session(provider), case, brief, source, evaluation.CONFIG,
                                             lambda name, payload: events.append((name, payload)))
        self.assertEqual(out['completion']['status'], 'result', out['completion']['reason'])
        world = out['completion']['value']
        self.assertEqual(next(iter(world['locations'].values()))['name'], '模型库房')
        self.assertEqual(world['initialTime'], source['input']['context']['world']['initial']['initialTime'])
        self.assertNotIn('draft', calls[0][1])
        self.assertEqual(calls[0][1]['brief'], brief['input']['brief'])
        self.assertNotEqual(calls[0][1]['draftId'], brief['input']['draftId'])
        self.assertFalse(out['worldCreated'])
        self.assertFalse(out['formalAuthority'])
        self.assertTrue(any(name == 'offline_A_initial_validation' and p['status'] == 'result' for name, p in events))
        from short_preview import _load_kernel
        _load_kernel().contracts.WorldInitialState.model_validate(world)
        for person in world['characters'].values():
            self.assertTrue(all(len(task) <= 128 for task in person['tasks']))

    def test_initial_missing_model_stage_or_A_invalid_time_cannot_seal(self):
        source = row()
        brief = initialization_row(source)
        case = next(c for c in evaluation.register_cases([source, brief]) if c['scope'] == 'live_initialization')
        out = evaluation.initialization_case(session(lambda *_: incomplete('untrained_component')),
                                             case, brief, source, evaluation.CONFIG, lambda *_: None)
        self.assertEqual([x['status'] for x in out['stages']], ['incomplete', 'not_started', 'not_started'])
        source['input']['context']['world']['initial']['initialTime']['calendar'] = 'unregistered'
        case = next(c for c in evaluation.register_cases([source, brief]) if c['scope'] == 'live_initialization')
        out = evaluation.initialization_case(session(initial_provider), case, brief, source,
                                             evaluation.CONFIG, lambda *_: None)
        self.assertEqual([x['status'] for x in out['stages']], ['result', 'incomplete', 'incomplete'])
        self.assertIn('initial_validation', out['completion']['reason'])

    def test_model_time_drives_real_A_six_phase_preview_without_D05_facts(self):
        from test_short_settlement import FixtureSession
        source = row()
        case = next(c for c in evaluation.register_cases([source]) if c['scope'] == 'live_pure_time')
        fixture = FixtureSession({'D08.1': result({'boundary': 'elapsed', 'duration': {'amount': 3, 'unit': 'minute'}})})
        events = []
        out = evaluation.pure_time_case(fixture, case, source, evaluation.CONFIG,
                                       lambda name, payload: events.append((name, payload)))
        self.assertEqual(out['completion']['status'], 'result', out['completion']['reason'])
        previews = [p for name, p in events if name == 'offline_A_preview']
        self.assertEqual(len(previews), 6)
        self.assertTrue(previews[-1]['completeUnitValidated'])
        self.assertFalse(out['D05Executed'])
        self.assertFalse(out['committed'])
        self.assertEqual(fixture.calls[0][0], 'D08.1')
        self.assertEqual(fixture.calls[0][1]['frozenActions'], [])
        self.assertEqual(fixture.calls[0][1]['world'], source['input']['context']['world'])
        u3 = next(p for name, p in fixture.calls if name == 'U3.1')
        self.assertEqual(set(u3['characterIds']), set(source['input']['context']['world']['characters']))
        expected_tasks = {t for person in source['input']['context']['world']['characters'].values() for t in person['tasks']}
        self.assertEqual(set(u3['taskIds']), expected_tasks)
        from datetime import datetime, timedelta
        before = datetime.fromisoformat(source['input']['context']['world']['time']['dateTime'])
        after = datetime.fromisoformat(u3['world']['time']['dateTime'])
        self.assertEqual(after - before, timedelta(minutes=3))
        self.assertTrue(all(p['settlement'] is None and p['facts'] == [] for name, p in fixture.calls if name != 'D08.1'))
        mapping = next(p for name, p in fixture.calls if name == 'D06.P.mapping')
        self.assertEqual(mapping['timeFact']['timeAdvance'], out['timeAdvance'])
        self.assertNotIn('text', mapping['timeFact'])

    def test_pure_time_failure_never_fills_a_default_time_or_unchanged_update(self):
        source = row()
        case = next(c for c in evaluation.register_cases([source]) if c['scope'] == 'live_pure_time')
        with patch('short_settlement.run_updates', side_effect=AssertionError('must not start')):
            out = evaluation.pure_time_case(session(lambda *_: incomplete('time_head_missing')),
                                           case, source, evaluation.CONFIG, lambda *_: None)
        self.assertEqual([x['status'] for x in out['stages']], ['incomplete', 'not_started'])
        self.assertNotIn('timeAdvance', out)

    def test_pure_time_task_achievement_scans_offscene_personality_and_sanity(self):
        from test_short_preview import complete_context
        from test_short_settlement import FixtureSession
        source = row()
        source['input']['context']['world'] = complete_context()['world']
        case = next(c for c in evaluation.register_cases([source]) if c['scope'] == 'live_pure_time')
        def keep_appearances(payload):
            return result({'checkedEntityIds': payload['entityIds'],
                           'checkedRecordIds': [r for key in payload['entityIds'] for r in payload['activeRecords'][key]],
                           'operations': [{'entityId': key, 'op': 'keep', 'recordIds': list(payload['activeRecords'][key])}
                                          for key in payload['entityIds']]})
        fixture = FixtureSession({'D08.1': result({'boundary': 'elapsed', 'duration': {'amount': 1, 'unit': 'hour'}}),
                                  'U2.1': keep_appearances}, effects=True)
        out = evaluation.pure_time_case(fixture, case, source, evaluation.CONFIG, lambda *_: None)
        self.assertEqual(out['completion']['status'], 'result', out['completion']['reason'])
        u5 = next(p for name, p in fixture.calls if name == 'U5.1')
        self.assertEqual(set(u5['entityIds']), {'a', 'b', 'off'})
        u6 = [p for name, p in fixture.calls if name == 'U6.1']
        self.assertEqual([p['entityId'] for p in u6], ['off'])
        self.assertEqual(out['completion']['value']['candidates']['sanities'], {'off': 48})


class CaseDeadlineTests(unittest.TestCase):
    def guard(self):
        now, events = [0], []
        def sink(name, payload):
            events.append((name, copy.deepcopy(payload)))
            return {'checkpointRef': {'sequence': len(events), 'sha256': digest(payload)}, 'name': name}
        guard = evaluation.CaseCheckpoints(sink, evaluation.CONFIG, 'diagnostic', clock=lambda: now[0])
        return guard, now, events

    def test_deadline_before_primitive_preserves_input_and_does_not_count_model_call(self):
        guard, now, events = self.guard()
        now[0] = 30 * 10**9
        payload = {'component': 'D01.1.next', 'input': {'brief': 'full source input'}}
        with self.assertRaisesRegex(evaluation.CaseBudgetExceeded, 'before_primitive'):
            guard('semantic_call_started', payload)
        self.assertEqual(guard.counters['primitiveCalls'], 0)
        self.assertEqual(guard.counters['primitiveBlockedBeforeCall'], 1)
        self.assertFalse(events[0][1]['modelCalled'])
        self.assertEqual(events[0][1]['attemptedCall'], payload)

    def test_late_output_is_saved_before_rejection_and_is_not_empty(self):
        guard, now, events = self.guard()
        guard('semantic_call_started', {'component': 'D04.1.text', 'input': {'full': True}})
        now[0] = 31 * 10**9
        raw = {'component': 'D04.1.text', 'value': '原始短句。', 'rawTokenIds': [3, 4, 5], 'elapsedMs': 31000}
        with self.assertRaisesRegex(evaluation.CaseBudgetExceeded, 'late_primitive'):
            guard('semantic_call_finished', raw)
        self.assertEqual(events[1], ('semantic_call_finished', raw))
        self.assertEqual(events[2][0], 'case_late_output_rejected')
        self.assertEqual(events[2][1]['rawCheckpoint']['checkpointRef']['sequence'], 2)
        out = guard.finish({'completion': {'status': 'result', 'value': 'must not accept'}})
        self.assertEqual(out['completion']['status'], 'incomplete')
        self.assertNotIn('handback', out['completion']['reason'])

    def test_primitive_count_limit_logs_blocked_input_without_an_extra_call(self):
        guard, _, events = self.guard()
        guard.config = {**guard.config, 'maxPrimitiveCallsPerCase': 1}
        guard('semantic_call_started', {'component': 'first'})
        with self.assertRaisesRegex(evaluation.CaseBudgetExceeded, 'primitive_call_budget'):
            guard('semantic_call_started', {'component': 'second'})
        self.assertEqual(guard.counters['primitiveCalls'], 1)
        self.assertEqual(events[-1][1]['attemptedCall']['component'], 'second')

    def test_expired_case_does_not_block_later_registered_case_in_common_worker(self):
        first, second = row(group='first'), row(group='second')
        cases = [c for c in evaluation.register_cases([first, second]) if c['scope'] == 'diagnostic']
        plan = {'runId': 'fixture-deadline', 'config': evaluation.CONFIG, 'cases': cases,
                'provider': {'identity': 'fixture'}, 'codeSha256': {'fixture': 'fixture'}}
        now = [0]
        class FixtureProvider:
            def __init__(self, m, **options): self.checkpoint = None; self.observations = []
            def __call__(self, component, payload):
                self.checkpoint('semantic_call_started', {'component': component, 'input': payload})
                if payload['context']['world']['worldId'] == 'first': now[0] += 31 * 10**9
                self.checkpoint('semantic_call_finished', {'component': component, 'value': 'skip', 'elapsedMs': 1.})
                return result('skip')
        with tempfile.TemporaryDirectory() as directory:
            plan_path, record_path = Path(directory) / 'plan.json', Path(directory) / 'record.json'
            plan_path.write_text(json.dumps(plan))
            with patch.object(evaluation, 'verify', return_value=([first, second], manifest())), \
                 patch.object(evaluation, 'paths', return_value=(plan_path, record_path)), \
                 patch.object(evaluation, 'LocalSemanticProvider', FixtureProvider), \
                 patch.object(evaluation.time, 'monotonic_ns', side_effect=lambda: now[0]):
                self.assertEqual(evaluation.worker(plan_path), 0)
            record = json.loads(record_path.read_text())
            self.assertEqual([a['outcome']['completion']['status'] for a in record['attempts']], ['incomplete', 'result'])
            events = list(common.iter_checkpoint_events(record, record_path.with_suffix('.journal.jsonl')))
            self.assertEqual(sum(event['name'] == 'semantic_call_finished' for event in events), 2)
            self.assertEqual(record['unexecutedAttempts'], 0)


class WebGPUWorkerIsolationTests(unittest.TestCase):
    """No browser/model calls: exercise the actual worker's lifecycle routing."""
    def run_fixture(self, ready=True):
        from types import SimpleNamespace
        from contextlib import ExitStack
        first, second = row('test', 'webgpu-first'), row('test', 'webgpu-second')
        cases = [c for c in evaluation.register_cases([first, second]) if c['scope'] == 'diagnostic']
        plan = {'runId': 'webgpu-engineering-fixture', 'backendMode': 'qwen_webgpu',
                'config': evaluation.configuration('webgpu'), 'cases': cases,
                'provider': {'identity': 'fixture'}, 'codeSha256': {'actual-runtime': 'fixture-code'}}
        observations = []
        class Provider:
            def __init__(self):
                self.text_backend = SimpleNamespace(binding=None, policy={})
                self.observations = []
                self.previous_cancelled = None
            def model_identity(self):
                return ModelIdentity('fixture', 'fixture', 'fixture', 'fixture', 'fixture', 'old_training_runtime')
            def __call__(self, component, payload):
                observations.append({'binding': copy.deepcopy(self.text_backend.binding),
                    'binding_now': self.text_backend.policy['binding_now'](),
                    'cancelled_now': self.text_backend.policy['cancelled'](),
                    'previous_cancelled': self.previous_cancelled() if self.previous_cancelled else None})
                self.previous_cancelled = self.text_backend.policy['cancelled']
                self.checkpoint('semantic_call_started', {'component': component, 'input': payload})
                self.checkpoint('semantic_call_finished', {'component': component, 'elapsedMs': 1., 'value': 'skip'})
                return result('skip')
        class Bridge:
            closed = False
            def __init__(self, sink): self.sink = sink
            def start(self): return 'http://localhost/engineering-fixture'
            def wait_ready(self, timeout, require_model):
                self.sink('browser_engineering_ready', {'ready': ready, 'modelCalled': False})
                return {'status': 'ready'} if ready else {'status': 'incomplete', 'reason': 'fixture_device_unavailable'}
            def close(self):
                self.closed = True
                self.sink('browser_engineering_closed', {'modelCalled': False})
        provider = Provider(); bridge_list = []; identities = []
        def factory(_manifest, *, global_checkpoint):
            bridge = Bridge(global_checkpoint); bridge_list.append(bridge)
            return provider, bridge
        actual_session = evaluation.ModelSession
        class RecordingSession(actual_session):
            def __init__(self, *args, **kwargs):
                identities.append(kwargs['identity']); super().__init__(*args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            plan_path, record_path = Path(directory)/'plan.json', Path(directory)/'record.json'
            plan_path.write_text(json.dumps(plan))
            with ExitStack() as stack:
                stack.enter_context(patch.object(evaluation, 'verify', return_value=([first, second], manifest())))
                stack.enter_context(patch.object(evaluation, 'paths', return_value=(plan_path, record_path)))
                stack.enter_context(patch('short_mixed_provider.create_provider', side_effect=factory))
                stack.enter_context(patch.object(evaluation, 'ModelSession', RecordingSession))
                code = evaluation.worker(plan_path)
            record = json.loads(record_path.read_text())
            browser_events = list(common.JournalStream(record['browserRawJournal']['path'], record['planSha256']))
            self.assertTrue(bridge_list[0].closed)
            self.assertEqual(len(browser_events), record['browserRawJournal']['events'])
            self.assertIn('browser_GPU_and_process_memory_not_measured', record['browserRawJournal']['memoryMeasurement'])
            return code, record, observations, identities, plan

    def test_ready_failure_preserves_all_registered_cases_without_any_model_call(self):
        code, record, observations, identities, plan = self.run_fixture(ready=False)
        self.assertEqual(code, 1)
        self.assertEqual(observations, []); self.assertEqual(identities, [])
        self.assertEqual(record['attempts'], [])
        self.assertTrue(all(slot['status'] == 'not_started' for slot in record['attemptSlots']))
        self.assertEqual(record['browserBootstrap']['status'], 'incomplete')

    def test_per_case_binding_cancellation_and_current_runtime_identity(self):
        code, record, observations, identities, plan = self.run_fixture()
        self.assertEqual(code, 0); self.assertEqual(len(observations), 2)
        self.assertNotEqual(observations[0]['binding']['caseId'], observations[1]['binding']['caseId'])
        self.assertTrue(observations[1]['previous_cancelled'])
        self.assertTrue(all(not r['cancelled_now'] and r['binding'] == r['binding_now'] for r in observations))
        self.assertTrue(all(i.implementation == digest(plan['codeSha256']) for i in identities))
        self.assertEqual(record['unexecutedAttempts'], 0)
        self.assertTrue(all(a['timing']['primitiveCalls'] == 1 for a in record['attempts']))


if __name__ == '__main__': unittest.main()
