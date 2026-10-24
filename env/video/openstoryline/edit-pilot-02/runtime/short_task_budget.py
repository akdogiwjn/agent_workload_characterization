"""Fresh monotonic wall-budget windows for OpenStoryline preparation runs."""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable


@dataclass(frozen=True)
class DeadlineWindow:
    started_monotonic: float
    deadline_monotonic: float

    def remaining(self, now: float | None = None) -> float:
        return max(0.0, self.deadline_monotonic - (time.monotonic() if now is None else now))

    def execution_deadline(self, cleanup_reserve_s: float) -> float:
        if cleanup_reserve_s < 0:
            raise ValueError("cleanup reserve cannot be negative")
        deadline = self.deadline_monotonic - cleanup_reserve_s
        if deadline <= self.started_monotonic:
            raise ValueError("cleanup reserve consumes the complete wall budget")
        return deadline


def begin_deadline(duration_s: float,
                   monotonic: Callable[[], float] = time.monotonic) -> DeadlineWindow:
    """Start a new budget now; no prior run identity or timestamp is accepted."""
    if duration_s <= 0:
        raise ValueError("wall budget must be positive")
    started = monotonic()
    return DeadlineWindow(started, started + duration_s)
