"""Offline fixtures through the complete three-run analysis and SVG/CSV entry."""
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'scripts'), str(Path(__file__).resolve().parents[1] / 'src')]
import volcano_three_chain_characterization as analysis

G = 'deepseek-v4-flash-ga-260731'
S = 'deepseek-v4-flash-0731'
BASE = 1_000_000_000


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(x)+'\n' for x in rows))


def record(path, root):
    return analysis.file_record(path, root)


def sample(t, cpu, mem=1048576, process=False):
    common = {'t_monotonic_ns': BASE+t, 'read_status': {'io':'ok', 'stat':'ok', 'cpu.stat':'ok',
        'memory.current':'ok', 'memory.peak':'ok'}, 'container_id':'c'*64}
    if process:
        common.update(pid=11,starttime_ticks=9,clk_tck=100,cpu_ticks=cpu,rss_bytes=mem,
            process_io={'read_bytes':cpu*10,'write_bytes':cpu*20,'rchar':cpu*30,'wchar':cpu*40})
    else:
        common.update(cpu_usage_usec=cpu,mem_current_bytes=mem,mem_peak_bytes=mem*2,
                      io_read_bytes=cpu*2,io_write_bytes=cpu*3)
    return common


def event(kind, eid, status, t, **attrs):
    return {'kind':kind,'event_id':eid,'status':status,'t_monotonic_ns':BASE+t,
            'clock_domain':'system_monotonic','attrs':attrs}


