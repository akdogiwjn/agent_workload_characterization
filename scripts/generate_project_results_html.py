#!/usr/bin/env python3
"""Generate a small, offline reading pack from the project's accepted reports."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_REL = Path("reports/html/PROJECT-RESULTS-v5")
PACKAGES = {
    "swe": "reports/analysis/SWE-REBENCH-behavior-v2",
    "swebench": "reports/analysis/SWEBENCH-subset-behavior-v1",
    "osworld": "reports/analysis/OSWORLD-task-behavior-v3",
    "macro": "reports/analysis/AGENTX-APPLIED-MACRO-v1",
    "coding": "reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3",
    "link": "reports/analysis/CODING-RESOURCE-LINK-feasibility-v1",
    "word": "reports/analysis/DOCOPS-WORD-RESOURCE-03-04-review-v1",
    "office": "reports/analysis/DOCOPS-OFFICE-REPEAT-01-characterization-v1",
    "office02": "reports/analysis/DOCOPS-OFFICE-REPEAT-02-characterization-v1",
    "synthesis": "reports/analysis/PROJECT-characterization-synthesis-v2",
}
REPORT_FILES = {
    "swe": ["summary.json", "summary.md", "measurement_candidates.json", "manifest.json"],
    "swebench": ["summary.json", "summary.md", "selection.json", "manifest.json"],
    "osworld": ["summary.json", "summary.md", "task_semantics.jsonl", "per_trajectory.jsonl", "manifest.json"],
    "macro": ["summary.json", "summary.md", "per_trace.jsonl", "per_template.jsonl", "manifest.json"],
    "coding": ["summary.json", "summary.md", "per_run.jsonl", "manifest.json"],
    "link": ["decision.json", "summary.md", "manifest.json"],
    "word": ["summary.json", "summary.md", "per_run.jsonl", "manifest.json"],
    "office": ["summary.json", "summary.md", "per_run.jsonl", "manifest.json"],
    "office02": ["summary.json", "summary.md", "per_run.jsonl", "manifest.json"],
    "synthesis": ["evidence_matrix.json", "summary.md", "manifest.json"],
}
HISTORY_DRIFT = {
    "coding": {
        "analysis/tool_timing.py": "references/repos/agentcgroup/analysis/tool_timing.py",
        "analysis/compute_active_time.py": "references/repos/agentcgroup/analysis/compute_active_time.py",
    },
    "link": {},
    "synthesis": {},
}
HISTORY_SNAPSHOT_PATHS = {
    "link": {"methodology.md": "local_archive/20261016-full-docs/methodology.md"},
    "synthesis": {"methodology.md": "local_archive/20261016-full-docs/methodology.md"},
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def hash_matches(path: Path, expected_sha256: Any, expected_bytes: Any = None) -> bool:
    return bool(path.is_file() and isinstance(expected_sha256, str)
                and sha256(path) == expected_sha256
                and (expected_bytes is None or path.stat().st_size == expected_bytes))


def record(path: Path, root: Path, role: str) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
            "sha256": sha256(path), "role": role}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rel_report(here: Path, target: str, root: Path) -> str | None:
    p = root / target
    return Path(__import__("os").path.relpath(p, here)).as_posix() if p.is_file() else None


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def fmt(value: Any, digits: int = 2) -> str:
    if value is None or isinstance(value, bool):
        return "—"
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return "—"
        return f"{value:,.{digits}f}".rstrip("0").rstrip(".") if isinstance(value, float) else f"{value:,}"
    return str(value)


def svg_bars(items: list[tuple[str, float]], *, title: str, unit: str = "count", width: int = 720) -> str:
    items = [(str(k), float(v)) for k, v in items if isinstance(v, (int, float)) and math.isfinite(v) and v >= 0]
    if not items:
        return '<p class="muted">没有可绘制的有效值。</p>'
    left, right, top, row, barh = 180, 18, 34, 31, 16
    height = top + len(items) * row + 12
    maxv = max((v for _, v in items), default=1) or 1
    plotw = width - left - right
    out = [f'<svg class="bars" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
           f'<title>{esc(title)}</title>']
    for i, (label, value) in enumerate(items):
        y = top + i * row
        w = max(1, plotw * value / maxv)
        out.append(f'<text x="{left-8}" y="{y+13}" text-anchor="end">{esc(label)}</text>')
        out.append(f'<rect x="{left}" y="{y}" width="{w:.2f}" height="{barh}" rx="4"><title>{esc(label)}: {fmt(value)} {esc(unit)}</title></rect>')
        out.append(f'<text x="{min(width-right, left+w+6):.2f}" y="{y+13}">{fmt(value)}</text>')
    out.append('</svg>')
    return ''.join(out)


def manifest_entries(manifest: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = manifest.get(key, [])
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict) and x.get("path")]
    if isinstance(value, dict):
        return [dict(v, path=k) if isinstance(v, dict) else {"path": k} for k, v in value.items()]
    return []


def declared_file(root: Path, package: Path, rel: str) -> Path:
    p = root / rel
    if p.is_file():
        return p
    return package / rel


def check_report_outputs(root: Path, package: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    checked = []
    for entry in manifest_entries(manifest, "outputs"):
        path = declared_file(root, package, entry["path"])
        expected = entry.get("sha256")
        exists = path.is_file()
        actual = sha256(path) if exists else None
        expected_bytes = entry.get("bytes")
        checked.append({"path": str(path.relative_to(root)) if exists else entry["path"],
                        "exists": exists, "expected_sha256": expected, "actual_sha256": actual,
                        "expected_bytes": expected_bytes, "actual_bytes": path.stat().st_size if exists else None,
                        "match": bool(exists and actual == expected and
                                      (expected_bytes is None or path.stat().st_size == expected_bytes))})
    return checked


def check_historical_inputs(root: Path, manifest: dict[str, Any], package_name: str,
                            paths: dict[str, str] | list[str], *, snapshot: bool = False) -> list[dict[str, Any]]:
    entries = []
    for section in ("inputs", "reference_files"):
        entries.extend(manifest_entries(manifest, section))
    by_path = {x.get("path"): x for x in entries}
    result = []
    path_map = paths if isinstance(paths, dict) else {p: p for p in paths}
    for rel, resolved_rel in path_map.items():
        old = by_path.get(rel)
        path = root / resolved_rel
        matched = bool(old and path.is_file() and old.get("sha256") == sha256(path)
                       and (old.get("bytes") is None or old.get("bytes") == path.stat().st_size))
        result.append({"manifest_path": rel, "resolved_project_path": resolved_rel,
                       "registered_sha256": old.get("sha256") if old else None,
                       "current_sha256": sha256(path) if path.is_file() else None,
                       "registered_bytes": old.get("bytes") if old else None,
                       "current_bytes": path.stat().st_size if path.is_file() else None,
                       "status": "match" if matched else ("missing" if not path.is_file() else
                                   ("current_status_snapshot_drift" if snapshot else "mismatch")),
                       "current_exists": path.is_file(), "drift": not matched})
    return result


def package_data(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    data, consumed, package_checks = {}, [], []
    for name, rel in PACKAGES.items():
        folder = root / rel
        manifest_path = folder / "manifest.json"
        manifest = load_json(manifest_path)
        output_checks = check_report_outputs(root, folder, manifest)
        historical_reference_checks=check_historical_inputs(root, manifest, name, HISTORY_DRIFT.get(name, {}))
        historical_status_snapshot_checks=check_historical_inputs(
            root, manifest, name, HISTORY_SNAPSHOT_PATHS.get(name, []), snapshot=True)
        package_checks.append({"package": name, "manifest": rel + "/manifest.json",
                               "output_checks": output_checks,
                               "outputs_pass": all(x["match"] for x in output_checks),
                               "historical_reference_checks": historical_reference_checks,
                               "historical_status_snapshot_checks": historical_status_snapshot_checks})
        consumed.append(record(manifest_path, root, "source_analysis_manifest"))
        for check in historical_reference_checks + historical_status_snapshot_checks:
            current_path=root/check["resolved_project_path"]
            if current_path.is_file():
                consumed.append(record(current_path,root,"historical_reference_or_status_snapshot"))
        for filename in REPORT_FILES[name]:
            path = folder / filename
            if path.is_file() and path != manifest_path:
                consumed.append(record(path, root, "analysis_result"))
        data[name] = {"folder": folder, "manifest": manifest, "checks": output_checks}
    return data, consumed, package_checks


def load_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def find_declared(manifest: dict[str, Any], path_rel: str) -> dict[str, Any] | None:
    for section in ("inputs", "outputs"):
        for item in manifest_entries(manifest, section):
            if item.get("path") == path_rel:
                return item
    return None


def sample_projection(raw: dict[str, Any]) -> dict[str, Any]:
    samples = raw.get("samples", [])
    points = []
    first_t = next((s.get("t_monotonic_ns") for s in samples if isinstance(s.get("t_monotonic_ns"), int)), None)
    prev_t = prev_cpu = None
    for s in samples:
        t = s.get("t_monotonic_ns")
        c = s.get("container") or {}
        cpu = c.get("cpu_usage_usec")
        dt = (t - prev_t) / 1e9 if isinstance(t, int) and isinstance(prev_t, int) and t > prev_t else None
        cores = ((cpu - prev_cpu) / 1e6 / dt) if dt and isinstance(cpu, (int, float)) and isinstance(prev_cpu, (int, float)) and cpu >= prev_cpu else None
        points.append({"t_s": (t-first_t)/1e9 if isinstance(t, int) and first_t is not None else None,
                       "cpu_cores": cores,
                       "memory_mib": c.get("mem_current_bytes") / (1024*1024) if isinstance(c.get("mem_current_bytes"), (int,float)) else None})
        prev_t, prev_cpu = t, cpu
    phases = []
    events = raw.get("events", [])
    visible_phases = {"harbor_start_begin", "harbor_start_done", "agent_setup_begin",
                      "agent_setup_done", "agent_begin", "agent_end", "verifier_begin",
                      "verifier_end", "harbor_stop_begin", "harbor_stop_done"}
    for e in events:
        label = e.get("phase")
        t = e.get("t_monotonic_ns")
        if label in visible_phases and isinstance(t, int) and first_t is not None:
            rel_s=(t-first_t)/1e9
            window_s=(points[-1]["t_s"] if points and points[-1]["t_s"] is not None else None)
            phases.append({"label": label, "t_s": rel_s,
                           "in_sample_window": bool(window_s is not None and 0 <= rel_s <= window_s)})
    return {"points": points, "phases": phases, "sample_count": len(points),
            "window_s": points[-1]["t_s"] if points and points[-1]["t_s"] is not None else None}


def coding_phase_projection(event_rows: list[dict[str, Any]], first_sample_ns: int | None,
                            window_s: float | None) -> list[dict[str, Any]]:
    """Use only explicit monotonic container/verifier lifecycle events."""
    phase_map = {
        ("container", "agent", "start"): "agent_begin",
        ("container", "agent", "stop_and_verify_removal"): "agent_end",
        ("container", "verifier", "start"): "verifier_begin",
        ("container", "verifier", "stop_and_verify_removal"): "verifier_end",
    }
    phases = []
    relevant_times = [e.get("t_monotonic_ns") for e in event_rows
                      if (e.get("kind"), (e.get("attrs") or {}).get("scope"),
                          (e.get("attrs") or {}).get("action")) in phase_map
                      and e.get("clock_domain") == "system_monotonic"
                      and isinstance(e.get("t_monotonic_ns"), int)]
    if first_sample_ns is None and relevant_times:
        first_sample_ns = min(relevant_times)
    for event in event_rows:
        attrs = event.get("attrs") or {}
        key = (event.get("kind"), attrs.get("scope"), attrs.get("action"))
        label = phase_map.get(key)
        t = event.get("t_monotonic_ns")
        if label and event.get("clock_domain") == "system_monotonic" and isinstance(t, int) and first_sample_ns is not None:
            relative = (t - first_sample_ns) / 1e9
            phases.append({"label": label, "t_s": relative,
                           "in_sample_window": bool(window_s is not None and 0 <= relative <= window_s) if window_s is not None else None})
    return phases


def _valid_counter(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def coding_evidence_projection(samples_doc: dict[str, Any]) -> dict[str, Any]:
    """Project the two explicitly identified Coding cgroup evidence scopes."""
    expected = {
        "agent_container": "cpuacct.usage",
        "verifier_container": "cpuacct.usage",
    }
    scopes = samples_doc.get("scopes") or {}
    evidence = samples_doc.get("evidence") or {}
    selected: dict[str, tuple[str, dict[str, Any], dict[str, Any]]] = {}
    for kind in expected:
        candidates = [(scope_id, ev) for scope_id, ev in evidence.items()
                      if isinstance(ev, dict) and ev.get("scope_kind") == kind]
        if len(candidates) != 1:
            raise ValueError(f"expected one {kind} evidence scope, found {len(candidates)}")
        scope_id, ev = candidates[0]
        summary = scopes.get(scope_id)
        if not isinstance(summary, dict):
            raise ValueError(f"summary scope missing for evidence scope {scope_id}")
        if ev.get("scope") != scope_id or summary.get("scope_kind") != kind:
            raise ValueError(f"scope identity/kind mismatch for {scope_id}")
        selected[kind] = (scope_id, ev, summary)

    starts = [ev.get("boundary_start", {}).get("t_monotonic_ns")
              for _, ev, _ in selected.values()]
    starts = [t for t in starts if isinstance(t, int) and not isinstance(t, bool)]
    origin_ns = min(starts) if len(starts) == len(selected) else None
    projected: dict[str, Any] = {}
    for kind, (scope_id, ev, summary) in selected.items():
        start, end = ev.get("boundary_start") or {}, ev.get("boundary_end") or {}
        start_ns, end_ns = start.get("t_monotonic_ns"), end.get("t_monotonic_ns")
        if not (isinstance(start_ns, int) and not isinstance(start_ns, bool)
                and isinstance(end_ns, int) and not isinstance(end_ns, bool)
                and end_ns > start_ns):
            raise ValueError(f"invalid observation boundaries for {scope_id}")
        if origin_ns is None:
            raise ValueError("common run monotonic origin unavailable")
        raw_samples = ev.get("samples")
        if not isinstance(raw_samples, list):
            raise ValueError(f"evidence samples missing for {scope_id}")
        entries = [("boundary_start", start)] + [("sample", p) for p in raw_samples] + [("boundary_end", end)]
        cpu_intervals: list[dict[str, Any]] = []
        memory_points: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        counts = {
            "cpu_valid_counter_points": 0, "cpu_invalid_read_status": 0,
            "cpu_valid_sample_counter_points": 0, "cpu_valid_boundary_counter_points": 0,
            "cpu_missing_or_invalid_value": 0, "cpu_missing_timestamp": 0,
            "cpu_outside_boundary": 0, "cpu_nonincreasing_time": 0,
            "cpu_counter_decrease": 0, "cpu_no_predecessor": 0,
            "memory_valid_points": 0, "memory_valid_sample_points": 0,
            "memory_valid_boundary_points": 0, "memory_invalid_read_status": 0,
            "memory_missing_or_invalid_value": 0, "memory_missing_timestamp": 0,
            "memory_outside_boundary": 0,
        }
        previous: tuple[int, int] | None = None
        timestamp_projection = []
        for source_kind, point in entries:
            timestamp = point.get("t_monotonic_ns")
            valid_t = isinstance(timestamp, int) and not isinstance(timestamp, bool)
            rel_s = (timestamp - origin_ns) / 1e9 if valid_t else None
            inside = valid_t and start_ns <= timestamp <= end_ns
            if source_kind == "sample":
                timestamp_projection.append(timestamp if valid_t else None)
            status = point.get("read_status") or {}
            cpu_value = point.get("cpu_usage_usec")
            cpu_ok = status.get("cpuacct.usage") == "ok_ns_converted_to_usec"
            if not valid_t:
                counts["cpu_missing_timestamp"] += 1
                previous = None
            elif not inside:
                counts["cpu_outside_boundary"] += 1
                previous = None
            elif not cpu_ok:
                counts["cpu_invalid_read_status"] += 1
                previous = None
            elif not _valid_counter(cpu_value) or cpu_value < 0:
                counts["cpu_missing_or_invalid_value"] += 1
                previous = None
            else:
                counts["cpu_valid_counter_points"] += 1
                counts["cpu_valid_sample_counter_points" if source_kind == "sample"
                       else "cpu_valid_boundary_counter_points"] += 1
                current = (timestamp, int(cpu_value))
                if previous is None:
                    counts["cpu_no_predecessor"] += 1
                else:
                    prev_t, prev_cpu = previous
                    if timestamp <= prev_t:
                        counts["cpu_nonincreasing_time"] += 1
                    elif current[1] < prev_cpu:
                        counts["cpu_counter_decrease"] += 1
                    else:
                        dt = (timestamp - prev_t) / 1e9
                        cores = ((current[1] - prev_cpu) / 1e6) / dt
                        cpu_intervals.append({"t_start_ns": prev_t, "t_end_ns": timestamp,
                                              "t_start_s": (prev_t-origin_ns)/1e9,
                                              "t_end_s": rel_s, "average_cores": cores})
                # A valid current reading starts a new adjacent interval after a reset/time anomaly.
                previous = current

            mem_value = point.get("mem_current_bytes")
            mem_ok = status.get("memory.usage_in_bytes") == "ok"
            if not valid_t:
                counts["memory_missing_timestamp"] += 1
            elif not inside:
                counts["memory_outside_boundary"] += 1
            elif not mem_ok:
                counts["memory_invalid_read_status"] += 1
            elif not _valid_counter(mem_value) or mem_value < 0:
                counts["memory_missing_or_invalid_value"] += 1
            else:
                counts["memory_valid_points"] += 1
                counts["memory_valid_sample_points" if source_kind == "sample"
                       else "memory_valid_boundary_points"] += 1
                memory_points.append({"t_monotonic_ns": timestamp, "t_s": rel_s,
                                      "memory_current_bytes": int(mem_value),
                                      "memory_current_mib": mem_value / 1048576,
                                      "source": source_kind})
            observations.append({"source": source_kind,
                "t_monotonic_ns": timestamp if valid_t else None,
                "cpu_usage_usec": cpu_value if _valid_counter(cpu_value) else None,
                "cpu_read_status": status.get("cpuacct.usage"),
                "memory_current_bytes": mem_value if _valid_counter(mem_value) else None,
                "memory_read_status": status.get("memory.usage_in_bytes"),
                "inside_registered_boundary": bool(inside)})

        projected[kind] = {
            "scope_id": scope_id, "scope_kind": kind,
            "interval_target_s": ev.get("interval_target_s"),
            "boundary_start_ns": start_ns, "boundary_end_ns": end_ns,
            "window_s": (end_ns-start_ns)/1e9, "common_origin_ns": origin_ns,
            "saved_sample_count": len(raw_samples),
            "sample_gaps_ns_count": len(ev.get("sample_gaps_ns") or []),
            "sample_timestamps_ns": timestamp_projection,
            "observations": observations,
            "boundary_start": start, "boundary_end": end,
            "cpu_intervals": cpu_intervals, "memory_points": memory_points,
            "counts": counts,
            "aggregate": summary,
            "curve_status": "generated" if cpu_intervals and memory_points else "partial_no_valid_series",
        }
    return {"common_origin_ns": origin_ns, "scopes": projected}


def coding_resource_svg(scope: dict[str, Any], metric: str,
                        phases: list[dict[str, Any]], *, css_class: str = "coding-resource") -> str:
    """Draw only saved interval averages or observed memory points; gaps remain gaps."""
    cpu = metric == "cpu"
    title = f"{scope['scope_kind']} {scope['scope_id']} · " + (
        "采样区间平均 CPU (core)" if cpu else "memory.current (MiB)")
    x0 = (scope["boundary_start_ns"]-scope["common_origin_ns"])/1e9
    x1 = (scope["boundary_end_ns"]-scope["common_origin_ns"])/1e9
    series = scope["cpu_intervals"] if cpu else scope["memory_points"]
    values = ([x["average_cores"] for x in series] if cpu else
              [x["memory_current_mib"] for x in series])
    if not series:
        return f'<div class="empty-chart">{esc(title)}：无有效观测；缺口未插值。</div>'
    w, h, left, right, top, bottom = 760, 270, 68, 22, 24, 52
    xmax = max(x1, x0 + 1e-9)
    ymin, ymax = min([0.0] + values), max([0.0] + values)
    if ymin == ymax:
        ymax = ymin + 1.0
    def px(t: float) -> float:
        return left + (w-left-right) * (t-x0)/(xmax-x0)
    def py(v: float) -> float:
        return top + (h-top-bottom) * (1-(v-ymin)/(ymax-ymin))
    parts = [f'<svg class="{esc(css_class)}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">',
             f'<title>{esc(title)}</title>']
    for i in range(5):
        y = top + (h-top-bottom)*i/4
        value = ymax-(ymax-ymin)*i/4
        parts.append(f'<line class="grid" x1="{left}" y1="{y:.2f}" x2="{w-right}" y2="{y:.2f}"/><text x="{left-7}" y="{y+4:.2f}" text-anchor="end">{value:.2f}</text>')
    for i in range(5):
        t = x0+(xmax-x0)*i/4
        x=px(t)
        parts.append(f'<line class="axis-tick" x1="{x:.2f}" y1="{h-bottom}" x2="{x:.2f}" y2="{h-bottom+4}"/><text x="{x:.2f}" y="{h-bottom+18}" text-anchor="middle">{t:.2f} s</text>')
    for phase in phases:
        t = phase.get("t_s")
        if isinstance(t,(int,float)) and x0 <= t <= x1:
            x=px(t)
            parts.append(f'<line class="phase" x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{h-bottom}"><title>{esc(phase["label"])} · {t:.6f}s</title></line>')
    if cpu:
        for interval in series:
            y=py(interval["average_cores"])
            parts.append(f'<line class="cpu-interval" x1="{px(interval["t_start_s"]):.2f}" y1="{y:.2f}" x2="{px(interval["t_end_s"]):.2f}" y2="{y:.2f}"><title>{interval["average_cores"]:.6f} core · adjacent saved readings</title></line>')
    else:
        for point in series:
            x,y=px(point["t_s"]),py(point["memory_current_mib"])
            parts.append(f'<circle class="memory-point" cx="{x:.2f}" cy="{y:.2f}" r="2.2"><title>{point["memory_current_mib"]:.4f} MiB · {point["source"]} observed point</title></circle>')
    unit = "平均core（100% = 1 core；未按配额归一化）" if cpu else "memory.current（MiB；原始观测点）"
    parts.append(f'<text x="{w/2}" y="{h-7}" text-anchor="middle">相对本run共同 monotonic 原点（秒）</text><text x="8" y="15">{unit}</text></svg>')
    return "".join(parts)


def coding_scope_plot(scope: dict[str, Any], metric: str,
                      phases: list[dict[str, Any]], source: str) -> str:
    counts = scope["counts"]
    valid = len(scope["cpu_intervals"]) if metric == "cpu" else counts["memory_valid_sample_points"]
    kind_label = "Agent容器" if scope["scope_kind"] == "agent_container" else "verifier容器"
    metric_label = "采样区间平均core" if metric == "cpu" else "memory.current"
    missing = (counts["cpu_invalid_read_status"] + counts["cpu_missing_or_invalid_value"] +
               counts["cpu_missing_timestamp"] + counts["cpu_nonincreasing_time"] +
               counts["cpu_counter_decrease"] + counts["cpu_outside_boundary"]) if metric == "cpu" else (
               counts["memory_invalid_read_status"] + counts["memory_missing_or_invalid_value"] +
               counts["memory_missing_timestamp"] + counts["memory_outside_boundary"])
    window = f'{scope["boundary_start_ns"]}–{scope["boundary_end_ns"]} ns; {fmt(scope["window_s"],3)} s'
    return (f'<section class="coding-scope-plot"><h4>{kind_label} · {metric_label}</h4>'
            f'<p><code>{esc(scope["scope_id"])}</code> · 来源 <code>{esc(source)}</code> · '
            f'evidence samples={scope["saved_sample_count"]} · 有效{metric_label}样本点={valid} · '
            f'有效边界点={counts["cpu_valid_boundary_counter_points"] if metric == "cpu" else counts["memory_valid_boundary_points"]} · '
            f'窗口 {window} · interval target={fmt(scope["interval_target_s"])} s · 缺读/异常={missing}。'
            '横轴采用本run两个scope共享的 monotonic 原点；仅显示登记边界内观测。CPU是相邻有效累计读数的区间平均值，缺口不连接。'
            'boundary_start没有前序差分；其后的首个有效采样可与该边界读数构成区间。'
            f'</p>{coding_resource_svg(scope,metric,phases)}</section>')


def coding_lifecycle_svg(phases: list[dict[str, Any]]) -> str:
    by_label = {p["label"]: p["t_s"] for p in phases}
    last = max((p["t_s"] for p in phases), default=0.0)
    if not phases or last <= 0:
        return '<div class="empty-chart">未保存可核验的Agent/verifier阶段边界。</div>'
    left, right, width = 84, 20, 720
    x = lambda t: left + (width-left-right)*t/last
    rows = [("Agent container", "agent_begin", "agent_end", 42, "agent-phase"),
            ("Verifier container", "verifier_begin", "verifier_end", 88, "verifier-phase")]
    parts = [f'<svg class="phase-timeline" viewBox="0 0 {width} 126" role="img" aria-label="Saved monotonic Agent/verifier container lifecycle">',
             '<title>Saved monotonic container lifecycle events, not a resource curve</title>']
    for label, start, end, y, cls in rows:
        parts.append(f'<text x="{left-8}" y="{y+4}" text-anchor="end">{esc(label)}</text>')
        if start in by_label and end in by_label:
            parts.append(f'<rect class="{cls}" x="{x(by_label[start]):.2f}" y="{y-8}" width="{max(1,x(by_label[end])-x(by_label[start])):.2f}" height="16" rx="4"/>')
            parts.append(f'<line class="phase-edge" x1="{x(by_label[start]):.2f}" y1="{y-14}" x2="{x(by_label[start]):.2f}" y2="{y+14}"/><line class="phase-edge" x1="{x(by_label[end]):.2f}" y1="{y-14}" x2="{x(by_label[end]):.2f}" y2="{y+14}"/>')
        else:
            parts.append(f'<text x="{left}" y="{y+4}">边界记录不完整</text>')
    parts.append(f'<text x="{left}" y="122">0 s</text><text x="{width-right}" y="122" text-anchor="end">{fmt(last,3)} s</text></svg>')
    return ''.join(parts)


def chart_series(points: list[dict[str, Any]], key: str, title: str, unit: str, phases: list[dict[str, Any]]) -> str:
    values = [(p.get("t_s"), p.get(key)) for p in points]
    good = [(x, y) for x, y in values if isinstance(x, (int,float))
            and isinstance(y, (int,float)) and math.isfinite(x) and math.isfinite(y)]
    if len(good) < 2:
        return f'<div class="empty-chart">{esc(title)}: 有效样本不足；缺失保持为空。</div>'
    w, h, l, r, top, bot = 720, 240, 58, 18, 22, 42
    xs=[x for x,_ in good]; ys=[y for _,y in good]
    xmax=max(xs) or 1; ymin=min(ys); ymax=max(ys); yrange=(ymax-ymin) or 1
    def xy(x,y): return l+(w-l-r)*x/xmax, top+(h-top-bot)*(1-(y-ymin)/yrange)
    seg=[]; current=[]
    for x,y in values:
        if not isinstance(x,(int,float)) or not math.isfinite(x) or y is None or not isinstance(y,(int,float)) or not math.isfinite(y):
            if current: seg.append(current); current=[]
        else: current.append(xy(x,y))
    if current: seg.append(current)
    paths=''.join('<polyline points="'+' '.join(f'{x:.1f},{y:.1f}' for x,y in line)+'"/>' for line in seg if len(line)>1)
    ticks=[]
    for i in range(5):
        x = l+(w-l-r)*i/4
        ticks.append(f'<text x="{x:.1f}" y="{h-24}" text-anchor="middle">{xmax*i/4:.2f}s</text>')
    for i in range(5):
        y=top+(h-top-bot)*i/4; val=ymax-(ymax-ymin)*i/4
        ticks.append(f'<line class="grid" x1="{l}" y1="{y:.1f}" x2="{w-r}" y2="{y:.1f}"/><text x="{l-7}" y="{y+4:.1f}" text-anchor="end">{val:.2f}</text>')
    marks=[]
    for phase in phases:
        x=phase.get('t_s')
        if isinstance(x,(int,float)) and 0 <= x <= xmax:
            px=l+(w-l-r)*x/xmax
            marks.append(f'<line class="phase" x1="{px:.1f}" y1="{top}" x2="{px:.1f}" y2="{h-bot}"/><text class="phase-label" x="{px+3:.1f}" y="{top+10}">{esc(phase["label"])}</text>')
    return (f'<svg class="series" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}"><title>{esc(title)}</title>'
            +''.join(ticks)+''.join(marks)+f'<g class="line">{paths}</g><text x="{w/2}" y="{h-8}" text-anchor="middle">相对时间（秒）</text><text x="8" y="15">{esc(unit)}</text></svg>')


def svg_task_points(groups: list[dict[str, Any]], *, title: str, unit: str) -> str:
    """Small-n raw points with source median/IQR; no sorting or rank encoding."""
    values = [v for group in groups for v in group.get("points", [])
              if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)]
    values += [v for group in groups for v in (group.get("median"),group.get("q1"),group.get("q3"))
               if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)]
    if not values:
        return f'<div class="empty-chart">{esc(title)}：无有效观测</div>'
    width, left, right, top, row_h = 760, 220, 24, 38, 52
    height = top + row_h * len(groups) + 26
    lo, hi = min(values), max(values)
    if lo == hi:
        pad = max(abs(lo) * .05, 1.0)
        lo, hi = lo-pad, hi+pad
    def px(v: float) -> float:
        return left + (width-left-right) * (v-lo)/(hi-lo)
    out = [f'<svg class="dots" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
           f'<title>{esc(title)} · raw points with median/IQR · {esc(unit)}</title>']
    for i, group in enumerate(groups):
        y = top + i*row_h
        out.append(f'<text x="{left-10}" y="{y-3}" text-anchor="end">{esc(group["label"])}</text>')
        q1, q3, median = group.get("q1"), group.get("q3"), group.get("median")
        if all(isinstance(v, (int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (q1,q3)):
            out.append(f'<line class="iqr" x1="{px(q1):.2f}" y1="{y}" x2="{px(q3):.2f}" y2="{y}"/>')
        if isinstance(median,(int,float)) and not isinstance(median,bool) and math.isfinite(median):
            out.append(f'<line class="median" x1="{px(median):.2f}" y1="{y-9}" x2="{px(median):.2f}" y2="{y+9}"/>')
        for j, val in enumerate(group.get("points", [])):
            if isinstance(val, (int,float)) and not isinstance(val,bool) and math.isfinite(val):
                cy = y + (j-(len(group["points"])-1)/2)*8
                out.append(f'<circle class="raw-point" cx="{px(val):.2f}" cy="{cy:.2f}" r="4"><title>{esc(group["label"])} raw point {j+1}: {fmt(val,4)} {esc(unit)}</title></circle>')
        if group.get("median") is not None or group.get("iqr") is not None:
            out.append(f'<text class="dot-stat" x="{left-10}" y="{y+17}" text-anchor="end">median {fmt(group.get("median"),4)} · IQR {fmt(group.get("iqr"),4)}</text>')
    out.append(f'<text x="{left}" y="{height-4}">{fmt(lo,3)} {esc(unit)}</text><text x="{width-right}" y="{height-4}" text-anchor="end">{fmt(hi,3)} {esc(unit)}</text></svg>')
    return ''.join(out)


def card(label: str, value: Any, note: str = "") -> str:
    return f'<div class="metric"><span>{esc(label)}</span><strong>{esc(fmt(value))}</strong><small>{esc(note)}</small></div>'


def office02_call_projection(row: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Cross-check accepted intervals by event ID; never pair messages by position."""
    spans: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("kind") in ("llm_request", "tool_call"):
            spans.setdefault(event["event_id"], []).append(event)
    calls = []
    for kind, items in (("llm_request", row["requests"]), ("tool_call", row["tools"])):
        for item in items:
            saved = spans.get(item["event_id"], [])
            opened = [e for e in saved if e.get("status") == "open"]
            closed = [e for e in saved if e.get("status") != "open"]
            if len(opened) != 1 or len(closed) != 1:
                raise ValueError(f"Call event pairing mismatch: {row['run_id']} {item['event_id']}")
            a, b = opened[0], closed[0]
            if (a.get("kind") != kind or b.get("kind") != kind
                    or a.get("clock_domain") != "system_monotonic"
                    or b.get("clock_domain") != "system_monotonic"
                    or a.get("t_monotonic_ns") != item["start_ns"]
                    or b.get("t_monotonic_ns") != item["end_ns"]
                    or item["end_ns"] < item["start_ns"]
                    or b.get("attrs", {}).get("ok") != item["ok"]):
                raise ValueError(f"Call interval differs from accepted analysis: {item['event_id']}")
            role = "request" if kind == "llm_request" else item["role"]
            name = "逻辑请求" if kind == "llm_request" else item["name"]
            if kind == "tool_call" and (a.get("attrs", {}).get("tool_name") != name
                                        or a.get("attrs", {}).get("role") != role):
                raise ValueError(f"Tool identity differs from accepted analysis: {item['event_id']}")
            calls.append({"event_id": item["event_id"], "role": role, "name": name,
                          "start_ns": item["start_ns"], "end_ns": item["end_ns"], "ok": item["ok"]})
    if len(spans) != len(calls):
        raise ValueError(f"Unaccounted saved call events: {row['run_id']}")
    finish = [e for e in events if e.get("kind") == "agent_action"
              and e.get("attrs", {}).get("action") == "finish"]
    if any(e.get("clock_domain") != "system_monotonic"
           or not _valid_counter(e.get("t_monotonic_ns")) for e in finish):
        raise ValueError(f"Finish clock unavailable: {row['run_id']}")
    return {"calls": sorted(calls, key=lambda c: c["start_ns"]),
            "finish_ns": [e["t_monotonic_ns"] for e in finish]}


