"""Projection/coverage, frozen identity and whole-expression cost boundaries."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import realizer_steps as s


class StepProjectionTests(unittest.TestCase):
    def test_all_eighteen_development_cases_and_every_step_are_retained(self):
        data=s.rows();self.assertEqual(len(data),18)
        self.assertTrue(all(r['role']=='development_candidate' for r in data))
        self.assertEqual(sum(len(r['planDraft']['steps'])>1 for r in data),5)
        self.assertEqual(sum(len(s.project(r,'steps')) for r in data),23)
        for row in data:
            before=copy.deepcopy(row);projected=s.project(row,'steps')
            self.assertEqual(row,before)
            self.assertEqual([p['planDraft']['steps'][0] for p in projected],row['planDraft']['steps'])
            for p in projected:
                self.assertEqual(p['sourceCase'],row['sourceCase'])
                self.assertEqual(p['planDraft']['actorId'],row['planDraft']['actorId'])
                self.assertEqual(p['sourceGroup'],row['sourceGroup'])
                self.assertFalse(s.t.contract.validate_candidate(p['sourceCase'],p['planDraft'])['semanticApproved'])

    def test_single_step_controls_have_exact_same_model_input(self):
        controls=[r for r in s.rows() if len(r['planDraft']['steps'])==1]
        self.assertEqual(len(controls),13)
        for row in controls:self.assertEqual(s.t.input_text(s.project(row,'whole')[0]),s.t.input_text(s.project(row,'steps')[0]))

    def test_reference_wording_never_enters_projected_inputs(self):
        for row in s.rows():
            other=copy.deepcopy(row);other['expressionDraft']='unrelated hidden target never sent to model'
            self.assertEqual([s.t.input_text(p) for p in s.project(row,'steps')],[s.t.input_text(p) for p in s.project(other,'steps')])

    def test_assembly_retains_original_text_bytes_and_refuses_missing_order(self):
        parts=[{'partIndex':1,'raw':'  原文一。\r'},{'partIndex':2,'raw':'原文二！  '}]
        self.assertEqual(s.assemble(parts),'  原文一。\r\n原文二！  ')
        with self.assertRaises(ValueError):s.assemble(parts[::-1])
        with self.assertRaises(ValueError):s.assemble([])

    def test_unknown_reference_or_actor_is_not_silently_repaired(self):
        row=copy.deepcopy(s.rows()[0]);row['planDraft']['actorId']='unknown'
        with self.assertRaises(ValueError):s.project(row,'steps')
        row=copy.deepcopy(s.rows()[0]);row['planDraft']['steps'][0]['objects']=[{'kind':'item','id':'unknown'}]
        with self.assertRaises(ValueError):s.project(row,'steps')

    def test_prepare_freezes_all_attempts_without_loading_model(self):
        adapter=s.identity()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'plan.json'
            with mock.patch.object(s.t.old,'paths',return_value=(path,Path(directory)/'record.json')),mock.patch.object(s,'identity',return_value=adapter),mock.patch.object(s.t,'observe_m02',return_value={'model':'metadata'}),mock.patch.object(s.t,'observe_environment',return_value={'venv':'metadata'}):
                s.prepare(s.RUN);plan=json.loads(path.read_text())
        slots=s.t.run.planned_slots(plan,s.ARMS)
        self.assertEqual(len(slots),108);self.assertEqual(plan['trainingSteps'],0)
        self.assertFalse(plan['formalEvaluationAllowed']);self.assertEqual(plan['config']['steps'],0)
        self.assertEqual([a['arm'] for a in slots[:2]],['whole','steps'])
        self.assertEqual([a['arm'] for a in slots[36:38]],['steps','whole'])

    def test_changed_scope_rejected_before_model_verification(self):
        plan={'runId':s.RUN,'config':{},'arms':list(s.ARMS),'trainingSteps':0,'formalEvaluationAllowed':False}
        with mock.patch.object(s.t,'observe_m02') as model:
            with self.assertRaisesRegex(ValueError,'scope drift'):s.verify(plan)
            model.assert_not_called()

    def test_real_record_retains_every_call_and_identical_single_step_controls(self):
        report=s.observed()
        self.assertEqual((report['attemptCount'],report['generationCalls'],report['trainingSteps']),(108,123,0))
        self.assertEqual(len(report['singleStepControls']),13)
        self.assertEqual(len({(a['arm'],a['caseId'],a['repeat']) for a in report['attempts']}),108)
        self.assertTrue(all(a['outputComplete'] for a in report['attempts']))
        for a in report['attempts']:
            self.assertGreaterEqual(a['elapsedIncludingTelemetryMs'],a['elapsedThroughResultMs'])
            self.assertGreaterEqual(a['elapsedThroughResultMs'],sum(p['elapsedMs'] for p in a['parts']))
        self.assertFalse(report['semanticQualityApproved']);self.assertFalse(report['formalEvaluationAllowed'])

    def test_negative_result_and_regression_remain_in_report(self):
        report=s.materials()
        self.assertEqual(report['multiStepQuality']['whole']['candidate_correct'],1)
        self.assertEqual(report['multiStepQuality']['steps'],{'candidate_correct':0,'fail':5,'uncertain':0})
        self.assertEqual(report['qualityCounts']['steps']['new_development'],{'candidate_correct':3,'fail':7,'uncertain':2})
        self.assertTrue(all(p[a]['allThreeOutputsIdentical'] for p in report['comparisons'] for a in s.ARMS))

    def test_changed_snapshot_text_or_cost_is_not_silently_accepted(self):
        _,path=s.t.old.paths(s.RUN);original=s.t.run.read_json
        for key,value in (('combinedRaw','invented good answer'),('elapsedIncludingTelemetryMs',0.)):
            record=original(path);record['attempts'][0][key]=value
            def read(p):return copy.deepcopy(record) if p==path else original(p)
            with mock.patch.object(s.t.run,'read_json',side_effect=read):
                with self.assertRaises(ValueError):s.observed()

    def test_report_is_stable_across_process_hash_seeds_without_model_load(self):
        import os,subprocess
        for seed in ('0','9'):
            result=subprocess.run([sys.executable,str(BASE/'realizer_steps.py'),'--check'],capture_output=True,text=True,timeout=30,
                env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1'})
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
