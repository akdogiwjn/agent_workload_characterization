"""Explicit, pure v0.1 -> v0.2 upgrade; never rewrites source files."""

from .adapters.base import strict_object
from .ir import TraceDocument, validate_json


def upgrade_v0_1(payload: str | bytes) -> TraceDocument:
    data = strict_object(payload.encode() if isinstance(payload, str) else payload)
    if data.get("schema_version") != "0.1.0":
        raise ValueError("migration requires schema 0.1.0")
    # Reject fields/values that were not part of v0.1, then use all shared rules.
    for clock in data.get("clocks", []):
        if "precision_missing_reason" in clock or clock.get("precision_ns") is None:
            raise ValueError("invalid v0.1 clock")
    additions = {"agents": {"source_agent_id", "source_agent_type", "source_status"},
                 "requests": {"model_name", "source_request_type"}}
    for group, fields in additions.items():
        if any(fields.intersection(row) for row in data.get(group, [])):
            raise ValueError("v0.2 fields present in v0.1 payload")
    data["schema_version"] = "0.2.0"
    from .adapters.base import canonical_json
    return validate_json(canonical_json(data))
