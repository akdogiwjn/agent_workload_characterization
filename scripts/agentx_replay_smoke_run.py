"""Run the pinned official harness against an owned, loopback-only mock."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw/agentx-replay-smoke-01'
TOKENIZER_REVISION='c1899de289a04d12100db370d81485cdf75e47ca'


def prepare_tokenizer_cache():
    """Expose downloaded files through the documented HuggingFace cache layout.

    Harness 1.0.7's offline loader resolves a Hub snapshot even for local paths.
    Use its supported repo+revision route without patching the installed harness.
    """
    cache=RAW/'hf-cache'
    snapshot=cache/'models--Qwen--Qwen3-0.6B'/'snapshots'/TOKENIZER_REVISION
    snapshot.mkdir(parents=True,exist_ok=True)
    for name in ['tokenizer.json','tokenizer_config.json','config.json','merges.txt','vocab.json']:
        target=snapshot/name
        if not target.exists():target.symlink_to(RAW/'tokenizer'/name)
    return cache


def clean_environment():
    env={k:os.environ[k] for k in ['PATH','HOME','LANG','LC_ALL','LD_LIBRARY_PATH','TMPDIR'] if k in os.environ}
    env.update({'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1',
                'DO_NOT_TRACK':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1',
                'NO_PROXY':'127.0.0.1,localhost','TOKENIZERS_PARALLELISM':'false',
                'HF_HUB_CACHE':str(prepare_tokenizer_cache()),
                'AIPERF_DATASET_MMAP_CACHE_ENABLED':'false',
                'AIPERF_DATASET_WEKA_PARALLEL_WORKERS':'1',
                'AIPERF_HTTP_X_DYNAMO_SESSION_ID_FROM_CORRELATION_ID':'true',
                'AIPERF_DATASET_CONFIGURATION_TIMEOUT':'300',
                'AIPERF_SERVICE_PROFILE_CONFIGURE_TIMEOUT':'300'})
    return env


def terminate_owned(process):
    if process is not None and process.poll() is None:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)


def run(name, input_dir=None, sessions=5, timeout=600):
    if not name or '/' in name or name in ['.','..']:raise ValueError('invalid attempt name')
    if importlib.metadata.version('agentx-harness')!='1.0.7':raise ValueError('unexpected harness version')
    path=RAW/'attempts'/name
    path.mkdir(parents=True,exist_ok=False)
    input_dir=Path(input_dir or RAW/'sessions').resolve()
    ready=path/'server-ready.json'
    mock=[sys.executable,'-B',str(ROOT/'scripts/agentx_loopback_mock.py'),
          '--tokenizer',str(RAW/'tokenizer'),'--output',str(path/'mock'),'--ready',str(ready)]
    env=clean_environment();server=None;client=None;started=time.monotonic()
    metadata={'schema':'agentx-loopback-attempt-v1','name':name,'harness_version':'1.0.7',
              'input_dir':str(input_dir),'model_loaded':False,'real_model_calls':0,
              'timing_mode':'ignore source delays for mechanical mapping check; not source-time or official performance reproduction',
              'environment_keys_passed':sorted(env),'server_command':mock}
    (path/'environment.json').write_text(json.dumps({'python':sys.version,
        'packages':sorted([{'name':d.metadata['Name'],'version':d.version} for d in importlib.metadata.distributions()],key=lambda d:d['name'].lower())},indent=2)+'\n')
    try:
        with (path/'server.stdout').open('w') as so,(path/'server.stderr').open('w') as se:
            server=subprocess.Popen(mock,cwd=ROOT,env=env,stdout=so,stderr=se,start_new_session=True)
        for _ in range(300):
            if server.poll() is not None:raise RuntimeError('mock startup failed; see server.stderr')
            if ready.exists():break
            time.sleep(.1)
        if not ready.exists():raise TimeoutError('mock readiness timeout')
        info=json.loads(ready.read_text());url=info['url']
        if not url.startswith('http://127.0.0.1:'):raise ValueError('non-loopback URL rejected')
        # Bypass all proxy settings for the local readiness request.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url+'/health',timeout=5) as response:
            if json.load(response).get('no_model') is not True:raise ValueError('unexpected server')
        command=[str(ROOT/'.venv/bin/aiperf'),'profile','--model','agentx-mock',
                 '--tokenizer','Qwen/Qwen3-0.6B','--tokenizer-revision',TOKENIZER_REVISION,
                 '--no-gpu-telemetry','--endpoint-type','chat','--url',url,
                 '--custom-dataset-type','weka_trace','--input-file',str(input_dir),
                 '--no-fixed-schedule','--ignore-trace-delays','--num-conversations',str(sessions),
                 '--concurrency',str(sessions),'--dataset-sampling-strategy','sequential',
                 '--streaming','--use-server-token-count','--apply-chat-template','--cache-bust','none',
                 '--random-seed','42','--workers-max','2','--export-level','raw',
                 '--request-timeout-seconds','120','--output-artifact-dir',str(path/'harness'),
                 '--ui','none','--log-level','info']
        metadata.update(client_command=command,server=info)
        (path/'attempt.json').write_text(json.dumps(metadata,indent=2)+'\n')
        with (path/'client.stdout').open('w') as co,(path/'client.stderr').open('w') as ce:
            client=subprocess.Popen(command,cwd=ROOT,env=env,stdout=co,stderr=ce,start_new_session=True)
        last=0
        while client.poll() is None:
            elapsed=time.monotonic()-started
            if elapsed>timeout:raise TimeoutError(f'attempt exceeded {timeout}s')
            if elapsed-last>10:
                received=path/'mock/server_requests.jsonl'
                count=sum(1 for _ in received.open()) if received.exists() else 0
                print(json.dumps({'attempt':name,'elapsed_s':round(elapsed,1),'mock_completed_records':count}),flush=True);last=elapsed
            time.sleep(.2)
        metadata.update(exit_code=client.returncode,elapsed_s=time.monotonic()-started,status='completed' if client.returncode==0 else 'harness_failed')
    except BaseException as error:
        metadata.update(status='orchestration_failed',error_type=type(error).__name__,error=str(error),elapsed_s=time.monotonic()-started)
        raise
    finally:
        terminate_owned(client);terminate_owned(server)
        metadata['owned_process_cleanup_confirmed']=all(p is None or p.poll() is not None for p in [client,server])
        (path/'attempt.json').write_text(json.dumps(metadata,indent=2)+'\n')
        print(json.dumps({'attempt':name,'status':metadata.get('status'),'exit_code':metadata.get('exit_code'),'elapsed_s':metadata.get('elapsed_s'),'cleanup':metadata['owned_process_cleanup_confirmed']}),flush=True)
    return metadata


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--name',required=True);p.add_argument('--input-dir',type=Path);p.add_argument('--sessions',type=int,default=5);p.add_argument('--timeout',type=int,default=600)
    a=p.parse_args();result=run(a.name,a.input_dir,a.sessions,a.timeout)
    if result.get('exit_code')!=0:raise SystemExit(result.get('exit_code') or 1)
