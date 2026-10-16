from __future__ import annotations
import argparse, hashlib, json, math, statistics
from collections import Counter, defaultdict
from pathlib import Path

AGENTX_REV='8fecd2fc56694469f758f0afbbb6335ad3043740'
APPLIED_REV='6918da7915e3ae57ce3750a375ef50e41cad2b36'
SCHEMA='agentx-applied-macro-v1'


def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def finite_number(x):
    return type(x) in (int,float) and not isinstance(x,bool) and math.isfinite(float(x))


def nonnegative(x):
    return finite_number(x) and float(x) >= 0


def percentile(values,q):
    a=sorted(float(x) for x in values if finite_number(x))
    if not a:return None
    if len(a)==1:return a[0]
    z=(len(a)-1)*q; lo=int(math.floor(z)); hi=int(math.ceil(z))
    return a[lo] if lo==hi else a[lo]+(a[hi]-a[lo])*(z-lo)


def stats(values):
    a=[float(x) if isinstance(x,float) else x for x in values if finite_number(x)]
    return {'n':len(a),'missing':len(values)-len(a),'min':percentile(a,0) if a else None,'q1':percentile(a,.25),'median':percentile(a,.5),'q3':percentile(a,.75),'iqr':None if not a else percentile(a,.75)-percentile(a,.25),'max':percentile(a,1) if a else None}


def interval_stats(requests):
    intervals=[]
    for r in requests:
        if nonnegative(r.get('t')) and nonnegative(r.get('api_time')):
            intervals.append((float(r['t']),float(r['t'])+float(r['api_time'])))
    if not intervals:return {'valid_intervals':0,'union_s':None,'overlap_s':None,'observed_span_s':None}
    intervals.sort(); union=0.0; covered_end=None; covered_start=intervals[0][0]; overlap=0.0
    for start,end in intervals:
        if covered_end is None: covered_end=end; continue
        if start>covered_end:
            union += covered_end-covered_start; covered_start=start; covered_end=end
        else:
            overlap += max(0.0,min(covered_end,end)-start); covered_end=max(covered_end,end)
    union += covered_end-covered_start
    return {'valid_intervals':len(intervals),'union_s':union,'overlap_s':overlap,'observed_span_s':max(e for _,e in intervals)-min(s for s,_ in intervals)}


def prefix_stats(requests):
    vals=[r.get('hash_ids') for r in requests if isinstance(r.get('hash_ids'),list)]
    shared=0; comparisons=0
    for a,b in zip(vals,vals[1:]):
        comparisons+=1; n=0
        for x,y in zip(a,b):
            if x!=y:break
            n+=1
        shared+=n
    return {'requests_with_hash_ids':len(vals),'adjacent_same_scope_comparisons':comparisons,'adjacent_shared_prefix_block_count':shared}


def agentx_scope(requests):
    token_in=[r.get('in') for r in requests]; token_out=[r.get('out') for r in requests]
    seq=[r for r in requests if isinstance(r,dict)]
    context_delta=[]
    for a,b in zip(seq,seq[1:]):
        if nonnegative(a.get('in')) and nonnegative(b.get('in')): context_delta.append(b['in']-a['in'])
    times=[r.get('api_time') for r in seq]
    return {'request_count':len(seq),'input_tokens':stats(token_in),'output_tokens':stats(token_out),'api_time_s':stats(times),'context_adjacent_delta_tokens':stats(context_delta),'first_input_tokens':seq[0].get('in') if seq else None,'last_input_tokens':seq[-1].get('in') if seq else None,'intervals':interval_stats(seq),'prefix':prefix_stats(seq)}


