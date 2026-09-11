"""Synthetic semantic/gold tests; never ingest or mutate legacy trace assets."""

import copy
import json
import unittest

from pydantic import ValidationError

from agent_workload_characterization.ir import Interval, TraceDocument, validate_json
from agent_workload_characterization.metric_contracts import interval_totals, template_lengths
import test_skeleton as skeleton

ROOT = skeleton.ROOT
FIXTURES = ROOT / "tests/fixtures/ir"


def fixture(name="semantic_open"):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def bound(identity, **fields):
    return {"id": identity, "provenance_id": "p", "run_id": "run", "association": {"status": "resolved", "method": "explicit_id", "evidence_ref": "synthetic fixture"}, **fields}


def interval(start=0, end=10, clock="clock"):
    return {"clock_id": clock, "start_ns": start, "end_ns": end, "source": "native_event", "missing_reason": "censored" if start is None or end is None else None}


def resource():
    doc = fixture()
    doc["profile"] = "resource_trace"
    doc["events"].append(bound("tool-2", kind="tool_call", name="poll"))
    doc["jobs"] = [bound("job")]
    doc["processes"] = [bound("process", host_id="host", boot_id="boot", pid_namespace="ns", pid=42, start_identifier="start-1")]
    doc["resource_scopes"] = [bound("scope", kind="service", attribution_method="shared_scope", includes_children=True)]
    association = {"status": "resolved", "method": "explicit_id", "evidence_ref": "fixture"}
    doc["links"] = [{"source_id": a, "target_id": b, "kind": k, "association": association} for a, b, k in [
        ("tool", "job", "submit"), ("tool-2", "job", "poll"),
        ("scope", "tool", "scope_tool"), ("scope", "tool-2", "scope_tool"), ("scope", "process", "scope_process")]]
    return doc