def office02_sample_projection(raw: dict[str, Any]) -> dict[str, Any]:
    """Project the saved shared-container readings, with explicit invalid intervals."""
    projected = sample_projection(raw)
    points, previous = [], None
    origin = raw["samples"][0]["t_monotonic_ns"]
    intervals, memory_points = [], []
    previous_time = None
    for sample in raw["samples"]:
        t = sample.get("t_monotonic_ns")
        container = sample.get("container") or {}
        status = container.get("read_status") or {}
        same_scope = (sample.get("clock_domain") == "system_monotonic"
                      and container.get("scope_kind") == "agent_container"
                      and container.get("scope") == "agent_container")
        cpu = container.get("cpu_usage_usec")
        mem = container.get("mem_current_bytes")
        valid_time = _valid_counter(t) and (previous_time is None or t > previous_time)
        cpu_ok = (same_scope and valid_time and _valid_counter(cpu) and cpu >= 0
                  and status.get("cpuacct.usage", "").startswith("ok"))
        mem_ok = (same_scope and valid_time and _valid_counter(mem) and mem >= 0
                  and status.get("memory.usage_in_bytes", "").startswith("ok"))
        cores = None
        if cpu_ok and previous is not None:
            pt, pc = previous
            if t > pt and cpu >= pc:
                cores = (cpu-pc)/1e6/((t-pt)/1e9)
                intervals.append({"t_start_s": (pt-origin)/1e9, "t_end_s": (t-origin)/1e9,
                                  "average_cores": cores})
        if mem_ok:
            memory_points.append({"t_s": (t-origin)/1e9, "memory_current_mib": mem/1048576,
                                  "source": sample["role"]})
        points.append({"t_s": (t-raw["samples"][0]["t_monotonic_ns"])/1e9 if valid_time else None,
                       "cpu_cores": cores, "memory_mib": mem/1048576 if mem_ok else None})
        previous = (t, cpu) if cpu_ok else None
        previous_time = t if _valid_counter(t) else None
    projected["points"] = points
    projected["scope"] = "shared task container / agent_container"
    projected["curve_scope"] = {"scope_id": "agent_container", "scope_kind": "shared_task_container",
                                "boundary_start_ns": origin,
                                "boundary_end_ns": raw["samples"][-1]["t_monotonic_ns"],
                                "common_origin_ns": origin, "cpu_intervals": intervals,
                                "memory_points": memory_points}
    return projected