def flatten_agentx(raw, line):
    if not isinstance(raw,dict) or not isinstance(raw.get('id'),str) or not isinstance(raw.get('requests'),list):
        raise ValueError('invalid AgentX trace shape')
    main=[]; scopes=[]; groups=[]; errors=[]; seen_agents=set()
    def walk(items, owner, depth):
        if not isinstance(items,list): raise ValueError('request array missing')
        out=[]
        for i,item in enumerate(items):
            if not isinstance(item,dict): errors.append({'line':line,'kind':'request_not_object','path':owner+'/'+str(i)}); continue
            kind=item.get('type')
            if kind=='subagent':
                aid=item.get('agent_id')
                if not isinstance(aid,str) or not aid or aid in seen_agents:
                    errors.append({'line':line,'kind':'subagent_identity_invalid_or_duplicate','path':owner+'/'+str(i)})
                else: seen_agents.add(aid)
                groups.append({'agent_id':aid,'depth':depth+1,'t':item.get('t'),'duration_ms':item.get('duration_ms'),'status':item.get('status'),'inner_request_count':len(item.get('requests',[])) if isinstance(item.get('requests'),list) else None})
                inner=walk(item.get('requests'),aid,depth+1)
                scopes.append({'scope':'subagent','agent_id':aid,'depth':depth+1,'requests':inner})
            elif kind in ('s','n'):
                out.append(item)
            else: errors.append({'line':line,'kind':'unknown_request_type','type':kind})
        return out
    top=raw['requests']
    for i,item in enumerate(top):
        if isinstance(item,dict) and item.get('type')=='subagent':
            aid=item.get('agent_id')
            if not isinstance(aid,str) or not aid or aid in seen_agents: errors.append({'line':line,'kind':'subagent_identity_invalid_or_duplicate','path':f'requests/{i}'})
            else: seen_agents.add(aid)
            groups.append({'agent_id':aid,'depth':1,'t':item.get('t'),'duration_ms':item.get('duration_ms'),'status':item.get('status'),'inner_request_count':len(item.get('requests',[])) if isinstance(item.get('requests'),list) else None})
            inner=walk(item.get('requests'),aid,1)
            scopes.append({'scope':'subagent','agent_id':aid,'depth':1,'requests':inner})
        elif isinstance(item,dict) and item.get('type') in ('s','n'): main.append(item)
        else: errors.append({'line':line,'kind':'unknown_request_type','path':f'requests/{i}'})
    return main,scopes,groups,errors


def analyze_agentx(path):
    rows=[]; errors=[]; seen=set(); models=Counter(); total_groups=0; total_inner=0; total_main=0; all_requests=[]; main_requests=[]
    with path.open() as f:
        for line_no,line in enumerate(f,1):
            try: raw=json.loads(line)
            except Exception: errors.append({'line':line_no,'kind':'invalid_json'}); continue
            try: main,scopes,groups,e=flatten_agentx(raw,line_no)
            except Exception as exc: errors.append({'line':line_no,'kind':'invalid_trace','error':type(exc).__name__}); continue
            errors.extend(e); tid=raw['id']
            if tid in seen: errors.append({'line':line_no,'kind':'duplicate_trace_id','id':tid})
            seen.add(tid); total_main+=len(main); total_groups+=len(groups); total_inner+=sum(len(s['requests']) for s in scopes); all_requests.extend(main+[r for s in scopes for r in s['requests']]); main_requests.extend(main)
            for r in main+[r for s in scopes for r in s['requests']]:
                if isinstance(r.get('model'),str): models[r['model']]+=1
            rows.append({'trace_id':tid,'line':line_no,'models':raw.get('models'),'block_size':raw.get('block_size'),'hash_id_scope':raw.get('hash_id_scope'),'main':agentx_scope(main),'subagent_scopes':[{'agent_id':s['agent_id'],'depth':s['depth'],'metrics':agentx_scope(s['requests'])} for s in scopes],'subagent_group_count':len(groups),'subagent_fanout':len(groups),'model_request_count':len(main)+sum(len(s['requests']) for s in scopes),'model_requests_main':len(main),'model_requests_subagents':sum(len(s['requests']) for s in scopes),'tokens':{'input':sum(r.get('in') for r in main+[r for s in scopes for r in s['requests']] if nonnegative(r.get('in'))),'output':sum(r.get('out') for r in main+[r for s in scopes for r in s['requests']] if nonnegative(r.get('out')))},'errors':e,'source':{'path':str(path),'line':line_no}})
    return rows,errors,{'trace_count':len(rows),'main_request_count':total_main,'subagent_group_count':total_groups,'subagent_inner_request_count':total_inner,'total_model_request_count':total_main+total_inner,'models':dict(models),'request_input_tokens':stats([r.get('in') for r in all_requests]),'request_output_tokens':stats([r.get('out') for r in all_requests]),'trace_total_input_tokens':stats([r['tokens']['input'] for r in rows]),'trace_total_output_tokens':stats([r['tokens']['output'] for r in rows]),'scope_time':interval_stats(main_requests),'errors':errors}


