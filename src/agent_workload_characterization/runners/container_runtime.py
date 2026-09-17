"""Container runtime abstraction for the coding pilot.

Two implementations:
- FakeContainerRuntime: fully synthetic, scripted lifecycle + counters for
  offline tests (no Docker, no processes beyond optional test helpers).
- DockerCliRuntime: the real local-docker path (docker run/exec/rm over the
  local unix socket). Gate A develops and unit-checks ARGV construction
  only; no container is ever started in this batch. Every runtime call is
  gated behind an `authorized` flag which the pilot flips only after the
  user approves gate B/C.

Identity rule: every container name carries the owning run_id so cleanup
can only ever touch resources created by THIS run attempt.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..collectors.resource_sampler import (CounterSnapshot, ScopeReader)


class RuntimeError_(RuntimeError):
    """Runtime-level failure (infrastructure), distinct from task failure."""


@dataclass
class ContainerSpec:
    run_id: str
    scope: str                 # e.g. agent_sandbox / verifier
    image: str                 # full reference; digest form after pinning
    cwd: str = "/testbed"
    env: dict[str, str] = field(default_factory=dict)
    timeout_s: int = 60
    mem_limit: str | None = None     # e.g. "8g"
    cpu_limit: str | None = None     # e.g. "4"
    network: str = "none"            # default offline; any change needs gate C
    platform: str | None = None      # e.g. "linux/amd64" for emulated runs
    pull: str | None = None          # "never" -> --pull=never (forbid
                                     # any implicit image pull)
    storage_size: str | None = None  # e.g. "6g" writable-layer quota via
                                     # --storage-opt size=... (requires
                                     # overlay2 on xfs with pquota; support
                                     # is verified, not assumed)


@dataclass
class ContainerHandle:
    container_id: str
    spec: ContainerSpec
    cgroup_dir: Path | None = None
    cgroup_version: str | None = None
    status: str = "running"


class CleanupResult(list):
    """List-compatible cleanup result with explicit confirmation state."""

    def __init__(self, confirmed=None, *, status="confirmed", errors=None,
                 unconfirmed=None):
        super().__init__(confirmed or [])
        self.status = status
        self.errors = list(errors or [])
        self.unconfirmed = list(unconfirmed or [])


class ContainerRuntime:
    """Lifecycle + execution + counter reads for containers."""

    name = "abstract"

    def start(self, spec: ContainerSpec) -> ContainerHandle:  # pragma: no cover
        raise NotImplementedError

    def execute(self, handle: ContainerHandle, command: str,
                timeout_s, *, output_limit: int = 100_000,
                should_stop=None) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def open_interactive(self, handle: ContainerHandle, command: str,
                         timeout_s: float):  # pragma: no cover
        """Open one persistent stdin/stdout worker session."""
        raise NotImplementedError

    def read_counters(self, handle: ContainerHandle,
                      t_monotonic_ns: int) -> CounterSnapshot:  # pragma: no cover
        raise NotImplementedError

    def terminate_workload(self, handle: ContainerHandle,
                           timeout_s: float = 15.0,
                           step_share_deadline: float | None = None
                           ) -> dict:  # pragma: no cover
        """Stop in-container work WITHOUT removing the container.

        A local `docker exec` timeout only kills the CLIENT-side docker
        CLI process — the command keeps running inside the container.
        Verifier/agent timeouts must call this so the measured workload is
        actually stopped before the final counter read.

        Result contract (three distinguishable outcomes):
        - {"confirmed": True,  "container_alive": True}  — the process-
          tree check returned EXPLICITLY 0 (nothing but the container's
          main process and the check itself remains; name-pattern kills
          alone never confirm);
        - {"confirmed": bool,  "container_alive": False} — fallback
          docker stop (kills everything; the container is EXITED and its
          cgroup counters may be gone/unreadable afterwards);
        - {"confirmed": False, ...} — neither path could prove the
          workload stopped (record as NOT-confirmed, never as success)."""
        raise NotImplementedError

    def stop(self, handle: ContainerHandle,
             timeout_s: float = 60.0) -> None:  # pragma: no cover
        raise NotImplementedError

    def cleanup_run(self, run_id: str,
                    timeout_s: float = 60.0) -> CleanupResult:  # pragma: no cover
        raise NotImplementedError

    def verify_removal(self, handle: ContainerHandle,
                       timeout_s: float = 30.0) -> str:
        """Three-way removal verification: 'removed' / 'still_exists' /
        'check_failed'. Implementations MUST NOT silently map errors to
        'removed' — a check failure is 'check_failed', not success."""
        raise NotImplementedError

    def container_init_pid(self, handle: ContainerHandle,
                           timeout_s: float = 10.0) -> int | None:
        """Host-side PID of the container's init process (docker inspect
        State.Pid). Minimal addition for CPU-02: the container-PID ->
        host-PID mapping needs the pid-namespace anchor; inspecting the
        init PID alone does NOT identify an exec'd process — callers must
        combine it with NSpid/inode/starttime checks."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# fake (synthetic tests)
