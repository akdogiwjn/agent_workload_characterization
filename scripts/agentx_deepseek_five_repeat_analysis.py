"""Audit 351 executions of 117 frozen sources; combine five descriptive strata."""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from scripts.agentx_deepseek_pilot import ROOT, canonical, sha, dump, lines, file_record
from scripts.agentx_deepseek_finish_repeats import RAW, ENV, BASELINE, BRANCHES, COVERAGE
from scripts.agentx_deepseek_branches import verify_code
from scripts.agentx_deepseek_branch_analysis import normalize, audit_edges, intervals
from scripts.agentx_deepseek_coverage_analysis import summarize
from scripts.agentx_deepseek_repeat_analysis import paired_changes, run_ranges
from scripts.agentx_deepseek_analysis import response_oracle
from scripts.agentx_deep_analysis import table

PREVIOUS=Path('/home/lcq/agentx_deepseek_repeats_20261023')
STEP2=Path('/home/lcq/agentx_replay_smoke_20261023')
OUT=ROOT/'reports/analysis/AGENTX-DEEPSEEK-FIVE-REPEATS-v1'
LABELS={'baseline':'单链基线','single_subagent':'单子代理','multiple_subagents':'多子代理',
        'serial_intervals':'原始区间串行','long_context':'长上下文'}


def verify_source_repetitions(rows, expected):
    key=lambda q:(q['trace_id'],q['source_outer_idx'],q.get('source_inner_idx'))
    wanted={key(q):q['source_request_sha256'] for q in expected}
    if len(wanted)!=len(expected):raise ValueError('duplicate expected source')
    seen=defaultdict(set)
    for q in rows:
        k=key(q);r=q['replicate']
        if k not in wanted or wanted[k]!=q['source_request_sha256']:raise ValueError('unexpected or changed source')
        if r in seen[k]:raise ValueError('source repeated within replicate')
        seen[k].add(r)
    if set(seen)!=set(wanted) or any(reps!={1,2,3} for reps in seen.values()):
        raise ValueError('incomplete source repetitions')
    return {'unique_sources':len(wanted),'executions':len(rows),'replicates_per_source':3,
            'unique_sessions':len({q['trace_id'] for q in rows})}


def verify_historical(source, inherited, visited=None):
    """Historical tracked manifest binds raw evidence, code and derived artifacts."""
    visited=set() if visited is None else visited
    assert file_record(source)['sha256']==file_record(inherited)['sha256']
    def inspect(path):
        path=Path(path)
        if str(path) in visited:return
        visited.add(str(path));q=json.loads(path.read_text())
        for key in ['inputs','outputs','code','configuration','files']:
            records=q.get(key,[]); records=[records] if isinstance(records,dict) else records
            for item in records:
                if not isinstance(item,dict) or not {'path','sha256','bytes'}<=set(item):continue
                actual=file_record(item['path'])
                assert all(actual[k]==item[k] for k in actual)
                p=Path(item['path'])
                if p.name in ['manifest.json','local-evidence-manifest.json']:inspect(p)
    inspect(source)
    return file_record(source)


def audit_observation(label,r,root,directory,case):
    nodes={q['node_id']:q for q in case['nodes']}
    results=[q for q in lines(directory/'requests.jsonl') if q['phase']=='profile']
    by_id={q.get('node_id',f"baseline#{q['index']}"):q for q in results}
    assert len(results)==len(by_id)==case['requests'] and set(by_id)==set(nodes)
    edges=[{'case':label,'replicate':r,**q} for q in audit_edges(case['edges'],by_id)]
    origin=min(q['started_monotonic_ns'] for q in results);rows=[];checks=[]
    for nid,q in by_id.items():
        node=nodes[nid];assert q['status']=='completed' and q['http_status']==200
        for field in ['trace_id','source_outer_idx','source_pointer','source_request_sha256']:
            assert q[field]==node[field]
        assert q.get('source_inner_idx')==node.get('source_inner_idx')
        prefix=directory/f"{q['sequence']:03d}-profile"
        body=gzip.decompress(prefix.with_suffix('.request.json.gz').read_bytes());payload=json.loads(body)
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
        rows.append({**normalize(q,label,origin),'replicate':r,'trace_id':q['trace_id'],
            'source_outer_idx':q['source_outer_idx'],'source_inner_idx':q.get('source_inner_idx'),
            'source_request_sha256':q['source_request_sha256']})
        checks.append({'case':label,'replicate':r,'node_id':nid,'body_sha256':sha(body),
            'source_request_sha256':q['source_request_sha256'],'source_and_body_verified':True,'raw_SSE_verified':True})
    attempt=json.loads((root/'attempt.json').read_text());assert attempt['status']=='completed' and attempt['owned_process_cleanup_confirmed']
    samples=lines(root/'client_resources.jsonl')
    assert all(q['pids']==[attempt['worker_pid']] for q in samples if q['pids'])
    samples=[{**q,'relative_s':(q['monotonic_ns']-origin)/1e9,'case':label,'replicate':r} for q in samples if q['pids']]
    metric,points,selected=summarize(label,rows,samples,case['native_subagent_groups'],case['execution_chains'])
    metric['label']=LABELS[label];metric['source_output_limit_tokens']=metric.pop('source_output_tokens')
    metric['output_to_target_pct']=metric.pop('output_to_source_pct')
    assert metric['peak_inflight']<=8 and (label!='baseline' or metric['peak_inflight']==1)
    prelude='one connectivity probe'
    if r==1:
        prelude={'multiple_subagents':'connectivity probe + single_subagent in same worker',
                 'serial_intervals':'three length probes',
                 'long_context':'three length probes + serial_intervals in same worker'}.get(label,prelude)
    metric.update(replicate=r,started_at_shanghai=min(q['started_at_shanghai'] for q in results),process_prelude=prelude)
    return metric,rows,selected,edges,checks,[{'case':label,'replicate':r,**q} for q in points]


