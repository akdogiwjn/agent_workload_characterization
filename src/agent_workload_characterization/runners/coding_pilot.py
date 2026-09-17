"""RUN-01 coding pilot runner: single-task orchestration with budget,
watchdog, isolated verifier and three-phase status accounting.

Phases and their INDEPENDENT statuses (a verifier timeout is never recorded
as an agent failure, an archive failure never rewrites execution facts):

  execution  : ok | agent_error | budget_exceeded | watchdog_timeout |
               infra_failure | no_candidate
  evaluation : not_run | patch_apply_failed | tests_not_run |
               verifier_timeout | infra_failure | ok
  archive    : ok | failed | budget_exceeded

Scope discipline (methodology / RUN-01 task brief):
- agent sandbox container, verifier container, host agent runtime and the
  collector are measured as separate scopes; the sampler runs outside them
  and its own cost is stated separately;
- final counter reads happen BEFORE container teardown, and failing paths
  still archive the measurement evidence before cleanup;
- cleanup only touches resources whose identity (run_id) matches this
  attempt.

Gate A: everything here runs offline against fakes; the real mini/docker
entry points refuse to execute without explicit authorization.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any

from ..collectors.resource_sampler import (CounterSnapshot, ResourceSampler,
                                           ScopeReader)
from ..collectors.semantic_recorder import Clock, SemanticRecorder, SystemClock
from .container_runtime import (ContainerHandle, ContainerRuntime,
                                ContainerSpec, RuntimeError_)
from .report_writer import _catalog_protected_roots
from .mini_agent_adapter import AgentError, AgentHarness, AgentResult, AgentTask

RUN_COLLECTION_PREFIX = "RUN-01"


# ---------------------------------------------------------------------------
# budgets
# ---------------------------------------------------------------------------

@dataclass
class BudgetLimits:
    max_model_requests: int = 30
    max_steps: int = 30
    max_output_tokens_per_request: int = 4096
    agent_wall_s: float = 25 * 60.0
    verifier_wall_s: float = 5 * 60.0
    total_wall_s: float = 30 * 60.0
    max_new_artifact_bytes: int = 5 * 2**30

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


class BudgetExceeded(RuntimeError):
    def __init__(self, limit_name: str, observed: Any, cap: Any):
        super().__init__(f"budget exceeded: {limit_name}={observed} cap={cap}")
        self.limit_name = limit_name
        self.observed = observed
        self.cap = cap


@dataclass
class BudgetTracker:
    limits: BudgetLimits
    clock: Clock
    requests: int = 0
    steps: int = 0
    output_tokens: int = 0
    artifact_bytes: int = 0
    artifact_exceeded: bool = False
    t_start_ns: int | None = None
    t_phase_ns: int | None = None
    phase: str = "execution"
    exceeded: BudgetExceeded | None = None

    def start(self, phase: str = "execution") -> None:
        self.t_start_ns = self.clock.monotonic_ns()
        self.t_phase_ns = self.t_start_ns
        self.phase = phase

    def begin_phase(self, phase: str) -> None:
        self.t_phase_ns = self.clock.monotonic_ns()
        self.phase = phase

    def elapsed_s(self) -> float:
        """Wall since the CURRENT phase start (phase-local budget)."""
        if self.t_phase_ns is None:
            return 0.0
        return (self.clock.monotonic_ns() - self.t_phase_ns) / 1e9

    def elapsed_total_s(self) -> float:
        if self.t_start_ns is None:
            return 0.0
        return (self.clock.monotonic_ns() - self.t_start_ns) / 1e9

    def count_request(self) -> None:
        self.requests += 1

    def count_requests(self, delta: int) -> None:
        """Advance the request counter by a cumulative COUNTER DELTA (a
        status line may jump from n_calls=1 to 3 — that is two requests)."""
        if delta > 0:
            self.requests += int(delta)

    def count_step(self) -> None:
        self.steps += 1

    def count_steps(self, delta: int) -> None:
        if delta > 0:
            self.steps += int(delta)

    def count_output_tokens(self, tokens: int) -> None:
        self.output_tokens += max(0, int(tokens))

    def count_request_output(self, tokens: int) -> None:
        """Per-request output cap (single-request ceiling, distinct from the
        cumulative counter)."""
        tokens = max(0, int(tokens))
        if tokens > self.limits.max_output_tokens_per_request:
            self._exceed(BudgetExceeded("output_tokens_per_request", tokens,
                                        self.limits.max_output_tokens_per_request))
        self.output_tokens += tokens

    # -- artifact accounting (SOFT: never aborts the delivery flow) --------
    # Archiving must still deliver minimal failure evidence and clean up
    # when the artifact ceiling is hit; a hard exception here would destroy
    # the run outcome instead of recording it.

    def would_exceed_artifacts(self, n: int) -> bool:
        return self.artifact_bytes + int(n) > self.limits.max_new_artifact_bytes

    def account_artifact_bytes(self, n: int) -> bool:
        """Record archived bytes; returns True when the ceiling is exceeded
        (first time or already). NEVER raises — the archive phase keeps
        going with minimal evidence."""
        self.artifact_bytes += int(n)
        if self.artifact_bytes > self.limits.max_new_artifact_bytes:
            if not self.artifact_exceeded:
                self.artifact_exceeded = True
            return True
        return False

    def _exceed(self, exc: BudgetExceeded) -> None:
        if self.exceeded is None:
            self.exceeded = exc
        raise exc
    def check(self, *, phase: str | None = None) -> None:
        phase = phase or self.phase
        lim = self.limits
        if self.requests > lim.max_model_requests:
            self._exceed(BudgetExceeded("model_requests", self.requests,
                                        lim.max_model_requests))
        if self.steps > lim.max_steps:
            self._exceed(BudgetExceeded("steps", self.steps,
                                        lim.max_steps))
        wall_cap = lim.agent_wall_s if phase == "execution" else lim.verifier_wall_s
        if self.elapsed_s() > wall_cap:
            self._exceed(BudgetExceeded(f"{phase}_wall_s", self.elapsed_s(),
                                        wall_cap))
        if self.elapsed_total_s() > lim.total_wall_s:
            self._exceed(BudgetExceeded("total_wall_s",
                                        self.elapsed_total_s(),
                                        lim.total_wall_s))
        # hard in-flight artifact ceiling: once the monitor (or the archive
        # accounting) has marked an exceed, every later check raises
        if self.artifact_exceeded:
            self._exceed(BudgetExceeded("new_artifact_bytes",
                                        self.artifact_bytes,
                                        lim.max_new_artifact_bytes))

    # -- phase-relative remaining time (for unified deadlines) -------------

    def remaining_s(self, phase: str | None = None) -> float:
        """Seconds left under the CURRENT phase wall AND the total wall
        (their minimum); never negative."""
        phase = phase or self.phase
        lim = self.limits
        wall_cap = lim.agent_wall_s if phase == "execution" \
            else lim.verifier_wall_s
        left = wall_cap - self.elapsed_s()
        left_total = lim.total_wall_s - self.elapsed_total_s()
        return max(0.0, min(left, left_total))

    def usage_dict(self) -> dict:
        return {"requests": self.requests, "steps": self.steps,
                "output_tokens": self.output_tokens,
                "artifact_bytes": self.artifact_bytes,
                "artifact_exceeded": self.artifact_exceeded,
                "elapsed_s": self.elapsed_s(),
                "elapsed_total_s": self.elapsed_total_s(),
                "phase": self.phase,
                "exceeded": (self.exceeded.limit_name
                             if self.exceeded else None)}


# ---------------------------------------------------------------------------
# watchdog
# ---------------------------------------------------------------------------

class WallWatchdog:
    """Hard wall enforcement over real subprocesses.

    The harness registers any subprocess it spawns; when the deadline
    passes, every registered process gets SIGKILL (uncatchable — SDK or
    alarm swallowing is irrelevant) and the stop flag flips so the runner
    records watchdog_timeout with evidence preserved. cancel() retires the
    watchdog early when the harness finishes within budget.
    """

    def __init__(self, clock: Clock | None = None):
        self.clock = clock or SystemClock()
        self._procs: list[Any] = []
        self._lock = threading.Lock()
        self.stop_requested = threading.Event()
        self.cancelled = False
        self.killed: list[int] = []

    def register(self, proc) -> None:
        with self._lock:
            self._procs.append(proc)

    def cancel(self) -> None:
        """Retire the watchdog (harness finished within budget)."""
        self.cancelled = True
        self.stop_requested.set()

    def enforce(self, deadline_s: float, poll_s: float = 0.05) -> None:
        import time as _time
        t0 = _time.monotonic()
        while not self.cancelled and _time.monotonic() - t0 <= deadline_s:
            _time.sleep(poll_s)
        if self.cancelled:
            return
        with self._lock:
            procs = [p for p in self._procs if p.poll() is None]
        for p in procs:
            p.kill()  # SIGKILL
            self.killed.append(p.pid)
        self.stop_requested.set()


# ---------------------------------------------------------------------------
# verifier
# ---------------------------------------------------------------------------

@dataclass
class VerifierSpec:
    instance_id: str
    image: str                      # same digest as the agent sandbox
    eval_script_ref: str            # locator only; verifier reads it itself
    log_parser: str
    eval_type: str
    record_locator: str             # fixed record path (read-only)


@dataclass
class VerifierResult:
    status: str         # ok | patch_apply_failed | tests_not_run |
                        # verifier_timeout | infra_failure
    resolved: bool | None = None
    detail: str | None = None
    container_ids: list[str] = field(default_factory=list)
    eval_log_locator: str | None = None


class VerifierRunner:
    """Verifier logic only; the container lifecycle is owned by the runner.

    The runner creates a FRESH container from the pinned digest, takes the
    counter baseline, hands the handle to the verifier, takes the final
    counter read, archives, and only then tears the container down:
    create -> baseline -> execute -> final read -> archive -> teardown.
    The verifier never starts or stops its own container."""

    name = "abstract"

    def run(self, spec: VerifierSpec, candidate_patch: str | None,
            budget: BudgetTracker, recorder: SemanticRecorder,
            runtime: ContainerRuntime,
            container: ContainerHandle) -> VerifierResult:  # pragma: no cover
        raise NotImplementedError


class FakeVerifier(VerifierRunner):
    """Scripted verifier operating on the runner-provided container."""

    name = "fake"

    def __init__(self, clock, script: dict):
        self.clock = clock
        self.script = script
        self.seen_container_id: str | None = None

    def run(self, spec: VerifierSpec, candidate_patch: str | None,
            budget: BudgetTracker, recorder: SemanticRecorder,
            runtime: ContainerRuntime,
            container: ContainerHandle) -> VerifierResult:
        self.seen_container_id = container.container_id
        ev = recorder.begin("verifier", {"status": "running",
                                         "resolved": None})
        result = VerifierResult(status="ok",
                                container_ids=[container.container_id])
        try:
            if candidate_patch is None or not candidate_patch.strip():
                result.status = "patch_apply_failed"
                result.detail = "empty candidate patch"
                return result
            # apply + run tests (scripted); advance the clock to consume wall
            self.clock.advance_s(float(self.script.get("wall_s", 1.0)))
            budget.check(phase="evaluation")
            status = self.script.get("status", "ok")
            if status == "patch_apply_failed":
                result.status = "patch_apply_failed"
                result.detail = "simulated patch application failure"
                return result
            if status == "verifier_timeout":
                result.status = "verifier_timeout"
                result.detail = "simulated verifier wall exceeded"
                return result
            if status == "infra_failure":
                result.status = "infra_failure"
                result.detail = "simulated evaluator infrastructure failure"
                return result
            if status == "tests_not_run":
                result.status = "tests_not_run"
                result.detail = "SUITE_RAN guard: tests never executed"
                return result
            result.status = "ok"
            result.resolved = bool(self.script.get("resolved", False))
            result.eval_log_locator = f"fake-evallog-{uuid.uuid4().hex[:8]}"
            return result
        finally:
            recorder.end(ev, attrs={"status": result.status,
                                    "resolved": result.resolved,
                                    "detail": result.detail})


class SwebenchVerifierRunner(VerifierRunner):
    """Real evaluator runner replicating the official SWE-bench chain.

    Implements the run_instance semantics (fixed commit 02e7a74) on the
    runner-provided CLEAN container from the pinned digest:

    1. the candidate patch is written into the container via heredoc;
    2. the official GIT_APPLY_CMDS chain applies it (git apply --verbose /
       --3way / --reject / patch -p1), resetting the tree between failed
       attempts and honouring the "already applied" reverse-check;
    3. the fixed eval_script (from make_test_spec over the read-only
       record) is written to /eval.sh and executed — it checks out the
       base test files, applies the TEST patch and runs the suite;
    4. the test output is parsed with the official get_eval_report
       (parse_log_django for this instance; infra_failure semantics and
       the SUITE_RAN guard stay with the official parser).

    The verifier reads the test specs itself (record_locator); answers
    never flow back to a live agent. swebench imports are lazy so the
    default offline suite needs no swebench package; the parsing path is
    covered by tests/integration_swebench.py (explicit venv entry).
    Execution requires gate B/C authorization.
    """

    name = "swebench-02e7a74"

    PATCH_FILE = "/tmp/run01_patch.diff"
    EVAL_FILE = "/eval.sh"
    # same order as the official run_evaluation.GIT_APPLY_CMDS
    GIT_APPLY_CMDS = (
        "git apply --verbose",
        "git apply --verbose --3way",
        "git apply --verbose --reject",
        "patch --batch --forward --fuzz=5 -p1 -i",
    )
    HEREDOC_DELIM = "AWC_RUN01_EOF_7c2f"

    def __init__(self, *, authorized: bool = False,
                 model_name: str = "mini-swe-agent-2.4.6"):
        self.authorized = authorized
        self.model_name = model_name

    def _require_authorized(self) -> None:
        if not self.authorized:
            raise RuntimeError_(
                "swebench verifier not authorized; gate B/C required")

    # -- pure command construction (offline-testable) ----------------------

    def build_patch_heredoc(self, candidate_patch: str) -> str:
        if self.HEREDOC_DELIM in candidate_patch:
            raise ValueError(
                "candidate patch contains the heredoc delimiter; refusing "
                "to build an ambiguous command")
        return (f"cat > {self.PATCH_FILE} <<'{self.HEREDOC_DELIM}'\n"
                f"{candidate_patch}\n{self.HEREDOC_DELIM}")

    def build_eval_heredoc(self, eval_script: str) -> str:
        if self.HEREDOC_DELIM in eval_script:
            raise ValueError("eval script contains the heredoc delimiter")
        return (f"cat > {self.EVAL_FILE} <<'{self.HEREDOC_DELIM}'\n"
                f"{eval_script}\n{self.HEREDOC_DELIM}")

    def build_apply_chain(self) -> list[tuple[str, str]]:
        """(reset_command_or_empty, apply_command) pairs, official order."""
        chain = []
        for i, cmd in enumerate(self.GIT_APPLY_CMDS):
            reset = "" if i == 0 else "git checkout -- . ; git clean -fd"
            chain.append((reset, f"{cmd} {self.PATCH_FILE}"))
        return chain

    # -- execution ----------------------------------------------------------

    def run(self, spec: VerifierSpec, candidate_patch: str | None,
            budget: BudgetTracker, recorder: SemanticRecorder,
            runtime: ContainerRuntime,
            container: ContainerHandle) -> VerifierResult:
        self._require_authorized()
        from swebench.harness.utils import make_test_spec  # lazy: venv only
        from swebench.harness.grading import get_eval_report

        import time as _time
        result = VerifierResult(status="ok",
                                container_ids=[container.container_id])
        ev = recorder.begin("verifier", {"status": "running",
                                         "resolved": None})

        # ONE unified deadline: verifier phase wall minus already-elapsed
        # time, capped by the TOTAL run wall. Every container operation
        # gets at most the REMAINING time — no per-command 300 s budgets
        # that could stack up to multiples of the verifier allocation.
        deadline = _time.monotonic() + budget.remaining_s("evaluation")

        def remaining() -> float:
            return deadline - _time.monotonic()

        def op_timeout(floor: float = 1.0) -> int:
            return max(1, int(remaining())) if remaining() > 0 else 0

        # external stop condition: the in-flight artifact ceiling (the
        # monitor thread sets budget.artifact_exceeded even while this
        # call is blocked on a long container command)
        def stop_now() -> bool:
            return budget.artifact_exceeded

        def _deadline_exceeded(self_ignored=None) -> VerifierResult:
            # the local exec timeout only kills the docker CLI client;
            # make sure the in-container workload is ACTUALLY stopped
            # before the final counter read happens in the runner, and
            # record HOW CONFIRMED that stop is (confirmed / not
            # confirmed / counters possibly unreadable after docker stop)
            term = runtime.terminate_workload(container, 15)
            confirmed = term.get("confirmed")
            method = term.get("method")
            if confirmed and term.get("container_alive"):
                stop_state = "stopped_confirmed"
            elif confirmed:
                stop_state = ("stopped_via_docker_stop; "
                              "container exited; final counters may be "
                              "unreadable")
            else:
                stop_state = "stop_not_confirmed"
            result.status = "verifier_timeout"
            result.detail = (f"verifier deadline exceeded; workload "
                             f"termination={method}; stop_state={stop_state}")
            return result

        try:
            record = json.loads(Path(spec.record_locator).read_bytes())
            test_spec = make_test_spec(record)

            if candidate_patch is None or not candidate_patch.strip():
                result.status = "patch_apply_failed"
                result.detail = "empty candidate patch"
                return result

            # 1. write the patch into the container
            if remaining() <= 0:
                return _deadline_exceeded(None)
            w = runtime.execute(container,
                                self.build_patch_heredoc(candidate_patch),
                                op_timeout(), should_stop=stop_now)
            if w.get("returncode") != 0:
                result.status = "infra_failure"
                result.detail = "patch upload to container failed"
                return result

            # 2. official apply chain — each attempt bounded by the
            #    REMAINING deadline, not a fixed 300 s
            applied = False
            for reset, apply_cmd in self.build_apply_chain():
                if remaining() <= 0:
                    return _deadline_exceeded(None)
                if reset:
                    runtime.execute(container, reset, op_timeout(),
                                    should_stop=stop_now)
                r = runtime.execute(container, apply_cmd, op_timeout(),
                                    should_stop=stop_now)
                if r.get("returncode") == 0:
                    applied = True
                    break
            if not applied:
                if remaining() <= 0:
                    return _deadline_exceeded(None)
                rev = runtime.execute(
                    container,
                    f"git apply --check --reverse {self.PATCH_FILE}",
                    op_timeout())
                if rev.get("returncode") != 0:
                    result.status = "patch_apply_failed"
                    result.detail = "all official apply strategies failed"
                    return result
                applied = True  # verified already applied

            # 3. eval script (checks out base test files, applies test
            #    patch, runs the suite) — wall = remaining deadline
            budget.check(phase="evaluation")
            if remaining() <= 0:
                return _deadline_exceeded(None)
            e = runtime.execute(container, self.build_eval_heredoc(
                test_spec.eval_script), op_timeout(),
                should_stop=stop_now)
            if e.get("returncode") != 0:
                result.status = "infra_failure"
                result.detail = "eval script upload failed"
                return result
            out = runtime.execute(container, f"bash {self.EVAL_FILE}",
                                  max(1, int(remaining()) + 1),
                                  output_limit=2_000_000,
                                  should_stop=stop_now)
            if out.get("timed_out"):
                return _deadline_exceeded(None)
            log_text = out.get("output") or ""
            # official get_logs_eval only parses the slice between the
            # ">>>>> Start/End Test Output" markers; output without them
            # means the suite never ran (SUITE_RAN guard semantics)
            if (not log_text.strip()
                    or ">>>>> Start Test Output" not in log_text
                    or ">>>>> End Test Output" not in log_text):
                result.status = "tests_not_run"
                result.detail = ("no official test-output markers "
                                 "(suite never ran)")
                return result

            # 4. grade with the official parser
            log_dir = Path(recorder.run_dir) / "verifier"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "test_output.txt"
            log_path.write_text(log_text, encoding="utf-8")
            prediction = {"instance_id": spec.instance_id,
                          "model_name_or_path": self.model_name,
                          "model_patch": candidate_patch}
            report = get_eval_report(test_spec=test_spec,
                                     prediction=prediction,
                                     test_log_path=str(log_path),
                                     include_tests_status=True)
            entry = report[spec.instance_id]
            result.resolved = bool(entry.get("resolved"))
            result.eval_log_locator = str(log_path)
            result.detail = (f"patch_applied={applied}; "
                             f"infra_failure={entry.get('infra_failure')}")
            return result
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result.status = "infra_failure"
            result.detail = f"error:{type(exc).__name__}"
            return result
        finally:
            recorder.end(ev, attrs={"status": result.status,
                                    "resolved": result.resolved,
                                    "detail": result.detail})


# ---------------------------------------------------------------------------
# output guard for data/raw/generated (run directories)
# ---------------------------------------------------------------------------

def guard_run_dir(project_root: Path, destination: Path,
                  collection: str) -> Path:
    """Anchored, exclusive-create guard for one run directory.

    Rules:
    1. project_root resolves to a real directory (trusted anchor).
    2. data/raw/generated is not a symlink and resolves inside the project.
    3. EVERY segment of the collection path (and thus all ancestors below
       generated/) must be a real directory — any symlink segment is
       rejected outright, so a collection symlink cannot redirect writes
       to another tree inside or outside the project.
    4. The destination's fully-resolved path lies inside the resolved
       collection root (run-dir-name symlinks cannot escape either).
    5. The destination does not overlap protected read-only trees
       (references, data/catalog, data/raw/public, data/normalized,
       data/raw/replay, audit-catalogued legacy roots).
    6. The destination does not already exist (exclusive create).
    """
    project_root = project_root.resolve(strict=True)
    if project_root == Path(project_root.anchor):
        raise ValueError("filesystem root cannot be a project")
    gen_root = project_root / "data" / "raw" / "generated"
    if gen_root.is_symlink():
        raise ValueError("data/raw/generated must not be a symlink")
    gen_real = gen_root.resolve()
    if not gen_real.is_relative_to(project_root):
        raise ValueError("data/raw/generated resolves outside the project root")

    # walk every collection segment; symlinked segments are rejected
    # regardless of where they point (prevents escape via redirected dirs)
    current = gen_root
    for part in PurePath(collection).parts:
        if part in ("", ".", "..") or "/" in part or "\\" in part:
            raise ValueError(f"invalid collection path segment: {part!r}")
        current = current / part
        if current.is_symlink():
            raise ValueError(
                f"collection path segment is a symlink: {current}; run dirs "
                "must live on real paths under data/raw/generated")
    collection_real = (gen_root / collection).resolve()
    if not collection_real.is_relative_to(gen_real):
        raise ValueError("collection root resolves outside data/raw/generated")

    destination = destination if destination.is_absolute() else project_root / destination
    destination = destination.resolve()
    if destination == collection_real or not destination.is_relative_to(collection_real):
        raise ValueError(
            f"run dir must be inside data/raw/generated/{collection}/ (real path)")
    protected = [project_root / "references",
                 project_root / "data" / "catalog",
                 project_root / "data" / "raw" / "public",
                 project_root / "data" / "normalized",
                 project_root / "data" / "raw" / "replay",
                 *_catalog_protected_roots(project_root)]
    for path in protected:
        real = path.resolve()
        if (destination == real or destination.is_relative_to(real)
                or real.is_relative_to(destination)):
            raise ValueError(f"output overlaps protected path: {real}")
    if destination.exists():
        raise ValueError("run dir already exists; attempts are never overwritten")
    return destination


# ---------------------------------------------------------------------------
# sampler bridge
# ---------------------------------------------------------------------------

class _RuntimeScopeReader(ScopeReader):
    """Adapts a ContainerRuntime counter read to the ScopeReader API."""

    def __init__(self, runtime: ContainerRuntime, handle: ContainerHandle,
                 scope: str, scope_kind: str):
        self.runtime = runtime
        self.handle = handle
        self.scope = scope
        self.scope_kind = scope_kind

    def read(self, t_monotonic_ns: int) -> CounterSnapshot:
        snap = self.runtime.read_counters(self.handle, t_monotonic_ns)
        snap.scope = self.scope
        snap.scope_kind = self.scope_kind
        return snap


def _dir_size_bytes(path: Path) -> int:
    """Actual on-disk size of a directory tree (regular files only)."""
    total = 0
    try:
        stack = [path]
        while stack:
            current = stack.pop()
            try:
                for entry in current.iterdir():
                    if entry.is_symlink():
                        continue
                    if entry.is_file():
                        total += entry.stat().st_size
                    elif entry.is_dir():
                        stack.append(entry)
            except OSError:
                continue
    except OSError:
        return total
    return total


class _ArtifactMonitor(threading.Thread):
    """In-flight OVER-LIMIT DETECTION with a STOP mechanism for the run
    directory (bounded scope, NOT an absolute storage quota):

    - scope: the run_dir tree only. Container WRITABLE LAYERS are outside
      this check (they are constrained separately via the container's
      --storage-opt size when the daemon/filesystem supports it — checked
      in gate-B canary r7 — and are reclaimed at container removal);
    - detection is polled (interval_s, default 0.25 s): a write burst can
      overshoot the ceiling by (burst rate × interval) before the stop
      trips — this is a DETECTION LATENCY, not a hard guarantee;
    - once tripped, budget.check() raises for the harness poll loop and
      for verifier executions interrupted via should_stop, stopping the
      run at the next observable boundary.

    The archive-time accounting remains for precise bookkeeping. The C
    approval wording must describe this mechanism as bounded-scope
    over-limit detection with declared latency and overshoot — NOT as a
    hard 5 GiB ceiling."""

    def __init__(self, run_dir: Path, budget: "BudgetTracker",
                 interval_s: float = 0.25):
        super().__init__(daemon=True)
        self.run_dir = run_dir
        self.budget = budget
        self.interval_s = interval_s
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            if self.budget.artifact_exceeded:
                return
            size = _dir_size_bytes(self.run_dir)
            if size > self.budget.limits.max_new_artifact_bytes:
                self.budget.account_artifact_bytes(size)  # marks exceeded
                return
            self._stop.wait(self.interval_s)

    def stop(self) -> None:
        self._stop.set()


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

_ARTIFACT_ACCOUNTING_NOTE = (
    "artifact accounting covers runner-archived files plus events.jsonl; "
    "it is NOT a claim over all process outputs of the run")


@dataclass
class PilotOutcome:
    run_id: str
    attempt_id: str
    execution_status: str
    evaluation_status: str
    archive_status: str
    run_dir: str
    resolved: bool | None
    budget_usage: dict
    source_type: str
    cleanup_status: str = "ok"
    cleanup_errors: list[str] = field(default_factory=list)


class CodingPilotRunner:
    """One attempt over one fixed task with full offline-safe accounting."""

    def __init__(self, *, project_root: Path, collection: str,
                 harness: AgentHarness, verifier: VerifierRunner,
                 runtime: ContainerRuntime, clock: Clock | None = None,
                 limits: BudgetLimits | None = None,
                 task: AgentTask | None = None,
                 verifier_spec: VerifierSpec | None = None,
                 image: str = "synthetic-image:latest",
                 source_type: str = "synthetic",
                 interval_s: float = 0.5,
                 host_runtime_reader: ScopeReader | None = None,
                 monitor_interval_s: float = 0.25,
                 credentials: dict[str, str] | None = None,
                 agent_container_cpu: str | None = None,
                 agent_container_mem: str | None = None,
                 verifier_container_cpu: str | None = None,
                 verifier_container_mem: str | None = None):
        self.project_root = project_root.resolve(strict=True)
        self.collection = collection
        self.harness = harness
        self.verifier = verifier
        self.runtime = runtime
        self.clock = clock or SystemClock()
        self.limits = limits or BudgetLimits()
        self.task = task
        self.verifier_spec = verifier_spec
        self.image = image
        self.source_type = source_type
        self.interval_s = interval_s
        self.host_runtime_reader = host_runtime_reader
        self.monitor_interval_s = monitor_interval_s
        # credentials live ONLY in memory for the duration of the run:
        # passed through to the harness child's process environment; never
        # persisted, never logged (gate C wiring)
        self.credentials = credentials
        self.agent_container_cpu = agent_container_cpu
        self.agent_container_mem = agent_container_mem
        self.verifier_container_cpu = verifier_container_cpu
        self.verifier_container_mem = verifier_container_mem
        self._watchdog = WallWatchdog()

    # -- public entry -------------------------------------------------------

    def run(self) -> PilotOutcome:
        run_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:6]}"
        attempt_id = f"{run_id}-a1"
        run_dir = guard_run_dir(self.project_root,
                                Path("data/raw/generated") / self.collection / run_id,
                                self.collection)
        run_dir.mkdir(parents=True)
        recorder = SemanticRecorder(
            run_dir, self.clock, run_id=run_id, attempt_id=attempt_id,
            task_id=self.task.instance_id if self.task else "unknown",
            source_type=self.source_type)
        budget = BudgetTracker(self.limits, self.clock)
        sampler = ResourceSampler(clock=self.clock, interval_s=self.interval_s)

        execution_status = "infra_failure"
        evaluation_status = "not_run"
        archive_status = "failed"
        agent_result: AgentResult | None = None
        verifier_result: VerifierResult | None = None
        agent_handle: ContainerHandle | None = None
        verifier_handle: ContainerHandle | None = None
        cleanup_errors: list[str] = []
        agent_scope = f"{run_id}-agent-sandbox"
        verifier_scope = f"{run_id}-verifier"
        host_scope = f"{run_id}-host-runtime"
        # in-flight hard artifact ceiling covering execution + evaluation
        artifact_monitor = _ArtifactMonitor(run_dir, budget,
                                            self.monitor_interval_s)
        artifact_monitor.start()

        try:
            recorder.begin_run()
            budget.start()
            if self.host_runtime_reader is not None:
                sampler.register(host_scope, "host_agent_runtime",
                                 self.host_runtime_reader)
                sampler.start(host_scope)
            # execution phase ------------------------------------------------
            if self.task is not None:
                agent_handle = self.runtime.start(ContainerSpec(
                    run_id=run_id, scope="agent", image=self.image,
                    cpu_limit=self.agent_container_cpu,
                    mem_limit=self.agent_container_mem,
                    network="none", pull="never"))
                recorder.point("container", {
                    "container_id": agent_handle.container_id,
                    "image": self.image, "scope": "agent",
                    "action": "start", "detail": "agent sandbox"})
                sampler.register(agent_scope, "agent_container",
                                 _RuntimeScopeReader(self.runtime, agent_handle,
                                                     agent_scope, "agent_container"))
                sampler.start(agent_scope)
                sampler.start_background_sampling()
                agent_result = self._run_execution(recorder, budget,
                                                   agent_handle, run_dir)
                execution_status = agent_result.status
                sampler.stop(agent_scope)  # BEFORE teardown
                # The verifier is a distinct sequential phase.  The agent
                # container must be removed and verified before verifier
                # creation; a shared live container would violate the
                # approved attempt boundary.
                self._stop_and_verify_container(agent_handle, recorder,
                                                budget=budget, phase="agent")
                agent_handle = None
            # evaluation phase -----------------------------------------------
            # lifecycle: create -> baseline -> execute -> final read ->
            # archive -> teardown (teardown happens in the outer finally,
            # after the archive phase below has persisted all evidence)
            if execution_status in ("ok",) and agent_result is not None:
                if not agent_result.candidate_patch:
                    execution_status = "no_candidate"
                else:
                    budget.begin_phase("evaluation")
                    verifier_handle = self.runtime.start(ContainerSpec(
                        run_id=run_id, scope="verifier",
                        image=(self.verifier_spec.image
                               if self.verifier_spec else self.image),
                        cpu_limit=self.verifier_container_cpu,
                        mem_limit=self.verifier_container_mem,
                        network="none", pull="never"))
                    recorder.point("container", {
                        "container_id": verifier_handle.container_id,
                        "image": (self.verifier_spec.image
                                  if self.verifier_spec else self.image),
                        "scope": "verifier", "action": "start",
                        "detail": "independent clean verifier container"})
                    sampler.register(
                        verifier_scope, "verifier_container",
                        _RuntimeScopeReader(self.runtime, verifier_handle,
                                            verifier_scope,
                                            "verifier_container"))
                    sampler.start(verifier_scope)
                    vev = recorder.begin("verifier", {"status": "starting",
                                                      "resolved": None})
                    recorder.end(vev, attrs={"status": "phase_begin",
                                             "resolved": None})
                    try:
                        verifier_result = self.verifier.run(
                            self.verifier_spec, agent_result.candidate_patch,
                            budget, recorder, self.runtime, verifier_handle)
                        evaluation_status = verifier_result.status
                    except BudgetExceeded as exc:
                        evaluation_status = "verifier_timeout"
                        recorder.point("budget", {
                            "limit_name": exc.limit_name,
                            "observed": exc.observed,
                            "detail": "verifier wall exceeded"})
                    finally:
                        sampler.stop(verifier_scope)  # BEFORE teardown
                    self._stop_and_verify_container(verifier_handle, recorder,
                                                    budget=budget, phase="verifier")
                    verifier_handle = None
            elif execution_status == "no_candidate":
                recorder.point("verifier", {"status": "not_run",
                                            "resolved": None,
                                            "detail": "no candidate patch"})
            if self.host_runtime_reader is not None:
                sampler.stop(host_scope)
            # archive phase --------------------------------------------------
            archive_status = self._archive(
                run_dir, recorder, sampler, budget, agent_result,
                verifier_result, execution_status, evaluation_status)
        except RuntimeError_ as exc:
            execution_status = "infra_failure"
            if self.host_runtime_reader is not None:
                try:
                    sampler.stop(host_scope)
                except KeyError:
                    pass
            recorder.point("infra", {"status": "infra_failure",
                                     "detail": f"error:{type(exc).__name__}"})
            archive_status = self._archive(
                run_dir, recorder, sampler, budget, agent_result,
                verifier_result, execution_status, evaluation_status)
        finally:
            # stop the sampling thread FIRST, then tear down containers:
            # boundary reads already happened, but a stray sample must never
            # race a container removal
            artifact_monitor.stop()
            sampler.stop_background_sampling()
            for handle in (agent_handle, verifier_handle):
                if handle is not None:
                    try:
                        timeout_s = budget.remaining_s()
                        self.runtime.stop(handle, timeout_s=timeout_s)
                        removal = self.runtime.verify_removal(
                            handle, timeout_s=max(0.0, budget.remaining_s()))
                        if removal != "removed":
                            cleanup_errors.append(
                                f"{handle.spec.scope}:removal={removal}")
                    except Exception as exc:  # noqa: BLE001
                        cleanup_errors.append(
                            f"{handle.spec.scope}:{type(exc).__name__}")
            try:
                cleanup_result = self.runtime.cleanup_run(
                    run_id, timeout_s=budget.remaining_s())
                if getattr(cleanup_result, "status", "failed") != "confirmed":
                    cleanup_errors.append(
                        "cleanup_run:"
                        f"{getattr(cleanup_result, 'status', 'unknown')}"
                    )
                    cleanup_errors.extend(
                        f"cleanup_run:{error}"
                        for error in getattr(cleanup_result, "errors", []))
                    cleanup_errors.extend(
                        f"cleanup_run:unconfirmed:{name}"
                        for name in getattr(cleanup_result, "unconfirmed", []))
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(f"cleanup_run:{type(exc).__name__}")

        resolved = verifier_result.resolved if (verifier_result is not None
                                                and verifier_result.status == "ok") else None
        return PilotOutcome(
            run_id=run_id, attempt_id=attempt_id,
            execution_status=execution_status,
            evaluation_status=evaluation_status,
            archive_status=archive_status,
            run_dir=str(run_dir), resolved=resolved,
            budget_usage=budget.usage_dict(),
            source_type=self.source_type,
            cleanup_status="failed" if cleanup_errors else "ok",
            cleanup_errors=cleanup_errors)

    def _stop_and_verify_container(self, handle: ContainerHandle,
                                   recorder: SemanticRecorder,
                                   *, budget: BudgetTracker, phase: str):
        """Stop one owned container and retain explicit removal evidence."""
        try:
            self.runtime.stop(handle, timeout_s=budget.remaining_s())
            removal = self.runtime.verify_removal(
                handle, timeout_s=budget.remaining_s())
        except Exception as exc:  # noqa: BLE001 — archive the failure fact
            recorder.point("container", {
                "container_id": handle.container_id,
                "image": handle.spec.image,
                "scope": phase,
                "action": "stop_and_verify_removal",
                "removal": "check_failed",
                "error": type(exc).__name__,
            })
            raise RuntimeError_(f"{phase} container cleanup failed") from exc
        recorder.point("container", {
            "container_id": handle.container_id,
            "image": handle.spec.image,
            "scope": phase,
            "action": "stop_and_verify_removal",
            "removal": removal,
        })
        if removal != "removed":
            raise RuntimeError_(
                f"{phase} container cleanup not confirmed: {removal}")

    # -- phases -------------------------------------------------------------

    def _run_execution(self, recorder: SemanticRecorder, budget: BudgetTracker,
                       agent_handle: ContainerHandle,
                       run_dir: Path) -> AgentResult:
        """Run the harness with wall watchdog coverage.

        The watchdog enforces the hard wall over real subprocesses the
        harness spawns (fake harness registers its blocking child; the real
        mini harness registers its venv subprocess in gate C)."""
        result_box: dict[str, Any] = {}

        def _target():
            try:
                result_box["result"] = self.harness.run(
                    self.task, budget, recorder, self.runtime, agent_handle,
                    wd, run_dir, credentials=self.credentials)
            except BudgetExceeded as exc:
                recorder.point("budget", {"limit_name": exc.limit_name,
                                          "observed": exc.observed,
                                          "detail": "execution budget"})
                result_box["budget"] = exc
            except AgentError as exc:
                result_box["agent_error"] = exc
            except RuntimeError_ as exc:
                result_box["infra"] = exc

        wd = WallWatchdog(self.clock)
        self._watchdog = wd
        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        wd_thread = threading.Thread(
            target=wd.enforce, args=(self.limits.agent_wall_s,), daemon=True)
        wd_thread.start()
        thread.join(timeout=self.limits.agent_wall_s + 5)
        wd.cancel()  # retire the watchdog once the harness thread is done
        if wd.killed:
            # killing the harness subprocess does not stop commands it
            # launched inside the container — terminate and record
            try:
                termination = self.runtime.terminate_workload(agent_handle)
                recorder.point("container", {
                    "container_id": agent_handle.container_id,
                    "image": agent_handle.spec.image, "scope": "agent",
                    "action": "terminate_workload",
                    "detail": (f"method={termination.get('method')}; "
                               f"confirmed={termination.get('confirmed')}; "
                               f"container_alive="
                               f"{termination.get('container_alive')}")})
                stop_note = (f"watchdog killed {len(wd.killed)} pids; "
                             f"workload_stop_confirmed="
                             f"{termination.get('confirmed')}")
            except Exception as exc:  # noqa: BLE001 — record, keep going
                stop_note = (f"watchdog killed {len(wd.killed)} pids; "
                             f"workload termination failed:"
                             f"{type(exc).__name__}")
            return AgentResult(status="watchdog_timeout", candidate_patch=None,
                               stop_reason=stop_note)
        if "budget" in result_box:
            return AgentResult(status="budget_exceeded", candidate_patch=None,
                               stop_reason=result_box["budget"].limit_name)
        if "infra" in result_box:
            return AgentResult(status="infra_failure", candidate_patch=None,
                               error=str(result_box["infra"]))
        if "agent_error" in result_box:
            return AgentResult(status="agent_error", candidate_patch=None,
                               error=str(result_box["agent_error"]))
        if "result" in result_box:
            result: AgentResult = result_box["result"]
            if result.status == "ok" and result.nested_retry_detected:
                # retries were COUNTED in the request budget (not free); the
                # violation flag itself is evidence, not a silent pass
                recorder.point("budget", {
                    "limit_name": "nested_retry_detected",
                    "observed": True,
                    "detail": "multiple model calls within one step counted "
                              "in the request budget"})
            return result
        return AgentResult(status="watchdog_timeout", candidate_patch=None,
                           stop_reason="harness thread did not finish")

    # -- archive ------------------------------------------------------------

    def _archive(self, run_dir: Path, recorder: SemanticRecorder,
                 sampler: ResourceSampler, budget: BudgetTracker,
                 agent_result: AgentResult | None,
                 verifier_result: VerifierResult | None,
                 execution_status: str, evaluation_status: str) -> str:
        """Persist everything; never executes candidate code on the host.

        Soft artifact budgeting: every write is accounted BEFORE it happens;
        optional large artifacts (candidate patch, samples evidence) are
        SKIPPED when they would exceed the ceiling, while the minimal
        failure evidence (metadata + manifest) is always written. Hitting
        the ceiling therefore yields archive_status='budget_exceeded' with
        a delivered outcome — it never aborts the run with an exception.

        Accounting scope (declared in metadata, not silently broader):
        runner-archived files plus events.jsonl. This is NOT a claim over
        all outputs of the run's processes (e.g. harness/verifier working
        directories or container layers)."""
        skipped: list[str] = []
        accounted: list[str] = []

        def _write_accounted(path: Path, data: bytes, *,
                             optional: bool) -> bool:
            if optional and budget.would_exceed_artifacts(len(data)):
                skipped.append(path.name)
                return False
            budget.account_artifact_bytes(len(data))
            path.write_bytes(data)
            accounted.append(path.name)
            return True

        try:
            if agent_result is not None and agent_result.candidate_patch:
                _write_accounted(run_dir / "candidate.patch",
                                 agent_result.candidate_patch.encode("utf-8"),
                                 optional=True)
            # seal FIRST, then account the (now final) events.jsonl size
            seal = recorder.seal()
            events_path = run_dir / "events.jsonl"
            if events_path.is_file():
                budget.account_artifact_bytes(events_path.stat().st_size)
                accounted.append(events_path.name)
            samples = {
                "interval_s": self.interval_s,
                "scopes": sampler.all_scope_summaries(),
                "evidence": sampler.all_scope_evidence(),
                "collector": sampler.collector_self_observation(),
            }
            _write_accounted(
                run_dir / "samples.json",
                (json.dumps(samples, ensure_ascii=False, indent=2) + "\n")
                .encode("utf-8"),
                optional=True)
            # account EVERYTHING else already present in the run dir
            # (harness-child status/trajectory, verifier logs) — the
            # in-flight monitor polices the full tree, so the archive
            # accounting must cover the same scope. metadata.json and
            # manifest.json are accounted when written below.
            already = {run_dir / "candidate.patch",
                       run_dir / "events.jsonl",
                       run_dir / "samples.json"}
            for p in sorted(run_dir.rglob("*")):
                if p.is_file() and p not in already:
                    budget.account_artifact_bytes(p.stat().st_size)
                    accounted.append(str(p.relative_to(run_dir)))
            meta = {
                "run_id": recorder.run_id,
                "attempt_id": recorder.attempt_id,
                "task_id": recorder.task_id,
                "source_type": self.source_type,
                "execution_status": execution_status,
                "evaluation_status": evaluation_status,
                "budget_limits": self.limits.to_dict(),
                "budget_usage": budget.usage_dict(),
                "resolved": (verifier_result.resolved
                             if verifier_result else None),
                "nested_retry_detected": (agent_result.nested_retry_detected
                                          if agent_result else False),
                "events_sealed": seal,
                "archive": {
                    "skipped_files": skipped,
                    "artifact_exceeded": budget.artifact_exceeded,
                    "artifact_accounting_scope": (
                        "ALL files present in run_dir at archive time "
                        "(recursive: runner archives, harness-child "
                        "status/trajectory, verifier logs) plus metadata."
                        "json and manifest.json themselves; NOT a claim "
                        "over process outputs outside the run dir "
                        "(container writable layers)"),
                },
            }
            # minimal failure evidence: always written even over ceiling
            _write_accounted(run_dir / "metadata.json",
                             (json.dumps(meta, ensure_ascii=False, indent=2)
                              + "\n").encode("utf-8"),
                             optional=False)
            files = {}
            for child in sorted(run_dir.rglob("*")):
                if child.is_file() and child.name != "manifest.json":
                    files[str(child.relative_to(run_dir))] = hashlib.sha256(
                        child.read_bytes()).hexdigest()
            _write_accounted(run_dir / "manifest.json",
                             (json.dumps({"files": files,
                                          "sealed": True,
                                          "claim": ("attempt archived; statuses "
                                                    "are independent; "
                                                    "append-only")},
                                          ensure_ascii=False, indent=2)
                              + "\n").encode("utf-8"),
                             optional=False)
            if budget.artifact_exceeded:
                return "budget_exceeded"
            return "ok"
        except (OSError, TypeError, ValueError) as exc:
            # the recorder may already be sealed here — failures are recorded
            # as a sidecar file, never by rewriting sealed events
            try:
                (run_dir / "archive_error.txt").write_text(
                    f"error:{type(exc).__name__}\n", encoding="utf-8")
            except OSError:
                pass
            return "failed"
