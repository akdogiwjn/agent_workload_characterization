"""Directed tests for toolsandbox_hepm_behavior (v2) using synthetic fixtures.

Covers: one assistant message with multiple tool calls, SANDBOX tool_trace
resolution of scrambled names (exception rows with stale traces excluded),
duplicate/missing IDs, orphan results and missing returns, Unknown sequence
boundaries, tool-error vs task-result separation with SANDBOX cross-check,
missing fields not zero-filled, dual activity-stat denominators, run
provenance fields, final conversation_active and user-side end_conversation
reporting, input hash mismatch rejection, and the full entry generating all
outputs with conserved counts.
"""
import hashlib
import json
import os
import tempfile
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_spec = importlib.util.spec_from_file_location(
    'tsb', os.path.join(ROOT, 'scripts', 'toolsandbox_hepm_behavior.py'))
tsb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tsb)

GROUP_F = 'H-EPM_test_graph_False'
GROUP_T = 'H-EPM_test_graph_True'
SCEN_ONE = 'task_one_3_distraction_tools_tool_name_scrambled'
SCEN_TWO = 'task_two'


def write_json(*parts, obj=None):
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(json.dumps(obj, ensure_ascii=False))
    return path


def assistant_call(cid, name, arguments='{}'):
    return {'role': 'assistant', 'content': '',
            'tool_calls': [{'id': cid, 'type': 'function',
                            'function': {'name': name, 'arguments': arguments}}]}


def tool_result(cid, name, content, tool_details=None):
    m = {'role': 'tool', 'tool_call_id': cid, 'name': name, 'content': content}
    if tool_details is not None:
        m['tool_details'] = tool_details
    return m


def sb_row(cid, fn, tt=None, exc=None, active='True'):
    """A SANDBOX db row as saved by the source framework (string cells)."""
    return {'sandbox_message_index': '1', 'sender': 'AGENT' if cid else 'EXECUTION_ENVIRONMENT',
            'recipient': 'EXECUTION_ENVIRONMENT' if cid else 'USER', 'content': None,
            'openai_tool_call_id': cid, 'openai_function_name': fn,
            'conversation_active': active, 'tool_call_exception': exc, 'tool_trace': tt,
            'visible_to': None, 'entropy_data': None}


def sb_call_rows(cid, fn, native_name=None, exc=None):
    """Request row plus response row for one agent tool call."""
    rows = [sb_row(cid, fn)]
    if exc is not None:
        # Exception response rows in the real payload also carry a stale
        # summarize_the_task trace; reproduce that to test exclusion.
        rows.append(sb_row(cid, fn, exc=exc,
                           tt=[json.dumps({'tool_name': 'summarize_the_task', 'arguments': {}})]))
    else:
        rows.append(sb_row(cid, fn, tt=[json.dumps({'tool_name': native_name, 'arguments': {}, 'result': 'ok'})],
                           active='True', exc=None))
    return rows


def make_conversation_one():
    """One assistant message with two tool calls; the scrambled call resolves
    via the SANDBOX tool_trace of its call id."""
    return [
        {'role': 'system', 'content': 'sys'},
        {'role': 'user', 'content': 'u'},
        {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': 'a1', 'type': 'function',
             'function': {'name': 'get_current_timestamp', 'arguments': '{}'}},
            {'id': 'a2', 'type': 'function',
             'function': {'name': 'utilities_2', 'arguments': '{}'}}]},
        tool_result('a1', 'get_current_timestamp', '1763977470.0'),
        tool_result('a2', 'utilities_2', '1763977470.0'),
        {'role': 'assistant', 'content': 'done'},
    ]


