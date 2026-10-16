"""TOOLSANDBOX-RESOURCE-PILOT-01 worker.

Runs ONE official ToolSandbox scenario in this process through the real
official chain — role message conversion and response handling, Scenario.play,
the official ExecutionEnvironment (including parallel-call permutation
execution) and the official evaluator — with an injected model transport
(either an offline scripted fake or a configured OpenAI-compatible client).

Topology: this module is spawned as a subprocess by the entry. Agent model
client, user-simulator model client, tool execution and evaluator all share
THIS process; every resource window is therefore a shared-scope window and is
never attributed exclusively to a single tool.

Retry policy (single explicit layer; deviation from official defaults is
registered in the entry identity): the openai client is constructed with
max_retries=0 and this module counts every attempt itself. The official
tenacity decorators are NOT inherited because model_inference is overridden;
logical model calls are counted outside the retry loop and per role.

Credentials are never read here: a real route only receives the client built
by the entry-injected configuration, and the offline fake never touches the
network.
"""
from __future__ import annotations

import argparse
import datetime
import enum
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

RETRY_EXCEPTION_NAMES = ("APIConnectionError", "RateLimitError", "InternalServerError")
WORKER_SCHEMA = "toolsandbox-pilot-worker-result-v1"


class ModelBudgetExhausted(RuntimeError):
    """Raised BEFORE any transport attempt when a role's logical-call cap is hit."""

    def __init__(self, role: str, limit: int):
        super().__init__(f"{role} logical model call cap {limit} reached")
        self.role = role
        self.limit = limit


class SoftDeadlineExceeded(RuntimeError):
    """Raised before a transport attempt once the shared work deadline passed."""


class PhaseDeadlineExceeded(SoftDeadlineExceeded):
    def __init__(self, phase: str, deadline_kind: str):
        super().__init__(f"{phase}: {deadline_kind}")
        self.phase = phase
        self.deadline_kind = deadline_kind


def _json_value(value):
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        return _json_value(value.item())
    return {"unavailable_type": type(value).__name__}