def analyze():
    plan=json.loads((ENV/'plan.json').read_text());verify_code(plan)
    for q in plan['original_plans']:assert file_record(q['path'])==q
    historical=[];visited=set()
    for owner,name in [(COVERAGE,'AGENTX-DEEPSEEK-FIVE-CASES-v1'),(PREVIOUS,'AGENTX-DEEPSEEK-REPEATS-v1')]:
        historical.append(verify_historical(owner/'reports/analysis'/name/'manifest.json',ROOT/'reports/analysis'/name/'manifest.json',visited))
    previous_plan=json.loads((PREVIOUS/'env/agentx-deepseek-repeats-01/plan.json').read_text())
    cases={q['label']:q for q in previous_plan['cases']+plan['cases']};assert set(cases)==set(LABELS)
    base_root=BASELINE/'data/raw/agentx-deepseek-pilot-01/attempts/01-remote-session'
    branch_root=BRANCHES/'data/raw/agentx-deepseek-branches-01/attempts/01-remote-branches'
    coverage_root=COVERAGE/'data/raw/agentx-deepseek-coverage-01/attempts/01-complete-cases'
    observations=[('baseline',1,base_root,base_root)]
    observations += [(label,1,branch_root,branch_root/label) for label in ['single_subagent','multiple_subagents']]
    observations += [(label,1,coverage_root,coverage_root/label) for label in ['serial_intervals','long_context']]
    new_attempts=[];new_probes=[]
    for owner,current_plan in [(PREVIOUS,previous_plan),(ROOT,plan)]:
        raw=owner/('data/raw/agentx-deepseek-repeats-01' if owner==PREVIOUS else 'data/raw/agentx-deepseek-five-repeats-01')
        current_env=owner/('env/agentx-deepseek-repeats-01' if owner==PREVIOUS else 'env/agentx-deepseek-five-repeats-01')
        for run in current_plan['runs']:
            root=raw/'attempts'/run['name'];attempt=json.loads((root/'attempt.json').read_text())
            assert attempt['status']=='completed' and attempt['exit_code']==0 and attempt['owned_process_cleanup_confirmed']
            assert attempt['plan']==file_record(current_env/'plan.json')
            observations.append((run['case'],run['replicate'],root,root/run['case']))
            if owner==ROOT:
                new_attempts.append(attempt)
                probe=lines(root/'probe/requests.jsonl');assert len(probe)==1;probe=probe[0]
                body=gzip.decompress((root/'probe/000-probe.request.json.gz').read_bytes())
                expected_probe={'model':'deepseek-flash','messages':[{'role':'user','content':'Reply only with OK.'}],
                    'max_tokens':16,'stream':True,'stream_options':{'include_usage':True},'thinking':{'type':'disabled'},'temperature':0}
                assert body==canonical(expected_probe) and sha(body)==probe['request_body_sha256']
                oracle=response_oracle(root/'probe/000-probe.response.sse')
                assert probe['status']=='completed' and probe['http_status']==200 and oracle['done'] and oracle['text'].strip()=='OK' and oracle['usage']==probe['usage']
                new_probes.append({'case':run['case'],'replicate':run['replicate'],'status':'completed','http_status':200,
                    'completion_tokens':probe['usage']['completion_tokens'],'excluded_from_profile_metrics':True})
    assert len(observations)==15 and len(new_attempts)==6 and len(new_probes)==6
    rows=[];metrics=[];resources=[];edges=[];checks=[];profiles=[]
    for label in LABELS:
        for observation in sorted([q for q in observations if q[0]==label],key=lambda q:q[1]):
            m,rs,ss,es,cs,ps=audit_observation(*observation,cases[label])
            metrics.append(m);rows+=rs;resources+=ss;edges+=es;checks+=cs;profiles+=ps
    native=lines(STEP2/'data/raw/agentx-replay-smoke-01/source_requests.jsonl')
    expected=[{'trace_id':q['trace_id'],'source_outer_idx':q['outer_idx'],'source_inner_idx':q['inner_idx'],
               'source_request_sha256':q['source_request_sha256']} for q in native]
    coverage=verify_source_repetitions(rows,expected)
    assert coverage=={'unique_sources':117,'executions':351,'replicates_per_source':3,'unique_sessions':5}
    assert len(edges)==345 and all(q['passed'] for q in edges)
    paired=paired_changes(rows);ranges=run_ranges(metrics);assert len(paired)==234
    for d in [OUT,OUT/'figures',OUT/'plot_data']:d.mkdir(parents=True,exist_ok=True)
    for name,data in [('run_metrics',metrics),('request_metrics',rows),('paired_changes',paired),('run_ranges',ranges),
        ('client_resources',resources),('dependency_audit',edges),('request_verification',checks),('probes',new_probes),('inflight_profiles',profiles)]:
        table(OUT/f'{name}.csv',data)
    offline_path=ROOT/'reports/analysis/AGENTX-DEEP-ANALYSIS-v1/summary.json';offline=json.loads(offline_path.read_text())
    summary={'schema':'agentx-five-case-three-observations-v1','new_profile_executions':134,'new_connectivity_probes':6,
        'unique_source_requests':117,'unique_source_sessions':5,'profile_executions':351,'session_execution_instances':15,
        'replicates_per_case':3,'total_probes_across_all_phases':15,'total_chat_POSTs_across_all_phases':366,
        'new_dependency_edges_verified':132,'all_dependency_edges_verified':345,'automatic_retries':0,
        'max_remote_prompt_tokens':max(q['max_remote_prompt_tokens'] for q in metrics),
        'context_truncated':False,'source_timing_reproduced':False,'model_outputs_fed_back':False,
        'server_resources_measured':False,'original_business_tools_executed':False,'original_output_load_reproduced':False,
        'significance_claimed':False,'started_at_shanghai':new_attempts[0]['started_at_shanghai'],
        'ended_at_shanghai':new_attempts[-1]['ended_at_shanghai'],'cases':metrics,'ranges':ranges,
        'offline_source':file_record(offline_path),'historical_remote_manifests':historical,
        'selection':'five fixed purposive complete source sessions from step2; no random or population sampling',
        'limits':['n=3 per case, run-level descriptive ranges only','different tasks, contexts, output lengths and concurrency',
            'cache, network and remote load uncontrolled; alias not immutable','R1 multi and long shared processes after other cases',
            'frozen synthetic inputs and native output upper limits, natural early stop allowed',
            'offline prefix potential and provider cache measurements use different scopes and definitions']}
    dump(OUT/'summary.json',summary)
    from scripts.agentx_deepseek_five_presentation import render
    render(OUT,summary,offline,rows,profiles)
    report=['# AgentX 五类会话各三次：远程实测与全量分析汇报','',
        '已补齐单子代理、原始区间串行、长上下文各 2 次：新增 6 次完整会话执行、134 条正式请求、6 次连通性探针，全部 HTTP 200，零自动重试。',
        '所选 5 个会话现在各有 3 次观察，共 15 次会话执行、351 条正式执行，仍对应 117 个唯一源请求。跨全部实验含探针共 366 次 Chat POST（351 正式 + 15 探针）；重复执行没有增加源样本数量。','',
        '| 案例 | 轮次 | 耗时 s | 首内容 P50 / P95 s | RSS MiB | 平均单核 CPU % | 实际输出 token | 原始输出覆盖 % | 缓存命中 % |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for q in metrics:report.append(f"| {LABELS[q['case']]} | R{q['replicate']} | {q['wall_s']:.2f} | {q['first_content_p50_s']:.3f} / {q['first_content_p95_s']:.3f} | {q['client_sampled_peak_rss_mib']:.2f} | {q['mean_cpu_percent_one_core_from_sample_delta']:.2f} | {q['actual_output_tokens']:,} | {q['output_to_target_pct']:.2f} | {q['input_weighted_cache_hit_pct_reported']:.2f} |")
    report+=['','每类三次观察范围（非置信区间）：','']
    for label in LABELS:
        s={q['metric']:q for q in ranges if q['case']==label};w=s['wall_s'];p=s['first_content_p50_s'];o=s['output_to_target_pct']
        report.append(f"- {LABELS[label]}：耗时 {w['min']:.2f}–{w['max']:.2f} 秒；首内容 P50 {p['min']:.3f}–{p['max']:.3f} 秒；原始输出覆盖 {o['min']:.2f}–{o['max']:.2f}%。")
    report+=['','同一固定长输出请求的变化（多子代理索引 9，上限 59,903 token）：','']
    for q in sorted([q for q in rows if q['case']=='multiple_subagents' and q['index']==9],key=lambda q:q['replicate']):
        report.append(f"- R{q['replicate']}：{q['remote_completion_tokens']:,} token，`{q['finish_reason']}`，请求耗时 {q['duration_s']:.2f} 秒。")
    report+=['','输出上限不等于实际输出量。应将会话耗时、实际输出、缓存和首内容延迟一并阅读；不能把不同任务或不同输出量的耗时直接解释成子代理加速或性能退化。自然提前结束仍使原始长输出负载未能完整复现；输出覆盖是长度指标，不是任务成功率。',
        '',
        '本轮按单子代理 R2、串行 R2、长上下文 R2、长上下文 R3、串行 R3、单子代理 R3 执行（ABCCBA），并非随机实验。每次新进程和新 HTTP session，只先做一次最多 16 token 的探针。模型 `deepseek-flash`、thinking disabled、temperature=0；正文、原始输出长度对应 max_tokens 和依赖图与首次逐字节一致，不截断输入，不补齐输出，返回文本不送入后续请求。依赖保留 serial / post-SPAWN / SPAWN_JOIN，但不复现原始时间间隔。最多 8 个在途请求，失败停止新派发、排空在途并停止后续会话；没有自动重试。',
        '',
        '资源仅采样本任务拥有的 HTTP 工作进程及子进程，排除采样父进程、其他会话和服务器。RSS 包含序列化与证据保存；CPU 均值为正式窗口中首末采样的累计 CPU 差除以实际采样窗口，按单核百分比计。每个循环工作后 sleep 0.2 秒，实际中位间隔逐轮保存；采样峰值不是连续峰值。HTTP 正文流量不含 TLS、头部和代理开销。',
        '',
        '历史 R1 前置条件不同：多子代理接续同进程内的单子代理；长上下文接续串行案例；串行先做过 3 次输出长度探针。R2/R3 都各自新进程加一次连通性探针。远程缓存、服务负载、网络、本机竞争及模型别名底层版本没有控制，因此只给出每轮数值和 min–max，不计算置信区间、显著性或因果加速比。P50/P95 均在各轮内部计算，不把 351 条请求当独立总体样本。五类是固定案例，不代表整个 AgentX。',
        '',
        '汇报 PPT 的原数据部分引用既有全量分析：Full 为 393 会话、98,827 请求；256k 为同 393 会话、68,266 请求，两者不是独立总体。Full 历史前缀潜力约 98.27% 是完整 hash 前缀与已完成历史、无淘汰假设下的结构指标，不等于当前服务缓存命中。此次未重新扫描全量原始文件，已保存引用报告的 SHA256；原始统计与新实测用独立页面和图注呈现。公开数据缺原始业务提示词、工具参数/返回与正确性，本地实验使用固定合成文本，没有执行原始业务工具。',
        '',
        '已重新核验全部 351 次正式执行的正文、源指纹和原始 SSE，核对最终 usage、结束字段及输出上限。117 个源请求分别恰有 R1/R2/R3 一次，拒绝漏样、重复和错配；345 条依赖边全部通过，本轮新增 132 条。234 条相对 R1 的配对变化保存在 CSV。新 6 个探针另行核验并排除在正式指标外。',
        '',
        '[12 页汇报 PPT](AgentX全量分析与五类重复实测_汇报版_12页.pptx) · [逐页讲解](presentation_notes.md) · [逐轮指标](run_metrics.csv) · [逐请求指标](request_metrics.csv) · [配对变化](paired_changes.csv) · [范围统计](run_ranges.csv)。图表同时保存 3840×2160 PNG、SVG 和 CSV；PPT 图表为嵌入图片，标题可编辑，改图内数据请用配套 CSV/SVG。',
        '',
        '新原始证据位于本工作树 `data/raw/agentx-deepseek-five-repeats-01/`（Git 忽略）；历史证据只读引用 pilot、branches、coverage、repeats 原工作树。清单包含路径、大小及 SHA256。Git 远程包含脚本、计划、指标、图表、PPT 与身份清单，不包含原始请求/SSE 或密钥；离线重算需保留这些原工作树。',
        '',
        '本任务使用独立分支，未修改共享 project_state.json、状态页或视频文件；任务状态和待合并节点另存 env。全局状态检查的 36 个继承证据缺失均为新工作树未复制的历史忽略文件，另行列出；没有刷新历史哈希来掩盖缺口。',
        '',
        f"新增执行时间（Asia/Shanghai）：{summary['started_at_shanghai']} 至 {summary['ended_at_shanghai']}。",
        '',
        '来源：[全量深入分析](../AGENTX-DEEP-ANALYSIS-v1/summary.md)、[首次五类实测](../AGENTX-DEEPSEEK-FIVE-CASES-v1/summary.md)、[两类重复实测](../AGENTX-DEEPSEEK-REPEATS-v1/summary.md)。CSV 中参考成本按 [官方价格页](https://api-docs.deepseek.com/quick_start/pricing/) 的既有峰时单价计算，不是实际账单；接口设置参照 [官方 thinking 文档](https://api-docs.deepseek.com/guides/thinking_mode/)。']
    (OUT/'summary.md').write_text('\n'.join(report)+'\n')
    raw_files=[file_record(p) for p in sorted(RAW.rglob('*')) if p.is_file()]
    dump(OUT/'local-evidence-manifest.json',{'files':raw_files,'historical_manifests':historical,'ignored_raw_backed_up_by_git':False})
    secret=os.environ.get('DEEPSEEK_API_KEY');assert secret,'credential needed for exact-value leak check'
    scanned=0
    for p in [Path(q['path']) for q in raw_files]+list(ENV.rglob('*'))+list(OUT.rglob('*')):
        if not p.is_file():continue
        data=p.read_bytes();data=gzip.decompress(data) if p.name.endswith('.gz') else data
        assert secret.encode() not in data,'credential leak';scanned+=1
        if p.suffix=='.pptx':
            with zipfile.ZipFile(p) as z:
                assert z.testzip() is None
                assert len([n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')])==12
                for n in z.namelist():
                    assert secret.encode() not in z.read(n),'credential leak'
                    if n.endswith(('.xml','.rels')):ET.fromstring(z.read(n))
    from PIL import Image
    for p in (OUT/'figures').glob('*.png'):
        with Image.open(p) as im:assert im.size==(3840,2160)
    from scripts.check_project_state import check
    errors=check(ROOT);assert len(errors)==36 and all(not (ROOT/e.split(': evidence mismatch')[0]).exists() for e in errors)
    dump(OUT/'verification.json',{'task_status':'PASS','new_formal_requests':134,'new_probes_verified':6,'all_source_and_SSE_verified':351,
        'unique_source_requests':117,'replicates_verified_per_source':3,'matched_changes':234,'dependency_edges_verified':345,
        'no_credentials_in_artifacts':True,'credential_scan_files':scanned,'pptx_pages':12,'all_png_dimensions':'3840x2160',
        'new_owned_processes_cleaned_up':all(q['owned_process_cleanup_confirmed'] for q in new_attempts),
        'global_project_state_check':'FAIL_INHERITED_MISSING_IGNORED_EVIDENCE','inherited_missing_count':36,'inherited_errors':errors,
        'shared_project_state_modified':False})
    dump(OUT/'manifest.json',{'schema':'agentx-five-repeats-artifacts-v1','inputs':[file_record(ENV/'plan.json'),file_record(offline_path),
        file_record(STEP2/'data/raw/agentx-replay-smoke-01/source_requests.jsonl')]+historical,
        'code':[file_record(Path(__file__)),file_record(ROOT/'scripts/agentx_deepseek_five_presentation.py'),
                file_record(ROOT/'scripts/agentx_deepseek_repeat_analysis.py'),file_record(ROOT/'scripts/agentx_deepseek_coverage_analysis.py'),
                file_record(ROOT/'scripts/agentx_deepseek_branch_analysis.py'),file_record(ROOT/'scripts/agentx_deepseek_analysis.py'),
                file_record(ROOT/'scripts/agentx_deep_presentation.py')]+plan['code'],
        'outputs':[file_record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json']})
    print(json.dumps({'status':'PASS','cases':5,'runs':15,'unique_sources':117,'formal_executions':351,'dependency_edges':345}))


if __name__=='__main__':analyze()
