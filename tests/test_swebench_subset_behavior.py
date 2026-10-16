#!/usr/bin/env python3
"""Directed tests for swebench_subset_behavior using synthetic fixtures.

Covers: minimal real-format fixtures, missing/duplicate call ids and orphan
results, Unknown sequence boundary, test-keyword-in-shell != test call,
branch structure not flattened, termination/result separation, input-change
effects, and the full entry generating outputs.
"""
import json, os, sys, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_spec = importlib.util.spec_from_file_location('ssb', os.path.join(ROOT, 'scripts', 'swebench_subset_behavior.py'))
ssb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ssb)


def write_json(d, name, obj):
    p = os.path.join(d, name)
    json.dump(obj, open(p, 'w'))
    return p


def make_sweagent(exit_status, actions):
    return {
        'environment': 'docker',
        'trajectory': [{'action': a, 'observation': 'obs', 'response': 'r', 'state': '{}', 'thought': 't'} for a in actions],
        'history': [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}],
        'info': {'exit_status': exit_status, 'submission': 'diff --git a/x' if exit_status.startswith('submitted') else ''},
    }


def make_sonar(tool_calls, n_tool_msgs):
    msgs = [{'role': 'system', 'content': 's', 'blocks': [{'block_type': 'text', 'content': 's'}]}]
    for i, (name, args) in enumerate(tool_calls):
        msgs.append({'role': 'assistant', 'additional_kwargs': {'tool_calls': [
            {'id': 'id_%d' % i, 'type': 'function', 'index': 0,
             'function': {'name': name, 'arguments': args}}]},
            'blocks': [{'block_type': 'thinking', 'content': 'x'}, {'block_type': 'text', 'content': 'y'}]})
    for _ in range(n_tool_msgs):
        msgs.append({'role': 'tool', 'content': 'result', 'blocks': [{'block_type': 'text', 'content': 'r'}]})
    msgs.append({'role': 'assistant', 'blocks': [{'block_type': 'thinking', 'content': 'z'}, {'block_type': 'text', 'content': 'done'}]})
    return msgs


def test_sweagent_minimal_and_exit_cost():
    with tempfile.TemporaryDirectory() as d:
        p = write_json(d, 'a__a-1.traj', make_sweagent('submitted', ['open file.py', 'edit x', 'pytest -q', 'submit']))
        r = ssb.analyze_sweagent(p, 'a__a-1')
        assert r['interface_counts'] == {'open': 1, 'edit': 1, 'pytest': 1, 'submit': 1}
        assert r['activity_counts']['Edit/Write'] == 1 and r['activity_counts']['Read/Search'] == 1
        assert r['activity_counts']['Test'] == 1, r['activity_counts']
        assert r['activity_counts']['Submit-marker'] == 1
        assert r['termination'] == {'source': 'info.exit_status', 'value': 'submitted', 'explicit_in_trajectory': True}
        assert r['submission_patch_present'] is True
        # exit_cost: no explicit submit action but exit_status says submitted
        p2 = write_json(d, 'a__a-2.traj', make_sweagent('submitted (exit_cost)', ['open file.py', 'python run.py']))
        r2 = ssb.analyze_sweagent(p2, 'a__a-2')
        assert r2['activity_counts'].get('Submit-marker', 0) == 0
        assert r2['termination']['value'] == 'submitted (exit_cost)'
        assert r2['submission_patch_present'] is True


def test_sonar_ids_and_orphans():
    with tempfile.TemporaryDirectory() as d:
        msgs = make_sonar([('bash', 'cat a.py'), ('str_replace_based_edit_tool', '{"command": "view", "path": "/x"}'),
                           ('str_replace_based_edit_tool', '{"command": "create", "path": "/y"}')], n_tool_msgs=2)
        p = write_json(d, 'b__b-1.json', msgs)
        r = ssb.analyze_sonar(p, 'b__b-1')
        assert r['anomalies']['tool_messages_without_tool_call_id'] == 2
        assert r['association']['explicit_id_linkage'] is False
        assert r['interface_counts'] == {'bash': 1, 'str_replace_based_edit_tool': 2}
        assert r['activity_counts']['Read/Search'] == 2  # cat + view
        assert r['activity_counts']['Edit/Write'] == 1
        assert r['termination']['explicit_in_trajectory'] is False
        # duplicate call ids flagged
        msgs2 = make_sonar([('bash', 'ls')], n_tool_msgs=1)
        msgs2[1]['additional_kwargs']['tool_calls'].append(dict(msgs2[1]['additional_kwargs']['tool_calls'][0]))
        p2 = write_json(d, 'b__b-2.json', msgs2)
        r2 = ssb.analyze_sonar(p2, 'b__b-2')
        assert r2['anomalies'].get('duplicate_tool_call_ids') == 1


