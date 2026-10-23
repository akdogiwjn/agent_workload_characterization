import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.agentx_deepseek_pilot import SSEAudit,adapt_payload,worker_environment
from scripts.agentx_deepseek_analysis import cache_counts,response_oracle


class RemotePilotTests(unittest.TestCase):
    def test_payload_preserves_messages_and_output_limit(self):
        original={'messages':[{'role':'user','content':'literal input'}],'model':'agentx-mock','max_completion_tokens':19,
                  'stream':True,'stream_options':{'include_usage':True}}
        saved=copy.deepcopy(original);actual=adapt_payload(original)
        self.assertEqual(original,saved);self.assertEqual(actual['messages'],original['messages'])
        self.assertEqual(actual['max_tokens'],19);self.assertNotIn('max_completion_tokens',actual)
        self.assertEqual(actual['thinking'],{'type':'disabled'})

    def test_unknown_fields_not_silently_forwarded(self):
        with self.assertRaises(ValueError):adapt_payload({'tools':[{'type':'function'}]})

    def test_usage_on_final_content_chunk_supported(self):
        audit=SSEAudit();audit.event(json.dumps({'model':'m','choices':[{'delta':{'content':'OK'},'finish_reason':None}]}),.3)
        audit.event(json.dumps({'choices':[{'delta':{},'finish_reason':'stop'}],
                               'usage':{'prompt_tokens':10,'completion_tokens':1,'total_tokens':11}}),.4)
        audit.event('[DONE]',.5)
        self.assertTrue(audit.success());self.assertEqual(audit.first_content_s,.3)

    def test_keep_role_only_delta_out_of_ttft(self):
        audit=SSEAudit();audit.event(json.dumps({'choices':[{'delta':{'role':'assistant'},'finish_reason':None}]}),.1)
        self.assertIsNone(audit.first_content_s)

    def test_incomplete_stream_or_missing_usage_not_success(self):
        audit=SSEAudit();audit.event(json.dumps({'choices':[{'delta':{'content':'A'},'finish_reason':'stop'}]}),.1)
        self.assertFalse(audit.success());audit.event('[DONE]',.2);self.assertFalse(audit.success())

    def test_unexpected_thinking_is_rejected(self):
        audit=SSEAudit();audit.event(json.dumps({'choices':[{'delta':{'reasoning_content':'reason','content':'answer'},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}}),.1)
        audit.event('[DONE]',.2);self.assertFalse(audit.success())

    def test_tool_execution_cannot_start(self):
        with self.assertRaises(ValueError):SSEAudit().event(json.dumps({'choices':[{'delta':{'tool_calls':[{'id':'t'}]}}]}),.1)

    def test_other_provider_credentials_not_inherited(self):
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'sentinel','VOLCANO_API_KEY':'other','OPENAI_API_KEY':'other2'},clear=True):
            env=worker_environment();self.assertEqual(env['DEEPSEEK_API_KEY'],'sentinel')
            self.assertNotIn('VOLCANO_API_KEY',env);self.assertNotIn('OPENAI_API_KEY',env)

    def test_missing_cache_fields_are_unknown_not_zero(self):
        self.assertEqual(cache_counts({'prompt_tokens':10}),(None,None))
        self.assertEqual(cache_counts({'prompt_tokens':10,'prompt_cache_hit_tokens':0}),(0,10))

    def test_inconsistent_cache_counters_rejected(self):
        for usage in [{'prompt_tokens':10,'prompt_cache_hit_tokens':11},
                      {'prompt_tokens':10,'prompt_cache_hit_tokens':3,'prompt_cache_miss_tokens':8},
                      {'prompt_tokens':10,'prompt_cache_hit_tokens':3,'prompt_tokens_details':{'cached_tokens':4}}]:
            with self.assertRaises(ValueError):cache_counts(usage)

    def test_independent_saved_body_oracle_handles_usage_only_chunk(self):
        values=[{'model':'m','choices':[{'delta':{'content':'one'},'finish_reason':None}]},
                {'choices':[{'delta':{'content':'two'},'finish_reason':'length'}]},
                {'choices':[],'usage':{'prompt_tokens':12,'completion_tokens':2,'total_tokens':14}}]
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'r.sse';p.write_text(''.join('data: '+json.dumps(q)+'\n\n' for q in values)+'data: [DONE]\n\n')
            q=response_oracle(p);self.assertEqual(q['text'],'onetwo');self.assertTrue(q['done'])
            self.assertEqual(q['usage']['completion_tokens'],2);self.assertEqual(q['finish'],'length')


if __name__=='__main__':unittest.main()