def make_conversation_two():
    """Anomalies: an unresolved scrambled error call (exception row with a
    stale trace must not resolve it), a content-prefix fallback, a database
    namespace fallback, a duplicate call id, a call without id, a call without
    return, an orphan result, unparseable arguments, and tool errors."""
    return [
        {'role': 'system', 'content': 'sys'},
        {'role': 'user', 'content': 'u'},
        assistant_call('b1', 'summarize_0', '{"summary": "s"}'),
        tool_result('b1', 'summarize_0', '[SummaryTool] state summary'),
        assistant_call('b2', 'reminder_3', '{"content": "x"}'),
        tool_result('b2', 'reminder_3', '[]', {'database_update': {'REMINDER': [{'reminder_id': 'r1'}]}}),
        assistant_call('b3', 'utilities_9', '123'),
        tool_result('b3', 'utilities_9', 'TypeError: bad'),
        assistant_call('b1', 'summarize_0', '{"summary": "dup"}'),
        assistant_call('b4', 'search_reminder', '{"content": "y"}'),
        tool_result('b4', 'search_reminder', "ValueError: Parameter 'content' is not supported"),
        assistant_call(None, 'get_wifi_status', '{}'),
        assistant_call('b6', 'set_wifi_status', '{"x":'),
        tool_result('zz', 'search_reminder', 'orphan'),
        {'role': 'assistant', 'content': 'end'},
    ]


def execution_context(augmentations, allow, sandbox_rows, final_active, end_conversation):
    rows = [{'sandbox_message_index': '0', 'sender': None, 'recipient': None, 'content': None,
             'openai_tool_call_id': None, 'openai_function_name': None, 'conversation_active': 'True',
             'tool_call_exception': None, 'tool_trace': None, 'visible_to': None, 'entropy_data': None}]
    rows.extend(sandbox_rows)
    if end_conversation:
        rows.append(sb_row(None, None, tt=[json.dumps({'tool_name': 'end_conversation', 'arguments': {}})],
                           active=final_active))
    else:
        rows.append(sb_row(None, None, active=final_active))
    return {'_dbs': {'SANDBOX': rows, 'REMINDER': []}, 'interactive_console': None,
            'tool_allow_list': allow, 'tool_deny_list': None, 'trace_tool': True,
            'tool_augmentation_list': augmentations, 'preferred_tool_backend': 'DEFAULT'}


def rs_row(name, categories, **kw):
    row = {'name': name, 'categories': categories, 'traceback': None, 'exception_type': None,
           'milestone_similarity': 1, 'minefield_similarity': 0.0, 'similarity': 1,
           'turn_count': 4, 'milestone_mapping': {}, 'minefield_mapping': {}}
    row.update(kw)
    return row


ALLOW = ['get_current_timestamp', 'summarize_the_task', 'end_conversation',
         'search_reminder', 'set_wifi_status', 'get_wifi_status']


def scenario_specs():
    """(scenario, conversation, execution_context) per group-shared scenario."""
    return [
        (SCEN_ONE, make_conversation_one(),
         execution_context(['TOOL_NAME_SCRAMBLED'], ALLOW,
                           sb_call_rows('a1', 'get_current_timestamp', 'get_current_timestamp')
                           + sb_call_rows('a2', 'utilities_2', 'get_current_timestamp'),
                           final_active='False', end_conversation=True)),
        (SCEN_TWO, make_conversation_two(),
         execution_context([], ALLOW,
                           sb_call_rows('b3', 'utilities_9', exc='TypeError: bad')
                           + sb_call_rows('b4', 'search_reminder', exc="ValueError: Parameter 'content' is not supported"),
                           final_active='True', end_conversation=False)),
    ]


