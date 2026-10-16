from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.docops_office_repeat_characterization import (
    COLLECTION, IDENTITY, RAW, REPORT, SCHEDULE, TASKS, _decode_action, analyze, file_record, sha256,
)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def sign_outputs(run_dir: Path) -> list[dict]:
    return [{"path": p.relative_to(run_dir).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(run_dir.rglob("*")) if p.is_file() and p.name != "manifest.json"]


def fixture(root: Path, *, cpu=(100, 300, 600), memory=(10, 12, 14), include_return=True, tool="xlsx_set_formula"):
    repo = Path(__file__).resolve().parents[1]
    for relative in ("scripts/docops_office_repeat_characterization.py", "scripts/docops_word_resource_analysis.py"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repo / relative).read_bytes())
    identity = json.loads((repo / "env/docops-office-repeat-01/frozen-identity.json").read_text())["identity"]
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert digest == IDENTITY
    env = root / "env/docops-office-repeat-01"
    write_json(env / "plan-identity.json", {"identity": identity, "identity_sha256": digest})
    write_json(env / "frozen-identity.json", {"identity": identity, "identity_sha256": digest})
    approval_dir = root / "reports/resource" / COLLECTION
    write_json(approval_dir / "APPROVAL.json", {"collection": COLLECTION, "identity_sha256": digest, "user_approval": "approved"})

    results, raw_refs = [], []
    sample_times = (0, 2_000_000_000, 4_000_000_000)
    for round_no, task_row in enumerate(SCHEDULE):
        for task in task_row:
            short = {TASKS[0]: "excel001", TASKS[1]: "ppt008", TASKS[2]: "pdf004"}[task]
            run_id = f"fixture-r{round_no}-{short}"
            run_dir = root / RAW / run_id
            agent = run_dir / "agent"
            args = {"path": f"/root/{short}.xlsx", "sheet_name": "Sheet1", "cell": "B2", "formula": "=SUM(A1:A2)"}
            action_call = {"thought": "synthetic", "action": "call_tool", "tool_name": tool, "arguments": args}
            action_finish = {"thought": "synthetic", "action": "finish", "tool_name": None, "arguments": {}, "final_message": "done"}
            def log_response(action, messages, index):
                response = {"model": "deepseek-flash", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(action)}}],
                            "usage": {"prompt_tokens": index * 10, "completion_tokens": 5, "total_tokens": index * 10 + 5,
                                      "prompt_tokens_details": {"cached_tokens": index}}}
                return {"model": "deepseek-v4-flash", "custom_llm_provider": "openai",
                        "original_response": json.dumps(response), "messages": messages}
            bootstrap_messages = [
                {"role": "user", "content": "Bootstrap tool result (get_task_metadata): {}"},
                {"role": "user", "content": "Bootstrap tool result (inspect_document on input_path): {}"},
            ]
            write_json(agent / "llm_call_1.json", log_response(action_call, bootstrap_messages, 1))
            history = [{"role": "assistant", "content": json.dumps(action_call)}]
            if include_return:
                history.append({"role": "user", "content": f"Tool result for {tool}:\n{{\"ok\":true}}\nDecide the next action."})
            write_json(agent / "llm_call_2.json", log_response(action_finish, history, 2))
            events = [
                {"phase": "agent_setup_begin", "t_monotonic_ns": 500_000_000},
                {"phase": "agent_setup_done", "t_monotonic_ns": 750_000_000},
                {"phase": "agent_begin", "t_monotonic_ns": 1_000_000_000},
                {"phase": "agent_end", "t_monotonic_ns": 3_000_000_000},
                {"phase": "verifier_begin", "t_monotonic_ns": 3_500_000_000},
                {"phase": "verifier_end", "t_monotonic_ns": 4_500_000_000},
                {"phase": "harbor_stop_begin", "t_monotonic_ns": 5_000_000_000},
                {"phase": "harbor_stop_done", "t_monotonic_ns": 6_000_000_000, "stop_error": None},
                {"phase": "removal_verified", "t_monotonic_ns": 6_100_000_000, "result": "removed"},
            ]
            samples = []
            for i, timestamp in enumerate(sample_times):
                samples.append({"t_monotonic_ns": timestamp,
                                "container": {"t_monotonic_ns": timestamp, "cpu_usage_usec": cpu[i],
                                              "mem_current_bytes": memory[i], "mem_peak_bytes": memory[i] + 5 if memory[i] is not None else None,
                                              "io_read_bytes": i * 100, "io_write_bytes": i * 50,
                                              "read_status": {"cpuacct.usage": "ok_ns_converted_to_usec",
                                                              "io": "ok_summed_devices:blkio.throttle.io_service_bytes_recursive"}},
                                "host_agent": {"rss_bytes": 100 + i}})
            summary = {"run_id": run_id, "collection": COLLECTION, "task_key": task, "round": round_no,
                       "identity_sha256": digest, "wall_s": 10.0, "within_total_budget": True,
                       "outcome": {"phases": {"agent": {"status": "finish", "n_input_tokens": 20,
                                                            "n_output_tokens": 10, "n_cache_tokens": 5},
                                              "verifier": {"status": "completed", "reward": 1.0}}, "infra_failures": []},
                       "events": events, "samples": samples}
            write_json(run_dir / "summary.json", summary)
            write_json(run_dir / "ATTEMPT_STARTED.json", {"run_id": run_id})
            write_json(run_dir / "ATTEMPT_COMPLETED.json", {"run_id": run_id})
            (agent / "document-tools-agent.txt").write_text("STEP 1\n{}\nSTEP 2\n{}\n", encoding="utf-8")
            raw_manifest = {"run_id": run_id, "task_key": task, "round": round_no, "identity_sha256": digest,
                            "inputs": [], "outputs": sign_outputs(run_dir)}
            raw_manifest_path = run_dir / "manifest.json"
            write_json(raw_manifest_path, raw_manifest)
            raw_refs.append({"path": raw_manifest_path.relative_to(root).as_posix(), "bytes": raw_manifest_path.stat().st_size,
                             "sha256": sha256(raw_manifest_path)})
            results.append({"round": round_no, "task_key": task, "run_id": run_id, "status": "executed", "returncode": 0,
                            "identity_sha256": digest, "termination": "finish", "reward": 1.0,
                            "archive_verified": True, "archive_errors": [], "model_requests_logged": 2,
                            "action_counts": {"call_tool": 1, "finish": 1},
                            "bootstrap_tool_counts_from_first_request_history": {"get_task_metadata": 1, "inspect_document": 1}})
    batch_summary = {"schema": "docops-office-repeat-batch-summary-v1", "collection": COLLECTION,
                     "identity_sha256": digest, "results": results, "batch_wall_s": 60.0}
    batch_summary_path = approval_dir / "batch-summary.json"
    write_json(batch_summary_path, batch_summary)
    manifest_inputs = [file_record(root, path) for path in (env / "plan-identity.json", env / "frozen-identity.json",
                                                             approval_dir / "APPROVAL.json",
                                                             root / "scripts/docops_office_repeat_characterization.py",
                                                             root / "scripts/docops_word_resource_analysis.py")]
    batch_manifest = {"schema": "docops-office-repeat-batch-manifest-v1", "identity_sha256": digest,
                      "inputs": manifest_inputs, "outputs": [file_record(root, batch_summary_path)],
                      "raw_run_manifests": raw_refs}
    write_json(approval_dir / "batch-manifest.json", batch_manifest)
    return results


