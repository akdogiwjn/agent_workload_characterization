"""Trace IR v0.2: structural models plus document-level semantic validation.

IDs are document-wide; source_record_ref is an opaque source locator, not a run ID.
JSON Schema describes structure; validate_json also checks graphs and evidence.
"""

import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.2.0"
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Count = Annotated[int, Field(ge=0)]
Missing = Literal["not_recorded", "not_applicable", "unreadable", "unresolved", "unsupported", "censored"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Provenance(Model):
    id: Text
    source_id: Text
    snapshot_id: Text
    source_record_ref: Text
    adapter_version: Text


class Clock(Model):
    id: Text
    kind: Literal["monotonic", "utc", "source_relative"]
    source: Text
    precision_ns: Annotated[int, Field(gt=0)] | None
    precision_missing_reason: Missing | None = None
    utc_anchor_ns: int | None = None
    anchor_tick_ns: int | None = None
    alignment_method: Text | None = None
    alignment_error_ns: Count | None = None
    collection_delay_ns: Count | None = None

    @model_validator(mode="after")
    def anchor(self) -> Self:
        if (self.precision_ns is None) != (self.precision_missing_reason is not None):
            raise ValueError("unknown clock precision requires a missing reason")
        fields = [self.utc_anchor_ns, self.anchor_tick_ns, self.alignment_method, self.alignment_error_ns]
        if any(x is not None for x in fields) and not all(x is not None for x in fields):
            raise ValueError("clock anchor requires both coordinates, method and error")
        return self


class Interval(Model):
    clock_id: Text
    start_ns: int | None
    end_ns: int | None
    source: Literal["native_event", "log_receipt", "adjacent_event_estimate"]
    missing_reason: Missing | None = None

    @model_validator(mode="after")
    def bounds(self) -> Self:
        incomplete = self.start_ns is None or self.end_ns is None
        if incomplete != (self.missing_reason is not None):
            raise ValueError("unknown boundary requires a missing reason; complete interval forbids it")
        if not incomplete and self.end_ns < self.start_ns:
            raise ValueError("end precedes start in one clock domain")
        return self


class Record(Model):
    id: Text
    provenance_id: Text


class Task(Record):
    pass


class Attempt(Record):
    task_id: Text
    configuration_ref: Text


class Run(Record):
    task_id: Text | None = None
    attempt_id: Text | None = None
    execution_status: Literal["unknown", "running", "completed", "failed", "cancelled", "timed_out"] = "unknown"
    evaluation_status: Literal["unknown", "not_evaluated", "passed", "failed", "error"] = "unknown"
    archive_status: Literal["unknown", "complete", "partial", "missing", "unreadable"] = "unknown"
    interval: Interval | None = None


class Association(Model):
    status: Literal["resolved", "unresolved"]
    method: Text
    evidence_ref: Text


class BoundRecord(Record):
    run_id: Text | None
    association: Association

    @model_validator(mode="after")
    def binding(self) -> Self:
        if (self.run_id is not None) != (self.association.status == "resolved"):
            raise ValueError("run_id and association status disagree")
        return self


class Agent(BoundRecord):
    parent_id: Text | None = None
    source_agent_id: Text | None = None
    source_agent_type: Text | None = None
    source_status: Text | None = None


class Prefix(Model):
    hashes: list[Text]
    block_size: Annotated[int, Field(gt=0)]
    hash_id_scope: Text


class Request(BoundRecord):
    agent_id: Text | None = None
    batch_id: Text | None = None
    interval: Interval | None = None
    prefix: Prefix | None = None
    model_name: Text | None = None
    source_request_type: Text | None = None

    @model_validator(mode="after")
    def unassigned(self) -> Self:
        if self.run_id is None and self.batch_id is None:
            raise ValueError("unassigned request needs its batch identity")
        return self


class Event(BoundRecord):
    kind: Literal["tool_call", "span", "phase", "lifecycle"]
    name: Text
    parent_id: Text | None = None
    agent_id: Text | None = None
    interval: Interval | None = None


class Job(BoundRecord):
    interval: Interval | None = None


class Session(BoundRecord):
    interval: Interval | None = None


class Process(BoundRecord):
    host_id: Text
    boot_id: Text
    pid_namespace: Text
    pid: Annotated[int, Field(gt=0)]
    start_identifier: Text


class ResourceScope(BoundRecord):
    parent_id: Text | None = None
    kind: Literal["run", "cgroup", "process", "job", "service"]
    attribution_method: Literal["exclusive_scope", "shared_scope", "window_estimate", "unresolved"]
    interval: Interval | None = None
    includes_children: bool


class Link(Model):
    source_id: Text
    target_id: Text
    kind: Literal["depends_on", "submit", "poll", "wait", "session", "scope_tool", "scope_process"]
    association: Association


class Metric(Record):
    name: Text
    value: int | float | None
    unit: Text
    scope_id: Text
    aggregation: Text
    denominator: Text
    evidence: Literal["observed", "derived", "template_parameter", "estimated", "unavailable"]
    source_field_or_rule: Text
    input_metric_ids: list[Text] = Field(default_factory=list)
    missing_reason: Missing | None = None
    semantics: Literal["quantity", "counter", "gauge", "peak"] = "quantity"
    sample_time: Interval | None = None
    counter_epoch: Text | None = None

    @model_validator(mode="after")
    def evidence_value(self) -> Self:
        if self.value is None:
            if self.evidence != "unavailable" or self.missing_reason is None:
                raise ValueError("null metric requires unavailable evidence and missing reason")
        elif self.evidence == "unavailable" or self.missing_reason is not None:
            raise ValueError("present metric cannot have unavailable evidence or missing reason")
        if self.evidence == "derived" and not self.input_metric_ids:
            raise ValueError("derived metric requires explicit inputs")
        if self.evidence == "observed" and self.input_metric_ids:
            raise ValueError("observed metric cannot be a computation")
        if self.semantics == "counter" and self.counter_epoch is None:
            raise ValueError("counter requires epoch/reset identity")
        return self


class Template(Record):
    tool_use_turns: Count
    initial_input: Count | None
    assistant_outputs: list[Count | None]
    tool_outputs: list[Count | None]
    final_output: Count | None
    unit: Literal["token", "source_length"]
    length_definition_ref: Text
    length_missing_reason: Missing | None = None

    @model_validator(mode="after")
    def lengths(self) -> Self:
        if len(self.assistant_outputs) != self.tool_use_turns or len(self.tool_outputs) != self.tool_use_turns:
            raise ValueError("template vectors must match tool_use_turns")
        missing = None in [self.initial_input, self.final_output, *self.assistant_outputs, *self.tool_outputs]
        if missing != (self.length_missing_reason is not None):
            raise ValueError("unknown template lengths require a group missing reason")
        return self


class Replay(Model):
    original_trace_ref: Text
    spec_ref: Text
    mode: Literal["open_loop", "dependency_driven", "fast_as_possible"]


def check_acyclic(edges: dict[str, list[str]], label: str) -> None:
    """Iterative DFS: bounded by graph size, not Python recursion depth."""
    done: set[str] = set()
    active: set[str] = set()
    for root in edges:
        stack = [(root, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                active.remove(node)
                done.add(node)
            elif node in active:
                raise ValueError(f"cycle in {label}")
            elif node not in done:
                active.add(node)
                stack.append((node, True))
                stack.extend((child, False) for child in edges.get(node, []))


class TraceDocument(Model):
    schema_version: Literal["0.2.0"]
    profile: Literal["macro_template", "semantic_trace", "resource_trace", "replay_trace"]
    trace_type: Literal["production", "production_derived", "benchmark_real", "oracle", "replay", "synthetic", "unknown"]
    provenance: list[Provenance] = Field(min_length=1)
    clocks: list[Clock] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    attempts: list[Attempt] = Field(default_factory=list)
    runs: list[Run] = Field(default_factory=list)
    agents: list[Agent] = Field(default_factory=list)
    requests: list[Request] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    jobs: list[Job] = Field(default_factory=list)
    sessions: list[Session] = Field(default_factory=list)
    processes: list[Process] = Field(default_factory=list)
    resource_scopes: list[ResourceScope] = Field(default_factory=list)
    templates: list[Template] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    replay: Replay | None = None

    @model_validator(mode="after")
    def semantics(self) -> Self:
        names = ("tasks", "attempts", "runs", "agents", "requests", "events", "jobs", "sessions", "processes", "resource_scopes", "templates", "metrics")
        groups = {name: getattr(self, name) for name in names}
        records = [record for group in groups.values() for record in group]
        all_objects = [*self.provenance, *self.clocks, *records]
        index = {obj.id: obj for obj in all_objects}
        if len(index) != len(all_objects):
            raise ValueError("conflicting or duplicate ID")

        def ref(identity, expected):
            if identity is not None and not isinstance(index.get(identity), expected):
                raise ValueError("dangling reference or wrong entity type")

        for record in records:
            ref(record.provenance_id, Provenance)
            if isinstance(record, BoundRecord):
                ref(record.run_id, Run)
            interval = getattr(record, "interval", None) or getattr(record, "sample_time", None)
            if interval:
                ref(interval.clock_id, Clock)
            if isinstance(record, (Request, Event)):
                ref(record.agent_id, Agent)
                if record.agent_id and index[record.agent_id].run_id != record.run_id:
                    raise ValueError("agent and record run disagree")
            if isinstance(record, (Agent, Event, ResourceScope)):
                ref(record.parent_id, type(record))
                if record.parent_id:
                    parent = index[record.parent_id]
                    if parent.run_id != record.run_id:
                        raise ValueError("containment cannot cross runs")
                    child_time, parent_time = getattr(record, "interval", None), getattr(parent, "interval", None)
                    if child_time and parent_time and child_time.clock_id == parent_time.clock_id:
                        for boundary, invalid in (("start_ns", lambda a, b: a < b), ("end_ns", lambda a, b: a > b)):
                            a, b = getattr(child_time, boundary), getattr(parent_time, boundary)
                            if a is not None and b is not None and invalid(a, b):
                                raise ValueError("child interval outside parent")
            if isinstance(record, (Run, Attempt)):
                ref(record.task_id, Task)
            if isinstance(record, Run):
                ref(record.attempt_id, Attempt)
                if record.attempt_id and index[record.attempt_id].task_id != record.task_id:
                    raise ValueError("run task and attempt task disagree")
            if isinstance(record, Metric):
                ref(record.scope_id, (Task, Attempt, Run, BoundRecord, Template))
                for identity in record.input_metric_ids:
                    ref(identity, Metric)
                    evidence = index[identity].evidence
                    if evidence == "unavailable" and record.value is not None:
                        raise ValueError("cannot compute exact value from unavailable input")
                    if evidence == "template_parameter" and record.evidence not in ("template_parameter", "unavailable"):
                        raise ValueError("template evidence cannot become measured/derived evidence")
                    if evidence == "estimated" and record.evidence not in ("estimated", "unavailable"):
                        raise ValueError("estimated input cannot become exact evidence")
        for name in ("agents", "events", "resource_scopes"):
            check_acyclic({x.id: [x.parent_id] if x.parent_id else [] for x in groups[name]}, name)
        check_acyclic({x.id: x.input_metric_ids for x in self.metrics}, "metric inputs")
        process_keys = [(p.host_id, p.boot_id, p.pid_namespace, p.pid, p.start_identifier) for p in self.processes]
        if len(set(process_keys)) != len(process_keys):
            raise ValueError("duplicate process identity")
        allowed = {"depends_on": (Event, Event), "submit": (Event, Job), "poll": (Event, Job), "wait": (Event, Job), "session": (Event, Session), "scope_tool": (ResourceScope, Event), "scope_process": (ResourceScope, Process)}
        dependencies: dict[str, list[str]] = {}
        seen_links = set()
        exclusive: dict[str, set[str]] = {}
        for link in self.links:
            ref(link.source_id, allowed[link.kind][0])
            ref(link.target_id, allowed[link.kind][1])
            source, target = index[link.source_id], index[link.target_id]
            key = (link.source_id, link.target_id, link.kind)
            if key in seen_links or link.source_id == link.target_id:
                raise ValueError("duplicate or self link")
            seen_links.add(key)
            if source.run_id != target.run_id:
                raise ValueError("links cannot silently cross runs")
            if link.kind in ("submit", "poll", "wait") and source.kind != "tool_call":
                raise ValueError("job operations require tool call")
            if link.kind == "scope_tool":
                if target.kind != "tool_call":
                    raise ValueError("scope_tool target must be tool call")
                if source.attribution_method == "exclusive_scope" and link.association.status == "resolved":
                    exclusive.setdefault(source.id, set()).add(target.id)
            if link.kind == "depends_on" and link.association.status == "resolved":
                dependencies.setdefault(source.id, []).append(target.id)
                a, b = source.interval, target.interval
                if (a and b and a.clock_id == b.clock_id
                    and a.source == b.source == "native_event"
                    and a.start_ns is not None and b.end_ns is not None
                    and a.start_ns < b.end_ns):
                    raise ValueError("dependent event starts before predecessor finishes")
        if any(len(targets) > 1 for targets in exclusive.values()):
            raise ValueError("exclusive scope cannot attribute full resource to multiple calls")
        check_acyclic(dependencies, "dependencies")
        if self.profile == "macro_template":
            if not self.templates or any(groups[n] for n in ("attempts", "runs", "agents", "requests", "events", "jobs", "sessions", "processes", "resource_scopes")) or self.clocks:
                raise ValueError("macro template requires templates and forbids fabricated execution entities")
            if any(m.evidence not in ("template_parameter", "unavailable") or m.sample_time for m in self.metrics):
                raise ValueError("template metrics cannot be execution observations")
        elif self.templates:
            raise ValueError("template and execution records require separate documents")
        if self.profile == "semantic_trace" and (self.processes or self.resource_scopes):
            raise ValueError("system entities require resource or replay profile")
        if self.profile == "resource_trace" and not (self.processes or self.resource_scopes):
            raise ValueError("resource profile requires process or scope evidence")
        if (self.profile == "replay_trace") != (self.replay is not None):
            raise ValueError("replay profile and replay provenance must agree")
        if (self.profile == "replay_trace") != (self.trace_type == "replay"):
            raise ValueError("replay results must remain labelled replay")
        return self


def validate_json(payload: str | bytes) -> TraceDocument:
    """Reject ambiguous JSON before strict structural and semantic validation."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("non-finite JSON number")

    return TraceDocument.model_validate(json.loads(payload, object_pairs_hook=pairs, parse_constant=invalid_constant))
