"""Complete the five-case remote pilot and bound output-length feature probes."""
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

from scripts.agentx_deepseek_pilot import ROOT,BASE,MODEL,canonical,sha,dump,lines,file_record,stamp,request,worker_environment,adapt_payload
from scripts.agentx_deepseek_branch_prepare import key,compile_edges,validate_dag
from scripts.agentx_deepseek_branches import schedule,verify_code

RAW=ROOT/'data/raw/agentx-deepseek-coverage-01'
ENV=ROOT/'env/agentx-deepseek-coverage-01'
CASES=[('serial_intervals','240cd2e1b10e5b738ac6fee166b2aca7eff2',20),
       ('long_context','5df1df5ca50cef4a3c01d7b3e281e2c852f1',26)]


def length_probes():
    base={'model':MODEL,'messages':[{'role':'user','content':'Reply only with OK.'}],
          'max_tokens':64,'stream':True,'stream_options':{'include_usage':True},'thinking':{'type':'disabled'},'temperature':0}
    return [{'name':name,'payload':{**copy.deepcopy(base),**extra}} for name,extra in
            [('control',{}),('min_tokens',{'min_tokens':64}),('ignore_eos',{'ignore_eos':True})]]


def compile_offline(source_root):
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',
        HF_HUB_CACHE=str(source_root/'data/raw/agentx-replay-smoke-01/hf-cache'),TOKENIZERS_PARALLELISM='false',AIPERF_DATASET_WEKA_PARALLEL_WORKERS='1')
    from aiperf.config import BenchmarkConfig,BenchmarkRun
    from aiperf.common import random_generator as rng
    from aiperf.common.tokenizer import Tokenizer
    from aiperf.dataset.generator.prompt import PromptGenerator
    from aiperf.dataset.loader.weka_trace import WekaTraceLoader
    config_path=source_root/'data/raw/agentx-replay-smoke-01/attempts/03-full-sample/harness/profile_export_aiperf.json'
    cfg=BenchmarkConfig.model_validate(json.loads(config_path.read_text())['input_config'])
    assert cfg.get_default_dataset().ignore_trace_delays
    run=BenchmarkRun(benchmark_id='offline-remaining-cases',cfg=cfg,artifact_dir=RAW/'offline-loader',random_seed=42,cli_command=None)
    rng.init(42);tokenizer=Tokenizer.from_pretrained('Qwen/Qwen3-0.6B',revision='c1899de289a04d12100db370d81485cdf75e47ca')
    pg=PromptGenerator(prompts=None,prefix_prompts=None,tokenizer=tokenizer)
    loader=WekaTraceLoader(filename=str(source_root/'data/raw/agentx-replay-smoke-01/sessions'),run=run,prompt_generator=pg)
    all_data=loader.load_dataset();convs=loader.convert_to_conversations({trace:all_data[trace] for _,trace,_ in CASES})
    return [q.to_metadata().model_dump(mode='json') for q in convs]


