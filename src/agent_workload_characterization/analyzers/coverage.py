"""Coverage calculation (P0-09): per-definition per-entity denominator accounting.

Fixed accounting identities:
  n_total = n_applicable + n_not_applicable
  n_applicable = n_valid + n_missing + n_excluded
  n_present = n_valid + n_excluded
  coverage_ratio = n_valid / n_applicable (null if denominator 0)

CPU metrics are applicable-but-missing for real runs, not_applicable for
templates, and not applied to unassigned requests.
"""


# Metrics that are semantically inapplicable to macro templates (no real
# execution): a template may still carry an unavailable CPU/time metric, which
# must be counted as not_applicable rather than missing.
_TEMPLATE_NOT_APPLICABLE = {"run_elapsed", "local_cpu_time", "tool_cpu_time"}


def coverage_for(loaded_samples):
    rows = []
    for sample in loaded_samples:
        for (def_key, agg), metrics in sample.entity_metrics.items():
            rows.append(_row(sample, def_key, metrics, entity_level=sample.entity_type))
        for def_key, metrics in sample.request_metrics.items():
            rows.append(_row(sample, def_key, metrics, entity_level="request"))
    return rows


def _row(sample, def_key, metrics, entity_level):
    # Template CPU/time metrics are not applicable (no real execution).
    is_template_na = sample.entity_type == "template" and def_key in _TEMPLATE_NOT_APPLICABLE
    if is_template_na:
        return _base_na(sample, def_key, metrics, entity_level)
    present = [m for m in metrics if m.value is not None]
    n_present = len(present)
    n_valid = sum(1 for m in present if m.evidence in ("observed", "derived", "template_parameter"))
    n_excluded = n_present - n_valid
    missing = [m for m in metrics if m.value is None]
    n_missing = len(missing)
    # n_applicable: how many of the entity's metrics are applicable (default = all present+missing)
    n_applicable = n_present + n_missing
    n_total = n_applicable  # entity count is 1 per row here; each metric is one applicable slot
    exclusion_reasons = {}
    for m in present:
        if m.evidence not in ("observed", "derived", "template_parameter"):
            exclusion_reasons[m.evidence] = exclusion_reasons.get(m.evidence, 0) + 1
    missing_reasons = {}
    for m in missing:
        r = m.missing_reason or "not_recorded"
        missing_reasons[r] = missing_reasons.get(r, 0) + 1
    coverage_ratio = n_valid / n_applicable if n_applicable else None
    return {
        "source_id": sample.source_id, "sample_id": sample.sample_id,
        "profile": sample.profile, "trace_type": sample.trace_type,
        "entity_type": sample.entity_type, "entity_level": entity_level,
        "aggregation": getattr(metrics[0], "aggregation", None) if metrics else None,
        "definition_key": def_key,
        "n_total": n_total, "n_applicable": n_applicable, "n_not_applicable": 0,
        "n_present": n_present, "n_valid": n_valid, "n_missing": n_missing,
        "n_excluded": n_excluded,
        "missing_reasons": missing_reasons, "exclusion_reasons": exclusion_reasons,
        "coverage_ratio": coverage_ratio,
        "not_applicable_reason": None,
    }


def _base_na(sample, def_key, metrics, entity_level):
    # Keep the metric's own aggregation so coverage rows align with macro rows.
    agg = getattr(metrics[0], "aggregation", None) if metrics else None
    return {
        "source_id": sample.source_id, "sample_id": sample.sample_id,
        "profile": sample.profile, "trace_type": sample.trace_type,
        "entity_type": sample.entity_type, "entity_level": entity_level,
        "aggregation": agg,
        "definition_key": def_key,
        "n_total": 1, "n_applicable": 0, "n_not_applicable": 1,
        "n_present": 0, "n_valid": 0, "n_missing": 0, "n_excluded": 0,
        "missing_reasons": {}, "exclusion_reasons": {},
        "coverage_ratio": None, "not_applicable_reason": "no_real_execution_in_template",
    }


def capability_rows(samples, capability_defs):
    """Emit explicit unavailable capability rows for metrics that the IR did not emit.

    capability_defs: list of (definition_key, applicable_profiles, reason).
    For each run sample, a capability metric is applicable-but-missing.
    """
    rows = []
    for sample in samples:
        for def_key, reason in capability_defs:
            if sample.entity_type != "run":
                continue
            metrics = [m for (name, _agg), ms in sample.entity_metrics.items()
                       if name == def_key for m in ms]
            if metrics:
                continue  # already covered by normal coverage
            rows.append({
                "source_id": sample.source_id, "sample_id": sample.sample_id,
                "profile": sample.profile, "trace_type": sample.trace_type,
                "entity_type": sample.entity_type, "entity_level": sample.entity_type,
                "definition_key": def_key,
                "n_total": 1, "n_applicable": 1, "n_not_applicable": 0,
                "n_present": 0, "n_valid": 0, "n_missing": 1, "n_excluded": 0,
                "missing_reasons": {reason: 1}, "exclusion_reasons": {}, "aggregation": None,
                "coverage_ratio": 0.0, "not_applicable_reason": None,
            })
    return rows


def summarize_coverage(rows):
    out = {}
    for row in rows:
        key = row["definition_key"]
        if key not in out:
            out[key] = {"n_valid": 0, "n_total": 0, "n_applicable": 0}
        out[key]["n_valid"] += row["n_valid"]
        out[key]["n_total"] += row["n_total"]
        out[key]["n_applicable"] += row["n_applicable"]
    return out