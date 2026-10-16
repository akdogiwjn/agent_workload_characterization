#!/usr/bin/env python3
"""Offline public-trace operation and toolkit census. No recorded code is run.

All registered local SWE-bench objects are inventoried. Only explicit structured
actions/calls and Moatless transitions are interpreted; prose is not tool evidence.
Existing OSWorld/H-EPM/macro results remain source-separated and immutable.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
from agent_workload_characterization.analyzers.public_operations import (
    LABELS, SHELL, NATIVE, classify_call, classify_command, result, shares,
)

ACQUISITIONS = ('BULK-NONVIDEO-20260929', 'SWEBENCH-CONTINUATION-20260930',
                'SWEBENCH-SUPPLEMENT-20261006')
PACKAGES = ('SWE-REBENCH-behavior-v2', 'SWEBENCH-subset-behavior-v1',
            'OSWORLD-task-behavior-v3', 'TOOLSANDBOX-HEPM-behavior-v2',
            'AGENTX-APPLIED-MACRO-v1')
REBENCH = 'data/raw/public/swe_rebench_nonofficial/cdae27cdd16673f0c682871ad55d325f24cc7020'
SWEBENCH = 'data/raw/public/swebench_public_traces/40f164d5b8f1d249bf95a6df8b74b577fd8e519d'


def digest(data): return hashlib.sha256(data).hexdigest()


class Inputs:
    def __init__(self, root): self.root = Path(root); self.files = {}

    def read(self, path, expected=None):
        path = Path(path)
        path = path if path.is_absolute() else self.root / path
        name = str(path.relative_to(self.root))
        data = path.read_bytes()
        item = {'path': name, 'bytes': len(data), 'sha256': digest(data)}
        if expected is not None and (expected.get('sha256') != item['sha256'] or
                                    expected.get('bytes', len(data)) != len(data)):
            raise ValueError('input identity mismatch: ' + name)
        if name in self.files and self.files[name] != item: raise ValueError('input changed: ' + name)
        self.files[name] = item
        return data

    def json(self, path, expected=None): return json.loads(self.read(path, expected))

    def package(self, name):
        directory = 'reports/analysis/' + name + '/'
        manifest = self.json(directory + 'manifest.json')
        for item in manifest['outputs']:
            path = item['path'] if '/' in item['path'] else directory + item['path']
            self.read(path, item)
        return self.json(directory + 'summary.json'), manifest


def load_registrations(inputs):
    entries = {}
    for name in ACQUISITIONS:
        manifest = inputs.json('data/catalog/public_trace_acquisition/' + name + '/manifest.json')
        for item in manifest['inputs']:
            if not item['path'].startswith(SWEBENCH + '/') or item.get('role') != 'trajectory': continue
            old = entries.get(item['path'])
            if old and (old['bytes'], old['sha256']) != (item['bytes'], item['sha256']):
                raise ValueError('conflicting acquisition registration: ' + item['path'])
            entries[item['path']] = item
    return entries


def arguments(value):
    if isinstance(value, str):
        try: return json.loads(value), None
        except (ValueError, TypeError): return None, 'unparseable_arguments'
    return value, None if isinstance(value, (dict, list)) else 'missing_arguments'


def extract_structured(obj):
    """Return schema, saved units; never mine prompts/thoughts for commands."""
    if isinstance(obj, dict) and isinstance(obj.get('transitions'), list):
        return 'moatless_saved_transitions', [
            {'tool': t.get('name', 'missing'), 'arguments': None, 'position': i,
             'transition': True} for i, t in enumerate(obj['transitions']) if isinstance(t, dict)]
    if isinstance(obj, dict) and isinstance(obj.get('trajectory'), list):
        traj = obj['trajectory']
        if traj and all(isinstance(t, dict) and 'action' in t for t in traj):
            return 'sweagent_saved_actions', [
                {'tool': (t['action'].split()[0] if isinstance(t['action'], str) and t['action'].split() else 'missing'),
                 'arguments': t['action'], 'position': i, 'terminal_action': True}
                for i, t in enumerate(traj)]
    messages = obj.get('messages') if isinstance(obj, dict) else obj
    if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
        return 'unsupported_saved_structure', None
    units = []; explicit_protocol = False
    for mi, m in enumerate(messages):
        if m.get('role') != 'assistant': continue
        extra = m.get('additional_kwargs') if isinstance(m.get('additional_kwargs'), dict) else {}
        calls = m.get('tool_calls', extra.get('tool_calls'))
        if isinstance(calls, list):
            explicit_protocol = True
            for ci, call in enumerate(calls):
                fn = call.get('function', {}) if isinstance(call, dict) else {}
                arg, error = arguments(fn.get('arguments'))
                units.append({'tool': fn.get('name', 'missing'), 'arguments': arg,
                              'argument_error': error, 'position': [mi, ci]})
        # Anthropic's native tool_use content blocks, when not duplicated by tool_calls.
        elif isinstance(m.get('content'), list):
            for ci, block in enumerate(m['content']):
                if isinstance(block, dict) and block.get('type') == 'tool_use':
                    explicit_protocol = True
                    units.append({'tool': block.get('name', 'missing'), 'arguments': block.get('input'),
                                  'position': [mi, ci]})
    return ('explicit_message_tool_calls', units) if explicit_protocol else ('messages_without_explicit_tool_calls', None)


TRANSITIONS = {'SearchCode': 'content_search', 'IdentifyCode': 'file_view',
               'EditCode': 'edit_write', 'PlanToCode': 'plan', 'Finished': 'submit',
               'ClarifyCodeChange': 'plan', 'Rejected': 'other'}


def classify_unit(unit):
    if unit.get('argument_error'): return result([], unit['argument_error'], origin='protocol')
    if unit.get('transition'):
        return result([TRANSITIONS.get(unit['tool'], 'unknown')], origin='saved_transition')
    if unit.get('terminal_action'):
        if unit['tool'] in {'open', 'edit', 'create', 'find_file', 'search_file', 'search_dir',
                            'goto', 'scroll_down', 'scroll_up', 'submit'}:
            return result([NATIVE[unit['tool']]], origin='sweagent_editor_interface')
        return classify_command(unit['arguments'])
    return classify_call(unit['tool'], unit['arguments'])


def summarize_units(source, group, task, location, unit_kind, units):
    operations = Counter(); tools = Counter(); components = Counter(); heads = Counter(); reasons = Counter()
    call_presence = Counter()
    command_available = 0; examples = {}
    for unit in units:
        r = classify_unit(unit); operation = r['operation']
        operations[operation] += 1; tools[str(unit['tool'])] += 1
        components.update(r['components']); heads.update(r['executables'])
        call_presence.update(set(r['components']))
        if r['reason']: reasons[r['reason']] += 1
        arg = unit.get('arguments')
        command = arg.get('command', arg.get('cmd')) if isinstance(arg, dict) else arg
        if str(unit['tool']).lower() == 'sendshellinput' and isinstance(arg, dict): command = arg.get('input')
        if unit.get('terminal_action') or str(unit['tool']).lower() in SHELL:
            command_available += int(isinstance(command, (str, list)))
        if operation not in examples:
            # Point back to source rather than copying command arguments or messages.
            examples[operation] = {'position': unit['position'], 'tool': unit['tool'],
                                   'saved_arguments_sha256': digest(json.dumps(arg, sort_keys=True, ensure_ascii=False).encode()),
                                   'rule_origin': r['origin']}
    n = len(units)
    assert sum(operations.values()) == sum(tools.values()) == n
    return {'source': source, 'group': group, 'task': task, 'location': location,
            'unit_kind': unit_kind, 'unit_count': n, 'operation_counts': dict(operations),
            'native_tool_counts': dict(tools), 'syntactic_component_counts': dict(components),
            'operation_call_presence_counts': dict(call_presence),
            'executable_counts': dict(heads), 'classification_reasons': dict(reasons),
            'saved_command_available_count': command_available, 'evidence_examples': examples}


def analyze_rebench(inputs, old):
    base = inputs.root / REBENCH
    index = [json.loads(line) for line in inputs.read(base / 'index.jsonl').decode().split('\n') if line]
    expected = {r['path']: r for r in old['coverage']['shards']}
    rows = []; seen = set()
    for item in index:
        compressed = inputs.read(base / item['path'], expected[item['path']])
        data = gzip.decompress(compressed)
        if digest(data) != item['content_sha256']: raise ValueError('decompressed shard mismatch')
        parsed = 0
        for line_no, line in enumerate(data.decode().split('\n'), 1):
            if not line.strip(): continue
            obj = json.loads(line); parsed += 1
            key = obj['trajectory_id']
            if key in seen: raise ValueError('duplicate trajectory identity')
            seen.add(key)
            calls = [{'tool': e.get('tool', 'missing'), 'arguments': e.get('input'), 'position': i}
                     for i, e in enumerate(obj.get('events', [])) if e.get('type') == 'tool_call']
            rows.append(summarize_units('SWE-rebench', obj['participant']['key'], obj['instance_id'],
                        {'path': REBENCH + '/' + item['path'], 'line': line_no, 'trajectory_id': key},
                        'saved_tool_call', calls))
        if parsed != item['rows']: raise ValueError('shard row count mismatch')
    if len(rows) != old['scope']['record_count']: raise ValueError('corpus row count mismatch')
    if sum(r['unit_count'] for r in rows) != sum(old['native_tool_counts'].values()): raise ValueError('corpus tool count mismatch')
    return rows


def analyze_swebench(inputs, entries):
    rows = []; inventory = []; groups = defaultdict(Counter)
    for name, registration in sorted(entries.items()):
        group = name.split('/experiments/', 1)[1].split('/trajs/', 1)[0]
        task = name.split('/trajs/', 1)[1].split('/')[0].rsplit('.', 1)[0]
        data = inputs.read(name, registration)
        try: obj = json.loads(data)
        except (ValueError, UnicodeError): obj = None
        schema, units = extract_structured(obj)
        groups[group][schema] += 1
        item = {'path': name, 'group': group, 'schema': schema, 'bytes': len(data),
                'interpreted': units is not None, 'unit_count': len(units) if units is not None else None}
        inventory.append(item)
        if units is not None:
            rows.append(summarize_units('SWE-bench', group, task, {'path': name},
                        'saved_transition' if schema == 'moatless_saved_transitions' else 'saved_action_or_tool_call', units))
    actual = {str(p.relative_to(inputs.root)) for p in (inputs.root / SWEBENCH / 'experiments').rglob('*')
              if p.is_file() and '/trajs/' in str(p)}
    return rows, {'registered_object_count': len(inventory), 'registered_group_count': len(groups),
                  'interpreted_object_count': len(rows), 'unsupported_object_count': len(inventory) - len(rows),
                  'per_group_schema_counts': {g: dict(c) for g, c in sorted(groups.items())},
                  'unregistered_actual_paths': sorted(actual - set(entries)),
                  'objects': inventory,
                  'note': 'object != trajectory; unsupported logs, summaries and companion artifacts are not counted as parsed trajectories; upstream completeness not asserted'}


def aggregate(rows):
    counts = Counter(); tools = Counter(); tool_presence = Counter(); presence = Counter()
    components = Counter(); executables = Counter(); reasons = Counter()
    call_presence = Counter()
    for row in rows:
        counts.update(row['operation_counts']); tools.update(row['native_tool_counts'])
        tool_presence.update(k for k, v in row['native_tool_counts'].items() if v)
        presence.update(k for k, v in row['operation_counts'].items() if v)
        components.update(row['syntactic_component_counts']); executables.update(row['executable_counts'])
        call_presence.update(row['operation_call_presence_counts'])
        reasons.update(row['classification_reasons'])
    n = sum(counts.values())
    return {'record_count': len(rows), 'operations': shares(counts), 'native_tools': shares(tools),
            'operation_call_presence': {'all_call_denominator': n, 'counts': dict(call_presence),
                                        'percent_all_calls': {k: 100*v/n if n else None for k,v in call_presence.items()},
                                        'overlapping': True},
            'operation_record_presence': dict(sorted(presence.items())),
            'tool_record_presence': dict(sorted(tool_presence.items())),
            'syntactic_components': shares(components), 'executables': shares(executables),
            'classification_reasons': dict(reasons),
            'saved_command_available_count': sum(r['saved_command_available_count'] for r in rows)}


def coding_summary(rows):
    groups = defaultdict(list); repos = defaultdict(list)
    for row in rows:
        groups[(row['source'], row['group'], row['unit_kind'])].append(row)
        repos[(row['source'], row['group'], row['unit_kind'], row['task'].rsplit('-', 1)[0])].append(row)
    return {'groups': [{'source': s, 'group': g, 'unit_kind': u, **aggregate(rr)}
                       for (s, g, u), rr in sorted(groups.items())],
            'repository_scenarios': [{'source': s, 'group': g, 'unit_kind': u, 'repository': repo, **aggregate(rr)}
                                    for (s, g, u, repo), rr in sorted(repos.items())],
            'swe_rebench_pooled': aggregate([r for r in rows if r['source'] == 'SWE-rebench']),
            'pooling': 'SWE-bench submissions/transitions and SWE-rebench participants are not a shared population; per-group denominators retained; pooled SWE-rebench is call-weighted, not typical participant'}


def imported_rows(inputs, package):
    path = 'reports/analysis/' + package + '/per_trajectory.jsonl'
    return [json.loads(line) for line in inputs.read(path).decode().split('\n') if line]


def osworld_summary(inputs, old, manifest):
    base = 'reports/analysis/OSWORLD-task-behavior-v3/'
    tasks = {r['task_key']: r for r in [json.loads(x) for x in inputs.read(base + 'task_semantics.jsonl').decode().split('\n') if x]}
    rows = imported_rows(inputs, 'OSWORLD-task-behavior-v3')
    expected = {r['path']: r for r in manifest['inputs']}
    by_model = defaultdict(list); by_app = defaultdict(list); examples = {}
    for row in rows:
        # Existing source_file is relative to the downloaded trajectory root.
        name = 'data/raw/public/osworld2_trajectory_light/' + row['source_file']
        data = inputs.read(name, expected[name])
        native = Counter(); interfaces = Counter()
        for line in data.decode().split('\n'):
            if not line.strip(): continue
            obj = json.loads(line); action = obj.get('action')
            if isinstance(action, dict):
                payload = action.get('input') if isinstance(action.get('input'), dict) else action.get('action')
                action_name = payload.get('action') if isinstance(payload, dict) else None
                if isinstance(action_name, str): native[action_name] += 1
                elif action.get('action_type') in ('computer_call', 'tool_use'): native['unknown'] += 1
                if action.get('action_type'): interfaces[str(action['action_type'])] += 1
        item = {'task': row['task_key'], 'native': dict(native), 'static': row['static_category_counts'],
                'interfaces': dict(interfaces), 'applicable': row['native_representation_status'] == 'applicable',
                'analysis_status': row['analysis_status']}
        if sum(native.values()) != row['native_action_record_count']: raise ValueError('OSWorld native action count drift')
        by_model[row['model']].append(item)
        apps = tasks[row['task_key']].get('related_apps')
        apps = apps if isinstance(apps, list) else [apps] if isinstance(apps, str) else ['unknown']
        for app in set(apps or ['unknown']): by_app[(row['model'], str(app))].append(item)
    def summarize(rr):
        native = Counter(); static = Counter(); interfaces = Counter()
        for r in rr: native.update(r['native']); static.update(r['static']); interfaces.update(r['interfaces'])
        return {'trajectory_count': len(rr), 'native_applicable_trajectories': sum(r['applicable'] for r in rr),
                'native_saved_actions': shares(native), 'static_source_call_categories': shares(static),
                'saved_interfaces': dict(interfaces), 'analysis_status_counts': dict(Counter(r['analysis_status'] for r in rr))}
    return {'models': {m: summarize(rr) for m, rr in sorted(by_model.items())},
            'declared_application_scenarios': [{'model': m, 'declared_app': app, **summarize(rr)} for (m, app), rr in sorted(by_app.items())],
            'toolkit': ['computer/computer_call/tool_use saved actions: click, key/type/hotkey, scroll, pointer, screenshot, wait',
                        'pyautogui command-source static calls, kept separate from native actions'],
            'limits': ['declared related_apps are overlapping task-definition context, not proof which application each action operated on',
                       'historical task-version binding unknown; no application-specific business action is inferred from clicks',
                       'native action counts and static Python calls are separate denominators, never added together',
                       'no public DocOps tool execution corpus in this source set; local xlsx/ppt/pdf tools excluded']}


def assistant_summary(inputs, old):
    rows = imported_rows(inputs, 'TOOLSANDBOX-HEPM-behavior-v2')
    groups = defaultdict(list); scenarios = defaultdict(list)
    for row in rows:
        groups[row['group_directory']].append(row)
        for activity in row['activity_call_counts']:
            scenarios[(row['group_directory'], activity)].append(row)
    def summarize(rr):
        activity = Counter(); native = Counter(); called = Counter(); presence = Counter(); n = 0
        for row in rr:
            n += row['pairing']['tool_call_entries']; activity.update(row['activity_call_counts'])
            native.update(row['native_identity_counts']); called.update(row['called_name_counts'])
            presence.update(k for k, v in row['native_identity_counts'].items() if v)
        activity['unknown'] += n - sum(activity.values())
        return {'trajectory_count': len(rr), 'activities': shares(activity),
                'resolved_native_tools': {'all_call_denominator': n, 'resolved_count': sum(native.values()),
                                          'unresolved_identity_count': n - sum(native.values()), 'counts': dict(native),
                                          'percent_all_calls': {k: 100*v/n if n else None for k,v in native.items()}},
                'called_interfaces': shares(called), 'native_tool_trajectory_presence': dict(presence)}
    return {'groups': {g: summarize(rr) for g, rr in sorted(groups.items())},
            'conditional_activity_scenarios': [{'group': g, 'activity_present': a, **summarize(rr)} for (g, a), rr in sorted(scenarios.items())],
            'available_tool_inventory': old['tool_interface']['native_tool_names'],
            'native_tool_to_activity': old['tool_interface']['activity_classification'],
            'limits': ['H-EPM third-party extension, not Apple official trace release',
                       'available allow-list names are not all observed calls; observed and resolved identities kept separate',
                       'scenario groups are conditional overlapping slices; group-wide counts retain zero-call traces',
                       'two groups share scenario keys and have different source revisions; no causal comparison',
                       'summarize_the_task is H-EPM harness overhead, not a business tool; User end_conversation not agent calls']}


def render_toolkits(summary):
    """Readable scene/tool map, based only on observed identities and saved context."""
    lines = ['# 不同场景常用哪些工具', '',
             '工具名来自保存调用/动作，不把任务中提到的软件名当作已调用API。调用次数和轨迹覆盖分开；以下不是性能或能力排名。', '',
             '## Coding：工具接口与命令程序两层', '',
             '| 场景 | 可观察工具/命令 | 分类边界 |', '| --- | --- | --- |',
             '| 文件定位 | Glob/glob、find_file、find/ls、rg --files | 定位路径，不与内容检索合并 |',
             '| 内容/符号检索 | Grep/grep、search_file/search_dir、rg、find_symbols、SearchCode | 结构化搜索节点与shell调用分母不同 |',
             '| 文件查看 | Read/read、open、编辑器view、cat/head/sed -n | head也可作为检索命令的输出过滤，组合单列 |',
             '| 修改内容 | Edit/edit、Write、str_replace_based_edit_tool、apply_patch | 文件管理cp/mv等另列 |',
             '| 构建/编译 | make、cmake、编译器、python setup.py build等明确命令头/参数 | 不从thought中出现build一词推断 |',
             '| 测试 | pytest、python -m pytest/unittest、npm test、cargo/go test等 | grep/echo提及pytest不是测试 |',
             '| 环境准备 | pip、uv、conda、npm install等 | 与构建、测试分开 |', '',
             '上表是有限分类规则对应的工具族，不声称每个来源都调用了全部工具；下表给实际出现的原生接口。', '',
             '| 来源/组 | 保存记录数 | 保存单位数 | 实际高频接口（次数；出现记录数） |', '| --- | ---: | ---: | --- |']
    for g in summary['coding']['groups']:
        top = sorted(g['native_tools']['counts'].items(), key=lambda x: -x[1])[:8]
        names = '；'.join(f"`{name}` {n:,}；{g['tool_record_presence'][name]}条" for name, n in top)
        lines.append(f"| {g['source']} / {g['group']} | {g['record_count']} | {g['operations']['denominator']} | {names} |")
    lines += ['', '各代码仓库切片的同类统计在toolkits.json的coding.repository_scenarios；这是仓库来源切片，不是独立随机任务类别。', '',
              '## Computer/Office：桌面操作，不是文档API日志', '',
              'OSWorld保存接口以computer/computer_call/tool_use原生动作、以及pyautogui命令源码呈现。两者不能相加。', '',
              '| 保存接口层 | 常见动作 | 能说明什么 |', '| --- | --- | --- |',
              '| 原生桌面动作 | left_click/double_click、key/type/hotkey、scroll、mouse_move/drag、screenshot、wait | 已保存的动作接口分布 |',
              '| command静态源码 | pyautogui点击、按键、输入、滚动、移动；sleep等等待源码 | 静态可识别调用，不是实际GUI执行次数 |', '',
              '### 按任务声明应用分组', '',
              '同一任务可以涉及多个应用，因此以下场景重叠；应用来自当前下载的任务定义，与历史轨迹版本对应仍unknown。动作不自动归因给该应用。', '',
              '| 任务声明应用 | 涉及模型×任务记录 | 原生动作中高频保存名 |', '| --- | ---: | --- |']
    apps = defaultdict(list)
    for r in summary['computer_office']['declared_application_scenarios']: apps[r['declared_app']].append(r)
    for app, rr in sorted(apps.items()):
        native = Counter()
        for r in rr: native.update(r['native_saved_actions']['counts'])
        lines.append(f"| {app} | {sum(r['trajectory_count'] for r in rr)} | " + '；'.join(f'`{k}`={v:,}' for k,v in native.most_common(5)) + ' |')
    lines += ['', '具体模型下的应用切片、动作比例在toolkits.json；MiniMax-M3/Qwen的原生字段不适用，不填成0。',
              '未找到公开DocOps执行轨迹，不能据此列出openpyxl/python-docx等库的公开调用占比；本地DocOps测量在另一个证据集合，不混入本轮。', '',
              '## Assistant：状态化个人助理工具', '',
              '| 来源组 | 活动 | 保存调用数（全部调用占比） | 已还原原生身份中实际调用的工具 |', '| --- | --- | ---: | --- |']
    mapping = summary['assistant']['native_tool_to_activity']
    for group, row in summary['assistant']['groups'].items():
        for activity, n in sorted(row['activities']['counts'].items(), key=lambda x:-x[1]):
            native = [(k,v) for k,v in row['resolved_native_tools']['counts'].items() if mapping.get(k) == activity]
            names = '；'.join(f'`{k}`={v}' for k,v in sorted(native, key=lambda x:-x[1])) or '身份未完全还原，保留Unknown/活动级证据'
            lines.append(f"| {group} | {activity} | {n}（{row['activities']['percent_all'][activity]:.2f}%） | {names} |")
    lines += ['', '联系人、提醒、消息、设备状态、日期时间、位置/天气与网络查询分开。summarize_the_task属于H-EPM框架辅助，不与业务工具混称；allow-list中可用不代表实际调用。', '',
              '## 宏观模板与视频', '',
              '- AgentX：可分析请求与subagent结构，缺具体业务工具名，工具集无法从该语料恢复。',
              '- Applied Compute：agentic_coding/code_qa/office_work是派生模板类别，不是工具名或真实Office执行日志。',
              '- Video：当前VideoWeaver旧样本为宏观/部分解析；不在这里用推测的FFmpeg或生成工具名填补公开视频工具集。', '',
              '[操作占比与限制](summary.md) · [完整机器可读工具集](toolkits.json) · [覆盖清单](coverage.json)']
    return '\n'.join(lines)+'\n'


def write_operation_csv(path, coding):
    with path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['source', 'group', 'unit_kind', 'records', 'all_units', 'operation',
                         'exclusive_label_count', 'exclusive_percent_all',
                         'contains_operation_calls', 'contains_percent_all_nonexclusive'])
        for row in coding['groups']:
            for label in LABELS:
                writer.writerow([row['source'], row['group'], row['unit_kind'], row['record_count'],
                    row['operations']['denominator'], label, row['operations']['counts'].get(label, 0),
                    row['operations']['percent_all'].get(label, 0) if row['operations']['denominator'] else None,
                    row['operation_call_presence']['counts'].get(label, 0),
                    row['operation_call_presence']['percent_all_calls'].get(label, 0) if row['operations']['denominator'] else None])


def render_coverage(inventory):
    lines = ['# SWE-bench 本地对象覆盖清单', '',
             '仅针对三轮获取manifest登记、并在本轮逐文件核对SHA的本地对象；不是上游全部公开提交的覆盖率。对象可能是轨迹、日志或配套产物，不直接等于轨迹数。', '',
             '| submission | 登记对象 | 可提取结构化保存单位的对象 | 本轮未支持对象 |', '| --- | ---: | ---: | ---: |']
    known = {'moatless_saved_transitions', 'sweagent_saved_actions', 'explicit_message_tool_calls'}
    for group, counts in inventory['per_group_schema_counts'].items():
        n = sum(counts.values()); parsed = sum(v for k,v in counts.items() if k in known)
        lines.append(f'| {group} | {n} | {parsed} | {n-parsed} |')
    lines += ['', '未支持对象包括无显式tool_calls的消息、自由文本/非JSON日志、其他结构与配套说明。不能据此说这些对象不含命令；只说明本轮没有可靠提取协议。',
              '后续应按来源协议逐组验证，不从prompt/thought中的代码块直接猜测执行动作，也不为了降低Unknown强行归类。', '',
              f"实际存在但未登记的路径数：{len(inventory['unregistered_actual_paths'])}；路径逐项见coverage.json。", '',
              '[逐文件覆盖JSON](coverage.json) · [操作总结](summary.md)']
    return '\n'.join(lines)+'\n'


def render(summary):
    coding = summary['coding']; inv = summary['swebench_inventory']; rb = coding['swe_rebench_pooled']
    lines = ['# 公开轨迹：操作构成与常用工具集', '',
             '本轮仅离线读取公开数据与已验收分析；不运行轨迹、Agent、工具或模型。比例均注明来源、分母和可识别范围。', '',
             '## 先看结论', '',
             '- Coding：终端/shell、文件/代码检索、文件查看、编辑接口，以及命令内的构建/测试共同构成工具集；不能把 bash 都叫作“执行”。',
             '- Computer/Office：这里的公开证据来自 OSWorld 的桌面操作接口与 pyautogui 源码；可描述点击、输入、滚动等，不能从点击自动判断“编辑公式”。',
             '- Assistant：联系人、消息、提醒、设备设置、日期时间、位置/天气/查询等结构化工具；H-EPM 的摘要工具单列为框架辅助。',
             '- AgentX 与 Applied Compute 没有可用于统计具体工具名的完整工具日志；模板名 office_work 不证明使用了某个 Office API。',
             '- VideoWeaver 既有小样没有在本轮升级成完整公开工具语料；视频工具集仍不能从现有公开证据完整汇总。', '',
             '## Coding：SWE-rebench 全量已登记语料', '',
             f"{rb['record_count']:,} 条轨迹、{rb['operations']['denominator']:,} 个保存的 tool_call；按调用加权，不是平均 participant，也不是耗时/CPU占比。", '',
             '| 操作 | 单一主要用途/组合标签次数 | 占全部保存调用 |', '| --- | ---: | ---: |']
    for label, count in sorted(rb['operations']['counts'].items(), key=lambda x: -x[1]):
        lines.append(f"| {LABELS[label]} | {count:,} | {rb['operations']['percent_all'][label]:.3f}% |")
    lines += ['', 'mixed=一个保存调用中包含多类可识别操作；partial=含未识别片段；script_execute只确认解释器执行，不能细说用途。Unknown不排除分母。', '',
              '### 含某类操作的调用（允许重叠）', '',
              '一次 `grep ... | head ...` 同时涉及检索和查看。下表每类在同一调用内最多记一次，分母仍为全部调用；类别间不能相加成100%，也不证明条件分支实际执行。', '',
              '| 保存命令涉及的操作 | 调用数 | 全部调用占比 |', '| --- | ---: | ---: |']
    for label, count in sorted(rb['operation_call_presence']['counts'].items(), key=lambda x: -x[1]):
        lines.append(f"| {LABELS[label]} | {count:,} | {rb['operation_call_presence']['percent_all_calls'][label]:.3f}% |")
    lines += ['',
              '### 常用原生工具接口', '', '| 接口 | 调用数 | 调用占比 | 出现轨迹 / 全部轨迹 |', '| --- | ---: | ---: | ---: |']
    for name, n in sorted(rb['native_tools']['counts'].items(), key=lambda x: -x[1])[:15]:
        lines.append(f"| `{name}` | {n:,} | {rb['native_tools']['percent_all'][name]:.2f}% | {rb['tool_record_presence'][name]} / {rb['record_count']} |")
    lines += ['', '### 常见命令程序（源码片段口径）', '',
              '以下是保存命令静态拆分后的程序名频数，不是实际执行次数；&&/||、管道等不证明所有分支都执行。', '',
              ', '.join(f'`{k}`={v:,}' for k, v in sorted(rb['executables']['counts'].items(), key=lambda x: -x[1])[:25]), '',
              '### 分组与仓库场景', '',
              'toolkits.json 保留每个 participant、每个原生 submission、每个代码仓库切片的完整操作/工具计数、调用占比与轨迹出现次数；不合并跨格式分母。', '',
              '## SWE-bench：不再只检查原先的90条', '',
              f"登记对象 {inv['registered_object_count']:,} 个，覆盖 {inv['registered_group_count']} 个 submission；逐文件核对登记SHA。结构化解释 {inv['interpreted_object_count']:,} 个对象，另外 {inv['unsupported_object_count']:,} 个对象保留为未支持结构。", '',
              '对象不等于轨迹：日志、检索统计、说明与配套产物不能凑成轨迹数量。逐组清单见[coverage.md](coverage.md)，逐文件见coverage.json；未登记本地路径另列，不擅自计入。', '',
              '| submission | 保存单位 | 已解释记录 | 保存单位总数 | unknown / partial |', '| --- | --- | ---: | ---: | ---: |']
    for group in coding['groups']:
        if group['source'] != 'SWE-bench': continue
        c = group['operations']['counts']
        lines.append(f"| {group['group']} | {group['unit_kind']} | {group['record_count']} | {group['operations']['denominator']} | {c.get('unknown', 0)} / {c.get('partial', 0)} |")
    lines += ['', '不解析自由文本中的thought、prompt或示例命令作为真实工具调用。Moatless是保存的流程节点，不当作shell调用。未支持的格式不声称已经分析完毕。', '',
              '## Computer/Office：OSWorld', '',
              '| 模型 | 轨迹 | 原生动作记录 | 静态源码调用节点 |', '| --- | ---: | ---: | ---: |']
    for model, row in summary['computer_office']['models'].items():
        lines.append(f"| {model} | {row['trajectory_count']} | {row['native_saved_actions']['denominator'] if row['native_applicable_trajectories'] else '不适用'} | {row['static_source_call_categories']['denominator']} |")
    lines += ['', '### 各模型保存的常用桌面动作', '']
    for model, row in summary['computer_office']['models'].items():
        native = row['native_saved_actions']
        if row['native_applicable_trajectories']:
            lines.append('- ' + model + '：' + '、'.join(f"`{k}` {v:,}（{native['percent_all'][k]:.1f}%）" for k,v in sorted(native['counts'].items(), key=lambda x:-x[1])[:8]))
        else: lines.append('- ' + model + '：原生动作字段不适用；只报告另一层静态源码类别，不填原生动作0%。')
    lines += ['', '原生动作保存了点击、键盘输入、滚动、指针移动、截图和等待等接口；静态 command 调用单列，不能与原生动作重复相加，也不证明实际GUI执行次数。',
              '按任务定义声明的应用（浏览器、表格、文档、邮件等）分组的动作构成见toolkits.json。一个任务可涉及多个应用，不把多应用切片强行加成100%。历史任务版本绑定仍unknown。',
              '没有公开DocOps执行轨迹作为本轮分母；不能把本地DocOps的xlsx/ppt/pdf工具名单冒充公开Office工具统计。', '',
              '## Assistant：H-EPM ToolSandbox', '']
    for group, row in summary['assistant']['groups'].items():
        lines += [f'### {group}', '', f"{row['trajectory_count']} 条轨迹，{row['activities']['denominator']} 个Agent调用。", '',
                  '| 活动 | 调用数 | 全部调用占比 |', '| --- | ---: | ---: |']
        for k, v in sorted(row['activities']['counts'].items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v} | {row['activities']['percent_all'][k]:.2f}% |")
        lines += ['', '常用已解析原生工具：' + ', '.join(f'`{k}`={v}' for k,v in sorted(row['resolved_native_tools']['counts'].items(), key=lambda x:-x[1])[:12]), '']
    lines += ['允许工具清单不等于实际调用；扰动名的身份解析依据既有v2的SANDBOX记录，24条无法分类调用保留Unknown。User结束工具和Agent业务调用不混合。', '',
              '## 不可提供具体工具集的来源', '',
              '- AgentX：请求流及显式subagent结构，具体业务工具名/参数未提供。',
              '- Applied Compute：三类派生workload模板，只有轮次、token长度与模拟延迟；没有实际Office API调用。',
              '- VideoWeaver：现有宏观小样/部分解析不能替代完整公开视频工具语料。', '',
              '## 口径与可复核性', '',
              '- 主操作比例：每个保存单位一个标签，含mixed/partial/unknown，合计等于该来源分母。',
              '- 文本查看包括cat/read以及管道中的head/tail输出截取，不都代表直接打开源码文件；内容修改/写入也包含生成脚本与其他文件，不冒称全部都是仓库源码修改。',
              '- 组件比例：静态命令片段单独分母，只表示保存源码构成，不是实际执行频率。',
              '- 重定向只辅助识别命令用途：测试日志保存不另算一次工具操作；单条echo/printf/cat输出写入文件另识别为写入。仅对单个闭合、字面量marker及已知消费者的heredoc做静态解析，不执行正文；其他情况Unknown。',
              '- 常用工具同时给调用频数和轨迹出现数，避免少数长轨迹决定全部结论。',
              '- 所有分类都不代表时间或CPU占比；没有新增性能、成功率或因果结论。',
              '- 不执行数据中的代码、AST、shell、工具、evaluator；不读取凭据或访问网络。', '',
              '## 历史更正', '',
              '原90条子集中的SWE-agent组，旧summary.md写1053个action，但同包summary.json接口与活动合计均为1064。本轮从该组30份原件重新统计，见summary.json的historical_corrections；旧包不改写。', '',
              '[场景工具表](toolkits.md) · [操作统计CSV](coding_operations.csv) · [summary.json](summary.json) · [toolkits.json](toolkits.json) · [coverage.json](coverage.json) · [per_trajectory.jsonl](per_trajectory.jsonl) · [manifest.json](manifest.json)']
    return '\n'.join(lines) + '\n'


def run(root, out):
    root = Path(root); out = Path(out)
    if out.exists(): raise FileExistsError('refusing to overwrite output')
    inputs = Inputs(root); packages = {n: inputs.package(n) for n in PACKAGES}
    print('verified source analysis outputs', flush=True)
    registrations = load_registrations(inputs)
    rows = analyze_rebench(inputs, packages['SWE-REBENCH-behavior-v2'][0])
    print('classified SWE-rebench', len(rows), flush=True)
    swe_rows, inventory = analyze_swebench(inputs, registrations); rows += swe_rows
    print('inventoried SWE-bench', inventory['registered_object_count'], 'interpreted', len(swe_rows), flush=True)
    osworld = osworld_summary(inputs, *packages['OSWORLD-task-behavior-v3'])
    assistant = assistant_summary(inputs, packages['TOOLSANDBOX-HEPM-behavior-v2'][0])
    macro = packages['AGENTX-APPLIED-MACRO-v1'][0]
    selection = inputs.json('reports/analysis/SWEBENCH-subset-behavior-v1/selection.json')
    first = selection['groups'][0]
    selected = []
    for item in first['items']:
        obj = inputs.json(item['file'], item)
        selected.append(len(obj['trajectory']))
    old_group = packages['SWEBENCH-subset-behavior-v1'][0]['groups'][first['submission']]
    json_total = sum(old_group['interface_totals'].values())
    old_text = inputs.read('reports/analysis/SWEBENCH-subset-behavior-v1/summary.md').decode()
    match = re.search(r'sweagent 组 ([\d,]+) 个 action', old_text)
    corrections = {'sweagent_old_30': {'reported_text_total': int(match.group(1).replace(',', '')) if match else None,
                                     'registered_json_total': json_total,
                                     'raw_recomputed_total': sum(selected),
                                     'old_artifacts_modified': False}}
    if sum(selected) != json_total: raise ValueError('old subset discrepancy needs further review')
    coding = coding_summary(rows)
    summary = {'schema': 'public-trace-operations-v1', 'coding': coding,
               'swebench_inventory': {k:v for k,v in inventory.items() if k != 'objects'},
               'computer_office': osworld, 'assistant': assistant,
               'macro_sources': macro['sources'], 'historical_corrections': corrections,
               'taxonomy': LABELS,
               'scope': 'public data only; no local resource runs; source-specific denominators; no blanket completeness claim',
               'limits': ['SWE-bench unsupported formats explicitly inventoried, not guessed',
                          'command source occurrences are not execution or resource counts',
                          'OSWorld native and static representations never pooled',
                          'H-EPM extension is third-party; Applied templates are not real tool traces',
                          'Video public toolkit evidence incomplete; no remote CPU claims']}
    out.mkdir(parents=True)
    (out/'per_trajectory.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False, separators=(',',':'))+'\n' for r in rows))
    (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    (out/'toolkits.json').write_text(json.dumps({'coding': coding, 'computer_office': osworld, 'assistant': assistant}, ensure_ascii=False, indent=2)+'\n')
    (out/'coverage.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n')
    (out/'coverage.md').write_text(render_coverage(inventory))
    (out/'summary.md').write_text(render(summary))
    (out/'toolkits.md').write_text(render_toolkits(summary))
    write_operation_csv(out/'coding_operations.csv', coding)
    for path in (Path(__file__), PROJECT/'src/agent_workload_characterization/analyzers/public_operations.py', PROJECT/'tests/test_public_trace_operations.py'):
        inputs.read(root/path.relative_to(PROJECT))
    outputs = [{'path': str(p.relative_to(root)), 'bytes': p.stat().st_size, 'sha256': digest(p.read_bytes())}
               for p in sorted(out.iterdir()) if p.is_file()]
    manifest = {'schema': 'public-trace-operations-manifest-v1', 'inputs': list(inputs.files.values()),
                'outputs': outputs, 'manifest_self_hash': 'excluded',
                'verification_scope': 'SWE-rebench shard identities/content; registered SWE-bench objects; source-package outputs; OSWorld raw action records; H-EPM source results reused, not re-executed'}
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(PROJECT, args.output_dir.resolve())
    return 0


if __name__ == '__main__': raise SystemExit(main())