def office02_timeline(row: dict[str, Any], projection: dict[str, Any]) -> str:
    phases = row["time"]["phase"]
    origin = phases["harbor_start"]["start_monotonic_ns"]
    end = max(p["end_monotonic_ns"] for p in phases.values()
              if p.get("end_monotonic_ns") is not None)
    width, left, right, height = 900, 155, 24, 236
    def x(t):
        return left+(width-left-right)*(t-origin)/(end-origin)
    parts = [f'<svg class="call-timeline" viewBox="0 0 {width} {height}" role="img" '
             'aria-label="真实调用时间线"><title>同宿主 monotonic；事件 ID 配对</title>']
    for index, (key, label) in enumerate((("harbor_start", "start"), ("agent_setup", "setup"),
                                         ("agent", "Agent"), ("verifier", "verifier"),
                                         ("harbor_stop", "stop"), ("archive", "archive markers"))):
        p = phases[key]
        if p.get("start_monotonic_ns") is not None and p.get("end_monotonic_ns") is not None:
            a, b = x(p["start_monotonic_ns"]), x(p["end_monotonic_ns"])
            parts.append(f'<rect class="lifecycle" x="{a:.2f}" y="{26+index*4}" width="{max(b-a,.5):.2f}" height="4"><title>{label}</title></rect>')
            parts.append(f'<text x="{a:.2f}" y="{16+index%2*9}">{label}</text>')
    rows = {"request": (80, "请求"), "bootstrap": (124, "bootstrap"), "agent": (168, "自主工具")}
    for role, (y, label) in rows.items():
        parts.append(f'<text x="8" y="{y+5}">{label}</text>')
    for call in projection["calls"]:
        y = rows[call["role"]][0]
        a, b = x(call["start_ns"]), x(call["end_ns"])
        css = "failed-call" if call["ok"] is False else "saved-call"
        parts.append(f'<rect class="{css}" data-event-id="{esc(call["event_id"])}" x="{a:.2f}" y="{y-7}" width="{max(b-a,.5):.2f}" height="14">'
                     f'<title>{esc(call["role"])} · {esc(call["name"])} · ok={esc(call["ok"])} · '
                     f'{(call["start_ns"]-origin)/1e9:.6f}–{(call["end_ns"]-origin)/1e9:.6f}s</title></rect>')
        parts.append(f'<circle class="terminal-marker" cx="{b:.2f}" cy="{y}" r="2"><title>已保存终态 {esc(call["event_id"])}</title></circle>')
    for t in projection["finish_ns"]:
        parts.append(f'<line class="finish-marker" x1="{x(t):.2f}" x2="{x(t):.2f}" y1="60" y2="185"><title>finish · {(t-origin)/1e9:.6f}s</title></line>')
    for i in range(6):
        t = origin+(end-origin)*i/5
        parts.append(f'<text x="{x(t):.2f}" y="214" text-anchor="middle">{(t-origin)/1e9:.2f}s</text>')
    parts.append('<text x="450" y="234" text-anchor="middle">相对本 run harbor_start monotonic 原点（秒）</text></svg>')
    return ''.join(parts)


def office02_card(summary: dict[str, Any]) -> str:
    t = summary["totals"]
    return (f'<section class="card" id="office-repeat-02"><h2>DOCOPS-OFFICE-REPEAT-02 · 新采集口径</h2>'
            '<p>单批、固定任务、小样本；不代表 Office 总体，不与旧批或 Excel 单次验证合并。</p>'
            '<div class="grid metrics">' + ''.join(card(label, t[key]) for key, label in (
                ("independent_tasks", "固定任务"), ("runs", "运行（每任务三次）"),
                ("finish", "finish"), ("reward_1", "reward=1"), ("logical_requests", "逻辑请求"),
                ("agent_tools", "自主工具"), ("bootstrap_tools", "bootstrap"),
                ("bootstrap_ok_false", "bootstrap 失败"))) + '</div>'
            '<p>PPT bootstrap inspection：ok=false / AttributeError；错误返回已保存并进入上下文，'
            'Agent 继续使用 PPT 专用工具。自主工具与 reward 分列；reward=1 不证明异常无影响。'
            '具体抛错属性及失败影响尚未确认；<code>prs.slides[:max_items]</code>仅为静态候选位置。</p>'
            '<p>费用及实际 transport 尝试次数 unknown；token 不是账单，框架 cost=0 不是免费。'
            '新批次调用时间线和资源曲线见本地测量及独立运行详情。</p></section>')


def office02_task_plots(summary: dict[str, Any]) -> str:
    metrics = (
        ("attempt_wall_s", "attempt wall", "s", 1), ("window_s", "采样窗口", "s", 1),
        ("agent_wall_s", "Agent 阶段", "s", 1), ("request_union_s", "请求区间并集", "s", 1),
        ("bootstrap_union_s", "bootstrap 工具并集", "s", 1), ("agent_tool_union_s", "自主工具并集", "s", 1),
        ("verifier_wall_s", "verifier 阶段", "s", 1), ("harbor_stop_wall_s", "stop 阶段", "s", 1),
        ("agent_boundary_cpu_core_s", "Agent 共享容器 CPU（边界计数器）", "core-s", 1),
        ("verifier_boundary_cpu_core_s", "verifier 共享容器 CPU（边界计数器）", "core-s", 1),
        ("memory_current_peak_bytes", "memory.current 采样峰值", "MiB", 1048576),
        ("kernel_peak_bytes", "内核 memory peak（累计高水位）", "MiB", 1048576),
        ("host_rss_peak_bytes", "共享宿主批进程 RSS", "MiB", 1048576),
        ("io_read_bytes", "cgroup block-service read", "bytes", 1),
        ("io_write_bytes", "cgroup block-service write", "bytes", 1))
    sections = []
    for task, group in summary["by_task"].items():
        label = task.split("__", 1)[1].split("_", 1)[0].upper()
        charts, rows = [], []
        for key, title, unit, factor in metrics:
            stat = group["metrics"][key]
            def scale(v):
                return v/factor if isinstance(v, (int, float)) and not isinstance(v, bool) else None
            points = [scale(p["value"]) for p in stat["points"]]
            plot = {"label": label, "points": points,
                    **{k: scale(stat.get(k)) for k in ("median", "q1", "q3", "iqr")}}
            charts.append(svg_task_points([plot], title=f"REPEAT-02 {label} · {title}", unit=unit))
            rows.append([title, unit, ', '.join(fmt(p, 6) for p in points), stat["n"],
                         stat["missing_or_invalid"], fmt(plot["median"], 6), fmt(plot["iqr"], 6)])
        sequences = table(["run（r0/r1/r2 原始点对应）", "保存的自主工具顺序"],
                          [[r["run_id"], ' → '.join(r["sequence"])] for r in group["sequences"]])
        sections.append(f'<section class="card"><h3>REPEAT-02 · {esc(label)}</h3>{sequences}'
                        + table(["指标", "单位", "原始点", "有效 n", "缺失/异常", "median", "IQR"], rows)
                        + '<div class="grid two">' + ''.join(charts) + '</div></section>')
    return ''.join(sections)


def check_projection_input(root: Path, entry: dict[str, Any], section: str) -> dict[str, Any]:
    """Keep run evidence strict; report live documentation/source snapshot drift separately.

    This is a reading-pack check, never an execution/approval identity check.
    analysis_code, raw data, saved identities and other inputs remain mandatory.
    """
    rel = Path(entry['path'])
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError(f"REPEAT-02 source hash mismatch: {entry['path']}")
    path = root / rel
    mutable_context = section == 'inputs' and (
        (rel.parts[0] == 'docs' and rel.suffix == '.md') or
        (rel.parts[0] in ('src', 'scripts', 'tests') and rel.suffix == '.py'))
    matched = hash_matches(path, entry.get('sha256'), entry.get('bytes'))
    if not matched and not mutable_context:
        raise ValueError(f"REPEAT-02 source hash mismatch: {entry['path']}")
    return {'path': entry['path'], 'section': section,
            'kind': 'historical_source_context' if mutable_context else 'required_evidence',
            'expected_sha256': entry.get('sha256'), 'expected_bytes': entry.get('bytes'),
            'current_sha256': sha256(path) if path.is_file() else None,
            'current_bytes': path.stat().st_size if path.is_file() else None,
            'match': matched,
            'status': 'match' if matched else ('current_source_drift' if path.is_file() else 'historical_source_unavailable')}


