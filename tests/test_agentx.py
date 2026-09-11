"""AgentX contract fixtures are explicitly synthetic; no legacy input required."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pydantic import ValidationError
import yaml

from agent_workload_characterization.adapters import Catalog, ingest
from agent_workload_characterization.adapters.agentx import AgentXAdapter, summarize
from agent_workload_characterization.adapters.base import Context, RawRecord, RecordError
from agent_workload_characterization.ir import TraceDocument, validate_json
from agent_workload_characterization.migrations import upgrade_v0_1
import test_skeleton as skeleton


def request(**updates):
    return {"type": "s", "t": 0, "api_time": 1.515, "in": 448, "out": 21,
            "model": "synthetic-model", "hash_ids": [0, 1, 2, 3, 4, 5, 6], "ttft": 1.198} | updates


def source(requests=None):
    return {"id": "synthetic-session", "models": ["synthetic-model"], "block_size": 64,
            "hash_id_scope": "local", "requests": [request()] if requests is None else requests}


def normalize(raw, snapshot="fixture-v1", ref="line:1"):
    adapter = AgentXAdapter()
    return adapter.normalize(RawRecord(ref, hashlib.sha256(json.dumps(raw).encode()).hexdigest(), raw),
                             Context("fixture-agentx", snapshot, adapter.version, {"trace_type": "synthetic"}))


def values(doc, scope="all_agents"):
    return {key: item["value"] for key, item in summarize(doc)["metrics"][scope].items()}


class AgentXTests(unittest.TestCase):
    def test_single_request_gold(self):
        doc = normalize(source())
        result = values(doc)
        self.assertEqual([result[k] for k in ("model_request_count", "input_tokens", "output_tokens", "model_work")], [1, 448, 21, 1515000000])
        self.assertIsNone(result["run_elapsed"])
        self.assertIsNone(result["turn_count"])
        self.assertIsNone(doc.runs[0].task_id)
        self.assertIsNone(doc.runs[0].attempt_id)
        self.assertIsNone(doc.runs[0].interval)
        self.assertEqual(doc.trace_type, "synthetic")
        self.assertEqual(validate_json(doc.model_dump_json()), doc)

    def test_full_prefix_and_model(self):
        doc = normalize(source([request(hash_ids=list(range(1000)))]))
        self.assertEqual(doc.requests[0].prefix.hashes, list(map(str, range(1000))))
        self.assertEqual(doc.requests[0].prefix.block_size, 64)
        self.assertEqual(doc.requests[0].prefix.hash_id_scope, "local")
        self.assertEqual(doc.requests[0].model_name, "synthetic-model")
        self.assertEqual(doc.requests[0].source_request_type, "s")

    def test_missing_latency_does_not_make_zero_end(self):
        doc = normalize(source([request(api_time=None)]))
        self.assertIsNone(doc.requests[0].interval.end_ns)
        self.assertEqual(doc.requests[0].interval.start_ns, 0)
        for key in ("model_work", "model_busy", "observed_span"):
            self.assertIsNone(values(doc)[key])

    def test_missing_start_does_not_remove_observed_duration(self):
        doc = normalize(source([request(t=None)]))
        self.assertEqual(values(doc)["model_work"], 1515000000)
        self.assertIsNone(values(doc)["model_busy"])
        self.assertIsNone(doc.requests[0].interval.start_ns)

    def test_observed_zero(self):
        doc = normalize(source([request(api_time=0, **{"in": 0, "out": 0}, ttft=0)]))
        for key in ("input_tokens", "output_tokens", "model_work", "model_busy", "observed_span"):
            self.assertEqual(values(doc)[key], 0)
        self.assertEqual(doc.requests[0].interval.end_ns, 0)

    def test_missing_tokens_do_not_become_partial_sum(self):
        doc = normalize(source([request(), request(**{"in": None})]))
        self.assertIsNone(values(doc)["input_tokens"])
        self.assertIsNone(values(doc)["max_context_tokens"])
        self.assertEqual(values(doc)["output_tokens"], 42)

    def test_group_absolute_offset_main_all_and_status(self):
        raw = source([request(api_time=10), {"type": "subagent", "agent_id": "child", "t": 5,
                      "duration_ms": 10000, "status": "completed", "tool_use_count": None,
                      "total_tokens": 999999, "requests": [request(type="n", t=5, api_time=10)]}])
        doc = normalize(raw)
        self.assertEqual(values(doc, "main_agent")["input_tokens"], 448)
        self.assertEqual(values(doc)["input_tokens"], 896)
        self.assertEqual(values(doc)["model_work"], 20_000_000_000)
        self.assertEqual(values(doc)["model_busy"], 15_000_000_000)
        self.assertEqual(values(doc)["model_overlap"], 5_000_000_000)
        self.assertEqual(doc.requests[1].interval.start_ns, 5_000_000_000)
        self.assertEqual(doc.agents[1].parent_id, doc.agents[0].id)
        self.assertNotEqual(doc.agents[1].parent_id, doc.agents[1].id)
        self.assertEqual(doc.agents[1].source_status, "completed")
        self.assertEqual(doc.runs[0].execution_status, "unknown")
        self.assertIsNone(values(doc)["tool_call_count"])
        metric = next(m for m in doc.metrics if m.name == "source_tool_use_count")
        self.assertIsNone(metric.value)
        self.assertEqual(metric.scope_id, doc.agents[1].id)

    def test_nested_groups_and_siblings(self):
        group = lambda identity, children: {"type": "subagent", "agent_id": identity, "requests": children}
        doc = normalize(source([group("a", [request(), group("b", [request()])]), group("c", [request()])]))
        self.assertEqual(values(doc)["subagent_count"], 3)
        self.assertEqual(values(doc)["model_request_count"], 3)
        self.assertEqual(values(doc, "main_agent")["model_request_count"], 0)
        self.assertEqual(doc.agents[2].parent_id, doc.agents[1].id)
        self.assertEqual(doc.agents[3].parent_id, doc.agents[0].id)
        self.assertEqual(doc.links, [])  # no fabricated dependency/join

    def test_unknown_precision_not_nanosecond_accuracy(self):
        clock = normalize(source()).clocks[0]
        self.assertIsNone(clock.precision_ns)
        self.assertEqual(clock.precision_missing_reason, "not_recorded")
        self.assertEqual(clock.kind, "source_relative")

    def test_invalid_numeric_and_unknown_request_rejected(self):
        for update in ({"in": True}, {"in": -1}, {"t": -1}, {"api_time": "1"},
                       {"api_time": float("inf")}, {"hash_ids": [False]}, {"type": "tool"}):
            with self.subTest(update=update), self.assertRaises((RecordError, ValidationError)):
                normalize(source([request(**update)]))

    def test_missing_identity_and_requests_rejected(self):
        for key in ("id", "requests"):
            raw = source()
            del raw[key]
            with self.assertRaises(RecordError):
                normalize(raw)

    def test_duplicate_subagent_identity_rejected(self):
        group = {"type": "subagent", "agent_id": "same", "requests": []}
        with self.assertRaises(RecordError):
            normalize(source([group, group]))

    def test_scope_tool_zero_not_run_count(self):
        group = {"type": "subagent", "agent_id": "child", "tool_use_count": 0, "requests": []}
        doc = normalize(source([group]))
        self.assertEqual(next(m.value for m in doc.metrics if m.name == "source_tool_use_count"), 0)
        self.assertIsNone(values(doc)["tool_call_count"])
        self.assertIsNone(values(doc)["max_context_tokens"])

    def test_identity_stable_across_location_snapshot(self):
        first = normalize(source())
        second = normalize(source(), "different-snapshot", "line:99")
        self.assertEqual(first.runs[0].id, second.runs[0].id)
        self.assertEqual(first.requests[0].id, second.requests[0].id)

    def test_ax7_scalar_hand_calculation(self):
        # Numeric reproduction only; not the original session or original hashes.
        scalars = [(0, 1.515, 448, 21), (.091, 3.711, 41984, 431), (3.77, 17.59, 2944, 1179),
                   (21.474, 9.675, 44800, 797), (211.801, 1.792, 46528, 82),
                   (355.343, 3.901, 46464, 600), (373.459, 12.222, 11200, 987)]
        doc = normalize(source([request(t=t, api_time=d, **{"in": i, "out": o}) for t, d, i, o in scalars]))
        actual = values(doc)
        self.assertEqual(actual["input_tokens"], 194368)
        self.assertEqual(actual["output_tokens"], 4097)
        self.assertEqual(actual["model_work"], 50_406_000_000)
        self.assertEqual(actual["model_busy"], 48_950_000_000)
        self.assertEqual(actual["observed_span"], 385_681_000_000)
        self.assertIsNone(actual["run_elapsed"])

    def test_ingest_duplicate_and_lineage_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="awc-agentx-test-") as temporary:
            root = Path(temporary)
            project, legacy = root / "project", root / "legacy"
            project.mkdir()
            legacy.mkdir()
            path = legacy / "input.jsonl"
            path.write_text((json.dumps(source()) + "\n") * 2)
            catalog = project / "catalog.yaml"
            catalog.write_text(yaml.safe_dump({"catalog_version": "1.1", "roots": {"project": str(project), "legacy": str(legacy)},
                                              "sources": [{"source_id": "fixture-agentx", "locator": {"root": "legacy", "path": "input.jsonl", "kind": "file"}}]}))
            arguments = (AgentXAdapter(), Catalog(catalog), "fixture-agentx", project)
            batch = ingest(*arguments, config={"trace_type": "synthetic"})
            self.assertEqual(batch["counts"]["runs"], 1)
            self.assertEqual(batch["counts"]["duplicates"], 1)
            self.assertTrue(ingest(*arguments, config={"trace_type": "synthetic"})["reused"])
            row = json.loads((Path(batch["path"]) / "documents.jsonl").read_text())
            self.assertEqual(validate_json(json.dumps(row["trace"])).trace_type, "synthetic")


class MigrationTests(unittest.TestCase):
    def old(self):
        return {"schema_version": "0.1.0", "profile": "semantic_trace", "trace_type": "synthetic",
                "provenance": [{"id": "p", "source_id": "fixture", "snapshot_id": "v1", "source_record_ref": "original", "adapter_version": "manual/1"}],
                "clocks": [{"id": "c", "kind": "monotonic", "source": "synthetic", "precision_ns": 1}]}

    def test_explicit_upgrade_preserves_source(self):
        original = self.old()
        payload = json.dumps(original)
        upgraded = upgrade_v0_1(payload)
        self.assertEqual(upgraded.schema_version, "0.2.0")
        self.assertEqual(upgraded.provenance[0].source_record_ref, "original")
        self.assertEqual(original["schema_version"], "0.1.0")
        self.assertEqual(upgraded, upgrade_v0_1(payload))
        self.assertEqual(validate_json(upgraded.model_dump_json()), upgraded)
        with self.assertRaises(ValidationError):
            validate_json(payload)  # no silent migration

    def test_reject_invalid_legacy_and_wrong_version(self):
        for change in ("new-field", "missing-precision", "wrong-version"):
            data = self.old()
            if change == "new-field":
                data["clocks"][0]["precision_missing_reason"] = None
            elif change == "missing-precision":
                data["clocks"][0]["precision_ns"] = None
            else:
                data["schema_version"] = "0.2.0"
            with self.assertRaises(ValueError):
                upgrade_v0_1(json.dumps(data))


class AgentXCLITests(unittest.TestCase):
    run_python = skeleton.CLITests.run_python
    run_cli = skeleton.CLITests.run_cli

    def test_missing_selectors_fail(self):
        result = self.run_cli("check-agentx-samples", "--catalog", "/nonexistent/catalog.yaml")
        self.assertEqual(result.returncode, 1)
        self.assertIn("INVALID", result.stderr)
