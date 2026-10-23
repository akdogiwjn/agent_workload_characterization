"""Static review of H-EPM saved native execution requests, never executing them."""
from __future__ import annotations

import ast
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import toolsandbox_hepm_behavior as v2

ROOT=Path(__file__).resolve().parents[1]
BASE=Path('reports/analysis/TOOLSANDBOX-HEPM-behavior-v2')
OUT=Path('reports/analysis/TOOLSANDBOX-HEPM-behavior-v3')
RAW=Path('data/raw/public/toolsandbox_hepm')/v2.COMMIT/'ToolSandbox/data'


def record(path):
    path=Path(path);size,digest=v2.sha(path)
    try:name=str(path.relative_to(ROOT))
    except ValueError:name=str(path)
    return {'path':name,'bytes':size,'sha256':digest}


def native_request(source,call_id,allowed):
    """Accept only the exact saved wrapper and call-id-specific variable names.

    ast.parse inspects syntax only. No eval, imports, execution, or calls to
    functions appearing in source text. Dictionary values remain AST nodes.
    """
    try:tree=ast.parse(source)
    except (ValueError,SyntaxError,TypeError):return None,'invalid_python_syntax'
    if len(tree.body)!=3 or [type(n) for n in tree.body]!=[ast.Assign,ast.Assign,ast.Expr]:
        return None,'unsupported_request_wrapper'
    params,response,display=tree.body
    def target(node,name):
        return len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id==name
    if not target(params,call_id+'_parameters') or not isinstance(params.value,ast.Dict):
        return None,'parameter_binding_mismatch'
    if not target(response,call_id+'_response') or not isinstance(response.value,ast.Call):
        return None,'response_binding_mismatch'
    invoke=response.value
    if not isinstance(invoke.func,ast.Name) or invoke.func.id not in allowed:
        return None,'native_function_not_allow_listed'
    if invoke.args or len(invoke.keywords)!=1:
        return None,'unsupported_native_arguments'
    kw=invoke.keywords[0]
    if kw.arg is not None or not isinstance(kw.value,ast.Name) or kw.value.id!=call_id+'_parameters':
        return None,'parameter_expansion_mismatch'
    # Restrict the exact print(repr(<id>_response)) wrapper as well. A call in a
    # string, a different variable, or unrelated executable text cannot bind.
    outer=display.value
    if not isinstance(outer,ast.Call) or not isinstance(outer.func,ast.Name) or outer.func.id!='print' or outer.keywords or len(outer.args)!=1:
        return None,'unsupported_result_display'
    inner=outer.args[0]
    if not isinstance(inner,ast.Call) or not isinstance(inner.func,ast.Name) or inner.func.id!='repr' or inner.keywords or len(inner.args)!=1 or not isinstance(inner.args[0],ast.Name) or inner.args[0].id!=call_id+'_response':
        return None,'result_display_binding_mismatch'
    return invoke.func.id,'exact_saved_request_ast'


def request_index(ec):
    result=defaultdict(list)
    for index,row in enumerate(ec.get('_dbs',{}).get('SANDBOX',[])):
        if row.get('sender')=='AGENT' and row.get('recipient')=='EXECUTION_ENVIRONMENT' and isinstance(row.get('openai_tool_call_id'),str):
            result[row['openai_tool_call_id']].append((index,row))
    return dict(result)


