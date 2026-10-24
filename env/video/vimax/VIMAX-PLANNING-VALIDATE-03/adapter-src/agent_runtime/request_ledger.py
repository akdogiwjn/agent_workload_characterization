"""Unified request ledger + pre-send budget gate for the Bailian adaptation.

One JSONL ledger covers LLM calls (outer agent + inner LangChain), image
generation, video create/poll and media downloads. Design rules:

- an `open` event is persisted BEFORE the request is sent (with a logical
  request id, role/stage, model, monotonic start);
- every open is closed by `close` (ok) or `error` (failure, with the error
  type; right-censoring is explicit when the outcome is unknown, e.g. a
  transport timeout on a paid generation);
- tool-call ids, logical requests, HTTP exchanges and remote jobs are
  DISTINCT concepts and are recorded as separate fields, never conflated;
- ledger write failures are NOT swallowed: they are counted, stored in a
  sidecar state file and surfaced via `failure_state()`;
- the budget gate raises BudgetExceeded BEFORE a send when a configured cap
  (calls / attempts / generations / creates / polls / downloads /
  single-request output tokens / shared wall deadline) is exhausted;
- observed usage totals are SOFT thresholds of already-returned usage — they
  are never presented as hard money or token guarantees.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextvars import ContextVar
from contextvars import Token
from pathlib import Path
from typing import Any

CAP_KEYS = (
    "llm_calls", "llm_attempts", "image_generations", "video_creates",
    "video_polls", "media_downloads", "single_request_output_tokens",
)

_CURRENT_REQUEST_ID: ContextVar[str | None] = ContextVar("vimax_current_request_id", default=None)


def bind_current_request(request_id: str) -> Token:
    return _CURRENT_REQUEST_ID.set(request_id)


def get_current_request_id() -> str | None:
    return _CURRENT_REQUEST_ID.get()


def clear_current_request() -> None:
    _CURRENT_REQUEST_ID.set(None)


class BudgetExceeded(RuntimeError):
    def __init__(self, key: str, cap: int, detail: str = "") -> None:
        self.key = key
        self.cap = cap
        super().__init__(
            f"budget cap exceeded before send: {key} cap={cap}"
            + (f"; {detail}" if detail else ""))


class DeadlineExceeded(RuntimeError):
    pass


class LedgerWriteError(RuntimeError):
    """A required pre-send ledger event could not be persisted."""


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class RequestLedger:
    """Process-wide singleton-style ledger (one per agent/adapter process)."""

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {k: 0 for k in CAP_KEYS}
        self._observed_output_tokens = 0
        self._write_failures = 0
        self._write_failure_last: str | None = None
        self._open: dict[str, dict] = {}
        caps: dict[str, int | None] = {k: _env_int(
            f"VIMAX_BAILIAN_BUDGET_{k.upper()}") for k in CAP_KEYS}
        self._caps = caps
        self._deadline = _env_float("VIMAX_BAILIAN_BUDGET_DEADLINE_SECONDS")
        self._t0 = time.monotonic()

    # ------------------------------------------------------------------ #
    # persistence (failures are recorded, never silently swallowed)
    # ------------------------------------------------------------------ #
    def _append(self, event: dict, *, required: bool = False) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError as exc:
            self._write_failures += 1
            self._write_failure_last = f"{type(exc).__name__}: {exc}"
            try:
                sidecar = self.path.with_suffix(
                    self.path.suffix + ".writefailures")
                sidecar.parent.mkdir(parents=True, exist_ok=True)
                with open(sidecar, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({
                        "ts": time.time(), "error": self._write_failure_last,
                        "event_kind": event.get("kind"),
                    }, ensure_ascii=False) + "\n")
            except OSError:
                pass  # sidecar is best-effort; counter above is the source
            if required:
                raise LedgerWriteError(
                    "required request-ledger event could not be persisted"
                ) from exc

    # ------------------------------------------------------------------ #
    # budget gate (pre-send)
    # ------------------------------------------------------------------ #
    def guard(self, key: str, n: int = 1) -> None:
        """Raise BEFORE any network send when the cap or deadline is hit."""
        if self._deadline is not None and \
                time.monotonic() - self._t0 > self._deadline:
            raise DeadlineExceeded(
                f"shared wall budget exhausted "
                f"({self._deadline:g}s since ledger start)")
        cap = self._caps.get(key)
        with self._lock:
            if cap is not None and self._counts.get(key, 0) + n > cap:
                raise BudgetExceeded(key, cap,
                                     f"already_sent={self._counts.get(key, 0)}")

    def bump(self, key: str, n: int = 1) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + n

    def reserve_and_open(self, kind: str, reservations: dict[str, int],
                         **fields: Any) -> str:
        """Atomically enforce caps, reserve counters and persist a pre-send open.

        A failed required write leaves the reservation consumed, so a caller
        cannot accidentally turn a persistence failure into extra request
        capacity.  The exception is raised before the model transport runs.
        """
        with self._lock:
            if self._deadline is not None and \
                    time.monotonic() - self._t0 >= self._deadline:
                raise DeadlineExceeded(
                    f"shared wall budget exhausted "
                    f"({self._deadline:g}s since ledger start)")
            if self.path is None:
                self._write_failures += 1
                self._write_failure_last = (
                    "LedgerWriteError: request-ledger path is not configured")
                raise LedgerWriteError(
                    "request-ledger path is not configured; refusing model send")
            for key, n in reservations.items():
                cap = self._caps.get(key)
                current = self._counts.get(key, 0)
                if cap is not None and current + n > cap:
                    raise BudgetExceeded(key, cap,
                                         f"already_sent={current}")
            for key, n in reservations.items():
                self._counts[key] = self._counts.get(key, 0) + n
            request_id = "req-" + uuid.uuid4().hex[:12]
            event = {"kind": "open", "request_id": request_id,
                     "op": kind,
                     "t_start_monotonic": round(time.monotonic(), 3),
                     "t_start_wall": time.time(), **fields}
            self._append(event, required=True)
            self._open[request_id] = {"op": kind, **fields}
            return request_id

    def guard_output_tokens(self, expected_max: int) -> None:
        """Soft observed-usage threshold check for a single request's output
        cap (max_completion_tokens style). Enforced by the caller before the
        send; observed totals are informational."""
        cap = self._caps.get("single_request_output_tokens")
        if cap is not None and expected_max > cap:
            raise BudgetExceeded("single_request_output_tokens", cap,
                                 f"requested={expected_max}")

    # ------------------------------------------------------------------ #
    # event recording
    # ------------------------------------------------------------------ #
    def open(self, kind: str, **fields: Any) -> str:
        request_id = "req-" + uuid.uuid4().hex[:12]
        event = {"kind": "open", "request_id": request_id, "op": kind,
                 "t_start_monotonic": round(time.monotonic(), 3),
                 "t_start_wall": time.time(), **fields}
        self._append(event)
        with self._lock:
            self._open[request_id] = {"op": kind, **fields}
        return request_id

    def close(self, request_id: str, status: str = "ok", **fields: Any) -> None:
        with self._lock:
            opened = self._open.pop(request_id, None) or {}
        event = {"kind": "close", "request_id": request_id,
                 "op": opened.get("op"),
                 "status": status,
                 "t_end_monotonic": round(time.monotonic(), 3),
                 "t_end_wall": time.time(), **fields}
        self._append(event)

    def error(self, request_id: str, error_type: str,
              right_censored: bool = False, **fields: Any) -> None:
        """Close an open request with a failure; right_censored=True marks an
        UNKNOWN outcome (e.g. transport timeout on a paid generation)."""
        with self._lock:
            opened = self._open.pop(request_id, None) or {}
        event = {"kind": "error", "request_id": request_id,
                 "op": opened.get("op"),
                 "error_type": error_type,
                 "right_censored": right_censored,
                 "t_end_monotonic": round(time.monotonic(), 3),
                 "t_end_wall": time.time(), **fields}
        self._append(event)

    def diagnostic(self, request_id: str | None, **fields: Any) -> None:
        """Persist bounded non-secret parse diagnostics linked to a logical request when available."""
        self._append({"kind": "diagnostic", "request_id": request_id,
                      "request_id_available": request_id is not None,
                      "t_wall": time.time(), **fields})

    def observe_usage(self, output_tokens: int | None = None, **fields: Any) -> None:
        """Record observed (already returned) usage. The configured
        VIMAX_BAILIAN_BUDGET_OBSERVED_OUTPUT_TOKENS_TOTAL is a SOFT stop
        threshold: crossing it emits a threshold_reached event once (never a
        hard guarantee that total tokens stayed below it — in-flight
        responses may overshoot)."""
        if output_tokens:
            with self._lock:
                self._observed_output_tokens += output_tokens
                total = self._observed_output_tokens
                soft = _env_int(
                    "VIMAX_BAILIAN_BUDGET_OBSERVED_OUTPUT_TOKENS_TOTAL")
                crossed = (soft is not None and total >= soft
                           and total - output_tokens < soft)
            if crossed:
                self._append({"kind": "threshold_reached",
                              "threshold": soft,
                              "observed_output_tokens_total": total,
                              "note": "soft stop threshold; in-flight "
                                      "responses may overshoot"})
        self._append({"kind": "usage",
                      "observed_output_tokens_total": self._observed_output_tokens,
                      **fields})

    # ------------------------------------------------------------------ #
    # state
    # ------------------------------------------------------------------ #
    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def caps(self) -> dict[str, int | None]:
        return dict(self._caps)

    def observed_output_tokens(self) -> int:
        with self._lock:
            return self._observed_output_tokens

    def failure_state(self) -> dict:
        with self._lock:
            unclosed = {k: v.get("op") for k, v in self._open.items()}
            return {"ledger_write_failures": self._write_failures,
                    "ledger_write_failure_last": self._write_failure_last,
                    "unclosed_requests": unclosed,
                    "counts": dict(self._counts),
                    "caps": dict(self._caps),
                    "observed_output_tokens_total":
                        self._observed_output_tokens}

    def flush_state(self) -> None:
        """Persist the ledger's own state so write failures and unclosed
        requests are never invisible."""
        if self.path is None:
            return
        state_path = self.path.with_suffix(self.path.suffix + ".state")
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps(self.failure_state(), indent=1,
                           ensure_ascii=False) + "\n")
        except OSError:
            pass


_LEDGER: RequestLedger | None = None
_LEDGER_LOCK = threading.Lock()


def get_ledger() -> RequestLedger:
    global _LEDGER
    with _LEDGER_LOCK:
        if _LEDGER is None:
            _LEDGER = RequestLedger(
                os.environ.get("VIMAX_BAILIAN_EVENT_LOG")
                or os.environ.get("VIMAX_REQUEST_LEDGER"))
        return _LEDGER