class DocOpsOfficeRepeatCharacterizationTests(unittest.TestCase):
    def test_harness_embedded_json_recovery_and_actual_invalid_are_separate(self):
        embedded = {"thought": "synthetic", "action": "finish", "tool_name": None,
                    "arguments": {}, "final_message": "done"}
        wrapped = {"original_response": json.dumps({"model": "deepseek-flash", "choices": [
            {"finish_reason": "stop", "message": {"content": "prefix " + json.dumps(embedded) + " suffix"}}]})}
        action, evidence = _decode_action(wrapped)
        self.assertEqual(action["action"], "finish")
        self.assertEqual(evidence["status"], "finish")
        self.assertEqual(evidence["parse_method"], "first_embedded_json_object")
        unsupported = {"original_response": json.dumps({"choices": [
            {"message": {"content": json.dumps({"thought": "x", "action": "other", "arguments": {}})}}]})}
        _, bad_evidence = _decode_action(unsupported)
        self.assertEqual(bad_evidence["status"], "invalid_or_unknown")
        self.assertEqual(bad_evidence["reason"], "unsupported_action_value")

    def test_nine_run_entry_generates_hashed_outputs_and_separates_bootstrap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            out = root / "reports/analysis/fixture"
            result = analyze(root, out)
            self.assertEqual(result["summary"]["n_runs"], 9)
            self.assertEqual(result["summary"]["logical_request_count"], 18)
            self.assertEqual(result["summary"]["agent_tool_call_count"], 9)
            self.assertEqual(result["summary"]["bootstrap_totals"], {"get_task_metadata": 9, "inspect_document": 9})
            self.assertTrue(all(r["requests"]["return_status_counts"] == {"saved_ok_true": 1} for r in result["runs"]))
            manifest = json.loads((out / "manifest.json").read_text())
            for item in manifest["outputs"]:
                path = root / item["path"]
                self.assertEqual((path.stat().st_size, sha256(path)), (item["bytes"], item["sha256"]))
            self.assertNotIn("manifest.json", [x["path"].split("/")[-1] for x in manifest["outputs"]])
            self.assertTrue(str(out).startswith(temp))

    def test_behavior_or_resource_fixture_change_changes_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root_a = Path(temp) / "a"
            fixture(root_a, cpu=(100, 300, 600), tool="xlsx_set_formula")
            a = analyze(root_a, root_a / "reports/analysis/a")["runs"][0]
            root_b = Path(temp) / "b"
            fixture(root_b, cpu=(100, 700, 1600), tool="xlsx_write_cells")
            b = analyze(root_b, root_b / "reports/analysis/b")["runs"][0]
            self.assertNotEqual(a["tool_sequence"], b["tool_sequence"])
            self.assertNotEqual(a["resources"]["container_cpu_core_s"], b["resources"]["container_cpu_core_s"])

    def test_manifest_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            raw_summary = root / RAW / "fixture-r0-excel001" / "summary.json"
            raw_summary.write_text(raw_summary.read_text() + " ", encoding="utf-8")
            with self.assertRaises(ValueError):
                analyze(root, root / "reports/analysis/out")

    def test_missing_tool_return_stays_unknown_not_failed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root, include_return=False)
            # Resign the altered fixture log and its raw manifest so only result-linkage is under test.
            run_dir = root / RAW / "fixture-r0-excel001"
            raw_manifest_path = run_dir / "manifest.json"
            raw = json.loads(raw_manifest_path.read_text())
            raw["outputs"] = sign_outputs(run_dir)
            write_json(raw_manifest_path, raw)
            approval_dir = root / "reports/resource" / COLLECTION
            batch = json.loads((approval_dir / "batch-summary.json").read_text())
            batch_item = next(x for x in batch["results"] if x["run_id"] == "fixture-r0-excel001")
            batch_item["archive_verified"] = True
            write_json(approval_dir / "batch-summary.json", batch)
            manifest = json.loads((approval_dir / "batch-manifest.json").read_text())
            ref = next(x for x in manifest["raw_run_manifests"] if x["path"].endswith("fixture-r0-excel001/manifest.json"))
            ref.update({"bytes": raw_manifest_path.stat().st_size, "sha256": sha256(raw_manifest_path)})
            for output in manifest["outputs"]:
                if output["path"].endswith("batch-summary.json"):
                    path = root / output["path"]
                    output.update({"bytes": path.stat().st_size, "sha256": sha256(path)})
            write_json(approval_dir / "batch-manifest.json", manifest)
            run = analyze(root, root / "reports/analysis/out")["runs"][0]
            self.assertEqual(run["requests"]["return_status_counts"], {"missing_or_unlinked": 1})
            self.assertEqual(run["cleanup"]["results"], ["removed"])

    def test_cpu_reset_and_missing_memory_are_null(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root, cpu=(900, 500, 1000), memory=(None, None, None))
            # Fixture builder signs summary; rewrite and resign the one tested run.
            run_dir = root / RAW / "fixture-r0-excel001"
            summary_path = run_dir / "summary.json"
            summary = json.loads(summary_path.read_text())
            for sample, value in zip(summary["samples"], (900, 500, 1000)):
                sample["container"]["cpu_usage_usec"] = value
                sample["container"]["mem_current_bytes"] = None
            write_json(summary_path, summary)
            raw_path = run_dir / "manifest.json"
            raw = json.loads(raw_path.read_text())
            raw["outputs"] = sign_outputs(run_dir)
            write_json(raw_path, raw)
            batch_dir = root / "reports/resource" / COLLECTION
            batch_manifest_path = batch_dir / "batch-manifest.json"
            batch_manifest = json.loads(batch_manifest_path.read_text())
            ref = next(x for x in batch_manifest["raw_run_manifests"] if x["path"].endswith("fixture-r0-excel001/manifest.json"))
            ref.update({"bytes": raw_path.stat().st_size, "sha256": sha256(raw_path)})
            write_json(batch_manifest_path, batch_manifest)
            run = analyze(root, root / "reports/analysis/out")["runs"][0]
            self.assertIsNone(run["resources"]["container_cpu_core_s"])
            self.assertEqual(run["resources"]["cpu_status"], "cpu_counter_decreased")
            self.assertIsNone(run["resources"]["memory_current_sampled_peak_bytes"])

    def test_phase_boundary_cpu_remains_mixed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            run = analyze(root, root / "reports/analysis/out")["runs"][0]
            resources = run["resources"]
            self.assertGreater(resources["sample_intervals_crossing_recorded_event_boundaries"], 0)
            self.assertGreater(resources["boundary_mixed_cpu_interval_count"], 0)
            self.assertIsNone(resources["phase_metrics"]["agent"]["sampled_cpu_core_s"])


if __name__ == "__main__":
    unittest.main()
