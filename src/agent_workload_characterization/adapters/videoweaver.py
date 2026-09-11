"""VideoWeaver local trace composition: manifest + proxy telemetry + ReAct native.

This module is a pure compositor. It receives already-read manifest dict, proxy
telemetry records (with source refs/hashes) and ReAct event records (with source
refs/hashes) and returns one closed semantic_trace TraceDocument. It never opens
files, never executes media/exporter, and never writes normalized batches.

Inputs keep their own provenance: request metrics point to the telemetry file
provenance, Tool spans to the ReAct file provenance, status declarations to the
manifest provenance. No fabricated run/task/attempt/agent identity.
"""

from ..ir import SCHEMA_VERSION, TraceDocument, Interval, Metric
from .base import RecordError, stable_id

SOURCE_ID = "gen_videoweaver_traces"
VERSION = "videoweaver-v1/0.1.0"
# Adapted local run: text model routed via local proxy to Volcengine; media via
# DashScope/Bailian. Not production, oracle or replay.
DEFAULT_TRACE_TYPE = "benchmark_real"


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise RecordError(f"invalid {field}")
    return value


def _count(value, field):
    if value is not None and (type(value) is not int or value < 0):
        raise RecordError(f"invalid {field}")
    return value


def _token(value, field):
    if value is None:
        return None
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise RecordError(f"invalid {field}")
    return value