# ---------------------------------------------------------------------------

class FakeContainerRuntime(ContainerRuntime):
    """Scripted runtime: no Docker, no model, deterministic behavior."""

    name = "fake"

    def __init__(self, clock, readers: dict[str, ScopeReader] | None = None):
        self.clock = clock
        self.readers = dict(readers or {})
        self.containers: dict[str, ContainerHandle] = {}
        self.foreign_containers: set[str] = set()  # never touched by cleanup
        self.started: list[ContainerSpec] = []
        self.active_at_start: list[list[str]] = []
        self.stop_calls: list[float] = []
        self.cleanup_calls: list[float] = []
        self.stopped: list[str] = []
        self.read_log: list[tuple[str, str]] = []  # (scope, container status at read)
        self.terminated: list[str] = []
        self.terminate_calls: list[dict] = []
        self.next_terminate_result: dict | None = None
        self.next_verify_result: str | None = None
        self.next_start_fails = False
        self.execute_script: dict[str, dict[str, Any]] = {}
        self.default_exec = {"returncode": 0, "output": "fake-output"}
        self.init_pids: dict[str, int] = {}  # container_id -> host init pid

    def container_init_pid(self, handle: ContainerHandle,
                           timeout_s: float = 10.0) -> int | None:
        return self.init_pids.get(handle.container_id)

    def add_foreign_container(self, name: str) -> None:
        """A container owned by someone else; cleanup must leave it alone."""
        self.foreign_containers.add(name)

    def start(self, spec: ContainerSpec,
              timeout_s: int = 60) -> ContainerHandle:
        if self.next_start_fails:
            self.next_start_fails = False
            raise RuntimeError_("fake: container start failure injected")
        self.active_at_start.append(list(self.containers))
        handle = ContainerHandle(
            container_id=f"fake-{spec.run_id}-{len(self.started):04d}",
            spec=spec)
        self.containers[handle.container_id] = handle
        self.started.append(spec)
        return handle

    def execute(self, handle: ContainerHandle, command: str,
                timeout_s: int, *, output_limit: int = 100_000,
                should_stop=None) -> dict[str, Any]:
        if handle.container_id not in self.containers:
            raise RuntimeError_("fake: unknown container")
        result = dict(self.execute_script.get(command, self.default_exec))
        result["duration_s"] = 0.0
        result["output"] = (result.get("output") or "")[:output_limit]
        if should_stop is not None and should_stop():
            result.update({"returncode": 124, "timed_out": True,
                           "stopped_by": "external"})
        return result

    def read_counters(self, handle: ContainerHandle,
                      t_monotonic_ns: int) -> CounterSnapshot:
        status = ("absent" if handle.container_id not in self.containers
                  else self.containers[handle.container_id].status)
        self.read_log.append((handle.spec.scope, status))
        reader = self.readers.get(handle.spec.scope)
        if reader is None:
            return CounterSnapshot(
                scope=handle.spec.scope, scope_kind="agent_container",
                t_monotonic_ns=t_monotonic_ns,
                read_status={"all": "no_reader_registered"})
        return reader.read(t_monotonic_ns)

    def terminate_workload(self, handle: ContainerHandle,
                           timeout_s: int = 15,
                           step_share_deadline: float | None = None) -> dict:
        """Record-only fake; inject `next_terminate_result` to test the
        not-confirmed / docker-stop paths. Records the received
        timeout_s and step_share_deadline for budget assertions."""
        self.terminated.append(handle.container_id)
        self.terminate_calls.append({
            "timeout_s": timeout_s,
            "step_share_deadline": step_share_deadline,
            "monotonic": time.monotonic()})
        result = dict(self.next_terminate_result
                      or {"confirmed": True, "method": "pkill",
                          "container_alive": True})
        self.next_terminate_result = None
        return result

    def stop(self, handle: ContainerHandle, timeout_s: float = 60.0) -> None:
        self.stop_calls.append(timeout_s)
        handle.status = "stopped"
        self.stopped.append(handle.container_id)
        self.containers.pop(handle.container_id, None)

    def cleanup_run(self, run_id: str, timeout_s: float = 60.0) -> CleanupResult:
        self.cleanup_calls.append(timeout_s)
        removed = []
        for cid in list(self.containers):
            if cid.startswith(f"fake-{run_id}-"):
                self.stopped.append(cid)
                del self.containers[cid]
                removed.append(cid)
        # foreign containers intentionally untouched
        return CleanupResult(removed)

    def verify_removal(self, handle: ContainerHandle,
                       timeout_s: float = 30.0) -> str:
        """Fake: no Docker calls — checks the in-memory containers map.
        Inject `next_verify_result` to test the three-way semantics."""
        if self.next_verify_result is not None:
            result = self.next_verify_result
            self.next_verify_result = None
            return result
        return "removed" if handle.container_id not in self.containers \
            else "still_exists"


