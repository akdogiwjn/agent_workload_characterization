"""Derived report for one sealed RUN-02 attempt."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .resource_summary import summarize_run
from .tool_timeline import build_tool_timeline


def _event_view(path: Path) -> dict:
    events = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    groups = {kind: [e.get("event_id") for e in events if e.get("event") == kind]
              for kind in ("open", "closed", "error")}
    opens, closes, errors = (set(groups["open"]), set(groups["closed"]),
                             set(groups["error"]))
    duplicates = lambda values: sorted({x for x in values if values.count(x) > 1})
    return {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
        if path.is_file() else None,
        "n_events": len(events), "n_open": len(opens),
        "n_closed": len(closes), "n_error": len(errors),
        "duplicate_open_ids": duplicates(groups["open"]),
        "duplicate_closed_ids": duplicates(groups["closed"]),
        "duplicate_error_ids": duplicates(groups["error"]),
        "closed_without_open": sorted(closes - opens),
        "error_without_open": sorted(errors - opens),
        "unclosed_open_ids": sorted(opens - closes),
        "terminal_error_ids": sorted(errors),
        "safe_command_views_only": all(
            "command" not in e and "output" not in e for e in events),
    }


def _native_timeline(path: Path) -> dict:
    """Use native hook start/end, never trajectory receipt timestamps."""
    if not path.is_file():
        return {"status": "missing", "reason": "mini_tool_events.jsonl missing",
                "records": [], "coverage": {"n_valid_durations": 0}}
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    grouped: dict[str, list[dict]] = {}
    order: list[str] = []
    for event in events:
        event_id = event.get("event_id")
        if event_id is None:
            continue
        if event_id not in grouped:
            order.append(event_id)
        grouped.setdefault(event_id, []).append(event)
    records = []
    for event_id in order:
        items = grouped[event_id]
        opening = next((e for e in items if e.get("event") == "open"), None)
        ending = next((e for e in items if e.get("event") in ("closed", "error")), None)
        start = opening.get("t_start_ns") if opening else None
        end = ending.get("t_end_ns") if ending else None
        duration = ((end - start) / 1e9 if isinstance(start, int)
                    and isinstance(end, int) and end >= start else None)
        records.append({
            "event_id": event_id,
            "seq": opening.get("seq") if opening else None,
            "tool_call_id": (opening or ending or {}).get("tool_call_id"),
            "command_view": opening.get("command_view") if opening else None,
            "event_kind": ending.get("event") if ending else "unclosed",
            "returncode": ending.get("returncode") if ending else None,
            "exception_type": ending.get("exception_type") if ending else None,
            "t_start_ns": start, "t_end_ns": end,
            "duration_s": duration,
            "duration_evidence": ("native_hook_boundaries"
                                   if duration is not None else "unavailable"),
        })
    view = _event_view(path)
    unclosed_without_terminal = sorted(set(view["unclosed_open_ids"])
                                       - set(view["terminal_error_ids"]))
    structural = (view["duplicate_open_ids"] + view["duplicate_closed_ids"]
                  + view["duplicate_error_ids"] + view["closed_without_open"]
                  + view["error_without_open"] + unclosed_without_terminal)
    return {
        "status": "complete" if records and not structural else "partial",
        "records": records,
        "coverage": {"n_valid_durations": sum(
            record["duration_s"] is not None for record in records),
            "n_records": len(records)},
        "structural_checks": {
            "duplicate": view["duplicate_open_ids"]
                         + view["duplicate_closed_ids"]
                         + view["duplicate_error_ids"],
            "orphaned": view["closed_without_open"] + view["error_without_open"],
            "unclosed": view["unclosed_open_ids"],
            "unclosed_without_terminal_error": unclosed_without_terminal,
        },
        "event_view": view,
    }


def summarize_run_02(run_dir: Path) -> dict:
    """Return a safe derived summary; missing raw files are never normal."""
    base = summarize_run(run_dir)
    host_path = run_dir / "host_process.jsonl"
    host = None
    if host_path.is_file():
        doc = json.loads(host_path.read_text(encoding="utf-8"))
        host = {
            "path": host_path.name,
            "sha256": hashlib.sha256(host_path.read_bytes()).hexdigest(),
            "identity_present": (doc.get("identity", {}).get("pid") is not None
                                  and "starttime_ticks" in doc.get("identity", {})),
            "units_present": "units" in doc,
            "n_snapshots": len(doc.get("records") or []),
            "summary": doc.get("summary"),
        }
    event_path = run_dir / "mini_tool_events.jsonl"
    native = _native_timeline(event_path)
    missing = [name for name in ("mini_tool_events.jsonl", "host_process.jsonl")
               if not (run_dir / name).is_file()]
    trajectory_tool_count = None
    trajectory_path = run_dir / "mini_trajectory.json"
    if trajectory_path.is_file():
        try:
            trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
            trajectory_tool_count = sum(
                len((message.get("extra") or {}).get("actions") or [])
                for message in trajectory.get("messages") or []
                if message.get("role") == "assistant")
        except (OSError, ValueError, TypeError):
            trajectory_tool_count = None
    observed_tool_count = len(native.get("records") or [])
    tool_complete = (trajectory_tool_count == 0
                     if trajectory_tool_count == 0 else
                     trajectory_tool_count is not None
                     and observed_tool_count == trajectory_tool_count
                     and native.get("coverage", {}).get("n_valid_durations", 0)
                     == observed_tool_count)
    host_valid = bool(host and host.get("identity_present")
                      and host.get("units_present")
                      and host.get("n_snapshots", 0) > 0)
    native_observation_ok = (
        native["status"] == "complete"
        or (trajectory_tool_count == 0
            and not any((native.get("structural_checks") or {}).values())))
    status = ("complete" if not missing and native_observation_ok
              and tool_complete and host_valid
              else "partial")
    return {
        "collection": "RUN-02", "run_dir": str(run_dir), "status": status,
        "missing_required_files": missing, "resource_summary": base,
        "observation_quality": {
            "trajectory_tool_count": trajectory_tool_count,
            "observed_tool_count": observed_tool_count,
            "tool_complete": tool_complete,
            "native_observation_ok": native_observation_ok,
            "host_identity_and_samples": host_valid,
        },
        "tool_events": _event_view(event_path), "host_process": host,
        "tool_timeline": native,
        "trajectory_timeline": build_tool_timeline(run_dir) if not missing else None,
        "limitations": [
            "tool and resource windows are shared-scope associations, not exclusive Tool CPU",
            "raw mini_tool_events.jsonl and host_process.jsonl remain authoritative",
            "unknown and censored values remain null; no interpolation is performed",
        ],
    }


def write_run_02_report(report_dir: Path, run_dir: Path, *, identity: dict) -> dict:
    """Write a new derived report without modifying the sealed raw run."""
    from ..runners.report_writer import guard_resource_report
    project_root = run_dir.resolve().parents[4]
    report_dir = guard_resource_report(project_root, report_dir, "RUN-02")
    report_dir.mkdir(parents=True, exist_ok=False)
    summary = summarize_run_02(run_dir)
    summary["identity"] = identity
    (report_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (report_dir / "summary.md").write_text(
        "# RUN-02 resource report\n\n"
        f"status: {summary['status']}\nraw_run_dir: {run_dir}\n\n"
        "Tool windows use native hook boundaries; resource association is "
        "shared-scope only.\n", encoding="utf-8")
    files = {child.name: hashlib.sha256(child.read_bytes()).hexdigest()
             for child in sorted(report_dir.iterdir()) if child.is_file()}
    manifest = {"run_dir": str(run_dir), "status": summary["status"],
                "files": files}
    (report_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": summary["status"], "manifest": manifest}
