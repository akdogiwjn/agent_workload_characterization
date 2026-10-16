from __future__ import annotations
import argparse, collections, gzip, hashlib, json, math, shlex, sys
from pathlib import Path

SCHEMA='1.1.0'
CATEGORIES=('Read/Search','Edit/Write','Test','Interpreter/Execute','Other','Unknown')
PREFIX='data/raw/public/swe_rebench_nonofficial/cdae27cdd16673f0c682871ad55d325f24cc7020/'

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def number(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def percentile(values,q):
    a=sorted(x for x in values if number(x))
    if not a:return None
    if len(a)==1:return a[0]
    z=(len(a)-1)*q; lo,hi=math.floor(z),math.ceil(z)
    return a[lo] if lo==hi else a[lo]+(a[hi]-a[lo])*(z-lo)
def iqr(values):
    a,b=percentile(values,.25),percentile(values,.75); return None if a is None or b is None else b-a
def stats(values):
    a=[x for x in values if number(x)]
    return {'raw':values,'n':len(a),'median':percentile(a,.5),'iqr':iqr(a)}

def command_form(value):
    if isinstance(value,str): return ('string',value)
    if isinstance(value,list) and all(isinstance(x,str) for x in value): return ('argv',value)
    if isinstance(value,dict):
        c=value.get('command')
        if isinstance(c,str): return ('structured_string',c)
        if isinstance(c,list) and all(isinstance(x,str) for x in c): return ('structured_argv',c)
        return ('unsupported_structured',None)
    return ('unsupported',None)

def shell_argv(inp):
    form, value=command_form(inp)
    if value is None:return form,None,'unsupported_command_shape'
    if form.endswith('argv'): return form,value,None
    try: argv=shlex.split(value,posix=True)
    except ValueError:return form,None,'shell_parse_error'
    if not argv:return form,[], 'empty_command'
    if any(tok in {'|','||','&&',';','&','>','>>','<','2>','2>>'} or any(ch in tok for ch in '|;&<>') for tok in argv):
        return form,None,'compound_or_redirection'
    return form,argv,None

def activity(tool, inp):
    t=str(tool or ''); tl=t.lower()
    if tl in {'read','open','glob','grep','ls','search','find','list','readfile'}: return 'Read/Search','direct_tool',None
    if tl in {'edit','write','multiedit','notebookedit','replace','patch','apply_patch','insert','delete'}: return 'Edit/Write','direct_tool',None
    if tl in {'task','notebook','browser','computer','submit'}: return 'Other','explicit_non_shell_tool',None
    if tl not in {'bash','bash_terminal','shell','terminal','python','interpreter','execute','run_command'}: return 'Unknown','unrecognized_tool',None
    form,argv,reason=shell_argv(inp)
    if reason:return 'Unknown',reason,form
    if not argv:return 'Unknown','empty_command',form
    exe=Path(argv[0]).name.lower(); args=[x.lower() for x in argv[1:]]
    is_test=False
    if exe in {'pytest','py.test'}: is_test=not any(x in {'--help','-h','--version'} for x in args)
    elif exe in {'python','python3','python3.11','python3.12'} and len(args)>=2 and args[0]=='-m' and args[1] in {'pytest','unittest'}: is_test=not any(x in {'--help','-h','--version'} for x in args[2:])
    elif exe in {'npm','yarn','pnpm'} and args and args[0]=='test': is_test=True
    elif exe in {'mvn','gradle','make','go','cargo'} and 'test' in args and not any(x in {'--help','-h','--version'} for x in args): is_test=True
    elif exe in {'./gradlew','gradlew'} and 'test' in args and not any(x in {'--help','-h','--version'} for x in args): is_test=True
    if is_test:return 'Test','explicit_test_command',form
    if exe in {'pytest','py.test','npm','yarn','pnpm','mvn','gradle','make','go','cargo','./gradlew','gradlew'} and any(x in {'--help','-h','--version','testing'} for x in args): return 'Unknown','test_help_version_or_non_test',form
    if exe in {'cat','head','tail','less','more','grep','rg','ripgrep','find','ls','stat','file','awk'}: return 'Read/Search','simple_read_search_command',form
    if exe=='git' and args and args[0] in {'diff','show','status','log','grep'}: return 'Read/Search','simple_git_read_command',form
    if exe in {'sed','perl'} and any(x in {'-i','--in-place'} or x.startswith('-i') for x in args): return 'Edit/Write','simple_in_place_command',form
    if exe in {'cp','mv','install','tee'}: return 'Edit/Write','simple_write_command',form
    if exe in {'python','python3','python3.11','python3.12'} and args and args[0] in {'-c','-e'}: return 'Unknown','inline_code_semantics_unsupported',form
    if exe in {'python','python3','python3.11','python3.12','node','ruby','bash','sh','zsh','java','julia'}: return 'Interpreter/Execute','simple_interpreter_command',form
    return 'Unknown','unrecognized_command',form

def summarize(rec,shard,line):
    participant=rec.get('participant') if isinstance(rec.get('participant'),dict) else {}
    run=rec.get('run') if isinstance(rec.get('run'),dict) else {}
    usage=rec.get('usage') if isinstance(rec.get('usage'),dict) else {}
    tok=usage.get('tokens') if isinstance(usage.get('tokens'),dict) else {}
    events=rec.get('events') if isinstance(rec.get('events'),list) else []
    calls=[e for e in events if e.get('type')=='tool_call']; results=[e for e in events if e.get('type')=='tool_result']
    call_ids=collections.Counter(e.get('tool_call_id') for e in calls if e.get('tool_call_id') is not None)
    result_ids=collections.Counter(e.get('tool_call_id') for e in results if e.get('tool_call_id') is not None)
    native=collections.Counter(str(e.get('tool')) for e in calls)
    activities=[]; reasons=collections.Counter(); unknown_reasons=collections.Counter(); forms=collections.Counter()
    for e in calls:
        cat,reason,form=activity(e.get('tool'),e.get('input')); activities.append(cat); reasons[reason]+=1; unknown_reasons[reason]+=int(cat=='Unknown'); forms[form or 'unknown']+=1
    transitions=collections.Counter(); segments=[]; current=None
    for cat in activities+['Unknown']:
        if cat=='Unknown':
            if current: segments.append({'category':current[0],'count':current[1]}); current=None
        elif current is None: current=[cat,1]
        else:
            transitions[f'{current[0]}→{cat}']+=1
            if current[0]==cat: current[1]+=1
            else: segments.append({'category':current[0],'count':current[1]}); current=[cat,1]
    duration={'present':0,'missing':0,'null':0,'valid':0,'zero':0,'negative':0,'invalid_type':0,'associated_id_valid':0}
    for e in results:
        if 'duration_ms' not in e: duration['missing']+=1; continue
        duration['present']+=1; v=e.get('duration_ms')
        if v is None: duration['null']+=1
        elif not number(v): duration['invalid_type']+=1
        elif v<0: duration['negative']+=1
        else:
            duration['valid']+=1; duration['zero']+=int(v==0); duration['associated_id_valid']+=int(e.get('tool_call_id') is not None)
    ev=rec.get('evaluation') if isinstance(rec.get('evaluation'),dict) else {}
    return {'trajectory_id':rec.get('trajectory_id'),'task_id':rec.get('instance_id'),'participant':participant.get('key'),'model':participant.get('model'),'scaffold':participant.get('scaffold'),'run_index':run.get('index'),'source':{'shard':shard,'line':line},'schema_version':rec.get('schema_version'),'event_count':len(events),'model_message_count':sum(e.get('type') in {'prompt','assistant_message','final_message'} for e in events),'tool_call_count':len(calls),'tool_result_count':len(results),'native_tools':dict(native),'activity_counts':dict(collections.Counter(activities)),'activity_unknown_reasons':dict(unknown_reasons),'command_forms':dict(forms),'activity_sequence':activities,'transitions':dict(transitions),'segments':segments,'segment_count':len(segments),'segment_activity_count':sum(x['count'] for x in segments),'association':association(call_ids,result_ids,calls,results),'duration_ms':duration,'sequence_order_basis':'saved_tool_call_event_order','concurrency_order':'unknown_not_recorded','record_completeness':dict(collections.Counter(e.get('completeness') for e in events if e.get('completeness'))),'unavailable_event_count':sum(bool(e.get('unavailable')) for e in events),'usage':{'model_calls':usage.get('model_calls'),'steps':usage.get('steps'),'tool_calls':usage.get('tool_calls'),'wall_time_seconds':usage.get('wall_time_seconds'),'input_tokens':tok.get('input'),'output_tokens':tok.get('output'),'total_tokens':tok.get('total')},'evaluation':{'status':ev.get('status'),'resolved':ev.get('resolved'),'agent_exit_status':ev.get('agent_exit_status'),'evaluation_matches_selected':ev.get('evaluation_matches_selected')}}

def association(calls,results,call_events,result_events):
    all_ids=set(calls)|set(results); only_calls=sum(1 for x in all_ids if calls[x] and not results[x]); only_results=sum(1 for x in all_ids if results[x] and not calls[x]); one=sum(1 for x in all_ids if calls[x]==1 and results[x]==1); non=sum(1 for x in all_ids if not (calls[x]==1 and results[x]==1))
    return {'call_event_count':len(call_events),'result_event_count':len(result_events),'calls_with_id':sum(calls.values()),'results_with_id':sum(results.values()),'distinct_call_ids':len(calls),'distinct_result_ids':len(results),'missing_id_call_count':len(call_events)-sum(calls.values()),'missing_id_result_count':len(result_events)-sum(results.values()),'duplicate_call_ids':{k:v for k,v in calls.items() if v>1},'duplicate_result_ids':{k:v for k,v in results.items() if v>1},'only_call_id_count':only_calls,'only_result_id_count':only_results,'one_to_one_id_count':one,'non_one_to_one_id_count':non,'matched_distinct_id_count':sum(1 for x in all_ids if calls[x] and results[x])}

def analyze(root,acq,out):
    if out.exists():raise FileExistsError(str(out))
    sm=json.loads((root/'manifest.json').read_text()); index=[json.loads(x) for x in (root/'index.jsonl').read_text().splitlines() if x.strip()]
    if sm.get('schema_version')!=SCHEMA or len(index)!=sm.get('shards'):raise ValueError('schema or shard count mismatch')
    am=json.loads(acq.read_text()); amap={x['path']:x for x in am.get('inputs',[])}; records=[]; errors=[]; shards=[]; prefix=PREFIX
    for ent in index:
        rel=ent['path']; p=root/rel; problems=[]
        if not p.is_file():errors.append({'kind':'missing_shard','path':rel});continue
        b=p.stat().st_size; h=sha256(p); ae=amap.get(prefix+rel)
        if b!=ent.get('gzip_bytes'):problems.append('index_bytes_mismatch')
        if not ae:problems.append('acquisition_manifest_missing')
        elif (ae.get('bytes'),ae.get('sha256'))!=(b,h):problems.append('acquisition_hash_mismatch')
        start=len(records); count=0; content_hash=hashlib.sha256()
        try:
            with gzip.open(p,'rb') as f:
                for line_no,raw in enumerate(f,1):
                    content_hash.update(raw)
                    try:line=raw.decode('utf-8')
                    except UnicodeDecodeError as e:errors.append({'kind':'invalid_utf8','path':rel,'line':line_no,'error_type':type(e).__name__});continue
                    if not line.strip():continue
                    try:r=json.loads(line)
                    except Exception as e:errors.append({'kind':'invalid_jsonl','path':rel,'line':line_no,'error_type':type(e).__name__});continue
                    if r.get('schema_version')!=SCHEMA:errors.append({'kind':'record_schema_mismatch','path':rel,'line':line_no,'value':r.get('schema_version')});continue
                    count+=1;records.append(summarize(r,rel,line_no))
        except Exception as e:errors.append({'kind':'gzip_error','path':rel,'error_type':type(e).__name__})
        uh=content_hash.hexdigest()
        if ent.get('content_sha256') and uh!=ent['content_sha256']:problems.append('index_content_sha256_mismatch')
        if count!=ent.get('rows'):problems.append('index_row_count_mismatch');errors.append({'kind':'row_count_mismatch','path':rel,'expected':ent.get('rows'),'parsed':count})
        quarantined=bool(set(problems)&{'index_bytes_mismatch','index_content_sha256_mismatch','acquisition_manifest_missing','acquisition_hash_mismatch'})
        if quarantined:
            del records[start:];errors.append({'kind':'quarantined_shard','path':rel,'reasons':problems})
        shards.append({'path':rel,'bytes':b,'sha256':h,'content_sha256':uh,'index_rows':ent.get('rows'),'parsed_rows':0 if quarantined else count,'errors':problems,'quarantined':quarantined})
    return write_report(records,errors,shards,sm,root,acq,out)

def write_report(records,errors,shards,sm,root,acq,out):
    groups=collections.defaultdict(list)
    for r in records:groups[(r['task_id'],r['participant'])].append(r)
    participants=sorted({r['participant'] for r in records});tasks=sorted({r['task_id'] for r in records});p_tasks={p:{r['task_id'] for r in records if r['participant']==p} for p in participants};common=sorted(set.intersection(*p_tasks.values())) if p_tasks else []
    ident=collections.Counter((r['task_id'],r['participant'],r['run_index']) for r in records);dup=[{'task_id':a,'participant':b,'run_index':c,'count':n} for (a,b,c),n in ident.items() if n>1]
    native=collections.Counter();acts=collections.Counter();trans=collections.Counter();term=collections.Counter();evstat=collections.Counter();duration=collections.defaultdict(lambda:collections.Counter()); assoc=collections.Counter()
    for r in records:
        native.update(r['native_tools']);acts.update(r['activity_counts']);trans.update(r['transitions']);term[str(r['evaluation']['agent_exit_status'])]+=1;evstat[str(r['evaluation']['status'])]+=1;assoc.update({k:r['association'][k] for k in ('call_event_count','result_event_count','calls_with_id','results_with_id','missing_id_call_count','missing_id_result_count','only_call_id_count','only_result_id_count','one_to_one_id_count','non_one_to_one_id_count')})
        for k,v in r['duration_ms'].items():duration[r['participant']][k]+=v
    repeat={}
    for (task,p),rows in sorted(groups.items()):repeat[f'{task}::{p}']={'task_id':task,'participant':p,'n':len(rows),'run_indices':sorted(r['run_index'] for r in rows),'metrics':{k:stats([r[k] for r in rows]) for k in ('tool_call_count','tool_result_count','event_count')},'usage':{k:stats([r['usage'].get(k) for r in rows]) for k in ('model_calls','steps','tool_calls','wall_time_seconds','input_tokens','output_tokens','total_tokens')}}
    med=percentile([r['tool_call_count'] for r in records],.5)
    def cand(r,role,value):return {'role':role,'task_id':r['task_id'],'participant':r['participant'],'run_index':r['run_index'],'value':value}
    candidates={'roles':{'typical_workload':[cand(r,'closest_to_pooled_median',r['tool_call_count']) for r in sorted(records,key=lambda r:(abs(r['tool_call_count']-med),r['task_id'],r['participant'],r['run_index']))[:3]],'high_tool_call_volume':[cand(r,'high_tool_call_volume',r['tool_call_count']) for r in sorted(records,key=lambda r:(-r['tool_call_count'],r['task_id'],r['participant'],r['run_index']))[:3]],'high_read_search_share':[cand(r,'high_read_search_share',r['activity_counts'].get('Read/Search',0)/r['tool_call_count'] if r['tool_call_count'] else 0) for r in sorted(records,key=lambda r:(-(r['activity_counts'].get('Read/Search',0)/r['tool_call_count'] if r['tool_call_count'] else 0),r['task_id'],r['participant'],r['run_index']))[:3]],'high_test_share':[cand(r,'high_test_share',r['activity_counts'].get('Test',0)/r['tool_call_count'] if r['tool_call_count'] else 0) for r in sorted(records,key=lambda r:(-(r['activity_counts'].get('Test',0)/r['tool_call_count'] if r['tool_call_count'] else 0),r['task_id'],r['participant'],r['run_index']))[:3]]},'note':'Roles can overlap; they are research leads, not execution authorization or independent-task counts.'}
    variability=[]
    for (task,p),rows in groups.items():vals=[r['tool_call_count'] for r in rows];variability.append((-(iqr(vals) or 0),task,p,vals))
    candidates['roles']['largest_repeat_iqr']=[{'role':'largest_repeat_iqr','task_id':t,'participant':p,'tool_call_counts':v,'iqr':-x} for x,t,p,v in sorted(variability)[:3]]
    out.mkdir(parents=True);(out/'per_trajectory.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in records));(out/'measurement_candidates.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2)+'\n')
    semantic_coverage={p:{'total_tool_calls':sum(r['tool_call_count'] for r in records if r['participant']==p),'classified':sum(v for r in records if r['participant']==p for k,v in r['activity_counts'].items() if k!='Unknown'),'unknown':sum(r['activity_counts'].get('Unknown',0) for r in records if r['participant']==p),'unknown_reasons':dict(collections.Counter(reason for r in records if r['participant']==p for reason,n in r['activity_unknown_reasons'].items() for _ in range(n)))} for p in participants}
    summary={
        'scope': {'corpus':'third-party SWE-rebench normalized trajectory corpus','record_count':len(records),'task_count':len(tasks),'participant_count':len(participants),'trajectory_shards':len(shards)},
        'coverage': {
            'source_manifest': {'schema_version':sm.get('schema_version'),'declared_rows':sm.get('rows'),'declared_shards':sm.get('shards'),'declared_participants':sm.get('participants')},
            'shards':shards,
            'records': {'parsed':len(records),'errors':len(errors),'error_examples':errors[:30]},
            'task_count':len(tasks),'participant_count':len(participants),'participants':participants,
            'participant_task_counts':{p:len(v) for p,v in p_tasks.items()},
            'common_task_count':len(common),'common_task_sample':common[:20],
            'duplicate_identity_count':len(dup),'duplicate_identities':dup,
            'participant_run_counts':{p:dict(collections.Counter(r['run_index'] for r in records if r['participant']==p)) for p in participants}
        },
        'native_tool_counts':dict(native),'activity_counts':dict(acts),
        'semantic_coverage_by_participant':semantic_coverage,
        'association_totals':dict(assoc),
        'duration_ms_by_participant':{p:dict(v) for p,v in duration.items()},
        'transition_counts':dict(trans),'termination_counts':dict(term),
        'evaluation_status_counts':dict(evstat),'repeat_groups':repeat,
        'pooled_workload': {
            'tool_calls': {'total':sum(r['tool_call_count'] for r in records),'median':med,'iqr':iqr([r['tool_call_count'] for r in records])},
            'tool_results': {'total':sum(r['tool_result_count'] for r in records),'median':percentile([r['tool_result_count'] for r in records],.5),'iqr':iqr([r['tool_result_count'] for r in records])},
            'source_usage':{k:stats([r['usage'].get(k) for r in records]) for k in ('model_calls','steps','tool_calls','wall_time_seconds','input_tokens','output_tokens','total_tokens')},
            'activity_denominator':'all parsed tool_call events; Unknown is retained'
        },
        'rules': {'command_semantics':'finite simple command/argv forms only; compound/redirection/wrappers and unsupported shapes are Unknown','test':'bounded executable/argument recognition; help/version/non-test names are not Test','sequence':'saved tool_call event order only; Unknown breaks adjacency; concurrency order is unknown; no event reordering','association':'Counter-preserving ID association; no positional pairing'},
        'candidates':candidates,
        'limits':['No CPU, memory, I/O, hotspot, tool duration, waiting, or causal conclusions.','duration_ms semantics and clock/window are unknown; not interpreted as execution or CPU time.','Usage is source data, not billing.','Participant labels are not controlled model comparisons.','resolved and agent_exit_status are separate source fields.']
    }
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    top_native=sorted(native.items(),key=lambda z:(-z[1],z[0]))[:5];top_trans=sorted(trans.items(),key=lambda z:(-z[1],z[0]))[:5]
    md=['# SWE-rebench behavior v2','', '第三方 normalized Coding corpus 的流式离线行为分析；不称官方原始轨迹，不执行记录命令。','', '## 规模与身份',f'- `{len(shards)}` 个 shard、`{len(records)}` 条 trajectory、`{len(tasks)}` 个 task、`{len(participants)}` 个 participant；每个 participant 的 run 分布从实际记录生成。',f'- 解析/哈希隔离错误 `{len(errors)}`，重复 task×participant×run 身份 `{len(dup)}`；source content hash 按解压 JSONL bytes 核对。','', '## v2 数据观察',f'- 原生 tool_call 总数 `{sum(r["tool_call_count"] for r in records):,}`；tool_result 总数 `{sum(r["tool_result_count"] for r in records):,}`；差额 `{sum(r["tool_result_count"] for r in records)-sum(r["tool_call_count"] for r in records):,}` 由逐事件计数和 ID 关联字段解释，未强行一一配对。',f'- 原生工具名称最高：'+', '.join(f'{k}={v:,}' for k,v in top_native)+'.',f'- 保守活动分类：'+', '.join(f'{k}={acts.get(k,0):,}' for k in CATEGORIES)+ '；通用 shell 未被自动当作具体读写活动。',f'- 保存的 tool_call 顺序转换最高：'+', '.join(f'{k}={v:,}' for k,v in top_trans)+ '；不称实际执行顺序，不声称已检测并发。',f'- evaluation status：'+', '.join(f'{k}={v:,}' for k,v in sorted(evstat.items()))+'；agent_exit_status：'+', '.join(f'{k}={v:,}' for k,v in sorted(term.items()))+'。', '- `duration_ms` 仅做字段可用性计数，未解释为 CPU、完整 wall 或精确执行区间。','', '## 候选与边界','候选位于 `measurement_candidates.json`，角色可重叠，不构成实验授权；participant 间语义覆盖差异不用于排名。','', '## v1→v2','- v2 保留原生接口计数和基础 task/participant/run 覆盖；活动语义改为有限命令证据，Test 边界收紧，重复 ID/多返回/孤立返回/缺 ID 单独报告。','- v1 的“Shell 即执行活动”、Test 前缀识别、集合丢 ID、以及“已排除并发边界”的表述撤回。','', '## 限制','不支持 CPU/内存/I/O/热点、单工具耗时、等待/思考时间、因果解释、模型排名或 Coding 类别代表性。resolved 不等于正常 termination，usage 不等于账单。','', '[summary.json](summary.json) · [per_trajectory.jsonl](per_trajectory.jsonl) · [measurement_candidates.json](measurement_candidates.json) · [manifest.json](manifest.json)']
    (out/'summary.md').write_text('\n'.join(md)+'\n')
    corrections=['# v1 → v2 corrections','', '| 原问题 | 实际修复 | 影响 |','|---|---|---|','| 通用 shell 被直接归为执行类别 | 原生接口与有限活动语义分层；未支持命令保留 Unknown/Mixed | 活动计数和 Read/Test 候选收紧；原生调用总数不变 |','| Test 使用宽松 startswith | 按 executable、参数边界和 help/version 排除规则识别 | `pytest_fake`、`npm testing`、echo/grep/print 文本不再是 Test |','| ID 转 set 丢失重复 | Counter 保留重复调用/返回 ID，区分 1:1、非 1:1、孤立及缺 ID | 关联结论更细；调用/返回总计不被改写 |','| 序列实际只按保存调用顺序连接 | 明确命名为保存 tool_call 事件顺序；Unknown 打断；并发顺序 unknown | 撤回“已排除并发边界”表述 |','| 未盘点 duration_ms | 按 participant 统计 present/valid/zero/negative/invalid/missing 和 ID 关联 | 纠正“完全没有字段”，仍不开展耗时分析 |','', '## v1 撤回项', '- 通用 shell 分类可代表具体读写/执行活动。', '- Test 最高/最低比较可直接解释为测试活动密集度。', '- 保存事件转换已排除不明并发边界。', '', '## v2 仍可支持', '- 111 task、17 participant、5 个 run 的实际覆盖与重复统计。', '- 原生工具接口计数、保守活动类别、保存事件顺序转换、调用/返回差额和有限重复波动。', '- `duration_ms` 字段存在性盘点；其语义仍 unknown。']
    (out/'corrections.md').write_text('\n'.join(corrections)+'\n')
    project=Path.cwd();
    def disp(q):
        try:return str(q.relative_to(project))
        except ValueError:return str(q)
    outputs=[]
    for name in ('summary.json','summary.md','per_trajectory.jsonl','measurement_candidates.json','corrections.md'):
        q=out/name;outputs.append({'path':disp(q),'bytes':q.stat().st_size,'sha256':sha256(q)})
    man={'schema':'swe-rebench-behavior-v2-manifest','inputs':[{'path':disp(root/'manifest.json'),'bytes':(root/'manifest.json').stat().st_size,'sha256':sha256(root/'manifest.json'),'role':'source_manifest'},{'path':disp(root/'index.jsonl'),'bytes':(root/'index.jsonl').stat().st_size,'sha256':sha256(root/'index.jsonl'),'role':'source_index'},{'path':disp(acq),'bytes':acq.stat().st_size,'sha256':sha256(acq),'role':'acquisition_manifest'}],'shards':shards,'analyzer':{'path':disp(Path(__file__)),'sha256':sha256(Path(__file__))},'outputs':outputs,'manifest_self_hash':'excluded'}
    (out/'manifest.json').write_text(json.dumps(man,ensure_ascii=False,indent=2)+'\n')
    return summary

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-root',type=Path,required=True);ap.add_argument('--acquisition-manifest',type=Path,required=True);ap.add_argument('--output-dir',type=Path,required=True);a=ap.parse_args()
    try:analyze(a.input_root,a.acquisition_manifest,a.output_dir)
    except FileExistsError as e:print(f'output_exists: {e}',file=sys.stderr);return 2
    except Exception as e:print(f'analysis_failed: {type(e).__name__}: {e}',file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
