"""Current registry boundaries only: no model import, training, or inference."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import experiment
import short_experiment as run


class ActiveSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name)
        self.dataset=self.directory/'current.jsonl.gz';self.dataset.write_bytes(b'explicit engineering dataset bytes')
        self.model=self.directory/'qwen.model.json'
        self.model.write_text(json.dumps({'training':{'steps':32,'optimizerCumulativeSteps':144},
                                       'trainedComponents':['D08.1.amount']}))
        self.selection={'schema':'jity-short-active-selection-v1','references':{
            'dataset':{'path':str(self.dataset),'sha256':run.sha256_file(self.dataset)},
            'trainedQwen':{'path':str(self.model),'sha256':run.sha256_file(self.model)}},
            'browserProvider':None}
        self.patch=patch.object(run,'active_selection',side_effect=lambda:copy.deepcopy(self.selection))
        self.patch.start();self.addCleanup(self.patch.stop)

    def test_active_default_rejects_different_bytes_at_same_path(self):
        self.assertEqual(run.active_data_path(),self.dataset)
        self.dataset.write_bytes(b'different otherwise plausible packet')
        with self.assertRaisesRegex(ValueError,'active_reference_identity_mismatch:dataset'):
            run.active_data_path()

    def test_missing_active_data_never_falls_back_to_historical_data(self):
        self.dataset.unlink()
        with self.assertRaisesRegex(ValueError,'active_reference_identity_mismatch:dataset'):
            run.active_data_path()

    def test_status_does_not_read_training_or_data_after_identity_mismatch(self):
        for name,path in [('dataset',self.dataset),('trainedQwen',self.model)]:
            with self.subTest(name=name):
                original=path.read_bytes();path.write_bytes(b'changed')
                with patch.object(run,'load_rows') as load,patch.object(run.common,'read_json') as read:
                    with self.assertRaisesRegex(ValueError,'active_reference_identity_mismatch:'+name):
                        run.active_status()
                    load.assert_not_called();read.assert_not_called()
                path.write_bytes(original)

    def test_current_status_is_metadata_only_and_never_grants_quality(self):
        with patch.object(run,'load_rows',return_value=[]) as load,patch.object(run,'validate_rows',return_value={'engineeringFixture':True}),patch.object(run,'audit_resources',side_effect=AssertionError('historical model audit must not run')),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run.active_status(),0)
        value=json.loads(output.getvalue());load.assert_called_once_with(self.dataset)
        self.assertEqual(value['naturalLanguageBackend']['selected'],'Qwen3-0.6B')
        self.assertEqual(value['naturalLanguageBackend']['randeng'],'retired_no_fallback')
        self.assertEqual(value['statusCommandModelExecutions'],0)
        self.assertEqual(value['realQwenTraining']['optimizerCumulativeSteps'],144)
        self.assertFalse(value['realQwenTraining']['semanticQualityApproved'])
        self.assertEqual(value['formalQuality'],'not_approved')
        self.assertIn('qualified_browser_provider_not_selected',value['candidateAudit']['blockers'])

    def test_audit_reports_drift_and_missing_browser_without_model_calls(self):
        self.model.write_text('{}')
        value=run.active_audit()
        self.assertIn('missing_or_changed_reference:trainedQwen',value['blockers'])
        self.assertIn('qualified_browser_provider_not_selected',value['blockers'])
        self.assertFalse(value['references']['trainedQwen']['identityMatches'])
        self.assertFalse(value['semanticQualityApproved']);self.assertEqual(value['modelCalls'],0)


class ActiveCliTests(unittest.TestCase):
    def test_prepare_defaults_use_active_data_and_explicit_override_wins(self):
        import short_qwen_training,short_encoder_repair,short_evaluation
        cases=[(['short-prepare','fixture'],run),
               (['short-qwen-prepare','fixture','--model-manifest','model.json'],short_qwen_training),
               (['short-encoder-focus-prepare','fixture','--source-provider','provider.json'],short_encoder_repair),
               (['short-eval-prepare','fixture','--provider','provider.json'],short_evaluation)]
        for args,module in cases:
            for explicit in (False,True):
                with self.subTest(command=args[0],explicit=explicit):
                    active=Path('/fixture/current.jsonl.gz');chosen=Path('/fixture/override.jsonl.gz') if explicit else active
                    with patch.object(run,'active_data_path',return_value=active) as lookup,patch.object(module,'freeze',return_value=Path('/fixture/new.plan.json')) as freeze,contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(experiment.main(args+(['--dataset',str(chosen)] if explicit else [])),0)
                    self.assertEqual(freeze.call_args.kwargs['dataset'],chosen)
                    if explicit:lookup.assert_not_called()
                    else:lookup.assert_called_once_with()

    def test_short_data_uses_active_packet(self):
        active=Path('/fixture/current.jsonl.gz')
        with patch.object(run,'active_data_path',return_value=active),patch.object(run,'load_rows',return_value=[]) as load,patch.object(run,'validate_rows',return_value={'engineeringFixture':True}),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(experiment.main(['short-data']),0)
        load.assert_called_once_with(active)

    def test_historical_audit_requires_explicit_flag(self):
        with patch.object(run,'active_audit',return_value={'modelCalls':0}) as active,patch.object(run,'audit_resources',return_value={'modelCalls':0}) as old,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(experiment.main(['short-audit']),0)
            active.assert_called_once_with();old.assert_not_called()
            with self.assertRaisesRegex(ValueError,'requires --historical'):
                experiment.main(['short-audit','--model-root','/old'])
            self.assertEqual(experiment.main(['short-audit','--historical','--model-root','/old']),0)
            old.assert_called_once_with(Path('/old'))

    def test_historical_load_rows_default_is_preserved(self):
        self.assertEqual(run.load_rows.__defaults__,(run.DATA/'supervision.jsonl.gz',))


if __name__=='__main__':unittest.main()
