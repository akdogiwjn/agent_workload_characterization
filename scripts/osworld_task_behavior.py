#!/usr/bin/env python3
"""Offline OSWorld task semantics + multi-model saved-action analysis.
No task/action source is imported or executed.
"""
from __future__ import annotations
import argparse, ast, hashlib, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
REVISION='01cb84fcd5fb8ee415e7e065d7aaf3ec8f95fe1f'
TASK_COMMIT='e7996f4cc850be108e510bd8433c63ee7b8303dd'
sys.path.insert(0,str(Path(__file__).parent))
import osworld_minimax_behavior as behavior


def sha(path):
    h=hashlib.sha256(); n=0
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b); n+=len(b)
    return n,h.hexdigest()

def rel(path):
    try:return str(path.relative_to(PROJECT))
    except ValueError:return str(path)

def finite(x): return type(x) in (int,float) and not isinstance(x,bool) and math.isfinite(float(x))
def q(values,p):
    a=sorted(float(x) for x in values if finite(x))
    if not a:return None
    z=(len(a)-1)*p; lo=int(z); hi=min(lo+1,len(a)-1)
    return a[lo] if lo==hi else a[lo]+(a[hi]-a[lo])*(z-lo)
def stats(values):
    a=[x for x in values if finite(x)]; q1,q3=q(a,.25),q(a,.75)
    return {'n':len(a),'missing':len(values)-len(a),'min':q(a,0),'q1':q1,'median':q(a,.5),'q3':q3,'iqr':None if q1 is None else q3-q1,'max':q(a,1)}

def literal(node,env):
    if isinstance(node,ast.Constant): return node.value,True
    if isinstance(node,ast.Name) and node.id in env:return env[node.id],True
    if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
        v,ok=literal(node.operand,env); return ((-v if isinstance(node.op,ast.USub) else v),True) if ok and finite(v) else (None,False)
    if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):
        a,ok1=literal(node.left,env); b,ok2=literal(node.right,env)
        if ok1 and ok2 and type(a)==type(b) and isinstance(a,(str,tuple,list)): return a+b,True
    if isinstance(node,(ast.Tuple,ast.List,ast.Set)):
        vals=[]
        for x in node.elts:
            v,ok=literal(x,env)
            if not ok:return None,False
            vals.append(v)
        return (tuple(vals) if isinstance(node,ast.Tuple) else set(vals) if isinstance(node,ast.Set) else vals),True
    if isinstance(node,ast.Dict):
        d={}
        for k,v in zip(node.keys,node.values):
            kk,ok1=literal(k,env); vv,ok2=literal(v,env)
            if not(ok1 and ok2):return None,False
            d[kk]=vv
        return d,True
    return None,False

def top_env(tree):
    env={}
    for node in tree.body:
        if isinstance(node,ast.Assign):
            for t in node.targets:
                if isinstance(t,ast.Name):
                    v,ok=literal(node.value,env)
                    if ok:env[t.id]=v
        elif isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name):
            v,ok=literal(node.value,env)
            if ok:env[node.target.id]=v
    return env

def attr_values(cls,env,path):
    vals={}; ev={}
    for node in cls.body:
        target=value=None
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name): target=node.targets[0].id; value=node.value
        elif isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name): target=node.target.id; value=node.value
        if target:
            v,ok=literal(value,env)
            if ok: vals[target]=v; ev[target]={'path':rel(path),'line':node.lineno}
    return vals,ev