def save_scenario_context(path: Path, scenario, mods: dict, scenario_name: str,
                          started_utc: str, completed_utc: str) -> dict:
    """Persist actual time-sensitive initial state and evaluator targets."""
    ec = mods["execution_context"]
    relevant = {
        "send_message_with_contact_content_cellular_off": ["SETTING", "CONTACT", "MESSAGING", "SANDBOX"],
        "add_reminder_content_and_week_delta_and_time": ["REMINDER", "SANDBOX"],
        "modify_contact_with_message_recency_multiple_user_turn": ["CONTACT", "MESSAGING", "SANDBOX"],
    }[scenario_name]
    initial_state = {}
    for name in relevant:
        namespace = ec.DatabaseNamespace[name]
        frame = scenario.starting_context.get_database(
            namespace=namespace, drop_sandbox_message_index=False,
            get_all_history_snapshots=True)
        initial_state[name] = _json_value(frame.to_dicts())
    milestones = []
    matcher = scenario.evaluation.milestone_matcher
    for milestone_index, milestone in enumerate(matcher.milestones):
        constraints = []
        for constraint in milestone.snapshot_constraints:
            frame = constraint.target_dataframe
            constraints.append({
                "database_namespace": _json_value(constraint.database_namespace),
                "target_rows": _json_value(frame.to_dicts()) if frame is not None else None,
            })
        milestones.append({"index": milestone_index, "constraints": constraints})
    local_now = datetime.datetime.now().astimezone()
    record = {
        "scenario_name": scenario_name,
        "initialization_started_utc": started_utc,
        "initialization_completed_utc": completed_utc,
        "local_timezone_name": local_now.tzname(),
        "local_timezone_utc_offset_seconds": (local_now.utcoffset().total_seconds()
                                                if local_now.utcoffset() is not None else None),
        "timezone_basis": "official sources use naive datetime.now() and datetime.timestamp(); recorded host local timezone applies",
        "max_messages": scenario.max_messages,
        "tool_allow_list": list(scenario.starting_context.tool_allow_list or []),
        "tool_deny_list": list(scenario.starting_context.tool_deny_list or []),
        "initial_state": initial_state,
        "evaluation_milestone_targets": milestones,
        "uuid_behavior": "official scenario source uses deterministic_uuid (uuid5) for identified initial rows; actual IDs retained in initial_state",
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n")
    return record


def begin_phase(boundaries, name: str, limit_s: float, common_deadline_ns: int) -> int:
    """Persist the actual phase start BEFORE entering its blocking function."""
    start_ns = time.monotonic_ns()
    deadline_ns = min(start_ns + int(limit_s * 1e9), common_deadline_ns)
    kind = "common_work_deadline" if common_deadline_ns <= deadline_ns else f"{name}_deadline"
    fields = {"phase_start_ns": start_ns, "phase_deadline_ns": deadline_ns,
              "common_work_deadline_ns": common_deadline_ns, "deadline_kind": kind}
    if deadline_ns <= start_ns:
        boundaries.write(name + "_not_started", fields)
        raise PhaseDeadlineExceeded(name, kind)
    boundaries.write(name + "_begin", fields)
    return deadline_ns


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ScriptedTransport:
    """Offline fake transport for one role; drives the real official chain.

    Responses are scripted per logical call. ``http_status`` entries simulate
    API errors (exercising the retry layer); ``sleep_s`` entries block inside
    the transport to exercise the hard deadline. Nothing here touches the
    network: httpx.MockTransport answers directly.
    """

    def __init__(self, script: list[dict]):
        self.script = [dict(s) for s in script]
        self.request_count = 0
        self.request_bodies: list[dict] = []
        self.transport = None
        import httpx

        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request):
        self.request_count += 1
        try:
            body = json.loads(request.content)
        except ValueError:
            body = {}
        self.request_bodies.append({"url": str(request.url),
                                    "message_count": len(body.get("messages", [])),
                                    "model": body.get("model")})
        if not self.script:
            return _json_response(500, {"error": {"message": "fake script exhausted",
                                                  "type": "server_error"}})
        spec = self.script.pop(0)
        if "sleep_s" in spec:
            time.sleep(spec["sleep_s"])
        if "http_status" in spec:
            return _json_response(spec["http_status"],
                                  {"error": {"message": spec.get("error_message", "fake api error"),
                                             "type": "server_error"}})
        message = {"role": "assistant", "content": spec.get("content")}
        finish = "stop"
        if spec.get("tool_calls"):
            message["tool_calls"] = spec["tool_calls"]
            finish = "tool_calls"
        return _json_response(200, {
            "id": spec.get("response_id", f"chatcmpl-fake-{self.request_count}"),
            "object": "chat.completion", "created": 1,
            "model": spec.get("model", "fake-model"),
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": spec.get("usage", {"prompt_tokens": 10, "completion_tokens": 5,
                                        "total_tokens": 15}),
        })


def _json_response(status: int, body: dict):
    import httpx

    return httpx.Response(status, json=body)


def construct_openai_role_clients(openai_mod, *, base_url: str, api_key: str):
    """Construct the two production OpenAI clients with the frozen SDK policy."""
    clients = []
    try:
        clients.append(openai_mod.OpenAI(base_url=base_url, api_key=api_key,
                                        max_retries=0))
        clients.append(openai_mod.OpenAI(base_url=base_url, api_key=api_key,
                                        max_retries=0))
        return clients[0], clients[1]
    except Exception:
        for client in clients:
            client.close()
        raise


class WorkerBudget:
    """Per-role logical model-call caps, checked BEFORE any transport attempt."""

    def __init__(self, caps: dict):
        self.caps = {"agent": int(caps["agent_logical_calls"]),
                     "user": int(caps["user_logical_calls"])}
        self.counts = {"agent": 0, "user": 0}

    def check_and_count(self, role: str) -> int:
        if self.counts[role] >= self.caps[role]:
            raise ModelBudgetExhausted(role, self.caps[role])
        self.counts[role] += 1
        return self.counts[role]


