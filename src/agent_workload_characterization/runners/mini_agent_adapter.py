"""Agent harness adapters for the coding pilot (RUN-01).

- FakeAgentHarness: scripted agent used by the offline regression suite.
  It drives the REAL runner interfaces (budget counting, semantic events,
  container runtime, candidate export) with synthetic model replies and
  synthetic tool results. Its data is synthetic — never a benchmark claim.

- MiniSweAgentHarness: the real mini-SWE-agent 2.4.6 single-task adapter.
  It calls mini's Python API in an ISOLATED SUBPROCESS (the ENV-01 venv
  interpreter) so the host runner can hard-kill it via watchdog. Input
  isolation: mini receives an instance PROJECTION (instance_id + image only)
  plus problem_statement — never the record's gold/test patches, F2P/P2P
  lists, or eval script. The bundled swebench_single CLI is NOT used (it
  loads the full HF dataset); we call get_sb_environment / get_agent /
  agent.run directly with our local record projection.

  Gate A: payload construction + isolation checks only. The subprocess is
  never spawned here; `authorized=False` refuses execution until gate C.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..collectors.semantic_recorder import SemanticRecorder
from .container_runtime import ContainerHandle, ContainerRuntime

# Fields allowed into the mini instance projection. This whitelist is the
# input-isolation boundary: anything else in the record must not reach mini.
MINI_INSTANCE_FIELDS = ("instance_id", "image_name")

FORBIDDEN_PROJECTION_FIELDS = ("patch", "test_patch", "hints_text",
                               "FAIL_TO_PASS", "PASS_TO_PASS", "eval_script")


class AgentError(RuntimeError):
    """Agent-side failure (distinct from infrastructure failure)."""


@dataclass
class AgentTask:
    """What the agent is allowed to see (whitelist projection result)."""
    instance_id: str
    problem_statement: str
    image: str                  # environment view only
    cwd: str = "/testbed"
    source_type: str = "synthetic"


@dataclass
class ModelCallRecord:
    request_id: str
    step_index: int
    ok: bool
    usage: dict | None
    error: str | None
    t_start_ns: int
    t_end_ns: int


@dataclass
class AgentResult:
    status: str                 # ok | agent_error | budget_exceeded |
                                # watchdog_timeout | infra_failure | no_candidate
    candidate_patch: str | None
    steps: int = 0
    model_calls: list[ModelCallRecord] = field(default_factory=list)
    output_tokens: int = 0
    error: str | None = None
    container_ids: list[str] = field(default_factory=list)
    trajectory: list[dict] = field(default_factory=list)
    nested_retry_detected: bool = False
    stop_reason: str | None = None


class AgentHarness:
    """One agent attempt over one task."""
    name = "abstract"

    def run(self, task: AgentTask, budget, recorder: SemanticRecorder,
            runtime: ContainerRuntime,
            container: ContainerHandle | None,
            watchdog=None, run_dir: Path | None = None,
            credentials: dict | None = None) -> AgentResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# fake harness (synthetic regression tests)
# ---------------------------------------------------------------------------

class FakeAgentHarness(AgentHarness):
    """Scripted agent: model replies + tool calls from a behavior script.

    Script schema (all synthetic):
      steps: list of
        model: {usage: {...}, error: null | "ErrorType: msg",
                extra_calls: int}     # extra_calls simulate nested retries
        tools: list of {command, category, returncode, timed_out}
        sleep_s: float                # simulated wall time (clock advanced)
      final: {status: ok|no_candidate, candidate_patch: str} | null (agent_error)
      hang_after_step: int            # spawn a REAL blocking subprocess to be
                                       # watchdog-killed (wall budget test)
    """

    name = "fake"

    def __init__(self, clock, script: dict):
        self.clock = clock
        self.script = script
        self.killed_child: subprocess.Popen | None = None

    def _model_call(self, budget, recorder, step_index, call) -> ModelCallRecord:
        request_id = uuid.uuid4().hex
        t0 = self.clock.monotonic_ns()
        ev = recorder.begin("llm_request", {"request_id": request_id,
                                            "step_index": step_index})
        ok = call.get("error") is None
        budget.count_request()
        self.clock.advance_s(0.2)
        usage = call.get("usage")
        tokens = 0
        if isinstance(usage, dict):
            tokens = int(usage.get("completion_tokens") or 0)
        budget.count_request_output(tokens)
        t1 = self.clock.monotonic_ns()
        recorder.end(ev, attrs={"request_id": request_id,
                                "step_index": step_index, "ok": ok,
                                "usage": usage or None,
                                "error": call.get("error")})
        budget.check()
        return ModelCallRecord(request_id=request_id, step_index=step_index,
                               ok=ok, usage=usage, error=call.get("error"),
                               t_start_ns=t0, t_end_ns=t1)

    def run(self, task: AgentTask, budget, recorder: SemanticRecorder,
            runtime: ContainerRuntime,
            container: ContainerHandle | None,
            watchdog=None, run_dir: Path | None = None,
            credentials: dict | None = None) -> AgentResult:
        result = AgentResult(status="ok", candidate_patch=None)
        calls: list[ModelCallRecord] = []
        hang_after = self.script.get("hang_after_step")
        real_sleep_s = float(self.script.get("real_sleep_s") or 0.0)
        try:
            for step_index, step in enumerate(self.script.get("steps", [])):
                if real_sleep_s:
                    time.sleep(real_sleep_s)
                budget.count_step()
                budget.check()
                model = step.get("model", {})
                call = self._model_call(budget, recorder, step_index, model)
                calls.append(call)
                if not call.ok:
                    raise AgentError(call.error or "model error")
                # nested-retry simulation: extra unapproved calls in one step
                for _ in range(int(model.get("extra_calls") or 0)):
                    retry = self._model_call(budget, recorder, step_index,
                                             {"usage": model.get("usage")})
                    calls.append(retry)
                for tool in step.get("tools", []):
                    tev = recorder.begin("tool_call",
                                         {"tool_index": len(result.trajectory),
                                          "command": tool["command"],
                                          "category": tool.get("category", "Other"),
                                          "container_id":
                                              container.container_id if container else None})
                    if container is not None:
                        outcome = runtime.execute(container, tool["command"],
                                                  60)
                        rc = outcome.get("returncode", 0)
                    else:
                        rc = int(tool.get("returncode", 0))
                    recorder.end(tev, attrs={
                        "tool_index": len(result.trajectory),
                        "command": tool["command"],
                        "category": tool.get("category", "Other"),
                        "returncode": rc,
                        "timed_out": bool(tool.get("timed_out"))})
                    result.trajectory.append(
                        {"step": step_index, "command": tool["command"],
                         "category": tool.get("category", "Other"),
                         "returncode": rc})
                # simulated wall time for the whole step (model + tools)
                self.clock.advance_s(float(step.get("sleep_s", 0.05)))
                budget.check()
                result.steps = step_index + 1
                if hang_after is not None and step_index + 1 >= hang_after:
                    # REAL subprocess so the watchdog must hard-kill it.
                    self.killed_child = subprocess.Popen(
                        ["python3", "-c", "import time; time.sleep(120)"])
                    if watchdog is not None:
                        watchdog.register(self.killed_child)
                    self.killed_child.wait()
                    raise AgentError("fake harness blocked past wall budget")
            final = self.script.get("final")
            if final is None:
                raise AgentError("scripted agent failure")
            if final.get("status") == "no_candidate":
                result.status = "no_candidate"
                result.candidate_patch = None
            else:
                result.candidate_patch = final.get("candidate_patch", "")
        except AgentError as exc:
            result.status = "agent_error"
            result.error = str(exc)
            result.stop_reason = "agent_error"
        result.model_calls = calls
        result.output_tokens = sum(
            int((c.usage or {}).get("completion_tokens") or 0) for c in calls)
        result.nested_retry_detected = _detect_nested_retries(calls)
        return result


def _detect_nested_retries(calls: list[ModelCallRecord]) -> bool:
    """More than one model call inside a single step == nested retry."""
    per_step: dict[int, int] = {}
    for call in calls:
        per_step[call.step_index] = per_step.get(call.step_index, 0) + 1
    return any(n > 1 for n in per_step.values())


# ---------------------------------------------------------------------------
# real mini adapter (implemented in gate A round 3; execution still gated)
# ---------------------------------------------------------------------------

class MiniSweAgentHarness(AgentHarness):
    """Real mini-SWE-agent 2.4.6 harness running in an isolated subprocess.

    Architecture (keeps mini's action protocol and agent loop intact):
    - The venv child process runs the mini agent loop against an
      ``AttachedDockerEnvironment`` that execs into the container the RUNNER
      already created and measured (create -> baseline -> execute -> final
      read -> archive -> teardown). mini never starts its own container,
      so the measurement boundary stays with the runner.
    - The child appends one JSON line PER MODEL REQUEST to a status file
      (the hook is at DefaultAgent.query level, so format-error requests
      and the final request before exit are counted too). Each line carries
      the cumulative n_calls/n_steps, the request's usage, ok=False for
      format-error requests, and the request's OWN monotonic start/end
      timestamps taken in the child.
    - The parent polls the status file: request/step counters advance by
      the CUMULATIVE DELTA (a line that jumps from n_calls=1 to 3 counts
      2 requests), output tokens go through the PER-REQUEST ceiling check,
      and any limit trip hard-kills the subprocess.
    - The candidate patch is extracted from the container's working tree
      (git -c core.fileMode=false diff) — it must come from THIS attempt's
      work tree, never from gold patches or history. A failed/empty
      extraction NEVER overwrites the original stop reason.
    - Credentials never enter the payload or any file: the parent injects
      SDK env vars into the child's process environment only.

    Authorization: `authorized=False` refuses to run (gate C approval
    required). Tests inject `child_code` (a fake child that speaks the
    same status protocol) for offline orchestration coverage; the real
    mini chain (installed mini + fake transport + fake env executor) is
    covered by tests/integration_run01.py.
    """

    name = "mini-swe-agent-2.4.6"

    # capture cap for the child's stdout: fixed-size binary blocks are
    # drained continuously (see run); past the cap we keep draining but
    # stop accumulating, preserving the prefix
    CAPTURE_CAP_BYTES = 4 * 1024 * 1024

    def __init__(self, venv_python: Path, *, authorized: bool = False,
                 mini_config: dict | None = None,
                 target_image_ref: str | None = None,
                 child_code: str | None = None,
                 poll_interval_s: float = 0.2,
                 payload_extras: dict | None = None):
        self.venv_python = venv_python
        self.authorized = authorized
        # FULL mini config (model name, templates, environment) supplied by
        # the runner assembly; budget fields are enforced/merged in
        # _effective_config so run() never sends an empty config.
        self.mini_config = mini_config or {}
        # configuration-level image mapping: the fixed record names the
        # x86_64 build; the runner references the native arm64 digest here.
        # The record itself stays read-only and unmodified.
        self.target_image_ref = target_image_ref
        self.child_code = child_code or self.REAL_CHILD_CODE
        self.poll_interval_s = poll_interval_s
        self._required_config: dict = {}
        self.host_summary: dict | None = None
        self.host_archive_status: str | None = None
        # OFFLINE TEST HOOK ONLY: extra payload keys (fake transport /
        # fake env specs) for integration tests; never used in production.
        self.payload_extras = payload_extras or {}

    # -- configuration ------------------------------------------------------

    @staticmethod
    def load_bundled_config(venv_python: Path) -> dict:
        """Load mini's bundled swebench.yaml from the installed venv
        (templates/model defaults). Read-only; the caller merges overrides."""
        import yaml
        cfg = (venv_python.parent.parent / "lib" / "python3.11"
               / "site-packages" / "minisweagent" / "config" / "benchmarks"
               / "swebench.yaml")
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "agent" not in data:
            raise ValueError(f"unexpected bundled config shape: {cfg}")
        return data

    def _effective_config(self, budget) -> dict:
        """bundled/base config + caller config + budget-enforced limits.

        The result is what the child actually receives — never empty: the
        model section must carry model_name (from the caller config) and
        the agent section carries mini-native limits derived from the
        approved budget."""
        merged = {"agent": {}, "model": {}, "environment": {}}
        for section in merged:
            merged[section] = dict(self.mini_config.get(section) or {})
        lim = budget.limits
        merged["agent"]["step_limit"] = lim.max_model_requests
        merged["agent"]["wall_time_limit_seconds"] = int(lim.agent_wall_s)
        merged["agent"]["cost_limit"] = 0
        merged["agent"].pop("output_path", None)
        model_kwargs = dict(merged["model"].get("model_kwargs") or {})
        model_kwargs["num_retries"] = 0
        model_kwargs["max_tokens"] = lim.max_output_tokens_per_request
        merged["model"]["model_kwargs"] = model_kwargs
        if not str(merged["model"].get("model_name") or "").strip():
            raise ValueError(
                "mini_config.model.model_name is required (run() must be "
                "assembled with the confirmed model routing, never an "
                "empty config)")
        merged["environment"].setdefault("timeout", 60)
        merged["environment"].setdefault("interpreter", ["bash", "-c"])
        return merged

    # -- payload construction (pure, unit-testable) ------------------------

    def build_instance_projection(self, record: dict) -> dict:
        """instance_id + image reference ONLY — the input isolation boundary.

        The image is mapped to the configured target digest reference when
        one is set; the record's own x86_64 tag is never forwarded."""
        projection = {k: record[k] for k in MINI_INSTANCE_FIELDS if k in record}
        if "image_name" not in projection and "docker_image" in record:
            projection["image_name"] = record["docker_image"]
        if self.target_image_ref is not None:
            projection["image_name"] = self.target_image_ref
        leaked = [f for f in FORBIDDEN_PROJECTION_FIELDS if f in projection]
        if leaked:
            raise ValueError(f"isolation violation: {leaked} in projection")
        return projection

    def build_payload(self, record: dict, trajectory_path: Path,
                      status_path: Path, container_id: str,
                      mini_config: dict | None = None) -> dict:
        payload = {
            "instance": self.build_instance_projection(record),
            "problem_statement": record["problem_statement"],
            "container_id": container_id,
            "env_mode": "attached",
            "output": {"trajectory_path": str(trajectory_path),
                       "status_path": str(status_path)},
            "mini_config": mini_config or self._required_config,
            "retry_env": {"MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT": "1"},
            "cost_tracking": "ignore_errors",
        }
        self.check_payload_isolated(payload)
        return payload

    def set_required_config(self, config: dict) -> None:
        """Config that build_payload must carry (set by run())."""
        self._required_config = config

    @staticmethod
    def check_payload_isolated(payload: dict) -> None:
        def walk(node, path=""):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in FORBIDDEN_PROJECTION_FIELDS:
                        raise ValueError(
                            f"isolation violation at {path}.{key}: answer "
                            "material must not reach the agent harness")
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, f"{path}[{i}]")
        walk(payload)

    def default_mini_config(self, *, step_limit: int, agent_wall_s: int,
                            max_output_tokens: int,
                            environment_timeout: int = 60) -> dict:
        """Budget-derived mini limits (kept for callers assembling configs;
        run() enforces the same fields via _effective_config).

        mini's step_limit gates ``n_calls`` (the MODEL REQUEST count — see
        DefaultAgent.query; mini does not track a separate step counter),
        and wall_time_limit_seconds gates the agent loop internally."""
        return {
            "agent": {
                "step_limit": step_limit,
                "wall_time_limit_seconds": agent_wall_s,
                "cost_limit": 0,
                "output_path": None,
            },
            "model": {
                "model_kwargs": {
                    "num_retries": 0,
                    "max_tokens": max_output_tokens,
                },
            },
            "environment": {
                "timeout": environment_timeout,
                "interpreter": ["bash", "-c"],
            },
        }

    # -- child script (runs INSIDE the venv subprocess) --------------------

    REAL_CHILD_CODE = r'''
import json, os, subprocess, sys, time

payload = json.loads(sys.stdin.read())
os.environ.update(payload.get("retry_env", {}))
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ.setdefault("MSWEA_CONFIG_DIR", "/tmp/mswea-run01-config")

from minisweagent import Environment
from minisweagent.agents.default import DefaultAgent
from minisweagent.exceptions import FormatError
from minisweagent.models import get_model


class AttachedDockerEnvironment(Environment):
    """Executes mini actions in the runner-created container.

    Same execution semantics as mini's DockerEnvironment (docker exec
    with the configured env vars forwarded via -e — including
    BASH_ENV=/root/.bashrc so the image's conda testbed env activates;
    without it bash -c runs under the base conda python — merged
    stdout/stderr, per-command timeout) but against an existing
    container so the measurement boundary stays with the runner."""

    def __init__(self, container_id: str, *, timeout: int = 60,
                 interpreter=None, cwd: str = "/testbed", env=None):
        self.container_id = container_id
        self.env = dict(env or {})
        self.config = type("C", (), {"timeout": timeout,
                                     "interpreter": interpreter or ["bash", "-c"],
                                     "cwd": cwd})()
        self._finished = False

    def execute(self, action: dict, cwd: str = "", *, timeout=None):
        command = action.get("command", "")
        cwd = cwd or self.config.cwd
        cmd = ["docker", "exec", "-w", cwd]
        for key, value in self.env.items():
            cmd.extend(["-e", f"{key}={value}"])
        cmd.extend([self.container_id, *self.config.interpreter, command])
        try:
            result = subprocess.run(cmd, text=True, timeout=timeout or self.config.timeout,
                                    encoding="utf-8", errors="replace",
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            return {"output": result.stdout, "returncode": result.returncode,
                    "exception_info": ""}
        except Exception as e:  # same shape as mini's DockerEnvironment
            return {"output": "", "returncode": -1,
                    "exception_info": f"error executing command: {e}"}

    def get_template_vars(self, **kwargs):
        return {"cwd": self.config.cwd, **kwargs}

    def _check_finished(self, output):
        if output["exception_info"]:
            raise RuntimeError(output["exception_info"])


class FakeScriptedEnvironment(Environment):
    """OFFLINE TEST ONLY (payload env_mode == 'fake'): scripted command
    outputs, no docker. Same execute() contract (including the Submitted
    completion check) as the attached env. Every executed command is
    appended to a log file so tests can prove the tool stage was actually
    entered (not just the SDK import phase)."""

    def __init__(self, script: dict, *, timeout: int = 60,
                 cwd: str = "/testbed", log_path: str | None = None):
        self.script = script
        self.config = type("C", (), {"timeout": timeout, "cwd": cwd})()
        self._finished = False
        self._log_path = log_path

    def _log(self, command: str):
        if not self._log_path:
            return
        with open(self._log_path, "a") as fh:
            fh.write(json.dumps({"command": command,
                                 "t_ns": time.monotonic_ns()}) + "\n")

    def execute(self, action: dict, cwd: str = "", *, timeout=None):
        command = action.get("command", "")
        self._log(command)
        out = self.script.get(command, {"returncode": 0, "output": ""})
        if out.get("sleep_s"):
            time.sleep(float(out["sleep_s"]))  # test-only pacing
        output = {"output": out.get("output", ""),
                  "returncode": out.get("returncode", 0),
                  "exception_info": ""}
        self._check_finished(output)
        return output

    def get_template_vars(self, **kwargs):
        return {"cwd": self.config.cwd, **kwargs}

    def _check_finished(self, output):
        from minisweagent.exceptions import Submitted
        lines = output.get("output", "").lstrip().splitlines(keepends=True)
        if lines and lines[0].strip() == "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" \
                and output["returncode"] == 0:
            raise Submitted({
                "role": "exit",
                "content": "".join(lines[1:]),
                "extra": {"exit_status": "Submitted",
                          "submission": "".join(lines[1:])}})


class StatusTrackingAgent(DefaultAgent):
    """DefaultAgent + one status JSONL line PER MODEL REQUEST.

    The hook sits at query() level: a billed request that later fails to
    parse (FormatError) still writes its line with ok=false, and the final
    request before exit is recorded too. Each line carries the request's
    OWN monotonic start/end timestamps so the parent never has to invent
    timing from archive-write time."""

    def __init__(self, *args, status_path=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._status_path = status_path
        self._n_steps = 0

    def _write_status(self, *, ok, usage, t_start_ns, t_end_ns):
        if not self._status_path:
            return
        with open(self._status_path, "a") as fh:
            fh.write(json.dumps({
                "n_calls": self.n_calls, "n_steps": self._n_steps,
                "cost": self.cost,
                "elapsed_s": int(time.time() - self._start_time),
                "ok": ok, "usage": usage,
                "t_start_ns": t_start_ns, "t_end_ns": t_end_ns}) + "\n")

    @staticmethod
    def _usage_of(message):
        extra = (message or {}).get("extra", {}) if isinstance(message, dict) else {}
        return (extra.get("usage")
                or (extra.get("response") or {}).get("usage")
                or extra.get("response_usage"))

    def step(self):
        result = super().step()
        self._n_steps += 1
        return result

    def query(self):
        t0 = time.monotonic_ns()
        try:
            message = super().query()
            self._write_status(ok=True, usage=self._usage_of(message),
                               t_start_ns=t0, t_end_ns=time.monotonic_ns())
            return message
        except FormatError as e:
            # the call was billed before parsing failed: count it too
            usage = None
            msgs = getattr(e, "messages", None) or []
            if msgs:
                usage = self._usage_of(msgs[0])
            self._write_status(ok=False, usage=usage,
                               t_start_ns=t0, t_end_ns=time.monotonic_ns())
            raise


def _install_fake_transport(responses, *, assert_credentials=False):
    """OFFLINE TEST ONLY: block all real httpx transport and answer from
    the scripted responses — each element is a COMPLETE chat-completion
    response body (same shape as the ENV-01 fake transport tests)."""
    import httpx, litellm
    _orig = httpx.HTTPTransport.handle_request
    class _NetViolation(RuntimeError):
        pass
    def _blocked(self, request, *_a, **_k):
        raise _NetViolation("real network blocked: %s" % request.url)
    expected_base = os.environ.get("OPENAI_API_BASE")
    expected_key = os.environ.get("OPENAI_API_KEY")
    if assert_credentials and (not expected_base or not expected_key):
        raise _NetViolation("credential propagation assertion failed")

    class _FT(httpx.HTTPTransport):
        def __init__(self):
            super().__init__()
            self.n = 0
        def handle_request(self, request):
            self.n += 1
            if assert_credentials:
                auth = request.headers.get("authorization", "")
                proxy_names = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                               "NO_PROXY", "http_proxy", "https_proxy",
                               "all_proxy", "no_proxy")
                if (not str(request.url).startswith(expected_base + "/")
                        or auth != "Bearer " + expected_key
                        or any(os.environ.get(name) for name in proxy_names)):
                    raise _NetViolation("credential propagation assertion failed")
            body = responses[min(self.n - 1, len(responses) - 1)]
            return httpx.Response(200, json=body)
    httpx.HTTPTransport.handle_request = _blocked
    try:
        litellm.client_session = httpx.Client(transport=_FT())
    except Exception:
        httpx.HTTPTransport.handle_request = _orig
        raise


def main():
    out = payload["output"]
    mini_config = payload.get("mini_config") or {}
    agent_cfg = dict(mini_config.get("agent") or {})
    env_cfg = dict(mini_config.get("environment") or {})
    model_cfg = dict(mini_config.get("model") or {})
    agent_cfg.pop("output_path", None)

    if payload.get("_fake_transport"):
        fake_transport = payload["_fake_transport"]
        enforce_credentials = bool(fake_transport.get("assert_credentials"))
        _install_fake_transport(fake_transport["responses"],
                                assert_credentials=enforce_credentials)
        # Legacy offline fixtures may supply synthetic credentials.  The R2
        # integration path sets assert_credentials and therefore retains and
        # checks the credentials supplied by the parent environment.
        if not enforce_credentials:
            os.environ["OPENAI_API_KEY"] = "sk-fake-run01-offline-test"
            os.environ["OPENAI_API_BASE"] = "https://fake-run01-offline.invalid/v1"

    if payload.get("env_mode") == "fake":
        base_env = FakeScriptedEnvironment(
            payload.get("_fake_env") or {},
            log_path=payload.get("_fake_env_log"))
    else:
        base_env = AttachedDockerEnvironment(
            payload["container_id"],
            timeout=env_cfg.get("timeout", 60),
            interpreter=env_cfg.get("interpreter"),
            env=env_cfg.get("env") or {},
        )
    # G1-01-A tool-event hook: SHARED implementation (also used by the
    # G1-01-B container validation entry) — see runners/tool_event_env.
    # The child embeds the exact source text (carried in the payload by
    # the parent, which imports the module normally) so the venv
    # subprocess needs no import path; semantics: OPEN persisted before
    # the call, CLOSED/ERROR after, safe projections only.
    tool_events_path = payload.get("output", {}).get("tool_events_path")
    _ns: dict = {}
    exec(payload["tool_event_env_source"], _ns)
    ToolEventRecordingEnvironment = _ns["ToolEventRecordingEnvironment"]

    env = ToolEventRecordingEnvironment(base_env, tool_events_path) \
        if tool_events_path else base_env
    # cost_tracking from the payload (ignore_errors: unpriced models must
    # not raise; the cost stays a source value of 0.0, tracked as unknown
    # upstream — same semantics as the ENV-01 adapter)
    if payload.get("cost_tracking"):
        model_cfg["cost_tracking"] = payload["cost_tracking"]
    model = get_model(config=model_cfg)
    agent = StatusTrackingAgent(model, env, status_path=out["status_path"],
                                **agent_cfg)
    info = agent.run(payload["problem_statement"])
    trajectory = agent.save(None)  # serialize in memory
    import pathlib
    pathlib.Path(out["trajectory_path"]).write_text(json.dumps(trajectory, indent=2))
    if hasattr(env, "close"):
        env.close()
    print(json.dumps({"exit_status": info.get("exit_status"),
                      "n_calls": agent.n_calls,
                      "n_steps": agent._n_steps}))


main()
'''

    def build_child_argv(self) -> list[str]:
        return [str(self.venv_python), "-c", self.child_code]

    # -- parent-side orchestration ------------------------------------------

    def run(self, task: AgentTask, budget, recorder: SemanticRecorder,
            runtime: ContainerRuntime,
            container: ContainerHandle | None,
            watchdog=None, run_dir: Path | None = None,
            credentials: dict[str, str] | None = None) -> AgentResult:
        if not self.authorized:
            raise AgentError(
                "mini harness execution not authorized: gate C approval "
                "required")
        if container is None:
            return AgentResult(status="infra_failure", candidate_patch=None,
                               error="mini harness requires a runner-created "
                                     "agent container")
        if run_dir is None:
            return AgentResult(status="infra_failure", candidate_patch=None,
                               error="mini harness requires the run dir for "
                                     "status/trajectory outputs")
        status_path = run_dir / "mini_status.jsonl"
        traj_path = run_dir / "mini_trajectory.json"
        tool_events_path = run_dir / "mini_tool_events.jsonl"
        host_process_path = run_dir / "host_process.jsonl"

        # FULL config (templates/model/limits) — never {}
        effective = self._effective_config(budget)
        self.set_required_config(effective)

        record_like = {
            "instance_id": task.instance_id,
            "problem_statement": task.problem_statement,
            "image_name": task.image,
        }
        payload = self.build_payload(record_like, traj_path, status_path,
                                     container.container_id,
                                     mini_config=effective)
        payload.setdefault("output", {})["tool_events_path"] = \
            str(tool_events_path)
        # the shared tool-event hook source travels in the payload (the
        # child runs as `python -c` with no package context)
        from .tool_event_env import TOOL_EVENT_WRAPPED_SOURCE
        payload["tool_event_env_source"] = TOOL_EVENT_WRAPPED_SOURCE
        self.check_payload_isolated(payload)
        if self.payload_extras:
            payload.update(self.payload_extras)
            self.check_payload_isolated(payload)
        # offline integration evidence: log tool-entry in the run dir
        if payload.get("env_mode") == "fake":
            payload.setdefault("_fake_env_log",
                               str(run_dir / "mini_env_log.jsonl"))

        result = AgentResult(status="ok", candidate_patch=None)
        result.container_ids = [container.container_id]
        proc = None
        try:
            import subprocess as _sp
            # credentials live ONLY in the child's process environment
            child_env = {k: v for k, v in os.environ.items()
                         if k in ("PATH", "HOME", "LANG", "LC_ALL",
                                  "MSWEA_CONFIG_DIR")}
            if credentials:
                child_env.update(credentials)
            proc = _sp.Popen(self.build_child_argv(), stdin=_sp.PIPE,
                             stdout=_sp.PIPE, stderr=_sp.STDOUT,
                             env=child_env)
            if watchdog is not None:
                watchdog.register(proc)
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(payload).encode("utf-8"))
            proc.stdin.close()

            # CONTINUOUS pipe draining with FIXED-SIZE binary blocks: the
            # child (mini + litellm logging) can produce more than the
            # ~64 KiB pipe buffer, and line iteration would buffer an
            # entire huge line before any size check. Blocks bound memory
            # regardless of newlines; past the cap we keep draining (the
            # child must never block) but stop accumulating, keeping the
            # prefix. The summary line is parsed from what was kept.
            kept = bytearray()
            drain_state = {"total": 0}

            def _drain():
                while True:
                    try:
                        block = proc.stdout.read(65536)
                    except (OSError, ValueError):
                        return
                    if not block:
                        return
                    drain_state["total"] += len(block)
                    cap = self.CAPTURE_CAP_BYTES
                    if len(kept) < cap:
                        kept.extend(block[:cap - len(kept)])

            drain_thread = threading.Thread(target=_drain, daemon=True)
            drain_thread.start()

            # poll the status file: cumulative-delta budget counting and
            # real-time event emission with the child's own timestamps
            seen_lines = 0
            killed_reason = None
            termination = None
            # G1-01-A3 host observation: pin the child's identity
            # (pid+starttime), then poll /proc CPU/RSS alongside the
            # status polling; the final read after exit honestly yields
            # process_exited (verified final = null, last readable is
            # diagnostic)
            from ..collectors.host_process import (HostProcessMonitor,
                                                   read_starttime)
            child_starttime = read_starttime(proc.pid)
            host_monitor = HostProcessMonitor(
                proc.pid, expected_starttime=child_starttime,
                interval_s=self.poll_interval_s)
            host_records = []
            while proc.poll() is None:
                snap = host_monitor.poll_once()
                host_records.append({
                    "t_monotonic_ns": snap.t_monotonic_ns,
                    "cpu_ticks": snap.cpu_ticks,
                    "rss_bytes": snap.rss_bytes,
                    "stat": snap.read_status.get("stat")})
                lines = self._read_status(status_path)
                for line in lines[seen_lines:]:
                    seen_lines += 1
                    self._count_status_line(line, budget)
                    self._emit_line_event(recorder, line)
                try:
                    budget.check()
                except Exception as exc:  # BudgetExceeded
                    killed_reason = f"budget:{exc}"
                    proc.kill()
                    break
                time.sleep(self.poll_interval_s)
            # one final read after exit (typically process_exited — kept)
            final_snap = host_monitor.poll_once()
            host_records.append({
                "t_monotonic_ns": final_snap.t_monotonic_ns,
                "cpu_ticks": final_snap.cpu_ticks,
                "rss_bytes": final_snap.rss_bytes,
                "stat": final_snap.read_status.get("stat")})
            self.host_summary = host_monitor.summary()
            # PERSIST the full host evidence: identity, units, coverage
            # interval and the summary — a write failure is recorded as
            # run state, never silently ignored
            host_doc = {
                "identity": {
                    "pid": proc.pid,
                    "starttime_ticks": child_starttime,
                    "identity_note": ("pid + starttime (field 22 of "
                                      "/proc/<pid>/stat); a reused PID "
                                      "with a different starttime is "
                                      "reported as pid_reuse_detected, "
                                      "not accepted"),
                },
                "units": {
                    "clk_tck": host_monitor.reader.clk_tck,
                    "page_size": host_monitor.reader.page_size,
                    "cpu_ticks_semantics": "utime+stime cumulative ticks",
                    "rss_semantics": "resident pages * page_size",
                },
                "coverage": {
                    "n_snapshots": len(host_records),
                    "first_t_monotonic_ns": host_records[0][
                        "t_monotonic_ns"] if host_records else None,
                    "last_t_monotonic_ns": host_records[-1][
                        "t_monotonic_ns"] if host_records else None,
                    "final_read_status": (host_records[-1]["stat"]
                                          if host_records else None),
                },
                "records": host_records,
                "summary": self.host_summary,
            }
            try:
                host_process_path.write_text(
                    json.dumps(host_doc, indent=1) + "\n",
                    encoding="utf-8")
                self.host_archive_status = "ok"
            except OSError as exc:
                # recorded on the result and the recorder — NOT silent
                self.host_archive_status = (
                    f"host_process_archive_failed:"
                    f"{type(exc).__name__}")
                recorder.point("infra", {
                    "status": "host_process_archive_failed",
                    "detail": f"error:{type(exc).__name__}"})
            # killing the mini subprocess does NOT stop the commands it
            # launched inside the container (docker exec clients dying
            # leaves the server side running) — terminate the in-container
            # workload and record HOW CONFIRMED that stop is
            if killed_reason is not None:
                termination = runtime.terminate_workload(container)
                recorder.point("container", {
                    "container_id": container.container_id,
                    "image": task.image, "scope": "agent",
                    "action": "terminate_workload",
                    "detail": (f"method={termination.get('method')}; "
                               f"confirmed={termination.get('confirmed')}; "
                               f"container_alive="
                               f"{termination.get('container_alive')}")})
            # final drain after exit (last requests before exit included)
            for line in self._read_status(status_path)[seen_lines:]:
                self._count_status_line(line, budget)
                self._emit_line_event(recorder, line)
            # a fast child may finish before the first poll cycle; the
            # counted-over-limit fact must still be recorded even when no
            # kill was needed
            if killed_reason is None:
                try:
                    budget.check()
                except Exception as exc:  # BudgetExceeded
                    killed_reason = f"budget:{exc}"

            # reap and finalize the drained output. If EOF has not
            # arrived (an orphaned grandchild holds the pipe's write
            # end), close from a daemon thread — a synchronous close()
            # would block on the reader's buffer lock until the orphan
            # exits.
            drain_thread.join(timeout=2)
            if drain_thread.is_alive():
                def _close_quietly(stream):
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
                threading.Thread(target=_close_quietly,
                                 args=(proc.stdout,), daemon=True).start()
                drain_thread.join(timeout=2)
            else:
                try:
                    proc.stdout.close()
                except (OSError, ValueError):
                    pass
            proc.wait()
            stdout = bytes(kept).decode("utf-8", "replace")
            if killed_reason is not None:
                result.status = "budget_exceeded"
                result.stop_reason = killed_reason
                result.error = killed_reason
                if termination is not None:
                    result.stop_reason = (
                        f"{killed_reason}; "
                        f"workload_stop_confirmed="
                        f"{termination.get('confirmed')}")
            elif proc.returncode != 0:
                result.status = "agent_error"
                result.error = f"mini child rc={proc.returncode}"
                result.stop_reason = "child_exit"
            summary = self._parse_child_summary(stdout or "")
            final = self._last_status(status_path)
            result.steps = (summary or final or {}).get("n_steps", seen_lines)
            result.trajectory = self._read_status(status_path)

            # candidate patch from THIS attempt's working tree. A failed or
            # empty extraction NEVER overwrites the original stop reason —
            # it only annotates it.
            diff = runtime.execute(
                container, "git -c core.fileMode=false diff", 60)
            candidate = (diff.get("output") or "").strip()
            if diff.get("returncode") != 0:
                if result.status == "ok":
                    result.status = "infra_failure"
                    result.error = "candidate extraction (git diff) failed"
                else:
                    result.error = (f"{result.error}; "
                                    "candidate extraction also failed")
            elif not candidate:
                if result.status == "ok":
                    result.status = "no_candidate"
                    result.stop_reason = "no_candidate"
                # else: keep budget_exceeded/agent_error — no patch is a
                # consequence of the earlier stop, not a new reason
            else:
                result.candidate_patch = candidate
            return result
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _read_status(path: Path) -> list[dict]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    out.append({"unparseable": True})
        return out

    @staticmethod
    def _last_status(path: Path) -> dict | None:
        lines = MiniSweAgentHarness._read_status(path)
        return lines[-1] if lines else None

    @staticmethod
    def _count_status_line(line: dict, budget) -> None:
        """Feed ONE status line into the budget counters.

        n_calls/n_steps are CUMULATIVE counters written by the child: the
        parent advances its counters by the DELTA, so a line that jumps
        from n_calls=1 to n_calls=3 counts two requests (a polling gap may
        have missed intermediate lines). Output tokens use the
        PER-REQUEST ceiling check (one line == one request's usage)."""
        if line.get("unparseable"):
            return
        n_calls = line.get("n_calls")
        if isinstance(n_calls, int):
            prev = getattr(budget, "_mini_calls_counted", 0)
            if n_calls > prev:
                budget.count_requests(n_calls - prev)
                budget._mini_calls_counted = n_calls
        n_steps = line.get("n_steps")
        if isinstance(n_steps, int):
            prev_s = getattr(budget, "_mini_steps_counted", 0)
            if n_steps > prev_s:
                budget.count_steps(n_steps - prev_s)
                budget._mini_steps_counted = n_steps
        usage = line.get("usage")
        if isinstance(usage, dict):
            tokens = usage.get("completion_tokens")
            if isinstance(tokens, int):
                budget.count_request_output(tokens)

    @staticmethod
    def _emit_line_event(recorder: SemanticRecorder, line: dict) -> None:
        """Emit one llm_request event per status line, carrying the
        request's OWN boundaries from the child (t_start_ns/t_end_ns).
        When the child did not provide timestamps the event records
        timing_source=unknown instead of inventing a duration."""
        if line.get("unparseable") or not isinstance(line.get("n_calls"), int):
            return
        step_index = int(line.get("n_steps") or 0)
        request_id = f"mini-{line['n_calls']}"
        ev = recorder.begin("llm_request", {
            "request_id": request_id, "step_index": step_index})
        attrs = {"request_id": request_id, "step_index": step_index,
                 "ok": bool(line.get("ok", True)),
                 "usage": line.get("usage"),
                 "t_start_ns": line.get("t_start_ns"),
                 "t_end_ns": line.get("t_end_ns"),
                 "timing_source": "child_status"}
        recorder.end(ev, attrs=attrs)

    @staticmethod
    def _parse_child_summary(stdout: str) -> dict | None:
        for line in reversed((stdout or "").strip().splitlines()):
            line = line.strip()
            if line.startswith("{") and "exit_status" in line:
                try:
                    return json.loads(line)
                except ValueError:
                    return None
        return None
