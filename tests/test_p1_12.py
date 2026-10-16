"""P1-12 bounded OFFLINE tests: real batch entry + the REAL shared
CodingPilotRunner chain; only the external environment (runtime, harness,
verifier) is faked. No Docker, no model, no network, no real benchmark.
"""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import yaml

from agent_workload_characterization.runners import p1_12_entry as entry
from agent_workload_characterization.runners.coding_pilot import FakeVerifier
from agent_workload_characterization.runners.container_runtime import (
    FakeContainerRuntime)
from agent_workload_characterization.runners.mini_agent_adapter import (
    AgentTask, FakeAgentHarness)
from agent_workload_characterization.collectors.semantic_recorder import FakeClock

OK_PATCH = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"
OK_SCRIPT = {"steps": [
    {"model": {"usage": {"prompt_tokens": 100, "completion_tokens": 20,
                         "total_tokens": 120}},
     "tools": [{"command": "grep -rn something /testbed",
                "category": "Search"}]},
], "final": {"status": "ok", "candidate_patch": OK_PATCH}}


class RecordingHarness(FakeAgentHarness):
    """The existing scripted harness plus a record of every task it ran:
    reuses the shared fake, no parallel implementation."""

    def __init__(self, clock, record, script=None):
        super().__init__(clock, script if script is not None else OK_SCRIPT)
        self.task_record = record

    def run(self, task, budget, recorder, runtime, container,
            watchdog=None, run_dir=None, credentials=None):
        self.task_record.append({
            "instance_id": task.instance_id,
            "problem_statement": task.problem_statement,
            "image": task.image,
            "field_names": sorted(vars(task)),
        })
        return super().run(task, budget, recorder, runtime, container,
                           watchdog=watchdog, run_dir=run_dir,
                           credentials=credentials)


