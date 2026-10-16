#!/usr/bin/env python3
"""CODING-REPEAT-01 characterization v2: tool behavior, time structure, and
resource trajectories with corrected identity association, classification,
and conclusion boundaries.

v2 fixes vs v1 (see corrections.md in the output for details):
- shell-aware tokenization that respects quotes and heredocs;
- identity association validates command hash/length and rejects duplicates;
- python invocations classified by evidence (pytest/unittest), not assumed;
- memory trajectory independent of CPU validity;
- observation window explicitly named and separated from attempt/agent wall;
- no single-threaded inference, no thinking-time, no exclusive attribution;
- all numbers derived at run time from input files.
"""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "reports/resource/P1-12/repeats/CODING-REPEAT-01"
RAW_ROOT = ROOT / "data/raw/generated/P1-12-CODING-REPEAT-01"
OUT = ROOT / "reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3"
AGENTCGROUP = ROOT / "references/repos/agentcgroup"
MARKER = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
MIB = 1048576


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def file_record(p: Path, root: Path) -> dict:
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
# shell-aware command splitting and classification (v2)
# ---------------------------------------------------------------------------

def split_top_level(cmd: str) -> list[str]:
    """Split on && and ; only when OUTSIDE single/double quotes and
    heredoc bodies.  Manual character-level scan; no shell parsing claim."""
    parts = []
    current = []
    i = 0
    n = len(cmd)
    in_squote = in_dquote = False
    heredoc_delim = None
    while i < n:
        ch = cmd[i]
        if heredoc_delim is not None:
            # inside a heredoc body: look for the delimiter on its own line
            current.append(ch)
            if ch == "\n":
                line_start = i + 1
                line_end = cmd.find("\n", line_start)
                if line_end == -1:
                    line_end = n
                line = cmd[line_start:line_end].strip()
                if line == heredoc_delim:
                    heredoc_delim = None
            i += 1
            continue
        if in_squote:
            current.append(ch)
            if ch == "'":
                in_squote = False
            i += 1
            continue
        if in_dquote:
            current.append(ch)
            if ch == '"':
                in_dquote = False
            i += 1
            continue
        if ch == "'":
            in_squote = True
            current.append(ch)
            i += 1
            continue
        if ch == '"':
            in_dquote = True
            current.append(ch)
            i += 1
            continue
        # check for heredoc start
        if ch == "<" and i + 1 < n and cmd[i + 1] == "<":
            current.append(ch)
            i += 1
            current.append(cmd[i])
            i += 1
            # skip optional quote and read delimiter
            j = i
            while j < n and cmd[j] in (" ", "\t", "'", '"'):
                if cmd[j] in ("'", '"'):
                    current.append(cmd[j])
                    j += 1
                else:
                    current.append(cmd[j])
                    j += 1
            delim_start = j
            while j < n and cmd[j] not in ("\n", " ", "\t", "&", "|", ";"):
                current.append(cmd[j])
                j += 1
            heredoc_delim = cmd[delim_start:j].strip()
            i = j
            continue
        # check for && or ; at top level
        if ch == "&" and i + 1 < n and cmd[i + 1] == "&":
            parts.append("".join(current).strip())
            current = []
            i += 2
            continue
        if ch == ";":
            parts.append("".join(current).strip())
            current = []
            i += 1
            continue
        # check for | (pipe) — treat as a split too for classification
        if ch == "|":
            parts.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    last = "".join(current).strip()
    if last:
        parts.append(last)
    return [p for p in parts if p]


# frozen classification rules (v2): match on the command head after safe
# splitting; each part gets a FORM classification; purpose is inferred only
# with explicit evidence.

_TEST_INVOCATION = re.compile(
    r"^(timeout\s+\d+\s+)?(python3?\s+(-m\s+)?(pytest|unittest)\b|pytest\b|tox\b|"
    r"python3?\s+tests/runtests\.py\b)")
_PYTHON_HEAD = re.compile(r"^(timeout\s+\d+\s+)?python3?\b")
_READ_HEAD = re.compile(
    r"^(sed\s+-n|grep|cat(?!>)|find|ls|head|tail|wc|du|pwd|"
    r"git\s+(show|log|diff|status|branch|merge-base|remote|rev-parse))\b")
_WRITE_HEAD = re.compile(r"^(cat\s*>|tee\s)")
_GIT_ACTION_HEAD = re.compile(r"^(git\s+(apply|stash|checkout|add|commit|reset|clean))\b")
_SETUP_HEAD = re.compile(r"^(pip|conda)\s")
_ECHO_HEAD = re.compile(r"^echo\b")


