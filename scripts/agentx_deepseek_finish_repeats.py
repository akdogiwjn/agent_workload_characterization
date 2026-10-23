"""Complete three remaining frozen AgentX workloads; remote inference, owned-client metrics only."""
from __future__ import annotations

import argparse
import asyncio
import copy
import gzip
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from scripts.agentx_deepseek_pilot import ROOT, BASE, MODEL, canonical, sha, dump, lines, file_record, stamp, request, worker_environment
from scripts.agentx_deepseek_branches import schedule, verify_code
from scripts.agentx_deepseek_branch_prepare import validate_dag

RAW = ROOT/'data/raw/agentx-deepseek-five-repeats-01'
ENV = ROOT/'env/agentx-deepseek-five-repeats-01'
BASELINE = Path('/home/lcq/agentx_deepseek_pilot_20261023')
BRANCHES = Path('/home/lcq/agentx_deepseek_branches_20261023')
COVERAGE = Path('/home/lcq/agentx_deepseek_coverage_20261023')
RUNS = [('single_subagent', 2), ('serial_intervals', 2), ('long_context', 2), ('long_context', 3), ('serial_intervals', 3), ('single_subagent', 3)]


def prepare():
    branch_path = BRANCHES/'env/agentx-deepseek-branches-01/plan.json'
    coverage_path = COVERAGE/'env/agentx-deepseek-coverage-01/plan.json'
    branch = json.loads(branch_path.read_text())
    coverage = json.loads(coverage_path.read_text())
    cases = [copy.deepcopy(next(q for q in branch['cases'] if q['label']=='single_subagent'))]
    cases += copy.deepcopy(coverage['cases'])
    assert [q['label'] for q in cases]==['single_subagent','serial_intervals','long_context']
    assert sum(q['requests'] for q in cases)==67
    target = RAW/'frozen-requests'
    target.mkdir(parents=True, exist_ok=False)
    for case in cases:
        validate_dag(case['nodes'])
        for node in case['nodes']:
            body = gzip.decompress(Path(node['payload']).read_bytes())
            assert sha(body)==node['body_sha256']
            payload = json.loads(body)
            assert payload['model']==MODEL and payload['thinking']=={'type':'disabled'} and payload['temperature']==0
            assert payload['max_tokens']==node['source_output_tokens']
            node['original_payload'] = file_record(node['payload'])
            path = target/f"{case['label']}-{node['index']:03d}.json.gz"
            path.write_bytes(gzip.compress(body, mtime=0))
            node['payload'] = str(path)
    ENV.mkdir(parents=True, exist_ok=True)
    plan = {'schema':'agentx-deepseek-repeats-plan-v1', 'created_at_shanghai':stamp(),
            'endpoint':BASE+'/chat/completions', 'model':MODEL, 'thinking':'disabled', 'temperature':0,
            'runs':[{'name':f'{i+1:02d}-{label}-r{r}', 'case':label, 'replicate':r} for i,(label,r) in enumerate(RUNS)],
            'profile_requests':134, 'probe_requests':6, 'request_count_limit':140,
            'maximum_inflight_requests':8, 'request_total_timeout_s':900, 'read_timeout_s':120, 'wall_limit_s':2400,
            'automatic_retries':0, 'failure_policy':'stop batch on first failed run; drain inflight; retain evidence',
            'source_timing_reproduced':False, 'model_outputs_fed_back':False, 'server_resources_collected':False,
            'context_truncation_allowed':False, 'remote_cache_controlled':False,
            'order':'ABCCBA for the six new runs; historical R1 observations were earlier and not randomized',
            'process_policy':'fresh worker and HTTP session for each new run, one connectivity probe first',
            'historical_difference':'single R1 followed probe; serial R1 followed 3 length probes; long R1 shared process after serial case',
            'original_plans':[file_record(branch_path), file_record(coverage_path)],
            'code':[file_record(ROOT/'scripts'/name) for name in ['agentx_deepseek_finish_repeats.py','agentx_deepseek_pilot.py',
                    'agentx_deepseek_branches.py','agentx_deepseek_branch_prepare.py']], 'cases':cases}
    dump(ENV/'plan.json', plan)
    print(json.dumps({'runs':plan['runs'], 'profile_requests':134, 'probe_requests':6, 'frozen_unique_payloads':67}))


