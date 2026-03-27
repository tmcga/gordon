"""Tests for DrawdownTracker and DailyLossTracker."""

from __future__ import annotations

from decimal import Decimal

import pytest

from gordon.risk.limits import DailyLossTracker, DrawdownTracker

# ---------------------------------------------------------------------------
# DrawdownTracker
# ---------------------------------------------------------------------------


class TestDrawdownTracker:
    def test_initial_state(self):
        tracker = DrawdownTracker()
        assert tracker.peak == Decimal("0")
        assert tracker.drawdown == 0.0

    def test_tracks_peak(self):
        tracker = DrawdownTracker()
        tracker.update(Decimal("100"))
        assert tracker.peak == Decimal("100")
        tracker.update(Decimal("120"))
        assert tracker.peak == Decimal("120")

    def test_peak_does_not_decrease(self):
        tracker = DrawdownTracker()
        tracker.update(Decimal("120"))
        tracker.update(Decimal("100"))
        assert tracker.peak == Decimal("120")

    def test_drawdown_calculation(self):
        tracker = DrawdownTracker()
        tracker.update(Decimal("100"))
        tracker.update(Decimal("90"))
        assert tracker.drawdown == pytest.approx(0.10)

    def test_drawdown_returns_to_zero_at_new_peak(self):
        tracker = DrawdownTracker()
        tracker.update(Decimal("100"))
        tracker.update(Decimal("90"))
        assert tracker.drawdown > 0
        tracker.update(Decimal("110"))
        assert tracker.drawdown == 0.0

    def test_drawdown_never_negative(self):
        tracker = DrawdownTracker()
        tracker.update(Decimal("100"))
        tracker.update(Decimal("150"))
        assert tracker.drawdown == 0.0


# ---------------------------------------------------------------------------
# DailyLossTracker
# ---------------------------------------------------------------------------


class TestDailyLossTracker:
    def test_initial_zero_loss(self):
        tracker = DailyLossTracker()
        assert tracker.daily_loss == Decimal("0")

    def test_record_single_loss(self):
        tracker = DailyLossTracker()
        tracker.record_loss(Decimal("500"))
        assert tracker.daily_loss == Decimal("500")

    def test_record_multiple_losses(self):
        tracker = DailyLossTracker()
        tracker.record_loss(Decimal("200"))
        tracker.record_loss(Decimal("300"))
        assert tracker.daily_loss == Decimal("500")

    def test_negative_amount_treated_as_positive(self):
        tracker = DailyLossTracker()
        tracker.record_loss(Decimal("-100"))
        assert tracker.daily_loss == Decimal("100")

    def test_reset_day(self):
        tracker = DailyLossTracker()
        tracker.record_loss(Decimal("1000"))
        assert tracker.daily_loss == Decimal("1000")
        tracker.reset_day()
        assert tracker.daily_loss == Decimal("0")

    def test_accumulate_after_reset(self):
        tracker = DailyLossTracker()
        tracker.record_loss(Decimal("1000"))
        tracker.reset_day()
        tracker.record_loss(Decimal("200"))
        assert tracker.daily_loss == Decimal("200")