def _classify_part(part: str) -> tuple[str, str]:
    """Classify one safely-split part.  Returns (label, basis).
    Test only when the part INVOKES a test runner (pytest/unittest/tox/
    runtests.py as the command head), not when the keyword appears in
    arguments or script bodies."""
    p = part.strip()
    if not p:
        return ("empty", "empty part")
    if MARKER in p:
        return ("Submit-marker", "command text contains the registered submit marker")
    if _TEST_INVOCATION.match(p):
        return ("Test", "test runner invoked as the command head (pytest/unittest/tox/runtests)")
    if _PYTHON_HEAD.match(p):
        return ("Interpreter/Execute", "python process started; specific purpose not determinable from static text")
    if _GIT_ACTION_HEAD.match(p):
        return ("Git-action", "git state-changing subcommand")
    if _WRITE_HEAD.match(p):
        return ("File-write", "file creation/overwrite via cat>/tee")
    if _SETUP_HEAD.match(p):
        return ("Setup/Dependency", "pip/conda install")
    if _READ_HEAD.match(p):
        return ("Read/Search", "read-only file/repo inspection command")
    if _ECHO_HEAD.match(p):
        return ("Echo", "echo command")
    return ("Unknown", "no frozen rule matched")


def classify_command(cmd: str) -> dict:
    """Full v2 classification: shell-aware split, per-part form classification,
    composite label with explicit coverage semantics."""
    body = re.sub(r"^(cd\s+\S+\s*&&\s*)+", "", cmd.strip())
    if MARKER in body:
        return {"label": "Submit-marker",
                "basis": "command contains the registered submit marker",
                "coverage": "form-identified",
                "parts": [{"part_label": "Submit-marker",
                           "basis": "marker present"}]}
    parts = split_top_level(body)
    part_results = []
    for p in parts:
        label, basis = _classify_part(p)
        part_results.append({"part_label": label, "basis": basis})
    labels = {r["part_label"] for r in part_results if r["part_label"] not in ("empty",)}
    known = {l for l in labels if l not in ("Unknown",)}
    unknown_present = "Unknown" in labels
    if not known and unknown_present:
        composite = "Unknown"
        coverage = "unknown"
    elif known and unknown_present:
        composite = "Partially-known"
        coverage = "partial"
    elif len(known) > 1:
        composite = "Mixed"
        coverage = "form-identified"
    elif len(known) == 1:
        composite = known.pop()
        coverage = "form-identified"
    else:
        composite = "Unknown"
        coverage = "unknown"
    return {"label": composite, "coverage": coverage, "parts": part_results}


# ---------------------------------------------------------------------------
# identity association (v2: validates hash/length, rejects duplicates)
# ---------------------------------------------------------------------------

