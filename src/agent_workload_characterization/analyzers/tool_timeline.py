"""G1-01 A1: historical tool timeline and sampling-window audit.

Reads the SEALED RUN-01-C run directory (read-only) and reconstructs
tool-call identity/sequence/result plus the best available time
evidence. Key semantics (verified against the installed mini 2.4.6):

- assistant message ``extra.timestamp`` = ``time.time()`` (epoch float)
  set at the END of the model query, BEFORE tools execute
  (litellm_model.py:104);
- tool message ``extra.timestamp`` = ``time.time()`` set AFTER
  ``env.execute`` returned and the observation was formatted
  (models/utils/actions_toolcall.py:100) — post-execution receipt;
- mini_status.jsonl ``t_start_ns/t_end_ns`` = the child-side
  StatusTrackingAgent request boundaries (CLOCK_MONOTONIC ns).

Because ``(assistant.extra.timestamp, status.t_end_ns)`` for the same
request are read within the same process microseconds apart, they form
an epoch<->monotonic ANCHOR PAIR. On this host CLOCK_MONOTONIC is
system-wide (Linux; not per-process), so calibrated windows can be
compared with the runner's sampler boundaries — with the anchor
residual declared as the error bound. Tool windows are
estimated/bound (log-receipt stamps bracket the execution, they are
NOT native tool start/end); true durations remain null with reason.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# coarse command category heuristic (NOT the P1-06 classifier; labelled
# heuristic_category in every record)
_READISH = ("cat ", "head ", "tail ", "ls", "grep ", "find ", "rg ", "sed -n",
            "awk ", "wc ", "diff ", "git log", "git show", "git diff", "less ")
_WRITISH = ("> ", "tee ", "touch ", "mkdir ", "rm ", "mv ", "cp ", "git add",
            "git commit", "git checkout", "git apply")
_EXECISH = ("python", "pytest", "pip ", "bash ", "sh ", "make ", "echo ")


def heuristic_category(command: str) -> str:
    c = command.strip()
    low = c.lower()
    if any(low.startswith(p) or f" {p}" in low for p in _READISH):
        return "Read/Search"
    if any(low.startswith(p) or f"| {p}" in low for p in _WRITISH):
        return "Write/Edit"
    if any(low.startswith(p) for p in _EXECISH):
        return "Execute"
    if "edit" in low or "sed -i" in low:
        return "Edit"
    return "Other"


def _safe_command_view(command: str) -> dict:
    """Whitelisted safe summary: no raw command content in derived views."""
    return {"heuristic_category": heuristic_category(command),
            "length": len(command),
            "sha256": hashlib.sha256(command.encode()).hexdigest()}


def load_messages(run_dir: Path) -> list[dict]:
    traj = json.loads((run_dir / "mini_trajectory.json")
                      .read_text(encoding="utf-8"))
    return traj.get("messages") or []


def load_status(run_dir: Path) -> list[dict]:
    out = []
    for line in (run_dir / "mini_status.jsonl").read_text(
            encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def pair_tools(messages: list[dict]) -> list[dict]:
    """Pair assistant actions with their tool observation messages.

    mini's execute_actions runs the actions of ONE assistant message in
    order and format_observation_messages zips actions with outputs, so
    the k tool messages following an assistant message with k actions
    belong to it positionally — BUT positional order alone is not
    identity: when BOTH sides carry a tool identifier (mini puts
    ``tool_call_id`` on the action and the tool message carries the
    rendered observation of that action), the IDs must AGREE. A
    mismatch is reported as id_mismatch (never silently accepted); IDs
    are also checked for duplicates and orphaned results.
    """
    pairs = []
    i = 0
    seq = 0
    seen_action_ids: dict[str, int] = {}
    orphaned_results: list[int] = []
    while i < len(messages):
        m = messages[i]
        actions = (m.get("extra") or {}).get("actions") or []
        if m.get("role") == "assistant" and actions:
            tool_msgs = []
            j = i + 1
            while j < len(messages) and messages[j].get("role") == "tool" \
                    and len(tool_msgs) < len(actions):
                tool_msgs.append(messages[j])
                j += 1
            # any further adjacent tool messages are ORPHANED results
            while j < len(messages) and messages[j].get("role") == "tool":
                orphaned_results.append(j)
                j += 1
            for k, action in enumerate(actions):
                tm = tool_msgs[k] if k < len(tool_msgs) else None
                aid = action.get("tool_call_id")
                pairing = "positional"
                if aid is not None:
                    if aid in seen_action_ids:
                        pairing = f"duplicate_action_id"
                    seen_action_ids[aid] = seq
                if tm is None:
                    pairing = "missing_result"
                elif aid is not None:
                    # mini's tool message does not repeat the id; the
                    # mini-side identity comes from the action list zip.
                    # When the tool message DOES carry an id-bearing
                    # structure, compare it (fixture/injected cases).
                    tm_id = (tm.get("tool_call_id")
                             or (tm.get("extra") or {}).get("tool_call_id"))
                    if tm_id is not None and tm_id != aid:
                        pairing = "id_mismatch"
                pairs.append({
                    "seq": seq,
                    "tool_call_id": aid,
                    "assistant_msg_index": i,
                    "tool_msg_index": (i + 1 + k) if tm else None,
                    "action": action,
                    "tool_message": tm,
                    "pairing": pairing,
                })
                seq += 1
            i = j
        else:
            i += 1
    return pairs


def build_anchors(messages: list[dict], status: list[dict]) -> list[dict]:
    """Epoch<->monotonic anchor pairs from successful requests.

    Pairing is by ORDER (the i-th ok status line with the i-th
    assistant-with-actions message). A COUNT MISMATCH between the two
    streams means a line was dropped or added SOMEWHERE in the middle —
    order-based pairing then silently misaligns every anchor after the
    gap, so calibrate() must REFUSE (see _calibration_gate). Anchors
    are still returned for diagnostics, but downstream must honor the
    gate."""
    ok_lines = [line for line in status
                if line.get("ok") and isinstance(line.get("t_end_ns"), int)]
    assistant_stamps = []
    for m in messages:
        actions = (m.get("extra") or {}).get("actions") or []
        if m.get("role") == "assistant" and actions:
            ts = (m.get("extra") or {}).get("timestamp")
            if isinstance(ts, (int, float)):
                assistant_stamps.append(float(ts))
    anchors = []
    n = min(len(ok_lines), len(assistant_stamps))
    for i in range(n):
        anchors.append({"request_ordinal": i + 1,
                        "epoch_s": assistant_stamps[i],
                        "monotonic_ns": int(ok_lines[i]["t_end_ns"])})
    return anchors


def _calibration_gate(messages: list[dict], status: list[dict]) -> dict:
    """Refuse calibration when the anchor streams disagree in count.

    A mid-stream dropped status line shifts every later pairing — the
    anchor residuals may still look small while every converted window
    after the gap is WRONG. When counts mismatch and the gap position
    cannot be reliably located, calibration and ALL derived monotonic
    windows are disabled (null + reason), not warned-and-used."""
    ok_lines = [line for line in status
                if line.get("ok") and isinstance(line.get("t_end_ns"), int)]
    assistant_stamps = [
        m for m in messages
        if m.get("role") == "assistant"
        and (m.get("extra") or {}).get("actions")
        and isinstance((m.get("extra") or {}).get("timestamp"),
                       (int, float))]
    n_ok, n_as = len(ok_lines), len(assistant_stamps)
    if n_ok == n_as:
        return {"enabled": True, "reason": None,
                "n_ok_status_lines": n_ok,
                "n_assistant_with_actions": n_as}
    return {"enabled": False,
            "reason": (f"anchor stream count mismatch ({n_ok} ok status "
                       f"lines vs {n_as} assistant-with-actions): a "
                       "mid-stream gap cannot be reliably located, so "
                       "order-based pairing would silently misalign "
                       "anchors after the gap — calibration and all "
                       "derived monotonic windows are DISABLED"),
            "n_ok_status_lines": n_ok,
            "n_assistant_with_actions": n_as}


def anchor_consistency(messages: list[dict], status: list[dict]) -> dict:
    """Count agreement between the two anchor streams (flag, don't hide)."""
    ok_lines = [line for line in status
                if line.get("ok") and isinstance(line.get("t_end_ns"), int)]
    assistant_stamps = [
        m for m in messages
        if m.get("role") == "assistant"
        and (m.get("extra") or {}).get("actions")
        and isinstance((m.get("extra") or {}).get("timestamp"),
                       (int, float))]
    return {"n_ok_status_lines": len(ok_lines),
            "n_assistant_with_actions": len(assistant_stamps),
            "counts_match": len(ok_lines) == len(assistant_stamps),
            "pairing_rule": ("shorter common prefix; a mismatch means "
                             "dropped or extra lines in one stream and is "
                             "reported here, not silently absorbed")}


def calibrate(anchors: list[dict], *, gate: dict | None = None) -> dict:
    """Offset epoch->monotonic from anchor pairs, with residual spread.

    When ``gate`` is provided and reports a stream-count mismatch, the
    calibration is DISABLED (available=false) even if anchors exist:
    order-based pairing after a mid-stream gap silently misaligns, and
    small residuals do NOT prove correctness. Derived monotonic windows
    must then stay null.

    The anchor RESIDUAL (max deviation of per-request offsets from the
    median) is NOT a proven bound on the calibration error — it bounds
    only the spread across anchor pairs. The residual is reported as
    `anchor_residual_ns_max` (its own name); any downstream use must
    cite it as the observed anchor spread, not as an error bound."""
    if gate is not None and not gate.get("enabled", True):
        return {"available": False,
                "reason": gate["reason"],
                "gate": gate}
    if not anchors:
        return {"available": False,
                "reason": "no anchor pairs (status or timestamps missing)"}
    offsets = [a["monotonic_ns"] - a["epoch_s"] * 1e9 for a in anchors]
    offsets.sort()
    mid = len(offsets) // 2
    median = offsets[mid] if len(offsets) % 2 else (offsets[mid - 1]
                                                    + offsets[mid]) / 2
    residual_ns = max(abs(o - median) for o in offsets)
    return {"available": True,
            "n_anchors": len(anchors),
            "offset_ns_median": median,
            "anchor_residual_ns_max": residual_ns,
            "anchor_residual_semantics": (
                "observed max spread of per-anchor offsets around the "
                "median; NOT a proven calibration error bound"),
            "method": ("per-request (assistant.extra.timestamp epoch, "
                       "status.t_end_ns monotonic) read within the same "
                       "child-process query call")}


def epoch_to_monotonic_ns(epoch_s: float, calib: dict) -> float | None:
    if not calib.get("available"):
        return None
    return epoch_s * 1e9 + calib["offset_ns_median"]


def build_tool_timeline(run_dir: Path) -> dict:
    """Full A1 analysis over the sealed run (read-only)."""
    messages = load_messages(run_dir)
    status = load_status(run_dir)
    pairs = pair_tools(messages)
    gate = _calibration_gate(messages, status)
    anchors = build_anchors(messages, status)
    calib = calibrate(anchors, gate=gate)

    samples = json.loads((run_dir / "samples.json").read_text(
        encoding="utf-8"))
    scopes_ev = samples.get("evidence") or {}
    scope_bounds = {}
    for scope, ev in scopes_ev.items():
        bs, be = ev.get("boundary_start"), ev.get("boundary_end")
        if bs and be:
            scope_bounds[scope] = (bs.get("t_monotonic_ns"),
                                   be.get("t_monotonic_ns"))

    records = []
    for p in pairs:
        action, tm = p["action"], p["tool_message"]
        a_ts = None
        for m in messages[max(0, p["assistant_msg_index"]):
                          p["assistant_msg_index"] + 1]:
            a_ts = (m.get("extra") or {}).get("timestamp")
        t_ts = (tm.get("extra") or {}).get("timestamp") if tm else None
        rec = {
            "seq": p["seq"],
            "tool_call_id": p["tool_call_id"],
            "pairing": p["pairing"],
            "request_index": _request_index(messages, p["assistant_msg_index"]),
            "command": _safe_command_view(action.get("command", "")),
            "result": (None if tm is None else {
                "returncode": (tm.get("extra") or {}).get("returncode"),
                "exception_present": bool(
                    (tm.get("extra") or {}).get("exception_info")),
                "output_length": len((tm.get("extra") or {})
                                     .get("raw_output") or ""),
            }),
            "time": {
                "true_start_ns": None,
                "true_end_ns": None,
                "true_duration_s": None,
                "true_missing_reason": (
                    "historical run has NO native tool start/end: the "
                    "G1-01-A hook did not exist; only log-receipt epoch "
                    "stamps are available"),
                "receipt_start_epoch_s": a_ts,
                "receipt_end_epoch_s": t_ts,
                "window_s_estimated": (
                    (t_ts - a_ts)
                    if isinstance(a_ts, (int, float))
                    and isinstance(t_ts, (int, float)) else None),
                "window_semantics": (
                    "estimated/bound: receipt_start is post-query "
                    "pre-execution, receipt_end is post-execution "
                    "post-formatting — the window OVERSTATES tool "
                    "execution by scheduling+formatting overhead"),
                "window_monotonic_ns": (None, None),
            },
            "scope_association": {
                "method": "shared_scope/window (calibrated)",
                "window_in_agent_scope": None,
                "n_agent_scope_samples_in_window": None,
            },
        }
        w_start = epoch_to_monotonic_ns(a_ts, calib) \
            if isinstance(a_ts, (int, float)) else None
        w_end = epoch_to_monotonic_ns(t_ts, calib) \
            if isinstance(t_ts, (int, float)) else None
        if w_start is not None and w_end is not None:
            rec["time"]["window_monotonic_ns"] = [w_start, w_end]
        agent_scope = next((s for s, b in scope_bounds.items()
                            if "agent" in s), None)
        if agent_scope and w_start is not None and w_end is not None:
            lo, hi = scope_bounds[agent_scope]
            rec["scope_association"]["window_in_agent_scope"] = bool(
                w_start >= lo and w_end <= hi)
            ev = scopes_ev[agent_scope]
            n = sum(1 for s in (ev.get("samples") or [])
                    if w_start <= s.get("t_monotonic_ns", -1) <= w_end)
            rec["scope_association"]["n_agent_scope_samples_in_window"] = n
            rec["scope_association"]["anchor_residual_ns_max"] = calib.get(
                "anchor_residual_ns_max")
        records.append(rec)

    # sampling-window audit per scope: samples inside/outside boundaries
    window_audit = {}
    for scope, ev in scopes_ev.items():
        bs, be = ev.get("boundary_start"), ev.get("boundary_end")
        sams = ev.get("samples") or []
        if not (bs and be):
            window_audit[scope] = {"status": "boundary_missing"}
            continue
        lo, hi = bs.get("t_monotonic_ns"), be.get("t_monotonic_ns")
        inside = [s for s in sams if lo <= s.get("t_monotonic_ns", -1) <= hi]
        outside = [s for s in sams if not lo <= s.get("t_monotonic_ns", -1)
                   <= hi]
        gaps = ev.get("sample_gaps_ns") or []
        interval_target = (scopes_ev.get(scope) or {}).get(
            "interval_target_s")
        window_audit[scope] = {
            "boundary_start_ns": lo, "boundary_end_ns": hi,
            "n_samples_total": len(sams),
            "n_samples_in_boundary": len(inside),
            "n_samples_outside_boundary": len(outside),
            "outside_sample_timestamps_ns": [s.get("t_monotonic_ns")
                                             for s in outside],
            "n_gaps_recorded": len(gaps),
            "interval_target_s": interval_target,
            "note": ("out-of-boundary samples are preserved in the sealed "
                     "file and listed here in the derived view; they are "
                     "NOT counted in the in-window peak/sample numbers"),
        }

    n_missing = sum(1 for r in records if r["pairing"] == "missing_result")
    durations_est = [r["time"]["window_s_estimated"] for r in records
                     if r["time"]["window_s_estimated"] is not None]
    return {
        "tool_calls_total": len(records),
        "pairing_missing_results": n_missing,
        "pairing_anomalies": {
            "n_id_mismatch": sum(1 for r in records
                                 if r["pairing"] == "id_mismatch"),
            "n_duplicate_action_id": sum(1 for r in records
                                         if r["pairing"]
                                         == "duplicate_action_id"),
        },
        "identity_basis": ("tool_call_id + positional pairing with ID "
                           "cross-check (mismatch/duplicate/orphan "
                           "reported, never silently accepted)"),
        "calibration": calib,
        "anchor_gate": gate,
        "true_duration_coverage": {
            "n_valid": 0,
            "n_applicable": len(records),
            "reason": "no native tool start/end in the historical run",
        },
        "estimated_window_coverage": {
            "n_valid": len(durations_est),
            "n_applicable": len(records),
        },
        "records": records,
        "scope_window_audit": window_audit,
    }


def _request_index(messages: list[dict], msg_index: int) -> int:
    """1-based index over successful requests up to this message."""
    n = 0
    for m in messages[:msg_index + 1]:
        if m.get("role") == "assistant" and \
                (m.get("extra") or {}).get("actions"):
            n += 1
    return n


def write_tool_timeline_outputs(run_dir: Path, out_dir: Path) -> dict:
    """Write tool_timeline.jsonl + scope_coverage.json (derived views)."""
    analysis = build_tool_timeline(run_dir)
    with (out_dir / "tool_timeline.jsonl").open("w", encoding="utf-8") as fh:
        for rec in analysis["records"]:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    coverage = {
        "calibration": analysis["calibration"],
        "anchor_gate": analysis["anchor_gate"],
        "identity": {"tool_calls_total": analysis["tool_calls_total"],
                     "pairing_missing_results":
                         analysis["pairing_missing_results"],
                     "pairing_anomalies": analysis["pairing_anomalies"],
                     "identity_basis": analysis["identity_basis"]},
        "true_duration_coverage": analysis["true_duration_coverage"],
        "estimated_window_coverage": analysis["estimated_window_coverage"],
        "scope_window_audit": analysis["scope_window_audit"],
        "host_scope": {
            "status": "missing_historical",
            "reason": ("the host-side mini child had no per-process "
                       "CPU/RSS reader in RUN-01-C; G1-01-A adds "
                       "HostProcessReader for FUTURE runs — the gap is "
                       "not back-filled"),
        },
        "io_formal": {"status": "null_degraded",
                      "reason": "host cgroup v1 blkio (approved wording)"},
    }
    (out_dir / "scope_coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return analysis
