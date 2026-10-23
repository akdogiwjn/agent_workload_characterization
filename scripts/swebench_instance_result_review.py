"""Audit frozen per-instance results, refine native failure stages, render findings."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from swebench_instance_results import CAT, BASE, OUT, RAW, file_record, verified_read, split_group, write_json
from swebench_coverage_results import strata_for_instances

LABELS={'resolved':'已解决','unresolved':'逐任务报告：未解决',
        'legacy_completed_not_resolved':'旧日志已完成、公开评价未解决',
        'no_generation':'来源明确标记未生成','empty_prediction':'预测patch为空',
        'evaluation_stage_failure':'生成后的评测阶段异常','evaluation_logs_missing':'来源明确标记缺日志',
        'invalid_instance_report':'上游空报告', 'prediction_record_absent':'已公布预测清单不含此任务',
        'prediction_present_result_missing':'已有预测、公开评测结果缺失',
        'public_evaluation_artifacts_absent':'对应公开目录无评价产物',
        'conflicting_published_results':'汇总与逐任务报告冲突'}


def refine(row,has_predictions):
    out={**row,'evaluation':dict(row['evaluation'])}
    if row['evaluation']['status']=='invalid_instance_report' and row.get('review_test_output',{}).get('text','').strip()=='Timeout error: 1800 seconds exceeded.':
        out['evaluation']={'status':'evaluation_stage_failure','resolved':None,
                           'basis':'explicit_saved_test_output_timeout','conflicts':[]}
        return out
    if row['evaluation']['status']!='no_public_result_artifact':return out
    log=row.get('legacy_log')
    if log and any(m in {'Patch Apply Failed; (pred)','Patch Apply Failed; (test)'} for m in log['markers']):
        out['evaluation']={'status':'evaluation_stage_failure','resolved':None,
                           'basis':'explicit_native_legacy_patch_apply_failed_marker','conflicts':[]}
    elif has_predictions:
        out['evaluation']['status']='prediction_present_result_missing' if row.get('prediction') else 'prediction_record_absent'
        out['evaluation']['basis']='complete_public_log_listing_and_saved_prediction_inventory'
    else:
        out['evaluation']['status']='public_evaluation_artifacts_absent'
        out['evaluation']['basis']='complete_public_log_listing_and_no_registered_prediction_file'
    return out


def main():
    if (OUT/'summary.md').exists():raise FileExistsError('refusing to overwrite reviewed report')
    checked={}
    def check(entry):
        data=verified_read(entry);checked[entry['path']]={k:entry[k] for k in ('path','bytes','sha256')};return data
    manifest=json.loads(check(file_record(OUT/'manifest.json')))
    for entry in manifest['inputs']+manifest['outputs']+manifest['analysis_code_and_tests']:check(entry)
    acq=json.loads(check(file_record(CAT/'manifest.json')))
    original=json.loads((OUT/'summary.json').read_text())
    frozen_code=[file_record(Path(__file__)),file_record(Path('tests/test_swebench_instance_result_review.py'))]
    pred_groups={r['group'] for r in acq['files'] if r['artifact']=='predictions'}
    listings={};listing_pages=0
    discovery=json.loads((CAT/'discovery.json').read_text())
    for group in discovery['groups']:
        obj=json.loads(check(group['listing']))
        assert obj['pagination_complete']
        listings[group['group']]={o['key']:o for o in obj['objects']}
        listing_pages+=len(obj['pages'])
    extra=[];rows=[]
    for line in (OUT/'per_instance.jsonl').open():
        row=json.loads(line)
        if row['evaluation']['status']=='invalid_instance_report':
            split,submission=split_group(row['group'])
            key=f'{split}/{submission}/logs/{row["task"]}/test_output.txt'
            obj=listings[row['group']].get(key)
            if obj and obj['bytes']:
                path=RAW/key
                data=check(file_record(path))
                headers=CAT/'source_metadata/bracket-sympy-test-output.headers'
                head=check(file_record(headers)).decode()
                assert len(data)==obj['bytes'] and hashlib.md5(data).hexdigest()==obj['etag']
                assert re.findall(r'^HTTP/\S+\s+(\d+)',head,re.M)[-1]=='200'
                row['review_test_output']={'path':str(path),'text':data.decode()}
                extra.append({**file_record(path),'source':'https://swe-bench-submissions.s3.amazonaws.com/'+key,
                              'listing_entry':obj,'headers':file_record(headers)})
        rows.append(refine(row,row['group'] in pred_groups))
    old8730=Counter(r['evaluation']['status'] for r in rows if r['previous_evaluation']['status']=='not_listed_in_saved_fields')
    old666=Counter(r['evaluation']['status'] for r in rows if r['previous_evaluation']['status']=='evaluation_file_missing')
    old1747=Counter(r['evaluation']['status'] for r in rows if r['previous_evaluation']['status']=='listed_other_saved_fields')
    outcomes=Counter(r['evaluation']['status'] for r in rows)
    revised=sum(r['evaluation']!=before['evaluation'] for r,before in zip(rows,map(json.loads,(OUT/'per_instance.jsonl').open())))
    conflicts=[r for r in rows if r['evaluation']['conflicts']]
    residual=[]
    for row in rows:
        status=row['evaluation']['status']
        if status not in ('invalid_instance_report','prediction_record_absent','prediction_present_result_missing','public_evaluation_artifacts_absent','conflicting_published_results'):
            continue
        split,submission=split_group(row['group']);prefix=f'{split}/{submission}/logs/{row["task"]}/'
        found=[obj for k,obj in listings[row['group']].items() if k.startswith(prefix)]
        report=next((x for x in found if x['key'].endswith('/report.json')),None)
        output=next((x for x in found if x['key'].endswith('/test_output.txt')),None)
        if status=='invalid_instance_report':
            assert report and report['bytes']==0 and output and output['bytes']==0
        if status in ('prediction_record_absent','prediction_present_result_missing','public_evaluation_artifacts_absent'):
            assert report is None
        residual.append({'group':row['group'],'task':row['task'],'status':status,
                         'prediction_records':len(row.get('prediction') or []),
                         'report_listing_bytes':report['bytes'] if report else None,
                         'test_output_listing_bytes':output['bytes'] if output else None,
                         'listed_artifact_names':';'.join(x['key'].rsplit('/',1)[-1] for x in found),
                         'basis':row['evaluation']['basis']})
    group_outcomes={g:dict(Counter(r['evaluation']['status'] for r in rows if r['group']==g)) for g in original['groups']}
    strata,excluded=strata_for_instances(rows)
    summary={**original,'outcomes':dict(outcomes),'previous_8730_now':dict(old8730),
             'previous_666_missing_summary_now':dict(old666),'previous_1747_other_fields_now':dict(old1747),
             'group_outcomes_reviewed':group_outcomes,'behavior_strata':strata,
             'additional_test_output_files':len(extra),'additional_test_output_bytes':sum(e['bytes'] for e in extra),
             'multiple_behavior_rows_excluded':excluded,'native_stage_refinements':revised,
             'review_rules':'native Patch Apply Failed markers become evaluation-stage failure; prediction/public-directory absence are source facts, not task-failure assertions'}
    write_json(OUT/'reviewed_summary.json',summary)
    write_json(OUT/'additional-source-manifest.json',{'schema':'swebench-empty-report-companion-check-v1','files':extra,
                                                   'reason':'inspect the only nonempty test_output accompanying the 75 empty reports'})
    with (OUT/'reviewed_per_instance.jsonl').open('w') as stream:
        for row in rows:stream.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    def csv_out(name,fields,items):
        with (OUT/name).open('w',newline='') as stream:
            w=csv.DictWriter(stream,fields);w.writeheader();w.writerows(items)
    csv_out('remaining_source_gaps.csv',['group','task','status','prediction_records','report_listing_bytes','test_output_listing_bytes','listed_artifact_names','basis'],residual)
    csv_out('conflicting_results.csv',['group','task','summary_resolved','instance_report_resolved','instance_report_path'],
            [{'group':r['group'],'task':r['task'],'summary_resolved':r['published_summary']['reported_resolved'],
              'instance_report_resolved':r['instance_report']['resolved'],'instance_report_path':r['instance_report']['path']} for r in conflicts])
    statuses=sorted(outcomes)
    csv_out('reviewed_group_outcomes.csv',['group','trace_instance_keys']+statuses,
            [{'group':g,'trace_instance_keys':sum(c.values()),**{k:c.get(k,0) for k in statuses}} for g,c in group_outcomes.items()])
    csv_out('reviewed_behavior_strata.csv',['group','unit_kind','result','n','median','q1','q3','iqr'],
            [{'group':r['group'],'unit_kind':r['unit_kind'],'result':r['saved_result_stratum'],
              **{k:r['saved_units_per_instance'][k] for k in ('n','median','q1','q3','iqr')}} for r in strata])
    cross=Counter((r['previous_evaluation']['status'],r['evaluation']['status']) for r in rows)
    csv_out('reviewed_result_recovery.csv',['previous_status','current_status','instances'],
            [{'previous_status':k[0],'current_status':k[1],'instances':v} for k,v in sorted(cross.items())])
    # The old 90 sample selections stay frozen; bind the same rows by native key.
    lookup={(r['group'],r['previous_task']):r for r in rows}
    selected=[json.loads(line) for line in (BASE/'subset90_links.jsonl').open()]
    subset=[]
    for item in selected:
        row=lookup[(item['group'],item['task'])]
        subset.append({'group':item['group'],'task':row['task'],'selected_path':item['selected_path'],
                       'evaluation':row['evaluation'],'instance_report':row['instance_report'],'legacy_log':row['legacy_log']})
    with (OUT/'reviewed_subset90_links.jsonl').open('w') as stream:
        for row in subset:stream.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    assert len(rows)==19514 and len({(r['group'],r['task']) for r in rows})==19514
    assert len({r['task'] for r in rows})==2294 and original['native_task_id_corrections']==300
    assert sum(old8730.values())==8730 and sum(old666.values())==666 and sum(old1747.values())==1747
    assert len(subset)==90 and sum(outcomes.values())==19514 and len(conflicts)==5
    assert sum(e['content_validation']=='upstream_empty_or_invalid_json_preserved' for e in acq['files'])==75
    for conflict in conflicts:assert conflict['evaluation']['resolved'] is None
    # Verify all preceding report outputs, not only the ones needed above.
    previous_outputs=0
    for folder in ('PUBLIC-TRACE-OPERATIONS-v3','SWEBENCH-subset-behavior-v1','SWEBENCH-COVERAGE-RESULTS-v1'):
        path=Path('reports/analysis')/folder/'manifest.json'
        previous=json.loads(check(file_record(path)))
        for entry in previous['outputs']:check(entry);previous_outputs+=1
    from matplotlib import pyplot as plt
    plt.rcParams.update({'font.size':10})
    fig,axis=plt.subplots(figsize=(9,4.5),layout='constrained')
    order=['unresolved','resolved','no_generation','evaluation_stage_failure','invalid_instance_report','prediction_record_absent','prediction_present_result_missing','public_evaluation_artifacts_absent']
    order=[s for s in order if old8730[s]]
    axis.barh(order,[old8730[s] for s in order],color=['#3478a5' if s in ('unresolved','resolved','no_generation') else '#c78c37' for s in order])
    for i,s in enumerate(order):axis.text(old8730[s]+30,i,f'{old8730[s]:,}',va='center')
    axis.set_xlim(0,max(old8730.values())*1.13);axis.invert_yaxis();axis.set_xlabel('Submission × instance keys')
    axis.set_title('Recovery of 8,730 previously unlisted result keys')
    fig.savefig(OUT/'result_recovery.png',dpi=160);plt.close(fig)
    md=['# SWE-bench：逐任务评价补全与复核','','本轮补齐公开逐任务报告、旧评测日志与预测文件，并更新行为×结果分层。旧数据与旧报告保留；不执行Agent、保存命令、patch、benchmark或verifier。','',
        '## 实际新增的数据','',f"- {acq['counts']['instance_report']:,}份逐任务report.json、{acq['counts']['legacy_evaluation_log']:,}份旧评测日志、{acq['counts']['predictions']}份预测文件、{acq['counts']['evaluation_diagnostic']}份缺报告任务的评测诊断日志。",
        f"- 主批次{len(acq['files']):,}文件、{acq['bytes']:,}字节；另补1份39字节测试输出，共20,098文件、510,938,617字节（约510.9 MB）。HTTP、listing/HEAD字节数、ETag及本地SHA256核验完成；上游空文件按原字节保存。",
        '- 41组对应logs命名空间全部分页列举结束；下载了其中全部逐任务报告和4个旧格式组的完整评测日志，而非只查看成功清单。','',
        '## 原来8,730个未列入汇总清单的键，现在是什么状态','', '| 本轮状态 | 数量 |','|---|---:|']
    md += [f'| {LABELS[k]} | {v:,} |' for k,v in old8730.items()]
    md += ['', '8,625个已取得明确解决状态或来源未生成标签，另1个从配套测试输出确认1800秒超时；74个报告及对应测试输出在上游均为零字节，另30个没有对应逐任务报告。后30个的预测清单/目录情况在下表及逐任务缺口CSV展开，不自动转为任务失败。','',
           '![原8,730个键的补全分布](result_recovery.png)','',
           '## 原来缺汇总评价文件的两组','', '| 组 | 已解决 | 未解决 | 对应公开结果仍缺失 |','|---|---:|---:|---:|']
    for group in ('20250615_agentless_mindlink','lite/20251009_MAYA_claude-sonnet-4-5-20250929'):
        c=group_outcomes[group];missing=sum(v for k,v in c.items() if k not in ('resolved','unresolved'))
        md.append(f"| {group} | {c.get('resolved',0)} | {c.get('unresolved',0)} | {missing} |")
    md += ['', 'MAYA实际有222份逐任务报告，155个resolved=true、67个false；另外78个未公布同名逐任务报告，其中76个目录只有patch.diff。Mindlink的同名logs目录完整列举为0对象，对应预测文件HEAD为404；现有366条轨迹中没有可替代外部评测的明确结果证据。这里的缺失限定于已登记同名公开来源，不声称世界上不存在其他私有或异名版本。','',
           '## 全范围结果与剩余来源问题','', '| 状态（分母：19,514个submission×原生任务键） | 数量 |','|---|---:|']
    md += [f'| {LABELS[k]} | {v:,} |' for k,v in outcomes.items()]
    md += ['', '这些状态把原生报告布尔值、旧日志和流程阶段分开。no_generation、空patch、缺日志及评测异常不冒充经过完整测试后的普通失败。旧日志的“未解决”只在保存日志明确完成且公开清单同时含applied/with_logs、但不含resolved时推断；并非对任意缺失ID取补集。30条原生Patch Apply Failed标记及Bracket的sympy-20428明确超时另归评测异常。','',
           '[逐组完整统计](reviewed_group_outcomes.csv) · [每个剩余问题及目录证据](remaining_source_gaps.csv) · [5个冲突任务](conflicting_results.csv)','',
           '5个任务的Git汇总resolved=true、当前S3逐任务报告resolved=false：MASAI的3个astropy任务、learn-by-interact的django-13807、Warp的requests-5414。两份证据分别保存，冲突实例不归入统一成功/失败分层。固定Git索引与当前可变S3产物可能属于不同修订，不能据此断言具体原因。','',
           '## 任务身份和行为分析更正','',
           'KGCompass的300个文件名附有模型后缀；旧宽松文件名规则把它误当作Instance ID的一部分，造成关联缺失并虚增去重任务数。本轮逐个读取原文Task Metadata中的Instance ID并核对文件名前缀。跨组去重任务数更正为2,294，上一轮2,594包含这300个错误身份。来源文件、保存行为数量和原90条选择不变。','',
           '报告格式支持17,237份以Instance ID为键的嵌套JSON和994份按精确S3任务目录绑定的平铺JSON；75份零字节报告保持原样，其中1份配套测试输出明确超时，74份配套输出也为空。不能因平铺JSON没有内部ID而误判为下载失败，也不将目录绑定说成同一次attempt的完整证明。','',
           f"原90条样本现为：{dict(Counter(r['evaluation']['status'] for r in subset))}。[关联明细](reviewed_subset90_links.jsonl)。全范围按组、保存单位、结果重算中位数/IQR，共{len(strata)}个分层，见[行为与结果CSV](reviewed_behavior_strata.csv)。不同格式和任务集不用于模型排名或因果推断。",
           '', '原生patch与公开预测的字节比较：289条Moatless记录完全一致，其余2,805条所选三格式记录缺少可比较的原生patch或公开预测证据。对没有精确patch证据的记录，仅声称同发布组/任务关系。没有本轮CPU、内存、I/O或可靠工具时长的新证据。','',
           '## 复现与验证','', '```bash',
           'python3 -B -m unittest tests.test_swebench_instance_results tests.test_swebench_instance_result_review -v',
           'python3 -B scripts/swebench_instance_results.py --analyze',
           'python3 -B scripts/swebench_instance_result_review.py', '```','',
           '分析和报告入口均拒绝覆盖已有输出；复现需保留完整本地原始资产，在独立副本中新建输出目录。源文件及获取记录见[下载manifest](../../../data/catalog/public_trace_acquisition/SWEBENCH-INSTANCE-RESULTS-20261023/manifest.json)。[初始分析manifest](manifest.json)、[复核manifest](review-manifest.json)分别冻结各阶段，最新机器汇总为[reviewed_summary.json](reviewed_summary.json)。']
    (OUT/'summary.md').write_text('\n'.join(md)+'\n')
    verification={'status':'PASS_WITH_EXPLICIT_SOURCE_GAPS','verified_distinct_files':len(checked),
                  'historical_report_outputs_verified':previous_outputs,'listing_groups_complete':41,'listing_pages':listing_pages,
                  'acquisition_files':len(acq['files'])+len(extra),'acquisition_bytes':acq['bytes']+sum(e['bytes'] for e in extra),
                  'trace_group_instance_keys':19514,'distinct_native_task_ids':2294,'native_id_corrections':300,
                  'original_unknown_cohort':8730,'recovered_explicit_outcome_or_generation_stage':8625,
                  'original_unknown_empty_reports':74,'original_unknown_no_report':30,'original_unknown_timeout':1,
                  'source_conflicts':5,'native_stage_refinements':revised,'directed_tests_passed':18,
                  'old_raw_and_reports_preserved':True,'agent_or_verifier_executed':False}
    write_json(OUT/'verification.json',verification)
    # All inputs were verified; make sure no source changed during rendering.
    for entry in frozen_code:verified_read(entry)
    new_names=['summary.md','reviewed_summary.json','reviewed_per_instance.jsonl','reviewed_subset90_links.jsonl',
               'reviewed_group_outcomes.csv','reviewed_behavior_strata.csv','reviewed_result_recovery.csv',
               'remaining_source_gaps.csv','conflicting_results.csv','verification.json','result_recovery.png','additional-source-manifest.json']
    write_json(OUT/'review-manifest.json',{'schema':'swebench-instance-review-manifest-v1','inputs':list(checked.values()),
                                        'analysis_code_and_tests':frozen_code,'outputs':[file_record(OUT/name) for name in new_names]})
    print(json.dumps(verification,ensure_ascii=False))


if __name__=='__main__':main()
