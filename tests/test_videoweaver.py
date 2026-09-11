"""VideoWeaver synthetic composition tests; no legacy input required."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from agent_workload_characterization.adapters.videoweaver import (
    compose_run, compose_unassigned_request, make_provenance,
    parse_proxy_record, parse_react_event, SOURCE_ID, VERSION, DEFAULT_TRACE_TYPE)
from agent_workload_characterization.adapters.videoweaver_checks import check_samples
from agent_workload_characterization.adapters.base import RecordError, stable_id
from agent_workload_characterization.ir import TraceDocument, validate_json
import test_skeleton as skeleton


def _hash(data):
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


def _provenances(role="manifest"):
    return {"manifest": {"id": f"syn:{role}:m", "source_id": SOURCE_ID, "snapshot_id": _hash(role),
                         "source_record_ref": f"synthetic/{role}.json", "adapter_version": VERSION},
            "telemetry": {"id": f"syn:{role}:t", "source_id": SOURCE_ID, "snapshot_id": _hash(role+"t"),
                          "source_record_ref": "synthetic/telemetry.jsonl", "adapter_version": VERSION},
            "native": {"id": f"syn:{role}:n", "source_id": SOURCE_ID, "snapshot_id": _hash(role+"n"),
                       "source_record_ref": "synthetic/react.jsonl", "adapter_version": VERSION}}


def _manifest(**kw):
    base = {"trace_id": "synthetic:test:run-001", "generation_status": "success",
            "trajectory": {"wall_time_s": 100.0, "started_at": "2026-09-07T04:59:47.539Z",
                           "ended_at": "2026-09-07T05:01:27.539Z"},
            "openclaw_session_id": "syn-session-001"}
    base.update(kw)
    return base


def _proxy(trace_id="synthetic:test:run-001", call_id="syn-call-001", tokens=448):
    ctx = tokens + 200 if tokens is not None else None
    return {"trace_id": trace_id, "call_id": call_id, "model": "syn-model",
            "stream": True, "request_sequence": 1,
            "input_tokens": tokens, "output_tokens": 200,
            "context_tokens": ctx,
            "cached_input_tokens": 0, "reasoning_output_tokens": 25,
            "ttft": 1.5, "api_latency": 3.0, "upstream_latency": 3.0, "model_latency": 3.0,
            "http_status": 200, "usage_source": "upstream",
            "timestamp_request": 1000.0,
            "timestamp_request_utc": "2026-09-07T04:59:47.808168+00:00",
            "timestamp_first_token": 1001.5,
            "timestamp_response": 1003.0,
            "timestamp_response_utc": "2026-09-07T04:59:50.808168+00:00"}


def _react_call(tool_id="call-1", name="test_tool", with_result=True):
    lines = []
    lines.append({"type": "message", "timestamp": "2026-09-07T04:59:48.000Z",
                  "message": {"role": "assistant",
                              "content": [{"type": "toolCall", "id": tool_id, "name": name}]}})
    if with_result:
        lines.append({"type": "message", "timestamp": "2026-09-07T04:59:49.000Z",
                      "message": {"role": "toolResult", "toolCallId": tool_id, "content": "done"}})
    return lines


def _telemetry_entry(record, ref="line:1"):
    return {"record": record, "ref": ref, "hash": hashlib.sha256(json.dumps(record).encode()).hexdigest()}


def _react_entry(line):
    return {"record": line, "ref": "line:1", "hash": hashlib.sha256(json.dumps(line).encode()).hexdigest()}


def _syn_run(tel=None, react=None, trace_type="synthetic"):
    return compose_run(manifest=_manifest(),
                       telemetry=tel or [_telemetry_entry(_proxy())],
                       react=react or [_react_entry(r) for r in _react_call()],
                       provenances=_provenances(),
                       trace_type=trace_type)


class VideoWeaverTests(unittest.TestCase):
    def test_main_round_trip(self):
        doc = _syn_run()
        self.assertEqual(validate_json(doc.model_dump_json()), doc)
        self.assertEqual(doc.profile, "semantic_trace")
        self.assertEqual(doc.trace_type, "synthetic")
        self.assertEqual(len(doc.requests), 1)
        self.assertEqual(len(doc.events), 1)
        self.assertEqual(len(doc.provenance), 3)

    def test_trace_type_synthetic(self):
        doc = _syn_run()
        self.assertEqual(doc.trace_type, "synthetic")

    def test_trace_type_real(self):
        doc = compose_run(manifest=_manifest(), telemetry=[_telemetry_entry(_proxy())],
                          react=[], provenances=_provenances(), trace_type="benchmark_real")
        self.assertEqual(doc.trace_type, "benchmark_real")

    def test_duplicate_proxy_call_rejected(self):
        tel = [_telemetry_entry(_proxy(call_id="same")), _telemetry_entry(_proxy(call_id="same"))]
        with self.assertRaises(RecordError):
            compose_run(manifest=_manifest(), telemetry=tel, react=[],
                        provenances=_provenances(), trace_type="synthetic")

    def test_duplicate_toolcall_rejected(self):
        react = [_react_entry(r) for r in _react_call("dup") + _react_call("dup")]
        with self.assertRaises(RecordError):
            compose_run(manifest=_manifest(), telemetry=[_telemetry_entry(_proxy())],
                        react=react, provenances=_provenances(), trace_type="synthetic")

    def test_tool_without_result(self):
        doc = compose_run(manifest=_manifest(), telemetry=[_telemetry_entry(_proxy())],
                          react=[_react_entry(r) for r in _react_call("orphan-call", with_result=False)],
                          provenances=_provenances(), trace_type="synthetic")
        self.assertEqual(len([e for e in doc.events if e.kind == "tool_call"]), 1)
        self.assertIsNone(doc.events[0].interval.end_ns)

    def test_orphan_results_preserved(self):
        result_only = {"type": "message", "timestamp": "2026-09-07T04:59:49.000Z",
                       "message": {"role": "toolResult", "toolCallId": "missing-call", "content": "done"}}
        doc = compose_run(manifest=_manifest(), telemetry=[_telemetry_entry(_proxy())],
                          react=[_react_entry(result_only)],
                          provenances=_provenances(), trace_type="synthetic")
        m = {metric.name: metric for metric in doc.metrics if metric.scope_id == doc.runs[0].id}
        self.assertIn("orphan_tool_results", m)

    def test_conflicting_tool_result_rejected(self):
        result_a = {"type": "message", "timestamp": "2026-09-07T04:59:49.000Z",
                    "message": {"role": "toolResult", "toolCallId": "cid", "content": "first"}}
        result_b = {"type": "message", "timestamp": "2026-09-07T04:59:50.000Z",
                    "message": {"role": "toolResult", "toolCallId": "cid", "content": "second"}}
        tel = [_telemetry_entry(_proxy())]
        react = [_react_entry(r) for r in _react_call("cid") + [result_b]]
        with self.assertRaises(RecordError):
            compose_run(manifest=_manifest(), telemetry=tel, react=react,
                        provenances=_provenances(), trace_type="synthetic")

    def test_proxy_null_tokens_give_null_aggregates(self):
        proxy = _proxy()
        proxy["input_tokens"] = None
        proxy["output_tokens"] = None
        proxy["context_tokens"] = None  # proxy sets context = input+output, so null too
        doc = compose_run(manifest=_manifest(), telemetry=[_telemetry_entry(proxy)],
                          react=[], provenances=_provenances(), trace_type="synthetic")
        m = {metric.name: metric for metric in doc.metrics if metric.scope_id == doc.runs[0].id and metric.aggregation == "all_requests"}
        for name in ("total_input_tokens", "total_output_tokens", "max_input_context", "max_source_context_tokens"):
            self.assertIsNone(m[name].value, f"{name} should be None when inputs missing")

    def test_mixed_null_and_present_aggregates_null(self):
        """Strict coverage: one null token makes all aggregates null."""
        tel = [_telemetry_entry(_proxy(call_id="a", tokens=100)),
               _telemetry_entry(_proxy(call_id="b", tokens=None))]
        # b has null input, output and context
        tel[1]["record"]["output_tokens"] = None
        tel[1]["record"]["context_tokens"] = None
        doc = compose_run(manifest=_manifest(), telemetry=tel, react=[],
                          provenances=_provenances(), trace_type="synthetic")
        m = {metric.name: metric for metric in doc.metrics if metric.scope_id == doc.runs[0].id
             and metric.aggregation == "all_requests"}
        for name in ("total_input_tokens", "max_input_context"):
            self.assertIsNone(m[name].value, f"{name} strict: should be None")
        # model_request_count still counts both requests
        self.assertEqual(m["model_request_count"].value, 2)

    def test_http_200_without_usage_kept(self):
        proxy = _proxy()
        proxy["input_tokens"] = None
        proxy["output_tokens"] = None
        doc = compose_run(manifest=_manifest(), telemetry=[_telemetry_entry(proxy)],
                          react=[], provenances=_provenances(), trace_type="synthetic")
        req = doc.requests[0]
        self.assertIsNotNone(req.interval)
        self.assertIsNotNone(req.model_name)
        rid = req.id
        m = {metric.name: metric for metric in doc.metrics if metric.scope_id == rid}
        self.assertIsNone(m["input_tokens"].value)
        self.assertEqual(m["ttft"].value, 1.5)
        self.assertEqual(m["api_latency"].value, 3.0)

    def test_unassigned_request(self):
        raw = _proxy(trace_id="other-trace")
        prov = make_provenance("synthetic", _hash("other"), "other.jsonl", VERSION)
        doc = compose_unassigned_request(source_id="synthetic", raw_record=raw, provenance=prov)
        self.assertEqual(validate_json(doc.model_dump_json()), doc)
        self.assertEqual(doc.profile, "semantic_trace")
        self.assertEqual(doc.trace_type, "unknown")
        self.assertIsNone(doc.requests[0].run_id)
        self.assertEqual(doc.requests[0].association.status, "unresolved")
        self.assertEqual(len(doc.metrics), 4)

    def test_run_no_fake_elapsed(self):
        doc = _syn_run()
        run = doc.runs[0]
        self.assertIsNone(run.interval)
        self.assertEqual(run.execution_status, "completed")
        rand_metrics = {m.name: m for m in doc.metrics if m.scope_id == doc.runs[0].id and m.aggregation == "all_requests"}
        for name in ("run_elapsed", "local_cpu_time", "tool_cpu_time"):
            self.assertIsNone(rand_metrics[name].value)

    def test_three_provenances_separate(self):
        doc = _syn_run()
        self.assertEqual(len(doc.provenance), 3)
        refs = {p.source_record_ref for p in doc.provenance}
        self.assertIn("synthetic/manifest.json", refs)

    def test_negative_duration_rejected(self):
        proxy = _proxy()
        proxy["api_latency"] = -1.0
        with self.assertRaises(RecordError):
            parse_proxy_record(proxy)

    def test_reject_inf_ttft(self):
        proxy = _proxy()
        proxy["ttft"] = float("inf")
        with self.assertRaises(RecordError):
            parse_proxy_record(proxy)

    def test_reject_bool_value(self):
        proxy = _proxy()
        proxy["input_tokens"] = True
        with self.assertRaises(RecordError):
            parse_proxy_record(proxy)

    def test_reject_bool_timestamp(self):
        proxy = _proxy()
        proxy["timestamp_request"] = True
        with self.assertRaises(RecordError):
            parse_proxy_record(proxy)

    def test_huge_latency_rejected(self):
        proxy = _proxy()
        proxy["api_latency"] = 10 ** 400
        with self.assertRaises(RecordError):
            parse_proxy_record(proxy)


    def test_tool_result_missing_timestamp_keeps_open(self):
        """Result exists but timestamp absent -> end=null, not a validation error."""
        call_line = {"type": "message", "timestamp": "2026-09-07T04:59:48.000Z",
                     "message": {"role": "assistant",
                                 "content": [{"type": "toolCall", "id": "no-ts", "name": "x"}]}}
        result_no_ts = {"type": "message",
                        "message": {"role": "toolResult", "toolCallId": "no-ts", "content": "done"}}
        doc = compose_run(manifest=_manifest(), telemetry=[_telemetry_entry(_proxy())],
                          react=[_react_entry(call_line), _react_entry(result_no_ts)],
                          provenances=_provenances(), trace_type="synthetic")
        ev = [e for e in doc.events if e.kind == "tool_call"][0]
        self.assertIsNone(ev.interval.end_ns)
        self.assertEqual(ev.interval.missing_reason, "not_recorded")

    def test_tool_call_missing_timestamp(self):
        call_no_ts = {"type": "message",
                      "message": {"role": "assistant",
                                  "content": [{"type": "toolCall", "id": "no-start", "name": "y"}]}}
        result = {"type": "message", "timestamp": "2026-09-07T04:59:49.000Z",
                  "message": {"role": "toolResult", "toolCallId": "no-start", "content": "done"}}
        doc = compose_run(manifest=_manifest(), telemetry=[_telemetry_entry(_proxy())],
                          react=[_react_entry(call_no_ts), _react_entry(result)],
                          provenances=_provenances(), trace_type="synthetic")
        ev = [e for e in doc.events if e.kind == "tool_call"][0]
        self.assertIsNone(ev.interval.start_ns)
        self.assertEqual(ev.interval.missing_reason, "not_recorded")


class VideoWeaverIntegrationTests(unittest.TestCase):
    """Minimal bundle + catalog round-trips via check_samples.

    Each test builds a self-contained temp project with real files and runs the
    full check_samples pipeline, then asserts the expected failure mode.
    """

    def _full_catalog_and_bundle(self, root, telemetry_body, react_body, sidecar_ok=True):
        """Write a minimal but real bundle + catalog under *root*.

        Returns (catalog_path, samples_path, bundle_dir).  catalog  has three
        sources: gen_videoweaver_traces (the bundle dir), sidecar_videoweaver,
        telemetry_video_weaver (the raw JSONL).
        """
        import yaml
        base = Path(root)
        bund = base / "bundle"
        bund.mkdir()

        manifest = {"trace_id": "test:run", "generation_status": "success",
                    "trajectory": {"wall_time_s": 10.0,
                                   "started_at": "2026-09-07T04:59:47Z",
                                   "ended_at": "2026-09-07T04:59:57Z"}}
        (bund / "manifest.json").write_text(json.dumps(manifest))

        tel_dir = bund / "model_telemetry"
        tel_dir.mkdir()
        (tel_dir / "model_telemetry.jsonl").write_text(telemetry_body)
        (tel_dir / "model_telemetry_summary.json").write_text(json.dumps(
            {"model_request_count": 1, "total_input_tokens": 100,
             "total_output_tokens": 50, "max_context_tokens": 150}))

        nat_dir = bund / "native_trajectory"
        nat_dir.mkdir()
        (nat_dir / "original_ReAct.jsonl").write_text(react_body)

        # raw telemetry (for aux, but must exist)
        raw = base / "raw_telemetry.jsonl"
        raw.write_text(telemetry_body)

        # sidecar
        side = base / "sidecar"
        side.mkdir()
        if sidecar_ok:
            (side / "model_calls.jsonl").write_text(
                json.dumps({"trace_id": "test:run", "call_id": "c1",
                            "input_tokens": 100, "output_tokens": 50,
                            "context_tokens": 150, "ttft_s": 0.5, "api_latency_s": 1.0}) + "\n")
            (side / "tool_calls.jsonl").write_text(
                json.dumps({"trace_id": "test:run", "tool_call_id": "tcid"}) + "\n")
        else:
            (side / "model_calls.jsonl").write_text("")
            (side / "tool_calls.jsonl").write_text("")

        cat = base / "catalog.yaml"
        cat.write_text(yaml.safe_dump({
            "catalog_version": "1.1",
            "roots": {"benchmark": str(base), "project": str(base)},
            "sources": [
                {"source_id": "gen_videoweaver_traces",
                 "locator": {"root": "benchmark", "path": "bundle", "kind": "directory"}},
                {"source_id": "sidecar_videoweaver",
                 "locator": {"root": "benchmark", "path": "sidecar", "kind": "directory"}},
                {"source_id": "telemetry_video_weaver",
                 "locator": {"root": "benchmark", "path": "raw_telemetry.jsonl", "kind": "file"}},
            ]}))

        samples = base / "samples.yaml"
        samples.write_text(yaml.safe_dump({
            "catalog_version": "1.1", "audit_revision": "P0-10-test",
            "roots": {"benchmark": str(base), "project": str(base)},
            "real_candidates": [{
                "sample_id": "VW-LONG",
                "source_id": "gen_videoweaver_traces",
                "locator": {"root": "benchmark", "path": "bundle/manifest.json"},
                "record_id": "test:run",
                "expected": {"selected_model_requests": 1,
                             "total_input_tokens": 100, "total_output_tokens": 50,
                             "max_context_tokens": 150, "max_input_context": 100,
                             "manifest_wall_time_s": 10.0,
                             "manifest_tool_call_count": 1}}]}))

        return cat, samples, bund

    def _ok_proxy(self, tid="test:run", cid="c1"):
        return {"trace_id": tid, "call_id": cid, "model": "m", "stream": True,
                "request_sequence": 1, "input_tokens": 100, "output_tokens": 50,
                "context_tokens": 150, "cached_input_tokens": 0, "reasoning_output_tokens": 0,
                "ttft": 0.5, "api_latency": 1.0, "http_status": 200,
                "timestamp_request": 1000.0,
                "timestamp_request_utc": "2026-09-07T04:59:47.000+00:00",
                "timestamp_response": 1001.0,
                "timestamp_response_utc": "2026-09-07T04:59:48.000+00:00"}

    def test_happy_path_passes(self):
        with tempfile.TemporaryDirectory(prefix="vw-integ-") as tmp:
            tel = json.dumps(self._ok_proxy()) + "\n"
            react = json.dumps({"type": "message",
                                "message": {"role": "assistant",
                                            "content": [{"type": "toolCall", "id": "tcid", "name": "t"}]}}) + "\n"
            cat, samples, bund = self._full_catalog_and_bundle(tmp, tel, react)
            # Append the auxiliary incomplete record (required by AUX-INCOMPLETE)
            aux = {"trace_id": "videoweaver:reference_image_video:UniVBench-R2V:run-003",
                   "call_id": "b6c324adb8dd40179883ecead5cb4262", "model": "m",
                   "input_tokens": None, "output_tokens": None, "ttft": 3.716896,
                   "api_latency": 5.253902, "http_status": 200}
            with open(Path(tmp) / "raw_telemetry.jsonl", "a") as f:
                f.write(json.dumps(aux) + "\n")
            result = check_samples(cat, samples)
            self.assertEqual(result["status"], "PASS")

    def test_malformed_react_causes_failure(self):
        with tempfile.TemporaryDirectory(prefix="vw-mal-") as tmp:
            tel = json.dumps(self._ok_proxy()) + "\n"
            react = "NOT VALID JSON\n"
            cat, samples, _ = self._full_catalog_and_bundle(tmp, tel, react)
            with self.assertRaises(ValueError):
                check_samples(cat, samples)

    def test_malformed_telemetry_causes_failure(self):
        with tempfile.TemporaryDirectory(prefix="vw-mal-tel-") as tmp:
            tel = "NOT VALID JSON\n"
            react = json.dumps({"type": "message",
                                "message": {"role": "assistant",
                                            "content": [{"type": "toolCall", "id": "tcid", "name": "t"}]}}) + "\n"
            cat, samples, _ = self._full_catalog_and_bundle(tmp, tel, react)
            with self.assertRaises(ValueError):
                check_samples(cat, samples)

    def test_empty_sidecar_causes_fail(self):
        with tempfile.TemporaryDirectory(prefix="vw-side-") as tmp:
            tel = json.dumps(self._ok_proxy()) + "\n"
            react = json.dumps({"type": "message",
                                "message": {"role": "assistant",
                                            "content": [{"type": "toolCall", "id": "tcid", "name": "t"}]}}) + "\n"
            cat, samples, _ = self._full_catalog_and_bundle(tmp, tel, react, sidecar_ok=False)
            result = check_samples(cat, samples)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("missing", str(result["results"]))

    def test_symlink_escape_causes_failure(self):
        """Catalog root (bundles/) contains two sibling bundles; selected bundle's
        subdir symlinks to sibling.  The check must reject because the resolved
        path escapes bundle_dir (the selected bundle), even though it stays within
        the catalog root (declared_bundle = bundles/)."""
        import os
        import shutil
        with tempfile.TemporaryDirectory(prefix="vw-sym-") as tmp:
            base = Path(tmp)
            bundles = base / "bundles"
            bundles.mkdir()
            selected = bundles / "selected"
            sibling = bundles / "sibling"
            for d in (selected, sibling):
                d.mkdir(parents=True)
                (d / "manifest.json").write_text(json.dumps(
                    {"trace_id": "test:run", "generation_status": "success",
                     "trajectory": {"wall_time_s": 10.0,
                                    "started_at": "2026-09-07T04:59:47Z",
                                    "ended_at": "2026-09-07T04:59:57Z"}}))
                (d / "model_telemetry").mkdir()
                tel = json.dumps({"trace_id": "test:run", "call_id": "c1",
                                  "input_tokens": 100, "output_tokens": 50,
                                  "context_tokens": 150, "ttft": 0.5,
                                  "api_latency": 1.0, "http_status": 200,
                                  "timestamp_request": 1000,
                                  "timestamp_request_utc": "2026-09-07T04:59:47Z",
                                  "timestamp_response": 1001,
                                  "timestamp_response_utc": "2026-09-07T04:59:48Z"})
                (d / "model_telemetry" / "model_telemetry.jsonl").write_text(
                    tel + "\n")
                (d / "model_telemetry" / "model_telemetry_summary.json").write_text(
                    json.dumps({"model_request_count": 1, "total_input_tokens": 100,
                                "total_output_tokens": 50, "max_context_tokens": 150}))
            # sibling has a native_trajectory; selected symlinks to it
            (sibling / "native_trajectory").mkdir()
            (sibling / "native_trajectory" / "original_ReAct.jsonl").write_text(
                json.dumps({"type": "message",
                            "message": {"role": "assistant",
                                        "content": [{"type": "toolCall", "id": "tcid", "name": "t"}]}}) + "\n")
            os.symlink(sibling / "native_trajectory",
                       selected / "native_trajectory", target_is_directory=True)
            # raw telemetry and sidecar (must exist for the check to proceed)
            (base / "raw_telemetry.jsonl").write_text(tel + "\n")
            side = base / "sidecar"
            side.mkdir()
            (side / "model_calls.jsonl").write_text(
                json.dumps({"trace_id": "test:run", "call_id": "c1",
                            "input_tokens": 100, "output_tokens": 50,
                            "context_tokens": 150, "ttft_s": 0.5,
                            "api_latency_s": 1.0}) + "\n")
            (side / "tool_calls.jsonl").write_text(
                json.dumps({"trace_id": "test:run", "tool_call_id": "tcid"}) + "\n")
            import yaml
            cat = base / "catalog.yaml"
            # gen_videoweaver_traces points at bundles/ (contains selected + sibling)
            cat.write_text(yaml.safe_dump({
                "catalog_version": "1.1",
                "roots": {"benchmark": str(base), "project": str(base)},
                "sources": [
                    {"source_id": "gen_videoweaver_traces",
                     "locator": {"root": "benchmark", "path": "bundles", "kind": "directory"}},
                    {"source_id": "sidecar_videoweaver",
                     "locator": {"root": "benchmark", "path": "sidecar", "kind": "directory"}},
                    {"source_id": "telemetry_video_weaver",
                     "locator": {"root": "benchmark", "path": "raw_telemetry.jsonl", "kind": "file"}},
                ]}))
            samples = base / "samples.yaml"
            samples.write_text(yaml.safe_dump({
                "catalog_version": "1.1", "audit_revision": "P0-10-sym",
                "roots": {"benchmark": str(base), "project": str(base)},
                "real_candidates": [{
                    "sample_id": "VW-LONG",
                    "source_id": "gen_videoweaver_traces",
                    "locator": {"root": "benchmark", "path": "bundles/selected/manifest.json"},
                    "record_id": "test:run",
                    "expected": {"selected_model_requests": 1,
                                 "total_input_tokens": 100, "total_output_tokens": 50,
                                 "max_context_tokens": 150, "max_input_context": 100,
                                 "manifest_wall_time_s": 10.0,
                                 "manifest_tool_call_count": 1}}]}))
            with self.assertRaises(ValueError):
                check_samples(cat, samples)


class VideoWeaverCLITests(unittest.TestCase):
    run_python = skeleton.CLITests.run_python
    run_cli = skeleton.CLITests.run_cli

    def test_missing_catalog_fails(self):
        result = self.run_cli("check-videoweaver-samples", "--catalog", "/nonexistent/catalog.yaml")
        self.assertEqual(result.returncode, 1)
        self.assertIn("INVALID", result.stderr)


if __name__ == "__main__":
    unittest.main()