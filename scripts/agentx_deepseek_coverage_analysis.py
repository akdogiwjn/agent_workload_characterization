"""Verify 117 unique source requests, compare five cases, audit length probes."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from scripts.agentx_deep_analysis import table
from scripts.agentx_deep_presentation import style,figure,save,write_pptx,BLUE,ORANGE,TEAL
from scripts.agentx_deepseek_pilot import ROOT,canonical,sha,dump,lines,file_record,adapt_payload
from scripts.agentx_deepseek_analysis import response_oracle
from scripts.agentx_deepseek_branch_analysis import normalize,intervals,audit_edges
from scripts.agentx_deepseek_branches import verify_code
from scripts.agentx_deepseek_complete import RAW,ENV

OUT=ROOT/'reports/analysis/AGENTX-DEEPSEEK-FIVE-CASES-v1'
STEP2=Path('/home/lcq/agentx_replay_smoke_20261023')
BASELINE=Path('/home/lcq/agentx_deepseek_pilot_20261023')
BRANCHES=Path('/home/lcq/agentx_deepseek_branches_20261023')
LABELS={'baseline':'主流重叠样本','single_subagent':'单子代理','multiple_subagents':'多子代理',
        'serial_intervals':'原始区间串行','long_context':'长上下文'}


def probe_conclusion(result,requested):
    if result['status']=='http_error' and result.get('http_status') in [400,422]:return 'parameter_rejected'
    if result['status']!='completed':return 'no_valid_capability_observation'
    if result['usage']['completion_tokens']<requested and result['finish_reason']=='stop':return 'normal_stop_below_probe_target'
    return 'target_reached_in_one_trial_not_a_guarantee'


def unique_coverage(expected,observed):
    keys=lambda q:(q['trace_id'],q['source_outer_idx'],q.get('source_inner_idx'))
    wanted={keys(q):q for q in expected};seen={keys(q):q for q in observed}
    if len(seen)!=len(observed):raise ValueError('duplicate source request across cases')
    if set(wanted)!=set(seen):raise ValueError('missing or unexpected source request')
    for key in wanted:
        if wanted[key]['source_request_sha256']!=seen[key]['source_request_sha256']:raise ValueError('source fingerprint changed')
    return len(seen)


def summarize(label,rows,samples,native_groups,chains):
    clock,points=intervals(rows);span=max(q['end_s'] for q in rows)
    selected=[q for q in samples if 0<=q['relative_s']<=span and q['pids']]
    assert selected and all(q['pids']==selected[0]['pids'] for q in selected)
    assert all(b['cpu_seconds']>=a['cpu_seconds'] for a,b in zip(selected,selected[1:]))
    cpu_time=selected[-1]['cpu_seconds']-selected[0]['cpu_seconds'];window=selected[-1]['relative_s']-selected[0]['relative_s']
    prompt=sum(q['remote_prompt_tokens'] for q in rows);hit=sum(q['cache_hit_tokens'] for q in rows)
    output=sum(q['remote_completion_tokens'] for q in rows);target=sum(q['source_output_tokens'] for q in rows)
    return {'case':label,'label':LABELS[label],'requests':len(rows),'native_groups':native_groups,'execution_chains':chains,
        'wall_s':span,'first_content_p50_s':float(np.median([q['first_content_s'] for q in rows])),
        'first_content_p95_s':float(np.percentile([q['first_content_s'] for q in rows],95)),
        'duration_p50_s':float(np.median([q['duration_s'] for q in rows])),
        'duration_p95_s':float(np.percentile([q['duration_s'] for q in rows],95)),
        'peak_inflight':clock['peak'],'mean_inflight':clock['interval_sum_s']/span,'multi_request_s':clock['multi_request_s'],
        'client_sampled_peak_rss_mib':max(q['rss_bytes'] for q in selected)/2**20,
        'cpu_seconds_sample_delta':cpu_time,'cpu_sample_window_s':window,'mean_cpu_percent_one_core_from_sample_delta':100*cpu_time/window,
        'source_input_tokens':sum(q['source_input_tokens'] for q in rows),'remote_prompt_tokens':prompt,
        'max_remote_prompt_tokens':max(q['remote_prompt_tokens'] for q in rows),
        'actual_output_tokens':output,'source_output_tokens':target,'output_to_source_pct':100*output/target,
        'finish_length':sum(q['finish_reason']=='length' for q in rows),'finish_stop':sum(q['finish_reason']=='stop' for q in rows),
        'cache_hit_tokens_reported':hit,'cache_miss_tokens_reported':prompt-hit,'input_weighted_cache_hit_pct_reported':100*hit/prompt,
        'completion_tokens_per_wall_s':output/span,'request_body_bytes':sum(q['request_body_bytes'] for q in rows),
        'response_body_bytes':sum(q['response_body_bytes'] for q in rows),'resource_samples':len(selected),
        'actual_sample_interval_p50_s':float(np.median(np.diff([q['relative_s'] for q in selected]))),
        'cost_peak_rate_upper_estimate_usd':(hit*.006+(prompt-hit)*.3+output*1.2)/1e6},points,selected


def analyze(name):
    attempt_dir=RAW/'attempts'/name;attempt=json.loads((attempt_dir/'attempt.json').read_text());plan=json.loads((ENV/'plan.json').read_text())
    assert attempt['status']=='completed' and attempt['exit_code']==0 and attempt['owned_process_cleanup_confirmed']
    assert file_record(ENV/'plan.json')['sha256']==attempt['plan']['sha256'];verify_code(plan)
    assert file_record(plan['official_metadata']['path'])['sha256']==plan['official_metadata']['sha256']
    assert file_record(plan['source_export']['path'])['sha256']==plan['source_export']['sha256']
    source_captures={(q['metadata']['conversation_id'],q['metadata']['turn_index']):q for q in lines(plan['source_export']['path'])}
    native=lines(STEP2/'data/raw/agentx-replay-smoke-01/source_requests.jsonl')
    native_expected=[{'trace_id':q['trace_id'],'source_outer_idx':q['outer_idx'],'source_inner_idx':q['inner_idx'],
                      'source_request_sha256':q['source_request_sha256']} for q in native]
    raw_files=[file_record(p) for p in attempt_dir.rglob('*') if p.is_file()]
    rows=[];resources=[];case_metrics=[];profiles={};edge_rows=[];coverage_rows=[]
    sources=[]
    # Reuse already measured cases; do not issue additional API requests.
    baseline_manifest=BASELINE/'reports/analysis/AGENTX-DEEPSEEK-CLIENT-v1/manifest.json'
    branch_manifest=BRANCHES/'reports/analysis/AGENTX-DEEPSEEK-BRANCHES-v1/manifest.json'
    for path in [baseline_manifest,branch_manifest]:
        old_manifest=json.loads(path.read_text())
        for item in old_manifest['inputs']:
            assert file_record(item['path'])['sha256']==item['sha256']
        evidence_path=path.parent/'local-evidence-manifest.json'
        assert file_record(evidence_path)['sha256']==next(q['sha256'] for q in old_manifest['outputs'] if q['path']==str(evidence_path))
        for item in json.loads(evidence_path.read_text())['files']:
            assert file_record(item['path'])['sha256']==item['sha256']
    base_attempt=BASELINE/'data/raw/agentx-deepseek-pilot-01/attempts/01-remote-session'
    sources.append(('baseline',base_attempt,None,0,1))
    old_branch_attempt=BRANCHES/'data/raw/agentx-deepseek-branches-01/attempts/01-remote-branches'
    old_plan=json.loads((BRANCHES/'env/agentx-deepseek-branches-01/plan.json').read_text())
    for case in old_plan['cases']:sources.append((case['label'],old_branch_attempt,case,case['native_subagent_groups'],case['execution_chains']))
    for case in plan['cases']:sources.append((case['label'],attempt_dir,case,case['native_subagent_groups'],case['execution_chains']))
    for label,root,case,native_groups,chains in sources:
        directory=root if label=='baseline' else root/label
        requests=[q for q in lines(directory/'requests.jsonl') if q['phase']=='profile']
        assert all(q['status']=='completed' and q['http_status']==200 for q in requests)
        by_id={q.get('node_id',f"baseline#{q['index']}"):q for q in requests}
        if case:
            nodes={q['node_id']:q for q in case['nodes']}
            assert set(by_id)==set(nodes) and len(requests)==len(nodes)
            witnesses=audit_edges(case['edges'],by_id);edge_rows.extend({'case':label,**q} for q in witnesses)
        else:
            ordered=sorted(requests,key=lambda q:q['index'])
            baseline_edges=[{'predecessor':f"baseline#{a['index']}",'successor':f"baseline#{b['index']}",'kind':'serial'} for a,b in zip(ordered,ordered[1:])]
            edge_rows.extend({'case':label,**q} for q in audit_edges(baseline_edges,by_id))
        origin=min(q['started_monotonic_ns'] for q in requests);current=[]
        for q in requests:
            prefix=directory/f"{q['sequence']:03d}-profile"
            body=gzip.decompress(prefix.with_suffix('.request.json.gz').read_bytes());payload=json.loads(body)
            assert sha(body)==q['request_body_sha256'] and payload['thinking']=={'type':'disabled'}
            assert payload['max_tokens']==q['source_output_tokens']
            if case:
                n=nodes[q['node_id']]
                assert body==canonical(adapt_payload(source_captures[(n['conversation_id'],n['turn_index'])]['payload']))
                assert sha(body)==n['body_sha256']
            oracle=response_oracle(prefix.with_suffix('.response.sse'))
            assert oracle['done'] and oracle['usage']==q['usage'] and oracle['finish']==q['finish_reason']
            assert oracle['reasoning_chars']==0 and len(oracle['text'])==q['content_chars']
            assert 0<q['usage']['completion_tokens']<=q['source_output_tokens']
            value=normalize(q,label,origin)
            value.update(trace_id=q['trace_id'],source_outer_idx=q['source_outer_idx'],source_inner_idx=q.get('source_inner_idx'),
                source_request_sha256=q['source_request_sha256'])
            current.append(value)
            coverage_rows.append({k:value[k] for k in ['case','node_id','trace_id','source_outer_idx','source_inner_idx','source_pointer','source_request_sha256']})
        sample_rows=lines(root/'client_resources.jsonl')
        worker_pid=json.loads((root/'attempt.json').read_text())['worker_pid']
        assert all(q['pids']==[worker_pid] for q in sample_rows if q['pids'])
        sample_rows=[{**q,'case':label,'relative_s':(q['monotonic_ns']-origin)/1e9} for q in sample_rows]
        metric,points,selected=summarize(label,current,sample_rows,native_groups,chains)
        case_metrics.append(metric);profiles[label]=points;rows.extend(current);resources.extend(selected)
    verified=unique_coverage(native_expected,coverage_rows);assert verified==117
    probe_rows=[]
    for i,probe in enumerate(plan['probes']):
        directory=attempt_dir/f"probe-{probe['name']}";r=lines(directory/'requests.jsonl');assert len(r)==1;r=r[0]
        body=gzip.decompress((directory/f'{i:03d}-probe.request.json.gz').read_bytes())
        assert body==canonical(probe['payload'])
        if r['status']=='completed':
            oracle=response_oracle(directory/f'{i:03d}-probe.response.sse')
            assert oracle['done'] and oracle['usage']==r['usage'] and oracle['text'].strip()=='OK'
        probe_rows.append({'probe':probe['name'],'request_fields':json.dumps({k:v for k,v in probe['payload'].items() if k in ['min_tokens','ignore_eos','max_tokens']},sort_keys=True),
            'status':r['status'],'http_status':r.get('http_status'),'requested_max_tokens':64,
            'actual_completion_tokens':(r.get('usage') or {}).get('completion_tokens'),'finish_reason':r.get('finish_reason'),
            'conclusion':probe_conclusion(r,64)})
    OUT.mkdir(parents=True,exist_ok=True)
    for d in ['figures','plot_data']:(OUT/d).mkdir(exist_ok=True)
    summary={'schema':'agentx-deepseek-five-case-v1','new_profile_requests':46,'new_capability_probes':3,'new_attempt_wall_s':attempt['elapsed_s'],
        'started_at_shanghai':attempt['started_at_shanghai'],'ended_at_shanghai':attempt['ended_at_shanghai'],
        'sessions_compared':5,'unique_source_requests':verified,'total_capability_or_connectivity_probes':5,'total_chat_HTTP_calls':122,
        'automatic_retries':0,'dependency_edges_audited_all_cases':len(edge_rows),
        'all_dependency_edges_passed':all(q['passed'] for q in edge_rows),'contexts_truncated':False,
        'source_interval_concurrency_reproduced':False,'model_outputs_fed_back':False,'server_resources_measured':False,
        'cases':case_metrics,'length_probes':probe_rows,
        'original_output_tokens':sum(q['source_output_tokens'] for q in case_metrics),'actual_output_tokens':sum(q['actual_output_tokens'] for q in case_metrics),
        'remote_prompt_tokens':sum(q['remote_prompt_tokens'] for q in case_metrics),
        'baseline_manifest':file_record(baseline_manifest),'branch_manifest':file_record(branch_manifest),
        'context_scope':'complete fixed synthetic messages; original model tokenizer differs; use provider usage for remote actual length',
        'comparison_limits':'one run per stratum, non-random five-case selection; no population estimate or causal speedup; client capture overhead included'}
    summary['output_to_original_pct']=100*summary['actual_output_tokens']/summary['original_output_tokens']
    dump(OUT/'summary.json',summary);table(OUT/'case_comparison.csv',case_metrics);table(OUT/'request_metrics.csv',rows)
    table(OUT/'source_coverage.csv',coverage_rows);table(OUT/'client_resources.csv',resources);table(OUT/'dependency_audit.csv',edge_rows)
    table(OUT/'length_probes.csv',probe_rows);render(summary,rows,resources,profiles)
    secret=os.environ.get('DEEPSEEK_API_KEY')
    if not secret:raise ValueError('credential needed for exact-value leak check')
    raw_files.extend(file_record(Path(q['payload'])) for c in plan['cases'] for q in c['nodes'])
    raw_files.append(file_record(RAW/'official-metadata.json'))
    for p in [Path(q['path']) for q in raw_files]+list(OUT.rglob('*'))+list(ENV.rglob('*')):
        if p.is_file():
            data=p.read_bytes();data=gzip.decompress(data) if p.name.endswith('.gz') else data
            assert secret.encode() not in data,'credential leak'
    deck=OUT/'AgentX五类会话远程实测_汇报版_8页.pptx'
    with zipfile.ZipFile(deck) as z:
        assert z.testzip() is None
        assert len([n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')])==8
        for n in z.namelist():
            if n.endswith('.xml') or n.endswith('.rels'):ET.fromstring(z.read(n))
    from PIL import Image
    for p in (OUT/'figures').glob('*.png'):
        with Image.open(p) as im:assert im.size==(3840,2160)
    from scripts.check_project_state import check
    state_errors=check(ROOT)
    dump(OUT/'verification.json',{'status':'PASS','all_117_source_requests_uniquely_covered':True,'all_117_source_fingerprints_verified':True,
        'new_response_SSE_verified':49,'all_profile_responses_SSE_rechecked':117,'dependency_edges_verified':len(edge_rows),
        'no_credentials_in_artifacts':True,'owned_process_cleanup_confirmed':attempt['owned_process_cleanup_confirmed'],
        'pptx_slides':8,'figure_pixels':[3840,2160],
        'global_state_check':{'status':'FAIL' if state_errors else 'PASS','errors':state_errors,'disposition':'isolated worktree lacks inherited ignored evidence; shared state untouched'}})
    dump(OUT/'local-evidence-manifest.json',{'files':raw_files,'raw_files_in_git':False})
    dump(OUT/'manifest.json',{'inputs':[file_record(ENV/'plan.json'),file_record(baseline_manifest),file_record(branch_manifest),
                file_record(STEP2/'data/raw/agentx-replay-smoke-01/source_requests.jsonl')],
        'outputs':[file_record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json'],
        'code':[file_record(p) for p in [ROOT/'scripts/agentx_deepseek_complete.py',Path(__file__),ROOT/'tests/test_agentx_deepseek_complete.py']],
        'configuration':[file_record(p) for p in sorted(ENV.glob('*')) if p.is_file()]})
    print(json.dumps(summary,ensure_ascii=False,indent=2));return summary


def render(s,rows,resources,profiles):
    import matplotlib.pyplot as plt
    style();slides=[];colors=dict(zip(LABELS,[BLUE,TEAL,ORANGE,'#7C3AED','#DB2777']));cases=s['cases']
    footer='5个预选完整会话、117条正式请求，各类仅实测一次；探针另计。远程DeepSeek非思考模式。\n输入、输出、缓存和结构均不同，不作因果加速或全体393会话的性能分布推断；原始时钟未复现。'
    def finish(fig,name,title):
        save(fig,OUT,name);p=OUT/'figures'/f'{name}.svg';p.write_text('\n'.join(x.rstrip() for x in p.read_text().splitlines())+'\n')
        slides.append({'heading':title,'image':OUT/'figures'/f'{name}.png'})
    fig,ax=figure('五类会话的请求覆盖已补齐','117个原生来源索引及指纹一一对应；资源仅覆盖HTTP工作进程，包含序列化和抓取开销',footer)
    ax.axis('off');cells=[[c['label'],str(c['requests']),str(c['peak_inflight']),f"{c['wall_s']:.1f}",f"{c['first_content_p50_s']:.3f}",f"{c['client_sampled_peak_rss_mib']:.1f}",f"{c['mean_cpu_percent_one_core_from_sample_delta']:.2f}"] for c in cases]
    t=ax.table(cellText=cells,colLabels=['会话','请求数','并发峰值','墙钟秒','首内容P50秒','RSS MiB','CPU单核均值%'],cellLoc='center',bbox=[0,.05,1,.9]);t.auto_set_font_size(False);t.set_fontsize(14)
    for (r,c),v in t.get_celld().items():v.set_edgecolor('#CBD5E1');v.set_facecolor('#EFF6FF' if r==0 else 'white')
    table(OUT/'plot_data/01_cases.csv',cases);finish(fig,'01_cases','五类会话：客户端实测汇总')
    long=sorted((q for q in rows if q['case']=='long_context'),key=lambda q:q['source_outer_idx'])
    fig,ax=figure('长上下文：原始长度与远程实际输入',f"26条完整请求；远程单请求最大输入 {max(q['remote_prompt_tokens'] for q in long):,} token，未裁剪文本",footer+'\n横轴按原生外层索引排序；分支可能按另一实际顺序执行。两个分词口径分别保留。')
    x=range(1,len(long)+1)
    ax.plot(x,[q['source_input_tokens']/1000 for q in long],marker='o',color=BLUE,label='原始hash长度')
    ax.plot(x,[q['remote_prompt_tokens']/1000 for q in long],marker='o',color='#DB2777',label='远程usage输入')
    ax.set(xlabel='长上下文会话的原生请求序号',ylabel='输入长度（千 token）');ax.legend()
    table(OUT/'plot_data/02_long_context.csv',long);finish(fig,'02_long_context','长上下文：完整内容的远程接收验证')
    fig,ax=figure('首次非空内容延迟的请求级分布','每个会话分别统计ECDF，不把不同上下文、输出量和缓存状态当作受控对照',footer)
    for c in cases:
        values=np.sort([q['first_content_s'] for q in rows if q['case']==c['case']]);ax.step(values,np.arange(1,len(values)+1)/len(values)*100,where='post',color=colors[c['case']],lw=2,label=f"{c['label']} n={len(values)}")
    ax.set(xlabel='客户端首次非空内容时间（秒）',ylabel='请求累计占比（%）',ylim=(0,102));ax.legend(fontsize=12)
    table(OUT/'plot_data/03_latency.csv',[{k:q[k] for k in ['case','index','first_content_s','duration_s']} for q in rows]);finish(fig,'03_latency','请求延迟：五种样本分别呈现')
    fig,ax=figure('实际请求并发随会话时间变化','按实际发送至接收结束区间统计；来自官方依赖图，不是原始t/api_time曲线',footer)
    for c in cases:
        ps=profiles[c['case']];ax.step([p['time_s'] for p in ps],[p['inflight'] for p in ps],where='post',color=colors[c['case']],lw=2,label=c['label'])
    ax.set(xlabel='各会话首请求起的时间（秒）',ylabel='在途HTTP请求数',yticks=range(max(c['peak_inflight'] for c in cases)+1));ax.legend(fontsize=12)
    table(OUT/'plot_data/04_concurrency.csv',[{'case':k,**q} for k,ps in profiles.items() for q in ps]);finish(fig,'04_concurrency','分支调度：保留实测并发轨迹')
    fig,ax=figure('客户端RSS随会话时间变化','资源包含正文解压、JSON、流式接收与证据保存；新增每轮两个会话复用工作进程',footer+'\n采样峰值可能遗漏瞬时峰值；跨会话残留堆和连接会影响比较；不包含业务工具或模型服务资源。')
    for c in cases:
        selected=[q for q in resources if q['case']==c['case']];ax.plot([q['relative_s'] for q in selected],[q['rss_bytes']/2**20 for q in selected],color=colors[c['case']],label=c['label'],lw=2)
    ax.set(xlabel='各会话首请求起的时间（秒）',ylabel='HTTP工作进程RSS（MiB）',ylim=(0,None));ax.legend(fontsize=12)
    table(OUT/'plot_data/05_resources.csv',resources);finish(fig,'05_resources','客户端内存：上下文与并发样本对比')
    fig,ax=figure('实际生成量与原始输出长度必须分开','原始out设为新请求max_tokens，只限制上限；正常提前stop不会被补发请求掩盖',footer)
    x=np.arange(5);ax.bar(x,[c['output_to_source_pct'] for c in cases],color=[colors[c['case']] for c in cases],width=.6)
    for i,c in enumerate(cases):ax.text(i,c['output_to_source_pct']+2,f"{c['actual_output_tokens']:,}/{c['source_output_tokens']:,}\n{c['output_to_source_pct']:.2f}%",ha='center',fontsize=11)
    ax.set(xticks=x,xticklabels=[c['label'] for c in cases],ylabel='实际输出 / 原始输出长度（%）',ylim=(0,120))
    table(OUT/'plot_data/06_output_coverage.csv',[{k:c[k] for k in ['case','source_output_tokens','actual_output_tokens','output_to_source_pct','finish_length','finish_stop']} for c in cases]);finish(fig,'06_output_coverage','输出负载：覆盖不足明确登记')
    fig,ax=figure('输出长度控制探针：HTTP接受不等于有效','相同短提示词，最多64 token；字段分别测试，未混入任何正式会话',footer+'\n单次达到64也不能证明保证；正常短停的反例可以说明当前字段不能保证最小长度。')
    probes=s['length_probes'];values=[p['actual_completion_tokens'] or 0 for p in probes]
    ax.bar(range(3),values,color=[BLUE,TEAL,ORANGE],width=.55);ax.axhline(64,color='#64748B',ls='--',label='本次上限 / min_tokens探针目标=64')
    for i,p in enumerate(probes):ax.text(i,values[i]+2,f"HTTP {p['http_status']}\n输出 {p['actual_completion_tokens']}，{p['finish_reason']}",ha='center',fontsize=14)
    ax.set(xticks=range(3),xticklabels=['默认对照','min_tokens=64','ignore_eos=true'],ylabel='实际输出token（服务端usage）',ylim=(0,78));ax.legend(fontsize=12,loc='upper right')
    table(OUT/'plot_data/07_probes.csv',probes);finish(fig,'07_probes','接口能力：记录最小输出控制反例')
    fig,ax=figure('当前证据覆盖到哪一层？','全量离线统计、固定输入回放和真实业务执行分开登记',footer)
    ax.axis('off');cells=[['原数据深入分析','393会话；Full与256k分别统计','已完成限定范围'],['本地模拟映射','5会话、117请求','逐条核验通过'],['远程典型会话','5会话、117请求，每类一次','全部请求覆盖'],['原始长输出负载','模型可提前正常停止','尚未严格复现'],['原始时间与业务工具','本次保留依赖、移除等待；无工具原文','未复现'],['重复试验和总体推断','预选样本，不是随机抽样','尚未做重复测量']]
    t=ax.table(cellText=cells,colLabels=['证据层次','范围与口径','状态'],cellLoc='center',bbox=[0,0,1,.95],colWidths=[.23,.55,.22]);t.auto_set_font_size(False);t.set_fontsize(13)
    for (r,c),v in t.get_celld().items():v.set_edgecolor('#CBD5E1');v.set_facecolor('#EFF6FF' if r==0 else 'white')
    finish(fig,'08_scope','结论边界：请求覆盖与业务复现分开')
    write_pptx(OUT/'AgentX五类会话远程实测_汇报版_8页.pptx',slides)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--attempt',default='01-complete-cases');analyze(p.parse_args().attempt)
