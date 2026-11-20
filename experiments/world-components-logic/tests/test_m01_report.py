"""Read-only summary checks on preserved records, no models or local weights."""
from pathlib import Path
import copy
import json
import sys
import unittest
from unittest import mock

BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
import m01_report as report


class M01ReportTests(unittest.TestCase):
    def test_fit_and_retained_observations_stay_separate(self):
        result,_=report.build()
        self.assertEqual(result['qualityObservations']['D02']['fit']['sourceGroups'],8)
        self.assertEqual(result['qualityObservations']['D02']['retained_development']['sourceGroups'],2)
        self.assertEqual(result['qualityObservations']['D03']['retained_development']['matchingSourceGroups'],1)
        self.assertFalse(result['semanticQualityApproved'])
        self.assertEqual(result['round1TrainingQuota'],0)
        self.assertEqual(result['newIndependentTrainingGroups'],0)

    def test_full_roster_and_all_windows_are_the_timed_unit(self):
        result,_=report.build()
        for row in result['timingAfter']:
            self.assertEqual(row['n'],5)
            self.assertLessEqual(row['maxWindowTokens'],512)
            self.assertEqual(row['local50ms'],'fail')
            if row['task']=='D03':
                self.assertEqual(row['candidateCount'],3)
                self.assertEqual(row['windowsPerItem'],12)
        self.assertEqual(result['finalForwardCalls'],160)
        self.assertEqual(result['fullRequest500msStatus'],'unverified')

    def test_original_large_evidence_is_losslessly_archived(self):
        result,_=report.build()
        self.assertEqual(len(result['archives']),3)
        self.assertTrue(all(a['path'].endswith('.gz') and a['rawBytes']>1000000 for a in result['archives']))
        self.assertEqual(result['headParameters'],514)
        self.assertTrue(result['encoderFrozenAndUnchanged'])

    def test_frozen_fit_archive_plan_and_head_identity_cannot_be_rebound(self):
        p=json.loads((report.DATA/(report.INFER+'.plan.json')).read_text())
        fitted=report.read_archive(report.FIT+'.record.json')
        record=report.DATA/(report.FIT+'.record.json.gz');plan=report.DATA/(report.FIT+'.plan.json')
        for field in ('archive','plan','head'):
            bad=copy.deepcopy(p)
            if field=='archive':bad['fitRecord']['sha256']='0'*64
            elif field=='plan':bad['fitPlanSha256']='0'*64
            else:bad['trainedHeadSha256']['D02']='0'*64
            with self.assertRaises(ValueError):report.verify_fit_evidence(bad,record,plan,fitted)


    def test_changed_current_fact_windows_still_requires_exact_historical_source(self):
        with mock.patch.object(report.subprocess,'check_output',return_value=b'wrong historical source'):
            with self.assertRaisesRegex(ValueError,'inference code mismatch'):report.build()


if __name__=='__main__':unittest.main()
