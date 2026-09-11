"""Macro summary (P0-08): stratified by source/profile/entity_type.

Each stratum is reported separately — no cross-source merging. P50 formula
h=(n-1)*0.5. Entity-level and request-level summaries are separate.
"""

import math

# Canonical row key shared by macro and coverage so the two outputs align
# on (source_id, sample_id, entity_type, entity_level, aggregation, definition_key).
REQUEST_AGGREGATION = "single_request"


def row_key(source_id, sample_id, entity_type, entity_level, aggregation, definition_key):
    return (source_id, sample_id, entity_type, entity_level, aggregation, definition_key)


def p50(values):
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    h = (len(ordered) - 1) * 0.5
    lo = math.floor(h)
    hi = math.ceil(h)
    return (ordered[lo] + ordered[hi]) / 2.0


def mean(values):
    return sum(values) / len(values) if values else None


def macro_summary(loaded_samples):
    """Stratified per-definition summary. No cross-source/template merging."""
    rows = []
    for sample in loaded_samples:
        for (def_key, agg), metrics in sample.entity_metrics.items():
            vals = [(m.value, m.evidence) for m in metrics if m.value is not None
                    and m.evidence in ("observed", "derived", "template_parameter")]
            if not vals:
                rows.append(_row(def_key, sample, n_valid=0, aggregation=agg))
                continue
            nums = [v for v, _ in vals]
            rows.append(_row(def_key, sample, n_valid=len(nums),
                             min_val=min(nums), max_val=max(nums),
                             mean_val=mean(nums), p50_val=p50(nums),
                             singleton=len(nums) == 1, aggregation=agg))
    # Request-level summary per source
    for sample in loaded_samples:
        if not sample.request_metrics:
            continue
        for def_key, metrics in sample.request_metrics.items():
            vals = [(m.value, m.evidence) for m in metrics if m.value is not None
                    and m.evidence in ("observed", "derived")]
            if not vals:
                rows.append(_row(def_key, sample, n_valid=0, entity_level="request",
                                 aggregation=REQUEST_AGGREGATION))
                continue
            nums = [v for v, _ in vals]
            rows.append(_row(def_key, sample, n_valid=len(nums),
                             min_val=min(nums), max_val=max(nums),
                             mean_val=mean(nums), p50_val=p50(nums),
                             entity_level="request", aggregation=REQUEST_AGGREGATION))
    return rows


def _row(def_key, sample, n_valid=0,
         min_val=None, max_val=None, mean_val=None, p50_val=None,
         singleton=False, entity_level=None, aggregation=None):
    return {
        "source_id": sample.source_id, "sample_id": sample.sample_id,
        "profile": sample.profile, "trace_type": sample.trace_type,
        "entity_type": sample.entity_type,
        "entity_level": entity_level or sample.entity_type,
        "aggregation": aggregation,
        "definition_key": def_key,
        "n_valid": n_valid, "min": min_val, "max": max_val,
        "mean": mean_val, "p50": p50_val, "singleton": singleton,
    }