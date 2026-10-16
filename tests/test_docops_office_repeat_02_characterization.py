from __future__ import annotations
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts import docops_office_repeat_02_characterization as a


def write(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False)+'\n')


def reading(t, cpu=None):
    return {'scope':'agent_container','scope_kind':'agent_container','t_monotonic_ns':int(t*a.NS),
            'cpu_usage_usec':int(t*100000) if cpu is None else cpu,'mem_current_bytes':int(t*1000),
            'mem_peak_bytes':12000,'io_read_bytes':0,'io_write_bytes':int(t*100),
            'read_status':{'cpuacct.usage':'ok_ns_converted_to_usec','memory.usage_in_bytes':'ok',
                           'memory.max_usage_in_bytes':'ok','io':'ok_summed_devices:synthetic'}}


def fixture(root):
    code=[]
    for rel in ['references/repos/DocOps/harnesses/document_tools_runtime.py','references/repos/DocOps/harnesses/document_tools_agent.py',
                'src/agent_workload_characterization/runners/docops_word_runtime.py','src/agent_workload_characterization/runners/docops_word_agent.py','scripts/docops_word_resource_01_entry.py']:
        dest=root/rel;dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((Path(a.__file__).resolve().parents[1]/rel).read_bytes());code.append(a.old.file_record(root,dest))
    identity={'collection':a.COLLECTION,'code_and_runtime_files':code,'tasks':list(a.TASKS)}
    digest=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    for name in ['plan-identity.json','frozen-identity.json']:write(root/a.ENV/name,{'identity':identity,'identity_sha256':digest})
    write(root/a.REPORT/'APPROVAL.json',{'collection':a.COLLECTION,'identity_sha256':digest,'user_approval':'approved'})
    write(root/a.REPORT/'ATTEMPT_STARTED.json',{'collection':a.COLLECTION,'identity_sha256':digest})
    rows=[]
    for rnd,tasks in enumerate(a.SCHEDULE):
        for task in tasks:
            run=f'r{rnd}-{a.old.SHORT[task]}';p=root/a.RAW/run;native=[]
            def span(kind,eid,t0,t1,attrs,ends):
                for status,t,kw in [('open',t0,attrs),('closed',t1,ends)]:
                    native.append({'kind':kind,'event_id':eid,'status':status,'clock_domain':'system_monotonic',
                                   't_monotonic_ns':int(t*a.NS),'attrs':kw})
            error=task==a.TASKS[1];payload={'ok':False,'error':'AttributeError'} if error else {'ok':True}
            resultsha=hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest()
            span('tool_call',run+'b',1,2,{'role':'bootstrap','tool_name':'inspect_document','resource_before':reading(1)},
                 {'ok':not error,'result_sha256':resultsha,'resource_after':reading(2)})
            span('llm_request',run+'q1',2,6,{'model':'openai/deepseek-v4-flash','step_index':1},
                 {'ok':True,'response_model':'deepseek-flash','usage':{'prompt_tokens':10,'completion_tokens':2}})
            span('tool_call',run+'t',5,7,{'role':'agent','request_event_id':run+'q1','tool_name':'copy_file','resource_before':reading(5)},
                 {'ok':True,'result_sha256':'synthetic','resource_after':reading(7)})
            span('llm_request',run+'q2',7,9,{'model':'openai/deepseek-v4-flash','step_index':2},
                 {'ok':True,'response_model':'deepseek-flash','usage':{'prompt_tokens':20,'completion_tokens':3}})
            native.append({'kind':'agent_action','event_id':run+'f','status':'point','t_monotonic_ns':9*a.NS,
                           'clock_domain':'system_monotonic','attrs':{'action':'finish'}})
            native.sort(key=lambda e:e['t_monotonic_ns']);ep=p/'agent/events.jsonl';ep.parent.mkdir(parents=True)
            ep.write_text(''.join(json.dumps(e)+'\n' for e in native))
            life=[]
            for phase,t in [('attempt_started',0),('harbor_start_begin',0),('harbor_start_done',.2),('agent_setup_begin',.2),
                            ('agent_setup_done',.5),('agent_begin',1),('agent_end',10),('verifier_begin',11),('verifier_end',12),
                            ('harbor_stop_begin',12),('harbor_stop_done',13),('removal_verified',13.1),('image_tag_after_stop',13.2),
                            ('archive_begin',13.3),('archive_done',13.4)]:
                e={'phase':phase,'t_monotonic_ns':int(t*a.NS)}
                if phase.startswith('agent_') or phase.startswith('verifier_'):e['shared_resource_boundary']=reading(t)
                if phase=='removal_verified':e['result']='removed'
                if phase=='harbor_stop_done':e['stop_error']=None
                if phase=='image_tag_after_stop':e.update(present=True,id='sha256:synthetic',query_error=None)
                life.append(e)
            samples=[{'t_monotonic_ns':int(t*a.NS),'clock_domain':'system_monotonic','container':reading(t),
                      'host_agent':{'rss_bytes':10000},'read_wall_ns':100} for t in [0,1,3,5,6,7,9,10,11,12]]
            outcome={'phases':{'agent':{'status':'finish'},'verifier':{'status':'completed','reward':1}},'infra_failures':[]}
            summary={'run_id':run,'task_key':task,'round':rnd,'identity_sha256':digest,'wall_s':14,'within_total_budget':True,
                     'outcome':outcome,'events':life,'samples':samples}
            write(p/'summary.json',summary);write(p/'measurement.json',{'call_timing_status':'complete'});write(p/'environment.json',{'filesystem':None})
            write(p/'ATTEMPT_STARTED.json',{'run_id':run,'task_key':task,'round':rnd,'identity_sha256':digest,'collection':a.COLLECTION})
            write(p/'ATTEMPT_COMPLETED.json',{'run_id':run,'wall_s':14})
            write(p/'verifier/ctrf.json',{'results':{'summary':{'passed':1,'failed':0}}})
            for n,act in [(1,{'action':'call_tool','tool_name':'copy_file','arguments':{'src':'a','dest':'b'}}),(2,{'action':'finish','arguments':{}})]:
                write(p/f'agent/llm_call_{n}.json',{'messages':[{'role':'user','content':'Bootstrap tool result (inspect_document on input_path):\n'+json.dumps(payload)}],
                      'original_response':json.dumps({'model':'deepseek-flash','choices':[{'message':{'content':json.dumps(act)}}]})})
            row={'run_id':run,'task_key':task,'round':rnd,'identity_sha256':digest,'termination':'finish','reward':1,'model_requests_logged':2}
            rows.append(row)
    batch={'collection':a.COLLECTION,'identity_sha256':digest,'results':rows,'batch_wall_s':140}
    write(root/a.REPORT/'batch-summary.json',batch)
    reseal(root)


