"""Offline route wiring regressions for the three single-run profiles."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src"),
               str(ROOT / "references/repos/DocOps/harnesses")]

import docops_measurement_validate_01_entry as office_profile
import docops_word_resource_01_entry as office_shared
import toolsandbox_resource_pilot_01_entry as assistant_entry
from agent_workload_characterization.runners import c_entry


class VolcanoRouteWiringTests(unittest.TestCase):
    def test_office_production_agent_consumes_explicit_route(self):
        route = office_profile.configured_route(office_profile.VOLCANO_PROFILE)
        config = {"task_dir": str(ROOT / "references/repos/DocOps/tasks/atomic__excel_001_budget_bucket_totals_seed"),
                  "max_steps": 40, "max_tokens": 32768,
                  "model_route": {"api_base": route["api_base"],
                                  "request_model": route["request_model"],
                                  "credential_env": route["credential_env"]}}
        with tempfile.TemporaryDirectory(prefix="volcano-office-route-") as tmp:
            agent = office_shared.build_agent(Path(tmp), config)
        self.assertEqual(agent.api_base, route["api_base"])
        self.assertEqual(agent.llm._inner._model_name, route["request_model"])
        self.assertNotEqual(route["api_base"], office_shared.API_BASE)
        self.assertEqual(route["credential_env"], "VOLCANO_API_KEY")

    def test_coding_shared_runner_consumes_explicit_route_and_namespace(self):
        runner, identity = c_entry.build_c_runner(
            authorized=False,
            collection="CODING-MEASUREMENT-VOLCANO-01",
            model_name="openai/deepseek-v4-flash",
            credentials_env=("PILOT_API_BASE", "PILOT_API_KEY"))
        self.assertEqual(runner.collection, "CODING-MEASUREMENT-VOLCANO-01")
        self.assertEqual(runner.harness.mini_config["model"]["model_name"],
                         "openai/deepseek-v4-flash")
        self.assertEqual(identity["credentials_env"]["user_api_base_env"],
                         "PILOT_API_BASE")
        self.assertEqual(identity["credentials_env"]["child_sdk_env"],
                         ["OPENAI_API_BASE", "OPENAI_API_KEY"])

    def test_assistant_agent_user_transport_uses_same_explicit_route(self):
        route = assistant_entry.route_for(assistant_entry.VOLCANO_PROFILE)
        identity = assistant_entry.build_identity(profile=assistant_entry.VOLCANO_PROFILE)
        self.assertEqual(identity["route"], route)
        self.assertEqual(route["provider"], "火山AI网关")
        self.assertEqual(route["request_model_alias"], "openai/deepseek-v4-flash")
        self.assertEqual(route["request_model_raw_client"], "deepseek-v4-flash")
        self.assertEqual(route["api_key_env"], "VOLCANO_API_KEY")
        self.assertNotEqual(route["api_base"], assistant_entry.ROUTE["api_base"])
        import openai
        from agent_workload_characterization.runners.toolsandbox_worker import (
            construct_openai_role_clients)
        agent_client, user_client = construct_openai_role_clients(
            openai, base_url=route["api_base"], api_key="synthetic-no-send")
        try:
            self.assertEqual(str(agent_client.base_url).rstrip("/"),
                             route["api_base"].rstrip("/"))
            self.assertEqual(str(user_client.base_url).rstrip("/"),
                             route["api_base"].rstrip("/"))
            self.assertEqual(agent_client.max_retries, 0)
            self.assertEqual(user_client.max_retries, 0)
        finally:
            agent_client.close()
            user_client.close()

    def test_probe_schema_accepts_finish_action_without_network(self):
        import json
        from document_tools_agent import AgentAction
        parsed = AgentAction.model_validate(json.loads(
            '{"thought":"probe","action":"finish","tool_name":null,'
            '"arguments":{},"final_message":"protocol probe"}'))
        self.assertEqual(parsed.action, "finish")

    def test_office_approval_is_new_collection_scoped_and_exclusive(self):
        plan = {"ready_for_approval": True, "identity_sha256": "a" * 64}
        with tempfile.TemporaryDirectory(prefix="volcano-office-approval-") as tmp:
            root = Path(tmp)
            with patch.object(office_profile, "plan_mode", return_value=plan):
                result = office_profile.record_explicit_approval(
                    root, profile=office_profile.VOLCANO_PROFILE)
            approval = __import__("json").loads(
                (root / result["approval_path"]).read_text())
        self.assertEqual(approval["identity_sha256"], "a" * 64)
        self.assertNotIn("entry_invocation", approval)
        with self.assertRaises(ValueError):
            office_profile.record_explicit_approval(
                profile=office_profile.OFFICIAL_PROFILE)

    def test_assistant_approval_is_new_collection_scoped_and_exclusive(self):
        plan = {"ready_for_approval": True, "identity_sha256": "b" * 64,
                "identity": {"budgets": {"total_wall_s": 480}}}
        with tempfile.TemporaryDirectory(prefix="volcano-assistant-approval-") as tmp:
            root = Path(tmp)
            with patch.object(assistant_entry, "plan_mode", return_value=plan):
                result = assistant_entry.record_explicit_approval(
                    root, profile=assistant_entry.VOLCANO_PROFILE)
            approval = __import__("json").loads(
                (root / result["approval_path"]).read_text())
        self.assertEqual(approval["identity_sha256"], "b" * 64)
        self.assertTrue(approval["accept_unknown_cost_no_hard_cap"])
        self.assertNotIn("entry_invocation", approval)
        with self.assertRaises(ValueError):
            assistant_entry.record_explicit_approval(
                profile=assistant_entry.PILOT_01_PROFILE)


if __name__ == "__main__":
    unittest.main()
