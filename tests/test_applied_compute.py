"""Applied Compute synthetic contract tests; no legacy input required."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pydantic import ValidationError
import yaml

from agent_workload_characterization.adapters import Catalog, ingest
from agent_workload_characterization.adapters.applied_compute import AppliedComputeAdapter
from agent_workload_characterization.adapters.base import Context, RawRecord, RecordError
from agent_workload_characterization.ir import TraceDocument, validate_json
from agent_workload_characterization.metric_contracts import template_lengths
from agent_workload_characterization.adapters import stable_id
import test_skeleton as skeleton


def template(N=2, initial=6318, assistant=(101, 1084), tool=(6118, 23),
             final=801, delays=(0.431, 2.339)):
    return {
        "num_turns": N,
        "input_prompt_length": initial,
        "assistant_response_length": list(assistant),
        "tool_call_output_length": list(tool),
        "tool_call_latency": list(delays),
        "final_assistant_response_length": final,
    }


def normalize(raw, source_id="fixture-applied", snapshot="fixture-v1", ref="line:1"):
    adapter = AppliedComputeAdapter()
    return adapter.normalize(RawRecord(ref, hashlib.sha256(json.dumps(raw).encode()).hexdigest(), raw),
                             Context(source_id, snapshot, adapter.version, {"trace_type": "synthetic"}))


def metric_value(doc, scope, name):
    for m in doc.metrics:
        if m.scope_id == scope and m.name == name:
            return m.value, m.evidence, m.missing_reason
    return None, None, None


def template_metrics(doc):
    tid = doc.templates[0].id
    out = {}
    for m in doc.metrics:
        if m.scope_id == tid:
            out[m.name] = {"value": m.value, "evidence": m.evidence,
                           "missing_reason": m.missing_reason, "aggregation": m.aggregation}
    return out


class AppliedComputeTests(unittest.TestCase):

    def test_n2_hand_calculation(self):
        raw = template()
        doc = normalize(raw)
        t = doc.templates[0]
        self.assertEqual(t.tool_use_turns, 2)
        self.assertEqual(t.initial_input, 6318)
        self.assertEqual(t.assistant_outputs, [101, 1084])
        self.assertEqual(t.tool_outputs, [6118, 23])
        self.assertEqual(t.final_output, 801)
        self.assertEqual(t.unit, "token")
        self.assertIsNone(t.length_missing_reason)

        m = template_metrics(doc)
        self.assertEqual(m["model_request_count"]["value"], 3)
        self.assertEqual(m["total_input_tokens"]["value"], 32499)
        self.assertEqual(m["max_context_tokens"]["value"], 13644)
        self.assertEqual(m["total_output_tokens"]["value"], 1986)
        self.assertEqual(m["total_simulated_delay"]["value"], 2.770)

        contexts = {}
        delays = {}
        for metric in doc.metrics:
            if metric.name == "completion_context":
                parts = metric.aggregation.split(":") if ":" in metric.aggregation else [metric.aggregation, ""]
                contexts[int(parts[1])] = metric.value
            elif metric.name == "simulated_tool_delay":
                parts = metric.aggregation.split(":") if ":" in metric.aggregation else [metric.aggregation, ""]
                delays[int(parts[1])] = metric.value
        self.assertEqual([contexts[i] for i in sorted(contexts)], [6318, 12537, 13644])
        for i, expected in enumerate([0.431, 2.339]):
            self.assertEqual(delays[i], expected)

        for key in ("model_request_count", "total_input_tokens", "total_simulated_delay"):
            self.assertEqual(m[key]["evidence"], "template_parameter")

    def test_n0(self):
        raw = template(N=0, initial=32, final=64, assistant=(), tool=(), delays=())
        doc = normalize(raw)
        t = doc.templates[0]
        self.assertEqual(t.tool_use_turns, 0)
        m = template_metrics(doc)
        self.assertEqual(m["model_request_count"]["value"], 1)
        self.assertEqual(m["total_input_tokens"]["value"], 32)
        self.assertEqual(m["max_context_tokens"]["value"], 32)
        self.assertEqual(m["total_output_tokens"]["value"], 64)
        self.assertEqual(m["total_simulated_delay"]["value"], 0.0)

    def test_zero_preserved(self):
        raw = template(initial=0, final=0, delays=(0.0, 0.0))
        doc = normalize(raw)
        t = doc.templates[0]
        self.assertEqual(t.initial_input, 0)
        self.assertEqual(t.final_output, 0)
        m = template_metrics(doc)
        self.assertEqual(m["total_simulated_delay"]["value"], 0.0)
        self.assertIsNotNone(m["total_input_tokens"]["value"])

    def test_initial_missing_propagates(self):
        raw = template(initial=None)
        doc = normalize(raw)
        t = doc.templates[0]
        self.assertIsNone(t.initial_input)
        self.assertEqual(t.length_missing_reason, "not_recorded")
        m = template_metrics(doc)
        self.assertIsNone(m["total_input_tokens"]["value"])
        self.assertIsNone(m["max_context_tokens"]["value"])

    def test_final_missing_does_not_remove_outputs(self):
        raw = template(final=None)
        doc = normalize(raw)
        self.assertEqual(doc.templates[0].tool_use_turns, 2)
        m = template_metrics(doc)
        # total_output sums final too, so it becomes unavailable when final is null
        self.assertIsNone(m["total_output_tokens"]["value"])
        # context inputs (completion contexts) are unaffected
        contexts = {}
        for metric in doc.metrics:
            if metric.name == "completion_context":
                parts = metric.aggregation.split(":")
                contexts[int(parts[1])] = metric.value
        self.assertEqual([contexts[i] for i in sorted(contexts)], [6318, 12537, 13644])

    def test_delay_null_does_not_affect_tokens(self):
        raw = template(delays=(None, 2.339))
        doc = normalize(raw)
        m = template_metrics(doc)
        self.assertEqual(m["total_input_tokens"]["value"], 32499)
        self.assertIsNone(m["total_simulated_delay"]["value"])

    def test_delay_zero_is_not_null(self):
        raw = template(delays=(0.0, 0.0))
        doc = normalize(raw)
        delays_found = {}
        for metric in doc.metrics:
            if metric.name == "simulated_tool_delay" and "tool_turn:" in metric.aggregation:
                parts = metric.aggregation.split(":")
                delays_found[int(parts[1])] = metric.value
        for i in range(2):
            self.assertEqual(delays_found[i], 0.0)
        self.assertEqual(len(delays_found), 2)

    def test_unknown_length_as_zero_fails(self):
        for bad in (True, -1, 1.5, "42", float("inf")):
            with self.subTest(bad=bad):
                with self.assertRaises(RecordError):
                    normalize(template(initial=bad))

    def test_negative_latency_fails(self):
        with self.assertRaises(RecordError):
            normalize(template(delays=(-1, 2.339)))

    def test_nonfinite_latency_fails(self):
        for bad in (float("inf"), float("nan")):
            with self.subTest(bad=bad):
                with self.assertRaises((RecordError, ValueError)):
                    normalize(template(delays=(bad, 0.5)))

    def test_bool_as_value_fails(self):
        with self.assertRaises(RecordError):
            normalize(template(initial=True))

    def test_float_initial_rejected(self):
        # 6318.0 must not silently become 6318
        for bad in (6318.0, 1.5):
            with self.subTest(bad=bad):
                with self.assertRaises(RecordError):
                    normalize(template(initial=bad))

    def test_missing_initial_key_allowed_as_unknown(self):
        raw = template()
        del raw["input_prompt_length"]
        doc = normalize(raw)
        self.assertIsNone(doc.templates[0].initial_input)
        self.assertEqual(doc.templates[0].length_missing_reason, "not_recorded")
        self.assertIsNone(template_metrics(doc)["total_input_tokens"]["value"])

    def test_missing_final_key_allowed_as_unknown(self):
        raw = template()
        del raw["final_assistant_response_length"]
        doc = normalize(raw)
        self.assertIsNone(doc.templates[0].final_output)
        self.assertIsNone(template_metrics(doc)["total_output_tokens"]["value"])

    def test_huge_integer_does_not_overflow_process(self):
        # float(10**400) would raise OverflowError; it must become RecordError.
        raw = template(delays=(0.5, 1.0))
        raw["tool_call_latency"] = [10**400, 1.0]
        with self.assertRaises((RecordError, ValueError)):
            normalize(raw)

    def test_huge_float_does_not_overflow_process(self):
        raw = template(delays=(1e400, 1.0))
        with self.assertRaises((RecordError, ValueError)):
            normalize(raw)

    def test_vector_wrong_length_fails(self):
        with self.assertRaises(RecordError):
            normalize(template(assistant=(101,)))

    def test_vector_not_list_fails(self):
        raw = template()
        raw["assistant_response_length"] = 42
        with self.assertRaises(RecordError):
            normalize(raw)

    def test_scalar_not_list_for_latency_fails(self):
        raw = template()
        raw["tool_call_latency"] = 0.5
        with self.assertRaises(RecordError):
            normalize(raw)

    def test_n_negative_fails(self):
        with self.assertRaises(RecordError):
            normalize(template(N=-1))

    def test_n_bool_fails(self):
        with self.assertRaises(RecordError):
            normalize(template(N=True))

    def test_n_float_fails(self):
        with self.assertRaises(RecordError):
            normalize(template(N=2.5))

    def test_n_string_fails(self):
        raw = template()
        raw["num_turns"] = "2"
        with self.assertRaises(RecordError):
            normalize(raw)

    def test_profile_and_trace_type(self):
        doc = normalize(template())
        self.assertEqual(doc.profile, "macro_template")
        self.assertEqual(doc.trace_type, "synthetic")
        self.assertEqual(len(doc.templates), 1)
        self.assertFalse(doc.runs)
        self.assertFalse(doc.agents)
        self.assertFalse(doc.requests)
        self.assertFalse(doc.clocks)

    def test_three_sources_have_distinct_ids(self):
        ids = set()
        for sid in ("applied_agentic_coding", "applied_code_qa", "applied_office_work"):
            doc = normalize(template(), source_id=sid, ref=f"line:1_{sid}")
            tid = doc.templates[0].id
            self.assertNotIn(tid, ids, f"{sid} template ID collides")
            ids.add(tid)
            pid = doc.provenance[0].id
            self.assertNotIn(pid, ids, f"{sid} provenance ID collides")
            ids.add(pid)

    def test_identity_stable_across_location_snapshot(self):
        # Same source position (line:1729) keeps identity when file moves / snapshot changes.
        first = normalize(template(), source_id="applied_agentic_coding", ref="line:1729")
        second = normalize(template(), source_id="applied_agentic_coding", ref="line:1729",
                           snapshot="different-snapshot")
        self.assertEqual(first.templates[0].id, second.templates[0].id)
        self.assertEqual(first.provenance[0].id, second.provenance[0].id)
        # Different line positions are distinct identities.
        third = normalize(template(), source_id="applied_agentic_coding", ref="line:1728")
        self.assertNotEqual(first.templates[0].id, third.templates[0].id)

    def test_runtime_entities_are_empty(self):
        doc = normalize(template())
        for field in ("runs", "agents", "requests", "events", "jobs", "sessions",
                      "processes", "resource_scopes", "clocks", "attempts"):
            self.assertFalse(getattr(doc, field), f"{field} should be empty")

    def test_ir_round_trip(self):
        doc = normalize(template())
        self.assertEqual(validate_json(doc.model_dump_json()), doc)

    def test_unknown_keys_rejected(self):
        raw = template()
        raw["unknown_field"] = "surprise"
        with self.assertRaises(RecordError):
            normalize(raw)

    def test_missing_keys_rejected(self):
        raw = template()
        del raw["num_turns"]
        with self.assertRaises(RecordError):
            normalize(raw)

    def test_ingest_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="awc-applied-test-") as temporary:
            root = Path(temporary)
            project, legacy = root / "project", root / "legacy"
            project.mkdir()
            legacy.mkdir()
            path = legacy / "input.jsonl"
            path.write_text(json.dumps(template()) + "\n")
            catalog = project / "catalog.yaml"
            catalog.write_text(yaml.safe_dump({
                "catalog_version": "1.1",
                "roots": {"project": str(project), "legacy": str(legacy)},
                "sources": [{"source_id": "fixture-applied",
                             "locator": {"root": "legacy", "path": "input.jsonl", "kind": "file"}}]}))
            adapter = AppliedComputeAdapter()
            cat = Catalog(catalog)
            batch = ingest(adapter, cat, "fixture-applied", project, config={"trace_type": "synthetic"})
            self.assertEqual(batch["counts"]["seen"], 1)
            self.assertEqual(batch["counts"]["accepted"], 1)
            self.assertEqual(batch["counts"]["runs"], 0)
            self.assertEqual(batch["counts"]["rejected"], 0)
            row = json.loads((Path(batch["path"]) / "documents.jsonl").read_text())
            doc = validate_json(json.dumps(row["trace"]))
            self.assertEqual(doc.profile, "macro_template")
            self.assertEqual(doc.trace_type, "synthetic")
            self.assertEqual(len(doc.templates), 1)

    def test_ingest_deduplicate_reuse(self):
        with tempfile.TemporaryDirectory(prefix="awc-applied-ingest-") as temporary:
            root = Path(temporary)
            project, legacy = root / "project", root / "legacy"
            project.mkdir()
            legacy.mkdir()
            path = legacy / "input.jsonl"
            path.write_text(json.dumps(template()) + "\n")
            catalog = project / "catalog.yaml"
            catalog.write_text(yaml.safe_dump({
                "catalog_version": "1.1",
                "roots": {"project": str(project), "legacy": str(legacy)},
                "sources": [{"source_id": "fixture-applied",
                             "locator": {"root": "legacy", "path": "input.jsonl", "kind": "file"}}]}))
            adapter = AppliedComputeAdapter()
            cat = Catalog(catalog)
            first = ingest(adapter, cat, "fixture-applied", project, config={"trace_type": "synthetic"})
            second = ingest(adapter, cat, "fixture-applied", project, config={"trace_type": "synthetic"})
            self.assertTrue(second["reused"])
            self.assertEqual(second["counts"]["accepted"], first["counts"]["accepted"])

    def test_ingest_reject_bad_record(self):
        with tempfile.TemporaryDirectory(prefix="awc-applied-reject-") as temporary:
            root = Path(temporary)
            project, legacy = root / "project", root / "legacy"
            project.mkdir()
            legacy.mkdir()
            path = legacy / "input.jsonl"
            bad = template()
            bad["num_turns"] = -1
            path.write_text(json.dumps(bad) + "\n")
            catalog = project / "catalog.yaml"
            catalog.write_text(yaml.safe_dump({
                "catalog_version": "1.1",
                "roots": {"project": str(project), "legacy": str(legacy)},
                "sources": [{"source_id": "fixture-applied",
                             "locator": {"root": "legacy", "path": "input.jsonl", "kind": "file"}}]}))
            adapter = AppliedComputeAdapter()
            cat = Catalog(catalog)
            batch = ingest(adapter, cat, "fixture-applied", project, config={"trace_type": "synthetic"})
            self.assertEqual(batch["counts"]["seen"], 1)
            self.assertEqual(batch["counts"]["rejected"], 1)
            self.assertEqual(batch["counts"]["accepted"], 0)

    def test_template_fixture_reflects_source(self):
        doc = normalize(template())
        t = doc.templates[0]
        self.assertIn("6918da7", t.length_definition_ref)
        self.assertIn("token", t.unit)


class AppliedComputeCLITests(unittest.TestCase):
    run_python = skeleton.CLITests.run_python
    run_cli = skeleton.CLITests.run_cli

    def test_missing_catalog_fails(self):
        result = self.run_cli("check-applied-samples", "--catalog", "/nonexistent/catalog.yaml")
        self.assertEqual(result.returncode, 1)
        self.assertIn("INVALID", result.stderr)


if __name__ == "__main__":
    unittest.main()