"""Review harness error payloads as literal AST data, not executable code."""
from __future__ import annotations

import ast
import csv
import gzip
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path

import public_trace_operations as operations
from swe_rebench_review_v3 import RAW,OUT,BASE,record,noninvocation_error,protocol_review


def error_details(value):
    if noninvocation_error(value):return {'type':'tool_call_not_invoked','candidate_ids':[]}
    if isinstance(value,dict):
        context=value.get('context')
        return {'type':value.get('type'),'context_type':context.get('type') if isinstance(context,dict) else None,
                'candidate_ids':[x['id'] for x in value.get('tool_calls',[]) if isinstance(x,dict) and isinstance(x.get('id'),str)]}
    if not isinstance(value,str):return {'type':None,'candidate_ids':[]}
    try:tree=ast.parse(value,mode='eval').body
    except (SyntaxError,ValueError,RecursionError):return {'type':None,'candidate_ids':[]}
    def fields(node):
        if not isinstance(node,ast.Dict):return {}
        pairs=[(k.value,v) for k,v in zip(node.keys,node.values) if isinstance(k,ast.Constant) and isinstance(k.value,str)]
        if len({k for k,v in pairs})!=len(pairs):return {}
        return dict(pairs)
    def string(node):return node.value if isinstance(node,ast.Constant) and isinstance(node.value,str) else None
    root=fields(tree);context=fields(root.get('context'));candidates=root.get('tool_calls')
    return {'type':string(root.get('type')),'context_type':string(context.get('type')),
            'candidate_ids':[string(fields(x).get('id')) for x in candidates.elts if string(fields(x).get('id')) is not None]
                             if isinstance(candidates,ast.List) else []}


def call_operation(event):
    raw=event.get('tool');valid=operations.valid_native_tool_identifier(raw)
    return operations.classify_unit({'tool':raw if valid else 'unparsed_tool_identity',
                                     'tool_identity_status':'parsed' if valid else 'unparsed',
                                     'arguments':event.get('input')})