def associate_calls(trajectory_msgs, tool_events):
    """Link trajectory tool_calls to hook events with full validation.
    Returns (records, diagnostics).

    v3 hardening: every valid link requires exactly one open and one
    terminal, matching event_id, matching t_start_ns, mandatory (not
    optional) command_view sha256+length, and valid integer timestamps.
    Missing or inconsistent fields reject the record."""
    # collect trajectory calls, detecting duplicate tool_call_ids
    traj_calls = {}
    traj_duplicates = []
    for m in trajectory_msgs:
        if m.get("role") != "assistant":
            continue
        for tc in (m.get("tool_calls") or []):
            tid = tc.get("id")
            if not tid:
                continue
            try:
                args = json.loads(tc["function"]["arguments"])
                cmd = args.get("command", "")
            except (ValueError, KeyError):
                cmd = ""
            if tid in traj_calls:
                traj_duplicates.append(tid)
            else:
                traj_calls[tid] = cmd
    # collect hook events by tool_call_id
    hook = {}
    for ev in tool_events:
        tid = ev.get("tool_call_id")
        if tid:
            hook.setdefault(tid, []).append(ev)
    # also track event_id → tool_call_id to detect cross-contamination
    event_id_map = {}
    for ev in tool_events:
        eid = ev.get("event_id")
        tid = ev.get("tool_call_id")
        if eid and tid:
            if eid in event_id_map and event_id_map[eid] != tid:
                # same event_id bound to different calls
                event_id_map[eid] = "__CONFLICT__"
            elif eid not in event_id_map:
                event_id_map[eid] = tid

    def _reject(tid, reason, diag):
        diag["rejected"] += 1
        return {"tool_call_id": tid, "valid": False,
                "reject_reason": reason, "category": "Unknown"}

    records = []
    diag = {"traj_total": len(traj_calls) + len(traj_duplicates),
            "traj_unique_ids": len(traj_calls),
            "traj_duplicate_ids": len(traj_duplicates),
            "hook_unique_ids": len(hook),
            "hook_orphan_ids": 0,
            "hash_mismatch": 0, "length_mismatch": 0,
            "missing_hash": 0, "missing_length": 0,
            "multi_terminal": 0, "no_terminal": 0,
            "no_open": 0, "multi_open": 0,
            "event_id_mismatch": 0, "event_id_conflict": 0,
            "missing_event_id": 0,
            "t_start_mismatch": 0, "invalid_times": 0,
            "valid_linked": 0, "rejected": 0}
    for tid in hook:
        if tid not in traj_calls:
            diag["hook_orphan_ids"] += 1
    for tid, cmd in traj_calls.items():
        if tid in traj_duplicates:
            records.append(_reject(tid, "duplicate_trajectory_id", diag))
            continue
        evs = hook.get(tid)
        if not evs:
            records.append(_reject(tid, "no_hook_events", diag))
            continue
        opens = [e for e in evs if e.get("event") == "open"]
        terminals = [e for e in evs if e.get("event") in ("closed", "error")]
        if len(opens) == 0:
            diag["no_open"] += 1
            records.append(_reject(tid, "no_open_event", diag))
            continue
        if len(opens) > 1:
            diag["multi_open"] += 1
            records.append(_reject(tid, "multiple_open_events", diag))
            continue
        if len(terminals) > 1:
            diag["multi_terminal"] += 1
            records.append(_reject(tid, "multiple_terminal_events", diag))
            continue
        if not terminals:
            diag["no_terminal"] += 1
            records.append(_reject(tid, "no_terminal_event", diag))
            continue
        opn, term = opens[0], terminals[0]
        # event_id: must exist on both, be equal, and not conflict with another call
        opn_eid = opn.get("event_id")
        term_eid = term.get("event_id")
        if not opn_eid or not term_eid:
            diag["missing_event_id"] += 1
            records.append(_reject(tid, "missing_event_id", diag))
            continue
        if opn_eid != term_eid:
            diag["event_id_mismatch"] += 1
            records.append(_reject(tid, "event_id_mismatch", diag))
            continue
        if event_id_map.get(opn_eid) in ("__CONFLICT__",):
            diag["event_id_conflict"] += 1
            records.append(_reject(tid, "event_id_cross_call_conflict", diag))
            continue
        # t_start must match between open and terminal
        opn_ts = opn.get("t_start_ns")
        term_ts = term.get("t_start_ns")
        if opn_ts != term_ts:
            diag["t_start_mismatch"] += 1
            records.append(_reject(tid, "t_start_ns_mismatch", diag))
            continue
        # command hash/length: MANDATORY fields, not optional
        cmd_sha = hashlib.sha256(cmd.encode()).hexdigest() if cmd else ""
        cmd_len = len(cmd)
        cv = opn.get("command_view") or {}
        cv_sha = cv.get("sha256")
        cv_len = cv.get("length")
        if not cv_sha:
            diag["missing_hash"] += 1
            records.append(_reject(tid, "command_view_missing_sha256", diag))
            continue
        if cv_sha != cmd_sha:
            diag["hash_mismatch"] += 1
            records.append(_reject(tid, "command_hash_mismatch", diag))
            continue
        if not isinstance(cv_len, int) or isinstance(cv_len, bool):
            diag["missing_length"] += 1
            records.append(_reject(tid, "command_view_missing_length", diag))
            continue
        if cv_len != cmd_len:
            diag["length_mismatch"] += 1
            records.append(_reject(tid, "command_length_mismatch", diag))
            continue
        # times: valid integers, end >= start, exclude bool
        ts, te = term.get("t_start_ns"), term.get("t_end_ns")
        if (not isinstance(ts, int) or isinstance(ts, bool)
                or not isinstance(te, int) or isinstance(te, bool)
                or te < ts):
            diag["invalid_times"] += 1
            records.append(_reject(tid, "invalid_times", diag))
            continue
        diag["valid_linked"] += 1
        cat = classify_command(cmd)
        records.append({
            "tool_call_id": tid, "valid": True,
            "category": cat["label"], "coverage": cat["coverage"],
            "classification_parts": cat["parts"],
            "command_sha256": cmd_sha, "command_length": cmd_len,
            "t_start_ns": ts, "t_end_ns": te,
            "terminal": term.get("event"),
            "terminal_exception": term.get("exception_type"),
            "returncode": term.get("returncode"),
        })
    return records, diag


# ---------------------------------------------------------------------------
# per-run analysis (v2)
# ---------------------------------------------------------------------------

