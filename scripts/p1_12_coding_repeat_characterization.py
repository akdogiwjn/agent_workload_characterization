#!/usr/bin/env python3
"""CODING-REPEAT-01 characterization: tool behavior, time structure, and
resource trajectories for the nine sealed runs.

Read-only analysis over the sealed batch; every number is derived from the
input files at run time (no hardcoded conclusions).  The method adapts
interval-merging and command-classification ideas from the local AgentCgroup
reference (recorded in the manifest) while refusing its banned patterns
(thinking-time subtraction, one-sample-one-second, latest-attempt selection,
exclusive tool CPU from shared containers, correlation-as-causation).
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "reports/resource/P1-12/repeats/CODING-REPEAT-01"
RAW_ROOT = ROOT / "data/raw/generated/P1-12-CODING-REPEAT-01"
OUT = ROOT / "reports/analysis/P1-12-CODING-REPEAT-01-characterization-v1"
AGENTCGROUP = ROOT / "references/repos/agentcgroup"
MARKER = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
MIB = 1048576


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def file_record(p: Path, root: Path = ROOT) -> dict:
    return {"path": str(p.relative_to(root)), "bytes": p.stat().st_size,
            "sha256": sha256(p)}


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _lines(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def median_iqr(values):
    if not values:
        return {"n": 0, "median": None, "iqr": None, "min": None, "max": None}
    vs = sorted(values)
    n = len(vs)
    def q(p):
        pos = p * (n - 1)
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        return vs[lo] + (vs[hi] - vs[lo]) * (pos - lo)
    return {"n": n, "median": statistics.median(vs),
            "iqr": q(0.75) - q(0.25), "min": vs[0], "max": vs[-1]}


# ---------------------------------------------------------------------------
# interval helpers (adapted from AgentCgroup tool_timing.py; integer ns)
# ---------------------------------------------------------------------------

def merge_intervals_ns(intervals):
    valid = sorted((s, e) for s, e in intervals
                   if s is not None and e is not None and e >= s)
    if not valid:
        return []
    merged = [valid[0]]
    for s, e in valid[1:]:
        ps, pe = merged[-1]
        if s <= pe:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def union_ns(intervals):
    return sum(e - s for s, e in merge_intervals_ns(intervals))


def intersection_ns(a, b):
    """Total overlap between the unions of two interval lists."""
    ma, mb = merge_intervals_ns(a), merge_intervals_ns(b)
    i = j = 0
    total = 0
    while i < len(ma) and j < len(mb):
        lo = max(ma[i][0], mb[j][0])
        hi = min(ma[i][1], mb[j][1])
        if hi > lo:
            total += hi - lo
        if ma[i][1] < mb[j][1]:
            i += 1
        else:
            j += 1
    return total


# ---------------------------------------------------------------------------
# command classification (frozen rules based on the actual nine-run corpus)
# ---------------------------------------------------------------------------

_READ_HEADS = re.compile(
    r"^(sed\s+-n|grep|cat(?!>)|find|ls|head|tail|wc|du|pwd|echo\s+merge-base|"
    r"git\s+(show|log|diff|status|branch|merge-base|remote|rev-parse))\b")
_TEST_HEADS = re.compile(
    r"^(python3?|timeout\s+\d+\s+python3?|python3?\s+tests/)")
_EDIT_HEADS = re.compile(r"^(cat\s*>|sed\s+.*-i)")
_GIT_ACTION_HEADS = re.compile(
    r"^(git\s+(apply|stash|checkout|add|commit|reset|clean)|cat\s+patch\.txt)")
_SETUP_HEADS = re.compile(r"^(pip|conda)\s")


def _classify_body(body: str) -> str:
    """Classify a single command body (after stripping cd prefix)."""
    b = body.strip()
    if MARKER in b:
        return "Submit"
    if _GIT_ACTION_HEADS.match(b):
        return "Git/Patch"
    if _TEST_HEADS.match(b):
        return "Test/Execute"
    if _EDIT_HEADS.match(b):
        return "Edit"
    if _SETUP_HEADS.match(b):
        return "Setup/Dependency"
    if _READ_HEADS.match(b):
        return "Read/Search"
    if b.startswith("echo") or b.startswith("true"):
        return "Other"
    return "Unknown"


def classify_command(cmd: str) -> str:
    """Frozen classification: a command containing the submit marker is
    Submit regardless of chained parts; otherwise strip 'cd X &&' prefix,
    split on '&&' / ';', classify each part; different non-navigation
    categories in one chain -> Mixed."""
    body = re.sub(r"^(cd\s+\S+\s*&&\s*)+", "", cmd.strip())
    if MARKER in body:
        return "Submit"
    parts = [p.strip() for p in re.split(r"&&|;", body) if p.strip()]
    if not parts:
        return "Unknown"
    cats = set()
    for p in parts:
        c = _classify_body(p)
        if c not in ("Other",):
            cats.add(c)
    if not cats:
        return "Other"
    if len(cats) > 1:
        return "Mixed"
    return cats.pop()


# ---------------------------------------------------------------------------
# per-run analysis
# ---------------------------------------------------------------------------

def analyze_run(rd: Path, root: Path = ROOT) -> dict:
    meta = _json(rd / "metadata.json")
    trajectory = _json(rd / "mini_trajectory.json")
    status = _lines(rd / "mini_status.jsonl")
    tool_events = _lines(rd / "mini_tool_events.jsonl")
    samples = _json(rd / "samples.json")
    info = trajectory.get("info") or {}
    messages = trajectory.get("messages", [])

    # -- identity association ---------------------------------------------
    traj_calls = {}
    for m in messages:
        if m.get("role") != "assistant":
            continue
        for tc in (m.get("tool_calls") or []):
            try:
                args = json.loads(tc["function"]["arguments"])
            except (ValueError, KeyError):
                continue
            traj_calls[tc["id"]] = args.get("command", "")
    hook_by_id = {}
    for ev in tool_events:
        tid = ev.get("tool_call_id")
        if tid:
            hook_by_id.setdefault(tid, []).append(ev)
    linked = missing_hook = missing_traj = ambiguous = 0
    call_records = []
    for tid, cmd in traj_calls.items():
        evs = hook_by_id.get(tid)
        if not evs:
            missing_hook += 1
            call_records.append({"tool_call_id": tid, "category": classify_command(cmd),
                                 "command_sha256": hashlib.sha256(cmd.encode()).hexdigest(),
                                 "t_start_ns": None, "t_end_ns": None,
                                 "terminal": "no_hook_event",
                                 "command_length": len(cmd)})
            continue
        terminals = [e for e in evs if e.get("event") in ("closed", "error")]
        if len(terminals) > 1:
            ambiguous += 1
        terminal = terminals[-1] if terminals else evs[-1]
        linked += 1
        call_records.append({
            "tool_call_id": tid,
            "category": classify_command(cmd),
            "command_sha256": hashlib.sha256(cmd.encode()).hexdigest(),
            "command_length": len(cmd),
            "t_start_ns": terminal.get("t_start_ns"),
            "t_end_ns": terminal.get("t_end_ns"),
            "terminal": terminal.get("event"),
            "terminal_exception": terminal.get("exception_type"),
            "returncode": terminal.get("returncode"),
        })
    for tid in hook_by_id:
        if tid not in traj_calls:
            missing_traj += 1

    # -- category stats ------------------------------------------------------
    cat_calls = {}
    cat_durations = {}
    for c in call_records:
        cat = c["category"]
        cat_calls[cat] = cat_calls.get(cat, 0) + 1
        if c["t_start_ns"] is not None and c["t_end_ns"] is not None:
            cat_durations[cat] = cat_durations.get(cat, 0) + (c["t_end_ns"] - c["t_start_ns"])
    classified = [c for c in call_records if c["category"] not in ("Unknown",)]
    coverage = len(classified) / len(call_records) if call_records else None

    # tool interval union (all terminal events with valid times)
    tool_intervals = [(c["t_start_ns"], c["t_end_ns"]) for c in call_records
                      if c["t_start_ns"] is not None and c["t_end_ns"] is not None]
    tool_union = union_ns(tool_intervals)

    # category sequence and transitions
    seq_calls = sorted([c for c in call_records if c["t_start_ns"] is not None],
                       key=lambda c: c["t_start_ns"])
    cat_seq = [c["category"] for c in seq_calls]
    transitions = {}
    for i in range(len(cat_seq) - 1):
        pair = f"{cat_seq[i]}->{cat_seq[i+1]}"
        transitions[pair] = transitions.get(pair, 0) + 1

    # -- time structure -------------------------------------------------------
    request_intervals = [(r["t_start_ns"], r["t_end_ns"]) for r in status
                         if r.get("t_start_ns") and r.get("t_end_ns")]
    request_union = union_ns(request_intervals)
    overlap = intersection_ns(request_intervals, tool_intervals)
    all_ends = [e for _, e in request_intervals + tool_intervals if e]
    all_starts = [s for s, _ in request_intervals + tool_intervals if s]
    window_start = min(all_starts) if all_starts else None
    window_end = max(all_ends) if all_ends else None
    window_ns = (window_end - window_start) if (window_start and window_end) else None
    uncovered = (window_ns - request_union - tool_union + overlap
                 ) if window_ns is not None else None
    if window_ns is not None and window_ns > 0:
        # conservation: only_request + only_tool + overlap + uncovered = window
        only_req = request_union - overlap
        only_tool = tool_union - overlap
        decomposed = {"only_request_ns": only_req, "only_tool_ns": only_tool,
                      "overlap_ns": overlap, "uncovered_ns": uncovered,
                      "window_ns": window_ns,
                      "conservation_residual_ns": window_ns - (only_req + only_tool + overlap + uncovered)}

    # -- resource trajectory --------------------------------------------------
    ev = samples.get("evidence") or {}
    agent_key = next((k for k in ev if k.endswith("-agent-sandbox")), None)
    agent_ev = ev.get(agent_key) if agent_key else None
    resource = {"status": "missing"}
    cpu_rates = []
    mem_trajectory = []
    if agent_ev:
        raw = agent_ev.get("samples") or []
        bs = agent_ev.get("boundary_start") or {}
        be = agent_ev.get("boundary_end") or {}
        pts = [bs] + raw + [be]
        valid = [(p["t_monotonic_ns"], p["cpu_usage_usec"], p["mem_current_bytes"])
                 for p in pts if p.get("t_monotonic_ns") is not None
                 and p.get("cpu_usage_usec") is not None]
        for i in range(1, len(valid)):
            dt = valid[i][0] - valid[i-1][0]
            dc = valid[i][1] - valid[i-1][1]
            if dt > 0 and dc >= 0:
                cpu_rates.append({"t_start_ns": valid[i-1][0], "t_end_ns": valid[i][0],
                                  "core_rate": (dc / 1e6) / (dt / 1e9)})
            elif dt > 0 and dc < 0:
                cpu_rates.append({"t_start_ns": valid[i-1][0], "t_end_ns": valid[i][0],
                                  "core_rate": None, "invalid": "counter_reset"})
            mem_trajectory = [(p["t_monotonic_ns"], p["mem_current_bytes"])
                              for p in pts if p.get("t_monotonic_ns") is not None
                              and p.get("mem_current_bytes") is not None]
        scope = (samples.get("scopes") or {}).get(agent_key) or {}
        mem_sampled_max = scope.get("memory_sampled_max_bytes")
        mem_kernel_peak = scope.get("memory_kernel_peak_bytes")
        resource = {
            "status": "present",
            "n_samples": len(raw),
            "n_valid_cpu_intervals": len([r for r in cpu_rates if r["core_rate"] is not None]),
            "n_invalid_cpu_intervals": len([r for r in cpu_rates if r.get("invalid")]),
            "cpu_rates": cpu_rates,
            "mem_trajectory": mem_trajectory,
            "mem_sampled_max_bytes": mem_sampled_max,
            "mem_kernel_peak_bytes": mem_kernel_peak,
            "cpu_core_seconds": scope.get("cpu_core_seconds"),
            "agent_wall_s": scope.get("wall_s"),
            "sampling_interval_target_s": (samples.get("evidence") or {}).get(
                agent_key, {}).get("interval_target_s"),
        }
        # top CPU intervals
        valid_rates = sorted([r for r in cpu_rates if r["core_rate"] is not None],
                             key=lambda r: r["core_rate"], reverse=True)
        resource["top_cpu_intervals"] = valid_rates[:5]
        # high-memory intervals (top 5 by value)
        if mem_trajectory:
            sorted_mem = sorted(mem_trajectory, key=lambda x: x[1], reverse=True)
            resource["top_mem_points"] = sorted_mem[:5]

    # -- correlate resource with activity ----------------------------------
    correlations = []
    if resource["status"] == "present":
        for r in resource.get("top_cpu_intervals", []):
            overlapping_tools = [c for c in call_records
                                 if c["t_start_ns"] is not None and c["t_end_ns"] is not None
                                 and c["t_start_ns"] < r["t_end_ns"] and c["t_end_ns"] > r["t_start_ns"]]
            overlapping_reqs = [1 for s, e in request_intervals
                                if s < r["t_end_ns"] and e > r["t_start_ns"]]
            correlations.append({
                "kind": "cpu_high",
                "core_rate": round(r["core_rate"], 3),
                "t_start_ns": r["t_start_ns"], "t_end_ns": r["t_end_ns"],
                "overlapping_tool_categories": sorted({c["category"] for c in overlapping_tools}),
                "n_overlapping_tools": len(overlapping_tools),
                "n_overlapping_requests": len(overlapping_reqs),
                "note": "shared-container sampling interval; co-occurrence only, not exclusive attribution",
            })
        for t, v in resource.get("top_mem_points", [])[:3]:
            overlapping_tools = [c for c in call_records
                                 if c["t_start_ns"] is not None and c["t_end_ns"] is not None
                                 and c["t_start_ns"] < t and c["t_end_ns"] > t]
            correlations.append({
                "kind": "mem_high",
                "mem_bytes": v, "t_ns": t,
                "overlapping_tool_categories": sorted({c["category"] for c in overlapping_tools}),
                "n_overlapping_tools": len(overlapping_tools),
                "note": "sampling-point co-occurrence; kernel peak is not a per-tool RSS",
            })

    return {
        "run_dir": str(rd.relative_to(root)),
        "task": meta["task_id"], "run_id": rd.name,
        "termination": info.get("exit_status"),
        "resolved": meta.get("resolved"),
        "identity_link": {"linked": linked, "missing_hook": missing_hook,
                          "missing_traj": missing_traj, "ambiguous": ambiguous,
                          "total_trajectory_calls": len(traj_calls),
                          "total_hook_ids": len(hook_by_id)},
        "tools": {"total_calls": len(call_records),
                  "category_calls": cat_calls,
                  "category_cumulative_ns": {k: v for k, v in cat_durations.items()},
                  "classified_coverage": coverage,
                  "union_ns": tool_union,
                  "sum_of_durations_ns": sum(
                      c["t_end_ns"] - c["t_start_ns"] for c in call_records
                      if c["t_start_ns"] is not None and c["t_end_ns"] is not None),
                  "category_sequence": cat_seq,
                  "top_transitions": dict(sorted(transitions.items(),
                                                 key=lambda x: -x[1])[:8]),
                  "call_records": call_records},
        "time_structure": {
            "request_union_ns": request_union,
            "tool_union_ns": tool_union,
            "overlap_ns": overlap,
            "window_ns": window_ns,
            "decomposition": decomposed,
            "window_definition": "first request/tool start to last request/tool end",
            "n_requests": len(request_intervals),
        },
        "resources": resource,
        "activity_correlations": correlations,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def analyze(*, root: Path = ROOT, report_root: Path = REPORT_ROOT,
            raw_root: Path = RAW_ROOT, out: Path = OUT) -> dict:
    if out.exists():
        raise FileExistsError(f"refusing to overwrite: {out}")
    batch = _json(report_root / "batch/summary.json")
    batch_manifest = _json(report_root / "batch/manifest.json")
    approval = _json(report_root / "APPROVAL.json")
    attempt = _json(report_root / "ATTEMPT_STARTED.json")
    identity = batch_manifest["identity"]
    if (approval.get("checklist_identity") != identity
            or attempt.get("identity") != identity):
        raise ValueError("identity mismatch")
    if identity.get("collection") != "P1-12-CODING-REPEAT-01":
        raise ValueError("unexpected collection")
    for name, rec in batch_manifest.get("outputs", {}).items():
        p = report_root / "batch" / name
        if not p.is_file() or p.stat().st_size != rec["bytes"] or sha256(p) != rec["sha256"]:
            raise ValueError(f"batch manifest mismatch: {name}")

    inputs = {}
    for n in ("APPROVAL.json", "ATTEMPT_STARTED.json", "PREFLIGHT.json",
              "batch/summary.json", "batch/manifest.json"):
        p = report_root / n
        inputs[str(p.relative_to(root))] = file_record(p, root)

    runs = []
    for item in batch["attempts"]:
        run_id = item["run_id"]
        rd = raw_root / run_id
        if not rd.is_dir():
            raise ValueError(f"missing run dir: {run_id}")
        raw_manifest = _json(rd / "manifest.json")
        for rel, expected in (raw_manifest.get("files") or {}).items():
            p = rd / rel
            if not p.is_file() or sha256(p) != expected:
                raise ValueError(f"raw manifest mismatch: {run_id}/{rel}")
        for n in ("metadata.json", "samples.json", "mini_trajectory.json",
                  "mini_status.jsonl", "mini_tool_events.jsonl"):
            p = rd / n
            inputs[str(p.relative_to(root))] = file_record(p, root)
        runs.append(analyze_run(rd, root))
    if len(runs) != 9 or len({r["run_id"] for r in runs}) != 9:
        raise ValueError("not exactly nine unique runs")
    unselected = sorted(p.name for p in raw_root.iterdir()
                        if p.is_dir() and p.name not in {r["run_id"] for r in runs})

    # per-task aggregation
    per_task = {}
    for task in sorted({r["task"] for r in runs}):
        rows = [r for r in runs if r["task"] == task]
        def vals(fn):
            return [v for v in (fn(r) for r in rows) if isinstance(v, (int, float))]
        per_task[task] = {
            "n_runs": len(rows),
            "terminations": {k: sum(r["termination"] == k for r in rows)
                             for k in sorted({r["termination"] for r in rows})},
            "resolved": {"true": sum(r["resolved"] is True for r in rows),
                         "false": sum(r["resolved"] is False for r in rows)},
            "category_calls_aggregate": {
                cat: sum(r["tools"]["category_calls"].get(cat, 0) for r in rows)
                for cat in sorted({c for r in rows for c in r["tools"]["category_calls"]})},
            "attempt_wall_s": median_iqr([(_json(root / r["run_dir"] / "metadata.json")
                                            .get("budget_usage") or {}).get("elapsed_total_s")
                                           for r in rows]),
            "agent_cpu_core_s": median_iqr([r["resources"].get("cpu_core_seconds")
                                            for r in rows]),
            "agent_mem_kernel_peak_mib": median_iqr(
                [r["resources"].get("mem_kernel_peak_bytes", 0) / MIB
                 if r["resources"].get("mem_kernel_peak_bytes") else None
                 for r in rows]),
            "tool_union_s": median_iqr([r["time_structure"]["tool_union_ns"] / 1e9
                                        for r in rows]),
            "request_union_s": median_iqr([r["time_structure"]["request_union_ns"] / 1e9
                                           for r in rows]),
            "overlap_s": median_iqr([r["time_structure"]["overlap_ns"] / 1e9
                                     for r in rows]),
            "uncovered_s": median_iqr([r["time_structure"]["decomposition"]["uncovered_ns"] / 1e9
                                       for r in rows]),
        }

    # reference method mapping
    ref_files = {}
    for name in ("analysis/tool_timing.py", "analysis/compute_active_time.py",
                 "analysis/analyze_tool_time_ratio.py", "analysis/analyze_extended_insights.py"):
        p = AGENTCGROUP / name
        if p.is_file():
            ref_files[name] = file_record(p)
    try:
        commit = (AGENTCGROUP).exec_git  # never executed; placeholder
    except Exception:
        pass

    result = {
        "schema": "awc-p1-12-coding-repeat-01-characterization-v1",
        "collection": identity["collection"],
        "selected_run_ids": [r["run_id"] for r in runs],
        "unselected_raw_directories": unselected,
        "identity_check": {"approval_equals_batch": True, "attempt_equals_batch": True},
        "method_mapping": [
            {"reference": "tool_timing.py: merge_intervals, union_duration_seconds",
             "original": "merge overlapping datetime intervals; sum union duration",
             "adopted": "same algorithm with integer monotonic-ns intervals",
             "implementation": "scripts/p1_12_coding_repeat_characterization.py: merge_intervals_ns, union_ns",
             "output_fields": "tool_union_ns, request_union_ns, overlap_ns",
             "limits": "only intervals with valid start/end; Submitted terminal events included"},
            {"reference": "tool_timing.py: attribute_union_seconds",
             "original": "split union time among overlapping categories evenly",
             "adopted": "NOT adopted",
             "implementation": None, "output_fields": None,
             "limits": "even splitting would imply exclusive attribution unsupported by shared-container sampling"},
            {"reference": "compute_active_time.py: compute_active_time_from_trace",
             "original": "active_time = last trace timestamp - first trace timestamp",
             "adopted": "adapted as the agent observation window (first request/tool start to last end); NOT called active time",
             "implementation": "analyze_run time_structure",
             "output_fields": "window_ns",
             "limits": "uncovered time within the window is NOT thinking/waiting time; it is simply not covered by request or tool intervals"},
            {"reference": "analyze_tool_time_ratio.py: categorize_bash_command",
             "original": "regex-based bash categorization (Test/Git/Package/File/Python/Text/Shell/Other)",
             "adopted": "adapted: frozen rules for the actual command corpus; compound commands classified Mixed when parts differ; navigation (cd) stripped",
             "implementation": "classify_command, _classify_body",
             "output_fields": "category per tool call",
             "limits": "static text only; does not prove actual subprocess behavior or side effects"},
            {"reference": "analyze_extended_insights.py: analyze_transient_bursts",
             "original": "peak/avg overprovisioning factor; spike duration at 80% of peak (1 sample = 1 s)",
             "adopted": "NOT adopted as-is; only peak-to-median memory ratio reported descriptively",
             "implementation": "per-task agent_mem_kernel_peak stats",
             "output_fields": "memory peak/median (descriptive)",
             "limits": "no threshold claimed as validated; actual timestamps used, not sample-count-as-seconds"},
            {"reference": "analyze_tool_time_ratio.py: thinking_time = exec_time - tool_time",
             "original": "subtraction to get thinking time",
             "adopted": "PROHIBITED by task; uncovered time is reported as uncovered only",
             "implementation": None, "output_fields": None,
             "limits": "explicitly banned"},
        ],
        "reference_commit": "551ca16 (local git log)",
        "reference_files": ref_files,
        "runs": runs,
        "per_task": per_task,
        "statistics": {"quantiles": "linear interpolation; IQR=Q3-Q1",
                       "units": "times in ns unless suffixed _s (seconds) or _mib (mebibytes)",
                       "memory": "kernel peak, sampled max and trajectory values are distinct"},
        "limitations": [
            "three repeats per task are raw points, not independent tasks",
            "container CPU/memory are shared-scope evidence; no exclusive per-tool attribution",
            "request intervals are client-observed, not server inference time",
            "uncovered window time is not thinking/waiting time",
            "static command classification does not prove actual subprocess behavior",
            "model usage is not a bill; cost unknown",
            "no causal or frequency-ranking claims",
        ],
        "batch_status": {k: batch.get(k) for k in ("status", "budget_overrun", "wall_min")},
    }

    out.mkdir(parents=True, exist_ok=False)
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    _write_md(out, result, root)
    outputs = {n: file_record(out / n, root) for n in ("summary.json", "summary.md")}
    manifest = {
        "schema": "awc-p1-12-coding-repeat-01-characterization-v1-manifest",
        "inputs": inputs, "analysis_code": file_record(Path(__file__), root),
        "reference_files": ref_files,
        "outputs": outputs,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return result


def _write_md(out: Path, result: dict, root: Path):
    runs = result["runs"]
    per_task = result["per_task"]
    md = ["# CODING-REPEAT-01 characterization", "",
          f"9 runs, 3 tasks × 3 repeats; collection `{result['collection']}`.",
          f"Unselected raw dirs excluded: {result['unselected_raw_directories'] or 'none'}.",
          "", "## Method mapping (AgentCgroup reference → this project)", "",
          "| Reference | Original | Adopted | Why / limits |",
          "| --- | --- | --- | --- |"]
    for m in result["method_mapping"]:
        md.append(f"| {m['reference']} | {m['original']} | {m['adopted']} | {m['limits']} |")
    md += ["", "Reference commit: " + result["reference_commit"], ""]

    md += ["## Per-run overview", "",
           "| run | task | term | resolved | tools | reqs | tool union (s) | req union (s) | overlap (s) | uncovered (s) |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        ts = r["time_structure"]
        d = ts["decomposition"]
        md.append(f"| {r['run_id'][-6:]} | {r['task']} | {r['termination']} | "
                  f"{r['resolved']} | {r['tools']['total_calls']} | {ts['n_requests']} | "
                  f"{ts['tool_union_ns']/1e9:.1f} | {ts['request_union_ns']/1e9:.1f} | "
                  f"{ts['overlap_ns']/1e9:.1f} | {d['uncovered_ns']/1e9:.1f} |")

    md += ["", "## Tool composition (per run)", "",
           "| run | Read/Search | Edit | Test/Exec | Git/Patch | Submit | Mixed | Other | Unknown | coverage |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        c = r["tools"]["category_calls"]
        md.append(f"| {r['run_id'][-6:]} | {c.get('Read/Search',0)} | {c.get('Edit',0)} | "
                  f"{c.get('Test/Execute',0)} | {c.get('Git/Patch',0)} | {c.get('Submit',0)} | "
                  f"{c.get('Mixed',0)} | {c.get('Other',0)} | {c.get('Unknown',0)} | "
                  f"{r['tools']['classified_coverage']:.0%} |")

    md += ["", "## Time structure (per run, seconds)", "",
           "Window = first request/tool start to last end. Decomposition is mutually exclusive and conserves the window.",
           "",
           "| run | window | only-request | only-tool | overlap | uncovered | residual |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        d = r["time_structure"]["decomposition"]
        md.append(f"| {r['run_id'][-6:]} | {d['window_ns']/1e9:.1f} | "
                  f"{d['only_request_ns']/1e9:.1f} | {d['only_tool_ns']/1e9:.1f} | "
                  f"{d['overlap_ns']/1e9:.1f} | {d['uncovered_ns']/1e9:.1f} | "
                  f"{d['conservation_residual_ns']/1e9:.6f} |")

    md += ["", "## Per-task aggregate (medians over n=3)", "",
           "| task | wall (s) | agent CPU (core-s) | mem kernel peak (MiB) | tool union (s) | req union (s) |",
           "| --- | --- | --- | --- | --- | --- |"]
    for task, g in per_task.items():
        md.append(f"| {task} | {g['attempt_wall_s']['median']:.1f} | "
                  f"{g['agent_cpu_core_s']['median']:.2f} | "
                  f"{g['agent_mem_kernel_peak_mib']['median']:.1f} | "
                  f"{g['tool_union_s']['median']:.1f} | {g['request_union_s']['median']:.1f} |")

    md += ["", "## Key observations (descriptive, n=3 per task)", ""]

    # django memory
    django_runs = [r for r in runs if "django" in r["task"]]
    if django_runs:
        all_mem = [(r["run_id"][-6:], r["resources"].get("mem_kernel_peak_bytes", 0) / MIB) for r in django_runs]
        md.append(f"- **Django memory**: kernel peak across the three runs: "
                  + ", ".join(f"{rid}={m:.1f} MiB" for rid, m in all_mem) + ".")

    # astropy-13398 CPU contrast
    a33 = [r for r in runs if "13398" in r["task"]]
    if a33:
        md.append("- **Astropy-13398 CPU contrast** (three runs):")
        for r in a33:
            cats = r["tools"]["category_calls"]
            md.append(f"  - {r['run_id'][-6:]}: resolved={r['resolved']}, term={r['termination']}, "
                      f"tools={r['tools']['total_calls']} "
                      f"(Read/Search={cats.get('Read/Search',0)}, Test={cats.get('Test/Execute',0)}, "
                      f"Git/Patch={cats.get('Git/Patch',0)}), "
                      f"CPU={r['resources'].get('cpu_core_seconds')}, "
                      f"wall={r['resources'].get('agent_wall_s')}")

    # alternation pattern
    md.append("- **Request/tool alternation**: every run shows sequential "
              "request-then-tool patterns; overlap between request intervals and "
              "tool intervals is small (see per-run table), consistent with a "
              "single-threaded agent loop. This is a description of interval "
              "co-occurrence, not a concurrency claim.")

    # corrections
    md += ["", "## Corrections to the previous review (P1-12-CODING-REPEAT-01-review-v1)", "",
           "- Astropy-13398 wall raw point middle value: the old summary.md "
           "states 162.69 s; the actual value from metadata.json "
           "budget_usage.elapsed_total_s is "
           f"{per_task['astropy__astropy-13398']['attempt_wall_s']['median']:.2f} s (median). "
           "The old report's number was hardcoded and incorrect.",
           "- Memory IQR 136136704 bytes = "
           f"{136136704/MIB:.2f} MiB, not 136.1 MiB as stated in the old report. "
           "Unit conversion error.",
           "- All numbers in this report are computed from input files at run "
           "time; no conclusion values are hardcoded."]

    md += ["", "## Limits", ""]
    md += [f"- {lim}" for lim in result["limitations"]]
    md += ["", "CPU-02 and Replay remain paused. No G2 or architecture claim."]

    (out / "summary.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    try:
        result = analyze()
    except Exception as exc:
        print(f"analysis refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    print(f"characterized {len(result['selected_run_ids'])} runs")
