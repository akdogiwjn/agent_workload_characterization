"""Independently join native AgentX records to captured loopback HTTP requests."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np

from scripts.agentx_deep_analysis import dump, table
from scripts.agentx_deep_presentation import style, figure, save, write_pptx, BLUE, ORANGE, TEAL
from scripts.agentx_replay_smoke_prepare import record

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw/agentx-replay-smoke-01'
OUT=ROOT/'reports/analysis/AGENTX-REPLAY-SMOKE-v1'


def read_lines(path):return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def source_key(q, exported=False):
    if exported:return q['source_trace_id'],q['source_outer_idx'],q.get('source_inner_idx')
    return q['trace_id'],q['outer_idx'],q['inner_idx']


def longest_prefix(a,b):
    n=min(len(a),len(b))
    unequal=np.flatnonzero(a[:n]!=b[:n])
    return int(unequal[0]) if len(unequal) else n


def validate_joins(source, exported, wire):
    """Reject duplicates/missing records; counts alone cannot establish identity."""
    s={source_key(q):q for q in source}
    e={source_key(q['metadata'],True):q for q in exported}
    w={q['request_id']:q for q in wire}
    if len(s)!=len(source) or len(e)!=len(exported) or len(w)!=len(wire):
        raise ValueError('duplicate source or request identity')
    if set(s)!=set(e):raise ValueError('source/export coverage mismatch')
    ids=[q['metadata']['x_request_id'] for q in exported]
    if len(set(ids))!=len(ids) or set(ids)!=set(w):raise ValueError('export/wire coverage mismatch')
    return s,e,w


def audit(name):
    attempt=RAW/'attempts'/name
    source=read_lines(RAW/'source_requests.jsonl')
    exported=read_lines(attempt/'harness/profile_export.jsonl')
    wire=read_lines(attempt/'mock/server_requests.jsonl')
    s,e,w=validate_joins(source,exported,wire)
    rows=[];vectors={};errors=[]
    first=min(q['received_monotonic_ns'] for q in wire)
    for key,q in s.items():
        exp=e[key];m=exp['metadata'];http=w[m['x_request_id']]
        npz=attempt/'mock/requests'/f"{http['file_id']}.npz"
        with np.load(npz,allow_pickle=False) as f:
            vectors[key]={'prompt':f['prompt_ids'],'content':f['content_ids']}
        metrics=exp['metrics']
        checks={
            'http_completed':http['status']=='completed',
            'not_cancelled':not m.get('was_cancelled',False),
            'not_overflow_skipped':not m.get('context_overflow_skip',False),
            'model_rewritten':http['model']=='agentx-mock',
            'output_target_matches':http['max_tokens']==max(1,q['output_tokens']),
            'output_response_matches':http['response_tokens']==http['max_tokens'],
            'export_input_matches_observed':metrics['input_sequence_length']['value']==http['rendered_input_tokens'],
            'export_output_matches_observed':metrics['output_sequence_length']['value']==http['response_tokens'],
            'correlation_matches':m['x_correlation_id']==http['correlation_id']==http['dynamo_session_id'],
            'parent_header_matches':m.get('parent_correlation_id')==http.get('dynamo_parent_id'),
            'no_authorization_header':http['authorization_header_present'] is False,
        }
        errors.extend({'key':key,'check':label} for label,ok in checks.items() if not ok)
        rows.append({'trace_id':q['trace_id'],'pointer':q['pointer'],'source_outer_idx':q['outer_idx'],
            'source_inner_idx':q['inner_idx'],'scope':'/'.join(q['scope']) or 'main',
            'source_request_sha256':q['source_request_sha256'],'source_t':q['source_t'],
            'source_input':q['input_tokens'],'source_output':q['output_tokens'],
            'observed_input':http['rendered_input_tokens'],'observed_content_input':http['content_input_tokens'],
            'input_delta':http['rendered_input_tokens']-q['input_tokens'],
            'input_delta_pct':100*(http['rendered_input_tokens']-q['input_tokens'])/q['input_tokens'],
            'observed_output':http['response_tokens'],'request_id':http['request_id'],
            'conversation_id':m['conversation_id'],'correlation_id':m['x_correlation_id'],
            'parent_correlation_id':m.get('parent_correlation_id'),'turn_index':m['turn_index'],
            'source_kind':m['source_kind'],'agent_depth':m.get('agent_depth',0),
            'start_s':(http['received_monotonic_ns']-first)/1e9,
            'end_s':(http['completed_monotonic_ns']-first)/1e9,
            'body_sha256':http['body_sha256'],'checks_passed':all(checks.values())})
    # Conversation order is a measured property. No cross-branch source-time claim.
    by_conversation=defaultdict(list)
    for row in rows:by_conversation[row['conversation_id']].append(row)
    order_checks=0
    for conversation,turns in by_conversation.items():
        turns.sort(key=lambda q:q['turn_index'])
        if [q['turn_index'] for q in turns]!=list(range(len(turns))):
            errors.append({'check':'non_contiguous_turns','conversation':conversation})
        for a,b in zip(turns,turns[1:]):
            order_checks+=1
            if b['start_s']<a['end_s']:errors.append({'check':'serial_order_violation','conversation':conversation})
    correlations={q['correlation_id'] for q in rows}
    child_conversations={q['conversation_id'] for q in rows if q['parent_correlation_id']}
    for q in rows:
        if q['parent_correlation_id'] and q['parent_correlation_id'] not in correlations:
            errors.append({'check':'unresolved_parent','request_id':q['request_id']})
    # All within-session/model unordered pairs, rather than arrival-conditioned
    # cache hits. This detects both missing reuse and unintended extra sharing.
    pairs=[]
    keys=list(s)
    for i,key_a in enumerate(keys):
        a=s[key_a]
        for key_b in keys[i+1:]:
            b=s[key_b]
            if a['trace_id']!=b['trace_id'] or a['model']!=b['model']:continue
            expected=64*longest_prefix(np.asarray(a['hash_ids']),np.asarray(b['hash_ids']))
            prompt=longest_prefix(vectors[key_a]['prompt'],vectors[key_b]['prompt'])
            content=longest_prefix(vectors[key_a]['content'],vectors[key_b]['content'])
            pairs.append({'trace_id':a['trace_id'],'pointer_a':a['pointer'],'pointer_b':b['pointer'],
                'cross_scope':a['scope']!=b['scope'],'source_hash_lcp_tokens':expected,
                'observed_prompt_lcp_tokens':prompt,'observed_content_lcp_tokens':content,
                'prompt_delta':prompt-expected,'content_delta':content-expected})
    groups=defaultdict(list)
    for q in rows:groups[q['trace_id']].append(q)
    manifest=json.loads((ROOT/'data/catalog/agentx-replay-smoke-01/sample-manifest.json').read_text())
    sessions=[]
    for chosen in manifest['complete_selected_sessions']:
        rs=groups[chosen['trace_id']]
        sessions.append({'stratum':chosen['stratum'],'trace_id':chosen['trace_id'],'requests':len(rs),
            'native_groups':chosen['groups'],'replay_conversations':len({r['conversation_id'] for r in rs}),
            'max_source_input':max(r['source_input'] for r in rs),
            'max_abs_input_delta':max(abs(r['input_delta']) for r in rs),
            'max_abs_input_delta_pct':max(abs(r['input_delta_pct']) for r in rs),
            'first_start_s':min(r['start_s'] for r in rs),'last_end_s':max(r['end_s'] for r in rs)})
    shared=[p for p in pairs if p['source_hash_lcp_tokens']>0]
    lost=[p for p in shared if p['observed_prompt_lcp_tokens']<p['source_hash_lcp_tokens']]
    exported_summary=json.loads((attempt/'harness/profile_export_aiperf.json').read_text())
    summary={'schema':'agentx-replay-smoke-audit-v1','date_shanghai':'2026-10-23',
        'successful_attempt':name,'mapping_passed':not errors,'errors':errors,
        'sessions':len(sessions),'requests':len(rows),'native_groups':sum(x['native_groups'] for x in sessions),
        'replay_conversations':len(by_conversation),'child_conversations':len(child_conversations),
        'source_subagent_requests':sum(q['source_inner_idx'] is not None for q in rows),
        'replay_child_requests':sum(bool(q['parent_correlation_id']) for q in rows),
        'serial_order_pairs_checked':order_checks,'source_to_export_to_http_one_to_one':True,
        'wire_auth_headers':sum(wi['authorization_header_present'] for wi in wire),
        'source_zero_output_clamped':sum(q['source_output']==0 for q in rows),
        'exact_input_matches':sum(q['input_delta']==0 for q in rows),
        'input_delta_min':min(q['input_delta'] for q in rows),'input_delta_max':max(q['input_delta'] for q in rows),
        'max_abs_input_delta_pct':max(abs(q['input_delta_pct']) for q in rows),
        'input_abs_delta_p50':float(np.median([abs(q['input_delta']) for q in rows])),
        'input_abs_delta_p95':float(np.percentile([abs(q['input_delta']) for q in rows],95)),
        'input_weighted_abs_delta_pct':100*sum(abs(q['input_delta']) for q in rows)/sum(q['source_input'] for q in rows),
        'within_session_model_pairs':len(pairs),'source_shared_prefix_pairs':len(shared),
        'shared_pairs_with_shorter_prompt_prefix':len(lost),
        'shared_pairs_exact_prompt_prefix':sum(p['prompt_delta']==0 for p in shared),
        'shared_pairs_with_zero_content_prefix':sum(p['observed_content_lcp_tokens']==0 for p in shared),
        'max_shared_prefix_loss':max((-p['prompt_delta'] for p in lost),default=0),
        'min_shared_prefix_retention_ratio':min((p['observed_prompt_lcp_tokens']/p['source_hash_lcp_tokens'] for p in shared),default=None),
        'real_model_calls':0,'model_weights_loaded':False,'cache_hits_measured':False,
        'source_timing_reproduced':False,'business_tools_reproduced':False,
        'branch_statistics':exported_summary.get('branch_stats',exported_summary.get('branch_statistics')),
        'attempt':json.loads((attempt/'attempt.json').read_text()),'sample_sessions':sessions}
    OUT.mkdir(parents=True,exist_ok=True)
    for directory in ['figures','plot_data']:(OUT/directory).mkdir(exist_ok=True)
    dump(OUT/'summary.json',summary)
    table(OUT/'request_mapping.csv',rows)
    table(OUT/'prefix_pairs.csv',pairs)
    table(OUT/'sessions.csv',sessions)
    dump(OUT/'attempts.json',[json.loads(p.read_text()) for p in sorted((RAW/'attempts').glob('*/attempt.json'))])
    render(summary,rows,pairs)
    inputs=[record(RAW/'source_requests.jsonl'),record(attempt/'harness/profile_export.jsonl'),record(attempt/'mock/server_requests.jsonl')]
    outputs=[record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ['manifest.json','final-verification.json']]
    dump(OUT/'manifest.json',{'schema':'agentx-replay-artifacts-v1','inputs':inputs,'outputs':outputs,
        'raw_attempt_root':str(attempt),'raw_capture_policy':'gzip HTTP bodies and npz token vectors kept locally, excluded from Git'})
    print(json.dumps({k:v for k,v in summary.items() if k not in ['attempt','sample_sessions']},ensure_ascii=False,indent=2))
    return summary


def render(summary,rows,pairs):
    style();slides=[]
    labels={'serial':'串行区间','root_overlap':'主流重叠','explicit_subagent':'显式子代理','multiple_subagents':'多子代理','long_context':'长上下文'}
    footer='AgentX Full固定5会话，官方agentx-harness 1.0.7 + 本地模拟服务；没有真实模型。\n移除原始等待，仅验证请求映射与结构；图中耗时不能用于模型性能比较。'
    def finish(fig,name,heading):
        save(fig,OUT,name)
        svg=OUT/'figures'/f'{name}.svg'
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
        slides.append({'heading':heading,'image':OUT/'figures'/f'{name}.png'})
    fig,ax=figure('117条原始请求均已完成一对一核对','原始来源 → 官方回放器导出 → 实际HTTP请求；以来源索引与X-Request-ID连接',footer)
    ss=summary['sample_sessions'];x=np.arange(len(ss));counts=[q['requests'] for q in ss]
    ax.bar(x,counts,color=BLUE,width=.6)
    for i,q in enumerate(ss):ax.text(i,q['requests']+.4,str(q['requests']),ha='center')
    ax.set(xticks=x,xticklabels=[labels[q['stratum']] for q in ss],ylabel='完整会话内的请求数',ylim=(0,36))
    table(OUT/'plot_data/01_sample.csv',ss);finish(fig,'01_sample','样本覆盖：5会话、117请求、7个原生子代理组')
    fig,ax=figure('实际输入长度接近原值，但并非逐token精确复刻',f"精确相等 {summary['exact_input_matches']}/117；输入长度偏差 {summary['input_delta_min']:+d}～{summary['input_delta_max']:+d} token",footer)
    colors=[BLUE,ORANGE,TEAL,'#7C3AED','#DB2777']
    plot=[]
    for sample,color in zip(ss,colors):
        rs=sorted((q for q in rows if q['trace_id']==sample['trace_id']),key=lambda q:(q['source_t'],q['pointer']))
        for i,q in enumerate(rs):plot.append({'stratum':sample['stratum'],'request_order':i+1,'source_input':q['source_input'],'observed_input':q['observed_input'],'delta':q['input_delta']})
        ax.plot(range(1,len(rs)+1),[q['input_delta'] for q in rs],marker='o',markersize=4,color=color,label=labels[sample['stratum']])
    ax.axhline(0,color='#64748B',lw=1);ax.set(xlabel='各会话内按来源时间排序的请求序号',ylabel='实际输入 − 原始输入（token）');ax.legend(fontsize=12,ncol=2)
    table(OUT/'plot_data/02_input_delta.csv',plot);finish(fig,'02_input_delta','输入校验：必须保留并报告分词和模板偏差')
    fig,ax=figure('共享前缀需按实际token序列检查',f"同会话、同模型共{len(pairs):,}对；其中{summary['source_shared_prefix_pairs']:,}对原始hash前缀大于0",footer+'\n最长公共前缀是静态共享潜力，不是实际KV缓存命中；不同会话不比较hash ID。')
    shared=[p for p in pairs if p['source_hash_lcp_tokens']>0]
    ax.scatter([p['source_hash_lcp_tokens']/1000 for p in shared],[p['observed_prompt_lcp_tokens']/1000 for p in shared],s=22,alpha=.5,color=BLUE)
    largest=max(p['source_hash_lcp_tokens'] for p in shared)/1000
    ax.plot([0,largest],[0,largest],ls='--',color=ORANGE,label='逐token完全保留的参考线')
    ax.set(xlabel='来源hash前缀长度（千 token）',ylabel='实际HTTP模板前缀长度（千 token）');ax.legend()
    table(OUT/'plot_data/03_prefix.csv',pairs);finish(fig,'03_prefix','前缀校验：原始hash关系与实际请求token关系分开报告')
    chosen=next(q for q in ss if q['stratum']=='multiple_subagents')
    rs=sorted((q for q in rows if q['trace_id']==chosen['trace_id']),key=lambda q:(q['agent_depth'],q['conversation_id'],q['turn_index']))
    conv=list(dict.fromkeys(q['conversation_id'] for q in rs));offset=min(q['start_s'] for q in rs)
    fig,ax=figure('子代理执行时间线：显示实际收到请求的区间',f"多子代理样本：{chosen['native_groups']}个原生组 → {chosen['replay_conversations']}条执行链；父子关系已逐条校验",footer)
    for q in rs:ax.barh(conv.index(q['conversation_id']),q['end_s']-q['start_s'],left=q['start_s']-offset,color=TEAL if q['parent_correlation_id'] else BLUE,height=.65)
    ax.set(yticks=range(len(conv)),yticklabels=['root' if i==0 else f'child {i}' for i in range(len(conv))],xlabel='相对该样本首个HTTP请求的时间（秒）',ylabel='官方回放执行链');ax.invert_yaxis()
    table(OUT/'plot_data/04_timeline.csv',rs);finish(fig,'04_timeline','执行时间线：压缩等待的本地工程验证')
    write_pptx(OUT/'AgentX本地回放验证_汇报版_4页.pptx',slides)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--attempt',default='03-full-sample')
    audit(p.parse_args().attempt)
