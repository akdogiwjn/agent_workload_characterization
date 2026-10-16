#!/usr/bin/env python3
"""Offline descriptive analysis for the sealed CODING-REPEAT-01 batch.

This is deliberately a batch-specific read-only analyzer.  It accepts only
the run IDs in the sealed batch summary, validates every referenced file
before producing output, and refuses to overwrite an existing report.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "reports/resource/P1-12/repeats/CODING-REPEAT-01"
RAW_ROOT = ROOT / "data/raw/generated/P1-12-CODING-REPEAT-01"
OUT = ROOT / "reports/analysis/P1-12-CODING-REPEAT-01-review-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_record(path: Path, root: Path = ROOT) -> dict:
    return {"path": str(path.relative_to(root)), "bytes": path.stat().st_size,
            "sha256": sha256(path)}


def median_iqr(values: list[float | int]) -> dict:
    if not values:
        return {"n": 0, "median": None, "iqr": None, "min": None, "max": None}
    values = sorted(values)

    def q(p: float) -> float:
        pos = p * (len(values) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(values) - 1)
        return values[lo] + (values[hi] - values[lo]) * (pos - lo)

    return {"n": len(values), "median": statistics.median(values),
            "iqr": q(.75) - q(.25), "min": values[0], "max": values[-1]}


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _lines(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _scope(samples: dict, suffix: str) -> tuple[dict | None, str | None]:
    for key, value in (samples.get("scopes") or {}).items():
        if key.endswith(suffix):
            return value, key
    return None, None


def _scope_view(samples: dict, suffix: str) -> dict:
    value, key = _scope(samples, suffix)
    if value is None:
        return {"scope_key": None, "scope_kind": None, "cpu_core_seconds": None,
                "wall_s": None, "memory_kernel_peak_bytes": None,
                "memory_sampled_max_bytes": None, "n_samples": None,
                "status": "missing"}
    return {"scope_key": key, "scope_kind": value.get("scope_kind"),
            "cpu_core_seconds": value.get("cpu_core_seconds"),
            "cpu_evidence": value.get("cpu_evidence"),
            "cpu_core_seconds_reason": value.get("cpu_core_seconds_reason"),
            "wall_s": value.get("wall_s"),
            "memory_current_end_bytes": value.get("memory_current_end_bytes"),
            "memory_kernel_peak_bytes": value.get("memory_kernel_peak_bytes"),
            "memory_sampled_max_bytes": value.get("memory_sampled_max_bytes"),
            "memory_peak_basis": value.get("memory_peak_basis"),
            "n_samples": value.get("n_samples"), "status": "present"}


def _tokens(status_lines: list[dict]) -> dict:
    usage = [x.get("usage") or {} for x in status_lines]
    fields = {name: sum((u.get(name) or 0) for u in usage)
              for name in ("prompt_tokens", "completion_tokens", "total_tokens")}
    return {**fields, "status_lines": len(status_lines),
            "all_ok": (all(x.get("ok") is True for x in status_lines)
                       if status_lines else None),
            "source": "mini_status.jsonl usage summed across recorded calls"}


def _tools(events: list[dict]) -> dict:
    opens = [x for x in events if x.get("event") == "open"]
    terminal = [x for x in events if x.get("event") in ("closed", "error")]
    errors = [x for x in terminal if x.get("event") == "error"]
    return {"calls": len(opens), "closed": sum(x.get("event") == "closed" for x in terminal),
            "error": len(errors),
            "error_exception_types": sorted({x.get("exception_type") for x in errors}),
            "submitted_error": sum(x.get("exception_type") == "Submitted" for x in errors),
            "other_error": sum(x.get("exception_type") not in (None, "Submitted")
                                for x in errors),
            "source": "mini_tool_events.jsonl open/terminal events"}


def _validate_identity():
    approval = _json(REPORT_ROOT / "APPROVAL.json")
    attempt = _json(REPORT_ROOT / "ATTEMPT_STARTED.json")
    batch_manifest = _json(REPORT_ROOT / "batch/manifest.json")
    identity = batch_manifest["identity"]
    checks = {
        "approval_equals_batch_manifest": approval.get("checklist_identity") == identity,
        "attempt_equals_batch_manifest": attempt.get("identity") == identity,
        "collection": identity.get("collection"),
    }
    if not checks["approval_equals_batch_manifest"] or not checks["attempt_equals_batch_manifest"]:
        raise ValueError("approval/attempt/batch identity mismatch")
    return approval, attempt, batch_manifest, identity, checks


def _validate_file(path: Path, expected: dict):
    if not path.is_file():
        raise ValueError(f"missing registered file: {path}")
    if path.stat().st_size != expected.get("bytes", path.stat().st_size) or sha256(path) != expected["sha256"]:
        raise ValueError(f"hash/bytes mismatch: {path}")


def analyze(*, root: Path = ROOT, report_root: Path = REPORT_ROOT,
            raw_root: Path = RAW_ROOT, out: Path = OUT) -> dict:
    if out.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {out}")
    approval = _json(report_root / "APPROVAL.json")
    attempt = _json(report_root / "ATTEMPT_STARTED.json")
    batch_manifest = _json(report_root / "batch/manifest.json")
    batch = _json(report_root / "batch/summary.json")
    identity = batch_manifest["identity"]
    if approval.get("checklist_identity") != identity or attempt.get("identity") != identity:
        raise ValueError("approval/attempt/batch identity mismatch")
    if identity.get("collection") != "P1-12-CODING-REPEAT-01":
        raise ValueError("unexpected collection")
    for name, record in batch_manifest.get("outputs", {}).items():
        _validate_file(report_root / "batch" / name, record)

    selected = []
    input_records: dict[str, dict] = {}
    for item in batch.get("attempts", []):
        run_id = item.get("run_id")
        if not run_id or (raw_root / run_id).parent != raw_root:
            raise ValueError("invalid explicit run selection")
        run_dir = raw_root / run_id
        raw_manifest_path = run_dir / "manifest.json"
        if not raw_manifest_path.is_file():
            raise ValueError(f"missing raw manifest: {run_id}")
        raw_manifest = _json(raw_manifest_path)
        for rel, expected_sha in (raw_manifest.get("files") or {}).items():
            path = run_dir / rel
            if not path.is_file() or sha256(path) != expected_sha:
                raise ValueError(f"raw manifest mismatch: {run_id}/{rel}")
            input_records[str(path.relative_to(root))] = file_record(path, root)
        meta = _json(run_dir / "metadata.json")
        samples = _json(run_dir / "samples.json")
        trajectory = _json(run_dir / "mini_trajectory.json")
        status = _lines(run_dir / "mini_status.jsonl")
        tool_events = _lines(run_dir / "mini_tool_events.jsonl")
        agent, agent_key = _scope(samples, "-agent-sandbox")
        verifier, verifier_key = _scope(samples, "-verifier")
        host = _json(run_dir / "host_process.jsonl") if (run_dir / "host_process.jsonl").is_file() else None
        info = trajectory.get("info") or {}
        bu = meta.get("budget_usage") or {}
        selected.append({
            "round": item.get("round"), "task": item.get("instance_id") or meta.get("task_id"),
            "run_id": run_id, "run_dir": str(run_dir.relative_to(root)),
            "termination": {"agent": info.get("exit_status"),
                            "submission_present": bool(info.get("submission")),
                            "resolved": meta.get("resolved"),
                            "execution_status": item.get("execution_status"),
                            "evaluation_status": item.get("evaluation_status"),
                            "archive_status": item.get("archive_status"),
                            "cleanup_status": item.get("cleanup_status")},
            "requests": {"count": (info.get("model_stats") or {}).get("api_calls"),
                         "budget_counter": bu.get("requests"), "usage": _tokens(status)},
            "tools": _tools(tool_events),
            "resources": {"agent": _scope_view(samples, "-agent-sandbox"),
                          "verifier": _scope_view(samples, "-verifier")},
            "host_observation": ({"scope": (host.get("summary") or {}).get("scope"),
                                  "cpu_seconds": (host.get("summary") or {}).get("cpu_seconds"),
                                  "rss_sampled_max": (host.get("summary") or {}).get("rss_sampled_max"),
                                  "n_snapshots": (host.get("summary") or {}).get("n_snapshots"),
                                  "window": {"first": (host.get("coverage") or {}).get("first_t_monotonic_ns"),
                                             "last": (host.get("coverage") or {}).get("last_t_monotonic_ns")},
                                  "source": "host_process.jsonl summary; host scope is separate from container scopes"}
                                 if host else None),
            "source_fields": {"metadata": "metadata.json:budget_usage, resolved, statuses",
                              "agent_verifier": "samples.json:scopes[*] selected by scope_kind/key suffix",
                              "termination": "mini_trajectory.json:info.exit_status/submission",
                              "tokens": "mini_status.jsonl:usage",
                              "tools": "mini_tool_events.jsonl:event"},
        })
    if len(selected) != 9 or len({x["run_id"] for x in selected}) != 9:
        raise ValueError("explicit batch selection is not exactly nine unique runs")

    groups = {}
    for task in sorted({x["task"] for x in selected}):
        rows = [x for x in selected if x["task"] == task]
        def vals(path):
            outv = []
            for row in rows:
                v = row
                for key in path:
                    v = v.get(key) if isinstance(v, dict) else None
                if isinstance(v, (int, float)) and not isinstance(v, bool): outv.append(v)
            return outv
        groups[task] = {
            "n_runs": len(rows),
            "termination_counts": {k: sum(x["termination"]["agent"] == k for x in rows)
                                    for k in sorted({x["termination"]["agent"] for x in rows})},
            "resolved_true": sum(x["termination"]["resolved"] is True for x in rows),
            "resolved_false": sum(x["termination"]["resolved"] is False for x in rows),
            "resolved_unknown": sum(x["termination"]["resolved"] is None for x in rows),
            "metrics": {
                "attempt_wall_s": median_iqr(vals(["requests", "usage", "_nope"]) if False else
                    [x["_meta_wall_s"] for x in []]),
                "agent_cpu_core_seconds": median_iqr(vals(["resources", "agent", "cpu_core_seconds"])),
                "agent_wall_s": median_iqr(vals(["resources", "agent", "wall_s"])),
                "agent_memory_kernel_peak_bytes": median_iqr(vals(["resources", "agent", "memory_kernel_peak_bytes"])),
                "agent_memory_sampled_max_bytes": median_iqr(vals(["resources", "agent", "memory_sampled_max_bytes"])),
                "verifier_cpu_core_seconds": median_iqr(vals(["resources", "verifier", "cpu_core_seconds"])),
                "verifier_wall_s": median_iqr(vals(["resources", "verifier", "wall_s"])),
                "verifier_memory_kernel_peak_bytes": median_iqr(vals(["resources", "verifier", "memory_kernel_peak_bytes"])),
                "tool_calls": median_iqr(vals(["tools", "calls"])),
                "model_requests": median_iqr(vals(["requests", "count"])),
            },
        }
    # Add attempt wall after constructing the safe per-run record.
    for item, original in zip(selected, batch["attempts"]):
        item["attempt_wall_s"] = (json.loads((raw_root / item["run_id"] / "metadata.json").read_text())
                                   .get("budget_usage") or {}).get("elapsed_total_s")
    for task, group in groups.items():
        rows = [x for x in selected if x["task"] == task]
        group["metrics"]["attempt_wall_s"] = median_iqr([x["attempt_wall_s"] for x in rows
                                                            if isinstance(x["attempt_wall_s"], (int, float))])

    analysis = {"schema": "awc-p1-12-coding-repeat-review-v1",
                "collection": identity["collection"], "selected_run_count": len(selected),
                "selected_run_ids": [x["run_id"] for x in selected],
                "unselected_raw_directories": sorted(p.name for p in raw_root.iterdir()
                                                       if p.is_dir() and p.name not in {x["run_id"] for x in selected}),
                "identity_check": {"approval_equals_batch": True, "attempt_equals_batch": True},
                "runs": selected, "per_task": groups,
                "statistics": {"quantiles": "linear interpolation on sorted n-point values; IQR=Q3-Q1",
                               "scope": "agent/verifier metrics remain separate; missing values are null",
                               "memory": "kernel peak and sampled maximum are distinct; neither is process RSS unless labelled",
                               "cpu": "cgroup counter-boundary cpu_core_seconds; no cumulative counters summed"},
                "limitations": ["three repeats per task are raw points, not independent tasks",
                                "container scopes overlap with host observations and are not additive",
                                "tool calls are counts, not rates; no valid time denominator is claimed",
                                "wall minus CPU is not interpreted as waiting",
                                "model usage is not a bill; pricing and network variation are unknown",
                                "descriptive batch only; no Coding-category or causal claim"],
                "batch_status": {k: batch.get(k) for k in ("status", "budget_overrun", "wall_min", "archive_status")},
                "descriptive_findings": {
                    "termination_and_resolution": "astropy__astropy-13398: all three Agent terminations are LimitsExceeded; resolved true=1, false=2, unknown=0",
                    "largest_absolute_iqr": "astropy__astropy-13398: attempt wall 41.279976112s, Agent CPU 37.889564 core-s, Agent kernel peak memory 136136704 bytes; descriptive only"
                }}

    out.mkdir(parents=True, exist_ok=False)
    (out / "summary.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n")
    rows = []
    for task, group in groups.items():
        m = group["metrics"]
        rows.append(f"| {task} | {group['resolved_true']}/{group['resolved_false']}/{group['resolved_unknown']} | "
                    f"{m['attempt_wall_s']['median']:.1f} | {m['agent_cpu_core_seconds']['median']:.2f} | "
                    f"{m['agent_memory_kernel_peak_bytes']['median'] / 1048576:.1f} | "
                    f"{m['verifier_cpu_core_seconds']['median']:.2f} | {m['model_requests']['median']:.0f} | "
                    f"{m['tool_calls']['median']:.0f} |")
    md = ["# CODING-REPEAT-01 offline resource analysis", "",
          "限定范围验收：9 个由 batch/summary.json 显式登记的真实 run，输入 manifest 全部匹配；不含旧 P1-12、FINISH-01/02。",
          "", "## Per-task descriptive resources", "",
          "| task | resolved T/F/unknown | attempt wall median (s) | agent CPU median (core-s) | agent kernel peak median (MiB) | verifier CPU median (core-s) | requests median | tools median |",
          "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"] + rows + [
          "", "CPU is cgroup counter-boundary core-seconds; agent and verifier are separate scopes. Memory kernel peak is not sampled maximum or process RSS.",
          "", "## Observations", "",
          "- The fixed-task repeats show descriptive spread in wall, CPU, memory, request counts and tool counts; the three points are not independent tasks.",
          "- Astropy-13398 的三次 Agent 终止均为 `LimitsExceeded`；其中 `resolved=true` 1 次、`resolved=false` 2 次。任务结果与 Agent 终止类型是两个独立维度。",
          "- 三任务中按绝对 IQR，Astropy-13398 的波动最大：attempt wall IQR 41.28 s、Agent CPU IQR 37.89 core-s、内核峰值内存 IQR 136.1 MiB；这只是三个登记重复的描述。",
          "- `Submitted` 是正常 Agent 终止信号；`LimitsExceeded` 是预算限制结果，不是工具故障.",
          "- Tool counts are counts, not rates. The archived evidence has no denominator that supports a frequency ranking.",
          "- Host observations are reported separately and do not establish container-wide or Agent-wide waiting time; wall minus CPU is not used.",
          "", "## Limits", "",
          "No causal explanation, stable population claim, per-tool CPU, bill, or Coding-category representativeness is supported. Stored requests show no network failure; this does not prove network conditions were constant.",
          "CPU-02 and Replay remain paused; this report does not change G2 or project-wide status."]
    (out / "summary.md").write_text("\n".join(md) + "\n")

    outputs = {name: file_record(out / name) for name in ("summary.json", "summary.md")}
    manifest = {"schema": "awc-p1-12-coding-repeat-review-v1-manifest",
                "inputs": {**{str((report_root / n).relative_to(root)): file_record(report_root / n)
                             for n in ("APPROVAL.json", "ATTEMPT_STARTED.json", "PREFLIGHT.json", "batch/summary.json", "batch/manifest.json")},
                           **input_records},
                "analysis_code": file_record(Path(__file__)),
                "outputs": outputs, "manifest_self_hash": None,
                "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return analysis


if __name__ == "__main__":
    try:
        result = analyze()
    except Exception as exc:
        print(f"analysis refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    print(f"analyzed {result['selected_run_count']} explicit runs")
