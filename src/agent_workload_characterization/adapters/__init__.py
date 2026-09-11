"""Common adapter API; no production source adapter is registered yet."""

from .base import Adapter, RawRecord, RecordError, stable_id
from .catalog import Catalog
from .ingest import ingest

__all__ = ["Adapter", "Catalog", "RawRecord", "RecordError", "ingest", "stable_id"]