def build_fixture():
    """Return (TemporaryDirectory, project_root, manifest_path)."""
    tmp = tempfile.TemporaryDirectory()
    root = tmp.name
    raw = os.path.join(root, 'data', 'raw', 'public', 'toolsandbox_hepm', tsb.COMMIT)
    os.makedirs(os.path.join(raw, 'ToolSandbox', 'data'))
    with open(os.path.join(raw, 'README.md'), 'w') as f:
        f.write('# fixture readme\n')
    with open(os.path.join(raw, 'ToolSandbox', 'README.md'), 'w') as f:
        f.write('# fixture toolsandbox readme\n')
    rows = scenario_specs()
    groups = {
        GROUP_F: [(s, c, e, rs_row(s, cats, **kw)) for (s, c, e), (cats, kw) in zip(
            rows, [(['THREE_DISTRACTION_TOOLS', 'TOOL_NAME_SCRAMBLED'], {'milestone_similarity': 0.7, 'similarity': 0.7, 'turn_count': 5}),
                   (['NO_DISTRACTION_TOOLS', 'MULTIPLE_TOOL_CALL'], {'turn_count': 9})])],
        GROUP_T: [(s, c, e, rs_row(s, cats, **kw)) for (s, c, e), (cats, kw) in zip(
            rows, [(['THREE_DISTRACTION_TOOLS', 'TOOL_NAME_SCRAMBLED'], {'milestone_similarity': 0.9, 'similarity': 0.9, 'turn_count': 7}),
                   (['NO_DISTRACTION_TOOLS', 'MULTIPLE_TOOL_CALL'], {'milestone_similarity': None, 'minefield_similarity': None, 'similarity': None, 'exception_type': 'ValueError', 'turn_count': 11})])],
    }
    provenance = {GROUP_F: {'split': 'test', 'split_seed': 42, 'split_ratio': 0.8,
                            'git_sha': 'ffff0000 + local changes'},
                  GROUP_T: {'split': 'test', 'split_seed': 42, 'split_ratio': 0.8,
                            'git_sha': 'tttt0000 + local changes'}}
    for gdir, grows in groups.items():
        write_json(raw, 'ToolSandbox', 'data', gdir, 'result_summary.json',
                   obj={'per_scenario_results': [r[3] for r in grows], **provenance[gdir]})
        for scen, conv, ec, _ in grows:
            write_json(raw, 'ToolSandbox', 'data', gdir, 'trajectories', scen,
                       'conversation.json', obj=conv)
            write_json(raw, 'ToolSandbox', 'data', gdir, 'trajectories', scen,
                       'execution_context.json', obj=ec)
    files = []
    for dirpath, _, filenames in os.walk(raw):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            with open(full, 'rb') as f:
                data = f.read()
            files.append({'path': os.path.relpath(full, root), 'bytes': len(data),
                          'sha256': hashlib.sha256(data).hexdigest()})
    manifest = write_json(root, 'acquisition', 'manifest.json',
                          obj={'repository': 'fixture/repo', 'commit': tsb.COMMIT,
                               'status': 'complete', 'files': files})
    return tmp, root, manifest


def load_records(out):
    with open(os.path.join(out, 'per_trajectory.jsonl')) as f:
        return [json.loads(line) for line in f if line.strip()]


def test_multi_tool_call_message_and_sandbox_tool_trace_resolution():
    tmp, root, manifest = build_fixture()
    try:
        out = os.path.join(root, 'out')
        tsb.run(manifest, out, project_root=root)
        recs = {(r['group_directory'], r['scenario']): r for r in load_records(out)}
        r = recs[(GROUP_F, SCEN_ONE)]
        assert r['pairing']['tool_call_entries'] == 2
        assert r['multi_tool_call_assistant_messages'] == 1
        assert r['pairing']['paired_call_entries'] == 2
        assert r['call_resolution_counts'] == {'native_name': 1, 'sandbox_tool_trace': 1}
        assert r['native_identity_counts'] == {'get_current_timestamp': 2}
        assert r['called_name_counts'] == {'get_current_timestamp': 1, 'utilities_2': 1}
        assert r['activity_call_counts'] == {'datetime': 2}
        sa = r['sandbox_association']
        assert sa['sandbox_unique_call_ids'] == 2
        assert sa['sandbox_call_id_rows'] == 4
        assert sa['calls_matched_in_sandbox'] == 2
        assert sa['calls_with_id_not_in_sandbox'] == 0
        assert sa['sandbox_call_ids_with_clean_tool_trace'] == 2
        assert r['execution_context_facts']['final_conversation_active'] == 'False'
        assert r['execution_context_facts']['sandbox_end_conversation_tool_trace_rows'] == 1
    finally:
        tmp.cleanup()