def run():
    if OUT.exists():raise FileExistsError(OUT)
    checked={}
    def read(entry):
        path=Path(entry['path']);data=path.read_bytes()
        actual=record(path)
        if (actual['bytes'],actual['sha256'])!=(entry['bytes'],entry['sha256']):raise ValueError('frozen input mismatch: '+str(path))
        checked[entry['path']]={k:entry[k] for k in ('path','bytes','sha256')};return data
    frozen_code=[record(Path(__file__)),record(ROOT/'tests/test_toolsandbox_hepm_review_v3.py')]
    manifest=json.loads(read(record(BASE/'manifest.json')))
    for entry in manifest['inputs']+manifest['analysis_code']:read(entry)
    for entry in manifest['outputs']:read({**entry,'path':str(BASE/entry['path'])})
    originals=list(map(json.loads,(BASE/'per_trajectory.jsonl').open()))
    summary2=json.loads((BASE/'summary.json').read_text())
    native=set(v2.NATIVE_ACTIVITY)
    groups={};calls=[];trajectories=[];termination=[];issues=[];recoveries=[];clean_checks=0
    global_counters=Counter();old_unknown=old_activity_only=0
    for old in originals:
        group,scenario=old['group_directory'],old['scenario']
        folder=RAW/group/'trajectories'/scenario
        conv=json.loads((folder/'conversation.json').read_text());ec=json.loads((folder/'execution_context.json').read_text())
        index=request_index(ec);sbx=v2.sandbox_index(ec)
        allow=set(ec['tool_allow_list'])
        results={}
        for mi,msg in enumerate(conv):
            if msg.get('role')=='tool':
                cid=msg['tool_call_id']
                if cid in results:raise ValueError('duplicate result ID')
                results[cid]=(mi,msg)
        identity=Counter();activity=Counter();resolution=Counter();sequence=[];localcalls=[]
        for mi,msg in enumerate(conv):
            if msg.get('role')!='assistant':continue
            for ci,call in enumerate(msg.get('tool_calls') or []):
                cid=call['id'];called=call['function']['name'];entries=index.get(cid,[])
                if len(entries)!=1:raise ValueError('missing/duplicate native request ID')
                sb_index,request=entries[0]
                if request['openai_function_name']!=called:raise ValueError('request function alias mismatch')
                canonical,method=native_request(request['content'],cid,allow)
                if canonical is None:
                    issues.append({'group':group,'scenario':scenario,'id':cid,'reason':method})
                    raise ValueError('unsupported native request: '+method)
                if canonical not in native:raise ValueError('activity classification missing')
                if called in native and called!=canonical:raise ValueError('native call/request name conflict')
                previous=sbx['by_id'][cid]['tool_trace_name']
                if previous is not None:
                    if previous!=canonical:raise ValueError('clean tool_trace/request name conflict')
                    clean_checks+=1
                result_mi,result=results[cid]
                exception=sbx['by_id'][cid]['has_exception']
                error=v2.ERROR_RE.match(result.get('content') or '')
                # Determine what v2 could establish, without treating an
                # expected milestone trace or stale exception trace as actual.
                dbs=set((result.get('tool_details') or {}).get('database_update') or {}) & set(v2.DB_ACTIVITY)
                old_native=called if called in native else previous
                old_method='native_name' if called in native else 'sandbox_tool_trace' if previous else 'database_namespace_activity' if len(dbs)==1 else 'unresolved_scrambled'
                if called not in native and old_native is None:
                    old_unknown+=old_method=='unresolved_scrambled';old_activity_only+=old_method=='database_namespace_activity'
                    recoveries.append({'group':group,'scenario':scenario,'call_id':cid,'called_name':called,
                                       'native_name':canonical,'previous_basis':old_method,'error_class':error.group(1) if error else None,
                                       'sandbox_request_row':sb_index})
                rec={'group':group,'scenario':scenario,'call_id':cid,'message_index':mi,'call_index':ci,
                     'called_name':called,'native_name':canonical,'activity':v2.NATIVE_ACTIVITY[canonical],
                     'identity_basis':method,'sandbox_request_row':sb_index,
                     'sandbox_message_index':request['sandbox_message_index'],'result_message_index':result_mi,
                     'tool_execution_error':bool(error),'error_class':error.group(1) if error else None,
                     'sandbox_exception':exception,'clean_tool_trace_agrees':previous is not None,
                     'previous_identity_basis':old_method,'native_name_previously_unknown':old_native is None,
                     'source_execution_context':str(folder/'execution_context.json')}
                calls.append(rec);localcalls.append(rec);identity[canonical]+=1;activity[rec['activity']]+=1
                resolution[method]+=1;sequence.append(rec['activity'])
                global_counters['tool_calls']+=1;global_counters['tool_errors']+=bool(error)
                if bool(error)!=exception:raise ValueError('exception sources disagree')
        assert len(localcalls)==old['pairing']['tool_call_entries']
        # V2 classified 2 database-only calls to activities; v3 establishes
        # their exact native identities as well as the 24 formerly Unknown.
        row={**old,'native_identity_counts':dict(identity),'activity_call_counts':dict(activity),
             'activity_sequence':sequence,'activity_transitions':v2.transitions(sequence),
             'call_resolution_counts':dict(resolution),'all_agent_calls_native_request_bound':True,
             'previous_resolution_counts':old['call_resolution_counts']}
        trajectories.append(row)
        # Count user end requests separately; never add them to agent calls.
        user_ends=[]
        for i,sandbox_row in enumerate(ec['_dbs']['SANDBOX']):
            if sandbox_row.get('sender')!='USER' or sandbox_row.get('recipient')!='EXECUTION_ENVIRONMENT':continue
            source=sandbox_row.get('content')
            try:tree=ast.parse(source)
            except (ValueError,SyntaxError,TypeError):continue
            for node in tree.body:
                if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='end_conversation':user_ends.append(i)
        end={'group':group,'scenario':scenario,'saved_final_conversation_active':sbx['final_conversation_active'],
             'user_end_request_rows':user_ends,'user_end_result_traces':sbx['end_conversation_tool_trace_rows'],
             'agent_end_calls':identity.get('end_conversation',0),'last_conversation_role':old['last_message_role'],
             'agent_termination_reason':None,'saved_result_summary':old['result_summary_row']}
        termination.append(end)
    if len(calls)!=2021 or len(trajectories)!=414 or old_unknown!=24 or old_activity_only!=2:raise ValueError('baseline scope/recovery count mismatch')
    assert sum(t['tool_result_error_count'] for t in originals)==global_counters['tool_errors']==304
    for group in sorted({r['group'] for r in calls}):
        gcalls=[c for c in calls if c['group']==group];gtraj=[r for r in trajectories if r['group_directory']==group]
        ends=[r for r in termination if r['group']==group]
        activities=Counter(c['activity'] for c in gcalls);identities=Counter(c['native_name'] for c in gcalls)
        groups[group]={'trajectories':len(gtraj),'calls':len(gcalls),'errors':sum(c['tool_execution_error'] for c in gcalls),
                       'native_name_counts':dict(identities),'activity_counts':dict(activities),
                       'activity_stats_all_trajectories':{a:v2.stats([r['activity_call_counts'].get(a,0) for r in gtraj]) for a in sorted(activities)},
                       'calls_per_trajectory':v2.stats([r['pairing']['tool_call_entries'] for r in gtraj]),
                       'saved_final_active_counts':dict(Counter(r['saved_final_conversation_active'] for r in ends)),
                       'user_end_request_trajectories':sum(bool(r['user_end_request_rows']) for r in ends),
                       'user_end_result_trajectories':sum(bool(r['user_end_result_traces']) for r in ends),
                       'agent_end_calls':sum(r['agent_end_calls'] for r in ends),
                       'same_activity_transitions':sum(r['activity_transitions']['same_tool_transitions'] for r in gtraj),
                       'cross_activity_transitions':sum(r['activity_transitions']['cross_tool_transitions'] for r in gtraj),
                       'unknown_activity_boundaries':sum(r['activity_transitions']['boundary_adjacent_pairs'] for r in gtraj)}
    source_metadata={}
    for group in groups:
        rs=json.loads((RAW/group/'result_summary.json').read_text())
        source_metadata[group]={k:v for k,v in rs.items() if k!='per_scenario_results'}
    summary={'schema':'toolsandbox-hepm-native-request-review-v3','trajectories':414,'calls':2021,
             'paired_returns':2021,'tool_errors':304,'supported_request_patterns':2021,
             'clean_tool_trace_cross_checks':clean_checks,'former_unknown_activity_calls_recovered':old_unknown,
             'former_activity_only_native_names_recovered':old_activity_only,'remaining_unknown_native_identities':0,
             'groups':groups,'source_run_metadata':source_metadata,
             'user_end_trajectories':sum(bool(r['user_end_request_rows']) for r in termination),
             'user_end_result_trajectories':sum(bool(r['user_end_result_traces']) for r in termination),
             'user_end_request_without_saved_result_trajectories':sum(bool(r['user_end_request_rows']) and not r['user_end_result_traces'] for r in termination),
             'no_user_end_request_trajectories':sum(not r['user_end_request_rows'] for r in termination),
             'observed_agent_native_tools':len({c['native_name'] for c in calls}),
             'saved_active_trajectories':sum(r['saved_final_conversation_active']=='True' for r in termination),
             'agent_end_calls':sum(r['agent_end_calls'] for r in termination),
             'agent_termination_reason':'not recorded; saved inactive state and user end event are separate facts',
             'comparison_boundary':'two source versions, both local changes; descriptive only, no graph causal inference',
             'source_code_executed':False,'agent_model_benchmark_or_verifier_executed':False,
             'old_raw_and_v1_v2_preserved':True}
    assert summary['user_end_trajectories']==406 and summary['user_end_result_trajectories']==402
    assert summary['user_end_request_without_saved_result_trajectories']==4 and summary['no_user_end_request_trajectories']==8
    OUT.mkdir(parents=True)
    for name,rows in [('call_records.jsonl',calls),('per_trajectory.jsonl',trajectories),('termination_records.jsonl',termination)]:
        with (OUT/name).open('w') as stream:
            for row in rows:stream.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    with (OUT/'recovered_tool_identities.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,list(recoveries[0]));writer.writeheader();writer.writerows(recoveries)
    with (OUT/'activity_counts.csv').open('w',newline='') as stream:
        w=csv.DictWriter(stream,['group','activity','calls','all_trajectories','median_per_trajectory','iqr']);w.writeheader()
        for group,g in groups.items():
            for a,n in sorted(g['activity_counts'].items()):
                s=g['activity_stats_all_trajectories'][a];w.writerow({'group':group,'activity':a,'calls':n,'all_trajectories':207,'median_per_trajectory':s['median'],'iqr':s['iqr']})
    md=['# H-EPM / ToolSandbox：原生工具身份与终止证据复核 v3','',
        '当前两组414条轨迹的离线行为复核完成。无须以任务成功为前提，也不将源材料未记录的字段当作尚未执行的分析任务。仅读取冻结JSON并静态解析保存的请求，不执行任何来源代码、Agent、工具或模型。','',
        '## 本轮补齐','',
        '- 全部2,021次Agent调用与2,021次返回继续按调用ID关联，错误304次，数量不变。',
        '- SANDBOX请求行保存了原生函数名。严格核对发送方/接收方、call ID、扰动名称、allow list和三条语句的AST结构，2,021次调用全部可绑定到原生工具身份。没有运行保存的Python。',
        f'- 与无异常返回中的有效tool_trace交叉核对{clean_checks}次，名称一致；异常行的陈旧tool_trace继续排除。',
        '- 原24次未知调用的原生身份全部补齐；另外2次原来只有数据库活动分类的调用也取得确切工具名。剩余未知原生身份0。',
        '', '[26条身份补全证据](recovered_tool_identities.csv) · [逐调用记录](call_records.jsonl) · [活动统计](activity_counts.csv)', '',
        '## 两组统计（描述性）','', '| 组 | 轨迹 | Agent调用 | 工具错误 | 活动序列未知边界 |','|---|---:|---:|---:|---:|']
    for group,g in groups.items():md.append(f"| {'graph_False' if 'graph_False' in group else 'graph_True'} | {g['trajectories']} | {g['calls']} | {g['errors']} | {g['unknown_activity_boundaries']} |")
    md += ['', '调用数量、调用返回配对和来源similarity字段不变；活动与原生工具分布按补全身份重算。每轨迹分布以各组全部207条为分母，含该活动的零值；与调用条目总量分母分开。','',
           '## 终止记录：哪些是事实，哪些没有记录','',
           f'- {summary["user_end_trajectories"]}条保存了用户模拟器向执行环境发出的end_conversation请求，其中{summary["user_end_result_trajectories"]}条还保存了相应tool_trace返回，且末态conversation_active=false。用户侧请求及返回不算Agent业务调用。',
           f'- 另外{summary["saved_active_trajectories"]}条末态conversation_active=true：4条已保存用户end请求但没有保存对应执行返回，8条没有保存用户end请求。它只说明记录中的请求/返回及末态，不能自动称为任务失败或异常终止。',
           '- Agent侧end_conversation调用为0。源材料未记录完整Agent终止原因，因此不推断正常结束、轮数上限或超时。上述12条也不被当作尚未分析。',
           '', '[逐轨迹终止证据](termination_records.jsonl)。milestone_similarity、minefield_similarity、similarity继续按来源值保存；不把分数阈值擅自转换成任务成功。','',
           '## 两组运行来源与剩余材料边界','',
           '共享207个场景键、各109个基础场景。来源result_summary保存的split=test、seed=42、ratio=0.8；两组git_sha分别为`4f7fffb17fe1fdfd969350b5ab081fcfec130585 + local changes`和`75cf0c9bb12a87f60c95fb1407e1ab431869a42f + local changes`。完整字段见summary.json的source_run_metadata。',
           '', 'graph开关来自目录名和README，源码版本不同且都有未冻结的本地修改，不能把组间差异归因为单一graph开关。无法从这些材料恢复受控实验或完整的历史源码/环境身份。',
           '', '没有完整时间戳、usage/token、CPU、内存、I/O、工具耗时和费用数据；本轮不伪造或通过重跑回填这些字段。当前已选公开材料的工具行为与证据复核可收尾，未来扩充其他轨迹或开展本地测量属于另一个任务。', '',
           '## 校验与复现','',
           '先复核v2 manifest的全部输入/输出/分析代码及本轮代码/测试，再静态分析；末尾再次核验输入。旧raw、v1/v2及其manifest保持不变。',
           '', '```bash','python3 -B -m unittest tests.test_toolsandbox_hepm_review_v3 -v',
           'python3 -B scripts/toolsandbox_hepm_review_v3.py','```','',
           '入口拒绝覆盖已存在的v3目录。复现需要完整本机raw与冻结v2产物，请在独立副本中使用新输出目录。', '',
           '[summary.json](summary.json) · [manifest](manifest.json) · [v2历史报告](../TOOLSANDBOX-HEPM-behavior-v2/summary.md)']
    (OUT/'summary.md').write_text('\n'.join(md)+'\n')
    for entry in list(checked.values())+frozen_code:read(entry)
    verification={'status':'PASS_WITH_SOURCE_LIMITS','frozen_files_verified':len(checked),
                  'trajectories':414,'calls_and_returns':2021,'native_requests_bound':2021,
                  'tool_errors_preserved':304,'formerly_unknown_calls_recovered':24,'activity_only_names_recovered':2,
                  'remaining_unknown_native_names':0,'user_end_trajectories':summary['user_end_trajectories'],
                  'user_end_result_trajectories':summary['user_end_result_trajectories'],
                  'user_end_request_without_saved_result':4,'no_user_end_request':8,
                  'saved_active_trajectories':summary['saved_active_trajectories'],'agent_end_calls':0,
                  'clean_trace_agreements':clean_checks,'old_outputs_preserved':True,'dataset_code_executed':False}
    (OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
    (OUT/'manifest.json').write_text(json.dumps({'schema':'toolsandbox-hepm-review-v3-manifest','inputs':list(checked.values()),
                                              'analysis_code_and_tests':frozen_code,
                                              'outputs':[record(p) for p in sorted(OUT.iterdir()) if p.is_file()]},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(verification,ensure_ascii=False))


if __name__=='__main__':run()
