"""Training isolation, data identity and actual synthetic autograd checks."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import plan_training as trainer
from lab import guard_case


class Tokenizer:
    eos_token_id=1;pad_token_id=0
    def __init__(self):self.calls=[]
    def encode(self,text,**kwargs):
        self.calls.append((text,kwargs));return [2+ord(c)%97 for c in text]+[1]


class TrainingPreparationTests(unittest.TestCase):
    def setUp(self):self.rows=trainer.candidate_rows()
    def claims(self):
        return {'schema':'jity-d-realizer-training-review-v1','batchId':trainer.BATCH,
            'packetSha256':trainer.packet_identity(self.rows),'reviewer':'synthetic test receipt, no actual review',
            'decisions':[{'annotationId':r['annotationId'],'annotationSha256':trainer.digest(r),
                          'decision':'agree','note':'unit fixture only'} for r in self.rows]}

    def test_twelve_new_groups_are_disjoint_and_cover_each_cell_on_both_sides(self):
        self.assertEqual(len(self.rows),12);self.assertEqual(len({r['sourceGroup'] for r in self.rows}),12)
        for coverage in {r['coverage'] for r in self.rows}:
            self.assertEqual({r['role'] for r in self.rows if r['coverage']==coverage},{'train_candidate','development_candidate'})
            self.assertEqual(sum(r['coverage']==coverage for r in self.rows),2)
        self.assertTrue(all(not r['trainingEligible'] and r['sourceIndependence']=='unverified' for r in self.rows))

    def test_all_authored_worlds_and_typed_plans_are_structurally_valid(self):
        for r in self.rows:
            self.assertTrue(guard_case(r['sourceCase'])['shouldCall'])
            check=trainer.contract.validate_candidate(r['sourceCase'],r['planDraft'])
            self.assertFalse(check['semanticApproved']);self.assertEqual(check['sourceInputSha256'],r['sourceInputSha256'])
            self.assertEqual(trainer.digest(r['expressionDraft']),r['expressionSha256'])

    def test_realizer_input_contains_plan_facts_but_not_reference_sentence(self):
        for r in self.rows:
            x=trainer.input_text(r);self.assertNotIn(r['expressionDraft'],x)
            self.assertNotIn('expressionDraft',x);self.assertNotIn('sourceIndependence',x)
            payload=trainer.realizer_payload(r)
            self.assertEqual(len(payload['计划']),len(r['planDraft']['steps']))
            for a,b in zip(payload['计划'],r['planDraft']['steps']):self.assertEqual(a['动作'],b['verb'])

    def test_no_reviews_cannot_create_a_training_plan_or_load_models(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'claims.json';p.write_text('null')
            with mock.patch.object(trainer,'observe_m02') as model,mock.patch.object(trainer.old,'paths') as paths:
                with self.assertRaisesRegex(ValueError,'not fully reviewed'):trainer.training_plan('never-created',p)
                model.assert_not_called();paths.assert_not_called()

    def test_old_reviews_and_old_plan_reviews_are_rejected(self):
        for schema in ('jity-d-user-review-claims-v1','jity-d-action-plan-review-claims-v1'):
            claims=self.claims();claims['schema']=schema
            with self.assertRaisesRegex(ValueError,'batch drift'):trainer.reconcile_reviews(self.rows,claims)

    def test_packet_changed_reference_or_split_invalidates_review(self):
        claims=self.claims()
        for field in ('expressionDraft','role'):
            rows=copy.deepcopy(self.rows);rows[0][field]='changed'
            with self.assertRaisesRegex(ValueError,'batch drift'):trainer.reconcile_reviews(rows,claims)
        claims=self.claims();claims['decisions'][0]['annotationSha256']='changed'
        with self.assertRaisesRegex(ValueError,'identity drift'):trainer.reconcile_reviews(self.rows,claims)

    def test_partial_duplicate_and_uncertain_reviews_do_not_open_training(self):
        claims=self.claims();claims['decisions'].pop();self.assertFalse(trainer.reconcile_reviews(self.rows,claims)['trainingDataReady'])
        claims=self.claims();claims['decisions'].append(claims['decisions'][0])
        with self.assertRaisesRegex(ValueError,'identity drift'):trainer.reconcile_reviews(self.rows,claims)
        claims=self.claims();claims['decisions'][0].update(decision='uncertain',note='needs checking')
        self.assertFalse(trainer.reconcile_reviews(self.rows,claims)['trainingDataReady'])

    def test_assistant_cannot_self_sign_labels(self):
        c=self.claims();c['reviewer']='assistant'
        with self.assertRaisesRegex(ValueError,'human reviewer'):trainer.reconcile_reviews(self.rows,c)

    def test_complete_synthetic_claims_preserve_six_train_six_dev_only(self):
        with self.assertRaisesRegex(ValueError,'superseded'):trainer.reviewed_data(self.claims())
        rows=trainer.audited_candidate_rows();claims=self.claims()
        claims.update(batchId=trainer.AUDIT_BATCH,packetSha256=trainer.packet_identity(rows,batch_id=trainer.AUDIT_BATCH),
            decisions=[{'annotationId':r['annotationId'],'annotationSha256':trainer.digest(r),'decision':'agree','note':'synthetic test fixture only'} for r in rows])
        train,dev=trainer.reviewed_data(claims)
        self.assertEqual(len(train),6);self.assertEqual(len(dev),6)
        self.assertFalse({r['sourceGroup'] for r in train}&{r['sourceGroup'] for r in dev})
        self.assertFalse(trainer.reconcile_reviews(self.rows,self.claims())['formalEvaluationAllowed'])

    def test_audited_revision_repairs_missing_lamp_and_preserves_all_expression_inputs(self):
        revised=trainer.audited_candidate_rows();changed=[]
        for old,new in zip(self.rows,revised):
            if old!=new:changed.append(old['annotationId'])
            self.assertEqual(old['sourceGroup'],new['sourceGroup']);self.assertEqual(old['role'],new['role'])
            self.assertEqual(old['expressionDraft'],new['expressionDraft'])
            self.assertEqual(trainer.input_text(old),trainer.input_text(new))
            self.assertFalse(new['trainingEligible']);self.assertEqual(new['sourceIndependence'],'unverified')
            self.assertFalse(trainer.contract.validate_candidate(new['sourceCase'],new['planDraft'])['semanticApproved'])
        self.assertEqual(changed,['realizer-new-10'])
        before=self.rows[9];after=revised[9];items=after['sourceCase']['input']['world']['items']
        self.assertEqual(before['sourceCase']['input']['world']['items'][0]['position']['containerId'],'loc_a')
        self.assertEqual(items[0]['position']['containerId'],items[2]['id'])
        self.assertIn('冷却',items[2]['appearance']);self.assertIn('松开',items[2]['appearance'])
        self.assertEqual(after['revisionOfAnnotationSha256'],trainer.digest(before))
        for pointer in ('/world/items/0','/world/items/2'):
            self.assertIn(pointer,after['planDraft']['basis'])
            self.assertIn(trainer.contract.resolve_pointer(after['sourceCase']['input'],pointer),items)

    def test_assistant_precheck_never_opens_human_review_or_training(self):
        audit=trainer.label_audit_materials()
        self.assertEqual(audit['checkedAnnotations'],12);self.assertEqual(audit['correctedSourceInputs'],1)
        self.assertEqual(audit['review']['reviewedGroups'],0);self.assertFalse(audit['review']['trainingDataReady'])
        self.assertEqual(audit['newIndependentTrainingGroups'],0)
        self.assertFalse(any(e['humanReviewPerformed'] for e in audit['entries']))
        with self.assertRaises(ValueError):trainer.reviewed_data(audit)
        self.assertEqual(audit['sourceRisks'][0]['caseIds'],['realizer-new-05','realizer-new-06'])

    def test_old_batch_claims_cannot_approve_new_context_revision(self):
        with self.assertRaisesRegex(ValueError,'batch drift'):
            trainer.reconcile_reviews(trainer.audited_candidate_rows(),self.claims(),batch_id=trainer.AUDIT_BATCH)

    def test_future_training_plan_binds_revised_source_and_audit_without_executing_model(self):
        rows=trainer.audited_candidate_rows();claims=self.claims()
        claims.update(batchId=trainer.AUDIT_BATCH,packetSha256=trainer.packet_identity(rows,batch_id=trainer.AUDIT_BATCH),
            decisions=[{'annotationId':r['annotationId'],'annotationSha256':trainer.digest(r),'decision':'agree','note':'synthetic test fixture only'} for r in rows])
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'plan.json';review=Path(d)/'unit-receipt.json';review.write_text(json.dumps(claims))
            with mock.patch.object(trainer.old,'paths',return_value=(path,Path(d)/'record.json')),mock.patch.object(trainer,'observe_m02',return_value={'allSixFilesFullyRehashedAndVerified':True}),mock.patch.object(trainer,'observe_environment',return_value={'registeredVersionsMatch':True}):
                trainer.training_plan('unit-fixture-not-a-business-run',review);plan=json.loads(path.read_text());trainer.verify_training(plan)
                self.assertEqual(plan['candidateBatchId'],trainer.AUDIT_BATCH)
                self.assertEqual(plan['candidateAuditManifestSha256'],trainer.sha256_file(trainer.AUDIT_DATA/'source-manifest.json'))
                self.assertFalse(plan['formalEvaluationAllowed'])

    def test_audit_materials_are_stable_across_hash_seeds_and_cannot_overwrite_other_revision(self):
        import os
        for seed in ('0','9'):
            result=subprocess.run([sys.executable,str(trainer.BASE/'plan_training.py'),'--check-audit'],capture_output=True,text=True,timeout=20,
                env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1'})
            self.assertEqual(result.returncode,0,result.stderr)
        with tempfile.TemporaryDirectory() as d,mock.patch.object(trainer,'AUDIT_DATA',Path(d)):
            (Path(d)/'candidates.jsonl').write_text('unrelated data')
            with self.assertRaisesRegex(ValueError,'preserve delivered label audit'):trainer.label_audit_materials(write=True)

    def authorization(self):
        return trainer.run.read_json(trainer.ART/'m01-fitting'/f'{trainer.FIT_RUN}.authorization.json')

    def test_recorded_user_authorization_keeps_drafts_and_zero_human_reviews(self):
        auth=self.authorization();train,dev=trainer.authorized_draft_data(auth)
        self.assertEqual(len(train),6);self.assertEqual(len(dev),6)
        self.assertEqual(auth['humanLabelReviews'],0);self.assertFalse(auth['formalEvaluationAllowed'])
        self.assertTrue(all(not r['trainingEligible'] for r in train+dev))
        with self.assertRaises(ValueError):trainer.reviewed_data(auth)

    def test_authorization_cannot_expand_data_config_run_or_formal_claims(self):
        for key,value in (('runId','another-run'),('batchId',trainer.BATCH),('packetSha256','0'*64),
                          ('configSha256','0'*64),('humanLabelReviews',12),('formalEvaluationAllowed',True),
                          ('sourceRisksAcknowledged',[]),('trainGroups',[]),('userInstruction','')):
            auth=self.authorization();auth[key]=value
            with self.assertRaisesRegex(ValueError,'scope/data drift'):trainer.authorized_draft_data(auth)

    def test_explicit_authorization_plan_freezes_before_after_without_fabricated_review(self):
        auth=self.authorization()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'plan.json';receipt=Path(d)/'authorization.json';receipt.write_text(json.dumps(auth))
            with mock.patch.object(trainer.old,'paths',return_value=(path,Path(d)/'record.json')),mock.patch.object(trainer,'observe_m02',return_value={'allSixFilesFullyRehashedAndVerified':True}),mock.patch.object(trainer,'observe_environment',return_value={'registeredVersionsMatch':True}):
                trainer.training_plan(trainer.FIT_RUN,authorization_path=receipt);plan=json.loads(path.read_text());trainer.verify_training(plan)
                self.assertIsNone(plan['reviewClaims']);self.assertEqual(plan['humanLabelReviewedGroups'],0)
                self.assertIn('before_fit_and_after',plan['outputComparison'])
                bad=copy.deepcopy(plan);bad['humanLabelReviewedGroups']=12
                with self.assertRaisesRegex(ValueError,'fabricate'):trainer.verify_training(bad)

    def test_absent_or_wrong_run_authorization_refuses_before_dependencies_or_plan_write(self):
        with self.assertRaisesRegex(ValueError,'choose reviewed'):trainer.training_plan('none')
        path=trainer.ART/'m01-fitting'/f'{trainer.FIT_RUN}.authorization.json'
        with mock.patch.object(trainer,'observe_m02') as model,mock.patch.object(trainer.old,'paths') as paths:
            with self.assertRaisesRegex(ValueError,'another run'):trainer.training_plan('another-run',authorization_path=path)
            model.assert_not_called();paths.assert_not_called()

    def test_real_fit_archive_accounts_for_all_optimizer_steps_sources_and_first_outputs(self):
        s=trainer.observed_fit()
        self.assertEqual(s['trainingSteps'],80);self.assertEqual(s['generationAttempts'],24)
        self.assertEqual(s['generationsWithSavedOutputs'],24);self.assertTrue(s['realizerTrained'])
        self.assertEqual(sum(s['trainGroupExposures'].values()),160)
        self.assertEqual(s['modelForwardCounts']['encoderForwardCallsByPhase'],{'before_fit':12,'training':80,'after_fit':12})
        self.assertEqual(s['review']['reviewedGroups'],0);self.assertFalse(s['formalEvaluationAllowed'])
        self.assertFalse(s['semanticQualityApproved']);self.assertEqual(s['fullRequest500msStatus'],'unverified')
        for pair in s['comparisons']:
            self.assertEqual(pair['before_fit']['inputTokenIds'],pair['after_fit']['inputTokenIds'])

    def test_assistant_output_review_keeps_three_development_failures_and_punctuation_variants(self):
        s=trainer.fit_materials();counts=s['assistantQualityCounts']
        self.assertEqual(counts['after_fit']['train_candidate']['candidate_correct'],6)
        self.assertEqual(counts['after_fit']['development_candidate'],{'candidate_correct':3,'fail':3,'uncertain':0})
        failed={d['annotationId'] for d in s['assistantOutputReview']['decisions'] if d['phase']=='after_fit' and d['verdict']=='fail'}
        self.assertEqual(failed,{'realizer-new-04','realizer-new-08','realizer-new-10'})
        self.assertEqual(counts['before_fit']['development_candidate']['candidate_correct'],0)
        self.assertFalse(s['semanticQualityApproved'])

    def test_fit_training_source_or_saved_prediction_tampering_is_rejected(self):
        _,path=trainer.old.paths(trainer.FIT_RUN);original=trainer.run.read_json
        for mode in ('source','prediction'):
            record=original(path)
            if mode=='source':
                event=next(c for c in record['attempts'][0]['checkpoints'] if c['name']=='training_step_started')
                event['payload']['sourceGroups'][0]='d-realizer-new-source-02'
            else:record['attempts'][0]['predictions'][0]['raw']='invented corrected output'
            def read(p):return copy.deepcopy(record) if p==path else original(p)
            with mock.patch.object(trainer.run,'read_json',side_effect=read):
                with self.assertRaisesRegex(ValueError,'journal reconstruction'):trainer.observed_fit()

    def test_fit_report_is_stable_across_process_hash_seeds_without_running_model(self):
        import os
        for seed in ('0','9'):
            result=subprocess.run([sys.executable,str(trainer.BASE/'plan_training.py'),'--check-fit'],capture_output=True,text=True,timeout=20,
                env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1'})
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['trainingSteps'],80)

    def test_expansion_has_eighteen_groups_with_paired_variants_on_the_same_side(self):
        import realizer_expansion as x
        rows=x.new_rows();self.assertEqual(len(rows),36)
        self.assertEqual(len({r['sourceGroup'] for r in rows}),18)
        for group in {r['sourceGroup'] for r in rows}:
            siblings=[r for r in rows if r['sourceGroup']==group]
            self.assertEqual({r['variant'] for r in siblings},{'a','b'})
            self.assertEqual(len({r['role'] for r in siblings}),1)
            self.assertEqual(siblings[1]['sourceCase']['derivedFrom'],siblings[0]['annotationId'])
        for row in rows:
            self.assertFalse(row['trainingEligible']);self.assertFalse(trainer.contract.validate_candidate(row['sourceCase'],row['planDraft'])['semanticApproved'])

    def test_expansion_keeps_old_development_out_of_training_and_binds_current_authorization(self):
        import realizer_expansion as x
        auth=trainer.run.read_json(x.ART/'m01-fitting'/f'{x.RUN}.authorization.json')
        train,dev=trainer.authorized_draft_data(auth)
        self.assertEqual((len(train),len(dev)),(30,18))
        self.assertFalse(set(r['sourceGroup'] for r in train)&set(r['sourceGroup'] for r in dev))
        self.assertTrue(all(r['annotationId'] not in {a['annotationId'] for a in train} for r in trainer.audited_candidate_rows() if r['role']=='development_candidate'))
        profile=trainer.fit_profile(x.RUN)
        self.assertEqual(profile['baseline']['checkpoint'],trainer.observed_fit()['checkpoint'])
        self.assertEqual(profile['config']['steps'],80);self.assertTrue(profile['config']['allowGroupedExamples'])
        bad=copy.deepcopy(auth);bad['trainGroups'].append(dev[-1]['sourceGroup'])
        with self.assertRaises(ValueError):trainer.authorized_draft_data(bad)

    def test_expanded_complete_token_inputs_and_targets_fit_without_truncation(self):
        import realizer_expansion as x
        record=trainer.run.read_json(x.ART/'l3-18-expanded-tokenizer-check.json')
        self.assertEqual(record['packetSha256'],x.packet());self.assertEqual(len(record['examples']),48)
        self.assertEqual(record['neuralForwardCalls'],0);self.assertFalse(record['neuralModelLoaded'])
        self.assertLessEqual(record['maxInputTokens'],256);self.assertLessEqual(record['maxTargetTokens'],64)
        for row,encoded in zip(x.rows(),record['examples']):
            self.assertEqual(encoded['annotationId'],row['annotationId'])
            self.assertEqual(encoded['inputSha256'],trainer.digest(trainer.realizer_payload(row)))
            self.assertEqual(encoded['labels'][-1],1)

    def test_expanded_run_accounts_for_variants_baseline_reset_and_all_ninety_six_outputs(self):
        import realizer_expansion as x
        s=trainer.observed_fit(x.RUN)
        self.assertEqual((s['trainingSteps'],s['generationAttempts'],s['generationsWithSavedOutputs']),(80,96,96))
        self.assertEqual(s['modelForwardCounts']['encoderForwardCallsByPhase'],{'before_fit':48,'training':80,'after_fit':48})
        self.assertEqual(len(s['trainGroupExposures']),18);self.assertEqual(sum(s['trainGroupExposures'].values()),160)
        self.assertEqual(s['baselineAdapter']['checkpoint'],trainer.observed_fit()['checkpoint'])
        for p in s['comparisons']:self.assertEqual(p['before_fit']['inputTokenIds'],p['after_fit']['inputTokenIds'])
        self.assertFalse(s['formalEvaluationAllowed']);self.assertEqual(s['newIndependentTrainingGroups'],0)

    def test_expanded_report_preserves_regressions_uncertainty_and_group_denominator(self):
        import realizer_expansion as x
        s=trainer.fit_materials(run_id=x.RUN);counts=s['cohortQualityCounts']
        self.assertEqual(counts['after_fit']['old_development_regression']['candidate_correct'],3)
        self.assertEqual(counts['after_fit']['new_development'],{'candidate_correct':4,'fail':6,'uncertain':2})
        self.assertEqual(s['newDevelopmentGroupsAllVariantsCorrect'],{'before_fit':0,'after_fit':1})
        self.assertEqual(sum(counts['after_fit']['new_development'].values()),12)
        self.assertEqual(s['review']['missingReviews'],48)

    def test_expanded_report_is_deterministic_without_loading_models(self):
        import os
        for seed in ('0','9'):
            result=subprocess.run([sys.executable,str(trainer.BASE/'plan_training.py'),'--check-expanded'],capture_output=True,text=True,timeout=30,
                env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1'})
            self.assertEqual(result.returncode,0,result.stderr)

    def test_tokenization_retains_complete_separate_input_and_target(self):
        tokenizer=Tokenizer();row=self.rows[0]
        encoded=trainer.tokenize_example(tokenizer,row,{**trainer.CONFIG,'maxInputTokens':10000,'maxTargetTokens':10000})
        self.assertEqual([x[0] for x in tokenizer.calls],[trainer.input_text(row),row['expressionDraft']])
        self.assertTrue(all(x[1]=={'add_special_tokens':True,'truncation':False} for x in tokenizer.calls))
        self.assertEqual(encoded['labels'][-1],1);self.assertEqual(encoded['sourceGroup'],row['sourceGroup'])

    def test_source_target_overflow_and_missing_eos_fail_without_truncation(self):
        for key in ('maxInputTokens','maxTargetTokens'):
            config={**trainer.CONFIG,'maxInputTokens':10000,'maxTargetTokens':10000,key:2}
            with self.assertRaisesRegex(ValueError,'exceeds'):trainer.tokenize_example(Tokenizer(),self.rows[0],config)
        tok=Tokenizer();tok.eos_token_id=999
        with self.assertRaisesRegex(ValueError,'EOS'):trainer.tokenize_example(tok,self.rows[0],{**trainer.CONFIG,'maxInputTokens':10000,'maxTargetTokens':10000})

    def test_inspection_never_counts_as_project_training(self):
        result=trainer.observed_inspection();self.assertEqual(result['sourceModelForwardCalls'],0)
        self.assertEqual(result['sourceParameters'],77440384);self.assertEqual(result['adapterModules'],48)
        self.assertEqual(result['trainableAdapterParameters'],172032)
        self.assertEqual(result['totalInferenceParameters'],77612416)
        self.assertEqual(result['syntheticNumericCheck']['projectModelTrainingSteps'],0)

    def test_training_verify_rejects_scope_before_dependencies(self):
        with self.assertRaisesRegex(ValueError,'scope/config'):trainer.verify_training({'purpose':'unreviewed','config':{},'formalEvaluationAllowed':False})

    def test_current_materials_have_zero_eligible_labels_and_no_business_model_calls(self):
        summary,files=trainer.build_materials()
        self.assertEqual(summary['review']['missingReviews'],12);self.assertFalse(summary['review']['trainingDataReady'])
        self.assertEqual(summary['trainingSteps'],0);self.assertEqual(summary['businessInferenceCalls'],0)
        self.assertFalse(summary['plannerModelImplemented']);self.assertFalse(summary['realizerTrained'])
        self.assertTrue(summary['realizerTrainerImplemented']);self.assertEqual(len(files),4)

    def test_original_candidate_materials_remain_exact_after_trainer_extension(self):
        _,files=trainer.build_materials()
        for path,raw in files.items():self.assertEqual(path.read_bytes(),raw,str(path))

    def test_smoke_plan_freezes_only_two_numeric_fixtures_and_no_business_labels(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'plan.json'
            with mock.patch.object(trainer.old,'paths',return_value=(path,Path(d)/'record.json')),mock.patch.object(trainer,'observe_m02',return_value={'allSixFilesFullyRehashedAndVerified':True}),mock.patch.object(trainer,'observe_environment',return_value={'registeredVersionsMatch':True}):
                trainer.inspection_plan('unit-fixture',smoke=True);plan=json.loads(path.read_text())
                trainer.verify_inspection(plan)
        self.assertEqual(plan['syntheticExamples'],list(trainer.SYNTHETIC_EXAMPLES));self.assertEqual(plan['config']['steps'],2)
        self.assertEqual(plan['businessSourceGroups'],0);self.assertEqual(plan['businessTrainingSteps'],0)
        self.assertEqual(plan['businessInferenceCalls'],0);self.assertNotIn('reviewClaims',plan)

    def test_changed_synthetic_tokens_or_business_counts_fail_before_model_verification(self):
        plan={'purpose':'real_m02_synthetic_training_save_reload_only','config':trainer.SMOKE_CONFIG,
              'formalEvaluationAllowed':False,'protocolSha256':trainer.sha256_file(trainer.SMOKE_PROTOCOL),
              'syntheticExamples':copy.deepcopy(list(trainer.SYNTHETIC_EXAMPLES)),'syntheticExamplesSha256':trainer.digest(list(trainer.SYNTHETIC_EXAMPLES)),
              'syntheticOptimizerSteps':2,'businessSourceGroups':0,'businessTrainingSteps':0,'businessInferenceCalls':0,
              'adapterScope':'disposable_synthetic_fixture_never_business_inference','schema':'jity-d-realizer-smoke-plan-v1',
              'arms':['smoke'],'cases':[{'caseId':'m02-synthetic-training-smoke'}]}
        for key,value in (('businessTrainingSteps',1),('businessInferenceCalls',1),('arms',['fit']),('syntheticOptimizerSteps',80)):
            bad=copy.deepcopy(plan);bad[key]=value
            with mock.patch.object(trainer,'observe_m02') as model:
                with self.assertRaisesRegex(ValueError,'scope drift'):trainer.verify_inspection(bad)
                model.assert_not_called()
        bad=copy.deepcopy(plan);bad['syntheticExamples'][0]['labels'][0]=999
        with self.assertRaisesRegex(ValueError,'scope drift'):trainer.verify_inspection(bad)

    def test_missing_historical_source_is_not_silently_accepted(self):
        with mock.patch.object(trainer.subprocess,'check_output',return_value=''):
            with self.assertRaisesRegex(ValueError,'unavailable'):trainer.verify_historical_file(trainer.BASE/'does-not-exist.py','0'*64)

    def test_smoke_entry_uses_same_supervised_path_without_review_export(self):
        import experiment
        from contextlib import redirect_stdout
        import io
        with mock.patch.object(trainer,'inspection_plan',return_value=Path('/tmp/unit.json')) as prepare,redirect_stdout(io.StringIO()):
            self.assertEqual(experiment.main(['train-smoke','--prepare','unit-only']),0)
            prepare.assert_called_once_with('unit-only',smoke=True)
        with mock.patch.object(trainer,'execute_inspection',return_value=3) as execute:
            self.assertEqual(experiment.main(['train-smoke','--execute','unit.json']),3)
            execute.assert_called_once_with(Path('unit.json'))

    def test_real_smoke_archive_reconstructs_every_forward_and_never_becomes_business_training(self):
        summary=trainer.observed_smoke();check=summary['realModelSyntheticCheck']
        self.assertEqual(check['syntheticOptimizerSteps'],2)
        self.assertEqual(sum(summary['forwardPhaseCounts'].values()),check['modelTopForwardCalls'])
        self.assertEqual(summary['businessTrainingSteps'],0);self.assertEqual(summary['businessInferenceCalls'],0)
        self.assertFalse(summary['realizerTrained']);self.assertFalse(summary['semanticQualityApproved'])
        self.assertEqual(summary['fullRequest500msStatus'],'unverified')
        self.assertEqual(summary['review']['missingReviews'],12)

    def test_synthetic_step_count_and_semantic_claim_tampering_are_rejected(self):
        _,path=trainer.old.paths(trainer.SMOKE_RUN);original=trainer.run.read_json
        for mode in ('steps','semantic'):
            record=original(path)
            if mode=='steps':record['syntheticOptimizerSteps']=1
            else:record['attempts'][0]['syntheticFullModelCheck']['semanticQualityApproved']=True
            def read(p):return copy.deepcopy(record) if p==path else original(p)
            with mock.patch.object(trainer.run,'read_json',side_effect=read):
                with self.assertRaises(ValueError):trainer.observed_smoke()

    def test_rendered_smoke_materials_are_identical_across_process_hash_seeds(self):
        import os
        for seed in ('0','9'):
            result=subprocess.run([sys.executable,str(trainer.BASE/'plan_training.py'),'--check-smoke'],
                capture_output=True,text=True,timeout=20,env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1'})
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['businessTrainingSteps'],0)


class NumericImplementationTests(unittest.TestCase):
    def test_expression_generation_never_reads_target_and_logs_phase_tokens_and_stopping(self):
        python=trainer.ROOT/'.local/world-components-logic/venv/bin/python'
        code=r'''
import sys,json
sys.path.insert(0,sys.argv[1])
import torch
import plan_training as t
torch.set_num_threads(1)
class Tokenizer:
 eos_token_id=1
 def encode(self,text,**kw):assert kw=={'add_special_tokens':True,'truncation':False};return [3,4,1]
 def decode(self,tokens,**kw):return 'numeric fixture output'
class Numeric(torch.nn.Module):
 def forward(self,input_ids):return input_ids
 def generate(self,input_ids,**kw):self(input_ids);return torch.tensor([[0,8,1]])
row=t.audited_candidate_rows()[0];row['expressionDraft']=object()
events=[];result=t.generate_expressions(torch,Numeric(),Tokenizer(),[row],'before_fit',lambda n,p:events.append((n,p)))
assert result[0]['eos'] and result[0]['stopStatus']=='eos' and result[0]['modelTopForwardCalls']==1
assert result[0]['phase']=='before_fit' and result[0]['inputTokenIds']==[3,4,1]
assert [n for n,p in events]==['generation_started','generation_output','generation_timing']
assert result[0]['elapsedIncludingOutputJournalMs']>=result[0]['elapsedMs']
print(json.dumps({'targetNeverRead':True,'phaseAndRawTokensSaved':True,'pretrainedModelUsed':False}))
'''
        result=subprocess.run([str(python),'-c',code,str(BASE)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['targetNeverRead'])

    def test_complete_t5_forward_backward_disk_reload_and_token_equivalence_on_random_tiny_model(self):
        # Random tiny T5, not the pretrained M02 and not a business source.
        python=trainer.ROOT/'.local/world-components-logic/venv/bin/python'
        code=r'''
import sys,tempfile,json
from pathlib import Path
from unittest import mock
sys.path.insert(0,sys.argv[1])
import torch
from transformers import T5Config,T5ForConditionalGeneration
import plan_training as t
torch.set_num_threads(1);torch.manual_seed(42)
model=T5ForConditionalGeneration(T5Config(vocab_size=64,d_model=8,d_kv=4,d_ff=16,num_layers=8,num_decoder_layers=8,num_heads=2,dropout_rate=0.,decoder_start_token_id=0,eos_token_id=1,pad_token_id=0)).eval()
events=[]
with tempfile.TemporaryDirectory() as directory,mock.patch.object(t,'ROOT',Path(directory)):
 result=t.real_model_smoke(torch,model,{'runId':'unit-tiny','syntheticExamples':list(t.SYNTHETIC_EXAMPLES),'config':t.SMOKE_CONFIG},lambda n,p:events.append((n,p.copy())))
 path=Path(directory)/result['checkpoint']['path']
 assert path.exists() and t.sha256_file(path)==result['checkpoint']['sha256']
 state=torch.load(path,weights_only=True)
 assert len(state)==96 and all(n.endswith(('.lora_A','.lora_B')) for n in state)
 with torch.no_grad():
  for p in model.parameters():
   if p.requires_grad:p.zero_()
 before=t.old.tensor_hash(t.adapter_state(model))
 try:t.save_reload_adapter(torch,model,path.parent,result['checkpoint']['sourceTensorSha256'],lambda *_:None);raise AssertionError('overwrote checkpoint')
 except FileExistsError:pass
 assert t.old.tensor_hash(t.adapter_state(model))==before
assert result['sourceParameters']<100000 and result['adapterModules']==48 and result['syntheticOptimizerSteps']==2
assert result['sourceBaseUnchanged'] and result['reloadedLogitsExact'] and result['reloadedGeneratedTokensExact']
assert sum(n=='training_step_started' for n,p in events)==2 and sum(n=='training_step_settled' for n,p in events)==2
assert sum(n=='model_forward_started' for n,p in events)==result['modelTopForwardCalls']
assert sum(n=='model_forward_settled' for n,p in events)==result['modelTopForwardCalls']
assert result['businessTrainingSteps']==0 and result['businessInferenceCalls']==0
print(json.dumps({'fullTinyT5SmokePassed':True,'syntheticOptimizerSteps':2,'pretrainedModelUsed':False}))
'''
        result=subprocess.run([str(python),'-c',code,str(BASE)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['fullTinyT5SmokePassed'])

    def test_actual_autograd_freeze_padding_fit_loop_and_checkpoint_reload(self):
        # Uses a tiny numeric module, not M02 or any business scenario/label.
        python=trainer.ROOT/'.local/world-components-logic/venv/bin/python'
        code=r'''
import sys,json,types
sys.path.insert(0,sys.argv[1])
import torch
from unittest import mock
import plan_training as t
torch.set_num_threads(1)
check=t.synthetic_gradient_check(torch)
class Toy(torch.nn.Module):
 def __init__(self):
  super().__init__();self.embedding=torch.nn.Embedding(10,8)
  for p in self.embedding.parameters():p.requires_grad_(False)
  self.output=t.lora_linear(torch,torch.nn.Linear(8,10),2,4)
 def forward(self,input_ids,attention_mask,labels):
  x=(self.embedding(input_ids)*attention_mask.unsqueeze(-1)).sum(1)/attention_mask.sum(1,keepdim=True)
  logits=self.output(x).unsqueeze(1).expand(-1,labels.shape[1],-1)
  return types.SimpleNamespace(loss=torch.nn.functional.cross_entropy(logits.reshape(-1,10),labels.reshape(-1),ignore_index=-100))
model=Toy();before=t.old.tensor_hash(t.base_state(model))
rows=[{'sourceGroup':'synthetic-a'},{'sourceGroup':'synthetic-b'}];events=[]
def tokens(tok,row,config):return {'inputIds':[2,3] if row['sourceGroup'].endswith('a') else [4], 'labels':[5,1], 'sourceGroup':row['sourceGroup']}
with mock.patch.object(t,'tokenize_example',side_effect=tokens):
 loss=t.fit_adapter(torch,model,types.SimpleNamespace(pad_token_id=0),rows,{**t.CONFIG,'steps':3},lambda n,p:events.append((n,p)))
assert len(loss)==3 and len(events)==6 and before==t.old.tensor_hash(t.base_state(model))
batch=t.collate(torch,[{'inputIds':[2,3],'labels':[5,1]},{'inputIds':[4],'labels':[1]}],0)
assert batch['labels'].tolist()==[[5,1],[1,-100]] and batch['attention_mask'].tolist()==[[1,1],[1,0]]
s=t.adapter_state(model);wrong=dict(s);wrong.pop(next(iter(wrong)))
try:t.restore_adapter(model,wrong);raise AssertionError('missing state accepted')
except ValueError:pass
print(json.dumps({'numeric':check,'syntheticFitLoopSteps':len(loss),'paddingAndMaskVerified':True,'baseFrozen':True,'businessModelUsed':False}))
'''
        r=subprocess.run([str(python),'-c',code,str(BASE)],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr);result=json.loads(r.stdout)
        self.assertTrue(result['numeric']['checkpointReloadExact']);self.assertEqual(result['syntheticFitLoopSteps'],3)
        self.assertTrue(result['baseFrozen']);self.assertFalse(result['businessModelUsed'])

if __name__=='__main__':unittest.main()
