"""Semantic event recorder for the coding pilot (RUN-01, P1-01 subset).

Records run / LLM-request / tool-call / container / verifier lifecycle
events with same-host monotonic timestamps plus a UTC wall-clock anchor.
Events are appended to a JSONL file inside the run directory; the file is
append-only while a run is open and sealed (never rewritten) afterwards.

Contract notes (docs/trace_contract.md):
- durations come from ONE monotonic clock domain; the UTC anchor is stored
  separately and never subtracted from monotonic values;
- unfinished events keep status='unclosed' with a null end — never zero;
- credentials never enter event payloads: sensitive keys are rejected at
  record time, and text fields are canary-checked before persistence.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..runners.preparation import (SENSITIVE_CONFIG_KEYS, _sanitize_error,
                                   _sanitize_usage)

_SECRET_VALUE_RE = re.compile(r"(sk-[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._-]{8,})")

# Event kinds emitted by the pilot runner.
EVENT_KINDS = ("run", "llm_request", "tool_call", "container", "verifier",
               "archive", "budget", "infra")

# Attr keys allowed per event kind (whitelist; new keys are dropped, not
# propagated silently).
_ATTR_WHITELIST = {
    "run": ("run_id", "attempt_id", "task_id", "source_type", "phase"),
    "llm_request": ("request_id", "step_index", "ok", "usage", "error",
                    "cost_status", "model", "t_start_ns", "t_end_ns",
                    "timing_source"),
    "tool_call": ("tool_index", "command", "category", "returncode",
                  "timed_out", "error", "container_id"),
    "container": ("container_id", "image", "scope", "action", "detail"),
    "verifier": ("status", "resolved", "detail"),
    "archive": ("status", "detail"),
    "budget": ("limit_name", "observed", "detail"),
    "infra": ("status", "detail"),
}


class ClockError(ValueError):
    """Raised when timestamps from different clock domains are mixed."""


class Clock:
    """Single monotonic clock domain + UTC anchor provider.

    Subclasses may provide deterministic time for tests; production code
    uses SystemClock. Monotonic values from different Clock instances must
    never be subtracted from each other (enforced by WallSpan below)."""

    domain: str = "system_monotonic"

    def monotonic_ns(self) -> int:
        raise NotImplementedError

    def utc_now_iso(self) -> str:
        raise NotImplementedError


class SystemClock(Clock):
    domain = "system_monotonic"

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()

    def utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class FakeClock(Clock):
    """Deterministic clock for synthetic tests (advance() moves time)."""

    def __init__(self, start_ns: int = 1_000_000_000):
        self._now_ns = start_ns
        self.domain = f"fake_{id(self):x}"

    def monotonic_ns(self) -> int:
        return self._now_ns

    def utc_now_iso(self) -> str:
        return datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()

    def advance_ns(self, delta_ns: int) -> None:
        if delta_ns < 0:
            raise ClockError("FakeClock cannot go backwards")
        self._now_ns += delta_ns

    def advance_s(self, delta_s: float) -> None:
        self.advance_ns(int(delta_s * 1_000_000_000))


class WallSpan:
    """Duration between two monotonic stamps of the SAME clock domain."""

    def __init__(self, clock: Clock, t_start_ns: int, t_end_ns: int | None):
        if t_end_ns is not None and t_end_ns < t_start_ns:
            raise ClockError("end before start within one clock domain")
        self.clock = clock
        self.t_start_ns = t_start_ns
        self.t_end_ns = t_end_ns

    @property
    def duration_s(self) -> float | None:
        if self.t_end_ns is None:
            return None  # unclosed — never zero
        return (self.t_end_ns - self.t_start_ns) / 1e9


def _check_attrs_safe(kind: str, attrs: dict[str, Any],
                      *, value_checked_skip: tuple[str, ...] = ()) -> None:
    """Reject credential-bearing payloads before they reach any file.

    Keys in value_checked_skip (e.g. 'error' after sanitization) skip the
    credential-value regex because their content is already type-classified.
    """
    for key in attrs:
        if any(s in str(key).lower() for s in SENSITIVE_CONFIG_KEYS):
            raise ValueError(f"sensitive attr key rejected: {key!r}")
    for key, value in attrs.items():
        if key in value_checked_skip or not isinstance(value, str):
            continue
        if _SECRET_VALUE_RE.search(value):
            raise ValueError(f"credential-like value rejected in attr {key!r}")


def duration_s(event_start: dict, event_end: dict) -> float | None:
    """Duration between two events of the SAME clock domain.

    Mixing clock domains raises ClockError instead of silently producing a
    meaningless number. Unclosed ends return None (never zero)."""
    if event_end["t_monotonic_ns"] < event_start["t_monotonic_ns"]:
        raise ClockError("end before start")
    if event_start.get("clock_domain") != event_end.get("clock_domain"):
        raise ClockError(
            f"clock domain mismatch: {event_start.get('clock_domain')} vs "
            f"{event_end.get('clock_domain')}; cross-domain subtraction refused")
    if event_end.get("status") == "unclosed" or event_start.get("status") == "unclosed":
        return None
    return (event_end["t_monotonic_ns"] - event_start["t_monotonic_ns"]) / 1e9


class SemanticRecorder:
    """Append-only JSONL event log for one run attempt."""

    def __init__(self, run_dir: Path, clock: Clock, *,
                 run_id: str, attempt_id: str, task_id: str,
                 source_type: str):
        self.run_dir = run_dir
        self.clock = clock
        self.run_id = run_id
        self.attempt_id = attempt_id
        self.task_id = task_id
        self.source_type = source_type  # synthetic | benchmark_real
        self._path = run_dir / "events.jsonl"
        self._open_events: dict[str, dict] = {}
        self._sealed = False
        self._anchor_written = False

    # -- low-level ---------------------------------------------------------

    def _emit(self, event: dict) -> None:
        if self._sealed:
            raise RuntimeError("recorder sealed; events are immutable")
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _stamp(self) -> dict:
        return {"t_monotonic_ns": self.clock.monotonic_ns(),
                "t_utc": self.clock.utc_now_iso(),
                "clock_domain": self.clock.domain}

    # -- lifecycle ---------------------------------------------------------

    def begin_run(self) -> None:
        if self._anchor_written:
            raise RuntimeError("run already begun")
        self._anchor_written = True
        self._emit({"event_id": uuid.uuid4().hex, "kind": "run",
                    "status": "open", "parent_id": None,
                    **self._stamp(),
                    "attrs": {"run_id": self.run_id,
                              "attempt_id": self.attempt_id,
                              "task_id": self.task_id,
                              "source_type": self.source_type,
                              "phase": "execution"}})

    def begin(self, kind: str, attrs: dict[str, Any] | None = None) -> str:
        if kind not in EVENT_KINDS or kind == "run":
            raise ValueError(f"invalid event kind: {kind!r}")
        attrs = dict(attrs or {})
        _check_attrs_safe(kind, attrs)
        kept = {k: attrs[k] for k in _ATTR_WHITELIST[kind] if k in attrs}
        event_id = uuid.uuid4().hex
        self._open_events[event_id] = kind
        self._emit({"event_id": event_id, "kind": kind, "status": "open",
                    "parent_id": None, **self._stamp(), "attrs": kept})
        return event_id

    def end(self, event_id: str, *, attrs: dict[str, Any] | None = None,
            error: str | None = None) -> None:
        if event_id not in self._open_events:
            raise KeyError(f"unknown or already-closed event: {event_id}")
        kind = self._open_events.pop(event_id)
        attrs = dict(attrs or {})
        if error is not None:
            attrs["error"] = error
        # any error text — from the error= argument or an attrs dict — is
        # type-classified before persistence; raw third-party messages never
        # reach the file
        if isinstance(attrs.get("error"), str):
            attrs["error"] = _sanitize_error(attrs.pop("error"))
        _check_attrs_safe(kind, attrs, value_checked_skip=("error",))
        kept = {k: attrs[k] for k in _ATTR_WHITELIST[kind] if k in attrs}
        if "usage" in kept and isinstance(kept["usage"], dict):
            kept["usage"] = _sanitize_usage(kept["usage"])
        self._emit({"event_id": event_id, "kind": kind,
                    "status": "closed" if error is None else "error",
                    "parent_id": None, **self._stamp(), "attrs": kept})

    def point(self, kind: str, attrs: dict[str, Any] | None = None) -> None:
        """Instantaneous event (container action, budget hit, archive)."""
        if kind not in EVENT_KINDS or kind in ("run",):
            raise ValueError(f"invalid point-event kind: {kind!r}")
        attrs = dict(attrs or {})
        _check_attrs_safe(kind, attrs)
        kept = {k: attrs[k] for k in _ATTR_WHITELIST[kind] if k in attrs}
        self._emit({"event_id": uuid.uuid4().hex, "kind": kind,
                    "status": "point", "parent_id": None,
                    **self._stamp(), "attrs": kept})

    def seal(self) -> dict:
        """Close the run: mark unclosed events, write the anchor, seal file."""
        if not self._anchor_written:
            raise RuntimeError("cannot seal a run that never began")
        for event_id, kind in list(self._open_events.items()):
            self._emit({"event_id": event_id, "kind": kind,
                        "status": "unclosed", "parent_id": None,
                        **self._stamp(), "attrs": {"note": "right-censored; "
                                                         "end never observed"}})
        self._open_events.clear()
        self._emit({"event_id": uuid.uuid4().hex, "kind": "run",
                    "status": "closed", "parent_id": None, **self._stamp(),
                    "attrs": {"run_id": self.run_id,
                              "attempt_id": self.attempt_id,
                              "task_id": self.task_id,
                              "source_type": self.source_type,
                              "phase": "sealed"}})
        self._sealed = True
        return {"events_path": str(self._path),
                "sealed": True,
                "clock_domain": self.clock.domain}
