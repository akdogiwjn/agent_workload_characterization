"""Audit repeated frozen requests and present run-level descriptive variation."""
from __future__ import annotations

from collections import defaultdict
import gzip
import json
import os
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from scripts.agentx_deepseek_pilot import ROOT, canonical, sha, dump, lines, file_record
from scripts.agentx_deepseek_repeats import RAW, ENV, BASELINE, BRANCHES
from scripts.agentx_deepseek_branches import verify_code
from scripts.agentx_deepseek_branch_analysis import normalize, summarize, audit_edges
from scripts.agentx_deepseek_analysis import response_oracle
from scripts.agentx_deep_analysis import table
from scripts.agentx_deep_presentation import style, figure, save, write_pptx, BLUE, ORANGE

OUT=ROOT/'reports/analysis/AGENTX-DEEPSEEK-REPEATS-v1'
LABELS={'baseline':'单链基线','multiple_subagents':'多子代理'}
METRICS=['wall_s','first_content_p50_s','first_content_p95_s','client_sampled_peak_rss_mib',
         'mean_cpu_percent_one_core_from_sample_delta','actual_output_tokens','output_to_target_pct',
         'input_weighted_cache_hit_pct_reported']


def paired_changes(rows):
    groups=defaultdict(dict)
    for q in rows:
        key=(q['case'],q['node_id']); r=q['replicate']
        if r in groups[key]:raise ValueError('duplicate run observation for source request')
        groups[key][r]=q
    output=[]
    for (case,node),runs in sorted(groups.items()):
        if set(runs)!={1,2,3}:raise ValueError('missing replicate')
        first=runs[1]
        for r in [2,3]:
            q=runs[r]
            if any(first[k]!=q[k] for k in ['body_sha256','source_pointer','source_request_sha256']):
                raise ValueError('paired request identity changed')
            output.append({'case':case,'node_id':node,'index':first['index'],'replicate':r,
                'source_pointer':first['source_pointer'],'body_sha256':first['body_sha256'],
                'r1_first_content_s':first['first_content_s'],'repeat_first_content_s':q['first_content_s'],
                'first_content_change_s':q['first_content_s']-first['first_content_s'],
                'r1_output_tokens':first['remote_completion_tokens'],'repeat_output_tokens':q['remote_completion_tokens'],
                'r1_cache_hit_tokens':first['cache_hit_tokens'],'repeat_cache_hit_tokens':q['cache_hit_tokens']})
    return output


def run_ranges(metrics):
    groups=defaultdict(dict)
    for q in metrics:
        if q['replicate'] in groups[q['case']]:raise ValueError('duplicate run metric')
        groups[q['case']][q['replicate']]=q
    output=[]
    for label,runs in sorted(groups.items()):
        if set(runs)!={1,2,3}:raise ValueError('three observations required')
        for metric in METRICS:
            values=[runs[r][metric] for r in [1,2,3]]
            output.append({'case':label,'metric':metric,'n_runs':3,'r1':values[0],'r2':values[1],'r3':values[2],
                           'min':min(values),'max':max(values),'median':statistics.median(values),'mean':statistics.mean(values)})
    return output


