"""Frozen AgentX request replay through the official remote DeepSeek API.

Credentials are read only by the worker, never serialized. No SDK retries,
model tools, server-resource sampling, or shared-checkout mutations.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
from datetime import datetime
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw/agentx-deepseek-pilot-01'
ENV=ROOT/'env/agentx-deepseek-pilot-01'
BASE='https://api.deepseek.com/v1'
MODEL='deepseek-flash'
TRACE='12cfecf98c158ab54fb65980602421f00d69'


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sha(data):return hashlib.sha256(data).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def lines(path):return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
def file_record(path):
    path=Path(path);return {'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path.read_bytes())}
def stamp():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()


def prepare(source_root):
    source_root=Path(source_root)
    verified=source_root/'reports/analysis/AGENTX-REPLAY-SMOKE-v1'
    raw=source_root/'data/raw/agentx-replay-smoke-01/attempts/03-full-sample/harness/profile_export_raw.jsonl'
    expected=json.loads((verified/'local-evidence-manifest.json').read_text())
    wanted=next(q for q in expected['files'] if q['path']==str(raw))
    assert file_record(raw)['sha256']==wanted['sha256'],'source replay export changed'
    selected=[q for q in lines(raw) if q['metadata']['source_trace_id']==TRACE]
    selected.sort(key=lambda q:q['metadata']['turn_index'])
    assert len(selected)==20 and len({q['metadata']['conversation_id'] for q in selected})==1
    assert [q['metadata']['turn_index'] for q in selected]==list(range(20))
    source_rows=lines(source_root/'data/raw/agentx-replay-smoke-01/source_requests.jsonl')
    source={q['outer_idx']:q for q in source_rows if q['trace_id']==TRACE}
    assert set(source)==set(range(20))
    target=RAW/'frozen-requests';target.mkdir(parents=True,exist_ok=False)
    requests=[]
    for i,q in enumerate(selected):
        meta=q['metadata'];native=source[meta['source_outer_idx']]
        payload=adapt_payload(q['payload'])
        assert payload['max_tokens']==native['output_tokens']
        body=canonical(payload);path=target/f'{i:03d}.json.gz'
        with gzip.open(path,'wb') as f:f.write(body)
        requests.append({'index':i,'trace_id':TRACE,'source_outer_idx':meta['source_outer_idx'],
            'source_pointer':native['pointer'],'source_request_sha256':native['source_request_sha256'],
            'source_input_tokens':native['input_tokens'],'source_output_tokens':native['output_tokens'],
            'source_mock_request_id':meta['x_request_id'],'messages_sha256':sha(canonical(payload['messages'])),
            'body_sha256':sha(body),'body_bytes':len(body),'payload':str(path)})
    plan={'schema':'agentx-deepseek-pilot-plan-v1','created_at_shanghai':stamp(),
        'source_export':file_record(raw),'source_trace_id':TRACE,
        'selection_rule':'among the five validated complete sessions, choose fewest requests then trace ID subject to exactly one harness execution chain',
        'endpoint':BASE+'/chat/completions','model':MODEL,'thinking':'disabled','temperature':0,
        'remote_model_version_basis':'official docs 2026-10-23: DeepSeek-V4.1-Flash-1017; alias not immutable',
        'source_tokenizer':'Qwen/Qwen3-0.6B fixed in step 2; NOT claimed to match remote tokenizer',
        'client':'direct aiohttp SSE client over frozen official-harness payloads; no AgentX performance submission',
        'authorization_basis':'user requested remote DeepSeek client-only measurements and said 开始',
        'measurement':'one worker process and its descendants only; sampler parent excluded',
        'sampling_interval_s':0.2,'request_total_timeout_s':180,'read_timeout_s':90,
        'wall_limit_s':1200,'automatic_retries':0,'failure_policy':'stop after first unsuccessful request; preserve all evidence',
        'probe_requests':1,'replay_requests':len(requests),'request_count_limit':21,
        'profile_max_output_sum':sum(q['source_output_tokens'] for q in requests),
        'profile_source_input_sum':sum(q['source_input_tokens'] for q in requests),
        'source_max_input':max(q['source_input_tokens'] for q in requests),
        'source_timing_reproduced':False,'real_output_fed_into_next_request':False,
        'raw_policy':'no Authorization headers or credentials saved; bodies/responses stay ignored locally',
        'requests':requests,'code':file_record(Path(__file__))}
    ENV.mkdir(parents=True,exist_ok=True);dump(ENV/'plan.json',plan)
    print(json.dumps({k:plan[k] for k in ['source_trace_id','replay_requests','profile_max_output_sum','profile_source_input_sum','source_max_input']},ensure_ascii=False))
    return plan


def adapt_payload(original):
    payload=copy.deepcopy(original)
    if set(payload)-{'messages','model','stream','max_completion_tokens','stream_options'}:
        raise ValueError('unreviewed source payload fields')
    payload['model']=MODEL
    payload['max_tokens']=payload.pop('max_completion_tokens')
    payload['thinking']={'type':'disabled'};payload['temperature']=0
    payload['stream']=True;payload['stream_options']={'include_usage':True}
    return payload


class SSEAudit:
    """Count output deltas and final usage without trusting packet boundaries."""
    def __init__(self):
        self.done=False;self.usage=None;self.finish=None;self.response_model=None
        self.content_chars=0;self.reasoning_chars=0;self.content_events=0;self.first_content_s=None
        self.first_reasoning_s=None;self.last_content_s=None;self.response_id=None

    def event(self,data,elapsed):
        if data=='[DONE]':self.done=True;return
        q=json.loads(data)
        if q.get('error'):raise ValueError('provider_error_event')
        self.response_model=q.get('model',self.response_model);self.response_id=q.get('id',self.response_id)
        if q.get('usage') is not None:self.usage=q['usage']
        for choice in q.get('choices',[]):
            delta=choice.get('delta',{});content=delta.get('content') or '';reasoning=delta.get('reasoning_content') or ''
            if delta.get('tool_calls'):raise ValueError('unexpected_tool_call')
            if content:
                if self.first_content_s is None:self.first_content_s=elapsed
                self.last_content_s=elapsed;self.content_chars+=len(content);self.content_events+=1
            if reasoning:
                if self.first_reasoning_s is None:self.first_reasoning_s=elapsed
                self.reasoning_chars+=len(reasoning)
            if choice.get('finish_reason') is not None:self.finish=choice['finish_reason']

    def success(self):
        valid_usage=(isinstance(self.usage,dict) and all(type(self.usage.get(k)) is int and self.usage[k]>=0
                     for k in ['prompt_tokens','completion_tokens','total_tokens']))
        return self.done and valid_usage and self.finish in ['stop','length'] and self.first_content_s is not None and self.reasoning_chars==0


async def request(session,payload,identity,out,secret):
    body=canonical(payload);prefix=out/f"{identity['sequence']:03d}-{identity['phase']}"
    prefix.with_suffix('.request.json.gz').write_bytes(gzip.compress(body,mtime=0))
    start=time.monotonic();started_ns=time.monotonic_ns();audit=SSEAudit();response_bytes=0;status=None
    result={**identity,'started_at_shanghai':stamp(),'started_monotonic_ns':started_ns,
        'request_body_sha256':sha(body),'request_body_bytes':len(body),'requested_max_tokens':payload['max_tokens'],
        'messages_sha256':sha(canonical(payload['messages'])),'status':'started'}
    dump(prefix.with_suffix('.started.json'),result)
    try:
        # Fixed HTTPS origin, no redirects; no credential in URL, command or logs.
        async with session.post(BASE+'/chat/completions',data=body,
                headers={'Authorization':'Bearer '+secret,'Content-Type':'application/json',
                         'Accept':'text/event-stream','Accept-Encoding':'identity'},allow_redirects=False) as response:
            status=response.status
            result.update(http_status=status,headers_received_s=time.monotonic()-start,
                response_request_id=response.headers.get('x-request-id'),provider_date=response.headers.get('date'))
            if status!=200:
                error=(await response.content.read(4096)).decode(errors='replace').replace(secret,'[REDACTED]')
                result.update(status='http_error',error_body=error)
            else:
                data_lines=[]
                with prefix.with_suffix('.response.sse').open('wb') as capture,prefix.with_suffix('.events.jsonl').open('w') as events:
                    async for line in response.content:
                        elapsed=time.monotonic()-start;capture.write(line);response_bytes+=len(line)
                        decoded=line.decode('utf-8').rstrip('\r\n')
                        if decoded.startswith('data:'):data_lines.append(decoded[5:].lstrip(' '))
                        elif not decoded and data_lines:
                            data='\n'.join(data_lines);data_lines=[];audit.event(data,elapsed)
                            events.write(json.dumps({'elapsed_s':elapsed,'data_sha256':sha(data.encode()),
                                'cumulative_content_chars':audit.content_chars,'done':audit.done},separators=(',',':'))+'\n')
                    if data_lines:audit.event('\n'.join(data_lines),time.monotonic()-start)
                valid=audit.success() and audit.usage['completion_tokens']<=payload['max_tokens']
                result.update(status='completed' if valid else 'invalid_response')
    except Exception as error:
        # Exception strings can include proxy URLs/headers. Persist type only.
        result.update(status='transport_error',error_type=type(error).__name__)
    result.update(duration_s=time.monotonic()-start,ended_monotonic_ns=time.monotonic_ns(),response_body_bytes=response_bytes,
        first_content_s=audit.first_content_s,last_content_s=audit.last_content_s,first_reasoning_s=audit.first_reasoning_s,
        response_model=audit.response_model,response_id=audit.response_id,finish_reason=audit.finish,
        usage=audit.usage,content_chars=audit.content_chars,reasoning_chars=audit.reasoning_chars,
        sse_content_events=audit.content_events,sse_done=audit.done)
    usage=audit.usage or {};tokens=usage.get('completion_tokens')
    result['completion_tokens_per_total_s']=tokens/result['duration_s'] if tokens is not None else None
    interval=None if audit.first_content_s is None or audit.last_content_s is None else audit.last_content_s-audit.first_content_s
    result['output_window_s']=interval
    result['completion_tokens_minus_one_per_output_window_s']=(tokens-1)/interval if tokens is not None and tokens>1 and interval and interval>0 else None
    # SSE deltas can contain multiple tokens: this is not per-token ITL/TPOT.
    dump(prefix.with_suffix('.result.json'),result)
    with (out/'requests.jsonl').open('a') as f:f.write(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps({'phase':identity['phase'],'sequence':identity['sequence'],'status':result['status'],
        'http_status':status,'duration_s':round(result['duration_s'],3),'completion_tokens':tokens},ensure_ascii=False),flush=True)
    return result


async def worker(out):
    import aiohttp
    plan=json.loads((ENV/'plan.json').read_text());secret=os.environ.get('DEEPSEEK_API_KEY')
    if not secret:raise ValueError('DEEPSEEK_API_KEY missing')
    if file_record(Path(__file__))['sha256']!=plan['code']['sha256']:raise ValueError('code changed since plan freeze')
    timeout=aiohttp.ClientTimeout(total=plan['request_total_timeout_s'],connect=20,sock_read=plan['read_timeout_s'])
    async with aiohttp.ClientSession(timeout=timeout,trust_env=True,auto_decompress=False) as session:
        probe={'model':MODEL,'messages':[{'role':'user','content':'Reply only with OK.'}],
            'max_tokens':16,'stream':True,'stream_options':{'include_usage':True},'thinking':{'type':'disabled'},'temperature':0}
        r=await request(session,probe,{'phase':'probe','sequence':0},out,secret)
        if r['status']!='completed':return 1
        for q in plan['requests']:
            body=gzip.decompress(Path(q['payload']).read_bytes())
            if sha(body)!=q['body_sha256']:raise ValueError('frozen payload hash mismatch')
            identity={k:q[k] for k in ['index','trace_id','source_outer_idx','source_pointer','source_request_sha256','source_input_tokens','source_output_tokens']}
            identity.update(phase='profile',sequence=q['index']+1)
            r=await request(session,json.loads(body),identity,out,secret)
            if r['status']!='completed':return 1
    return 0


def worker_environment():
    allowed=['PATH','HOME','LANG','LC_ALL','LD_LIBRARY_PATH','TMPDIR','SSL_CERT_FILE','SSL_CERT_DIR',
             'HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','NO_PROXY','no_proxy','DEEPSEEK_API_KEY']
    env={k:os.environ[k] for k in allowed if k in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONPATH=str(ROOT))
    return env


def run(name):
    import psutil
    if not name or '/' in name or name in ['.','..']:raise ValueError('invalid attempt name')
    plan=json.loads((ENV/'plan.json').read_text())
    assert plan['endpoint']==BASE+'/chat/completions' and plan['replay_requests']==20
    assert plan['code']['sha256']==file_record(Path(__file__))['sha256']
    out=RAW/'attempts'/name;out.mkdir(parents=True,exist_ok=False)
    env=worker_environment();command=[sys.executable,'-B',str(Path(__file__)),'worker','--output',str(out)]
    versions={d.metadata['Name']:d.version for d in importlib.metadata.distributions()}
    dump(out/'environment.json',{'python':sys.version,'packages':versions,'environment_names_passed':sorted(env),
        'credential_present':bool(env.get('DEEPSEEK_API_KEY')),'proxy_present':bool(env.get('HTTPS_PROXY') or env.get('https_proxy')),
        'endpoint':BASE,'model':MODEL,'credential_values_recorded':False})
    metadata={'schema':'agentx-deepseek-attempt-v1','name':name,'started_at_shanghai':stamp(),
        'plan':file_record(ENV/'plan.json'),'command':command,'sampler_parent_pid':os.getpid(),
        'sampler_scope':'only owned worker pid and descendants; parent sampler excluded','sample_interval_s':.2}
    dump(out/'attempt.json',metadata);process=None;started=time.monotonic();baseline=None;previous=None
    try:
        with (out/'worker.stdout').open('w') as stdout,(out/'worker.stderr').open('w') as stderr:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        owned=psutil.Process(process.pid);metadata['worker_pid']=process.pid;dump(out/'attempt.json',metadata)
        with (out/'client_resources.jsonl').open('w') as samples:
            last_notice=0
            while process.poll() is None:
                now=time.monotonic();cpu=0.;rss=0;read_bytes=0;write_bytes=0;pids=[]
                try:members=[owned,*owned.children(recursive=True)]
                except psutil.NoSuchProcess:members=[]
                for member in members:
                    try:
                        c=member.cpu_times();cpu+=c.user+c.system;rss+=member.memory_info().rss;pids.append(member.pid)
                        io=member.io_counters();read_bytes+=io.read_bytes;write_bytes+=io.write_bytes
                    except (psutil.NoSuchProcess,psutil.AccessDenied):continue
                if baseline is None:baseline=(now,cpu)
                row={'monotonic_ns':time.monotonic_ns(),'elapsed_s':now-started,'pids':pids,'rss_bytes':rss,
                     'cpu_seconds':cpu,'cpu_percent_one_core':None if previous is None else max(0.,100*(cpu-previous[1])/(now-previous[0])),
                     'disk_read_bytes':read_bytes,'disk_write_bytes':write_bytes}
                samples.write(json.dumps(row,separators=(',',':'))+'\n');samples.flush();previous=(now,cpu)
                if now-started>plan['wall_limit_s']:raise TimeoutError('pilot wall limit')
                if now-started-last_notice>=15:
                    log=out/'requests.jsonl';count=len(lines(log)) if log.exists() else 0
                    print(json.dumps({'attempt':name,'elapsed_s':round(now-started,1),'finished_requests_including_probe':count}),flush=True);last_notice=now-started
                time.sleep(.2)
        metadata.update(exit_code=process.returncode,status='completed' if process.returncode==0 else 'stopped_after_failure')
    except BaseException as error:
        metadata.update(status='orchestration_error',error_type=type(error).__name__)
        raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
        metadata.update(elapsed_s=time.monotonic()-started,ended_at_shanghai=stamp(),owned_process_cleanup_confirmed=process is None or process.poll() is not None)
        dump(out/'attempt.json',metadata)
        print(json.dumps(metadata,ensure_ascii=False),flush=True)
    return metadata.get('exit_code',1)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('prepare');q.add_argument('--source-root',type=Path,required=True)
    q=sub.add_parser('run');q.add_argument('--name',required=True)
    q=sub.add_parser('worker');q.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.source_root)
    elif a.action=='run':raise SystemExit(run(a.name))
    else:raise SystemExit(asyncio.run(worker(a.output)))
