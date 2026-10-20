#!/usr/bin/env python3
"""Read-only combined acceptance and characterization of the 27 fixed slots.

The original Office run and continuation runs remain separate identity/route
strata. This script never opens a production execution path.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import volcano_three_chain_characterization as resource

OUTPUT = Path("reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v2")
OLD_COLLECTION = "LOCAL-THREE-CLASS-REPEAT-01"
NEW_COLLECTION = "LOCAL-THREE-CLASS-REPEAT-01-CONTINUATION-01"
NEW_REPORT = Path("reports/resource") / NEW_COLLECTION
NEW_RAW = Path("data/raw/generated") / NEW_COLLECTION
OLD_REPORT = Path("reports/resource") / OLD_COLLECTION
OLD_RAW = Path("data/raw/generated") / OLD_COLLECTION
NEW_ENV = Path("env/local-three-class-repeat-01-continuation-01")
OLD_ENV = Path("env/local-three-class-repeat-01")

TASKS = {
    "Coding": ("django__django-16485", "astropy__astropy-13236", "astropy__astropy-13398"),
    "Office": ("atomic__excel_001_budget_bucket_totals_seed",
               "atomic__ppt_008_bullet_editing_seed",
               "atomic__pdf_004_audit_pages_reorder_seed"),
    "Assistant": ("send_message_with_contact_content_cellular_off",
                  "add_reminder_content_and_week_delta_and_time",
                  "modify_contact_with_message_recency_multiple_user_turn"),
}


def digest(obj: object, *, ensure_ascii: bool = False) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=ensure_ascii, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def distribution(values: list[object]) -> dict:
    points = sorted(v for v in values if type(v) in (int, float) and math.isfinite(v))

    def q(p: float):
        if not points:
            return None
        pos = (len(points) - 1) * p
        lo = int(pos)
        hi = min(lo + 1, len(points) - 1)
        return points[lo] + (points[hi] - points[lo]) * (pos - lo)

    q1, med, q3 = q(.25), q(.5), q(.75)
    return {"n": len(points), "raw_points": points, "median": med, "q1": q1,
            "q3": q3, "iqr": q3 - q1 if points else None,
            "quantile_method": "linear interpolation at (n-1)*p; null excluded per metric"}


class AuditInputs(resource.Inputs):
    def check_tree(self, raw: Path, entries: list[dict], *, manifest_name="manifest.json"):
        rels = [str(row["path"]) for row in entries]
        if len(rels) != len(set(rels)):
            raise ValueError(f"duplicate raw manifest path: {raw}")
        actual = {p.relative_to(self.root / raw).as_posix()
                  for p in (self.root / raw).rglob("*") if p.is_file() and p.name != manifest_name}
        if actual != set(rels):
            raise ValueError(f"raw file set mismatch: {raw}; missing={sorted(set(rels)-actual)[:5]}; extra={sorted(actual-set(rels))[:5]}")
        for row in entries:
            self.check(raw / row["path"], row)
        return len(actual)


def _raw_entries(chain: str, manifest: dict) -> list[dict]:
    if chain == "Office":
        return manifest["outputs"]
    if chain == "Coding":
        return [{"path": name, "sha256": sha}
                for name, sha in manifest["files"].items()]
    return manifest["files"]


def _verify_protected_snapshot(inp: AuditInputs) -> dict:
    snap = inp.json(NEW_ENV / "protected-before.json")
    checked = 0
    for directory, rows in snap.items():
        root = Path(directory)
        current = {p.relative_to(inp.root).as_posix()
                   for p in (inp.root / root).rglob("*") if p.is_file()}
        expected = {row["path"] for row in rows}
        if current != expected:
            raise ValueError(f"historical protected file set changed: {directory}")
        for row in rows:
            inp.check(Path(row["path"]), row)
            checked += 1
    return {"directories": len(snap), "files": checked, "result": "unchanged"}


def _verify_identity(inp: AuditInputs, env: Path, *, legacy=False) -> dict:
    plan = inp.json(env / "plan-identity.json")
    frozen = inp.json(env / "frozen-identity.json")
    if plan != frozen:
        raise ValueError(f"plan/frozen complete structure mismatch: {env}")
    ident = frozen["identity"]
    expected = frozen["identity_sha256"]
    # Both batch entry identities use compact UTF-8 JSON; legacy means only
    # "historical execution identity", not a different canonicalization.
    got = digest(ident, ensure_ascii=False)
    if got != expected:
        raise ValueError(f"complete identity digest mismatch: {env}")
    return frozen


def _check_manifest_records(inp: AuditInputs, manifest_path: Path, *, check_raw=True) -> dict:
    manifest = inp.json(manifest_path)
    records = [*manifest.get("inputs", []), *manifest.get("outputs", [])]
    if check_raw:
        records += manifest.get("raw_manifests", [])
    for row in records:
        inp.check(Path(row["path"]), row)
    return {"path": str(manifest_path), "verified_records": len(records),
            "raw_manifests": len(manifest.get("raw_manifests", []))}


def _route_profile(inp: AuditInputs, frozen: dict, batch_rows: list[dict]) -> dict:
    office = frozen["identity"]["components"]["Office"]
    ident_route = office["model"].get("route", {})
    configs = office["run_configs_by_task_round"]
    config_has_route = all("model_route" in configs[task][round_no]
                           for task in TASKS["Office"] for round_no in range(3))
    source_path = Path("scripts/docops_word_resource_01_entry.py")
    source = inp.data(source_path).decode()
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    bound = any(row.get("path") == str(source_path) and row.get("sha256") == source_hash
                for row in office.get("code_and_runtime_files", []))
    default = re.search(r"^API_BASE\s*=\s*['\"]([^'\"]+)['\"]", source, re.M)
    has_fallback = "api_base=route.get('api_base', API_BASE)" in source
    mismatch = ident_route.get("provider") == "火山AI网关" and not config_has_route and has_fallback
    for row in batch_rows:
        if row["chain"] == "Office" and row.get("slot_status") == "executed":
            row["execution_profile_status"] = "route_config_mismatch" if mismatch else "reviewed"
            row["route_resolution_evidence"] = {
                "frozen_provider": ident_route.get("provider"),
                "frozen_api_base": ident_route.get("api_base"),
                "run_config_contains_model_route": "model_route" in configs[row["task"]][row["round"]],
                "bound_source_hash_matches": bound,
                "production_fallback_expression_present": has_fallback,
                "production_default_api_base": default.group(1) if default else None,
                "actual_request_destination_observation": "unknown; no transport-level destination event saved",
            }
    return {"frozen_provider": ident_route.get("provider"),
            "frozen_route": ident_route.get("api_base"),
            "per_run_configs_include_model_route": config_has_route,
            "production_fallback_expression_present": has_fallback,
            "production_default_api_base": default.group(1) if default else None,
            "source_matches_frozen_file_record": bound,
            "new_office_route_mismatch_confirmed": mismatch,
            "source_path": str(source_path), "source_sha256": source_hash,
            "interpretation": "run config omits model_route; build_agent uses API_BASE fallback. This is code/config route resolution, not transport-level endpoint evidence."}


def _scalar_task_result(run: dict):
    v = run["task_result"]
    if isinstance(v, dict):
        for key in ("reward", "similarity", "resolved"):
            if type(v.get(key)) in (int, float, bool):
                return float(v[key])
    if type(v) in (int, float, bool):
        return float(v)
    return None


def _scope_role(scope: dict) -> str:
    kind = scope.get("scope_kind")
    roles = {"agent_container": "agent_container", "verifier_container": "verifier_container",
             "shared_host_mini_child": "host_mini_child", "shared_task_container": "container",
             "shared_host_agent_and_collector": "host_agent",
             "shared_Agent_User_tools_evaluator_worker": "worker"}
    if kind not in roles:
        raise ValueError("unrecognized resource scope kind; cannot aggregate by instance ID")
    return roles[kind]


def _primary_metric(metrics: dict, chain: str, prefix: str):
    role = {"Coding": "agent_container", "Office": "container", "Assistant": "worker"}[chain]
    return metrics.get(prefix + "::" + role)


def _reassess_verifier(run: dict, report: dict, events: list[dict]) -> None:
    """Preserve archived adjudication while distinguishing absent from inapplicable."""
    if run["chain"] != "Coding":
        return
    skipped = (report.get("execution_status") == "no_candidate"
               and report.get("evaluation_status") == "not_run"
               and not any(s.get("scope_kind") == "verifier_container" for s in run["scopes"])
               and any(e.get("kind") == "verifier" and e.get("attrs", {}).get("status") == "not_run"
                       for e in events)
               and not any((e.get("kind") == "container" and e.get("attrs", {}).get("scope") == "verifier"
                            and e.get("attrs", {}).get("action") == "start")
                           or (e.get("kind") == "verifier" and e.get("attrs", {}).get("status") == "running")
                           for e in events))
    archived = run.get("acceptance", {}).get("measurement", {})
    gaps = list(archived.get("gaps") or [])
    if skipped:
        gaps = [g for g in gaps if g not in
                ("verifier_container_cpu_intervals_missing", "verifier_workspace_footprint_partial")]
    run["measurement_reassessment"] = {
        "archived_status": archived.get("status"),
        "status": "partial" if gaps else "complete" if archived.get("status") in ("complete", "partial") else "unknown",
        "gaps": gaps, "verifier": "not_applicable" if skipped else "required_or_unknown",
        "reason": "no_candidate; evaluation not_run; no verifier started" if skipped else None,
        "historical_stop_record_preserved": True}


def _metrics_for(run: dict) -> dict:
    b = run["behavior"]
    out = {"attempt_wall_s": run.get("attempt_wall_s"),
           "logical_requests": b.get("logical_requests"),
           "agent_requests": b.get("requests_by_role", {}).get("agent", 0),
           "user_requests": b.get("requests_by_role", {}).get("user", 0),
           "agent_tools": b.get("tools_by_role", {}).get("agent", 0),
           "bootstrap_tools": b.get("tools_by_role", {}).get("bootstrap", 0),
           "user_tools": b.get("tools_by_role", {}).get("user", 0),
           "ordinary_tool_errors": b.get("ordinary_tool_errors"),
           "request_union_s": b.get("request_union_s"),
           "tool_window_union_s": b.get("tool_window_union_s"),
           "task_result_scalar": _scalar_task_result(run)}
    seen_roles = set()
    for scope in run["scopes"]:
        key = _scope_role(scope)
        if key in seen_roles:
            raise ValueError("duplicate resource role within one run; refusing implicit sum")
        seen_roles.add(key)
        for metric, doc in scope["metric_quality"].items():
            out[f"observed_delta_bytes::{key}::{metric}"] = doc.get("observed_valid_delta_sum") if metric != "cpu" else None
            if metric == "cpu":
                out[f"observed_cpu_s::{key}"] = doc.get("observed_valid_delta_sum")
        out[f"memory_sampled_peak_bytes::{key}"] = scope.get("memory_sampled_peak_bytes")
        out[f"kernel_memory_peak_bytes::{key}"] = scope.get("kernel_memory_peak_bytes")
    for phase in run["phases"]:
        name = phase["name"]
        out[f"phase_wall_s::{name}"] = phase.get("wall_s")
        out[f"phase_shared_cpu_s::{name}"] = phase.get("shared_cpu_s")
    for label, path in resource.disk_rows(run):
        before, after = path.get("before") or {}, path.get("after") or {}
        if before.get("bytes") is not None:
            out[f"disk_before_bytes::{label}::{path.get('scope')}"] = before["bytes"]
        if after.get("bytes") is not None:
            out[f"disk_after_bytes::{label}::{path.get('scope')}"] = after["bytes"]
        if path.get("delta_bytes") is not None:
            out[f"disk_growth_bytes::{label}::{path.get('scope')}"] = path["delta_bytes"]
    return out


def _strip_sensitive_result(run: dict) -> None:
    """Drop raw tool error text; retain only status/category-level evidence."""
    for tool in run["behavior"].get("tools", []):
        if "error" in tool:
            raw = tool.pop("error")
            tool["error_detail_saved_in_source"] = raw is not None
    run["behavior"]["actual_http_attempts"] = None
    run["behavior"]["actual_bill"] = None
    run["behavior"]["transport_evidence"] = "unknown; logical requests are not HTTP attempts"
    models = run["behavior"].get("response_models", {})
    if "None" in models:
        unknown = models.pop("None")
        run["behavior"]["response_model_unknown_count"] = unknown
    if run["chain"] == "Office" and run.get("execution_profile_status") == "route_config_mismatch":
        run["task_protocol_valid_for_frozen_route"] = False
        run["safe_agent_failure_category"] = "BadRequestError/authentication_rejection_text_saved"
        run["credential_or_remote_receipt"] = "unknown; no transport-level destination/receipt record; raw detail intentionally not reproduced"
    else:
        run["task_protocol_valid_for_frozen_route"] = True


def _task_stats(runs: list[dict], slots: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for run in runs:
        groups.setdefault((run["chain"], run["task"], run["profile_stratum"]), []).append(run)
    stats = []
    for (chain, task, stratum), group in sorted(groups.items()):
        metric_maps = [_metrics_for(run) for run in group]
        keys = sorted({key for m in metric_maps for key in m})
        planned = [slot for slot in slots if slot["chain"] == chain and slot["task"] == task]
        historical_only = stratum == "historical_original_Volcano_identity"
        planned_count = 1 if historical_only else len(planned)
        not_executed_count = 0 if historical_only else sum(
            s.get("slot_status") == "not_executed" for s in planned)
        profile_ok = all(run.get("task_protocol_valid_for_frozen_route", True) for run in group)
        for key in keys:
            d = distribution([m.get(key) for m in metric_maps])
            if key.endswith("_s") or key.startswith("phase_wall_s::"):
                unit = "s"
            elif key.startswith("observed_cpu_s::") or key.startswith("phase_shared_cpu_s::"):
                unit = "CPU-s"
            elif "bytes" in key:
                unit = "bytes"
            elif key == "task_result_scalar":
                unit = "task-specific official scalar; not cross-chain comparable"
            else:
                unit = "count"
            stats.append({"chain": chain, "task": task, "profile_stratum": stratum,
                "metric": key, "unit": unit, **d, "planned_slots": planned_count,
                "executed_slots_in_stratum": len(group),
                "not_executed_slots_task_total": not_executed_count,
                "eligible_as_frozen_profile_summary": profile_ok,
                "note": ("descriptive misrouted Office path; excluded from intended Volcano task inference"
                         if not profile_ok else "single historical run/identity; do not pool with continuation"
                         if historical_only else "same frozen profile only; no cross-task pooling")})
    # Explicit zero-evidence rows for the four unexecuted Coding slots.
    for slot in slots:
        if slot.get("slot_status") == "not_executed":
            stats.append({"chain": slot["chain"], "task": slot["task"],
                "profile_stratum": "planned_not_executed", "metric": "attempt_wall_s",
                "n": 0, "raw_points": [], "median": None, "q1": None, "q3": None,
                "iqr": None, "quantile_method": "linear interpolation at (n-1)*p; no points",
                "planned_slots": 1, "executed_slots_in_stratum": 0,
                "not_executed_slots_task_total": 1,
                "eligible_as_frozen_profile_summary": False,
                "note": "not_executed; never represented as zero"})
    return stats


def _write_csv(path: Path, rows: list[dict], fields: list[str] | None = None):
    if fields is None:
        fields = list(dict.fromkeys(key for row in rows for key in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                             if isinstance(value, (dict, list)) else value
                             for key, value in row.items()})


def _flatten_disk(run: dict) -> list[dict]:
    rows = []
    supp = run["disk"]
    if supp.get("task_workspace") == "not_applicable":
        rows.append({"chain": run["chain"], "task": run["task"], "round": run["round"],
                     "run_id": run["run_id"], "role": "task_state", "scope": "in_memory",
                     "path": None, "before_bytes": None, "after_bytes": None, "growth_bytes": None,
                     "status": "not_applicable"})
    for label, item in resource.disk_rows(run):
        before, after = item.get("before") or {}, item.get("after") or {}
        rows.append({"chain": run["chain"], "task": run["task"], "round": run["round"],
            "run_id": run["run_id"], "role": label, "scope": item.get("scope"),
            "path": (after.get("path") or before.get("path")),
            "before_bytes": before.get("bytes"), "after_bytes": after.get("bytes"),
            "growth_bytes": item.get("delta_bytes"), "status": item.get("delta_status"),
            "before_scan_wall_ns": before.get("scan_wall_ns"),
            "after_scan_wall_ns": after.get("scan_wall_ns"),
            "size_basis": item.get("size_basis")})
    return rows


def _render_task_svg(chain: str, task: str, stratum: str, rows: list[dict]) -> str:
    selected = [r for r in rows if r["chain"] == chain and r["task"] == task and r["profile_stratum"] == stratum]
    metrics = ["attempt_wall_s", "task_result_scalar", "logical_requests", "agent_tools"]
    by_metric = {r["metric"]: r for r in selected}
    cpu_row = _primary_metric(by_metric, chain, "observed_cpu_s")
    memory_row = _primary_metric(by_metric, chain, "memory_sampled_peak_bytes")
    cpu_metric = cpu_row["metric"] if cpu_row else None
    memory_metric = memory_row["metric"] if memory_row else None
    if cpu_metric:
        metrics.insert(2, cpu_metric)
    if memory_metric:
        metrics.insert(3, memory_metric)
    # Values are already from each run's unchanged raw-derived primary metrics.
    width, height, x0, x1, y0 = 1050, 680, 260, 940, 620
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<style>text{font:13px sans-serif;fill:#243447}.axis{stroke:#aab2bb}</style>',
           f'<text x="24" y="28">{html.escape(chain)} / {html.escape(task)} / {html.escape(stratum)}</text>',
           '<text x="24" y="49">Raw run points; only per-metric observed values; no zero-fill or cross-task pooling.</text>']
    # Build from the raw-derived point lists in task_statistics records.
    y = 90
    for metric in metrics:
        row = next((x for x in selected if x["metric"] == metric), None)
        if row is None:
            continue
        pts = row["raw_points"]
        out.append(f'<text x="24" y="{y+4}">{html.escape(metric)} (n={len(pts)})</text>')
        out.append(f'<path d="M{x0} {y+15}H{x1}" class="axis"/>')
        if pts:
            lo, hi = min(pts), max(pts)
            pad = (hi-lo)*.1 if hi != lo else max(abs(hi)*.05, 1)
            lo, hi = lo-pad, hi+pad
            scale = lambda v: x0+(v-lo)/(hi-lo)*(x1-x0)
            med, q1, q3 = row["median"], row["q1"], row["q3"]
            out.append(f'<path d="M{scale(q1):.2f} {y+15}H{scale(q3):.2f}" stroke="#b45309" stroke-width="5"/>')
            out.append(f'<path d="M{scale(med):.2f} {y+7}V{y+23}" stroke="#b45309" stroke-width="2"/>')
            for i, value in enumerate(pts):
                px = scale(value)
                out.append(f'<circle cx="{px:.2f}" cy="{y+15}" r="5" fill="#165dbe"/>')
                out.append(f'<text class="small" x="{px:.2f}" y="{y+37}" text-anchor="middle">{value:.5g}</text>')
            out.append(f'<text x="{x1+16}" y="{y+19}">median {med:.5g}; IQR {row["iqr"]:.5g}</text>')
        else:
            out.append(f'<text x="{x0+10}" y="{y+20}">no executed observation</text>')
        y += 86
    return "\n".join(out + ["</svg>"])


def _verify_and_load(inp: AuditInputs) -> tuple[list[dict], list[dict], dict]:
    prior_path = Path("reports/analysis/LOCAL-THREE-CLASS-REPEAT-01-combined-review-v1/manifest.json")
    prior = inp.json(prior_path)
    changed_sources = {
        "scripts/local_three_class_repeat_01_continuation_01_entry.py",
        "scripts/local_three_class_repeat_01_combined_review.py",
        "tests/test_local_three_class_repeat_01_continuation_01.py",
        "tests/test_local_three_class_repeat_01_combined_review.py"}
    for row in [*prior["input_records"], *prior["analysis_code"], *prior["outputs"]]:
        path = Path(row["path"])
        if row["path"] in changed_sources:
            path = Path("env/local-three-class-repeat-01-offline-repair/source-before") / row["path"].replace("/", "__")
        inp.check(path, row)
    new_frozen = _verify_identity(inp, NEW_ENV)
    old_frozen = _verify_identity(inp, OLD_ENV, legacy=True)
    if old_frozen["identity_sha256"] != "460c9c28e4799d864ff2aa3a2bf7cf2e272fa095eabb917f4bec4f1b45893b22":
        raise ValueError("historical original identity does not match the registered Excel run")
    new_approval = inp.json(NEW_REPORT / "APPROVAL.json")
    if new_approval.get("identity_sha256") != new_frozen["identity_sha256"]:
        raise ValueError("continuation approval identity mismatch")
    new_summary = inp.json(NEW_REPORT / "batch-summary.json")
    if new_summary.get("identity_sha256") != new_frozen["identity_sha256"]:
        raise ValueError("continuation batch identity mismatch")
    old_approval = inp.json(OLD_REPORT / "APPROVAL.json")
    old_summary = inp.json(OLD_REPORT / "batch-summary.json")
    if old_approval.get("identity_sha256") != old_frozen["identity_sha256"]:
        raise ValueError("historical approval identity mismatch")
    new_manifest = _check_manifest_records(inp, NEW_REPORT / "manifest.json")
    old_manifest = _check_manifest_records(inp, OLD_REPORT / "manifest.json")
    protected = _verify_protected_snapshot(inp)
    if len(new_summary["runs"]) != 26:
        raise ValueError("continuation slot census must contain 26 rows")
    rows = new_summary["runs"]
    if sum(r.get("slot_status") == "executed" for r in rows) != 22 or sum(
            r.get("slot_status") == "not_executed" for r in rows) != 4:
        raise ValueError("continuation execution/not-executed census mismatch")
    ids = [r["run_id"] for r in rows if r.get("run_id")]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate continuation run id")
    actual_raw = {p.name for p in (inp.root / NEW_RAW).iterdir() if p.is_dir()}
    if actual_raw != set(ids):
        raise ValueError("continuation raw namespace differs from executed batch slots")
    for row in rows:
        if row.get("slot_status") == "not_executed":
            if row.get("run_id") is not None:
                raise ValueError("not-executed slot unexpectedly has run id")
            continue
        chain, run = row["chain"], row["run_id"]
        if row["identity_sha256"] != new_frozen["identity_sha256"]:
            raise ValueError("continuation slot identity mismatch")
        raw = Path(row["raw_path"])
        raw_manifest = inp.json(raw / "manifest.json")
        entries = _raw_entries(chain, raw_manifest)
        inp.check(raw / "manifest.json", {"path": str(raw / "manifest.json"),
            "bytes": (inp.root / raw / "manifest.json").stat().st_size,
            "sha256": hashlib.sha256((inp.root / raw / "manifest.json").read_bytes()).hexdigest()})
        inp.check_tree(raw, entries)
        report_path = Path(row["report_path"])
        report = inp.json(report_path)
        if report.get("identity_sha256") != new_frozen["identity_sha256"] or report.get("run_id") != run:
            raise ValueError("run report identity/run association mismatch")
        validation = inp.json(NEW_REPORT / run / "VALIDATION.json")
        if validation.get("identity_sha256") != new_frozen["identity_sha256"] or validation.get("run_id") != run:
            raise ValueError("validation identity/run association mismatch")
        if validation.get("cleanup_status") != "confirmed" or validation.get("archive_status") != "verified":
            raise ValueError("launched attempt lacks confirmed cleanup or archive verification")
    # Historical run is independently tied to the original identity and the one frozen slot.
    old_id = "20261016T182559Z-09-r0-office"
    old_raw = OLD_RAW / old_id
    old_run_report = inp.json(OLD_REPORT / old_id / "run-report.json")
    old_manifest_doc = inp.json(old_raw / "manifest.json")
    if old_run_report["identity_sha256"] != old_frozen["identity_sha256"]:
        raise ValueError("old Excel run identity mismatch")
    if old_manifest_doc.get("identity_sha256") != old_frozen["identity_sha256"]:
        raise ValueError("old Excel raw identity mismatch")
    old_entries = old_manifest_doc["outputs"]
    inp.check_tree(old_raw, old_entries)
    old_start = inp.json(old_raw / "ATTEMPT_STARTED.json")
    old_end = inp.json(old_raw / "ATTEMPT_COMPLETED.json")
    if old_start.get("identity_sha256") != old_frozen["identity_sha256"] or old_end.get("run_id") != old_id:
        raise ValueError("old Excel markers mismatch")
    # Verify the prior report manifest as well; its old summary remains immutable.
    old_batch_manifest = inp.json(OLD_REPORT / "manifest.json")
    for record in [*old_batch_manifest.get("inputs", []), *old_batch_manifest.get("outputs", [])]:
        inp.check(Path(record["path"]), record)
    if old_summary.get("identity_sha256") != old_frozen["identity_sha256"]:
        raise ValueError("old batch summary identity mismatch")
    old_run_row = next((x for x in old_summary.get("runs", []) if x.get("run_id") == old_id), None)
    if not old_run_row or old_run_row.get("task") != TASKS["Office"][0] or old_run_row.get("round") != 0:
        raise ValueError("historical Excel slot association mismatch")
    integrity = {"new_outer_manifest": new_manifest, "old_outer_manifest": old_manifest,
        "protected_history": protected, "new_executed_runs": len(ids),
        "new_not_executed_slots": 4, "old_run_id": old_id,
        "old_original_batch_state_retained": old_summary.get("overall_status", old_summary.get("status")),
        "new_raw_manifests_checked": len(ids)}
    return rows, [old_run_row], {"new": new_frozen, "old": old_frozen, "new_summary": new_summary,
                                 "old_summary": old_summary, "integrity": integrity}


def build(root: Path = ROOT, output: Path = OUTPUT) -> dict:
    inp = AuditInputs(root)
    slots, old_rows, identities = _verify_and_load(inp)
    continuation = identities["new"]
    old_frozen = identities["old"]
    route = _route_profile(inp, continuation, slots)
    if not route["source_matches_frozen_file_record"]:
        route["new_office_route_mismatch_confirmed"] = False
        route["interpretation"] = "current production source is not the frozen source; historical route resolution remains unknown"

    actual_specs = []
    old_id = "20261016T182559Z-09-r0-office"
    actual_specs.append({"chain": "Office", "collection": OLD_COLLECTION, "task": TASKS["Office"][0],
        "round": 0, "run_id": old_id,
        "report_path": str(OLD_REPORT / old_id / "run-report.json"),
        "identity": old_frozen, "profile_stratum": "historical_original_Volcano_identity"})
    for slot in slots:
        if slot.get("slot_status") != "executed":
            continue
        actual_specs.append({"chain": slot["chain"], "collection": NEW_COLLECTION,
            "task": slot["task"], "round": slot["round"], "run_id": slot["run_id"],
            "report_path": slot["report_path"], "identity": continuation,
            "profile_stratum": ("continuation_Office_route_mismatch" if slot["chain"] == "Office"
                                and route["new_office_route_mismatch_confirmed"]
                                else "continuation_frozen_profile")})

    runs, series_by_id = [], {}
    for spec in actual_specs:
        chain = spec["chain"]
        saved = {"identity_sha256": spec["identity"]["identity_sha256"]}
        slot_row = next((r for r in slots if r.get("run_id") == spec["run_id"]), None)
        archived_rc = slot_row.get("returncode") if slot_row else 0
        run, series = resource.analyze_run(inp, (chain, spec["collection"], spec["run_id"], ""),
            saved, archived_rc, report_path=Path(spec["report_path"]))
        run.update(task=spec["task"], round=spec["round"], profile_stratum=spec["profile_stratum"],
                   identity_sha256=spec["identity"]["identity_sha256"])
        if slot_row:
            run["slot_status"] = slot_row["slot_status"]
            run["acceptance"] = {k: slot_row.get(k) for k in
                ("report_status", "cleanup_status", "archive_status", "stop_reason")}
            m = slot_row.get("measurement") or {}
            run["acceptance"]["measurement"] = {k: m.get(k) for k in
                ("status", "gaps", "cpu_intervals", "memory_valid_samples", "io_intervals", "disk_roles", "cache")}
            run["acceptance"]["network_samples"] = (m.get("network") or {}).get("network_samples")
        else:
            run["slot_status"] = "executed_historical_original"
            run["acceptance"] = {"report_status": old_rows[0].get("report_status"),
                "measurement": old_rows[0].get("measurement"), "cleanup_status": old_rows[0].get("cleanup_status"),
                "archive_status": old_rows[0].get("archive_status"),
                "note": "old batch acceptance failure was not task execution failure; independent validation preserved"}
        if chain == "Coding":
            _reassess_verifier(run, inp.json(Path(spec["report_path"])),
                              inp.lines(Path("data/raw/generated") / spec["collection"] / spec["run_id"] / "events.jsonl"))
        for scope in run["scopes"]:
            scope["aggregation_role"] = _scope_role(scope)
        if chain == "Office" and spec["collection"] == NEW_COLLECTION:
            run["execution_profile_status"] = "route_config_mismatch" if route["new_office_route_mismatch_confirmed"] else "route_unverified"
            run["task_protocol_valid_for_frozen_route"] = False
            run["saved_failure_category"] = "BadRequestError/authentication_rejection_text_saved"
            run["credential_receipt_status"] = "unknown; raw error detail withheld; no transport hook"
        elif chain == "Office":
            run["execution_profile_status"] = "historical_original_identity_not_pooled"
            run["task_protocol_valid_for_frozen_route"] = True
        else:
            run["execution_profile_status"] = "continuation_frozen_profile"
            run["task_protocol_valid_for_frozen_route"] = True
        # Make missing response model explicit, never serialize raw exception text.
        _strip_sensitive_result(run)
        run["response_model_evidence_note"] = (
            "response_model recorded only when the saved response contains it; request model is not substituted")
        runs.append(run)
        series_by_id[run["run_id"]] = series

    # Add the four planned-but-unexecuted slots as explicit rows in the slot census.
    slot_outputs = []
    for row in slots:
        slot_outputs.append({k: row.get(k) for k in ("sequence", "original_sequence", "chain", "round", "task",
            "run_id", "slot_status", "task_result", "agent_termination", "infra_status",
            "cleanup_status", "archive_status", "stop_reason", "returncode")})
        slot_outputs[-1]["measurement_status"] = (row.get("measurement") or {}).get("status")

    statistics_rows = _task_stats(runs, slots)
    operations = []
    for run in runs:
        for tool in run["behavior"].get("tools", []):
            operations.append({"chain": run["chain"], "task": run["task"], "round": run["round"],
                "run_id": run["run_id"], "profile_stratum": run["profile_stratum"],
                "role": tool.get("role"), "tool_name": tool.get("name"),
                "static_operation": tool.get("static_operation"), "terminal_status": tool.get("status"),
                "ok": tool.get("ok"), "exception_type": tool.get("exception_type"),
                "event_id": tool.get("event_id"), "source": "native events or Coding mini_tool_events.jsonl"})
    footprint = [row for run in runs for row in _flatten_disk(run)]

    # Keep the historical row and all executed continuation rows in the output census.
    old_slot = {"sequence": 9, "original_sequence": 9, "chain": "Office", "round": 0,
        "task": TASKS["Office"][0], "run_id": "20261016T182559Z-09-r0-office",
        "slot_status": "executed_historical_original", "identity_sha256": old_frozen["identity_sha256"],
        "source_collection": OLD_COLLECTION, "task_result": 1.0, "agent_termination": "finish",
        "infra_status": "ok", "measurement_status": "complete",
        "cleanup_status": "confirmed", "archive_status": "independently_verified"}
    slots_all = [old_slot, *slot_outputs]
    old_route = old_frozen["identity"]["components"]["Office"]["run_configs"][TASKS["Office"][0]]["model_route"]
    if old_route.get("api_base") != old_frozen["identity"]["components"]["Office"]["model"]["api_base"]:
        raise ValueError("historical Excel model route does not match its frozen declaration")
    route["historical_excel_route"] = old_route
    result = {"schema": "local-three-class-repeat-01-combined-review-v2",
        "planned_slots_total": 27, "historical_original_executed": 1,
        "continuation_planned": 26,
        "continuation_executed": sum(r.get("slot_status") == "executed" for r in slots),
        "continuation_not_executed": sum(r.get("slot_status") == "not_executed" for r in slots),
        "actual_run_count_in_analysis": len(runs), "all_runs": runs,
        "continuation_slots": slot_outputs, "slot_census_27": slots_all,
        "route_audit": route,
        "batch": {"wall_s": identities["new_summary"].get("wall_s"),
                  "within_batch_wall_limit": identities["new_summary"].get("within_batch_wall_limit"),
                  "class_stops": identities["new_summary"].get("class_stops"),
                  "global_stop": identities["new_summary"].get("global_stop")},
        "historical_batch": {"identity_sha256": identities["old_summary"].get("identity_sha256"),
                             "status": identities["old_summary"].get("status"),
                             "failed": identities["old_summary"].get("failed")},
        "integrity": identities["integrity"],
        "task_statistics": statistics_rows,
        "measurement_scope_note": "container/process/netns scopes kept separate; no cross-scope sums; network is shared netns, not task/API-exclusive",
        "analysis_limits": [
            "Office continuation run configs omit model_route although frozen identity declares Volcano; not valid as intended Volcano task outcomes and not pooled with old Excel.",
            "Coding archived stop was a false positive: no_candidate and evaluation not_run means no verifier was started; its CPU and workspace are not_applicable. Four remaining slots remain not_executed.",
            "Assistant has three executed observations per task; this is a fixed local sample, not a class-level distribution.",
            "Actual HTTP attempts, endpoint receipt, billing, and credential delivery are not instrumented; logical request counts are not HTTP counts.",
            "No task/API-exclusive network bytes; per-interface shared netns observations can include background/virtual duplicate traffic.",
            "Directory scans use apparent bytes and can overlap observed CPU/I/O; host output scan precedes final archive writes.",
            "The historical successful Excel run uses its own identity/route and remains a separate stratum."]}

    outdir = root / output
    if outdir.exists() and any(outdir.iterdir()):
        raise FileExistsError(f"analysis output already exists and will not be overwritten: {output}")
    for name in ("figures", "series"):
        (outdir / name).mkdir(parents=True, exist_ok=True)

    per_run_lines = []
    for run in runs:
        run_id = run["run_id"]
        series = series_by_id[run_id]
        csv_path = outdir / "series" / f"{run_id}.csv"
        _write_csv(csv_path, series)
        run["series_csv"] = f"series/{run_id}.csv"
        run["figure"] = f"figures/{run_id}.svg"
        svg = resource.render_svg(run, series)
        svg = svg.replace(f"series/{run['chain'].lower()}.csv", run["series_csv"])
        if run.get("execution_profile_status") == "route_config_mismatch":
            svg = svg.replace('<text x="40" y="75">',
                '<text x="40" y="115" fill="#b42318">OFFICE ROUTE MISMATCH: raw resource path only; not a valid frozen-route task result.</text><text x="40" y="75">')
        (outdir / run["figure"]).write_text(svg, encoding="utf-8")
        per_run_lines.append(json.dumps(run, ensure_ascii=False, sort_keys=True))

    # Small task-specific dot/IQR summaries. Route-mismatched Office data is
    # explicitly presented as a diagnostic stratum, never pooled with history.
    plot_groups = sorted({(r["chain"], r["task"], r["profile_stratum"]) for r in statistics_rows})
    for chain, task, stratum in plot_groups:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", f"{chain}-{task}-{stratum}").strip("-")
        svg = _render_task_svg(chain, task, stratum, statistics_rows)
        (outdir / "figures" / f"task-points-{slug}.svg").write_text(svg, encoding="utf-8")

    (outdir / "per_run.jsonl").write_text("\n".join(per_run_lines) + "\n", encoding="utf-8")
    _write_csv(outdir / "task_statistics.csv", statistics_rows)
    _write_csv(outdir / "tool_operations.csv", operations)
    _write_csv(outdir / "directory_footprint.csv", footprint)
    compact_summary = {key: value for key, value in result.items()
        if key not in ("all_runs", "continuation_slots", "batch", "historical_batch")}
    compact_summary["batch"] = {"wall_s": identities["new_summary"].get("wall_s"),
        "within_batch_wall_limit": identities["new_summary"].get("within_batch_wall_limit"),
        "class_stops": identities["new_summary"].get("class_stops"),
        "global_stop": identities["new_summary"].get("global_stop"),
        "executed": result["continuation_executed"], "not_executed": result["continuation_not_executed"]}
    compact_summary["historical_batch"] = {"identity_sha256": identities["old_summary"].get("identity_sha256"),
        "status": identities["old_summary"].get("status"), "failed": identities["old_summary"].get("failed"),
        "note": "historical batch acceptance failure retained; original run independently verified"}
    compact_summary["run_references"] = [{k: r.get(k) for k in
        ("chain", "task", "round", "run_id", "collection", "profile_stratum", "figure", "series_csv")}
        for r in runs]
    (outdir / "summary.json").write_text(json.dumps(compact_summary, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    (outdir / "summary.md").write_text(_markdown(result), encoding="utf-8")

    code_files = [Path("scripts/local_three_class_repeat_01_combined_review.py"),
        Path("tests/test_local_three_class_repeat_01_combined_review.py"),
        Path("scripts/volcano_three_chain_characterization.py"),
        Path("scripts/toolsandbox_resource_pilot_02_review.py"),
        Path("scripts/docops_word_resource_01_entry.py"),
        Path("scripts/local_three_class_repeat_01_continuation_01_entry.py"),
        Path("src/agent_workload_characterization/collectors/execution_measurement.py"),
        Path("src/agent_workload_characterization/analyzers/public_operations.py")]
    for path in code_files:
        inp.data(path)
    # Existing analysis input reads are already content-hashed. Add report/raw
    # evidence as a finite manifest input set; the manifest never hashes itself.
    output_records = []
    for p in sorted(x for x in outdir.rglob("*") if x.is_file()):
        data = p.read_bytes()
        output_records.append({"path": p.relative_to(root).as_posix(), "bytes": len(data),
                               "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {"schema": "local-three-class-repeat-01-combined-review-manifest-v1",
        "input_records": sorted(inp.records.values(), key=lambda x: x["path"]),
        "analysis_code": [inp.records[str((root / p).resolve())] for p in code_files],
        "outputs": output_records,
        "manifest_note": "manifest.json intentionally not self-hashed; input records include exact raw and report files read after validating source manifests; v1 remains immutable; changed source originals are preserved under env/local-three-class-repeat-01-offline-repair/source-before"}
    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    # Final disk read-back: output bytes and SHA must equal the manifest.
    for row in output_records:
        p = root / row["path"]
        data = p.read_bytes()
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError(f"analysis output read-back mismatch: {row['path']}")
    result["output_manifest_records"] = len(output_records)
    result["input_manifest_records"] = len(manifest["input_records"])
    return result


def _markdown(summary: dict) -> str:
    runs = summary["all_runs"]
    counts = {chain: sum(r["chain"] == chain for r in runs) for chain in TASKS}
    lines = ["# 三类任务固定重复批次：续批合并复核", "",
        "## 批次完成度", "",
        "原批已启动 1 次；续批计划 26 个槽位，实际启动 22 次，4 次 Coding 因验收误将不适用的 verifier 指标判为缺测而停止。总计 23 次已启动运行，不是 27 次执行。", "",
        "续批整体 wall 为 1338.141 秒，14 小时上限内；Coding 最后一次为 no_candidate、evaluation_status=not_run，生命周期明确没有启动 verifier，其 CPU 与目录占用应为 not_applicable，而非采集器故障。原停止记录保持不变。各已启动 attempt 的容器/worker 清理与 raw 归档核验通过。", "",
        "|链路|本次分析中的实际运行|计划续批|任务/采集结论|", "|---|---:|---:|---|"]
    lines += [f"|{c}|{counts[c]}|{9 if c!='Office' else 8}|" + {
        "Coding":"5次启动；3个 resolved true、1个 false、1个 no_candidate/未评估；末次 verifier 不适用被历史验收误判为 partial；剩4槽 not_executed。",
        "Office":"原批 Excel 1 次成功单列；续批8次均 Agent authentication BadRequestError，verifier reward=0；路由配置与冻结身份不一致。",
        "Assistant":"9次完整；每个固定任务3次，保留原始官方 similarity。"}[c] + "|" for c in TASKS]
    lines += ["", "## 关键路由偏差", "",
        "续批 Office 冻结身份声明火山网关，但 8 个 task run_config 均未包含 `model_route`。已绑定的生产 `build_agent()` 在该字段缺失时回退到模块常量 `https://api.deepseek.com/v1`。所有 Office run 保存为 `agent_error/BadRequestError`，没有响应模型；认证失败文本已在原始证据中，本文不复制其正文。",
        "因此这 8 次是已消费的 attempt 和真实资源观察，但不是冻结火山路由下的有效任务结果；不能与旧 Excel 成功运行合并为 Office n=3。HTTP 尝试数、实际目的端收到与否、费用均 unknown。由于凭据路由错配可能涉及凭据被送往非预期端点，建议在后续处置中按凭据安全事件核查；本分析未读取凭据、未重发请求，也未修改历史记录。", "",
        "## 固定任务统计", "",
        "下面各任务按 profile_stratum 分行。数值分布对每个指标使用该指标实际有效 n，分位数采用 `(n−1)×p` 线性插值。Office 的路由错配行仅是错误路径诊断，不纳入冻结配置任务推断；Coding 不足三次；Assistant 每任务 n=3。", "",
        "完整逐 run 原始点与 median/IQR 在 `task_statistics.csv`；每次运行资源曲线在 `figures/`，作图数据在 `series/`。", "",
        "|链路|任务|profile分层|官方结果原始点（n；中位数/IQR）|attempt wall（秒）|主要共享scope CPU（CPU-s）|",
        "|---|---|---|---|---|---|"]
    grouped = {}
    for row in summary["task_statistics"]:
        grouped.setdefault((row["chain"], row["task"], row["profile_stratum"]), {})[row["metric"]] = row
    def fmt_dist(doc):
        if not doc or doc["median"] is None:
            return "n=0; median/IQR=unknown"
        raw = ", ".join(f"{x:g}" for x in doc["raw_points"])
        return f"n={doc['n']}; raw=[{raw}]; med={doc['median']:.5g}; IQR={doc['iqr']:.5g}"
    for (chain, task_name, stratum), metrics in sorted(grouped.items()):
        cpu = _primary_metric(metrics, chain, "observed_cpu_s")
        lines.append(f"|{chain}|`{task_name}`|`{stratum}`|{fmt_dist(metrics.get('task_result_scalar'))}|{fmt_dist(metrics.get('attempt_wall_s'))}|{fmt_dist(cpu)}|")
    lines.append("")
    for r in runs:
        task = r["task_result"]
        score = task.get("reward", task.get("similarity", task.get("resolved"))) if isinstance(task, dict) else task
        lines.append(f"- **{r['chain']} / {r['task']} / r{r['round']}** — `{r['run_id']}`；profile `{r['profile_stratum']}`；结果 `{score}`；终止 `{r['termination']}`；attempt wall `{r['attempt_wall_s']}` s；测量 `{r['measurement_status']['coverage']}`；清理/归档以 `per_run.jsonl` 的 acceptance 字段为准。")
        lines.append(f"  [资源图]({r['figure']}) · [作图数据]({r['series_csv']})")
    lines += ["", "## 允许的观察与边界", "",
        "1. Assistant 三个固定任务均完成 3 次，原始 similarity 在 per-run 数据中；这是固定场景描述，不代表 Assistant 类总体或成功率。", 
        "2. Coding 只覆盖已启动的5个槽；Astropy-13398 r1 无候选补丁，verifier 未运行，缺少该阶段资源应为不适用。历史验收误判导致4个剩余槽未执行，本轮没有补跑。跨run按稳定scope角色汇总，原scope ID保留用于追溯，不跨scope相加。", 
        "3. Office 路由错配让 Agent 在首请求失败；资源采样窗口仍可描述初始化/失败/清理期间的共享容器变化，但不能解释为 Office 文档操作成功路径。", 
        "4. Coding 的 Agent 与 verifier 容器 CPU、内存和目录分别保留；共享宿主进程、共享 netns、磁盘I/O各自不与容器合并。资源区间与阶段/工具只作共现，不作单工具独占或因果归因。", 
        "5. 共享网络按接口单独统计，图中最多选择3个完整窗口非 lo 接口，仅为可读展示，不是 API 出口识别；接口不求和。任务目录为 apparent size，缓存仍 unsupported；扫描可贡献于观察窗口内 CPU/I/O。", 
        "6. 原 Office Excel 的冻结身份与单次 model_route 均显式登记火山网关，v1 的“旧 DeepSeek 配置”标签错误；本轮改为 historical_original_Volcano_identity。原样本独立保留，不与续批 Office 错误路由数据合并。PILOT/其他实验不纳入。", 
        "7. 逻辑请求数不等于 HTTP 发送次数；请求耗时不称思考时间；token 与框架 cost 不代表账单。", "",
        "## 证据与产物", "",
        f"- 新续批：22 次已执行、4 次 not_executed；stop=`critical_measurement_gap`（Coding），global_stop=null。", 
        f"- 新续批 identity：`{summary['integrity']['new_outer_manifest']['path']}` 对应完整 SHA 见冻结文件；原 identity 不覆盖。", 
        "- 文件集合、raw manifests、外层清单及历史保护目录均在 manifest/summary 中登记；SHA-256 回读通过。", 
        "- 没有将批验收解析异常称为任务失败；本次确认的 Office 问题是冻结 route 与实际单次 config 接线不一致。", 
        "- v2 离线修复：单次 Office 显式传入并校验路由，缺失/错配在模型客户端创建前拒绝；结构化 BadRequestError 保守停止，避免连续错误请求。没有重冻结历史身份或执行新attempt，修改后代码尚未实测。",
        "- 本分析不修改 raw、批准、冻结身份、原报告或 HTML；不提交 Git。", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build(args.root, args.output)
    print(json.dumps({"actual_runs": result["actual_run_count_in_analysis"],
        "continuation_executed": result["continuation_executed"],
        "continuation_not_executed": result["continuation_not_executed"],
        "office_route_mismatch": result["route_audit"]["new_office_route_mismatch_confirmed"],
        "output": str(args.output), "inputs": result["input_manifest_records"],
        "outputs": result["output_manifest_records"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