def fixture(root, *, cpu_scale=1, office_tools=1):
    """Save all three native archive formats, not a mocked successful summary."""
    central_rows=[];central_inputs=[]
    for chain,col,run,env in analysis.RUNS:
        b=root/'data/raw/generated'/col/run;d=root/'reports/resource'/col;e=root/'env'/env
        b.mkdir(parents=True);d.mkdir(parents=True);e.mkdir(parents=True,exist_ok=True)
        identity={'collection':col,'code_and_runtime_files':[],'fixture':'synthetic, never executed'}
        digest=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=chain=='Office',separators=(',',':')).encode()).hexdigest()
        plan={'identity':identity,'identity_sha256':digest}
        write(e/'plan-identity.json',plan);write(e/'frozen-identity.json',plan)
        write(d/'APPROVAL.json',{'identity_sha256':digest,'collection':col})
        write(b/'environment.json',{'sc_clk_tck':100})
        container=[sample(i*1_000_000_000,i*1_000_000*cpu_scale) for i in range(3)]
        process=[sample(i*1_000_000_000,i*100,process=True) for i in range(3)]
        events=[event('run','root','open',0)]
        count=2 if chain!='Office' else office_tools+1
        for i in range(count):
            events += [event('llm_request',f'r{i}','open',100_000_000+i*300_000_000,role='user' if chain=='Assistant' and i==count-1 else 'agent'),
                       event('llm_request',f'r{i}','closed',200_000_000+i*300_000_000,response_model=G if i==0 else S,transport_attempt_count=1)]
        if chain=='Office':
            for i in range(2+office_tools):
                attrs={'tool_name':'get_task_metadata' if i==0 else 'inspect_document','role':'bootstrap' if i<2 else 'agent'}
                events += [event('tool_call',f't{i}','open',100_000_000+i*100_000_000,**attrs),
                           event('tool_call',f't{i}','closed',150_000_000+i*100_000_000,ok=True,result_sha256='safe')]
            events.append(event('agent_action','finish','point',1_900_000_000,action='finish'))
            life=[]
            for name,start,end in [('agent_setup',0,100_000_000),('agent',100_000_000,1_900_000_000),('verifier',2_000_000_000,2_100_000_000),('harbor_stop',2_200_000_000,2_300_000_000),('archive',2_400_000_000,2_450_000_000)]:
                ends=('begin','done') if name in ('agent_setup','harbor_stop','archive') else ('begin','end')
                for suffix,t in zip(ends,(start,end)):life.append({'phase':name+'_'+suffix,'t_monotonic_ns':BASE+t})
            life += [{'phase':'removal_verified','result':'removed'},{'phase':'image_tag_after_stop','id':'fixed','present':True}]
            summary={'identity_sha256':digest,'wall_s':3,'container':{'id':'c'*64},
                     'samples':[{'t_monotonic_ns':x['t_monotonic_ns'],'container':x,'host_agent':process[i]} for i,x in enumerate(container)],
                     'events':life,'measurement':{'collector':{'read_wall_ns':10}},
                     'outcome':{'phases':{'agent':{'status':'finish'},'verifier':{'reward':1}},'infra_failures':[]}}
            write(b/'summary.json',summary);report={'summary':summary,'exit_code':0}
            jsonl(b/'agent/events.jsonl',events+[event('run','root','closed',2_000_000_000)])
            tool_count=2+office_tools
        elif chain=='Coding':
            for row in events:
                if row['kind']=='llm_request' and row['status']=='closed':
                    row['attrs']['response_model']='wrong_event_field_not_the_saved_response'
            write(b/'metadata.json',{'identity_sha256':digest})
            ev={};scopes={}
            for kind,shift,tag in [('agent_container',0,'agent'),('verifier_container',2_200_000_000,'verifier')]:
                rows=[dict(x,t_monotonic_ns=x['t_monotonic_ns']+shift) for x in container]
                ev[tag]={'scope_kind':kind,'scope':tag,'boundary_start':rows[0],'boundary_end':rows[-1],
                         'samples':rows[1:2],'interval_target_s':.5}
                events.append(event('container',tag,'point',shift,scope=tag,action='start',container_id='c'*64))
            write(b/'samples.json',{'evidence':ev,'scopes':scopes,'collector':{'read_wall_ns':20}})
            write(b/'host_process.jsonl',{'records':process,'summary':{'scope':'mini_child','clk_tck':100,'collector':{'read_wall_ns_total':5}}})
            native=[];messages=[]
            for i in range(2):
                native += [{'event':'open','event_id':f't{i}','tool_call_id':f'call{i}','t_start_ns':BASE+300_000_000+i*600_000_000},
                    {'event':'closed' if i==0 else 'error','event_id':f't{i}','tool_call_id':f'call{i}',
                     't_end_ns':BASE+400_000_000+i*600_000_000,'exception_type':None if i==0 else 'Submitted','returncode':0 if i==0 else None}]
                messages.append({'role':'assistant','tool_calls':[{'id':f'call{i}','function':{'name':'bash','arguments':json.dumps({'command':'python -m pytest' if i==0 else 'echo done'})}}],
                                 'extra':{'response':{'model':G if i==0 else S}}})
            jsonl(b/'mini_tool_events.jsonl',native);write(b/'mini_trajectory.json',{'info':{'exit_status':'Submitted'},'messages':messages})
            jsonl(b/'events.jsonl',events+[event('run','root','closed',4_500_000_000)])
            report={'budget_usage':{'elapsed_total_s':4.5},'resolved':True,'execution_status':'ok','evaluation_status':'ok','archive_status':'ok','cleanup_status':'ok','cleanup_errors':[]}
            tool_count=2
        else:
            for i,name in enumerate(('search_contacts','end_conversation')):
                events += [event('tool_call',f't{i}','open',300_000_000+i*600_000_000,tool_name=name,role='agent' if i==0 else 'user'),
                           event('tool_call',f't{i}','closed',400_000_000+i*600_000_000,ok=True,result_sha256='safe')]
            jsonl(b/'events.jsonl',events+[event('run','root','closed',2_000_000_000)])
            jsonl(b/'samples.jsonl',process)
            boundaries=[{'phase':name,**sample(t,i*100,process=True)} for i,(name,t) in enumerate([
                ('worker_start',0),('imports_begin',0),('imports_end',100_000_000),('play_begin',200_000_000),('system_setup_exec',300_000_000),
                ('play_end',1_300_000_000),('evaluate_begin',1_400_000_000),('evaluate_end',1_900_000_000),('worker_end',2_000_000_000)])]
            jsonl(b/'boundaries.jsonl',boundaries)
            report={'parent_start_ns':BASE,'wall_s':2.5,'worker_window_wall_s':2.4,'exit_code':0,
                    'cleanup':{'checked_monotonic_ns':BASE+2_400_000_000},'worker_result':{'stop':{'reason':'user_end_conversation'},'failure':None},
                    'evaluation':{'similarity':.8}}
            tool_count=2
        report.update(identity_sha256=digest,run_id=run)
        write(d/'run-report.json',report)
        marker={'run_id':run,'identity_sha256':digest,'started_at_monotonic_ns':BASE}
        if chain=='Coding':write(d/'ATTEMPT_STARTED.json',marker)
        else:
            write(b/'ATTEMPT_STARTED.json',marker);write(b/'ATTEMPT_COMPLETED.json',marker)
        network=[]
        for i in range(3):network.append({'t_monotonic_ns':BASE+i*1_000_000_000,'namespace_id':'net:[synthetic]',
            'namespace_status':'observed','read_status':'observed',
            'interfaces':{'eth0':{'rx_bytes':i*1048576,'tx_bytes':i*2048},'lo':{'rx_bytes':i*99999999,'tx_bytes':i*99999999}}})
        write(b/'supplemental_measurements.json',{'status':'partial','network':{'samples':network,'read_wall_ns':30,'interval_target_s':.5},
            'task_workspace':{'status':'not_applicable' if chain=='Assistant' else 'observed'},
            'container_disk_footprints':{},'disk_footprint':{'paths':[]}})
        entries=[record(p,b) for p in sorted(b.rglob('*')) if p.is_file()]
        rawmanifest={'files':{x['path']:x['sha256'] for x in entries}} if chain=='Coding' else {'identity_sha256':digest,'run_id':run,'outputs' if chain=='Office' else 'files':entries}
        write(b/'manifest.json',rawmanifest)
        write(d/'manifest.json',{'identity_sha256':digest,'inputs':[record(p,root) for p in (e/'plan-identity.json',e/'frozen-identity.json',d/'APPROVAL.json',b/'manifest.json')],
                                'outputs':[record(d/'run-report.json',root)]})
        central_rows.append({'chain':chain,'run_id':run,'identity_sha256':digest,'logical_requests':count,
            'response_models':{G:1,S:count-1},'tool_pairs':tool_count,'entry_returncode':7 if chain=='Coding' else 0})
        central_inputs += [record(d/'manifest.json',root)]
    write(root/analysis.CENTRAL/'validation-closeout.json',{'runs':central_rows})
    md=root/analysis.CENTRAL/'validation-summary.md';md.write_text('\n'.join(x[2] for x in analysis.RUNS))
    write(root/analysis.CENTRAL/'validation-manifest.json',{'inputs':central_inputs,
        'outputs':[record(md,root),record(root/analysis.CENTRAL/'validation-closeout.json',root)]})


