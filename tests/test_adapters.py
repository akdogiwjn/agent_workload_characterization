"""P0-03 synthetic integration tests; all writes stay in private temp projects."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from agent_workload_characterization.adapters import Adapter, Catalog, RecordError, ingest, stable_id
from agent_workload_characterization.adapters.base import jsonl_records
from agent_workload_characterization.adapters.catalog import CatalogError
from agent_workload_characterization.adapters.ingest import file_hash, output_guard
from agent_workload_characterization.ir import TraceDocument, validate_json
import test_skeleton as skeleton


class SyntheticAdapter(Adapter):
    name = "synthetic-contract"
    version = "1"

    def normalize(self, record, context):
        raw = record.value
        if raw.get("reject"):
            raise RecordError("sensitive raw payload must not appear in reject report")
        if raw.get("crash"):
            raise RuntimeError("unexpected implementation failure")
        if "native_id" not in raw:
            raise RecordError("missing semantic source key")
        identity = stable_id(context.source_id, "run", raw["native_id"], raw.get("model", "m"), raw.get("attempt", "0"))
        provenance = stable_id(context.source_id, "provenance", identity)
        doc = TraceDocument.model_validate({
            "schema_version": "0.2.0", "profile": "semantic_trace", "trace_type": "synthetic",
            "provenance": [{"id": provenance, "source_id": context.source_id,
                            "snapshot_id": context.snapshot_id, "source_record_ref": record.source_record_ref,
                            "adapter_version": context.adapter_version}],
            "runs": [{"id": identity, "provenance_id": provenance, "execution_status": raw.get("execution_status", "unknown")}],
        })
        if raw.get("bad_ir"):
            doc.runs[0].provenance_id = "absent"
        if raw.get("bad_lineage"):
            doc.provenance[0].source_record_ref = "not-the-current-record"
        return doc


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="awc-adapter-test-")
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.project = base / "project"
        self.legacy = base / "legacy"
        self.project.mkdir()
        self.legacy.mkdir()
        self.input = self.legacy / "trace.jsonl"
        self.input.write_text('{"native_id":"a"}\n', encoding="utf-8")
        self.catalog_path = self.project / "sources.yaml"
        self.catalog_data = {"catalog_version": "1.1", "roots": {"benchmark": str(self.legacy), "project": str(self.project)},
                             "sources": [{"source_id": "synthetic", "locator": {"root": "benchmark", "path": "trace.jsonl", "kind": "file"}}]}
        self.write_catalog()

    def write_catalog(self):
        self.catalog_path.write_text(yaml.safe_dump(self.catalog_data), encoding="utf-8")
        self.catalog = Catalog(self.catalog_path)

    def write_records(self, records):
        self.input.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    def ingest(self, adapter=None, **kwargs):
        return ingest(adapter or SyntheticAdapter(), self.catalog, "synthetic", self.project, **kwargs)

    def rows(self, batch, name):
        return [json.loads(line) for line in (Path(batch["path"]) / name).read_text().splitlines()]

    def test_catalog_inspection_and_discovery(self):
        info = self.catalog.inspect("synthetic")
        self.assertEqual(info["status"], "exists")
        self.assertEqual(SyntheticAdapter().discover(self.catalog.source("synthetic")), (self.input,))
        self.assertEqual(SyntheticAdapter().inspect(self.catalog.source("synthetic"))["adapter_version"], "1")

    def test_catalog_duplicate_source(self):
        self.catalog_data["sources"].append(copy.deepcopy(self.catalog_data["sources"][0]))
        with self.assertRaises(CatalogError):
            self.write_catalog()

    def test_catalog_rejects_unsafe_yaml_and_duplicate_keys(self):
        for payload in ("a: 1\na: 2\n", "!!python/object/apply:os.system ['echo forbidden']"):
            self.catalog_path.write_text(payload)
            with self.assertRaises(CatalogError):
                Catalog(self.catalog_path)

    def test_locator_escape_and_unknown_root(self):
        for locator in ({"root": "benchmark", "path": "../escape", "kind": "file"},
                        {"root": "unknown", "path": "trace.jsonl", "kind": "file"}):
            self.catalog_data["sources"][0]["locator"] = locator
            with self.assertRaises(CatalogError):
                self.write_catalog()

    def test_locator_symlink_escape(self):
        (self.legacy / "escape").symlink_to(self.project, target_is_directory=True)
        self.catalog_data["sources"][0]["locator"]["path"] = "escape/file.jsonl"
        with self.assertRaises(CatalogError):
            self.write_catalog()

    def test_missing_and_kind_mismatch(self):
        self.catalog_data["sources"][0]["locator"]["path"] = "missing.jsonl"
        self.write_catalog()
        self.assertEqual(self.catalog.inspect("synthetic")["status"], "missing")
        self.catalog_data["sources"][0]["locator"].update(path=".", kind="file")
        self.write_catalog()
        self.assertEqual(self.catalog.inspect("synthetic")["status"], "kind_mismatch")

    def test_stable_identity_not_task_only(self):
        self.assertEqual(stable_id("s", "run", "task", "m1", "0"), stable_id("s", "run", "task", "m1", "0"))
        self.assertNotEqual(stable_id("s", "run", "task", "m1", "0"), stable_id("s", "run", "task", "m2", "0"))
        self.assertNotEqual(stable_id("s", "run", "ab", "c"), stable_id("s", "run", "a", "bc"))
        with self.assertRaises(ValueError):
            stable_id("s", "run", "")

    def test_jsonl_invalid_lines_are_not_skipped(self):
        self.input.write_bytes(b'{"a":1}\n\n[1]\n{"a":1,"a":2}\n{"a":NaN}\n\xff\n{"a":1e309}\n{"a":2}\n')
        records = list(jsonl_records(self.input))
        self.assertEqual(len(records), 8)
        self.assertEqual(sum(r.error is not None for r in records), 6)
        self.assertEqual(records[-1].source_record_ref, "line:8")
        self.assertEqual(records[-1].value, {"a": 2})

    def test_oversized_line_drained_without_losing_next(self):
        self.input.write_bytes(b"x" * 100 + b'\n{"a":1}\n')
        records = list(jsonl_records(self.input, max_record_bytes=10))
        self.assertEqual([r.error for r in records], ["record_too_large", None])
        self.assertEqual(records[-1].source_record_ref, "line:2")

    def test_round_trip_lineage_and_immutable_reuse(self):
        source_before = (file_hash(self.input), self.input.stat().st_mtime_ns)
        first = self.ingest()
        row = self.rows(first, "documents.jsonl")[0]
        doc = validate_json(json.dumps(row["trace"]))
        self.assertEqual(doc.provenance[0].source_record_ref, "line:1")
        self.assertEqual(doc.provenance[0].snapshot_id, "sha256:" + source_before[0])
        before = {p.name: (file_hash(p), p.stat().st_mtime_ns) for p in Path(first["path"]).iterdir()}
        second = self.ingest()
        after = {p.name: (file_hash(p), p.stat().st_mtime_ns) for p in Path(first["path"]).iterdir()}
        self.assertTrue(second["reused"])
        self.assertEqual(before, after)
        self.assertEqual(second["counts"]["runs"], 1)
        self.assertEqual(source_before, (file_hash(self.input), self.input.stat().st_mtime_ns))

    def test_duplicate_records_and_distinct_models(self):
        self.write_records([{"native_id": "same-task", "model": "m1"}, {"native_id": "same-task", "model": "m2"}, {"native_id": "same-task", "model": "m1"}])
        batch = self.ingest()
        self.assertEqual(batch["counts"], {"seen": 3, "accepted": 2, "duplicates": 1, "rejected": 0, "runs": 2})
        ledger = self.rows(batch, "records.jsonl")
        self.assertEqual([r["source_record_ref"] for r in ledger], ["line:1", "line:2", "line:3"])
        self.assertEqual(ledger[0]["document_id"], ledger[2]["document_id"])

    def test_conflicting_identity_quarantined(self):
        self.write_records([{"native_id": "a"}, {"native_id": "a", "execution_status": "failed"}, {"native_id": "b"}])
        batch = self.ingest()
        self.assertEqual(batch["counts"]["accepted"], 2)
        self.assertEqual(batch["counts"]["rejected"], 1)
        self.assertEqual(self.rows(batch, "rejects.jsonl")[0]["reason"], "identity_conflict")
        manifest = json.loads((Path(batch["path"]) / "manifest.json").read_text())
        self.assertEqual(manifest["quality_status"], "has_rejects")

    def test_bad_ir_lineage_and_expected_error_isolation(self):
        self.write_records([{"native_id": "a", "bad_ir": True}, {"native_id": "b", "bad_lineage": True}, {"native_id": "c", "reject": True}, {"native_id": "d"}])
        batch = self.ingest()
        self.assertEqual(batch["counts"]["rejected"], 3)
        self.assertEqual(batch["counts"]["accepted"], 1)
        self.assertNotIn("sensitive raw", (Path(batch["path"]) / "rejects.jsonl").read_text())

    def test_parse_errors_in_batch_conservation(self):
        self.input.write_bytes(b'not-json\n{"native_id":"a"}\n\n')
        batch = self.ingest()
        self.assertEqual(batch["counts"], {"seen": 3, "accepted": 1, "duplicates": 0, "rejected": 2, "runs": 1})
        self.assertEqual(len(self.rows(batch, "rejects.jsonl")), 2)

    def test_unexpected_failure_leaves_incomplete_not_success(self):
        self.write_records([{"native_id": "a"}, {"native_id": "b", "crash": True}])
        with self.assertRaises(RuntimeError):
            self.ingest()
        batches = list((self.project / "data/normalized").iterdir())
        self.assertEqual(len(batches), 1)
        self.assertFalse((batches[0] / "manifest.json").exists())
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.ingest()

    def test_changed_source_does_not_publish(self):
        source = self.input

        class ChangingAdapter(SyntheticAdapter):
            def records(self, path):
                yield from super().records(path)
                with source.open("ab") as stream:
                    stream.write(b"\n")

        with self.assertRaisesRegex(ValueError, "source changed"):
            self.ingest(ChangingAdapter())
        self.assertFalse(any((self.project / "data/normalized").glob("*/manifest.json")))

    def test_corrupted_batch_refused_not_overwritten(self):
        batch = self.ingest()
        output = Path(batch["path"]) / "documents.jsonl"
        output.write_text("tampered")
        with self.assertRaisesRegex(ValueError, "content changed"):
            self.ingest()
        self.assertEqual(output.read_text(), "tampered")

    def test_new_config_new_batch_same_run_identity(self):
        for invalid in ([], False, "config"):
            with self.assertRaises(ValueError):
                self.ingest(config=invalid)
        first = self.ingest(config={"mode": "a"})
        second = self.ingest(config={"mode": "b"})
        self.assertNotEqual(first["batch_id"], second["batch_id"])
        self.assertEqual(self.rows(first, "documents.jsonl")[0]["trace"]["runs"][0]["id"], self.rows(second, "documents.jsonl")[0]["trace"]["runs"][0]["id"])

    def test_source_move_keeps_ids(self):
        first = self.ingest()
        moved = self.legacy / "moved.jsonl"
        moved.write_bytes(self.input.read_bytes())
        self.catalog_data["sources"][0]["locator"]["path"] = "moved.jsonl"
        self.write_catalog()
        second = self.ingest()
        self.assertEqual(self.rows(first, "documents.jsonl")[0]["document_id"], self.rows(second, "documents.jsonl")[0]["document_id"])

    def test_direct_legacy_and_outside_outputs_refused(self):
        for output in (self.legacy, self.legacy / "new-batch", self.project, self.input):
            with self.assertRaises(ValueError):
                self.ingest(output=output)
        self.assertEqual(list(self.legacy.iterdir()), [self.input])

    def test_output_symlink_into_legacy_refused(self):
        normalized = self.project / "data/normalized"
        normalized.mkdir(parents=True)
        (normalized / "alias").symlink_to(self.legacy, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.ingest(output=normalized / "alias/new-batch")
        self.assertFalse((self.legacy / "new-batch").exists())

    def test_normalized_root_symlink_refused(self):
        (self.project / "data").mkdir()
        (self.project / "data/normalized").symlink_to(self.legacy, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.ingest()

    def test_input_output_overlap_inside_project(self):
        normalized = self.project / "data/normalized"
        with self.assertRaises(ValueError):
            output_guard(self.project, normalized / "input/new", (normalized / "input",))
        with self.assertRaises(ValueError):
            output_guard(self.project, normalized, (normalized / "input/file",))

    def test_default_directory_adapter_refused(self):
        self.catalog_data["sources"][0]["locator"].update(path=".", kind="directory")
        self.write_catalog()
        with self.assertRaises(ValueError):
            self.ingest()
        self.assertFalse((self.project / "data").exists())


class InspectCLITests(unittest.TestCase):
    run_python = skeleton.CLITests.run_python
    run_cli = skeleton.CLITests.run_cli

    def test_fixture_catalog_locator_stat_only(self):
        with tempfile.TemporaryDirectory(prefix="awc-inspect-test-") as temporary:
            root = Path(temporary)
            (root / "source.jsonl").write_text("not JSON: inspect must only stat this file")
            catalog = root / "catalog.yaml"
            catalog.write_text(yaml.safe_dump({"catalog_version": "1.1", "roots": {"fixture": temporary},
                                              "sources": [{"source_id": "fixture", "locator": {"root": "fixture", "path": "source.jsonl", "kind": "file"}}]}))
            result = self.run_cli("inspect-source", "fixture", "--catalog", str(catalog))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["actual_kind"], "file")

    def test_unknown_source_fails(self):
        result = self.run_cli("inspect-source", "does-not-exist", "--catalog", str(skeleton.ROOT / "data/catalog/sources.yaml"))
        self.assertEqual(result.returncode, 1)