def prepare(source_root):
    source_root=Path(source_root);RAW.mkdir(parents=True,exist_ok=False);ENV.mkdir(parents=True,exist_ok=True)
    metadata=compile_offline(source_root);dump(RAW/'official-metadata.json',metadata)
    source_export=source_root/'data/raw/agentx-replay-smoke-01/attempts/03-full-sample/harness/profile_export_raw.jsonl'
    pinned=json.loads((source_root/'reports/analysis/AGENTX-REPLAY-SMOKE-v1/local-evidence-manifest.json').read_text())
    assert file_record(source_export)['sha256']==next(q['sha256'] for q in pinned['files'] if q['path']==str(source_export))
    captures=lines(source_export)
    native={(q['trace_id'],q['outer_idx'],q['inner_idx']):q for q in lines(source_root/'data/raw/agentx-replay-smoke-01/source_requests.jsonl')}
    cases=[]
    for label,trace,count in CASES:
        current=[q for q in metadata if q['conversation_id']==trace or q['conversation_id'].startswith(trace+'::')]
        deps,edges,parents=compile_edges(current)
        records=[q for q in captures if q['metadata']['source_trace_id']==trace]
        lookup={key(q['metadata']['conversation_id'],q['metadata']['turn_index']):q for q in records};nodes=[]
        for conv in current:
            for i,turn in enumerate(conv['turns']):
                nid=key(conv['conversation_id'],i);q=lookup[nid];m=q['metadata']
                assert (turn['source_trace_id'],turn['source_outer_idx'],turn['source_inner_idx'])==(m['source_trace_id'],m['source_outer_idx'],m.get('source_inner_idx'))
                source=native[(trace,m['source_outer_idx'],m.get('source_inner_idx'))]
                payload=adapt_payload(q['payload']);assert payload['max_tokens']==source['output_tokens']
                body=canonical(payload);path=RAW/'frozen-requests'/label/f'{len(nodes):03d}.json.gz';path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(gzip.compress(body,mtime=0))
                nodes.append({'node_id':nid,'index':len(nodes),'conversation_id':conv['conversation_id'],'turn_index':i,
                    'parent_conversation_id':parents.get(conv['conversation_id']),'depends_on':sorted(deps[nid]),'trace_id':trace,
                    'source_outer_idx':source['outer_idx'],'source_inner_idx':source['inner_idx'],'source_pointer':source['pointer'],
                    'source_request_sha256':source['source_request_sha256'],'source_input_tokens':source['input_tokens'],
                    'source_output_tokens':source['output_tokens'],'body_sha256':sha(body),'messages_sha256':sha(canonical(payload['messages'])),
                    'body_bytes':len(body),'payload':str(path)})
        assert len(nodes)==len(records)==len(lookup)==count
        layers=validate_dag(nodes)
        cases.append({'label':label,'trace_id':trace,'requests':count,'execution_chains':len(current),
            'native_subagent_groups':len({q['source_outer_idx'] for q in nodes if q['source_inner_idx'] is not None}),
            'source_input_token_sum':sum(q['source_input_tokens'] for q in nodes),'output_token_limit_sum':sum(q['source_output_tokens'] for q in nodes),
            'max_source_input_plus_output':max(q['source_input_tokens']+q['source_output_tokens'] for q in nodes),
            'edges':edges,'topological_layers':layers,'nodes':nodes})
    plan={'schema':'agentx-deepseek-coverage-plan-v1','created_at_shanghai':stamp(),'endpoint':BASE+'/chat/completions',
        'model':MODEL,'thinking':'disabled','temperature':0,'probe_requests':3,'profile_requests':46,'request_count_limit':49,
        'probes':length_probes(),'maximum_inflight_requests':8,'request_total_timeout_s':900,'read_timeout_s':120,'wall_limit_s':2400,
        'automatic_retries':0,'profile_failure_policy':'stop new dispatch on failed response, drain in-flight requests, stop batch; never truncate input or silently retry',
        'probe_policy':'control must succeed; experimental fields may return HTTP 400/422 as a capability result; stop on auth/transport/quota failures',
        'source_timing_reproduced':False,'model_outputs_fed_back':False,'server_resources_collected':False,'context_truncation_allowed':False,
        'cases_run':'serial_intervals first, then long_context; no overlap across cases',
        'source_export':file_record(source_export),'official_metadata':file_record(RAW/'official-metadata.json'),
        'code':[file_record(ROOT/'scripts'/name) for name in ['agentx_deepseek_complete.py','agentx_deepseek_pilot.py','agentx_deepseek_branches.py','agentx_deepseek_branch_prepare.py']],
        'cases':cases}
    dump(ENV/'plan.json',plan)
    print(json.dumps([{k:q[k] for k in ['label','requests','execution_chains','source_input_token_sum','output_token_limit_sum','max_source_input_plus_output']} for q in cases],indent=2))


def acceptable_probe(result,name):
    if name=='control':return result['status']=='completed'
    return result['status']=='completed' or (result['status']=='http_error' and result.get('http_status') in [400,422])