def test_duplicate_missing_orphan_and_missing_return_counts():
    tmp, root, manifest = build_fixture()
    try:
        out = os.path.join(root, 'out')
        tsb.run(manifest, out, project_root=root)
        recs = {(r['group_directory'], r['scenario']): r for r in load_records(out)}
        p = recs[(GROUP_F, SCEN_TWO)]['pairing']
        assert p['tool_call_entries'] == 7
        assert p['calls_missing_id'] == 1
        assert p['calls_with_id'] == 6
        assert p['duplicate_call_id_entries'] == 1
        assert p['calls_with_id_without_return'] == 1   # only b6 lacks a return
        assert p['orphan_result_messages'] == 1
        assert p['tool_result_messages'] == 5
        assert p['call_result_name_mismatches'] == 0
        assert recs[(GROUP_F, SCEN_TWO)]['protocol_issue_counts']['unparseable_arguments'] == 1
        assert p['tool_call_entries'] == p['calls_with_id'] + p['calls_missing_id']
        assert p['calls_with_id'] == p['paired_call_entries'] + p['calls_with_id_without_return']
        assert p['tool_result_messages'] == p['results_with_id'] + p['results_missing_id']
        sa = recs[(GROUP_F, SCEN_TWO)]['sandbox_association']
        assert sa['calls_matched_in_sandbox'] == 2          # b3 and b4 only
        assert sa['calls_with_id_not_in_sandbox'] == 4
        assert sa['sandbox_call_ids_with_exception'] == 2
    finally:
        tmp.cleanup()


def test_unknown_is_sequence_boundary_and_transitions_do_not_cross():
    tmp, root, manifest = build_fixture()
    try:
        out = os.path.join(root, 'out')
        tsb.run(manifest, out, project_root=root)
        recs = {(r['group_directory'], r['scenario']): r for r in load_records(out)}
        r = recs[(GROUP_F, SCEN_TWO)]
        # b3 (utilities_9) has only an exception SANDBOX row whose trace is a
        # stale summarize_the_task entry; it must stay unresolved.
        assert r['activity_sequence'] == ['harness_summary', 'reminder', None, 'harness_summary',
                                          'reminder', 'settings', 'settings']
        tr = r['activity_transitions']
        assert tr['boundary_adjacent_pairs'] == 2
        assert not any('None' in k for k in tr['transition_counts'])
        assert tr['same_tool_transitions'] == 1   # settings -> settings
        assert tr['cross_tool_transitions'] == 3
        assert r['call_resolution_counts']['unresolved_scrambled'] == 1
        assert r['call_resolution_counts']['content_prefix_summary_tool'] == 2
        assert r['call_resolution_counts']['database_namespace_activity'] == 1
        assert r['call_resolution_counts']['native_name'] == 3
    finally:
        tmp.cleanup()


def test_tool_error_separated_from_task_result_and_cross_checked_with_sandbox():
    tmp, root, manifest = build_fixture()
    try:
        out = os.path.join(root, 'out')
        s = tsb.run(manifest, out, project_root=root)
        recs = {(r['group_directory'], r['scenario']): r for r in load_records(out)}
        r = recs[(GROUP_F, SCEN_TWO)]
        assert r['tool_result_error_count'] == 2
        assert r['tool_result_error_classes'] == {'TypeError': 1, 'ValueError': 1}
        # task evaluation fields stay as saved, never converted into success
        assert r['result_summary_row']['similarity'] == 1
        # SANDBOX exception cross-check
        e = s['tool_result_errors']['per_group'][GROUP_F]
        assert e['sandbox_exception_call_ids'] == 2
        assert e['content_regex_equals_sandbox_exception'] is True
        # harness exception counted separately from tool execution errors
        gt = s['termination_and_results']['per_group_result_fields'][GROUP_T]
        gf = s['termination_and_results']['per_group_result_fields'][GROUP_F]
        assert gt['exception_type_non_null'] == 1
        assert gf['exception_type_non_null'] == 0
        assert s['termination_and_results']['end_conversation_calls_per_group'] == {GROUP_F: 0, GROUP_T: 0}
    finally:
        tmp.cleanup()