class CallRegistry:
    """Logical tool-call spans: opened at proposal, closed at batch result.

    Agent proposals carry openai_tool_call_id. The official
    OpenAIAPIUser.respond OMITS openai_tool_call_id on tool-call messages, so
    user proposals are keyed by the model-emitted tool_call.id recovered from
    the response, in emission order, and closed FIFO against the id-less
    execution-environment responses addressed to the user.
    """

    def __init__(self, recorder):
        self.recorder = recorder
        self.open_calls: dict[str, dict] = {}   # message call id -> span info
        self.user_calls: dict[str, str] = {}    # model-emitted id -> span id (ordered)
        self.results: dict[str, dict] = {}

    @staticmethod
    def _error_class(message) -> str | None:
        """Exception class from the official tool_call_exception tail line."""
        text = message.tool_call_exception
        if not text:
            return None
        head = text.strip().splitlines()[-1].split(":", 1)[0].strip()
        return head or "ToolExecutionError"

    @classmethod
    def _result_record(cls, message) -> dict:
        result = (message.content or "").encode("utf-8")
        error_class = cls._error_class(message)
        return {"ok": error_class is None,
                "result_bytes": len(result), "result_sha256": _sha256_bytes(result),
                "error": error_class}

    def begin_call(self, role: str, message, request_id, argument_json: str):
        args = (argument_json or "").encode("utf-8")
        span = self.recorder.begin("tool_call", {
            "role": role, "request_event_id": request_id,
            "tool_name": message.openai_function_name,
            "argument_bytes": len(args), "argument_sha256": _sha256_bytes(args)})
        self.open_calls[message.openai_tool_call_id] = {"span": span, "role": role}

    def begin_user_call(self, request_id, spec: dict):
        args = (spec.get("arguments") or "").encode("utf-8")
        span = self.recorder.begin("tool_call", {
            "role": "user", "request_event_id": request_id,
            "tool_name": spec.get("name"),
            "argument_bytes": len(args), "argument_sha256": _sha256_bytes(args)})
        self.user_calls[spec["id"]] = span

    def close_call(self, message):
        record = self._result_record(message)
        self.results[message.openai_tool_call_id] = record
        info = self.open_calls.pop(message.openai_tool_call_id, None)
        if info is not None:
            self.recorder.end(info["span"],
                               attrs={**{k: v for k, v in record.items() if k != "error"},
                                      "role": info["role"]},
                               error=record["error"])

    def close_oldest_user_call(self, message):
        for key, span in list(self.user_calls.items()):
            record = self._result_record(message)
            self.results[key] = record
            del self.user_calls[key]
            self.recorder.end(span,
                               attrs={**{k: v for k, v in record.items() if k != "error"},
                                      "role": "user"},
                               error=record["error"])
            return
        raise KeyError("no open user tool call to close")

    def batch_call_ids(self, pending_messages) -> list:
        """Message call ids; id-less (user) messages map to open user keys in order."""
        ids = []
        user_iter = iter(list(self.user_calls))
        for m in pending_messages:
            if m.openai_tool_call_id:
                ids.append(m.openai_tool_call_id)
            else:
                ids.append(next(user_iter, None))
        return ids

    def batch_results(self, call_ids) -> dict:
        return {cid: self.results.get(cid) for cid in call_ids}


def load_tool_sandbox(source_root: str, manifest_path: str):
    """Verify the frozen source manifest, then import the official modules.

    Only JSON parsing and hashing happen here; no code from the data is
    executed and the reference tree is never touched.
    """
    manifest = json.loads(Path(manifest_path).read_text())
    root = Path(source_root)
    for entry in manifest["files"]:
        p = root / entry["path"]
        data = p.read_bytes()
        if len(data) != entry["bytes"] or _sha256_bytes(data) != entry["sha256"]:
            raise ValueError(f"frozen source drift: {entry['path']}")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tool_sandbox.common import execution_context as execution_context_mod
    from tool_sandbox.common import scenario as scenario_mod
    from tool_sandbox.common import utils as utils_mod
    from tool_sandbox.common.tool_discovery import ToolBackend
    from tool_sandbox.roles import base_role as base_role_mod
    from tool_sandbox.roles import execution_environment as execution_environment_mod
    from tool_sandbox.roles import openai_api_agent as openai_api_agent_mod
    from tool_sandbox.roles import openai_api_user as openai_api_user_mod
    from tool_sandbox.scenarios import named_scenarios
    import attrs
    import openai as openai_mod

    return {"execution_context": execution_context_mod, "scenario": scenario_mod,
            "utils": utils_mod, "ToolBackend": ToolBackend, "base_role": base_role_mod,
            "execution_environment": execution_environment_mod,
            "openai_api_agent": openai_api_agent_mod, "openai_api_user": openai_api_user_mod,
            "named_scenarios": named_scenarios, "attrs": attrs, "openai": openai_mod}


