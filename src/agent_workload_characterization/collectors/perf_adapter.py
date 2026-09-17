"""CPU-01 perf adapter: argv construction plus stat CSV / report stdio parsing.

Command and format semantics are anchored to the LOCAL perf documentation
(static reading only; this module never executes perf):

- perf-stat(1) "CSV FORMAT": fields are, in order, optional usec timestamp
  (with -I), optional CPU/core/socket, optional aggregated-CPU count,
  counter value, unit (or empty), event name, run time of counter,
  percentage of measurement time the counter was running, then optional
  variance / metric value / metric unit. ``-x`` sets the separator
  (recommended ``-x ';'``); ``-o file`` writes counters to a file.
- perf core shell tests (tests/shell/stat+csv_output.sh, stat+csv_summary.sh
  and lib/perf_json_output_lint.py): ``'<not counted>'`` and
  ``'<not supported>'`` are legal counter-value strings.
- perf-record(1): ``-F`` frequency, ``-o`` output file, workload mode
  ``-- <command>``; child tasks inherit counters by default.
- perf-report(1): ``--stdio``, ``--no-children``, ``-i`` input; arm64 shell
  tests (test_arm_coresight.sh, test_arm_spe.sh) show data rows like
  ``73.04%  touch  libc-2.27.so  [.] _dl_addr`` and header lines
  ``# Samples: N of event '...'``.

Ambiguity kept honest: the number of trailing optional fields and whether
the CSV carries one or two time columns is a runtime property, so the
parser records what it actually saw and never fabricates enabled/running
values from a percentage.
"""
from __future__ import annotations

import json
import re
from typing import Any

NOT_COUNTED = "<not counted>"
NOT_SUPPORTED = "<not supported>"


def stat_argv(perf_bin: str, csv_path: str, events: str,
              target_argv: list[str]) -> list[str]:
    return [perf_bin, "stat", "-x", ";", "-o", str(csv_path),
            "-e", events, "--", *target_argv]


def record_argv(perf_bin: str, data_path: str, event: str, freq: int,
                target_argv: list[str]) -> list[str]:
    return [perf_bin, "record", "-F", str(freq), "-o", str(data_path),
            "-e", event, "--", *target_argv]


def report_argv(perf_bin: str, data_path: str) -> list[str]:
    return [perf_bin, "report", "--stdio", "--no-children", "-i", str(data_path)]


def _as_float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _as_percent(text: str) -> float | None:
    value = _as_float(text)
    if value is None or not 0.0 <= value <= 100.0:
        return None
    return value


def parse_stat_line(line: str, separator: str = ";") -> dict[str, Any] | None:
    """Parse one CSV counter line per perf-stat(1) field order.

    Returns None for blank/comment lines. The manual defines exactly ONE
    time column ("run time of counter") followed by the running percentage;
    after those come OPTIONAL variance / metric value / metric unit fields.
    This parser therefore never fabricates a second time column from numeric
    shapes: trailing fields are preserved raw as extras. A line with neither
    value nor event is a metric-only line, not a counter. Values that cannot
    be parsed are kept as None with a distinct status; the raw line is always
    preserved by the caller.
    """
    line = line.rstrip("\n")
    if not line.strip() or line.lstrip().startswith("#"):
        return None
    fields = line.split(separator)
    if len(fields) < 3:
        return {"status": "parse_error", "raw_line": line,
                "reason": "too_few_fields"}
    value_raw, unit, event = fields[0].strip(), fields[1].strip(), fields[2].strip()
    row: dict[str, Any] = {
        "event": event or None,
        "unit": unit or None,
        "value_raw": value_raw,
        "value": _as_float(value_raw),
        "time_enabled_ns": None,
        "time_running_ns": None,
        "run_time_ns": None,
        "percent_running": None,
        "extra_fields": fields[5:] if len(fields) > 5 else [],
        "extra_fields_semantics":
            "optional variance / metric value / metric unit per perf-stat(1); kept raw, not interpreted",
        "time_fields_interpretation": "single_run_time_percent",
        "status": "ok",
    }
    if not value_raw and not event:
        row["status"] = "metric_only"
        return row
    run_time = _as_float(fields[3]) if len(fields) > 3 else None
    pct = _as_percent(fields[4]) if len(fields) > 4 else None
    if run_time is None or pct is None:
        row.update(status="parse_error", reason="missing_time_or_percent")
        return row
    row["run_time_ns"] = run_time
    row["percent_running"] = pct
    if value_raw == NOT_SUPPORTED:
        row["status"] = "not_supported"
    elif value_raw == NOT_COUNTED:
        row["status"] = "not_counted"
    elif not value_raw:
        row["status"] = "missing"
        row["value"] = None
    elif row["value"] is None:
        row["status"] = "parse_error"
    elif row["value"] == 0.0:
        row["status"] = "zero"  # real measured zero, distinct from missing
    return row


def parse_stat_csv(text: str, separator: str = ";") -> dict[str, Any]:
    rows = []
    for line in text.splitlines():
        parsed = parse_stat_line(line, separator)
        if parsed is not None:
            rows.append(parsed)
    # metric-only lines carry no counter: they are retained as evidence but
    # never count toward "the stat produced counters"
    n_counters = sum(1 for r in rows if r["status"] != "metric_only")
    return {
        "events": rows,
        "n_lines": len(text.splitlines()) if text else 0,
        "n_events": len(rows),
        "n_counters": n_counters,
        "n_metric_only": len(rows) - n_counters,
        "n_parse_errors": sum(1 for r in rows if r["status"] == "parse_error"),
        "value_raw_lines_retained": True,
    }


