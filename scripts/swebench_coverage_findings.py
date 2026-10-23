"""Render and independently check the frozen SWE-bench coverage/result analysis."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from swebench_coverage_results import SONAR, file_record, verified_read


def main():
    out = Path('reports/analysis/SWEBENCH-COVERAGE-RESULTS-v1')
    if (out / 'findings.md').exists():
        raise FileExistsError('refusing to overwrite findings')
    checked = {}

    def check(entry):
        data = verified_read(entry)
        checked[entry['path']] = {k: entry[k] for k in ('path', 'bytes', 'sha256')}
        return data

    main_manifest = out / 'manifest.json'
    manifest = json.loads(check(file_record(main_manifest)))
    for entry in manifest['inputs'] + manifest['outputs'] + manifest['analysis_code_and_tests']:
        check(entry)
    # Check every historical report output, including ones not needed by the join.
    historical_outputs = 0
    for folder in ('PUBLIC-TRACE-OPERATIONS-v3', 'SWEBENCH-subset-behavior-v1'):
        path = Path('reports/analysis') / folder / 'manifest.json'
        previous = json.loads(check(file_record(path)))
        for entry in previous['outputs']:
            check(entry)
            historical_outputs += 1
    acquisition_path = Path('data/catalog/public_trace_acquisition/SWEBENCH-GAP-20261023/manifest.json')
    acquisition = json.loads(check(file_record(acquisition_path)))
    for entry in acquisition['files']:
        check(entry)
        check(entry['headers'])
    plan = json.loads(check(acquisition['plan']))
    old_plan = json.loads(check(plan['old_plan']))

    summary = json.loads((out / 'summary.json').read_text())
    sources = json.loads((out / 'evaluation_sources.json').read_text())
    objects = [json.loads(line) for line in (out / 'object_links.jsonl').open()]
    instances = [json.loads(line) for line in (out / 'per_instance.jsonl').open()]
    selected = [json.loads(line) for line in (out / 'subset90_links.jsonl').open()]
    negatives = [json.loads(line) for line in (out / 'negative_coverage_review.jsonl').open()]
    old_coverage = json.loads(Path('reports/analysis/PUBLIC-TRACE-OPERATIONS-v3/coverage.json').read_text())['objects']
    sonar_plan = {Path(x['key']).stem: x['bytes'] for x in old_plan['p2_new_coverage']['items']
                  if x['split'] + '/' + x['group'] == SONAR}
    sonar_saved = {Path(x['path']).stem: x['bytes'] for x in old_coverage if x['group'] == SONAR}
    sonar_saved.update({x['task']: x['bytes'] for x in acquisition['files']})
    assert sonar_saved == sonar_plan and len(sonar_saved) == 2294
    assert len(objects) == summary['objects'] == 20023
    assert len({r['path'] for r in objects}) == len(objects)
    assert len(instances) == len({(r['group'], r['task']) for r in instances}) == 19514
    assert len(selected) == 90 and len({(r['group'], r['task']) for r in selected}) == 90
    assert len(negatives) == 7367 and all(r['same_as_frozen_v3'] for r in negatives)
    assert sum(summary['coverage_status_counts'].values()) == len(objects)
    assert sum(summary['evaluation_status_instance_counts'].values()) == len(instances)
    assert sum(e['available'] for e in sources.values()) == 39
    assert all(not e['problems'] for e in sources.values())
    duplicate_entries = sum(f['duplicate_entries'] for e in sources.values() for f in e['fields'].values())
    # No absent outcome or non-resolved publication label becomes False.
    assert all(r['evaluation']['reported_resolved'] is None for r in instances
               if r['evaluation']['status'] not in ('listed_resolved', 'listed_unresolved'))
    assert not any(len(r['objects']) > 1 for r in instances)

    noninstance = Counter(r['group'] for r in objects if r['evaluation']['status'] == 'not_an_instance_identifier')
    no_behavior = sum(not r['behavior_rows'] for r in instances)
    new_results = Counter(r['evaluation']['status'] for r in objects if r['acquisition_cohort'] == 'new_sonar_gap')
    native_cross = Counter()
    for row in instances:
        for native in row['native_records']:
            label_source = 'last_saved_transition' if native['format'] == 'moatless-transitions' else 'info.exit_status'
            label = native.get('last_saved_transition') if label_source == 'last_saved_transition' else native['termination']['value']
            native_cross[(row['group'], label_source, '<missing>' if label is None else str(label), row['evaluation']['status'])] += 1

    def csv_write(name, fields, rows):
        with (out / name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fields)
            writer.writeheader()
            writer.writerows(rows)

    csv_write('behavior_strata.csv', ['group', 'unit_kind', 'saved_result_stratum', 'n', 'min', 'q1', 'median', 'q3', 'iqr', 'max'],
              [{**{k: r[k] for k in ('group', 'unit_kind', 'saved_result_stratum')}, **r['saved_units_per_instance']}
               for r in summary['behavior_strata']])
    csv_write('native_result_cross_tabs.csv', ['group', 'native_field', 'native_value', 'evaluation_status', 'instances'],
              [dict(zip(['group', 'native_field', 'native_value', 'evaluation_status', 'instances'], (*k, v)))
               for k, v in sorted(native_cross.items())])
    reasons = Counter((r['group'], r['status'], r['reason_code']) for r in negatives)
    csv_write('negative_coverage_by_group.csv', ['group', 'status', 'reason_code', 'objects'],
              [dict(zip(['group', 'status', 'reason_code', 'objects'], (*k, v))) for k, v in sorted(reasons.items())])

    labels = {'listed_resolved': '明确列为 resolved', 'listed_other_saved_fields': '列其他保存字段',
              'not_listed_in_saved_fields': '未列入保存字段', 'evaluation_file_missing': '缺评价文件'}
    short = {'20240620_sweagent_claude3.5sonnet': 'SWE-agent', 'lite/20240617_moatless_gpt4o': 'Moatless', SONAR: 'Sonar'}
    md = ['# SWE-bench 本轮发现与缺口', '', '[完整范围与规则](summary.md) · [逐组覆盖/评价](coverage_results.csv) · [校验](verification.json)', '',
          '## 本轮实际补齐了什么', '',
          f"新增147个Sonar文件，39,377,587字节；与原固定下载清单逐任务及字节核对，累计2,294/2,294。新增文件评价标签：{dict(new_results)}。",
          '', '登记对象19,876→20,023；跨submission去重的任务ID为2,506→2,594，新增88个。物理对象包含轨迹、上下文、配套产物和alternate视图，不能都称为完整轨迹。', '',
          '| 物理对象覆盖分类 | 数量 |', '|---|---:|']
    md += [f'| {k} | {v:,} |' for k, v in summary['coverage_status_counts'].items()]
    md += ['', '原7,367个非动作对象全部按冻结v3协议重解析，分类/原因/单位数均未改变。这是覆盖复核，没有增加这些文件的语义支持；本轮新增的147个文件均提取到保存动作。', '',
           '## 评价关联：分母与未知项', '',
           '41组中39组已有同split/submission的公开results.json，均来自本地固定Git索引；本轮实际新增的是关联分析。另2组缺失：`20250615_agentless_mindlink`、`lite/20251009_MAYA_claude-sonnet-4-5-20250929`。这只描述该索引的登记范围。', '',
           '按完整原生instance ID精确连接，共19,514个group×instance键。它们不等同于已验证的独立attempt；下表也不构成模型成功率或排名。', '',
           '| 保存评价关系 | group×instance数 |', '|---|---:|']
    md += [f'| {labels.get(k,k)} | {v:,} |' for k, v in summary['evaluation_status_instance_counts'].items()]
    md += ['', '未出现明确unresolved清单成员或冲突标签。8,730个未列入保存字段的键仍未知；其他字段包含generated/applied/with_logs/no_generation/no_logs等阶段标签，不能统一转成失败。`20240402_sweagent_gpt4`的no_generation清单有30项、26个唯一ID，4项重复已登记，连接按成员关系去重，不把重复项计为额外任务。', '',
           f'另有{sum(noninstance.values())}个对象未按原样匹配instance ID：', '', '| 组 | 不匹配对象数 |', '|---|---:|']
    md += [f'| {g} | {v} |' for g,v in sorted(noninstance.items())]
    md += ['', '其中Google组含500个`_alternate`对象及1个README；其余为汇总/配置等文件。不擅自去掉后缀，把不同视图或汇总文件冒充已精确绑定的任务。', '',
           '来源核查：37组metadata的trajs字段与预期S3命名空间字面相符；CodeShell另1组写成Git相对路径`evaluation/verified/.../trajs`，未冒称其S3字段匹配；SWE-Exp及2个缺评价组未取得对应metadata。这不妨碍按目录/ID记录发布清单关系，但不证明字节、patch或attempt一致。来源checked标签仅9组为true，29组false、3组缺失；它不是本项目独立重验。', '',
           '## 三种原生格式的行为与评价分层', '',
           '原90条子集不变，全部追加独立评价关系：SWE-agent 10 resolved/20未列；Moatless 10 resolved/20列其他字段；Sonar 8 resolved/1列其他字段/21未列。全组的描述统计如下：', '',
           '| 组 | 保存单位 | 评价分层 | n | 单位数中位数 | Q1–Q3 |', '|---|---|---|---:|---:|---:|']
    for r in summary['behavior_strata']:
        if r['group'] not in short:
            continue
        d = r['saved_units_per_instance']
        md.append(f"| {short[r['group']]} | {r['unit_kind']} | {labels.get(r['saved_result_stratum'],r['saved_result_stratum'])} | {d['n']} | {d['median']:g} | {d['q1']:g}–{d['q3']:g} |")
    md += ['', f"全41组共{len(summary['behavior_strata'])}个保存单位×评价分层，见[完整CSV](behavior_strata.csv)。其中{no_behavior:,}个group×instance没有已识别行为行，未填成零工具调用。Moatless的transition与另两组的动作/调用分母不同；其他组还包含保存过程节点等单位，不横向比较为工具效率。", '',
           'SWE-agent的500条中，408条写有exit_status=submitted，84条为submitted (exit_cost)，6条exit_cost，2条缺失；仅168个任务列为resolved。Moatless末条transition有274个Finished，其中72个列为resolved、202个只列其他字段；另有2个resolved的末条保存状态分别为Rejected与PlanToCode。由此不能用最后保存状态替代公开评价，也不能反推保存记录完整。', '',
           '[原生状态×评价交叉表](native_result_cross_tabs.csv)保留两类证据；Sonar没有同等原生exit_status字段，仍保留缺失。提交patch存在性与显式submit标记在逐instance中另列，未按末条文本推断正常终止。', '',
           '## 仍未补齐', '',
           '- 6,054个部分/歧义对象和1,313个配套产物仍不能统一恢复成完整业务工具轨迹；逐组原因见[复核表](negative_coverage_by_group.csv)。',
           '- 没有穷尽这41组之外的公开submission；2组缺评价、未列入清单的任务及alternate对象仍有绑定缺口。',
           '- 同一次attempt/同一份patch的精确绑定、无ID工具返回的关联、可靠工具耗时仍缺证据。',
           '- 原始CPU、内存、I/O和业务工具资源成本无法从本轮材料恢复；固定Git索引也不冻结可变S3对象的历史字节。', '',
           '## 复现与完整性', '',
           '复现命令：', '', '```bash',
           'python3 -B -m unittest tests.test_swebench_coverage_results -v',
           'python3 -B scripts/swebench_coverage_results.py --gap-manifest data/catalog/public_trace_acquisition/SWEBENCH-GAP-20261023/manifest.json --output-dir /tmp/SWEBENCH-COVERAGE-RESULTS-reproduce',
           '```', '', '主分析拒绝覆盖已有目录。发现汇总由`scripts/swebench_coverage_findings.py`从冻结产物生成，执行前复核主manifest全部输入/输出、代码/测试、历史报告全部输出，以及新增下载的HTTP头/原始文件。', '',
           '本轮未执行任何保存命令、Agent、模型、patch、benchmark或verifier。旧原始数据、旧报告及原90条选择保留原样。']
    (out / 'findings.md').write_text('\n'.join(md) + '\n')
    verification = {'status': 'PASS', 'verified_distinct_files': len(checked), 'historical_report_outputs_verified': historical_outputs,
                    'sonar_exact_task_and_size_set_matches_frozen_listing': True, 'original_objects':19876,'new_objects':147,
                    'new_acquisition_bytes':39377587,'objects':20023,'group_instance_keys':19514,'non_instance_objects':sum(noninstance.values()),
                    'negative_rechecks_unchanged':7367,'subset_selection_links':90,'evaluation_groups':39,'total_groups':41,
                    'result_field_parse_problems':0,'result_duplicate_entries':duplicate_entries,'instances_without_behavior_rows':no_behavior,
                    'unit_tests_passed':11,'agent_or_benchmark_executed':False}
    (out / 'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
    review = {'schema':'swebench-coverage-findings-manifest-v1', 'inputs':list(checked.values()),
              'analysis_code':[file_record(Path(__file__))], 'outputs':[file_record(out/name) for name in
               ('findings.md','verification.json','behavior_strata.csv','native_result_cross_tabs.csv','negative_coverage_by_group.csv')]}
    (out / 'findings-manifest.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(verification,ensure_ascii=False))


if __name__ == '__main__':
    main()
