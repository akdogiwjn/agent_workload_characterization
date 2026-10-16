import hashlib
import csv
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("public_trace_software_toolkits", ROOT / "scripts/public_trace_software_toolkits.py")
ANALYZER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ANALYZER
SPEC.loader.exec_module(ANALYZER)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _jsonl(rows):
    return ("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)).encode()


def _package(root, key, files):
    rel_dir = ANALYZER.PACKAGES[key][0]
    directory = root / rel_dir
    directory.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, data in files.items():
        target = directory / name
        target.write_bytes(data)
        outputs.append({"path": name, "bytes": len(data), "sha256": _sha(data)})
    (directory / "manifest.json").write_text(json.dumps({"schema": "fixture", "outputs": outputs}, indent=2))


def _make_fixture(root):
    for rel in ("scripts", "src/agent_workload_characterization/analyzers", "references/repos/DocOps/harnesses"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    for rel in ("scripts/public_trace_operations.py", "src/agent_workload_characterization/analyzers/public_operations.py",
                "scripts/public_trace_software_toolkits.py", "references/repos/DocOps/harnesses/document_tools_runtime.py"):
        shutil.copy2(ROOT / rel, root / rel)
    v1_dir = root / ANALYZER.PACKAGES["software_toolkits_v1"][0]
    v1_dir.mkdir(parents=True, exist_ok=True)
    v1_json = json.dumps({"counts": {}, "coding_groups": [], "toolkits": []}).encode()
    (v1_dir / "software_toolkits.json").write_bytes(v1_json)
    old_script = root / "scripts/public_trace_software_toolkits.py"
    snapshot = root / "env/public-trace-software-toolkits-v2/source-before-edit/public_trace_software_toolkits.py"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(old_script, snapshot)
    (v1_dir / "manifest.json").write_text(json.dumps({
        "inputs": [],
        "analysis_code": [{"path": "scripts/public_trace_software_toolkits.py",
                           "bytes": old_script.stat().st_size, "sha256": _sha(old_script.read_bytes())}],
        "outputs": [{"path": "software_toolkits.json", "bytes": len(v1_json), "sha256": _sha(v1_json)}],
    }, indent=2))

    historical_v2_source = ROOT / "env/public-trace-software-toolkits-v3/source-before-edit/public_trace_software_toolkits.py"
    v2_snapshot = root / "env/public-trace-software-toolkits-v3/source-before-edit/public_trace_software_toolkits.py"
    v2_snapshot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(historical_v2_source, v2_snapshot)
    v2_fixture = {
        "counts": {"osworld_task_definitions": 108, "osworld_model_task_records": 755},
        "coding_groups": [
            {"source": "SWE-bench", "group": "fixture", "unit_kind": "saved_action_or_tool_call",
             "trajectory_denominator": 1, "task_denominator": 1, "record_denominator": 12},
            {"source": "SWE-bench", "group": "fixture", "unit_kind": "saved_operation_event",
             "trajectory_denominator": 1, "task_denominator": 1, "record_denominator": 20},
        ],
        "coding_solver_denominators": {}, "local_coding_task_counts": {}, "docops_library_usage": [],
        "toolkits": [
            {"scene": "Coding/public", "source": "SWE-bench", "group": "fixture",
             "unit_kind": "saved_operation_event", "raw_name": "pytest", "entry_kind": "explicit_python_module",
             "frequency": 1, "task_denominator": 0, "trajectory_denominator": None, "record_denominator": None},
            {"scene": "Coding/public", "source": "SWE-bench", "group": "fixture",
             "unit_kind": "saved_operation_event", "raw_name": "unittest", "entry_kind": "explicit_python_module",
             "frequency": 2, "task_denominator": 0, "trajectory_denominator": None, "record_denominator": None},
        ],
    }
    _package(root, "software_toolkits_v2", {"software_toolkits.json": json.dumps(v2_fixture).encode()})
    v2_manifest_path = root / ANALYZER.PACKAGES["software_toolkits_v2"][0] / "manifest.json"
    v2_manifest = json.loads(v2_manifest_path.read_text())
    v2_manifest["analysis_code"] = [
        {"path": "scripts/public_trace_software_toolkits.py", "bytes": v2_snapshot.stat().st_size,
         "sha256": _sha(v2_snapshot.read_bytes())},
        {"path": "scripts/public_trace_operations.py", "bytes": (ROOT / "scripts/public_trace_operations.py").stat().st_size,
         "sha256": _sha((ROOT / "scripts/public_trace_operations.py").read_bytes())},
        {"path": "src/agent_workload_characterization/analyzers/public_operations.py",
         "bytes": (ROOT / "src/agent_workload_characterization/analyzers/public_operations.py").stat().st_size,
         "sha256": _sha((ROOT / "src/agent_workload_characterization/analyzers/public_operations.py").read_bytes())},
    ]
    v2_manifest_path.write_text(json.dumps(v2_manifest, indent=2))

    raw_rel = "data/raw/public/swebench_fixture/trajs/task-a.jsonl"
    raw_bytes = _jsonl([
        {"messages": [{"role": "assistant", "content": [{"type": "tool_use", "id": "shared-id",
                      "name": "bash", "input": {"command": "python -m pytest -q"}}]}]},
        [
            {"id": "shared-id", "event_type": "execution", "event_data": {"command": "python -m unittest -q", "stdout": "ambiguous id", "exit_code": 0}},
            {"id": "operation-unique", "event_type": "execution", "event_data": {"command": "python -m unittest -q", "stdout": "matched", "exit_code": 0}},
        ],
    ])
    raw_path = root / raw_rel
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw_bytes)
    operation_rows = [
        {"source": "SWE-bench", "group": "fixture", "task": "task-a", "location": {"path": raw_rel, "trajectory_id": "traj-a"},
         "unit_kind": "saved_action_or_tool_call", "saved_command_available_count": 1, "executable_counts": {"python": 1}},
        {"source": "SWE-bench", "group": "fixture", "task": "task-a", "location": {"path": raw_rel, "trajectory_id": "traj-a"},
         "unit_kind": "saved_operation_event", "saved_command_available_count": 1, "executable_counts": {"python": 1}},
    ]
    toolkit = {"coding": {"groups": [
        {"source": "SWE-bench", "group": "fixture", "unit_kind": "saved_action_or_tool_call", "trajectory_count": 1, "operations": {"denominator": 12}},
        {"source": "SWE-bench", "group": "fixture", "unit_kind": "saved_operation_event", "trajectory_count": 1, "operations": {"denominator": 20}},
    ]}}
    public_manifest = {"inputs": [
        {"path": "scripts/public_trace_operations.py", "bytes": (ROOT / "scripts/public_trace_operations.py").stat().st_size, "sha256": _sha((ROOT / "scripts/public_trace_operations.py").read_bytes())},
        {"path": "src/agent_workload_characterization/analyzers/public_operations.py", "bytes": (ROOT / "src/agent_workload_characterization/analyzers/public_operations.py").stat().st_size, "sha256": _sha((ROOT / "src/agent_workload_characterization/analyzers/public_operations.py").read_bytes())},
        {"path": raw_rel, "bytes": len(raw_bytes), "sha256": _sha(raw_bytes)},
    ]}
    _package(root, "public_operations_v3", {
        "summary.json": json.dumps({}).encode(), "toolkits.json": json.dumps(toolkit).encode(),
        "per_trajectory.jsonl": _jsonl(operation_rows), "coverage.json": json.dumps({"objects": [
            {"path": raw_rel, "group": "fixture", "task": "task-a", "expected_bytes": len(raw_bytes),
             "expected_sha256": _sha(raw_bytes)}]}).encode(),
    })
    # Replace the package manifest with the accepted parser-source bindings.
    pdir = root / ANALYZER.PACKAGES["public_operations_v3"][0]
    outputs = [{"path": name, "bytes": (pdir / name).stat().st_size, "sha256": _sha((pdir / name).read_bytes())}
               for name in ("summary.json", "toolkits.json", "per_trajectory.jsonl", "coverage.json")]
    (pdir / "manifest.json").write_text(json.dumps({"inputs": public_manifest["inputs"], "outputs": outputs}, indent=2))

    semantics = []
    trajectories = []
    models = [f"m{i}" for i in range(7)]
    task_ids = [f"{i:03d}" for i in range(1, 109)]
    emitted = 0
    for model in models:
        for tid in task_ids:
            if model == "m6" and tid == "108":
                continue
            if model == "m0":
                apps = ["libreoffice_writer", "libreoffice_calc"] if tid == "001" else (["browser"] if tid == "002" else [])
                if tid not in {x["task_key"] for x in semantics}:
                    semantics.append({"task_key": tid, "related_apps": apps, "snapshot": None, "evidence": {"related_apps": {"path": f"task_{tid}.py", "line": 1}}})
            trajectories.append({"task_key": tid, "source_file": f"web/m{model[1:]}/tasks/{tid}/trajectory.jsonl"})
            emitted += 1
    # One semantic row for every task definition, including tasks without a label.
    known = {row["task_key"] for row in semantics}
    for tid in task_ids:
        if tid not in known:
            semantics.append({"task_key": tid, "related_apps": [], "snapshot": None, "evidence": {}})
    os_manifest = {"outputs": []}
    _package(root, "osworld_behavior_v3", {
        "summary.json": json.dumps({}).encode(), "task_semantics.jsonl": _jsonl(semantics),
        "per_trajectory.jsonl": _jsonl(trajectories),
    })

    hepm_rows = [{"group": "hepm-fixture", "scenario": "scenario-a", "native_identity_counts": {"search_contacts": 1}}]
    _package(root, "hepm_behavior_v2", {"summary.json": json.dumps({}).encode(), "per_trajectory.jsonl": _jsonl(hepm_rows)})
    docops_rows = [
        {"task_key": "excel-task", "run_id": "docops-xlsx", "source": "data/raw/generated/f/docops-xlsx/summary.json",
         "tools": [{"name": "inspect_document", "event_id": "e1", "request_event_id": "req1", "role": "agent", "ok": True},
                   {"name": "xlsx_set_formula", "event_id": "e2", "role": "agent", "ok": True}]},
        {"task_key": "ppt-task", "run_id": "docops-ppt", "source": "data/raw/generated/f/docops-ppt/summary.json",
         "tools": [{"name": "inspect_document", "event_id": "e3", "request_event_id": "req3", "role": "agent", "ok": True}]},
        {"task_key": "pdf-task", "run_id": "docops-pdf", "source": "data/raw/generated/f/docops-pdf/summary.json",
         "tools": [{"name": "inspect_document", "event_id": "e4", "request_event_id": "req4", "role": "agent", "ok": True}]},
        {"task_key": "word-task", "run_id": "docops-docx", "source": "data/raw/generated/f/docops-docx/summary.json",
         "tools": [{"name": "inspect_document", "event_id": "e5", "request_event_id": "req5", "role": "agent", "ok": True}]},
        {"task_key": "ppt-task", "run_id": "docops-bootstrap", "source": "data/raw/generated/f/docops-bootstrap/summary.json",
         "tools": [{"name": "inspect_document", "event_id": "e6", "request_event_id": None, "role": "bootstrap", "ok": False}]},
        {"task_key": "ppt-task", "run_id": "docops-failed", "source": "data/raw/generated/f/docops-failed/summary.json",
         "tools": [{"name": "inspect_document", "event_id": "e7", "request_event_id": "req7", "role": "agent", "ok": False}]},
    ]
    docops_runtime = (ROOT / "references/repos/DocOps/harnesses/document_tools_runtime.py").read_bytes()
    _package(root, "docops_repeat02", {"summary.json": json.dumps({}).encode(), "per_run.jsonl": _jsonl(docops_rows)})
    ddir = root / ANALYZER.PACKAGES["docops_repeat02"][0]
    dout = [{"path": name, "bytes": (ddir / name).stat().st_size, "sha256": _sha((ddir / name).read_bytes())}
            for name in ("summary.json", "per_run.jsonl")]
    docops_inputs = [{"path": "references/repos/DocOps/harnesses/document_tools_runtime.py",
                      "bytes": len(docops_runtime), "sha256": _sha(docops_runtime)}]
    extensions = {"docops-xlsx": ".xlsx", "docops-ppt": ".pptx", "docops-pdf": ".pdf", "docops-docx": ".docx"}
    for run in docops_rows:
        agent_dir = root / Path(run["source"]).parent / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        call = run["tools"][0]
        args = {"path": "/workspace/input" + extensions.get(run["run_id"], ".pptx")}
        arg_hash = hashlib.sha256(json.dumps(args, ensure_ascii=False).encode()).hexdigest()
        attrs = {"role": call["role"], "tool_name": "inspect_document", "request_event_id": call["request_event_id"],
                 "argument_sha256": arg_hash}
        events = [{"kind": "tool_call", "status": "open", "event_id": call["event_id"], "attrs": attrs}]
        if call["request_event_id"]:
            events.append({"kind": "agent_action", "status": "instant", "event_id": "action-" + call["event_id"],
                           "attrs": {"request_event_id": call["request_event_id"], "action": "call_tool", "tool_name": "inspect_document"}})
        events.append({"kind": "tool_call", "status": "closed", "event_id": call["event_id"],
                       "attrs": {"ok": call["ok"], "result_sha256": "0" * 64}})
        event_rel = (agent_dir / "events.jsonl").relative_to(root).as_posix()
        event_bytes = _jsonl(events)
        (root / event_rel).write_bytes(event_bytes)
        docops_inputs.append({"path": event_rel, "bytes": len(event_bytes), "sha256": _sha(event_bytes)})
        if call["request_event_id"]:
            action = {"action": "call_tool", "tool_name": "inspect_document", "arguments": args}
            log = {"original_response": json.dumps({"choices": [{"message": {"content": json.dumps(action)}}]})}
            log_rel = (agent_dir / "llm_call_1.json").relative_to(root).as_posix()
            log_bytes = json.dumps(log).encode()
            (root / log_rel).write_bytes(log_bytes)
            docops_inputs.append({"path": log_rel, "bytes": len(log_bytes), "sha256": _sha(log_bytes)})
    (ddir / "manifest.json").write_text(json.dumps({"inputs": docops_inputs, "outputs": dout}, indent=2))
    assistant_rows = [{"task": "assistant-task", "run_id": "assistant-run", "behavior": {"tool_calls": {"details": [{"tool_name": "add_contact", "role": "agent", "event_id": "e2", "ok": True}]}}}]
    _package(root, "toolsandbox_assistant_repeat01", {"summary.json": json.dumps({}).encode(), "per_run.jsonl": _jsonl(assistant_rows)})
    macro = {"sources": {"AgentX": {"summary": {"trace_count": 1}}, "Applied Compute": {"summary": {"agentic_coding_8k": {"template_count": 1}}}}}
    _package(root, "agentx_applied_macro", {"summary.json": json.dumps(macro).encode()})

    p1 = root / "reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3"
    p1.mkdir(parents=True)
    p1_inputs = {}
    p1_runs = []
    selected = []
    for task in ("astropy__a", "astropy__b", "django__c"):
        for rep in range(3):
            run_id = f"run-{task}-{rep}"
            selected.append(run_id)
            run_dir = f"data/raw/generated/P1-12-CODING-REPEAT-01/{run_id}"
            command = "python -m pytest -q" if task == "astropy__a" else ("git diff --stat" if task == "astropy__b" else "rg TODO && rg FIXME")
            traj = {"messages": [
                {"role": "assistant", "tool_calls": [{"id": f"call-{run_id}", "function": {"name": "bash", "arguments": json.dumps({"command": command})}}]},
                {"role": "tool", "tool_call_id": f"call-{run_id}", "extra": {"returncode": 0, "exception_info": None}},
            ]}
            rel = f"{run_dir}/mini_trajectory.json"
            data = json.dumps(traj).encode()
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            p1_inputs[rel] = {"path": rel, "bytes": len(data), "sha256": _sha(data)}
            p1_runs.append({"task": task, "run_id": run_id, "run_dir": run_dir})
    summary_data = json.dumps({"selected_run_ids": selected, "runs": p1_runs}).encode()
    (p1 / "summary.json").write_bytes(summary_data)
    (p1 / "manifest.json").write_text(json.dumps({"inputs": p1_inputs, "outputs": {"summary.json": {
        "path": f"{p1.relative_to(root).as_posix()}/summary.json", "bytes": len(summary_data), "sha256": _sha(summary_data)}}}, indent=2))
    return emitted


class SoftwareToolkitTests(unittest.TestCase):
    def _parser(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        sys.path.insert(0, str(ROOT / "src"))
        import public_trace_operations
        from agent_workload_characterization.analyzers import public_operations
        return public_trace_operations, public_operations

    def test_explicit_software_identity_is_not_keyword_or_builtin(self):
        parser, operations = self._parser()
        unit = {"tool": "bash_terminal", "arguments": {"command": "python -m pytest -q && grep pytest test_file"}}
        programs, _ = ANALYZER._command_programs(unit, parser, operations)
        self.assertEqual({(x["raw_name"], x["entry_kind"]) for x in programs},
                         {("python", "command_head"), ("pytest", "explicit_python_module"), ("grep", "command_head")})
        grep_only = {"tool": "bash_terminal", "arguments": {"command": "grep pytest test_file"}}
        names = {x["raw_name"] for x in ANALYZER._command_programs(grep_only, parser, operations)[0]}
        self.assertEqual(names, {"grep"})
        builtins = {"tool": "bash_terminal", "arguments": {"command": "echo libreoffice; cd repo"}}
        self.assertEqual(ANALYZER._command_programs(builtins, parser, operations)[0], [])
        repeated = {"tool": "bash_terminal", "arguments": {"command": "grep one a.py | grep two b.py"}}
        aggregate = {}
        touched = ANALYZER._observe_call(repeated, parser, operations, ("SWE-bench", "fixture"), "task-a",
                                         "trace.jsonl", "trace-a", {"line": 4}, aggregate)
        self.assertEqual(len(touched), 1)
        self.assertEqual(aggregate[touched[0]]["component_occurrences"], 2)
        self.assertEqual(len(aggregate[touched[0]]["call_keys"]), 1)

    def test_python_module_recognition_respects_command_boundary_and_wrappers(self):
        parser, operations = self._parser()
        def names(command):
            unit = {"tool": "bash_terminal", "arguments": {"command": command}}
            return {(x["raw_name"], x["entry_kind"]) for x in ANALYZER._command_programs(unit, parser, operations)[0]}
        self.assertIn(("pytest", "explicit_python_module"), names("python -m pytest -q"))
        self.assertIn(("unittest", "explicit_python_module"), names("python -u -m unittest -q"))
        self.assertIn(("pytest", "explicit_python_module"), names("env FOO=1 python -B -m pytest"))
        self.assertIn(("unittest", "explicit_python_module"), names("timeout 20s python -m unittest"))
        self.assertIn(("pytest", "explicit_python_module"), names("PYTHONPATH=. python -m pytest -q"))
        self.assertIn(("pytest", "explicit_python_module"), names("xvfb-run -a python -m pytest -q"))
        for command in ("echo python -m pytest", "grep python -m pytest file.txt",
                        'printf "%s" python -m unittest', 'python -c "print(1)" -m pytest',
                        "src:$PYTHONPATH python -m pytest"):
            self.assertNotIn(("pytest", "explicit_python_module"), names(command), command)
            self.assertNotIn(("unittest", "explicit_python_module"), names(command), command)
        self.assertIn(("jest", "explicit_npx_package"), names("npx --yes jest --runInBand"))
        self.assertNotIn(("jest", "explicit_npx_package"), names("echo npx jest"))

    def test_coding_source_group_keeps_unit_kind_and_matching_denominator(self):
        rows = [
            {"source": "SWE-bench", "group": "same", "unit_kind": "saved_operation_event", "task": "t",
             "location": {"path": "p", "trajectory_id": "trace"}, "executable_counts": {"python": 1}},
            {"source": "SWE-bench", "group": "same", "unit_kind": "saved_retrieval_event", "task": "t",
             "location": {"path": "p", "trajectory_id": "trace"}, "executable_counts": {"grep": 1}},
        ]
        toolkit = {"coding": {"groups": [
            {"source": "SWE-bench", "group": "same", "unit_kind": "saved_operation_event", "trajectory_count": 1, "operations": {"denominator": 5037}},
            {"source": "SWE-bench", "group": "same", "unit_kind": "saved_retrieval_event", "trajectory_count": 1, "operations": {"denominator": 543}},
        ]}}
        software = ANALYZER._coding_software(rows, toolkit)
        python_row = next(x for x in software if x["raw_name"] == "python")
        self.assertEqual(python_row["unit_kind"], "saved_operation_event")
        self.assertEqual(python_row["record_denominator"], 5037)
        self.assertEqual(len({(x["source"], x["group"]) for x in toolkit["coding"]["groups"]}), 1)

    def test_nonempty_coding_software_without_exact_unit_metadata_fails(self):
        rows = [{"source": "SWE-bench", "group": "missing", "unit_kind": "saved_action_or_tool_call",
                 "task": "t", "location": {"path": "p", "trajectory_id": "trace"},
                 "executable_counts": {"python": 1}}]
        with self.assertRaisesRegex(ValueError, "no matching Coding group metadata"):
            ANALYZER._coding_software(rows, {"coding": {"groups": []}})

    def test_docops_inspect_document_maps_confirmed_format_branches(self):
        with tempfile.TemporaryDirectory(prefix="docops-conditional-map-") as tmp:
            root = Path(tmp)
            _make_fixture(root)
            report = ANALYZER.build(root)["software_toolkits"]
            self.assertEqual(report["docops_inspect_document"]["call_count"], 6)
            statuses = report["docops_inspect_document"]["resolved_status_counts"]
            self.assertEqual(statuses["success"], 4)
            self.assertEqual(statuses["failed_branch_associated"], 1)
            self.assertEqual(report["docops_inspect_document"]["call_count"], 6)
            self.assertEqual(report["docops_inspect_document"]["unlinked_or_unavailable_branch_count"], 1)
            self.assertEqual(report["docops_inspect_document"]["all_call_branch_status_counts"]["branch_unknown"], 1)
            self.assertEqual(report["docops_inspect_document"]["bootstrap_failed_call_count"], 1)
            branch_rows = [x for x in report["toolkits"] if x.get("entry_kind") == "conditional_implementation_library"]
            self.assertTrue(any(x["group"] == "excel-task" and x["library_module"] == "openpyxl" and x["branch_status"] == "success" for x in branch_rows))
            self.assertTrue(any(x["group"] == "ppt-task" and x["library_module"] == "pptx" and x["branch_status"] == "success" for x in branch_rows))
            pdf = [x for x in branch_rows if x["group"] == "pdf-task" and x["branch_status"] == "success"]
            self.assertEqual({x["library_module"] for x in pdf}, {"pypdf", "pdfplumber"})
            self.assertTrue(any(x["group"] == "word-task" and x["library_module"] == "docx" for x in branch_rows))
            self.assertTrue(any(x["group"] == "ppt-task" and x["branch_status"] == "failed_branch_associated" and x["ok_count"] == 0 for x in branch_rows))
            self.assertTrue(any(x["group"] == "ppt-task" and x["role"] == "bootstrap" and x["branch_status"] == "branch_unknown" for x in branch_rows))

    def test_osworld_declarations_do_not_become_runtime_calls_and_family_deduplicates(self):
        semantics = [{"task_key": "t1", "related_apps": ["libreoffice_writer", "libreoffice_calc", "browser", "xlsx"],
                      "snapshot": "chrome", "evidence": {}}]
        pairs = [{"task_key": "t1", "source_file": f"web/m{i}/tasks/t1/traj.jsonl"} for i in range(755)]
        # The production helper enforces the corpus denominator of 755, regardless of fixture model naming.
        raw, pair_set, families = ANALYZER._osworld_apps(semantics, pairs)
        self.assertEqual(len(pair_set), 755)
        generic = next(x for x in raw if x["raw_name"] == "browser")
        self.assertIsNone(generic["software"])
        self.assertEqual(generic["runtime_use_status"], "unknown; declarations are not runtime evidence")
        self.assertIsNone(next(x for x in raw if x["raw_name"] == "xlsx")["software"])
        family = next(x for x in families if x["family"] == "LibreOffice")
        self.assertEqual(family["task_count"], 1)
        self.assertEqual(family["trajectory_count"], 755)

    def test_unbound_implementation_reference_is_not_runtime_use(self):
        rows = ANALYZER._docops([{"task_key": "t", "run_id": "r", "tools": [{"name": "xlsx_set_formula", "event_id": "e", "ok": True}]}], "runtime.py", "abc", {})
        unbound = next(x for x in rows if x["raw_name"] == "xlsx_set_formula")
        self.assertEqual(unbound["software"], "项目自有工具接口")
        self.assertEqual(unbound["evidence_type"], "saved tool interface; implementation mapping unavailable")
        self.assertIsNone(unbound["library_module"])
        word = next(x for x in rows if x["raw_name"] == "python-docx")
        self.assertEqual(word["evidence_type"], "implementation reference only")
        self.assertEqual(word["trajectory_count"], 0)
        self.assertEqual(word["library_version"], "unknown")

    def test_swebench_mixed_unit_kind_real_generation_and_summary_integrity(self):
        with tempfile.TemporaryDirectory(prefix="software-unit-kind-report-") as tmp:
            root = Path(tmp)
            _make_fixture(root)
            output = root / "reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3"
            report = ANALYZER.generate(root, output)
            machine = json.loads((output / "software_toolkits.json").read_text())
            details = [x for x in machine["toolkits"] if x.get("scene") == "Coding/public"
                       and x.get("source") == "SWE-bench" and x.get("group") == "fixture"
                       and x.get("entry_kind") == "explicit_python_module"]
            observed = {(x["unit_kind"], x["raw_name"], x["record_denominator"]) for x in details}
            self.assertEqual(observed, {
                ("saved_action_or_tool_call", "pytest", 12),
                ("saved_operation_event", "unittest", 20),
            })
            self.assertTrue(all(x["task_denominator"] == 1 and x["trajectory_denominator"] == 1 for x in details))
            self.assertEqual({x["paired_return_ids"] for x in details if x["raw_name"] == "pytest"}, {0})
            self.assertEqual({x["paired_return_ids"] for x in details if x["raw_name"] == "unittest"}, {1})
            self.assertEqual(machine["coding_reparse"]["saved_return_records_in_reparsed_command_files"]["SWE-bench_returns_saved"], 2)
            self.assertEqual(sum(x["software_component_occurrences"] for x in machine["coding_groups"]
                                 if x.get("source") == "SWE-bench" and x.get("group") == "fixture"), 5)
            self.assertEqual(sum(x["software_component_occurrences"] for x in machine["coding_groups"]),
                             sum(x.get("frequency") or 0 for x in machine["toolkits"] if x.get("scene", "").startswith("Coding/")))
            with (output / "software_toolkits.csv").open(encoding="utf-8-sig", newline="") as f:
                csv_rows = [x for x in csv.DictReader(f) if x.get("source") == "SWE-bench" and x.get("group") == "fixture"
                            and x.get("entry_kind") == "explicit_python_module"]
            self.assertEqual({(x["unit_kind"], x["raw_name"], int(x["record_denominator"])) for x in csv_rows}, observed)
            summary = (output / "summary.md").read_text()
            self.assertIn("`saved_action_or_tool_call`", summary)
            self.assertIn("`saved_operation_event`", summary)
            self.assertIn("`pytest`", summary)
            self.assertIn("`unittest`", summary)
            self.assertEqual(report["software_toolkits"]["v2_unit_kind_correction"]["affected_v2_component_occurrences"], 3)

    def test_full_generation_in_temporary_project_and_manifest_readback(self):
        with tempfile.TemporaryDirectory(prefix="public-software-toolkits-") as tmp:
            root = Path(tmp)
            expected = _make_fixture(root)
            self.assertEqual(expected, 755)
            report = ANALYZER.build(root)
            self.assertEqual(report["software_toolkits"]["counts"]["osworld_model_task_records"], 755)
            self.assertEqual(report["software_toolkits"]["counts"]["local_coding_run_count"], 9)
            local_test = next(x for x in report["rows"] if x["scene"] == "Coding/local" and x["raw_name"] == "pytest")
            self.assertEqual(local_test["paired_return_ids"], 3)
            self.assertEqual(local_test["frequency"], 3)
            local_rg = next(x for x in report["rows"] if x["scene"] == "Coding/local" and x["group"] == "django__c" and x["raw_name"] == "rg")
            self.assertEqual((local_rg["frequency"], local_rg["component_calls"], local_rg["trajectory_count"]), (6, 3, 3))
            module_rows = [x for x in report["rows"] if x["scene"] == "Coding/public" and x["source"] == "SWE-bench"
                           and x["group"] == "fixture" and x.get("entry_kind") == "explicit_python_module"]
            by_module = {x["raw_name"]: x for x in module_rows}
            self.assertEqual(set(by_module), {"pytest", "unittest"})
            self.assertEqual((by_module["pytest"]["unit_kind"], by_module["pytest"]["record_denominator"]),
                             ("saved_action_or_tool_call", 12))
            self.assertEqual((by_module["unittest"]["unit_kind"], by_module["unittest"]["record_denominator"]),
                             ("saved_operation_event", 20))
            self.assertEqual(by_module["pytest"]["paired_return_ids"], 0)
            self.assertEqual(by_module["unittest"]["paired_return_ids"], 1)
            self.assertEqual(report["software_toolkits"]["coding_reparse"]["saved_return_records_in_reparsed_command_files"]["SWE-bench_returns_saved"], 2)
            self.assertEqual({(x["unit_kind"], x["raw_name"]) for x in module_rows},
                             {("saved_action_or_tool_call", "pytest"), ("saved_operation_event", "unittest")})
            self.assertEqual(report["software_toolkits"]["counts"]["coding_group_count"], 1)
            self.assertEqual(report["software_toolkits"]["docops_inspect_document"]["resolved_status_counts"]["success"], 4)
            out = root / "reports/analysis/PUBLIC-TRACE-SOFTWARE-TOOLKITS-v3"
            ANALYZER.write_outputs(report, out)
            self.assertNotIn("python -m pytest", (out / "evidence.jsonl").read_text())
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual({x["path"] for x in manifest["outputs"]},
                             {"summary.md", "software_toolkits.csv", "software_toolkits.json", "evidence.jsonl", "corrections.md"})
            machine = json.loads((out / "software_toolkits.json").read_text())
            machine_fixture = [x for x in machine["toolkits"] if x.get("source") == "SWE-bench" and x.get("group") == "fixture"
                               and x.get("entry_kind") == "explicit_python_module"]
            self.assertEqual({(x["unit_kind"], x["raw_name"], x["record_denominator"]) for x in machine_fixture},
                             {("saved_action_or_tool_call", "pytest", 12), ("saved_operation_event", "unittest", 20)})
            group_fixture = {(x["source"], x["group"], x["unit_kind"]): x for x in machine["coding_groups"]}
            detail_totals = {}
            for item in machine["toolkits"]:
                if item.get("scene") == "Coding/public":
                    key = (item["source"], item["group"], item.get("unit_kind"))
                    detail_totals[key] = detail_totals.get(key, 0) + (item.get("frequency") or 0)
            for key, total in detail_totals.items():
                self.assertIn(key, group_fixture)
                self.assertEqual(group_fixture[key]["software_component_occurrences"], total)
            self.assertEqual(machine["v2_unit_kind_correction"]["affected_v2_rows"], 2)
            self.assertEqual(machine["v2_unit_kind_correction"]["affected_v2_component_occurrences"], 3)
            local_machine = [x for x in machine["toolkits"] if x["scene"] == "Coding/local"]
            with (out / "software_toolkits.csv").open(encoding="utf-8-sig", newline="") as f:
                all_csv_rows = list(csv.DictReader(f))
                local_csv = [x for x in all_csv_rows if x["scene"] == "Coding/local"]
                fixture_csv = [x for x in all_csv_rows if x.get("source") == "SWE-bench" and x.get("group") == "fixture"
                               and x.get("entry_kind") == "explicit_python_module"]
            self.assertEqual({(x["group"], x["raw_name"], x["frequency"], x["component_calls"]) for x in local_machine},
                             {(x["group"], x["raw_name"], int(x["frequency"]), int(x["component_calls"])) for x in local_csv})
            self.assertEqual({(x["unit_kind"], x["raw_name"], int(x["record_denominator"])) for x in fixture_csv},
                             {("saved_action_or_tool_call", "pytest", 12), ("saved_operation_event", "unittest", 20)})
            summary_text = (out / "summary.md").read_text()
            self.assertIn("saved_action_or_tool_call", summary_text)
            self.assertIn("saved_operation_event", summary_text)
            self.assertIn("`pytest`", summary_text)
            self.assertIn("`unittest`", summary_text)
            self.assertIn("astropy__a", summary_text)
            self.assertIn("astropy__b", summary_text)
            self.assertIn("django__c", summary_text)
            self.assertIn("6组件 / 3调用 / 3run", summary_text)
            self.assertIn("inspect_document", summary_text)
            self.assertIn("成功关联", summary_text)
            self.assertIn("库分支未知", summary_text)
            for item in manifest["outputs"]:
                data = (out / item["path"]).read_bytes()
                self.assertEqual((len(data), _sha(data)), (item["bytes"], item["sha256"]))
            self.assertNotIn("cdn", summary_text.lower())

    def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="public-software-hash-") as tmp:
            root = Path(tmp)
            (root / "input.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "input hash mismatch"):
                ANALYZER.Reader(root).read("input.json", {"bytes": 2, "sha256": "0" * 64})


if __name__ == "__main__":
    unittest.main(verbosity=2)
