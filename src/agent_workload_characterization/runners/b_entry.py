"""G1-01-B0: no-model container validation entry (offline assembly).

Default (no flags): SIDE-EFFECT-FREE PLAN — prints the complete batch
plan (both container cases, budget, guards, identities) without calling
Docker, the network, or anything else with side effects.

--execute --i-approve-the-b-validation (BOTH required): the real B1
batch via ``execute_batch``. The flags are a SOFTWARE GATE ONLY; the
authorization act is the user's explicit approval of the final
checklist, recorded in an approval file whose CONTENT must bind the
registered checklist identity (image, budget and code SHAs) — an empty
or mismatched file is refused, not just a missing one.

B1 scope (task brief §§4–7): at most 2 SEQUENTIAL containers (the first
is fully stopped and cleaned before the second starts) from the fixed
arm64 digest, no model, no Agent loop, no task/gold/candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]

IMAGE = ("swebench/sweb.eval.arm64.django_1776_django-16485"
         "@sha256:19d403c243c2857e7cb9cf5af8ce3f1cb6d87be91c5254e1de"
         "00040e6db3b7d2")

APPROVAL_RECORD = PROJECT_ROOT / "reports/resource/G1-01-B/APPROVAL.txt"

BUDGET = {
    "batch_wall_s": 180.0,
    "cleanup_reserve_s": 30.0,
    "max_containers": 2,
    "per_container": {"cpu": "2", "mem": "256m", "network": "none"},
    "per_command_timeout_s": 20,
    "terminate_timeout_s": 15,
    "background_busy_max_s": 5,
    "synthetic_file": "/tmp/g1b.bin",
    "synthetic_write_mib": 8,
    "synthetic_write_total_mib": 16,
    "host_child": {"max": 1, "lifetime_s": 5,
                   "note": "own deterministic short program; no busy "
                           "loop, no data files; not an Agent"},
    "report_threshold_mib": 20,
    "sampling_interval_s": 0.2,
}

CONTAINER_1_COMMANDS = [
    ("b1-sleep-1", "sleep 1"),
    ("b1-dd-8mib", "dd if=/dev/urandom of=/tmp/g1b.bin bs=1M count=8 "
                   "&& sync && rm -f /tmp/g1b.bin"),
    ("b1-fail", "false"),
    ("b1-cpu", 'python3 -c "x=sum(range(2_000_000))"'),
]

CONTAINER_2_BACKGROUND = {
    "registered_script": (
        "setsid sh -c 'while :; do :; done' "
        "< /dev/null > /dev/null 2>&1 & "
        "echo BG_PID=$!"),
    "semantics": (
        "setsid detaches the session (no controlling terminal); stdin/"
        "stdout/stderr are redirected to /dev/null BEFORE backgrounding "
        "so the exec pipe closes and the call returns immediately; the "
        "background PID is echoed and recorded as the workload identity"),
    "window_s": 5.0,
}

HOST_CHILD_CODE = "import time; time.sleep(2)"


class B0Error(RuntimeError):
    """Plan/guard/execution failure (reported without secrets)."""


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _checklist_identity() -> dict:
    """The identity an approval record must bind: image, budget, and
    the code SHAs of the execution path. The code SHAs are read from
    the REAL project root (the running code's location), independent
    of any PROJECT_ROOT patching for report directories."""
    _real_root = Path(__file__).resolve().parents[3]
    def _sha(rel: str) -> str:
        p = _real_root / rel
        return _sha_file(p) if p.is_file() else "MISSING"
    import copy
    return {
        "image": IMAGE,
        "budget": copy.deepcopy(BUDGET),
        "code_sha256": {
            "runners/b_entry.py": _sha(
                "src/agent_workload_characterization/runners/b_entry.py"),
            "runners/tool_event_env.py": _sha(
                "src/agent_workload_characterization/runners/"
                "tool_event_env.py"),
            "runners/container_runtime.py": _sha(
                "src/agent_workload_characterization/runners/"
                "container_runtime.py"),
            "runners/mini_agent_adapter.py": _sha(
                "src/agent_workload_characterization/runners/"
                "mini_agent_adapter.py"),
            "collectors/resource_sampler.py": _sha(
                "src/agent_workload_characterization/collectors/"
                "resource_sampler.py"),
            "collectors/host_process.py": _sha(
                "src/agent_workload_characterization/collectors/"
                "host_process.py"),
        },
    }


def _verify_approval(approval_path: Path,
                     identity: dict | None = None) -> dict:
    """Authorization check: the record file must EXIST and its CONTENT
    must bind the registered checklist identity (image + budget + code
    SHAs). An empty file, a file missing the identity block, or one
    whose embedded identity no longer matches (drift) is refused."""
    identity = identity or _checklist_identity()
    if not approval_path.is_file():
        raise B0Error("no approval record found — authorization is the "
                      "user's recorded approval of the B1 checklist")
    try:
        record = json.loads(approval_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise B0Error(f"approval record unreadable "
                      f"({type(exc).__name__}) — refusing") from None
    if not isinstance(record, dict) \
            or "checklist_identity" not in record:
        raise B0Error("approval record does not carry a "
                      "checklist_identity block — refusing (an empty or "
                      "non-conforming file is not authorization)")
    for key in ("image", "budget", "code_sha256"):
        expected = identity.get(key)
        actual = record["checklist_identity"].get(key)
        if expected != actual:
            raise B0Error(
                f"approval record identity drift in {key!r} — the "
                "registered checklist/code changed since approval; "
                "re-approval required")
    return record


def _guard_report_root(root: Path) -> Path:
    """Guard the REPORT ROOT: check the ORIGINAL path segments for
    symlinks FIRST (resolving before the check would follow the symlink
    and lose the escape), then verify the resolved path is inside the
    project, does not overlap protected trees, and IS the expected
    fixed location (an in-project redirect is refused too)."""
    project = PROJECT_ROOT.resolve()
    # 1) ORIGINAL path: every segment must be a real directory, never
    #    a symlink (checked BEFORE any resolve())
    raw = root if root.is_absolute() else PROJECT_ROOT / root
    try:
        rel = raw.relative_to(project)
    except ValueError:
        raise B0Error(f"report root not under the project: {raw}") \
            from None
    cur = project
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise B0Error(f"symlink in report root path: {cur}")
        if cur.exists() and not cur.is_dir():
            raise B0Error(f"report root path is not a directory: {cur}")
    # 2) RESOLVED path must be the EXPECTED fixed location
    resolved = raw.resolve()
    expected = (project / "reports" / "resource" / "G1-01-B").resolve()
    if resolved != expected:
        raise B0Error(
            f"report root resolves to {resolved} but the B report root "
            f"is fixed at {expected} — redirects are refused")
    # 3) protected trees
    for protected in (project / "references",
                      project / "data/raw/public",
                      project / "data/raw/generated",
                      project / "data/catalog"):
        p = protected.resolve()
        if resolved == p or resolved.is_relative_to(p) \
                or p.is_relative_to(resolved):
            raise B0Error(f"report root overlaps protected path: {p}")
    try:
        from .report_writer import _catalog_protected_roots
        for legacy in _catalog_protected_roots(project):
            if resolved == legacy or resolved.is_relative_to(legacy) \
                    or legacy.is_relative_to(resolved):
                raise B0Error(f"report root overlaps legacy source "
                              f"root: {legacy}")
    except ImportError:
        pass
    return raw

def _guard_report_dir(batch_id: str) -> Path:
    """Batch-level guard (on top of the root guard): valid id, no
    traversal/symlink, exclusive create."""
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", batch_id):
        raise B0Error(f"invalid batch id: {batch_id!r}")
    root = _guard_report_root(PROJECT_ROOT / "reports/resource/G1-01-B")
    candidate = root / batch_id
    cur = root
    for part in Path(batch_id).parts:
        cur = cur / part
        if cur.is_symlink():
            raise B0Error(f"symlink in batch path: {cur}")
    if candidate.resolve() != (root / batch_id).resolve():
        raise B0Error("batch path escapes the report root")
    if candidate.exists():
        raise B0Error("batch directory already exists; reports are "
                      "never overwritten")
    return candidate


# ---------------------------------------------------------------------------
# B1 execution
# ---------------------------------------------------------------------------

def execute_batch(*, runtime, clock=None, report_root: Path | None = None,
                  batch_id: str | None = None,
                  approval_record: Path | None = None,
                  approval_identity: dict | None = None,
                  _batch_deadline: float | None = None,
                  reader_factory=None) -> dict:
    """The full B1 batch orchestration (production code path; tests
    inject a FakeContainerRuntime and a synthetic approval record).

    Sequencing: container 1 is fully STOPPED and CLEANED (with verified
    removal) before container 2 starts — at most one live container at
    any time. Handles are registered for cleanup IMMEDIATELY after
    creation (inside the case functions, via the lifecycle registry)
    so an exception cannot orphan them. A FAIL in case 1 stops the
    batch (case 2 is SKIPPED with the reason)."""
    identity = approval_identity or _checklist_identity()
    approval_path = approval_record if approval_record is not None \
        else APPROVAL_RECORD
    _verify_approval(approval_path, identity)

    t0 = time.monotonic()
    deadline = _batch_deadline if _batch_deadline is not None \
        else t0 + BUDGET["batch_wall_s"]

    def remaining() -> float:
        return deadline - time.monotonic()

    def cap_wait(requested: float) -> float:
        """Cap any fixed wait at the remaining batch budget."""
        return max(0.0, min(requested, remaining()))

    def cap_timeout(requested: float) -> float:
        """Cap a blocking-op timeout at the remaining budget. Returns
        a FLOAT (no int rounding that inflates 0.2s to 1s). An expired
        budget gives 0.0 — the caller refuses, no free seconds."""
        rem = remaining()
        if rem <= 0:
            return 0.0
        return min(requested, rem)

    def enough_for_next_case() -> bool:
        return remaining() > BUDGET["cleanup_reserve_s"]

    batch = batch_id or (
        f"G1-01-B-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        f"-{uuid.uuid4().hex[:6]}")
    if report_root is None:
        out_dir = _guard_report_dir(batch)
        out_dir.mkdir(parents=True)
    else:
        out_dir = report_root / batch
        out_dir.mkdir(parents=True, exist_ok=True)

    run_id = batch
    cases: list[dict] = []
    stopped_scopes: list[str] = []

    from ..collectors.resource_sampler import ResourceSampler
    from ..runners.tool_event_env import wrap_environment
    from ..collectors.host_process import (HostProcessMonitor,
                                           read_starttime)

    sampler = ResourceSampler(clock=clock,
                              interval_s=BUDGET["sampling_interval_s"])
    runner_starttime = read_starttime(os.getpid())
    runner_mon = HostProcessMonitor(os.getpid(),
                                    expected_starttime=runner_starttime)

    # in-flight report threshold: checked between cases AND inside the
    # case functions (via the stop_batch callback); exceeding it stops
    # the batch with a FAIL status and the evidence is archived
    report_state = {"exceeded": False, "bytes": 0}

    def _check_report_threshold() -> bool:
        try:
            total = sum(f.stat().st_size
                        for f in out_dir.rglob("*") if f.is_file())
        except OSError:
            total = report_state["bytes"]
        report_state["bytes"] = total
        if total > BUDGET["report_threshold_mib"] * 2**20:
            report_state["exceeded"] = True
        return report_state["exceeded"]

    def stop_batch(reason: str) -> None:
        """Raise the batch-stopping exception (caught by the batch's
        broad handler; evidence + cleanup still run)."""
        raise B0Error(reason)

    def report_threshold_stop() -> bool:
        """should_stop callback for BLOCKING case executions: checks
        the report threshold and interrupts the execute when tripped."""
        return _check_report_threshold()

    # lifecycle registry: handles registered AT CREATION, cleaned in
    # finally; removal VERIFIED (a stop() call alone is not "removed")
    live_handles: list = []

    def register_handle(h) -> None:
        live_handles.append(h)

    def verified_cleanup() -> list:
        """Stop + verify each handle via the runtime's three-way
        verify_removal interface. Every blocking operation (stop,
        verify) is capped at the REMAINING batch budget. A
        'check_failed' or 'still_exists' result keeps the handle in
        the pending list and is reflected in batch_status."""
        results = []
        for h in list(live_handles):
            rem = remaining()
            overrun = rem <= 0
            # cleanup is MANDATORY (task brief §7): a 0.1-second floor
            # keeps the stop callable, but the OVERRUN is recorded.
            # Float timeouts — no int(max(1,...)) rounding.
            stop_to = min(60.0, max(0.1, rem))
            try:
                runtime.stop(h, timeout_s=stop_to)
            except TypeError:
                try:
                    runtime.stop(h)
                except Exception as exc:  # noqa: BLE001
                    results.append({"container_id": h.container_id,
                                    "removed": False,
                                    "error": type(exc).__name__,
                                    "budget_overrun": overrun})
                    continue
            except Exception as exc:  # noqa: BLE001
                results.append({"container_id": h.container_id,
                                "removed": False,
                                "error": type(exc).__name__,
                                "budget_overrun": overrun})
                continue
            verify_rem = remaining()
            verify_to = min(30.0, max(0.1, verify_rem))
            verify_overrun = verify_rem <= 0
            try:
                verdict = runtime.verify_removal(
                    h, timeout_s=verify_to)
            except TypeError:
                try:
                    verdict = runtime.verify_removal(h)
                except Exception:  # noqa: BLE001
                    verdict = "check_failed"
            except Exception:  # noqa: BLE001
                verdict = "check_failed"
            if verdict == "removed":
                results.append({"container_id": h.container_id,
                                "removed": True,
                                "budget_overrun": overrun
                                or verify_overrun})
                live_handles.remove(h)
            else:
                results.append({"container_id": h.container_id,
                                "removed": False,
                                "verdict": verdict,
                                "budget_overrun": overrun
                                or verify_overrun})
        return results

    # ====================== UNIFIED FINAL STATUS ======================
    # Computed from ALL sources in ONE place; used by the return value,
    # batch.json, manifest.json, and the CLI exit code (B0-C).
    archive_status = "not_reached"
    archive_error = None
    cleanup_results: list = []
    cleanup_error = None
    final_evidence = {}

    def _compute_final_status(case_list, cleanup, arch_status, arch_err,
                              cleanup_err, budget_overrun_any,
                              all_skipped, evidence):
        """ONE authoritative status computation.

        FAIL sources: any case FAIL, unconfirmed removals, archive
        failure, budget overrun during cleanup, missing required
        evidence. ALL-SKIPPED is NOT OK (it means nothing was
        validated). Returns (status, reasons)."""
        reasons = []
        fails = [c for c in case_list if c.get("status") == "FAIL"]
        if fails:
            reasons.append({"source": "case_failures",
                            "detail": [c.get("reason") for c in fails]})
        unconf = [e for e in cleanup if not e.get("removed", True)]
        if unconf:
            reasons.append({"source": "unconfirmed_removals",
                            "detail": [e.get("container_id")
                                       for e in unconf]})
        if arch_status != "ok":
            reasons.append({"source": "archive",
                            "detail": arch_status})
        if cleanup_err:
            reasons.append({"source": "cleanup",
                            "detail": cleanup_err})
        if budget_overrun_any:
            reasons.append({"source": "budget_overrun",
                            "detail": "cleanup exceeded batch deadline"})
        if all_skipped and not fails:
            reasons.append({"source": "all_skipped",
                            "detail": "no case executed — nothing "
                            "validated, cannot report OK"})
        for key, check in evidence.items():
            if check is False:
                reasons.append({"source": "evidence_missing",
                                "detail": key})
        return ("FAIL" if reasons else "OK"), reasons

    try:
        if _check_report_threshold():
            cases.append({"case": 1, "status": "FAIL",
                          "reason": "report threshold exceeded"})
        elif not enough_for_next_case():
            cases.append({"case": 1, "status": "SKIPPED",
                          "reason": "insufficient remaining budget"})
        else:
            case1 = _run_container_1(runtime, sampler, run_id, out_dir,
                                     wrap_environment, remaining,
                                     cap_wait, register_handle,
                                     reader_factory=reader_factory,
                                     stop_callback=report_threshold_stop,
                                     cap_timeout=cap_timeout)
            cases.append(case1)
        # SEQUENTIAL: case 1's container is fully stopped and its
        # removal VERIFIED before case 2 starts
        c1_status = next((c["status"] for c in cases
                          if c.get("case") == 1), None)
        if c1_status is not None:
            c1_cleanup = verified_cleanup()
            for c in cases:
                if c.get("case") == 1:
                    c["container_cleanup"] = c1_cleanup
                    for entry in c1_cleanup:
                        if not entry.get("removed", False):
                            c["status"] = "FAIL"
                            c["reason"] = ("container 1 removal not "
                                           "verified before case 2")
        if c1_status == "FAIL" or any(
                c.get("case") == 1 and c.get("status") == "FAIL"
                for c in cases):
            cases.append({"case": 2, "status": "SKIPPED",
                          "reason": "case 1 failed — batch stopped"})
        elif _check_report_threshold():
            cases.append({"case": 2, "status": "FAIL",
                          "reason": "report threshold exceeded"})
        elif not enough_for_next_case():
            cases.append({"case": 2, "status": "SKIPPED",
                          "reason": "insufficient remaining budget"})
        else:
            case2 = _run_container_2(runtime, sampler, run_id, out_dir,
                                     wrap_environment, remaining,
                                     cap_wait, register_handle,
                                     stopped_scopes, runner_mon,
                                     reader_factory=reader_factory,
                                     stop_callback=report_threshold_stop,
                                     cap_timeout=cap_timeout)
            cases.append(case2)
    except B0Error as exc:
        cases.append({"case": "abort", "status": "FAIL",
                      "reason": str(exc)})
    except Exception as exc:  # noqa: BLE001 — infrastructure failure:
        cases.append({"case": "abort", "status": "FAIL",
                      "reason": f"infrastructure failure: "
                              f"{type(exc).__name__}"})

    # ==================== CLEANUP (independent, B0-B) ====================
    # Cleanup runs REGARDLESS of archive/monitor/serialization failures.
    # It is never inside a try that could skip it.
    try:
        runner_mon.poll_once()
    except Exception:  # noqa: BLE001 — monitoring failure never blocks cleanup
        pass
    try:
        cleanup_results = verified_cleanup()
    except Exception as exc:  # noqa: BLE001 — cleanup itself failed
        cleanup_error = f"error:{type(exc).__name__}"
    # B0-B: consume any pending (create-response-lost) names; this is
    # the path that makes the pre-registered identity ACTUALLY reach
    # the cleanup, not just be stored
    try:
        if hasattr(runtime, "cleanup_pending"):
            # cleanup_pending gets the REMAINING batch budget (not a
            # fresh default 10s). If the budget is exhausted, a small
            # mandatory floor keeps the cleanup callable but the OVERRUN
            # is recorded and makes the batch FAIL.
            pending_rem = remaining()
            pending_overrun = pending_rem <= 0
            pending_budget = min(10.0, max(0.1, pending_rem)) if pending_rem > 0 else 0.1
            pending_results = runtime.cleanup_pending(timeout_s=pending_budget)
            if pending_overrun:
                for pr in pending_results:
                    pr["budget_overrun"] = True
            cleanup_results.extend(pending_results)
            # any unremoved pending name is an unconfirmed residue
            for pr in pending_results:
                if not pr.get("removed", True):
                    cleanup_error = (cleanup_error or "") + \
                        f";pending_name_unremoved:{pr.get('name')}"
    except Exception as exc:  # noqa: BLE001 — pending cleanup failed
        cleanup_error = (cleanup_error or "") + \
            f";pending_cleanup_error:{type(exc).__name__}"
    budget_overrun_any = any(e.get("budget_overrun")
                             for e in cleanup_results)

    # ==================== ARCHIVE (B0-E: full identity) ====================
    try:
        host_summary = runner_mon.summary()
    except Exception:  # noqa: BLE001 — summary failure is degraded, not fatal
        host_summary = {"scope": "host_runner_process",
                        "summary_error": "monitor_summary_failed"}
    host_summary["scope"] = "host_runner_process"

    # B0-D: evidence quality checks — PROVE collection happened
    final_evidence = _check_evidence_quality(cases, sampler,
                                              stopped_scopes)

    all_skipped = (all(c.get("status") == "SKIPPED" for c in cases)
                   and cases)
    batch_status, batch_reasons = _compute_final_status(
        cases, cleanup_results, "pending", None, cleanup_error,
        budget_overrun_any, all_skipped, final_evidence)

    batch_doc = {
        "batch": batch,
        "executed_at_utc":
            datetime.now(timezone.utc).isoformat(),
        "wall_s": round(time.monotonic() - t0, 2),
        "budget": BUDGET,
        "budget_deadline": _batch_deadline,
        "cases": cases,
        "host_runner_process": host_summary,
        "host_runner_raw_snapshots": [
            {"t_monotonic_ns": sn.t_monotonic_ns,
             "cpu_ticks": sn.cpu_ticks,
             "rss_bytes": sn.rss_bytes,
             "stat": sn.read_status.get("stat")}
            for sn in runner_mon.snapshots],
        "stopped_scopes": stopped_scopes,
        "evidence_quality": final_evidence,
        "batch_status": batch_status,
        "batch_fail_reasons": batch_reasons,
        "image": IMAGE,
        "no_model": True,
        "no_agent_loop": True,
    }
    try:
        (out_dir / "batch.json").write_text(
            json.dumps(batch_doc, ensure_ascii=False, indent=2)
            + "\n", encoding="utf-8")
        archive_status = "ok"
    except OSError as exc:
        archive_status = f"archive_failed:{type(exc).__name__}"
        archive_error = type(exc).__name__

    # recompute with the actual archive status
    batch_status, batch_reasons = _compute_final_status(
        cases, cleanup_results, archive_status, archive_error,
        cleanup_error, budget_overrun_any, all_skipped, final_evidence)
    batch_doc["batch_status"] = batch_status
    batch_doc["batch_fail_reasons"] = batch_reasons
    batch_doc["archive_status"] = archive_status

    # rewrite batch.json with the final status (archive error recorded)
    try:
        (out_dir / "batch.json").write_text(
            json.dumps(batch_doc, ensure_ascii=False, indent=2)
            + "\n", encoding="utf-8")
    except OSError:
        pass  # already recorded

    # B0-E: manifest with identity, budget, timeline, output accounting
    files = {}
    for p in sorted(out_dir.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            files[str(p.relative_to(out_dir))] = _sha_file(p)
    output_bytes = sum(
        (out_dir / n).stat().st_size for n in files)
    manifest = {
        "batch": batch,
        "generated_at_utc":
            datetime.now(timezone.utc).isoformat(),
        "files": files,
        "output_bytes": output_bytes,
        "archive_status": archive_status,
        "cleanup": cleanup_results,
        "batch_status": batch_status,
        "batch_fail_reasons": batch_reasons,
        "identity": {
            "image": IMAGE,
            "budget": BUDGET,
            "code_sha256": identity.get("code_sha256"),
            "approval_record_sha256": (
                _sha_file(approval_path)),
            "wall_s": batch_doc["wall_s"],
            "budget_deadline": _batch_deadline,
            "batch_started_utc": batch_doc["executed_at_utc"],
            "cleanup_overrun": budget_overrun_any,
            "report_threshold_exceeded": report_state["exceeded"],
        },
        "claim": ("G1-01-B no-model container validation; "
                  "unified final status; append-only"),
    }
    manifest_status = "ok"
    try:
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        written = json.loads((out_dir / "manifest.json")
                             .read_text(encoding="utf-8"))
        mismatched = [n for n, sha in written.get("files", {}).items()
                      if _sha_file(out_dir / n) != sha]
        if mismatched:
            manifest_status = ("manifest_verification_failed:"
                               + ",".join(mismatched))
    except OSError as exc:
        manifest_status = f"manifest_write_failed:{type(exc).__name__}"
    except (ValueError, KeyError) as exc:
        manifest_status = f"manifest_readback_failed:{type(exc).__name__}"
    # B0-C: the manifest status feeds the unified final status — a
    # failed manifest write makes the batch FAIL, not silently OK
    if manifest_status != "ok":
        archive_status = manifest_status
    batch_status, batch_reasons = _compute_final_status(
        cases, cleanup_results, archive_status, archive_error,
        cleanup_error, budget_overrun_any, all_skipped, final_evidence)

    return {
        "batch": batch,
        "wall_s": round(time.monotonic() - t0, 2),
        "archive_status": archive_status,
        "cleanup": cleanup_results,
        "batch_status": batch_status,
        "batch_fail_reasons": batch_reasons,
        "evidence_quality": final_evidence,
        "report_state": {"bytes": report_state["bytes"],
                         "exceeded": report_state["exceeded"]},
        "cases": [{"case": c.get("case"), "status": c.get("status"),
                   "reason": c.get("reason"),
                   "container_cleanup": c.get("container_cleanup")}
                  for c in cases],
        "out_dir": str(out_dir),
    }


# module-level reader factory: CgroupV1FileReader in production; the
# CLI tests patch this to inject the fake runtime's synthetic counters
READER_FACTORY = None  # set by tests; None -> CgroupV1FileReader


def _default_reader_factory(scope, scope_kind, container_id):
    from ..collectors.resource_sampler import CgroupV1FileReader
    return CgroupV1FileReader(scope, scope_kind, container_id)


def _run_container_1(runtime, sampler, run_id, out_dir,
                     wrap_environment, remaining, cap_wait,
                     register_handle, reader_factory=None,
                     stop_callback=None, cap_timeout=None) -> dict:
    if cap_timeout is None:
        def cap_timeout(req):
            rem = remaining()
            return 0.0 if rem <= 0 else min(req, rem)
    from ..collectors.resource_sampler import CgroupV1FileReader
    from ..runners.container_runtime import ContainerSpec
    scope = f"{run_id}-c1"
    handle = runtime.start(ContainerSpec(
        run_id=run_id, scope="c1", image=IMAGE, cwd="/",
        cpu_limit=BUDGET["per_container"]["cpu"],
        mem_limit=BUDGET["per_container"]["mem"],
        pull="never"),
        timeout_s=cap_timeout(60))
    register_handle(handle)  # cleanup registration AT CREATION
    case = {"case": 1, "status": "PASS",
            "container_id": handle.container_id}
    env = None
    try:
        if reader_factory is not None:
            sampler.register(scope, "agent_container",
                             reader_factory(scope, "agent_container",
                                            handle.container_id))
        else:
            sampler.register(scope, "agent_container",
                             CgroupV1FileReader(scope, "agent_container",
                                                handle.container_id))
        sampler.start(scope)
        sampler.start_background_sampling()
        events_path = out_dir / "c1_tool_events.jsonl"
        env = wrap_environment(
            _RuntimeExecuteBridge(runtime, handle, stop_callback),
            events_path)
        for tid, cmd in CONTAINER_1_COMMANDS:
            if remaining() <= 0:
                case["status"] = "FAIL"
                case["reason"] = "budget exhausted mid-case"
                return case
            # per-command timeout capped at the remaining budget
            timeout = cap_timeout(BUDGET["per_command_timeout_s"])
            if tid == "b1-sleep-1":
                # open-persistence DURING the call: a reader thread
                # polls the events file while the execute is in flight;
                # the PROOF requires the read timestamp to be BEFORE
                # the call returned (call_end), not merely that an
                # open line exists (reading after the call would be
                # trivially true). The full evidence triple
                # (read_at_ns, call_start_ns, call_end_ns) is
                # persisted in the case result.
                import threading as _th
                open_ev = {}
                call_bounds = {}
                def _open_reader():
                    dl = time.monotonic() + 10
                    while time.monotonic() < dl:
                        try:
                            lines = [l for l in
                                     events_path.read_text()
                                     .splitlines() if l.strip()]
                        except OSError:
                            lines = []
                        for l in lines:
                            try:
                                e = json.loads(l)
                            except ValueError:
                                continue
                            if e.get("event") == "open" \
                                    and e.get("tool_call_id") == tid:
                                open_ev["read_at_ns"] = \
                                    time.monotonic_ns()
                                open_ev["event"] = e
                                return
                        time.sleep(0.05)
                call_start = time.monotonic_ns()
                rd = _th.Thread(target=_open_reader, daemon=True)
                rd.start()
                out = env.execute({"command": cmd,
                                   "tool_call_id": tid}, timeout=timeout)
                call_end = time.monotonic_ns()
                rd.join(1)
                call_bounds["call_start_ns"] = call_start
                call_bounds["call_end_ns"] = call_end
                read_ns = open_ev.get("read_at_ns")
                case["open_read_evidence"] = {
                    "read_at_ns": read_ns,
                    "call_start_ns": call_start,
                    "call_end_ns": call_end,
                    "read_before_call_end": (
                        read_ns is not None and read_ns < call_end),
                }
                if not case["open_read_evidence"][
                        "read_before_call_end"]:
                    case["status"] = "FAIL"
                    case["reason"] = ("open event was not read "
                                      "BEFORE the sleep call returned "
                                      f"(read_at_ns={read_ns}, "
                                      f"call_end_ns={call_end})")
                    return case
            else:
                out = env.execute({"command": cmd,
                                   "tool_call_id": tid},
                                  timeout=timeout)
            if tid == "b1-fail":
                # the EXPECTED result is a non-zero rc (the command is
                # literally `false`); rc=0 is a bug; rc=124/timed_out
                # is a TIMEOUT (infrastructure), not the expected result
                if out.get("returncode") == 0:
                    case["status"] = "FAIL"
                    case["reason"] = "false unexpectedly succeeded"
                    return case
                if out.get("timed_out") or \
                        out.get("returncode") == 124:
                    case["status"] = "FAIL"
                    case["reason"] = (f"{tid} timed out (expected a "
                                      "quick non-zero rc, got 124)")
                    return case
                # a genuine non-zero rc: the expected outcome
                case["expected_nonzero_rc"] = out.get("returncode")
            elif out.get("timed_out") or \
                    out.get("returncode") == 124:
                case["status"] = "FAIL"
                case["reason"] = (f"{tid} timed out "
                                  f"(rc={out.get('returncode')})")
                return case
            elif out.get("returncode") != 0:
                case["status"] = "FAIL"
                case["reason"] = f"{tid} rc={out.get('returncode')}"
                return case
            # the sleep window: monotonic evidence, no threshold fix
            if tid == "b1-sleep-1":
                closes = [json.loads(l) for l in
                          events_path.read_text().splitlines()
                          if l.strip() and '"closed"' in l]
                if closes:
                    w = (closes[0]["t_end_ns"]
                         - closes[0]["t_start_ns"]) / 1e9
                    case["sleep_window_s"] = round(w, 3)
                    if w < 1.0:
                        case["status"] = "FAIL"
                        case["reason"] = (f"sleep window {w:.3f}s "
                                          "< 1s requested")
                        return case
        events = [json.loads(l) for l in
                  events_path.read_text().splitlines() if l.strip()]
        opens = [e for e in events if e["event"] == "open"]
        closes = [e for e in events if e["event"] == "closed"]
        if len(opens) != 4 or len(closes) != 4:
            case["status"] = "FAIL"
            case["reason"] = ("expected 4 open/closed pairs, got "
                              f"{len(opens)}/{len(closes)}")
            return case
        # container evidence BEFORE teardown: full raw samples
        sampler.stop(scope)
        sampler.stop_background_sampling()
        ev = sampler.samples(scope).evidence()
        case["scope_summary"] = sampler.samples(scope).summary()
        case["scope_evidence_present"] = {
            "boundary_start": ev["boundary_start"] is not None,
            "boundary_end": ev["boundary_end"] is not None,
            "raw_samples": len(ev["samples"])}
        (out_dir / "c1_scope_evidence.json").write_text(
            json.dumps(ev, ensure_ascii=False) + "\n",
            encoding="utf-8")
        # CPU evidence gate: the container must show a measurable CPU
        # increment over the case (baseline vs final boundary)
        cpu_ok = None
        bs, be = ev.get("boundary_start"), ev.get("boundary_end")
        if bs and be and bs.get("cpu_usage_usec") is not None \
                and be.get("cpu_usage_usec") is not None:
            cpu_ok = be["cpu_usage_usec"] > bs["cpu_usage_usec"]
        case["cpu_evidence"] = cpu_ok
        if cpu_ok is not True:
            case["status"] = "FAIL"
            case["reason"] = ("no container CPU increment evidence "
                              "(baseline vs final boundary)")
            return case
        # the cpu command must NOT have timed out
        for e in events:
            if e["event"] == "closed" and \
                    e.get("tool_call_id") == "b1-cpu" and \
                    e.get("returncode") == 124:
                case["status"] = "FAIL"
                case["reason"] = "b1-cpu timed out"
                return case
        case["n_tool_events"] = len(events)
        return case
    finally:
        if env is not None:
            try:
                env.close()
            except Exception:  # noqa: BLE001
                pass
        if case.get("scope_summary") is None:
            try:
                sampler.stop(scope)
                sampler.stop_background_sampling()
                case["scope_summary_partial"] = \
                    sampler.samples(scope).summary()
                # FULL raw evidence on the failure path too
                ev = sampler.samples(scope).evidence()
                (out_dir / "c1_scope_evidence.json").write_text(
                    json.dumps(ev, ensure_ascii=False) + "\n",
                    encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        _apply_io_degradation(case)
        # I/O formal degradation applied UNCONDITIONALLY to every
        # persisted scope summary (host cgroup v1): formal=null with
        # the reason; the raw numeric block is kept as diagnostic
        _apply_io_degradation(case)


def _run_container_2(runtime, sampler, run_id, out_dir,
                     wrap_environment, remaining, cap_wait,
                     register_handle, stopped_scopes,
                     runner_mon, reader_factory=None,
                     stop_callback=None, cap_timeout=None,
                     batch_deadline=None) -> dict:
    if cap_timeout is None:
        def cap_timeout(req):
            rem = remaining()
            return 0.0 if rem <= 0 else min(req, rem)
    if batch_deadline is None:
        batch_deadline = time.monotonic() + remaining()
    import subprocess
    from ..collectors.resource_sampler import CgroupV1FileReader
    from ..collectors.host_process import (HostProcessMonitor,
                                           read_starttime)
    from ..runners.container_runtime import ContainerSpec
    scope = f"{run_id}-c2"
    handle = runtime.start(ContainerSpec(
        run_id=run_id, scope="c2", image=IMAGE, cwd="/",
        cpu_limit=BUDGET["per_container"]["cpu"],
        mem_limit=BUDGET["per_container"]["mem"],
        pull="never"),
        timeout_s=cap_timeout(60))
    register_handle(handle)  # cleanup registration AT CREATION
    case = {"case": 2, "status": "PASS",
            "container_id": handle.container_id}
    env = None
    try:
        if reader_factory is not None:
            sampler.register(scope, "verifier_container",
                             reader_factory(scope, "verifier_container",
                                            handle.container_id))
        else:
            sampler.register(scope, "verifier_container",
                             CgroupV1FileReader(scope,
                                                "verifier_container",
                                                handle.container_id))
        sampler.start(scope)
        sampler.start_background_sampling()
        events_path = out_dir / "c2_tool_events.jsonl"
        env = wrap_environment(
            _RuntimeExecuteBridge(runtime, handle, stop_callback),
            events_path)
        # Background deadline: the EARLIER of (now + busy_max_s) and
        # the batch deadline — the background work never outlives the
        # batch budget even if busy_max_s would allow more
        bg_deadline = min(
            time.monotonic() + BUDGET["background_busy_max_s"],
            batch_deadline)

        def bg_remaining() -> float:
            return bg_deadline - time.monotonic()

        bg_start_to = cap_timeout(min(BUDGET["per_command_timeout_s"],
                                      bg_remaining()))
        if bg_start_to <= 0:
            case["status"] = "FAIL"
            case["reason"] = ("background budget exhausted before "
                              "start")
            return case
        bg_out = env.execute(
            {"command": CONTAINER_2_BACKGROUND["registered_script"],
             "tool_call_id": "b2-bg-start"},
            timeout=bg_start_to)
        if bg_out.get("returncode") != 0:
            case["status"] = "FAIL"
            case["reason"] = "background start failed"
            return case
        case["bg_output"] = bg_out.get("output", "")[:100]

        # two CPU reads within the window; capped by the bg deadline
        r1 = runtime.read_counters(handle, time.monotonic_ns())
        time.sleep(max(0.0, min(1.0,
                                CONTAINER_2_BACKGROUND["window_s"] / 2,
                                bg_remaining())))
        r2 = runtime.read_counters(handle, time.monotonic_ns())
        cpu_grew = None
        if r1.cpu_usage_usec is not None and r2.cpu_usage_usec is not None:
            cpu_grew = r2.cpu_usage_usec > r1.cpu_usage_usec
        case["cpu_reads"] = {
            "t1_ns": r1.t_monotonic_ns, "t2_ns": r2.t_monotonic_ns,
            "cpu1_usec": r1.cpu_usage_usec,
            "cpu2_usec": r2.cpu_usage_usec,
            "cpu_grew_while_tool_returned": cpu_grew}
        # the PASS verdict REQUIRES the background-work evidence
        if cpu_grew is not True:
            case["status"] = "FAIL"
            case["reason"] = ("no CPU growth evidence that the "
                              "background workload kept working after "
                              "the tool call returned")
            return case
        # host child (own deterministic short program): the wait is
        # capped at BOTH the child lifetime and the remaining budget;
        # a timeout KILLS and reaps the child (identity confirmed
        # before kill); any exception also reaps by identity
        child = subprocess.Popen(
            [sys.executable, "-c", HOST_CHILD_CODE])
        child_starttime = read_starttime(child.pid)
        child_mon = HostProcessMonitor(
            child.pid, expected_starttime=child_starttime)
        try:
            time.sleep(max(0.0, min(0.3, bg_remaining())))
            child_mon.poll_once()  # mid-life snapshot 1
            runner_mon.poll_once()  # runner samples DURING the batch
            # a second mid-life poll for a 2-point interval (B0-D:
            # evidence needs >= 2 readable snapshots to prove the
            # interval was observed, not a single boundary)
            time.sleep(max(0.0, min(0.3, bg_remaining())))
            child_mon.poll_once()  # mid-life snapshot 2
            child_wait_to = min(BUDGET["host_child"]["lifetime_s"],
                                bg_remaining())
            child.wait(timeout=child_wait_to)
            if child.returncode not in (0, None):
                case["status"] = "FAIL"
                case["reason"] = (f"host child exited rc="
                                  f"{child.returncode}")
        except subprocess.TimeoutExpired:
            if read_starttime(child.pid) == child_starttime:
                child.kill()
                child.wait(timeout=5)
                case["host_child_timeout_killed"] = True
            case["status"] = "FAIL"
            case["reason"] = "host child exceeded lifetime budget"
        finally:
            if child.poll() is None:
                if read_starttime(child.pid) == child_starttime:
                    child.kill()
                    child.wait(timeout=5)
        child_mon.poll_once()
        child_summary = child_mon.summary()
        child_summary["scope"] = "host_short_child"
        child_summary["note"] = ("this batch's own deterministic "
                                 "short program; NOT the mini child "
                                 "(host_mini_child) and NOT an Agent")
        case["host_child"] = child_summary
        case["host_child_raw_snapshots"] = [
            {"t_monotonic_ns": sn.t_monotonic_ns,
             "cpu_ticks": sn.cpu_ticks,
             "rss_bytes": sn.rss_bytes,
             "stat": sn.read_status.get("stat")}
            for sn in child_mon.snapshots]
        # stop the background workload: the stop chain gets the
        # REMAINING background budget as its TOTAL allowance — it
        # must divide this across its internal steps (pkill → check
        # → docker stop), not re-derive a fresh per-step timeout
        bg_rem = bg_remaining()
        case["background_budget_remaining_s"] = round(bg_rem, 3)
        if bg_rem <= 0:
            case["status"] = "FAIL"
            case["reason"] = (f"background busy exceeded its "
                              f"{BUDGET['background_busy_max_s']}s "
                              "budget before the stop chain")
            return case
        # the runtime receives the TOTAL remaining budget; its
        # internal steps must each take at most their share of what's
        # left (we pass it as a step_share_deadline so the runtime
        # can decrement rather than restart)
        term_total = min(BUDGET["terminate_timeout_s"], bg_rem)
        term = runtime.terminate_workload(
            handle, timeout_s=term_total,
            step_share_deadline=bg_deadline)
        case["termination"] = term
        # a stop_not_confirmed FAILS the case (workload may remain)
        if term.get("confirmed") is not True:
            case["status"] = "FAIL"
            case["reason"] = ("terminate_workload not confirmed: "
                              f"{term}")
            return case
        # B0-D: the freeze observation must prove three things:
        # 1) the sampling THREAD was alive during the observation
        #    window (not just that samples exist from before);
        # 2) the scope's reads/samples/boundary are unchanged across
        #    the observation window;
        # 3) the reader has a COUNTABLE number of reads (not
        #    None==None which is vacuously true).
        # We record the observation duration, the thread aliveness,
        # and the countable reads for the evidence.
        sampler.stop(scope)
        reader_obj = sampler._readers.get(scope)
        reads_at_stop = getattr(reader_obj, "reads", None)
        n_samples_at_stop = len(sampler._data[scope].samples)
        boundary_at_stop = sampler._data[scope].boundary_end

        # thread aliveness check: the sampling thread must still be
        # alive when the observation STARTS (it may be stopped after)
        thread_alive_at_start = (sampler._thread is not None
                                 and sampler._thread.is_alive())
        obs_start = time.monotonic()
        obs_duration = cap_wait(2 * BUDGET["sampling_interval_s"] + 0.05)
        time.sleep(obs_duration)
        obs_actual = time.monotonic() - obs_start

        reader_after = sampler._readers.get(scope)
        reads_after = getattr(reader_after, "reads", None)
        n_samples_after = len(sampler._data[scope].samples)
        boundary_after = sampler._data[scope].boundary_end

        # the frozen proof: reads AND samples AND boundary unchanged
        reads_frozen = (reads_at_stop is not None
                        and reads_after == reads_at_stop)
        samples_frozen = n_samples_after == n_samples_at_stop
        boundary_frozen = boundary_after is boundary_at_stop
        frozen = reads_frozen and samples_frozen and boundary_frozen

        # the thread-aliveness proof: the thread was alive when the
        # observation began; if it was already dead, the freeze
        # evidence is INVALID (no counter-observation happened)
        case["scope_frozen_after_stop"] = (
            frozen and thread_alive_at_start)
        case["freeze_observation"] = {
            "thread_alive_at_start": thread_alive_at_start,
            "observation_target_s": round(obs_duration, 3),
            "observation_actual_s": round(obs_actual, 3),
            "reads_at_stop": reads_at_stop,
            "reads_after": reads_after,
            "reads_countable": reads_at_stop is not None,
            "n_samples_at_stop": n_samples_at_stop,
            "n_samples_after": n_samples_after,
            "reads_frozen": reads_frozen,
            "samples_frozen": samples_frozen,
            "boundary_frozen": boundary_frozen,
        }
        if not case["scope_frozen_after_stop"]:
            case["status"] = "FAIL"
            if not thread_alive_at_start:
                case["reason"] = ("freeze observation invalid: the "
                                  "sampling thread was not alive "
                                  "during the observation window")
            else:
                case["reason"] = "scope did not freeze after stop()"
            return case
        stopped_scopes.append(scope)
        sampler.stop_background_sampling()
        ev = sampler.samples(scope).evidence()
        case["scope_summary"] = sampler.samples(scope).summary()
        (out_dir / "c2_scope_evidence.json").write_text(
            json.dumps(ev, ensure_ascii=False) + "\n",
            encoding="utf-8")
        _apply_io_degradation(case)
        return case
    finally:
        if env is not None:
            try:
                env.close()
            except Exception:  # noqa: BLE001
                pass
        if case.get("scope_summary") is None:
            try:
                sampler.stop(scope)
                sampler.stop_background_sampling()
                case["scope_summary_partial"] = \
                    sampler.samples(scope).summary()
                ev = sampler.samples(scope).evidence()
                (out_dir / "c2_scope_evidence.json").write_text(
                    json.dumps(ev, ensure_ascii=False) + "\n",
                    encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        _apply_io_degradation(case)


def _check_evidence_quality(cases: list, sampler, stopped_scopes) -> dict:
    """B0-D: verify that collection ACTUALLY happened, not just that
    fields exist. Checks are True (proven), False (missing), or None
    (not applicable). A False check makes the batch FAIL."""
    evidence = {}
    for c in cases:
        if c.get("case") == 2:
            # scope freeze proof: the reader must have a COUNTABLE
            # number of reads (not None==None which is vacuously true);
            # and samples must have actually been taken
            scope_data = None
            for scope, data in sampler._data.items():
                if "c2" in scope:
                    scope_data = data
                    break
            if scope_data is not None:
                n_samples = len(scope_data.samples)
                boundary = scope_data.boundary_end is not None
                # the sampling thread must have WORKED: > 0 samples
                # taken BEFORE the stop (excluding the boundary reads)
                evidence["c2_sampling_worked"] = n_samples > 0
                evidence["c2_boundary_taken"] = boundary
                # the freeze proof: must be True (not None) AND the
                # observation evidence must show the thread was alive
                # during the observation window with countable reads
                obs = c.get("freeze_observation", {})
                evidence["c2_scope_frozen"] = (
                    c.get("scope_frozen_after_stop") is True)
                evidence["c2_thread_alive_during_observation"] = (
                    obs.get("thread_alive_at_start") is True)
                evidence["c2_reads_countable"] = (
                    obs.get("reads_countable") is True)
                # the read counter: for readers WITH a `reads` counter,
                # verify reads happened; for those without, the sample
                # count IS the observable
                reader = sampler._readers.get(
                    next((s for s in sampler._readers if "c2" in s),
                         ""), None)
                reads_val = getattr(reader, "reads", None) \
                    if reader is not None else None
                if reads_val is not None:
                    evidence["c2_reader_had_reads"] = reads_val > 0
                else:
                    # no countable reads attribute: fall back to the
                    # sample count, but mark the distinction
                    evidence["c2_reader_had_reads"] = n_samples > 0
                    evidence["c2_reader_countable"] = False
            else:
                evidence["c2_sampling_worked"] = False
                evidence["c2_boundary_taken"] = False
                evidence["c2_scope_frozen"] = False
                evidence["c2_reader_had_reads"] = False
            # host child: at least 2 readable interval snapshots OR
            # explicitly partial
            hc = c.get("host_child", {})
            n_readable = hc.get("n_readable", 0)
            if n_readable >= 2:
                evidence["host_child_two_interval_snapshots"] = True
            elif hc.get("final_read_status") == "process_exceeded":
                evidence["host_child_two_interval_snapshots"] = None
            else:
                evidence["host_child_two_interval_snapshots"] = False
    return evidence


def _apply_io_degradation(case: dict) -> None:
    """Unconditional formal-I/O degradation on every scope summary in
    the case result (host cgroup v1): formal null + reason; the raw
    numeric block (if present) moves to diagnostic."""
    for key in ("scope_summary", "scope_summary_partial"):
        summary = case.get(key)
        if not isinstance(summary, dict):
            continue
        io = summary.get("io")
        if not isinstance(io, dict):
            continue
        degraded = {
            "formal": None,
            "reason": ("degraded_host_v1_blkio: writeback attributed "
                       "to root cgroup; reads are page-cache hits; "
                       "not application bytes"),
            "diagnostic": dict(io),
        }
        summary["io"] = degraded


class _RuntimeExecuteBridge:
    """Adapts a ContainerRuntime into the Environment.execute shape so
    the shared hook wraps it exactly like the mini child path. The
    optional stop_callback lets the batch interrupt a BLOCKING execute
    (e.g. when the report threshold trips mid-case)."""

    def __init__(self, runtime, handle, stop_callback=None):
        self._runtime = runtime
        self._handle = handle
        self._stop = stop_callback

    def execute(self, action, cwd="", *, timeout=None):
        # timeout<=0 means the budget is EXHAUSTED: refuse the call
        # (the old `timeout or default` silently turned 0 into the
        # 20-second per-command default — a free-time bug). The
        # timeout is a FLOAT (0.2s stays 0.2s, no int rounding).
        effective = timeout if timeout is not None \
            else BUDGET["per_command_timeout_s"]
        if effective <= 0:
            return {"returncode": 124, "output": "",
                    "timed_out": True,
                    "stopped_by": "budget_exhausted"}
        return self._runtime.execute(
            self._handle, action.get("command", ""),
            effective,
            should_stop=self._stop)


# ---------------------------------------------------------------------------
# plan / CLI
# ---------------------------------------------------------------------------

def _plan() -> dict:
    """Complete side-effect-free batch plan."""
    identity = _checklist_identity()
    return {
        "mode": "offline_plan",
        "image": IMAGE,
        "budget": BUDGET,
        "guards": [
            "report ROOT guarded: every parent segment up to the "
            "project root is a real directory (no symlinks), inside "
            "the project, not overlapping references/catalog legacy "
            "roots/sealed data; batch id additionally validated",
            "batch wall 180 s; every fixed wait capped at the "
            "remaining budget; cleanup reserve 30 s checked before "
            "each case",
            "containers are SEQUENTIAL: case 1's container is fully "
            "stopped and its removal VERIFIED before case 2 starts; "
            "a case-1 FAIL skips case 2",
            "handles registered for cleanup AT CREATION (exceptions "
            "cannot orphan containers); removal verified by inspect, "
            "not assumed from a stop() call",
            "docker pinned to the LOCAL socket (DOCKER_HOST cleared); "
            "pull disabled (image must pre-exist; missing = stop)",
            "approval record CONTENT binds image + budget + code SHAs "
            "(empty/mismatched files refused, not just missing ones)",
        ],
        "cases": [
            {
                "container": 1,
                "purpose": "real tool hook + container counter window",
                "commands": [{"tool_call_id": tid, "command": cmd}
                             for tid, cmd in CONTAINER_1_COMMANDS],
                "assertions": [
                    "4 open/closed pairs, unique IDs, rc 0/0/nonzero/0",
                    "sleep window >= 1 s (monotonic; FAIL preserved, "
                    "no threshold adjustment)",
                    "full raw scope evidence persisted (boundaries + "
                    "samples), not just the summary",
                    "I/O degradation recorded in the actual result "
                    "(formal null + reason)",
                ],
            },
            {
                "container": 2,
                "purpose": "background work + host observation + stop "
                           "boundary",
                "background": CONTAINER_2_BACKGROUND,
                "assertions": [
                    "PASS requires CPU growth evidence (background "
                    "kept working after the tool call returned)",
                    "PASS requires terminate_workload confirmed; "
                    "stop_not_confirmed FAILS the case",
                    "PASS requires scope frozen after stop (reads AND "
                    "samples unchanged over >= 2 intervals)",
                    "host runner monitor sampled DURING the batch; "
                    "host child observed with full raw snapshots",
                ],
            },
        ],
        "degradations": [
            "host cgroup v1: formal block I/O = null + "
            "degraded_host_v1_blkio; raw values diagnostic only",
            "no container writable-layer quota; write budget is not a "
            "disk hard cap",
        ],
        "identity": {
            "entry_module": "agent_workload_characterization.runners"
                            ".b_entry",
            "interpreter": "PYTHONPATH=src python3 (stdlib-only)",
            "plan_command": (
                "cd /home/lcq/agent_workload_characterization "
                "&& PYTHONPATH=src python3 -B -m "
                "agent_workload_characterization.runners.b_entry"),
            "execute_command": (
                "cd /home/lcq/agent_workload_characterization "
                "&& PYTHONPATH=src python3 -B -m "
                "agent_workload_characterization.runners.b_entry "
                "--execute --i-approve-the-b-validation"),
            "checklist_identity": identity,
        },
        "authorization": {
            "B_user_approval": "pending",
            "approval_record_path": str(
                APPROVAL_RECORD.relative_to(PROJECT_ROOT)),
            "record_format": json.dumps({
                "checklist_identity": identity,
                "approved_by": "<user>",
                "approved_at_utc": "<timestamp>",
                "note": "user writes this file when approving the "
                        "checklist; content must match the registered "
                        "identity or execution is refused"},
                indent=2)[:400] + "... (see record_format above)",
            "note": ("the double flag is a software gate only; "
                     "authorization is the approval RECORD whose "
                     "content binds image + budget + code SHAs"),
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="b_entry", description=__doc__.splitlines()[0],
        allow_abbrev=False)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-approve-the-b-validation", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(_plan(), ensure_ascii=False, indent=2))
        return 0
    if not args.i_approve_the_b_validation:
        print("REFUSED: --execute requires --i-approve-the-b-validation "
              "(software gate; the authorization act is the user's "
              "recorded approval of the B1 checklist)",
              file=sys.stderr)
        return 2
    try:
        _verify_approval(APPROVAL_RECORD)
    except B0Error as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    # Batch deadline starts NOW: it covers the context check, image
    # preflight, execution, AND cleanup — every subsequent blocking
    # operation derives its timeout from this single deadline
    import subprocess as _sp
    t0 = time.monotonic()
    deadline = t0 + BUDGET["batch_wall_s"]

    def _rem() -> float:
        return deadline - time.monotonic()

    # Pin the LOCAL docker endpoint: explicitly set DOCKER_HOST to the
    # local unix socket (not just clear it), refuse remote contexts,
    # and treat a context-check FAILURE as a refusal (not a pass)
    local_socket = "unix:///var/run/docker.sock"
    os.environ["DOCKER_HOST"] = local_socket
    os.environ.pop("DOCKER_CONTEXT", None)
    try:
        ctx = _sp.run(["docker", "context", "show"],
                      capture_output=True, text=True,
                      timeout=min(10, max(0.5, _rem())))
    except (OSError, _sp.TimeoutExpired):
        ctx = None
    if ctx is None or ctx.returncode != 0:
        print("REFUSED: docker context check failed — cannot confirm "
              "local endpoint; refusing", file=sys.stderr)
        return 4
    if ctx.stdout.strip() != "default":
        print(f"REFUSED: docker context is {ctx.stdout.strip()!r}, not "
              "'default' — remote routing refused", file=sys.stderr)
        return 4
    from .container_runtime import DockerCliRuntime
    runtime = DockerCliRuntime(authorized=True,
                               docker_executable="docker")
    # preflight INSIDE the same deadline (missing = stop; no pull)
    pre_to = max(0.5, min(30, _rem()))
    if pre_to < 1:
        print("REFUSED: batch budget exhausted before image "
              "preflight", file=sys.stderr)
        return 5
    pre = _sp.run(
        ["docker", "--config", "/dev/null", "image", "inspect", IMAGE],
        capture_output=True, text=True, timeout=pre_to)
    if pre.returncode != 0:
        print("REFUSED: fixed image not present locally; B1 forbids "
              "pull/build — stopping", file=sys.stderr)
        return 4
    result = execute_batch(runtime=runtime,
                           _batch_deadline=deadline,
                           reader_factory=READER_FACTORY)
    # the unified batch_status drives the exit code (B0-C): archive
    # failures, budget overruns, all-skipped, and evidence gaps are
    # all reflected — not just case failures
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("batch_status") != "OK":
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