class BoundaryWriter:
    """Phase-boundary reads of THIS process's /proc counters."""

    def __init__(self, path: Path):
        from ..collectors.host_process import HostProcessReader

        self.path = path
        self.reader = HostProcessReader(os.getpid())

    def write(self, phase: str, extra: dict | None = None) -> None:
        snap = self.reader.read()
        row = {"phase": phase, "t_monotonic_ns": snap.t_monotonic_ns,
               "pid": snap.pid, "starttime_ticks": snap.starttime_ticks,
               "cpu_ticks": snap.cpu_ticks, "user_ticks": snap.user_ticks,
               "system_ticks": snap.system_ticks, "rss_bytes": snap.rss_bytes,
               "minor_faults": snap.minor_faults, "major_faults": snap.major_faults,
               "threads": snap.threads, "process_io": snap.process_io,
               "context_switches": snap.context_switches,
               "read_status": snap.read_status}
        if extra:
            row.update(extra)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


def build_roles(mods, recorder, budget, retry_cfg, registry, boundaries,
                work_deadline_ns: int, phase_deadline: dict):
    """Create the routed Agent/User classes and the instrumented environment.

    The official constructors of the two API roles are deliberately NOT
    invoked: they hardcode ``base_url="https://api.openai.com/v1"``. The
    injected client is the only client ever constructed for each role.
    """
    BaseRole = mods["base_role"].BaseRole
    RoleType = mods["execution_context"].RoleType
    retry_exceptions = tuple(getattr(mods["openai"], name) for name in RETRY_EXCEPTION_NAMES)
    all_logging_disabled = mods["utils"].all_logging_disabled

    def make_api_role(base_cls, role_name):
        class RoutedRole(base_cls):
            pilot_role = role_name

            def __init__(self, client, model_name):
                self.openai_client = client
                self.model_name = model_name
                self._last_request_id = None
                self._last_arguments = {}
                self._last_unkeyed = []

            def model_inference(self, openai_messages, openai_tools):
                if time.monotonic_ns() >= work_deadline_ns:
                    raise SoftDeadlineExceeded("work deadline passed before request")
                call_number = budget.check_and_count(role_name)
                request_id = f"{role_name}-{call_number}"
                self._last_request_id = request_id
                self._last_arguments = {}
                span = recorder.begin("llm_request", {
                    "request_id": request_id, "step_index": call_number,
                    "role": role_name, "model": self.model_name,
                    "context_message_count": len(openai_messages),
                    "context_characters": sum(len(str(m.get("content") or "")) for m in openai_messages),
                    "retry_scope": "single_explicit_layer_sdk_max_retries_0"})
                attempts = 0
                try:
                    while True:
                        if time.monotonic_ns() >= min(work_deadline_ns, phase_deadline["deadline_ns"]):
                            raise PhaseDeadlineExceeded("play", phase_deadline["deadline_kind"])
                        attempts += 1
                        try:
                            with all_logging_disabled():
                                response = self.openai_client.chat.completions.create(
                                    model=self.model_name, messages=openai_messages,
                                    tools=openai_tools)
                            break
                        except retry_exceptions:
                            if attempts >= int(retry_cfg["max_attempts_per_logical_call"]):
                                raise
                            time.sleep(min(float(retry_cfg["backoff_base_s"]) * (2 ** (attempts - 1)),
                                           float(retry_cfg["backoff_cap_s"])))
                except BaseException as exc:
                    recorder.end(span, attrs={"transport_attempt_count": attempts},
                                 error=type(exc).__name__)
                    raise
                # stash raw model-emitted tool call arguments for the registry
                choice = response.choices[0] if response.choices else None
                self._last_unkeyed = []
                if choice is not None and choice.message.tool_calls:
                    for tool_call in choice.message.tool_calls:
                        self._last_arguments[tool_call.id] = tool_call.function.arguments
                        self._last_unkeyed.append({"id": tool_call.id,
                                                   "name": tool_call.function.name,
                                                   "arguments": tool_call.function.arguments})
                usage = None
                if response.usage is not None:
                    usage = {"prompt_tokens": response.usage.prompt_tokens,
                             "completion_tokens": response.usage.completion_tokens,
                             "total_tokens": response.usage.total_tokens}
                    usage.update(response.usage.model_extra or {})
                recorder.end(span, attrs={
                    "transport_attempt_count": attempts,
                    "response_model": response.model, "response_id": response.id,
                    "usage": usage, "cost_status": "unknown_not_billing_evidence",
                    "timing_source": "native_event"})
                return response

            def add_messages(self, messages):
                for m in messages:
                    if m.recipient != RoleType.EXECUTION_ENVIRONMENT:
                        continue
                    if m.openai_tool_call_id:
                        registry.begin_call(role_name, m, self._last_request_id,
                                            self._last_arguments.get(m.openai_tool_call_id))
                    elif role_name == "user" and self._last_unkeyed:
                        # Official OpenAIAPIUser.respond omits openai_tool_call_id;
                        # recover the model-emitted id/arguments in emission order.
                        spec = self._last_unkeyed.pop(0)
                        registry.begin_user_call(self._last_request_id, spec)
                BaseRole.add_messages(messages)

        return RoutedRole

    execution_environment_mod = mods["execution_environment"]
    ordering_counter = {"executions": 0}

    def _wrap_respond_to_messages(fn):
        def wrapper(*args, **kwargs):
            ordering_counter["executions"] += 1
            return fn(*args, **kwargs)
        return wrapper

    execution_environment_mod.respond_to_messages = _wrap_respond_to_messages(
        execution_environment_mod.respond_to_messages)

    class InstrumentedEnvironment(execution_environment_mod.ExecutionEnvironment):
        def __init__(self):
            self._batch_index = 0
            self._reader = boundaries.reader

        def _read_counters(self) -> dict:
            snap = self._reader.read()
            return {"t_monotonic_ns": snap.t_monotonic_ns, "cpu_ticks": snap.cpu_ticks,
                    "user_ticks": snap.user_ticks, "system_ticks": snap.system_ticks,
                    "rss_bytes": snap.rss_bytes, "threads": snap.threads,
                    "process_io": snap.process_io,
                    "context_switches": snap.context_switches,
                    "read_status": snap.read_status}

        def respond(self, ending_index=None):
            if ending_index is not None:
                boundaries.write("system_setup_exec", {"ending_index": ending_index})
                return super().respond(ending_index=ending_index)
            messages = self.get_messages()
            pending = execution_environment_mod.get_messages_to_process(
                messages, recipient=self.role_type)
            call_ids = registry.batch_call_ids(pending)
            tool_names = [m.openai_function_name for m in pending]
            before = self._read_counters()
            executions_before = ordering_counter["executions"]
            self._batch_index += 1
            batch_index = self._batch_index
            span = recorder.begin("tool_batch", {
                "batch_index": batch_index, "call_ids": call_ids,
                "tool_names": tool_names,
                "attribution_method": "shared_scope_window"})
            error = None
            try:
                super().respond()
            except BaseException as exc:
                error = type(exc).__name__
                raise
            finally:
                after = self._read_counters()
                executed = ordering_counter["executions"] - executions_before
                recorder.end(span, attrs={
                    "resource_before": before, "resource_after": after,
                    "planned_orderings": (math.factorial(len(pending)) if len(pending) > 1 else 1),
                    "executed_orderings": executed}, error=error)

        def add_messages(self, messages):
            for m in messages:
                if m.sender != RoleType.EXECUTION_ENVIRONMENT:
                    continue
                if m.openai_tool_call_id:
                    registry.close_call(m)
                elif m.recipient == RoleType.USER:
                    registry.close_oldest_user_call(m)
            BaseRole.add_messages(messages)

    return make_api_role, InstrumentedEnvironment, ordering_counter


