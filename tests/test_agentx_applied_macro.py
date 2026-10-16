import hashlib, json, tempfile, unittest
from pathlib import Path
from scripts.agentx_applied_macro import applied_row, analyze_agentx, interval_stats, write_report

class MacroTests(unittest.TestCase):
    def make_inputs(self):
        td=tempfile.TemporaryDirectory(); base=Path(td.name); ax=base/'agentx'; ac=base/'applied'; (ac/'workloads').mkdir(parents=True); ax.mkdir()
        trace={'id':'t1','models':['m'],'block_size':64,'hash_id_scope':'local','requests':[
            {'type':'s','t':0.0,'in':10,'out':2,'api_time':1.0,'model':'m','hash_ids':[0,1]},
            {'type':'subagent','agent_id':'a1','t':0.5,'duration_ms':1000,'requests':[
                {'type':'n','t':0.6,'in':20,'out':3,'api_time':0.5,'model':'m','hash_ids':[0,2]}]}
        ]}
        (ax/'traces.jsonl').write_text(json.dumps(trace)+'\n'); (ax/'README.md').write_text('readme'); (ax/'stats.txt').write_text('stats')
        applied={'num_turns':2,'input_prompt_length':10,'assistant_response_length':[2,0],'tool_call_output_length':[3,4],'tool_call_latency':[0.0,1.5],'final_assistant_response_length':5}
        (ac/'README.md').write_text('readme'); (ac/'LICENSE').write_text('license'); (ac/'workloads'/'agentic_coding_8k.jsonl').write_text(json.dumps(applied)+'\n')
        for name in ('code_qa_8k.jsonl','office_work_8k.jsonl'):(ac/'workloads'/name).write_text('')
        files=[ax/'README.md',ax/'stats.txt',ax/'traces.jsonl',ac/'README.md',ac/'LICENSE',*(ac/'workloads').glob('*.jsonl')]
        entries=[]
        for p in files: entries.append({'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
        am=base/'acq.json'; am.write_text(json.dumps({'inputs':entries})); return td,ax,ac,am
    def test_actual_entry_and_report(self):
        td,ax,ac,am=self.make_inputs()
        try:
            out=Path(td.name)/'out'; s=write_report(ax,ac,am,out,Path('scripts/agentx_applied_macro.py'))
            self.assertEqual(s['sources']['AgentX']['summary']['trace_count'],1)
            self.assertEqual(s['sources']['AgentX']['summary']['total_model_request_count'],2)
            self.assertEqual(s['sources']['Applied Compute']['summary']['agentic_coding_8k']['valid_template_count'],1)
            self.assertEqual(s['sources']['Applied Compute']['summary']['agentic_coding_8k']['derived_completion_requests']['median'],3)
            self.assertEqual(json.loads((out/'manifest.json').read_text())['manifest_self_hash'],'excluded')
        finally: td.cleanup()
    def test_zero_missing_and_length_anomaly(self):
        good=applied_row({'num_turns':1,'input_prompt_length':0,'assistant_response_length':[0],'tool_call_output_length':[0],'tool_call_latency':[0.0],'final_assistant_response_length':0},Path('x'),1)
        self.assertTrue(good['valid']); self.assertEqual(good['derived']['total_input_tokens'],0)
        bad=applied_row({'num_turns':2,'input_prompt_length':1,'assistant_response_length':[1],'tool_call_output_length':[1,1],'tool_call_latency':[0,0],'final_assistant_response_length':1},Path('x'),1)
        self.assertFalse(bad['valid']); self.assertIn('assistant_response_length_length_mismatch',bad['errors'])
        missing=applied_row({'num_turns':0,'input_prompt_length':None,'assistant_response_length':[],'tool_call_output_length':[],'tool_call_latency':[],'final_assistant_response_length':0},Path('x'),1)
        self.assertFalse(missing['valid'])
    def test_time_scope_and_input_change(self):
        self.assertEqual(interval_stats([{'t':0,'api_time':2},{'t':1,'api_time':2}])['overlap_s'],1)
        self.assertEqual(interval_stats([{'t':0,'api_time':1},{'t':10,'api_time':1}])['union_s'],2)
        td,ax,ac,am=self.make_inputs()
        try:
            a=analyze_agentx(ax/'traces.jsonl')[2]['request_input_tokens']['median']
            raw=json.loads((ax/'traces.jsonl').read_text()); raw['requests'][0]['in']=100; (ax/'traces.jsonl').write_text(json.dumps(raw)+'\n')
            b=analyze_agentx(ax/'traces.jsonl')[2]['request_input_tokens']['median']; self.assertNotEqual(a,b)
        finally: td.cleanup()
    def test_hash_mismatch_rejected(self):
        td,ax,ac,am=self.make_inputs()
        try:
            x=json.loads(am.read_text()); x['inputs'][0]['sha256']='0'*64; am.write_text(json.dumps(x))
            with self.assertRaises(ValueError): write_report(ax,ac,am,Path(td.name)/'out',Path('scripts/agentx_applied_macro.py'))
        finally: td.cleanup()

if __name__=='__main__': unittest.main()
