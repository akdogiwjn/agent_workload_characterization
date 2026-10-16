"""Offline tests. No benchmark/framework/model imports or shell execution."""
import hashlib
import gzip
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from agent_workload_characterization.analyzers.public_operations import (
    classify_call, classify_command, shares,
)
from scripts.public_trace_operations import (
    Inputs, PROJECT, REBENCH, SWEBENCH, ACQUISITIONS, PACKAGES,
    aggregate, coding_summary, extract_structured, summarize_units, run,
    _json_object_records, _analyze_swebench_bytes, pairing_summary, _lingxi_text, _globant_text, classify_unit,
    valid_native_tool_identifier,
)


class TestOperations(unittest.TestCase):
    def test_split_read_operations(self):
        cases = {'find . -name a.py': 'file_locate', 'rg --files': 'file_locate',
                 'rg foo src': 'content_search', 'grep pytest a.py': 'content_search',
                 'sed -n "20,40p" a.py': 'file_view', 'cat a.py': 'file_view',
                 'sed -i s/a/b/ a.py': 'edit_write', 'cp a.py b.py': 'file_manage'}
        for command, expected in cases.items():
            self.assertEqual(classify_command(command)['operation'], expected, command)

    def test_actual_test_and_build_not_keywords(self):
        cases = {'python -m pytest -q': 'test', 'python tests/runtests.py': 'test',
                 'timeout 5 python -m unittest': 'test', 'npm run test': 'test',
                 'cargo test': 'test', 'python setup.py build_ext --inplace': 'build',
                 'cmake --build build': 'build', 'pip install -e .': 'environment',
                 'echo pytest': 'other', 'python -c \'print("pytest")\'': 'script_execute',
                 'pytest --help': 'other', 'pytest_fake a.py': 'unknown'}
        for command, expected in cases.items():
            self.assertEqual(classify_command(command)['operation'], expected, command)

    def test_quotes_and_wrappers(self):
        cases = {'cd /repo && pytest -q': 'test', 'rg "a; b && c" a.py | head -5': 'mixed',
                 'python -c \'print("a;b|c")\'': 'script_execute',
                 'X=1 python -m pytest': 'test', '/bin/bash -lc "cd /repo && cat a.py"': 'file_view'}
        for command, expected in cases.items():
            self.assertEqual(classify_command(command)['operation'], expected, command)

    def test_unknown_component_is_not_dropped(self):
        r = classify_command('cat a.py && strange_tool a.py')
        self.assertEqual(r['operation'], 'partial')
        self.assertIn('unknown', r['components'])
        self.assertEqual(classify_command('find . -exec sh {}')['operation'], 'partial')
        self.assertEqual(classify_command('cat "unterminated')['operation'], 'unknown')

    def test_python_source_never_evaluated(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)/'must_not_exist'
            source = f'python -c \'open("{target}","w").write("pytest")\''
            self.assertEqual(classify_command(source)['operation'], 'edit_write')
            self.assertFalse(target.exists())
            self.assertEqual(classify_command('python -c \'def f():\n open("x","w")\'')['operation'], 'script_execute')
            self.assertEqual(classify_command('python -c \'x.write_text("x")\'')['operation'], 'script_execute')

    def test_expansions_and_heredocs_unresolved(self):
        for command in ('echo $(pytest)', 'echo `pytest`', "python <<'PY'\nprint('pytest')"):
            self.assertEqual(classify_command(command)['operation'], 'unknown', command)

    def test_literal_redirections_and_quoted_symbols(self):
        cases = {'cd /repo && pytest -q 2>&1 | head -20': 'mixed',
                 'pytest > result.txt': 'test', 'echo x > a.py': 'edit_write',
                 'cat < a.py': 'file_view', 'grep "a > b" x.py': 'content_search'}
        for command, expected in cases.items():
            self.assertEqual(classify_command(command)['operation'], expected, command)

    def test_native_tools_not_all_bash(self):
        self.assertEqual(classify_call('Read', {'file_path': 'x'})['operation'], 'file_view')
        self.assertEqual(classify_call('Grep', {})['operation'], 'content_search')
        self.assertEqual(classify_call('Glob', {})['operation'], 'file_locate')
        self.assertEqual(classify_call('str_replace_based_edit_tool', {'command': 'view'})['operation'], 'file_view')
        self.assertEqual(classify_call('shell', {'command': ['bash', '-lc', 'pytest -q']})['operation'], 'test')
        self.assertEqual(classify_call('execute_bash', {'command': 'pytest -q'})['operation'], 'test')
        self.assertEqual(classify_call('stringReplaceEditor', {'command': 'view', 'path': 'x'})['operation'], 'file_view')
        self.assertEqual(classify_call('sendShellInput', {'input': 'pytest -q', 'isControlCharacter': False})['operation'], 'test')
        self.assertEqual(classify_call('sendShellInput', {'input': 'C', 'isControlCharacter': True})['operation'], 'other')

    def test_literal_heredoc_not_executed(self):
        self.assertEqual(classify_command("cd /repo && python3 - <<'PY'\nprint('pytest')\nPY")['operation'], 'script_execute')
        self.assertEqual(classify_command("cat >a.py <<'EOF'\nprint('pytest')\nEOF")['operation'], 'edit_write')
        self.assertEqual(classify_command("replace <<'EOF'\na: b\nEOF")['operation'], 'edit_write')
        self.assertEqual(classify_command("python <<'PY'\nprint('x')\nPY\npytest -q")['operation'], 'mixed')
        self.assertEqual(classify_command("cat <<EOF\nhi\nEOF")['operation'], 'unknown')
        self.assertEqual(classify_command("cat <<A <<B\na\nA\nb\nB")['operation'], 'unknown')
        self.assertEqual(classify_command("echo '<<PY'\npytest -q")['operation'], 'mixed')
        self.assertEqual(classify_command("cat >a <<EOF\n$(pytest)\nEOF")['operation'], 'partial')

    def test_one_label_per_call_and_prevalence(self):
        calls = [{'tool': 'bash', 'arguments': {'command': 'cat a && pytest -q'}, 'position': 1},
                 {'tool': 'Read', 'arguments': {}, 'position': 2},
                 {'tool': 'Read', 'arguments': {}, 'position': 3}]
        row = summarize_units('SWE-rebench', 'p', 'r__r-1', {'path': 'x'}, 'saved_tool_call', calls)
        out = aggregate([row])
        self.assertEqual(out['operations']['denominator'], 3)
        self.assertEqual(out['native_tools']['counts']['Read'], 2)
        self.assertEqual(out['tool_record_presence']['Read'], 1)
        self.assertEqual(out['operations']['counts']['mixed'], 1)
        self.assertEqual(sum(out['operations']['percent_all'].values()), 100)
        self.assertEqual(out['syntactic_components']['denominator'], 4)
        self.assertEqual(out['operation_call_presence']['counts']['test'], 1)
        self.assertEqual(out['operation_call_presence']['counts']['file_view'], 3)

    def test_protocol_counts_and_no_prompt_mining(self):
        messages = [{'role': 'user', 'content': 'Run pytest'},
                    {'role': 'assistant', 'content': 'I might run pytest', 'tool_calls': [
                        {'function': {'name': 'bash', 'arguments': '{"command":"cat a"}'}},
                        {'function': {'name': 'bash', 'arguments': 'bad json'}}]}]
        fmt, calls = extract_structured(messages)
        self.assertEqual(fmt, 'explicit_message_tool_calls'); self.assertEqual(len(calls), 2)
        row = summarize_units('SWE-bench', 'g', 'r-1', {}, 'saved_tool_call', calls)
        self.assertEqual(row['operation_counts'], {'file_view': 1, 'unknown': 1})
        self.assertIsNone(extract_structured([{'role': 'assistant', 'content': '```bash\npytest\n```'}])[1])

    def test_real_source_protocol_families(self):
        # Solver operations and retrieval are separate saved event units.
        events = [{'id': 'a', 'event_type': 'execution', 'event_data': {'command': 'pytest -q', 'exit_code': 0}},
                  {'id': 'b', 'event_type': 'retrieval', 'event_data': {'query': 'symbol'}}]
        groups, returns, duplicates, schema, _ = _json_object_records(events, '20240920_solver')
        self.assertEqual(schema, 'solver_event_list')
        self.assertEqual([kind for kind, _ in groups], ['saved_operation_event', 'saved_retrieval_event'])
        self.assertEqual(groups[0][1][0]['call_id'], 'a')
        self.assertEqual(len(returns), 1)
        self.assertEqual(summarize_units('SWE-bench', 'solver', 'repo-1', {}, groups[0][0], groups[0][1], returns)['operation_counts'], {'test': 1})

        # Anthropic tool_use/result blocks preserve IDs; identical context replay
        # is not counted twice, while a new ID with the same command is real.
        call = {'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'c1', 'name': 'bash', 'input': {'command': 'pytest -q'}}]}
        messages = [call, call, {'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'c2', 'name': 'bash', 'input': {'command': 'pytest -q'}}]},
                    {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'c1', 'content': 'ok'}]}]
        groups, returns, duplicates, schema, _ = _json_object_records({'llm_call_data': messages}, '20241212_epam')
        self.assertEqual(schema, 'anthropic_tool_use_messages')
        self.assertEqual(len(groups[0][1]), 2)
        self.assertEqual(duplicates['exact'], 1)
        pair = pairing_summary(groups[0][1], returns, duplicates)
        self.assertEqual(pair['paired_1_to_1_by_id_count'], 1)
        self.assertEqual(pair['call_only_id_count'], 1)

    def test_explicit_action_boundaries_and_no_prompt_examples(self):
        marscode = [{'role': 'user', 'content': '### Action:\n```bash\npytest\n```'},
                    {'role': 'assistant', 'content': '### Action:\n```bash\nrg foo src | head\n```'},
                    {'role': 'assistant', 'content': 'Thought: maybe run pytest\n```bash\npytest\n```'}]
        schema, units = extract_structured(marscode, '20241125_marscode-agent-dev')
        self.assertEqual(schema, 'marscode_fenced_action_messages')
        self.assertEqual(len(units), 1)
        self.assertEqual(summarize_units('SWE-bench', 'marscode', 'repo-1', {}, 'saved_action_or_tool_call', units)['operation_counts'], {'mixed': 1})

        learn = ['Let me inspect.\n<execute_bash>ls</execute_bash>\nUSER: OBSERVATION: files',
                 'Now edit.\n<file_edit path="x.py">x=1</file_edit>']
        schema, units = extract_structured(learn, '20250110_learn_by_interact_claude3.5')
        self.assertEqual(schema, 'learn_by_interact_action_tag_messages')
        self.assertEqual(len(units), 2)
        self.assertEqual(summarize_units('SWE-bench', 'learn', 'repo-1', {}, 'saved_action_or_tool_call', units)['operation_counts'], {'file_locate': 1, 'edit_write': 1})
        self.assertIsNone(extract_structured(learn)[1])

    def test_xml_calls_only_in_confirmed_protocol_groups(self):
        messages = [{'role': 'assistant', 'content': '<function=execute_bash><parameter=command>cat x</parameter></function>'}]
        self.assertIsNone(extract_structured(messages)[1])
        self.assertEqual(len(extract_structured(messages, '20250616_Skywork-SWE-32B')[1]), 1)
        antml = [{'role': 'assistant', 'content': '<antml:function_calls><antml:invoke name="bash"><antml:parameter name="command">cat x</antml:parameter></antml:invoke></antml:function_calls>'},
                 {'role': 'assistant', 'content': '<function_results>ok</function_results>'}]
        schema, units = extract_structured(antml, '20250522_tools_claude-4-opus')
        self.assertEqual(schema, 'claude_antml_function_calls')
        self.assertEqual(len(units), 1)

    def test_lingxi_heading_action_call_and_return_are_separate(self):
        text = ('### 🎯 Action\nview_directory({\'depth\': 3})\n\n## Step 2\n'
                '### 👁️ Observation\nFound files\n\n### 🎯 Action\n'
                "bash({'command': 'cd src && pytest -q'})\n\n## Step 3\n"
                '### 👁️ Observation\nTests passed\n')
        units, returns = _lingxi_text(text)
        self.assertEqual([u['tool'] for u in units], ['view_directory', 'bash'])
        self.assertEqual([classify_unit(u)['operation'] for u in units], ['file_locate', 'test'])
        self.assertEqual(len(returns), 2)
        summary = summarize_units('SWE-bench', 'lingxi', 'repo-1', {}, 'saved_action_or_tool_call', units, returns)
        self.assertEqual(summary['operation_counts'], {'file_locate': 1, 'test': 1})
        self.assertEqual(summary['call_return_evidence']['return_record_count'], 2)
        self.assertEqual(summary['call_return_evidence']['paired_1_to_1_by_id_count'], 0)

    def test_globant_toolu_ids_are_calls_not_success_results(self):
        text = ('Suggested tool call (toolu_abc123): search_codebase\nArguments: \n'
                '{"search_term":"option directive"}\n*****\n'
                'Suggested tool call (toolu_def456): read_file\n')
        units, returns, detail = _globant_text(text)
        self.assertEqual([u['call_id'] for u in units], ['toolu_abc123', 'toolu_def456'])
        self.assertEqual(detail['structured_argument_blocks'], 1)
        self.assertEqual(detail['missing_or_invalid_argument_blocks'], 1)
        self.assertEqual(returns, [])
        summary = summarize_units('SWE-bench', 'globant', 'repo-1', {}, 'saved_tool_call', units, returns)
        self.assertEqual(summary['operation_counts'], {'content_search': 1, 'file_view': 1})
        self.assertEqual(summary['call_return_evidence']['call_event_count'], 2)
        self.assertEqual(summary['call_return_evidence']['return_record_count'], 0)

    def test_non_identifier_tool_field_is_unknown_without_exporting_text(self):
        long_value = 'assistant response body\n' + ('source text ' * 40)
        self.assertFalse(valid_native_tool_identifier(long_value))
        self.assertTrue(valid_native_tool_identifier('str_replace_editor'))
        unit = {'tool': 'unparsed_tool_identity', 'tool_identity_status': 'unparsed',
                'raw_tool_name_length': len(long_value),
                'raw_tool_name_sha256': hashlib.sha256(long_value.encode()).hexdigest(),
                'arguments': {'command': 'pytest'}, 'position': 7}
        row = summarize_units('SWE-rebench', 'fixture', 'task-1', {}, 'saved_tool_call', [unit])
        self.assertEqual(row['operation_counts'], {'unknown': 1})
        self.assertEqual(row['native_tool_counts'], {'unparsed_tool_identity': 1})
        self.assertEqual(row['unparsed_native_tool_identity_count'], 1)
        serialized = json.dumps(row)
        self.assertNotIn(long_value, serialized)
        self.assertEqual(row['unparsed_native_tool_identities'][0]['sha256'],
                         hashlib.sha256(long_value.encode()).hexdigest())

    def test_bad_jsonl_is_partial_but_retains_explicit_calls(self):
        data = b'{"messages":[{"role":"assistant","tool_calls":[{"id":"1","function":{"name":"bash","arguments":"{\\"command\\":\\"pytest\\"}"}}]}]}\nnot-json\n'
        got = _analyze_swebench_bytes('x.jsonl', '20241125_enginelabs', data)
        self.assertEqual(got['status'], 'process_partial_or_ambiguous')
        self.assertEqual(got['jsonl_invalid_line_count'], 1)
        self.assertEqual(got['unit_count'], 1)
        self.assertEqual(got['reason_code'], 'jsonl_rows_include_unparsed_lines')

    def test_sweagent_and_transitions_have_different_units(self):
        fmt, calls = extract_structured({'trajectory': [{'action': 'edit a.py'}, {'action': 'pytest -q'}]})
        row = summarize_units('SWE-bench', 'g', 'r-1', {}, fmt, calls)
        self.assertEqual(row['operation_counts'], {'edit_write': 1, 'test': 1})
        fmt, calls = extract_structured({'transitions': [{'name': 'SearchCode'}, {'name': 'Finished'}]})
        row2 = summarize_units('SWE-bench', 'h', 'r-1', {}, fmt, calls)
        out = coding_summary([row, row2])
        self.assertEqual(len(out['groups']), 2)
        self.assertEqual(out['swe_rebench_pooled']['operations']['denominator'], 0)

    def test_hash_tampering_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'input.json'; p.write_text('{}')
            expected = {'bytes': 2, 'sha256': hashlib.sha256(b'{}').hexdigest()}
            inputs = Inputs(td); inputs.json('input.json', expected)
            p.write_text('[]')
            with self.assertRaises(ValueError): inputs.json('input.json', expected)

    def test_empty_denominator_is_null_not_zero_percent(self):
        self.assertEqual(shares({})['denominator'], 0)
        self.assertEqual(shares({'unknown': 0})['percent_all']['unknown'], None)

    def test_complete_offline_report_in_temporary_project(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            def put(name, data):
                p = root/name; p.parent.mkdir(parents=True, exist_ok=True)
                raw = data if isinstance(data, bytes) else data.encode() if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode()
                p.write_bytes(raw)
                return {'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            def pack(name, outputs, extra_inputs=()):
                records = [put('reports/analysis/'+name+'/'+leaf, data) for leaf,data in outputs.items()]
                put('reports/analysis/'+name+'/manifest.json', {'inputs': list(extra_inputs), 'outputs': records})
            raw = (json.dumps({'trajectory_id': 't', 'participant': {'key': 'p'}, 'instance_id': 'r__r-1',
                    'events': [{'type': 'tool_call', 'tool': 'bash', 'input': {'command': 'cat "a\u2028b" && pytest -q'}}]}, ensure_ascii=False)+'\n').encode()
            shard = put(REBENCH+'/trajectories/p/run_0.jsonl.gz', gzip.compress(raw))
            put(REBENCH+'/index.jsonl', json.dumps({'path': 'trajectories/p/run_0.jsonl.gz', 'rows': 1, 'content_sha256': hashlib.sha256(raw).hexdigest()})+'\n')
            pack(PACKAGES[0], {'summary.json': {'scope': {'record_count': 1}, 'native_tool_counts': {'bash': 1},
                 'coverage': {'shards': [{**shard, 'path': 'trajectories/p/run_0.jsonl.gz'}]}}})
            swe_path = SWEBENCH+'/experiments/g/trajs/r__r-1.traj'
            swe_data = {'trajectory': [{'action': 'open a.py', 'observation': 'file'}, {'action': 'edit a.py'}]}
            swe = put(swe_path, swe_data)
            for acq in ACQUISITIONS:
                put('data/catalog/public_trace_acquisition/'+acq+'/manifest.json', {'inputs': [{**swe, 'role': 'trajectory'}]})
            pack(PACKAGES[1], {'summary.json': {'groups': {'g': {'interface_totals': {'open': 1, 'edit': 1}}}},
                 'summary.md': 'sweagent 组 1 个 action', 'selection.json': {'groups': [{'submission': 'g', 'items': [dict(swe, file=swe['path'])]}]}})
            source = 'website_demo/m/tasks/001/traj.jsonl'
            action = put('data/raw/public/osworld2_trajectory_light/'+source,
                         json.dumps({'action': {'action_type': 'computer_call', 'input': {'action': 'left_click'}}})+'\n')
            osrow = {'source_file': source, 'task_key': '001', 'model': 'm', 'native_action_record_count': 1,
                     'native_representation_status': 'applicable', 'static_category_counts': {'click': 1}, 'analysis_status': 'partial'}
            pack(PACKAGES[2], {'summary.json': {}, 'per_trajectory.jsonl': json.dumps(osrow)+'\n',
                 'task_semantics.jsonl': json.dumps({'task_key': '001', 'related_apps': ['browser','editor']})+'\n'}, [action])
            ar = {'group_directory': 'h', 'pairing': {'tool_call_entries': 2},
                  'activity_call_counts': {'contact': 1}, 'native_identity_counts': {'search_contacts': 1},
                  'called_name_counts': {'search_contacts': 1, 'scrambled': 1}}
            pack(PACKAGES[3], {'summary.json': {'tool_interface': {'native_tool_names': ['search_contacts'],
                 'activity_classification': {'search_contacts': 'contact'}}}, 'per_trajectory.jsonl': json.dumps(ar)+'\n'})
            pack(PACKAGES[4], {'summary.json': {'sources': {}}})
            pack('PUBLIC-TRACE-OPERATIONS-v1', {'coverage.json': {
                'interpreted_object_count': 0, 'objects': []}, 'summary.json': {'schema': 'public-trace-operations-v1'}})
            snapshot_dir = PROJECT/'env/public-trace-operations-v2/source-before-edit'
            snapshot_manifest = json.loads((snapshot_dir/'manifest.json').read_text())
            for item in snapshot_manifest['files']:
                put('env/public-trace-operations-v2/source-before-edit/'+item['path'],
                    (snapshot_dir/item['path']).read_bytes())
            put('env/public-trace-operations-v2/source-before-edit/manifest.json', snapshot_manifest)
            for filename in ('scripts/public_trace_operations.py', 'tests/test_public_trace_operations.py',
                             'src/agent_workload_characterization/analyzers/public_operations.py'):
                put(filename, (PROJECT/filename).read_bytes())
            out = root/'reports/analysis/PUBLIC-TRACE-OPERATIONS-v2'
            data = run(root, out)
            self.assertEqual(data['coding']['swe_rebench_pooled']['operations']['denominator'], 1)
            self.assertEqual(data['swebench_inventory']['registered_object_count'], 1)
            self.assertEqual(data['swebench_inventory']['action_object_count'], 1)
            self.assertEqual(data['historical_corrections']['sweagent_old_30']['raw_recomputed_total'], 2)
            self.assertEqual(len(data['computer_office']['declared_application_scenarios']), 2)
            self.assertEqual(data['assistant']['groups']['h']['activities']['counts']['unknown'], 1)
            manifest = json.loads((out/'manifest.json').read_text())
            self.assertNotIn('manifest.json', [Path(x['path']).name for x in manifest['outputs']])
            for item in manifest['inputs'] + manifest['outputs']:
                raw = (root/item['path']).read_bytes()
                self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (item['bytes'], item['sha256']))
            with self.assertRaises(FileExistsError): run(root, out)

            # Changed source content and matching registration must change the
            # generated operation counts, not just the manifest hash.
            changed = put(swe_path, {'trajectory': [{'action': 'grep foo x.py'}, {'action': 'edit a.py'}]})
            for acq in ACQUISITIONS:
                put('data/catalog/public_trace_acquisition/'+acq+'/manifest.json', {'inputs': [{**changed, 'role': 'trajectory'}]})
            pack(PACKAGES[1], {'selection.json': {'groups': [{'submission': 'g', 'items': [{**changed, 'file': swe_path}]}]}})
            second = run(root, root/'reports/analysis/PUBLIC-TRACE-OPERATIONS-v2-changed')
            changed_group = next(g for g in second['coding']['groups'] if g['source'] == 'SWE-bench')
            self.assertEqual(changed_group['operations']['counts']['content_search'], 1)

    def test_hash_mismatch_isolated_at_registered_object(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            name = SWEBENCH+'/experiments/g/trajs/r__r-1.traj'
            p = root/name; p.parent.mkdir(parents=True); p.write_text('{"trajectory":[]}')
            from scripts.public_trace_operations import analyze_swebench
            row, inventory = analyze_swebench(Inputs(root), {name: {'path': name, 'bytes': 2, 'sha256': '0'*64}})
            self.assertEqual(row, [])
            self.assertEqual(inventory['identity_mismatch_count'], 1)
            self.assertEqual(inventory['objects'][0]['status'], 'isolated_content_identity_mismatch')


if __name__ == '__main__': unittest.main()