def render(metrics,rows,ranges):
    style(); slides=[]
    footer='每类 n=3；R1 为历史观察，R2/R3 为独立新进程。远程缓存/服务负载未控制；不作因果或显著性判断。'
    def finish(fig,name,title):
        save(fig,OUT,name)
        svg=OUT/'figures'/f'{name}.svg'
        svg.write_text('\n'.join(q.rstrip() for q in svg.read_text().splitlines())+'\n')
        slides.append({'heading':title,'image':OUT/'figures'/f'{name}.png'})
    fig,ax=figure('两个案例各三次：比较实际执行波动','新增 100 条正式执行 + 4 次探针；两类 50 个唯一请求，共 150 次正式观察',footer)
    ax.axis('off')
    cols=['案例 / 轮次','会话耗时 s','首内容 P50 s','首内容 P95 s','峰值 RSS MiB','实际输出 token','缓存命中 %']
    vals=[[f"{LABELS[q['case']]} R{q['replicate']}",f"{q['wall_s']:.2f}",f"{q['first_content_p50_s']:.3f}",
        f"{q['first_content_p95_s']:.3f}",f"{q['client_sampled_peak_rss_mib']:.2f}",f"{q['actual_output_tokens']:,}",
        f"{q['input_weighted_cache_hit_pct_reported']:.2f}"] for q in metrics]
    t=ax.table(cellText=vals,colLabels=cols,loc='center',cellLoc='center');t.auto_set_font_size(False);t.set_fontsize(14);t.scale(1,2.7)
    for (r,c),cell in t.get_celld().items():
        cell.set_edgecolor('#CBD5E1')
        if r==0:cell.set_facecolor('#DBEAFE');cell.set_text_props(weight='bold')
    finish(fig,'01-overview','三次重复实测总览')
    fig,ax=figure('首内容延迟：逐次 P50 / P95','每个分位数在该轮的 20 或 30 个请求内计算；连线只表示观察顺序',footer)
    for label,color in zip(LABELS,[BLUE,ORANGE]):
        current=sorted([q for q in metrics if q['case']==label],key=lambda q:q['replicate'])
        for field,ls,marker,desc in [('first_content_p50_s','-','o','P50'),('first_content_p95_s','--','s','P95')]:
            ax.plot([1,2,3],[q[field] for q in current],color=color,linestyle=ls,marker=marker,lw=2.5,label=f'{LABELS[label]} {desc}')
    ax.set_xticks([1,2,3],['R1（历史）','R2','R3']);ax.set_ylabel('首内容延迟 / 秒');ax.legend(ncol=2)
    finish(fig,'02-first-content','首内容延迟的逐次变化')
    fig,ax=figure('会话耗时：三次观察与最小—最大范围','耗时从本轮首个正式请求开始，到最后一个正式请求完成；不含探针',footer)
    for i,(label,color) in enumerate(zip(LABELS,[BLUE,ORANGE])):
        values=[q['wall_s'] for q in metrics if q['case']==label]
        ax.vlines(i,min(values),max(values),color=color,lw=6,alpha=.3)
        for j,(q,offset) in enumerate(zip([q for q in metrics if q['case']==label],[-.08,0,.08])):
            ax.scatter(i+offset,q['wall_s'],color=color,s=100);ax.annotate(f"R{q['replicate']}  {q['wall_s']:.2f}s",(i+offset,q['wall_s']),xytext=(12,(j-1)*18),textcoords='offset points',fontsize=14)
    ax.set_xlim(-.4,1.7);ax.set_xticks([0,1],list(LABELS.values()));ax.set_ylabel('正式会话耗时 / 秒')
    finish(fig,'03-wall-range','会话耗时的三次范围')
    fig,ax=figure('客户端资源：逐次 RSS 与 CPU','仅 HTTP 工作进程；包括序列化和证据保存，不含采样父进程或其他会话',
        footer+'\nR1 多子代理接续同进程的单子代理；新轮次每次独立进程，资源值不完全同条件。')
    ax.remove();axes=fig.subplots(1,2);fig.subplots_adjust(left=.09,right=.96,bottom=.20,top=.73,wspace=.28)
    for axis,field,ylabel in zip(axes,['client_sampled_peak_rss_mib','mean_cpu_percent_one_core_from_sample_delta'],
        ['采样峰值 RSS / MiB','采样窗口平均 CPU / 单核 %']):
        for label,color in zip(LABELS,[BLUE,ORANGE]):
            current=[q for q in metrics if q['case']==label]
            axis.plot([1,2,3],[q[field] for q in current],'-o',color=color,label=LABELS[label])
        axis.set_ylabel(ylabel);axis.set_ylim(0,max(q[field] for q in metrics)*1.3)
        axis.set_xticks([1,2,3],['R1（历史）','R2','R3']);axis.grid(alpha=.17);axis.legend(loc='lower left')
    finish(fig,'04-client-resources','客户端资源的重复观察')
    fig,ax=figure('输出长度：重复执行仍允许模型自然结束','原始输出 token 数仅作为 max_tokens 上限；输入由固定合成文本构造',footer+'\n原始业务工具未执行；长度比例是负载指标，不是任务成功率。')
    for label,color in zip(LABELS,[BLUE,ORANGE]):
        current=[q for q in metrics if q['case']==label]
        ax.plot([1,2,3],[q['output_to_target_pct'] for q in current],'-o',color=color,lw=2.5,label=f"{LABELS[label]}：原始合计 {current[0]['source_output_limit_tokens']:,}")
        for q in current:ax.annotate(f"{q['actual_output_tokens']:,}",(q['replicate'],q['output_to_target_pct']),xytext=(0,12),textcoords='offset points',ha='center',fontsize=14)
    ax.axhline(100,color='#64748B',ls=':',label='原始输出长度合计 100%');ax.set_ylim(0,116);ax.set_ylabel('实际输出 / 原始输出长度合计 %');ax.set_xticks([1,2,3],['R1（历史）','R2','R3']);ax.legend(loc='center right',fontsize=13)
    finish(fig,'05-output-coverage','原始输出负载的覆盖情况')
    fig,ax=figure('服务返回的输入缓存命中比例','按 prompt token 加权；没有清缓存或添加 cache-busting 字段',footer+'\n缓存比例与延迟同时变化，不能单独据此归因。')
    for label,color in zip(LABELS,[BLUE,ORANGE]):
        current=[q for q in metrics if q['case']==label]
        ax.plot([1,2,3],[q['input_weighted_cache_hit_pct_reported'] for q in current],'-o',color=color,lw=2.5,label=LABELS[label])
        for q in current:ax.annotate(f"{q['input_weighted_cache_hit_pct_reported']:.2f}%",(q['replicate'],q['input_weighted_cache_hit_pct_reported']),xytext=(0,12),textcoords='offset points',ha='center',fontsize=14)
    ax.set_ylim(0,110);ax.set_ylabel('输入缓存命中 token 比例 %');ax.set_xticks([1,2,3],['R1（历史）','R2','R3']);ax.legend()
    finish(fig,'06-cache','缓存状态的逐次变化')
    fig,ax=figure('同一源请求的首内容延迟配对','横轴为固定请求索引，与完成顺序无关；多子代理索引不表示线性时间',footer)
    ax.remove();axes=fig.subplots(1,2);fig.subplots_adjust(left=.09,right=.96,bottom=.20,top=.73,wspace=.25)
    for axis,(label,title) in zip(axes,LABELS.items()):
        for r,color in zip([1,2,3],[BLUE,ORANGE,'#0D9488']):
            current=sorted([q for q in rows if q['case']==label and q['replicate']==r],key=lambda q:q['index'])
            axis.plot([q['index'] for q in current],[q['first_content_s'] for q in current],'-o',color=color,ms=4,label=f'R{r}')
        axis.set_title(title);axis.set_xlabel('固定源请求索引');axis.set_ylabel('首内容延迟 / 秒');axis.grid(alpha=.17);axis.legend()
    finish(fig,'07-paired-requests','逐请求配对核对')
    write_pptx(OUT/'AgentX重复实测_汇报版_7页.pptx',slides)
    dump(OUT/'slides.json',[{'heading':q['heading'],'image':str(q['image'].relative_to(OUT))} for q in slides])
    table(OUT/'plot_data/run_metrics.csv',metrics);table(OUT/'plot_data/request_first_content.csv',rows);table(OUT/'plot_data/run_ranges.csv',ranges)