def office02_provenance_notice(verification: dict[str, Any]) -> str:
    drift = [r for r in verification['input_checks'] if not r['match']]
    if not drift:
        return ''
    names = '、'.join(f'<code>{esc(r["path"])}</code>' for r in drift)
    return ('<p class="note provenance-drift">来源版本核验为 PARTIAL：实验数据、保存身份及分析产物仍严格核验；'
            f'{len(drift)} 项当前规范/采集源码与历史登记版本不同或缺失：{names}。'
            '历史源码版本一致性未通过；本页只投影已封存结果，不代表当前代码可复现旧执行身份。'
            '原登记哈希与当前哈希分别保存在 verification.json，未修改历史 manifest。</p>')


def load_office02(root: Path, manifest: dict[str, Any], summary: dict[str, Any],
                  consumed: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Do not confuse a changed live source file with corrupted immutable run evidence.
    input_checks = []
    for section in ("inputs", "analysis_code"):
        for entry in manifest_entries(manifest, section):
            path = root / entry["path"]
            check = check_projection_input(root, entry, section)
            input_checks.append(check)
            if path.is_file():
                role = "office02_verified_analysis_" + section if check['match'] else "current_source_context_not_historical_version"
                consumed.append(record(path, root, role))
    plan = load_json(root / "env/docops-office-repeat-02/plan-identity.json")
    frozen = load_json(root / "env/docops-office-repeat-02/frozen-identity.json")
    batch = load_json(root / "reports/resource/DOCOPS-OFFICE-REPEAT-02/batch-summary.json")
    approval = load_json(root / "reports/resource/DOCOPS-OFFICE-REPEAT-02/APPROVAL.json")
    identity = summary["identity_check"]["identity_sha256"]
    if (plan["identity"] != frozen["identity"]
            or any(d.get("identity_sha256") != identity for d in (plan, frozen, batch, approval))):
        raise ValueError("REPEAT-02 saved identity conflict")
    rows = load_lines(root / PACKAGES["office02"] / "per_run.jsonl")
    ids = summary["explicit_run_ids"]
    if ([r["run_id"] for r in rows] != ids or len(set(ids)) != len(ids)
            or [r["run_id"] for r in batch["results"]] != ids):
        raise ValueError("REPEAT-02 explicit run list conflict")
    details, verified_outputs = [], 0
    for row, result in zip(rows, batch["results"]):
        raw_path = root / row["source"]
        raw_manifest_path = raw_path.parent / "manifest.json"
        raw_manifest = load_json(raw_manifest_path)
        for entry in manifest_entries(raw_manifest, "outputs"):
            path = raw_path.parent / entry["path"]
            if not hash_matches(path, entry.get("sha256"), entry.get("bytes")):
                raise ValueError(f"REPEAT-02 raw output hash mismatch: {path}")
            consumed.append(record(path, root, "office02_verified_raw_output"))
            verified_outputs += 1
        raw = load_json(raw_path)
        if (any(d.get("identity_sha256") != identity for d in (row, raw, raw_manifest, result))
                or any(d.get("task_key") != row["task_key"] or d.get("round") != row["round"]
                       for d in (raw, raw_manifest, result))):
            raise ValueError(f"REPEAT-02 raw run identity conflict: {row['run_id']}")
        events_path = raw_path.parent / "agent/events.jsonl"
        measurement_path = raw_path.parent / "measurement.json"
        events = load_lines(events_path)
        measurement = load_json(measurement_path)
        timeline = office02_call_projection(row, events)
        projected = office02_sample_projection(raw)
        resources = row["resources"]
        to_mib = lambda k: resources[k]/1048576 if resources.get(k) is not None else None
        details.append({"id": row["run_id"], "cohort": "Office-02", "task_key": row["task_key"],
                        "task": row["task_key"].split("__", 1)[1].split("_", 1)[0].upper(),
                        "round": row["round"], "identity": identity, "termination": row["termination"],
                        "reward": row["reward"], "resolved": None, "request_count": row["request_count"],
                        "tool_count": row["agent_tool_count"], "bootstrap": row["bootstrap_tool_count"],
                        "attempt_wall_s": row["attempt_wall_s"], "cpu_core_s": resources["cpu_core_s"],
                        "mem_current_mib": to_mib("memory_current_peak_bytes"),
                        "kernel_peak_mib": to_mib("kernel_peak_bytes"), "host_rss_mib": to_mib("host_rss_peak_bytes"),
                        "cleanup": ', '.join(row["cleanup"]),
                        "archive": "verified" if result["archive_verified"] else "unverified",
                        "infra": json.dumps(row["infra"], ensure_ascii=False),
                        "response_model": ', '.join(sorted({r["response_model"] for r in row["requests"]})),
                        "request_model": ', '.join(sorted({r["request_model"] for r in row["requests"]})),
                        "samples": projected, "source": row["source"], "sequence": row["sequence"],
                        "analysis_manifest": PACKAGES["office02"] + "/manifest.json",
                        "raw_manifest": str(raw_manifest_path.relative_to(root)),
                        "event_source": str(events_path.relative_to(root)),
                        "measurement_source": str(measurement_path.relative_to(root)),
                        "measurement": row["measurement_saved_status"], "measurement_record": measurement,
                        "image_retention": result["image_retention_verified"],
                        "timeline": timeline, "accepted_row": row})
    return details, {"source_input_count": len(manifest_entries(manifest, "inputs")),
                     "input_checks": input_checks,
                     "source_provenance_status": "PARTIAL" if any(not r['match'] for r in input_checks) else "MATCH",
                     "raw_outputs_verified": verified_outputs, "identity_sha256": identity,
                     "saved_plan_frozen_structure_equal": True,
                     "identity_scope": "saved plan/frozen full structures, digest links and registered bytes; not a new execution identity",
                     "totals": summary["totals"], "by_task": summary["by_task"]}


def table(headers: list[str], rows: list[list[Any]]) -> str:
    head=''.join(f'<th>{esc(h)}</th>' for h in headers)
    body=''.join('<tr>'+''.join(f'<td>{esc(fmt(v))}</td>' for v in row)+'</tr>' for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def office02_detail(r: dict[str, Any], root: Path, output: Path, index: int) -> str:
    row, samples = r["accepted_row"], r["samples"]
    tools = table(["角色 / 工具", "活动", "事件 ID", "保存返回 ok", "共享容器窗口 CPU core-s"],
                  [[f'{t["role"]} / {t["name"]}', t["activity"], t["event_id"],
                    json.dumps(t["ok"]), t["shared_container_change"].get("cpu_core_s")] for t in row["tools"]])
    phases = table(["阶段", "保存的观测区间 s / marker span", "共享容器边界 CPU core-s"],
                   [[name, p.get("wall_s", p.get("event_span_s")),
                     row["phase_boundary_changes"].get(name, {}).get("cpu_core_s")]
                    for name, p in row["time"]["phase"].items()])
    metrics = ''.join(card(label, r[key], unit) for key, label, unit in (
        ("request_count", "逻辑请求", "实际 transport 次数 unknown"),
        ("tool_count", "自主工具", "不含 bootstrap"), ("bootstrap", "bootstrap", "另计"),
        ("measurement", "测量完整性", "声明观测范围"), ("reward", "reward", "官方 verifier"),
        ("termination", "Agent 终止", "与 reward 分列"), ("infra", "infra", "保存证据"),
        ("attempt_wall_s", "attempt wall", "s"), ("cpu_core_s", "共享容器 CPU", "core-s；来源验收值"),
        ("mem_current_mib", "memory.current 峰值", "MiB；采样观测"),
        ("kernel_peak_mib", "内核 peak", "MiB；累计高水位"), ("host_rss_mib", "共享宿主 RSS", "MiB；共享批进程")))
    failure = (f'<p class="note">bootstrap inspect_document：ok=false / AttributeError；'
               f'{row["bootstrap_error_tool_count"]} 次失败返回已保存并进入后续上下文。'
               'Agent 继续使用 PPT 专用工具，自主工具成功、最终 reward=1；具体抛错属性及反事实影响 unknown。'
               '<code>prs.slides[:max_items]</code>仅为静态候选，不是已证实根因。</p>'
               if row["bootstrap_error_tool_count"] else '')
    links = ' · '.join(report_link(root, output, path, label) for path, label in (
        (PACKAGES["office02"] + "/summary.md", "本批分析"), (r["analysis_manifest"], "分析 manifest"),
        (r["source"], "raw summary / samples"), (r["event_source"], "调用事件"),
        (r["measurement_source"], "measurement"), (r["raw_manifest"], "raw manifest")))
    return (f'<article class="run-panel" id="run-{index}" data-run-id="{esc(r["id"])}" style="display:none">'
            f'<h2>Office-02 · {esc(r["task"])} · {esc(r["id"])}</h2><div class="grid metrics">{metrics}</div>'
            f'<p>task <code>{esc(r["task_key"])}</code> · round {r["round"]} · identity <code>{esc(r["identity"])}</code><br>'
            f'请求模型：{esc(r["request_model"])}；响应 model：{esc(r["response_model"])}<br>'
            f'清理：{esc(r["cleanup"])}；镜像保留：{json.dumps(r["image_retention"])}；归档：{esc(r["archive"])}<br>'
            f'自主工具顺序：{esc(" → ".join(r["sequence"]))}</p>{failure}'
            f'<h3>真实调用时间线（事件 ID 配对）</h3>{office02_timeline(row, r["timeline"])}'
            f'<p>每个圆点是已保存终态，末次工具返回可回查：{esc(row["last_agent_tool_terminal"]["event_id"])}。'
            'finish 独立标记；生命周期与调用共享同宿主 monotonic 时钟。红色工具区间表示失败，不是 API 错误。</p>'
            f'{tools}{phases}<div class="grid two"><div><h3>共享任务容器 CPU 区间平均 core</h3>'
            f'{coding_resource_svg(samples["curve_scope"], "cpu", samples["phases"], css_class="office02-resource")}</div>'
            f'<div><h3>共享任务容器 memory.current（MiB）</h3>'
            f'{coding_resource_svg(samples["curve_scope"], "memory", samples["phases"], css_class="office02-resource")}</div></div>'
            f'<p class="note">{samples["sample_count"]} 个保存采样点，'
            f'{len(samples["curve_scope"]["cpu_intervals"])} 个有效CPU区间 / '
            f'{len(samples["curve_scope"]["memory_points"])} 个有效memory.current点，窗口 {fmt(samples["window_s"],6)}s；'
            '资源横轴原点为本run采样首点（与时间线 harbor_start 原点不同），阶段标记采用同域保存事件。'
            '0.5s目标采样，CPU为相邻有效累计差分的区间平均core（100%=1core），首点/缺读/回退/异常时间留空，'
            '不插值、不跨scope，汇总CPU仍采用分析值。工具窗口内共享容器变化不是单工具独占资源。'
            'memory.current、内核peak、宿主RSS不相加；宿主RSS不是每任务独立需求。</p>'
            f'<p>来源：{links}</p></article>')


def report_link(root: Path, html_dir: Path, rel: str, label: str) -> str:
    href=rel_report(html_dir, rel, root)
    if href is None:
        return f'<span class="missing">{esc(label)}（证据文件当前不可用）</span>'
    return f'<a href="{esc(href)}">{esc(label)}</a>'


def shell(title: str, content: str, active: str) -> str:
    nav=[("index.html","总览","home"),("public-traces.html","公开 trace","public"),("local-measurements.html","本地测量","local"),("run-details.html","运行详情","runs")]
    links=''.join(f'<a class="{"active" if key==active else ""}" href="{url}">{label}</a>' for url,label,key in nav)
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{esc(title)} · Agent Workload</title><link rel="stylesheet" href="assets/style.css"></head><body><header><a class="brand" href="index.html">Agent Workload <span>研究成果阅读包 v5</span></a><nav>{links}</nav></header><main><div class="eyebrow">离线阅读包 · 2026-10-11</div>{content}</main><footer>静态离线页面 · 本报告只投影既有分析，不重新分析实验数据。指标均附来源与范围说明。</footer></body></html>'''


def render_site(root: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing reading pack: {output}")
    pkg, consumed, checks = package_data(root)
    # All source-package output artifacts must match their registered hashes.
    failed=[c["package"] for c in checks if not c["outputs_pass"]]
    if failed:
        raise ValueError("Registered analysis output hash mismatch: " + ", ".join(failed))
    summaries={name:load_json(root/PACKAGES[name]/filename) for name,filename in {
        "swe": "summary.json", "swebench":"summary.json", "osworld":"summary.json",
        "macro":"summary.json", "coding":"summary.json", "link":"decision.json",
        "word":"summary.json", "office":"summary.json", "office02":"summary.json", "synthesis":"evidence_matrix.json"}.items()}
    state=load_json(root/"project_state.json")
    consumed.append(record(root/"project_state.json",root,"current_status_source"))
    task_path=root/"docs/current_task.md"
    consumed.append(record(task_path,root,"task_record_context"))

    # Explicit raw sample files used for the detail plots, each bound by its accepted analysis manifest.
    detail_runs=[]
    office_rows=load_lines(root/PACKAGES["office"]/"per_run.jsonl")
    office_manifest=pkg["office"]["manifest"]
    for row in office_rows:
        rid=row["run_id"]
        raw_rel=f'data/raw/generated/DOCOPS-OFFICE-REPEAT-01/{rid}/summary.json'
        declared=find_declared(office_manifest,raw_rel)
        raw_path=root/raw_rel
        if not declared or not raw_path.is_file() or sha256(raw_path)!=declared.get("sha256") or raw_path.stat().st_size!=declared.get("bytes"):
            raise ValueError(f"Office raw sample failed registered hash: {raw_rel}")
        raw=load_json(raw_path); projected=sample_projection(raw)
        detail_runs.append({"id":rid,"cohort":"Office","task":row["task_label"],"task_key":row["task_key"],"round":row["round"],"identity":row["identity_sha256"],"termination":row["termination"],"reward":row["reward"],"resolved":None,"request_count":len(row.get("requests",{}).get("items",[])),"tool_count":len(row.get("tool_sequence",[])),"attempt_wall_s":row["attempt_wall_s"],"cpu_core_s":row["resources"].get("container_cpu_core_s"),"mem_current_mib":(row["resources"].get("memory_current_sampled_peak_bytes") or 0)/(1024*1024) if row["resources"].get("memory_current_sampled_peak_bytes") is not None else None,"kernel_peak_mib":(row["resources"].get("kernel_memory_peak_bytes") or 0)/(1024*1024) if row["resources"].get("kernel_memory_peak_bytes") is not None else None,"host_rss_mib":None,"bootstrap":row["bootstrap_tool_counts"],"sequence":row["activity_sequence"],"cleanup":", ".join(row.get("cleanup",{}).get("results",[])) or "unknown","archive":"verified" if row.get("archive",{}).get("batch_archive_verified") else "unknown","infra":"failed" if row.get("infra_failures") else "no registered failure","response_model":"see batch response-model distribution","samples":projected,"source":raw_rel,"analysis_manifest":"reports/analysis/DOCOPS-OFFICE-REPEAT-01-characterization-v1/manifest.json","raw_manifest":f'data/raw/generated/DOCOPS-OFFICE-REPEAT-01/{rid}/manifest.json'})
        consumed.append(record(raw_path,root,"raw_sample_for_run_detail"))
    word_s=summaries["word"]
    for row in word_s["runs"]:
        raw_rel=f'data/raw/generated/{row["collection"]}/{row["run_id"]}/summary.json'
        declared=find_declared(pkg["word"]["manifest"],raw_rel)
        raw_path=root/raw_rel
        if not declared or not raw_path.is_file() or sha256(raw_path)!=declared.get("sha256") or raw_path.stat().st_size!=declared.get("bytes"):
            raise ValueError(f"Word raw sample failed registered hash: {raw_rel}")
        raw=load_json(raw_path); projected=sample_projection(raw)
        detail_extra=next((x for x in word_s["run_details"] if x["collection"]==row["collection"]),{})
        detail_runs.append({"id":row["run_id"],"cohort":"Word","task":"Word 001","task_key":row["collection"],"round":"—","identity":raw.get("identity_sha256"),"termination":row["termination"],"reward":row["reward"],"resolved":None,"request_count":row["model_calls"],"tool_count":row["tool_actions"],"attempt_wall_s":row["wall_s"],"cpu_core_s":row["container_cpu_core_s"],"mem_current_mib":row["memory_current_sampled_peak_bytes"]/(1024*1024),"kernel_peak_mib":row["kernel_memory_peak_bytes"]/(1024*1024),"host_rss_mib":row["host_agent_rss_sampled_peak_bytes"]/(1024*1024),"bootstrap":row["bootstrap_tool_counts"],"sequence":[],"sequence_note":"此两运行摘要仅保留分类计数，未登记工具时间顺序；不从字典顺序推造","stage_time":detail_extra.get("phase_durations_s",{}),"cleanup":"removed verified" if any(e.get("phase")=="removal_verified" and e.get("result")=="removed" for e in raw.get("events",[])) else "unknown","archive":"verified" if row.get("archive_verified") else "unknown","infra":"not represented in the two-run summary","response_model":json.dumps(detail_extra.get("response_model_counts",{}),ensure_ascii=False),"samples":projected,"source":raw_rel,"analysis_manifest":"reports/analysis/DOCOPS-WORD-RESOURCE-03-04-review-v1/manifest.json","raw_manifest":f'data/raw/generated/{row["collection"]}/{row["run_id"]}/manifest.json'})
        consumed.append(record(raw_path,root,"raw_sample_for_run_detail"))

    swe=summaries["swe"]; sb=summaries["swebench"]; osw=summaries["osworld"]; macro=summaries["macro"]
    coding=summaries["coding"]; office=summaries["office"]
    coding_batch_rel="reports/resource/P1-12/repeats/CODING-REPEAT-01/batch/manifest.json"
    coding_batch_path=root/coding_batch_rel
    coding_declared=find_declared(pkg["coding"]["manifest"],coding_batch_rel)
    if not coding_declared or not coding_batch_path.is_file() or sha256(coding_batch_path)!=coding_declared.get("sha256") or coding_batch_path.stat().st_size!=coding_declared.get("bytes"):
        raise ValueError("Coding batch identity manifest is not hash-bound by characterization manifest")
    coding_batch_summary_rel="reports/resource/P1-12/repeats/CODING-REPEAT-01/batch/summary.json"
    coding_batch_summary_path=root/coding_batch_summary_rel
    coding_summary_declared=find_declared(pkg["coding"]["manifest"],coding_batch_summary_rel)
    if not coding_summary_declared or not coding_batch_summary_path.is_file() or sha256(coding_batch_summary_path)!=coding_summary_declared.get("sha256") or coding_batch_summary_path.stat().st_size!=coding_summary_declared.get("bytes"):
        raise ValueError("Coding batch summary is not hash-bound by characterization manifest")
    coding_batch=load_json(coding_batch_path)
    consumed.extend([record(coding_batch_path,root,"coding_identity_manifest"),record(coding_batch_summary_path,root,"coding_batch_summary")])
    coding_attempts=load_json(coding_batch_summary_path).get("attempts",[])
    coding_rows={r["run_id"]:r for r in summaries["coding"].get("runs",[])}
    coding_errors=[]
    coding_raw_verified_file_count=0
    coding_manifest_inputs={x["path"]:x for x in manifest_entries(pkg["coding"]["manifest"],"inputs")}
    coding_identity=coding_batch.get("identity",{})
    coding_agent=coding_identity.get("agent",{})
    for attempt in coding_attempts:
        rid=attempt.get("run_id")
        row=coding_rows.get(rid)
        if row is None:
            coding_errors.append({"run_id":rid,"error":"run id absent from characterization summary"})
            continue
        if row.get("task") != attempt.get("instance_id"):
            coding_errors.append({"run_id":rid,"error":"task identity mismatch between batch and characterization",
                                  "batch_task":attempt.get("instance_id"),"analysis_task":row.get("task")})
            continue
        run_rel=row.get("run_dir","")
        run_dir=(root/run_rel).resolve()
        if not run_dir.is_relative_to(root.resolve()):
            coding_errors.append({"run_id":rid,"error":"raw path escapes repository"})
            continue
        batch_run_dir=Path(attempt.get("run_dir","")).resolve()
        if batch_run_dir != run_dir:
            coding_errors.append({"run_id":rid,"error":"run directory mismatch between batch and characterization",
                                  "batch_run_dir":str(batch_run_dir),"analysis_run_dir":str(run_dir)})
            continue
        raw_manifest_path=run_dir/"manifest.json"
        if not raw_manifest_path.is_file():
            coding_errors.append({"run_id":rid,"file":(Path(run_rel)/"manifest.json").as_posix(),"error":"raw manifest missing"})
            continue
        raw_manifest=load_json(raw_manifest_path)
        consumed.append(record(raw_manifest_path,root,"coding_raw_run_manifest"))
        raw_file_entries=raw_manifest.get("files",{})
        if not isinstance(raw_file_entries,dict) or not raw_file_entries:
            coding_errors.append({"run_id":rid,"file":(Path(run_rel)/"manifest.json").as_posix(),"error":"raw manifest has no file hash map"})
            continue
        raw_files_valid=True
        for raw_rel_file, raw_entry in raw_file_entries.items():
            rel_path=Path(raw_rel_file)
            file_path=(run_dir/rel_path).resolve()
            if not file_path.is_relative_to(run_dir):
                raw_files_valid=False
                coding_errors.append({"run_id":rid,"file":raw_rel_file,"error":"raw manifest path escapes run directory"})
                continue
            raw_hash=raw_entry.get("sha256") if isinstance(raw_entry,dict) else raw_entry
            actual_hash=sha256(file_path) if file_path.is_file() else None
            actual_bytes=file_path.stat().st_size if file_path.is_file() else None
            accepted_entry=coding_manifest_inputs.get((Path(run_rel)/rel_path).as_posix())
            raw_bytes = raw_entry.get("bytes") if isinstance(raw_entry, dict) else None
            matches=hash_matches(file_path, raw_hash, raw_bytes)
            if accepted_entry:
                matches=matches and actual_hash==accepted_entry.get("sha256") and actual_bytes==accepted_entry.get("bytes")
            if not matches:
                raw_files_valid=False
                coding_errors.append({"run_id":rid,"file":(Path(run_rel)/rel_path).as_posix(),"error":"raw manifest hash mismatch or missing file",
                    "raw_manifest_sha256":raw_hash,"analysis_manifest_sha256":accepted_entry.get("sha256") if accepted_entry else None,
                    "actual_sha256":actual_hash,"actual_bytes":actual_bytes})
            else:
                consumed.append(record(file_path,root,"coding_raw_manifest_verified_output"))
                coding_raw_verified_file_count += 1
        if not raw_files_valid:
            continue
        loaded={}; valid=True
        for filename in ("samples.json","events.jsonl"):
            file_path=run_dir/filename
            rel=(Path(run_rel)/filename).as_posix()
            raw_expected=raw_manifest.get("files",{}).get(filename)
            if isinstance(raw_expected,dict): raw_expected=raw_expected.get("sha256")
            registered=coding_manifest_inputs.get(rel)
            actual_hash=sha256(file_path) if file_path.is_file() else None
            actual_bytes=file_path.stat().st_size if file_path.is_file() else None
            matches=hash_matches(file_path, raw_expected)
            if filename == "samples.json" and not registered:
                matches = False
            if registered:
                matches=matches and actual_hash==registered.get("sha256") and actual_bytes==registered.get("bytes")
            if not matches:
                valid=False
                coding_errors.append({"run_id":rid,"file":rel,"error":"missing or hash mismatch",
                    "raw_manifest_sha256":raw_expected,"analysis_manifest_sha256":registered.get("sha256") if registered else None,
                    "actual_sha256":actual_hash,"actual_bytes":actual_bytes})
                continue
            consumed.append(record(file_path,root,"coding_raw_sample_or_stage_input"))
            loaded[filename]=file_path
        if not valid:
            continue
        try:
            samples_doc=load_json(loaded["samples.json"])
            event_rows=load_lines(loaded["events.jsonl"])
        except (OSError,ValueError,json.JSONDecodeError) as exc:
            coding_errors.append({"run_id":rid,"error":f"input parse error: {type(exc).__name__}"})
            continue
        try:
            coding_projection=coding_evidence_projection(samples_doc)
        except ValueError as exc:
            coding_errors.append({"run_id":rid,"file":(Path(run_rel)/"samples.json").as_posix(),
                                  "error":str(exc)})
            continue
        scope_projections=coding_projection["scopes"]
        agent_scope=scope_projections["agent_container"]["aggregate"]
        verifier_scope=scope_projections["verifier_container"]["aggregate"]
        common_origin=coding_projection["common_origin_ns"]
        run_window_s=max((x["boundary_end_ns"]-common_origin)/1e9 for x in scope_projections.values())
        phases=coding_phase_projection(event_rows,common_origin,run_window_s)
        for scope_projection in scope_projections.values():
            scope_projection["phases"] = phases
        budget=attempt.get("budget_usage") or {}
        detail_runs.append({"id":rid,"cohort":"Coding","task":row.get("task"),"task_key":row.get("task"),
            "round":attempt.get("round"),"identity":"see bound batch identity manifest",
            "termination":row.get("termination"),"resolved":row.get("resolved"),"reward":None,
            "request_count":budget.get("requests"),"tool_count":row.get("tools",{}).get("total_trajectory_calls"),
            "attempt_wall_s":row.get("attempt_wall_s"),"cpu_core_s":row.get("resources",{}).get("cpu_core_seconds"),
            "mem_current_mib":None,"kernel_peak_mib":(row.get("resources",{}).get("memory",{}).get("kernel_peak_bytes")/1048576
                if isinstance(row.get("resources",{}).get("memory",{}).get("kernel_peak_bytes"),(int,float)) else None),
            "host_rss_mib":None,"bootstrap":"not separately recorded in this Coding record",
            "sequence":row.get("tools",{}).get("category_sequence",[]),
            "cleanup":attempt.get("cleanup_status","unknown"),"archive":attempt.get("archive_status","unknown"),
            "infra":attempt.get("execution_status","unknown"),
            "response_model":f'{coding_agent.get("model_request_id","unknown")} · batch identity source',
            "samples":{"points":[],"phases":phases,"sample_count":0,"window_s":None},
            "coding_scopes":{"agent":agent_scope,"verifier":verifier_scope},
            "coding_resources":scope_projections,
            "source":(Path(run_rel)/"samples.json").as_posix(),
            "event_source":(Path(run_rel)/"events.jsonl").as_posix(),
            "raw_manifest":(Path(run_rel)/"manifest.json").as_posix(),
            "analysis_manifest":"reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/manifest.json",
            "batch_manifest":coding_batch_rel,"batch_summary":coding_batch_summary_rel,
            "characterization_summary":"reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/summary.md"})
        if agent_scope is None or verifier_scope is None:
            coding_errors.append({"run_id":rid,"file":(Path(run_rel)/"samples.json").as_posix(),"error":"agent/verifier scope missing"})
    batch_ids=[a.get("run_id") for a in coding_attempts]
    if len(batch_ids)!=9 or len(set(batch_ids))!=9 or set(batch_ids)!=set(coding_rows):
        coding_errors.append({"error":"expected nine unique matching ids from explicit batch summary and characterization output",
                              "batch_ids":batch_ids,"analysis_ids":sorted(coding_rows)})
    displayed_ids=[r["id"] for r in detail_runs]
    if len(displayed_ids)!=len(set(displayed_ids)):
        coding_errors.append({"error":"duplicate run ids in reading-pack detail selector"})
    detail_runs.sort(key=lambda r: ({"Coding":0,"Office":1,"Word":2}.get(r.get("cohort"),9),
                                    r.get("round") if isinstance(r.get("round"),int) else 99,
                                    r.get("id","")))
    office02 = summaries["office02"]
    new_details, office02_verification = load_office02(root, pkg["office02"]["manifest"], office02, consumed)
    detail_runs.extend(new_details)
    if len({r["id"] for r in detail_runs}) != len(detail_runs):
        raise ValueError("Duplicate reading-pack detail run ID")
    single_folder = root / "reports/resource/DOCOPS-MEASUREMENT-VALIDATE-01"
    single_manifest = load_json(single_folder / "VALIDATION-MANIFEST.json")
    if not all(x["match"] for x in check_report_outputs(root, single_folder, single_manifest)):
        raise ValueError("Single Excel validation output hash mismatch")
    single_validation = load_json(single_folder / "VALIDATION.json")
    consumed.extend(record(single_folder / name, root, "independent_single_validation")
                    for name in ("VALIDATION-MANIFEST.json", "VALIDATION.json"))
    cov=osw["coverage"]
    state_summary={"updated_at":state["updated_at"],"gates":state["gates"],"cpu_02":state.get("cpu_02",{}),
                   "replay":state.get("replay",{}),"public_summary":state.get("public_summary",[])}

    # Safe native interface projection: raw arbitrary keys can contain free text, so only retain bounded identifiers.
    native=swe.get("native_tool_counts",{})
    safe_native=[(k,v) for k,v in native.items() if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}",k)]
    safe_native=sorted(safe_native,key=lambda x:x[1],reverse=True)[:8]
    swe_activity=swe.get("activity_counts",{})
    selection=load_json(root/PACKAGES["swebench"]/"selection.json")
    split_by_submission={x["submission"]:x["split"] for x in selection.get("groups",[])}
    group_rows=[]
    for g,v in sb["groups"].items():
        group_rows.append([split_by_submission.get(g,"unknown"),g,v.get("n_analyzed"),v.get("format"),sum(v.get("interface_totals",{}).values()),v.get("submission_patch_present_n"),"无 trajectory evaluation"])
    candidate_rows=[]
    for role,items in swe.get("candidates",{}).get("roles",{}).items():
        for item in items[:3]:
            candidate_rows.append([role,item.get("task_id"),item.get("participant"),item.get("run_index"),item.get("value") if "value" in item else item.get("iqr")])
    osw_labels=cov.get("task_label_counts",{})
    osw_per_model=[[k,v] for k,v in cov.get("model_counts",{}).items()]
    macro_agent=macro["sources"]["AgentX"]["summary"]
    macro_applied=macro["sources"]["Applied Compute"]["summary"]

    synthesis=summaries["synthesis"]
    finding_cards=''.join(
        f'<article class="card"><h3>{esc(f["title"])}</h3><p>{esc(f["text"])}</p>'
        + ' '.join(report_link(root,output,p,"来源报告") for p in f["sources"])
        + '</article>' for f in synthesis["findings"])
    rq_table=table(["研究问题","当前覆盖","允许的结论","仍缺什么"],[
        [r["rq"]+"："+r["question"],r["status"],r["allowed_claim"],r["missing"]]
        for r in synthesis["matrix"]])
    next_task=synthesis["next_task"]

    overview=f'''<section class="hero"><div><p class="eyebrow">行为 × CPU/OS 资源特征</p><h1>从保存轨迹到本地运行测量</h1><p>本项目研究 Agent 的工作负载行为与 CPU/OS 资源特征；benchmark 是负载来源，不是模型排行榜。阅读包将公开轨迹与本地实验分开呈现，统计沿用已验收报告。</p><a class="button" href="public-traces.html">查看公开 trace</a> <a class="button secondary" href="local-measurements.html">查看本地测量</a></div><div class="hero-side"><span class="status-pill">当前 Gate：G2 / G3-R 未通过</span><p>CPU-02：暂停；监督器未安装、未批准。Replay：暂停。</p><p>状态取自当前 <code>project_state.json</code>，不由本阅读包重新裁定。</p></div></section>
    <section><h2>证据覆盖</h2><div class="grid metrics">{card("公开 SWE-rebench trajectories",swe['scope']['record_count'],"第三方 normalized corpus")}{card("OSWorld model×task 轨迹",osw['inputs']['trajectory_count'],"7 个模型；108 个任务 key")}{card("AgentX traces",macro_agent['trace_count'],"请求流量代理数据")}{card("本地 Office runs",office['n_runs'],"3 个 DocOps 任务 × 3 次")}</div><p class="note">任务数、轨迹数、重复数采用各来源自己的单位，不跨来源相加为总体样本量。</p></section>
    <section><h2>主要发现（限定于已登记数据）</h2><p>{esc(synthesis["stage"])}</p><div class="grid two">{finding_cards}</div></section>
    <section><h2>综合报告原有证据矩阵 · 六个原始 RQ</h2><p>更新于 {esc(synthesis["updated_at"])}；综合v2保持原报告时点口径；新采集批另列卡片和详情，不回写旧结论。本地资源已覆盖 Coding 与 Office 的有限 scope，不等于单工具特性或函数热点已完成。</p>{rq_table}{report_link(root,output,PACKAGES["synthesis"]+"/summary.md","当前综合报告 v2")}</section>
    <section class="card"><h2>综合报告原有建议（保留来源，非本轮新增任务）</h2><h3>{esc(next_task["id"])}：{esc(next_task["title"])}</h3><p>{esc(next_task["goal"])}</p><p class="note">{esc(next_task["boundary"])}</p><p>{esc(next_task["stop_condition"])}</p><p>{esc(next_task["alternatives"])}</p></section>
    <section><h2>研究材料</h2><div class="grid two"><article class="card"><h3>公开数据分析</h3><p>SWE-rebench、SWE-bench 原生格式子集、OSWorld、AgentX 请求流与 Applied Compute 模板。</p><a href="public-traces.html">打开公开 trace 分页 →</a></article><article class="card"><h3>本地资源测量</h3><p>修复后 Coding 重复、有限 CPU 区间链接、Word 单任务两个配置、三任务 DocOps Office 重复。</p><a href="local-measurements.html">打开本地测量分页 →</a></article></div></section>'''

    overview += office02_card(office02) + office02_provenance_notice(office02_verification) + '<p><a href="local-measurements.html#office-repeat-02">新批次原始点、阶段与资源 →</a></p>'
    public=f'''<section class="page-title"><p class="eyebrow">分来源呈现，不合并分母</p><h1>公开 trace 与 workload 模板</h1><p>这里只展示来源报告中的既有统计。第三方来源保持其来源标签；公开轨迹通常没有本地 CPU/内存观测。</p></section>
    <section class="card"><h2>SWE-rebench · 第三方 normalized Coding corpus</h2><div class="grid metrics">{card("trajectories",swe['scope']['record_count'])}{card("task",swe['scope']['task_count'])}{card("participant",swe['scope']['participant_count'])}{card("shards",swe['scope']['trajectory_shards'])}{card("tool calls",swe['association_totals']['call_event_count'])}{card("tool results",swe['association_totals']['result_event_count'])}</div><div class="grid two"><div><h3>保守活动分类</h3>{svg_bars(list(swe_activity.items()),title="SWE-rebench activity counts")}</div><div><h3>常见安全投影的原生接口</h3>{svg_bars(safe_native,title="SWE-rebench native tool interfaces")}</div></div><p>Unknown 活动 {fmt(swe_activity.get('Unknown'))}；1:1 ID 关联 {fmt(swe['association_totals'].get('one_to_one_id_count'))}，无 ID result {fmt(swe['association_totals'].get('missing_id_result_count'))}，仅 call ID {fmt(swe['association_totals'].get('only_call_id_count'))}。Evaluation 计数：{esc(json.dumps(swe.get('evaluation_status_counts',{}),ensure_ascii=False))}；终止标签：{esc(json.dumps(swe.get('termination_counts',{}),ensure_ascii=False))}。不同维度分列；无 CPU/内存证据。</p><h3>已有重复与工作量候选（非排名）</h3>{table(["候选角色","task","participant","run index","登记值"],candidate_rows)}<p class="note">候选只作后续选样线索；活动分类覆盖不均，不能比较 participant 的完整活动占比。</p>{report_link(root,output,"reports/analysis/SWE-REBENCH-behavior-v2/summary.md","完整结果与候选")}</section>
    <section class="card"><h2>SWE-bench 原生格式子集</h2><p>冻结索引 commit <code>{esc(selection.get('index_commit'))}</code>；Verified、Lite 与部分 Test 三组各取前 30 条，共 90 条。组内按 task ID 字典序选择，不是随机或代表性抽样；Test 来源组仅部分下载。</p>{table(["split","submission / harness 组","n","原生格式","接口调用总数","有 patch","evaluation"],group_rows)}<p>三个格式分开统计。保存的终止字段/过程结构不能替代 evaluation；本子集 trajectory 中没有 evaluation。各组任务集合不同，不将组间差异归因给 harness。</p>{report_link(root,output,"reports/analysis/SWEBENCH-subset-behavior-v1/summary.md","完整来源报告")}</section>
    <section class="card"><h2>OSWorld · task 语义与保存行为</h2><div class="grid metrics">{card("model×task",cov['trajectory_count'])}{card("task definitions",osw['inputs']['task_semantics_count'])}{card("models",len(cov['model_counts']))}{card("valid analyzability",cov['analysis_status_counts'].get('valid'),"partial 不是失败")}</div>{table(["模型来源标签","轨迹数","缺失 task"],[[m,n,", ".join(cov['missing_task_by_model'].get(m,[])) or "无"] for m,n in osw_per_model])}<div class="grid two"><div><h3>任务多标签计数（允许重叠）</h3>{svg_bars(list(osw_labels.items()),title="OSWorld task labels")}</div><div><h3>原生动作记录类别</h3>{svg_bars(list(cov['native_action_category_counts'].items()),title="OSWorld native action records")}</div></div><p>另有 command 源码静态调用节点，但不代表 GUI 实际执行次数；数百万静态节点受超长 action 文本影响。MiniMax-M3 才有 35,272 条 usage 调用记录。历史运行与当前 task 定义的 revision 绑定仍 unknown；无资源、动作耗时结论。</p>{report_link(root,output,"reports/analysis/OSWORLD-task-behavior-v3/summary.md","完整报告")}</section>
    <section class="card"><h2>AgentX 与 Applied Compute（分别呈现）</h2><div class="grid two"><div><h3>AgentX 请求流 proxy</h3><div class="grid metrics">{card("traces",macro_agent['trace_count'])}{card("主请求",macro_agent['main_request_count'])}{card("subagent 内部请求",macro_agent['subagent_inner_request_count'])}{card("请求输入 token median",macro_agent['request_input_tokens']['median'])}</div><p>公开发布的过滤/结构化 request-flow corpus，不是完整工具执行日志。记录时间仅按来源语义解释，不能当 CPU 时间。</p></div><div><h3>Applied Compute 派生模板</h3>{table(["模板","有效模板","turn median","初始 token median","工具阶段 latency median"],[[name,vals['valid_template_count'],vals['num_turns']['median'],vals['initial_prompt_tokens']['median'],vals['latency_s']['median']] for name,vals in macro_applied.items()])}<p>生产轨迹派生 workload 模板，不是原始 Agent 消息或真实 Office 工具操作。</p></div></div>{report_link(root,output,"reports/analysis/AGENTX-APPLIED-MACRO-v1/summary.md","完整宏观分析")}</section>'''

    coding_tasks=[]
    coding_point_groups={"wall":[],"cpu":[],"memory":[]}
    for task,v in coding["per_task"].items():
        wall=v["attempt_wall_s"]; cpu=v["agent_cpu_core_s"]; mem=v["agent_mem_kernel_peak_mib"]
        points=[r for r in coding["runs"] if r["task"]==task]
        walls=', '.join(fmt(r.get('attempt_wall_s')) for r in points)
        cpus=', '.join(fmt(r.get('resources',{}).get('cpu_core_seconds')) for r in points)
        mems=', '.join(fmt((r.get('resources',{}).get('memory',{}).get('kernel_peak_bytes') or 0)/(1024*1024) if r.get('resources',{}).get('memory',{}).get('kernel_peak_bytes') is not None else None) for r in points)
        coding_tasks.append([task,v["n_runs"],", ".join(f'{k}:{n}' for k,n in v["terminations"].items()),", ".join(f'{k}:{n}' for k,n in v["resolved"].items()),f"{walls}；median {fmt(wall['median'])} / IQR {fmt(wall['iqr'])}",f"{cpus}；median {fmt(cpu['median'])} / IQR {fmt(cpu['iqr'])}",f"{mems}；median {fmt(mem['median'])} / IQR {fmt(mem['iqr'])}"])
        coding_point_groups["wall"].append({"label":task,"points":[r.get("attempt_wall_s") for r in points],"median":wall.get("median"),"iqr":wall.get("iqr")})
        coding_point_groups["cpu"].append({"label":task,"points":[r.get("resources",{}).get("cpu_core_seconds") for r in points],"median":cpu.get("median"),"iqr":cpu.get("iqr")})
        coding_point_groups["memory"].append({"label":task,"points":[(r.get("resources",{}).get("memory",{}).get("kernel_peak_bytes")/1048576 if isinstance(r.get("resources",{}).get("memory",{}).get("kernel_peak_bytes"),(int,float)) else None) for r in points],"median":mem.get("median"),"iqr":mem.get("iqr")})
    office_groups={}
    for r in office_rows: office_groups.setdefault(r["task_label"],[]).append(r)
    office_rows_summary=[]
    office_columns=[("task","任务"),("n","n"),("sequence","三次操作顺序"),
        ("logical_requests","逻辑请求数：原始点 / median / IQR"),
        ("agent_tool_calls","Agent工具数：原始点 / median / IQR"),
        ("attempt_wall_s","attempt wall 秒：原始点 / median / IQR"),
        ("container_cpu_core_s","容器 CPU core-s：原始点 / median / IQR"),
        ("memory_current_sampled_peak_bytes","memory.current 采样峰值 MiB：原始点 / median / IQR"),
        ("kernel_memory_peak_bytes","内核 memory peak MiB：原始点 / median / IQR"),
        ("host_agent_rss_sampled_peak_bytes","共享批执行进程 RSS MiB：原始点 / median / IQR")]
    office_metric_columns=office_columns[3:]
    for task_key,task_stat in office.get("task_summaries",{}).items():
        task=task_stat["task_label"]; rs=sorted(office_groups.get(task,[]),key=lambda r:r.get("round",99))
        cell_by_name={"task":task,"n":task_stat.get("n",len(rs))}
        seqs=[]
        for run in rs:
            seqs.append(f'r{run.get("round","?")}: '+" → ".join(run.get("tool_sequence",[])))
        cell_by_name["sequence"]="\n".join(seqs)
        for metric_key,label in office_metric_columns:
            metric=task_stat.get("metrics",{}).get(metric_key,{})
            points=metric.get("points",[])
            vals=[p.get("value") for p in points if isinstance(p.get("value"),(int,float))]
            if metric_key in ("memory_current_sampled_peak_bytes","kernel_memory_peak_bytes","host_agent_rss_sampled_peak_bytes"):
                vals=[v/(1024*1024) for v in vals]
                med=(metric.get("median")/(1024*1024)) if metric.get("median") is not None else None
                iqr=(metric.get("iqr")/(1024*1024)) if metric.get("iqr") is not None else None
            else:
                med=metric.get("median"); iqr=metric.get("iqr")
            digits=6 if metric_key=="container_cpu_core_s" else (2 if "bytes" in metric_key else 2)
            cell_by_name[metric_key]=f"{', '.join(fmt(v,digits) for v in vals)}；median {fmt(med,digits)} / IQR {fmt(iqr,digits)}"
        office_rows_summary.append([cell_by_name[key] for key,label in office_columns])
    office_point_groups={"wall":[],"cpu":[],"memory":[]}
    for task_stat in office.get("task_summaries",{}).values():
        metrics=task_stat.get("metrics",{})
        for name,key in (("wall","attempt_wall_s"),("cpu","container_cpu_core_s"),("memory","memory_current_sampled_peak_bytes")):
            metric=metrics.get(key,{})
            factor=1048576 if name=="memory" else 1
            office_point_groups[name].append({"label":task_stat["task_label"],
                "points":[(p.get("value")/factor if isinstance(p.get("value"),(int,float)) else None) for p in metric.get("points",[])],
                "median":metric.get("median")/factor if isinstance(metric.get("median"),(int,float)) else None,
                "iqr":metric.get("iqr")/factor if isinstance(metric.get("iqr"),(int,float)) else None,
                "q1":metric.get("q1")/factor if isinstance(metric.get("q1"),(int,float)) else None,
                "q3":metric.get("q3")/factor if isinstance(metric.get("q3"),(int,float)) else None})
    word_rows=[[r["collection"],r["max_steps"],r["model_calls"],r["tool_actions"],r["termination"],r["reward"],r["wall_s"],r["container_cpu_core_s"],fmt(r["memory_current_sampled_peak_bytes"]/(1024*1024)),fmt(r["kernel_memory_peak_bytes"]/(1024*1024)),fmt(r["host_agent_rss_sampled_peak_bytes"]/(1024*1024))] for r in word_s["runs"]]
    coding_identity=coding_batch.get("identity",{}); coding_agent=coding_identity.get("agent",{}); coding_budget=coding_identity.get("budget_per_attempt",{})
    office_identity=office.get("identity",{}); office_model=office_identity.get("model",{}); office_attempt=office_identity.get("budget",{}).get("per_attempt",{})
    coding_points_html=(f'<h3>Coding：三次原始点（Agent scope）</h3><div class="grid two">'
        f'<div>{svg_task_points(coding_point_groups["wall"],title="Coding attempt wall by task",unit="s")}</div>'
        f'<div>{svg_task_points(coding_point_groups["cpu"],title="Coding Agent container CPU by task",unit="core-s")}</div>'
        f'<div>{svg_task_points(coding_point_groups["memory"],title="Coding Agent kernel memory peak by task",unit="MiB")}</div></div>')
    office_points_html=(f'<h3>Office：三次原始点</h3><div class="grid two">'
        f'<div>{svg_task_points(office_point_groups["wall"],title="Office attempt wall by task",unit="s")}</div>'
        f'<div>{svg_task_points(office_point_groups["cpu"],title="Office container CPU by task",unit="core-s")}</div>'
        f'<div>{svg_task_points(office_point_groups["memory"],title="Office memory.current sampled peak by task",unit="MiB")}</div></div>')
    local=f'''<section class="page-title"><p class="eyebrow">本地运行观测 · 不作跨 workload 排名</p><h1>Coding 与 DocOps 资源测量</h1><p>单位和统计范围沿用各已验收报告。每任务展示原始点或报告统计；三次重复仍是同一任务的重复，不等于三个独立任务。</p></section>
    <section class="card"><h2>P1-12 CODING-REPEAT-01 · characterization v3</h2><p>修复后链路的 3 task × 3 repeat。登记 harness：{esc(coding_agent.get('harness','—'))}；请求模型：{esc(coding_agent.get('model_request_id','—'))}；每 attempt 上限 {fmt(coding_budget.get('max_model_requests'))} requests、{fmt(coding_budget.get('max_steps'))} steps、{fmt(coding_budget.get('max_output_tokens_per_request'))} output tokens/request。identity 从批 manifest 读取，且被 characterization manifest 哈希绑定。表格和点图沿用来源报告原始点与median/IQR；终止类型独立保留。</p>{table(["Task","n","终止","resolved","attempt wall 原始点；median/IQR (s)","Agent CPU 原始点；median/IQR (core-s)","Agent kernel memory peak 原始点；median/IQR (MiB)"],coding_tasks)}{coding_points_html}<p class="note">版本修订：v2只读取 <code>scopes</code> 汇总，因而错误写成没有逐样本曲线；实际逐点资源保存在 <code>evidence.&lt;scope_id&gt;.samples</code>。v3 按同一 scope ID 分别投影 CPU 区间平均 core 与 memory.current 采样轨迹。来源总 CPU 仍沿用已验收报告汇总，不以展示曲线积分替代。费用 unknown。</p>{report_link(root,output,"reports/analysis/P1-12-CODING-REPEAT-01-characterization-v3/summary.md","Coding characterization v3")}</section>
    <section class="card"><h2>CODING-RESOURCE-LINK · 有限 CPU 区间分解</h2><p>在九次 Coding run 中，request-only 已观测区间的容器 CPU 差分为零（限该采样区间与计数器精度）；tool-only 区间为共享容器 CPU，不是工具独占 CPU。边界 mixed 区间不分摊。75.6% 工具调用短于 0.5 秒采样间隔，限制细粒度归因。</p>{report_link(root,output,"reports/analysis/CODING-RESOURCE-LINK-feasibility-v1/summary.md","区间分析与限制")}</section>
    <section class="card"><h2>DOCOPS-WORD-RESOURCE-03/04 · 单任务不同步数配置</h2><p>同一 Word task；03 max_steps=12，04 max_steps=40。不是受控重复，不能将差异归因于预算变化。两次 reward=0，所见资源属于未解决路径开销，不是成功完成成本。</p>{table(["Collection","max steps","请求","工具动作","终止","reward","attempt wall (s)","container CPU (core-s)","memory.current peak (MiB)","kernel peak (MiB)","宿主 RSS (MiB)"],word_rows)}<p>阶段采样边界依据见报告。顶级标题格式断言为首个失败。</p>{report_link(root,output,"reports/analysis/DOCOPS-WORD-RESOURCE-03-04-review-v1/summary.md","Word 03/04 分析")}</section>
    <section class="card"><h2>DOCOPS-OFFICE-REPEAT-01 · 3 个任务 × 3 次</h2><div class="grid metrics">{card("逻辑请求",office['logical_request_count'])}{card("Agent 工具动作",office['agent_tool_call_count'],"运行时重建计数")}{card("bootstrap / run",2,"metadata + document inspection；另计")}{card("finish / reward=1",f"{sum(office['termination_counts'].values())} / {sum(office['reward_counts'].values())}")}</div><p>请求模型 {esc(office_model.get('request_model','openai/deepseek-v4-flash'))}；响应记录 {esc(json.dumps(office.get('response_models',{}),ensure_ascii=False))}。冻结配置：DocOpsWordAgent 共用工具清单；每 attempt {fmt(office_attempt.get('max_steps'))} 步、{fmt(office_attempt.get('max_tokens_per_request'))} tokens/request、{fmt(office_attempt.get('cpu'))} CPU / {fmt(office_attempt.get('memory_gib'))} GiB、0.5s 采样。ARM64 适配镜像不等同官方 amd64。</p><p>批摘要旧派生计数为34次工具、6次 invalid/unknown；characterization 复核为37次工具、3次 invalid/unknown。页面采用最新修正结果，bootstrap 不并入 Agent 动作。</p>{table([label for key,label in office_columns],office_rows_summary)}{office_points_html}<p>三次顺序对应 round 0/1/2。工具返回按保存关联证据核验；不提供逐工具耗时。宿主 RSS 是共享批执行进程窗口观测，不是每个任务独立Agent的净内存成本。</p>{report_link(root,output,"reports/analysis/DOCOPS-OFFICE-REPEAT-01-characterization-v1/summary.md","Office characterization")}</section>
    <section class="card"><h2>运行级详情</h2><p>Coding {sum(r['cohort']=='Coding' for r in detail_runs)} 次、Office旧批 {sum(r['cohort']=='Office' for r in detail_runs)} 次、Office新批 {sum(r['cohort']=='Office-02' for r in detail_runs)} 次、Word {sum(r['cohort']=='Word' for r in detail_runs)} 次，共 {len(detail_runs)} 个显式 run。Coding 与 DocOps 均有已保存的采样观测；Coding按Agent/verifier scope分别展示。CPU 是采样区间平均 core，不是瞬时值；阶段共现不等于单工具独占资源归因，旧批未保存可靠逐工具起止；新REPEAT-02已有调用边界（客户端窗口，不是独占耗时）。</p><a class="button" href="run-details.html">选择一个 run →</a></section>'''

    new_run_links = ''.join(f'<li><a href="run-details.html#run-{detail_runs.index(r)}">'
                            f'{esc(r["task"])} · r{r["round"]} · {esc(r["id"])}</a></li>' for r in new_details)
    local += (office02_card(office02) + office02_provenance_notice(office02_verification) + '<p>'
              + report_link(root, output, PACKAGES["office02"] + "/summary.md", "REPEAT-02 分析报告")
              + ' · ' + report_link(root, output, PACKAGES["office02"] + "/manifest.json", "来源分析 manifest")
              + '</p><ul>' + new_run_links + '</ul>' + office02_task_plots(office02)
              + f'<p class="note">所有原始点与 n/median/IQR直接读取来源 by_task.metrics；{esc(office02["quantile_method"])}。'
              '任务分别统计，未用median比值生成逐run比例；新旧批次不合并，不作因果或模型排名。'
              '请求区间不是思考时间；工具时长包含客户端包装，阶段/工具窗口为共享容器。'
              'blkio不是完整文件系统I/O。archive只显示保存marker跨度，不冒称完整归档成本。</p>')
    local += (f'<section class="card" id="single-excel-validation"><h2>Excel 单次新采集验证（独立证据，不计入重复批次）</h2>'
              f'<p>run {esc(single_validation["run_id"])}；逻辑请求 {fmt(single_validation["requests"]["logical_started"])}；'
              f'自主工具 {fmt(single_validation["tools"]["agent"])} / bootstrap {fmt(single_validation["tools"]["bootstrap"])}；'
              f'reward {fmt(single_validation["task_result"]["reward"])}；终止 {esc(single_validation["agent_termination"])}。'
              '正常采集与镜像保留验收不等于异常路径已验证。</p>'
              + report_link(root, output, "reports/resource/DOCOPS-MEASUREMENT-VALIDATE-01/VALIDATION.json", "单次验证结果")
              + ' · ' + report_link(root, output, "reports/resource/DOCOPS-MEASUREMENT-VALIDATE-01/VALIDATION-MANIFEST.json", "单次验证 manifest") + '</section>')
    # Build detail selectors and static panels. Only the new measured batch has call timelines.
    options=''.join(f'<option value="{i}">{esc(r["cohort"])} · {esc(r["task"])} · {esc(r["id"])} · {esc(r["termination"])}</option>' for i,r in enumerate(detail_runs))
    panels=[]
    for i,r in enumerate(detail_runs):
        disp='block' if i==0 else 'none'
        sequence_text=' → '.join(r['sequence']) if r['sequence'] else r.get('sequence_note','not available')
        if r["cohort"]=="Coding":
            scope_cards=[]
            for scope_name,scope_label in (("agent","Agent container scope"),("verifier","Verifier container scope")):
                scope=r.get("coding_scopes",{}).get(scope_name) or {}
                to_mib=lambda key: (scope.get(key)/1048576 if isinstance(scope.get(key),(int,float)) else None)
                scope_cards.extend([card(f"{scope_label} wall",scope.get("wall_s"),"秒；各自容器scope"),
                    card(f"{scope_label} CPU",scope.get("cpu_core_seconds"),f"core-s · n={fmt(scope.get('n_samples'))}"),
                    card(f"{scope_label} sampled max",fmt(to_mib("memory_sampled_max_bytes")),"MiB；scope field"),
                    card(f"{scope_label} kernel peak",fmt(to_mib("memory_kernel_peak_bytes")),"MiB；scope field")])
            resolved_text="resolved=true" if r.get("resolved") is True else ("resolved=false" if r.get("resolved") is False else "resolved unknown")
            resources=r["coding_resources"]
            resource_plots=[]
            for kind,label in (("agent_container","Agent容器"),("verifier_container","verifier容器")):
                resource_plots.append(f'<h3>{label}资源采样</h3><div class="grid two">'
                    f'<div>{coding_scope_plot(resources[kind],"cpu",r["samples"]["phases"],r["source"])}</div>'
                    f'<div>{coding_scope_plot(resources[kind],"memory",r["samples"]["phases"],r["source"])}</div></div>')
            panel=f'''<article class="run-panel" id="run-{i}" style="display:{disp}"><h2>Coding · {esc(r['task'])} · {esc(r['id'])}</h2><div class="grid metrics">{card('逻辑请求',r['request_count'])}{card('工具调用',r['tool_count'])}{card('Agent termination',r['termination'])}{card('任务评估',resolved_text)}{card('attempt wall',r['attempt_wall_s'],'秒；分析报告字段')}{''.join(scope_cards)}</div><p>round {esc(r['round'])} · 配置来源：P1-12 batch identity manifest · 请求模型：{esc(r['response_model'])}<br>cleanup：{esc(r['cleanup'])} · archive：{esc(r['archive'])} · execution：{esc(r['infra'])}<br>工具行为顺序（分类序列，非时间轴）：{esc(sequence_text)}</p><h3>Agent / verifier 容器生命周期（单调时钟事件）</h3>{coding_lifecycle_svg(r['samples']['phases'])}{''.join(resource_plots)}<p class="note">Coding raw 的 <code>scopes</code> 是容器汇总；逐点值来自 <code>evidence.&lt;scope_id&gt;.samples</code>，并与同一 scope ID 的汇总配对。CPU总量沿用来源报告；图中为相邻有效累计读数的采样区间平均core（100% = 1 core，未按配额归一化）。memory.current原始点以MiB展示。boundary_start/end限定scope窗口；缺读、回退和非递增时间形成断口，不插值。Agent与verifier计数器及内存不拼接、不相加；生命周期标记不是工具耗时。</p><p>证据：{report_link(root,output,r['source'],'scope samples.json')} · {report_link(root,output,r['event_source'],'events.jsonl')} · {report_link(root,output,r['raw_manifest'],'raw manifest')} · {report_link(root,output,r['analysis_manifest'],'characterization manifest')} · {report_link(root,output,r['batch_manifest'],'batch manifest')} · {report_link(root,output,r['batch_summary'],'batch summary')} · {report_link(root,output,r['characterization_summary'],'characterization summary')}</p></article>'''
        elif r["cohort"] == "Office-02":
            panel = office02_detail(r, root, output, i)
        else:
            phase_text='；'.join(f"{p['label']} {fmt(p['t_s'],3)}s"+("（采样窗外）" if not p.get("in_sample_window") else "") for p in r['samples']['phases']) or '无登记阶段边界'
            panel=f'''<article class="run-panel" id="run-{i}" style="display:{disp}"><h2>{esc(r['cohort'])} · {esc(r['task'])} · {esc(r['id'])}</h2><div class="grid metrics">{card('逻辑请求',r['request_count'])}{card('Agent 工具动作',r['tool_count'])}{card('终止',r['termination'])}{card('resolved',r.get('resolved'))}{card('reward',r['reward'])}{card('attempt wall',r['attempt_wall_s'],'秒')}{card('容器 CPU',r['cpu_core_s'],'core-s')}{card('memory.current peak',r['mem_current_mib'],'MiB')}{card('kernel peak',r['kernel_peak_mib'],'MiB')}{card('host RSS',r['host_rss_mib'],'MiB；来源缺失不填零')}</div><p>任务/集合：<code>{esc(r['task_key'])}</code> · round {esc(r['round'])} · identity {esc(r['identity'] or '未登记')}<br>响应 model：{esc(r['response_model'])}<br>阶段边界（相对采样窗口首点，同一 monotonic 时钟）：{esc(phase_text)}<br>基础设施：{esc(r['infra'])} · 清理：{esc(r['cleanup'])} · 归档：{esc(r['archive'])}<br>bootstrap 单列：{esc(json.dumps(r['bootstrap'],ensure_ascii=False))}<br>行为序列：{esc(sequence_text)}</p><div class="grid two"><div><h3>容器 CPU 区间平均利用率（core）</h3>{chart_series(r['samples']['points'],'cpu_cores','CPU interval average cores','core',r['samples']['phases'])}</div><div><h3>memory.current 观测（MiB）</h3>{chart_series(r['samples']['points'],'memory_mib','memory.current','MiB',r['samples']['phases'])}</div></div><p class="note">{r['samples']['sample_count']} 个保存采样点；采样窗口 {fmt(r['samples']['window_s'])} 秒。边界标记不是工具边界；阶段共现不表示单工具独占资源。数据源：{report_link(root,output,r['source'],'本地 raw summary.json')}</p><p>来源：{report_link(root,output,r['raw_manifest'],'raw manifest')} · {report_link(root,output,r['analysis_manifest'],'analysis manifest')}</p></article>'''
        panels.append(panel)
    detail=f'''<section class="page-title"><p class="eyebrow">{len(detail_runs)} 个显式 run · Coding / Office / Word</p><h1>运行详情</h1><p>Office/Word展示已保存采样差分；Coding展示evidence中的Agent/verifier逐点资源观测。缺失留空。旧批工具顺序不映射为时间；新 REPEAT-02 使用真实调用起止事件 ID 时间线，不推导独占资源。</p></section><section class="card"><label for="run-select">选择运行</label><select id="run-select">{options}</select><span id="selection-status" class="muted" aria-live="polite"></span></section>{''.join(panels)}'''

    output.mkdir(parents=True)
    (output/"assets").mkdir()
    (output/"index.html").write_text(shell("项目总览",overview,"home"),encoding="utf-8")
    (output/"public-traces.html").write_text(shell("公开 trace",public,"public"),encoding="utf-8")
    (output/"local-measurements.html").write_text(shell("本地测量",local,"local"),encoding="utf-8")
    (output/"run-details.html").write_text(shell("运行详情",detail,"runs"),encoding="utf-8")
    css='''*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#172638;font:16px/1.58 system-ui,-apple-system,"Segoe UI",sans-serif}header{position:sticky;top:0;background:#10283f;color:#fff;padding:14px max(22px,calc((100vw - 1180px)/2));display:flex;justify-content:space-between;align-items:center;gap:20px;z-index:2}.brand{font-weight:750;color:white;text-decoration:none}.brand span{font-weight:400;color:#b8cada;margin-left:8px}nav{display:flex;gap:6px;flex-wrap:wrap}nav a{color:#d4e0ea;text-decoration:none;padding:8px 12px;border-radius:8px}nav a.active,nav a:hover{background:#244560;color:#fff}main{max-width:1180px;margin:34px auto;padding:0 22px}h1{font-size:clamp(2.1rem,5vw,3.8rem);line-height:1.08;margin:.25em 0}h2{font-size:1.55rem;margin-top:0}h3{font-size:1.1rem}section{margin:24px 0}.hero{background:linear-gradient(125deg,#dcebf4,#fff 65%);border:1px solid #d7e2ec;border-radius:22px;padding:clamp(24px,5vw,56px);display:grid;grid-template-columns:2fr 1fr;gap:30px}.hero p{max-width:760px}.hero-side{border-left:1px solid #bdd0de;padding:16px}.eyebrow{color:#3a718d;text-transform:uppercase;letter-spacing:.08em;font-size:.78rem;font-weight:700}.grid{display:grid;gap:14px}.grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.metrics{grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin:14px 0}.metric,.card{background:#fff;border:1px solid #dce5ec;border-radius:14px;padding:18px}.metric{display:flex;flex-direction:column;min-height:106px}.metric span,.metric small{color:#627588}.metric strong{font-size:1.35rem;margin:5px 0}.metric small{font-size:.77rem}.card h2{margin-bottom:8px}.note{background:#edf4f8;border-left:4px solid #5d91ab;padding:12px 14px;color:#43596c}.button{display:inline-block;background:#176789;color:white;text-decoration:none;border-radius:9px;padding:10px 16px;font-weight:650}.button.secondary{background:#dfeaf0;color:#24465c}.status-pill{display:inline-block;background:#fff1cc;color:#704c00;border:1px solid #e8ce85;border-radius:99px;padding:5px 12px;font-weight:700}.table-wrap{overflow:auto;margin:14px 0}table{border-collapse:collapse;width:100%;background:#fff;font-size:.91rem}th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #e2e9ef;vertical-align:top}th{background:#edf3f7;white-space:nowrap}td{white-space:pre-line}.bars,.series,.dots,.phase-timeline,.coding-resource{width:100%;height:auto;background:#fff;border:1px solid #e1e9ef;border-radius:10px}.bars text,.series text,.dots text,.phase-timeline text,.coding-resource text{font:12px system-ui,sans-serif;fill:#53687a}.bars rect{fill:#347f9e}.series .grid,.coding-resource .grid{stroke:#dbe4ea;stroke-width:1}.series .line polyline{fill:none;stroke:#167a9b;stroke-width:2}.series .phase,.coding-resource .phase{stroke:#cc8741;stroke-dasharray:4 4}.series .phase-label{font-size:9px;writing-mode:vertical-rl}.coding-resource .cpu-interval{stroke:#167a9b;stroke-width:2.4}.coding-resource .memory-point{fill:#167a9b;stroke:#fff;stroke-width:.7}.coding-resource .axis-tick{stroke:#53687a;stroke-width:1}.dots .raw-point{fill:#1c7d9b}.dots .median{stroke:#bf6d2f;stroke-width:2}.dots .iqr{stroke:#78a7ba;stroke-width:7;stroke-linecap:round}.dots .dot-stat{font-size:10px;fill:#6b7d8c}.phase-timeline .agent-phase{fill:#6aa8c1;opacity:.75}.phase-timeline .verifier-phase{fill:#e0a45e;opacity:.75}.phase-timeline .phase-edge{stroke:#24465c;stroke-width:1.2;stroke-dasharray:3 2}.coding-scope-plot p{font-size:.82rem;color:#52687a;overflow-wrap:anywhere}.empty-chart{padding:40px 16px;color:#617487;background:#f6f8fa;border:1px dashed #c5d0d9;border-radius:10px}.missing{color:#8a4b45}.muted{color:#63788a}.page-title{padding:20px 0}.run-panel{margin-top:18px}.run-panel code{overflow-wrap:anywhere}select{padding:10px;max-width:100%;font:inherit;border:1px solid #bbcbd6;border-radius:8px;background:white}label{font-weight:700;margin-right:10px}footer{border-top:1px solid #d8e1e8;padding:24px;text-align:center;color:#667a8a;margin-top:50px}a{color:#126589}code{font-size:.88em;background:#eef2f5;padding:2px 5px;border-radius:4px}@media(max-width:760px){header{position:static;display:block}nav{margin-top:12px}.hero,.grid.two{grid-template-columns:1fr}.hero-side{border-left:0;border-top:1px solid #bdd0de}}'''
    css += "\n.call-timeline{width:100%;height:auto;background:white;border:1px solid #dce5ec;border-radius:10px}.call-timeline text{font:11px system-ui;fill:#53687a}.call-timeline .lifecycle{fill:#a0b5c3}.saved-call{fill:#347f9e}.failed-call{fill:#ba6954}.terminal-marker{fill:#18394c}.finish-marker{stroke:#6b8551;stroke-width:2}.run-panel:target{scroll-margin-top:90px}\n"
    css += "\n.office02-resource{width:100%;height:auto;background:white;border:1px solid #dce5ec;border-radius:10px}.office02-resource text{font:12px system-ui;fill:#53687a}.office02-resource .grid{stroke:#dbe4ea;stroke-width:1}.office02-resource .phase{stroke:#cc8741;stroke-dasharray:4 4}.office02-resource .cpu-interval{stroke:#167a9b;stroke-width:2.4}.office02-resource .memory-point{fill:#167a9b;stroke:white;stroke-width:.7}.office02-resource .axis-tick{stroke:#53687a;stroke-width:1}\n"
    (output/"assets/style.css").write_text(css,encoding="utf-8")
    js='''(()=>{const s=document.getElementById("run-select");if(!s)return;const status=document.getElementById("selection-status");function show(){document.querySelectorAll(".run-panel").forEach((p,i)=>p.style.display=String(i)===s.value?"block":"none");status.textContent="显示第 "+(Number(s.value)+1)+" / "+s.options.length+" 个登记运行";}function fromHash(){const m=location.hash.match(/^#run-([0-9]+)$/);if(m&&Number(m[1])<s.options.length)s.value=String(Number(m[1]));show();}s.addEventListener("change",()=>{location.hash="run-"+s.value;show();});window.addEventListener("hashchange",fromHash);fromHash();})();'''
    (output/"assets/app.js").write_text(js,encoding="utf-8")
    # Attach only a tiny selector script to the details page; static pages need no runtime data fetch.
    details_path=output/"run-details.html"
    details_path.write_text(details_path.read_text(encoding="utf-8").replace("</body>","<script src=\"assets/app.js\"></script></body>"),encoding="utf-8")

    # Data summary also makes the verification scope machine-readable without copying raw event content.
    coding_sampling=[]
    for run in detail_runs:
        if run["cohort"] != "Coding":
            continue
        scope_results={}
        for kind, scope in run["coding_resources"].items():
            scope_results[kind]={"scope_id":scope["scope_id"],"scope_kind":scope["scope_kind"],
                "interval_target_s":scope["interval_target_s"],
                "boundary_start_ns":scope["boundary_start_ns"],"boundary_end_ns":scope["boundary_end_ns"],
                "window_s":scope["window_s"],"common_origin_ns":scope["common_origin_ns"],
                "saved_sample_count":scope["saved_sample_count"],"sample_gaps_ns_count":scope["sample_gaps_ns_count"],
                "sample_timestamps_ns":scope["sample_timestamps_ns"],"counts":scope["counts"],
                "observations":scope["observations"],
                "effective_cpu_interval_count":len(scope["cpu_intervals"]),
                "effective_memory_sample_point_count":scope["counts"]["memory_valid_sample_points"],
                "boundary_memory_point_count":scope["counts"]["memory_valid_boundary_points"],
                "cpu_intervals":scope["cpu_intervals"],"memory_points":scope["memory_points"],
                "aggregate_scope_summary":scope["aggregate"],"curve_status":scope["curve_status"]}
        coding_sampling.append({"run_id":run["id"],"samples_source":run["source"],
                                "events_source":run["event_source"],
                                "lifecycle_phases":run["samples"]["phases"],
                                "phase_clock_domain":"system_monotonic",
                                "scopes":scope_results})
    verification={"source_packages":checks,
                  "office02": {**office02_verification, "detail_count": len(new_details),
                      "runs": [{"run_id": r["id"], "anchor": f"run-{detail_runs.index(r)}",
                                "timeline": r["timeline"], "measurement_status": r["measurement"],
                                "sample_count": r["samples"]["sample_count"],
                                "valid_cpu_intervals": sum(p["cpu_cores"] is not None for p in r["samples"]["points"]),
                                "valid_memory_points": sum(p["memory_mib"] is not None for p in r["samples"]["points"]),
                                "scope": r["samples"]["scope"], "source": r["source"],
                                "event_source": r["event_source"], "measurement_source": r["measurement_source"],
                                "phase_boundaries": r["samples"]["phases"],
                                "last_tool_terminal": r["accepted_row"]["last_agent_tool_terminal"],
                                "image_retention": r["image_retention"]} for r in new_details]},
                  "single_excel_validation": {"run_id": single_validation["run_id"], "included_in_repeat_stats": False},
                  "browser_render_check": "not performed; no local browser executable or browser tool available",
                  "synthesis_source":PACKAGES["synthesis"]+"/evidence_matrix.json",
                  "research_question_count":len(synthesis["matrix"]),
                  "next_task_status":next_task["status"],
                  "status_source":"project_state.json","detail_run_count":len(detail_runs),
                  "coding_detail_count":sum(r["cohort"]=="Coding" for r in detail_runs),
                  "coding_raw_manifest_verified_file_count":coding_raw_verified_file_count,
                  "office_detail_count":sum(r["cohort"]=="Office" for r in detail_runs),
                  "word_detail_count":sum(r["cohort"]=="Word" for r in detail_runs),
                  "coding_detail_errors":coding_errors,
                  "coding_detail_integrity":"verified" if not coding_errors and sum(r["cohort"]=="Coding" for r in detail_runs)==9 else "incomplete",
                  "coding_sampling":coding_sampling,
                  "coding_sampling_revision":"v2 read only scopes summaries and incorrectly concluded no saved point series; v3 projects evidence.<scope_id>.samples by matching scope ID",
                  "historical_reference_checks":{c["package"]:c["historical_reference_checks"] for c in checks},
                  "historical_status_snapshot_checks":{c["package"]:c["historical_status_snapshot_checks"] for c in checks},
                  "office_table_column_count":len(office_columns),
                  "detail_runs":[{"run_id":r["id"],"anchor":f"run-{i}","source":r["source"],"sample_count":r["samples"]["sample_count"],"window_s":r["samples"]["window_s"]} for i,r in enumerate(detail_runs)],
                  "gates":state_summary["gates"],"cpu_02_status":state_summary["cpu_02"].get("current_status"),
                  "limitations":["Coding evidence samples are scope-level observations, not per-tool resource attribution","Public trace packages do not supply local resource observations","Source snapshot drift is preserved as a caveat","This renderer does not independently re-run analyses"]}
    (output/"verification.json").write_text(json.dumps(verification,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    # Manifest covers exact consumed files and generated outputs; it deliberately excludes itself.
    unique={x["path"]:x for x in consumed}
    outputs=[record(p,root,"reading_pack_output") for p in sorted(output.rglob("*")) if p.is_file() and p.name!="manifest.json"]
    manifest={"schema":"project-results-html-v5","generated_from":"fixed report set and synthesis-v2; no source analysis rerun",
              "inputs":sorted(unique.values(),key=lambda x:x["path"]),"outputs":outputs,
              "analysis_code":[record(Path(__file__).resolve(),root,"generator")],
              "notes":["Manifest does not self-hash.","Historical source snapshot checks are separate from experimental output integrity.","Displayed raw command text, prompts, credentials and document content are excluded."]}
    (output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"output":str(output),"pages":["index.html","public-traces.html","local-measurements.html","run-details.html"],"detail_runs":len(detail_runs),"source_checks":checks,"manifest":manifest}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--output",type=Path,default=None)
    args=parser.parse_args()
    root=args.root.resolve(); output=(args.output or (root/OUT_REL)).resolve()
    result=render_site(root,output)
    print(json.dumps({"output":result["output"],"pages":result["pages"],"detail_runs":result["detail_runs"],"input_files":len(result["manifest"]["inputs"]),"output_files":len(result["manifest"]["outputs"])},ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
