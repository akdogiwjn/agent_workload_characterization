"""Applied Compute trie workloads: template-only macro profiles.

Three JSONL files, each ~8192 rows. Each row is a workload template with
per-turn token length vectors and simulated delays. No timestamps, tool
names or execution measurements exist in the source format.

Per trie reference at 6918da7915e3:
  - length fields are token counts (template_parameter, not observed usage)
  - N tool-use turns -> N+1 completion requests
  - tool_call_latency is simulated delay in seconds
"""

import math

from .base import Adapter, Context, RawRecord, RecordError, stable_id
from ..ir import SCHEMA_VERSION, TraceDocument, Metric, Template
from ..metric_contracts import template_lengths

SOURCE_MAP: dict[str, str] = {
    "applied_agentic_coding": "agentic_coding_8k.jsonl",
    "applied_code_qa": "code_qa_8k.jsonl",
    "applied_office_work": "office_work_8k.jsonl",
}

LENGTH_REF = "trie 6918da7 README+types.py: length = token; N turns = N+1 completions"


def _nonnegative(value, field):
    if value is None:
        return None
    if isinstance(value, bool) or type(value) is not int:
        raise RecordError(f"{field} must be a non-negative integer or null")
    if value < 0:
        raise RecordError(f"{field} must be non-negative")
    return value


def _latency(value, field):
    if value is None:
        return None
    if isinstance(value, bool) or type(value) not in (int, float):
        raise RecordError(f"{field} must be a finite non-negative number")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise RecordError(f"{field} overflowed or invalid")
    if number < 0 or not math.isfinite(number):
        raise RecordError(f"{field} must be finite non-negative")
    return number


def _int_list(values, field, expected):
    if not isinstance(values, list):
        raise RecordError(f"{field} must be a list")
    if len(values) != expected:
        raise RecordError(f"{field} length {len(values)} != N={expected}")
    return [_nonnegative(v, f"{field}[{i}]") for i, v in enumerate(values)]


def _latency_list(values, field, expected):
    if not isinstance(values, list):
        raise RecordError(f"{field} must be a list")
    if len(values) != expected:
        raise RecordError(f"{field} length {len(values)} != N={expected}")
    return [_latency(v, f"{field}[{i}]") for i, v in enumerate(values)]


