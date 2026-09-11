"""Read-only, bounded-selector regression for the two audited AgentX records."""

import hashlib
from pathlib import Path

from .agentx import AgentXAdapter, summarize
from .base import Context, RawRecord, strict_object
from .catalog import Catalog, UniqueLoader
from ..ir import validate_json
import yaml


def check_samples(catalog_path: Path, samples_path: Path) -> dict:
    catalog = Catalog(catalog_path)
    with samples_path.open(encoding="utf-8") as stream:
        selectors = yaml.load(stream, Loader=UniqueLoader)
    candidates = {item["sample_id"]: item for item in selectors["real_candidates"] if item["sample_id"] in ("AX-7", "AX-SUB")}
    if set(candidates) != {"AX-7", "AX-SUB"}:
        raise ValueError("both audited AgentX sample selectors are required")
    source = catalog.source("agentx_256k")
    selected = {}
    for sample_id, item in candidates.items():
        locator = item["locator"]
        if item["source_id"] != source.source_id:
            raise ValueError("sample source does not match catalog")
        location = (Path(selectors["roots"][locator["root"]]) / locator["path"]).resolve(strict=True)
        number = locator["line_1based"]
        if location != source.path or type(number) is not int or number <= 0 or number in selected:
            raise ValueError("invalid or duplicate sample locator")
        selected[number] = (sample_id, item)
    adapter = AgentXAdapter()
    results = []
    stat_before = source.path.stat()
    # Read through the highest selector, but parse/normalize only selected rows.
    # No whole-file SHA claim: sample snapshots are explicitly record-scoped.
    with source.path.open("rb") as stream:
        for number in range(1, max(selected) + 1):
            line = stream.readline()
            if not line:
                raise ValueError("selected sample is missing")
            if number not in selected:
                continue
            sample_id, item = selected[number]
            raw = strict_object(line)
            if raw.get("id") != item["locator"]["record_id"]:
                raise ValueError("selected record identity changed")
            row_hash = hashlib.sha256(line).hexdigest()
            record = RawRecord(f"line:{number}", row_hash, raw)
            context = Context(source.source_id, "record-sha256:" + row_hash, adapter.version, {})
            document = adapter.normalize(record, context)
            if validate_json(document.model_dump_json()) != document:
                raise ValueError("IR round-trip mismatch")
            summary = summarize(document)
            actual = summary["metrics"]
            observed = {"main_requests": actual["main_agent"]["model_request_count"]["value"],
                        "model_requests": actual["all_agents"]["model_request_count"]["value"],
                        "subagent_groups": actual["all_agents"]["subagent_count"]["value"],
                        "input_tokens": actual["all_agents"]["input_tokens"]["value"],
                        "output_tokens": actual["all_agents"]["output_tokens"]["value"]}
            mismatches = [key for key, expected in item["expected"].items() if observed.get(key) != expected]
            # Compare entire hash vectors and declared scope, not only lengths.
            original_requests = []
            def collect(items):
                for request in items:
                    if request["type"] == "subagent":
                        collect(request["requests"])
                    else:
                        original_requests.append(request)
            collect(raw["requests"])
            prefix_ok = len(original_requests) == len(document.requests) and all(
                request.prefix is not None and request.prefix.hashes == [str(h) for h in original["hash_ids"]]
                and request.prefix.block_size == raw["block_size"] and request.prefix.hash_id_scope == raw["hash_id_scope"]
                for original, request in zip(original_requests, document.requests, strict=True))
            if not prefix_ok:
                mismatches.append("prefix_vectors")
            for name in ("turn_count", "tool_call_count", "run_elapsed", "local_cpu_time"):
                if actual["all_agents"][name]["value"] is not None:
                    mismatches.append(name)
            results.append({"sample_id": sample_id, "line_1based": number, "record_id": raw["id"],
                            "row_sha256": row_hash, "status": "FAIL" if mismatches else "PASS",
                            "mismatches": mismatches, "prefix_vectors_equal": prefix_ok, "summary": summary})
    stat_after = source.path.stat()
    if (stat_before.st_size, stat_before.st_mtime_ns, stat_before.st_ino) != (stat_after.st_size, stat_after.st_mtime_ns, stat_after.st_ino):
        raise ValueError("source changed while selecting samples")
    return {"task": "P0-04", "adapter_version": adapter.version,
            "status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
            "source_id": source.source_id, "source_path": str(source.path),
            "snapshot_scope": "selected raw record hashes only; whole-file audit checksum not reverified",
            "parsed_records": len(results), "full_ingest": False, "results": results}