def event_row(events: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for row in events:
        if row.get("event") == name:
            return row
    return None


def compute_ipc(stat_parsed: dict[str, Any]) -> dict[str, Any]:
    """IPC only when cycles and instructions are both valid counters of the
    SAME stat session and the denominator is positive. A real measured zero
    for cycles is a valid counter but not a usable denominator — that is a
    distinct reason from an invalid/unsupported counter. Nothing is invented."""
    cycles = event_row(stat_parsed["events"], "cycles")
    instructions = event_row(stat_parsed["events"], "instructions")
    if cycles is None or instructions is None:
        return {"ipc": None, "reason": "cycles_or_instructions_absent"}
    if cycles.get("status") not in ("ok", "zero") \
            or instructions.get("status") not in ("ok", "zero"):
        return {"ipc": None, "reason": "cycles_or_instructions_not_valid",
                "cycles_status": cycles.get("status"),
                "instructions_status": instructions.get("status")}
    if not cycles.get("value") or cycles["value"] <= 0:
        return {"ipc": None, "reason": "cycles_not_positive",
                "cycles_status": cycles.get("status")}
    return {"ipc": instructions["value"] / cycles["value"],
            "reason": None,
            "basis": "instructions/cycles same stat session both valid"}


_SAMPLES_HEADER = re.compile(r"^#\s+Samples:\s+(\d+)\s+of event\s+'([^']+)'",
                             re.MULTILINE)
_EVENT_COUNT_HEADER = re.compile(r"^#\s+Event count \(approx\.\):\s+(\d+)",
                                 re.MULTILINE)
_HEADER_LINE = re.compile(r"^#\s+Overhead\b")
_DATA_ROW = re.compile(
    r"^\s*(\d+(?:\.\d+)?)%\s+(\S+)\s+(\S+)\s+(\[\.\]\s*\S+|\[unknown\]|\S.*)$")


def parse_report(text: str) -> dict[str, Any]:
    """Parse ``perf report --stdio --no-children`` output into a small
    function table.

    Denominator semantics (kept honest): the Overhead column is perf
    report's Self overhead, accumulated over sample PERIODS — it is NOT a
    ratio over the '# Samples:' header count. The header count and the
    approximated event count are recorded as separate fields when present
    and stay null otherwise; nothing is inferred. Evidence status separates
    a genuine zero-sample profile (header explicitly says 0) from unknown
    output (no header and no rows), an empty stream, and header/row
    inconsistencies.
    """
    if not text or not text.strip():
        return {
            "evidence_status": "empty_output",
            "total_samples": None,
            "event_count_approx": None,
            "denominator_note": ("Self overhead is period-weighted per "
                                 "perf-report(1), not a ratio over total "
                                 "samples; sample counts are separate "
                                 "fields, null when absent"),
            "n_rows": 0, "rows": [], "unparsed_percent_lines": [],
            "zero_samples": False, "unknown_symbol_rows": 0,
        }
    match = _SAMPLES_HEADER.search(text)
    total_samples = int(match.group(1)) if match else None
    match = _EVENT_COUNT_HEADER.search(text)
    event_count = int(match.group(1)) if match else None
    rows = []
    parse_errors = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _DATA_ROW.match(line)
        if m:
            overhead, command, dso, symbol = m.groups()
            symbol = symbol.strip()
            rows.append({
                "overhead_percent_raw": overhead,
                "overhead_percent": _as_float(overhead),
                "command": command,
                "dso": dso,
                "symbol": symbol,
                "symbol_unknown": symbol == "[unknown]" or "[unknown]" in symbol,
            })
        elif "%" in line:
            parse_errors.append(line)
    if total_samples == 0:
        evidence = "header_zero"
    elif total_samples is None and not rows:
        evidence = "no_header_no_rows"
    elif total_samples is None:
        evidence = "no_header_rows"
    elif not rows:
        evidence = "header_no_rows"
    else:
        evidence = "header_and_rows"
    return {
        "evidence_status": evidence,
        "total_samples": total_samples,
        "event_count_approx": event_count,
        "denominator_note": ("Self overhead is period-weighted per "
                             "perf-report(1), not a ratio over total "
                             "samples; sample counts are separate fields, "
                             "null when absent"),
        "n_rows": len(rows),
        "rows": rows,
        "unparsed_percent_lines": parse_errors,
        "zero_samples": total_samples == 0,
        "unknown_symbol_rows": sum(1 for r in rows if r["symbol_unknown"]),
    }


def expected_checksum(n: int) -> str:
    """Closed-form expected checksum for the owned target's fixed loop:
    acc = sum_{k=1..n} 3*k*(k-1)//2 (mod 2**32); sha256 of its decimal
    string. Matches scripts/cpu_01_target.py without running the loop."""
    import hashlib
    total = (n * (n + 1) * (n - 1) // 2) & 0xFFFFFFFF
    return hashlib.sha256(str(total).encode()).hexdigest()


def parse_target_lines(text: str) -> dict[str, Any]:
    """Parse the owned target's JSONL self-reports from perf's forwarded
    stdout: target_started (pid/starttime identity) and target_done."""
    started = done = None
    bad_lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            bad_lines.append(line)
            continue
        if obj.get("event") == "target_started":
            started = obj
        elif obj.get("event") == "target_done":
            done = obj
    return {"target_started": started, "target_done": done,
            "non_json_lines": bad_lines,
            "identity_complete": bool(started and started.get("pid")
                                      and started.get("starttime_ticks"))}
