"""Read-only VideoWeaver sample regression: VW-LONG main run + auxiliary incomplete."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .base import strict_object
from .catalog import Catalog, UniqueLoader
from .videoweaver import (SOURCE_ID, VERSION, compose_run, compose_unassigned_request,
                          make_provenance, parse_proxy_record)
from ..ir import validate_json
import yaml


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _jsonl_lines(path: Path):
    """Strict JSONL reader: malformed lines raise, never errors=ignore."""
    rows = []
    malformed = 0
    empty = 0
    with path.open("rb") as stream:
        for n, line in enumerate(stream, 1):
            stripped = line.strip()
            if not stripped:
                empty += 1
                continue
            try:
                rows.append({"record": strict_object(line), "ref": f"line:{n}",
                             "hash": _sha256_bytes(line)})
            except (ValueError, UnicodeError, RecursionError):
                malformed += 1
    return rows, malformed, empty


def check_samples(catalog_path: Path, samples_path: Path) -> dict:
    catalog = Catalog(catalog_path)
    with samples_path.open(encoding="utf-8") as stream:
        selectors = yaml.load(stream, Loader=UniqueLoader)

    candidates = {item["sample_id"]: item for item in selectors["real_candidates"]
                  if item["sample_id"] in ("VW-LONG",)}
    if set(candidates) != {"VW-LONG"}:
        raise ValueError("VW-LONG selector required")
    item = candidates["VW-LONG"]

    rel = item["locator"]["path"]
    benchmark_root = Path(selectors["roots"]["benchmark"])
    manifest_path = (benchmark_root / rel).resolve(strict=True)
    bundle_dir = manifest_path.parent
    # Catalog-root containment guard: manifest must live under the catalog bundle root.
    bundle_source = catalog.source("gen_videoweaver_traces")
    declared_bundle = bundle_source.path.resolve()
    if not manifest_path.is_relative_to(declared_bundle):
        raise ValueError("manifest not inside catalog bundle locator")
    # Bundle-dir containment guard: every input file we read must resolve inside the
    # selected bundle directory (a symlink to a sibling bundle must not pass).
    bundle_dir = bundle_dir.resolve()

    telemetry_source = catalog.source("telemetry_video_weaver")
    bundle_telemetry_path = bundle_dir / "model_telemetry" / "model_telemetry.jsonl"
    react_path = bundle_dir / "native_trajectory" / "original_ReAct.jsonl"
    summary_path = bundle_dir / "model_telemetry" / "model_telemetry_summary.json"

    required = [manifest_path, bundle_telemetry_path, react_path, summary_path,
                telemetry_source.path]
    for p in required:
        # Resolve the true path and require it to be contained in the selected
        # bundle dir (or the telemetry root) — a symlink pointing to a sibling
        # bundle is a real escape even if p itself is not a symlink.
        real = p.resolve()
        if p.is_symlink():
            raise ValueError(f"required input symlink not allowed: {p}")
        if not p.is_file():
            raise ValueError(f"required input missing: {p}")
        if p not in (telemetry_source.path,):
            if not real.is_relative_to(bundle_dir):
                raise ValueError(f"input resolves outside selected bundle: {p} -> {real}")
        else:
            telemetry_root = telemetry_source.path.parent.resolve()
            if not real.is_relative_to(telemetry_root):
                raise ValueError(f"telemetry input resolves outside root: {p} -> {real}")
    # Every member we will read must resolve inside the selected bundle dir.
    for sub in (bundle_dir / "native_trajectory", bundle_dir / "model_telemetry"):
        for child in sub.iterdir():
            real = child.resolve()
            if child.is_symlink() or not real.is_relative_to(bundle_dir):
                raise ValueError(f"bundle member escapes selected bundle: {child} -> {real}")

    stat_before = {p: p.stat() for p in [manifest_path, bundle_telemetry_path, react_path,
                                         telemetry_source.path]}

    manifest = json.loads(manifest_path.read_bytes())
    bundle_telemetry, bundle_malformed, bundle_empty = _jsonl_lines(bundle_telemetry_path)
    react_lines, react_malformed, react_empty = _jsonl_lines(react_path)
    raw_telemetry, raw_malformed, raw_empty = _jsonl_lines(telemetry_source.path)

    # Malformed records make the sample check non-authoritative.
    any_malformed = bundle_malformed + react_malformed + raw_malformed
    if any_malformed:
        raise ValueError(f"malformed JSON lines detected: telemetry={bundle_malformed}, react={react_malformed}, raw={raw_malformed}")

    # provenance reflects the actual files read
    p_manifest = make_provenance(SOURCE_ID, _sha256_file(manifest_path),
                                 "manifest.json", VERSION)
    p_telemetry = make_provenance(SOURCE_ID, _sha256_file(bundle_telemetry_path),
                                  "model_telemetry/model_telemetry.jsonl", VERSION)
    p_native = make_provenance(SOURCE_ID, _sha256_file(react_path),
                               "native_trajectory/original_ReAct.jsonl", VERSION)

    native_trace_id = manifest["trace_id"]
    tel_main = [e for e in bundle_telemetry if e["record"].get("trace_id") == native_trace_id]
    tel_other = [e for e in bundle_telemetry if e["record"].get("trace_id") != native_trace_id]

    doc = compose_run(manifest=manifest, telemetry=bundle_telemetry, react=react_lines,
                      provenances={"manifest": p_manifest, "telemetry": p_telemetry,
                                   "native": p_native})
    if validate_json(doc.model_dump_json()) != doc:
        raise ValueError("IR round-trip mismatch")

    run_id = doc.runs[0].id
    m = {metric.name: metric for metric in doc.metrics if metric.scope_id == run_id}
    run_level = {name: m[name] for name in
                 ("model_request_count", "total_input_tokens", "total_output_tokens",
                  "max_input_context", "max_source_context_tokens",
                  "total_api_latency_s", "tool_call_count",
                  "manifest_reported_wall_time_s", "run_elapsed", "local_cpu_time", "tool_cpu_time")}

    mismatches = []
    summary = json.loads(summary_path.read_bytes())
    expected = item.get("expected", {})

    # Gold expectations must be present in the sample selector; silently missing
    # expectations would weaken the regression, so require them explicitly.
    required_expected = ("selected_model_requests", "total_input_tokens", "total_output_tokens",
                         "max_context_tokens", "max_input_context", "manifest_wall_time_s",
                         "manifest_tool_call_count")
    missing_expected = [k for k in required_expected if k not in expected]
    if missing_expected:
        raise ValueError(f"sample candidate missing gold expectations: {missing_expected}")

    def check(name, actual, expected_value, note=""):
        if actual != expected_value:
            mismatches.append(f"{name}: actual={actual} expected={expected_value} {note}")

    check("model_request_count", run_level["model_request_count"].value, expected["selected_model_requests"],
          "manifest/summary declare; (trace_id,call_id) uniqueness verified")
    check("total_input_tokens", run_level["total_input_tokens"].value, expected["total_input_tokens"])
    check("total_output_tokens", run_level["total_output_tokens"].value, expected["total_output_tokens"])
    check("max_source_context_tokens", run_level["max_source_context_tokens"].value, expected["max_context_tokens"])
    check("manifest_reported_wall_time_s", run_level["manifest_reported_wall_time_s"].value, expected["manifest_wall_time_s"])

    # max input context is based on input_tokens, NOT source context
    actual_max_input = run_level["max_input_context"].value
    check("max_input_context", actual_max_input, expected["max_input_context"],
          "(based on input_tokens)")

    tool_events = [ev for ev in doc.events if ev.kind == "tool_call" and ev.run_id == run_id]
    check("tool_call_count", len(tool_events), expected["manifest_tool_call_count"])

    for name in ("run_elapsed", "local_cpu_time", "tool_cpu_time"):
        if run_level[name].value is not None:
            mismatches.append(f"{name}: expected unavailable but got {run_level[name].value}")

    # --- Tool orphan/dup accounting ---
    orphan_metric = m.get("orphan_tool_results")
    if orphan_metric is not None and orphan_metric.value != 0:
        mismatches.append("unexpected orphan_tool_results")

    # --- sidecar comparison: REQUIRED, FAIL when missing or mismatched ---
    sidecar_source = catalog.source("sidecar_videoweaver")
    sidecar_models_path = sidecar_source.path / "model_calls.jsonl"
    sidecar_tools_path = sidecar_source.path / "tool_calls.jsonl"
    sidecar_errors = []
    sidecar_model_rows = []
    sidecar_tool_rows = []
    if not sidecar_models_path.is_file():
        sidecar_errors.append(f"sidecar model_calls missing: {sidecar_models_path}")
    if not sidecar_tools_path.is_file():
        sidecar_errors.append(f"sidecar tool_calls missing: {sidecar_tools_path}")
    if not sidecar_errors:
        for p, rows in ((sidecar_models_path, sidecar_model_rows), (sidecar_tools_path, sidecar_tool_rows)):
            try:
                rows.extend([json.loads(line) for line in p.read_bytes().splitlines() if line.strip()])
            except Exception as exc:
                sidecar_errors.append(f"sidecar unreadable {p}: {exc}")
    if sidecar_errors:
        mismatches.extend(sidecar_errors)

    sidecar_models_vw = [r for r in sidecar_model_rows if r.get("trace_id") == native_trace_id]
    sidecar_tools_vw = [r for r in sidecar_tool_rows if r.get("trace_id") == native_trace_id]

    # request keys and values must actually match
    bundle_call_ids = set((e["record"]["trace_id"], e["record"]["call_id"]) for e in tel_main)
    sidecar_call_ids = set((r.get("trace_id"), r.get("call_id")) for r in sidecar_models_vw)
    missing_in_sidecar = bundle_call_ids - sidecar_call_ids
    extra_in_sidecar = sidecar_call_ids - bundle_call_ids
    if missing_in_sidecar:
        mismatches.append(f"bundle requests missing from sidecar: {sorted(str(k) for k in missing_in_sidecar)[:3]}")
    if extra_in_sidecar:
        mismatches.append(f"sidecar requests not in bundle: {sorted(str(k) for k in extra_in_sidecar)[:3]}")

    # key numeric comparison per request (sidecar uses _s suffix for time fields)
    sc_field_map = {"ttft": "ttft_s", "api_latency": "api_latency_s"}
    value_mismatch = 0
    for entry in tel_main:
        rec = entry["record"]
        cid = rec.get("call_id")
        side = next((r for r in sidecar_models_vw if r.get("call_id") == cid), None)
        if side is None:
            continue
        for bf, sf in [("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
                       ("context_tokens", "context_tokens"), ("ttft", "ttft_s"), ("api_latency", "api_latency_s")]:
            expected = rec.get(bf)
            actual = side.get(sf)
            if expected != actual and not (expected is None and actual is None):
                value_mismatch += 1
                break
    if value_mismatch:
        mismatches.append(f"{value_mismatch} request records differ from sidecar on token/latency fields")

    # Native tool call IDs from parsed ReAct (sidecar stores these as tool_call_id)
    native_tool_ids = set()
    for entry in react_lines:
        ev = entry["record"]
        msg = ev.get("message") if ev.get("type") == "message" else None
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "assistant":
            for it in (msg.get("content") or []):
                if isinstance(it, dict) and it.get("type") == "toolCall" and it.get("id"):
                    native_tool_ids.add(it["id"])
    our_tool_ids = set(native_tool_ids)
    sidecar_tool_ids = set(r.get("tool_call_id") for r in sidecar_tools_vw)
    missing_tools = our_tool_ids - sidecar_tool_ids
    extra_tools = sidecar_tool_ids - our_tool_ids
    if missing_tools:
        mismatches.append(f"bundle tool events missing from sidecar: {sorted(str(t) for t in missing_tools)[:3]}")
    if extra_tools:
        mismatches.append(f"sidecar tool ids not in bundle: {sorted(str(t) for t in extra_tools)[:3]}")
    if not sidecar_tool_ids and not our_tool_ids:
        mismatches.append("both bundle and sidecar have zero tool events")

    sidecar_info = {
        "bundle_request_keys": len(bundle_call_ids),
        "sidecar_request_keys": len(sidecar_call_ids),
        "missing_from_sidecar": len(missing_in_sidecar),
        "extra_in_sidecar": len(extra_in_sidecar),
        "value_mismatch_records": value_mismatch,
        "bundle_tool_ids": len(our_tool_ids),
        "sidecar_tool_ids": len(sidecar_tool_ids),
        "missing_tools": len(missing_tools),
        "extra_tools": len(extra_tools),
    }

    # --- auxiliary incomplete request from raw telemetry ---
    aux_trace = "videoweaver:reference_image_video:UniVBench-R2V:run-003"
    aux_call = "b6c324adb8dd40179883ecead5cb4262"
    aux_raw = None
    aux_line = None
    aux_hash = None
    for e in raw_telemetry:
        r = e["record"]
        if r.get("trace_id") == aux_trace and r.get("call_id") == aux_call:
            aux_raw, aux_line, aux_hash = r, e["ref"], e["hash"]
            break
    aux_checks = []
    if aux_raw is None:
        aux_checks.append("auxiliary request not found in raw telemetry")
        aux_result = {"sample_id": "AUX-INCOMPLETE", "status": "FAIL", "error": aux_checks}
    else:
        aux_prov = make_provenance("telemetry_video_weaver", _sha256_file(telemetry_source.path),
                                   f"video_weaver.jsonl;{aux_line}", VERSION)
        aux_doc = compose_unassigned_request(source_id="telemetry_video_weaver",
                                             raw_record=aux_raw, provenance=aux_prov)
        if validate_json(aux_doc.model_dump_json()) != aux_doc:
            raise ValueError("aux IR round-trip mismatch")
        aux_metrics = {m.name: m for m in aux_doc.metrics}
        if aux_metrics["input_tokens"].value is not None:
            aux_checks.append("input_tokens expected null")
        if aux_metrics["output_tokens"].value is not None:
            aux_checks.append("output_tokens expected null")
        if aux_doc.requests[0].run_id is not None:
            aux_checks.append("run_id expected null")
        if aux_doc.requests[0].association.status != "unresolved":
            aux_checks.append("expected unresolved")
        aux_result = {"sample_id": "AUX-INCOMPLETE", "status": "FAIL" if aux_checks else "PASS",
                      "trace_id": aux_trace, "call_id": aux_call, "line": aux_line,
                      "row_hash": aux_hash, "input_tokens_raw": aux_raw.get("input_tokens"),
                      "output_tokens_raw": aux_raw.get("output_tokens"),
                      "ttft": aux_raw.get("ttft"), "api_latency": aux_raw.get("api_latency"),
                      "http_status": aux_raw.get("http_status"),
                      "normalized_input": aux_metrics["input_tokens"].value,
                      "normalized_output": aux_metrics["output_tokens"].value,
                      "mismatches": aux_checks}

    # --- accounting (physical / selected / other / malformed / dedup) ---
    accounting = {
        "physical_lines_bundle_telemetry": len(bundle_telemetry) + bundle_malformed + bundle_empty,
        "selected_bundle_main_requests": len(tel_main),
        "other_trace_bundle_records": len(tel_other),
        "malformed_bundle_telemetry": bundle_malformed,
        "malformed_react": react_malformed,
        "malformed_raw_telemetry": raw_malformed,
        "empty_lines_bundle_telemetry": bundle_empty,
        "empty_lines_react": react_empty,
        "empty_lines_raw_telemetry": raw_empty,
        "physical_lines_raw_telemetry": len(raw_telemetry) + raw_malformed + raw_empty,
    }

    # --- stat unchanged check ---
    for p in [manifest_path, bundle_telemetry_path, react_path, telemetry_source.path]:
        after = p.stat()
        before = stat_before[p]
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f"source changed: {p}")

    main_result = {
        "sample_id": "VW-LONG", "status": "FAIL" if mismatches else "PASS",
        "trace_id": native_trace_id,
        "run_metrics": {name: {"value": v.value, "evidence": v.evidence, "missing_reason": v.missing_reason}
                        for name, v in run_level.items()},
        "note_max_input_vs_context": (
            f"max(input_tokens)={run_level['max_input_context'].value} differs from "
            f"max(context_tokens)={run_level['max_source_context_tokens'].value}; context_tokens "
            f"in this proxy = input+output, not a separate input context metric"),
        "mismatches": mismatches,
        "sidecar_comparison": sidecar_info,
        "manifest": {"generation_status": manifest.get("generation_status"),
                     "pipeline_reported_status": manifest.get("pipeline_reported_status")},
    }

    overall = "FAIL" if (mismatches or main_result["status"] == "FAIL"
                         or aux_result["status"] == "FAIL") else "PASS"
    now_utc = datetime.now(timezone.utc).isoformat()
    return {
        "task": "P0-10", "adapter_version": VERSION, "checked_at_utc": now_utc,
        "status": overall,
        "snapshot_scope": "selected bundle + raw telemetry files; hashes per input; not a whole-source claim",
        "parsed_records": 2, "full_ingest": False,
        "accounting": accounting,
        "files_checked": {
            "manifest": {"path": str(manifest_path), "sha256": p_manifest["snapshot_id"]},
            "bundle_telemetry": {"path": str(bundle_telemetry_path), "sha256": p_telemetry["snapshot_id"]},
            "react": {"path": str(react_path), "sha256": p_native["snapshot_id"]},
            "telemetry_summary": {"path": str(summary_path), "sha256": _sha256_file(summary_path)},
            "telemetry_raw": {"path": str(telemetry_source.path), "sha256": _sha256_file(telemetry_source.path)},
            "sidecar_models": {"path": str(sidecar_models_path), "sha256": _sha256_file(sidecar_models_path) if sidecar_models_path.is_file() else None},
            "sidecar_tools": {"path": str(sidecar_tools_path), "sha256": _sha256_file(sidecar_tools_path) if sidecar_tools_path.is_file() else None},
        },
        "results": [main_result, aux_result],
    }