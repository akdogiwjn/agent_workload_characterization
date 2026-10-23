import unittest

from scripts.agentx_deepseek_complete import acceptable_probe,length_probes
from scripts.agentx_deepseek_coverage_analysis import probe_conclusion,unique_coverage


class CompletePilotTests(unittest.TestCase):
    def test_acceptance_does_not_imply_minimum_generation_is_honored(self):
        q={'status':'completed','http_status':200,'finish_reason':'stop','usage':{'completion_tokens':1}}
        self.assertEqual(probe_conclusion(q,64),'normal_stop_below_probe_target')
        q['usage']['completion_tokens']=64;q['finish_reason']='length'
        self.assertEqual(probe_conclusion(q,64),'target_reached_in_one_trial_not_a_guarantee')

    def test_full_request_count_cannot_hide_duplicate_or_wrong_source(self):
        q={'trace_id':'a','source_outer_idx':0,'source_inner_idx':None,'source_request_sha256':'x'}
        r={**q,'source_outer_idx':1,'source_request_sha256':'y'}
        self.assertEqual(unique_coverage([q,r],[dict(q),dict(r)]),2)
        for rows in [[q,q],[q], [q,{**r,'source_request_sha256':'bad'}], [q,{**r,'trace_id':'other'}]]:
            with self.assertRaises(ValueError):unique_coverage([q,r],rows)

    def test_experimental_fields_are_isolated_between_probes(self):
        probes=length_probes();control,minimum,eos=[q['payload'] for q in probes]
        self.assertNotIn('min_tokens',control);self.assertNotIn('ignore_eos',control)
        self.assertNotIn('ignore_eos',minimum);self.assertNotIn('min_tokens',eos)
        minimum['messages'][0]['content']='changed'
        self.assertNotEqual(minimum['messages'],control['messages'])

    def test_bounded_probe_generation_and_identical_original_prompts(self):
        probes=length_probes()
        self.assertEqual(len(probes),3)
        self.assertTrue(all(q['payload']['max_tokens']==64 for q in probes))
        self.assertTrue(all(q['payload']['messages']==probes[0]['payload']['messages'] for q in probes))

    def test_expected_parameter_rejection_not_general_failure_bypass(self):
        rejected={'status':'http_error','http_status':400}
        self.assertTrue(acceptable_probe(rejected,'min_tokens'))
        self.assertFalse(acceptable_probe(rejected,'control'))
        for q in [{'status':'http_error','http_status':401},{'status':'http_error','http_status':429},
                  {'status':'transport_error','http_status':None}]:
            self.assertFalse(acceptable_probe(q,'ignore_eos'))


if __name__=='__main__':unittest.main()
