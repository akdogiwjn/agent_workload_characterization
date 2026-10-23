"""Execute two frozen branch DAGs through remote DeepSeek, client-only metrics."""
from __future__ import annotations

import argparse
import asyncio
import gzip
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from scripts.agentx_deepseek_pilot import ROOT,MODEL,BASE,canonical,sha,dump,lines,file_record,stamp,request,worker_environment
from scripts.agentx_deepseek_branch_prepare import RAW,ENV,validate_dag


async def schedule(nodes,send,limit=8):
    """Bound concurrency, preserve all dependency edges and drain on failure."""
    validate_dag(nodes)
    done={q['node_id']:asyncio.Event() for q in nodes};failed=asyncio.Event();sem=asyncio.Semaphore(limit)
    results={}
    async def one(node):
        nid=node['node_id']
        await asyncio.gather(*(done[d].wait() for d in node['depends_on']))
        async with sem:
            if failed.is_set():
                results[nid]={'node_id':nid,'status':'not_executed'};done[nid].set();return
            try:result=await send(node)
            except Exception as error:result={'node_id':nid,'status':'scheduler_error','error_type':type(error).__name__}
            results[nid]=result
            if result['status']!='completed':failed.set()
            done[nid].set()
    await asyncio.gather(*(one(q) for q in nodes))
    return results


async def worker(out):
    import aiohttp
    plan=json.loads((ENV/'plan.json').read_text());verify_code(plan)
    secret=os.environ.get('DEEPSEEK_API_KEY')
    if not secret:raise ValueError('credential absent')
    timeout=aiohttp.ClientTimeout(total=plan['request_total_timeout_s'],connect=20,sock_read=plan['read_timeout_s'])
    connector=aiohttp.TCPConnector(limit=plan['maximum_inflight_requests'])
    async with aiohttp.ClientSession(timeout=timeout,connector=connector,trust_env=True,auto_decompress=False) as session:
        probe_dir=out/'probe';probe_dir.mkdir()
        probe={'model':MODEL,'messages':[{'role':'user','content':'Reply only with OK.'}],
            'max_tokens':16,'stream':True,'stream_options':{'include_usage':True},'thinking':{'type':'disabled'},'temperature':0}
        result=await request(session,probe,{'phase':'probe','sequence':0},probe_dir,secret)
        if result['status']!='completed':return 1
        for case in plan['cases']:
            current=out/case['label'];current.mkdir()
            dump(current/'case-started.json',{'label':case['label'],'started_at_shanghai':stamp(),'monotonic_ns':time.monotonic_ns()})
            async def send(node):
                body=gzip.decompress(Path(node['payload']).read_bytes())
                if sha(body)!=node['body_sha256']:raise ValueError('frozen body changed')
                identity={k:node[k] for k in ['node_id','index','trace_id','source_outer_idx','source_inner_idx','source_pointer',
                    'source_request_sha256','source_input_tokens','source_output_tokens','conversation_id','turn_index','parent_conversation_id','depends_on']}
                identity.update(phase='profile',sequence=node['index']+1,case=case['label'])
                return await request(session,json.loads(body),identity,current,secret)
            results=await schedule(case['nodes'],send,plan['maximum_inflight_requests'])
            dump(current/'dispatch-results.json',results)
            dump(current/'case-ended.json',{'label':case['label'],'ended_at_shanghai':stamp(),'monotonic_ns':time.monotonic_ns(),
                'completed':sum(r['status']=='completed' for r in results.values()),'planned':len(case['nodes'])})
            if any(q['status']!='completed' for q in results.values()):return 1
    return 0


def verify_code(plan):
    for q in plan['code']:
        if file_record(q['path'])['sha256']!=q['sha256']:raise ValueError('runtime code changed after plan freeze')


def run(name):
    import psutil
    if not name or '/' in name or name in ['.','..']:raise ValueError('invalid name')
    plan=json.loads((ENV/'plan.json').read_text());verify_code(plan)
    assert plan['endpoint']==BASE+'/chat/completions' and plan['profile_requests']==51
    out=RAW/'attempts'/name;out.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,'-B',str(Path(__file__)),'worker','--output',str(out)]
    env=worker_environment()
    dump(out/'environment.json',{'python':sys.version,'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
        'environment_names_passed':sorted(env),'credential_present':bool(env.get('DEEPSEEK_API_KEY')),
        'proxy_present':bool(env.get('HTTPS_PROXY') or env.get('https_proxy')),'credential_values_recorded':False})
    metadata={'schema':'agentx-deepseek-branch-attempt-v1','name':name,'started_at_shanghai':stamp(),'plan':file_record(ENV/'plan.json'),
        'command':command,'sampler_parent_pid':os.getpid(),'sampler_scope':'owned HTTP worker and descendants only; parent excluded',
        'sample_sleep_s':.2};process=None;start=time.monotonic();previous=None
    dump(out/'attempt.json',metadata)
    try:
        with (out/'worker.stdout').open('w') as stdout,(out/'worker.stderr').open('w') as stderr:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        owned=psutil.Process(process.pid);metadata['worker_pid']=process.pid;dump(out/'attempt.json',metadata)
        with (out/'client_resources.jsonl').open('w') as samples:
            last_notice=0
            while process.poll() is None:
                now=time.monotonic();cpu=0.;rss=0;pids=[]
                try:members=[owned,*owned.children(recursive=True)]
                except psutil.NoSuchProcess:members=[]
                for member in members:
                    try:
                        c=member.cpu_times();cpu+=c.user+c.system;rss+=member.memory_info().rss;pids.append(member.pid)
                    except (psutil.NoSuchProcess,psutil.AccessDenied):continue
                row={'monotonic_ns':time.monotonic_ns(),'elapsed_s':now-start,'pids':pids,'rss_bytes':rss,'cpu_seconds':cpu,
                    'cpu_percent_one_core':None if previous is None else max(0.,100*(cpu-previous[1])/(now-previous[0]))}
                samples.write(json.dumps(row,separators=(',',':'))+'\n');samples.flush();previous=(now,cpu)
                if now-start>plan['wall_limit_s']:raise TimeoutError('branch pilot wall limit')
                if now-start-last_notice>=15:
                    counts={p.parent.name:len(lines(p)) for p in out.glob('*/requests.jsonl')}
                    print(json.dumps({'elapsed_s':round(now-start,1),'finished_requests':counts}),flush=True);last_notice=now-start
                time.sleep(.2)
        metadata.update(exit_code=process.returncode,status='completed' if process.returncode==0 else 'stopped_after_failure')
    except BaseException as error:
        metadata.update(status='orchestration_error',error_type=type(error).__name__);raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
        metadata.update(elapsed_s=time.monotonic()-start,ended_at_shanghai=stamp(),owned_process_cleanup_confirmed=process is None or process.poll() is not None)
        dump(out/'attempt.json',metadata);print(json.dumps(metadata,ensure_ascii=False),flush=True)
    return metadata.get('exit_code',1)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('run');q.add_argument('--name',required=True)
    q=s.add_parser('worker');q.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.action=='run':raise SystemExit(run(a.name))
    raise SystemExit(asyncio.run(worker(a.output)))
