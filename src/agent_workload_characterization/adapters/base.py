"""Separate source interpretation from streaming, rejection and batch storage."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Iterator

from ..ir import TraceDocument, validate_json
from .catalog import Source


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stable_id(source_id: str, kind: str, *identity_parts: str) -> str:
    """Identity v1: source namespace + semantic key, NOT path/snapshot/adapter.

    Callers must include model/attempt identity when the native key needs it.
    Only source adapters can determine equivalence between separate source IDs.
    """
    parts = (source_id, kind, *identity_parts)
    if len(parts) < 3 or any(not isinstance(x, str) or not x.strip() for x in parts):
        raise ValueError("identity needs nonempty source, kind and semantic key")
    digest = hashlib.sha256(canonical_json(parts).encode()).hexdigest()
    return f"awc:v1:{digest}"


class RecordError(ValueError):
    """Expected per-record rejection; never log the exception payload."""

    def __init__(self, message: str, *, code: str = "normalization_error"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RawRecord:
    source_record_ref: str
    raw_sha256: str
    value: dict | None
    error: str | None = None


@dataclass(frozen=True)
class Context:
    source_id: str
    snapshot_id: str
    adapter_version: str
    config: dict


def strict_object(payload: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RecordError("duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise RecordError("nonfinite number")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise RecordError("overflowed JSON number")
        return number

    result = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs,
                        parse_constant=invalid, parse_float=finite_float)
    if not isinstance(result, dict):
        raise RecordError("record must be object")
    return result


def jsonl_records(path: Path, *, max_record_bytes: int = 8 * 1024 * 1024) -> Iterator[RawRecord]:
    """Bounded line reader; every physical line is accepted or explicitly rejected."""
    if type(max_record_bytes) is not int or max_record_bytes < 1:
        raise ValueError("max_record_bytes must be positive integer")
    with path.open("rb") as stream:
        number = 0
        while chunk := stream.readline(max_record_bytes + 1):
            number += 1
            digest = hashlib.sha256(chunk)
            oversized = len(chunk) > max_record_bytes
            if oversized:
                while not chunk.endswith(b"\n"):
                    chunk = stream.readline(max_record_bytes + 1)
                    if not chunk:
                        break
                    digest.update(chunk)
                yield RawRecord(f"line:{number}", digest.hexdigest(), None, "record_too_large")
                continue
            try:
                value = strict_object(chunk)
            except (ValueError, UnicodeError, RecursionError):
                yield RawRecord(f"line:{number}", digest.hexdigest(), None, "invalid_json_record")
            else:
                yield RawRecord(f"line:{number}", digest.hexdigest(), value)


class Adapter(ABC):
    """Trusted project code, not a plugin sandbox; never execute trace content."""

    name: str
    version: str

    def discover(self, source: Source) -> tuple[Path, ...]:
        # Explicit narrow default: directory/archive discovery needs source logic.
        if source.kind != "file" or source.path.suffix != ".jsonl" or not source.path.is_file():
            raise ValueError("default adapter supports one regular JSONL file only")
        return (source.path,)

    def inspect(self, source: Source) -> dict:
        return {"source_id": source.source_id, "inputs": [str(p) for p in self.discover(source)],
                "adapter": self.name, "adapter_version": self.version}

    def records(self, path: Path) -> Iterator[RawRecord]:
        return jsonl_records(path)

    @abstractmethod
    def normalize(self, record: RawRecord, context: Context) -> TraceDocument:
        """Return one closed IR document or raise RecordError; never return None."""

    def validate(self, document: TraceDocument) -> TraceDocument:
        # Revalidate mutable model instances instead of trusting their old state.
        if not isinstance(document, TraceDocument):
            raise RecordError("normalize must return TraceDocument")
        return validate_json(document.model_dump_json())
