#!/usr/bin/env python3
"""Fixed offline-preparable 3-task x 3-repeat ToolSandbox batch entry."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from toolsandbox_resource_pilot_01_entry import (
    EntryProfile, PILOT_01_PROFILE, build_identity, command_for, execute,
    file_record, freeze as shared_freeze, identity_sha, namespace_state,
    plan_mode as shared_plan_mode, prepare_source as shared_prepare_source,
    verify_run_archive,
)

ROOT = Path(__file__).resolve().parents[1]
TASKS = (
    "send_message_with_contact_content_cellular_off",
    "add_reminder_content_and_week_delta_and_time",
    "modify_contact_with_message_recency_multiple_user_turn",
)
TASK_LABELS = {TASKS[0]: "A", TASKS[1]: "B", TASKS[2]: "C"}
ROUND_SCHEDULE = (
    (TASKS[0], TASKS[1], TASKS[2]),
    (TASKS[1], TASKS[2], TASKS[0]),
    (TASKS[2], TASKS[0], TASKS[1]),
)
BATCH_BUDGET = {
    "total_wall_s": 4800.0,
    "cleanup_reserve_s": 480.0,
    "max_logical_model_calls": 360,
    "logical_call_basis": "9 runs x (20 Agent + 20 User); not an HTTP request limit",
    "attempt_retry": 0,
    "failure_policy": "stop_on_infrastructure_archive_reap_or_worker_phase_timeout; remaining_not_executed; never_top_up",
}
PROFILE = EntryProfile(
    collection="TOOLSANDBOX-ASSISTANT-REPEAT-01",
    env_rel=Path("env/toolsandbox-assistant-repeat-01"),
    report_rel=Path("reports/resource/TOOLSANDBOX-ASSISTANT-REPEAT-01"),
    raw_rel=Path("data/raw/generated/TOOLSANDBOX-ASSISTANT-REPEAT-01"),
    approval_flag="--i-approve-the-toolsandbox-assistant-repeat-01",
    entry_script="scripts/toolsandbox_assistant_repeat_01_entry.py",
    run_suffix="tsbassistant01",
    source_copy_rel=PILOT_01_PROFILE.source_copy_rel,
    shared_entry_script="scripts/toolsandbox_resource_pilot_01_entry.py",
    scenario_names=TASKS,
    batch_schedule=ROUND_SCHEDULE,
    batch_budget=BATCH_BUDGET,
)
RUN_BUDGETS = {
    "agent_logical_calls": 20, "user_logical_calls": 20,
    "play_s": 300.0, "evaluate_s": 60.0,
    "total_wall_s": 480.0, "cleanup_reserve_s": 120.0,
    "max_messages": 30,
}


def identity(root: Path = ROOT) -> dict:
    return build_identity(root, profile=PROFILE)


def plan_mode(root: Path = ROOT) -> dict:
    p = shared_plan_mode(root, profile=PROFILE)
    p["batch_command"] = command_for(PROFILE)
    p["planned_run_count"] = 9
    p["execution_authorized"] = False
    return p


def prepare_source(root: Path = ROOT) -> dict:
    return shared_prepare_source(root, profile=PROFILE)


def freeze(root: Path = ROOT) -> dict:
    return shared_freeze(root, profile=PROFILE)


def _quantile(values: list[float], q: float) -> float:
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(float(v) for v in values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def _distribution(points: list[dict], key: str) -> dict:
    values = [p[key] for p in points if isinstance(p.get(key), (int, float))
              and not isinstance(p.get(key), bool)]
    if not values:
        return {"n": 0, "raw_points": [], "median": None, "q1": None, "q3": None, "iqr": None}
    med = float(statistics.median(values))
    q1, q3 = _quantile(values, .25), _quantile(values, .75)
    return {"n": len(values), "raw_points": values, "median": med,
            "q1": q1, "q3": q3, "iqr": q3 - q1,
            "quantile_method": "linear interpolation at (n-1)*p"}


def _phase_metrics(report: dict) -> dict:
    rows = report.get("budget_phase_report", {}).get("phases", [])
    by_name = {}
    for row in rows:
        by_name.setdefault(row.get("phase"), []).append(row)
    out = {}
    for phase, start_name, end_name in (
        ("setup", "imports_begin", "play_begin"),
        ("play", "play_begin", "play_end"),
        ("evaluator", "evaluate_begin", "evaluate_end"),
    ):
        start = next((x for x in by_name.get(start_name, []) if isinstance(x.get("t_monotonic_ns"), int)), None)
        end = next((x for x in by_name.get(end_name, []) if isinstance(x.get("t_monotonic_ns"), int)), None)
        if start is None or end is None or end["t_monotonic_ns"] < start["t_monotonic_ns"]:
            out[phase] = {"wall_s": None, "cpu_ticks": None, "user_ticks": None, "system_ticks": None}
        else:
            out[phase] = {
                "wall_s": (end["t_monotonic_ns"] - start["t_monotonic_ns"]) / 1e9,
                "cpu_ticks": (end.get("cpu_ticks") - start.get("cpu_ticks")
                              if isinstance(end.get("cpu_ticks"), int) and isinstance(start.get("cpu_ticks"), int)
                              and end["cpu_ticks"] >= start["cpu_ticks"] else None),
                "user_ticks": (end.get("user_ticks") - start.get("user_ticks")
                               if isinstance(end.get("user_ticks"), int) and isinstance(start.get("user_ticks"), int)
                               and end["user_ticks"] >= start["user_ticks"] else None),
                "system_ticks": (end.get("system_ticks") - start.get("system_ticks")
                                 if isinstance(end.get("system_ticks"), int) and isinstance(start.get("system_ticks"), int)
                                 and end["system_ticks"] >= start["system_ticks"] else None),
            }
    return out


def _summarize_run(run_id: str, task: str, round_index: int, order_index: int,
                   report: dict, raw_dir: Path, report_path: Path, root: Path) -> dict:
    wr = report.get("worker_result") or {}
    counts = wr.get("counts") or {}
    evaluation = wr.get("evaluation")
    env_path = raw_dir / "environment.json"
    scenario_path = raw_dir / "scenario_context.json"
    samples = _read_jsonl(raw_dir / "samples.jsonl")
    cpu_samples = [x["cpu_ticks"] for x in samples
                   if isinstance(x.get("cpu_ticks"), int) and not isinstance(x.get("cpu_ticks"), bool)]
    phase_boundaries = _phase_metrics(report)
    phase_distributions = {
        f"{phase}_{field}": value
        for phase, values in phase_boundaries.items()
        for field, value in values.items()
    }
    return {
        "run_id": run_id, "task": task, "task_label": TASK_LABELS[task],
        "round": round_index, "position_in_round": order_index,
        "report_path": str(report_path.relative_to(root)),
        "raw_path": str(raw_dir.relative_to(root)),
        "exit_code": report.get("exit_code"),
        "termination": ("timeout" if report.get("killed_by_deadline") else
                        "model_budget_terminated" if report.get("exit_code") == 3 else
                        "finished" if report.get("worker_exit_code") == 0 else "error"),
        "logical_requests": {"agent": counts.get("agent_logical_calls"),
                             "user": counts.get("user_logical_calls")},
        "logical_tool_calls": counts.get("logical_tool_calls"),
        "tool_batches": counts.get("tool_batches"),
        "tool_call_executions": counts.get("tool_call_executions"),
        "evaluation": evaluation,
        "worker_failure": wr.get("failure"),
        "wall_s": report.get("wall_s"),
        "worker_window_wall_s": report.get("worker_window_wall_s"),
        "phase_boundaries": phase_boundaries,
        "phase_metrics_flat": phase_distributions,
        "sample_points": report.get("host_sampling", {}).get("rows"),
        "sample_cpu_ticks_delta": cpu_samples[-1] - cpu_samples[0] if len(cpu_samples) > 1
        and cpu_samples[-1] >= cpu_samples[0] else None,
        "rss_sampled_peak_bytes": max((x.get("rss_bytes") for x in samples
                                         if isinstance(x.get("rss_bytes"), int)), default=None),
        "runtime_environment_present": env_path.is_file(),
        "scenario_context_present": scenario_path.is_file(),
        "cleanup": report.get("cleanup"),
        "archive_verification": report.get("archive_verification"),
        "within_total_budget": report.get("within_total_budget"),
    }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _batch_summary(run_points: list[dict], not_executed: list[dict], stop_reason: str | None) -> dict:
    metrics = ("wall_s", "worker_window_wall_s", "sample_points", "rss_sampled_peak_bytes")
    grouped = {}
    for task in TASKS:
        points = [p for p in run_points if p["task"] == task]
        grouped[task] = {
            "task_label": TASK_LABELS[task], "planned_repeats": 3,
            "executed": len(points), "not_executed": sum(x["task"] == task for x in not_executed),
            "runs": points,
            "metrics": {k: _distribution(points, k) for k in metrics},
            "logical_requests_agent": _distribution(
                [{"v": p["logical_requests"].get("agent")} for p in points], "v"),
            "logical_requests_user": _distribution(
                [{"v": p["logical_requests"].get("user")} for p in points], "v"),
            "phase_metrics": {
                key: _distribution([{"v": (p.get("phase_metrics_flat") or {}).get(key)}
                                    for p in points], "v")
                for key in sorted({k for p in points for k in (p.get("phase_metrics_flat") or {})})
            },
            "sample_cpu_ticks_delta": _distribution(
                [{"v": p.get("sample_cpu_ticks_delta")} for p in points], "v"),
        }
    return {
        "schema": "toolsandbox-assistant-repeat-batch-summary-v1",
        "collection": PROFILE.collection, "planned_tasks": list(TASKS),
        "schedule": [[{"task": t, "label": TASK_LABELS[t]} for t in row] for row in ROUND_SCHEDULE],
        "executed": len(run_points), "not_executed_count": len(not_executed),
        "not_executed": not_executed, "stop_reason": stop_reason,
        "per_task": grouped,
        "statistics": "Per-task n, raw points, median and linear-interpolated Q1/Q3/IQR where a numeric metric is available; missing metrics are omitted, never zero-filled.",
        "execution_occurred": bool(run_points),
    }


def _valid_approval(root: Path, plan: dict) -> bool:
    path = root / PROFILE.report_rel / "APPROVAL.json"
    try:
        a = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    return (a.get("schema") == "toolsandbox-pilot-approval-v1"
            and a.get("collection") == PROFILE.collection
            and a.get("user_approval") == "approved"
            and a.get("identity_sha256") == plan["identity_sha256"]
            and a.get("accept_unknown_cost_no_hard_cap") is True
            and "entry_invocation" not in a)


def execute_batch(root: Path, plan: dict, *, transport_provider=None,
                  started_monotonic_ns: int | None = None,
                  budgets_override: dict | None = None,
                  batch_budget_override: dict | None = None) -> int:
    if not plan.get("identity_matches_frozen") or not plan.get("ready_for_execution"):
        raise ValueError("batch execution refused: full identity, approval or namespace gate failed")
    if not _valid_approval(root, plan):
        raise ValueError("batch approval is stale or not accepted for this identity")
    raw_root = root / PROFILE.raw_rel
    report_root = root / PROFILE.report_rel
    raw_root.mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)
    started_path = report_root / "BATCH_ATTEMPT_STARTED.json"
    with started_path.open("x") as stream:
        json.dump({"collection": PROFILE.collection,
                   "identity_sha256": plan["identity_sha256"],
                   "started_at_utc": datetime.now(timezone.utc).isoformat()}, stream, indent=1)
        stream.write("\n")
    batch_started_ns = started_monotonic_ns or time.monotonic_ns()
    batch_budget = {**BATCH_BUDGET, **(batch_budget_override or {})}
    batch_deadline_ns = batch_started_ns + int(batch_budget["total_wall_s"] * 1e9)
    batch_work_deadline_ns = batch_deadline_ns - int(batch_budget["cleanup_reserve_s"] * 1e9)
    budgets = {**plan["identity"]["budgets"], **(budgets_override or {})}
    points = []
    not_executed = []
    stop_reason = None
    flat = [(ri, pos, task) for ri, tasks in enumerate(ROUND_SCHEDULE)
            for pos, task in enumerate(tasks)]
    for sequence, (round_index, order_index, task) in enumerate(flat):
        remaining_ns = batch_deadline_ns - time.monotonic_ns()
        required_ns = int((budgets["total_wall_s"] + batch_budget["cleanup_reserve_s"]) * 1e9)
        if time.monotonic_ns() + required_ns > batch_deadline_ns:
            stop_reason = "insufficient_batch_budget_for_complete_attempt_and_reserved_batch_cleanup"
            not_executed = [{"round": r, "position_in_round": p, "task": t,
                             "task_label": TASK_LABELS[t], "reason": stop_reason}
                            for r, p, t in flat[sequence:]]
            break
        run_id = (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                  + f"-r{round_index}-{TASK_LABELS[task].lower()}-{PROFILE.run_suffix}")
        run_dir = raw_root / run_id
        report_path = report_root / "runs" / f"{run_id}.json"
        manifest_path = report_root / "runs" / f"{run_id}.manifest.json"
        metadata = {"round": round_index, "position_in_round": order_index,
                    "sequence_index": sequence, "task_label": TASK_LABELS[task],
                    "batch_identity_sha256": plan["identity_sha256"]}
        transport = transport_provider(task, round_index, order_index) if transport_provider else None
        attempt_plan = dict(plan)
        attempt_plan["ready_for_execution"] = True
        try:
            rc = execute(root, attempt_plan, transport=transport, profile=PROFILE,
                         scenario_name=task, run_id=run_id, run_metadata=metadata,
                         budgets_override=budgets, batch_deadline_ns=batch_deadline_ns,
                         batch_work_deadline_ns=batch_work_deadline_ns,
                         report_path=report_path, outer_manifest_path=manifest_path)
            report = json.loads(report_path.read_text())
        except Exception as exc:
            stop_reason = "batch_runner_error:" + type(exc).__name__
            not_executed = [{"round": r, "position_in_round": p, "task": t,
                             "task_label": TASK_LABELS[t], "reason": stop_reason}
                            for r, p, t in flat[sequence + 1:]]
            break
        point = _summarize_run(run_id, task, round_index, order_index,
                               report, run_dir, report_path, root)
        point["exit_code"] = rc
        points.append(point)
        cleanup = report.get("cleanup") or {}
        infra_ok = (cleanup.get("wait_reaped") is True
                    and cleanup.get("original_process_gone") is True
                    and cleanup.get("sampler_stopped") is True
                    and report.get("archive_verification", {}).get("valid") is True
                    and report.get("within_total_budget") is True)
        if report.get("killed_by_deadline"):
            stop_reason = "worker_phase_or_common_deadline_timeout"
        elif not infra_ok or rc not in (0, 3):
            stop_reason = "infrastructure_cleanup_or_archive_failure"
        if stop_reason:
            not_executed = [{"round": r, "position_in_round": p, "task": t,
                             "task_label": TASK_LABELS[t], "reason": stop_reason}
                            for r, p, t in flat[sequence + 1:]]
            break
    summary = _batch_summary(points, not_executed, stop_reason)
    summary_path = report_root / "batch-summary.json"
    with summary_path.open("x") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    completed_path = report_root / "BATCH_ATTEMPT_COMPLETED.json"
    with completed_path.open("x") as stream:
        json.dump({"collection": PROFILE.collection,
                   "identity_sha256": plan["identity_sha256"],
                   "executed": len(points), "not_executed": len(not_executed),
                   "stop_reason": stop_reason,
                   "completed_at_utc": datetime.now(timezone.utc).isoformat()}, stream, indent=1)
        stream.write("\n")
    manifest_path = report_root / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError("batch manifest already exists")
    inputs = [file_record(root / PROFILE.report_rel / "APPROVAL.json", PROFILE.report_rel / "APPROVAL.json"),
              file_record(root / PROFILE.env_rel / "plan-identity.json", PROFILE.env_rel / "plan-identity.json"),
              file_record(root / PROFILE.env_rel / "frozen-identity.json", PROFILE.env_rel / "frozen-identity.json"),
              file_record(root / PROFILE.env_rel / "preparation-manifest.json",
                          PROFILE.env_rel / "preparation-manifest.json")]
    outputs = [file_record(p, p.relative_to(root)) for p in sorted(report_root.rglob("*"))
               if p.is_file() and p != manifest_path]
    raw_run_manifests = []
    for point in points:
        raw_manifest = root / PROFILE.raw_rel / point["run_id"] / "manifest.json"
        raw_run_manifests.append(file_record(raw_manifest, raw_manifest.relative_to(root)))
    with manifest_path.open("x") as stream:
        json.dump({"schema": "toolsandbox-assistant-repeat-batch-manifest-v1",
                   "identity_sha256": plan["identity_sha256"], "inputs": inputs,
                   "outputs": outputs, "raw_run_manifests": raw_run_manifests,
                   "manifest_self_hash": False}, stream, indent=1)
        stream.write("\n")
    for item in outputs:
        path = root / item["path"]
        payload = path.read_bytes()
        if len(payload) != item["bytes"] or hashlib.sha256(payload).hexdigest() != item["sha256"]:
            return 7
    for item in raw_run_manifests:
        path = root / item["path"]
        payload = path.read_bytes()
        if len(payload) != item["bytes"] or hashlib.sha256(payload).hexdigest() != item["sha256"]:
            return 7
        if not verify_run_archive(path.parent)[0]:
            return 7
    return 0 if not stop_reason else 4


def main(argv=None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare-source", action="store_true")
    modes.add_argument("--freeze", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument(PROFILE.approval_flag, action="store_true", dest="approved")
    args = parser.parse_args(argv)
    try:
        if args.execute:
            if not args.approved:
                raise ValueError("this collection's explicit approval flag is required")
            return execute_batch(root, plan_mode(root))
        if args.prepare_source:
            print(json.dumps(prepare_source(root), ensure_ascii=False, indent=2))
            return 0
        p = freeze(root) if args.freeze else plan_mode(root)
        print(json.dumps(p, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, FileExistsError) as exc:
        print("REFUSED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