# ---------------------------------------------------------------------------
# real docker CLI (developed in gate A; executed only after gate B/C approval)
# ---------------------------------------------------------------------------

class DockerCliRuntime(ContainerRuntime):
    """Local docker CLI runtime. NO call is made unless authorized=True."""

    name = "docker_cli"

    def __init__(self, *, authorized: bool = False,
                 docker_executable: str = "docker",
                 collection: str = "RUN-01"):
        self.authorized = authorized
        self.executable = docker_executable
        self.collection = collection
        self._name_prefix = ("awc-run01" if collection == "RUN-01"
                              else f"awc-{collection.lower()}")
        self._seq = 0
        self.pending_names: dict[str, dict] = {}

    def _require_authorized(self) -> None:
        if not self.authorized:
            raise RuntimeError_(
                "docker runtime not authorized (gate B/C approval required); "
                "construction-time checks only in gate A")

    def _container_name(self, spec: ContainerSpec) -> str:
        self._seq += 1
        return f"{self._name_prefix}-{spec.run_id}-{spec.scope}-{self._seq:03d}"

    def build_run_argv(self, spec: ContainerSpec, name: str) -> list[str]:
        """ARGV for `docker run` — pure construction, unit-testable offline."""
        argv = [self.executable, "run", "-d", "--name", name,
                "--network", spec.network, "-w", spec.cwd]
        if spec.platform:
            argv += ["--platform", spec.platform]
        if spec.mem_limit:
            argv += ["--memory", spec.mem_limit]
        if spec.cpu_limit:
            argv += ["--cpus", spec.cpu_limit]
        if spec.pull:
            argv += ["--pull", spec.pull]
        if spec.storage_size:
            argv += ["--storage-opt", f"size={spec.storage_size}"]
        for key, value in sorted(spec.env.items()):
            argv += ["-e", f"{key}={value}"]
        argv += [spec.image, "sleep", "2h"]
        return argv

    def start(self, spec: ContainerSpec,
              timeout_s: int = 60,
              deadline: float | None = None) -> ContainerHandle:
        """Create a container with an ABSOLUTE deadline budget.

        ``deadline`` (preferred): both the create call and cgroup
        resolution derive their timeout from the REMAINING time to
        this absolute monotonic deadline — the create's elapsed time
        is subtracted before _resolve_cgroup gets its share.
        ``timeout_s`` (legacy): total budget; deadline is set at entry.

        The container NAME is registered in ``pending_names`` BEFORE
        the docker call; a lost response leaves a cleanable identity
        that ``cleanup_pending`` consumes (see below)."""
        import time as _time
        import uuid
        self._require_authorized()
        if deadline is None:
            deadline = _time.monotonic() + timeout_s
        name = self._container_name(spec)
        self.pending_names[name] = {"run_id": spec.run_id,
                                    "registered_at": _time.monotonic()}
        argv = self.build_run_argv(spec, name)
        create_to = deadline - _time.monotonic()
        if create_to <= 0:
            self.pending_names.pop(name, None)
            raise RuntimeError_("start budget exhausted before create")
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=create_to)
        if proc.returncode != 0:
            self.pending_names.pop(name, None)
            raise RuntimeError_(f"docker run failed rc={proc.returncode}")
        cid = proc.stdout.strip()
        # create confirmed: no longer pending
        self.pending_names.pop(name, None)
        handle = ContainerHandle(container_id=cid, spec=spec)
        resolve_to = deadline - _time.monotonic()
        if resolve_to <= 0:
            handle.cgroup_version = "unresolved"
            return handle
        try:
            self._resolve_cgroup(handle, timeout_s=resolve_to)
        except Exception:  # noqa: BLE001
            handle.cgroup_version = "unresolved"
        return handle

    # hard cap on captured output regardless of the caller's limit
    MAX_CAPTURE_BYTES = 16 * 1024 * 1024

    def build_exec_argv(self, handle: ContainerHandle, command: str) -> list[str]:
        return [self.executable, "exec", "-w", handle.spec.cwd,
                handle.container_id, "bash", "-lc", command]

    def execute(self, handle: ContainerHandle, command: str,
                timeout_s, *, output_limit: int = 100_000,
                should_stop=None) -> dict[str, Any]:
        """Run a command in the container with CONTINUOUS pipe draining.

        The reader thread uses FIXED-SIZE BINARY blocks. All three exit
        paths (normal / timeout / external stop) apply the same
        output_limit. Timeouts and external stops also terminate the
        in-container workload via the shared-deadline stop chain."""
        self._require_authorized()
        argv = self.build_exec_argv(handle, command)
        import subprocess as _sp
        import threading as _th
        try:
            proc = _sp.Popen(argv, stdout=_sp.PIPE, stderr=_sp.STDOUT)
        except OSError as exc:
            return {"returncode": -1, "output": f"error:{type(exc).__name__}"}

        state = {"total": 0}
        kept = bytearray()

        def _drain():
            while True:
                try:
                    block = proc.stdout.read(65536)
                except (OSError, ValueError):
                    return
                if not block:
                    return
                state["total"] += len(block)
                cap = self.MAX_CAPTURE_BYTES
                if len(kept) < cap:
                    kept.extend(block[:cap - len(kept)])

        reader = _th.Thread(target=_drain, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout_s
        stopped_by = None
        while proc.poll() is None:
            if should_stop is not None and should_stop():
                stopped_by = "external"
                break
            if time.monotonic() > deadline:
                stopped_by = "timeout"
                break
            time.sleep(0.05)
        if stopped_by is not None:
            proc.kill()
        reader.join(timeout=2)
        if reader.is_alive():
            def _close_quietly(stream):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
            _th.Thread(target=_close_quietly, args=(proc.stdout,),
                       daemon=True).start()
            reader.join(timeout=2)
        else:
            try:
                proc.stdout.close()
            except (OSError, ValueError):
                pass
        proc.wait()
        output = bytes(kept).decode("utf-8", "replace")
        truncated = (state["total"] > output_limit
                     or state["total"] > self.MAX_CAPTURE_BYTES)
        result: dict[str, Any] = {
            "returncode": proc.returncode,
            "output": output[:output_limit],
            "output_bytes_total": state["total"],
            "output_truncated": truncated}
        rem = max(0.0, deadline - time.monotonic())
        if stopped_by == "external":
            term = self.terminate_workload(
                handle, timeout_s=rem if rem > 0 else 1.0,
                step_share_deadline=deadline)
            result.update({"returncode": 124, "timed_out": True,
                           "stopped_by": "external", "termination": term})
        elif stopped_by == "timeout":
            term = self.terminate_workload(
                handle, timeout_s=1.0, step_share_deadline=deadline)
            result.update({"returncode": 124, "timed_out": True,
                           "termination": term})
        return result

    def open_interactive(self, handle: ContainerHandle, command: str,
                         timeout_s: float):
        """Start one long-lived docker exec -i worker; caller owns closure."""
        self._require_authorized()
        if timeout_s <= 0:
            raise RuntimeError_("interactive pipe budget exhausted")
        argv = [self.executable, "exec", "-i", "-w", handle.spec.cwd,
                handle.container_id, "bash", "-lc", command]
        try:
            return subprocess.Popen(argv, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
        except OSError as exc:
            raise RuntimeError_(f"interactive pipe unavailable:{type(exc).__name__}") from None

    def cleanup_pending(self, timeout_s: float = 10.0) -> list[dict]:
        """Consume and clean up pending names (create response lost).
        Identity-checked: only names from THIS runtime's naming scheme
        are touched. Each step CHECKS its return code:
        - listing fails (rc!=0/timeout/OSError) → removed=False (error)
        - rm fails (rc!=0/timeout/OSError) → removed=False (error)
        - rm "succeeds" → VERIFY by re-listing (a daemon bug that
          ignores rm must not misreport removed=True)
        - not found in listing → removed=True (nothing to clean)
        The timeout is a SHARED float budget, no per-step fresh 10s."""
        import subprocess as _sp
        import time as _time
        self._require_authorized()
        deadline = _time.monotonic() + timeout_s
        results = []
        for name in list(self.pending_names):
            def _rem(to):
                return max(0.0, deadline - _time.monotonic())

            # step 1: list (identity check)
            ls_to = _rem(timeout_s)
            if ls_to <= 0:
                results.append({"name": name, "removed": False,
                                "error": "budget_exhausted"})
                continue
            try:
                listing = _sp.run(
                    [self.executable, "ps", "-a", "--filter",
                     f"name=^{name}$", "--format", "{{.ID}} {{.Names}}"],
                    capture_output=True, text=True, timeout=ls_to)
            except (OSError, _sp.TimeoutExpired):
                results.append({"name": name, "removed": False,
                                "error": "listing_failed"})
                continue
            if listing.returncode != 0:
                results.append({"name": name, "removed": False,
                                "error": "listing_rc_nonzero"})
                continue

            found = None
            for line in listing.stdout.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1] == name:
                    found = parts[0]
                    break
            if found is None:
                results.append({"name": name, "removed": True,
                                "note": "not_found_on_daemon"})
                self.pending_names.pop(name, None)
                continue

            # step 2: rm (identity-confirmed by the listing)
            rm_to = _rem(timeout_s)
            if rm_to <= 0:
                results.append({"name": name, "removed": False,
                                "error": "budget_exhausted_before_rm"})
                continue
            try:
                rm = _sp.run(
                    [self.executable, "rm", "-f", found],
                    capture_output=True, text=True, timeout=rm_to)
            except (OSError, _sp.TimeoutExpired):
                results.append({"name": name, "removed": False,
                                "error": "rm_failed"})
                continue
            if rm.returncode != 0:
                results.append({"name": name, "removed": False,
                                "error": f"rm_rc_{rm.returncode}"})
                continue

            # step 3: VERIFY (a "successful" rm must be confirmed)
            verify_to = _rem(timeout_s)
            if verify_to <= 0:
                results.append({"name": name, "removed": False,
                                "error": "budget_exhausted_before_verify"})
                continue
            try:
                verify = _sp.run(
                    [self.executable, "ps", "-a", "--filter",
                     f"id={found}", "--format", "{{.ID}}"],
                    capture_output=True, text=True, timeout=verify_to)
            except (OSError, _sp.TimeoutExpired):
                results.append({"name": name, "removed": False,
                                "error": "verify_listing_failed"})
                continue
            if verify.returncode != 0:
                results.append({"name": name, "removed": False,
                                "error": "verify_rc_nonzero"})
                continue
            if verify.stdout.strip():
                results.append({"name": name, "removed": False,
                                "error": "still_exists_after_rm"})
                continue
            results.append({"name": name, "removed": True,
                            "container_id": found})
            self.pending_names.pop(name, None)
        return results

    def _resolve_cgroup(self, handle: ContainerHandle,
                        timeout_s: float = 30.0) -> None:
        """Locate the container's cgroup dirs on the host (read-only
        probe). The timeout SHARES the caller's budget — passed as a
        FLOAT remaining amount, no rounding."""
        from pathlib import Path as _P
        try:
            proc = subprocess.run(
                [self.executable, "inspect", handle.container_id,
                 "--format", "{{.Id}}"],
                capture_output=True, text=True,
                timeout=timeout_s)
            full_id = proc.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            full_id = handle.container_id
        cg = _P("/sys/fs/cgroup")
        v1 = (cg / "cpu,cpuacct" / "docker" / full_id).is_dir()
        if v1:
            handle.cgroup_dir = cg / "cpu,cpuacct" / "docker" / full_id
            handle.cgroup_version = "v1"
            return
        for candidate in (cg / "system.slice" / f"docker-{full_id}.scope",
                          cg / "docker" / full_id):
            if candidate.is_dir():
                handle.cgroup_dir = candidate
                handle.cgroup_version = "v2"
                return
        handle.cgroup_version = "unresolved"

    # ERE alternation: matches eval/test execution and agent tool
    # commands. bash -c covers mini's interpreter; /eval.sh the
    # verifier; python/pytest common test runners.
    WORKLOAD_PATTERN = "bash -c|/eval.sh|pytest|python"

    def terminate_workload(self, handle: ContainerHandle,
                           timeout_s: float = 15.0,
                           step_share_deadline: float | None = None
                           ) -> dict:
        """Stop in-container work; never reports success unconfirmed.

        ``step_share_deadline``: when provided, every internal step
        (pkill / process check / docker stop) derives its timeout from
        the REMAINING time to that absolute deadline — steps SHARE the
        budget and decrement it (as a FLOAT, no rounding). Without it,
        timeout_s is the per-step cap (legacy callers)."""
        import subprocess as _sp
        import time as _time
        self._require_authorized()

        def _step_timeout() -> float:
            if step_share_deadline is not None:
                rem = step_share_deadline - _time.monotonic()
                return rem if rem > 0 else 0.0
            return float(timeout_s)

        def _exec(script: str):
            to = _step_timeout()
            if to <= 0:
                class _Expired:
                    returncode = -999
                    stdout = ""
                return _Expired()
            return _sp.run(
                [self.executable, "exec", handle.container_id,
                 "sh", "-c", script],
                capture_output=True, text=True, timeout=to)

        # best-effort name-pattern kill (fast path only; NOT the proof)
        try:
            _exec(f"pkill -9 -f \'{self.WORKLOAD_PATTERN}\'")
        except (_sp.TimeoutExpired, OSError):
            pass
        # PROOF: process-tree check. rc==0 (explicitly idle) confirms.
        # Uses ${PROC_ROOT:-/proc} so tests can redirect to a fixture.
        try:
            check = _exec(
                "P=${PROC_ROOT:-/proc}; busy=0; "
                "for d in $P/[0-9]*; do "
                "pid=${d##*/}; "
                "[ \"$pid\" = 1 ] && continue; "
                "[ \"$pid\" = $$ ] && continue; "
                "[ -r \"$d/stat\" ] || exit 2; "
                "read -r line < \"$d/stat\" || exit 2; "
                "rest=${line##*)}; set -- $rest; "
                "[ \"$1\" = Z ] && continue; "
                "[ \"$2\" = $$ ] && continue; "
                "busy=1; break; done; exit $busy")
            if check.returncode == 0:
                # rc=0: the check found no busy process — the tree is
                # idle and the stop is CONFIRMED
                return {"confirmed": True,
                        "method": "pkill+process_tree_check",
                        "container_alive": True}
            # rc=1: busy (still running) — fall through to docker stop
            # rc=2: check error — fall through to docker stop
        except (_sp.TimeoutExpired, OSError):
            pass
        # fallback: docker stop (also shares the deadline)
        stop_to = _step_timeout()
        if stop_to <= 0:
            return {"confirmed": False,
                    "method": "budget_exhausted_before_stop",
                    "container_alive": None,
                    "error": "step_share_deadline_expired"}
        try:
            proc = _sp.run([self.executable, "stop", "-t", "0",
                            handle.container_id],
                           capture_output=True, text=True,
                           timeout=stop_to)
            return {"confirmed": proc.returncode == 0,
                    "method": "docker_stop",
                    "container_alive": False,
                    "rc": proc.returncode}
        except (_sp.TimeoutExpired, OSError) as exc:
            return {"confirmed": False, "method": "docker_stop_failed",
                    "container_alive": None,
                    "error": type(exc).__name__}

    def read_counters(self, handle: ContainerHandle,
                      t_monotonic_ns: int) -> CounterSnapshot:
        """Read cgroup counters from the container's resolved cgroup dir."""
        from ..collectors.resource_sampler import CgroupV1FileReader, \
            CgroupV2FileReader
        self._require_authorized()
        version = getattr(handle, "cgroup_version", None)
        if version is None:
            self._resolve_cgroup(handle)
            version = getattr(handle, "cgroup_version", None)
        if version == "v1":
            return CgroupV1FileReader(handle.spec.scope,
                                      "agent_container",
                                      handle.container_id).read(t_monotonic_ns)
        if handle.cgroup_dir is not None:
            return CgroupV2FileReader(handle.spec.scope,
                                      "agent_container",
                                      handle.cgroup_dir).read(t_monotonic_ns)
        return CounterSnapshot(
            scope=handle.spec.scope, scope_kind="agent_container",
            t_monotonic_ns=t_monotonic_ns,
            read_status={"cgroup": "not_resolved"})

    def stop(self, handle: ContainerHandle,
             timeout_s: float = 60.0) -> None:
        self._require_authorized()
        if timeout_s <= 0:
            raise RuntimeError_("container stop budget exhausted")
        subprocess.run([self.executable, "rm", "-f", handle.container_id],
                       capture_output=True, text=True,
                       timeout=timeout_s)

    def verify_removal(self, handle: ContainerHandle,
                       timeout_s: float = 30.0) -> str:
        """Three-way: 'removed' / 'still_exists' / 'check_failed'.

        A daemon error (non-zero rc, timeout, OSError) is
        'check_failed' — NEVER silently mapped to 'removed'. A stopped
        but present container is 'still_exists' (removal not yet done
        is not removal verified)."""
        self._require_authorized()
        if timeout_s <= 0:
            return "check_failed"
        try:
            r = subprocess.run(
                [self.executable, "ps", "-a", "--filter",
                 f"id={handle.container_id}", "--format", "{{.ID}}"],
                capture_output=True, text=True,
                timeout=timeout_s)
        except (OSError, subprocess.TimeoutExpired):
            return "check_failed"
        if r.returncode != 0:
            return "check_failed"
        # empty output = container not in the list = removed
        if not r.stdout.strip():
            return "removed"
        return "still_exists"

    def container_init_pid(self, handle: ContainerHandle,
                           timeout_s: float = 10.0) -> int | None:
        """docker inspect State.Pid (host-side init PID). Read-only."""
        self._require_authorized()
        if timeout_s <= 0:
            return None
        try:
            r = subprocess.run(
                [self.executable, "inspect", "-f", "{{.State.Pid}}",
                 handle.container_id],
                capture_output=True, text=True, timeout=timeout_s)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode != 0:
            return None
        try:
            return int(r.stdout.strip())
        except ValueError:
            return None

    def cleanup_run(self, run_id: str, timeout_s: float = 60.0) -> CleanupResult:
        """Remove owned containers and explicitly confirm each removal."""
        self._require_authorized()
        deadline = time.monotonic() + max(0.0, timeout_s)
        remaining = lambda: max(0.0, deadline - time.monotonic())
        if remaining() <= 0:
            return CleanupResult(status="not_checked",
                                 errors=["cleanup_budget_exhausted"])
        try:
            listing = subprocess.run(
                [self.executable, "ps", "-a", "--filter",
                 f"name={self._name_prefix}-{run_id}-",
                 "--format", "{{.ID}} {{.Names}}"],
                capture_output=True, text=True, timeout=remaining())
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CleanupResult(status="check_failed",
                                 errors=[f"list:{type(exc).__name__}"])
        if listing.returncode != 0:
            return CleanupResult(status="check_failed",
                                 errors=[f"list:returncode={listing.returncode}"])
        removed = []
        errors = []
        unconfirmed = []
        for line in listing.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].startswith(
                    f"{self._name_prefix}-{run_id}-"):
                if remaining() <= 0:
                    unconfirmed.append(parts[1])
                    break
                try:
                    deletion = subprocess.run(
                        [self.executable, "rm", "-f", parts[0]],
                        capture_output=True, text=True, timeout=remaining())
                except (OSError, subprocess.TimeoutExpired) as exc:
                    errors.append(f"{parts[1]}:delete:{type(exc).__name__}")
                    unconfirmed.append(parts[1])
                    continue
                if deletion.returncode != 0:
                    errors.append(f"{parts[1]}:delete:returncode={deletion.returncode}")
                    unconfirmed.append(parts[1])
                    continue
                if remaining() <= 0:
                    unconfirmed.append(parts[1])
                    continue
                check = self.verify_removal(
                    ContainerHandle(parts[0], ContainerSpec(run_id, "cleanup",
                                                            "unknown")),
                    timeout_s=remaining())
                if check == "removed":
                    removed.append(parts[1])
                else:
                    errors.append(f"{parts[1]}:verify:{check}")
                    unconfirmed.append(parts[1])
        status = "confirmed" if not errors and not unconfirmed else (
            "not_checked" if unconfirmed and remaining() <= 0 else "failed")
        return CleanupResult(removed, status=status, errors=errors,
                             unconfirmed=unconfirmed)

    def describe_argv(self, argv: list[str]) -> str:
        """Human-readable command for approval lists (shlex-quoted)."""
        return shlex.join(argv)