def applied_row(raw, source, line):
    fields=('num_turns','input_prompt_length','assistant_response_length','tool_call_output_length','tool_call_latency','final_assistant_response_length')
    missing=[k for k in fields if k not in raw]; errors=[]
    n=raw.get('num_turns')
    if isinstance(n,bool) or not isinstance(n,int) or n<0: errors.append('invalid_num_turns'); n=None
    arrays={k:raw.get(k) for k in ('assistant_response_length','tool_call_output_length','tool_call_latency')}
    for k,v in arrays.items():
        if not isinstance(v,list): errors.append(k+'_not_list')
        elif n is not None and len(v)!=n: errors.append(k+'_length_mismatch')
    def seq_values(k):
        v=arrays[k]; return [x for x in v if nonnegative(x)] if isinstance(v,list) else []
    valid=not missing and not errors and nonnegative(raw.get('input_prompt_length')) and nonnegative(raw.get('final_assistant_response_length')) and all(nonnegative(x) for k in arrays for x in arrays[k])
    if not valid and not errors: errors.append('invalid_scalar_or_array_value')
    derived={'completion_request_count':n+1 if n is not None else None,'total_output_tokens':None,'max_context_tokens':None,'total_input_tokens':None,'total_simulated_delay_s':None}
    if valid:
        a=arrays['assistant_response_length']; t=arrays['tool_call_output_length']; l=arrays['tool_call_latency']; initial=raw['input_prompt_length']; contexts=[initial]
        for aa,tt in zip(a,t): contexts.append(contexts[-1]+aa+tt)
        derived.update(total_output_tokens=sum(a)+raw['final_assistant_response_length'],max_context_tokens=max(contexts),total_input_tokens=sum(contexts),total_simulated_delay_s=sum(l))
    return {'source':{'path':str(source),'line':line},'valid':valid,'errors':errors,'num_turns':n,'input_prompt_length':raw.get('input_prompt_length'),'assistant_response_lengths':seq_values('assistant_response_length'),'tool_output_lengths':seq_values('tool_call_output_length'),'latency_s':seq_values('tool_call_latency'),'final_assistant_response_length':raw.get('final_assistant_response_length'),'derived':derived}


def analyze_applied(root):
    rows=[]; groups={}; errors=[]
    for path in sorted(root.glob('workloads/*.jsonl')):
        name=path.stem; group=[]
        with path.open() as f:
            for line_no,line in enumerate(f,1):
                try: raw=json.loads(line); row=applied_row(raw,path,line_no)
                except Exception as exc: errors.append({'path':str(path),'line':line_no,'kind':'invalid_json','error':type(exc).__name__}); continue
                group.append(row); rows.append({'workload':name,**row})
        groups[name]=group
    return rows,groups,errors


def summarize_applied(groups):
    out={}
    for name,rows in groups.items():
        good=[r for r in rows if r['valid']]
        def flat(field): return [r[field] for r in good]
        out[name]={'template_count':len(rows),'valid_template_count':len(good),'invalid_template_count':len(rows)-len(good),'errors':dict(Counter(e for r in rows for e in r['errors'])),'num_turns':stats(flat('num_turns')),'initial_prompt_tokens':stats(flat('input_prompt_length')),'assistant_output_per_turn_tokens':stats([x for r in good for x in r['assistant_response_lengths']]),'tool_output_per_turn_tokens':stats([x for r in good for x in r['tool_output_lengths']]),'final_response_tokens':stats(flat('final_assistant_response_length')),'latency_s':stats([x for r in good for x in r['latency_s']]),'derived_completion_requests':stats([r['derived']['completion_request_count'] for r in good]),'derived_total_input_tokens':stats([r['derived']['total_input_tokens'] for r in good]),'derived_max_context_tokens':stats([r['derived']['max_context_tokens'] for r in good]),'derived_total_output_tokens':stats([r['derived']['total_output_tokens'] for r in good]),'derived_total_simulated_delay_s':stats([r['derived']['total_simulated_delay_s'] for r in good])}
    return out


