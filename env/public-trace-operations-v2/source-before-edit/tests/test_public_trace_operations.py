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
            swe = put(SWEBENCH+'/experiments/g/trajs/r__r-1.traj', {'trajectory': [{'action': 'open a.py'}, {'action': 'edit a.py'}]})
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
            for filename in ('scripts/public_trace_operations.py', 'tests/test_public_trace_operations.py',
                             'src/agent_workload_characterization/analyzers/public_operations.py'):
                put(filename, (PROJECT/filename).read_bytes())
            out = root/'reports/analysis/PUBLIC-TRACE-OPERATIONS-v1'
            data = run(root, out)
            self.assertEqual(data['coding']['swe_rebench_pooled']['operations']['denominator'], 1)
            self.assertEqual(data['swebench_inventory']['registered_object_count'], 1)
            self.assertEqual(data['historical_corrections']['sweagent_old_30']['raw_recomputed_total'], 2)
            self.assertEqual(len(data['computer_office']['declared_application_scenarios']), 2)
            self.assertEqual(data['assistant']['groups']['h']['activities']['counts']['unknown'], 1)
            manifest = json.loads((out/'manifest.json').read_text())
            self.assertNotIn('manifest.json', [Path(x['path']).name for x in manifest['outputs']])
            for item in manifest['inputs'] + manifest['outputs']:
                raw = (root/item['path']).read_bytes()
                self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (item['bytes'], item['sha256']))
            with self.assertRaises(FileExistsError): run(root, out)


if __name__ == '__main__': unittest.main()