def reseal(root):
    batch=a.old.load_json(root/a.REPORT/'batch-summary.json');digest=batch['identity_sha256'];refs=[]
    for row in batch['results']:
        p=root/a.RAW/row['run_id'];outs=[a.old.file_record(p,q) for q in sorted(p.rglob('*')) if q.is_file() and q.name!='manifest.json']
        write(p/'manifest.json',{**{k:row[k] for k in ['run_id','task_key','round','identity_sha256']},'inputs':[],'outputs':outs})
        refs.append(a.old.file_record(root,p/'manifest.json'))
    paths=[root/a.REPORT/name for name in ['APPROVAL.json','ATTEMPT_STARTED.json','batch-summary.json']]
    write(root/a.REPORT/'batch-manifest.json',{'identity_sha256':digest,'input_root':str(root),'output_root':str(root),'inputs':[],
          'outputs':[a.old.file_record(root,p) for p in paths],'raw_run_manifests':refs})
    write(root/a.REPORT/'VALIDATION.json',{'identity_sha256':digest})
    write(root/a.REPORT/'VALIDATION-MANIFEST.json',{'identity_sha256':digest,'input_root':str(root),'output_root':str(root),
          'inputs':[a.old.file_record(root,root/a.REPORT/'batch-manifest.json')], 'outputs':[a.old.file_record(root,root/a.REPORT/'VALIDATION.json')]})


