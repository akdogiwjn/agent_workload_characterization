import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import swebench_instance_results as analysis


class ResultEvidenceTests(unittest.TestCase):
    def ev(self,flags=(),value=None):
        return {'memberships':list(flags),'reported_resolved':value}

    def test_missing_membership_does_not_become_failure(self):
        self.assertIsNone(analysis.classify(self.ev())['resolved'])

    def test_explicit_report_false_recovers_absent_summary_id(self):
        report=analysis.parse_report(json.dumps({'org__repo-1':{'resolved':False}}),'org__repo-1')
        result=analysis.classify(self.ev(),report)
        self.assertEqual(result['status'],'unresolved')
        self.assertIs(result['resolved'],False)

    def test_report_requires_exact_native_id(self):
        report=analysis.parse_report(b'{"other__repo-1":{"resolved":true}}','org__repo-1')
        self.assertIsNone(report['resolved'])
        self.assertEqual(report['status'],'report_instance_id_mismatch')

    def test_false_string_is_not_boolean_false(self):
        for value in ['false',0,None,[],{}]:
            report=analysis.parse_report(json.dumps({'org__repo-1':{'resolved':value}}),'org__repo-1')
            self.assertIsNone(report['resolved'])

    def test_flat_report_requires_directory_binding_and_schema(self):
        data=b'{"resolved":false,"patch_exists":true}'
        self.assertIsNone(analysis.parse_report(data,'org__repo-1')['resolved'])
        self.assertIs(analysis.parse_report(data,'org__repo-1',allow_flat=True)['resolved'],False)
        self.assertIsNone(analysis.parse_report(b'{"resolved":false}','org__repo-1',allow_flat=True)['resolved'])

    def test_summary_report_conflict_is_recorded(self):
        result=analysis.classify(self.ev(['resolved'],True),{'resolved':False})
        self.assertEqual(result['conflicts'],['summary_vs_instance_report'])

    def test_positive_report_with_failure_stage_is_flagged(self):
        result=analysis.classify(self.ev(['no_logs']),{'resolved':True})
        self.assertIn('positive_report_vs_saved_failure_stage',result['conflicts'])

    def test_no_generation_and_empty_patch_remain_stages(self):
        self.assertIsNone(analysis.classify(self.ev(['no_generation']))['resolved'])
        self.assertEqual(analysis.classify(self.ev(),prediction=[{'empty_patch':True}])['status'],'empty_prediction')

    def test_duplicate_predictions_not_silently_chosen(self):
        data=b'{"instance_id":"org__repo-1","model_patch":""}\n'*2
        values=analysis.parse_predictions(data)['org__repo-1']
        self.assertEqual(len(values),2)
        self.assertEqual(analysis.classify(self.ev(),prediction=values)['status'],'no_public_result_artifact')

    def test_pretty_json_prediction_array_is_supported(self):
        data=b'[\n {"instance_id":"org__repo-1","model_patch":"diff"}\n]'
        self.assertFalse(analysis.parse_predictions(data)['org__repo-1'][0]['empty_patch'])

    def test_legacy_complement_requires_positive_completed_cohort(self):
        log={'test_script_completed':True,'error_markers':[]}
        self.assertIsNone(analysis.classify(self.ev(),legacy=log)['resolved'])
        self.assertIsNone(analysis.classify(self.ev(['with_logs']),legacy=log)['resolved'])
        self.assertEqual(analysis.classify(self.ev(['applied','with_logs']),legacy=log)['status'],'legacy_completed_not_resolved')
        log['error_markers']=['Tests Timed Out']
        self.assertIsNone(analysis.classify(self.ev(['applied','with_logs']),legacy=log)['resolved'])

    def test_legacy_test_failure_marker_alone_does_not_resolve(self):
        self.assertFalse(analysis.legacy_evidence(b'>>>>> Some Tests Failed\n')['test_script_completed'])
        self.assertTrue(analysis.legacy_evidence(b'>>>>> Some Tests Failed\n[native] Test script run successful\n')['test_script_completed'])

    def test_kg_compass_uses_explicit_metadata_and_checks_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'native.traj'
            path.write_text('Task Metadata:\n - Instance ID: astropy__astropy-12907\n')
            task,basis=analysis.canonical_task('lite/KGCompass','astropy__astropy-12907.model-5',[{'path':str(path)}])
            self.assertEqual(task,'astropy__astropy-12907')
            with self.assertRaises(ValueError):
                analysis.canonical_task('lite/KGCompass','different__repo-1.model-5',[{'path':str(path)}])


if __name__=='__main__':unittest.main()
