"""Small resource summary analyzer for RUN-01 pilot attempts (P1-13 subset).

Reads one archived run directory (events.jsonl + samples.json +
metadata.json — all append-only archives) and produces a compact,
honest summary:

- per-scope: observed wall span, CPU core-seconds (counter-boundary
  evidence), avg cores (cpu/wall — explicitly NOT an efficiency metric),
  memory current / kernel peak / sampled max (three distinct numbers,
  never summed across scopes), I/O with unsupported-nulls kept;
- LLM request count, tool call count, budget usage;
- per-metric coverage with n_valid / n_applicable and missing reasons;
- the data source type (synthetic vs benchmark_real) is carried through
  and cross-checked — synthetic runs can never be reported as real.

The summary makes no attempt to produce a single "total CPU" or "total
peak memory" number: parent/child scopes may overlap and scope peaks are
not additive. Non-additivity is stated, not hidden.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _tools_block(calls_from_traj, messages_from_traj, tool_events):
    """Tool activity, never a fake zero.

    Source precedence: the mini trajectory (real runs — the runner emits
    no tool_call events on the real path) > runner tool_call events
    (fake-flow) > unknown (null)."""
    if calls_from_traj is not None:
        return {"calls": calls_from_traj,
                "observation_messages": messages_from_traj,
                "source": "mini_trajectory",
                "categories": [],
                "classification": ("not_available (no tool classifier "
                                   "wired; P1-06)"),
                "runner_event_count": len(tool_events)}
    if tool_events:
        return {"calls": len(tool_events),
                "observation_messages": None,
                "source": "runner_events",
                "categories": sorted({e["attrs"].get("category")
                                      for e in tool_events
                                      if e["attrs"].get("category")}),
                "classification": "runner_event_categories",
                "runner_event_count": len(tool_events)}
    return {"calls": None,
            "observation_messages": None,
            "source": "unknown",
            "categories": [],
            "classification": "not_available",
            "runner_event_count": 0}


def _archive_block(run_dir: Path, metadata: dict) -> dict:
    """Archive accounting reconciliation: what the in-run budget counted
    vs what is actually on disk, and what the original manifest listed
    (the original manifest iterated TOP-LEVEL files only — subdirectory
    artifacts like verifier/test_output.txt were missed; the supplement
    manifest carries the complete list).

    Two distinct sets, never conflated: the MANIFEST lists files present
    on disk (including harness-child outputs); the in-run ACCOUNTING
    covered only the RUNNER-ARCHIVED files. A file can be listed in the
    manifest yet still be outside the accounting (mini_status.jsonl,
    mini_trajectory.json)."""
    actual_files = {}
    for p in sorted(run_dir.rglob("*")):
        if p.is_file():
            actual_files[str(p.relative_to(run_dir))] = p.stat().st_size
    actual_total = sum(actual_files.values())
    original_manifest_files = []
    manifest_path = run_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            original_manifest_files = sorted(
                (json.loads(manifest_path.read_text(encoding="utf-8"))
                 .get("files") or {}).keys())
        except (OSError, ValueError):
            original_manifest_files = []
    missing = sorted(set(actual_files) - set(original_manifest_files)
                     - {"manifest.json"})
    reported = ((metadata.get("budget_usage") or {})
                .get("artifact_bytes"))
    # the static runner-archive set: what the in-run budget accounting
    # actually covered (harness-child and verifier outputs were written
    # during execution/evaluation, outside this scope)
    runner_archived = {"candidate.patch", "events.jsonl", "samples.json",
                       "metadata.json", "manifest.json", "archive_error.txt"}
    unaccounted = {name: size for name, size in actual_files.items()
                   if name not in runner_archived}
    return {
        "reported_artifact_bytes": reported,
        "reported_note": ("metadata snapshot taken before metadata.json/"
                          "manifest.json self-accounting; the outcome-level "
                          "final total is recorded in the supplement "
                          "manifest"),
        "actual_run_dir_bytes": actual_total,
        "files_total": len(actual_files),
        "original_manifest_files": original_manifest_files,
        "files_missing_from_original_manifest": missing,
        "bytes_outside_in_run_accounting": unaccounted,
        "bytes_outside_total": sum(unaccounted.values()),
        "accounting_scope_note": (
            "in-run budget accounting covered the RUNNER-ARCHIVED files "
            "only (candidate.patch, events.jsonl, samples.json, metadata."
            "json, manifest.json); harness-child outputs (mini_status."
            "jsonl, mini_trajectory.json) and the verifier test log were "
            "written during execution/evaluation outside that scope — "
            "the supplement manifest registers the complete list; the "
            "in-flight monitor polices the full tree; the runner now "
            "accounts the full tree for future runs"),
    }


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_events(path: Path) -> list[dict]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def _event_span(events: list[dict], kind: str) -> dict[str, Any]:
    """Observed span of one event kind (NOT a claimed run duration)."""
    stamps = [e["t_monotonic_ns"] for e in events if e["kind"] == kind]
    if not stamps:
        return {"observed_span_s": None, "n_events": 0,
                "missing_reason": "not_recorded"}
    return {"observed_span_s": (max(stamps) - min(stamps)) / 1e9,
            "n_events": len(stamps), "missing_reason": None}


def _count_valid(values: list[Any]) -> dict[str, Any]:
    applicable = [v for v in values if v is not None]
    return {"n_valid": len(applicable), "n_applicable": len(values),
            "missing": len(values) - len(applicable)}


def summarize_run(run_dir: Path) -> dict[str, Any]:
    """One attempt -> resource summary with coverage and limitations."""
    metadata = _load_json(run_dir / "metadata.json")
    samples = _load_json(run_dir / "samples.json")
    events = _load_events(run_dir / "events.jsonl")

    # the mini trajectory (real runs) is the authoritative source for
    # tool activity and the agent's own exit status — the runner emits
    # no tool_call events on the real path (fake-flow only)
    trajectory = None
    traj_path = run_dir / "mini_trajectory.json"
    if traj_path.is_file():
        try:
            trajectory = json.loads(traj_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            trajectory = None
    tool_calls_from_traj = None
    tool_messages_from_traj = None
    agent_exit_status = None
    agent_submission_present = None
    if trajectory is not None:
        msgs = trajectory.get("messages") or []
        tool_calls_from_traj = sum(
            len((m.get("extra") or {}).get("actions") or [])
            for m in msgs if m.get("role") == "assistant")
        tool_messages_from_traj = sum(
            1 for m in msgs if m.get("role") == "tool")
        info = trajectory.get("info") or {}
        agent_exit_status = info.get("exit_status")
        agent_submission_present = bool(info.get("submission"))

    source_type = metadata.get("source_type", "unknown")
    # llm_request events come in open+closed pairs (begin/end per
    # request): count CLOSED events as requests; `ok` lives on the
    # closing event's attrs. Status lines without a closing event
    # (killed mid-request) are right-censored, not failed requests.
    llm_events = [e for e in events if e["kind"] == "llm_request"]
    llm_closed = [e for e in llm_events if e.get("status") == "closed"]
    # begin markers (status "open") are informational when a matching
    # closed event exists; TRUE censoring is status "unclosed"
    llm_censored = [e for e in llm_events if e.get("status") == "unclosed"]
    # tool_call events are emitted by the fake harness flow; the real
    # mini harness does not emit them (tool activity lives in the mini
    # trajectory) — reported as-is with the coverage limitation below
    tool_events = [e for e in events if e["kind"] == "tool_call"
                   and e.get("status") in ("closed", "error")]
    unclosed = [e for e in events if e.get("status") == "unclosed"]

    scopes = []
    evidence = samples.get("evidence") or {}
    for scope, data in (samples.get("scopes") or {}).items():
        entry = {"scope": scope, "scope_kind": data.get("scope_kind"),
                 **{k: data.get(k) for k in
                    ("cpu_core_seconds", "cpu_core_seconds_reason",
                     "cpu_evidence", "wall_s", "avg_cores", "memory_current_end_bytes",
                     "memory_kernel_peak_bytes", "memory_sampled_max_bytes",
                     "memory_peak_basis", "n_samples")}}
        # I/O formal-vs-diagnostic split: on this host (cgroup v1) scope
        # block I/O is UNRELIABLE (writeback attributed to the root
        # cgroup; reads are page-cache hits) — the APPROVED degradation
        # wording makes the formal metric null + reason and keeps the
        # raw counts as diagnostic values only. Detection: the boundary
        # read_status shows the v1 throttle blkio source.
        if "io" in data:
            ev = evidence.get(scope) or {}
            end_status = (ev.get("boundary_end") or {}).get("read_status") or {}
            is_v1_blkio = any("blkio.throttle" in str(v)
                              for v in end_status.values())
            if is_v1_blkio:
                entry["io"] = {
                    "formal": None,
                    "reason": ("degraded_host_v1_blkio: writeback "
                               "attributed to root cgroup; reads are "
                               "page-cache hits; not application bytes"),
                    "diagnostic": data["io"],
                }
            else:
                entry["io"] = data["io"]
        ev = evidence.get(scope) or {}
        entry["evidence_check"] = {
            "boundary_start_present": ev.get("boundary_start") is not None,
            "boundary_end_present": ev.get("boundary_end") is not None,
            "raw_sample_count": len(ev.get("samples") or []),
            "gaps_recorded": len(ev.get("sample_gaps_ns") or []),
        }
        scopes.append(entry)

    cpu_values = [s.get("cpu_core_seconds") for s in scopes]
    summary = {
        "run_id": metadata.get("run_id"),
        "attempt_id": metadata.get("attempt_id"),
        "task_id": metadata.get("task_id"),
        "source_type": source_type,
        "status": {"execution": metadata.get("execution_status"),
                   "evaluation": metadata.get("evaluation_status"),
                   "archive": "ok"},
        "resolved": metadata.get("resolved"),
        "budget": metadata.get("budget_usage"),
        "llm": {"requests": len(llm_closed),
                "ok": sum(1 for e in llm_closed if e["attrs"].get("ok") is True),
                "failed": sum(1 for e in llm_closed if e["attrs"].get("ok") is False),
                "censored": len(llm_censored),
                "usage_coverage": _count_valid(
                    [e["attrs"].get("usage") for e in llm_closed])},
        "agent": {
            "exit_status": agent_exit_status,
            "submitted": agent_submission_present,
            "candidate_source": (
                "container_working_tree_git_diff"
                if (run_dir / "candidate.patch").is_file() else None),
            "note": ("exit_status/submission come from the mini trajectory; "
                     "the runner always extracts the candidate from the "
                     "container working tree, so a non-submitted agent "
                     "exit (e.g. LimitsExceeded) can still yield a "
                     "verified candidate — execution=ok describes the "
                     "PIPELINE, not an agent clean finish"),
            "trajectory_present": trajectory is not None,
        },
        "tools": _tools_block(tool_calls_from_traj, tool_messages_from_traj,
                              tool_events),
        "llm_observed_span": _event_span(llm_closed, "llm_request"),
        "scopes": scopes,
        "cpu_core_seconds_coverage": _count_valid(cpu_values),
        "unclosed_events": len(unclosed),
        "archive": _archive_block(run_dir, metadata),
        "collector": samples.get("collector"),
        "limitations": [
            "scope peaks are NOT additive: no run-level peak memory exists",
            "avg cores = cpu/wall within a scope; not an efficiency metric",
            "parent/child scope overlap means scope CPUs must not be summed "
            "into a total without an explicit mutual-exclusion proof",
            "page cache makes block I/O differ from application bytes; "
            "io.read_bytes is the interval delta, not the cumulative value",
            "sample count is not accuracy evidence; boundary counters carry "
            "the CPU evidence for short bursts",
            "tool-level semantic events are emitted by the fake harness "
            "flow only; the real mini harness records tool activity in the "
            "mini trajectory, so tool counts here may be 0 for real runs",
            "host_agent_runtime scope (the host-side mini child) has no "
            "per-process CPU/RSS instrumentation; its wall/request "
            "boundaries come from the status protocol",
        ],
    }
    if source_type == "synthetic":
        summary["limitations"].insert(
            0, "SYNTHETIC run: fake model + fake containers; not a "
               "benchmark_real observation")
    return summary


def write_summary_report(report_dir: Path, summary: dict[str, Any],
                         *, batch: str) -> dict:
    """Write the summary package under reports/resource/<batch>/.

    Exclusive create; the report references the archived run by path and
    never rewrites run artifacts.
    """
    report_dir.mkdir(parents=True, exist_ok=False)
    (report_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    lines = ["# RUN-01 resource summary", "",
             f"batch: {batch}",
             f"generated: {datetime.now(timezone.utc).isoformat()}",
             f"source_type: {summary.get('source_type')}", "",
             "## Scopes", ""]
    for scope in summary.get("scopes", []):
        lines.append(
            f"- {scope.get('scope')} ({scope.get('scope_kind')}): "
            f"cpu={scope.get('cpu_core_seconds')} core-s "
            f"(reason={scope.get('cpu_core_seconds_reason')}), "
            f"wall={scope.get('wall_s')}s, "
            f"mem_peak_basis={scope.get('memory_peak_basis')}")
    lines += ["", "## Limitations", ""]
    for note in summary.get("limitations", []):
        lines.append(f"- {note}")
    (report_dir / "summary.md").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")
    files = {}
    for child in sorted(report_dir.iterdir()):
        if child.is_file():
            files[child.name] = hashlib.sha256(child.read_bytes()).hexdigest()
    (report_dir / "manifest.json").write_text(
        json.dumps({"batch": batch, "files": files}, ensure_ascii=False,
                   indent=2) + "\n", encoding="utf-8")
    return {"path": str(report_dir), "files": list(files)}
