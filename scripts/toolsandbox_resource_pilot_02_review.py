#!/usr/bin/env python3
"""Offline, single-run review for TOOLSANDBOX-RESOURCE-PILOT-02."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = "TOOLSANDBOX-RESOURCE-PILOT-02"
RUN_ID = "20261012T091455Z-tsbpilot02"
IDENTITY = "3f855a9c70efff83e259093c147e95cd87b7915a7891f2128ecae64021a7ea7b"
TASK = "send_message_with_contact_content_cellular_off"
RAW_REL = Path("data/raw/generated") / COLLECTION / RUN_ID
REPORT_REL = Path("reports/resource") / COLLECTION
ENV_REL = Path("env") / "toolsandbox-resource-pilot-02"
OUTPUT_REL = Path("reports/analysis") / f"{COLLECTION}-review-v1"
TASK_SOURCE_REL = Path("env/toolsandbox-resource-pilot-01/source/tool_sandbox/scenarios/multiple_tool_call_scenarios.py")
EVALUATOR_SOURCE_REL = Path("env/toolsandbox-resource-pilot-01/source/tool_sandbox/common/evaluation.py")
EXEC_ENV_SOURCE_REL = Path("env/toolsandbox-resource-pilot-01/source/tool_sandbox/roles/execution_environment.py")
SCENARIO_BASE_SOURCE_REL = Path("env/toolsandbox-resource-pilot-01/source/tool_sandbox/scenarios/base_scenarios.py")
WORKER_REL = Path("src/agent_workload_characterization/runners/toolsandbox_worker.py")
HOST_READER_REL = Path("src/agent_workload_characterization/collectors/host_process.py")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_record(path: Path, label: str | None = None) -> dict:
    data = path.read_bytes()
    return {"path": label or path.relative_to(ROOT).as_posix(),
            "bytes": len(data), "sha256": sha256(data)}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_inputs(root: Path = ROOT) -> dict:
    raw = root / RAW_REL
    report_dir = root / REPORT_REL
    env_dir = root / ENV_REL
    raw_manifest_path = raw / "manifest.json"
    outer_manifest_path = report_dir / "manifest.json"
    raw_manifest = read_json(raw_manifest_path)
    outer = read_json(outer_manifest_path)
    plan = read_json(env_dir / "plan-identity.json")
    frozen = read_json(env_dir / "frozen-identity.json")
    source_manifest = read_json(env_dir / "source-manifest.json")
    approval = read_json(report_dir / "APPROVAL.json")
    run_report = read_json(report_dir / "run-report.json")

    require(raw_manifest.get("identity_sha256") == IDENTITY and raw_manifest.get("run_id") == RUN_ID,
            "raw manifest identity/run mismatch")
    require(outer.get("identity_sha256") == IDENTITY and outer.get("run_id") == RUN_ID,
            "outer manifest identity/run mismatch")
    require(plan == frozen, "plan and frozen identity structures differ")
    identity_body = frozen.get("identity")
    require(isinstance(identity_body, dict), "frozen identity body missing")
    actual_digest = sha256(json.dumps(identity_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
    require(actual_digest == IDENTITY and frozen.get("identity_sha256") == IDENTITY,
            "frozen identity digest mismatch")
    require(approval.get("identity_sha256") == IDENTITY, "approval identity mismatch")
    require(run_report.get("identity_sha256") == IDENTITY and run_report.get("run_id") == RUN_ID,
            "run report identity mismatch")

    raw_entries = raw_manifest.get("files", [])
    listed = {entry["path"]: entry for entry in raw_entries}
    require(len(listed) == len(raw_entries), "duplicate raw manifest path")
    actual_files = {p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file() and p != raw_manifest_path}
    require(actual_files == set(listed), "raw file set differs from raw manifest")
    raw_records = []
    for rel, entry in sorted(listed.items()):
        path = raw / rel
        rec = file_record(path, (RAW_REL / rel).as_posix())
        require(rec["bytes"] == entry["bytes"] and rec["sha256"] == entry["sha256"], f"raw hash mismatch: {rel}")
        raw_records.append(rec)

    for group in ("inputs", "outputs"):
        for entry in outer.get(group, []):
            path = root / entry["path"]
            require(path.is_file(), f"outer manifest path missing: {entry['path']}")
            rec = file_record(path, entry["path"])
            require(rec["bytes"] == entry["bytes"] and rec["sha256"] == entry["sha256"],
                    f"outer manifest hash mismatch: {entry['path']}")
    require(not any(entry.get("path") == outer_manifest_path.relative_to(root).as_posix()
                    for entry in outer.get("outputs", [])), "outer manifest self-hashes")

    start = read_json(raw / "ATTEMPT_STARTED.json")
    completed = read_json(raw / "ATTEMPT_COMPLETED.json")
    require(start.get("identity_sha256") == IDENTITY and completed.get("identity_sha256") == IDENTITY,
            "attempt marker identity mismatch")
    require(start.get("run_id") == RUN_ID and completed.get("run_id") == RUN_ID,
            "attempt marker run mismatch")

    # The run's frozen file list is the historical execution identity evidence.
    # Compare current files for drift, but do not rewrite or invalidate the archive.
    code_checks = []
    for entry in identity_body.get("code_and_runtime_files", []):
        path = root / entry["path"]
        if not path.is_file():
            code_checks.append({"path": entry["path"], "matches_frozen": False, "reason": "missing_now"})
            continue
        current = file_record(path, entry["path"])
        code_checks.append({"path": entry["path"], "matches_frozen": current["bytes"] == entry["bytes"] and current["sha256"] == entry["sha256"]})
    code_match = all(item["matches_frozen"] for item in code_checks)
    source_files = {entry["path"]: entry for entry in source_manifest.get("files", [])}
    snapshot_checks = []
    for rel in ("tool_sandbox/scenarios/multiple_tool_call_scenarios.py",
                "tool_sandbox/common/evaluation.py", "tool_sandbox/roles/execution_environment.py",
                "tool_sandbox/scenarios/base_scenarios.py"):
        expected = source_files.get(rel)
        path = root / "env/toolsandbox-resource-pilot-01/source" / rel
        require(expected is not None and path.is_file(), f"frozen task source manifest entry missing: {rel}")
        actual = file_record(path, rel)
        require(actual["bytes"] == expected["bytes"] and actual["sha256"] == expected["sha256"],
                f"frozen task source snapshot hash mismatch: {rel}")
        snapshot_checks.append({"path": rel, "matches_source_manifest": True,
                               "bytes": actual["bytes"], "sha256": actual["sha256"]})
    require(source_manifest.get("origin_commit") == "165848b9a78cead7ca7fe7c89c688b58e6501219",
            "source manifest commit mismatch")
    require((root / TASK_SOURCE_REL).is_file() and (root / EVALUATOR_SOURCE_REL).is_file() and
            (root / EXEC_ENV_SOURCE_REL).is_file() and (root / SCENARIO_BASE_SOURCE_REL).is_file(),
            "frozen static source evidence missing")

    # All files listed by both manifests, plus identity and static source evidence,
    # are part of the analysis input set. No directory discovery adds a run.
    inputs = [file_record(raw_manifest_path, (RAW_REL / "manifest.json").as_posix()),
              file_record(outer_manifest_path, (REPORT_REL / "manifest.json").as_posix()),
              file_record(report_dir / "APPROVAL.json", (REPORT_REL / "APPROVAL.json").as_posix()),
              file_record(report_dir / "run-report.json", (REPORT_REL / "run-report.json").as_posix()),
              file_record(env_dir / "plan-identity.json", (ENV_REL / "plan-identity.json").as_posix()),
              file_record(env_dir / "frozen-identity.json", (ENV_REL / "frozen-identity.json").as_posix()),
              file_record(env_dir / "source-manifest.json", (ENV_REL / "source-manifest.json").as_posix())]
    inputs.extend(raw_records)
    for rel in (TASK_SOURCE_REL, EVALUATOR_SOURCE_REL, EXEC_ENV_SOURCE_REL, SCENARIO_BASE_SOURCE_REL,
                WORKER_REL, HOST_READER_REL):
        inputs.append(file_record(root / rel, rel.as_posix()))
    return {"raw": raw, "report_dir": report_dir, "env_dir": env_dir,
            "raw_manifest": raw_manifest, "outer_manifest": outer,
            "plan": plan, "frozen": frozen, "approval": approval,
            "run_report": run_report, "raw_records": raw_records,
            "inputs": sorted({r["path"]: r for r in inputs}.values(), key=lambda x: x["path"]),
            "current_code_matches_frozen": code_match, "current_code_checks": code_checks,
            "source_manifest": source_manifest, "source_snapshot_checks": snapshot_checks}


def _pair_spans(events: list[dict]) -> tuple[list[dict], dict]:
    opened: dict[tuple[str, str], dict] = {}
    terminal_counts: dict[tuple[str, str], int] = {}
    duplicate_open, orphan_terminal, invalid_time, duplicate_terminal = [], [], [], []
    spans = []
    for event in events:
        key = (str(event.get("kind")), str(event.get("event_id")))
        status = event.get("status")
        t = event.get("t_monotonic_ns")
        if not isinstance(t, int) or isinstance(t, bool):
            invalid_time.append(key[1]); continue
        if status == "open":
            if key in opened:
                duplicate_open.append(key[1]); continue
            opened[key] = event
        elif status in ("closed", "error"):
            terminal_counts[key] = terminal_counts.get(key, 0) + 1
            if terminal_counts[key] > 1:
                duplicate_terminal.append(key[1]); continue
            start = opened.get(key)
            if start is None:
                orphan_terminal.append(key[1]); continue
            t0 = start["t_monotonic_ns"]
            if t < t0:
                invalid_time.append(key[1]); continue
            spans.append({"event_id": key[1], "kind": key[0], "status": status,
                          "start_ns": t0, "end_ns": t, "duration_s": (t-t0)/1e9,
                          "open": start, "terminal": event,
                          "attrs": start.get("attrs", {}), "terminal_attrs": event.get("attrs", {})})
    unclosed = [{"kind": k[0], "event_id": k[1], "start_ns": v.get("t_monotonic_ns"),
                 "attrs": v.get("attrs", {})} for k, v in opened.items()
                if terminal_counts.get(k, 0) == 0]
    return spans, {"duplicate_open": duplicate_open, "duplicate_terminal": duplicate_terminal,
                   "orphan_terminal": orphan_terminal, "invalid_time": invalid_time,
                   "unclosed": unclosed}


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out = []
    for start, end in sorted((a, b) for a, b in intervals if b >= a):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def _intersect(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out = []
    for x0, x1 in _merge(a):
        for y0, y1 in _merge(b):
            lo, hi = max(x0, y0), min(x1, y1)
            if hi > lo: out.append((lo, hi))
    return _merge(out)


def _duration(intervals: list[tuple[int, int]]) -> float:
    return sum(b-a for a, b in _merge(intervals)) / 1e9


def _partition(window: tuple[int, int], req: list[tuple[int, int]], batch: list[tuple[int, int]]) -> dict:
    lo, hi = window
    if hi < lo: raise ValueError("negative observation window")
    req = _intersect(_merge(req), [(lo, hi)])
    batch = _intersect(_merge(batch), [(lo, hi)])
    both = _intersect(req, batch)
    req_only = _duration(req) - _duration(both)
    batch_only = _duration(batch) - _duration(both)
    overlap = _duration(both)
    window_s = (hi-lo)/1e9
    uncovered = window_s - req_only - batch_only - overlap
    return {"window_s": window_s, "request_only_s": req_only, "batch_only_s": batch_only,
            "overlap_s": overlap, "uncovered_s": uncovered,
            "residual_s": window_s-(req_only+batch_only+overlap+uncovered)}


def _sample_resources(samples: list[dict], spans: list[dict], boundaries: list[dict], clk_tck: int) -> dict:
    if not samples:
        return {"sample_count": 0, "cpu_ticks_delta": None, "rss_peak_bytes": None}
    # Preserve JSONL order: sorting would hide a saved timestamp regression.
    times = [s.get("t_monotonic_ns") for s in samples]
    statuses = [s.get("read_status", {}) for s in samples]
    bad_sample = [i for i, (s, st) in enumerate(zip(samples, statuses))
                  if not isinstance(s.get("cpu_ticks"), int) or st.get("stat") != "ok"]
    regressions, nonpositive = [], []
    valid_deltas = []
    for i in range(1, len(samples)):
        prev, cur = samples[i-1], samples[i]
        t0, t1 = times[i-1], times[i]
        if not isinstance(t0, int) or not isinstance(t1, int) or t1 <= t0:
            nonpositive.append(i); continue
        if i-1 in bad_sample or i in bad_sample:
            continue
        dticks = cur["cpu_ticks"]-prev["cpu_ticks"]
        if dticks < 0:
            regressions.append(i); continue
        valid_deltas.append((i, t0, t1, dticks))
    rss_values = [s.get("rss_bytes") for s in samples if isinstance(s.get("rss_bytes"), int) and s.get("read_status", {}).get("status") == "ok"]
    io_keys = ("rchar", "wchar", "read_bytes", "write_bytes")
    io = {}
    for key in io_keys:
        vals = [s.get("process_io", {}).get(key) for s in samples]
        io[key] = (vals[-1]-vals[0] if len(vals) == len(samples) and all(isinstance(v, int) for v in vals)
                   and vals[-1] >= vals[0] else None)
    gaps = [(times[i]-times[i-1])/1e9 for i in range(1,len(times)) if isinstance(times[i],int) and isinstance(times[i-1],int) and times[i]>times[i-1]]
    phases = {b.get("phase"): b for b in boundaries}
    phase_ranges = [("initialization_setup", "worker_start", "play_begin"),
                    ("play", "play_begin", "play_end"),
                    ("play_to_evaluation_gap", "play_end", "evaluate_begin"),
                    ("evaluation", "evaluate_begin", "evaluate_end"),
                    ("worker_tail", "evaluate_end", "worker_end")]
    phase_cpu = {}
    for name, a, b in phase_ranges:
        x, y = phases.get(a), phases.get(b)
        if not x or not y or not isinstance(x.get("cpu_ticks"), int) or not isinstance(y.get("cpu_ticks"), int):
            phase_cpu[name] = None; continue
        d = y["cpu_ticks"]-x["cpu_ticks"]
        phase_cpu[name] = {"cpu_ticks": d, "user_ticks": y.get("user_ticks",0)-x.get("user_ticks",0),
                           "system_ticks": y.get("system_ticks",0)-x.get("system_ticks",0),
                           "cpu_s_using_current_clk_tck": d/clk_tck if d >= 0 and clk_tck > 0 else None,
                           "wall_s": (y["t_monotonic_ns"]-x["t_monotonic_ns"])/1e9,
                           "process_io_delta_bytes":{
                               key:(y.get("process_io",{}).get(key)-x.get("process_io",{}).get(key)
                                    if isinstance(x.get("process_io",{}).get(key),int) and
                                    isinstance(y.get("process_io",{}).get(key),int) and
                                    y["process_io"][key]>=x["process_io"][key] else None)
                               for key in ("rchar","wchar","read_bytes","write_bytes")}}
    play_start = phases.get("play_begin",{}).get("phase_start_ns", phases.get("play_begin",{}).get("t_monotonic_ns"))
    play_end = phases.get("play_end",{}).get("phase_end_ns", phases.get("play_end",{}).get("t_monotonic_ns"))
    event_bounds = []
    req_spans, batch_spans = [], []
    for span in spans:
        if span["kind"] == "llm_request": req_spans.append((span["start_ns"],span["end_ns"]))
        if span["kind"] == "tool_batch": batch_spans.append((span["start_ns"],span["end_ns"]))
        event_bounds.extend((span["start_ns"],span["end_ns"]))
    classified = {"request_only": 0, "batch_only": 0, "overlap": 0, "uncovered": 0,
                  "outside_play": 0, "mixed_stage_boundary": 0, "mixed_event_boundary": 0}
    categorized_wall = {k: 0.0 for k in classified}
    for _,t0,t1,dticks in valid_deltas:
        dt=(t1-t0)/1e9
        if not isinstance(play_start,int) or not isinstance(play_end,int) or t1 <= play_start or t0 >= play_end:
            cat="outside_play"
        elif t0 < play_start or t1 > play_end:
            cat="mixed_stage_boundary"
        elif any(t0 < point < t1 for point in event_bounds):
            cat="mixed_event_boundary"
        else:
            mid=(t0+t1)//2
            rin=any(a<=mid<b for a,b in req_spans)
            bin_=any(a<=mid<b for a,b in batch_spans)
            cat="overlap" if rin and bin_ else "request_only" if rin else "batch_only" if bin_ else "uncovered"
        classified[cat] += dticks
        categorized_wall[cat] += dt
    total_sample_ticks = sum(x[3] for x in valid_deltas)
    valid_wall_s = sum((x[2]-x[1])/1e9 for x in valid_deltas)
    user_ticks_delta = system_ticks_delta = 0
    user_system_partial = False
    for i, _, _, _ in valid_deltas:
        prev, cur = samples[i-1], samples[i]
        du = cur.get("user_ticks")-prev.get("user_ticks") if isinstance(cur.get("user_ticks"), int) and isinstance(prev.get("user_ticks"), int) else None
        ds = cur.get("system_ticks")-prev.get("system_ticks") if isinstance(cur.get("system_ticks"), int) and isinstance(prev.get("system_ticks"), int) else None
        if du is None or ds is None or du < 0 or ds < 0:
            user_system_partial = True
        else:
            user_ticks_delta += du
            system_ticks_delta += ds
    return {"sample_count":len(samples), "sample_window_start_ns":times[0], "sample_window_end_ns":times[-1],
            "sample_window_s":(times[-1]-times[0])/1e9 if isinstance(times[0],int) and isinstance(times[-1],int) else None,
            "cpu_ticks_delta":total_sample_ticks,
            "user_ticks_delta":user_ticks_delta if not user_system_partial else None,
            "system_ticks_delta":system_ticks_delta if not user_system_partial else None,
            "user_system_delta_partial":user_system_partial,
            "valid_sample_interval_wall_s":valid_wall_s,
            "cpu_s_using_current_clk_tck":total_sample_ticks/clk_tck if clk_tck > 0 else None,
            "cpu_delta_by_sample_interval_ticks":classified,
            "wall_by_sample_interval_s":categorized_wall,
            "sample_interval_cpu_conservation_ticks":total_sample_ticks-sum(classified.values()),
            "rss_peak_bytes":max(rss_values) if rss_values else None,
            "threads_max_observed":max((s["threads"] for s in samples if isinstance(s.get("threads"),int) and s.get("read_status",{}).get("status")=="ok"),default=None),
            "proc_io_delta_bytes":io,
            "read_status_counts":{key:sum(1 for st in statuses if st.get(key)!="ok") for key in ("stat","io","status")},
            "counter_regression_intervals":regressions,"nonpositive_time_intervals":nonpositive,
            "invalid_cpu_sample_indices":bad_sample,
            "sample_gap_s":{"count":len(gaps),"min":min(gaps) if gaps else None,"max":max(gaps) if gaps else None},
            "phase_boundary_cpu":phase_cpu,
            "phase_boundary_cpu_ticks_sum":sum(v["cpu_ticks"] for v in phase_cpu.values() if isinstance(v,dict)),
            "worker_boundary_cpu_ticks_delta":(phases["worker_end"].get("cpu_ticks")-phases["worker_start"].get("cpu_ticks")
                                                if isinstance(phases.get("worker_end",{}).get("cpu_ticks"),int) and
                                                isinstance(phases.get("worker_start",{}).get("cpu_ticks"),int) else None),
            "phase_cpu_conservation_ticks":((phases["worker_end"].get("cpu_ticks")-phases["worker_start"].get("cpu_ticks"))-
                                             sum(v["cpu_ticks"] for v in phase_cpu.values() if isinstance(v,dict))
                                             if isinstance(phases.get("worker_end",{}).get("cpu_ticks"),int) and
                                             isinstance(phases.get("worker_start",{}).get("cpu_ticks"),int) else None),
            "phase_boundary_cpu_ticks_scope":"worker_start to worker_end, five adjacent intervals including play-to-evaluation gap; cumulative process counter; shared worker process"}


def _usage_summary(spans: list[dict]) -> dict:
    by_role = {}
    fields = ("prompt_tokens","completion_tokens","total_tokens","prompt_cache_hit_tokens","prompt_cache_miss_tokens")
    for role in ("agent","user"):
        role_spans=[s for s in spans if s["kind"]=="llm_request" and s["attrs"].get("role")==role]
        totals={field:0 for field in fields}; missing={field:0 for field in fields}
        reasoning=0; reasoning_missing=0
        for span in role_spans:
            usage=span["terminal_attrs"].get("usage") or {}
            for field in fields:
                value=usage.get(field)
                if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value): totals[field]+=value
                else: missing[field]+=1
            details=usage.get("completion_tokens_details") or {}
            value=details.get("reasoning_tokens")
            if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value): reasoning+=value
            else: reasoning_missing+=1
        by_role[role]={"logical_requests":len(role_spans),"usage_sum_observed":totals,
                       "missing_per_field":missing,"reasoning_tokens_observed_sum":reasoning,
                       "reasoning_missing_calls":reasoning_missing}
    return by_role


def _resource_delta(before: dict | None, after: dict | None) -> dict | None:
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    result = {}
    for key in ("cpu_ticks", "user_ticks", "system_ticks", "rss_bytes", "threads"):
        a, b = before.get(key), after.get(key)
        result[key + "_delta"] = b-a if isinstance(a, int) and isinstance(b, int) else None
    io_before, io_after = before.get("process_io", {}), after.get("process_io", {})
    result["process_io_delta_bytes"] = {
        key: (io_after.get(key)-io_before.get(key)
              if isinstance(io_before.get(key), int) and isinstance(io_after.get(key), int)
              and io_after[key] >= io_before[key] else None)
        for key in ("rchar", "wchar", "read_bytes", "write_bytes")}
    result["interpretation"] = "shared worker process window; not exclusive tool resource use"
    return result


def _milestone_row(evaluation: dict, index: int, requirement: str) -> dict:
    value = evaluation.get("milestone_mapping", {}).get(str(index))
    return {"index": index, "mapped_snapshot_index": value[0] if isinstance(value, list) and len(value) > 0 else None,
            "requirement": requirement,
            "score": value[1] if isinstance(value, list) and len(value) > 1 else None}


def analyze(root: Path = ROOT) -> dict:
    verified=verify_inputs(root)
    raw=verified["raw"]
    events=read_jsonl(raw/"events.jsonl")
    samples=read_jsonl(raw/"samples.jsonl")
    boundaries=read_jsonl(raw/"boundaries.jsonl")
    result=read_json(raw/"result.json")
    job=read_json(raw/"job.json")
    trajectory=raw/"official/trajectories"/TASK
    conversation=read_json(trajectory/"conversation.json")
    execution_context=read_json(trajectory/"execution_context.json")
    run=verified["run_report"]
    require(result.get("run_id")==RUN_ID and result.get("scenario_name")==TASK,
            "worker result task/run mismatch")
    require(job.get("run_id")==RUN_ID and job.get("scenario_name")==TASK,
            "saved job task/run mismatch")
    require(run.get("evaluation")==result.get("evaluation"),
            "run report and worker result evaluation differ")
    spans, pairing=_pair_spans(events)
    phase={b.get("phase"):b for b in boundaries}
    requests=[s for s in spans if s["kind"]=="llm_request"]
    tool_calls=[s for s in spans if s["kind"]=="tool_call"]
    batches=[s for s in spans if s["kind"]=="tool_batch"]
    valid_requests=[s for s in requests if s["attrs"].get("role") in ("agent","user")]
    play_window=(phase["play_begin"].get("phase_start_ns",phase["play_begin"]["t_monotonic_ns"]),
                 phase["play_end"].get("phase_end_ns",phase["play_end"]["t_monotonic_ns"]))
    partition=_partition(play_window,[(s["start_ns"],s["end_ns"]) for s in valid_requests],
                         [(s["start_ns"],s["end_ns"]) for s in batches])
    clk_tck=os.sysconf("SC_CLK_TCK")
    resource=_sample_resources(samples,spans,boundaries,clk_tck)
    task_source=(root/TASK_SOURCE_REL).read_text(encoding="utf-8")
    evaluation_source=(root/EVALUATOR_SOURCE_REL).read_text(encoding="utf-8")
    exec_source=(root/EXEC_ENV_SOURCE_REL).read_text(encoding="utf-8")
    worker_source=(root/WORKER_REL).read_text(encoding="utf-8")
    # Source locations are evidence pointers; this deliberately does not import or execute source.
    source_refs={"task_definition":"multiple_tool_call_scenarios.py:1355-1447",
                 "evaluation_mapping":"common/evaluation.py:1070-1212,1246-1278",
                 "execution_ordering":"roles/execution_environment.py:140-205,265-310",
                 "worker_phases":"toolsandbox_worker.py:620-720"}
    require("send_message_with_contact_content_cellular_off" in task_source and "milestones=[" in task_source,
            "fixed task definition not found in frozen source")
    require("def _dfs" in evaluation_source and "compute_mapping_and_similarity" in evaluation_source,
            "evaluation mapping source not found")
    require("copy.deepcopy" in exec_source and "itertools.permutations" in exec_source,
            "execution ordering source not found")
    require('begin_phase(boundaries, "play"' in worker_source and
            'begin_phase(boundaries, "evaluate"' in worker_source,
            "worker phase source not found")

    role_tools={"agent":[],"user":[]}
    for s in tool_calls:
        role=s["attrs"].get("role","unknown")
        role_tools.setdefault(role,[]).append({"tool_name":s["attrs"].get("tool_name"),
            "event_id":s["event_id"],"request_event_id":s["attrs"].get("request_event_id"),
            "start_ns":s["start_ns"],"end_ns":s["end_ns"],
            "status":s["status"],"ok":s["terminal_attrs"].get("ok"),
            "result_bytes":s["terminal_attrs"].get("result_bytes"),
            "duration_s":s["duration_s"],"error_class":s["terminal_attrs"].get("error")})
    setup_events=[b for b in boundaries if b.get("phase")=="system_setup_exec"]
    request_attempts=[s["terminal_attrs"].get("transport_attempt_count") for s in requests]
    at_id_counts={}
    for s in tool_calls: at_id_counts[s["event_id"]]=at_id_counts.get(s["event_id"],0)+1
    call_roles={r:sum(1 for s in tool_calls if s["attrs"].get("role")==r) for r in ("agent","user")}
    batch_calls=[{"event_id":s["event_id"],"batch_index":s["attrs"].get("batch_index"),
                  "start_ns":s["start_ns"],"end_ns":s["end_ns"],
                  "duration_s":s["duration_s"],
                  "tool_names":s["attrs"].get("tool_names"),"planned_orderings":s["terminal_attrs"].get("planned_orderings"),
                  "executed_orderings":s["terminal_attrs"].get("executed_orderings"),
                  "native_call_id_count":len(s["attrs"].get("call_ids",[])) if isinstance(s["attrs"].get("call_ids"),list) else None,
                  "result_count":s["terminal_attrs"].get("result_count"),"error":s["terminal_attrs"].get("error"),
                  "shared_worker_resource_delta":_resource_delta(s["terminal_attrs"].get("resource_before"),
                                                                   s["terminal_attrs"].get("resource_after"))}
                 for s in batches]
    native_batch_call_ids=[call_id for span in batches for call_id in span["attrs"].get("call_ids",[])]
    native_batch_id_duplicates={cid for cid in native_batch_call_ids if native_batch_call_ids.count(cid)>1}
    phase_rows=[]
    for label,a,b in (("initialization_setup","worker_start","play_begin"),("play","play_begin","play_end"),
                      ("play_to_evaluation_gap","play_end","evaluate_begin"),
                      ("evaluation","evaluate_begin","evaluate_end"),("worker_tail","evaluate_end","worker_end")):
        left,right=phase.get(a),phase.get(b)
        if left and right:
            phase_rows.append({"phase":label,"start_ns":left.get("phase_start_ns",left.get("t_monotonic_ns")),
                               "end_ns":right.get("phase_end_ns",right.get("t_monotonic_ns")),
                               "wall_s":(right.get("phase_end_ns",right.get("t_monotonic_ns"))-left.get("phase_start_ns",left.get("t_monotonic_ns")))/1e9,
                               "cpu_boundary":resource["phase_boundary_cpu"].get(label)})
    tool_event_sequence=[s["attrs"].get("tool_name") for s in sorted(tool_calls,key=lambda x:x["start_ns"])]
    agent_tool_sequence=[s["attrs"].get("tool_name") for s in sorted(tool_calls,key=lambda x:x["start_ns"]) if s["attrs"].get("role")=="agent"]
    user_tool_sequence=[s["attrs"].get("tool_name") for s in sorted(tool_calls,key=lambda x:x["start_ns"]) if s["attrs"].get("role")=="user"]
    event_counts={}
    for event in events:
        key=f"{event.get('kind')}:{event.get('status')}"
        event_counts[key]=event_counts.get(key,0)+1
    request_ids={q["attrs"].get("request_id") for q in requests}
    linked_tool_requests=sum(1 for s in tool_calls if s["attrs"].get("request_event_id") in request_ids)
    user_end=[s for s in tool_calls if s["attrs"].get("tool_name")=="end_conversation" and s["attrs"].get("role")=="user"]
    after_end_request_count=sum(1 for q in requests if user_end and q["start_ns"]>user_end[-1]["end_ns"])
    wrapper_calls=result.get("counts",{}).get("tool_call_executions")
    count_crosscheck={"agent_calls_match":result.get("counts",{}).get("agent_logical_calls")==sum(1 for s in valid_requests if s["attrs"].get("role")=="agent"),
                      "user_calls_match":result.get("counts",{}).get("user_logical_calls")==sum(1 for s in valid_requests if s["attrs"].get("role")=="user"),
                      "wrapper_tool_calls_equal_logical_plus_setup":wrapper_calls==len(tool_calls)+len(setup_events),
                      "batch_open_count_matches_summary":result.get("counts",{}).get("tool_batches",{}).get("started")==sum(1 for e in events if e.get("kind")=="tool_batch" and e.get("status")=="open"),
                      "batch_close_count_matches_summary":result.get("counts",{}).get("tool_batches",{}).get("closed")==sum(1 for e in events if e.get("kind")=="tool_batch" and e.get("status") in ("closed","error"))}
    conversation_roles={role:sum(1 for m in conversation if m.get("role")==role) for role in sorted({m.get("role") for m in conversation})}
    request_details=[{"event_id":s["event_id"],"request_id":s["attrs"].get("request_id"),
                      "role":s["attrs"].get("role"),"start_ns":s["start_ns"],"end_ns":s["end_ns"],
                      "duration_s":s["duration_s"],"request_model":s["attrs"].get("model"),
                      "response_model":s["terminal_attrs"].get("response_model"),
                      "project_layer_attempt_count":s["terminal_attrs"].get("transport_attempt_count"),
                      "usage":s["terminal_attrs"].get("usage"),"status":s["status"]} for s in valid_requests]
    db_rows=execution_context.get("_dbs",{})
    context_state={"database_row_counts":{name:len(rows) for name,rows in db_rows.items() if isinstance(rows,list)},
                   "sandbox_agent_to_user_confirmation_rows":sum(1 for row in db_rows.get("SANDBOX",[])
                       if row.get("sender")=="AGENT" and row.get("recipient")=="USER"),
                   "raw_message_content_in_report":False}
    summary={"scope":{"collection":COLLECTION,"run_id":RUN_ID,"task":TASK,"n_runs":1,
                       "identity_sha256":IDENTITY,"analysis_kind":"single-run descriptive review"},
      "integrity":{"input_hashes_verified":True,"raw_file_count":len(verified["raw_records"]),
                   "raw_manifest_file_set_exact":True,"plan_frozen_structures_equal":True,
                   "identity_digest_verified":True,"archive_identity_links_verified":True,
                   "current_execution_code_matches_frozen":verified["current_code_matches_frozen"],
                   "current_code_checks":verified["current_code_checks"],
                   "official_source_snapshot_checks":verified["source_snapshot_checks"],
                   "run_event_recorder_open_is_right_censored":pairing["unclosed"],
                   "attempt_and_worker_completion_evidence":{
                       "entry_exit_code":run.get("exit_code"),"worker_exit_code":run.get("worker_exit_code"),
                       "deadline_timeout":run.get("deadline_timeout"),"cleanup":run.get("cleanup"),
                       "cleanup_confirmation_elapsed_s":((run.get("cleanup",{}).get("checked_monotonic_ns")-
                           run.get("parent_start_ns"))/1e9 if isinstance(run.get("cleanup",{}).get("checked_monotonic_ns"),int) and
                           isinstance(run.get("parent_start_ns"),int) else None),
                       "within_total_budget":run.get("within_total_budget"),
                       "archive_verification":run.get("archive_verification")}},
      "behavior":{"logical_requests":{"agent":sum(1 for s in valid_requests if s["attrs"].get("role")=="agent"),
                       "user":sum(1 for s in valid_requests if s["attrs"].get("role")=="user"),
                       "total":len(valid_requests),"request_model_labels":sorted({s["attrs"].get("model") for s in valid_requests}),
                       "response_models":sorted({s["terminal_attrs"].get("response_model") for s in valid_requests}),
                       "project_layer_attempt_count_per_call":request_attempts,
                       "actual_http_transport_count":"unknown; no transport-level hook",
                       "sdk_max_retries":result.get("retry",{}).get("sdk_max_retries"),
                       "details":request_details,
                       "usage_by_role":_usage_summary(spans)},
        "event_counts":event_counts,
        "tool_calls":{"logical_calls":len(tool_calls),"by_role":call_roles,"details":role_tools,
                       "tool_batch_count":len(batches),"batches":batch_calls,
                       "system_setup_exec_count":len(setup_events),"system_setup_not_agent_selected":True,
                       "batch_ordering_total":sum((s["terminal_attrs"].get("executed_orderings") or 0) for s in batches),
        "tool_event_sequence":tool_event_sequence,
                       "agent_tool_sequence":agent_tool_sequence,"user_tool_sequence":user_tool_sequence,
                       "bootstrap_tool_call_count":run.get("measurement",{}).get("span_coverage",{}).get("spans",{}).get("tool_call",{}).get("bootstrap"),
                       "tool_sequence_basis":"logical tool-call span start timestamps; saved event order is not treated as concurrency proof",
                       "id_pairing":{"unique_call_event_ids":len(at_id_counts),"duplicate_call_event_ids":[k for k,v in at_id_counts.items() if v>1],
                                      "tool_spans_linked_to_request_by_saved_request_id":linked_tool_requests,
                                      "request_ids_missing_or_unmatched":sum(1 for s in tool_calls if s["attrs"].get("request_event_id") not in request_ids),
                                      "batch_native_call_id_occurrences":len(native_batch_call_ids),
                                      "duplicate_batch_native_call_ids_count":len(native_batch_id_duplicates),
                                      "batches_missing_native_call_ids":sum(1 for s in batches if not s["attrs"].get("call_ids")),
                                      "batch_to_individual_tool_direct_id_link":"not available in saved span attributes; batch counts retained separately; no positional pairing",
                                      "pairing_anomalies":pairing},
                       "all_tool_returns_saved":len(tool_calls)==sum(1 for s in tool_calls if s["status"] in ("closed","error")),
                       "all_tool_results_ok":all(s["terminal_attrs"].get("ok") is True for s in tool_calls),
                       "all_tool_returns_before_worker_end":all(s["end_ns"]<=phase["worker_end"]["t_monotonic_ns"] for s in tool_calls),
                       "requests_after_user_end_conversation":after_end_request_count,
                       "result_counter_crosscheck":{"worker_agent_logical_calls":result.get("counts",{}).get("agent_logical_calls"),
                           "event_agent_logical_calls":sum(1 for s in valid_requests if s["attrs"].get("role")=="agent"),
                           "worker_user_logical_calls":result.get("counts",{}).get("user_logical_calls"),
                           "event_user_logical_calls":sum(1 for s in valid_requests if s["attrs"].get("role")=="user"),
                           "wrapper_tool_call_executions":result.get("counts",{}).get("tool_call_executions"),
                           "logical_tool_calls_plus_system_setup":len(tool_calls)+len(setup_events),
                           "worker_batch_counts":result.get("counts",{}).get("tool_batches"),
                           "event_batch_open_count":sum(1 for e in events if e.get("kind")=="tool_batch" and e.get("status")=="open"),
                           "event_batch_terminal_count":sum(1 for e in events if e.get("kind")=="tool_batch" and e.get("status") in ("closed","error")),
                           "all_counter_checks_match":all(count_crosscheck.values()),"checks":count_crosscheck},
                       "batch_window_is_shared_not_per_tool":True},
        "saved_official_trajectory":{"conversation_message_count":len(conversation),"message_counts_by_role":conversation_roles,
                                     "execution_context_database_rows":context_state},
        "stop":{"conversation_active":result.get("stop",{}).get("conversation_active"),
                "user_end_conversation_executed":result.get("stop",{}).get("user_end_conversation_executed"),
                "reason":result.get("stop",{}).get("reason"),"deadline_timeout":run.get("deadline_timeout"),
                "right_censored_run_event_does_not_override_attempt_completion":True}},
      "time":{"attempt_wall_s":run.get("wall_s"),"worker_window_s":(phase["worker_end"]["t_monotonic_ns"]-phase["worker_start"]["t_monotonic_ns"])/1e9,
              "sample_window_s":resource.get("sample_window_s"),"phases":phase_rows,
              "imports_window_s":(phase["imports_end"]["t_monotonic_ns"]-phase["imports_begin"]["t_monotonic_ns"])/1e9,
              "post_import_pre_play_window_s":(phase["play_begin"]["t_monotonic_ns"]-phase["imports_end"]["t_monotonic_ns"])/1e9,
              "play_to_evaluate_gap_s":(phase["evaluate_begin"]["t_monotonic_ns"]-phase["play_end"]["t_monotonic_ns"])/1e9,
              "play_request_batch_partition":partition,
              "request_span_count":len(valid_requests),"request_union_s":_duration([(s["start_ns"],s["end_ns"]) for s in valid_requests]),
              "batch_span_count":len(batches),"batch_union_s":_duration([(s["start_ns"],s["end_ns"]) for s in batches]),
              "tool_call_span_durations_s":[s["duration_s"] for s in tool_calls],
              "tool_span_duration_scope":"logical call recorder span, not exclusive underlying tool CPU or standalone execution time",
              "partition_residual_s":partition["residual_s"]},
      "resources":{"scope":"single shared host worker process; includes setup, Agent/User clients, tool execution, evaluator and recording",
                   "process_pid_starttime":{"pid":samples[0].get("pid") if samples else None,"starttime_ticks":samples[0].get("starttime_ticks") if samples else None},
                   "clk_tck":{"saved_runtime_value":None,"current_read_only_sysconf":clk_tck,
                               "cpu_seconds_are_conditional_on_current_clk_tck":True},
                   **resource,"cpu_units":"ticks are primary; seconds = ticks / current read-only SC_CLK_TCK; not a saved historical runtime value",
                   "sample_window_average_cores":((resource["cpu_ticks_delta"]/clk_tck)/resource["valid_sample_interval_wall_s"]
                                                    if resource.get("valid_sample_interval_wall_s") and clk_tck else None),
                   "rss_is_sampled_peak_not_kernel_peak":True,"kernel_peak":"not collected for this host-process scope",
                   "proc_io_semantics":"rchar/wchar are proc process byte counters; read_bytes/write_bytes are storage I/O accounting, not complete filesystem traffic",
                   "sampling_does_not_cover_entire_attempt":True,
                   "resource_attribution":"phase boundary counter deltas are shared worker-process deltas; sample intervals crossing event/phase boundaries are kept mixed"},
      "evaluation":{"status":run.get("evaluation_status"),"raw_metrics":run.get("evaluation"),
                     "milestone_interpretation":[
                      _milestone_row(run.get("evaluation",{}),0,"cellular setting state"),
                      _milestone_row(run.get("evaluation",{}),1,"contact-search tool trace in sandbox state"),
                      _milestone_row(run.get("evaluation",{}),2,"outgoing message state matching target recipient/content constraints"),
                      _milestone_row(run.get("evaluation",{}),3,"Agent-to-User confirmation message matching target")],
                     "fourth_milestone_explanation":"Partial score belongs to the confirmation-message milestone; the outgoing-message state milestone is fully scored. The exact component-level reason for the partial similarity cannot be uniquely inferred from saved aggregate mapping; no evaluator rerun was done.",
                     "success_threshold":"not defined or applied by this review"},
      "static_source_references":source_refs,
      "static_mechanism_candidates":{"initialization":"worker imports the selected official source modules and constructs the scenario/roles before play; boundary CPU is high in this shared initialization interval, but no function-level profile exists.",
        "ordering":"official ExecutionEnvironment has permutation/deep-copy handling for multi-call messages; saved batches each report one ordering, so that multi-order branch is not evidenced as exercised in this run.",
        "evaluation":"official evaluator searches milestone-to-snapshot mappings with DFS and similarity calculations; evaluator-stage shared process CPU is observed, but no profile proves a dominant function.",
        "causal_attribution":"unknown without function-level profiling; no mechanism is proven to explain most CPU"},
      "limitations":["one task, one run (n=1)","no controlled repetition or category-level inference","actual HTTP transmissions and bill unknown","sampling window does not span full attempt","no kernel RSS peak for host process","no single-tool exclusive CPU measurement","unclosed run recorder event remains right-censored although attempt/worker completion and cleanup are recorded","current source alignment is separate from historical archive integrity"]}
    return summary,{"spans":spans,"pairing":pairing,"resource":resource,"verified":verified,
                    "samples":samples,"boundaries":boundaries}


def _json_bytes(value) -> bytes:
    return (json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+"\n").encode("utf-8")


def render_markdown(summary: dict) -> str:
    b=summary["behavior"]; t=summary["time"]; r=summary["resources"]; e=summary["evaluation"]; integrity=summary["integrity"]
    cleanup_elapsed=integrity["attempt_and_worker_completion_evidence"]["cleanup_confirmation_elapsed_s"]
    cleanup_elapsed_text=f"{cleanup_elapsed:.3f}" if isinstance(cleanup_elapsed,(int,float)) else "unknown"
    lines=[f"# {COLLECTION}：单次运行离线行为—资源复核", "",
      f"- 任务：`{TASK}`；run：`{RUN_ID}`；identity：`{IDENTITY}`。本报告仅描述一次运行（n=1）。",
      f"- 输入身份与所有登记文件哈希核验：通过。当前执行代码与历史冻结文件身份匹配：{summary['integrity']['current_execution_code_matches_frozen']}。这两项分别表示归档证据完整性与当前源码对齐。",
      "- 历史事件流中的 run 根事件只有 open 行并列入 right-censored；这与独立 attempt/worker 完成、正常退出、评估完成及进程回收记录并列保留，不把事件跨度误作完整运行时长。", "",
      "## 四维结论", "", "| 测量完整性 | 官方任务评估 | 终止机制 | 基础设施与归档 |", "|---|---|---|---|",
      f"| {r['sample_count']}个周期样本；窗口与attempt wall不同；CLK_TCK历史运行值未单独保存，CPU秒按当前只读值换算 | 官方评估已完成；similarity={e['raw_metrics']['similarity']:.6f}，四项milestone分数前三项为1、末项为{e['milestone_interpretation'][3]['score']:.6f} | `user_end_conversation`；conversation_active=false；无deadline timeout | 入口/worker退出码0；worker已回收；采样器停止；原始归档哈希匹配 |", "",
      "## 行为与停止", "",
      f"Agent逻辑请求 {b['logical_requests']['agent']} 次，User {b['logical_requests']['user']} 次；保存的项目层尝试计数为 `{b['logical_requests']['project_layer_attempt_count_per_call']}`。这不是实际HTTP请求数；本次没有传输层hook，实际传输次数unknown。请求模型标签与响应model分别为 `{', '.join(b['logical_requests']['request_model_labels'])}` 与 `{', '.join(b['logical_requests']['response_models'])}`。usage（Agent/User）分别记录prompt {b['logical_requests']['usage_by_role']['agent']['usage_sum_observed']['prompt_tokens']}/{b['logical_requests']['usage_by_role']['user']['usage_sum_observed']['prompt_tokens']}、completion {b['logical_requests']['usage_by_role']['agent']['usage_sum_observed']['completion_tokens']}/{b['logical_requests']['usage_by_role']['user']['usage_sum_observed']['completion_tokens']} tokens；这不是账单，实际费用仍unknown。",
      f"Agent自主工具调用 {b['tool_calls']['by_role']['agent']} 次，User结束工具 {b['tool_calls']['by_role']['user']} 次；另有system setup事件 {b['tool_calls']['system_setup_exec_count']} 次，独立bootstrap tool_call span数为{b['tool_calls']['bootstrap_tool_call_count']}。共记录 {b['tool_calls']['tool_batch_count']} 个执行批次、{b['tool_calls']['batch_ordering_total']} 次ordering。{b['tool_calls']['logical_calls']}个逻辑工具调用返回均为ok；wrapper的tool_call_executions={b['tool_calls']['result_counter_crosscheck']['wrapper_tool_call_executions']}恰等于逻辑工具调用+system setup，不代表全是模型选择的工具。批次窗口是共享执行范围，不是每个工具的独占耗时/CPU。",
      "保存的Agent路径为："+" → ".join(f"`{name}`" for name in b['tool_calls']['agent_tool_sequence'])+"；随后User侧单独执行`end_conversation`。另有system setup记录，不计作Agent自主工具。工具ok、会话结束与评分是不同维度。逻辑调用span与请求ID可关联；批次与单工具span没有共同ID，故分别计数、不按位置强配。保存event ID配对无重复/孤立调用返回；只有顶层run事件保持open/right-censored，worker/attempt另有正常完成记录。所有工具返回早于worker结束，end_conversation后无新增模型请求。",
      "## 时间与共享进程资源", "",
      "| 窗口 | wall（秒） | 共享worker CPU ticks | CPU秒（除以当前只读CLK_TCK） |",
      "|---|---:|---:|---:|"]
    for p in t["phases"]:
        c=p["cpu_boundary"] or {}
        lines.append(f"| {p['phase']} | {p['wall_s']:.3f} | {c.get('cpu_ticks','unknown')} | {c.get('cpu_s_using_current_clk_tck','unknown') if c.get('cpu_s_using_current_clk_tck') is not None else 'unknown'} |")
    lines += [f"| attempt wall | {t['attempt_wall_s']:.3f} | — | — |",
       f"| worker窗口 | {t['worker_window_s']:.3f} | — | — |",
       f"| 周期采样窗口 | {t['sample_window_s']:.3f} | {r['cpu_ticks_delta']} | {r['cpu_s_using_current_clk_tck']:.2f} |", "",
       f"worker窗口 {t['worker_window_s']:.3f}s；周期采样窗口 {t['sample_window_s']:.3f}s，与attempt wall {t['attempt_wall_s']:.3f}s不同。清理进程回收核验发生于parent起点后 {cleanup_elapsed_text}s；归档验证状态为 `{integrity['attempt_and_worker_completion_evidence']['archive_verification']}`。没有独立归档完整起止时长。", "",
       f"Agent/User play观测窗请求/批次互斥分解：request-only {t['play_request_batch_partition']['request_only_s']:.3f}s，batch-only {t['play_request_batch_partition']['batch_only_s']:.3f}s，overlap {t['play_request_batch_partition']['overlap_s']:.3f}s，uncovered {t['play_request_batch_partition']['uncovered_s']:.3f}s；守恒残差 {t['partition_residual_s']:.3g}s。uncovered不解释为思考或等待时间。请求区间是客户端调用区间，不是模型思考时间。",
       f"周期采样：{r['sample_count']}点，最大线程数观测{r['threads_max_observed']}；RSS采样峰值 {r['rss_peak_bytes']} bytes。无独立内核peak。样本CPU差分为 {r['cpu_ticks_delta']} ticks（当前只读CLK_TCK换算 {r['cpu_s_using_current_clk_tck']:.2f} process CPU-s；按有效采样间隔计算平均约{r['sample_window_average_cores']:.2f}个process core-equivalents）。`rchar/wchar`差分为{r['proc_io_delta_bytes']['rchar']}/{r['proc_io_delta_bytes']['wchar']} bytes；`read_bytes/write_bytes`为{r['proc_io_delta_bytes']['read_bytes']}/{r['proc_io_delta_bytes']['write_bytes']} bytes。它们是不同proc I/O计数口径，不代表完整文件系统流量。采样窗口不覆盖整个attempt。", "",
       f"采样状态：stat/io/status缺读计数分别为{r['read_status_counts']['stat']}/{r['read_status_counts']['io']}/{r['read_status_counts']['status']}；CPU计数回退区间{len(r['counter_regression_intervals'])}、非递增时间区间{len(r['nonpositive_time_intervals'])}，最大采样间隔{r['sample_gap_s']['max']:.6f}s。样本CPU区间中outside-play {r['cpu_delta_by_sample_interval_ticks']['outside_play']} ticks、跨事件mixed {r['cpu_delta_by_sample_interval_ticks']['mixed_event_boundary']} ticks、跨阶段mixed {r['cpu_delta_by_sample_interval_ticks']['mixed_stage_boundary']} ticks；本次没有纯请求/批次区间可用于周期样本CPU归因。", "",
       f"阶段CPU ticks分段守恒残差为{r['phase_cpu_conservation_ticks']} ticks。样本计数器区间采用保存顺序；缺读/回退/时间异常区间保持缺口或mixed，不插值。阶段边界计数器与周期采样端点不同，二者总量不要求相等；所有阶段值属于共享worker进程。线程数不是核心数或实际并行度。RSS采样峰值不是内核峰值。", "",
       "## 官方评分解释", "",
       "任务定义的四项检查及保存匹配如下（不展示消息正文、收件人或参数）：", "",
       "| Milestone | 检查对象 | 保存映射snapshot | 分数 |", "|---:|---|---:|---:|"]
    for m in e["milestone_interpretation"]:
        lines.append(f"| {m['index']} | {m['requirement']} | {m['mapped_snapshot_index']} | {m['score']:.6f} |")
    lines += [f"", f"保存的overall similarity={e['raw_metrics']['similarity']:.9f}；四项分数的平均与该值一致，minefield mapping为空。第三项（消息状态检查）满分，因此未满整体分不能笼统说成消息未发送。末项部分分对应Agent→User确认消息检查；仅凭aggregate mapping无法唯一分解它为何为0.675106，本次没有重跑evaluator，也未另设成功阈值。", "",
       "## 批次窗口内共享进程变化", "",
       "下表是工具批次前后读取到的共享worker进程计数器差，不是单工具独占成本；调用与批次之间没有共同的可回查逐工具ID，因此不据批次名字按位置配对。", "",
       "| 批次 | 保存的工具名 | 窗口wall（秒） | 共享进程CPU ticks差 | RSS差（bytes） |", "|---:|---|---:|---:|---:|"]
    for batch in b["tool_calls"]["batches"]:
        names=[str(x) for x in (batch["tool_names"] or []) if x is not None]
        lines.append(f"| {batch['batch_index']} | {', '.join(names) or '未记录'} | {batch['duration_s']:.6f} | {batch['shared_worker_resource_delta']['cpu_ticks_delta'] if batch['shared_worker_resource_delta'] else 'unknown'} | {batch['shared_worker_resource_delta']['rss_bytes_delta'] if batch['shared_worker_resource_delta'] else 'unknown'} |")
    lines += ["", "## 高CPU机制：证据边界", "",
       "初始化/准备、play和evaluator的共享进程边界计数器差分均为可观察事实；evaluator阶段CPU较高。静态源码显示初始化构造场景/角色；官方执行环境在多工具并行消息分支存在排列与深拷贝处理，但本run每批仅记录一次ordering，不能证明该多排列分支实际执行；evaluator用DFS匹配milestone与snapshot。它们只是静态候选机制，缺少函数级profile，不能据此判定哪个机制主导CPU。未运行perf。", "",
       "## 测量限制与建议", "",
       "本次没有受控重复，不推断变异、Assistant类别规律、因果或架构敏感性；不推算账单、思考时间或单工具独占资源。没有保存运行时在线CPU数量或历史CLK_TCK快照；当前只读CLK_TCK仅用于条件换算。PILOT-01是首次客户端初始化失败，不是本run的受控重复。", "",
       "建议：优先扩大固定配置下的任务覆盖，再判断是否需要重复；本建议不是执行授权。", ""]
    return "\n".join(lines)


def run(root: Path = ROOT, output_dir: Path | None = None) -> dict:
    root=Path(root).resolve()
    output_dir=Path(output_dir) if output_dir else root/OUTPUT_REL
    output_dir=output_dir.resolve()
    require(not output_dir.exists() or not any(output_dir.iterdir()),"output directory already exists and is not empty")
    summary,details=analyze(root)
    output_dir.mkdir(parents=True,exist_ok=True)
    outputs=[]
    for name,value in (("summary.json",summary),("per_run.json",{"run_id":RUN_ID,"identity_sha256":IDENTITY,
            "time":summary["time"],"behavior":summary["behavior"],"resources":summary["resources"],
            "integrity":summary["integrity"],"evaluation":summary["evaluation"],
            "sample_points":details["samples"],"phase_boundary_points":details["boundaries"]})):
        path=output_dir/name; data=_json_bytes(value); path.write_bytes(data)
        outputs.append({"path":path.relative_to(root).as_posix() if path.is_relative_to(root) else name,
                        "bytes":len(data),"sha256":sha256(data)})
    md=render_markdown(summary).encode("utf-8")
    md_path=output_dir/"summary.md"; md_path.write_bytes(md)
    outputs.append({"path":md_path.relative_to(root).as_posix() if md_path.is_relative_to(root) else "summary.md",
                    "bytes":len(md),"sha256":sha256(md)})
    # Analyzer itself is added after the file exists; manifest does not hash itself.
    analyzer=root/"scripts/toolsandbox_resource_pilot_02_review.py"
    inputs=details["verified"]["inputs"]+[file_record(analyzer,"scripts/toolsandbox_resource_pilot_02_review.py")]
    manifest={"schema":"toolsandbox-pilot-02-review-manifest-v1","identity_sha256":IDENTITY,
              "inputs":inputs,"outputs":outputs}
    manifest_path=output_dir/"manifest.json"; manifest_path.write_bytes(_json_bytes(manifest))
    # Read back all output bytes and hashes; exclude the manifest itself by design.
    for entry in outputs:
        path=(root/entry["path"]) if (root/entry["path"]).exists() else output_dir/Path(entry["path"]).name
        rec=file_record(path,entry["path"])
        require(rec["bytes"]==entry["bytes"] and rec["sha256"]==entry["sha256"],"output readback mismatch")
    return {"summary":summary,"manifest":manifest,"output_dir":output_dir}


if __name__ == "__main__":
    result=run()
    print(json.dumps({"output_dir":str(result["output_dir"]),"identity_sha256":IDENTITY,
                      "logical_requests":{"agent":result["summary"]["behavior"]["logical_requests"]["agent"],
                                          "user":result["summary"]["behavior"]["logical_requests"]["user"]},
                      "sample_count":result["summary"]["resources"]["sample_count"]},indent=2))
