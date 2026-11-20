"""Reference identity, reversible annotations and controlled-expression handoff."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import realizer_slots as s


class SlotContractTests(unittest.TestCase):
    def test_all_original_fields_survive_added_reference_instructions(self):
        for row in s.train_rows()+s.evaluation_rows():
            original=s.t.realizer_payload(row);candidate=s.slot_payload(row)
            self.assertEqual(s.original_payload(candidate),original)
            self.assertEqual(len(candidate['计划']),len(original['计划']))
            for a,b in zip(candidate['计划'],original['计划']):
                self.assertEqual(a['动作'],b['动作']);self.assertEqual(a['拟说内容'],b['拟说内容'])

    def test_input_and_runtime_binding_do_not_read_reference_labels(self):
        row=s.train_rows()[0];expected=s.slot_payload(row);bound=s.bindings(row)
        del row['expressionDraft'];del row['expressionSha256']
        row['assistantPrecheck']='DO NOT INCLUDE ANNOTATION IN MODEL INPUT'
        self.assertEqual(s.slot_payload(row),expected);self.assertEqual(s.bindings(row),bound)
        self.assertNotIn('DO NOT INCLUDE',s.t.payload_text(s.slot_payload(row)))

    def test_mirrored_characters_use_stable_ids_not_always_actor_one(self):
        a,b=[r for r in s.new_rows() if r['sourceGroup']=='d-slots-source-06']
        self.assertEqual(s.slot_payload(a)['人物引用'],'【人1】')
        self.assertEqual(s.slot_payload(b)['人物引用'],'【人2】')
        self.assertEqual(s.slot_payload(a)['计划'][0]['接收人'][0]['引用'],'【人2】')
        self.assertEqual(s.slot_payload(b)['计划'][0]['接收人'][0]['引用'],'【人1】')

    def test_annotations_restore_original_spans_but_runtime_uses_full_registered_names(self):
        for row in s.train_rows()+s.evaluation_rows():
            a=s.annotation_projection(row);spans=iter(a['spanTrace'])
            self.assertEqual(s.MARKER.sub(lambda match:next(spans)['sourceText'],a['target']),row['expressionDraft'])
            self.assertEqual(s.lexicalize(a['target'],s.bindings(row))['text'],a['canonicalReference'])
        row=s.train_rows()[0];a=s.annotation_projection(row)
        self.assertIn('梁芷（甲）',a['canonicalReference']);self.assertNotIn('（甲）',row['expressionDraft'])

    def test_missing_unknown_malformed_and_duplicate_literal_markers_are_not_repaired(self):
        row=next(r for r in s.train_rows() if r['annotationId']=='realizer-new-07');bound=s.bindings(row);target=s.slot_target(row)
        for raw in (target.replace('【人1】',''),target+'【物99】',target+'【坏1】',target+'【话1】'):
            result=s.lexicalize(raw,bound);self.assertEqual(result['status'],'rejected');self.assertIsNone(result['text'])

    def test_literal_and_name_marker_lookalikes_are_replaced_once_only(self):
        bound={'entries':[{'marker':'【人1】','value':'人名【物2】','type':'entity'},
            {'marker':'【物2】','value':'登记物品','type':'entity'},
            {'marker':'【话1】','value':'请写【人9】原样。','type':'literal'}]}
        result=s.lexicalize('【人1】展示【物2】并说【话1】',bound)
        self.assertEqual(result['text'],'人名【物2】展示登记物品并说请写【人9】原样。')

    def test_reference_presence_never_claims_or_repairs_verb_semantics(self):
        bound=s.bindings(s.train_rows()[0]);raw='【人1】吃掉【物1】。'
        result=s.lexicalize(raw,bound)
        self.assertIn('吃掉',result['text']);self.assertNotIn('合上',result['text'])
        self.assertEqual(result['status'],'rendered_not_semantically_approved')
        self.assertIn('not_verb_step_or_direction',result['coverage'])

    def test_duplicate_names_need_explicit_annotation_instead_of_guessed_training_spans(self):
        row=copy.deepcopy(next(r for r in s.new_rows() if r['annotationId']=='slots-probe-06-a'))
        chars=row['sourceCase']['input']['world']['characters'];chars[1]['name']=chars[0]['name']
        with self.assertRaisesRegex(ValueError,'ambiguous automatic target'):s.annotation_projection(row)

    def test_new_probe_pairs_and_gradient_sources_are_disjoint_and_novelty_is_recorded(self):
        manifest=s.source_materials();rows=s.new_rows();train=s.train_rows()
        self.assertEqual((len(rows),len({r['sourceGroup'] for r in rows})),(24,12))
        self.assertFalse({r['sourceGroup'] for r in train}&{r['sourceGroup'] for r in s.evaluation_rows()})
        self.assertEqual(sum(v['abstractReferenceVerbPatternSeenInTraining'] for v in manifest['sources']),9)
        self.assertTrue(any(len(r['planDraft']['steps'])==3 for r in rows))
        self.assertTrue(any(len(step['recipients'])==2 for r in rows for step in r['planDraft']['steps']))
        self.assertFalse(manifest['formalEvaluationAllowed']);self.assertEqual(manifest['newIndependentVerifiedGroups'],0)
        for group in {r['sourceGroup'] for r in rows}:
            pair=[r for r in rows if r['sourceGroup']==group];self.assertEqual({r['variant'] for r in pair},{'a','b'})

    def test_complete_tokenizer_audit_has_no_neural_forward_or_truncation(self):
        audit=s.tokenizer_materials();self.assertEqual(len(audit['examples']),72)
        self.assertEqual(audit['neuralForwardCalls'],0);self.assertFalse(audit['neuralModelLoaded'])
        self.assertLessEqual(audit['maxSlotInputTokens'],384);self.assertLessEqual(audit['maxSlotTargetTokens'],64)
        for row,encoded in zip(s.train_rows()+s.evaluation_rows(),audit['examples']):
            self.assertEqual(encoded['slots']['targetSha256'],s.t.digest(s.slot_target(row)))
            self.assertEqual(encoded['slots']['labels'][-1],1)

    def test_prepared_plan_binds_supervisor_environment_and_rejects_scope_drift(self):
        audit=s.tokenizer_materials();environment=s.t.observe_environment(s.ROOT)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);weights=root/'fixture.pt';weights.write_bytes(b'unit fixture, never loaded')
            baseline={'checkpoint':{'path':str(weights),'sha256':s.t.sha256_file(weights)}}
            with mock.patch.object(s,'MANIFEST',root/'manifest.json'),mock.patch.object(s,'baseline_source',return_value=(baseline,{})),mock.patch.object(s.t.old,'paths',side_effect=lambda run:(root/(run+'.plan.json'),root/(run+'.record.json'))),mock.patch.object(s.t,'observe_m02',return_value=audit['modelIdentity']) as model,mock.patch.object(s.t,'observe_environment',return_value=environment):
                s.prepare();plan=s.t.run.read_json(root/(s.RUN+'-s42.plan.json'));s.verify(plan)
                self.assertEqual(plan['environment'],environment)
                for mutate in ('environment','seed','config'):
                    bad=copy.deepcopy(plan)
                    if mutate=='environment':bad.pop('environment')
                    elif mutate=='seed':bad['seed']=8
                    else:bad['config']['maxNewTokens']=1
                    model.reset_mock()
                    with self.assertRaisesRegex(ValueError,'execution plan drift'):s.verify(bad)
                    model.assert_not_called()

    def test_promotion_requires_both_seed_new_group_gains_and_no_old_regression(self):
        good={'natural':{'new_probe':{'candidate_correct':4,'allVariantsCorrectGroups':2},'old_regression':{'candidate_correct':5}},
              'slots':{'new_probe':{'candidate_correct':5,'allVariantsCorrectGroups':2},'old_regression':{'candidate_correct':5}}}
        self.assertTrue(s.promotion_status({'42':good,'7':good}).startswith('research_candidate'))
        bad=copy.deepcopy(good);bad['slots']['old_regression']['candidate_correct']=4
        self.assertTrue(s.promotion_status({'42':good,'7':bad}).startswith('mixed'))

    def test_archived_runs_count_all_training_and_full_expression_units(self):
        runs=[s.observed(seed) for seed in s.SEEDS]
        self.assertEqual(sum(r['trainingSteps'] for r in runs),640)
        self.assertEqual(sum(r['trainingSampleUses'] for r in runs),1280)
        self.assertEqual(sum(r['generationCalls'] for r in runs),168)
        self.assertEqual(sum(r['historicalRegressionOutputsReproduced'] for r in runs),36)
        for run in runs:
            self.assertEqual(run['modelForwardCounts']['encoderForwardCallsByPhase'],{'natural':42,'training':320,'slots':42})
            self.assertTrue(all(u['prediction']['eos'] for u in run['units']))
            self.assertEqual(len(run['units']),84)

    def test_final_report_preserves_reference_rejections_and_semantic_regressions(self):
        summary=s.materials();runs,decisions=s.reviewed_runs()
        self.assertTrue(summary['promotionStatus'].startswith('mixed'))
        self.assertFalse(summary['formalEvaluationAllowed']);self.assertFalse(summary['semanticQualityApproved'])
        self.assertFalse(summary['plannerModelImplemented']);self.assertEqual(summary['fullRequest500msStatus'],'unverified')
        for run in runs:
            for phase in ('natural','slots'):
                self.assertEqual(summary['qualityCounts'][str(run['seed'])][phase]['new_probe']['examples'],24)
                self.assertEqual(summary['qualityCounts'][str(run['seed'])][phase]['old_regression']['examples'],18)
            for u in run['units']:
                if u['rendering']['text'] is None:self.assertEqual(decisions[s.review_key(u)]['verdict'],'fail')
        # Complete references do not cover a missing middle action.
        u=next(u for u in runs[0]['units'] if u['phase']=='slots' and u['annotationId']=='slots-probe-10-a')
        self.assertIsNotNone(u['rendering']['text']);self.assertEqual(decisions[s.review_key(u)]['verdict'],'fail')

    def test_invented_rendered_text_cannot_replace_the_logged_model_output(self):
        _,rp=s.t.old.paths(s.RUN+'-s42');path=s.search.available(rp);read=s.t.run.read_json;bad=read(path)
        bad['attempts'][0]['slotUnits'][0]['rendering']['text']='invented perfect answer'
        with mock.patch.object(s.t.run,'read_json',side_effect=lambda p:copy.deepcopy(bad) if p==path else read(p)):
            with self.assertRaisesRegex(ValueError,'journal reconstruction differs'):s.observed(42)

    def test_report_is_deterministic_without_running_a_business_model(self):
        import os,subprocess
        for seed in ('0','9'):
            result=subprocess.run([sys.executable,str(Path(s.__file__)),'--check'],capture_output=True,text=True,timeout=45,
                env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1'})
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['generations'],168)


class SlotHandoffTests(unittest.TestCase):
    def test_shared_generator_and_timed_reference_handoff_without_pretrained_model(self):
        import torch
        torch.set_num_threads(1)
        class Tokenizer:
            eos_token_id=1
            def encode(self,text,**kwargs):return [5,1]
            def decode(self,ids,**kwargs):return '【人1】尝试合上【物1】。'
        class NumericFixture(torch.nn.Module):
            def forward(self,*args,**kwargs):return None
            def generate(self,**kwargs):self();self();return torch.tensor([[0,5,1]])
        row=s.train_rows()[0];del row['expressionDraft'];events=[]
        units=s.expression_units(torch,NumericFixture(),Tokenizer(),[row],'slots',lambda n,p:events.append((n,copy.deepcopy(p))),s.CONFIG)
        unit=units[0]
        self.assertEqual(unit['rendering']['text'],'梁芷（甲）尝试合上铜印匣。')
        self.assertEqual(unit['prediction']['modelTopForwardCalls'],2)
        self.assertGreaterEqual(unit['elapsedIncludingTelemetryMs'],unit['elapsedThroughResultMs'])
        self.assertGreaterEqual(unit['elapsedThroughResultMs'],unit['prediction']['elapsedIncludingOutputJournalMs'])
        s.search.validate_generation_snapshot([unit['prediction']],[p for n,p in events if n=='generation_output'],[p for n,p in events if n=='generation_timing'])
        recorded=next(p for n,p in events if n=='expression_unit_result')
        self.assertEqual({k:v for k,v in unit.items() if k not in ('elapsedThroughResultMs','elapsedIncludingTelemetryMs')},recorded)


if __name__=='__main__':unittest.main()
