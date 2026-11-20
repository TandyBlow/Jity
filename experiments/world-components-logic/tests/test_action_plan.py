"""Plan boundary and preparation tests; never import a model or run training."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import action_plan as plans
import experiment
from pilot_codec import unpack


class PlanPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows,cls.review=plans.build_drafts()
        cls.sources={r['case']['caseId']:r['case'] for r in plans.source_rows()[0]}

    def example(self,suffix='05'):
        row=copy.deepcopy(next(r for r in self.rows if r['sourceCaseId']=='dev-d02-'+suffix))
        return self.sources[row['sourceCaseId']],row['planDraft']

    def claims(self,rows=None):
        rows=self.rows if rows is None else rows
        return {'schema':'jity-d-action-plan-review-claims-v1','batchId':plans.BATCH,
                'packetSha256':plans.packet_identity(rows),'reviewer':'synthetic test fixture, not a real human receipt',
                'decisions':[{'annotationId':r['annotationId'],'annotationSha256':plans.digest(r),
                              'decision':'agree','note':'unit fixture only'} for r in rows]}

    def test_ten_drafts_are_unreviewed_and_original_roles_are_read_from_source(self):
        self.assertEqual(len(self.rows),10);self.assertEqual(len({r['sourceGroup'] for r in self.rows}),10)
        self.assertEqual(sum(r['planDraft']['kind']=='act' for r in self.rows),5)
        self.assertTrue(all(not r['trainingEligible'] and r['labelStatus']=='draft_pending_human_review' for r in self.rows))
        roles={r['sourceCaseId'][-2:]:r['originalRole'] for r in self.rows}
        self.assertEqual(sum(r=='fit' for r in roles.values()),8)
        self.assertEqual([roles[k] for k in ('01','07','03','05')],['fit','fit','retained_development','retained_development'])

    def test_roles_match_archived_event2_records_not_prose(self):
        import gzip
        record=json.loads(gzip.decompress((plans.ART/'m01-fitting/m01-event-dev42-20261102-r1.record.json.gz').read_bytes()))
        roles={r['caseId']:r['role'] for r in record['fitAndDevelopmentPredictions'] if r['arm']=='event2' and r['task']=='D02'}
        self.assertEqual({r['sourceCaseId']:r['originalRole'] for r in self.rows},roles)

    def test_expression_targets_are_separate_unreviewed_annotations_not_inputs(self):
        self.assertEqual(sum(r['expressionDraft'] is not None for r in self.rows),5)
        for row in self.rows:
            self.assertEqual(row['expressionSha256'],plans.digest(row['expressionDraft']))
            c=self.sources[row['sourceCaseId']]
            payload=plans.realizer_preview(c,plans.bind_candidate(c,row['planDraft']))
            self.assertNotIn('expressionDraft',json.dumps(payload))
            if row['planDraft']['kind']=='skip':self.assertIsNone(row['expressionDraft'])
            else:self.assertNotIn(row['expressionDraft'],json.dumps(payload,ensure_ascii=False))

    def test_planner_keeps_complete_world_without_draft_labels(self):
        for row in self.rows:
            c=self.sources[row['sourceCaseId']];v=plans.planner_input(c)
            self.assertEqual(unpack(v['payload']),c['input']);self.assertEqual(v['sourceInputSha256'],plans.digest(c['input']))
            self.assertFalse(v['containsPlanLabels']);self.assertFalse(v['modelImplemented'])
            raw=json.dumps(v['payload']);self.assertNotIn('planDraft',raw);self.assertNotIn('mustRespect',raw)

    def test_plan_draft_is_not_mutated_by_binding_or_preview(self):
        c,p=self.example();original=copy.deepcopy((c,p));b=plans.bind_candidate(c,p);preview=plans.realizer_preview(c,b)
        self.assertEqual((c,p),original);self.assertFalse(b['semanticApproved'])
        self.assertFalse(preview['allowedForModelUse']);self.assertFalse(preview['modelExecuted'])
        self.assertEqual(preview['planSha256'],plans.digest(p))

    def test_wrong_actor_is_rejected(self):
        c,p=self.example();p['actorId']='p3'
        with self.assertRaisesRegex(ValueError,'actor'):plans.bind_candidate(c,p)

    def test_unknown_wrong_type_and_duplicate_references_are_rejected(self):
        for ref in ({'kind':'item','id':'missing'},{'kind':'place','id':'item_1'},{'kind':'item','id':None}):
            c,p=self.example();p['steps'][0]['objects']=[ref]
            with self.assertRaises(ValueError):plans.validate_candidate(c,p)
        c,p=self.example();p['steps'][0]['objects']*=2
        with self.assertRaisesRegex(ValueError,'duplicate'):plans.validate_candidate(c,p)

    def test_outcome_dice_and_extra_step_fields_are_rejected(self):
        for key in ('success','roll','newState'):
            c,p=self.example();p[key]=True
            with self.assertRaisesRegex(ValueError,'closed draft'):plans.validate_candidate(c,p)
        c,p=self.example();p['steps'][0]['outcome']='成功'
        with self.assertRaisesRegex(ValueError,'closed step'):plans.validate_candidate(c,p)

    def test_skip_has_no_expression_and_cannot_smuggle_steps(self):
        c,p=self.example('03');v=plans.realizer_preview(c,plans.bind_candidate(c,p))
        self.assertFalse(v['wouldCallExpression']);self.assertFalse(v['modelExecuted'])
        p['steps']=[self.example()[1]['steps'][0]]
        with self.assertRaisesRegex(ValueError,'skip'):plans.validate_candidate(c,p)
        c,p=self.example();p['steps']=[]
        with self.assertRaisesRegex(ValueError,'act needs'):plans.validate_candidate(c,p)

    def test_verb_space_is_open_and_actions_need_not_have_an_object(self):
        c,p=self.example();p['steps']=[{'verb':'侧耳分辨远处动静','objects':[],'tools':[],
                                      'destinations':[],'recipients':[],'utterance':None}]
        self.assertTrue(plans.validate_candidate(c,p)['structurallyValid'])
        self.assertFalse(plans.validate_candidate(c,p)['semanticApproved'])

    def test_structurally_valid_wrong_task_is_not_given_semantic_approval(self):
        c,p=self.example('07');p['basis']=['/world/characters/2/tasks/0'];p['steps'][0]['verb']='核对'
        p['steps'][0]['objects']=[{'kind':'item','id':'item_2'}]
        # This is exactly the type of prior semantic failure: legal IDs and
        # current actor, but another person's task. Structure must not certify it.
        v=plans.validate_candidate(c,p);self.assertTrue(v['structurallyValid']);self.assertFalse(v['semanticApproved'])

    def test_stale_world_or_modified_binding_cannot_be_expressed(self):
        c,p=self.example();bound=plans.bind_candidate(c,p);changed=copy.deepcopy(c)
        changed['input']['world']['items'][0]['name']='changed'
        with self.assertRaisesRegex(ValueError,'stale'):plans.realizer_preview(changed,bound)
        bound['semanticApproved']=True
        with self.assertRaisesRegex(ValueError,'stale'):plans.realizer_preview(c,bound)

    def test_reference_lexicon_resolves_exact_original_names(self):
        c,p=self.example('01');preview=plans.realizer_preview(c,plans.bind_candidate(c,p))
        lex=preview['payload']['lexicon'];self.assertEqual(len(lex),len({(r['kind'],r['id']) for r in lex}))
        original=plans.lookup(c)
        for r in lex:self.assertEqual(r['name'],original[(r['kind'],r['id'])]['name'])
        self.assertTrue(preview['plannerFullCoverageRequired'])

    def test_missing_or_noncanonical_evidence_is_rejected(self):
        c,p=self.example()
        for path in ('/world/noSuchField','/world/characters/01/id','/world/characters/-1/id','/world/~0'):
            with self.assertRaises(ValueError):plans.resolve_pointer(c['input'],path)
        p['basis']*=2
        with self.assertRaisesRegex(ValueError,'duplicate source'):plans.validate_candidate(c,p)

    def test_no_plan_review_means_no_fit_export(self):
        self.assertEqual(plans.review_status(self.rows)['newPlanLabelsReviewed'],0)
        with self.assertRaisesRegex(ValueError,'no fitting export'):plans.fitting_packet(self.rows,None)

    def test_old_case_review_does_not_approve_new_plan_labels(self):
        old={'schema':'jity-d-user-review-claims-v1','reviewer':'old case initial reviewer','decisions':[]}
        with self.assertRaisesRegex(ValueError,'original case review'):plans.review_status(self.rows,old)

    def test_wrong_batch_packet_or_annotation_claims_are_rejected(self):
        for field in ('batchId','packetSha256'):
            claims=self.claims();claims[field]='stale'
            with self.assertRaisesRegex(ValueError,'batch identity'):plans.review_status(self.rows,claims)
        claims=self.claims();claims['decisions'][0]['annotationSha256']='stale'
        with self.assertRaisesRegex(ValueError,'annotation identity'):plans.review_status(self.rows,claims)

    def test_duplicate_partial_or_uncertain_reviews_cannot_open_fit_export(self):
        c=self.claims();c['decisions'].append(c['decisions'][0])
        with self.assertRaisesRegex(ValueError,'annotation identity'):plans.review_status(self.rows,c)
        for verdict in ('partial','uncertain','needs_change'):
            c=self.claims()
            if verdict=='partial':c['decisions'].pop()
            else:c['decisions'][0].update(decision=verdict,note='requires verification')
            with self.assertRaisesRegex(ValueError,'no fitting export'):plans.fitting_packet(self.rows,c)

    def test_assistant_claim_is_not_a_human_review(self):
        c=self.claims();c['reviewer']='assistant'
        with self.assertRaisesRegex(ValueError,'human reviewer'):plans.review_status(self.rows,c)

    def test_synthetic_review_exports_only_old_split_proposal_without_execution_authority(self):
        # Entirely in-memory fixture; no human receipt or approved data is written.
        packet=plans.fitting_packet(self.rows,self.claims())
        self.assertEqual(len(packet['fit']),8);self.assertEqual(len(packet['retainedDevelopment']),2)
        self.assertEqual({r['sourceCase']['caseId'] for r in packet['retainedDevelopment']},{'dev-d02-03','dev-d02-05'})
        self.assertFalse(packet['formalEvaluationAllowed']);self.assertFalse(packet['trainingExecuted'])
        self.assertFalse(packet['trainingExecutionAuthorizedByThisFile']);self.assertEqual(packet['newIndependentTrainingGroups'],0)
        self.assertTrue(all(not r['realizerAnnotationInput']['modelExecuted'] for r in packet['fit']))

    def test_reviewed_claims_cannot_move_a_source_across_splits(self):
        rows=copy.deepcopy(self.rows);next(r for r in rows if r['sourceCaseId']=='dev-d02-03')['originalRole']='fit'
        with self.assertRaisesRegex(ValueError,'source input/group/split'):plans.fitting_packet(rows,self.claims(rows))

    def test_stale_plan_hash_cannot_be_exported(self):
        rows=copy.deepcopy(self.rows);rows[0]['planDraft']['steps'][0]['verb']='改写'
        with self.assertRaisesRegex(ValueError,'stale plan'):plans.fitting_packet(rows,self.claims(rows))

    def test_changed_expression_requires_a_new_review_identity(self):
        rows=copy.deepcopy(self.rows);claims=self.claims(rows);rows[0]['expressionDraft']='different reference'
        with self.assertRaisesRegex(ValueError,'batch identity'):plans.review_status(rows,claims)
        with self.assertRaisesRegex(ValueError,'stale plan/expression'):plans.fitting_packet(rows,self.claims(rows))

    def test_materials_are_reproducible_and_do_not_import_model_libraries(self):
        with mock.patch.dict(sys.modules,{'torch':None,'transformers':None}):
            a,files=plans.build_materials();b,other=plans.build_materials()
        self.assertEqual(a,b);self.assertEqual(files,other)
        self.assertEqual(a['trainingSteps'],0);self.assertEqual(a['modelInferenceCalls'],0)
        self.assertFalse(a['plannerModelImplemented']);self.assertFalse(a['semanticQualityApproved'])

    def test_prepared_material_drift_is_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.json';p.write_bytes(b'original')
            with mock.patch.object(plans,'build_materials',return_value=({}, {p:b'different'})):
                with self.assertRaisesRegex(ValueError,'preserve earlier'):plans.prepare_materials(write=True)
            self.assertEqual(p.read_bytes(),b'original')

    def test_unified_plan_data_entry_never_executes_models(self):
        with mock.patch.object(plans,'prepare_materials',return_value={'batchId':'test','review':{'newPlanLabelsReviewed':0}}) as prepare,redirect_stdout(io.StringIO()):
            with mock.patch.dict(sys.modules,{'torch':None,'transformers':None}):
                self.assertEqual(experiment.main(['plan-data']),0)
            prepare.assert_called_once_with(write=False)

if __name__=='__main__':unittest.main()
