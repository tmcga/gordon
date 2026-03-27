"""Real-time limit tracking for drawdown and daily loss."""

from __future__ import annotations

from decimal import Decimal

import structlog

log = structlog.get_logger(__name__)


class DrawdownTracker:
    """Track portfolio drawdown from peak equity."""

    def __init__(self) -> None:
        self._peak: Decimal = Decimal("0")
        self._current: Decimal = Decimal("0")

    def update(self, equity: Decimal) -> None:
        """Update with the latest equity value."""
        self._current = equity
        if equity > self._peak:
            self._peak = equity
            log.debug("drawdown_tracker.new_peak", peak=str(self._peak))

    @property
    def peak(self) -> Decimal:
        """Return the peak equity observed."""
        return self._peak

    @property
    def drawdown(self) -> float:
        """Current drawdown as a fraction (0.0 to 1.0)."""
        if self._peak == 0:
            return 0.0
        dd = (self._peak - self._current) / self._peak
        return float(max(dd, Decimal("0")))


class DailyLossTracker:
    """Track daily realized loss."""

    def __init__(self) -> None:
        self._daily_loss: Decimal = Decimal("0")

    def record_loss(self, amount: Decimal) -> None:
        """Record a realized loss (pass as positive amount)."""
        self._daily_loss += abs(amount)
        log.debug(
            "daily_loss_tracker.loss_recorded",
            amount=str(amount),
            cumulative=str(self._daily_loss),
        )

    def reset_day(self) -> None:
        """Reset the daily loss counter (call at start of each trading day)."""
        log.info(
            "daily_loss_tracker.day_reset",
            previous_loss=str(self._daily_loss),
        )
        self._daily_loss = Decimal("0")

    @property
    def daily_loss(self) -> Decimal:
        """Cumulative realized loss for the current day."""
        return self._daily_loss
