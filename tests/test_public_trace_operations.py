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
    valid_native_tool_identifier, analyze_rebench, analyze_swebench, _sage_messages,
    _masai_text, _learn_by_interact_strings, _swe_exp_process_nodes,
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

    def test_sage_running_command_protocol_and_separate_returns(self):
        messages = [
            {'role': 'system', 'content': 'Running command: pytest -q'},
            {'role': 'user', 'content': 'Example: Running command: echo not-an-action'},
            {'role': 'assistant', 'content': 'THOUGHT: I may run pytest, but this is narration.'},
            {'role': 'assistant', 'content': 'THOUGHT: N/A.\n\nRunning command:\ncd /repo && cat a.py | head -5\npytest -q'},
            {'role': 'user', 'content': '<return_code>0</return_code>\noutput'},
            {'role': 'assistant', 'content': 'Running command:   '},
            {'role': 'user', 'content': 'ordinary output'}]
        units, returns, detail = _sage_messages(messages)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]['arguments']['command'], 'cd /repo && cat a.py | head -5\npytest -q')
        self.assertEqual(len(returns), 1)
        self.assertIsNone(units[0]['call_id']); self.assertIsNone(returns[0]['call_id'])
        self.assertEqual(detail['candidate_action_segment_count'], 2)
        self.assertEqual(detail['rejected_or_ambiguous_segment_count'], 1)
        self.assertEqual(detail['adjacent_following_return_code_record_count'], 1)
        self.assertEqual(pairing_summary(units, returns)['paired_1_to_1_by_id_count'], 0)

    def test_masai_all_three_agent_response_sections_only(self):
        text = ('========== 01-01-2025 00:00:00 Template Generation Agent Prompt:\n'
                '<action>WRITE</action>\n'
                '========== 01-01-2025 00:00:01 Template Generation Agent Model response:\n'
                '<reasoning>choose</reasoning><action>READ</action><path>x.py</path>\n'
                '========== 01-01-2025 00:00:02 Test Case Reproducer Agent Prompt:\n'
                '<action>DONE</action>\n'
                '========== 01-01-2025 00:00:03 Test Case Reproducer Agent Model response:\n'
                '<action>COMMAND</action><command>pytest -q</command>\n'
                '========== 01-01-2025 00:00:04 Search Agent Model response:\n'
                '<action>LIST</action><path>tests</path>\nYour actions returned:\n')
        units, returns, detail = _masai_text(text)
        self.assertEqual([u['subagent'] for u in units], [
            'Template Generation Agent', 'Test Case Reproducer Agent', 'Search Agent'])
        self.assertEqual([u['tool'] for u in units], ['READ', 'COMMAND', 'LIST'])
        self.assertEqual(detail['action_tags_outside_model_response_sections'], 2)
        self.assertEqual(len(returns), 1)
        row = summarize_units('SWE-bench', 'masai', 'repo-1', {}, 'saved_action_or_tool_call', units, returns)
        self.assertEqual(sum(row['subagent_unit_counts'].values()), row['unit_count'])
        self.assertEqual(row['call_return_evidence']['paired_1_to_1_by_id_count'], 0)

    def test_learn_by_interact_file_edit_attribute_shapes_and_ambiguity(self):
        messages = [
            'Narration <file_edit path="example.py">not a standalone action?</file_edit>\n'
            '<file_edit start = 244 end=245 path=/workspace/separable.py>\nnew text\n</file_edit>\n'
            '<file_edit path="/workspace/quoted.py" end="9" start="7">old</file_edit>\n'
            '<file_edit path=/workspace/broken.py>never closed',
            'USER: OBSERVATION:\n<file_edit path=/workspace/result-example.py>x</file_edit>']
        units, returns, detail = _learn_by_interact_strings(messages)
        edits = [u for u in units if u['tool'] == 'file_edit']
        self.assertEqual(len(edits), 2)
        self.assertEqual(edits[0]['arguments']['path'], '/workspace/separable.py')
        self.assertEqual(edits[0]['arguments']['attributes']['start'], '244')
        self.assertEqual(edits[0]['arguments']['attributes']['end'], '245')
        self.assertEqual(edits[1]['arguments']['path'], '/workspace/quoted.py')
        self.assertEqual(detail['file_edit_candidates'], 3)
        self.assertEqual(detail['file_edit_closed_candidates'], 2)
        self.assertEqual(detail['file_edit_extracted'], 2)
        self.assertEqual(detail['file_edit_rejected_or_ambiguous'], 1)
        self.assertEqual(len(returns), 1)
        # An unclosed explicit block makes the containing record partial, not complete.
        data = json.dumps(messages).encode()
        parsed = _analyze_swebench_bytes('x.json', '20250110_learn_by_interact_claude3.5', data)
        self.assertEqual(parsed['status'], 'actions_extracted')
        self.assertEqual(parsed['action_protocol_detail']['file_edit_rejected_or_ambiguous'], 1)

    def test_swe_exp_metadata_does_not_hide_process_nodes(self):
        obj = [{'problem_statement': 'metadata only'},
               {'node_id': 1, 'instructor': {'ty': 'view', 'context': '...'},
                'assistant': '{"thoughts":"..."}', 'observation': 'file view output'}]
        groups, returns, _, schema, detail = _json_object_records(obj, '20250806_SWE-Exp_DeepSeek-V3')
        self.assertEqual(schema, 'swe_exp_saved_process_nodes')
        self.assertEqual(groups[0][0], 'saved_process_node')
        self.assertEqual(len(groups[0][1]), 1)
        self.assertEqual(groups[0][1][0]['node_id'], 1)
        row = summarize_units('SWE-bench', 'sweexp', 'repo-1', {}, 'saved_process_node', groups[0][1], returns)
        self.assertEqual(row['saved_process_node_count'], 1)
        self.assertEqual(row['operation_counts'], {})
        self.assertEqual(row['native_tool_counts'], {})
        self.assertIn('view', detail['instructor_type_counts'])

    def test_solver_returns_route_once_to_operation_not_retrieval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            name = SWEBENCH+'/experiments/20240920_solver/trajs/repo__repo-1.json'
            payload = [{'id': 'exec-1', 'event_type': 'execution',
                        'event_data': {'command': 'pytest -q', 'exit_code': 0}},
                       {'id': 'search-1', 'event_type': 'retrieval', 'event_data': {'query': 'symbol'}}]
            raw = json.dumps(payload).encode(); path = root/name; path.parent.mkdir(parents=True); path.write_bytes(raw)
            rows, coverage = analyze_swebench(Inputs(root), {name: {'path': name, 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest()}})
            by_kind = {r['unit_kind']: r for r in rows}
            self.assertEqual(by_kind['saved_operation_event']['call_return_evidence']['return_record_count'], 1)
            self.assertEqual(by_kind['saved_retrieval_event']['call_return_evidence']['return_record_count'], 0)
            self.assertEqual(coverage['saved_return_record_count'], 1)
            self.assertEqual(coverage['unassigned_file_level_return_record_count'], 0)

    def test_rebench_native_call_result_ids_keep_duplicates_and_orphans(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); base = root/REBENCH
            raw = (json.dumps({'trajectory_id': 't1', 'instance_id': 'repo__repo-1',
                    'participant': {'key': 'p'}, 'events': [
                        {'type': 'tool_call', 'tool': 'bash', 'tool_call_id': 'dup', 'input': {'command': 'ls'}},
                        {'type': 'tool_call', 'tool': 'bash', 'tool_call_id': 'dup', 'input': {'command': 'pwd'}},
                        {'type': 'tool_call', 'tool': 'bash', 'input': {'command': 'cat x'}},
                        {'type': 'tool_result', 'tool_call_id': 'dup', 'status': 'ok'},
                        {'type': 'tool_result', 'tool_call_id': 'orphan', 'status': 'error'},
                        {'type': 'tool_result', 'status': 'ok'}]})+'\n').encode()
            compressed = gzip.compress(raw); shard = 'trajectories/p/run_0.jsonl.gz'
            (base/'trajectories/p').mkdir(parents=True); (base/shard).write_bytes(compressed)
            index = {'path': shard, 'rows': 1, 'content_sha256': hashlib.sha256(raw).hexdigest()}
            (base/'index.jsonl').write_text(json.dumps(index)+'\n')
            old = {'scope': {'record_count': 1}, 'native_tool_counts': {'bash': 3},
                   'coverage': {'shards': [{'path': shard, 'bytes': len(compressed),
                                             'sha256': hashlib.sha256(compressed).hexdigest()}]}}
            rows = analyze_rebench(Inputs(root), old)
            pairing = rows[0]['call_return_evidence']
            self.assertEqual(pairing['call_event_count'], 3)
            self.assertEqual(pairing['return_record_count'], 3)
            self.assertEqual(pairing['missing_call_id_count'], 1)
            self.assertEqual(pairing['return_ids_missing'], 1)
            self.assertEqual(pairing['duplicate_call_id_counts']['conflicting'], 1)
            self.assertEqual(pairing['paired_1_to_1_by_id_count'], 0)
            self.assertEqual(pairing['orphan_return_id_count'], 1)

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
                    'events': [{'type': 'tool_call', 'tool': 'bash', 'tool_call_id': 'c1', 'input': {'command': 'cat "a\u2028b" && pytest -q'}},
                               {'type': 'tool_result', 'tool_call_id': 'c1', 'status': 'ok'}]}, ensure_ascii=False)+'\n').encode()
            shard = put(REBENCH+'/trajectories/p/run_0.jsonl.gz', gzip.compress(raw))
            put(REBENCH+'/index.jsonl', json.dumps({'path': 'trajectories/p/run_0.jsonl.gz', 'rows': 1, 'content_sha256': hashlib.sha256(raw).hexdigest()})+'\n')
            pack(PACKAGES[0], {'summary.json': {'scope': {'record_count': 1}, 'native_tool_counts': {'bash': 1},
                 'coverage': {'shards': [{**shard, 'path': 'trajectories/p/run_0.jsonl.gz'}]}}})
            registrations = []
            swe_path = SWEBENCH+'/experiments/g/trajs/r__r-1.traj'
            registrations.append(put(swe_path, {'trajectory': [{'action': 'open a.py', 'observation': 'file'}, {'action': 'edit a.py'}]}))
            swe = registrations[0]
            sage_path = SWEBENCH+'/experiments/20251103_SalesforceAIResearch_SAGE_OpenHands/trajs/r__r-1.json'
            registrations.append(put(sage_path, {'instance_id': 'r__r-1', 'messages': [
                {'role': 'user', 'content': 'prompt: Running command: false'},
                {'role': 'assistant', 'content': 'THOUGHT: N/A.\n\nRunning command:\nls -la && cat x.py'},
                {'role': 'user', 'content': '<return_code>0</return_code>\noutput'}]}))
            exp_path = SWEBENCH+'/experiments/20250806_SWE-Exp_DeepSeek-V3/trajs/r__r-1.json'
            registrations.append(put(exp_path, [{'problem_statement': 'metadata'},
                {'node_id': 1, 'instructor': {'ty': 'view', 'context': 'x'},
                 'assistant': '{"thoughts":"read"}', 'observation': 'file output'}]))
            masai_path = SWEBENCH+'/experiments/20240612_MASAI_gpt4o/trajs/r__r-1.log'
            masai = ('========== 01-01-2025 00:00:00 Template Generation Agent Prompt:\n<action>WRITE</action>\n'
                     '========== 01-01-2025 00:00:01 Template Generation Agent Model response:\n<action>READ</action>\n'
                     '========== 01-01-2025 00:00:02 Test Case Reproducer Agent Model response:\n<action>COMMAND</action><command>pytest</command>\n'
                     '========== 01-01-2025 00:00:03 Search Agent Model response:\n<action>LIST</action>\nYour actions returned:')
            registrations.append(put(masai_path, masai))
            learn_path = SWEBENCH+'/experiments/20250110_learn_by_interact_claude3.5/trajs/r__r-1.json'
            registrations.append(put(learn_path, ['Do it. <execute_bash>ls</execute_bash>',
                '<file_edit start=2 end=4 path=/workspace/x.py>text</file_edit>']))
            solver_path = SWEBENCH+'/experiments/20240920_solver/trajs/r__r-1.json'
            registrations.append(put(solver_path, [
                {'id': 'exec', 'event_type': 'execution', 'event_data': {'command': 'pytest -q', 'exit_code': 0}},
                {'id': 'ret', 'event_type': 'retrieval', 'event_data': {'query': 'x'}}]))
            for acq in ACQUISITIONS:
                put('data/catalog/public_trace_acquisition/'+acq+'/manifest.json',
                    {'inputs': [{**item, 'role': 'trajectory'} for item in registrations]})
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
            old_pairing = pairing_summary([], [])
            old_groups = [
                {'source': 'SWE-bench', 'group': '20240612_MASAI_gpt4o', 'unit_kind': 'saved_action_or_tool_call',
                 'operations': shares({'other': 1}), 'native_tools': shares({'READ': 1}),
                 'call_return_evidence': old_pairing},
                {'source': 'SWE-bench', 'group': '20250110_learn_by_interact_claude3.5', 'unit_kind': 'saved_action_or_tool_call',
                 'operations': shares({'edit_write': 1}), 'native_tools': shares({'file_edit': 1}),
                 'call_return_evidence': old_pairing},
                {'source': 'SWE-bench', 'group': '20240920_solver', 'unit_kind': 'saved_operation_event',
                 'operations': shares({'test': 1}), 'native_tools': shares({'execution': 1}),
                 'call_return_evidence': {**old_pairing, 'return_record_count': 1}},
                {'source': 'SWE-bench', 'group': '20240920_solver', 'unit_kind': 'saved_retrieval_event',
                 'operations': shares({'content_search': 1}), 'native_tools': shares({'retrieval': 1}),
                 'call_return_evidence': {**old_pairing, 'return_record_count': 1}}]
            snapshot_dir = PROJECT/'env/public-trace-operations-v2/source-before-edit'
            v1_snapshot = json.loads((snapshot_dir/'manifest.json').read_text())
            for item in v1_snapshot['files']:
                put('env/public-trace-operations-v2/source-before-edit/'+item['path'], (snapshot_dir/item['path']).read_bytes())
            put('env/public-trace-operations-v2/source-before-edit/manifest.json', v1_snapshot)
            v2_snapshot_dir = PROJECT/'env/public-trace-operations-v3/source-before-edit'
            v2_snapshot = json.loads((v2_snapshot_dir/'manifest.json').read_text())
            for item in v2_snapshot['files']:
                put('env/public-trace-operations-v3/source-before-edit/'+item['path'], (v2_snapshot_dir/item['path']).read_bytes())
            put('env/public-trace-operations-v3/source-before-edit/manifest.json', v2_snapshot)
            current_sources = []
            for filename in ('scripts/public_trace_operations.py', 'tests/test_public_trace_operations.py',
                             'src/agent_workload_characterization/analyzers/public_operations.py'):
                current_sources.append(put(filename, (PROJECT/filename).read_bytes()))
            pack('PUBLIC-TRACE-OPERATIONS-v2', {
                'summary.json': {'coding': {'groups': old_groups, 'swe_rebench_pooled': {'call_return_evidence': old_pairing}},
                                 'swebench_inventory': {}},
                'coverage.json': {'per_group_status_counts': {
                    '20251103_SalesforceAIResearch_SAGE_OpenHands': {'process_partial_or_ambiguous': 1},
                    '20250806_SWE-Exp_DeepSeek-V3': {'companion_artifact': 1}}, 'objects': []}},
                extra_inputs=v2_snapshot['files'])
            out = root/'reports/analysis/PUBLIC-TRACE-OPERATIONS-v3'
            data = run(root, out)
            self.assertEqual(data['coding']['swe_rebench_pooled']['operations']['denominator'], 1)
            self.assertEqual(data['coding']['swe_rebench_pooled']['call_return_evidence']['paired_1_to_1_by_id_count'], 1)
            self.assertEqual(data['swebench_inventory']['registered_object_count'], 6)
            self.assertEqual(data['swebench_inventory']['action_object_count'], 5)
            self.assertEqual(data['swebench_inventory']['process_node_object_count'], 1)
            self.assertEqual(data['corrections']['masai']['v3_subagents']['Test Case Reproducer Agent']['unit_count'], 1)
            self.assertEqual(data['corrections']['swe_exp']['saved_process_nodes'], 1)
            self.assertEqual(data['corrections']['learn_by_interact']['file_edit_extracted_block_count'], 1)
            self.assertEqual(data['corrections']['solver']['v3_operation_return_records'], 1)
            self.assertEqual(data['corrections']['solver']['v3_retrieval_return_records'], 0)
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
                put('data/catalog/public_trace_acquisition/'+acq+'/manifest.json',
                    {'inputs': [{**item, 'role': 'trajectory'} for item in [changed, *registrations[1:]] ]})
            pack(PACKAGES[1], {'selection.json': {'groups': [{'submission': 'g', 'items': [{**changed, 'file': swe_path}]}]}})
            second = run(root, root/'reports/analysis/PUBLIC-TRACE-OPERATIONS-v2-changed')
            changed_group = next(g for g in second['coding']['groups']
                                 if g['source'] == 'SWE-bench' and g['group'] == 'g')
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
