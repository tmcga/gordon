"""Clock abstractions for simulated and live time."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime


class Clock(ABC):
    """Abstract clock for time management."""

    @abstractmethod
    def now(self) -> datetime: ...


class SimulatedClock(Clock):
    """Clock driven by backtest bar timestamps."""

    def __init__(self) -> None:
        self._current: datetime = datetime(1970, 1, 1, tzinfo=UTC)

    def advance(self, timestamp: datetime) -> None:
        """Advance the clock to the given timestamp."""
        self._current = timestamp

    def now(self) -> datetime:
        return self._current


class WallClock(Clock):
    """Real wall clock for live/paper trading."""

    def now(self) -> datetime:
        return datetime.now(tz=UTC)
