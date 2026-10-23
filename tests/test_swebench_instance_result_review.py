import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from swebench_instance_result_review import refine


class NativeStageReviewTests(unittest.TestCase):
    def row(self,markers=None,prediction=None,status='no_public_result_artifact'):
        return {'evaluation':{'status':status,'resolved':None,'conflicts':[]},
                'legacy_log':{'markers':markers} if markers else None,'prediction':prediction}

    def test_exact_native_patch_apply_failure_becomes_stage_failure(self):
        before=self.row({'Patch Apply Failed; (test)':1})
        after=refine(before,False)
        self.assertEqual(after['evaluation']['status'],'evaluation_stage_failure')
        self.assertIsNone(after['evaluation']['resolved'])
        self.assertEqual(before['evaluation']['status'],'no_public_result_artifact')

    def test_patch_applied_marker_is_not_failure(self):
        self.assertEqual(refine(self.row({'Applied Patch (test)':1}),False)['evaluation']['status'],'public_evaluation_artifacts_absent')

    def test_prediction_present_and_absent_are_distinct_source_facts(self):
        self.assertEqual(refine(self.row(),True)['evaluation']['status'],'prediction_record_absent')
        self.assertEqual(refine(self.row(prediction=[{'empty_patch':False}]),True)['evaluation']['status'],'prediction_present_result_missing')

    def test_explicit_report_and_conflicts_are_not_overridden(self):
        for status in ('resolved','unresolved','conflicting_published_results','invalid_instance_report'):
            self.assertEqual(refine(self.row({'Patch Apply Failed; (pred)':1},status=status),True)['evaluation']['status'],status)

    def test_empty_report_with_explicit_timeout_is_stage_failure(self):
        row=self.row(status='invalid_instance_report')
        row['review_test_output']={'text':'\n\nTimeout error: 1800 seconds exceeded.\n'}
        self.assertEqual(refine(row,True)['evaluation']['status'],'evaluation_stage_failure')
        self.assertIsNone(refine(row,True)['evaluation']['resolved'])


if __name__=='__main__':unittest.main()
