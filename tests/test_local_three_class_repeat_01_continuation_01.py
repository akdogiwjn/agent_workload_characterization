"""Offline continuation acceptance tests; fixtures stay under temporary roots."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from contextlib import redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import local_three_class_repeat_01_continuation_01_entry as entry


def tree_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class ContinuationAcceptanceTests(unittest.TestCase):
    def test_office_route_flows_through_real_config_and_agent_builder(self):
        import docops_office_repeat_01_entry as office
        import docops_word_resource_01_entry as shared
        route = {"api_base": "https://gateway.invalid/v1",
                 "request_model": "openai/deepseek-v4-flash", "credential_env": "VOLCANO_API_KEY"}
        task = {"key": entry.TASKS["Office"][0], "image_ref": "fixed", "image_id": "sha256:fixed"}
        captured = []
        class FakeAgent:
            def __init__(self, **kwargs):
                captured.append(kwargs)
                self.llm = object()
        module = SimpleNamespace(DocOpsWordAgent=FakeAgent)
        with tempfile.TemporaryDirectory() as tmp, patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), \
                patch.dict(sys.modules, {"agent_workload_characterization.runners.docops_word_agent": module}):
            config = entry.office_config_with_route(office, task, 0, route)
            shared.build_agent(Path(tmp), config)
        self.assertEqual(captured[0]["api_base"], route["api_base"])
        self.assertEqual(captured[0]["model_name"], route["request_model"])
        for invalid in ({}, {"model_route": {}},
                        {"model_route": {**route, "api_base": "https://wrong.invalid/v1"}}):
            with self.assertRaisesRegex(ValueError, "model_route"):
                entry.validate_office_route(invalid, route)

    def test_office_child_rejects_missing_route_before_run_attempt(self):
        from unittest.mock import Mock
        fake = SimpleNamespace(run_attempt=Mock(side_effect=AssertionError("must not execute")))
        task = {"key": "fixed"}
        frozen = {"identity": {"components": {"Office": {"tasks": [task],
            "model": {"route": {"api_base": "https://gateway.invalid/v1", "request_model": "m", "credential_env": "VOLCANO_API_KEY"}},
            "run_configs_by_task_round": {"fixed": [{}]}}}}}
        with patch.dict(sys.modules, {"docops_office_repeat_01_entry": SimpleNamespace(),
                                      "docops_word_resource_01_entry": fake}):
            with self.assertRaisesRegex(ValueError, "model_route"):
                entry._run_office({"task": "fixed", "round": 0}, frozen, "unused", 0)
        fake.run_attempt.assert_not_called()

    def test_batch_rejects_missing_route_before_images_credentials_or_attempt(self):
        from unittest.mock import Mock
        frozen = {"identity": {"components": {"Office": {
            "model": {"route": {"api_base": "https://gateway.invalid/v1", "request_model": "m", "credential_env": "VOLCANO_API_KEY"}},
            "run_configs_by_task_round": {"fixed": [{}]}}}}}
        images = Mock(side_effect=AssertionError("must not inspect Docker"))
        writes = Mock(side_effect=AssertionError("must not create approval/attempt"))
        with patch.object(entry, "read_json", return_value=frozen), \
                patch.object(entry, "verify_identity"), patch.object(entry, "namespace_clean", return_value=True), \
                patch.object(entry, "_image_records", images), patch.object(entry, "write_new", writes):
            with self.assertRaisesRegex(ValueError, "model_route"):
                entry.execute()
        images.assert_not_called()
        writes.assert_not_called()

    def test_no_candidate_skipped_verifier_is_not_a_measurement_gap(self):
        raw = ROOT / "data/raw/generated/LOCAL-THREE-CLASS-REPEAT-01-CONTINUATION-01/20261017T024449Z-04-r1-coding"
        report = json.loads((ROOT / "reports/resource/LOCAL-THREE-CLASS-REPEAT-01-CONTINUATION-01/20261017T024449Z-04-r1-coding/run-report.json").read_text())
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
            actual = entry.slot_acceptance("Coding", {"chain": "Coding", "round": 1}, report, raw)
        self.assertEqual(actual["measurement"]["status"], "complete")
        self.assertEqual(actual["measurement"]["not_applicable"]["verifier_container"]["status"], "not_applicable")
        self.assertEqual(entry.stop_policy(actual), (False, False, None))
        # A verifier that was expected or actually started must still be checked.
        actual = entry.measurement_quality(raw, "Coding", {**report, "execution_status": "ok", "evaluation_status": "ok"})
        self.assertIn("verifier_container_cpu_intervals_missing", actual["gaps"])
        evidence = {"v": {"scope_kind": "verifier_container"}}
        self.assertFalse(entry.verifier_not_applicable(raw, report, evidence))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "events.jsonl").write_text(json.dumps({"kind": "verifier", "attrs": {"status": "not_run"}}) + "\n" +
                json.dumps({"kind": "container", "attrs": {"scope": "verifier", "action": "start"}}) + "\n")
            self.assertFalse(entry.verifier_not_applicable(p, report, {}))

    def test_structured_bad_request_stops_without_copying_error_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "agent").mkdir()
            (raw / "agent/events.jsonl").write_text(json.dumps({"kind": "llm_request", "attrs": {
                "error_type": "BadRequestError", "error": "sensitive detail must not be used"}}) + "\n")
            self.assertTrue(entry._class_protocol_failure(raw, "Office"))
            result = {"cleanup_status": "confirmed", "archive_status": "verified", "measurement": {"status": "complete"}, "infra_status": "ok"}
            self.assertEqual(entry.stop_policy(result, shared_auth_failure=True),
                             (True, True, "shared_gateway_authentication_or_route_failure"))
            (raw / "agent/events.jsonl").write_text(json.dumps({"kind": "llm_request", "status": "error",
                "attrs": {"ok": False, "error": "BadRequestError:<sanitized>"}}) + "\n")
            self.assertTrue(entry._class_protocol_failure(raw, "Office"))
            actual = ROOT / "data/raw/generated/LOCAL-THREE-CLASS-REPEAT-01-CONTINUATION-01/20261017T024718Z-09-r0-office"
            self.assertTrue(entry._class_protocol_failure(actual, "Office"))

    def test_schedule_is_26_slots_and_skips_only_existing_excel_slot(self):
        rows = entry.planned_schedule()
        self.assertEqual(len(rows), 26)
        self.assertEqual([x["sequence"] for x in rows], list(range(26)))
        self.assertEqual(len({(x["chain"], x["round"], x["task"]) for x in rows}), 26)
        office = [x for x in rows if x["chain"] == "Office"]
        self.assertEqual(len(office), 8)
        self.assertNotIn(("Office", 0, entry.TASKS["Office"][0]),
                         {(x["chain"], x["round"], x["task"]) for x in rows})
        self.assertEqual([x["task"] for x in office], [
            entry.TASKS["Office"][1], entry.TASKS["Office"][2],
            entry.TASKS["Office"][1], entry.TASKS["Office"][2], entry.TASKS["Office"][0],
            entry.TASKS["Office"][2], entry.TASKS["Office"][0], entry.TASKS["Office"][1]])

    def test_complete02_profile_is_the_twelve_authorized_replacements(self):
        rows = entry.planned_schedule(entry.COMPLETE_02_PROFILE)
        self.assertEqual([(x["chain"], x["round"], x["task"]) for x in rows],
                         list(entry.COMPLETE_02_SLOTS))
        self.assertEqual([x["sequence"] for x in rows], list(range(12)))
        self.assertEqual(len({(x["chain"], x["round"], x["task"]) for x in rows}), 12)
        old = json.loads((ROOT / "reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v2/summary.json").read_text())
        old_slots = old["slot_census_27"]
        for row in rows:
            if row["chain"] == "Coding":
                source = [x for x in old_slots if x.get("chain") == "Coding"
                          and x.get("round") == row["round"] and x.get("task") == row["task"]
                          and x.get("slot_status") == "not_executed"]
                self.assertEqual(len(source), 1)
                self.assertEqual(row["replaces_original_sequence"], source[0]["original_sequence"])
            else:
                source = [x for x in old["run_references"] if x.get("chain") == "Office"
                          and x.get("round") == row["round"] and x.get("task") == row["task"]
                          and x.get("profile_stratum") == "continuation_Office_route_mismatch"]
                self.assertEqual(len(source), 1)
                self.assertEqual(row["replaces_run_id"], source[0]["run_id"])

    def test_complete02_office_component_binds_route_in_every_task_round_config(self):
        office = entry._component_process("Office", entry.COMPLETE_02_PROFILE)
        route = office["model"]["route"]
        self.assertEqual(route["provider"], "火山AI网关")
        for task in entry.TASKS["Office"]:
            self.assertEqual(len(office["run_configs_by_task_round"][task]), 3)
            for config in office["run_configs_by_task_round"][task]:
                entry.validate_office_route(config, route)
                self.assertEqual(config["collection"], entry.COMPLETE_02_PROFILE.collection)

    def test_complete02_plan_mode_does_not_create_approval_or_attempt(self):
        output = io.StringIO()
        with patch.object(entry, "namespace_clean", return_value=True), \
             patch.object(entry, "write_new", side_effect=AssertionError("plan wrote a file")), \
             redirect_stdout(output):
            self.assertEqual(entry.main(["--profile", "complete02"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["collection"], entry.COMPLETE_02_PROFILE.collection)
        self.assertEqual(len(result["schedule"]), 12)
        # COMPLETE-02 is already frozen before execution; plan mode reports it
        # without creating approval/attempt artifacts or rewriting the freeze.
        self.assertTrue(result["identity_exists"])

    def test_three_saved_production_shapes_pass_independent_acceptance(self):
        sources = (
            ("Office", "LOCAL-THREE-CLASS-REPEAT-01", "20261016T182559Z-09-r0-office",
             "reports/resource/LOCAL-THREE-CLASS-REPEAT-01/20261016T182559Z-09-r0-office/run-report.json"),
            ("Coding", "CODING-MEASUREMENT-VOLCANO-01", "20261016T144518Z-django16485-91776c",
             "reports/resource/CODING-MEASUREMENT-VOLCANO-01/run-report.json"),
            ("Assistant", "TOOLSANDBOX-MEASUREMENT-VOLCANO-01", "20261016T145056Z-tsbvolcano01",
             "reports/resource/TOOLSANDBOX-MEASUREMENT-VOLCANO-01/run-report.json"),
        )
        snapshots = []
        results = []
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
            for chain, collection, run_id, report_path in sources:
                raw = ROOT / "data/raw/generated" / collection / run_id
                snapshots.append(tree_hashes(raw))
                report = json.loads((ROOT / report_path).read_text())
                result = entry.slot_acceptance(chain, {"chain": chain, "task": "fixed", "round": 0}, report, raw)
                results.append(result)
                self.assertEqual(result["slot_status"], "executed")
                self.assertEqual(result["cleanup_status"], "confirmed")
                self.assertEqual(result["archive_status"], "verified")
                self.assertEqual(result["measurement"]["status"], "complete")
                self.assertEqual(entry.stop_policy(result), (False, False, None))
        for source, old in zip(sources, snapshots):
            raw = ROOT / "data/raw/generated" / source[1] / source[2]
            self.assertEqual(tree_hashes(raw), old)
        office = results[0]
        self.assertIn("host_agent_process", office["measurement"]["cpu_intervals"])
        self.assertTrue(office["measurement"]["network"]["network_valid_interface_interval_records"] > 0)
        self.assertIn("agent_container", results[1]["measurement"]["cpu_intervals"])
        self.assertIn("verifier_container", results[1]["measurement"]["cpu_intervals"])
        self.assertEqual(results[2]["measurement"]["network"]["network_samples"], 40)

    def test_unreadable_office_report_keeps_raw_cleanup_and_stops_only_its_chain(self):
        raw = ROOT / "data/raw/generated/LOCAL-THREE-CLASS-REPEAT-01/20261016T182559Z-09-r0-office"
        result = entry.slot_acceptance("Office", {"chain": "Office", "round": 0}, {}, raw)
        self.assertEqual(result["cleanup_status"], "confirmed")
        self.assertEqual(result["archive_status"], "verified")
        self.assertEqual(result["measurement"]["status"], "complete")
        result["infra_status"] = "unknown"
        self.assertEqual(entry.stop_policy(result), (True, False, "chain_infrastructure_failure"))
        self.assertIsNone(result["task_result"])

    def test_unconfirmed_cleanup_is_global_stop_even_when_task_reward_is_known(self):
        result = {"cleanup_status": "unconfirmed", "archive_status": "verified",
                  "infra_status": "ok", "measurement": {"status": "complete"},
                  "task_result": 1.0}
        self.assertEqual(entry.stop_policy(result), (True, True, "cleanup_unconfirmed"))

    def test_counter_quality_is_per_metric_and_does_not_fill_missing_io(self):
        rows = [
            {"scope": "agent", "t_monotonic_ns": 1_000_000_000,
             "cpu_usage_usec": 1_000_000, "io_read_bytes": 10,
             "io_write_bytes": 0,
             "read_status": {"cpuacct.usage": "ok", "io": "permission_denied"}},
            {"scope": "agent", "t_monotonic_ns": 2_000_000_000,
             "cpu_usage_usec": 2_000_000, "io_read_bytes": 20,
             "io_write_bytes": 0,
             "read_status": {"cpuacct.usage": "ok", "io": "ok"}},
        ]
        actual = entry._interval_status_from_samples(rows)
        self.assertEqual(actual["cpu"], {"candidate": 1, "valid": 1, "gaps": 0})
        self.assertEqual(actual["io_read"], {"candidate": 1, "valid": 0, "gaps": 1})
        self.assertEqual(actual["io_write"], {"candidate": 1, "valid": 0, "gaps": 1})

    def test_raw_manifest_fixture_is_temp_only_and_refuses_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "payload.json").write_text("{}\n")
            row = {"path": "payload.json", "bytes": (root / "payload.json").stat().st_size,
                   "sha256": hashlib.sha256((root / "payload.json").read_bytes()).hexdigest()}
            (root / "manifest.json").write_text(json.dumps({"outputs": [row]}))
            self.assertEqual(entry.verify_raw(root, "Office")["hashes_match"], True)
            (root / "payload.json").write_text("null\n")
            with self.assertRaisesRegex(ValueError, "hash"):
                entry.verify_raw(root, "Office")


if __name__ == "__main__":
    unittest.main()
