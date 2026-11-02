"""Inference identity tests on local metadata only; no model execution."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import m01_infer as infer
from run_pilot import digest


class InferenceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.fit_record=infer.read_record(infer.ART/'m01-fit-dev42-20261102-r1.record.json.gz')
        original=json.loads((infer.ART/'m01-fit-dev42-20261102-r1.plan.json').read_text())
        checkpoint=infer.ROOT/self.fit_record['checkpoint']['path'];real_sha=infer.sha256_file
        self.patches=[mock.patch.object(infer.fit,'model_identity',return_value=original['model']),
                      mock.patch.object(infer,'observe_environment',return_value=original['environment']),
                      mock.patch.object(infer,'sha256_file',side_effect=lambda p:self.fit_record['checkpoint']['sha256'] if Path(p)==checkpoint else real_sha(p))]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()

    def plan(self):
        fit_record=infer.ART/'m01-fit-dev42-20261102-r1.record.json.gz'
        with tempfile.TemporaryDirectory() as tmp:
            plan=Path(tmp)/'new.plan.json';record=Path(tmp)/'new.record.json';captured=[]
            with mock.patch.object(infer.fit,'paths',return_value=(plan,record)),mock.patch.object(infer,'exclusive',side_effect=lambda p,v:captured.append(v)):
                infer.prepare('qa-only',fit_record)
        return captured[0]

    def test_fixed_checkpoint_and_retained_cases_match_completed_fit(self):
        p=self.plan();infer.verify(p)
        self.assertEqual(len(p['cases']),4)
        self.assertFalse(p['config']['trainingPerformed'])
        self.assertFalse(p['config']['featureCacheForTiming'])
        self.assertFalse(p['formalEvaluationAllowed'])

    def test_fit_cases_cannot_be_substituted_for_retained_development(self):
        p=self.plan();rows,_=infer.fit.dataset();p['cases']=[r['case'] for r in rows if r['role']=='fit'][:4]
        with self.assertRaisesRegex(ValueError,'retained-case'):infer.verify(p)

    def test_rehashed_config_cannot_change_caps_or_enable_feature_cache(self):
        p=self.plan()
        for k,v in {'maxResidentMiB':4096,'processWallSeconds':3600,'featureCacheForTiming':True,'threshold':.1}.items():
            bad=copy.deepcopy(p);bad['config'][k]=v;bad['configSha256']=digest(bad['config'])
            with self.assertRaisesRegex(ValueError,'policy'):infer.verify(bad)

    def test_fit_plan_and_checkpoint_claims_are_rechecked(self):
        p=self.plan();p['fitPlanSha256']='0'*64
        with self.assertRaisesRegex(ValueError,'fit plan'):infer.verify(p)
        p=self.plan();p['trainedHeadSha256']['D02']='0'*64
        with self.assertRaisesRegex(ValueError,'checkpoint'):infer.verify(p)


if __name__=='__main__':unittest.main()
