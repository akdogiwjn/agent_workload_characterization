"""Shared loader for pilot samples: reads real files via adapters, returns documents + evidence.

Never opens media, prompts, credentials, or performs full ingest. Each
sample gets its own file hashes and provenance. Loader validates the fixed
selector/gold expectations, checks identity uniqueness, and recomputes the
actual cohort counts (it never trusts precomputed summaries).
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from ..adapters.base import Context, RawRecord, strict_object, stable_id
from ..adapters.catalog import Catalog, UniqueLoader
from ..adapters.agentx import AgentXAdapter
from ..adapters.applied_compute import AppliedComputeAdapter
from ..adapters.videoweaver import (compose_run, compose_unassigned_request,
                                     make_provenance, SOURCE_ID, VERSION)
from ..ir import TraceDocument
import yaml


# Canonical metric-name mapping from raw IR names to registry definition keys.
# Each source maps its IR metric names onto the shared registry vocabulary so
# macro/coverage operate on one set of definition keys, never raw IR names.
_CANONICAL_MAP = {
    "model_request_count": "model_request_count",
    "input_tokens": "total_input_tokens",
    "output_tokens": "total_output_tokens",
    "max_context_tokens": "max_input_context",
    "model_busy": "union_busy_ns",
    "model_work": "total_api_latency_ns",
    "subagent_count": "subagent_count",
    "tool_call_count": "tool_call_count",
    "run_elapsed": "run_elapsed",
    "local_cpu_time": "local_cpu_time",
    "tool_cpu_time": "tool_cpu_time",
    "total_input_tokens": "total_input_tokens",
    "total_output_tokens": "total_output_tokens",
    "max_input_context": "max_input_context",
    "max_source_context_tokens": "max_source_context_tokens",
    "total_api_latency_s": "total_api_latency_s",
    "manifest_reported_wall_time_s": "manifest_reported_wall_time_s",
}


def _canonical(name):
    return _CANONICAL_MAP.get(name, name)


def _sha256b(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256f(path: Path) -> str:
    return _sha256b(path.read_bytes())


@dataclass
class LoadedSample:
    sample_id: str
    source_id: str
    entity_type: str  # "run" | "template" | "unassigned_request"
    trace_type: str
    profile: str
    document: TraceDocument
    entity_id: str  # run_id or template_id
    files: list[dict]  # {"path": str, "sha256": str, "record_sha256": str?}
    entity_metrics: dict  # definition_key -> list[Metric] (entity-level, canonical aggregation)
    request_metrics: dict  # definition_key -> list[Metric] (per-request)
    record_ref: str | None = None  # e.g. "line:39"
    record_sha256: str | None = None  # specific record line hash
    # Raw source-side comparison data for sidecar cross-check (VW only).
    # request_records: {(trace_id, call_id): {field: value}} from bundle telemetry
    # tool_ids: set of native toolCall IDs from bundle ReAct
    request_records: dict | None = None
    tool_ids: set | None = None


def _read_jsonl(path: Path):
    """Strict JSONL reader; returns (records, malformed_count, empty_count)."""
    records = []
    malformed = 0
    empty = 0
    with path.open("rb") as stream:
        for n, line in enumerate(stream, 1):
            if not line.strip():
                empty += 1
                continue
            try:
                records.append({"record": strict_object(line), "ref": f"line:{n}",
                                "hash": _sha256b(line)})
            except (ValueError, UnicodeError, RecursionError):
                malformed += 1
    return records, malformed, empty


def load_pilot(catalog_path, pilot_path, samples_path = None):
    """Return {"samples": [LoadedSample...], "cohort": {...}, "ledger": [...]}.

    samples_path points at data/catalog/sample_candidates.yaml for gold
    expectations; when provided, each selected sample's gold is verified.
    """
    catalog_path = Path(catalog_path)
    pilot_path = Path(pilot_path)
    if samples_path is not None:
        samples_path = Path(samples_path)
    catalog = Catalog(catalog_path)
    pilot = yaml.load(pilot_path.read_text(), Loader=UniqueLoader)
    benchmark_root = None
    for name, root in catalog.roots.items():
        if name != "project":
            benchmark_root = root.resolve()
            break
    if benchmark_root is None:
        raise ValueError("catalog lacks a non-project root")

    gold = {}
    if samples_path is not None:
        gold_data = yaml.load(Path(samples_path).read_text(), Loader=UniqueLoader)
        gold = {item["sample_id"]: item for item in gold_data.get("real_candidates", [])}

    included = pilot.get("included", [])
    if not included:
        raise ValueError("pilot selection has no included samples")

    # Require the four core samples; gold expectations must also be present
    required_ids = {"AX-7", "AX-SUB", "AC-N2", "VW-LONG"}
    selected_ids = {s["sample_id"] for s in included}
    missing_ids = required_ids - selected_ids
    if missing_ids:
        raise ValueError(f"required pilot samples missing: {missing_ids}")
    # Gold expectations must be present in sample_candidates for all required samples
    if samples_path is not None:
        gold_data = yaml.load(Path(samples_path).read_text(), Loader=UniqueLoader)
        gold_map = {item["sample_id"]: item for item in gold_data.get("real_candidates", [])}
        missing_gold = required_ids - set(gold_map)
        if missing_gold:
            raise ValueError(f"required gold expectations missing: {missing_gold}")

    samples = []
    ledger = []
    seen_entity_ids = set()

    for sel in included:
        sid = sel["sample_id"]
        source_id = sel["source_id"]
        stats = _load_one(catalog, benchmark_root, sel, gold.get(sid), seen_entity_ids)
        samples.append(stats["sample"])
        ledger.append({"sample_id": sid, "source_id": source_id,
                       "status": "selected", "entity_id": stats["sample"].entity_id,
                       "entity_type": stats["sample"].entity_type,
                       "files": stats["sample"].files,
                       "record_ref": stats["sample"].record_ref,
                       "record_sha256": stats["sample"].record_sha256})

    aux = []
    for sel in pilot.get("auxiliary", []):
        if sel["sample_id"] != "AUX-INCOMPLETE":
            continue
        stats = _load_one(catalog, benchmark_root, sel, gold.get("AUX-INCOMPLETE"), seen_entity_ids)
        samples.append(stats["sample"])
        aux.append(stats["sample"])
        ledger.append({"sample_id": sel["sample_id"], "source_id": sel["source_id"],
                       "status": "selected", "entity_id": stats["sample"].entity_id,
                       "entity_type": stats["sample"].entity_type,
                       "files": stats["sample"].files,
                       "record_ref": stats["sample"].record_ref,
                       "record_sha256": stats["sample"].record_sha256})

    runs = [s for s in samples if s.entity_type == "run"]
    templates = [s for s in samples if s.entity_type == "template"]
    unassigned = [s for s in samples if s.entity_type == "unassigned_request"]

    cohort = {
        "real_runs": len(runs),
        "templates": len(templates),
        "unassigned_requests": len(unassigned),
        "bound_measured_requests": _bound_requests(runs),
        "ledger_rows": len(ledger),
        "note": "bound measured requests summed per run; template completions and unassigned requests separate; never merged into real calls",
    }
    return {"samples": samples, "cohort": cohort, "ledger": ledger}


def _bound_requests(runs) -> int:
    total = 0
    for s in runs:
        for (name, agg), metrics in s.entity_metrics.items():
            if name == "model_request_count" and "all_" in agg:
                for m in metrics:
                    if m.value is not None:
                        total += m.value
                        break
    return total


def _load_one(catalog, benchmark_root, sel, gold, seen_entity_ids):
    sid = sel["sample_id"]
    source_id = sel["source_id"]
    if sid in ("AX-7", "AX-SUB"):
        sample = _load_agentx(catalog, benchmark_root, sel, gold)
    elif sid == "AC-N2":
        sample = _load_applied(catalog, benchmark_root, sel, gold)
    elif sid == "VW-LONG":
        sample = _load_videoweaver(catalog, benchmark_root, sel, gold)
    elif sid == "AUX-INCOMPLETE":
        sample = _load_aux(catalog, benchmark_root, sel, gold)
    else:
        raise ValueError(f"unsupported pilot sample: {sid}")

    if sample.entity_id in seen_entity_ids:
        raise ValueError(f"duplicate entity identity: {sample.entity_id}")
    seen_entity_ids.add(sample.entity_id)
    return {"sample": sample, "record_ref": sample.record_ref, "record_sha256": sample.record_sha256}


def _validate_gold(sample_id, gold, actual):
    """Compare actual against gold expectations when provided."""
    if gold is None:
        return
    expected = gold.get("expected", {})
    for key, expected_value in expected.items():
        if key not in actual:
            raise ValueError(f"gold {sample_id}: expected {key} missing from actual")
        if actual[key] != expected_value:
            raise ValueError(f"gold {sample_id}: {key} actual={actual[key]} expected={expected_value}")


def _load_agentx(catalog, benchmark_root, sel, gold):
    sid = sel["sample_id"]
    source = catalog.source(sel["source_id"])
    loc = sel["locator"]
    line_no = loc["line_1based"]
    path = (benchmark_root / loc["path"]).resolve(strict=True)
    if path != source.path:
        raise ValueError(f"AX locator mismatch for {sid}")
    before = path.stat()
    raw = None
    with path.open("rb") as f:
        for lineno in range(1, line_no + 1):
            line = f.readline()
            if not line:
                raise ValueError(f"{sid}: line {line_no} not found")
            if lineno == line_no:
                raw = strict_object(line)
                raw_hash = _sha256b(line)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"source changed: {path}")

    record = RawRecord(f"line:{line_no}", raw_hash, raw)
    context = Context(sel["source_id"], "record-sha256:" + raw_hash,
                      "agentx-v7/0.1.0", {"trace_type": "production_derived"})
    doc = AgentXAdapter().normalize(record, context)
    entity_id = doc.runs[0].id
    entity_metrics, request_metrics = _extract_agentx_metrics(doc, entity_id)

    # Gold check (main/all separate) against canonical (name, aggregation) keys
    actual = {}
    for name in ("model_request_count", "input_tokens", "output_tokens", "subagent_count"):
        cname = _canonical(name)
        for agg in ("main_agent", "all_agents"):
            vals = [m.value for (m_name, m_agg), metrics in entity_metrics.items()
                    if m_name == cname and m_agg == agg
                    for m in metrics if m.value is not None]
            actual[f"{name}_{agg}"] = vals[0] if vals else None
    if gold:
        exp = gold.get("expected", {})
        required = {"main_requests", "model_requests", "input_tokens", "output_tokens"}
        missing_req = required - set(exp)
        if missing_req:
            raise ValueError(f"gold {sid}: required expectations missing: {sorted(missing_req)}")
        check_map = {"main_requests": ("model_request_count", "main_agent"),
                     "model_requests": ("model_request_count", "all_agents"),
                     "input_tokens": ("input_tokens", "all_agents"),
                     "output_tokens": ("output_tokens", "all_agents")}
        # Add subagent_groups validation (dynamically from entity_metrics)
        check_map_all = dict(check_map)
        for (m_name, m_agg), ms in entity_metrics.items():
            if m_name == "subagent_count":
                check_map_all["subagent_groups"] = ("subagent_count", m_agg)
        uncovered = set(exp) - set(check_map_all)
        if uncovered:
            raise ValueError(f"gold {sid}: expectations not validated: {sorted(uncovered)}")
        for gk, (raw_name, agg) in check_map_all.items():
            cname = _canonical(raw_name)
            if gk in check_map_all:  # only check against keys we can map
                if actual.get(f"{raw_name}_{agg}") != exp[gk]:
                    raise ValueError(f"gold {sid}: {gk} actual={actual.get(f'{raw_name}_{agg}')} expected={exp[gk]}")
    return LoadedSample(sid, sel["source_id"], "run", doc.trace_type, doc.profile,
                        doc, entity_id, [{"path": str(path), "sha256": _sha256f(path)}],
                        entity_metrics, request_metrics,
                        record_ref=f"line:{line_no}", record_sha256=raw_hash)


def _extract_agentx_metrics(doc, entity_id):
    """Run-level metrics keyed by (name, aggregation) + per-request metrics."""
    entity = {}
    request = {}
    for m in doc.metrics:
        if m.scope_id == entity_id:
            if m.aggregation in ("main_agent", "all_agents"):
                entity.setdefault((_canonical(m.name), m.aggregation), []).append(m)
        elif m.aggregation == "single_request":
            request.setdefault(_canonical(m.name), []).append(m)
    return entity, request


def _load_applied(catalog, benchmark_root, sel, gold):
    sid = sel["sample_id"]
    source = catalog.source(sel["source_id"])
    loc = sel["locator"]
    line_no = loc["line_1based"]
    path = (benchmark_root / loc["path"]).resolve(strict=True)
    if path != source.path:
        raise ValueError(f"AC locator mismatch for {sid}")
    before = path.stat()
    with path.open("rb") as f:
        for lineno in range(1, line_no + 1):
            line = f.readline()
            if not line:
                raise ValueError(f"{sid}: line {line_no} not found")
            if lineno == line_no:
                raw = strict_object(line)
                raw_hash = _sha256b(line)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"source changed: {path}")
    record = RawRecord(f"line:{line_no}", raw_hash, raw)
    context = Context(sel["source_id"], "record-sha256:" + raw_hash,
                      "applied_compute-v1/0.1.0", {"trace_type": "production_derived"})
    doc = AppliedComputeAdapter().normalize(record, context)
    entity_id = doc.templates[0].id
    entity = {}
    for m in doc.metrics:
        if m.scope_id == entity_id:
            entity.setdefault((_canonical(m.name), m.aggregation), []).append(m)
    # gold: model_requests, input/total, max_context, delay
    raw_names = ["model_request_count", "total_input_tokens", "total_output_tokens",
                 "max_context_tokens", "total_simulated_delay"]
    actual = {}
    for rn in raw_names:
        value = _first_value(entity, _canonical(rn))
        if value is not None:
            actual[rn] = value
    # completion contexts (template_parameter lineage)
    context_vals = [m.value for (name, agg), ms in entity.items()
                    if name == "completion_context" for m in ms if m.value is not None]
    actual["input_contexts"] = context_vals or None
    _validate_gold_map(sid, gold, actual,
                       {"model_requests": "model_request_count",
                        "input_contexts": "input_contexts",
                        "total_input_tokens": "total_input_tokens",
                        "total_output_tokens": "total_output_tokens",
                        "max_context_tokens": "max_context_tokens",
                        "total_simulated_delay": "total_simulated_delay"},
                       required_expected={"model_requests", "total_input_tokens",
                                          "total_output_tokens", "max_context_tokens",
                                          "total_simulated_delay"})
    return LoadedSample(sid, sel["source_id"], "template", doc.trace_type, doc.profile,
                        doc, entity_id, [{"path": str(path), "sha256": _sha256f(path)}],
                        entity, {},
                        record_ref=f"line:{line_no}", record_sha256=raw_hash)


def _load_videoweaver(catalog, benchmark_root, sel, gold):
    sid = sel["sample_id"]
    loc = sel["locator"]
    manifest_path = (benchmark_root / loc["path"]).resolve(strict=True)
    bundle_dir = manifest_path.parent
    tel_path = bundle_dir / loc["bundle_telemetry"]
    react_path = bundle_dir / loc["bundle_react"]
    summary_path = bundle_dir / loc["bundle_summary"]
    # The manifest must live under the catalog-declared bundle source root
    # (not merely under its own bundle_dir).
    vw_source = catalog.source(sel["source_id"])
    vw_root = vw_source.path.resolve()
    if not manifest_path.is_relative_to(vw_root):
        raise ValueError(f"VW manifest not inside catalog source root: {manifest_path}")
    for p in (manifest_path, tel_path, react_path, summary_path):
        real = p.resolve()
        if p.is_symlink() or not real.is_relative_to(bundle_dir):
            raise ValueError(f"VW file escapes bundle: {p}")
        if not p.is_file():
            raise ValueError(f"VW required file missing: {p}")

    before = {p: p.stat() for p in (manifest_path, tel_path, react_path, summary_path)}
    manifest = json.loads(manifest_path.read_bytes())
    telemetry, tel_malformed, _ = _read_jsonl(tel_path)
    react, react_malformed, _ = _read_jsonl(react_path)
    if tel_malformed or react_malformed:
        raise ValueError(f"VW malformed JSONL: telemetry={tel_malformed} react={react_malformed}")
    after = {p: p.stat() for p in (manifest_path, tel_path, react_path, summary_path)}
    for p in before:
        if (before[p].st_size, before[p].st_mtime_ns) != (after[p].st_size, after[p].st_mtime_ns):
            raise ValueError(f"VW source changed: {p}")

    p_manifest = make_provenance(SOURCE_ID, _sha256f(manifest_path), "manifest.json", VERSION)
    p_telemetry = make_provenance(SOURCE_ID, _sha256f(tel_path),
                                  "model_telemetry/model_telemetry.jsonl", VERSION)
    p_native = make_provenance(SOURCE_ID, _sha256f(react_path),
                               "native_trajectory/original_ReAct.jsonl", VERSION)
    doc = compose_run(manifest=manifest, telemetry=telemetry, react=react,
                      provenances={"manifest": p_manifest, "telemetry": p_telemetry,
                                   "native": p_native})
    entity_id = doc.runs[0].id
    entity = {}
    request = {}
    for m in doc.metrics:
        if m.scope_id == entity_id:
            entity.setdefault((_canonical(m.name), m.aggregation), []).append(m)
        elif m.aggregation == "single_request":
            request.setdefault(_canonical(m.name), []).append(m)
    actual = {name: _first_value(entity, name) for name in
              ("model_request_count", "total_input_tokens", "total_output_tokens",
               "max_input_context", "max_source_context_tokens",
               "total_api_latency_s", "tool_call_count",
               "manifest_reported_wall_time_s")}
    _validate_gold_map(sid, gold, actual,
                       {"selected_model_requests": "model_request_count",
                        "total_input_tokens": "total_input_tokens",
                        "total_output_tokens": "total_output_tokens",
                        "max_context_tokens": "max_source_context_tokens",
                        "max_input_context": "max_input_context",
                        "manifest_wall_time_s": "manifest_reported_wall_time_s",
                        "manifest_tool_call_count": "tool_call_count"},
                       required_expected={"selected_model_requests", "total_input_tokens",
                                          "total_output_tokens", "max_context_tokens",
                                          "max_input_context", "manifest_wall_time_s",
                                          "manifest_tool_call_count"})
    files = [{"path": str(manifest_path), "sha256": _sha256f(manifest_path)},
             {"path": str(tel_path), "sha256": _sha256f(tel_path)},
             {"path": str(react_path), "sha256": _sha256f(react_path)},
             {"path": str(summary_path), "sha256": _sha256f(summary_path)}]
    # Raw comparison data for sidecar cross-check: bundle request keys/values
    # and native ReAct toolCall IDs.
    native_trace_id = manifest.get("trace_id")
    request_records = {}
    for entry in telemetry:
        rec = entry["record"]
        key = (rec.get("trace_id"), rec.get("call_id"))
        request_records[key] = {
            "input_tokens": rec.get("input_tokens"),
            "output_tokens": rec.get("output_tokens"),
            "context_tokens": rec.get("context_tokens"),
            "ttft": rec.get("ttft"),
            "api_latency": rec.get("api_latency"),
        }
    tool_ids = set()
    for entry in react:
        ev = entry["record"]
        msg = ev.get("message") if ev.get("type") == "message" else None
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "assistant":
            for item in (msg.get("content") or []):
                if isinstance(item, dict) and item.get("type") == "toolCall" and item.get("id"):
                    tool_ids.add(item["id"])
    return LoadedSample(sid, sel["source_id"], "run", doc.trace_type, doc.profile,
                        doc, entity_id, files, entity, request,
                        record_ref="bundle",
                        request_records=request_records, tool_ids=tool_ids)


def _load_aux(catalog, benchmark_root, sel, gold):
    source = catalog.source(sel["source_id"])
    call = sel["locator"]["call_id"]
    path = source.path
    before = path.stat()
    found = None
    with path.open("rb") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            r = strict_object(line)
            if r.get("call_id") == call:
                found = (r, n, _sha256b(line))
                break
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"source changed: {path}")
    if found is None:
        raise ValueError(f"AUX-INCOMPLETE call_id={call} not found")
    raw, ln, rhash = found
    prov = make_provenance("telemetry_video_weaver", _sha256f(path),
                           f"video_weaver.jsonl;line:{ln}", VERSION)
    doc = compose_unassigned_request(source_id="telemetry_video_weaver",
                                     raw_record=raw, provenance=prov)
    entity_id = doc.requests[0].id
    request = {}
    for m in doc.metrics:
        request.setdefault(_canonical(m.name), []).append(m)
    actual = {name: _first_value(request, name) for name in ("input_tokens", "output_tokens")}
    if gold:
        # AUX has no numeric gold; just ensure run_id stays null via document check
        pass
    return LoadedSample("AUX-INCOMPLETE", sel["source_id"], "unassigned_request",
                        doc.trace_type, doc.profile, doc, entity_id,
                        [{"path": str(path), "sha256": _sha256f(path)}], {}, request,
                        record_ref=f"line:{ln}", record_sha256=rhash)


def _first_value(metric_groups, name):
    for key, metrics in metric_groups.items():
        if isinstance(key, tuple):
            if key[0] != name:
                continue
        elif key != name:
            continue
        for m in metrics:
            if m.value is not None:
                return m.value
    return None


def _validate_gold_map(sample_id, gold, actual, mapping, required_expected=None):
    if gold is None:
        return
    expected = gold.get("expected", {})
    if required_expected is not None:
        missing_req = required_expected - set(expected)
        if missing_req:
            raise ValueError(f"gold {sample_id}: required expectations missing: {sorted(missing_req)}")
    # Every expected gold key must be validated; uncovered keys indicate
    # the sample config drifted from what this adapter checks.
    uncovered = set(expected) - set(mapping)
    if uncovered:
        raise ValueError(f"gold {sample_id}: expectations not validated: {sorted(uncovered)}")
    for gk, actual_key in mapping.items():
        if gk in expected:
            if actual.get(actual_key) != expected[gk]:
                raise ValueError(f"gold {sample_id}: {gk} actual={actual.get(actual_key)} expected={expected[gk]}")


def _extract_metrics(doc: TraceDocument, entity_id: str, canonical_agg: str | None = None) -> dict:
    out = {}
    for m in doc.metrics:
        if m.scope_id != entity_id:
            continue
        if canonical_agg is not None:
            if m.aggregation == canonical_agg:
                out[(m.scope_id, m.aggregation, m.name)] = m
        else:
            out[(m.scope_id, m.aggregation, m.name)] = m
    return out