def _tool_trace_name(raw) -> str | None:
    """Native tool name from a SANDBOX tool_trace cell (list of JSON strings)."""
    if raw in (None, "null", "None", ""):
        return None
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        if isinstance(item, str):
            try:
                j = json.loads(item)
            except ValueError:
                continue
            if isinstance(j, dict) and isinstance(j.get("tool_name"), str):
                return j["tool_name"]
        elif isinstance(item, dict) and isinstance(item.get("tool_name"), str):
            return item["tool_name"]
    return None


def _analyze_stop(mods) -> dict:
    """Stop condition from the official ending context (no success inference).

    The user simulator's end_conversation request carries no
    openai_function_name in the official implementation; the reliable evidence
    is the tool_trace recorded on the execution-environment response row (all
    such rows are user-side; the agent never sees end_conversation).
    """
    execution_context_mod = mods["execution_context"]
    ctx = execution_context_mod.get_current_context()
    db = ctx.get_database(execution_context_mod.DatabaseNamespace.SANDBOX,
                          drop_sandbox_message_index=False, get_all_history_snapshots=True)
    conversation_active = bool(db["conversation_active"][-1])
    user_end_conversation = any(
        _tool_trace_name(cell) == "end_conversation" for cell in db["tool_trace"].to_list())
    return {"conversation_active": conversation_active,
            "user_end_conversation_executed": user_end_conversation,
            "reason": ("user_end_conversation" if user_end_conversation and not conversation_active
                       else "conversation_still_active" if conversation_active else "ended_other")}