def tree(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


class CharacterizationTests(unittest.TestCase):
    def test_full_entry_generates_svg_csv_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';fixture(root);before=tree(root);out=Path(tmp)/'report'
            with patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
                result=analysis.build(root,out)
            self.assertEqual(before,tree(root));self.assertEqual(len(result['runs']),3)
            for r in result['runs']:
                svg=ElementTree.parse(out/r['figure']);self.assertTrue(svg.findall('.//{*}path[@class="data"]'))
                self.assertIn('Shared netns', (out/r['figure']).read_text())
                with (out/r['series_csv']).open() as stream:rows=list(csv.DictReader(stream))
                self.assertTrue(rows);self.assertTrue(all(x['source'] and x['locator'] for x in rows))
            coding=result['runs'][1]['behavior']
            self.assertEqual(len(coding['tools']),2);self.assertEqual(coding['control_flow_terminals'],1)
            self.assertEqual(coding['ordinary_tool_errors'],0);self.assertEqual(coding['response_models'],{G:1,S:1})
            self.assertEqual(result['runs'][0]['behavior']['tools_by_role'],{'bootstrap':2,'agent':1})
            manifest=json.loads((out/'manifest.json').read_text())
            self.assertNotIn('manifest.json',[x['path'] for x in manifest['outputs']])
            for row in manifest['outputs']:self.assertEqual(record(out/row['path'],out),row)

    def test_cpu_io_units_and_scope_isolation(self):
        rows=[sample(0,0),sample(2_000_000_000,1_000_000)]
        stats,series=analysis.scope_projection(rows,scope='A',kind='container',source='raw',locations=['0','1'])
        self.assertEqual(next(x for x in series if x['metric']=='cpu')['value'],.5)
        self.assertEqual(next(x for x in series if x['metric']=='io_read_bytes')['value'],1_000_000)
        self.assertEqual(stats['memory_sampled_peak_bytes'],1048576)
        self.assertEqual(next(x for x in series if x['metric']=='memory.current')['value'],1)
        process=[sample(0,0,process=True),sample(2_000_000_000,50,process=True)]
        _,other=analysis.scope_projection(process,scope='B',kind='host',source='raw',locations=['0','1'],process=True)
        self.assertEqual(next(x for x in other if x['metric']=='cpu')['value'],.25)
        self.assertEqual({x['scope'] for x in other},{'B'})

    def test_missing_zero_reset_identity_and_gap_not_connected(self):
        rows=[sample(i*1_000_000_000,i*100,mem=0) for i in range(5)]
        rows[1]['read_status']['cpu.stat']='permission_denied';rows[1]['read_status']['memory.current']='permission_denied'
        rows[3]['cpu_usage_usec']=0;rows[4]['container_id']='new'
        stats,series=analysis.scope_projection(rows,scope='A',kind='container',source='raw',locations=list('abcde'))
        cpu=[x for x in series if x['metric']=='cpu']
        self.assertTrue(all(x['status']=='gap' for x in cpu))
        mem=[x for x in series if x['metric']=='memory.current']
        self.assertEqual(mem[0]['value'],0);self.assertIsNone(mem[1]['value']);self.assertIsNone(mem[-1]['value'])
        run={'chain':'X','run_id':'fixture','origin_monotonic_ns':BASE,'origin_source':'fixture', 'attempt_wall_s':5,'phases':[]}
        doc=ElementTree.fromstring(analysis.render_svg(run,series))
        paths=[x.attrib['d'] for x in doc.findall('.//{*}path[@class="data"]')]
        # Memory 0→2s must not be connected across the failed 1s read.
        self.assertFalse(any('M85.000' in d and 'L' in d for d in paths))
        self.assertEqual(stats['metric_quality']['cpu']['gap'],4)

    def test_network_deterministic_top3_no_interface_sum(self):
        samples=[]
        for i in range(3):samples.append({'t_monotonic_ns':BASE+i*1_000_000_000,'namespace_id':'n','namespace_status':'observed','read_status':'observed',
            'interfaces':{name:{'rx_bytes':i*n,'tx_bytes':0} for name,n in [('lo',999),('b',10),('a',10),('c',5),('d',1)]}})
        stats,series=analysis.project_network(samples,'raw')
        self.assertEqual(stats['selected_interfaces'],['a','b','c']);self.assertEqual(stats['interfaces']['a']['rx_bytes']['full_window_delta_bytes'],20)
        self.assertEqual({x['scope'] for x in series},{'a','b','c'});self.assertNotIn('total',stats)
        samples[1]['namespace_id']='other';stats,_=analysis.project_network(samples,'raw');self.assertEqual(stats['selected_interfaces'],[])

    def test_duplicate_time_and_missing_memory_remain_gaps(self):
        rows=[sample(0,0),sample(0,20),sample(1_000_000_000,30)]
        rows[2]['mem_current_bytes']=None
        summary,data=analysis.scope_projection(rows,scope='A',kind='container',source='raw',locations=['a','b','c'])
        self.assertEqual(summary['nonincreasing_times'],1)
        cpu=[x for x in data if x['metric']=='cpu']
        self.assertEqual(cpu[0]['reason'],'nonpositive_or_invalid_time_delta')
        self.assertEqual(cpu[1]['status'],'valid')
        self.assertEqual(summary['memory_gap_points'],2)

    def test_input_change_changes_complete_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root/'a');fixture(root/'b',cpu_scale=2,office_tools=2)
            a=analysis.build(root/'a',root/'out-a');b=analysis.build(root/'b',root/'out-b')
            self.assertEqual(b['runs'][0]['scopes'][0]['metric_quality']['cpu']['full_window_delta'],2*a['runs'][0]['scopes'][0]['metric_quality']['cpu']['full_window_delta'])
            self.assertNotEqual(a['runs'][0]['behavior']['logical_requests'],b['runs'][0]['behavior']['logical_requests'])
            self.assertNotEqual((root/'out-a/summary.md').read_text(),(root/'out-b/summary.md').read_text())

    def test_input_hash_tampering_refused_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';fixture(root);col,run=analysis.RUNS[0][1:3]
            (root/'data/raw/generated'/col/run/'summary.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'mismatch'):analysis.build(root,Path(tmp)/'out')
            self.assertFalse((Path(tmp)/'out').exists())

    def test_missing_ids_and_duplicate_events_not_silently_paired(self):
        events=[event('tool_call','id','open',0),event('tool_call','id','open',1),event('tool_call','id','closed',2),event('tool_call',None,'open',3)]
        _,quality=analysis.pairs(events)
        self.assertTrue(quality['duplicate_open']);self.assertTrue(quality['missing_id'])


if __name__=='__main__':unittest.main()