def test_missing_fields_are_not_zero_filled():
    tmp, root, manifest = build_fixture()
    try:
        out = os.path.join(root, 'out')
        s = tsb.run(manifest, out, project_root=root)
        gt = s['termination_and_results']['per_group_result_fields'][GROUP_T]
        assert gt['milestone_similarity']['n'] == 1
        assert gt['milestone_similarity']['missing'] == 1
        assert gt['similarity']['missing'] == 1
        md = s['group_comparison']['same_scenario_metric_diffs']
        assert md['milestone_similarity']['n_scenario_pairs'] == 1
        assert md['similarity']['n_scenario_pairs'] == 1
        assert md['milestone_similarity']['diff_stats']['median'] == 0.9 - 0.7
        assert md['turn_count']['n_scenario_pairs'] == 2
        recs = {(r['group_directory'], r['scenario']): r for r in load_records(out)}
        assert recs[(GROUP_T, SCEN_TWO)]['result_summary_row']['milestone_similarity'] is None
    finally:
        tmp.cleanup()


def test_dual_activity_stat_denominators():
    tmp, root, manifest = build_fixture()
    try:
        out = os.path.join(root, 'out')
        s = tsb.run(manifest, out, project_root=root)
        ti = s['tool_interface']['per_group'][GROUP_F]
        # datetime occurs only in task_one (2 calls); task_two has 0.
        assert ti['activity_trajectories_with_calls']['datetime'] == 1
        cond = ti['activity_calls_per_trajectory_conditional_stats']['datetime']
        full = ti['activity_calls_per_trajectory_all_trajectories_stats']['datetime']
        assert cond['n'] == 1 and cond['min'] == 2 and cond['max'] == 2
        assert full['n'] == 2 and full['min'] == 0 and full['max'] == 2 and full['median'] == 1.0
        # every activity's all-trajectory denominator equals the group size
        for a, st in ti['activity_calls_per_trajectory_all_trajectories_stats'].items():
            assert st['n'] == 2
    finally:
        tmp.cleanup()


def test_run_provenance_and_final_conversation_active_reported():
    tmp, root, manifest = build_fixture()
    try:
        out = os.path.join(root, 'out')
        s = tsb.run(manifest, out, project_root=root)
        prov = {g['directory']: g['result_summary_run_provenance'] for g in s['inputs']['groups']}
        assert prov[GROUP_F] == {'split': 'test', 'split_seed': 42, 'split_ratio': 0.8,
                                 'git_sha': 'ffff0000 + local changes'}
        assert prov[GROUP_T]['git_sha'] == 'tttt0000 + local changes'
        tr = s['termination_and_results']
        assert tr['final_conversation_active_counts'] == {GROUP_F: {'False': 1, 'True': 1},
                                                          GROUP_T: {'False': 1, 'True': 1}}
        assert tr['sandbox_end_conversation_tool_trace_trajectories'] == {GROUP_F: 1, GROUP_T: 1}
        recs = {(r['group_directory'], r['scenario']): r for r in load_records(out)}
        assert recs[(GROUP_F, SCEN_TWO)]['execution_context_facts']['final_conversation_active'] == 'True'
    finally:
        tmp.cleanup()