async def worker(out, run_name):
    import aiohttp
    plan=json.loads((ENV/'plan.json').read_text()); verify_code(plan)
    run=next(q for q in plan['runs'] if q['name']==run_name)
    case=next(q for q in plan['cases'] if q['label']==run['case'])
    secret=os.environ.get('DEEPSEEK_API_KEY')
    if not secret:raise ValueError('credential absent')
    timeout=aiohttp.ClientTimeout(total=plan['request_total_timeout_s'],connect=20,sock_read=plan['read_timeout_s'])
    async with aiohttp.ClientSession(timeout=timeout,connector=aiohttp.TCPConnector(limit=8),trust_env=True,auto_decompress=False) as session:
        probe_dir=out/'probe'; probe_dir.mkdir()
        probe={'model':MODEL,'messages':[{'role':'user','content':'Reply only with OK.'}], 'max_tokens':16,
               'stream':True,'stream_options':{'include_usage':True},'thinking':{'type':'disabled'},'temperature':0}
        result=await request(session,probe,{'phase':'probe','sequence':0,'run':run_name},probe_dir,secret)
        if result['status']!='completed':return 1
        directory=out/case['label']; directory.mkdir()
        async def send(node):
            body=gzip.decompress(Path(node['payload']).read_bytes())
            if sha(body)!=node['body_sha256']:raise ValueError('frozen body changed')
            identity={k:node[k] for k in ['node_id','index','trace_id','source_outer_idx','source_inner_idx','source_pointer',
                'source_request_sha256','source_input_tokens','source_output_tokens','conversation_id','turn_index','parent_conversation_id','depends_on']}
            identity.update(phase='profile',sequence=node['index']+1,case=case['label'],replicate=run['replicate'],run=run_name)
            return await request(session,json.loads(body),identity,directory,secret)
        results=await schedule(case['nodes'],send,8)
        dump(directory/'dispatch-results.json',results)
        return 0 if all(q['status']=='completed' for q in results.values()) else 1


def run_one(run_name):
    import psutil
    plan=json.loads((ENV/'plan.json').read_text()); verify_code(plan)
    run=next(q for q in plan['runs'] if q['name']==run_name)
    out=RAW/'attempts'/run_name; out.mkdir(parents=True,exist_ok=False)
    env=worker_environment()
    command=[sys.executable,'-B',str(Path(__file__)),'worker','--name',run_name,'--output',str(out)]
    dump(out/'environment.json',{'python':sys.version,'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
        'environment_names_passed':sorted(env),'credential_present':bool(env.get('DEEPSEEK_API_KEY')),
        'proxy_present':bool(env.get('HTTPS_PROXY') or env.get('https_proxy')),'credential_values_recorded':False})
    metadata={'schema':'agentx-deepseek-repeat-attempt-v1',**run,'started_at_shanghai':stamp(),'plan':file_record(ENV/'plan.json'),
        'command':command,'sampler_parent_pid':os.getpid(),'sampler_scope':'owned HTTP worker and descendants only; parent excluded', 'sample_sleep_s':.2}
    process=None; start=time.monotonic(); previous=None; dump(out/'attempt.json',metadata)
    try:
        with (out/'worker.stdout').open('w') as stdout,(out/'worker.stderr').open('w') as stderr:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        owned=psutil.Process(process.pid); metadata['worker_pid']=process.pid; dump(out/'attempt.json',metadata)
        with (out/'client_resources.jsonl').open('w') as stream:
            last_notice=0
            while process.poll() is None:
                now=time.monotonic(); cpu=0.; rss=0; pids=[]
                try:members=[owned,*owned.children(recursive=True)]
                except psutil.NoSuchProcess:members=[]
                for member in members:
                    try:
                        c=member.cpu_times(); cpu+=c.user+c.system; rss+=member.memory_info().rss; pids.append(member.pid)
                    except (psutil.NoSuchProcess,psutil.AccessDenied):continue
                stream.write(json.dumps({'monotonic_ns':time.monotonic_ns(),'elapsed_s':now-start,'pids':pids,'rss_bytes':rss,'cpu_seconds':cpu,
                    'cpu_percent_one_core':None if previous is None else max(0.,100*(cpu-previous[1])/(now-previous[0]))},separators=(',',':'))+'\n')
                stream.flush(); previous=(now,cpu)
                if now-start>plan['wall_limit_s']:raise TimeoutError('repeat wall limit')
                if now-start-last_notice>=15:
                    print(json.dumps({'run':run_name,'elapsed_s':round(now-start,1),'finished_requests':{p.parent.name:len(lines(p)) for p in out.glob('*/requests.jsonl')}}),flush=True)
                    last_notice=now-start
                time.sleep(.2)
        metadata.update(exit_code=process.returncode,status='completed' if process.returncode==0 else 'stopped_after_failure')
    except BaseException as error:
        metadata.update(status='orchestration_error',error_type=type(error).__name__); raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL); process.wait(timeout=10)
        metadata.update(elapsed_s=time.monotonic()-start,ended_at_shanghai=stamp(),owned_process_cleanup_confirmed=process is None or process.poll() is not None)
        dump(out/'attempt.json',metadata); print(json.dumps(metadata,ensure_ascii=False),flush=True)
    return metadata.get('exit_code',1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('prepare'); sub.add_parser('run-batch')
    p=sub.add_parser('worker'); p.add_argument('--name',required=True); p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='worker':raise SystemExit(asyncio.run(worker(args.output,args.name)))
    else:
        plan=json.loads((ENV/'plan.json').read_text()); verify_code(plan)
        assert plan['profile_requests']==134 and plan['probe_requests']==6 and plan['endpoint']==BASE+'/chat/completions'
        for item in plan['original_plans']:
            assert file_record(item['path'])['sha256']==item['sha256']
        for run in plan['runs']:
            status=run_one(run['name'])
            if status:raise SystemExit(status)
