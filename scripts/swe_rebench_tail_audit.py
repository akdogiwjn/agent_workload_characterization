"""Document all remaining complex submit-tail requests without executing text."""
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from swe_rebench_review_v3 import OUT,record
from swe_rebench_protocol_details import call_operation


def main():
    if (OUT/'findings.md').exists():raise FileExistsError('refusing to overwrite findings')
    checked={}
    def read(entry):
        data=Path(entry['path']).read_bytes()
        if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('source changed')
        checked[entry['path']]={k:entry[k] for k in ('path','bytes','sha256')};return data
    main_manifest=json.loads(read(record(OUT/'manifest.json')))
    detail_manifest=json.loads(read(record(OUT/'review-manifest.json')))
    for manifest in (main_manifest,detail_manifest):
        for e in manifest['outputs']+manifest['analysis_code_and_tests']:read(e)
    originals={r['trajectory_id']:r for r in map(json.loads,(OUT/'per_trajectory.jsonl').open())}
    summary=json.loads((OUT/'reviewed_summary.json').read_text())
    grouped=defaultdict(dict)
    for item in summary['unexplained_requests']:
        grouped[originals[item['trajectory_id']]['source']['path']][item['trajectory_id']]=item['event_index']
    input_index={e['path']:e for e in main_manifest['inputs']}
    evidence=[]
    for path,wanted in grouped.items():
        read(input_index[path])
        with gzip.open(path,'rt') as stream:
            for line_no,line in enumerate(stream,1):
                obj=json.loads(line)
                if obj['trajectory_id'] not in wanted:continue
                position=wanted[obj['trajectory_id']];event=obj['events'][position]
                command=event['input']['command'];last_call=max(i for i,e in enumerate(obj['events']) if e['type']=='tool_call')
                assert command.rstrip().endswith('submit') and obj['evaluation']['agent_exit_status']=='submit' and position==last_call
                classification=call_operation(event)
                evidence.append({'trajectory_id':obj['trajectory_id'],'shard':path,'line':line_no,
                                 'event_index':position,'call_id':event['tool_call_id'],'tool_as_saved':event['tool'],
                                 'command_sha256':hashlib.sha256(command.encode()).hexdigest(),
                                 'last_saved_tool_request':True,'command_text_ends_with_submit':True,
                                 'source_agent_exit_status':'submit','source_evaluation_status':obj['evaluation']['status'],
                                 'classification_reason':classification['reason'],
                                 'separate_execution_return_present':False,'execution_proven':False})
    assert len(evidence)==11
    totals=summary['protocol_details']
    assert totals['candidate_id_named_in_extraction_error']==1875 and totals['submit_source_branch_without_return']==7201
    assert 589061+1875+7201+11==598148 and 589061+27059+860==616980
    (OUT/'submit_tail_audit.json').write_text(json.dumps({'records':evidence,
      'rule':'last saved request + text ends with submit + source exit field submit; no assertion of shell branch execution, tool alias or returned result'},ensure_ascii=False,indent=2)+'\n')
    from matplotlib import pyplot as plt
    fig,ax=plt.subplots(figsize=(10,3.6),layout='constrained')
    for label,values,color in [('unique-ID response association',[589061,589061],'#457b9d'),
                               ('submit source/request tail',[7212,0],'#e9c46a'),
                               ('extraction candidates / errors',[1875,860],'#e76f51'),
                               ('explicit no-invocation reports',[0,27059],'#a8a8a8')]:
        left=getattr(ax,'_audit_left',[0,0]);ax.barh([1,0],values,left=left,label=label,color=color)
        ax._audit_left=[left[i]+values[i] for i in range(2)]
    ax.set_yticks([1,0],['tool_call events','tool_result events']);ax.set_xlim(0,665000)
    ax.text(600000,1,'598,148',va='center');ax.text(619000,0,'616,980',va='center')
    ax.set_xlabel('Saved records');ax.set_title('Event accounting: records do not imply execution count')
    ax.legend(loc='lower center',bbox_to_anchor=(.5,1.15),ncol=2,fontsize=8)
    fig.savefig(OUT/'protocol_accounting.png',dpi=160);plt.close(fig)
    md=['# SWE-rebench 第4项复核结果','',
        '已完成当前选定85分片、9,435条轨迹、111任务、17个participant的离线复核。原始文件齐全且压缩/解压SHA256匹配，本轮不需要补下载。来源是第三方normalized语料，不称官方原始执行日志。','',
        '## 调用/返回差额已经逐类核清','',
        '| 保存记录 | 分解 |','|---|---|',
        '| 598,148个tool_call事件 | 589,061个有唯一ID结果 + 1,875个提取错误中的候选 + 7,201个已识别提交分支请求 + 11个复杂提交末尾请求 |',
        '| 616,980个tool_result事件 | 589,061个唯一ID关联结果 + 27,059个明确未调用报告 + 860个多调用提取错误 |','',
        '两行相差18,832，来自保存协议的不同事件类型，不能据此推断漏下载或实际执行了更多工具。提取错误内候选ID与对应tool_call逐个匹配，未把一个harness错误复制成多个工具执行返回。','',
        '![保存事件分解](protocol_accounting.png)','',
        '11个复杂末尾请求也已逐项核查：10个包含heredoc/命令替换等有限分类器未支持的语法，1个保存的工具名为b_terminal；它们都是各自轨迹最后的工具请求、命令文本以submit结束、来源agent_exit_status=submit。仍不把这些事实提升为已解析的shell执行、工具别名修复或正常终止证明。[11条证据](submit_tail_audit.json)。','',
        '## 行为、结果与保存质量','',
        '- 通用shell操作沿用已冻结的[操作分析v3](../PUBLIC-TRACE-OPERATIONS-v3/summary.md)，逐轨迹对齐；另单列589,061个有ID结果的请求切片，保留Unknown/Partial与组合命令边界。',
        '- Junie的555条轨迹保存31,449个agent_step，与来源usage.tool_calls逐条一致。它不是零工具行为；摘要记录与标准调用分别统计。',
        '- 来源评测：4,751已解决、4,683失败、1跳过；评测字段内部一致。失败任务不等于分析未完成，提交退出也不等于修复成功。',
        '- 来源明确不发布patch；4,092条工具结果截断、32条缓存内容省略，均核对源manifest。duration_ms同时见于模型消息和工具结果，elapsed_ms也见于agent_step；这些字段不能充当本项目CPU、内存或工具独占耗时。','',
        '当前约定范围可以收尾。记录字段不足仍按来源边界保留；未来扩充其他语料、原始日志或开展本地资源测量是独立任务，不作为本轮未完成事项。','',
        '[完整分析与规则](summary.md) · [逐participant协议](participant_protocol_details.csv) · [操作证据切片](operations_by_evidence_scope.csv) · [评测/退出交叉表](evaluation_exit_cross_tab.csv) · [校验](final-verification.json)','',
        '12项定向测试通过；初步分析、协议明细与末尾核查分别冻结manifest。旧raw、v1/v2及PUBLIC-TRACE-OPERATIONS-v3保持不变，未执行保存代码、Agent、模型或benchmark。']
    (OUT/'findings.md').write_text('\n'.join(md)+'\n')
    verification={'status':'PASS_WITH_SOURCE_LIMITS','shards':85,'trajectories':9435,'tasks':111,'participants':17,
                  'call_events':598148,'result_events':616980,'unique_id_pairs':589061,
                  'extraction_candidates':1875,'explicit_no_invocation_reports':27059,'batch_extraction_errors':860,
                  'parsed_submit_source_requests':7201,'complex_submit_tail_requests_audited':11,
                  'call_and_return_differences_fully_accounted':True,'new_position_based_execution_pairs':0,
                  'junie_saved_steps':31449,'directed_tests_passed':12,'old_raw_and_reports_preserved':True,
                  'dataset_agent_model_command_or_benchmark_executed':False}
    (OUT/'final-verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
    (OUT/'tail-manifest.json').write_text(json.dumps({'schema':'swe-rebench-tail-audit-manifest-v3','inputs':list(checked.values()),
         'analysis_code':[record(Path(__file__))],'outputs':[record(OUT/n) for n in ('submit_tail_audit.json','findings.md','protocol_accounting.png','final-verification.json')]},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(verification,ensure_ascii=False))


if __name__=='__main__':main()