def test_input_hash_mismatch_and_missing_registered_file_rejected():
    tmp, root, manifest = build_fixture()
    try:
        out = os.path.join(root, 'out')
        target = os.path.join(root, 'data', 'raw', 'public', 'toolsandbox_hepm', tsb.COMMIT,
                              'ToolSandbox', 'data', GROUP_F, 'trajectories', SCEN_TWO,
                              'conversation.json')
        with open(target, 'rb') as f:
            original = f.read()
        with open(target, 'wb') as f:
            f.write(original + b' ')
        try:
            tsb.run(manifest, out, project_root=root)
            raise AssertionError('expected refusal on hash mismatch')
        except ValueError:
            pass
        assert not os.path.exists(out)
        with open(target, 'wb') as f:
            f.write(original)
        os.unlink(target)
        try:
            tsb.run(manifest, os.path.join(root, 'out2'), project_root=root)
            raise AssertionError('expected refusal on missing registered file')
        except ValueError:
            pass
    finally:
        tmp.cleanup()


def test_output_dir_exists_refused():
    tmp, root, manifest = build_fixture()
    try:
        out = os.path.join(root, 'out')
        os.makedirs(out)
        try:
            tsb.run(manifest, out, project_root=root)
            raise AssertionError('expected refusal on existing output dir')
        except ValueError:
            pass
    finally:
        tmp.cleanup()


def test_full_entry_generates_outputs_and_conserves_counts():
    tmp, root, manifest = build_fixture()
    try:
        out = os.path.join(root, 'out')
        s = tsb.run(manifest, out, project_root=root)
        assert s['schema'] == 'toolsandbox-hepm-behavior-v2'
        # 2 README + 2 result_summary + 4 conversation + 4 execution_context
        assert s['inputs']['payload_files_verified'] == 12
        assert s['coverage']['shared_scenario_keys'] == 2
        assert s['coverage']['per_group'][GROUP_F]['base_scenario_count'] == 2
        recs = load_records(out)
        assert len(recs) == 4
        assert s['conservation_checks']['per_trajectory_records'] == 4
        assert s['conservation_checks']['records_equal_sum_of_groups'] is True
        call_sum = sum(r['pairing']['tool_call_entries'] for r in recs)
        assert call_sum == s['conservation_checks']['call_entries_sum']
        assert set(s['v1_to_v2_corrections']) == {'scrambled_resolution', 'run_provenance',
                                                  'activity_stats_denominators', 'delivery_wording'}
        for name in ('summary.md', 'summary.json', 'per_trajectory.jsonl', 'manifest.json'):
            assert os.path.isfile(os.path.join(out, name))
        with open(os.path.join(out, 'manifest.json')) as f:
            m = json.load(f)
        assert m['manifest_self_hash_excluded'] is True
        assert {x['path'] for x in m['outputs']} == {'summary.md', 'summary.json', 'per_trajectory.jsonl'}
        assert len(m['inputs']) == 13  # acquisition manifest + 12 payload files
        assert any('scripts/toolsandbox_hepm_behavior.py' in x['path'] for x in m['analysis_code'])
        assert s['coverage']['per_group'][GROUP_F]['variant_suffix_counts'] == {
            '3_distraction_tools_tool_name_scrambled': 1}
        assert 'summarize_the_task' in s['tool_interface']['harness_tools']
        assert 'end_conversation' in s['tool_interface']['harness_tools']
    finally:
        tmp.cleanup()


def test_strip_variants_keeps_official_tokens():
    base, suffixes = tsb.strip_variants('find_x_low_battery_mode_alt_10_distraction_tools')
    assert base == 'find_x_low_battery_mode_alt'
    assert suffixes == ['10_distraction_tools']
    base, suffixes = tsb.strip_variants('find_days_till_holiday')
    assert base == 'find_days_till_holiday' and suffixes == []


def test_sandbox_tool_trace_name_parsing():
    assert tsb.sandbox_tool_trace_name(None) is None
    assert tsb.sandbox_tool_trace_name('null') is None
    assert tsb.sandbox_tool_trace_name([json.dumps({'tool_name': 'add_contact', 'arguments': {}})]) == 'add_contact'
    assert tsb.sandbox_tool_trace_name(json.dumps({'tool_name': 'x'})) == 'x'
    assert tsb.sandbox_tool_trace_name(['not json']) is None
    assert tsb.sandbox_tool_trace_name([{'tool_name': 'dict_row'}]) == 'dict_row'
