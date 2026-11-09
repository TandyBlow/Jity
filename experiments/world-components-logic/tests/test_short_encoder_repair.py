"""Engineering counterexamples; tiny fake features are not model evidence."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import short_encoder_repair as repair
from short_training import training_schedule
from test_short_intent import canonical_context


def payload():
    return {'context': canonical_context(), 'fragments': [], 'opportunityId': 'op:fixture',
            'reactionConstraints': None, 'representation': 'natural', 'semanticQuery': {}}


def manifest():
    tasks = {c: {'kind': 'label', 'labels': ['act','skip','incomplete'] if c == 'D02.1' else ['fragment','end']}
             for c in repair.COMPONENTS}
    return {'schema': 'jity-d-focus-encoder-provider-v1', 'arm': 'global_plus_focus',
            'tasks': tasks, 'config': copy.deepcopy(repair.CONFIG), 'trainingSteps': 2,
            'componentNonzeroDataGradientSteps': {c: 2 for c in repair.COMPONENTS},
            'componentLabelDataGradientExposures': {c: {v: 1 for v in t['labels']} for c,t in tasks.items()}}


class FocusProjectionTests(unittest.TestCase):
    def test_projection_preserves_actual_request_and_is_independent_copy(self):
        p = payload(); original = copy.deepcopy(p)
        focus = repair.focus_payload('D02.2.next', p)
        self.assertEqual(focus['context']['advance'], p['context']['advance'])
        self.assertEqual(focus['fragments'], p['fragments'])
        self.assertEqual(focus['opportunityId'], p['opportunityId'])
        self.assertEqual(focus['executorBinding']['id'], 'a')
        self.assertEqual(focus['executorBinding']['current'], p['context']['world']['characters']['a'])
        focus['context']['advance']['inputText'] = 'mutated'
        self.assertEqual(p, original)

    def test_reaction_executor_uses_member_not_originating_actor(self):
        p = payload(); p.update(memberId='b', threats=[{'memberId':'a','actionText':'尝试夺走图纸。'}],
                               judgments=[{'targetId':'b','admitted':True}], frozenActions=[{'memberId':'a'}])
        p['semanticQuery'] = {'constraints': ['已有约束']}
        focus = repair.focus_payload('D04.1.next', p)
        self.assertEqual(focus['executorBinding']['id'], 'b')
        self.assertEqual(focus['context']['actorId'], 'a')
        for field in ('threats','judgments','frozenActions','semanticQuery'): self.assertEqual(focus[field], p[field])

    def test_reaction_short_intent_preserves_constraints_and_reactor_context(self):
        p = payload(); p['context']['actorId'] = 'b'; p['reactionConstraints'] = {'constraints':['避开软刷。']}
        self.assertEqual(repair.focus_payload('D02.2.next', p)['executorBinding']['id'], 'b')
        self.assertEqual(repair.focus_payload('D02.2.next', p)['reactionConstraints'], p['reactionConstraints'])

    def test_joint_next_keeps_all_members_judgments_and_current_facts(self):
        p = payload(); p['context'].pop('actorId'); p['context']['group'] = {'memberIds':['a','b'], 'judgments':[{'passed':False}]}
        p.update(candidates=[{'text':'失败仍留下划痕。'}], joint={'judgments':[{'attemptId':'b','label':'not_achieved'}]})
        f = repair.focus_payload('D05.3.next', p)
        self.assertEqual(f['context']['group'], p['context']['group'])
        self.assertEqual(f['candidates'], p['candidates']); self.assertEqual(f['joint'], p['joint'])
        self.assertIsNone(f['executorBinding']['id'])

    def test_missing_executor_or_world_rejected_not_guessed(self):
        p = payload(); p['context']['actorId'] = 'absent'
        with self.assertRaisesRegex(ValueError, 'executor missing'): repair.focus_payload('D02.1',p)
        p = payload(); p['context'].pop('world')
        with self.assertRaisesRegex(ValueError, 'world'): repair.focus_payload('D02.1',p)

    def test_unregistered_head_has_no_projection(self):
        with self.assertRaisesRegex(ValueError, 'unregistered'): repair.focus_payload('D05.2.label',payload())

    def test_all_original_facts_are_sent_to_global_encoder_unchanged(self):
        p = payload(); p['context']['world']['items']['offstage-new'] = {'unusual':'全局必须保留'}
        calls = []
        class Torch:
            @staticmethod
            def cat(items): return tuple(items)
        def encoder(_torch,_model,_tok,c,v,_cfg,_log): calls.append((c,copy.deepcopy(v))); return c
        with patch.object(repair,'encode_complete',encoder):
            repair.feature(Torch,None,None,'D02.2.next',p,repair.CONFIG,lambda *_:None,'global_plus_focus')
        self.assertEqual(calls[0], ('D02.2.next',p))
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[1][0],'D02.2.next:focus')

    def test_control_uses_complete_single_branch_and_equal_head_dimensions(self):
        class Torch:
            @staticmethod
            def cat(items): return tuple(items)
        self.assertEqual(repair.representation(Torch,'full','focus','full_mean_control'),('full','full'))
        self.assertEqual(repair.representation(Torch,'full','focus','global_plus_focus'),('full','focus'))


class TrainingAndProviderTests(unittest.TestCase):
    def test_full_real_packet_each_training_row_and_each_class_exposed(self):
        path = repair.ART/'data/short-encoder-repair-20261109-r5/supervision.jsonl.gz'
        if not path.exists(): self.skipTest('local packet absent')
        rows = repair.selected_rows(path); schedule = training_schedule(rows,repair.CONFIG)
        inv = repair.inventory(rows,schedule)
        self.assertEqual(set(schedule['exampleIds']),{r['exampleId'] for r in rows if r['split']=='train'})
        self.assertTrue(all(v['minimumRowExposure']>0 for v in inv.values()))
        self.assertEqual(sum(schedule['taskExposures'].values()),repair.CONFIG['steps']*repair.CONFIG['batchSize'])

    def test_other_58_heads_not_silently_migrated(self):
        provider = repair.FocusSemanticProvider(manifest())
        provider._load = lambda: self.fail('must not load unknown task')
        completion = provider('D05.2.label',payload())
        self.assertEqual(completion.status,'incomplete')
        self.assertEqual(provider.primitive_calls,0)
        self.assertEqual(provider.identity['components'],list(repair.COMPONENTS))

    def test_zero_gradient_or_untrained_class_refuses_before_model(self):
        for mode in ('head','class'):
            m = manifest()
            if mode == 'head': m['componentNonzeroDataGradientSteps']['D02.1'] = 0
            else: m['componentLabelDataGradientExposures']['D02.1']['skip'] = 0
            provider = repair.FocusSemanticProvider(m); provider._load = lambda: self.fail('must not load')
            self.assertEqual(provider('D02.1',payload()).status,'incomplete')
            self.assertEqual(provider.primitive_calls,0)

    def test_provider_identity_drift_refused(self):
        provider = repair.FocusSemanticProvider(manifest()); provider.identity['components'].append('other')
        self.assertEqual(provider('D02.1',payload()).reason,'focus_provider_identity_changed')

    def test_explicit_end_preserved_and_no_forced_generation(self):
        import torch
        provider = repair.FocusSemanticProvider(manifest()); events = []
        provider.checkpoint = lambda name,p: events.append((name,p))
        heads = {'D02.2.next': lambda value: torch.tensor([-2.,3.])}
        provider._load = lambda: (torch,None,None,heads,{'D02.2.next':{'mean':torch.zeros(2),'std':torch.ones(2)}})
        with patch.object(repair,'feature',return_value=(torch.zeros(2),None,None)):
            completion = provider('D02.2.next',payload())
        self.assertEqual(completion.value,'end'); self.assertEqual(completion.status,'result')
        self.assertEqual(events[-1][1]['rawLogits'],[-2.,3.])

    def test_semantic_incomplete_remains_incomplete_and_logs_raw_label(self):
        import torch
        provider = repair.FocusSemanticProvider(manifest()); events = []
        provider.checkpoint = lambda name,p: events.append((name,p))
        provider._load = lambda: (torch,None,None,{'D02.1':lambda value:torch.tensor([-2.,0.,3.])},
                                 {'D02.1':{'mean':torch.zeros(2),'std':torch.ones(2)}})
        with patch.object(repair,'feature',return_value=(torch.zeros(2),None,None)):
            completion = provider('D02.1',payload())
        self.assertEqual(completion.status,'incomplete'); self.assertEqual(completion.reason,'semantic_incomplete:D02.1')
        self.assertEqual(events[-1][1]['rawLabel'],'incomplete')

    def test_pre_call_deadline_rejection_does_not_call_model_or_count(self):
        provider = repair.FocusSemanticProvider(manifest())
        provider.checkpoint = lambda *_: (_ for _ in ()).throw(RuntimeError('case_deadline'))
        provider._load = lambda: self.fail('must not load after deadline')
        with self.assertRaisesRegex(RuntimeError,'case_deadline'): provider('D02.1',payload())
        self.assertEqual(provider.primitive_calls,0)

    def test_equal_parameter_count_two_arms(self):
        import torch
        a = repair.build_model(torch,256,['end','fragment'],repair.CONFIG)
        b = repair.build_model(torch,256,['end','fragment'],repair.CONFIG)
        self.assertEqual(sum(p.numel() for p in a.parameters()),sum(p.numel() for p in b.parameters()))


if __name__ == '__main__': unittest.main()