class P112Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data/raw/generated").mkdir(parents=True)
        import hashlib, shutil
        base = Path(__file__).resolve().parents[1]
        rev_dir = base / "data/raw/public/swebench_verified/78f471bf655a3137b2e8a75af1501690ec009ec3"
        cfg = entry.load_config()
        self.catalog = self.root / "p1_12.yaml"
        tasks = []
        for t in cfg["tasks"]:
            digest = ("synthetic/%s@sha256:%s"
                      % (t["instance_id"].replace("_", "-"),
                         hashlib.sha256(t["instance_id"].encode()).hexdigest()))
            tasks.append(dict(t, image_arm64_digest=digest))
        cfg["tasks"] = tasks
        # Synthetic prices make the estimate arithmetic testable.  They do
        # not authorize the production monetary gate; run_batch itself is
        # exercised with fake external boundaries only.
        cfg["budget_batch"]["monetary"] = {
            "status": "closed", "currency": "USD",
            "input_price_per_mtok": 0.27, "output_price_per_mtok": 1.10,
            "max_input_tokens_per_request": 60000, "batch_cap": 500.0}
        self.catalog.write_text(yaml.safe_dump(cfg))
        self.records = {}
        self.reference_texts = {}
        for t in cfg["tasks"]:
            src = rev_dir / t["instance_id"] / "record.json"
            dst_dir = self.root / "records" / t["instance_id"]
            dst_dir.mkdir(parents=True)
            dst = dst_dir / "record.json"
            shutil.copy(src, dst)
            # point the catalog at the local copy, keeping the real SHA
            t["record_locator"] = str(dst)
            self.catalog.write_text(yaml.safe_dump(cfg))
            rec = json.loads(dst.read_text())
            self.reference_texts[t["instance_id"]] = rec["patch"][:200]
        self.namespace = self.root / "reports/resource/P1-12"
        self.patches = mock.patch.multiple(
            entry, PROJECT_ROOT=self.root, CATALOG=self.catalog,
            APPROVAL=self.namespace / "APPROVAL.json",
            ATTEMPT=self.namespace / "ATTEMPT_STARTED.json")
        self.patches.start()
        self.clock = FakeClock()
        self.harness_log = []
        self.verifier_scripts = {}  # instance_id -> script dict

    def tearDown(self):
        self.patches.stop()
        self.tmp.cleanup()

    def factories(self, *, verifier_default=None):
        def runtime_factory():
            from agent_workload_characterization.collectors.resource_sampler \
                import CounterSnapshot
            rt = FakeContainerRuntime(self.clock)
            return rt
        def harness_factory(image):
            return RecordingHarness(self.clock, record=self.harness_log)
        def verifier_factory():
            return FakeVerifier(self.clock, verifier_default or {"status": "ok", "resolved": True})
        return runtime_factory, harness_factory, verifier_factory

    def run_batch(self, **kw):
        r, h, v = self.factories(**{k: v for k, v in kw.items() if k in ("verifier_default",)})
        kw.pop("verifier_default", None)
        name = kw.pop("name", "batch")
        kw.setdefault("config", entry.load_config())
        return entry.run_batch(r, h, v, self.namespace / name, **kw)

    # ---- plan / gates ---------------------------------------------------
    def test_plan_mode_no_side_effects(self):
        before = {p for p in self.root.rglob("*")}
        with mock.patch.object(entry, "production_factories",
                               side_effect=AssertionError), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(entry.main([]), 0)
        self.assertEqual({p for p in self.root.rglob("*")}, before)

    def test_single_flag_and_no_approval(self):
        self.assertEqual(entry.main(["--execute"]), 2)
        with context_output():
            self.assertEqual(
                entry.main(["--execute", "--i-approve-the-p1-12-b"]), 3)
        self.assertFalse(entry.ATTEMPT.exists())

    def test_identity_drift_and_repeat_attempt_refused(self):
        self.namespace.mkdir(parents=True, exist_ok=True)
        entry.APPROVAL.write_text(json.dumps(dict(
            approved=True, approved_by="t", approved_at_utc="x",
            checklist_identity=entry.build_plan()["identity"])))
        entry.register_attempt(entry.build_plan()["identity"])
        with context_output():
            self.assertEqual(
                entry.main(["--execute", "--i-approve-the-p1-12-b"]), 3)
        # drift
        entry.ATTEMPT.unlink()
        ident = entry.build_plan()["identity"]
        ident["collection"] = "RUN-02"
        entry.APPROVAL.write_text(json.dumps(dict(
            approved=True, approved_by="t", approved_at_utc="x",
            checklist_identity=ident)))
        with context_output():
            self.assertEqual(
                entry.main(["--execute", "--i-approve-the-p1-12-b"]), 3)
        self.assertFalse(entry.ATTEMPT.exists())

    def test_output_guards(self):
        self.namespace.mkdir(parents=True)
        redirect = self.namespace / "redirect"
        redirect.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(entry.P112Error):
            entry.guarded(redirect / "batch", new=True)
        with self.assertRaises(entry.P112Error):
            entry.guarded(self.root / "data/raw/x", new=True)

    def test_block_order_deterministic_and_balanced(self):
        cfg = entry.load_config()
        t1 = entry.block_order(cfg)
        t2 = entry.block_order(cfg)
        self.assertEqual(t1, t2)
        ids = [i for _, i in t1]
        self.assertEqual(len(ids), 9)
        for inst in {i for i in ids}:
            self.assertEqual(ids.count(inst), 3)
        # each round contains every task exactly once
        for r in range(3):
            round_ids = [i for rr, i in t1 if rr == r]
            self.assertEqual(sorted(round_ids),
                             sorted(t["instance_id"] for t in cfg["tasks"]))

    # ---- routing / isolation --------------------------------------------
    def test_three_tasks_routed_with_correct_records_and_images(self):
        result = self.run_batch()
        self.assertEqual(result["status"], "complete", result["errors"])
        self.assertEqual(len(self.harness_log), 9)
        import hashlib as _h
        seen = {}
        for call in self.harness_log:
            seen.setdefault(call["instance_id"], []).append(call["image"])
        for inst, images in seen.items():
            expected = ("synthetic/%s@sha256:%s"
                        % (inst.replace("_", "-"),
                           _h.sha256(inst.encode()).hexdigest()))
            self.assertEqual(len(images), 3)  # 3 repeats per task
            self.assertTrue(all(im == expected for im in images))
        # attempted run directories are all distinct
        run_dirs = [a.get("run_dir") for a in result["attempts"]]
        self.assertEqual(len(set(run_dirs)), 9)

    def test_agent_input_is_whitelist_only(self):
        result = self.run_batch()
        self.assertEqual(result["status"], "complete")
        for call in self.harness_log:
            # AgentTask dataclass fields: whitelist projection only
            self.assertEqual(call["field_names"],
                             ["cwd", "image", "instance_id",
                              "problem_statement", "source_type"])
            # reference answers must NOT leak into agent inputs
            for inst, ref in self.reference_texts.items():
                self.assertNotIn(ref, call["problem_statement"])
            self.assertNotIn("FAIL_TO_PASS", call["problem_statement"])

    # ---- failure semantics ----------------------------------------------
    def test_resolved_false_is_valid_and_batch_continues(self):
        result = self.run_batch(verifier_default={"status": "ok",
                                                  "resolved": False})
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len([a for a in result["attempts"]
                              if a["status"] == "executed"]), 9)
        for inst, stats in result["per_task"].items():
            self.assertEqual(stats["resolved_false"], 3)
            self.assertEqual(stats["resolved_true"], 0)

    def test_infra_failure_stops_remaining_attempts(self):
        result = self.run_batch(verifier_default={"status": "infra_failure",
                                                  "resolved": None})
        self.assertEqual(result["status"], "stopped")
        executed = [a for a in result["attempts"] if a["status"] == "executed"]
        failed = [a for a in result["attempts"] if a["status"] == "failed"]
        not_exec = [a for a in result["attempts"] if a["status"] == "not_executed"]
        self.assertEqual(len(executed), 0)
        self.assertEqual(len(failed), 1)
        self.assertEqual(len(not_exec), 8)
        self.assertEqual(not_exec[0]["reason"],
                         "batch_stopped_after_infrastructure_failure")
        self.assertEqual(len(self.harness_log), 1)  # no further agent runs
        manifest = json.loads((self.namespace / "batch/manifest.json").read_text())
        self.assertEqual(manifest["status"], "stopped")

    def test_cleanup_failure_stops_batch(self):
        # verifier resolves fine but the runner reports cleanup errors via a
        # verifier status that maps to a stop condition
        result = self.run_batch(verifier_default={"status": "ok",
                                                  "resolved": True})
        self.assertEqual(result["status"], "complete")
        # now inject archive failure through write_json
        original = entry.write_json
        def write(path, payload):
            if Path(path).name == "manifest.json":
                raise OSError("fake archive failure")
            return original(path, payload)
        with mock.patch.object(entry, "write_json", side_effect=write):
            result = self.run_batch(name="archfail")
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["archive_status"], "failed")
        self.assertTrue((self.namespace / "archfail/archive_failure.json").exists())

    def test_shared_deadline_stops_batch_with_not_executed(self):
        cfg = entry.load_config()
        result = self.run_batch(config=cfg,
                                deadline=__import__("time").monotonic() + 0.05)
        self.assertIn(result["status"], ("stopped",))
        not_exec = [a for a in result["attempts"]
                    if a["status"] == "not_executed"]
        self.assertGreaterEqual(len(not_exec), 1)

    # ---- summary / statistics -------------------------------------------
    def test_summary_groups_by_task_with_median_iqr(self):
        result = self.run_batch()
        self.assertEqual(result["status"], "complete")
        for inst, stats in result["per_task"].items():
            self.assertEqual(stats["planned"], 3)
            self.assertEqual(stats["executed"], 3)
            self.assertEqual(stats["resolved_true"], 3)
            self.assertEqual(len(stats["raw_points"]), 3)
            self.assertIsNotNone(stats["wall_s_stats"]["median"])
        self.assertIn("linear interpolation", result["statistics_note"])
        manifest = json.loads((self.namespace / "batch/manifest.json").read_text())
        for name, value in manifest["outputs"].items():
            self.assertEqual(entry.sha(self.namespace / "batch" / name),
                             value["sha256"])
        self.assertEqual(len(manifest["inputs"]["records"]), 3)
        for inst, meta in manifest["inputs"]["records"].items():
            record_path = None
            for t in entry.load_config()["tasks"]:
                if t["instance_id"] == inst:
                    record_path = Path(t["record_locator"])
            self.assertEqual(entry.sha(record_path), meta["sha256"])

    def test_median_iqr_function(self):
        self.assertEqual(entry.median_iqr([])["median"], None)
        single = entry.median_iqr([5.0])
        self.assertEqual(single["median"], 5.0)
        self.assertEqual(single["iqr"], 0.0)
        stats = entry.median_iqr([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(stats["median"], 2.5)
        self.assertAlmostEqual(stats["iqr"], 1.5)

    # ---- preflight honesty ----------------------------------------------
    def test_preflight_not_ready_without_full_digests(self):
        # the REAL catalog after the 2026-09-24 closure round: all three
        # digests are full registry-verified values, so the ONLY remaining
        # readiness gap is the open monetary budget
        real_root = Path(__file__).resolve().parents[1]
        real_cfg = yaml.safe_load(
            (real_root / "workload_catalog/p1_12.yaml").read_text())
        with mock.patch.object(entry, "PROJECT_ROOT", real_root):
            pre = entry.preflight_checks(real_cfg)
        # the real catalog now registers the user's cost-risk acceptance:
        # the monetary blocker is cleared BY THAT REGISTRATION (not by a
        # closed pricing structure, which remains open/estimate-only)
        self.assertTrue(pre["checks"]["image_digests_full"])
        self.assertTrue(pre["checks"]["monetary_gate_satisfied"])
        self.assertEqual(pre["readiness"]["missing"], [])
        self.assertTrue(pre["readiness"]["cost_risk_acceptance"]["registered"])
        self.assertFalse(pre["readiness"]["monetary_bound"]["closed"])
        # digest gate itself still rejects a null entry
        cfg_mut = yaml.safe_load(
            (real_root / "workload_catalog/p1_12.yaml").read_text())
        cfg_mut["tasks"][1]["image_arm64_digest"] = None
        pre2 = entry.preflight_checks(cfg_mut)
        self.assertFalse(pre2["checks"]["image_digests_full"])
        self.assertIn("image_digest:astropy__astropy-13236",
                      pre2["readiness"]["missing"])

    # ---- review group 1: gates must actually block ----------------------
    def test_placeholder_digest_and_unknown_price_never_ready(self):
        cfg = entry.load_config()
        cfg["tasks"][0]["image_arm64_digest"] = "not-a-digest"
        pre = entry.preflight_checks(cfg)
        self.assertEqual(pre["status"], "NOT_READY")
        self.assertFalse(pre["checks"]["image_digests_full"])
        cfg2 = entry.load_config()
        cfg2["budget_batch"]["monetary"] = "unknown-price"
        cfg2["budget_batch"].pop("user_cost_risk_acceptance", None)
        pre2 = entry.preflight_checks(cfg2)
        self.assertEqual(pre2["status"], "NOT_READY")
        self.assertFalse(pre2["checks"]["monetary_gate_satisfied"])
        # truncated digest (19 hex) is also refused
        cfg3 = entry.load_config()
        cfg3["tasks"][0]["image_arm64_digest"] = "repo@sha256:" + "a" * 19
        self.assertFalse(entry.digest_is_full(cfg3["tasks"][0]["image_arm64_digest"]))

    def _not_ready_catalog(self):
        """Real catalog semantics (null astropy digests, unknown monetary)
        with record locators redirected to the tmp copies, so the whole
        main() path runs under the tmp project root."""
        real_root = Path(__file__).resolve().parents[1]
        cfg = yaml.safe_load(
            (real_root / "workload_catalog/p1_12.yaml").read_text())
        by_id = {t["instance_id"]: t for t in yaml.safe_load(
            self.catalog.read_text())["tasks"]}
        for t in cfg["tasks"]:
            t["record_locator"] = by_id[t["instance_id"]]["record_locator"]
        # remove the user's registered cost-risk acceptance: without that
        # registration the monetary gate must refuse (counter-example for
        # 'unregistered decision cannot be let through')
        cfg["budget_batch"].pop("user_cost_risk_acceptance", None)
        path = self.root / "p1_12_notready.yaml"
        path.write_text(yaml.safe_dump(cfg))
        return path

    def test_main_refuses_when_readiness_not_ready(self):
        # real readiness gaps (null digests, unknown price): full fake wiring
        # must never be reached; rc=4 from the readiness gate
        catalog = self._not_ready_catalog()
        self.namespace.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(entry, "CATALOG", catalog):
            identity = entry.build_plan()["identity"]
        entry.APPROVAL.write_text(json.dumps(dict(
            approved=True, approved_by="t", approved_at_utc="x",
            checklist_identity=identity)))
        calls = {"factories": 0, "credentials": 0, "docker_pre": 0}
        def no_factories():
            calls["factories"] += 1
            raise AssertionError("must not be reached")
        def no_creds():
            calls["credentials"] += 1
            raise AssertionError("must not be reached")
        def no_docker_pre(cfg, **kw):
            calls["docker_pre"] += 1
            raise AssertionError("must not be reached")
        with mock.patch.object(entry, "CATALOG", catalog), \
             mock.patch.object(entry, "production_factories", no_factories), \
             mock.patch.object(entry, "resolve_credentials", no_creds), \
             mock.patch.object(entry, "docker_image_preflight", no_docker_pre), \
             context_output():
            rc = entry.main(["--execute", "--i-approve-the-p1-12-b"])
        self.assertEqual(rc, 4)
        self.assertEqual(calls, {"factories": 0, "credentials": 0, "docker_pre": 0})
        marker = json.loads(entry.ATTEMPT.read_text())
        self.assertEqual(marker["status"], "failed")
        self.assertIn("preflight_not_ready", marker["detail"])

    # ---- review group 2: batch deadline propagates into attempts ---------
    def test_shared_deadline_propagates_into_attempt_limits(self):
        cfg = entry.load_config()
        # 40min deadline with the registered 30min reserve leaves ~10min of
        # work budget: every attempt budget must be capped by that remainder
        result = self.run_batch(config=cfg,
                                deadline=__import__("time").monotonic() + 40 * 60)
        caps = [a["attempt_budget_total_wall_s"] for a in result["attempts"]
                if "attempt_budget_total_wall_s" in a]
        self.assertTrue(caps)
        for cap in caps:
            self.assertLessEqual(cap, 10 * 60 + 1)  # never the full 30min registry
        # with a tiny deadline (below the reserve) the batch stops and marks
        # the rest not executed
        result = self.run_batch(config=cfg, name="tiny",
                                deadline=__import__("time").monotonic() + 0.05)
        self.assertEqual(result["status"], "stopped")
        not_exec = [a for a in result["attempts"] if a["status"] == "not_executed"]
        self.assertGreaterEqual(len(not_exec), 1)

    # ---- review group 4: verdict / on-disk report consistency ------------
    def test_last_attempt_infra_failure_is_not_complete(self):
        # infra failure strikes ONLY the final attempt: the batch must be
        # stopped even though no not_executed entries follow it; the failed
        # attempt carries status='failed' (ONE vocabulary, CLI and per-task
        # grouping read the same field)
        counters = {"n": 0}
        r, h, v = self.factories()
        class LastFailVerifier:
            def __init__(self, clock, inner):
                self.inner = inner
            def run(self, *a, **kw):
                counters["n"] += 1
                if counters["n"] >= 9:
                    from agent_workload_characterization.runners.coding_pilot \
                        import VerifierResult
                    return VerifierResult(status="infra_failure")
                return self.inner.run(*a, **kw)
        cfg = entry.load_config()
        result = entry.run_batch(r, h, lambda: LastFailVerifier(self.clock, v()),
                                 self.namespace / "lastfail", config=cfg)
        self.assertEqual(result["status"], "stopped")
        executed = [a for a in result["attempts"] if a.get("status") == "executed"]
        failed = [a for a in result["attempts"] if a.get("status") == "failed"]
        not_exec = [a for a in result["attempts"] if a.get("status") == "not_executed"]
        self.assertEqual(len(executed), 8)
        self.assertEqual(len(failed), 1)   # the LAST attempt, status='failed'
        self.assertEqual(len(not_exec), 0)
        total_failed = sum(s["failed"] for s in result["per_task"].values())
        self.assertEqual(total_failed, 1)
        # CLI-style counters (same field) agree with the per-task grouping
        cli_failed = sum(1 for a in result["attempts"] if a.get("status") == "failed")
        self.assertEqual(cli_failed, total_failed)

    def test_on_disk_summary_matches_final_verdict(self):
        result = self.run_batch()
        self.assertEqual(result["status"], "complete")
        on_disk = json.loads((self.namespace / "batch/summary.json").read_text())
        self.assertEqual(on_disk["status"], "complete")
        self.assertEqual(on_disk["archive_status"], "complete")
        # archive failure: the on-disk summary must carry the corrected
        # verdict too, not only the return value
        original = entry.write_json
        def write(path, payload):
            if Path(path).name == "manifest.json":
                raise OSError("fake archive failure")
            return original(path, payload)
        with mock.patch.object(entry, "write_json", side_effect=write):
            result = self.run_batch(name="archfail2")
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["archive_status"], "failed")
        on_disk = json.loads((self.namespace / "archfail2/summary.json").read_text())
        self.assertEqual(on_disk["status"], "stopped")
        self.assertEqual(on_disk["archive_status"], "failed")
        self.assertTrue((self.namespace / "archfail2/archive_failure.json").exists())

    # ---- review group 3: production assembly through main() --------------
    def test_main_production_assembly_offline(self):
        # With the user cost-risk acceptance REGISTERED (as it now is in the
        # real and synthetic catalogs), main() crosses the offline preflight
        # and assembles the production chain; verifies the pinned local
        # Docker endpoint, credential pass-through and the docker preflight
        # call, with fakes injected at the external boundaries only.
        self.namespace.mkdir(parents=True, exist_ok=True)
        entry.APPROVAL.write_text(json.dumps(dict(
            approved=True, approved_by="t", approved_at_utc="x",
            checklist_identity=entry.build_plan()["identity"])))
        seen = {"docker_env": None, "docker_context": None,
                "docker_pre": 0, "creds": None}
        def fake_docker_pre(cfg, *, runner=None, deadline=None):
            seen["docker_pre"] += 1
            seen["docker_env"] = os.environ.get("DOCKER_HOST")
            seen["docker_context"] = os.environ.get("DOCKER_CONTEXT")
            return {"status": "READY", "images": {}}
        r, h, v = self.factories()
        def fake_creds():
            return {"OPENAI_API_BASE": "https://fake", "OPENAI_API_KEY": "fake-key"}
        def run_batch_stub(rt_factory, h_factory, v_factory, out_dir, **kw):
            seen["creds"] = kw.get("credentials")
            return {"status": "complete", "archive_status": "complete",
                    "attempts": [{"status": "executed"}] * 9}
        with mock.patch.object(entry, "docker_image_preflight", fake_docker_pre), \
             mock.patch.object(entry, "production_factories", lambda: (r, h, v)), \
             mock.patch.object(entry, "resolve_credentials", fake_creds), \
             mock.patch.object(entry, "run_batch", run_batch_stub), \
             mock.patch.dict(os.environ, {"DOCKER_HOST": "tcp://remote:9",
                                          "DOCKER_CONTEXT": "evil"}), \
             context_output():
            rc = entry.main(["--execute", "--i-approve-the-p1-12-b"])
            # inside the outer patch scope: local_docker_environment already
            # restored the pinned outer values
            self.assertEqual(os.environ.get("DOCKER_HOST"), "tcp://remote:9")
            self.assertEqual(os.environ.get("DOCKER_CONTEXT"), "evil")
        self.assertEqual(rc, 0, entry.ATTEMPT.read_text())
        self.assertEqual(seen["docker_env"], "unix:///var/run/docker.sock")
        self.assertIsNone(seen["docker_context"])
        self.assertEqual(seen["docker_pre"], 1)
        self.assertEqual(seen["creds"], {"OPENAI_API_BASE": "https://fake",
                                         "OPENAI_API_KEY": "fake-key"})
        marker = json.loads(entry.ATTEMPT.read_text())
        self.assertEqual(marker["status"], "completed")


    # ---- review round 2: production-path gaps ---------------------------
    def test_resolve_credentials_real_chain_with_synthetic_config(self):
        from agent_workload_characterization.runners import smoke_launcher
        path = self.root / "synthetic_opencode.json"
        cfg = {"provider": {"deepseek-official": {
            "models": {"deepseek-flash": {"name": "DeepSeek Flash"}},
            "options": {"baseURL": "https://api.deepseek.com/v1",
                        "apiKey": "synthetic-key"}}}}
        path.write_text(json.dumps(cfg))
        with mock.patch.object(smoke_launcher, "DEFAULT_CONFIG", path):
            self.assertEqual(entry.resolve_credentials(), {
                "OPENAI_API_BASE": "https://api.deepseek.com/v1",
                "OPENAI_API_KEY": "synthetic-key"})
            options = cfg["provider"]["deepseek-official"]["options"]
            for field, invalid in (("apiKey", ""), ("baseURL", "https://other.invalid/v1")):
                original = options[field]
                options[field] = invalid
                path.write_text(json.dumps(cfg))
                with self.assertRaises(entry.P112Error):
                    entry.resolve_credentials()
                options[field] = original
            cfg["provider"]["old-gateway"] = cfg["provider"].pop("deepseek-official")
            path.write_text(json.dumps(cfg))
            with self.assertRaises(entry.P112Error):
                entry.resolve_credentials()

    def test_official_model_identity_and_production_factory(self):
        from agent_workload_characterization.runners.mini_agent_adapter import MiniSweAgentHarness
        with mock.patch.object(MiniSweAgentHarness, "load_bundled_config",
                               return_value={"agent": {}, "model": {}, "environment": {}}):
            with mock.patch.object(MiniSweAgentHarness, "__init__", return_value=None) as init:
                _, harness, _ = entry.production_factories()
                harness("synthetic-image")
        self.assertEqual(init.call_args.kwargs["mini_config"]["model"]["model_name"],
                         "openai/deepseek-flash")
        route = entry.build_plan()["identity"]["agent"]
        self.assertEqual(route["provider"], "deepseek-official")
        self.assertEqual(route["api_base"], "https://api.deepseek.com/v1")
        self.assertNotIn("apiKey", route)

    def test_docker_preflight_refuses_after_deadline(self):
        cfg = entry.load_config()
        calls = []
        def runner(argv, **kw):
            calls.append((argv, kw.get("timeout")))
            import subprocess as _sp
            ref = argv[3]
            return _sp.CompletedProcess(argv, 0,
                f"linux/arm64 {ref}", "")
        pre = entry.docker_image_preflight(
            cfg, runner=runner, deadline=__import__("time").monotonic() - 1)
        self.assertEqual(pre["status"], "NOT_READY")
        self.assertEqual(len(calls), 0)  # expired budget: NO docker call at all
        self.assertTrue(all(i["detail"] == "budget_exhausted"
                            for i in pre["images"].values()))
        # positive remaining budget: float timeout, capped at 15s
        pre2 = entry.docker_image_preflight(
            cfg, runner=runner, deadline=__import__("time").monotonic() + 3.5)
        self.assertEqual(len(calls), 3)
        for _, timeout in calls:
            self.assertLessEqual(timeout, 3.5)
            self.assertIsInstance(timeout, float)

    def test_monetary_bound_is_computable_not_a_label(self):
        cfg = entry.load_config()
        base = {"status": "closed", "currency": "USD",
                "input_price_per_mtok": 0.27, "output_price_per_mtok": 1.10,
                "max_input_tokens_per_request": 60000}
        # A cap that fits the arithmetic still cannot close the production
        # gate because input/spend enforcement is not present.
        good = dict(base, batch_cap=500.0)
        cfg["budget_batch"]["monetary"] = good
        b = entry.monetary_bound(cfg)
        self.assertFalse(b["closed"])
        self.assertFalse(b["enforced"])
        self.assertEqual(b["bound_kind"], "planning_estimate")
        self.assertEqual(b["request_count"], 270)
        # 9*30*60000*0.27 + 9*30*4096*1.10 (per 1e6) = 4.374 + 1.2165 = 5.5905
        self.assertAlmostEqual(b["computed_bound"], 5.5905, places=3)
        # cap below the computed bound -> NOT closed
        cfg["budget_batch"]["monetary"] = dict(base, batch_cap=1.0)
        b2 = entry.monetary_bound(cfg)
        self.assertFalse(b2["closed"])
        self.assertEqual(b2["reason"],
                         "no_execution_time_input_token_or_spend_enforcement")
        # missing price -> NOT closed (a bare positive number is not closure)
        cfg["budget_batch"]["monetary"] = {"status": "closed", "currency": "USD",
                                           "batch_cap": 500.0}
        b3 = entry.monetary_bound(cfg)
        self.assertFalse(b3["closed"])
        self.assertTrue(b3["reason"].startswith("missing_or_invalid"))
        # real catalog stays open
        real = yaml.safe_load((Path(__file__).resolve().parents[1]
                               / "workload_catalog/p1_12.yaml").read_text())
        self.assertFalse(entry.monetary_closed(real))

    def test_monetary_numeric_rejects_bool_and_nonfinite_values(self):
        cfg = entry.load_config()
        base = {"status": "closed", "currency": "USD",
                "input_price_per_mtok": 0.27, "output_price_per_mtok": 1.10,
                "max_input_tokens_per_request": 60000, "batch_cap": 500.0}
        for key, value in (("input_price_per_mtok", True),
                           ("output_price_per_mtok", float("nan")),
                           ("max_input_tokens_per_request", float("inf")),
                           ("batch_cap", False)):
            cfg["budget_batch"]["monetary"] = dict(base, **{key: value})
            result = entry.monetary_bound(cfg)
            self.assertFalse(result["closed"], key)
            self.assertTrue(result["reason"].startswith("missing_or_invalid"), key)

    def test_main_full_synthetic_catalog_still_rejects_estimate_only_money(self):
        # even with full synthetic prices, an estimate-only registration
        # (no user cost-risk acceptance) must refuse execution
        cfg = entry.load_config()
        cfg["budget_batch"].pop("user_cost_risk_acceptance", None)
        self.catalog.write_text(yaml.safe_dump(cfg))
        self.namespace.mkdir(parents=True, exist_ok=True)
        entry.APPROVAL.write_text(json.dumps(dict(
            approved=True, approved_by="t", approved_at_utc="x",
            checklist_identity=entry.build_plan()["identity"])))
        calls = {"factories": 0, "credentials": 0, "docker": 0, "runner": 0}
        def no_factories():
            calls["factories"] += 1
            raise AssertionError("production factories must not be reached")
        def no_creds():
            calls["credentials"] += 1
            raise AssertionError("credentials must not be reached")
        def no_docker(*args, **kwargs):
            calls["docker"] += 1
            raise AssertionError("docker preflight must not be reached")
        def no_runner(*args, **kwargs):
            calls["runner"] += 1
            raise AssertionError("runner must not be reached")
        with mock.patch.object(entry, "production_factories", no_factories), \
             mock.patch.object(entry, "resolve_credentials", no_creds), \
             mock.patch.object(entry, "docker_image_preflight", no_docker), \
             mock.patch.object(entry, "run_batch", no_runner), \
             context_output():
            rc = entry.main(["--execute", "--i-approve-the-p1-12-b"])
        self.assertEqual(rc, 4)
        self.assertEqual(calls, {"factories": 0, "credentials": 0,
                                 "docker": 0, "runner": 0})
        self.assertEqual(json.loads(entry.ATTEMPT.read_text())["status"], "failed")

    def test_post_archive_downgrade_refreshes_manifest_hashes(self):
        # the downgrade path must REBUILD the outputs table after rewriting
        # the summary: the manifest's recorded hashes must match the FINAL
        # on-disk files, not the pre-rewrite ones
        import time as _time
        result = self.run_batch()
        self.assertEqual(result["status"], "complete")
        out_dir = self.namespace / "batch"
        # simulate the post-archive overrun: downgrade via the real function
        result["budget_overrun"] = True
        result["status"] = "stopped"
        entry.downgrade_and_rearchive(result, out_dir,
                                      identity=entry.build_plan()["identity"],
                                      config=entry.load_config())
        manifest = json.loads((out_dir / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "stopped")
        summary_on_disk = json.loads((out_dir / "summary.json").read_text())
        self.assertEqual(summary_on_disk["status"], "stopped")
        # manifest hashes describe the FINAL on-disk content
        recorded = manifest["outputs"]["summary.json"]
        self.assertEqual(recorded["sha256"], entry.sha(out_dir / "summary.json"))
        self.assertEqual(recorded["bytes"],
                         (out_dir / "summary.json").stat().st_size)

    def test_archive_verification_failure_invalidates_written_manifest(self):
        """A manifest that was written before a later verification error
        must not remain a successful-looking archive."""
        real_sha = entry.sha
        calls = {"summary": 0}
        def flaky_sha(path):
            if Path(path).name == "summary.json":
                calls["summary"] += 1
                if calls["summary"] > 1:
                    raise OSError("verification read failed")
            return real_sha(path)
        with mock.patch.object(entry, "sha", side_effect=flaky_sha):
            result = self.run_batch(name="verifyfail")
        out = self.namespace / "verifyfail"
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["archive_status"], "failed")
        summary = json.loads((out / "summary.json").read_text())
        self.assertEqual(summary["status"], result["status"])
        self.assertEqual(summary["archive_status"], result["archive_status"])
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(manifest["archive_status"], "failed")
        self.assertEqual(manifest["archive_integrity"], "invalid")
        self.assertTrue((out / "archive_failure.json").is_file())

    def test_stopped_batch_archive_overrun_refreshes_final_disk_state(self):
        cfg = entry.load_config()
        clock = {"n": 0}
        real_monotonic = entry.time.monotonic
        def advancing():
            clock["n"] += 1
            return 2000 if clock["n"] > 2 else 0
        with mock.patch.object(entry.time, "monotonic", side_effect=advancing):
            result = self.run_batch(name="stopped-overrun",
                                    deadline=1800,
                                    verifier_default={"status": "infra_failure",
                                                      "resolved": None})
        out = self.namespace / "stopped-overrun"
        summary = json.loads((out / "summary.json").read_text())
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertTrue(result["budget_overrun"])
        self.assertEqual(summary["budget_overrun"], result["budget_overrun"])
        self.assertEqual(summary["status"], result["status"])
        self.assertEqual(manifest["status"], result["status"])
        self.assertEqual(manifest["archive_status"], result["archive_status"])
        meta = manifest["outputs"]["summary.json"]
        self.assertEqual(meta["bytes"], (out / "summary.json").stat().st_size)
        self.assertEqual(meta["sha256"], entry.sha(out / "summary.json"))


def context_output():
    return mock.patch("sys.stdout", new_callable=io.StringIO)


if __name__ == "__main__":
    unittest.main()


class CostRiskAcceptanceGateTests(unittest.TestCase):
    """The user's registered decision clears THIS pilot's monetary blocker;
    without the registration nothing passes, and the estimate semantics
    never change."""

    def setUp(self):
        import tempfile, shutil
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        real = Path(__file__).resolve().parents[1] / "workload_catalog/p1_12.yaml"
        cfg = yaml.safe_load(real.read_text())
        # records must exist under the tmp root for load_config-style checks;
        # readiness/cost checks themselves only need the monetary section
        self.cfg = cfg

    def test_registered_acceptance_clears_blocker(self):
        r = entry.readiness(self.cfg)
        self.assertTrue(r["ready"])
        self.assertEqual(r["missing"], [])
        self.assertTrue(r["cost_risk_acceptance"]["registered"])
        # the pricing structure itself REMAINS open/estimate-only
        self.assertFalse(r["monetary_bound"]["closed"])
        self.assertIn("planning_estimate", r["monetary_bound"]["bound_kind"])

    def test_unregistered_acceptance_refuses(self):
        cfg = yaml.safe_load(yaml.safe_dump(self.cfg))
        del cfg["budget_batch"]["user_cost_risk_acceptance"]
        r = entry.readiness(cfg)
        self.assertFalse(r["ready"])
        self.assertIn("monetary_budget_not_closed", r["missing"])
        self.assertFalse(r["cost_risk_acceptance"]["registered"])
        # partial / tampered registrations also refuse
        for mutate in (
            lambda a: a.update(decision="some_other_decision"),
            lambda a: a.update(scope="all_tasks"),
            lambda a: a.pop("acknowledged_gaps"),
            lambda a: a.update(acknowledged_gaps=["only_one_gap"]),
            lambda a: a.pop("registered_at"),
        ):
            cfg2 = yaml.safe_load(yaml.safe_dump(self.cfg))
            mutate(cfg2["budget_batch"]["user_cost_risk_acceptance"])
            r2 = entry.readiness(cfg2)
            self.assertFalse(r2["ready"], mutate)
            self.assertIn("monetary_budget_not_closed", r2["missing"])

    def test_bound_stays_estimate_even_with_prices(self):
        # even a fully-priced registration cannot claim closure/enforcement:
        # the chain has no execution-time spend enforcement (unchanged
        # semantics from the estimate-only fix)
        cfg = yaml.safe_load(yaml.safe_dump(self.cfg))
        cfg["budget_batch"]["monetary"].update(
            status="closed", currency="USD",
            input_price_per_mtok=0.27, output_price_per_mtok=1.10,
            max_input_tokens_per_request=60000, batch_cap=500.0)
        b = entry.monetary_bound(cfg)
        self.assertFalse(b["closed"])
        self.assertFalse(b["enforced"])
        self.assertIn(b["bound_kind"], ("planning_estimate",))
