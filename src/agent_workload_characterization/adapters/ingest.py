"""Immutable, content-addressed JSONL batches with explicit completion manifests."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3

from pydantic import ValidationError

from ..ir import SCHEMA_VERSION, validate_json
from .base import Adapter, Context, RecordError, canonical_json, stable_id
from .catalog import Catalog

FRAMEWORK_VERSION = "0.1.0"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def overlaps(a: Path, b: Path) -> bool:
    return a.is_relative_to(b) or b.is_relative_to(a)


def output_guard(project: Path, destination: Path, protected: tuple[Path, ...]) -> Path:
    """Resolve existing symlink ancestors, including for not-yet-existing output.

    Requires a trusted, non-concurrently-relinked project tree. This is a writer
    policy, not a security sandbox for hostile adapter code or other same-UID code.
    """
    project = project.resolve(strict=True)
    if project == Path(project.anchor):
        raise ValueError("filesystem root cannot be a project")
    normalized = project / "data" / "normalized"
    # Even the default output root must not be an alias outside the project.
    if normalized.resolve() != normalized:
        raise ValueError("normalized root must not have symlink ancestors")
    result = destination.resolve()
    if result != normalized and not result.is_relative_to(normalized):
        raise ValueError("output must be inside project data/normalized")
    for path in (*protected, project / "references", project / "data/raw"):
        if overlaps(result, path.resolve()):
            raise ValueError("output overlaps protected input")
    return result


def _write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(canonical_json(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def ingest(adapter: Adapter, catalog: Catalog, source_id: str, project: Path,
           *, output: Path | None = None, config: dict | None = None) -> dict:
    """Normalize one discovered file into a new immutable batch, or verify/reuse it.

    Expected record failures are quarantined. Unexpected adapter, input or I/O
    failures abort and leave an incomplete batch without manifest; never silently
    claim success, remove old files, or auto-overwrite a partial/corrupt batch.
    """
    source = catalog.source(source_id)
    inputs = adapter.discover(source)
    if len(inputs) != 1 or inputs[0].resolve(strict=True) != source.path:
        raise ValueError("v0.1 ingest requires exactly the catalog file locator")
    if not adapter.name or not adapter.version:
        raise ValueError("adapter name and version are required")
    if config is not None and not isinstance(config, dict):
        raise ValueError("adapter config must be a JSON object")
    config = json.loads(canonical_json({} if config is None else config))
    protected = (*catalog.protected_paths(), *inputs)
    destination = output_guard(project, output or project / "data/normalized", protected)
    source_hash = file_hash(inputs[0])
    snapshot = f"sha256:{source_hash}"
    spec = {"framework_version": FRAMEWORK_VERSION, "schema_version": SCHEMA_VERSION,
            "identity_version": "v1", "source_id": source_id, "snapshot_id": snapshot,
            "adapter": adapter.name, "adapter_version": adapter.version, "config": config,
            "catalog_entry_sha256": hashlib.sha256(canonical_json(source.metadata).encode()).hexdigest()}
    batch_id = hashlib.sha256(canonical_json(spec).encode()).hexdigest()
    batch = destination / batch_id
    output_guard(project, batch, protected)
    if batch.exists():
        if batch.is_symlink():
            raise ValueError("batch cannot be a symlink")
        manifest_path = batch / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError("incomplete batch; manual inspection required")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("spec") != spec or manifest.get("batch_id") != batch_id:
            raise ValueError("batch manifest conflict")
        if set(manifest.get("files", {})) != {"documents.jsonl", "records.jsonl", "rejects.jsonl", "identity.sqlite3"}:
            raise ValueError("batch file manifest conflict")
        for name, checksum in manifest["files"].items():
            path = batch / name
            if path.is_symlink() or file_hash(path) != checksum:
                raise ValueError("batch content changed")
        return {"batch_id": batch_id, "path": str(batch), "reused": True, "counts": manifest["counts"]}
    destination.mkdir(parents=True, exist_ok=True)
    # Exclusive directory creation arbitrates concurrent attempts; loser fails.
    batch.mkdir(mode=0o700)
    context = Context(source_id, snapshot, adapter.version, json.loads(canonical_json(config)))
    counts = {"seen": 0, "accepted": 0, "duplicates": 0, "rejected": 0, "runs": 0}
    database = sqlite3.connect(batch / "identity.sqlite3")
    try:
        database.execute("CREATE TABLE documents (identity TEXT PRIMARY KEY, digest TEXT NOT NULL)")
        database.execute("CREATE TABLE runs (identity TEXT PRIMARY KEY, document_id TEXT NOT NULL)")
        with (batch / "documents.jsonl").open("x", encoding="utf-8") as documents, \
             (batch / "records.jsonl").open("x", encoding="utf-8") as records, \
             (batch / "rejects.jsonl").open("x", encoding="utf-8") as rejects:
            for raw in adapter.records(inputs[0]):
                counts["seen"] += 1
                record_info = {"source_id": source_id, "snapshot_id": snapshot,
                               "source_record_ref": raw.source_record_ref, "raw_sha256": raw.raw_sha256}
                reason = raw.error
                if reason is None:
                    try:
                        doc = adapter.validate(adapter.normalize(raw, context))
                        doc = validate_json(doc.model_dump_json())
                        if not any(p.source_id == source_id and p.snapshot_id == snapshot
                                   and p.source_record_ref == raw.source_record_ref
                                   and p.adapter_version == adapter.version for p in doc.provenance):
                            raise RecordError("missing current source record lineage", code="lineage_error")
                        # The adapter must use a stable top-level identity. Provenance
                        # locators are excluded from content equivalence, not discarded.
                        entities = doc.runs or doc.templates or doc.requests or doc.events
                        if not entities:
                            raise RecordError("no independently identifiable normalized record")
                        identity = stable_id(source_id, "document", *sorted(e.id for e in entities))
                        value = doc.model_dump(mode="json")
                        comparison = json.loads(canonical_json(value))
                        for provenance in comparison["provenance"]:
                            provenance["source_record_ref"] = "<retained-in-records-index>"
                        digest = hashlib.sha256(canonical_json(comparison).encode()).hexdigest()
                        prior = database.execute("SELECT digest FROM documents WHERE identity=?", (identity,)).fetchone()
                        if prior:
                            if prior[0] != digest:
                                raise RecordError("identity conflict", code="identity_conflict")
                            counts["duplicates"] += 1
                            records.write(canonical_json(record_info | {"status": "duplicate", "document_id": identity}) + "\n")
                            continue
                        if any(database.execute("SELECT 1 FROM runs WHERE identity=?", (r.id,)).fetchone() for r in doc.runs):
                            raise RecordError("overlapping run document", code="overlapping_run_document")
                    except (RecordError, ValidationError) as error:
                        # Fixed categories only: arbitrary exception strings may leak payloads.
                        reason = "ir_validation" if isinstance(error, ValidationError) else error.code
                    else:
                        database.execute("INSERT INTO documents VALUES (?,?)", (identity, digest))
                        database.executemany("INSERT INTO runs VALUES (?,?)", [(r.id, identity) for r in doc.runs])
                        counts["accepted"] += 1
                        counts["runs"] += len(doc.runs)
                        documents.write(canonical_json({"document_id": identity, "trace": value}) + "\n")
                        records.write(canonical_json(record_info | {"status": "accepted", "document_id": identity}) + "\n")
                        continue
                counts["rejected"] += 1
                # Reader errors are codes, not exception messages or raw payloads.
                reason = reason if reason in ("record_too_large", "invalid_json_record", "ir_validation",
                                              "normalization_error", "lineage_error", "identity_conflict",
                                              "overlapping_run_document") else "record_error"
                rejection = record_info | {"status": "rejected", "reason": reason}
                rejects.write(canonical_json(rejection) + "\n")
                records.write(canonical_json(rejection) + "\n")
            for stream in (documents, records, rejects):
                stream.flush()
                os.fsync(stream.fileno())
        database.commit()
    finally:
        database.close()
    if file_hash(inputs[0]) != source_hash:
        raise ValueError("source changed during ingest; batch left incomplete")
    files = {name: file_hash(batch / name) for name in ("documents.jsonl", "records.jsonl", "rejects.jsonl", "identity.sqlite3")}
    # Manifest is the completion marker, linked atomically without overwrite.
    _write_json(batch / "completion.json", {"batch_id": batch_id, "spec": spec, "counts": counts,
                                          "quality_status": "has_rejects" if counts["rejected"] else "no_record_rejects",
                                          "input_locator": str(inputs[0]), "files": files})
    os.link(batch / "completion.json", batch / "manifest.json")
    return {"batch_id": batch_id, "path": str(batch), "reused": False, "counts": counts}
