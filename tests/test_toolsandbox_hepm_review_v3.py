import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from toolsandbox_hepm_review_v3 import native_request,request_index


class StaticNativeRequestTests(unittest.TestCase):
    def source(self,name='search_contacts',cid='call_x'):
        return f"{cid}_parameters = {{'name': 'Alice'}}\n{cid}_response = {name}(**{cid}_parameters)\nprint(repr({cid}_response))"

    def test_exact_wrapper_recovers_original_name(self):
        self.assertEqual(native_request(self.source(),'call_x',{'search_contacts'}),('search_contacts','exact_saved_request_ast'))

    def test_wrong_call_id_is_not_cross_paired(self):
        self.assertIsNone(native_request(self.source(),'call_other',{'search_contacts'})[0])

    def test_unknown_native_function_rejected(self):
        self.assertIsNone(native_request(self.source('invented'),'call_x',{'search_contacts'})[0])

    def test_name_in_argument_string_does_not_become_function(self):
        text=self.source().replace("'Alice'","'end_conversation(**call_x_parameters)'")
        self.assertEqual(native_request(text,'call_x',{'search_contacts','end_conversation'})[0],'search_contacts')

    def test_extra_executable_statement_rejected(self):
        self.assertIsNone(native_request('import os\n'+self.source(),'call_x',{'search_contacts'})[0])

    def test_parameter_and_print_binding_required(self):
        for text in [self.source().replace('**call_x_parameters','**other'),self.source().replace('repr(call_x_response)','repr(other)')]:
            self.assertIsNone(native_request(text,'call_x',{'search_contacts'})[0])

    def test_unparseable_saved_request_remains_unresolved(self):
        self.assertIsNone(native_request('broken >>>','call_x',{'search_contacts'})[0])

    def test_user_events_and_result_rows_are_not_agent_requests(self):
        rows=[{'sender':'USER','recipient':'EXECUTION_ENVIRONMENT','openai_tool_call_id':'call_u'},
              {'sender':'EXECUTION_ENVIRONMENT','recipient':'AGENT','openai_tool_call_id':'call_x'},
              {'sender':'AGENT','recipient':'EXECUTION_ENVIRONMENT','openai_tool_call_id':'call_x'}]
        self.assertEqual(set(request_index({'_dbs':{'SANDBOX':rows}})),{'call_x'})


if __name__=='__main__':unittest.main()