class IRTests(unittest.TestCase):
    def reject(self, doc):
        with self.assertRaises((ValidationError, ValueError)):
            validate_json(json.dumps(doc))

    def test_valid_profiles_round_trip(self):
        replay = resource()
        replay.update(profile="replay_trace", trace_type="replay", replay={"original_trace_ref": "source:snapshot:record", "spec_ref": "replay-spec/v1", "mode": "dependency_driven"})
        for doc in (fixture(), fixture("template_n2"), resource(), replay):
            with self.subTest(profile=doc["profile"]):
                result = validate_json(json.dumps(doc))
                self.assertEqual(validate_json(result.model_dump_json()), result)

    def test_independent_statuses_and_unassigned(self):
        doc = TraceDocument.model_validate(fixture())
        self.assertEqual(doc.runs[0].execution_status, "completed")
        self.assertEqual(doc.runs[0].evaluation_status, "failed")
        self.assertIsNone(doc.requests[0].run_id)
        self.assertIsNone(doc.events[0].interval.end_ns)

    def test_required_identity(self):
        for key in ("id", "provenance_id"):
            doc = fixture()
            del doc["runs"][0][key]
            self.reject(doc)

    def test_duplicate_ids_even_identical(self):
        doc = fixture()
        doc["runs"].append(copy.deepcopy(doc["runs"][0]))
        self.reject(doc)

    def test_unknown_fields_and_version(self):
        for changes in ({"schema_version": "9.9.0"}, {"cpu_guessed": 10}):
            self.reject(fixture() | changes)

    def test_dangling_and_wrong_type_references(self):
        for identity in ("absent", "p"):
            doc = fixture()
            doc["events"][0]["run_id"] = identity
            self.reject(doc)

    def test_containment_self_and_cycles(self):
        for group in ("agents", "events", "resource_scopes"):
            for cyclic in (False, True):
                doc = resource()
                fields = {"events": {"kind": "span", "name": "span"}, "agents": {}, "resource_scopes": {"kind": "service", "attribution_method": "shared_scope", "includes_children": True}}[group]
                doc.setdefault(group, []).extend([
                    bound("a", parent_id="b" if cyclic else "a", **fields),
                    bound("b", parent_id="a", **fields),
                ])
                self.reject(doc)

    def test_parent_bounds(self):
        doc = fixture()
        doc["events"] += [bound("parent", kind="span", name="parent", interval=interval(0, 10))]
        doc["events"][0].update(parent_id="parent", interval=interval(0, 11))
        self.reject(doc)

    def test_invalid_times(self):
        for changes in ({"end_ns": 99, "missing_reason": None}, {"end_ns": None, "missing_reason": None}, {"start_ns": True}, {"start_ns": 1.1}, {"clock_id": "missing"}):
            doc = fixture()
            doc["events"][0]["interval"].update(changes)
            self.reject(doc)

    def test_clock_calibration_metadata(self):
        doc = fixture()
        doc["clocks"][0]["utc_anchor_ns"] = 0
        self.reject(doc)
        doc["clocks"][0].update(anchor_tick_ns=0, alignment_method="synthetic", alignment_error_ns=5)
        TraceDocument.model_validate(doc)

    def test_zero_is_observed_not_missing(self):
        doc = fixture()
        doc["metrics"][0].update(value=0, evidence="observed", missing_reason=None, source_field_or_rule="measured_zero")
        self.assertEqual(TraceDocument.model_validate(doc).metrics[0].value, 0)
        for value in (None, True, "0", float("nan"), float("inf")):
            changed = copy.deepcopy(doc)
            changed["metrics"][0]["value"] = value
            self.reject(changed)

    def test_missing_metric_requires_reason(self):
        doc = fixture()
        del doc["metrics"][0]["missing_reason"]
        self.reject(doc)

    def test_evidence_propagation(self):
        for evidence in ("template_parameter", "estimated", "unavailable"):
            doc = fixture()
            base = doc["metrics"][0]
            if evidence != "unavailable":
                base.update(evidence=evidence, value=1, missing_reason=None)
            doc["metrics"].append(base | {"id": "derived", "value": 1, "evidence": "derived", "missing_reason": None, "input_metric_ids": ["latency"]})
            self.reject(doc)

    def test_metric_cycle(self):
        doc = fixture()
        doc["metrics"][0].update(value=1, missing_reason=None, evidence="derived", input_metric_ids=["latency"])
        self.reject(doc)

    def test_association_consistency(self):
        doc = fixture()
        doc["requests"][0]["run_id"] = "run"
        self.reject(doc)
        doc = fixture()
        del doc["requests"][0]["batch_id"]
        self.reject(doc)

    def test_process_identity(self):
        doc = resource()
        doc["processes"].append(doc["processes"][0] | {"id": "duplicate"})
        self.reject(doc)
        doc["processes"][1]["start_identifier"] = "start-2"
        TraceDocument.model_validate(doc)

    def test_shared_is_not_exclusive(self):
        doc = resource()
        doc["resource_scopes"][0]["attribution_method"] = "exclusive_scope"
        self.reject(doc)

    def test_counter_epoch(self):
        doc = resource()
        doc["metrics"][0].update(semantics="counter", scope_id="scope")
        self.reject(doc)
        doc["metrics"][0]["counter_epoch"] = "scope-creation-1"
        TraceDocument.model_validate(doc)

    def test_parallel_tree_and_join(self):
        doc = fixture()
        doc["events"] += [bound(x, kind="span", name=x, interval=interval(0, 10)) for x in ("root", "left", "right", "join")]
        for event in doc["events"][2:]:
            event["parent_id"] = "root"
        doc["events"][1]["interval"] = interval(0, 20)
        doc["events"][-1]["interval"] = interval(10, 20)
        assoc = {"status": "resolved", "method": "explicit_dependency", "evidence_ref": "fixture"}
        doc["links"] = [{"source_id": "join", "target_id": x, "kind": "depends_on", "association": assoc} for x in ("left", "right")]
        TraceDocument.model_validate(doc)
        invalid = copy.deepcopy(doc)
        invalid["events"][-1]["interval"] = interval(5, 20)
        self.reject(invalid)
        doc["links"].append({"source_id": "left", "target_id": "join", "kind": "depends_on", "association": assoc})
        self.reject(doc)

    def test_attempt_identity(self):
        doc = fixture()
        doc["tasks"] = [{"id": "task", "provenance_id": "p"}]
        doc["attempts"] = [{"id": f"attempt-{i}", "provenance_id": "p", "task_id": "task", "configuration_ref": f"model-{i}"} for i in range(2)]
        doc["runs"][0].update(task_id="task", attempt_id="attempt-0")
        doc["runs"].append(doc["runs"][0] | {"id": "run-2", "attempt_id": "attempt-1"})
        TraceDocument.model_validate(doc)
        doc["runs"][1]["task_id"] = None
        self.reject(doc)

    def test_replay_not_relabelled_real(self):
        doc = fixture() | {"profile": "replay_trace", "replay": {"original_trace_ref": "source", "spec_ref": "spec", "mode": "open_loop"}}
        self.reject(doc)
        self.reject(fixture() | {"trace_type": "replay"})

    def test_template_no_fake_run_or_observed_metric(self):
        doc = fixture("template_n2")
        doc["runs"] = [{"id": "run", "provenance_id": "fixture:provenance"}]
        self.reject(doc)
        doc = fixture("template_n2")
        metric = fixture()["metrics"][0] | {"provenance_id": "fixture:provenance", "scope_id": "fixture:n2", "value": 1, "evidence": "observed", "missing_reason": None}
        doc["metrics"] = [metric]
        self.reject(doc)

    def test_duplicate_json_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            validate_json('{"schema_version":"0.1.0","schema_version":"0.1.0"}')

    def test_schema_matches_models(self):
        self.assertEqual(json.loads((ROOT / "schemas/trace-ir.schema.json").read_text()), TraceDocument.model_json_schema())


