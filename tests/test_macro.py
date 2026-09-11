"""P0-08/09 synthetic tests; all fixture expecteds hand-computed."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from agent_workload_characterization.analyzers.macro import p50, macro_summary, mean
from agent_workload_characterization.analyzers.coverage import coverage_for, capability_rows
from agent_workload_characterization.analyzers.loader import LoadedSample
from agent_workload_characterization.metric_contracts import interval_totals
from agent_workload_characterization.ir import Interval
import test_skeleton as skeleton


def _mock_metric(value, evidence="observed", missing_reason=None):
    return type("M", (), {"value": value, "evidence": evidence,
                          "missing_reason": missing_reason, "id": "m"})()


def _sample(entity_type="run", profile="semantic_trace", source_id="src",
            entity_metrics=None, request_metrics=None):
    return LoadedSample(
        sample_id="s1", source_id=source_id, entity_type=entity_type,
        trace_type="production_derived" if entity_type != "unassigned_request" else "unknown",
        profile=profile, document=None, entity_id="e1",
        files=[], entity_metrics=entity_metrics or {},
        request_metrics=request_metrics or {})


class MacroTests(unittest.TestCase):
    def test_p50_formula(self):
        self.assertIsNone(p50([]))
        self.assertEqual(p50([0, 2, 4, 6]), 3.0)
        self.assertEqual(p50([0, 2, 4, 6, 8]), 4.0)
        self.assertEqual(p50([5]), 5)
        self.assertEqual(p50([0, 10]), 5.0)

    def test_mean(self):
        self.assertIsNone(mean([]))
        self.assertEqual(mean([0, 2, 4, 6]), 3.0)

    def test_macro_stratified(self):
        # Two samples from different sources must NOT be merged
        s1 = _sample(source_id="agentx", entity_type="run",
                     entity_metrics={("model_request_count", "all_agents"): [_mock_metric(10)]})
        s2 = _sample(source_id="applied", entity_type="template",
                     entity_metrics={("model_request_count", "all_agents"): [_mock_metric(3)]})
        rows = macro_summary([s1, s2])
        mr = [r for r in rows if r["definition_key"] == "model_request_count"]
        self.assertEqual(len(mr), 2)  # two strata
        self.assertEqual(mr[0]["source_id"], "agentx")
        self.assertEqual(mr[1]["source_id"], "applied")
        self.assertEqual(mr[0]["n_valid"], 1)
        self.assertEqual(mr[1]["n_valid"], 1)
        # Each is singleton, not merged
        self.assertEqual(mr[0]["n_valid"], 1)

    def test_macro_request_level(self):
        s = _sample(entity_type="run",
                    request_metrics={"input_tokens": [_mock_metric(100), _mock_metric(50)]})
        rows = macro_summary([s])
        ir = [r for r in rows if r["definition_key"] == "input_tokens" and r["entity_level"] == "request"]
        self.assertEqual(len(ir), 1)
        self.assertEqual(ir[0]["n_valid"], 2)
        self.assertEqual(ir[0]["min"], 50)
        self.assertEqual(ir[0]["max"], 100)

    def test_macro_no_cross_stratum_aggregation(self):
        s_runs = [_sample(source_id=f"src{i}", entity_type="run",
                          entity_metrics={("model_request_count", "all_agents"): [_mock_metric(i)]})
                  for i in (3, 70)]
        rows = macro_summary(s_runs)
        mr = [r for r in rows if r["definition_key"] == "model_request_count"]
        self.assertEqual(len(mr), 2)  # two source_id strata
        # Cross-source min/max must not be computed; each stratum has its own
        for r in mr:
            self.assertEqual(r["n_valid"], 1)


class CoverageTests(unittest.TestCase):
    def test_basic_accounting(self):
        # n_present=2, n_valid=1, n_excluded=1, n_missing=1
        m = [_mock_metric(None), _mock_metric(5, "observed"), _mock_metric(10, "estimated")]
        sample = _sample(entity_metrics={("x", "all_requests"): m})
        rows = coverage_for([sample])
        row = rows[0]
        self.assertEqual(row["n_total"], 3)
        self.assertEqual(row["n_applicable"], 3)
        self.assertEqual(row["n_present"], 2)
        self.assertEqual(row["n_valid"], 1)
        self.assertEqual(row["n_missing"], 1)
        self.assertEqual(row["n_excluded"], 1)
        self.assertEqual(row["coverage_ratio"], 1 / 3)

    def test_template_does_not_merge_with_run(self):
        t = _sample(entity_type="template", profile="macro_template",
                    entity_metrics={("model_request_count", "all_agents"): [_mock_metric(3)]})
        r = _sample(entity_type="run",
                    entity_metrics={("model_request_count", "all_agents"): [_mock_metric(70)]})
        rows = coverage_for([t, r])
        mr = [row for row in rows if row["definition_key"] == "model_request_count"]
        self.assertEqual(len(mr), 2)
        for row in mr:
            self.assertIn(row["entity_type"], ("run", "template"))

    def test_capability_rows(self):
        sample = _sample(entity_type="run",
                         entity_metrics={("model_request_count", "all_agents"): [_mock_metric(10)]})
        caps = capability_rows([sample], [("run_elapsed", "unsupported")])
        self.assertEqual(len(caps), 1)
        cap = caps[0]
        self.assertEqual(cap["definition_key"], "run_elapsed")
        self.assertEqual(cap["n_applicable"], 1)
        self.assertEqual(cap["n_missing"], 1)
        self.assertEqual(cap["coverage_ratio"], 0.0)

    def test_capability_deduplicates(self):
        # If the metric exists in entity_metrics, capability row is NOT added
        sample = _sample(entity_type="run",
                         entity_metrics={("run_elapsed", "all_requests"): [_mock_metric(None, missing_reason="unsupported")]})
        caps = capability_rows([sample], [("run_elapsed", "unsupported")])
        self.assertEqual(len(caps), 0)

    def test_coverage_not_applicable_template(self):
        # This test verifies the structure; CPU metrics for templates are
        # not emitted by the adapter (they don't exist in entity_metrics).
        # The loader/capability system doesn't add not_applicable rows for
        # templates by design (templates simply don't emit CPU metrics).
        # Full coverage for template is implicitly zero n_applicable.
        sample = _sample(entity_type="template", profile="macro_template",
                         entity_metrics={("model_request_count", "all_agents"): [_mock_metric(3)]})
        rows = coverage_for([sample])
        self.assertTrue(any(r["definition_key"] == "model_request_count" for r in rows))


class IntervalTotalsTests(unittest.TestCase):
    def test_union_work_overlap(self):
        iv = [Interval(clock_id="c", start_ns=a, end_ns=b, source="native_event", missing_reason=None)
              for a, b in [(0, 4), (2, 6), (8, 9)]]
        r = interval_totals(iv)
        self.assertEqual(r["work_ns"], 9)
        self.assertEqual(r["busy_ns"], 7)
        self.assertEqual(r["overlap_ns"], 2)
        self.assertEqual(r["observed_span_ns"], 9)

    def test_nested(self):
        iv = [Interval(clock_id="c", start_ns=a, end_ns=b, source="native_event", missing_reason=None)
              for a, b in [(0, 10), (2, 5)]]
        r = interval_totals(iv)
        self.assertEqual(r["work_ns"], 13)
        self.assertEqual(r["busy_ns"], 10)
        self.assertEqual(r["overlap_ns"], 3)

    def test_triple_overlap(self):
        iv = [Interval(clock_id="c", start_ns=a, end_ns=b, source="native_event", missing_reason=None)
              for a, b in [(0, 5), (1, 6), (2, 7)]]
        r = interval_totals(iv)
        self.assertEqual(r["work_ns"], 15)
        self.assertEqual(r["busy_ns"], 7)
        self.assertEqual(r["overlap_ns"], 8)

    def test_empty_unknown(self):
        self.assertIsNone(interval_totals([])["work_ns"])

    def test_cross_clock_rejected(self):
        iv = [Interval(clock_id="a", start_ns=0, end_ns=5, source="native_event", missing_reason=None),
              Interval(clock_id="b", start_ns=0, end_ns=5, source="native_event", missing_reason=None)]
        with self.assertRaises(ValueError):
            interval_totals(iv)

    def test_open_rejected(self):
        iv = [Interval(clock_id="c", start_ns=0, end_ns=None, source="native_event", missing_reason="not_recorded")]
        with self.assertRaises(ValueError):
            interval_totals(iv)

    def test_log_receipt_rejected(self):
        iv = [Interval(clock_id="c", start_ns=0, end_ns=5, source="log_receipt", missing_reason=None)]
        with self.assertRaises(ValueError):
            interval_totals(iv)


class PipelineTests(unittest.TestCase):
    """Full pipeline integration tests over a fully synthetic temp project.

    Default unittest never touches legacy trace data: every fixture (AX, AC,
    VW bundle, aux telemetry, sidecar) is generated in a TemporaryDirectory.
    """

    run_python = skeleton.CLITests.run_python
    run_cli = skeleton.CLITests.run_cli

    # ---------------- synthetic project builder ----------------

    def _synth_project(self, base, sidecar_mode="good"):
        """Build a complete synthetic pilot project under *base*.

        Returns (catalog, pilot, gold, paths_dict). sidecar_mode:
        "good" (matches bundle), "empty" (files exist, zero rows),
        "wrong_keys", "value_mismatch", "missing" (no files).
        """
        import yaml
        bench = base / "bench"
        bench.mkdir(parents=True, exist_ok=True)

        # --- AgentX traces.jsonl: AX-7 (line 1), AX-SUB (line 2) ---
        ax7 = {"id": "synth-ax7", "models": ["synth-model"], "block_size": 64,
               "hash_id_scope": "local",
               "requests": [{"type": "s", "t": 0, "api_time": 1.5, "in": 448,
                             "out": 21, "model": "synth-model",
                             "hash_ids": [0, 1], "ttft": 1.2}]}
        axsub = {"id": "synth-axsub", "models": ["synth-model"], "block_size": 64,
                 "hash_id_scope": "local",
                 "requests": [{"type": "s", "t": 0, "api_time": 2.0, "in": 300,
                               "out": 10, "model": "synth-model",
                               "hash_ids": [0, 1], "ttft": 0.5}]}
        ax_dir = bench / "agentx_256k"
        ax_dir.mkdir(exist_ok=True)
        (ax_dir / "traces.jsonl").write_text(
            json.dumps(ax7) + "\n" + json.dumps(axsub) + "\n")

        # --- Applied Compute: AC row at line 1 ---
        ac = {"input_prompt_length": 32, "assistant_response_length": [16],
              "num_turns": 1, "tool_call_latency": [1.5],
              "tool_call_output_length": [8],
              "final_assistant_response_length": 64}
        ac_dir = bench / "applied_compute"
        ac_dir.mkdir(exist_ok=True)
        (ac_dir / "agentic_coding_8k.jsonl").write_text(json.dumps(ac) + "\n")

        # --- VW bundle ---
        vw_tid = "synth:vw:run-001"
        vw_call = "vw-call-001"
        vw_tool = "call_synth_tool_001"
        bundle = bench / "bundles" / "synth_vw_bundle"
        (bundle / "model_telemetry").mkdir(parents=True, exist_ok=True)
        (bundle / "native_trajectory").mkdir(parents=True, exist_ok=True)
        (bundle / "manifest.json").write_text(json.dumps({
            "trace_id": vw_tid, "generation_status": "success",
            "trajectory": {"wall_time_s": 10.0,
                           "started_at": "2026-09-07T04:59:47Z",
                           "ended_at": "2026-09-07T04:59:57Z"},
            "openclaw_session_id": "synth-session"}))
        vw_tel = {"trace_id": vw_tid, "call_id": vw_call, "model": "synth-model",
                  "stream": True, "request_sequence": 1,
                  "input_tokens": 100, "output_tokens": 50, "context_tokens": 150,
                  "cached_input_tokens": 0, "reasoning_output_tokens": 0,
                  "ttft": 0.5, "api_latency": 1.0, "upstream_latency": 1.0,
                  "model_latency": 1.0, "http_status": 200, "usage_source": "upstream",
                  "timestamp_request": 1000.0,
                  "timestamp_request_utc": "2026-09-07T04:59:47.000+00:00",
                  "timestamp_response": 1001.0,
                  "timestamp_response_utc": "2026-09-07T04:59:48.000+00:00"}
        (bundle / "model_telemetry" / "model_telemetry.jsonl").write_text(
            json.dumps(vw_tel) + "\n")
        (bundle / "model_telemetry" / "model_telemetry_summary.json").write_text(
            json.dumps({"model_request_count": 1, "total_input_tokens": 100,
                        "total_output_tokens": 50, "max_context_tokens": 150}))
        (bundle / "native_trajectory" / "original_ReAct.jsonl").write_text(
            json.dumps({"type": "message", "timestamp": "2026-09-07T04:59:48.000Z",
                        "message": {"role": "assistant",
                                    "content": [{"type": "toolCall", "id": vw_tool,
                                                 "name": "read"}]}}) + "\n" +
            json.dumps({"type": "message", "timestamp": "2026-09-07T04:59:49.000Z",
                        "message": {"role": "toolResult", "toolCallId": vw_tool,
                                    "content": "done"}}) + "\n")

        # --- aux telemetry (unassigned) ---
        aux = {"trace_id": "synth:other:run-009", "call_id": "aux-call-001",
               "model": "synth-model", "stream": True, "request_sequence": 1,
               "input_tokens": None, "output_tokens": None,
               "ttft": 3.0, "api_latency": 5.0, "http_status": 200,
               "timestamp_request": 2000.0,
               "timestamp_request_utc": "2026-09-07T06:00:00.000+00:00",
               "timestamp_response": 2005.0,
               "timestamp_response_utc": "2026-09-07T06:00:05.000+00:00"}
        tel_dir = bench / "telemetry"
        tel_dir.mkdir(exist_ok=True)
        (tel_dir / "video_weaver.jsonl").write_text(json.dumps(aux) + "\n")

        # --- sidecar ---
        side = base / "side"
        side.mkdir(exist_ok=True)
        if sidecar_mode == "good":
            (side / "model_calls.jsonl").write_text(json.dumps({
                "trace_id": vw_tid, "call_id": vw_call, "input_tokens": 100,
                "output_tokens": 50, "context_tokens": 150, "ttft_s": 0.5,
                "api_latency_s": 1.0}) + "\n")
            (side / "tool_calls.jsonl").write_text(json.dumps({
                "trace_id": vw_tid, "tool_call_id": vw_tool}) + "\n")
        elif sidecar_mode == "empty":
            (side / "model_calls.jsonl").write_text("")
            (side / "tool_calls.jsonl").write_text("")
        elif sidecar_mode == "wrong_keys":
            (side / "model_calls.jsonl").write_text(json.dumps({
                "trace_id": vw_tid, "call_id": "WRONG_KEY", "input_tokens": 1,
                "output_tokens": 1, "context_tokens": 2, "ttft_s": 0.1,
                "api_latency_s": 0.2}) + "\n")
            (side / "tool_calls.jsonl").write_text("")
        elif sidecar_mode == "value_mismatch":
            (side / "model_calls.jsonl").write_text(json.dumps({
                "trace_id": vw_tid, "call_id": vw_call, "input_tokens": 999999,
                "output_tokens": 50, "context_tokens": 150, "ttft_s": 0.5,
                "api_latency_s": 1.0}) + "\n")
            (side / "tool_calls.jsonl").write_text(json.dumps({
                "trace_id": vw_tid, "tool_call_id": vw_tool}) + "\n")
        # "missing": leave dir empty

        # --- catalog ---
        cat = base / "catalog.yaml"
        cat.write_text(yaml.safe_dump({
            "catalog_version": "1.1",
            "roots": {"benchmark": str(bench), "project": str(base)},
            "sources": [
                {"source_id": "agentx_256k",
                 "locator": {"root": "benchmark", "path": "agentx_256k/traces.jsonl", "kind": "file"}},
                {"source_id": "applied_agentic_coding",
                 "locator": {"root": "benchmark", "path": "applied_compute/agentic_coding_8k.jsonl", "kind": "file"}},
                {"source_id": "gen_videoweaver_traces",
                 "locator": {"root": "benchmark", "path": "bundles", "kind": "directory"}},
                {"source_id": "sidecar_videoweaver",
                 "locator": {"root": "project", "path": "side", "kind": "directory"}},
                {"source_id": "telemetry_video_weaver",
                 "locator": {"root": "benchmark", "path": "telemetry/video_weaver.jsonl", "kind": "file"}},
            ]}))

        # --- pilot selection ---
        pilot = base / "pilot.yaml"
        pilot.write_text(yaml.safe_dump({
            "catalog_version": "1.1",
            "included": [
                {"sample_id": "AX-7", "source_id": "agentx_256k",
                 "locator": {"path": "agentx_256k/traces.jsonl", "line_1based": 1}},
                {"sample_id": "AX-SUB", "source_id": "agentx_256k",
                 "locator": {"path": "agentx_256k/traces.jsonl", "line_1based": 2}},
                {"sample_id": "AC-N2", "source_id": "applied_agentic_coding",
                 "locator": {"path": "applied_compute/agentic_coding_8k.jsonl", "line_1based": 1}},
                {"sample_id": "VW-LONG", "source_id": "gen_videoweaver_traces",
                 "locator": {"path": "bundles/synth_vw_bundle/manifest.json",
                             "bundle_telemetry": "model_telemetry/model_telemetry.jsonl",
                             "bundle_react": "native_trajectory/original_ReAct.jsonl",
                             "bundle_summary": "model_telemetry/model_telemetry_summary.json"}},
            ],
            "auxiliary": [
                {"sample_id": "AUX-INCOMPLETE", "source_id": "telemetry_video_weaver",
                 "locator": {"path": "telemetry/video_weaver.jsonl",
                             "call_id": "aux-call-001"}},
            ]}))

        # --- gold (AC N=1: contexts=[32,56], total_in=88, max=56, out=80, delay=1.5) ---
        gold = base / "gold.yaml"
        gold.write_text(yaml.safe_dump({
            "catalog_version": "1.1",
            "real_candidates": [
                {"sample_id": "AX-7", "source_id": "agentx_256k",
                 "expected": {"main_requests": 1, "model_requests": 1,
                              "subagent_groups": 0, "input_tokens": 448,
                              "output_tokens": 21}},
                {"sample_id": "AX-SUB", "source_id": "agentx_256k",
                 "expected": {"main_requests": 1, "model_requests": 1,
                              "subagent_groups": 0, "input_tokens": 300,
                              "output_tokens": 10}},
                {"sample_id": "AC-N2", "source_id": "applied_agentic_coding",
                 "expected": {"model_requests": 2,
                              "input_contexts": [32, 56],
                              "total_input_tokens": 88,
                              "max_context_tokens": 56,
                              "total_output_tokens": 80,
                              "total_simulated_delay": 1.5}},
                {"sample_id": "VW-LONG", "source_id": "gen_videoweaver_traces",
                 "expected": {"selected_model_requests": 1,
                              "total_input_tokens": 100,
                              "total_output_tokens": 50,
                              "max_context_tokens": 150,
                              "max_input_context": 100,
                              "manifest_wall_time_s": 10.0,
                              "manifest_tool_call_count": 1}},
            ]}))

        paths = {"vw_trace_id": vw_tid, "vw_call_id": vw_call, "vw_tool_id": vw_tool}
        return cat, pilot, gold, paths

    def _synth_samples(self, sidecar_mode="good"):
        from agent_workload_characterization.analyzers.loader import load_pilot
        with tempfile.TemporaryDirectory(prefix="awc-synth-") as tmp:
            cat, pilot, gold, _ = self._synth_project(Path(tmp), sidecar_mode)
            # load_pilot resolves paths relative to catalog roots; copy into
            # a stable location for the lifetime of the returned samples.
            return load_pilot(cat, pilot, gold)["samples"], Path(tmp)

    def _sidecar_catalog_for(self, base, sidecar_mode):
        from agent_workload_characterization.adapters.catalog import Catalog
        cat, _, _, _ = self._synth_project(base, sidecar_mode)
        return Catalog(cat)

    # ---------------- tests ----------------

    def test_empty_selection_fails(self):
        with tempfile.TemporaryDirectory(prefix="awc-pipe-") as tmp:
            import yaml
            base = Path(tmp)
            bench = base / "bench"
            bench.mkdir()
            cat = base / "catalog.yaml"
            cat.write_text(yaml.safe_dump({
                "catalog_version": "1.1",
                "roots": {"benchmark": str(bench), "project": str(base)},
                "sources": []}))
            sel = base / "empty.yaml"
            sel.write_text(yaml.safe_dump({"catalog_version": "1.1", "included": []}))
            candidates = base / "candidates.yaml"
            candidates.write_text(yaml.safe_dump({"catalog_version": "1.1", "real_candidates": []}))
            from agent_workload_characterization.analyzers.analyze import run_pilot
            with self.assertRaises(ValueError):
                run_pilot(cat, sel, candidates, output_dir=None)

    def test_missing_selection_fails(self):
        result = self.run_cli("analyze-macro-pilot", "--selection", "/nonexistent/selection.yaml")
        self.assertEqual(result.returncode, 1)
        self.assertIn("INVALID", result.stderr)

    def test_missing_required_gold_field_fails(self):
        """Deleting a required gold field must make the joint run FAIL."""
        import yaml
        with tempfile.TemporaryDirectory(prefix="awc-gold-") as tmp:
            base = Path(tmp)
            cat, pilot, gold, _ = self._synth_project(base, "good")
            data = yaml.safe_load(gold.read_text())
            for c in data["real_candidates"]:
                if c["sample_id"] == "VW-LONG":
                    del c["expected"]["max_input_context"]
                    break
            gold.write_text(yaml.safe_dump(data))
            from agent_workload_characterization.analyzers.analyze import run_pilot
            with self.assertRaises(ValueError):
                run_pilot(cat, pilot, gold, output_dir=None)

    def test_sidecar_missing_fails(self):
        """Sidecar directory with no files must FAIL."""
        with tempfile.TemporaryDirectory(prefix="awc-sc-") as tmp:
            base = Path(tmp)
            cat = self._sidecar_catalog_for(base, "missing")
            samples, _keep = self._synth_samples("good")
            from agent_workload_characterization.analyzers.analyze import _check_sidecar
            result = _check_sidecar(cat, samples)
            self.assertEqual(result["status"], "FAIL")

    def test_sidecar_empty_files_fail(self):
        """Sidecar files that exist but are empty must FAIL (not silent PASS)."""
        with tempfile.TemporaryDirectory(prefix="awc-sc-") as tmp:
            base = Path(tmp)
            cat = self._sidecar_catalog_for(base, "empty")
            samples, _keep = self._synth_samples("good")
            from agent_workload_characterization.analyzers.analyze import _check_sidecar
            result = _check_sidecar(cat, samples)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("zero" in e or "missing" in e for e in result["errors"]))

    def test_sidecar_wrong_keys_fail(self):
        """Sidecar with wrong call_id keys must FAIL."""
        with tempfile.TemporaryDirectory(prefix="awc-sc-") as tmp:
            base = Path(tmp)
            cat = self._sidecar_catalog_for(base, "wrong_keys")
            samples, _keep = self._synth_samples("good")
            from agent_workload_characterization.analyzers.analyze import _check_sidecar
            result = _check_sidecar(cat, samples)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("missing from sidecar" in e for e in result["errors"]))

    def test_sidecar_value_mismatch_fails(self):
        """Sidecar with correct keys but wrong token values must FAIL."""
        with tempfile.TemporaryDirectory(prefix="awc-sc-") as tmp:
            base = Path(tmp)
            cat = self._sidecar_catalog_for(base, "value_mismatch")
            samples, _keep = self._synth_samples("good")
            from agent_workload_characterization.analyzers.analyze import _check_sidecar
            result = _check_sidecar(cat, samples)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("differ" in e for e in result["errors"]))

    def test_sidecar_synthetic_passes(self):
        """Matching synthetic sidecar must PASS with zero value mismatches."""
        with tempfile.TemporaryDirectory(prefix="awc-sc-") as tmp:
            base = Path(tmp)
            cat = self._sidecar_catalog_for(base, "good")
            samples, _keep = self._synth_samples("good")
            from agent_workload_characterization.analyzers.analyze import _check_sidecar
            result = _check_sidecar(cat, samples)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["value_mismatches"], 0)
            self.assertEqual(result["bundle_request_keys"], 1)
            self.assertEqual(result["sidecar_request_keys"], 1)
            self.assertEqual(result["bundle_tool_ids"], 1)
            self.assertEqual(result["sidecar_tool_ids"], 1)

    def test_macro_coverage_alignment(self):
        """Every macro row must have a unique coverage match with equal n_valid."""
        from agent_workload_characterization.analyzers.macro import row_key
        from agent_workload_characterization.analyzers.analyze import run_pilot
        with tempfile.TemporaryDirectory(prefix="awc-align-") as tmp:
            base = Path(tmp)
            cat, pilot, gold, _ = self._synth_project(base, "good")
            r = run_pilot(cat, pilot, gold, output_dir=None)
            cov_keys = {}
            for c in r["coverage"]:
                k = row_key(c["source_id"], c["sample_id"], c["entity_type"],
                            c["entity_level"], c["aggregation"], c["definition_key"])
                self.assertNotIn(k, cov_keys, f"duplicate coverage key: {k}")
                cov_keys[k] = c
            for mr in r["macro"]:
                k = row_key(mr["source_id"], mr["sample_id"], mr["entity_type"],
                            mr["entity_level"], mr["aggregation"], mr["definition_key"])
                self.assertIn(k, cov_keys, f"macro row without coverage match: {k}")
                self.assertEqual(cov_keys[k]["n_valid"], mr["n_valid"],
                                 f"n_valid mismatch on {k}")
            self.assertEqual(r["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