def _batch_and_call_summary(events_path: Path) -> dict:
    batches = {"started": 0, "closed": 0, "error": 0, "unclosed": 0}
    calls = {"started": 0, "closed": 0, "error": 0, "unclosed": 0}
    if events_path.is_file():
        for line in events_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            kind = e.get("kind")
            if kind not in ("tool_batch", "tool_call"):
                continue
            target = batches if kind == "tool_batch" else calls
            status = e.get("status")
            if status == "open":
                target["started"] += 1
            elif status in ("closed", "error", "unclosed"):
                target[status] += 1
    return {"tool_batches": batches, "logical_tool_calls": calls}


def run_job(job: dict) -> int:
    """Run one official scenario with the injected transport; return exit code."""
    from ..collectors.semantic_recorder import SemanticRecorder, SystemClock
    from ..collectors.execution_measurement import span_coverage

    run_dir = Path(job["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    clock = SystemClock()
    recorder = SemanticRecorder(run_dir, clock, run_id=job["run_id"],
                                attempt_id=job["run_id"], task_id=job["scenario_name"],
                                source_type="benchmark_real")
    boundaries = BoundaryWriter(run_dir / "boundaries.jsonl")
    # Run markers are written BEFORE the (slow) official source import so a
    # deadline kill during environment preparation still leaves evidence.
    recorder.begin_run()
    boundaries.write("worker_start", {"transport_kind": job["transport"]["kind"]})
    boundaries.write("imports_begin")
    registry = CallRegistry(recorder)
    budget = WorkerBudget(job["budgets"])
    retry_cfg = job["retry"]
    mods = load_tool_sandbox(job["source_root"], job["source_manifest"])
    boundaries.write("imports_end")
    scenario_init_start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    scenario = mods["named_scenarios"](mods["ToolBackend"].DEFAULT)[job["scenario_name"]]
    official_max_messages = scenario.max_messages
    scenario.max_messages = int(job["budgets"].get("max_messages", official_max_messages))
    initial_max_index = scenario.starting_context.max_sandbox_message_index
    save_scenario_context(run_dir / "scenario_context.json", scenario, mods,
                          job["scenario_name"], scenario_init_start,
                          datetime.datetime.now(datetime.timezone.utc).isoformat())

    # The parent start precedes spawn/imports/setup; entering a phase never resets it.
    work_deadline_ns = job["common_work_deadline_ns"]
    phase_deadline = {"deadline_ns": work_deadline_ns, "deadline_kind": "common_work_deadline"}

    make_api_role, InstrumentedEnvironment, ordering_counter = build_roles(
        mods, recorder, budget, retry_cfg, registry, boundaries, work_deadline_ns, phase_deadline)

    transport = job["transport"]
    import httpx
    import openai as openai_mod

    clients = []
    agent_fake = user_fake = None
    fakes = None
    model_name = (transport.get("model_name", "fake-request-model")
                  if transport["kind"] == "fake" else transport.get("model"))
    route_note = ("offline fake transport; no network; request model is a label"
                  if transport["kind"] == "fake" else
                  "real OpenAI-compatible route; transport attempts counted by worker layer")
    try:
        if transport["kind"] == "fake":
            agent_fake = ScriptedTransport(transport["script"]["agent"])
            user_fake = ScriptedTransport(transport["script"]["user"])
            if transport.get("simulate_client_init_failure"):
                raise TypeError("synthetic default-client construction failure")
            agent_client = openai_mod.OpenAI(
                base_url="http://127.0.0.1:9/v1", api_key="offline-fake", max_retries=0,
                http_client=httpx.Client(transport=agent_fake.transport))
            user_client = openai_mod.OpenAI(
                base_url="http://127.0.0.1:9/v1", api_key="offline-fake", max_retries=0,
                http_client=httpx.Client(transport=user_fake.transport))
            clients = [agent_client, user_client]
            fakes = {"agent": agent_fake, "user": user_fake}
        elif transport["kind"] == "openai_compatible":
            # Real route: credential read happens HERE and only in this branch.
            api_key = os.environ.get(transport["api_key_env"])
            if not api_key:
                print(json.dumps({"status": "REFUSED", "reason": "missing api key env"}),
                      file=sys.stderr)
                return 2
            agent_client, user_client = construct_openai_role_clients(
                openai_mod, base_url=transport["base_url"], api_key=api_key)
            clients = [agent_client, user_client]
        else:
            raise ValueError(f"unknown transport kind: {transport['kind']}")
    except Exception as exc:
        error_type = type(exc).__name__
        recorder.point("infra", {"status": "error",
                                  "detail": "openai_client_initialization:" + error_type})
        print("OpenAI client initialization failed: " + error_type, file=sys.stderr)
        for client in clients:
            client.close()
        boundaries.write("worker_end", {"exit_code": 5})
        recorder.seal()
        events_path = run_dir / "events.jsonl"
        result_record = {
            "schema": WORKER_SCHEMA, "run_id": job["run_id"],
            "scenario_name": job["scenario_name"],
            "transport": {"kind": transport["kind"], "note": route_note,
                          "request_model_label": model_name,
                          "stats": ({"agent_requests": agent_fake.request_count,
                                     "user_requests": user_fake.request_count}
                                    if agent_fake is not None and user_fake is not None else None)},
            "budgets": {**job["budgets"], "official_max_messages_default": official_max_messages},
            "retry": {**retry_cfg, "retry_on": list(RETRY_EXCEPTION_NAMES)},
            "stop": None, "initial_max_sandbox_message_index": initial_max_index,
            "final_max_sandbox_message_index": None,
            "counts": {"agent_logical_calls": 0, "user_logical_calls": 0,
                       "tool_call_executions": 0,
                       **_batch_and_call_summary(events_path)},
            "evaluation": None,
            "failure": {"kind": "infra_error", "phase": "client_initialization",
                        "error_type": error_type},
            "worker_exit_code": 5,
            "measurement": {"span_coverage": span_coverage(events_path)},
            "known_nondeterminism": job.get("known_nondeterminism"),
        }
        (run_dir / "result.json").write_text(
            json.dumps(result_record, ensure_ascii=False, indent=1) + "\n")
        return 5

    RoleType = mods["execution_context"].RoleType
    agent_cls = make_api_role(mods["openai_api_agent"].OpenAIAPIAgent, "agent")
    user_cls = make_api_role(mods["openai_api_user"].OpenAIAPIUser, "user")
    roles = {RoleType.USER: user_cls(user_client, model_name),
             RoleType.EXECUTION_ENVIRONMENT: InstrumentedEnvironment(),
             RoleType.AGENT: agent_cls(agent_client, model_name)}

    # Wrap the actual play method, not play_and_evaluate (which also serializes/evaluates).
    scenario_cls = type(scenario)
    original_play = scenario_cls.play

    def wrapped_play(self, *args, **kwargs):
        deadline_ns = begin_phase(boundaries, "play", float(job["budgets"]["play_s"]), work_deadline_ns)
        phase_deadline.update(deadline_ns=deadline_ns,
                              deadline_kind="common_work_deadline" if deadline_ns == work_deadline_ns else "play_deadline")
        try:
            result = original_play(self, *args, **kwargs)
            if time.monotonic_ns() >= deadline_ns:
                raise PhaseDeadlineExceeded("play", phase_deadline["deadline_kind"])
            return result
        finally:
            boundaries.write("play_end", {"phase_end_ns": time.monotonic_ns()})

    scenario_cls.play = wrapped_play

    # Phase boundaries around the official evaluator, without replacing it.
    # Evaluation is an attrs slots class, so instance attribute assignment is
    # blocked; the wrap happens at class level (exactly one scenario runs per
    # worker, making the class wrap equivalent to an instance wrap).
    evaluation_cls = type(scenario.evaluation)
    original_evaluate = evaluation_cls.evaluate
    def wrapped_evaluate(self, *args, **kwargs):
        # Offline fixture can consume common work time before the stage begins.
        if transport["kind"] == "fake" and "evaluate_start_remaining_s" in transport:
            delay = (work_deadline_ns-time.monotonic_ns())/1e9 - transport["evaluate_start_remaining_s"]
            if delay > 0:
                time.sleep(delay)
        deadline_ns = begin_phase(boundaries, "evaluate", float(job["budgets"]["evaluate_s"]), work_deadline_ns)
        try:
            # Offline-only blocking fixture, analogous to ScriptedTransport.sleep_s.
            if transport["kind"] == "fake" and transport.get("evaluate_sleep_s"):
                time.sleep(transport["evaluate_sleep_s"])
            result = original_evaluate(self, *args, **kwargs)
            if time.monotonic_ns() >= deadline_ns:
                raise PhaseDeadlineExceeded("evaluate", "common_work_deadline" if deadline_ns == work_deadline_ns else "evaluate_deadline")
            return result
        finally:
            boundaries.write("evaluate_end", {"phase_end_ns": time.monotonic_ns()})

    evaluation_cls.evaluate = wrapped_evaluate

    exit_code = 0
    evaluation_dict = None
    stop = None
    failure = None
    result_obj = None
    try:
        result_obj = scenario.play_and_evaluate(
            roles=roles, output_directory=run_dir / "official",
            scenario_name=job["scenario_name"])
        evaluation_dict = mods["attrs"].asdict(result_obj.evaluation_result)
        stop = _analyze_stop(mods)
    except ModelBudgetExhausted as exc:
        recorder.point("budget", {"limit_name": f"{exc.role}_logical_calls",
                                  "observed": exc.limit,
                                  "detail": "request refused before any transport attempt"})
        exit_code = 3
        failure = {"kind": "model_budget_exhausted", "role": exc.role, "limit": exc.limit}
    except PhaseDeadlineExceeded as exc:
        recorder.point("budget", {"limit_name": exc.deadline_kind,
                                  "detail": "phase refused/stopped before next blocking call"})
        exit_code = 4
        failure = {"kind": "phase_deadline_exceeded", "phase": exc.phase,
                   "deadline_kind": exc.deadline_kind}
    except SoftDeadlineExceeded as exc:
        recorder.point("budget", {"limit_name": "work_deadline",
                                  "observed": "exceeded",
                                  "detail": "checked before transport attempt"})
        exit_code = 4
        failure = {"kind": "soft_deadline_exceeded", "detail": str(exc)}
    except BaseException as exc:  # official play failure; partial outputs kept
        recorder.point("infra", {"status": "error", "detail": type(exc).__name__})
        import traceback
        traceback.print_exc(file=sys.stderr)
        exit_code = 5
        failure = {"kind": "infra_error", "error_type": type(exc).__name__}
        try:
            stop = _analyze_stop(mods)
        except Exception:
            stop = None
    finally:
        for client in clients:
            client.close()
        boundaries.write("worker_end", {"exit_code": exit_code})
        recorder.seal()

    events_path = run_dir / "events.jsonl"
    coverage = span_coverage(events_path)
    result_record = {
        "schema": WORKER_SCHEMA,
        "run_id": job["run_id"], "scenario_name": job["scenario_name"],
        "transport": {"kind": transport["kind"], "note": route_note,
                      "request_model_label": model_name,
                      "stats": ({"agent_requests": fakes["agent"].request_count,
                                 "user_requests": fakes["user"].request_count}
                                if fakes is not None else
                                {"agent_requests": None, "user_requests": None,
                                 "note": "per-logical-call attempt counts live on llm_request spans; no transport-level hook"})},
        "budgets": {**job["budgets"], "official_max_messages_default": official_max_messages},
        "retry": {**retry_cfg, "retry_on": list(RETRY_EXCEPTION_NAMES)},
        "stop": stop,
        "initial_max_sandbox_message_index": initial_max_index,
        "final_max_sandbox_message_index": (
            mods["execution_context"].get_current_context().max_sandbox_message_index
            if stop is not None else None),
        "counts": {"agent_logical_calls": budget.counts["agent"],
                   "user_logical_calls": budget.counts["user"],
                   "tool_call_executions": ordering_counter["executions"],
                   **_batch_and_call_summary(events_path)},
        "evaluation": evaluation_dict,
        "failure": failure,
        "worker_exit_code": exit_code,
        "measurement": {"span_coverage": coverage},
        "known_nondeterminism": job.get("known_nondeterminism"),
    }
    (run_dir / "result.json").write_text(
        json.dumps(result_record, ensure_ascii=False, indent=1) + "\n")
    return exit_code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TOOLSANDBOX-RESOURCE-PILOT-01 worker")
    parser.add_argument("job", help="path to the job JSON written by the entry")
    args = parser.parse_args(argv)
    job = json.loads(Path(args.job).read_text())
    return run_job(job)


if __name__ == "__main__":
    raise SystemExit(main())
