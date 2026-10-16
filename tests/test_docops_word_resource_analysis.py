import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.docops_word_resource_analysis import RUNS, analyze, _label_counts, _resource_metrics


def put(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_json(path: Path, value) -> None:
    put(path, (json.dumps(value, ensure_ascii=False) + "\n").encode())


def make_docx(path: Path, text="A heading", include_toc=False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    toc = '<w:p><w:r><w:t>a. Isolation logic</w:t><w:tab/><w:t>4</w:t></w:r></w:p>' if include_toc else ""
    document = f'''<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>{toc}</w:body></w:document>'''
    styles = '''<?xml version="1.0"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/></w:style></w:styles>'''
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", document)
        zf.writestr("word/styles.xml", styles)


def fixture(root: Path, calls=1, cpu=(100, 300), include_return=True, finish=True) -> tuple:
    analyzer = Path(__file__).resolve().parents[1] / "scripts/docops_word_resource_analysis.py"
    put(root / "scripts/docops_word_resource_analysis.py", analyzer.read_bytes())
    task = root / "references/repos/DocOps/tasks/atomic__word_001_engineering_report_toc_hierarchy_seed"
    put(task / "task.toml", b"task")
    put(task / "instruction.md", b"instruction")
    put(task / "environment/task_metadata.json", b"{}")
    make_docx(task / "environment/word_001_engineering_report_toc_hierarchy_seed.docx")
    input_paths = {
        "task.toml": task / "task.toml",
        "instruction.md": task / "instruction.md",
        "environment/task_metadata.json": task / "environment/task_metadata.json",
        "input.docx": task / "environment/word_001_engineering_report_toc_hierarchy_seed.docx",
    }
    specs = []
    for (collection, run_id, suffix), identity in zip(RUNS, ("id03", "id04")):
        run = root / "data/raw/generated" / collection / run_id
        (run / "agent").mkdir(parents=True)
        (run / "verifier/submission").mkdir(parents=True)
        make_docx(run / "verifier/submission/word_001_engineering_report_toc_hierarchy_seed.docx")
        n = calls
        events = [
            {"phase": "agent_setup_begin", "t_monotonic_ns": 10},
            {"phase": "agent_setup_done", "t_monotonic_ns": 20},
            {"phase": "agent_begin", "t_monotonic_ns": 25},
            {"phase": "agent_end", "t_monotonic_ns": 80},
            {"phase": "verifier_begin", "t_monotonic_ns": 82},
            {"phase": "verifier_end", "t_monotonic_ns": 95},
            {"phase": "removal_verified", "t_monotonic_ns": 110, "result": "removed"},
        ]
        status = "steps_exhausted" if suffix == "03" else "finish"
        summary = {"run_id": run_id, "collection": collection, "identity_sha256": identity, "wall_s": 1.2,
                   "within_total_budget": True, "container": {"id": "fixture-container"},
                   "outcome": {"phases": {"agent": {"status": status, "n_input_tokens": 4, "n_output_tokens": 2,
                                                    "n_cache_tokens": 1},
                                           "verifier": {"status": "completed", "reward": 0}}},
                   "events": events, "samples": [
                       {"t_monotonic_ns": 30, "container": {"cpu_usage_usec": cpu[0], "mem_current_bytes": 10,
                        "mem_peak_bytes": 15, "io_read_bytes": 0, "io_write_bytes": 0,
                        "read_status": {"cpuacct.usage": "ok_ns_converted_to_usec", "io": "unknown"}},
                        "host_agent": {"rss_bytes": 20}},
                       {"t_monotonic_ns": 70, "container": {"cpu_usage_usec": cpu[1], "mem_current_bytes": 12,
                        "mem_peak_bytes": 18, "io_read_bytes": 0, "io_write_bytes": 0,
                        "read_status": {"cpuacct.usage": "ok_ns_converted_to_usec", "io": "unknown"}},
                        "host_agent": {"rss_bytes": 25}},
                   ]}
        write_json(run / "summary.json", summary)
        write_json(run / "ATTEMPT_STARTED.json", {"run_id": run_id, "identity_sha256": identity})
        write_json(run / "ATTEMPT_COMPLETED.json", {"run_id": run_id})
        write_json(run / "verifier/ctrf.json", {"results": {"tests": [{"name": "semantic", "status": "failed"}]}})
        put(run / "verifier/reward.txt", b"0\n")
        (run / "agent/document-tools-agent.txt").write_text("STEP 1\n", encoding="utf-8")
        for i in range(1, n + 1):
            action = {"action": "call_tool", "tool_name": "word_inspect_format", "arguments": {"paragraph_index": i}, "final_message": None} if i < n or not finish else {"action": "finish", "tool_name": None, "arguments": {}, "final_message": "done"}
            response = {"model": "deepseek-flash", "choices": [{"message": {"content": json.dumps(action)}}]}
            messages = [{"role": "system", "content": "system"}]
            if i > 1 and include_return:
                messages.extend([
                    {"role": "assistant", "content": json.dumps({"action": "call_tool", "tool_name": "word_inspect_format", "arguments": {"paragraph_index": i - 1}})},
                    {"role": "user", "content": 'Tool result for word_inspect_format:\n{"ok":true}\nDecide the next action.'},
                ])
            write_json(run / f"agent/llm_call_{i}.json", {"model": "openai/deepseek-v4-flash", "original_response": json.dumps(response), "messages": messages})
        plan = {"collection": collection, "identity_sha256": identity, "identity": {"budget": {"max_steps": 12 if suffix == "03" else 40}, "files": {}}}
        frozen = {"collection": collection, "identity_sha256": identity}
        approval = {"schema": "docops-single-run-approval-v1", "collection": collection,
                    "identity_sha256": identity, "user_approval": "approved"}
        write_json(root / f"env/docops-arm64-word001/plan-identity-{suffix}.json", plan)
        write_json(root / f"env/docops-arm64-word001/frozen-identity-{suffix}.json", frozen)
        write_json(root / f"reports/resource/{collection}/APPROVAL.json", approval)
        outputs = []
        for path in sorted(p for p in run.rglob("*") if p.is_file() and p.name != "manifest.json"):
            outputs.append({"path": path.relative_to(run).as_posix(), "bytes": path.stat().st_size,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        inputs = [{"path": key, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for key, path in input_paths.items()]
        write_json(run / "manifest.json", {"run_id": run_id, "identity_sha256": identity, "inputs": inputs, "outputs": outputs})
        specs.append((collection, run_id, suffix))
    return tuple(specs)


class DocOpsWordResourceAnalysisTests(unittest.TestCase):
    def test_docx_text_keeps_toc_tab_separate_from_body_label(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "with-toc.docx"
            make_docx(path, "a. Isolation logic", include_toc=True)
            counts = _label_counts(path)
            self.assertEqual(counts["new_body_label_exact_paragraphs"], 1)
            self.assertEqual(counts["new_toc_label_exact_paragraphs"], 1)
            self.assertEqual(counts["old_label_occurrences"], 0)

    def test_full_two_run_entry_writes_verified_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = fixture(root)
            out = root / "reports/analysis/review"
            result = analyze(root, out, specs)
            runs = result["summary"]["runs"]
            self.assertEqual([r["max_steps"] for r in runs], [12, 40])
            self.assertEqual([r["termination"] for r in runs], ["steps_exhausted", "finish"])
            self.assertTrue(all(r["identity_verified"] and r["archive_verified"] for r in runs))
            self.assertTrue((out / "per_run.json").is_file())
            self.assertTrue((out / "summary.md").is_file())
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(len(manifest["outputs"]), 3)
            self.assertNotIn("manifest.json", [x["path"].split("/")[-1] for x in manifest["outputs"]])

    def test_fixture_action_and_resource_change_changes_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = fixture(root, calls=2, cpu=(100, 300))
            first = analyze(root, root / "reports/a", specs)["summary"]["runs"][0]
            # Change saved source evidence in a fresh independent fixture/output.
            root2 = Path(temp) / "second"
            specs2 = fixture(root2, calls=3, cpu=(100, 900))
            second = analyze(root2, root2 / "reports/b", specs2)["summary"]["runs"][0]
            self.assertNotEqual(first["model_calls"], second["model_calls"])
            self.assertNotEqual(first["container_cpu_core_s"], second["container_cpu_core_s"])

    def test_manifest_hash_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = fixture(root)
            run = root / "data/raw/generated" / specs[0][0] / specs[0][1]
            path = run / "verifier/reward.txt"
            path.write_bytes(b"1\n")
            with self.assertRaises(ValueError):
                analyze(root, root / "reports/analysis/x", specs)

    def test_missing_and_rolled_back_cpu_are_not_zero(self):
        summary = {"samples": [
            {"t_monotonic_ns": 1, "container": {"cpu_usage_usec": 900, "read_status": {"cpuacct.usage": "ok_ns_converted_to_usec"}}},
            {"t_monotonic_ns": 2, "container": {"cpu_usage_usec": 100, "read_status": {"cpuacct.usage": "ok_ns_converted_to_usec"}}},
        ], "events": []}
        metrics = _resource_metrics(summary)
        self.assertIsNone(metrics["container_cpu_core_s"])
        self.assertEqual(metrics["cpu_status"], "cpu_counter_decreased")
        self.assertIsNone(metrics["memory_current_sampled_peak_bytes"])
        self.assertIsNone(_resource_metrics({"samples": [], "events": []})["container_cpu_core_s"])

    def test_nonmonotonic_sample_clock_invalidates_window(self):
        summary = {"samples": [
            {"t_monotonic_ns": 20, "container": {"cpu_usage_usec": 100, "read_status": {"cpuacct.usage": "ok_ns_converted_to_usec"}}},
            {"t_monotonic_ns": 10, "container": {"cpu_usage_usec": 200, "read_status": {"cpuacct.usage": "ok_ns_converted_to_usec"}}},
        ], "events": []}
        result = _resource_metrics(summary)
        self.assertIsNone(result["sample_window_s"])
        self.assertIsNone(result["container_cpu_core_s"])
        self.assertEqual(result["cpu_status"], "sample_clock_missing_or_nonmonotonic")

    def test_finish_steps_reward_and_missing_terminal_result_are_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = fixture(root, calls=1, include_return=False, finish=False)
            result = analyze(root, root / "reports/analysis/x", specs)
            run = result["summary"]["runs"][0]
            detail = json.loads((root / "reports/analysis/x/per_run.json").read_text())[0]
            self.assertEqual(run["termination"], "steps_exhausted")
            self.assertEqual(run["reward"], 0)
            self.assertEqual(detail["tool_return_status_counts"].get("unknown_not_persisted_or_not_linkable"), 1)


if __name__ == "__main__":
    unittest.main()