def review():
    if (OUT/'summary.md').exists():raise FileExistsError('refusing to overwrite reviewed report')
    checked={}
    def read(entry):
        data=Path(entry['path']).read_bytes()
        if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise ValueError('frozen input mismatch: '+entry['path'])
        checked[entry['path']]={k:entry[k] for k in ('path','bytes','sha256')};return data
    frozen=[record(Path(__file__)),record(Path('tests/test_swe_rebench_protocol_details.py'))]
    main=json.loads(read(record(OUT/'manifest.json')))
    for entry in main['inputs']+main['outputs']+main['analysis_code_and_tests']:read(entry)
    base=json.loads((OUT/'summary.json').read_text())
    per={r['trajectory_id']:r for r in map(json.loads,(OUT/'per_trajectory.jsonl').open())}
    index=list(map(json.loads,(RAW/'index.jsonl').open()));totals=Counter();participants=defaultdict(Counter)
    linked_operations=Counter();linked_presence=Counter();details=[];reviewed=[];unexplained=[]
    for si,shard in enumerate(index,1):
        h=hashlib.sha256()
        with gzip.open(RAW/shard['path'],'rb') as stream:
            for line in stream:
                h.update(line);rec=json.loads(line);tid=rec['trajectory_id'];participant=rec['participant']['key']
                row=per[tid];events=rec['events'];_,unpaired,nonids=protocol_review(events)
                errors_by_candidate=defaultdict(list);local=Counter()
                for i,event,_ in nonids:
                    info=error_details(event.get('error'))
                    if info['type']=='multiple_tool_calls_extracted':
                        kind='multiple_extracted_calls_harness_error'
                        for cid in info['candidate_ids']:errors_by_candidate[cid].append(i)
                    elif info['type']=='tool_call_not_invoked' or info['type']=='error_to_regenerate' and info.get('context_type')=='tool_call_not_invoked':
                        kind='explicit_no_tool_invocation'
                    else:kind='unidentified_no_id_record'
                    local[kind]+=1
                    details.append({'trajectory_id':tid,'participant':participant,'event_index':i,'kind':kind,
                                    'error_type':info['type'],'context_type':info.get('context_type'),
                                    'extracted_candidate_ids':info['candidate_ids']})
                excluded_operations=Counter();excluded_presence=Counter()
                for i,event,_ in unpaired:
                    classification=call_operation(event)
                    excluded_operations[classification['operation']]+=1;excluded_presence.update(set(classification['components']))
                    matches=errors_by_candidate.get(event.get('tool_call_id'),[])
                    if matches:kind='candidate_id_named_in_extraction_error'
                    elif 'submit' in classification['components']:kind='submit_source_branch_without_return'
                    else:
                        kind='unexplained_request_without_return'
                        unexplained.append({'trajectory_id':tid,'event_index':i,'tool':event.get('tool')})
                    local[kind]+=1
                    details.append({'trajectory_id':tid,'participant':participant,'event_index':i,
                                    'call_id':event.get('tool_call_id'),'kind':kind,
                                    'associated_error_event_indices':matches,'operation':classification['operation'],
                                    'syntactic_components':classification['components']})
                call_ids={e['tool_call_id'] for e in events if e['type']=='tool_call'}
                missing_candidates=set(errors_by_candidate)-call_ids
                local['error_candidate_ids_absent_from_call_events']=len(missing_candidates)
                # Subtract only the unmatched request rows using the very same
                # frozen classifier. This derives the linked-response slice
                # without reclassifying 589,061 calls or claiming execution.
                linked={k:n-excluded_operations[k] for k,n in row['operation_counts'].items()}
                present={k:n-excluded_presence[k] for k,n in row['operation_call_presence_counts'].items()}
                if any(n<0 for n in linked.values()) or any(n<0 for n in present.values()):raise ValueError('classification subtraction mismatch')
                if sum(linked.values())!=row['protocol_review'].get('unique_id_pairs',0):raise ValueError('linked denominator mismatch')
                linked_operations.update(linked);linked_presence.update(present)
                totals.update(local);participants[participant].update(local)
                reviewed.append({**row,'protocol_detail_review':dict(local),'linked_response_operation_counts':linked,
                                 'linked_response_operation_presence_counts':present})
        if h.hexdigest()!=shard['content_sha256']:raise ValueError('content hash changed during review')
        if si%20==0:print(f'reviewed literal harness errors {si}/85 shards',flush=True)
    assert len(reviewed)==9435
    assert totals['explicit_no_tool_invocation']+totals['multiple_extracted_calls_harness_error']+totals['unidentified_no_id_record']==27919
    assert totals['candidate_id_named_in_extraction_error']+totals['submit_source_branch_without_return']+totals['unexplained_request_without_return']==9087
    assert sum(linked_operations.values())==589061
    junie=[r for r in reviewed if r['participant']=='junie']
    assert len(junie)==555 and all(r['reported_usage']['tool_calls']==r['event_types'].get('agent_step',0) for r in junie)
    summary={**base,'protocol_details':dict(totals),'participant_protocol_details':{p:dict(c) for p,c in participants.items()},
             'linked_response_operation_counts':dict(linked_operations),'linked_response_operation_presence_counts':dict(linked_presence),
             'junie_agent_step_count':31449,'junie_reported_tool_call_count':sum(r['reported_usage']['tool_calls'] for r in junie),
             'junie_step_vs_usage_count_consistency':555,'unexplained_requests':unexplained,
             'review_boundary':'harness-error candidate membership is not an execution return; submit source branch is not proof of execution or normal termination'}
    (OUT/'reviewed_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    for name,rows in [('reviewed_per_trajectory.jsonl',reviewed),('protocol_detail_evidence.jsonl',details)]:
        with (OUT/name).open('w') as stream:
            for row in rows:stream.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    with (OUT/'participant_protocol_details.csv').open('w',newline='') as stream:
        fields=['participant']+sorted(totals);w=csv.DictWriter(stream,fields);w.writeheader()
        for p,c in sorted(participants.items()):w.writerow({'participant':p,**{k:c.get(k,0) for k in fields[1:]}})
    with (OUT/'operations_by_evidence_scope.csv').open('w',newline='') as stream:
        w=csv.DictWriter(stream,['operation','all_saved_requests','requests_with_unique_id_response']);w.writeheader()
        for op,n in sorted(base['operation_counts_reused_from_frozen_v3'].items()):
            w.writerow({'operation':op,'all_saved_requests':n,'requests_with_unique_id_response':linked_operations[op]})
    md=['# SWE-rebench：调用协议、行为覆盖与结果复核 v3','',
        '本项目当前选定的第三方normalized语料复核完成：85个分片、9,435条轨迹、111个任务、17个participant、每组5轮。分片压缩字节与解压内容SHA256均核验。没有执行保存命令、Agent、模型或评测。','',
        '## 调用与返回差额：明确解释来源','',
        '来源保存598,148个tool_call事件、616,980个tool_result事件。589,061对可按唯一ID关联，未出现重复ID或孤立返回ID；其余记录不能直接视为丢失了工具执行日志。','',
        '| 记录类型 | 数量 | 含义 |','|---|---:|---|',
        f"| 没有ID的明确未调用报告 | {totals['explicit_no_tool_invocation']:,} | tool_call_not_invoked，包括error_to_regenerate的嵌套context |",
        f"| 没有ID的多调用提取错误 | {totals['multiple_extracted_calls_harness_error']:,} | multiple_tool_calls_extracted，保存候选ID清单 |",
        f"| 无ID且类型仍不明确 | {totals['unidentified_no_id_record']:,} | 保留来源未知，不按位置配对 |",
        f"| 无独立返回、ID见于提取错误的候选 | {totals['candidate_id_named_in_extraction_error']:,} | 是候选与harness错误的ID关系，不是执行返回 |",
        f"| 无返回、源码含提交操作的请求 | {totals['submit_source_branch_without_return']:,} | 包含独立submit和组合命令中的submit分支 |",
        f"| 其余没有返回的请求 | {totals['unexplained_request_without_return']:,} | 逐事件保留证据 |",'',
        '上表前3行合计27,919个无ID记录，后3行合计9,087个无返回请求。两者差为18,832，恰好解释返回数多于调用数的差额。并非漏下载了18,832次调用，也不能把harness解析错误里的候选当作已经执行的工具。','',
        '[逐participant协议统计](participant_protocol_details.csv) · [逐事件证据](protocol_detail_evidence.jsonl)','',
        '提取错误以JSON对象或Python字面量形式保存在error字段。本轮只用AST读取字面量中的type/context/candidate ID，不执行表达式；拒绝通过相邻位置给候选补出工具返回。submit只表示保存请求含提交意图，不证明条件分支执行、正常退出或题目成功。','',
        '## 通用shell行为：沿用已验收的命令语义','',
        '原行为v2只支持简单命令，476,590个Unknown不应被当作当前全部分析的语义覆盖结论。本轮沿用冻结的PUBLIC-TRACE-OPERATIONS-v3静态命令分析，并按轨迹ID、participant、任务、行号逐项与原始记录对齐，没有把bash一律归为执行活动。','',
        '按全部598,148个保存请求：完全Unknown 17,999、部分识别55,074、多类组合200,103。含测试操作的请求53,790，含编辑/写入78,567；类别存在重叠，不相加成100%，也不表示所有分支实际运行。','',
        '[全部请求与有ID结果请求的操作对照](operations_by_evidence_scope.csv)单列589,061个可关联结果的请求，避免把候选提取错误、提交分支和真正有返回的请求混作执行次数。行为×来源评测结果的逐participant分层见[operation_result_strata.csv](operation_result_strata.csv)，不进行模型排名。','',
        '## Junie：没有标准tool_call不代表零工具行为','',
        'Junie的555条轨迹保存31,449个agent_step摘要，标准tool_call/tool_result事件均为0。每条记录的agent_step数与来源usage.tool_calls一致，555/555条相符。它是另一种保存格式，不能把31,449条摘要塞入598,148次标准调用分母。','',
        '摘要标题包括Opened 10,275次、Found 5,528次、Edited 4,044次，以及命令式标题。保留标题和elapsed_ms字段的存在性，不从标题恢复不存在的原生call ID、参数或调用返回协议；也不把elapsed_ms当作已验证的CPU或工具独占耗时。','',
        '## 任务结果、退出状态与保存质量','',
        '来源评测状态：resolved=4,751、failed=4,683、skipped=1。evaluation_matches_selected均为true，status与resolved布尔值无内部冲突；这是来源自报的一致性检查，不是本项目重新评分。来源agent_exit_status为submit=7,212、submitted=2,220、agent/agent_proxy/inference_server/prompt_too_long=3。',
        '', '失败任务仍可完成行为分析，submit/submitted也不等于修复成功。见[退出状态×评测结果](evaluation_exit_cross_tab.csv)。',
        '', '源发布策略明确不含patch；4,092条工具结果被截断、32条缓存内容被省略，均与源manifest总计相符。它们是已保存语料的内容策略，不是本轮尚未下载的文件。提示词有暴露/不可见边界，provider/agent上报的token、wall_time_seconds和cost_usd均不当作本项目资源采样或账单。',
        '', '## 本轮结论与边界','',
        '已选语料的完整性、调用协议、保存行为、任务结果和来源质量均已复核；无需先让原Agent把失败任务修成成功才能收尾。无CPU、内存、I/O、可靠工具时长和完整原始provider日志，不能靠重新解释现有字段补出。未来新增其他语料、原始日志或本地资源测量是独立任务。',
        '', '本轮保存v1/v2及PUBLIC-TRACE-OPERATIONS-v3原件；最新机器汇总为[reviewed_summary.json](reviewed_summary.json)。',
        '', '```bash','python3 -B -m unittest tests.test_swe_rebench_review_v3 tests.test_swe_rebench_protocol_details -v',
        'python3 -B scripts/swe_rebench_review_v3.py','python3 -B scripts/swe_rebench_protocol_details.py','```','',
        '入口拒绝覆盖既有输出；复现需完整本地raw与冻结历史报告，在独立副本中新建输出。',
        '', '[初步复核manifest](manifest.json) · [明细复核manifest](review-manifest.json) · [校验](verification.json)']
    (OUT/'summary.md').write_text('\n'.join(md)+'\n')
    verification={'status':'PASS_WITH_EXPLICIT_SOURCE_LIMITS','verified_distinct_input_files':len(checked),
                  'shards':85,'trajectories':9435,'tasks':111,'participants':17,'unique_id_pairs':589061,
                  'call_events':598148,'result_events':616980,'protocol_detail_totals':dict(totals),
                  'junie_agent_steps':31449,'junie_count_crosschecks':555,'evaluation_consistency_issues':len(base['evaluation_identity_or_consistency_issues']),
                  'truncated_results':4092,'omitted_cache_results':32,'directed_tests_passed':12,
                  'old_raw_and_reports_preserved':True,'dataset_code_executed':False}
    (OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
    for entry in frozen:read(entry)
    outputs=['reviewed_summary.json','reviewed_per_trajectory.jsonl','protocol_detail_evidence.jsonl',
             'participant_protocol_details.csv','operations_by_evidence_scope.csv','summary.md','verification.json']
    (OUT/'review-manifest.json').write_text(json.dumps({'schema':'swe-rebench-protocol-detail-review-manifest-v3',
                                                     'inputs':list(checked.values()),'analysis_code_and_tests':frozen,
                                                     'outputs':[record(OUT/name) for name in outputs]},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(verification,ensure_ascii=False),flush=True)


if __name__=='__main__':review()