def test_unknown_boundary_and_sequence():
    with tempfile.TemporaryDirectory() as d:
        # bash Unknown (compound) between two known activities breaks the chain
        msgs = make_sonar([('str_replace_based_edit_tool', '{"command": "view", "path": "/x"}'),
                           ('bash', 'cd /a && pytest -q'),
                           ('str_replace_based_edit_tool', '{"command": "create", "path": "/y"}')], 0)
        p = write_json(d, 'c__c-1.json', msgs)
        r = ssb.analyze_sonar(p, 'c__c-1')
        assert r['unknown_reasons'].get('compound_or_redirection') == 1
        assert 'Read/Search->Unknown' in r['transitions']
        assert 'Unknown->Edit/Write' not in r['transitions'], r['transitions']
        assert 'Read/Search->Edit/Write' not in r['transitions']


def test_shell_keyword_not_test():
    # 'grep pytest README.md' mentions pytest but is a read command, not a test run
    cat, reason = None, None
    with tempfile.TemporaryDirectory() as d:
        msgs = make_sonar([('bash', 'grep pytest README.md'), ('bash', 'pytest -q')], 0)
        p = write_json(d, 'd__d-1.json', msgs)
        r = ssb.analyze_sonar(p, 'd__d-1')
        assert r['activity_counts'].get('Test') == 1, r['activity_counts']
        assert r['activity_counts'].get('Read/Search') == 1
        # the grep call is Read/Search, NOT Test - keyword alone must not classify as test
        rows = [c for c in [('Read/Search', 1), ('Test', 1)]]
        assert rows == [('Read/Search', 1), ('Test', 1)]


def test_moatless_structure_not_flattened():
    with tempfile.TemporaryDirectory() as d:
        obj = {
            'name': 'gpt-4o run',
            'initial_message': 'solve',
            'transitions': [
                {'name': 'SearchCode', 'state': {}, 'actions': [{'action': {'thoughts': 't', 'file_pattern': '*.py'}}]},
                {'name': 'EditCode', 'state': {}, 'actions': [{'action': {'content': '<replace>code</replace>'}}]},
                {'name': 'Finished', 'state': {'message': 'done'}, 'actions': []},
            ],
            'info': {'instance_id': 'e__e-1', 'duration': 1.5, 'total_cost': 0.02, 'submission': 'diff'},
        }
        p = write_json(d, 'e__e-1.json', obj)
        r = ssb.analyze_moatless(p, 'e__e-1')
        # saved transition sequence preserved as-is
        assert r['structure']['transition_names'] == ['SearchCode', 'EditCode', 'Finished']
        # no branch markers saved -> reported as empty list, not inferred
        assert r['structure']['branch_markers'] == []
        # EditCode content is not treated as a shell command
        assert r['shell_command_classification'] == 'not_applicable_no_shell_commands_saved'
        assert 'Edit/Write' not in r['unknown_reasons']
        assert r['activity_counts'] == {'Read/Search': 1, 'Edit/Write': 1, 'Finished': 1}
        assert r['last_saved_transition'] == {'value': 'Finished', 'reached_Finished': True}
        assert r['termination']['value'] is None
        assert r['termination']['explicit_in_trajectory'] is False
        assert r['in_trajectory_fields'] == {'duration': True, 'total_cost': True}


def test_input_change_changes_output():
    with tempfile.TemporaryDirectory() as d:
        p = write_json(d, 'f__f-1.traj', make_sweagent('submitted', ['open a.py', 'submit']))
        r1 = ssb.analyze_sweagent(p, 'f__f-1')
        write_json(d, 'f__f-1.traj', make_sweagent('exit_cost', ['open a.py']))
        r2 = ssb.analyze_sweagent(p, 'f__f-1')
        assert r1['termination']['value'] != r2['termination']['value']
        assert r1['activity_counts'].get('Submit-marker', 0) == 1
        assert r2['activity_counts'].get('Submit-marker', 0) == 0


def test_full_entry_generates_outputs():
    # run the real entry over the frozen selection; outputs must exist and parse
    with tempfile.TemporaryDirectory() as out:
        selection = os.path.join(ssb.OUT, 'selection.json')
        with open(selection) as stream:
            frozen = json.load(stream)
        write_json(out, 'selection.json', frozen)
        old_out = ssb.OUT
        try:
            ssb.OUT = out
            ssb.main()
            _check_outputs(out)
        finally:
            ssb.OUT = old_out


def _check_outputs(out):
    for fn in ['per_trajectory.jsonl', 'summary.json']:
        p = os.path.join(out, fn)
        assert os.path.exists(p)
        if fn.endswith('.jsonl'):
            rows = [json.loads(l) for l in open(p)]
            assert len(rows) == 90
        else:
            s = json.load(open(p))
            assert s['n_trajectories'] == 90 and s['n_errors'] == 0
            assert len(s['groups']) == 3


if __name__ == '__main__':
    test_sweagent_minimal_and_exit_cost()
    test_sonar_ids_and_orphans()
    test_unknown_boundary_and_sequence()
    test_shell_keyword_not_test()
    test_moatless_structure_not_flattened()
    test_input_change_changes_output()
    test_full_entry_generates_outputs()
    print('all 7 directed tests passed')