class CharacterizationTests(unittest.TestCase):
    def test_full_entry_outputs_and_protection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root)
            before={str(p.relative_to(root)):a.old.file_record(root,p) for rel in [a.RAW,a.REPORT,a.ENV] for p in (root/rel).rglob('*') if p.is_file()}
            out=root/'analysis';self.assertEqual(a.main(['--root',str(root),'--output',str(out)]),0)
            s=a.old.load_json(out/'summary.json');self.assertEqual(s['totals']['runs'],9);self.assertEqual(s['totals']['bootstrap_ok_false'],3)
            self.assertEqual(s['totals']['logical_requests'],18);self.assertEqual(s['totals']['agent_tools'],9)
            self.assertTrue(s['ppt_diagnosis']['static_source_positions'])
            runs=[json.loads(l) for l in (out/'per_run.jsonl').read_text().splitlines()]
            self.assertTrue(all(r['time']['agent_partition']['residual_ns']==0 for r in runs))
            self.assertTrue(all(r['time']['agent_partition']['overlap_s']==1 for r in runs))
            self.assertTrue(all(abs(r['resources']['cpu_partition']['full_window_residual_core_s'])<1e-12 for r in runs))
            for x in a.old.load_json(out/'manifest.json')['outputs']:self.assertEqual(a.old.file_record(out,out/x['path']),x)
            after={str(p.relative_to(root)):a.old.file_record(root,p) for rel in [a.RAW,a.REPORT,a.ENV] for p in (root/rel).rglob('*') if p.is_file()}
            self.assertEqual(before,after)
            self.assertEqual(len(list(out.iterdir())),4)

    def test_input_changes_report(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);s1=a.analyze(root,root/'one')
            b=a.old.load_json(root/a.REPORT/'batch-summary.json');q=root/a.RAW/b['results'][0]['run_id']/'summary.json';s=a.old.load_json(q)
            s['samples'][-1]['container']['cpu_usage_usec']+=100000;write(q,s);reseal(root)
            s2=a.analyze(root,root/'two')
            task=a.TASKS[0];self.assertNotEqual(s1['by_task'][task]['metrics']['cpu_core_s']['points'],s2['by_task'][task]['metrics']['cpu_core_s']['points'])

    def test_hash_and_file_set_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);b=a.old.load_json(root/a.REPORT/'batch-summary.json');q=root/a.RAW/b['results'][0]['run_id']/'environment.json'
            q.write_text('{}');self.assertRaises(ValueError,a.analyze,root,root/'bad')
            reseal(root);(q.parent/'extra.txt').write_text('not registered');self.assertRaises(ValueError,a.analyze,root,root/'extra')

    def test_missing_and_duplicate_spans_real_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);b=a.old.load_json(root/a.REPORT/'batch-summary.json');p=root/a.RAW/b['results'][0]['run_id']/'agent/events.jsonl'
            es=[json.loads(l) for l in p.read_text().splitlines()];es=[e for e in es if not (e['kind']=='tool_call' and e['status']=='closed' and e['event_id'].endswith('t'))]
            es.append(next(e for e in es if e['kind']=='llm_request' and e['status']=='open'));p.write_text(''.join(json.dumps(e)+'\n' for e in es));reseal(root)
            s=a.analyze(root,root/'out');self.assertGreater(s['totals']['pairing_issue_count'],0)
            r=json.loads((root/'out/per_run.jsonl').read_text().splitlines()[0]);self.assertIsNone(r['last_agent_tool_terminal']);self.assertEqual(r['time']['agent_partition']['status'],'partial_due_to_event_pairing_issues')

    def test_overlap_conservation(self):
        v=a.partition((0,10),{'request':[(1,6),(3,8)],'tool':[(5,9)]})
        self.assertEqual(v['exclusive_ns'],{'uncovered':2,'request':4,'request+tool':3,'tool':1});self.assertEqual(v['residual_ns'],0)

    def test_resource_missing_reset_mixed(self):
        pts=[{'t_monotonic_ns':t*a.NS,'clock_domain':'system_monotonic','container':reading(t),'host_agent':{},'read_wall_ns':100} for t in [0,1,2]]
        r=a.sample_resources(pts,{'agent':[(int(.5*a.NS),int(1.5*a.NS))]}, {'request':[(int(.5*a.NS),int(1.5*a.NS))]})
        self.assertAlmostEqual(r['cpu_partition']['phase_core_s']['mixed_boundary'],.2);self.assertIsNone(r['host_rss_peak_bytes'])
        pts[1]['container']['cpu_usage_usec']=None;pts[1]['container']['mem_current_bytes']=None
        r=a.sample_resources(pts,{},{});self.assertIsNone(r['cpu_core_s']);self.assertEqual(r['missing_reads']['mem_current_bytes'],1)
        pts[1]['container']['cpu_usage_usec']=300000;r=a.sample_resources(pts,{},{});self.assertIsNone(r['cpu_core_s']);self.assertEqual(r['counter_regressions']['cpu_usage_usec'],1)

    def test_identity_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);f=root/a.ENV/'frozen-identity.json';s=a.old.load_json(f);s['identity']['collection']='old';write(f,s)
            self.assertRaises(ValueError,a.analyze,root,root/'bad')

    def test_zero_and_missing_distribution(self):
        self.assertEqual(a.distribution([0,None,False])['n'],1)
        self.assertEqual(a.distribution([0,None,False])['missing_or_invalid'],2)
        self.assertEqual(a.distribution([0,None])['median'],0)

    def test_resource_anomalies_through_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);b=a.old.load_json(root/a.REPORT/'batch-summary.json')
            p=root/a.RAW/b['results'][0]['run_id']/'summary.json';s=a.old.load_json(p)
            s['samples'][2]['container']['cpu_usage_usec']=None
            s['samples'][3]['container']['cpu_usage_usec']=99999999
            for x in s['samples']:
                x['container']['mem_current_bytes']=None;x['host_agent']['rss_bytes']=None
                x.pop('read_wall_ns')
            write(p,s);reseal(root);a.main(['--root',str(root),'--output',str(root/'out')])
            r=json.loads((root/'out/per_run.jsonl').read_text().splitlines()[0]);z=r['resources']
            self.assertIsNone(z['cpu_core_s']);self.assertIsNone(z['memory_current_peak_bytes']);self.assertIsNone(z['host_rss_peak_bytes'])
            self.assertIsNone(z['collector_read_wall_s']);self.assertIsNone(r['phase_boundary_changes']['agent']['cpu_core_s'])
            self.assertTrue(z['cpu_partition']['invalid_interval_indices'])

    def test_registered_interpreter_symlink_through_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';root.mkdir();fixture(root)
            outside=Path(d)/'python-binary';outside.write_bytes(b'synthetic interpreter, never executed')
            link=root/'.venvs/pilot/bin/python';link.parent.mkdir(parents=True);link.symlink_to(outside)
            m=root/a.REPORT/'batch-manifest.json';data=a.old.load_json(m);data['inputs'].append(a.file_record(root,link));write(m,data)
            vm=root/a.REPORT/'VALIDATION-MANIFEST.json';v=a.old.load_json(vm);v['inputs']=[a.file_record(root,m)];write(vm,v)
            self.assertEqual(a.main(['--root',str(root),'--output',str(root/'out')]),0)
            inputs=a.old.load_json(root/'out/manifest.json')['inputs'];self.assertIn('.venvs/pilot/bin/python',[x['path'] for x in inputs])

    def test_absent_resources_complete_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);b=a.old.load_json(root/a.REPORT/'batch-summary.json')
            p=root/a.RAW/b['results'][0]['run_id']/'summary.json';s=a.old.load_json(p);s['samples']=[];write(p,s);reseal(root)
            a.main(['--root',str(root),'--output',str(root/'out')]);s=a.old.load_json(root/'out/summary.json')
            m=s['by_task'][a.TASKS[0]]['metrics']['cpu_core_s'];self.assertEqual(m['n'],2);self.assertEqual(m['missing_or_invalid'],1)


if __name__=='__main__':unittest.main()
