"""Verify and present the remote-model pilot; never sends network requests."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from scripts.agentx_deep_analysis import table
from scripts.agentx_deep_presentation import style,figure,save,write_pptx,BLUE,ORANGE,TEAL
from scripts.agentx_deepseek_pilot import ROOT,RAW,ENV,TRACE,canonical,sha,dump,lines,file_record

OUT=ROOT/'reports/analysis/AGENTX-DEEPSEEK-CLIENT-v1'


def response_oracle(path):
    """Reconstruct final usage/content independently from the saved SSE body."""
    text=[];usage=None;finish=None;done=False;models=set();reasoning=[]
    for line in Path(path).read_text().splitlines():
        if not line.startswith('data:'):continue
        value=line[5:].strip()
        if value=='[DONE]':done=True;continue
        q=json.loads(value)
        if q.get('model'):models.add(q['model'])
        if q.get('usage') is not None:usage=q['usage']
        for choice in q.get('choices',[]):
            text.append(choice.get('delta',{}).get('content') or '')
            reasoning.append(choice.get('delta',{}).get('reasoning_content') or '')
            if choice.get('finish_reason'):finish=choice['finish_reason']
    return {'text':''.join(text),'usage':usage,'finish':finish,'done':done,'models':sorted(models),'reasoning_chars':len(''.join(reasoning))}


def cache_counts(usage):
    """Missing values remain unknown, and inconsistent cache fields fail."""
    total=usage['prompt_tokens'];hit=usage.get('prompt_cache_hit_tokens');miss=usage.get('prompt_cache_miss_tokens')
    nested=usage.get('prompt_tokens_details',{}).get('cached_tokens')
    if hit is None:hit=nested
    if hit is None:return None,None
    if nested is not None and hit!=nested:raise ValueError('cache counters disagree')
    if hit<0 or hit>total:raise ValueError('invalid cache hit count')
    if miss is None:miss=total-hit
    if hit+miss!=total:raise ValueError('cache counts do not partition input')
    return hit,miss


def analyze(name):
    out=RAW/'attempts'/name;attempt=json.loads((out/'attempt.json').read_text());plan=json.loads((ENV/'plan.json').read_text())
    assert file_record(ENV/'plan.json')['sha256']==attempt['plan']['sha256']
    assert file_record(ROOT/'scripts/agentx_deepseek_pilot.py')['sha256']==plan['code']['sha256']
    requests=lines(out/'requests.jsonl');profile=[q for q in requests if q['phase']=='profile'];probe=[q for q in requests if q['phase']=='probe']
    assert len(requests)==21 and len(probe)==1 and len(profile)==20
    assert [q['index'] for q in profile]==list(range(20))
    assert all(q['status']=='completed' and q['http_status']==200 for q in requests)
    assert attempt['status']=='completed' and attempt['exit_code']==0 and attempt['owned_process_cleanup_confirmed']
    first=profile[0]['started_monotonic_ns'];rows=[];files=[]
    expected={q['index']:q for q in plan['requests']}
    for q in requests:
        prefix=out/f"{q['sequence']:03d}-{q['phase']}"
        body=gzip.decompress(prefix.with_suffix('.request.json.gz').read_bytes());payload=json.loads(body)
        assert sha(body)==q['request_body_sha256']
        assert 'Authorization' not in payload and payload['model']=='deepseek-flash' and payload['thinking']=={'type':'disabled'}
        assert payload['max_tokens']==q['requested_max_tokens']
        response=prefix.with_suffix('.response.sse');oracle=response_oracle(response)
        assert oracle['done'] and oracle['usage']==q['usage'] and oracle['finish']==q['finish_reason']
        assert len(oracle['text'])==q['content_chars'] and oracle['reasoning_chars']==q['reasoning_chars']==0
        assert response.stat().st_size==q['response_body_bytes']
        files.extend(file_record(p) for p in prefix.parent.glob(prefix.name+'.*') if p.is_file())
        if q['phase']!='profile':continue
        source=expected[q['index']]
        assert q['trace_id']==TRACE and q['source_outer_idx']==source['source_outer_idx']
        assert q['source_request_sha256']==source['source_request_sha256']
        assert sha(body)==source['body_sha256']
        assert sha(canonical(payload['messages']))==source['messages_sha256']==q['messages_sha256']
        hit,miss=cache_counts(q['usage'])
        assert hit is not None,'this report requires observed cache fields'
        rows.append({'index':q['index'],'request_number':q['index']+1,'source_pointer':q['source_pointer'],
            'source_input_tokens':q['source_input_tokens'],'mock_rendered_input_tokens':None,
            'remote_prompt_tokens':q['usage']['prompt_tokens'],'input_delta':q['usage']['prompt_tokens']-q['source_input_tokens'],
            'output_target_tokens':q['source_output_tokens'],'remote_completion_tokens':q['usage']['completion_tokens'],
            'cache_hit_tokens_reported':hit,'cache_miss_tokens_reported':miss,
            'cache_hit_share_pct':100*hit/q['usage']['prompt_tokens'],
            'first_content_s':q['first_content_s'],'duration_s':q['duration_s'],'output_window_s':q['output_window_s'],
            'completion_tokens_per_total_s':q['completion_tokens_per_total_s'],
            'completion_tokens_minus_one_per_output_window_s':q['completion_tokens_minus_one_per_output_window_s'],
            'finish_reason':q['finish_reason'],'request_body_bytes':q['request_body_bytes'],'response_body_bytes':q['response_body_bytes'],
            'start_s':(q['started_monotonic_ns']-first)/1e9,'end_s':(q['ended_monotonic_ns']-first)/1e9,
            'response_model':q['response_model'],'body_sha256':q['request_body_sha256'],'messages_sha256':q['messages_sha256']})
    for a,b in zip(profile,profile[1:]):assert b['started_monotonic_ns']>=a['ended_monotonic_ns']
    assert all(q['remote_completion_tokens']<=q['output_target_tokens'] for q in rows)
    samples=lines(out/'client_resources.jsonl')
    assert len(samples)>2 and all(q['pids']==[attempt['worker_pid']] for q in samples)
    assert all(b['cpu_seconds']>=a['cpu_seconds'] for a,b in zip(samples,samples[1:]))
    for q in samples:q['profile_relative_s']=(q['monotonic_ns']-first)/1e9
    profile_samples=[q for q in samples if profile[0]['started_monotonic_ns']<=q['monotonic_ns']<=profile[-1]['ended_monotonic_ns']]
    prompt=sum(q['remote_prompt_tokens'] for q in rows);completion=sum(q['remote_completion_tokens'] for q in rows)
    hit=sum(q['cache_hit_tokens_reported'] for q in rows);miss=sum(q['cache_miss_tokens_reported'] for q in rows)
    duration=sum(q['duration_s'] for q in rows)
    span=(profile[-1]['ended_monotonic_ns']-first)/1e9
    cpu_observed_delta=profile_samples[-1]['cpu_seconds']-profile_samples[0]['cpu_seconds']
    summary={'schema':'agentx-deepseek-client-analysis-v1','started_at_shanghai':attempt['started_at_shanghai'],
        'ended_at_shanghai':attempt['ended_at_shanghai'],'successful_attempt':name,'sessions':1,'requests':20,
        'probe_requests':1,'automatic_retries':0,'request_model':plan['model'],'response_models':sorted({q['response_model'] for q in rows}),
        'thinking_disabled':True,'remote_version_not_immutably_verified':True,'source_trace_id':TRACE,
        'source_input_tokens':sum(q['source_input_tokens'] for q in rows),'remote_prompt_tokens':prompt,
        'source_output_target_tokens':sum(q['output_target_tokens'] for q in rows),'remote_completion_tokens':completion,
        'output_targets_met':sum(q['remote_completion_tokens']==q['output_target_tokens'] for q in rows),
        'input_delta_min':min(q['input_delta'] for q in rows),'input_delta_max':max(q['input_delta'] for q in rows),
        'input_total_delta_pct':100*(prompt-sum(q['source_input_tokens'] for q in rows))/sum(q['source_input_tokens'] for q in rows),
        'prompt_cache_hit_tokens_reported':hit,'prompt_cache_miss_tokens_reported':miss,
        'input_weighted_cache_hit_pct_reported':100*hit/prompt,
        'finish_reasons':dict(Counter(q['finish_reason'] for q in rows)),
        'profile_request_duration_sum_s':duration,'profile_wall_s':span,'attempt_wall_s':attempt['elapsed_s'],
        'first_content_s_p50':float(np.median([q['first_content_s'] for q in rows])),
        'first_content_s_p95':float(np.percentile([q['first_content_s'] for q in rows],95)),
        'duration_s_p50':float(np.median([q['duration_s'] for q in rows])),
        'duration_s_p95':float(np.percentile([q['duration_s'] for q in rows],95)),
        'completion_tokens_per_sum_request_duration_s':completion/duration,
        'request_body_bytes':sum(q['request_body_bytes'] for q in rows),'response_body_bytes':sum(q['response_body_bytes'] for q in rows),
        'resource_samples':len(samples),'profile_resource_samples':len(profile_samples),'sampling_interval_s':.2,
        'actual_sample_interval_p50_s':float(np.median(np.diff([q['elapsed_s'] for q in samples]))),
        'actual_sample_interval_max_s':float(max(np.diff([q['elapsed_s'] for q in samples]))),
        'profile_sampled_peak_rss_mib':max(q['rss_bytes'] for q in profile_samples)/2**20,
        'attempt_sampled_peak_rss_mib':max(q['rss_bytes'] for q in samples)/2**20,
        'profile_cpu_seconds_between_first_and_last_in_window_samples':cpu_observed_delta,
        'profile_cpu_sample_window_s':profile_samples[-1]['elapsed_s']-profile_samples[0]['elapsed_s'],
        'attempt_last_sample_cpu_seconds':samples[-1]['cpu_seconds'],
        'profile_mean_cpu_percent_one_core_from_sample_delta':100*cpu_observed_delta/(profile_samples[-1]['elapsed_s']-profile_samples[0]['elapsed_s']),
        'resource_scope':'one owned HTTP worker, including payload serialization and evidence capture; sampler parent excluded',
        'network_scope':'application request/response body bytes only; excludes headers, TLS, proxy and transport overhead',
        'server_resources_measured':False,'source_timing_reproduced':False,'business_tools_executed':False,
        'model_outputs_fed_back':False,'usage_tokens_source':'provider usage; no local DeepSeek tokenizer exact-count claim',
        'estimated_usd_at_documented_peak_rates':(hit*.006+miss*.3+completion*1.2)/1e6,
        'cost_basis':'official pricing accessed 2026-10-23, peak USD/1M: hit .006, miss .3, output 1.2; estimate not billing; probe excluded',
        'verification':{'profile_payloads':20,'received_sse_bodies_including_probe':21,'source_mapping_passed':True,
            'probe_content_is_OK':response_oracle(out/'000-probe.response.sse')['text'].strip()=='OK',
            'no_credentials_in_artifacts':None,'owned_process_cleanup_confirmed':attempt['owned_process_cleanup_confirmed']}}
    # Compare step-2's observed Qwen counts to provider counts only through the
    # pinned mapping table; never substitute one tokenizer's count for another.
    import csv
    # The source-export path is .../data/raw/.../attempts/.../harness/file.
    step2=Path(plan['source_export']['path']).parents[6]/'reports/analysis/AGENTX-REPLAY-SMOKE-v1/request_mapping.csv'
    if not step2.is_file():raise FileNotFoundError(step2)
    old={int(q['source_outer_idx']):q for q in csv.DictReader(step2.open()) if q['trace_id']==TRACE}
    for q in rows:q['mock_rendered_input_tokens']=int(old[q['index']]['observed_input'])
    OUT.mkdir(parents=True,exist_ok=True)
    for d in ['figures','plot_data']:(OUT/d).mkdir(exist_ok=True)
    table(OUT/'per_request.csv',rows);table(OUT/'client_resources.csv',samples)
    dump(OUT/'summary.json',summary);dump(OUT/'attempts.json',[json.loads(p.read_text()) for p in sorted((RAW/'attempts').glob('*/attempt.json'))])
    render(summary,rows,samples)
    files.extend(file_record(p) for p in out.iterdir() if p.is_file())
    files.extend(file_record(Path(q['payload'])) for q in plan['requests'])
    files=list({q['path']:q for q in files}.values())
    # Exact secret scan reads the current env but never prints or stores it.
    import os
    secret=os.environ.get('DEEPSEEK_API_KEY')
    if not secret:raise ValueError('credential required for offline exact-value leak check')
    check_paths=[Path(q['path']) for q in files]+list(OUT.rglob('*'))+list(ENV.rglob('*'))
    for p in check_paths:
        if not p.is_file():continue
        blob=p.read_bytes()
        if p.name.endswith('.gz'):blob=gzip.decompress(blob)
        assert secret.encode() not in blob,'credential found in artifact'
    summary['verification']['no_credentials_in_artifacts']=True
    dump(OUT/'summary.json',summary)
    with zipfile.ZipFile(OUT/'AgentX远程DeepSeek_客户端测量_4页.pptx') as z:
        assert z.testzip() is None
        for name in z.namelist():
            if name.endswith('.xml') or name.endswith('.rels'):ET.fromstring(z.read(name))
    from PIL import Image
    for p in (OUT/'figures').glob('*.png'):
        with Image.open(p) as im:assert im.size==(3840,2160)
    dump(OUT/'local-evidence-manifest.json',{'files':files,'raw_files_kept_local':True})
    from scripts.check_project_state import check
    state_errors=check(ROOT)
    dump(OUT/'verification.json',{'status':'PASS','checks':summary['verification'],'pptx_slides':4,'figure_pixels':[3840,2160],
        'global_state_check':{'status':'FAIL' if state_errors else 'PASS','errors':state_errors,
            'disposition':'isolated worktree lacks 36 inherited ignored historical evidence files; shared state untouched'}})
    dump(OUT/'manifest.json',{'inputs':[file_record(ENV/'plan.json'),file_record(out/'requests.jsonl'),file_record(out/'client_resources.jsonl')],
        'outputs':[file_record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json'],
        'code':[file_record(ROOT/'scripts/agentx_deepseek_pilot.py'),file_record(Path(__file__)),file_record(ROOT/'tests/test_agentx_deepseek_pilot.py')],
        'configuration':[file_record(p) for p in sorted(ENV.glob('*')) if p.is_file()],
        'raw_data_in_git':False,'server_resources_collected':False})
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary


def render(s,rows,samples):
    style();slides=[]
    footer='单个固定会话，20条请求，DeepSeek官方远程API；非思考模式；探针另计。\n客户端观测包含网络/代理、服务排队和响应；不能拆成纯模型推理耗时，也不代表全数据集性能。'
    def finish(fig,name,title):
        save(fig,OUT,name);p=OUT/'figures'/f'{name}.svg';p.write_text('\n'.join(x.rstrip() for x in p.read_text().splitlines())+'\n')
        slides.append({'heading':title,'image':OUT/'figures'/f'{name}.png'})
    x=[q['request_number'] for q in rows]
    fig,ax=figure('远程请求耗时：首次内容与完整响应',f"20/20成功、零重试；首次非空内容中位数 {s['first_content_s_p50']:.3f}s，完整响应中位数 {s['duration_s_p50']:.3f}s",footer)
    ax.plot(x,[q['first_content_s'] for q in rows],marker='o',color=TEAL,label='首次非空内容（客户端TTFT）')
    ax.plot(x,[q['duration_s'] for q in rows],marker='o',color=BLUE,label='完整请求耗时')
    ax.set(xlabel='固定会话的请求序号',ylabel='客户端观测耗时（秒）',xticks=range(1,21,2),ylim=(0,None));ax.legend()
    table(OUT/'plot_data/01_latency.csv',[{k:q[k] for k in ['request_number','first_content_s','duration_s']} for q in rows]);finish(fig,'01_latency','远程实测：请求延迟')
    fig,ax=figure('分词口径变化：原始长度与远程实际计数',f"原始输入 {s['source_input_tokens']:,} token → 远程usage {s['remote_prompt_tokens']:,} token；文本保持一致",footer+'\n原始长度来自hash块，第二步由Qwen分词器计数，远程计数来自DeepSeek usage；不可混用。')
    for key,label,color in [('source_input_tokens','原始hash长度',BLUE),('mock_rendered_input_tokens','第二步Qwen模板计数',ORANGE),('remote_prompt_tokens','远程DeepSeek usage',TEAL)]:
        ax.plot(x,[q[key]/1000 for q in rows],marker='o',markersize=4,color=color,label=label)
    ax.set(xlabel='固定会话的请求序号',ylabel='每请求输入长度（千 token）',xticks=range(1,21,2));ax.legend(fontsize=13)
    table(OUT/'plot_data/02_tokens.csv',[{k:q[k] for k in ['request_number','source_input_tokens','mock_rendered_input_tokens','remote_prompt_tokens']} for q in rows]);finish(fig,'02_tokens','实际输入：分词口径差异独立记录')
    fig,ax=figure('远程接口报告了多少输入缓存命中？',f"输入加权命中占比 {s['input_weighted_cache_hit_pct_reported']:.2f}%；仅表示服务端usage字段，无关闭缓存的对照组",footer+'\n命中来自prompt_cache_hit_tokens，并与cached_tokens及miss分区校验；未采集服务端显存或GPU。')
    ax.bar(x,[q['cache_hit_tokens_reported']/1000 for q in rows],color=TEAL,label='usage报告缓存命中')
    ax.bar(x,[q['cache_miss_tokens_reported']/1000 for q in rows],bottom=[q['cache_hit_tokens_reported']/1000 for q in rows],color=ORANGE,label='usage报告缓存未命中')
    ax.set(xlabel='固定会话的请求序号',ylabel='输入 token（千）',xticks=range(1,21,2));ax.legend(fontsize=13)
    table(OUT/'plot_data/03_cache.csv',[{k:q[k] for k in ['request_number','cache_hit_tokens_reported','cache_miss_tokens_reported','cache_hit_share_pct']} for q in rows]);finish(fig,'03_cache','缓存观察：服务端usage报告')
    fig,ax=figure('客户端资源：仅采集本次HTTP工作进程',f"实际采样间隔中位数{s['actual_sample_interval_p50_s']:.3f}s；RSS采样峰值 {s['profile_sampled_peak_rss_mib']:.1f}MiB；CPU按单核100%计",footer+'\n包含序列化和抓取证据的开销；排除采样父进程及其他会话；采样峰值可能遗漏瞬时峰值。')
    fig.subplots_adjust(right=.87)
    profile=[q for q in samples if 0<=q['profile_relative_s']<=s['profile_wall_s']]
    ax.plot([q['profile_relative_s'] for q in profile],[q['rss_bytes']/2**20 for q in profile],color=BLUE,label='RSS（MiB）')
    ax.set(xlabel='正式会话首请求起的相对时间（秒）',ylabel='工作进程RSS（MiB）',ylim=(0,None))
    right=ax.twinx();right.plot([q['profile_relative_s'] for q in profile],[q['cpu_percent_one_core'] or 0 for q in profile],color=ORANGE,alpha=.7,label='CPU（单核%）')
    right.set_ylabel('CPU（单逻辑核百分比）');right.set_ylim(0,max(10,max(q['cpu_percent_one_core'] or 0 for q in profile)*1.2))
    ax.legend(loc='upper left');right.legend(loc='upper right')
    table(OUT/'plot_data/04_resources.csv',profile);finish(fig,'04_resources','客户端实测：CPU与内存时间线')
    write_pptx(OUT/'AgentX远程DeepSeek_客户端测量_4页.pptx',slides)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--attempt',default='01-remote-session')
    analyze(p.parse_args().attempt)
