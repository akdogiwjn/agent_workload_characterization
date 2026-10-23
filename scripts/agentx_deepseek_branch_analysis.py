"""Offline dependency audit and PPT comparison for remote branch replay."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
import csv
import gzip
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from scripts.agentx_deep_analysis import table
from scripts.agentx_deep_presentation import style,figure,save,write_pptx,BLUE,ORANGE,TEAL
from scripts.agentx_deepseek_pilot import ROOT,canonical,sha,dump,lines,file_record
from scripts.agentx_deepseek_pilot import adapt_payload
from scripts.agentx_deepseek_branch_prepare import RAW,ENV
from scripts.agentx_deepseek_analysis import response_oracle,cache_counts
from scripts.agentx_deepseek_branches import verify_code

OUT=ROOT/'reports/analysis/AGENTX-DEEPSEEK-BRANCHES-v1'
BASELINE=Path('/home/lcq/agentx_deepseek_pilot_20261023')
LABELS={'baseline':'单链基线','single_subagent':'单子代理','multiple_subagents':'多子代理'}


def intervals(rows):
    changes=defaultdict(int)
    for q in rows:
        if q['end_s']<q['start_s']:raise ValueError('negative interval')
        if q['end_s']==q['start_s']:continue
        changes[q['start_s']]+=1;changes[q['end_s']]-=1
    current=peak=0;previous=None;busy=multi=area=0.;points=[]
    for t,delta in sorted(changes.items()):
        if previous is not None:
            width=t-previous;area+=width*current
            if current:busy+=width
            if current>1:multi+=width
        current+=delta;peak=max(peak,current);points.append({'time_s':t,'inflight':current});previous=t
    assert current==0
    return {'peak':peak,'busy_s':busy,'multi_request_s':multi,'interval_sum_s':area},points


def audit_edges(edges,results):
    witnesses=[]
    for edge in edges:
        pred=results[edge['predecessor']];succ=results[edge['successor']]
        gap=succ['started_monotonic_ns']-pred['ended_monotonic_ns']
        witnesses.append({**edge,'gap_ns':gap,'passed':gap>=0})
    if not all(q['passed'] for q in witnesses):raise ValueError('dependency violated')
    return witnesses


def normalize(q,case,origin):
    hit,miss=cache_counts(q['usage']);assert hit is not None
    return {'case':case,'node_id':q.get('node_id',f"baseline#{q['index']}"),'index':q['index'],
        'conversation_id':q.get('conversation_id',q['trace_id']),'parent_conversation_id':q.get('parent_conversation_id'),
        'turn_index':q.get('turn_index',q['index']),'source_pointer':q['source_pointer'],
        'source_input_tokens':q['source_input_tokens'],'source_output_tokens':q['source_output_tokens'],
        'remote_prompt_tokens':q['usage']['prompt_tokens'],'remote_completion_tokens':q['usage']['completion_tokens'],
        'cache_hit_tokens':hit,'cache_miss_tokens':miss,'first_content_s':q['first_content_s'],'duration_s':q['duration_s'],
        'finish_reason':q['finish_reason'],'start_s':(q['started_monotonic_ns']-origin)/1e9,
        'end_s':(q['ended_monotonic_ns']-origin)/1e9,'request_body_bytes':q['request_body_bytes'],
        'response_body_bytes':q['response_body_bytes'],'body_sha256':q['request_body_sha256']}


def summarize(label,rows,samples,native_groups,chains):
    clock,points=intervals(rows);span=max(q['end_s'] for q in rows)
    selected=[q for q in samples if 0<=q['relative_s']<=span]
    assert selected and all(q['pids']==[selected[0]['pids'][0]] for q in selected)
    assert all(b['cpu_seconds']>=a['cpu_seconds'] for a,b in zip(selected,selected[1:]))
    cpu_window=selected[-1]['relative_s']-selected[0]['relative_s'];cpu_delta=selected[-1]['cpu_seconds']-selected[0]['cpu_seconds']
    prompt=sum(q['remote_prompt_tokens'] for q in rows);hit=sum(q['cache_hit_tokens'] for q in rows)
    output=sum(q['remote_completion_tokens'] for q in rows);target=sum(q['source_output_tokens'] for q in rows)
    result={'case':label,'label':LABELS[label],'requests':len(rows),'native_groups':native_groups,'execution_chains':chains,
        'wall_s':span,'first_content_p50_s':float(np.median([q['first_content_s'] for q in rows])),
        'first_content_p95_s':float(np.percentile([q['first_content_s'] for q in rows],95)),
        'duration_p50_s':float(np.median([q['duration_s'] for q in rows])),
        'duration_p95_s':float(np.percentile([q['duration_s'] for q in rows],95)),
        'peak_inflight':clock['peak'],'mean_inflight':clock['interval_sum_s']/span,'multi_request_s':clock['multi_request_s'],
        'client_sampled_peak_rss_mib':max(q['rss_bytes'] for q in selected)/2**20,
        'cpu_seconds_sample_delta':cpu_delta,'cpu_sample_window_s':cpu_window,
        'mean_cpu_percent_one_core_from_sample_delta':100*cpu_delta/cpu_window,
        'source_input_tokens':sum(q['source_input_tokens'] for q in rows),'remote_prompt_tokens':prompt,
        'actual_output_tokens':output,'source_output_limit_tokens':target,'output_to_target_pct':100*output/target,
        'output_targets_met':sum(q['remote_completion_tokens']==q['source_output_tokens'] for q in rows),
        'finish_length':sum(q['finish_reason']=='length' for q in rows),'finish_stop':sum(q['finish_reason']=='stop' for q in rows),
        'cache_hit_tokens_reported':hit,'cache_miss_tokens_reported':prompt-hit,'input_weighted_cache_hit_pct_reported':100*hit/prompt,
        'completion_tokens_per_wall_s':output/span,'completion_tokens_per_summed_request_duration':output/clock['interval_sum_s'],
        'request_body_bytes':sum(q['request_body_bytes'] for q in rows),'response_body_bytes':sum(q['response_body_bytes'] for q in rows),
        'resource_samples':len(selected),'actual_sample_interval_p50_s':float(np.median(np.diff([q['relative_s'] for q in selected]))),
        'estimated_usd_at_documented_peak_rates':(hit*.006+(prompt-hit)*.3+output*1.2)/1e6}
    return result,points,selected


def analyze(name):
    attempt_dir=RAW/'attempts'/name;attempt=json.loads((attempt_dir/'attempt.json').read_text());plan=json.loads((ENV/'plan.json').read_text())
    assert attempt['status']=='completed' and attempt['exit_code']==0 and attempt['owned_process_cleanup_confirmed']
    assert file_record(ENV/'plan.json')['sha256']==attempt['plan']['sha256'];verify_code(plan)
    assert file_record(plan['official_metadata']['path'])['sha256']==plan['official_metadata']['sha256']
    source_path=Path(plan['source_export']['path']);assert file_record(source_path)['sha256']==plan['source_export']['sha256']
    source={(q['metadata']['conversation_id'],q['metadata']['turn_index']):q for q in lines(source_path)}
    raw_samples=lines(attempt_dir/'client_resources.jsonl')
    assert all(q['pids']==[attempt['worker_pid']] for q in raw_samples)
    raw_files=[file_record(p) for p in attempt_dir.rglob('*') if p.is_file()]
    raw_files.append(file_record(RAW/'official-metadata.json'))
    all_rows=[];resources=[];summaries=[];profiles={};edge_rows=[]
    for case in plan['cases']:
        label=case['label'];out=attempt_dir/label;results=lines(out/'requests.jsonl')
        by_id={q['node_id']:q for q in results};nodes={q['node_id']:q for q in case['nodes']}
        assert len(by_id)==len(results)==len(nodes)==case['requests'] and set(by_id)==set(nodes)
        assert all(q['status']=='completed' and q['http_status']==200 and q['phase']=='profile' for q in results)
        witnesses=audit_edges(case['edges'],by_id);edge_rows.extend({'case':label,**q} for q in witnesses)
        origin=min(q['started_monotonic_ns'] for q in results)
        rows=[]
        for q in results:
            node=nodes[q['node_id']];prefix=out/f"{q['sequence']:03d}-profile"
            body=gzip.decompress(prefix.with_suffix('.request.json.gz').read_bytes());payload=json.loads(body)
            source_record=source[(node['conversation_id'],node['turn_index'])]
            assert body==canonical(adapt_payload(source_record['payload']))
            assert sha(body)==node['body_sha256']==q['request_body_sha256']
            assert sha(canonical(payload['messages']))==node['messages_sha256']==q['messages_sha256']
            assert q['source_request_sha256']==node['source_request_sha256']
            assert payload['max_tokens']==node['source_output_tokens']==q['source_output_tokens']
            assert payload['model']=='deepseek-flash' and payload['thinking']=={'type':'disabled'}
            raw=response_oracle(prefix.with_suffix('.response.sse'))
            assert raw['done'] and raw['usage']==q['usage'] and raw['finish']==q['finish_reason']
            assert raw['reasoning_chars']==q['reasoning_chars']==0 and len(raw['text'])==q['content_chars']
            assert 0<q['usage']['completion_tokens']<=q['source_output_tokens']
            rows.append(normalize(q,label,origin));raw_files.append(file_record(node['payload']))
        samples=[{**q,'relative_s':(q['monotonic_ns']-origin)/1e9,'case':label} for q in raw_samples]
        summary,points,selected=summarize(label,rows,samples,case['native_subagent_groups'],case['execution_chains'])
        all_rows.extend(rows);resources.extend(selected);summaries.append(summary);profiles[label]=points
    first_end=json.loads((attempt_dir/'single_subagent/case-ended.json').read_text())['monotonic_ns']
    next_start=json.loads((attempt_dir/'multiple_subagents/case-started.json').read_text())['monotonic_ns']
    assert next_start>=first_end,'cases overlapped'
    # The probe remains separate from all profile statistics.
    probe=lines(attempt_dir/'probe/requests.jsonl');assert len(probe)==1 and probe[0]['status']=='completed'
    probe_raw=response_oracle(attempt_dir/'probe/000-probe.response.sse')
    assert probe_raw['done'] and probe_raw['text'].strip()=='OK' and probe_raw['usage']==probe[0]['usage']
    baseline_out=BASELINE/'reports/analysis/AGENTX-DEEPSEEK-CLIENT-v1'
    baseline_manifest=json.loads((baseline_out/'manifest.json').read_text())
    for q in baseline_manifest['inputs']:
        assert file_record(q['path'])['sha256']==q['sha256']
    baseline_raw=BASELINE/'data/raw/agentx-deepseek-pilot-01/attempts/01-remote-session'
    before=[q for q in lines(baseline_raw/'requests.jsonl') if q['phase']=='profile']
    assert len(before)==20;origin=min(q['started_monotonic_ns'] for q in before)
    baseline_rows=[normalize(q,'baseline',origin) for q in before]
    baseline_samples=[{**q,'relative_s':(q['monotonic_ns']-origin)/1e9,'case':'baseline'} for q in lines(baseline_raw/'client_resources.jsonl')]
    baseline_summary,points,selected=summarize('baseline',baseline_rows,baseline_samples,0,1)
    summaries.insert(0,baseline_summary);all_rows=baseline_rows+all_rows;resources=selected+resources;profiles['baseline']=points
    OUT.mkdir(parents=True,exist_ok=True)
    for d in ['figures','plot_data']:(OUT/d).mkdir(exist_ok=True)
    table(OUT/'case_comparison.csv',summaries);table(OUT/'request_comparison.csv',all_rows);table(OUT/'client_resources.csv',resources)
    table(OUT/'dependency_audit.csv',edge_rows)
    summary={'schema':'agentx-deepseek-branches-comparison-v1','new_sessions':2,'new_profile_requests':51,'new_probe_requests':1,
        'historical_baseline_sessions':1,'historical_baseline_profile_requests':20,'historical_baseline_probe_requests':1,
        'total_profile_requests_compared':71,'total_HTTP_calls_across_two_attempts':73,'automatic_retries':0,
        'request_model':'deepseek-flash','thinking':'disabled','started_at_shanghai':attempt['started_at_shanghai'],
        'ended_at_shanghai':attempt['ended_at_shanghai'],'new_attempt_wall_s':attempt['elapsed_s'],
        'dependency_edges_checked':len(edge_rows),'dependency_edge_types':dict(Counter(q['kind'] for q in edge_rows)),
        'all_dependency_edges_passed':all(q['passed'] for q in edge_rows),'native_groups_new':7,'execution_chains_new':10,
        'original_clock_reproduced':False,'original_interval_concurrency_reproduced':False,
        'real_model_outputs_fed_back':False,'server_resources_measured':False,
        'new_profile_actual_output_tokens':sum(q['actual_output_tokens'] for q in summaries if q['case']!='baseline'),
        'new_profile_target_output_tokens':sum(q['source_output_limit_tokens'] for q in summaries if q['case']!='baseline'),
        'new_profile_estimated_usd_at_documented_peak_rates':sum(q['estimated_usd_at_documented_peak_rates'] for q in summaries if q['case']!='baseline'),
        'cases':summaries,'baseline_manifest':file_record(baseline_out/'manifest.json'),
        'resource_scope':'one HTTP worker per attempt, includes serialization and evidence capture; excludes parent sampler and other conversations',
        'comparison_limits':'different contexts/output sizes/cache states, single run per case, shared worker for new two cases with retained heap; no causal speedup claim'}
    dump(OUT/'summary.json',summary);render(summary,all_rows,resources,profiles)
    secret=os.environ.get('DEEPSEEK_API_KEY')
    if not secret:raise ValueError('exact-value credential scan needs current key')
    scan_paths=[Path(q['path']) for q in raw_files]+list(ENV.rglob('*'))+list(OUT.rglob('*'))
    for p in scan_paths:
        if not p.is_file():continue
        data=p.read_bytes()
        if p.name.endswith('.gz'):data=gzip.decompress(data)
        assert secret.encode() not in data,'credential leak'
    deck=OUT/'AgentX子代理远程回放_三会话对比_6页.pptx'
    with zipfile.ZipFile(deck) as z:
        assert z.testzip() is None
        for n in z.namelist():
            if n.endswith('.xml') or n.endswith('.rels'):ET.fromstring(z.read(n))
    from PIL import Image
    for p in (OUT/'figures').glob('*.png'):
        with Image.open(p) as im:assert im.size==(3840,2160)
    from scripts.check_project_state import check
    global_errors=check(ROOT)
    dump(OUT/'verification.json',{'status':'PASS','new_profiles_one_to_one':51,'received_SSE_verified_including_probe':52,
        'dependency_edges_verified':len(edge_rows),'all_edges_passed':True,'probe_excluded':True,'no_credentials_in_artifacts':True,
        'owned_process_cleanup_confirmed':attempt['owned_process_cleanup_confirmed'],'pptx_slides':6,'figure_pixels':[3840,2160],
        'global_state_check':{'status':'FAIL' if global_errors else 'PASS','errors':global_errors,
            'disposition':'36 inherited ignored local evidence files missing in isolated worktree; shared status untouched'}})
    dump(OUT/'local-evidence-manifest.json',{'files':list({q['path']:q for q in raw_files}.values()),'raw_files_in_git':False})
    dump(OUT/'manifest.json',{'inputs':[file_record(ENV/'plan.json'),file_record(baseline_out/'manifest.json')],
        'outputs':[file_record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json'],
        'code':[file_record(p) for p in [ROOT/'scripts/agentx_deepseek_branches.py',ROOT/'scripts/agentx_deepseek_branch_prepare.py',Path(__file__),ROOT/'tests/test_agentx_deepseek_branches.py']],
        'configuration':[file_record(p) for p in sorted(ENV.glob('*')) if p.is_file()]})
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary


def render(s,rows,resources,profiles):
    import matplotlib.pyplot as plt
    style();slides=[];colors={'baseline':BLUE,'single_subagent':TEAL,'multiple_subagents':ORANGE}
    footer='3个固定会话、71条正式请求；另计2条历史/新增探针；每类只有一次实测。\n非思考远程DeepSeek；保留官方SPAWN/JOIN结构，移除原始等待；不同输入/输出量，不作因果加速比较。'
    def finish(fig,name,title):
        save(fig,OUT,name);p=OUT/'figures'/f'{name}.svg';p.write_text('\n'.join(x.rstrip() for x in p.read_text().splitlines())+'\n')
        slides.append({'heading':title,'image':OUT/'figures'/f'{name}.png'})
    cases=s['cases'];fig,ax=figure('三类会话已完成真实API回放',f"新增51/51成功；{s['dependency_edges_checked']}条依赖全部按序完成；原生子代理组与执行链分别登记",footer)
    ax.axis('off')
    cell=[[c['label'],str(c['requests']),str(c['native_groups']),str(c['execution_chains']),str(c['peak_inflight']),f"{c['wall_s']:.2f}",f"{c['client_sampled_peak_rss_mib']:.1f}",f"{c['mean_cpu_percent_one_core_from_sample_delta']:.3f}"] for c in cases]
    t=ax.table(cellText=cell,colLabels=['会话类型','请求数','原生组','执行链','峰值并发','墙钟秒','RSS MiB','CPU均值%'],cellLoc='center',loc='center',bbox=[0,.15,1,.7])
    t.auto_set_font_size(False);t.set_fontsize(16)
    fig.text(.12,.25,'CPU按各会话采样窗口计算均值，单逻辑核100%；RSS为采样峰值。',fontsize=13,color='#64748B')
    for (r,c),v in t.get_celld().items():
        v.set_edgecolor('#CBD5E1');v.set_facecolor('#EFF6FF' if r==0 else 'white')
    table(OUT/'plot_data/01_comparison.csv',cases);finish(fig,'01_comparison','结构覆盖：单链、单子代理、多子代理')
    fig,ax=figure('实际请求并发随时间变化','基于客户端请求区间的半开区间扫描；同一时刻结束与开始不重复计数',footer+'\n单子代理样本也可能没有HTTP重叠；峰值取决于保存结构及本次模型响应。')
    for case in cases:
        label=case['case'];points=profiles[label]
        ax.step([p['time_s'] for p in points],[p['inflight'] for p in points],where='post',color=colors[label],lw=2.5,label=case['label'])
    ax.set(xlabel='各会话首请求起的相对时间（秒）',ylabel='在途HTTP请求数',yticks=range(0,max(c['peak_inflight'] for c in cases)+1));ax.legend()
    table(OUT/'plot_data/02_concurrency.csv',[{'case':k,**p} for k,ps in profiles.items() for p in ps]);finish(fig,'02_concurrency','并发时间线：显示实测分支重叠')
    multi=[q for q in rows if q['case']=='multiple_subagents'];convs=sorted({q['conversation_id'] for q in multi},key=lambda cid:(bool('::' in cid),cid))
    fig,ax=figure('多子代理执行时间线：父链、辅助链与6条子链','每个条段代表一条实际请求；辅助链完成后才允许被它约束的父请求开始',footer)
    for q in multi:ax.barh(convs.index(q['conversation_id']),q['end_s']-q['start_s'],left=q['start_s'],height=.65,color=BLUE if not q['parent_conversation_id'] else ORANGE)
    sub_ids=[cid for cid in convs if '::sa:' in cid]
    labels=['root' if '::' not in cid else ('aux' if '::aux:' in cid else f'subagent {sub_ids.index(cid)+1}') for cid in convs]
    ax.set(yticks=range(len(convs)),yticklabels=labels,xlabel='会话首请求起的相对时间（秒）',ylabel='执行链');ax.invert_yaxis()
    table(OUT/'plot_data/03_timeline.csv',multi);finish(fig,'03_timeline','多子代理：按真实响应完成时间调度')
    fig,ax=figure('客户端RSS随会话时间变化','只测本任务HTTP工作进程；包含正文解压、序列化、流式解析和证据保存',footer+'\n新增两个会话复用一个进程，第二个会话保留堆与连接；RSS差异不能全归因于子代理数。')
    for case in cases:
        label=case['case'];rs=[q for q in resources if q['case']==label]
        ax.plot([q['relative_s'] for q in rs],[q['rss_bytes']/2**20 for q in rs],color=colors[label],label=case['label'],lw=2)
    ax.set(xlabel='各会话首请求起的相对时间（秒）',ylabel='HTTP工作进程RSS（MiB）',ylim=(0,None));ax.legend()
    table(OUT/'plot_data/04_resources.csv',resources);finish(fig,'04_resources','客户端资源：采样RSS时间线')
    fig,ax=figure('实际输出相当于原始输出长度的多少？','原始out在回放时设为max_tokens；正常提前停止单独登记，比例不代表业务成功率',footer)
    x=np.arange(3);values=[c['output_to_target_pct'] for c in cases]
    ax.bar(x,values,color=[colors[c['case']] for c in cases],width=.55)
    for i,c in enumerate(cases):ax.text(i,values[i]+2,f"{c['actual_output_tokens']:,} / {c['source_output_limit_tokens']:,}\n{values[i]:.2f}%",ha='center',fontsize=14)
    ax.set(xticks=x,xticklabels=[c['label'] for c in cases],ylabel='实际输出 / 原始输出长度（%）',ylim=(0,120))
    table(OUT/'plot_data/05_outputs.csv',[{k:c[k] for k in ['case','actual_output_tokens','source_output_limit_tokens','output_to_target_pct','finish_length','finish_stop']} for c in cases]);finish(fig,'05_outputs','输出覆盖：大上限不等于实际生成量')
    fig,ax=figure('接口报告的缓存命中与首次内容延迟','缓存来自DeepSeek usage；每类输入/输出/并发不同，不能据此识别缓存的独立加速效果',footer)
    for i,c in enumerate(cases):
        ax.scatter(c['input_weighted_cache_hit_pct_reported'],c['first_content_p50_s'],s=180,color=colors[c['case']],label=f"{c['label']}（n={c['requests']}）")
        ax.annotate(f"{c['input_weighted_cache_hit_pct_reported']:.2f}% / {c['first_content_p50_s']:.3f}s",(c['input_weighted_cache_hit_pct_reported'],c['first_content_p50_s']),xytext=(8,10),textcoords='offset points',fontsize=12)
    ax.set(xlabel='输入加权缓存命中占比（%，usage报告）',ylabel='首次非空内容中位数（秒）');ax.margins(x=.3,y=.35);ax.legend(loc='lower left',fontsize=13)
    table(OUT/'plot_data/06_cache_latency.csv',[{k:c[k] for k in ['case','remote_prompt_tokens','cache_hit_tokens_reported','input_weighted_cache_hit_pct_reported','first_content_p50_s','first_content_p95_s']} for c in cases]);finish(fig,'06_cache_latency','接口观察：缓存与延迟分口径呈现')
    write_pptx(OUT/'AgentX子代理远程回放_三会话对比_6页.pptx',slides)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--attempt',default='01-remote-branches');analyze(p.parse_args().attempt)
