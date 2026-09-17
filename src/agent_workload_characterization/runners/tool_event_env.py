"""G1-01 shared tool-event recording environment.

Single implementation used by BOTH the mini child process (via the
REAL_CHILD_CODE source, which reads this module's source text so the
subprocess needs no import path) and the G1-01-B container validation
entry. Semantics are unchanged from the A-round hook:

- OPEN line persisted (flushed) BEFORE the inner execute call;
- CLOSED line after (returncode/exception_present/output_length,
  t_start/t_end CLOCK_MONOTONIC ns);
- ERROR line on exception (type only, e.g. the Submitted interrupt) —
  the open stays explicitly non-closed, never a fake closed record;
- command projected to sha256+length only (no raw command/output/
  environment/traceback in events);
- no Agent/model loop involvement: this is an Environment wrapper.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

TOOL_EVENT_WRAPPED_SOURCE = r'''
import hashlib, json, time, uuid


class ToolEventRecordingEnvironment:
    """Wraps an inner Environment; brackets every execute() with an
    OPEN line persisted BEFORE the call and a CLOSED/ERROR line after.
    Safe projections only; same-host CLOCK_MONOTONIC."""

    def __init__(self, inner, events_path):
        self._inner = inner
        self._fh = open(events_path, "a") if events_path else None
        self._seq = 0

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def execute(self, action, cwd="", *, timeout=None):
        self._seq += 1
        cmd = action.get("command", "")
        view = {"sha256": hashlib.sha256(cmd.encode()).hexdigest(),
                "length": len(cmd)}
        event_id = uuid.uuid4().hex
        t_start = time.monotonic_ns()
        if self._fh:
            self._fh.write(json.dumps({
                "event": "open", "event_id": event_id,
                "tool_call_id": action.get("tool_call_id"),
                "seq": self._seq, "command_view": view,
                "t_start_ns": t_start}) + "\n")
            self._fh.flush()
        try:
            output = self._inner.execute(action, cwd=cwd, timeout=timeout)
        except BaseException as exc:
            if self._fh:
                self._fh.write(json.dumps({
                    "event": "error", "event_id": event_id,
                    "tool_call_id": action.get("tool_call_id"),
                    "seq": self._seq,
                    "exception_type": type(exc).__name__,
                    "t_start_ns": t_start,
                    "t_end_ns": time.monotonic_ns()}) + "\n")
                self._fh.flush()
            raise
        if self._fh:
            self._fh.write(json.dumps({
                "event": "closed", "event_id": event_id,
                "tool_call_id": action.get("tool_call_id"),
                "seq": self._seq,
                "returncode": output.get("returncode"),
                "exception_present": bool(output.get("exception_info")),
                "output_length": len(output.get("output") or ""),
                "t_start_ns": t_start,
                "t_end_ns": time.monotonic_ns()}) + "\n")
            self._fh.flush()
        return output

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None
'''


def wrap_environment(inner: Any, events_path) -> Any:
    """Host-side wrap (B entry). The mini child uses the SAME source
    text (TOOL_EVENT_WRAPPED_SOURCE) embedded in its payload — one
    implementation, two entrypoints."""
    namespace: dict = {}
    exec(TOOL_EVENT_WRAPPED_SOURCE, namespace)
    return namespace["ToolEventRecordingEnvironment"](inner, events_path)
