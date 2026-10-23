import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from swe_rebench_review_v3 import noninvocation_error,submit_intent,protocol_review,availability


class RebenchEvidenceTests(unittest.TestCase):
    def test_structured_and_literal_noninvocation_marker(self):
        for value in [{'type':'tool_call_not_invoked'},'{"type":"tool_call_not_invoked"}',"{'type': 'tool_call_not_invoked'}"]:
            self.assertTrue(noninvocation_error(value))
        for value in [None,'tool_call_not_invoked',"some text {'type': 'tool_call_not_invoked'}",{'type':'other_error'}]:
            self.assertFalse(noninvocation_error(value))

    def test_submit_request_requires_exact_command(self):
        for command in ['submit','  submit  ',['submit']]:
            self.assertTrue(submit_intent({'tool':'bash_terminal','input':{'command':command}}))
        for command in ['echo submit','grep submit file','submit && rm x','pytest test_submit.py','submit_fake']:
            self.assertFalse(submit_intent({'tool':'bash_terminal','input':{'command':command}}))

    def test_unique_id_and_noninvocation_are_different(self):
        events=[{'type':'tool_call','tool_call_id':'x','tool':'read'},
                {'type':'tool_result','tool_call_id':'x'},
                {'type':'tool_result','error':"{'type': 'tool_call_not_invoked'}"}]
        counts,unpaired,nonids=protocol_review(events)
        self.assertEqual(counts['unique_id_pairs'],1)
        self.assertEqual(counts['explicit_tool_not_invoked'],1)
        self.assertFalse(unpaired)

    def test_submit_intent_does_not_consume_unidentified_return(self):
        events=[{'type':'tool_call','tool_call_id':'end','tool':'submit'},
                {'type':'tool_result','content':'ok'}]
        counts,unpaired,nonids=protocol_review(events)
        self.assertEqual(counts['submit_request_without_saved_return'],1)
        self.assertEqual(counts['unidentified_result_without_id'],1)
        self.assertEqual(counts.get('unique_id_pairs',0),0)

    def test_duplicate_ids_are_never_silently_overwritten(self):
        events=[{'type':'tool_call','tool_call_id':'x'}]*2+[{'type':'tool_result','tool_call_id':'x'}]
        counts,_,_=protocol_review(events)
        self.assertEqual(counts['ambiguous_call_entries'],2)

    def test_duration_booleans_are_not_numeric_measurements(self):
        self.assertEqual(availability(True),'boolean')
        self.assertEqual(availability(float('nan')),'unsupported_or_nonfinite')
        self.assertEqual(availability(0),'finite_nonnegative')


if __name__=='__main__':unittest.main()