def analyze():
    plan=json.loads((ENV/'plan.json').read_text()); verify_code(plan)
    for item in plan['original_plans']:
        assert file_record(item['path'])['sha256']==item['sha256']
    # Verify historical evidence against the manifests already used by the five-case report.
    prior=json.loads((ROOT/'reports/analysis/AGENTX-DEEPSEEK-FIVE-CASES-v1/summary.json').read_text())
    historical=[]
    for key in ['baseline_manifest','branch_manifest']:
        item=prior[key]; assert file_record(item['path'])['sha256']==item['sha256']
        path=Path(item['path']); manifest=json.loads(path.read_text())
        for q in manifest['inputs']:assert file_record(q['path'])['sha256']==q['sha256']
        evidence=path.parent/'local-evidence-manifest.json'
        assert file_record(evidence)['sha256']==next(q['sha256'] for q in manifest['outputs'] if q['path']==str(evidence))
        for q in json.loads(evidence.read_text())['files']:
            assert file_record(q['path'])['sha256']==q['sha256']
        historical.append(file_record(path))
    cases={q['label']:q for q in plan['cases']}
    base_root=BASELINE/'data/raw/agentx-deepseek-pilot-01/attempts/01-remote-session'
    multi_root=BRANCHES/'data/raw/agentx-deepseek-branches-01/attempts/01-remote-branches'
    observations=[('baseline',1,base_root,base_root),('multiple_subagents',1,multi_root,multi_root/'multiple_subagents')]
    attempts=[]
    for run in plan['runs']:
        root=RAW/'attempts'/run['name']; attempt=json.loads((root/'attempt.json').read_text())
        assert attempt['status']=='completed' and attempt['exit_code']==0 and attempt['owned_process_cleanup_confirmed']
        assert attempt['plan']['sha256']==file_record(ENV/'plan.json')['sha256']
        attempts.append(attempt)
        observations.append((run['case'],run['replicate'],root,root/run['case']))
    rows=[];metrics=[];resources=[];edges=[];checks=[];probes=[]
    for label,r,root,directory in sorted(observations,key=lambda q:(q[0],q[1])):
        case=cases[label]; nodes={q['node_id']:q for q in case['nodes']}
        results=[q for q in lines(directory/'requests.jsonl') if q['phase']=='profile']
        by_id={q.get('node_id',f"baseline#{q['index']}"):q for q in results}
        assert len(results)==len(by_id)==case['requests'] and set(by_id)==set(nodes)
        edges.extend({'case':label,'replicate':r,**q} for q in audit_edges(case['edges'],by_id))
        origin=min(q['started_monotonic_ns'] for q in results); current=[]
        for nid,q in by_id.items():
            node=nodes[nid]; assert q['status']=='completed' and q['http_status']==200
            assert q['source_request_sha256']==node['source_request_sha256'] and q['source_pointer']==node['source_pointer']
            prefix=directory/f"{q['sequence']:03d}-profile"
            body=gzip.decompress(prefix.with_suffix('.request.json.gz').read_bytes()); payload=json.loads(body)
            assert sha(body)==q['request_body_sha256']==node['body_sha256']
            assert body==gzip.decompress(Path(node['payload']).read_bytes())
            assert sha(canonical(payload['messages']))==node['messages_sha256']==q['messages_sha256']
            assert payload['max_tokens']==q['source_output_tokens']==node['source_output_tokens']
            assert payload['model']=='deepseek-flash' and payload['thinking']=={'type':'disabled'} and payload['temperature']==0
            oracle=response_oracle(prefix.with_suffix('.response.sse'))
            assert oracle['done'] and oracle['usage']==q['usage'] and oracle['finish']==q['finish_reason']
            assert oracle['models']==['deepseek-flash'] and prefix.with_suffix('.response.sse').stat().st_size==q['response_body_bytes']
            assert oracle['reasoning_chars']==q['reasoning_chars']==0 and len(oracle['text'])==q['content_chars']
            assert 0<q['usage']['completion_tokens']<=q['source_output_tokens']
            current.append({**normalize(q,label,origin),'replicate':r,'source_request_sha256':q['source_request_sha256']})
            checks.append({'case':label,'replicate':r,'node_id':nid,'body_sha256':sha(body),'source_request_sha256':q['source_request_sha256'],
                           'body_and_source_verified':True,'raw_sse_verified':True,'source_output_limit_preserved':True})
        attempt=json.loads((root/'attempt.json').read_text()); samples=lines(root/'client_resources.jsonl')
        assert all(q['pids']==[attempt['worker_pid']] for q in samples if q['pids'])
        samples=[{**q,'relative_s':(q['monotonic_ns']-origin)/1e9,'case':label,'replicate':r} for q in samples if q['pids']]
        metric,points,selected=summarize(label,current,samples,case['native_subagent_groups'],case['execution_chains'])
        assert metric['peak_inflight']<=8 and (label!='baseline' or metric['peak_inflight']==1)
        metric.update(replicate=r,started_at_shanghai=min(q['started_at_shanghai'] for q in results),
                      process_prelude='probe + single_subagent case' if label=='multiple_subagents' and r==1 else 'probe only')
        metrics.append(metric);rows.extend(current);resources.extend(selected)
        if r>1:
            probe=lines(root/'probe/requests.jsonl');assert len(probe)==1;probe=probe[0]
            raw=response_oracle(root/'probe/000-probe.response.sse')
            assert probe['status']=='completed' and probe['http_status']==200 and raw['done'] and raw['usage']==probe['usage'] and raw['text'].strip()=='OK'
            expected_probe={'model':'deepseek-flash','messages':[{'role':'user','content':'Reply only with OK.'}],
                            'max_tokens':16,'stream':True,'stream_options':{'include_usage':True},'thinking':{'type':'disabled'},'temperature':0}
            probe_body=gzip.decompress((root/'probe/000-probe.request.json.gz').read_bytes())
            assert probe_body==canonical(expected_probe) and sha(probe_body)==probe['request_body_sha256']
            probes.append({'case':label,'replicate':r,'status':probe['status'],'http_status':probe['http_status'],
                           'completion_tokens':probe['usage']['completion_tokens'],'excluded_from_profile_metrics':True})
    assert len(rows)==150 and len(edges)==147 and len(probes)==4
    paired=paired_changes(rows); ranges=run_ranges(metrics)
    for d in [OUT,OUT/'figures',OUT/'plot_data']:d.mkdir(parents=True,exist_ok=True)
    for name,data in [('run_metrics',metrics),('request_metrics',rows),('paired_changes',paired),('run_ranges',ranges),
                      ('client_resources',resources),('dependency_audit',edges),('request_verification',checks),('probes',probes)]:
        table(OUT/f'{name}.csv',data)
    summary={'schema':'agentx-deepseek-repeats-v1','new_profile_executions':100,'new_connectivity_probes':4,
             'repeated_case_unique_source_requests':50,'repeated_case_profile_executions':150,'replicates_per_case':3,
             'cumulative_profile_executions':217,'cumulative_unique_source_requests':117,'cumulative_unique_sessions':5,
             'cumulative_session_execution_instances':9,'cumulative_probes':9,'cumulative_chat_POSTs':226,
             'new_dependency_edges_verified':98,'all_six_run_dependency_edges_verified':147,
             'automatic_retries':0,'server_resources_measured':False,'original_business_tools_executed':False,
             'context_truncated':False,'original_output_load_reproduced':False,'significance_claimed':False,
             'started_at_shanghai':attempts[0]['started_at_shanghai'],'ended_at_shanghai':attempts[-1]['ended_at_shanghai'],
             'historical_manifests':historical,'cases':metrics,'ranges':ranges,
             'limitations':['n=3 descriptive observations only','R1 multi shared worker after single_subagent; R2/R3 fresh workers',
                'remote cache and server load uncontrolled; model alias not immutable','fixed synthetic inputs; early EOS allowed; no business tool execution',
                'source timing not reproduced; generated content not fed into later inputs','request quantiles within run; no pooled independence or causal speedup claim']}
    dump(OUT/'summary.json',summary);render(metrics,rows,ranges)
    report=['# AgentX 两类会话三次重复实测','',
        '已完成新增 4 次完整会话执行：单链基线、多子代理各追加 2 次，新增 100 条正式请求与 4 次连通性探针，全部 HTTP 200，零自动重试。',
        '每类结合历史 R1 共 3 次观察；两类涉及 50 个唯一源请求、150 次正式执行。此前五类合计仍为 117 个唯一源请求、5 个唯一会话；累计正式执行 217 次，会话执行实例 9 次，含所有探针的 Chat POST 为 226 次。重复执行没有扩大源样本覆盖。','',
        '| 案例 | 轮次 | 耗时 s | 首内容 P50 / P95 s | RSS 峰值 MiB | 单核平均 CPU % | 实际输出 / 原始长度 % | 缓存命中 % |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for q in metrics:report.append(f"| {LABELS[q['case']]} | R{q['replicate']} | {q['wall_s']:.2f} | {q['first_content_p50_s']:.3f} / {q['first_content_p95_s']:.3f} | {q['client_sampled_peak_rss_mib']:.2f} | {q['mean_cpu_percent_one_core_from_sample_delta']:.2f} | {q['actual_output_tokens']:,} / {q['output_to_target_pct']:.2f}% | {q['input_weighted_cache_hit_pct_reported']:.2f} |")
    report+=['','本轮顺序为单链 R2、多子代理 R2、多子代理 R3、单链 R3（ABBA），不是随机实验。请求正文逐字节保持首次执行版本，模型 `deepseek-flash`、关闭 thinking、temperature=0、原始输出长度对应 max_tokens 和依赖图均不变；不强制补齐输出，不将返回文本送入后续输入。完整合成输入不是原始业务提示词。',
        '','三次波动范围（非置信区间）：']
    for label in LABELS:
        selected={q['metric']:q for q in ranges if q['case']==label}
        w=selected['wall_s'];p=selected['first_content_p50_s'];o=selected['output_to_target_pct']
        report.append(f"- {LABELS[label]}：耗时 {w['min']:.2f}–{w['max']:.2f} s；首内容 P50 {p['min']:.3f}–{p['max']:.3f} s；实际输出覆盖 {o['min']:.2f}–{o['max']:.2f}%。")
    report+=['','多子代理中同一长输出请求的自然结束差异值得单列：']
    long_index=max(cases['multiple_subagents']['nodes'],key=lambda q:q['source_output_tokens'])['index']
    for q in sorted([q for q in rows if q['case']=='multiple_subagents' and q['index']==long_index],key=lambda q:q['replicate']):
        report.append(f"- 固定请求索引 {long_index}，R{q['replicate']}：实际 {q['remote_completion_tokens']:,} / 上限 {q['source_output_tokens']:,} token，结束 `{q['finish_reason']}`，请求耗时 {q['duration_s']:.2f} s。")
    report+=['','同一 max_tokens 并不保证相同实际输出量。耗时与实际生成量必须一并阅读；上述观察不能从时长差异中分离网络、缓存、生成内容和服务端负载的影响。']
    report+=['','资源只采样本任务拥有的 HTTP 工作进程及其子进程，排除采样父进程与其他会话。RSS 包含请求序列化、响应和证据保存开销；CPU 均值由正式请求窗口内首末样本累计 CPU 差除以实际采样窗口得到，百分比按单核计。采样间隔为每轮工作后 sleep 0.2 秒，实际中位间隔已逐次保存；采样峰值不是连续观测峰值。未测服务器资源或全机网络。HTTP 正文流量不含 TLS、头部和代理开销。',
        '','R1 多子代理曾在同一个进程中接续单子代理案例，可能保留堆和连接；本轮 R2/R3 各自启动新进程，仅先做一次探针。R1 单链同样仅先做探针。远程缓存、服务负载、网络和模型别名底层版本均未受控，实际输出也可随自然结束变化。因此这些结果描述所测条件下的波动，不能证明子代理造成加速、缓存造成变化，或推广到整个 AgentX。n=3 不计算置信区间或显著性。P50/P95 均在每轮内部计算，不把所有重复请求当独立样本合并推断。',
        '','原始多子代理输出负载仍未复现：重复请求不改变提前 stop 的问题。比例反映输出 token 负载，不是业务成功率。本实验没有执行原始文件、Shell、浏览器等业务工具，也没有复现原始时间间隔。此前输出控制核查见 [五类报告](../AGENTX-DEEPSEEK-FIVE-CASES-v1/summary.md)。',
        '','全部 150 次正式观察重新解析原始 SSE，并核对同一源指纹、正文 SHA256、输出上限、最终 usage 和结束字段；147 条依赖边全部通过，其中本轮新增 98 条。按案例及稳定 node_id 配对，拒绝重复、缺失或源身份变化；100 条相对 R1 的配对变化已保存。',
        '','[7 页 PPT](AgentX重复实测_汇报版_7页.pptx)；[逐轮指标](run_metrics.csv)；[逐请求指标](request_metrics.csv)；[配对变化](paired_changes.csv)；[范围统计](run_ranges.csv)。图表有 3840×2160 PNG、SVG 和 CSV；PPT 内图表为嵌入图片，标题可编辑，图内数据修改需用配套 CSV/SVG。',
        '','新实验原始请求、SSE 和资源采样位于本工作树忽略目录 `data/raw/agentx-deepseek-repeats-01/`，历史 R1 只读引用两个原工作树；清单记录绝对位置、大小和 SHA256。Git 远程备份脚本、计划、派生指标、图表、PPT 与证据身份清单，不包含被忽略的原始证据或密钥，离线重建需保留原工作树。',
        '','独立分支不修改共享 `project_state.json`、状态页或视频文件；本任务状态与待合并补丁另存 env。全局状态检查仍单列 36 个继承证据缺失（新工作树不包含历史忽略文件），未修改历史哈希来掩盖该问题；本轮自身核验单独记录。',
        '',
        '模型接口语义参照 [官方 thinking 文档](https://api-docs.deepseek.com/guides/thinking_mode/)；CSV 中沿用文档峰时单价估算字段，仅作价格参考，不是实际账单，参照 [官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)。模型别名不能锁定不可变权重。',
        '',f"执行时间（Asia/Shanghai）：{summary['started_at_shanghai']} 至 {summary['ended_at_shanghai']}。"]
    (OUT/'summary.md').write_text('\n'.join(report)+'\n')
    raw_files=[file_record(p) for p in sorted(RAW.rglob('*')) if p.is_file()]
    dump(OUT/'local-evidence-manifest.json',{'files':raw_files,'historical_manifests':historical,'ignored_raw_backed_up_by_git':False})
    secret=os.environ.get('DEEPSEEK_API_KEY')
    if not secret:raise ValueError('credential required for exact-value leak check')
    scanned=0
    for p in [Path(q['path']) for q in raw_files]+list(ENV.rglob('*'))+list(OUT.rglob('*')):
        if not p.is_file():continue
        data=p.read_bytes();data=gzip.decompress(data) if p.name.endswith('.gz') else data
        assert secret.encode() not in data,'credential leak';scanned+=1
        if p.suffix=='.pptx':
            with zipfile.ZipFile(p) as z:
                assert z.testzip() is None
                assert len([n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')])==7
                for n in z.namelist():
                    assert secret.encode() not in z.read(n),'credential leak'
                    if n.endswith(('.xml','.rels')):ET.fromstring(z.read(n))
    from PIL import Image
    for p in (OUT/'figures').glob('*.png'):
        with Image.open(p) as im:assert im.size==(3840,2160)
    from scripts.check_project_state import check
    state_errors=check(ROOT)
    missing=[e for e in state_errors if not (ROOT/e.split(': evidence mismatch')[0]).exists()]
    assert len(missing)==len(state_errors)==36
    dump(OUT/'verification.json',{'task_status':'PASS','new_formal_requests':100,'new_probes_verified':4,'six_run_source_and_SSE_verified':150,
        'unique_source_payloads':50,'matched_changes':100,'dependency_edges_verified':147,'no_credentials_in_artifacts':True,
        'credential_scan_files':scanned,'pptx_pages':7,'all_png_dimensions':'3840x2160',
        'new_owned_processes_cleaned_up':all(q['owned_process_cleanup_confirmed'] for q in attempts),
        'global_project_state_check':'FAIL_INHERITED_MISSING_IGNORED_EVIDENCE','inherited_missing_count':len(missing),
        'inherited_errors':state_errors,'shared_project_state_modified':False})
    dump(OUT/'manifest.json',{'schema':'agentx-repeats-artifacts-v1',
        'inputs':[file_record(ENV/'plan.json')]+historical,
        'code':[file_record(Path(__file__))]+plan['code'],
        'outputs':[file_record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json']})
    print(json.dumps({'status':'PASS','runs':len(metrics),'profile_observations':len(rows),'new_formal':100,'paired_changes':len(paired),'dependency_edges':len(edges)},ensure_ascii=False))


if __name__=='__main__':analyze()
