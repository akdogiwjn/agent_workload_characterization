"""Shared metric registry for macro and coverage (P0-08/09).

Every metric macro/coverage refers to is defined here once, so the two
analyzers cannot drift in filtering rules. Each entry states definition,
entity level, scope, unit, source mapping, applicability and evidence rules.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    name: str
    entity_level: str          # "run" | "template" | "request" | "unassigned_request"
    scope: str                 # "all_requests" | "main_agent" | "single_request" | "template_*"
    unit: str
    definition: str
    source_mapping: str
    evidence: tuple[str, ...]
    capability: str            # "applicable_real" | "applicable_template" | "na_template" | "capability_only"
    missing_reason_default: str | None = None


REGISTRY: list[MetricDefinition] = [
    MetricDefinition(
        key="model_request_count", name="model_request_count", entity_level="run",
        scope="all_requests", unit="count",
        definition="Number of retained model request records for this run (main/all per aggregation).",
        source_mapping="AgentX/VW proxy request records; AC template N+1 completions",
        evidence=("observed", "derived", "template_parameter"), capability="applicable_real"),
    MetricDefinition(
        key="total_input_tokens", name="total_input_tokens", entity_level="run",
        scope="all_requests", unit="token",
        definition="Sum of input_tokens across retained requests; null if any request token missing (strict).",
        source_mapping="proxy input_tokens; AC template cumulative input",
        evidence=("derived", "template_parameter"), capability="applicable_real"),
    MetricDefinition(
        key="total_output_tokens", name="total_output_tokens", entity_level="run",
        scope="all_requests", unit="token",
        definition="Sum of output_tokens across retained requests; null if any request token missing.",
        source_mapping="proxy output_tokens; AC template sum(O)+final",
        evidence=("derived", "template_parameter"), capability="applicable_real"),
    MetricDefinition(
        key="max_input_context", name="max_input_context", entity_level="run",
        scope="all_requests", unit="token",
        definition="Maximum input_tokens across retained requests; distinct from source_context_tokens.",
        source_mapping="proxy input_tokens max; AC template max context",
        evidence=("derived", "template_parameter"), capability="applicable_real"),
    MetricDefinition(
        key="max_source_context_tokens", name="max_source_context_tokens", entity_level="run",
        scope="all_requests", unit="token",
        definition="Maximum of source context_tokens (input+output at proxy); source-declared, not input context.",
        source_mapping="proxy context_tokens max",
        evidence=("derived", "observed"), capability="applicable_real"),
    MetricDefinition(
        key="total_api_latency_s", name="total_api_latency_s", entity_level="run",
        scope="all_requests", unit="s",
        definition="Sum of proxy api_latency (proxy boundary, not server inference / not E2E).",
        source_mapping="proxy api_latency sum",
        evidence=("derived", "observed"), capability="applicable_real"),
    MetricDefinition(
        key="tool_call_count", name="tool_call_count", entity_level="run",
        scope="all_requests", unit="count",
        definition="Number of tool call events with a paired result where observable.",
        source_mapping="ReAct toolCall ids; AgentX source tool_use_count when known",
        evidence=("observed", "derived"), capability="applicable_real"),
    MetricDefinition(
        key="subagent_count", name="subagent_count", entity_level="run",
        scope="all_agents", unit="count",
        definition="Number of explicit subagent groups retained (not nested count).",
        source_mapping="AgentX subagent groups",
        evidence=("observed", "derived"), capability="applicable_real"),
    MetricDefinition(
        key="observed_span", name="observed_span", entity_level="run",
        scope="all_agents", unit="ns",
        definition="Union of closed published request intervals (same clock, native_event).",
        source_mapping="AgentX request intervals (model_busy)",
        evidence=("derived",), capability="applicable_real"),
    MetricDefinition(
        key="run_elapsed", name="run_elapsed", entity_level="run",
        scope="all_requests", unit="ns",
        definition="Trusted run boundary; unavailable when no monotonic boundary evidence.",
        source_mapping="not supplied by these sources",
        evidence=("unavailable",), capability="capability_only",
        missing_reason_default="unsupported"),
    MetricDefinition(
        key="local_cpu_time", name="local_cpu_time", entity_level="run",
        scope="all_requests", unit="ns",
        definition="Local CPU time; unavailable (no system measurement in this pilot).",
        source_mapping="not supplied",
        evidence=("unavailable",), capability="capability_only",
        missing_reason_default="unsupported"),
    MetricDefinition(
        key="tool_cpu_time", name="tool_cpu_time", entity_level="run",
        scope="all_requests", unit="ns",
        definition="Tool CPU time; unavailable.",
        source_mapping="not supplied",
        evidence=("unavailable",), capability="capability_only",
        missing_reason_default="unsupported"),
]


def metric_definition(key: str) -> MetricDefinition:
    for d in REGISTRY:
        if d.key == key:
            return d
    raise KeyError(key)


# Availability rules per profile (not metric-specific capability).
PROFILE_APPLICABILITY = {
    "semantic_trace": {
        "run_elapsed": "capability_only",
        "local_cpu_time": "capability_only",
        "tool_cpu_time": "capability_only",
    },
    "macro_template": {
        "model_request_count": "applicable_template",
        "total_input_tokens": "applicable_template",
        "total_output_tokens": "applicable_template",
        "max_input_context": "applicable_template",
        "run_elapsed": "not_applicable_template",
        "local_cpu_time": "not_applicable_template",
        "tool_cpu_time": "not_applicable_template",
    },
}
