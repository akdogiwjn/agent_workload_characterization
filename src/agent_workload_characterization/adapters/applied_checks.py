"""Read-only, bounded-selector regression for the audited Applied Compute template."""

import hashlib
from decimal import Decimal
from pathlib import Path

from .applied_compute import AppliedComputeAdapter
from .base import Context, RawRecord, strict_object
from .catalog import Catalog, UniqueLoader
from ..ir import validate_json
import yaml


def _decimal(value) -> Decimal:
    if value is None:
        return None
    return Decimal(str(value))


def _smoke_first_line(adapter, source_id, catalog) -> dict:
    """Read first line of a single-file source, normalize, round-trip."""
    source = catalog.source(source_id)
    with source.path.open("rb") as stream:
        line = stream.readline()
    if not line:
        raise ValueError(f"{source_id}: file is empty")
    row_hash = hashlib.sha256(line).hexdigest()
    raw = strict_object(line)
    record = RawRecord("line:1", row_hash, raw)
    context = Context(source_id, "record-sha256:" + row_hash, adapter.version,
                      {"trace_type": "production_derived"})
    doc = adapter.normalize(record, context)
    if validate_json(doc.model_dump_json()) != doc:
        raise ValueError(f"{source_id}: IR round-trip mismatch")
    t = doc.templates[0]
    return {"source_id": source_id, "line_1based": 1, "row_sha256": row_hash,
            "num_turns": t.tool_use_turns, "unit": t.unit, "profile": doc.profile,
            "trace_type": doc.trace_type, "status": "PASS"}


def check_samples(catalog_path: Path, samples_path: Path) -> dict:
    catalog = Catalog(catalog_path)
    with samples_path.open(encoding="utf-8") as stream:
        selectors = yaml.load(stream, Loader=UniqueLoader)
    candidates = {item["sample_id"]: item for item in selectors["real_candidates"]
                  if item["sample_id"] in ("AC-N2",)}
    if set(candidates) != {"AC-N2"}:
        raise ValueError("AC-N2 sample selector is required")
    item = candidates["AC-N2"]
    source_id = item["source_id"]
    source = catalog.source(source_id)
    locator = item["locator"]
    if item["source_id"] != source.source_id:
        raise ValueError("sample source does not match catalog")
    location = (Path(selectors["roots"][locator["root"]]) / locator["path"]).resolve(strict=True)
    number = locator["line_1based"]
    if location != source.path or type(number) is not int or number <= 0:
        raise ValueError("invalid sample locator")

    adapter = AppliedComputeAdapter()
    results = []

    # --- AC-N2 primary gold check ---
    stat_before = source.path.stat()
    with source.path.open("rb") as stream:
        for current in range(1, number + 1):
            line = stream.readline()
            if not line:
                raise ValueError("selected sample is missing")
            if current != number:
                continue
            raw = strict_object(line)
            for field in ("input_prompt_length", "assistant_response_length", "num_turns",
                          "tool_call_latency", "tool_call_output_length", "final_assistant_response_length"):
                if raw.get(field) != item["record"][field]:
                    raise ValueError(f"selected record field changed: {field}")
            row_hash = hashlib.sha256(line).hexdigest()
            record = RawRecord(f"line:{number}", row_hash, raw)
            context = Context(source.source_id, "record-sha256:" + row_hash, adapter.version,
                              {"trace_type": "production_derived"})
            document = adapter.normalize(record, context)
            if validate_json(document.model_dump_json()) != document:
                raise ValueError("IR round-trip mismatch")
            template = document.templates[0]
            assert template.tool_use_turns == item["expected"]["model_requests"] - 1

            m = {metric.name: metric for metric in document.metrics if metric.scope_id == template.id}
            contexts = {}
            for metric in document.metrics:
                if metric.name == "completion_context" and "completion:" in metric.aggregation:
                    contexts[int(metric.aggregation.split(":")[1])] = metric.value
            actual = {
                "model_request_count": m["model_request_count"].value,
                "input_contexts": [contexts[i] for i in sorted(contexts)],
                "total_input_tokens": m["total_input_tokens"].value,
                "max_context_tokens": m["max_context_tokens"].value,
                "total_output_tokens": m["total_output_tokens"].value,
            }
            expected = item["expected"]
            mismatches = []
            if actual["model_request_count"] != expected["model_requests"]:
                mismatches.append("model_requests")
            if actual["input_contexts"] != expected["input_contexts"]:
                mismatches.append("input_contexts")
            if actual["total_input_tokens"] != expected["total_input_tokens"]:
                mismatches.append("total_input_tokens")
            if actual["max_context_tokens"] != expected["max_context_tokens"]:
                mismatches.append("max_context_tokens")
            if actual["total_output_tokens"] != expected["total_output_tokens"]:
                mismatches.append("total_output_tokens")

            expected_delay = Decimal("2.770")
            delay_total = m["total_simulated_delay"].value
            if delay_total is None or abs(_decimal(delay_total) - expected_delay) > Decimal("0.001"):
                mismatches.append("total_simulated_delay")

            results.append({
                "sample_id": "AC-N2", "line_1based": number, "row_sha256": row_hash,
                "status": "FAIL" if mismatches else "PASS",
                "mismatches": mismatches, "actual": actual,
                "profile": document.profile, "trace_type": document.trace_type,
                "unit": template.unit, "length_definition_ref": template.length_definition_ref,
            })
    stat_after = source.path.stat()
    if (stat_before.st_size, stat_before.st_mtime_ns, stat_before.st_ino) != (stat_after.st_size, stat_after.st_mtime_ns, stat_after.st_ino):
        raise ValueError("source changed while selecting samples")

    # --- Subtype structural smokes (first line, no gold expectations) ---
    for sid in ("applied_agentic_coding", "applied_code_qa", "applied_office_work"):
        try:
            smoke = _smoke_first_line(adapter, sid, catalog)
            results.append(smoke)
        except (OSError, ValueError, KeyError) as exc:
            results.append({"source_id": sid, "line_1based": 1, "status": "FAIL", "error": str(exc)})
    return {
        "task": "P0-05", "adapter_version": adapter.version,
        "status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
        "source_id": source.source_id, "source_path": str(source.path),
        "snapshot_scope": "selected raw record hash only; whole-file audit checksum not reverified",
        "parsed_records": len(results), "full_ingest": False, "results": results,
    }