class GoldTests(unittest.TestCase):
    def test_n2_hand_calculation(self):
        result = template_lengths(TraceDocument.model_validate(fixture("template_n2")).templates[0])
        self.assertEqual(result, {"evidence": "template_parameter", "unit": "source_length", "model_request_count": 3, "context_inputs": [6318, 12537, 13644], "total_input": 32499, "max_context": 13644, "total_output": 1986})

    def test_n0(self):
        doc = fixture("template_n2")
        doc["templates"][0].update(tool_use_turns=0, initial_input=32, assistant_outputs=[], tool_outputs=[], final_output=64)
        result = template_lengths(TraceDocument.model_validate(doc).templates[0])
        self.assertEqual([result[k] for k in ("model_request_count", "total_input", "total_output", "max_context")], [1, 32, 64, 32])

    def test_missing_lengths_propagate(self):
        doc = fixture("template_n2")
        doc["templates"][0]["tool_outputs"][0] = None
        doc["templates"][0]["length_missing_reason"] = "not_recorded"
        result = template_lengths(TraceDocument.model_validate(doc).templates[0])
        self.assertEqual(result["context_inputs"], [6318, None, None])
        self.assertIsNone(result["total_input"])
        self.assertIsNone(result["max_context"])
        self.assertEqual(result["total_output"], 1986)

    def test_vector_mismatch(self):
        doc = fixture("template_n2")
        doc["templates"][0]["tool_outputs"] = []
        with self.assertRaises(ValidationError):
            TraceDocument.model_validate(doc)

    def test_concurrency_work_not_wall(self):
        result = interval_totals([Interval.model_validate(interval(0, 10)), Interval.model_validate(interval(5, 15))])
        self.assertEqual(result, {"work_ns": 20, "busy_ns": 15, "overlap_ns": 5, "observed_span_ns": 15})

    def test_zero_empty_open_and_clocks(self):
        self.assertEqual(interval_totals([Interval.model_validate(interval(0, 0))])["work_ns"], 0)
        self.assertIsNone(interval_totals([])["work_ns"])
        for values in ([interval(0, None)], [interval(), interval(clock="other")]):
            with self.assertRaises(ValueError):
                interval_totals([Interval.model_validate(x) for x in values])


class ValidationCLITests(unittest.TestCase):
    run_python = skeleton.CLITests.run_python
    run_cli = skeleton.CLITests.run_cli

    def test_validate_fixture_read_only(self):
        result = self.run_cli("validate", str(FIXTURES / "semantic_open.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VALID schema=0.2.0", result.stdout)

    def test_bad_input(self):
        for path in (ROOT / "README.md", ROOT / "nonexistent.json"):
            result = self.run_cli("validate", str(path))
            self.assertEqual(result.returncode, 1)
            self.assertIn("INVALID", result.stderr)
