import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from swe_rebench_protocol_details import error_details,call_operation


class LiteralHarnessEvidenceTests(unittest.TestCase):
    def test_nested_noninvocation_error(self):
        parsed=error_details("{'type': 'error_to_regenerate', 'context': {'type': 'tool_call_not_invoked'}}")
        self.assertEqual(parsed['context_type'],'tool_call_not_invoked')

    def test_candidate_ids_from_literal_error(self):
        parsed=error_details("{'type': 'multiple_tool_calls_extracted', 'tool_calls': [{'id': 'x', 'function': {'name':'read'}}, {'id':'y'}]}")
        self.assertEqual(parsed['candidate_ids'],['x','y'])

    def test_error_string_expression_is_never_executed(self):
        parsed=error_details("__import__('os').system('false')")
        self.assertIsNone(parsed['type'])
        self.assertEqual(parsed['candidate_ids'],[])

    def test_duplicate_literal_keys_not_silently_chosen(self):
        self.assertIsNone(error_details("{'type':'one','type':'two'}")['type'])

    def test_submit_inside_compound_is_only_source_component(self):
        classified=call_operation({'tool':'bash_terminal','input':{'command':'git diff --check && submit'}})
        self.assertIn('submit',classified['components'])
        self.assertNotIn('submit',call_operation({'tool':'bash_terminal','input':{'command':'echo submit'}})['components'])

    def test_nonidentifier_tool_name_not_inferred_from_body(self):
        self.assertEqual(call_operation({'tool':'read\nprint(42)','input':{}})['operation'],'unknown')


if __name__=='__main__':unittest.main()
