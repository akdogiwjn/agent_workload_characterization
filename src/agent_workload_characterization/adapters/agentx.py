"""AgentX v7 published, filtered proxy traces; never Tool/CPU measurements."""

from decimal import Decimal, ROUND_HALF_EVEN
import math

from .base import Adapter, Context, RawRecord, RecordError, stable_id
from ..ir import SCHEMA_VERSION, TraceDocument, Metric
from ..metric_contracts import interval_totals


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise RecordError(f"invalid {field}")
    return value


def count(value, field):
    if value is not None and (type(value) is not int or value < 0):
        raise RecordError(f"invalid {field}")
    return value


def time_ns(value, field, multiplier=1_000_000_000):
    if value is None:
        return None
    if type(value) not in (int, float) or value < 0 or (isinstance(value, float) and not math.isfinite(value)):
        raise RecordError(f"invalid {field}")
    # Round only the representation; original clock accuracy remains unknown.
    return int((Decimal(str(value)) * multiplier).to_integral_value(rounding=ROUND_HALF_EVEN))


class AgentXAdapter(Adapter):
    name = "agentx-v7"
    version = "agentx-v7/0.1.0"

    def normalize(self, record: RawRecord, context: Context) -> TraceDocument:
        raw = record.value
        if not isinstance(raw, dict) or record.error:
            raise RecordError("invalid raw record")
        if (context.adapter_version != self.version or set(context.config) - {"trace_type"}
            or context.config.get("trace_type", "production_derived") not in ("production_derived", "synthetic")):
            raise RecordError("unsupported adapter version/configuration")
        native_id = text(raw.get("id"), "session id")
        run_id = stable_id(context.source_id, "run", native_id)
        main_id = stable_id(context.source_id, "agent", native_id, "main")
        provenance_id = stable_id(context.source_id, "provenance", native_id)
        clock_id = stable_id(context.source_id, "clock", native_id)
        provenance = {"id": provenance_id, "source_id": context.source_id, "snapshot_id": context.snapshot_id,
                      "source_record_ref": record.source_record_ref, "adapter_version": self.version}
        doc = {"schema_version": SCHEMA_VERSION, "profile": "semantic_trace", "trace_type": context.config.get("trace_type", "production_derived"),
               "provenance": [provenance], "runs": [{"id": run_id, "provenance_id": provenance_id}],
               "clocks": [{"id": clock_id, "kind": "source_relative", "source": "AgentX v7 published proxy-relative t; unit seconds; conversion rounded to ns, not host monotonic",
                           "precision_ns": None, "precision_missing_reason": "not_recorded"}],
               "agents": [], "requests": [], "events": [], "metrics": []}

        def association(pointer):
            return {"status": "resolved", "method": "source_session_and_containment", "evidence_ref": f"{provenance_id}#/{pointer}"}

        def bound(identity, pointer):
            return {"id": identity, "provenance_id": provenance_id, "run_id": run_id, "association": association(pointer)}

        def metric(name, value, unit, scope, aggregation, rule, inputs=(), missing="not_recorded"):
            identity = stable_id(context.source_id, "metric", native_id, scope, name, aggregation)
            item = Metric(id=identity, provenance_id=provenance_id, name=name, value=value, unit=unit,
                          scope_id=scope, aggregation=aggregation,
                          denominator=f"{aggregation}; retained published requests, retries retained as published; no excluded requests reconstructed",
                          evidence="unavailable" if value is None else "derived" if inputs else "observed",
                          source_field_or_rule=rule, input_metric_ids=list(inputs),
                          missing_reason=missing if value is None else None)
            doc["metrics"].append(item.model_dump())
            return item

        doc["agents"].append(bound(main_id, "requests"))
        all_requests = []
        main_requests = []
        group_presence = []
        seen_agents = set()

        def walk(items, agent, pointer="requests", parent_event=None, depth=0):
            if not isinstance(items, list) or depth > 64:
                raise RecordError("requests must be an array; nesting limited to 64")
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    raise RecordError("request must be object")
                path = f"{pointer}/{index}"
                kind = item.get("type")
                if kind == "subagent":
                    source_agent = text(item.get("agent_id"), "subagent id")
                    if source_agent in seen_agents:
                        raise RecordError("duplicate native agent identity", code="identity_conflict")
                    seen_agents.add(source_agent)
                    aid = stable_id(context.source_id, "agent", native_id, "subagent", source_agent)
                    agent_row = bound(aid, path) | {"parent_id": agent, "source_agent_id": source_agent}
                    for original, target in (("subagent_type", "source_agent_type"), ("status", "source_status")):
                        if item.get(original) is not None:
                            agent_row[target] = text(item[original], original)
                    doc["agents"].append(agent_row)
                    group_presence.append(metric("subagent_presence", 1, "count", aid, "source_group", path))
                    metric("source_tool_use_count", count(item.get("tool_use_count"), "tool_use_count"), "count", aid, "source_group", path + "/tool_use_count")
                    metric("source_total_tokens", count(item.get("total_tokens"), "total_tokens"), "token", aid, "source_group", path + "/total_tokens; not added to request token totals")
                    start = time_ns(item.get("t"), "t")
                    duration = time_ns(item.get("duration_ms"), "duration_ms", 1_000_000)
                    metric("source_subagent_duration", duration, "ns", aid, "source_group", path + "/duration_ms * 1e6")
                    event_id = stable_id(context.source_id, "event", native_id, "subagent_span", source_agent)
                    doc["events"].append(bound(event_id, path) | {"kind": "span", "name": "agentx_subagent_group",
                        "agent_id": aid, "parent_id": parent_event, "interval": interval(start, duration)})
                    walk(item.get("requests"), aid, path + "/requests", event_id, depth + 1)
                    continue
                if kind not in ("s", "n"):
                    raise RecordError("unknown AgentX request type")
                rid = stable_id(context.source_id, "request", native_id, path)
                start, duration = time_ns(item.get("t"), "t"), time_ns(item.get("api_time"), "api_time")
                request = bound(rid, path) | {"agent_id": agent, "interval": interval(start, duration), "source_request_type": kind}
                if item.get("model") is not None:
                    request["model_name"] = text(item["model"], "model")
                if item.get("hash_ids") is not None:
                    hashes = item["hash_ids"]
                    block_size = count(raw.get("block_size"), "block_size")
                    if not isinstance(hashes, list) or not block_size:
                        raise RecordError("prefix hashes require array and positive block_size")
                    if any(type(h) not in (str, int) or (isinstance(h, str) and not h.strip()) for h in hashes):
                        raise RecordError("invalid prefix hash identifier")
                    request["prefix"] = {"hashes": [str(h) for h in hashes], "block_size": block_size,
                                         "hash_id_scope": text(raw.get("hash_id_scope"), "hash_id_scope")}
                doc["requests"].append(request)
                measures = {"presence": metric("request_presence", 1, "count", rid, "single_request", path)}
                for source_key, name, unit in (("in", "input_tokens", "token"), ("out", "output_tokens", "token"),
                                               ("api_time", "api_latency", "ns"), ("ttft", "source_ttft", "ns"),
                                               ("think_time", "source_think_time", "ns"), ("t", "source_start", "ns")):
                    value = count(item.get(source_key), source_key) if unit == "token" else time_ns(item.get(source_key), source_key)
                    measures[name] = metric(name, value, unit, rid, "single_request", path + "/" + source_key + ("; seconds -> ns, not Tool/CPU time" if unit == "ns" else ""))
                measures["interval"] = request["interval"]
                all_requests.append(measures)
                if agent == main_id:
                    main_requests.append(measures)

        def interval(start, duration):
            return {"clock_id": clock_id, "start_ns": start,
                    "end_ns": start + duration if start is not None and duration is not None else None,
                    "source": "native_event", "missing_reason": "not_recorded" if start is None or duration is None else None}

        walk(raw.get("requests"), main_id)
        metric("subagent_count", len(group_presence), "count", run_id, "all_agents", "count explicit retained subagent groups", [m.id for m in group_presence])
        for aggregation, requests in (("main_agent", main_requests), ("all_agents", all_requests)):
            metric("model_request_count", len(requests), "count", run_id, aggregation, "count retained s/n records, not turns", [r["presence"].id for r in requests])
            for name, source_name, unit, operation in (("input_tokens", "input_tokens", "token", sum),
                ("output_tokens", "output_tokens", "token", sum), ("max_context_tokens", "input_tokens", "token", max),
                ("model_work", "api_latency", "ns", sum)):
                values = [r[source_name] for r in requests]
                complete = all(m.value is not None for m in values)
                value = operation(m.value for m in values) if complete and values else 0 if not values and operation == sum else None
                metric(name, value, unit, run_id, aggregation, f"{operation.__name__} of retained {source_name}; strict coverage, not partial sum",
                       [m.id for m in values], missing="not_applicable" if not values else "not_recorded")
            times = [r["interval"] for r in requests]
            inputs = [r[key].id for r in requests for key in ("source_start", "api_latency")]
            from ..ir import Interval
            complete = all(t["start_ns"] is not None and t["end_ns"] is not None for t in times)
            totals = interval_totals([Interval.model_validate(t) for t in times]) if complete else {}
            for name, result in (("model_busy", "busy_ns"), ("model_overlap", "overlap_ns"), ("observed_span", "observed_span_ns")):
                metric(name, totals.get(result), "ns", run_id, aggregation,
                       "closed published request intervals: " + result + "; not run E2E or local CPU", inputs,
                       missing="not_applicable" if not times else "not_recorded")
        for name, unit in (("turn_count", "count"), ("tool_call_count", "count"), ("run_elapsed", "ns"), ("local_cpu_time", "ns")):
            metric(name, None, unit, run_id, "all_agents", "not supplied by retained AgentX proxy records", missing="unsupported")
        return TraceDocument.model_validate(doc)


def summarize(document: TraceDocument) -> dict:
    """Small validation summary, not a cross-source macro report."""
    run_id = document.runs[0].id
    return {"schema_version": document.schema_version, "profile": document.profile,
            "trace_type": document.trace_type, "run_id": run_id,
            "agents": len(document.agents), "requests": len(document.requests),
            "models": sorted({r.model_name for r in document.requests if r.model_name}),
            "metrics": {scope: {m.name: {"value": m.value, "unit": m.unit, "evidence": m.evidence,
                                        "missing_reason": m.missing_reason}
                                for m in document.metrics if m.scope_id == run_id and m.aggregation == scope}
                        for scope in ("main_agent", "all_agents")}}