class AppliedComputeAdapter(Adapter):
    name = "applied_compute-v1"
    version = "applied_compute-v1/0.1.0"

    def normalize(self, record: RawRecord, context: Context) -> TraceDocument:
        raw = record.value
        if not isinstance(raw, dict) or record.error:
            raise RecordError("invalid raw record")
        if (context.adapter_version != self.version
            or set(context.config) - {"trace_type"}
            or context.config.get("trace_type", "production_derived") not in ("production_derived", "synthetic")):
            raise RecordError("unsupported adapter version/configuration")

        allowed_keys = {"num_turns", "input_prompt_length", "assistant_response_length",
                        "tool_call_output_length", "tool_call_latency", "final_assistant_response_length"}
        extra = set(raw) - allowed_keys
        if extra:
            raise RecordError(f"unexpected keys {extra}")

        N = raw.get("num_turns")
        if isinstance(N, bool) or not isinstance(N, int) or N < 0:
            raise RecordError("num_turns must be a non-negative integer")

        assistant = _int_list(raw.get("assistant_response_length"), "assistant_response_length", N)
        tool_out = _int_list(raw.get("tool_call_output_length"), "tool_call_output_length", N)
        latency = _latency_list(raw.get("tool_call_latency"), "tool_call_latency", N)
        initial = _nonnegative(raw.get("input_prompt_length"), "input_prompt_length")
        final = _nonnegative(raw.get("final_assistant_response_length"), "final_assistant_response_length")

        native_id = record.source_record_ref
        template_id = stable_id(context.source_id, "template", context.source_id, record.source_record_ref)
        provenance_id = stable_id(context.source_id, "provenance", context.source_id, record.source_record_ref)

        missing = None in (initial, final, *assistant, *tool_out)
        template = Template(
            id=template_id, provenance_id=provenance_id,
            tool_use_turns=N, initial_input=initial,
            assistant_outputs=assistant, tool_outputs=tool_out,
            final_output=final, unit="token",
            length_definition_ref=LENGTH_REF,
            length_missing_reason="not_recorded" if missing else None,
        )
        lengths = template_lengths(template)
        doc = {
            "schema_version": SCHEMA_VERSION,
            "profile": "macro_template",
            "trace_type": context.config.get("trace_type", "production_derived"),
            "provenance": [{
                "id": provenance_id,
                "source_id": context.source_id,
                "snapshot_id": context.snapshot_id,
                "source_record_ref": record.source_record_ref,
                "adapter_version": self.version,
            }],
            "templates": [template.model_dump()],
            "metrics": [],
        }

        def metric(name, value, unit, scope, aggregation, rule, missing=None):
            identity = stable_id(context.source_id, "metric", context.source_id, record.source_record_ref, scope, name, aggregation)
            if value is None:
                doc["metrics"].append(Metric(
                    id=identity, provenance_id=provenance_id,
                    name=name, value=None, unit=unit,
                    scope_id=scope, aggregation=aggregation,
                    denominator="template; N=" + str(N),
                    evidence="unavailable",
                    source_field_or_rule=rule,
                    missing_reason=missing or "not_recorded",
                ).model_dump())
            else:
                doc["metrics"].append(Metric(
                    id=identity, provenance_id=provenance_id,
                    name=name, value=value, unit=unit,
                    scope_id=scope, aggregation=aggregation,
                    denominator="template; N=" + str(N),
                    evidence="template_parameter",
                    source_field_or_rule=rule,
                ).model_dump())

        metric("model_request_count", lengths["model_request_count"], "count", template_id, "template_expansion",
               "N+1: " + str(N) + " tool-use turns")
        metric("total_input_tokens", lengths["total_input"], "token", template_id, "template_arithmetic",
               "sum(I[0:N+1]) where I[0]=initial, I[i+1]=I[i]+O[i]+R[i]",
               missing="not_recorded" if lengths["total_input"] is None else None)
        metric("max_context_tokens", lengths["max_context"], "token", template_id, "template_arithmetic",
               "max(contexts) where contexts = [I[0..N+1]]",
               missing="not_recorded" if lengths["max_context"] is None else None)
        metric("total_output_tokens", lengths["total_output"], "token", template_id, "template_arithmetic",
               "sum(O[0:N-1]) + final; O[i]=assistant_response_length[i]; final separate",
               missing="not_recorded" if lengths["total_output"] is None else None)

        for i, ctx in enumerate(lengths["context_inputs"]):
            metric("completion_context", ctx, "token", template_id, f"completion:{i}",
                   "I[{}]".format(i),
                   missing="not_recorded" if ctx is None else None)
        for i, d in enumerate(latency):
            metric("simulated_tool_delay", d, "s", template_id, f"tool_turn:{i}",
                   "tool_call_latency[{}]; simulated, not measured CPU".format(i),
                   missing="not_recorded" if d is None else None)

        total_delay = sum(d for d in latency if d is not None)
        if None not in latency:
            metric("total_simulated_delay", total_delay, "s", template_id, "template_sum",
                   "sum(tool_call_latency); simulated wait budget, not E2E or Tool CPU")
        else:
            metric("total_simulated_delay", None, "s", template_id, "template_sum",
                   "computed from turn delays; null if any delay unknown",
                   missing="not_recorded")

        metric("run_elapsed", None, "ns", template_id, "template_parameter",
               "not supplied by template format", missing="unsupported")
        metric("local_cpu_time", None, "ns", template_id, "template_parameter",
               "not supplied by template format", missing="unsupported")

        return TraceDocument.model_validate(doc)