def _finite(value, field):
    """Finite non-negative number or None; huge values -> RecordError not OverflowError."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecordError(f"invalid {field}")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise RecordError(f"invalid {field} (overflow)")
    if number < 0 or number != number or number in (float("inf"), float("-inf")):
        raise RecordError(f"invalid {field}")
    return number


def _utc_ns(value, field):
    """Parse proxy ISO timestamp or epoch float to epoch nanoseconds; None stays None."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise RecordError(f"invalid {field} (bool)")
    if isinstance(value, (int, float)):
        try:
            return int(float(value) * 1_000_000_000)
        except (OverflowError, ValueError):
            raise RecordError(f"invalid {field} (overflow)")
    if not isinstance(value, str) or not value.strip():
        raise RecordError(f"invalid {field}")
    from datetime import datetime, timezone
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RecordError(f"invalid {field}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return int(dt.timestamp() * 1_000_000_000)
    except (OverflowError, ValueError):
        raise RecordError(f"invalid {field} (overflow)")


def make_provenance(source_id, snapshot_id, source_record_ref, adapter_version):
    identity = stable_id(source_id, "provenance", source_record_ref, snapshot_id)
    return {"id": identity, "source_id": source_id, "snapshot_id": snapshot_id,
            "source_record_ref": source_record_ref, "adapter_version": adapter_version}


def parse_proxy_record(raw):
    """Validate one proxy telemetry record; returns a canonical dict."""
    trace_id = _text(raw.get("trace_id"), "trace_id")
    call_id = _text(raw.get("call_id"), "call_id")
    return {
        "trace_id": trace_id, "call_id": call_id,
        "model": raw.get("model"),
        "stream": raw.get("stream"),
        "request_sequence": _count(raw.get("request_sequence"), "request_sequence"),
        "input_tokens": _token(raw.get("input_tokens"), "input_tokens"),
        "output_tokens": _token(raw.get("output_tokens"), "output_tokens"),
        "context_tokens": _token(raw.get("context_tokens"), "context_tokens"),
        "cached_input_tokens": _token(raw.get("cached_input_tokens"), "cached_input_tokens"),
        "reasoning_output_tokens": _token(raw.get("reasoning_output_tokens"), "reasoning_output_tokens"),
        "ttft": _finite(raw.get("ttft"), "ttft"),
        "api_latency": _finite(raw.get("api_latency"), "api_latency"),
        "upstream_latency": _finite(raw.get("upstream_latency"), "upstream_latency"),
        "model_latency": _finite(raw.get("model_latency"), "model_latency"),
        "http_status": raw.get("http_status"),
        "usage_source": raw.get("usage_source"),
        "timestamp_request": _utc_ns(raw.get("timestamp_request"), "timestamp_request"),
        "timestamp_request_utc": _utc_ns(raw.get("timestamp_request_utc"), "timestamp_request_utc"),
        "timestamp_first_token": _utc_ns(raw.get("timestamp_first_token"), "timestamp_first_token"),
        "timestamp_response": _utc_ns(raw.get("timestamp_response"), "timestamp_response"),
        "timestamp_response_utc": _utc_ns(raw.get("timestamp_response_utc"), "timestamp_response_utc"),
    }


def parse_react_event(raw):
    """Validate one ReAct JSONL event; returns canonical dict or None for non-message lines."""
    if not isinstance(raw, dict):
        raise RecordError("ReAct event must be object")
    if raw.get("type") != "message":
        return None
    message = raw.get("message")
    if not isinstance(message, dict):
        raise RecordError("ReAct message missing")
    role = message.get("role")
    timestamp = _utc_ns(raw.get("timestamp") or message.get("timestamp"), "react timestamp")
    if role == "assistant":
        tools = []
        content = message.get("content")
        if content is not None and not isinstance(content, list):
            raise RecordError("assistant content must be a list")
        for item in content or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "toolCall":
                cid = _text(item.get("id"), "toolCall id")
                tools.append({"id": cid, "name": item.get("name"), "args": item.get("args")})
        return {"type": "assistant", "tools": tools, "timestamp": timestamp}
    if role == "toolResult":
        cid = _text(message.get("toolCallId"), "toolCallId")
        return {"type": "toolResult", "call_id": cid, "timestamp": timestamp,
                "content": message.get("content")}
    return {"type": "message", "role": role, "timestamp": timestamp}


def interval(clock_id, start_ns, end_ns, source, missing=None):
    return Interval(clock_id=clock_id, start_ns=start_ns, end_ns=end_ns,
                    source=source, missing_reason=missing)


def compose_run(*, manifest, telemetry, react, provenances, trace_type=DEFAULT_TRACE_TYPE):
    """Compose one closed main-run semantic trace document.

    manifest: dict (already read bundle manifest.json)
    telemetry: list[dict] with keys record/ref/hash (proxy lines)
    react: list[dict] with keys record/ref/hash (ReAct lines)
    provenances: dict mapping role->provenance dict with keys
        manifest/telemetry/native
    """
    if set(provenances) != {"manifest", "telemetry", "native"}:
        raise RecordError("all three input provenances are required")
    native_trace_id = _text(manifest.get("trace_id"), "trace_id")
    run_id = stable_id(SOURCE_ID, "run", native_trace_id)
    clock_id = stable_id(SOURCE_ID, "clock", native_trace_id, "utc")
    prov = {role: p["id"] for role, p in provenances.items()}

    doc = {
        "schema_version": SCHEMA_VERSION,
        "profile": "semantic_trace",
        "trace_type": trace_type,
        "provenance": [p for p in provenances.values()],
        "clocks": [{"id": clock_id, "kind": "utc", "source": "proxy UTC wall-clock timestamps; ns is representation only",
                    "precision_ns": None, "precision_missing_reason": "not_recorded"}],
        "runs": [{"id": run_id, "provenance_id": prov["manifest"]}],
        "sessions": [], "requests": [], "events": [], "metrics": [], "agents": [],
        "tasks": [], "attempts": [], "jobs": [], "processes": [],
        "resource_scopes": [], "links": [], "templates": [], "replay": None,
    }

    def bound(identity, pointer):
        return {"id": identity, "provenance_id": prov["telemetry"], "run_id": run_id,
                "association": {"status": "resolved", "method": "source_session_and_record",
                                "evidence_ref": pointer}}

    def metric(name, value, unit, scope, aggregation, rule, *, provenance_id, evidence,
               inputs=(), missing=None):
        identity = stable_id(SOURCE_ID, "metric", native_trace_id, scope, name, aggregation)
        if value is None:
            evidence = "unavailable"
        item = Metric(id=identity, provenance_id=provenance_id, name=name, value=value, unit=unit,
                      scope_id=scope, aggregation=aggregation,
                      denominator=f"{aggregation}; source-declared records only",
                      evidence=evidence, source_field_or_rule=rule,
                      input_metric_ids=list(inputs),
                      missing_reason=missing if value is None else None)
        doc["metrics"].append(item.model_dump())
        return item

    # --- run-level status/claims (manifest provenance) ---
    gen_status = _text(manifest.get("generation_status"), "generation_status")
    execution = "completed" if gen_status == "success" else "unknown"
    eval_status = manifest.get("evaluation_status")
    evaluation = "unknown"
    if eval_status == "not_run":
        evaluation = "not_evaluated"
    doc["runs"][0]["execution_status"] = execution
    doc["runs"][0]["evaluation_status"] = evaluation
    doc["runs"][0]["archive_status"] = "unknown"
    trajectory = manifest.get("trajectory") or {}
    wall = trajectory.get("wall_time_s")
    if wall is not None:
        metric("manifest_reported_wall_time_s", _finite(wall, "wall_time_s"), "s", run_id,
               "manifest_declaration", "manifest.trajectory.wall_time_s; not verified run E2E",
               provenance_id=prov["manifest"], evidence="observed")
    session_id = manifest.get("openclaw_session_id")
    if session_id:
        sid = stable_id(SOURCE_ID, "session", native_trace_id, _text(session_id, "openclaw_session_id"))
        doc["sessions"].append({"id": sid, "provenance_id": prov["manifest"], "run_id": run_id,
                                "association": {"status": "resolved", "method": "manifest_session_declaration",
                                                "evidence_ref": "manifest.openclaw_session_id"}})

    # --- requests (telemetry provenance) ---
    request_inputs, request_outputs, request_contexts = [], [], []
    request_latency_metric = []
    seen_calls = set()
    for entry in telemetry:
        raw = entry["record"]
        parsed = parse_proxy_record(raw)
        if parsed["trace_id"] != native_trace_id:
            continue  # other-trace records are nonselected, not errors
        key = (parsed["trace_id"], parsed["call_id"])
        if key in seen_calls:
            raise RecordError("duplicate proxy (trace_id, call_id)")
        seen_calls.add(key)
        rid = stable_id(SOURCE_ID, "request", native_trace_id, parsed["call_id"])
        start = parsed["timestamp_request_utc"] if parsed["timestamp_request_utc"] is not None else parsed["timestamp_request"]
        end = parsed["timestamp_response_utc"] if parsed["timestamp_response_utc"] is not None else parsed["timestamp_response"]
        request = bound(rid, f"{entry['ref']}")
        request["model_name"] = parsed["model"]
        request["source_request_type"] = "stream" if parsed["stream"] is True else "chat_completion"
        request["interval"] = interval(clock_id, start, end, "native_event",
                                       missing=None if (start is not None and end is not None) else "not_recorded").model_dump()
        doc["requests"].append(request)
        m_input = metric("input_tokens", parsed["input_tokens"], "token", rid, "single_request",
                         "proxy input_tokens; not source_context_tokens", provenance_id=prov["telemetry"],
                         evidence="observed",
                         missing="not_recorded" if parsed["input_tokens"] is None else None)
        m_output = metric("output_tokens", parsed["output_tokens"], "token", rid, "single_request",
                          "proxy output_tokens", provenance_id=prov["telemetry"],
                          evidence="observed", missing="not_recorded" if parsed["output_tokens"] is None else None)
        m_ctx = metric("source_context_tokens", parsed["context_tokens"], "token", rid, "single_request",
                       "proxy context_tokens (input+output at proxy); NOT input context", provenance_id=prov["telemetry"],
                       evidence="observed", missing="not_recorded" if parsed["context_tokens"] is None else None)
        metric("cached_input_tokens", parsed["cached_input_tokens"], "token", rid, "single_request",
               "proxy cached_input_tokens; subset, not added to totals", provenance_id=prov["telemetry"],
               evidence="observed", missing="not_recorded" if parsed["cached_input_tokens"] is None else None)
        metric("reasoning_output_tokens", parsed["reasoning_output_tokens"], "token", rid, "single_request",
               "proxy reasoning_output_tokens; subset, not added to totals", provenance_id=prov["telemetry"],
               evidence="observed", missing="not_recorded" if parsed["reasoning_output_tokens"] is None else None)
        metric("ttft", parsed["ttft"], "s", rid, "single_request", "proxy ttft",
               provenance_id=prov["telemetry"], evidence="observed",
               missing="not_recorded" if parsed["ttft"] is None else None)
        m_latency = metric("api_latency", parsed["api_latency"], "s", rid, "single_request",
               "proxy boundary response time; not three additive stages and not server pure inference",
               provenance_id=prov["telemetry"], evidence="observed",
               missing="not_recorded" if parsed["api_latency"] is None else None)
        request_inputs.append(m_input)
        request_outputs.append(m_output)
        request_contexts.append(m_ctx)
        if parsed["api_latency"] is not None:
            request_latency_metric.append(m_latency)

    # --- run aggregates (strict coverage: null if any input unavailable) ---
    metric("model_request_count", len(request_inputs), "count", run_id, "all_requests",
           "count retained proxy requests for this trace_id", provenance_id=prov["telemetry"],
           evidence="observed")

    def strict_sum(name, metrics, unit, rule):
        complete = all(m.value is not None for m in metrics)
        value = sum(m.value for m in metrics) if complete and metrics else None
        metric(name, value, unit, run_id, "all_requests", rule,
               provenance_id=prov["telemetry"], evidence="derived", inputs=[m.id for m in metrics],
               missing="not_applicable" if not metrics else "not_recorded")
        return value

    def strict_max(name, metrics, unit, rule):
        complete = all(m.value is not None for m in metrics)
        values = [m.value for m in metrics if m.value is not None]
        value = max(values) if complete and metrics else None
        metric(name, value, unit, run_id, "all_requests", rule,
               provenance_id=prov["telemetry"], evidence="derived", inputs=[m.id for m in metrics],
               missing="not_applicable" if not metrics else "not_recorded")
        return value

    strict_sum("total_input_tokens", request_inputs, "token",
               "sum of proxy input_tokens; null unless every request has a value")
    strict_sum("total_output_tokens", request_outputs, "token",
               "sum of proxy output_tokens; null unless every request has a value")
    strict_max("max_input_context", request_inputs, "token",
               "max of proxy input_tokens; NOT source_context_tokens; null unless every request has a value")
    strict_max("max_source_context_tokens", request_contexts, "token",
               "max of proxy context_tokens (input+output); source-declared, not input context; null unless every request has a value")
    strict_sum("total_api_latency_s", request_latency_metric, "s",
               "sum proxy api_latency; proxy boundary, not server inference; null unless every request has a value")

    # --- Tool events (native provenance) ---
    calls = {}      # toolCallId -> {"name", "timestamp", "ref"}
    results = {}    # toolCallId -> {"timestamp", "ref", "content"}
    duplicate_calls = []
    orphan_results = []
    for entry in react:
        event = parse_react_event(entry["record"])
        if event is None:
            continue
        ref = entry.get("ref", "?")
        if event["type"] == "assistant":
            for tool in event["tools"]:
                if tool["id"] in calls:
                    duplicate_calls.append((tool["id"], ref))
                calls[tool["id"]] = {"name": tool["name"], "timestamp": event["timestamp"], "ref": ref}
        elif event["type"] == "toolResult":
            cid = event["call_id"]
            if cid in calls:
                if cid in results:
                    # Conflicting duplicate result must be surfaced, not silently overwritten.
                    raise RecordError(f"conflicting toolResult for {cid} at {ref}")
                results[cid] = {"timestamp": event["timestamp"], "ref": ref,
                                "content": event["content"]}
            else:
                orphan_results.append((cid, ref))
    if duplicate_calls:
        raise RecordError(f"duplicate toolCall id: {duplicate_calls[0]}")
    tool_ids = list(calls)
    for cid in tool_ids:
        event_id = stable_id(SOURCE_ID, "event", native_trace_id, "tool_call", cid)
        result = results.get(cid)
        # A result may exist but its timestamp be absent (missing log time).
        # Completeness is judged by both boundaries, not by result presence.
        start_ns = calls[cid]["timestamp"]
        end_ns = result["timestamp"] if (result and result.get("timestamp") is not None) else None
        incomplete = start_ns is None or end_ns is None
        ev = {"id": event_id, "provenance_id": prov["native"], "run_id": run_id,
              "association": {"status": "resolved", "method": "source_toolcall_result_pairing",
                              "evidence_ref": f"original_ReAct.jsonl;call={calls[cid]['ref']};result={result['ref'] if result else 'missing'}"},
              "kind": "tool_call", "name": calls[cid]["name"] or "unknown",
              "interval": interval(clock_id, start_ns, end_ns,
                                   "log_receipt",
                                   missing="not_recorded" if incomplete else None).model_dump()}
        doc["events"].append(ev)
    metric("tool_call_count", len(tool_ids), "count", run_id, "all_requests",
           "count unique toolCall IDs from parsed ReAct", provenance_id=prov["native"],
           evidence="observed")
    if orphan_results:
        metric("orphan_tool_results", len(orphan_results), "count", run_id, "all_requests",
               "toolResult without matching toolCall; refs retained in companion report", provenance_id=prov["native"],
               evidence="observed")

    # --- unavailable run/CPU metrics ---
    for name, unit in (("run_elapsed", "ns"), ("local_cpu_time", "ns"), ("tool_cpu_time", "ns")):
        metric(name, None, unit, run_id, "all_requests", "not supplied by this trace selection",
               provenance_id=prov["native"], evidence="unavailable", missing="unsupported")

    return TraceDocument.model_validate(doc)


def compose_unassigned_request(*, source_id, raw_record, provenance):
    """One unassigned request document from raw telemetry without an assembled run."""
    parsed = parse_proxy_record(raw_record)
    batch_id = stable_id(source_id, "batch", "videoweaver-unassigned", parsed["trace_id"])
    req_id = stable_id(source_id, "request", parsed["trace_id"], parsed["call_id"])
    doc = {
        "schema_version": SCHEMA_VERSION,
        "profile": "semantic_trace",
        "trace_type": "unknown",
        "provenance": [provenance],
        "requests": [{"id": req_id, "provenance_id": provenance["id"], "run_id": None,
                      "batch_id": batch_id,
                      "association": {"status": "unresolved", "method": "run_not_loaded_in_selection",
                                      "evidence_ref": "telemetry trace_id not assembled in this sample selection"},
                      "model_name": parsed["model"]}],
        "metrics": [],
        "runs": [], "agents": [], "events": [], "clocks": [], "sessions": [],
        "tasks": [], "attempts": [], "jobs": [], "processes": [],
        "resource_scopes": [], "links": [], "templates": [], "replay": None,
    }
    for name, value, unit in (("input_tokens", parsed["input_tokens"], "token"),
                              ("output_tokens", parsed["output_tokens"], "token"),
                              ("ttft", parsed["ttft"], "s"),
                              ("api_latency", parsed["api_latency"], "s")):
        doc["metrics"].append(Metric(
            id=stable_id(source_id, "metric", parsed["trace_id"], parsed["call_id"], name),
            provenance_id=provenance["id"], name=name, value=value, unit=unit,
            scope_id=req_id, aggregation="single_request",
            denominator="single_request; unassigned (run not loaded)",
            evidence="observed" if value is not None else "unavailable",
            source_field_or_rule=f"proxy {name}; request belongs to run not loaded in this selection",
            missing_reason=None if value is not None else "not_recorded",
        ).model_dump())
    return TraceDocument.model_validate(doc)