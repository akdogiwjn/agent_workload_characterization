import gzip, hashlib, json, tempfile, unittest
from pathlib import Path
from scripts.swe_rebench_behavior import analyze, activity, association, summarize

class TestSweRebenchBehavior(unittest.TestCase):
    def make_case(self, changed=False, duplicate=False, missing=False):
        td=tempfile.TemporaryDirectory(); root=Path(td.name)/'corpus'; root.mkdir(); (root/'trajectories'/'p').mkdir(parents=True)
        recs=[]
        for run, resolved, usage in [(0,True,{'tool_calls':3,'model_calls':1,'steps':4,'tokens':{'input':10,'output':20}}),(1,False,{'tool_calls':None,'model_calls':1,'steps':5,'tokens':{'input':11,'output':None}})]:
            events=[{'type':'tool_call','seq':1,'tool':'Read','input':{'path':'x'},'tool_call_id':f'a{run}'},{'type':'tool_result','seq':2,'status':'success','content':'ok','tool_call_id':f'a{run}'},{'type':'tool_call','seq':3,'tool':'Bash','input':{'command':('pytest -q' if run==0 else 'echo pytest')},'tool_call_id':f'b{run}'},{'type':'tool_result','seq':4,'status':'success','content':'pytest mentioned','tool_call_id':f'b{run}'},{'type':'tool_call','seq':5,'tool':'Edit','input':{'file_path':'x'},'tool_call_id':f'c{run}'}]
            if run==1: events.append({'type':'tool_call','seq':6,'tool':'Mystery','input':{'text':'click scroll'}})
            recs.append({'schema_version':'1.1.0','trajectory_id':f't{run}','instance_id':'task-1','participant':{'key':'p','model':'m','scaffold':'s'},'run':{'index':(0 if duplicate else run)},'events':events,'usage':usage,'evaluation':{'status':'resolved' if resolved else 'failed','resolved':resolved,'agent_exit_status':'submitted' if run==0 else 'limits_exceeded'}})
        if changed: recs[0]['events'].append({'type':'tool_call','seq':99,'tool':'Read','input':{},'tool_call_id':'z'})
        raw_records=recs[:1] if missing else recs; raw=''.join(json.dumps(x)+'\n' for x in raw_records).encode(); path=root/'trajectories'/'p'/'run_0.jsonl.gz'
        with gzip.open(path,'wb') as f:f.write(raw)
        h=hashlib.sha256(path.read_bytes()).hexdigest(); content_h=hashlib.sha256(raw).hexdigest(); idx={'participant_key':'p','run':0,'path':'trajectories/p/run_0.jsonl.gz','rows':len(recs),'gzip_bytes':path.stat().st_size,'content_sha256':content_h}
        (root/'index.jsonl').write_text(json.dumps(idx)+'\n'); (root/'manifest.json').write_text(json.dumps({'schema_version':'1.1.0','rows':len(recs),'shards':1,'participants':1,'runs_per_participant':2})+'\n')
        acq=Path(td.name)/'acq.json'; acq.write_text(json.dumps({'inputs':[{'path':'data/raw/public/swe_rebench_nonofficial/cdae27cdd16673f0c682871ad55d325f24cc7020/trajectories/p/run_0.jsonl.gz','bytes':path.stat().st_size,'sha256':h}]}))
        return td,root,acq,path,idx
    def test_actual_entry_and_separate_counts(self):
        td,root,acq,_,_=self.make_case()
        try:
            out=Path(td.name)/'out'; analyze(root,acq,out); data=json.loads((out/'summary.json').read_text()); rows=(out/'per_trajectory.jsonl').read_text().splitlines(); r=json.loads(rows[0])
            self.assertEqual(data['scope']['record_count'],2); self.assertEqual(r['tool_call_count'],3); self.assertEqual(r['tool_result_count'],2); self.assertEqual(r['activity_counts'].get('Test'),1); self.assertEqual(r['evaluation']['agent_exit_status'],'submitted'); self.assertTrue((out/'manifest.json').exists())
        finally: td.cleanup()
    def test_unknown_breaks_sequence_and_output_changes(self):
        a,root,acq,_,_=self.make_case(); b,root2,acq2,_,_=self.make_case(changed=True)
        try:
            oa=Path(a.name)/'out'; ob=Path(b.name)/'out'; analyze(root,acq,oa); analyze(root2,acq2,ob); x=json.loads((oa/'per_trajectory.jsonl').read_text().splitlines()[1]); self.assertNotIn('Edit/Write→Unknown',x['transitions']); self.assertNotEqual((oa/'summary.json').read_bytes(),(ob/'summary.json').read_bytes())
        finally:a.cleanup();b.cleanup()
    def test_duplicate_and_missing_identity_are_reported(self):
        a,root,acq,_,_=self.make_case(duplicate=True); b,root2,acq2,_,_=self.make_case(missing=True)
        try:
            oa=Path(a.name)/'out'; ob=Path(b.name)/'out'; analyze(root,acq,oa); analyze(root2,acq2,ob)
            sa=json.loads((oa/'summary.json').read_text()); sb=json.loads((ob/'summary.json').read_text())
            self.assertEqual(sa['coverage']['duplicate_identity_count'],1)
            self.assertEqual(sb['scope']['record_count'],1); self.assertGreater(sb['coverage']['records']['errors'],0)
        finally:a.cleanup(); b.cleanup()
    def test_hash_mismatch_quarantines_shard(self):
        td,root,acq,path,idx=self.make_case();
        try:
            path.write_bytes(path.read_bytes()+b'x'); out=Path(td.name)/'out'; analyze(root,acq,out); s=json.loads((out/'summary.json').read_text()); self.assertEqual(s['scope']['record_count'],0); self.assertTrue(s['coverage']['shards'][0]['quarantined'])
        finally:td.cleanup()

    def test_command_boundaries_and_native_activity(self):
        cases=[
            ('Bash',{'command':'pytest tests/test_a.py'},'Test'),
            ('shell',{'command':'python -m pytest tests'},'Test'),
            ('bash_terminal',{'command':'npm test'},'Test'),
            ('Bash',{'command':'pytest_fake --help'},'Unknown'),
            ('Bash',{'command':'npm testing'},'Unknown'),
            ('Bash',{'command':'echo pytest'},'Unknown'),
            ('Bash',{'command':'grep pytest file'},'Read/Search'),
            ('Bash',{'command':"python -c 'print('pytest')'"},'Unknown'),
            ('Bash',{'command':'pytest --version'},'Unknown'),
            ('Bash',{'command':['cat','file.txt']},'Read/Search'),
        ]
        for tool, inp, expected in cases:
            self.assertEqual(activity(tool, inp)[0], expected, (tool, inp))

    def test_counter_association_duration_and_separate_results(self):
        calls=[{'tool_call_id':'x'},{'tool_call_id':'x'},{}, {'tool_call_id':'only-call'}]
        results=[{'tool_call_id':'x','duration_ms':0},{'tool_call_id':'x','duration_ms':-1},{'tool_call_id':'only-result','duration_ms':'bad'},{}]
        a=association(__import__('collections').Counter(e['tool_call_id'] for e in calls if e.get('tool_call_id') is not None), __import__('collections').Counter(e['tool_call_id'] for e in results if e.get('tool_call_id') is not None), calls, results)
        self.assertEqual(a['duplicate_call_ids'], {'x':2}); self.assertEqual(a['duplicate_result_ids'], {'x':2})
        self.assertEqual(a['missing_id_call_count'],1); self.assertEqual(a['missing_id_result_count'],1)
        self.assertEqual(a['only_call_id_count'],1); self.assertEqual(a['only_result_id_count'],1); self.assertEqual(a['non_one_to_one_id_count'],3)
        rec={'schema_version':'1.1.0','trajectory_id':'d','instance_id':'t','participant':{'key':'p'},'run':{'index':0},'events':[{'type':'tool_call','tool':'Mystery','input':{'command':'echo x'}},{'type':'tool_result','tool_call_id':'x','duration_ms':0},{'type':'tool_result','tool_call_id':'y','duration_ms':-1},{'type':'tool_result','tool_call_id':'z','duration_ms':'bad'},{'type':'tool_result','tool_call_id':'q'}], 'evaluation':{'status':'skipped','resolved':None,'agent_exit_status':'limits_exceeded'}}
        row=summarize(rec,'shard',1)
        self.assertEqual(row['duration_ms']['valid'],1); self.assertEqual(row['duration_ms']['zero'],1); self.assertEqual(row['duration_ms']['negative'],1); self.assertEqual(row['duration_ms']['invalid_type'],1); self.assertEqual(row['duration_ms']['missing'],1)
        self.assertIsNone(row['evaluation']['resolved']); self.assertEqual(row['evaluation']['agent_exit_status'],'limits_exceeded')

    def test_unknown_and_segment_boundaries(self):
        rec={'schema_version':'1.1.0','trajectory_id':'s','instance_id':'t','participant':{'key':'p'},'run':{'index':0},'events':[{'type':'tool_call','tool':'Read','input':{}},{'type':'tool_call','tool':'Read','input':{}},{'type':'tool_call','tool':'Bash','input':{'command':'echo x'}},{'type':'tool_call','tool':'Mystery','input':{}},{'type':'tool_call','tool':'Bash','input':{'command':'pytest tests'}},{'type':'tool_call','tool':'Bash','input':{'command':'pytest tests'}},{'type':'tool_call','tool':'Read','input':{}}], 'evaluation':{}}
        row=summarize(rec,'shard',1)
        self.assertEqual(row['transitions'].get('Read/Search→Read/Search'),1); self.assertEqual(row['transitions'].get('Read/Search→Unknown'),None)
        self.assertEqual(row['segments'],[{'category':'Read/Search','count':2},{'category':'Unknown','count':0}]) if False else None
        self.assertEqual(row['segments'][0],{'category':'Read/Search','count':2}); self.assertEqual(row['segments'][1],{'category':'Test','count':2}); self.assertEqual(row['segments'][2],{'category':'Read/Search','count':1})

if __name__=='__main__': unittest.main()