def verify_inputs(agentx,applied,acquisition):
    am=json.loads(acquisition.read_text()); entries={x['path']:x for x in am.get('inputs',[])}; files=[agentx/'README.md',agentx/'stats.txt',agentx/'traces.jsonl',applied/'README.md',applied/'LICENSE']+sorted((applied/'workloads').glob('*.jsonl'))
    problems=[]; manifest=[]
    for p in files:
        try: rel=str(p.relative_to(Path.cwd()))
        except ValueError: rel=str(p)
        e=entries.get(rel)
        item={'path':rel,'bytes':p.stat().st_size if p.is_file() else None,'sha256':sha256(p) if p.is_file() else None,'role':'input'}
        if not e: problems.append({'path':rel,'kind':'not_in_acquisition_manifest'})
        elif (e.get('bytes'),e.get('sha256'))!=(item['bytes'],item['sha256']): problems.append({'path':rel,'kind':'hash_mismatch'})
        manifest.append(item)
    return manifest,problems


def write_report(agentx,applied,acquisition,out,analyzer):
    if out.exists(): raise FileExistsError(str(out))
    files,problems=verify_inputs(agentx,applied,acquisition)
    if problems: raise ValueError('input verification failed')
    ax_rows,ax_errors,ax_summary=analyze_agentx(agentx/'traces.jsonl'); ac_rows,ac_groups,ac_errors=analyze_applied(applied); ac_summary=summarize_applied(ac_groups)
    out.mkdir(parents=True)
    (out/'per_trace.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in ax_rows))
    (out/'per_template.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in ac_rows))
    summary={'schema':SCHEMA,'sources':{'AgentX':{'nature':'published filtered proxy/request-flow corpus; not complete tool execution logs','revision':AGENTX_REV,'summary':ax_summary,'errors':ax_errors},'Applied Compute':{'nature':'production-derived synthetic workload templates; not original Agent messages or Office execution logs','revision':APPLIED_REV,'summary':ac_summary,'errors':ac_errors}},'semantics':{'AgentX':{'t':'source-relative seconds per existing adapter and README retention rule; not host monotonic','api_time':'recorded request interval duration in seconds per adapter; not CPU time','tokens':'in/out request token fields; pooled and trace totals are separate','subagents':'explicit subagent records with nested requests; parent marker not counted as model request','hash':'hash_ids retained with block_size and local scope; only same trace/scope adjacency inspected','limits':['No cross-clock parent/child recombination beyond source-relative scope','No cache hit, memory, CPU, or performance inference']},'Applied Compute':{'num_turns':'tool-use turns','completion_requests':'N+1 derived from README','latency':'simulated tool delay in seconds','lengths':'template token parameters, not observed usage','limits':['No tool names, parallelism, real timestamps, CPU or memory']}} ,'input_verification':{'files':files,'problems':problems},'analysis_rules':{'quantile':'linear interpolation on sorted values; IQR=Q3-Q1','AgentX':'top-level main requests and nested subagent requests counted once; subagent marker excluded','Applied':'valid row requires all six fields and vectors length N; missing/invalid rows excluded from valid denominators but retained','time':'intervals only within each recorded scope; no parent/subagent clock merge'},'cross_source_comparison':'method/evidence comparison only; sources are not pooled'}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    md=['# AgentX + Applied Compute macro analysis v1','','仅使用本地固定版本输入；未联网、未执行轨迹或 workload。两类来源不合并统计。','', '## 输入与性质',f"- AgentX revision `{AGENTX_REV}`：{ax_summary['trace_count']} traces、{ax_summary['total_model_request_count']:,} model requests（主 `{ax_summary['main_request_count']:,}`，subagent 内部 `{ax_summary['subagent_inner_request_count']:,}`），显式 subagent groups `{ax_summary['subagent_group_count']:,}`。这是过滤后的 request-flow/proxy corpus，不是完整工具执行日志。",f"- Applied Compute revision `{APPLIED_REV}`："+', '.join(f"{k}={v['template_count']:,} templates（有效 {v['valid_template_count']:,}）" for k,v in ac_summary.items())+'；是 production-derived template，不是原始 Agent/Office execution trace。','', '## AgentX 主要观察',f"- 请求级 pooled input tokens median `{ax_summary['request_input_tokens']['median']}`、output median `{ax_summary['request_output_tokens']['median']}`；trace 总 token 另按 trace 汇总，不能与 pooled 请求分布混用。",f"- 每 trace 请求数由实际记录决定；subagent fan-out 只依据显式 marker，未从名称或时间恢复父子关系。",'- `t`/`api_time` 只在各自 source-relative scope 内形成记录区间；重叠是记录区间重叠，不是 CPU/GPU 并发。','- hash_ids 只在同一 trace 的相邻记录中检查前缀共享，不推导 cache 命中率或性能收益。','', '## Applied Compute 主要观察']
    for name,v in ac_summary.items(): md.append(f"- `{name}`：turn median {v['num_turns']['median']}；初始 prompt median {v['initial_prompt_tokens']['median']} token；assistant/tool/final median 分别为 {v['assistant_output_per_turn_tokens']['median']}/{v['tool_output_per_turn_tokens']['median']}/{v['final_response_tokens']['median']} token；simulated latency median {v['latency_s']['median']} s（per-turn pooled）。")
    md += ['', '## 可支持与缺口','- 可支持：请求/trace 规模、显式 subagent 结构、token 字段、有限 source-relative 区间、模板轮次/长度/模拟 delay。','- 不可支持：CPU、内存、I/O、热点、真实工具耗时、思考时间、真实 API 账单、模型排名或类别代表性。','- AgentX 与 Applied Compute 不形成共同总体；Applied 的派生 token 不能当真实 API 累计输入。','', '[summary.json](summary.json) · [per_trace.jsonl](per_trace.jsonl) · [per_template.jsonl](per_template.jsonl) · [manifest.json](manifest.json)']
    (out/'summary.md').write_text('\n'.join(md)+'\n')
    project=Path.cwd()
    def disp(p):
        try:return str(p.relative_to(project))
        except ValueError:return str(p)
    outputs=[]
    for name in ('summary.json','summary.md','per_trace.jsonl','per_template.jsonl'):
        q=out/name; outputs.append({'path':disp(q),'bytes':q.stat().st_size,'sha256':sha256(q)})
    man={'schema':SCHEMA+'-manifest','inputs':files+[{'path':disp(acquisition),'bytes':acquisition.stat().st_size,'sha256':sha256(acquisition),'role':'acquisition_manifest'}],'analyzer':{'path':disp(analyzer),'sha256':sha256(analyzer)},'outputs':outputs,'manifest_self_hash':'excluded'}
    (out/'manifest.json').write_text(json.dumps(man,ensure_ascii=False,indent=2)+'\n')
    return summary


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--agentx',type=Path,required=True); ap.add_argument('--applied',type=Path,required=True); ap.add_argument('--acquisition-manifest',type=Path,required=True); ap.add_argument('--output-dir',type=Path,required=True); a=ap.parse_args()
    try: write_report(a.agentx,a.applied,a.acquisition_manifest,a.output_dir,Path(__file__))
    except FileExistsError as e: print('output_exists',e); return 2
    except Exception as e: print('analysis_failed',type(e).__name__,e); return 1
    return 0
if __name__=='__main__': raise SystemExit(main())