def task_semantics(path):
    source=path.read_text(errors='replace'); tree=ast.parse(source,filename=str(path)); env=top_env(tree); key=path.stem.replace('task_','')
    classes=[n for n in tree.body if isinstance(n,ast.ClassDef)]; ranked=[]
    for cls in classes:
        vals,_=attr_values(cls,env,path); score=(3 if vals.get('id')==key else 0)+(2 if cls.name==f'Task{key}' else 0)+(1 if 'BaseTask' in [ast.unparse(x) for x in cls.bases] else 0)
        ranked.append((score,cls,vals))
    exact=[x for x in ranked if x[2].get('id')==key]
    named=[x for x in ranked if x[1].name==f'Task{key}']
    candidates=exact or named
    if len(candidates)!=1:
        status='ambiguous_class' if len(candidates)>1 else 'task_class_not_identified'
        cls=None; vals={}; ev={}
    else:
        status='ok'; _,cls,vals=candidates[0]; vals,ev=attr_values(cls,env,path)
    def excerpt(v): return v if isinstance(v,str) and len(v)<=1200 else (v[:1200]+'…' if isinstance(v,str) else None)
    instruction=vals.get('instruction'); apps=vals.get('related_apps'); snapshot=vals.get('snapshot')
    text=' '.join(str(x) for x in (instruction,apps,snapshot) if x is not None).lower()
    rules={
      'browser_information_processing':r'\b(browser|chrome|firefox|website|web page|url|internet|web search)\b',
      'spreadsheet':r'\b(spreadsheet|excel|calc|csv|cell|worksheet)\b',
      'document_pdf':r'\b(writer|document|pdf|word|odt)\b',
      'email':r'\b(thunderbird|email|e-mail|mailbox)\b',
      'calendar':r'\b(calendar|evolution|meeting|appointment)\b',
      'file_management':r'\b(file manager|folder|directory|file(s)?|desktop)\b',
      'development_terminal':r'\b(vscode|visual studio code|terminal|shell|python|git|javascript|npm|localhost|programming|code editor)\b',
      'presentation':r'\b(slides?|presentation|powerpoint|impress)\b',
      'media_game':r'\b(game|video|music|vlc)\b',
    }
    labels=[]; evidence={}
    for label,pat in rules.items():
        m=re.search(pat,text,re.I)
        if m:
            labels.append(label); evidence[label]={'field':'instruction/related_apps/snapshot','match':m.group(0),'rule':pat}
    if not labels: labels=['unknown']
    op_rules={'read_or_search':r'\b(read|find|search|check|view|look)\b','create_or_write':r'\b(create|write|add|enter|implement|build|save)\b','edit_or_modify':r'\b(edit|modify|update|change|delete|remove)\b','filter_or_sort':r'\b(filter|sort)\b','navigate_or_open':r'\b(open|launch|navigate|click)\b','compare_or_verify':r'\b(verify|compare|check|ensure)\b'}
    ops=sorted(k for k,p in op_rules.items() if re.search(p,text,re.I))
    methods=[n.name for n in (cls.body if cls else []) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
    return {'task_key':key,'task_id':vals.get('id'),'task_class':cls.name if cls else None,'instruction_excerpt':excerpt(instruction),'instruction_length':len(instruction) if isinstance(instruction,str) else None,'related_apps':apps,'snapshot':snapshot,'setup_present':'setup' in methods,'evaluator_present':any('eval' in n.lower() or 'score' in n.lower() for n in methods),'labels':labels,'label_evidence':evidence,'operation_needs':ops,'evidence':ev,'parse_status':status if isinstance(instruction,str) else ('partial' if status=='ok' else status),'semantic_version_binding':'unknown'}

def load_tasks(root):
    rows=[]; errors=[]
    for p in sorted(root.glob('task_*.py')):
        try: rows.append(task_semantics(p))
        except Exception as e: errors.append({'path':rel(p),'error':type(e).__name__})
    return rows,errors

NATIVE_MAP={'left_click':'click','double_click':'click','triple_click':'click','right_click':'click','left_click_drag':'pointer','mouse_move':'pointer','left_mouse_down':'pointer','left_mouse_up':'pointer','type':'text_or_key','key':'text_or_key','hotkey':'text_or_key','scroll':'scroll','wait':'wait'}
def native_from_action(a):
    if not isinstance(a,dict): return None,None
    payload=a.get('input') if isinstance(a.get('input'),dict) else a.get('action') if isinstance(a.get('action'),dict) else None
    if not isinstance(payload,dict):
        action_type=a.get('action_type')
        if action_type in ('computer_call','tool_use'): return action_type,'unknown'
        return None,None
    name=payload.get('action')
    return name,NATIVE_MAP.get(name,'screenshot' if name=='screenshot' else 'unknown') if isinstance(name,str) else 'unknown'
def action_sources(value):
    if isinstance(value,str): return {'command':value,'command_origin':'action_string','native_name':None,'native_category':None,'source_conflict':None}
    if not isinstance(value,dict): return {'command':None,'command_origin':'missing_or_unknown','native_name':None,'native_category':None,'source_conflict':None}
    name,cat=native_from_action(value); command=value.get('command') if isinstance(value.get('command'),str) else None
    conflict=None
    if name and command:
        parsed=behavior.static_calls(command)
        cats={x['category'] for x in parsed.get('calls',[])} if parsed.get('status')=='known' else set()
        expected=NATIVE_MAP.get(name)
        if name=='screenshot' and 'wait' in cats: conflict='native_screenshot_command_placeholder_wait'
        elif expected and cats and expected not in cats: conflict='native_command_category_conflict'
        else: conflict='consistent_or_unresolved'
    return {'command':command,'command_origin':'dict.command' if command else 'missing','native_name':name,'native_category':cat,'source_conflict':conflict}

def sequence_stats(tokens):
    clean=[x for x in tokens if x is not None]
    tr,sc,sa,sl=behavior.finish_segments(tokens)
    return {'transition_counts':{f'{a}->{b}':n for (a,b),n in sorted(tr.items())},'segment_counts':dict(sorted(sc.items())),'segment_action_counts':dict(sorted(sa.items())),'segment_length_counts':{f'{a}:{n}':v for (a,n),v in sorted(sl.items())}}

def safe_result(path,kind): return behavior.safe_result(path,kind)
def reward_summary(rows): return behavior.reward_summary(rows)

def analyze_task(task_dir,input_root):
    rows=[]; invalid=[]; steps=[]; static_tokens=[]; native_tokens=[]; source_calls=0; supported=[]; parse_reasons=Counter(); field_types=Counter(); native_counts=Counter(); native_unknown=0; commands=0; missing_commands=0; conflicts=Counter()
    with (task_dir/'traj.jsonl').open(errors='replace') as stream:
        for line_no,line in enumerate(stream,1):
            if not line.strip(): continue
            try: row=json.loads(line)
            except Exception as e: invalid.append({'line':line_no,'error_type':type(e).__name__}); static_tokens.append(None); native_tokens.append(None); continue
            rows.append(row); steps.append(row.get('step_num')); a=row.get('action'); field_types[type(a).__name__]+=1
            src=action_sources(a)
            if src['native_category']:
                native_counts[src['native_category']]+=1; native_tokens.append(None if src['native_category']=='unknown' else src['native_category'])
                if src['native_category']=='unknown': native_unknown+=1
            else: native_tokens.append(None)
            if src['source_conflict']: conflicts[src['source_conflict']]+=1
            if src['command'] is None: missing_commands+=1; parse_reasons['command_missing']+=1; static_tokens.append(None); continue
            commands+=1; parsed=behavior.static_calls(src['command']); source_calls+=parsed['source_call_syntax_count']; reason=parsed.get('reason') or 'known'; parse_reasons[reason]+=1
            if parsed['status']!='known': static_tokens.append(None); continue
            for call in parsed['calls']:
                item={'source_line':line_no,'step_num':row.get('step_num'),**call}; supported.append(item); static_tokens.append(call['category'])
    ints=[x for x in steps if isinstance(x,int) and not isinstance(x,bool)]
    step_info={'missing':sum('step_num' not in r for r in rows),'duplicate_value_count':len(ints)-len(set(ints)),'descending_adjacent_pairs':sum(b<a for a,b in zip(ints,ints[1:]))}
    status='valid' if rows and not invalid and not parse_reasons.get('command_missing') and not any(k!='known' for k in parse_reasons) else ('partial' if supported or native_counts else 'unanalysable')
    done=[r.get('done') for r in rows]; done_true=[i for i,v in enumerate(done) if v is True]
    static=sequence_stats(static_tokens); native=sequence_stats(native_tokens)
    native_status='applicable' if native_counts else 'not_applicable'
    return {'task_key':task_dir.name,'source_file':str(task_dir.joinpath('traj.jsonl').relative_to(input_root)),'record_count':len(rows),'invalid_json_lines':invalid,'action_field_type_counts':dict(sorted(field_types.items())),'step_num':step_info,'command_record_count':commands,'command_missing_count':missing_commands,'source_call_syntax_count':source_calls,'supported_static_call_count':len(supported),'native_representation_status':native_status,'native_action_record_count':sum(native_counts.values()),'native_unknown_action_count':native_unknown,'native_action_category_counts':dict(sorted(native_counts.items())),'native_source_conflicts':dict(sorted(conflicts.items())),'unknown_action_record_count':sum(v for k,v in parse_reasons.items() if k!='known'),'unknown_reason_counts':dict(sorted(parse_reasons.items())),'analysis_status':status,'static_category_counts':dict(sorted(Counter(x['category'] for x in supported).items())),'category_counts':dict(sorted(Counter(x['category'] for x in supported).items())),'static_sequence':static,'native_sequence':native,'action_order_sources':supported[:1000],'action_order_truncated':len(supported)>1000,'done_counts':dict(Counter(str(v) for v in done)),'done_true_record_indexes':done_true,'records_after_first_done':max(0,len(rows)-(done_true[0]+1)) if done_true else 0,'reward':reward_summary(rows),'results':{'result_json':safe_result(task_dir/'result.json','result'),'result_txt':safe_result(task_dir/'result.txt','txt'),'checkpoint_results':safe_result(task_dir/'checkpoint_results.json','checkpoint')},'timestamp_semantics':'unknown; not reported as duration'}

def api_summary(meta_root,task_ids):
    rows=[]; errors=[]; request_values=defaultdict(list); task_values=defaultdict(list); report_totals=Counter(); recomputed=Counter(); req_equal=0; source_missing=0; usage_missing=0; field_missing=Counter(); validation=Counter()
    base_fields=('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens'); input_fields=('input_tokens','cache_read_input_tokens','cache_creation_input_tokens')
    for tid in task_ids:
        p=meta_root/'website_demo'/'MiniMax-M3'/'tasks'/tid/'api_usage.json'
        if not p.is_file(): rows.append({'task_id':tid,'status':'missing'}); continue
        try:x=json.loads(p.read_text())
        except Exception as e: errors.append({'task_id':tid,'error_type':type(e).__name__}); continue
        if str(x.get('task_id')).zfill(3)!=tid: validation['task_id_mismatch']+=1
        calls=x.get('calls') if isinstance(x.get('calls'),list) else []; cc=x.get('call_count');
        if not isinstance(cc,int) or cc!=len(calls): validation['call_count_mismatch']+=1
        nums=[c.get('call_number') for c in calls]; validnums=[n for n in nums if type(n) is int]
        bad_nums=sum(type(n) is not int for n in nums); dup_nums=len(validnums)-len(set(validnums))
        if bad_nums: validation['call_number_missing_or_nonint']+=bad_nums
        if dup_nums: validation['duplicate_call_number']+=dup_nums
        source_missing+=int(x.get('missing_usage_count') or 0); sums=Counter(); field_counts=Counter(); miss_usage=0; eq=0
        for c in calls:
            rt,st=c.get('request_time'),c.get('response_time')
            if finite(rt) and finite(st) and rt==st:eq+=1
            u=c.get('usage')
            if not isinstance(u,dict):
                miss_usage+=1
                for k in base_fields: request_values[k].append(None); field_missing[k]+=1
                request_values['input_tokens_including_cache_derived'].append(None)
                continue
            for k in base_fields:
                v=u.get(k); field_counts[k]+=int(not finite(v)); request_values[k].append(v if finite(v) else None)
                if finite(v): sums[k]+=v
                else: field_missing[k]+=1
            if all(finite(u.get(k)) for k in input_fields): request_values['input_tokens_including_cache_derived'].append(sum(u[k] for k in input_fields))
            else: request_values['input_tokens_including_cache_derived'].append(None)
        usage_missing+=miss_usage
        report=x.get('numeric_totals') if isinstance(x.get('numeric_totals'),dict) else {}
        for k in base_fields:
            if finite(report.get(k)): report_totals[k]+=report[k]
        task_complete={k: field_counts[k]==0 and miss_usage==0 for k in base_fields}
        for k in base_fields:
            if finite(sums.get(k)): recomputed[k]+=sums[k]
            task_values[k].append(sums[k] if task_complete[k] else None)
        derived_complete=all(task_complete[k] for k in input_fields)
        task_values['input_tokens_including_cache_derived'].append(sum(sums[k] for k in input_fields) if derived_complete else None)
        comparison_fields=base_fields+('input_tokens_including_cache',)
        reported_values={**report,'input_tokens_including_cache':report.get('input_tokens_including_cache')}
        recomputed_values={**sums,'input_tokens_including_cache':sum(sums[k] for k in input_fields) if all(task_complete[k] for k in input_fields) else None}
        diffs={k:{'reported':reported_values.get(k),'recomputed':recomputed_values.get(k),'status':'match' if finite(reported_values.get(k)) and finite(recomputed_values.get(k)) and reported_values.get(k)==recomputed_values.get(k) else 'partial_or_mismatch'} for k in comparison_fields}
        if any(v['status']!='match' for v in diffs.values()): validation['numeric_total_mismatch_or_missing']+=1
        req_equal+=eq; rows.append({'task_id':tid,'call_count':cc,'calls_length':len(calls),'call_number_validation':{'count':len(nums),'unique':len(set(validnums)),'nonint_or_missing':sum(type(n) is not int for n in nums)},'source_missing_usage_count':x.get('missing_usage_count'),'calls_usage_missing_count':miss_usage,'usage_field_missing_counts':dict(field_counts),'numeric_totals':report,'recomputed_observed_subtotal':dict(sums),'numeric_total_comparison':diffs,'request_time_equal_count_valid':eq,'source':rel(p)})
    summary={'task_count_with_file':sum(r.get('status')!='missing' for r in rows),'missing_task_count':sum(r.get('status')=='missing' for r in rows),'call_count_sum':sum(r.get('call_count') or 0 for r in rows),'calls_length_sum':sum(r.get('calls_length') or 0 for r in rows),'source_missing_usage_count_sum':source_missing,'missing_usage_count_sum':source_missing,'calls_usage_missing_count_sum':usage_missing,'usage_field_missing_counts':dict(field_missing),'request_equal_count_valid':req_equal,'reported_numeric_totals':dict(report_totals),'recomputed_observed_subtotal':dict(recomputed),'request_level_field_stats':{k:stats(v) for k,v in request_values.items()},'task_level_field_stats':{k:stats(v) for k,v in task_values.items()},'validation_counts':dict(validation),'status':'PASS' if not errors and not validation and source_missing==0 else 'PARTIAL','errors':errors}
    return rows,summary

def gpt_manifest_check(meta,traj):
    p=meta/'website_demo'/'gpt-5.6'/'manifest.json'
    if not p.is_file():return {'status':'missing'}
    x=json.loads(p.read_text()); mismatch=[]; checked=0
    for row in x.get('tasks',[]):
        tid=str(row.get('task_id')).zfill(3); q=traj/'website_demo'/'gpt-5.6'/'tasks'/tid/'result.txt'
        if not q.is_file():mismatch.append({'task_id':tid,'kind':'missing_result'});continue
        checked+=1
        if sha(q)[1]!=row.get('result_sha256'):mismatch.append({'task_id':tid,'kind':'result_hash_mismatch'})
    return {'status':'checked','manifest_tasks':len(x.get('tasks',[])),'included_tasks':x.get('included_tasks'),'missing_tasks':x.get('missing_tasks'),'result_hash_checked':checked,'mismatch':mismatch,'source_run_values':sorted(set(r.get('source_run') for r in x.get('tasks',[])))}

def verify_inventory(root,inventory):
    inv=json.loads(inventory.read_text())
    if inv.get('requested_revision')!=REVISION: raise ValueError('inventory revision mismatch')
    reg={x['path']:x for x in inv.get('files',[])}; actual={str(p.relative_to(root)):p for p in root.rglob('*') if p.is_file()}
    errors=[]
    for path in sorted(set(actual)|set(reg)):
        if path not in actual: errors.append({'path':path,'kind':'registered_missing'})
        elif path not in reg: errors.append({'path':path,'kind':'unregistered_actual'})
        else:
            size,digest=sha(actual[path])
            if (size,digest)!=(reg[path].get('bytes'),reg[path].get('sha256')):errors.append({'path':path,'kind':'hash_mismatch'})
    if errors: raise ValueError('inventory completeness/hash verification failed: '+json.dumps(errors[:3]))
    return inv,actual

def run(trajectory_root,meta_root,tasks_root,inventory,output):
    if output.exists(): raise ValueError('output directory exists; refusing overwrite')
    inv,all_actual=verify_inventory(trajectory_root,inventory); task_rows,task_errors=load_tasks(tasks_root); task_map={x['task_key']:x for x in task_rows}
    v2_per=PROJECT/'reports'/'analysis'/'OSWORLD-task-behavior-v2'/'per_trajectory.jsonl'
    v2_unknown_transitions=None
    if v2_per.is_file():
        v2_unknown_transitions=0
        with v2_per.open() as v2_stream:
            for line in v2_stream:
                old_row=json.loads(line)
                v2_unknown_transitions += sum(n for k,n in old_row.get('native_sequence',{}).get('transition_counts',{}).items() if 'unknown' in k)
    task_cache=tasks_root/'.cache'/'huggingface'/'trees'/f'{TASK_COMMIT}.json'
    task_version_evidence={'status':'local_cache_evidence' if task_cache.is_file() else 'unknown','path':rel(task_cache) if task_cache.is_file() else None,'expected_revision':TASK_COMMIT,'sha256':sha(task_cache)[1] if task_cache.is_file() else None,'historical_execution_binding':'unknown'}
    models=[]; records=[]; data_files=[]
    web=trajectory_root/'website_demo'
    for md in sorted(p for p in web.iterdir() if p.is_dir() and p.name!='.cache'):
        models.append(md.name)
        for td in sorted((md/'tasks').iterdir()):
            if td.is_dir() and (td/'traj.jsonl').is_file():
                row=analyze_task(td,trajectory_root); row.update({'model':md.name,'task_label':task_map.get(td.name,{}).get('labels',['unknown']),'task_semantics_available':td.name in task_map,'source_trajectory_version_binding':'unknown'}); records.append(row)
                for f in sorted(td.iterdir()):
                    if f.is_file(): data_files.append(f)
    usage_rows,usage=api_summary(meta_root,[f'{i:03d}' for i in range(1,109)]); gpt=gpt_manifest_check(meta_root,trajectory_root)
    output.mkdir(parents=True); (output/'task_semantics.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in task_rows)); (output/'per_trajectory.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in records))
    statuses=Counter(r['analysis_status'] for r in records); model_counts=Counter(r['model'] for r in records); task_counts=Counter(r['task_key'] for r in records); static=Counter(); native=Counter(); labels=Counter(); static_by_model=defaultdict(Counter); native_by_model=defaultdict(Counter); anomalies=Counter(); static_lengths=defaultdict(list); native_lengths=defaultdict(list); native_denominators=defaultdict(Counter)
    for r in records:
        static.update(r['static_category_counts']); native.update(r['native_action_category_counts']); labels.update(r['task_label']); static_by_model[r['model']].update(r['static_category_counts']); native_by_model[r['model']].update(r['native_action_category_counts']); anomalies.update(r['step_num']); static_lengths[r['model']].append(r['supported_static_call_count']); native_denominators[r['model']]['total_records']+=1; native_denominators[r['model']][r['native_representation_status']]+=1
        if r['native_representation_status']=='applicable': native_lengths[r['model']].append(r['native_action_record_count'])
    label_model={m:{} for m in models}
    for m in models:
        for lab in sorted({x for r in records if r['model']==m for x in r['task_label']}):
            rs=[r for r in records if r['model']==m and lab in r['task_label']]; vals=[r['supported_static_call_count'] for r in rs]; label_model[m][lab]={'task_records':len(rs),'independent_task_keys':len({r['task_key'] for r in rs}),'supported_n':sum(v>0 for v in vals),'missing_n':sum(v==0 for v in vals),'static_call_stats':stats(vals)}
    per_task=[]
    for m in models:
        for tid in sorted({r['task_key'] for r in records if r['model']==m}):
            rs=[r for r in records if r['model']==m and r['task_key']==tid]; per_task.append({'model':m,'task_key':tid,'n':len(rs),'supported_static_call_stats':stats([r['supported_static_call_count'] for r in rs]),'native_action_stats':stats([r['native_action_record_count'] for r in rs])})
    summary={'schema':'osworld-task-behavior-v3','inputs':{'trajectory_revision':REVISION,'task_revision_or_cache_commit':TASK_COMMIT,'models':models,'trajectory_count':len(records),'task_semantics_count':len(task_rows),'task_errors':task_errors,'inventory_summary':inv.get('summary',{}),'inventory_completeness':'PASS','task_revision_binding':'inventory/cache evidence only; historical execution binding unknown','task_version_evidence':task_version_evidence},'task_semantics':{'rows':len(task_rows),'errors':task_errors},'coverage':{'trajectory_count':len(records),'model_counts':dict(model_counts),'missing_task_by_model':{m:sorted(set(task_counts)-{r['task_key'] for r in records if r['model']==m}) for m in models},'task_counts':dict(task_counts),'analysis_status_counts':dict(statuses),'step_anomalies':dict(anomalies),'static_category_counts':dict(sorted(static.items())),'native_action_category_counts':dict(sorted(native.items())),'task_label_counts':dict(labels),'labels_overlap':True,'per_model_static_category_counts':{m:dict(sorted(v.items())) for m,v in static_by_model.items()},'per_model_native_action_category_counts':{m:dict(sorted(v.items())) for m,v in native_by_model.items()},'per_model_static_length_stats':{m:stats(v) for m,v in static_lengths.items()},'per_model_native_action_stats':{m:stats(v) for m,v in native_lengths.items()},'per_model_native_action_denominators':{m:dict(v) for m,v in native_denominators.items()},'label_by_model':label_model,'per_model_task_points':per_task},'minimax_api_usage':{'summary':usage,'per_task':usage_rows,'position_pairing_with_trajectory':False,'api_logs_downloaded':False},'gpt56_manifest':gpt,'rules':{'task_class':'prefer exactly matching id or TaskNNN class; ambiguous classes are not guessed','task_labels':'word-boundary/phrase rules over statically extracted fields; labels overlap; related_apps is declaration','native_action':'structured action/input fields are counted separately from command source','command_action':'command is parsed once; raw_response is never parsed','static_vs_execution':'AST occurrences, conservative static calls, native saved records, and actual execution are separate','unknown_boundary':'unknown/unsupported action breaks sequence','time':'not analyzed'},'per_task':per_task,'pooled_static_category_counts':dict(sorted(static.items())),'pooled_native_action_category_counts':dict(sorted(native.items())),'limitations':['task numeric keys are dataset-local; historical version binding unknown','native records and command source are saved representations, not proof of execution','screenshot native actions and command sleep placeholders are kept separate','no CPU/memory/I/O/hotspot/action duration evidence','MiniMax usage does not generalize to other models']}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    corrections={'v2_to_v3':{'group1':{'old_formula':'input_tokens + output_tokens + cache_read_input_tokens + cache_creation_input_tokens','new_formula':'input_tokens + cache_read_input_tokens + cache_creation_input_tokens','request_level_derived_stats':usage['request_level_field_stats'].get('input_tokens_including_cache_derived'),'task_level_derived_stats':usage['task_level_field_stats'].get('input_tokens_including_cache_derived'),'old_v2_request_level_derived_stats':json.loads((PROJECT/'reports/analysis/OSWORLD-task-behavior-v2/summary.json').read_text())['minimax_api_usage']['summary']['request_level_field_stats'].get('input_tokens_including_cache_derived') if (PROJECT/'reports/analysis/OSWORLD-task-behavior-v2/summary.json').is_file() else None,'comparison_field':'numeric_totals.input_tokens_including_cache'},'group2':{'old':'native unknown was a literal category in sequence tokens','fixed':'unknown native records are retained in counts but become None boundaries; invalid JSON breaks both sequences','native_unknown_action_count':sum(r['native_unknown_action_count'] for r in records),'old_v2_unknown_transition_total':v2_unknown_transitions,'new_v3_unknown_transition_total':sum(n for r in records for k,n in r['native_sequence']['transition_counts'].items() if 'unknown' in k)},'group3':{'old':'not_applicable native representations and usage missingness could appear as zero','fixed':'native denominators and usage source/call/field missingness are separate; valid distributions exclude not_applicable','native_denominators':{m:dict(v) for m,v in native_denominators.items()},'usage_missingness':{'source_missing_usage_count':usage['source_missing_usage_count_sum'],'calls_usage_missing':usage['calls_usage_missing_count_sum'],'usage_field_missing':usage['usage_field_missing_counts']}},'group4':{'old':'constant task revision and partial actual-file check were insufficient evidence','fixed':'local HF tree cache evidence is consumed and registered; actual and registered inventory sets plus hashes are checked','task_version_evidence':task_version_evidence,'analysis_code':['scripts/osworld_task_behavior.py','scripts/osworld_minimax_behavior.py']}},'unchanged':['task semantics extraction remains static and non-executing','task labels remain overlapping source-based labels','static/native saved records are not proof of actual GUI execution','no resource, duration, billing or model-ranking claims'],'remaining_unknown':['historical runtime task-version binding','upstream authentication beyond local cache/inventory evidence','actual execution count and timing']}
    (output/'corrections.md').write_text('# v2→v3 修正记录\n\n'+json.dumps(corrections,ensure_ascii=False,indent=2)+'\n')
    md=['# OSWorld 任务语义与行为联合分析 v3','','固定 trajectory revision 与本地 task/cache 登记，离线覆盖 '+str(len(records))+' 条 model×task 轨迹、'+str(len(models))+' 个模型、'+str(len(task_rows))+' 个任务定义；未执行 task/action。','','## 有限观察',f"- 模型覆盖：{dict(sorted(model_counts.items()))}；分析状态：{dict(sorted(statuses.items()))}。GPT-5.6 缺 048，历史版本绑定 unknown。",f"- 静态源码类别总数：{dict(sorted(static.items()))}；原生结构化动作总数：{dict(sorted(native.items()))}。两层不相加，避免同一记录重复计数。",'- Claude/GPT 的 dict action 现在保留原生 action/input 与 command 源码；screenshot 与 command 中的占位 sleep 分列。字符串模型的原生动作表示为 not_applicable，不作为零值分布；unknown 只作边界。', '- 任务 080 按 id/类名选择 Task080；标签采用边界/短语规则，VP9、hard-coded 等词不会仅因包含 code 而标成 development_terminal。',f"- MiniMax API usage：{usage['call_count_sum']} calls；来源 missing_usage_count={usage['source_missing_usage_count_sum']}，calls 中 usage 缺失={usage['calls_usage_missing_count_sum']}，字段缺失={usage['usage_field_missing_counts']}，有效时间相等={usage['request_equal_count_valid']}；输入+缓存派生值使用三项输入字段，汇总核验状态={usage['status']}。不与轨迹按位置配对。",'','## 证据边界','原生动作记录、command 的保守 AST 调用和实际执行次数是不同指标；静态分析不证明 GUI 执行。related_apps 是任务声明，不是实际应用调用。没有动作耗时、CPU、内存、I/O、热点或模型优劣证据。GPT-5.6 的 107 个 result hash 单独核验，source_run 混合。','','## 后续用途','可用于按任务语义、模型格式覆盖和保存动作结构选择有限的后续本地测量线索，不构成执行授权或资源结论。','', '[summary.json](summary.json) · [task_semantics.jsonl](task_semantics.jsonl) · [per_trajectory.jsonl](per_trajectory.jsonl) · [corrections.md](corrections.md) · [manifest.json](manifest.json)']
    (output/'summary.md').write_text('\n'.join(md)+'\n')
    files=[inventory,task_cache,v2_per]+[tasks_root/f'task_{i:03d}.py' for i in range(1,109)]+data_files+sorted((meta_root/'website_demo'/'MiniMax-M3'/'tasks').glob('*/api_usage.json'))+sorted((meta_root/'website_demo'/'MiniMax-M3'/'tasks').glob('*/analysis_task_*.md'))+[meta_root/'website_demo'/'gpt-5.6'/'manifest.json']
    unique=[]; seen=set()
    for f in files:
        if f.is_file() and f not in seen: unique.append(f); seen.add(f)
    ins=[{'path':rel(f),'bytes':sha(f)[0],'sha256':sha(f)[1]} for f in unique]
    code_files=[Path(__file__).resolve(),Path(behavior.__file__).resolve()]
    codes=[{'path':rel(f),'bytes':sha(f)[0],'sha256':sha(f)[1]} for f in code_files]
    outs=[{'path':n,'bytes':sha(output/n)[0],'sha256':sha(output/n)[1]} for n in ('task_semantics.jsonl','per_trajectory.jsonl','summary.json','summary.md','corrections.md')]
    (output/'manifest.json').write_text(json.dumps({'schema':'osworld-task-behavior-manifest.v3','inputs':ins,'analysis_code':codes,'outputs':outs,'manifest_self_hash_excluded':True},ensure_ascii=False,indent=2)+'\n')
    return summary

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--trajectory-root',type=Path,required=True); ap.add_argument('--metadata-root',type=Path,required=True); ap.add_argument('--tasks-root',type=Path,required=True); ap.add_argument('--inventory',type=Path,required=True); ap.add_argument('--output-dir',type=Path,required=True); a=ap.parse_args()
    try:s=run(a.trajectory_root,a.metadata_root,a.tasks_root,a.inventory,a.output_dir); print(json.dumps({'status':'PASS','trajectories':s['inputs']['trajectory_count'],'tasks':s['inputs']['task_semantics_count'],'models':len(s['inputs']['models'])},ensure_ascii=False)); return 0
    except Exception as e: print(json.dumps({'status':'FAIL','error':type(e).__name__+': '+str(e)},ensure_ascii=False)); return 2
if __name__=='__main__':raise SystemExit(main())