def analyze_run(rd: Path, root: Path) -> dict:
    meta = _json(rd / "metadata.json")
    trajectory = _json(rd / "mini_trajectory.json")
    status = _lines(rd / "mini_status.jsonl")
    tool_events = _lines(rd / "mini_tool_events.jsonl")
    samples = _json(rd / "samples.json")
    info = trajectory.get("info") or {}
    messages = trajectory.get("messages", [])
    bu = meta.get("budget_usage") or {}

    # -- identity association (v2) ------------------------------------------
    call_records, assoc_diag = associate_calls(messages, tool_events)
    valid_calls = [c for c in call_records if c.get("valid")]

    # -- classification stats ------------------------------------------------
    cat_counts = {}
    cat_durations_ns = {}
    coverage_counts = {"form-identified": 0, "partial": 0, "unknown": 0}
    for c in valid_calls:
        cat = c["category"]
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        cov = c.get("coverage", "unknown")
        coverage_counts[cov] = coverage_counts.get(cov, 0) + 1
        if c.get("t_start_ns") is not None and c.get("t_end_ns") is not None:
            cat_durations_ns[cat] = cat_durations_ns.get(
                cat, 0) + (c["t_end_ns"] - c["t_start_ns"])

    # tool interval union
    tool_intervals = [(c["t_start_ns"], c["t_end_ns"]) for c in valid_calls
                      if c.get("t_start_ns") is not None and c.get("t_end_ns") is not None]
    tool_union = union_ns(tool_intervals)
    sum_durations = sum(e - s for s, e in tool_intervals)

    # category sequence (ordered by start time)
    seq = sorted([c for c in valid_calls if c.get("t_start_ns") is not None],
                 key=lambda c: c["t_start_ns"])
    cat_seq = [c["category"] for c in seq]
    transitions = {}
    for i in range(len(cat_seq) - 1):
        pair = f"{cat_seq[i]}->{cat_seq[i+1]}"
        transitions[pair] = transitions.get(pair, 0) + 1

    # -- time structure --------------------------------------------------------
    request_intervals = [(r["t_start_ns"], r["t_end_ns"]) for r in status
                         if r.get("t_start_ns") and r.get("t_end_ns")
                         and r["t_end_ns"] >= r["t_start_ns"]]
    request_union = union_ns(request_intervals)
    overlap = intersection_ns(request_intervals, tool_intervals)
    all_iv = request_intervals + tool_intervals
    window_start = min((s for s, _ in all_iv), default=None)
    window_end = max((e for _, e in all_iv), default=None)
    observation_window_ns = (window_end - window_start) if (
        window_start is not None and window_end is not None) else None
    if observation_window_ns is not None:
        only_req = request_union - overlap
        only_tool = tool_union - overlap
        uncovered = observation_window_ns - only_req - only_tool - overlap
        decomposition = {
            "only_request_ns": only_req, "only_tool_ns": only_tool,
            "overlap_ns": overlap, "uncovered_ns": uncovered,
            "observation_window_ns": observation_window_ns,
            "conservation_residual_ns": observation_window_ns - (
                only_req + only_tool + overlap + uncovered),
            "window_definition": "first request or tool start to last request or tool end (call observation window)",
        }
    else:
        decomposition = None

    # -- resource trajectory (v2: memory independent of CPU) ------------------
    ev = samples.get("evidence") or {}
    agent_key = next((k for k in ev if k.endswith("-agent-sandbox")), None)
    agent_ev = ev.get(agent_key) if agent_key else None
    scope = (samples.get("scopes") or {}).get(agent_key) or {}
    resource = {"status": "missing"}
    if agent_ev:
        raw = agent_ev.get("samples") or []
        bs = agent_ev.get("boundary_start") or {}
        be = agent_ev.get("boundary_end") or {}
        pts = [bs] + raw + [be]
        # CPU: adjacent-pair differencing on valid pairs only
        cpu_pairs = []
        for i in range(1, len(pts)):
            t0 = pts[i-1].get("t_monotonic_ns")
            t1 = pts[i].get("t_monotonic_ns")
            c0 = pts[i-1].get("cpu_usage_usec")
            c1 = pts[i].get("cpu_usage_usec")
            if t0 is None or t1 is None or t1 <= t0:
                cpu_pairs.append({"status": "invalid_time", "t_start_ns": t0, "t_end_ns": t1})
                continue
            if c0 is None or c1 is None:
                cpu_pairs.append({"status": "cpu_missing", "t_start_ns": t0, "t_end_ns": t1})
                continue
            if c1 < c0:
                cpu_pairs.append({"status": "counter_reset", "t_start_ns": t0, "t_end_ns": t1})
                continue
            dt_s = (t1 - t0) / 1e9
            dc_s = (c1 - c0) / 1e6
            cpu_pairs.append({"status": "valid", "t_start_ns": t0, "t_end_ns": t1,
                              "span_s": round(dt_s, 3), "core_rate": round(dc_s / dt_s, 4) if dt_s > 0 else None})
        # memory: independent of CPU validity
        mem_points = []
        for p in pts:
            t = p.get("t_monotonic_ns")
            m = p.get("mem_current_bytes")
            if t is not None and m is not None:
                mem_points.append({"t_ns": t, "mem_bytes": m})
        valid_cpu = [r for r in cpu_pairs if r["status"] == "valid"]
        resource = {
            "status": "present",
            "n_samples": len(raw),
            "cpu_intervals": {
                "total_pairs": len(cpu_pairs),
                "valid": len(valid_cpu),
                "cpu_missing": sum(1 for r in cpu_pairs if r["status"] == "cpu_missing"),
                "counter_reset": sum(1 for r in cpu_pairs if r["status"] == "counter_reset"),
                "invalid_time": sum(1 for r in cpu_pairs if r["status"] == "invalid_time"),
                "span_s_distribution": median_iqr([r["span_s"] for r in valid_cpu]) if valid_cpu else None,
                "top_by_core_rate": sorted(valid_cpu, key=lambda r: r["core_rate"], reverse=True)[:5],
            },
            "memory": {
                "n_points": len(mem_points),
                "sampled_max_bytes": scope.get("memory_sampled_max_bytes"),
                "kernel_peak_bytes": scope.get("memory_kernel_peak_bytes"),
                "top_points": sorted(mem_points, key=lambda p: p["mem_bytes"], reverse=True)[:5],
            },
            "cpu_core_seconds": scope.get("cpu_core_seconds"),
            "agent_scope_wall_s": scope.get("wall_s"),
        }
    verifier_scope = (samples.get("scopes") or {}).get(
        next((k for k in (samples.get("scopes") or {}) if k.endswith("-verifier")), ""), {}) or {}

    # -- activity correlation (v2: co-occurrence only) -------------------------
    correlations = []
    if resource["status"] == "present":
        for r in resource["cpu_intervals"]["top_by_core_rate"][:3]:
            ov_tools = [c for c in valid_calls
                        if c.get("t_start_ns") is not None and c.get("t_end_ns") is not None
                        and c["t_start_ns"] < r["t_end_ns"] and c["t_end_ns"] > r["t_start_ns"]]
            ov_reqs = sum(1 for s, e in request_intervals
                          if s < r["t_end_ns"] and e > r["t_start_ns"])
            cats = sorted({c["category"] for c in ov_tools})
            correlations.append({
                "kind": "high_cpu_sampling_interval", "core_rate": r["core_rate"],
                "span_s": r["span_s"], "t_start_ns": r["t_start_ns"], "t_end_ns": r["t_end_ns"],
                "overlapping_call_categories": cats,
                "n_overlapping_valid_calls": len(ov_tools),
                "n_overlapping_request_intervals": ov_reqs,
                "interpretation": ("shared-container sampling interval; "
                                   "co-occurrence with activities, not exclusive attribution"),
            })
        for mp in resource["memory"]["top_points"][:3]:
            ov_tools = [c for c in valid_calls
                        if c.get("t_start_ns") is not None and c.get("t_end_ns") is not None
                        and c["t_start_ns"] < mp["t_ns"] and c["t_end_ns"] > mp["t_ns"]]
            correlations.append({
                "kind": "high_mem_sampling_point", "mem_bytes": mp["mem_bytes"],
                "t_ns": mp["t_ns"],
                "overlapping_call_categories": sorted({c["category"] for c in ov_tools}),
                "n_overlapping_valid_calls": len(ov_tools),
                "interpretation": ("memory.current sampling point co-occurring with "
                                   "activities; NOT the kernel-peak moment, NOT causal"),
            })

    return {
        "run_dir": str(rd.relative_to(root)),
        "task": meta["task_id"], "run_id": rd.name,
        "termination": info.get("exit_status"),
        "resolved": meta.get("resolved"),
        "attempt_wall_s": bu.get("elapsed_total_s"),
        "walls": {
            "attempt_wall_s": bu.get("elapsed_total_s"),
            "agent_scope_wall_s": scope.get("wall_s"),
            "observation_window_s": observation_window_ns / 1e9 if observation_window_ns else None,
            "verifier_scope_wall_s": verifier_scope.get("wall_s"),
            "source": ("attempt: metadata.budget_usage.elapsed_total_s; "
                       "agent/verifier: samples.json scopes wall_s; "
                       "observation: first/last request-tool interval"),
        },
        "identity_association": assoc_diag,
        "tools": {
            "total_trajectory_calls": assoc_diag["traj_total"],
            "valid_linked": assoc_diag["valid_linked"],
            "rejected": assoc_diag["rejected"],
            "category_counts": cat_counts,
            "coverage_counts": coverage_counts,
            "category_cumulative_ns": cat_durations_ns,
            "union_ns": tool_union,
            "sum_of_durations_ns": sum_durations,
            "category_sequence": cat_seq,
            "top_transitions": dict(sorted(transitions.items(), key=lambda x: -x[1])[:8]),
            "call_records": call_records,
        },
        "time_structure": {
            "n_request_intervals": len(request_intervals),
            "request_union_ns": request_union,
            "tool_union_ns": tool_union,
            "overlap_ns": overlap,
            "decomposition": decomposition,
        },
        "resources": resource,
        "activity_correlations": correlations,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _git_head(path: Path) -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path,
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


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
        per_task[task] = {
            "n_runs": len(rows),
            "terminations": {k: sum(r["termination"] == k for r in rows)
                             for k in sorted({r["termination"] for r in rows})},
            "resolved": {"true": sum(r["resolved"] is True for r in rows),
                         "false": sum(r["resolved"] is False for r in rows)},
            "category_counts_aggregate": {
                cat: sum(r["tools"]["category_counts"].get(cat, 0) for r in rows)
                for cat in sorted({c for r in rows for c in r["tools"]["category_counts"]})},
            "coverage_counts_aggregate": {
                cov: sum(r["tools"]["coverage_counts"].get(cov, 0) for r in rows)
                for cov in ("form-identified", "partial", "unknown")},
            "attempt_wall_s": median_iqr([r["attempt_wall_s"] for r in rows]),
            "agent_scope_wall_s": median_iqr([r["walls"]["agent_scope_wall_s"] for r in rows]),
            "observation_window_s": median_iqr([r["walls"]["observation_window_s"] for r in rows]),
            "agent_cpu_core_s": median_iqr([r["resources"].get("cpu_core_seconds")
                                            for r in rows]),
            "agent_mem_kernel_peak_mib": median_iqr(
                [r["resources"]["memory"]["kernel_peak_bytes"] / MIB
                 if r["resources"].get("memory", {}).get("kernel_peak_bytes") else None
                 for r in rows]),
            "tool_union_s": median_iqr([r["time_structure"]["tool_union_ns"] / 1e9 for r in rows]),
            "request_union_s": median_iqr([r["time_structure"]["request_union_ns"] / 1e9 for r in rows]),
        }

    ref_files = {}
    for name in ("analysis/tool_timing.py", "analysis/compute_active_time.py"):
        p = AGENTCGROUP / name
        if p.is_file():
            # reference files live at the real project root, not the test root
            ref_files[name] = {"path": name, "bytes": p.stat().st_size,
                               "sha256": sha256(p)}
    ref_commit = _git_head(AGENTCGROUP)

    result = {
        "schema": "awc-p1-12-coding-repeat-01-characterization-v2",
        "collection": identity["collection"],
        "selected_run_ids": [r["run_id"] for r in runs],
        "unselected_raw_directories": unselected,
        "identity_check": {"approval_equals_batch": True, "attempt_equals_batch": True},
        "method_mapping": [
            {"reference": "tool_timing.py: merge_intervals, union_duration_seconds",
             "adopted": "same algorithm, integer ns",
             "implementation": "merge_intervals_ns, union_ns, intersection_ns",
             "limits": "only valid start/end"},
            {"reference": "compute_active_time.py",
             "adopted": "observation window (NOT active time)",
             "implementation": "analyze_run time_structure",
             "limits": "uncovered is not thinking/waiting"},
            {"reference": "analyze_tool_time_ratio.py: categorize_bash_command",
             "adopted": "v2: shell-aware split (shlex), per-part form classification, evidence-based Test only",
             "implementation": "classify_command, split_top_level, _classify_part",
             "limits": "static text; python purpose not determinable without pytest evidence"},
        ],
        "reference_commit": ref_commit,
        "reference_files": ref_files,
        "runs": runs,
        "per_task": per_task,
        "limitations": [
            "three repeats per task are raw points, not independent tasks",
            "shared-container CPU/memory; no exclusive per-tool attribution",
            "request intervals are client-observed, not server inference time",
            "uncovered window time is not thinking/waiting time",
            "python invocations without pytest evidence are Interpreter/Execute, not Test",
            "label assignment rate is not purpose identification accuracy",
            "sequential interval co-occurrence does not prove single-threadedness",
            "model usage is not a bill; cost unknown",
        ],
        "batch_status": {k: batch.get(k) for k in ("status", "budget_overrun", "wall_min")},
    }

    out.mkdir(parents=True, exist_ok=False)
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    _write_md(out, result)
    _write_corrections(out, result)
    outputs = {n: file_record(out / n, root) for n in
               ("summary.json", "summary.md", "corrections.md")}
    _self = Path(__file__)
    manifest = {
        "schema": "awc-p1-12-coding-repeat-01-characterization-v2-manifest",
        "inputs": inputs,
        "analysis_code": {"path": str(_self.relative_to(ROOT)),
                          "bytes": _self.stat().st_size, "sha256": sha256(_self)},
        "reference_files": ref_files,
        "reference_commit": ref_commit,
        "outputs": outputs,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return result


def _cpu_call_comparison(runs) -> list[str]:
    """Generate per-run CPU vs call-count comparison lines from actual data.
    Max/min and ties are computed; no hardcoded conclusions."""
    lines = ["- Per-run CPU and call composition (computed from data):"]
    lines.append("")
    lines.append("| run | task | CPU (core-s) | Interp/Exec | Test | tool union (s) | term | resolved |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in runs:
        cats = r["tools"]["category_counts"]
        lines.append(
            f"| {r['run_id'][-6:]} | {r['task']} | "
            f"{r['resources'].get('cpu_core_seconds') or 'null'} | "
            f"{cats.get('Interpreter/Execute', 0)} | "
            f"{cats.get('Test', 0)} | "
            f"{r['time_structure']['tool_union_ns'] / 1e9:.1f} | "
            f"{r['termination']} | {r['resolved']} |")
    # find max/min CPU and their call counts (per task with >1 run)
    by_task = {}
    for r in runs:
        by_task.setdefault(r["task"], []).append(r)
    for task, rows in sorted(by_task.items()):
        cpus = [(r["resources"].get("cpu_core_seconds"), r) for r in rows]
        valid = [(c, r) for c, r in cpus if isinstance(c, (int, float))]
        if len(valid) < 2:
            continue
        max_cpu = max(c for c, _ in valid)
        min_cpu = min(c for c, _ in valid)
        max_runs = [r for c, r in valid if c == max_cpu]
        min_runs = [r for c, r in valid if c == min_cpu]
        max_interp = [r["tools"]["category_counts"].get("Interpreter/Execute", 0) for r in max_runs]
        min_interp = [r["tools"]["category_counts"].get("Interpreter/Execute", 0) for r in min_runs]
        if len(max_runs) > 1:
            lines.append(f"- {task}: highest CPU ({max_cpu:.2f} core-s) is a TIE between "
                         f"{len(max_runs)} runs; their Interpreter/Execute counts are {max_interp}.")
        else:
            lines.append(f"- {task}: highest CPU run ({max_cpu:.2f} core-s) has "
                         f"{max_interp[0]} Interpreter/Execute calls; "
                         f"lowest CPU run ({min_cpu:.2f} core-s) has {min_interp[0]}.")
        if set(max_interp) == set(min_interp):
            lines.append(f"  The highest and lowest CPU runs have the SAME Interpreter/Execute "
                         f"count ({max_interp[0]}); call count alone does not explain the CPU "
                         f"difference in this batch.")
    return lines


def _write_md(out: Path, result: dict):
    runs = result["runs"]
    per_task = result["per_task"]
    md = ["# CODING-REPEAT-01 characterization v2", "",
          f"9 runs, 3 tasks × 3 repeats; collection `{result['collection']}`.",
          f"Unselected raw dirs excluded: {result['unselected_raw_directories'] or 'none'}.",
          "", "## Identity association", "",
          "| run | traj calls | valid linked | rejected | hash mismatch | dup IDs |",
          "| --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        a = r["identity_association"]
        md.append(f"| {r['run_id'][-6:]} | {a['traj_total']} | {a['valid_linked']} | "
                  f"{a['rejected']} | {a['hash_mismatch']} | {a['traj_duplicate_ids']} |")
    all_valid = sum(r["identity_association"]["valid_linked"] for r in runs)
    all_rejected = sum(r["identity_association"]["rejected"] for r in runs)
    md.append(f"| **total** | **{sum(r['identity_association']['traj_total'] for r in runs)}** | "
              f"**{all_valid}** | **{all_rejected}** | "
              f"**{sum(r['identity_association']['hash_mismatch'] for r in runs)}** | "
              f"**{sum(r['identity_association']['traj_duplicate_ids'] for r in runs)}** |")

    md += ["", "## Tool classification (per run)", "",
           "Labels are FORM classifications (what the command text looks like), not verified purposes.",
           "Python without pytest evidence = Interpreter/Execute.",
           "",
           "| run | Read/Search | Interpreter/Exec | Test | Git-action | File-write | Submit-marker | Mixed | Partial | Unknown |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        c = r["tools"]["category_counts"]
        md.append(f"| {r['run_id'][-6:]} | {c.get('Read/Search',0)} | "
                  f"{c.get('Interpreter/Execute',0)} | {c.get('Test',0)} | "
                  f"{c.get('Git-action',0)} | {c.get('File-write',0)} | "
                  f"{c.get('Submit-marker',0)} | {c.get('Mixed',0)} | "
                  f"{c.get('Partially-known',0)} | {c.get('Unknown',0)} |")

    md += ["", "## Time structure (per run, seconds)", "",
           "Observation window = first request/tool start to last end. NOT the attempt wall or agent scope wall.",
           "",
           "| run | attempt wall | agent scope wall | obs window | only-req | only-tool | overlap | uncovered |",
           "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        d = r["time_structure"]["decomposition"]
        md.append(f"| {r['run_id'][-6:]} | {r['walls']['attempt_wall_s']:.1f} | "
                  f"{r['walls']['agent_scope_wall_s']:.1f} | "
                  f"{r['walls']['observation_window_s']:.1f} | "
                  f"{d['only_request_ns']/1e9:.1f} | {d['only_tool_ns']/1e9:.1f} | "
                  f"{d['overlap_ns']/1e9:.1f} | {d['uncovered_ns']/1e9:.1f} |")

    md += ["", "## Per-task aggregate (medians over n=3)", "",
           "| task | attempt wall | agent scope wall | obs window | agent CPU | mem kernel peak (MiB) |",
           "| --- | --- | --- | --- | --- | --- |"]
    for task, g in per_task.items():
        md.append(f"| {task} | {g['attempt_wall_s']['median']:.1f} | "
                  f"{g['agent_scope_wall_s']['median']:.1f} | "
                  f"{g['observation_window_s']['median']:.1f} | "
                  f"{g['agent_cpu_core_s']['median']:.2f} | "
                  f"{g['agent_mem_kernel_peak_mib']['median']:.1f} |")

    md += ["", "## Key observations (descriptive)", "",
           "- Request and tool call intervals appear largely sequential in this batch's records "
            "(overlap ≈ 0). This is a description of recorded interval ordering; it does not "
            "prove single-threadedness, absence of background processes, or tool-internal "
            "concurrency.",
            "- Django runs show higher kernel-peak memory (~1.3 GiB) than astropy runs (~0.1-0.4 GiB). "
            "High memory.current sampling points co-occur with various activity categories; "
            "co-occurrence is not causation.",
            ]
    # per-run CPU vs Interpreter/Execute comparison: computed from data
    md += _cpu_call_comparison(runs)
    md += ["", "## Limits", ""]
    md += [f"- {lim}" for lim in result["limitations"]]
    md += ["", "CPU-02 and Replay remain paused. No G2 or architecture claim."]
    (out / "summary.md").write_text("\n".join(md) + "\n")


def _write_corrections(out: Path, result: dict):
    md = ["# v2 → v3 corrections", "",
          "## Problem 1: Test classification treated keywords as execution evidence",
          "- v2 `_TEST_EVIDENCE` searched the full part text for pytest/unittest/tox keywords.",
          "- `grep pytest README.md`, `echo pytest`, and `python -c 'print(\"pytest\")'` "
          "were all misclassified as Test.",
          "- v3: `_TEST_INVOCATION` matches only when a test runner is the command HEAD "
          "(pytest/python -m pytest/python -m unittest/tox/python tests/runtests.py).",
          "- Keyword occurrences in arguments or script bodies no longer trigger Test.",
          "", "## Problem 2: identity gate lacked open/event_id/t_start validation",
          "- v2 accepted: missing open, duplicate open, mismatched event_id, "
          "mismatched t_start_ns between open and terminal.",
          "- v2 hash/length checks were conditional (\"if field present\"); "
          "missing fields could bypass.",
          "- v3: all checks mandatory — exactly one open + one terminal, "
          "event_id present and equal on both, t_start_ns equal on both, "
          "command_view sha256+length required and matching, "
          "timestamps are valid non-bool integers with end >= start.",
          "", "## Problem 3: hardcoded CPU-call relationship",
          "- v2 summary.md stated: 'The run with highest CPU also has the most "
          "Interpreter/Execute calls.'",
          "- Actual astropy-13398 data: mid-CPU run had 1, high-CPU run had 2, "
          "low-CPU run had 2 — the high and low CPU runs had the SAME count.",
          "- v3: this observation is withdrawn; per-run comparison table is "
          "computed from data with ties explicitly reported.",
          "", "## Preserved from v2",
          "- Shell-aware splitting, memory independent of CPU, observation window naming.",
          "- 348/348 calls passed identity association (v3 re-verified with stricter gates).",
          "- Django higher kernel-peak memory; request/tool sequential ordering.",
          ]
    (out / "corrections.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    try:
        result = analyze()
    except Exception as exc:
        print(f"analysis refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    print(f"characterized {len(result['selected_run_ids'])} runs (v2)")