async def worker(out):
    import aiohttp
    plan=json.loads((ENV/'plan.json').read_text());verify_code(plan)
    secret=os.environ.get('DEEPSEEK_API_KEY')
    if not secret:raise ValueError('credential absent')
    timeout=aiohttp.ClientTimeout(total=plan['request_total_timeout_s'],connect=20,sock_read=plan['read_timeout_s'])
    async with aiohttp.ClientSession(timeout=timeout,connector=aiohttp.TCPConnector(limit=8),trust_env=True,auto_decompress=False) as session:
        for i,probe in enumerate(plan['probes']):
            directory=out/f"probe-{probe['name']}";directory.mkdir()
            r=await request(session,probe['payload'],{'phase':'probe','sequence':i,'probe_name':probe['name']},directory,secret)
            if not acceptable_probe(r,probe['name']):return 1
        for case in plan['cases']:
            directory=out/case['label'];directory.mkdir()
            dump(directory/'case-started.json',{'case':case['label'],'started_at_shanghai':stamp(),'monotonic_ns':time.monotonic_ns()})
            async def send(node):
                body=gzip.decompress(Path(node['payload']).read_bytes())
                if sha(body)!=node['body_sha256']:raise ValueError('frozen body changed')
                identity={k:node[k] for k in ['node_id','index','trace_id','source_outer_idx','source_inner_idx','source_pointer',
                    'source_request_sha256','source_input_tokens','source_output_tokens','conversation_id','turn_index','parent_conversation_id','depends_on']}
                identity.update(phase='profile',sequence=node['index']+1,case=case['label'])
                return await request(session,json.loads(body),identity,directory,secret)
            results=await schedule(case['nodes'],send,8);dump(directory/'dispatch-results.json',results)
            dump(directory/'case-ended.json',{'case':case['label'],'ended_at_shanghai':stamp(),'monotonic_ns':time.monotonic_ns(),
                'completed':sum(q['status']=='completed' for q in results.values()),'planned':len(case['nodes'])})
            if any(q['status']!='completed' for q in results.values()):return 1
    return 0


def run(name):
    import psutil
    if not name or '/' in name or name in ['.','..']:raise ValueError('invalid attempt name')
    plan=json.loads((ENV/'plan.json').read_text());verify_code(plan)
    assert plan['endpoint']==BASE+'/chat/completions' and plan['profile_requests']==46 and plan['probe_requests']==3
    out=RAW/'attempts'/name;out.mkdir(parents=True,exist_ok=False)
    env=worker_environment();command=[sys.executable,'-B',str(Path(__file__)),'worker','--output',str(out)]
    dump(out/'environment.json',{'python':sys.version,'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
        'environment_names_passed':sorted(env),'credential_present':bool(env.get('DEEPSEEK_API_KEY')),
        'proxy_present':bool(env.get('HTTPS_PROXY') or env.get('https_proxy')),'credential_values_recorded':False})
    metadata={'schema':'agentx-deepseek-coverage-attempt-v1','name':name,'started_at_shanghai':stamp(),'plan':file_record(ENV/'plan.json'),
        'command':command,'sampler_parent_pid':os.getpid(),'sampler_scope':'owned HTTP worker and descendants only; parent excluded','sample_sleep_s':.2}
    dump(out/'attempt.json',metadata);process=None;start=time.monotonic();previous=None
    try:
        with (out/'worker.stdout').open('w') as stdout,(out/'worker.stderr').open('w') as stderr:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        owned=psutil.Process(process.pid);metadata['worker_pid']=process.pid;dump(out/'attempt.json',metadata)
        with (out/'client_resources.jsonl').open('w') as stream:
            last_notice=0
            while process.poll() is None:
                now=time.monotonic();cpu=0.;rss=0;pids=[]
                try:members=[owned,*owned.children(recursive=True)]
                except psutil.NoSuchProcess:members=[]
                for member in members:
                    try:
                        c=member.cpu_times();cpu+=c.user+c.system;rss+=member.memory_info().rss;pids.append(member.pid)
                    except (psutil.NoSuchProcess,psutil.AccessDenied):continue
                stream.write(json.dumps({'monotonic_ns':time.monotonic_ns(),'elapsed_s':now-start,'pids':pids,'rss_bytes':rss,'cpu_seconds':cpu,
                    'cpu_percent_one_core':None if previous is None else max(0.,100*(cpu-previous[1])/(now-previous[0]))},separators=(',',':'))+'\n')
                stream.flush();previous=(now,cpu)
                if now-start>plan['wall_limit_s']:raise TimeoutError('coverage pilot wall limit')
                if now-start-last_notice>=15:
                    counts={p.parent.name:len(lines(p)) for p in out.glob('*/requests.jsonl')}
                    print(json.dumps({'elapsed_s':round(now-start,1),'finished_requests':counts}),flush=True);last_notice=now-start
                time.sleep(.2)
        metadata.update(exit_code=process.returncode,status='completed' if process.returncode==0 else 'stopped_after_failure')
    except BaseException as error:metadata.update(status='orchestration_error',error_type=type(error).__name__);raise
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
    q=s.add_parser('prepare');q.add_argument('--source-root',type=Path,required=True)
    q=s.add_parser('run');q.add_argument('--name',required=True)
    q=s.add_parser('worker');q.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.source_root)
    elif a.action=='run':raise SystemExit(run(a.name))
    else:raise SystemExit(asyncio.run(worker(a.output)))
