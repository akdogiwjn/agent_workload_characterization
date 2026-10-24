"""Identify non-recoverable control-flow exceptions without matching text."""
from __future__ import annotations

import asyncio
from concurrent.futures import CancelledError as FutureCancelledError
from typing import Any

from agent_runtime.request_ledger import BudgetExceeded, DeadlineExceeded, LedgerWriteError


CONTROL_EXCEPTION_TYPES = (
    BudgetExceeded,
    DeadlineExceeded,
    LedgerWriteError,
    asyncio.CancelledError,
    FutureCancelledError,
)

def _planning_control_types() -> tuple[type[BaseException], ...]:
    # Keep the parser independent of the runtime exception module while
    # making a provider-confirmed truncation terminal across Tenacity/tool
    # routing and the native AgentLoop.
    try:
        from utils.robust_json_parser import StructuredOutputTruncated
        return (StructuredOutputTruncated,)
    except ImportError:
        return ()


def find_control_exception(error: BaseException) -> BaseException | None:
    """Walk causes, contexts, groups and Tenacity RetryError safely."""
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, CONTROL_EXCEPTION_TYPES + _planning_control_types()):
            return current
        for candidate in (getattr(current, "__cause__", None), getattr(current, "__context__", None)):
            if isinstance(candidate, BaseException):
                pending.append(candidate)
        nested = getattr(current, "exceptions", None)
        if isinstance(nested, (list, tuple)):
            pending.extend(item for item in nested if isinstance(item, BaseException))
        last_attempt = getattr(current, "last_attempt", None)
        exception_method = getattr(last_attempt, "exception", None)
        if callable(exception_method):
            try:
                last_error = exception_method()
            except BaseException:
                last_error = None
            if isinstance(last_error, BaseException):
                pending.append(last_error)
    return None


def is_retryable_agent_error(error: BaseException) -> bool:
    return find_control_exception(error) is None
