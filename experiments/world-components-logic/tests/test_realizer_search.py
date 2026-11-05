"""Finite search, grouped validation and gradient isolation; no business models."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import realizer_search as search


class GridTests(unittest.TestCase):
    def test_cartesian_grid_has_eighteen_points_including_original_configuration(self):
        points=[(e['config']['learningRate'],e['config']['weightDecay'],step) for e in search.catalog() for step in search.STEPS]
        self.assertEqual(len(points),18);self.assertEqual(len(set(points)),18)
        self.assertIn((.001,.01,320),points)
        for entry in search.catalog():
            self.assertEqual(entry['config']['seed'],42);self.assertEqual(entry['config']['rank'],4)
            self.assertEqual(entry['config']['threads'],1);self.assertEqual(entry['config']['processWallSeconds'],120)

    def test_train_and_tuning_groups_are_separate_and_old_failed_dev_never_trains(self):
        train,dev=search.data()
        self.assertEqual((len(train),len(dev)),(30,18))
        self.assertFalse({r['sourceGroup'] for r in train}&{r['sourceGroup'] for r in dev})
        self.assertNotIn('realizer-new-04',{r['annotationId'] for r in train})
        self.assertFalse(any(r['trainingEligible'] for r in train+dev))

    def test_group_macro_average_does_not_double_weight_paired_variants_or_long_text(self):
        entries=[{'role':role,'sourceGroup':g,'meanTokenNll':v,'targetTokens':n}
            for role in ('train_candidate','development_candidate') for g,v,n in (('one',1.,10),('one',3.,30),('two',8.,10))]
        metrics=search.aggregate_loss(entries)['development_candidate']
        self.assertEqual(metrics['groupMacroNll'],5.)
        self.assertEqual(metrics['exampleMeanNll'],4.)
        self.assertEqual(metrics['tokenWeightedNll'],3.6)
        entries[0]['meanTokenNll']=float('nan')
        with self.assertRaisesRegex(ValueError,'invalid probe loss'):search.aggregate_loss(entries)

    def test_selection_prefers_complete_groups_then_examples_before_low_loss(self):
        base={'allVariantsCorrectGroups':5,'correctExamples':10,'developmentGroupMacroNll':.01,
            'config':{'steps':320,'learningRate':.001,'weightDecay':.01}}
        more_groups={**base,'allVariantsCorrectGroups':6,'correctExamples':9,'developmentGroupMacroNll':9.}
        more_examples={**base,'correctExamples':11,'developmentGroupMacroNll':9.}
        self.assertLess(search.ranking(more_groups),search.ranking(more_examples))
        self.assertLess(search.ranking(more_examples),search.ranking(base))
        earlier=copy.deepcopy(base);earlier['config']['steps']=80
        self.assertLess(search.ranking(earlier),search.ranking(base))

    def test_seed_confirmation_is_locked_and_deduplicates_unchanged_winner(self):
        original={**search.t.CONFIG,'allowGroupedExamples':True,'steps':320}
        entries=search.confirmation_entries({'selected':{'config':original}})
        self.assertEqual(len(entries),1);self.assertEqual(entries[0]['config']['seed'],7)
        changed={**original,'learningRate':.0003,'steps':160}
        entries=search.confirmation_entries({'selected':{'config':changed}})
        self.assertEqual(len(entries),2)
        self.assertEqual(entries[1]['config'],{**original,'seed':7})

    def test_search_plan_refuses_changed_grid_before_model_observation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with mock.patch.object(search,'MANIFEST',root/'manifest.json'),mock.patch.object(search.t.old,'paths',side_effect=lambda r:(root/(r+'.plan.json'),root/(r+'.record.json'))),mock.patch.object(search.t,'observe_m02',return_value={'allSixFilesFullyRehashedAndVerified':True}) as model,mock.patch.object(search.t,'observe_environment',return_value={'registeredVersionsMatch':True}):
                search.prepare();plan=search.t.run.read_json(root/(search.catalog()[0]['runId']+'.plan.json'))
                self.assertEqual(plan['environment'],{'registeredVersionsMatch':True})
                search.verify(plan);plan['config']['learningRate']=.5;model.reset_mock()
                with self.assertRaisesRegex(ValueError,'unregistered grid trajectory'):search.verify(plan)
                model.assert_not_called()

    def test_supervisor_environment_cannot_be_removed_from_frozen_plan(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with mock.patch.object(search,'MANIFEST',root/'manifest.json'),mock.patch.object(search.t.old,'paths',side_effect=lambda r:(root/(r+'.plan.json'),root/(r+'.record.json'))),mock.patch.object(search.t,'observe_m02',return_value={'allSixFilesFullyRehashedAndVerified':True}) as model,mock.patch.object(search.t,'observe_environment',return_value={'registeredVersionsMatch':True,'venvExecutableRelativePath':'fixture-only'}):
                search.prepare();plan=search.t.run.read_json(root/(search.catalog()[0]['runId']+'.plan.json'));del plan['environment'];model.reset_mock()
                with self.assertRaisesRegex(ValueError,'manifest/environment/scope'):search.verify(plan)
                model.assert_not_called()

    def test_own_record_archival_preserves_uncompressed_identity_and_other_archives(self):
        import gzip
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'record.json';path.write_bytes(b'{"fixture":true}\n');before=search.raw_sha(path)
            search.archive_file(path);packed=path.with_suffix('.json.gz')
            self.assertFalse(path.exists());self.assertEqual(search.raw_sha(packed),before)
            self.assertEqual(gzip.decompress(packed.read_bytes()),b'{"fixture":true}\n')
            path.write_bytes(b'different')
            with self.assertRaisesRegex(ValueError,'preserve unrelated archive'):search.archive_file(path)

    def test_every_unique_development_output_needs_its_own_bound_review(self):
        predictions=[{'annotationId':'a','raw':'text','role':'development_candidate'}]
        cell={'predictions':predictions};digest=search.t.digest('text')
        review={'schema':'jity-d-realizer-grid-assistant-review-v1','reviewer':'assistant',
            'formalEvaluationAllowed':False,'recordHashes':{'run':'hash'},'decisions':[]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'review.json';p.write_text(json.dumps(review))
            with self.assertRaisesRegex(ValueError,'not fully reviewed'):search.reviews([cell],p,{'run':'hash'})
            review['decisions']=[{'annotationId':'a','rawOutputSha256':digest,'verdict':'fail','reason':'fixture'}];p.write_text(json.dumps(review))
            self.assertEqual(len(search.reviews([cell,cell],p,{'run':'hash'})),1)
            with self.assertRaisesRegex(ValueError,'scope/record'):search.reviews([cell],p,{'run':'changed'})


class NumericValidationTests(unittest.TestCase):
    def test_loss_probe_has_no_gradients_parameter_changes_or_rng_consumption(self):
        import torch
        torch.set_num_threads(1)
        class Tiny(torch.nn.Module):
            def __init__(self):super().__init__();self.weight=torch.nn.Parameter(torch.tensor(.5));self.grad_modes=[]
            def forward(self,input_ids,attention_mask,labels):
                self.grad_modes.append(torch.is_grad_enabled())
                return SimpleNamespace(loss=(self.weight*input_ids.float().mean()-labels[labels!=-100].float().mean())**2)
        rows=[{'annotationId':str(i),'sourceGroup':str(i),'role':role} for i,role in enumerate(('train_candidate','development_candidate'))]
        encoded=[{'inputIds':[2,3,1],'labels':[4,1],'sourceGroup':str(i),'annotationId':str(i),'inputSha256':'input','targetSha256':'target'} for i in range(2)]
        model=Tiny();before=model.weight.detach().clone();rng=torch.get_rng_state().clone();events=[]
        probe=search.evaluate_loss(torch,model,encoded,rows,0,0,lambda n,p:events.append((n,p)))
        self.assertEqual(model.grad_modes,[False,False]);self.assertIsNone(model.weight.grad)
        self.assertTrue(torch.equal(before,model.weight));self.assertTrue(torch.equal(rng,torch.get_rng_state()))
        self.assertEqual(probe['metrics']['development_candidate']['examples'],1)
        # Same one optimizer path, with and without validation callbacks.
        control=Tiny();config={**search.t.CONFIG,'steps':8,'allowGroupedExamples':True}
        reference=search.t.fit_encoded_adapter(torch,control,encoded,0,config,lambda *_:None)
        def callback(name,payload):
            if name=='training_step_settled' and payload['step'] in (2,4,8):search.evaluate_loss(torch,model,encoded,rows,0,payload['step'],lambda *_:None)
        actual=search.t.fit_encoded_adapter(torch,model,encoded,0,config,callback)
        self.assertEqual(reference,actual);self.assertTrue(torch.equal(control.weight,model.weight))


if __name__=='__main__':unittest.main()
