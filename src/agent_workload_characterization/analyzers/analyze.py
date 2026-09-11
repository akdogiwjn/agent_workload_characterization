"""analyze-macro-pilot orchestrator: load -> macro -> coverage -> report."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .loader import load_pilot
from .macro import macro_summary
from .coverage import coverage_for, summarize_coverage, capability_rows


def _file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _stable_analysis_id(catalog_path, pilot_path, gold_path, input_hashes):
    payload = {
        "catalog_sha256": hashlib.sha256(Path(catalog_path).read_bytes()).hexdigest(),
        "pilot_sha256": hashlib.sha256(Path(pilot_path).read_bytes()).hexdigest(),
        "gold_sha256": hashlib.sha256(Path(gold_path).read_bytes()).hexdigest(),
        "input_file_hashes": sorted(input_hashes),
        "rule_version": "macro-coverage-0.1.0",
    }
    return "pilot-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def _output_guard(project, destination, catalog=None):
    from ..adapters.catalog import Catalog
    destination = destination.resolve()
    reports_macro = (project / "reports" / "macro").resolve()
    if not destination.is_relative_to(reports_macro):
        raise ValueError("output must be under reports/macro/")
    protect = [project / "references", project / "data/raw", project / "data/catalog"]
    if catalog is not None:
        for name, root in catalog.roots.items():
            if name == "project":
                continue  # project root contains our outputs; not a protected source
            protect.append(root)
        protect.append(catalog.path)
    for p in protect:
        real = p.resolve()
        if destination == real or destination.is_relative_to(real) or real.is_relative_to(destination):
            raise ValueError(f"output overlaps protected path: {real}")
    return destination


def _check_sidecar(catalog, samples):
    """Real cross-check of VW-LONG bundle requests/tools against sidecar.

    Compares (trace_id, call_id) request key sets, native toolCall ID sets,
    and per-request token/latency field values. Missing/extra keys or value
    conflicts all fail the joint check. Sidecar files that exist but are
    empty also fail (they are expected inputs).
    """
    sidecar_source = catalog.source("sidecar_videoweaver")
    model_path = sidecar_source.path / "model_calls.jsonl"
    tool_path = sidecar_source.path / "tool_calls.jsonl"
    errors = []
    if not model_path.is_file():
        errors.append(f"sidecar model_calls missing: {model_path}")
    if not tool_path.is_file():
        errors.append(f"sidecar tool_calls missing: {tool_path}")
    if errors:
        return {"status": "FAIL", "errors": errors}

    import hashlib as _h
    model_sha = _h.sha256(model_path.read_bytes()).hexdigest()
    tool_sha = _h.sha256(tool_path.read_bytes()).hexdigest()

    models = [json.loads(l) for l in model_path.read_bytes().splitlines() if l.strip()]
    tools = [json.loads(l) for l in tool_path.read_bytes().splitlines() if l.strip()]

    vw = next((s for s in samples if s.sample_id == "VW-LONG"), None)
    if vw is None:
        return {"status": "FAIL", "errors": ["VW-LONG not in samples for sidecar check"]}
    if vw.request_records is None or vw.tool_ids is None:
        return {"status": "FAIL", "errors": ["VW-LONG missing raw comparison data"]}

    native_trace_id = next(iter(vw.request_records))[0] if vw.request_records else None

    # --- request key comparison ---
    bundle_keys = set(vw.request_records.keys())
    sidecar_rows = [r for r in models if r.get("trace_id") == native_trace_id]
    sidecar_keys = set((r.get("trace_id"), r.get("call_id")) for r in sidecar_rows)
    missing_in_sidecar = bundle_keys - sidecar_keys
    extra_in_sidecar = sidecar_keys - bundle_keys
    if missing_in_sidecar:
        errors.append(f"{len(missing_in_sidecar)} bundle requests missing from sidecar: "
                      f"{sorted(str(k) for k in list(missing_in_sidecar)[:3])}")
    if extra_in_sidecar:
        errors.append(f"{len(extra_in_sidecar)} sidecar requests not in bundle: "
                      f"{sorted(str(k) for k in list(extra_in_sidecar)[:3])}")
    if not bundle_keys and not sidecar_keys:
        errors.append("both bundle and sidecar have zero request records")

    # --- per-request value comparison (token/latency fields) ---
    # Sidecar uses _s suffix for time fields.
    field_map = {"input_tokens": "input_tokens", "output_tokens": "output_tokens",
                 "context_tokens": "context_tokens", "ttft": "ttft_s",
                 "api_latency": "api_latency_s"}
    value_mismatches = 0
    for key, bundle_vals in vw.request_records.items():
        row = next((r for r in sidecar_rows
                    if r.get("trace_id") == key[0] and r.get("call_id") == key[1]), None)
        if row is None:
            continue
        for bfield, sfield in field_map.items():
            bval, sval = bundle_vals.get(bfield), row.get(sfield)
            if bval != sval and not (bval is None and sval is None):
                value_mismatches += 1
    if value_mismatches:
        errors.append(f"{value_mismatches} request records differ from sidecar on token/latency fields")

    # --- tool ID comparison ---
    sidecar_tool_ids = set(r.get("tool_call_id") for r in tools
                           if r.get("trace_id") == native_trace_id)
    missing_tools = vw.tool_ids - sidecar_tool_ids
    extra_tools = sidecar_tool_ids - vw.tool_ids
    if missing_tools:
        errors.append(f"{len(missing_tools)} bundle tool IDs missing from sidecar: "
                      f"{sorted(str(t) for t in list(missing_tools)[:3])}")
    if extra_tools:
        errors.append(f"{len(extra_tools)} sidecar tool IDs not in bundle: "
                      f"{sorted(str(t) for t in list(extra_tools)[:3])}")
    if not vw.tool_ids and not sidecar_tool_ids:
        errors.append("both bundle and sidecar have zero tool records")

    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "sidecar_model_sha256": model_sha,
        "sidecar_tool_sha256": tool_sha,
        "bundle_request_keys": len(bundle_keys),
        "sidecar_request_keys": len(sidecar_keys),
        "value_mismatches": value_mismatches,
        "bundle_tool_ids": len(vw.tool_ids),
        "sidecar_tool_ids": len(sidecar_tool_ids),
        "checked": True,
    }


def run_pilot(catalog_path, selection_path, samples_candidates_path, output_dir=None):
    from ..adapters.catalog import Catalog as _Cat
    _catalog = _Cat(Path(catalog_path))
    # Load with gold verification
    result = load_pilot(Path(catalog_path), Path(selection_path), Path(samples_candidates_path))
    samples = result["samples"]
    # Sidecar cross-check is part of the joint check chain; failure fails the run.
    sidecar = _check_sidecar(_catalog, samples)
    if sidecar["status"] != "PASS":
        raise ValueError(f"sidecar cross-check failed: {sidecar.get('errors')}")
    pilot_inputs = [Path(catalog_path), Path(selection_path), Path(samples_candidates_path)]
    for s in samples:
        for f in s.files:
            pilot_inputs.append(Path(f["path"]))
    input_hashes = [_file_sha(p) for p in set(pilot_inputs)]

    macro = macro_summary(samples)
    cov = coverage_for(samples)
    # Capability rows for metrics not emitted by real runs
    cap = capability_rows(samples, [
        ("run_elapsed", "unsupported"),
        ("local_cpu_time", "unsupported"),
        ("tool_cpu_time", "unsupported"),
    ])
    all_cov = cov + cap
    cov_summary = summarize_coverage(all_cov)

    analysis_id = _stable_analysis_id(catalog_path, selection_path, samples_candidates_path, input_hashes)
    now_utc = datetime.now(timezone.utc).isoformat()

    response = {
        "status": "PASS",
        "analysis_id": analysis_id,
        "checked_at_utc": now_utc,
        "schema_version": "0.2.0",
        "cohort": result["cohort"],
        "macro": macro,
        "coverage": all_cov,
        "coverage_summary": cov_summary,
        "ledger": result["ledger"],
        "sidecar_check": sidecar,
    }

    qa = _quality_checks(response)
    if qa.get("issues"):
        response["status"] = "FAIL"
    if output_dir is not None:
        response["output"] = _publish(output_dir, response, catalog_path, selection_path,
                                      samples_candidates_path,
                                      samples, macro, all_cov, result["ledger"])
    else:
        response["output"] = None
    return response


def _publish(output_dir, response, catalog_path, selection_path, gold_path,
             samples, macro_rows, cov_rows, ledger):
    from ..adapters.catalog import Catalog
    destination = output_dir.resolve()
    project = Path(".").resolve()
    catalog = Catalog(Path(catalog_path))
    destination = _output_guard(project, destination, catalog)
    if destination.exists():
        raise ValueError("output dir already exists; refusing to overwrite")
    destination.mkdir(parents=True)

    # macro_summary.csv (stratified)
    with (destination / "macro_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_id", "sample_id", "profile", "trace_type", "entity_type",
                     "entity_level", "aggregation", "definition_key", "n_valid", "min", "max", "mean", "p50", "singleton"])
        for r in macro_rows:
            w.writerow([r["source_id"], r["sample_id"], r["profile"], r["trace_type"],
                        r["entity_type"], r["entity_level"], r["aggregation"], r["definition_key"],
                        r["n_valid"], r["min"], r["max"], r["mean"], r["p50"],
                        "yes" if r["singleton"] else "no"])

    # trace_coverage.csv
    with (destination / "trace_coverage.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_id", "sample_id", "profile", "trace_type", "entity_type",
                     "entity_level", "aggregation", "definition_key",
                     "n_total", "n_applicable", "n_not_applicable",
                     "n_present", "n_valid", "n_missing", "n_excluded",
                     "coverage_ratio", "missing_reasons", "exclusion_reasons",
                     "not_applicable_reason"])
        for r in cov_rows:
            w.writerow([r["source_id"], r["sample_id"], r["profile"], r["trace_type"],
                        r["entity_type"], r["entity_level"], r["aggregation"], r["definition_key"],
                        r["n_total"], r["n_applicable"], r["n_not_applicable"],
                        r["n_present"], r["n_valid"], r["n_missing"], r["n_excluded"],
                        r["coverage_ratio"],
                        json.dumps(r["missing_reasons"]), json.dumps(r["exclusion_reasons"]),
                        r["not_applicable_reason"]])

    # selection_ledger.jsonl
    from ..adapters.base import canonical_json
    with (destination / "selection_ledger.jsonl").open("w", encoding="utf-8") as f:
        for entry in ledger:
            f.write(canonical_json(entry) + "\n")

    # quality_checks.json
    qa = _quality_checks(response)
    (destination / "quality_checks.json").write_text(canonical_json(qa) + "\n", encoding="utf-8")

    # summary.md (write before manifest so it can be hashed)
    (destination / "summary.md").write_text(_summary_md(response), encoding="utf-8")

    # manifest.json (last, atomic completion marker)
    file_hashes = {}
    for child in destination.iterdir():
        if child.is_file():
            file_hashes[child.name] = hashlib.sha256(child.read_bytes()).hexdigest()
    manifest = {
        "analysis_id": response["analysis_id"],
        "spec": {
            "catalog_sha256": _file_sha(catalog_path),
            "selection_sha256": _file_sha(selection_path),
            "gold_sha256": _file_sha(Path(gold_path)) if gold_path else None,
            "input_files": [str(p) for p in set(
                f["path"] for s in samples for f in s.files)],
            "rule_version": "macro-coverage-0.1.0",
            "schema_version": "0.2.0",
        },
        "counts": {k: response["cohort"][k] for k in ("real_runs", "templates", "unassigned_requests", "bound_measured_requests", "ledger_rows")},
        "files": file_hashes,
        "status": response["status"],
    }
    (destination / "manifest.json").write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    return {"path": str(destination), "analysis_id": response["analysis_id"], "files": file_hashes}


def _quality_checks(response):
    from .macro import row_key
    issues = []
    for r in response["macro"]:
        if r["n_valid"] > 0 and r["min"] is None:
            issues.append(f"macro {r['definition_key']}: n_valid>0 but min null")
    # Macro/coverage alignment: every macro row must have exactly one matching
    # coverage row on the shared key, with identical n_valid.
    cov_by_key = {}
    for c in response["coverage"]:
        k = row_key(c["source_id"], c["sample_id"], c["entity_type"],
                    c["entity_level"], c["aggregation"], c["definition_key"])
        if k in cov_by_key:
            issues.append(f"coverage duplicate key: {k}")
        cov_by_key[k] = c
    for r in response["macro"]:
        k = row_key(r["source_id"], r["sample_id"], r["entity_type"],
                    r["entity_level"], r["aggregation"], r["definition_key"])
        match = cov_by_key.get(k)
        if match is None:
            issues.append(f"macro row without coverage match: {k}")
        elif match["n_valid"] != r["n_valid"]:
            issues.append(f"macro/coverage n_valid mismatch on {k}: "
                          f"macro={r['n_valid']} coverage={match['n_valid']}")
    response["status"] = "FAIL" if issues else response["status"]
    return {"status": response["status"], "issues": issues}


def _summary_md(response):
    lines = ["# Macro pilot summary", "", f"analysis_id: {response['analysis_id']}",
             f"status: {response['status']}", "",
             f"cohort: {json.dumps(response['cohort'], ensure_ascii=False)}", ""]
    lines.append("## Per-stratum macro (entity-level)")
    for r in response["macro"]:
        if r["entity_level"] == "entity":
            lines.append(
                f"- {r['definition_key']} [{r['source_id']}/{r['profile']}] "
                f"n_valid={r['n_valid']} min={r['min']} max={r['max']} mean={r['mean']} p50={r['p50']}"
                + (" singleton" if r["singleton"] else ""))
    return "\n".join(lines) + "\n"