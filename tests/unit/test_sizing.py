"""Tests for position sizing algorithms."""

from __future__ import annotations

from decimal import Decimal

import pytest

from gordon.risk.sizing import (
    FixedFractionalSizer,
    KellyCriterionSizer,
    VolatilityTargetSizer,
)

# ---------------------------------------------------------------------------
# FixedFractionalSizer
# ---------------------------------------------------------------------------


class TestFixedFractionalSizer:
    def test_basic_calculation(self):
        sizer = FixedFractionalSizer(fraction=0.02)
        # notional = 0.02 * 100000 = 2000, qty = 2000 / 50 = 40
        qty = sizer.calculate(equity=Decimal("100000"), price=Decimal("50"))
        assert qty == Decimal("40.00000000")

    def test_fraction_of_equity(self):
        sizer = FixedFractionalSizer(fraction=0.05)
        # notional = 0.05 * 10000 = 500, qty = 500 / 100 = 5
        qty = sizer.calculate(equity=Decimal("10000"), price=Decimal("100"))
        assert qty == Decimal("5.00000000")

    def test_zero_price_returns_zero(self):
        sizer = FixedFractionalSizer(fraction=0.02)
        qty = sizer.calculate(equity=Decimal("100000"), price=Decimal("0"))
        assert qty == Decimal("0")

    def test_zero_equity_returns_zero(self):
        sizer = FixedFractionalSizer(fraction=0.02)
        qty = sizer.calculate(equity=Decimal("0"), price=Decimal("50"))
        assert qty == Decimal("0.00000000")

    def test_rounds_down(self):
        sizer = FixedFractionalSizer(fraction=0.02)
        # notional = 0.02 * 100000 = 2000, qty = 2000 / 3 = 666.666...
        qty = sizer.calculate(equity=Decimal("100000"), price=Decimal("3"))
        assert qty == Decimal("666.66666666")


# ---------------------------------------------------------------------------
# KellyCriterionSizer
# ---------------------------------------------------------------------------


class TestKellyCriterionSizer:
    def test_known_kelly_values(self):
        # win_rate=0.6, payoff=2.0 -> kelly = 0.6 - 0.4/2.0 = 0.4
        # half kelly = 0.2
        sizer = KellyCriterionSizer(win_rate=0.6, payoff_ratio=2.0, half_kelly=True)
        # notional = 0.2 * 100000 = 20000, qty ~ 200
        qty = sizer.calculate(equity=Decimal("100000"), price=Decimal("100"))
        assert float(qty) == pytest.approx(200.0, abs=0.01)

    def test_full_kelly(self):
        # kelly = 0.6 - 0.4/2.0 = 0.4
        sizer = KellyCriterionSizer(win_rate=0.6, payoff_ratio=2.0, half_kelly=False)
        # notional = 0.4 * 100000 = 40000, qty ~ 400
        qty = sizer.calculate(equity=Decimal("100000"), price=Decimal("100"))
        assert float(qty) == pytest.approx(400.0, abs=0.01)

    def test_half_kelly_is_half_of_full(self):
        full = KellyCriterionSizer(win_rate=0.6, payoff_ratio=2.0, half_kelly=False)
        half = KellyCriterionSizer(win_rate=0.6, payoff_ratio=2.0, half_kelly=True)
        equity = Decimal("100000")
        price = Decimal("100")
        qty_full = full.calculate(equity, price)
        qty_half = half.calculate(equity, price)
        assert float(qty_full) == pytest.approx(float(qty_half) * 2, abs=0.01)

    def test_negative_edge_returns_zero(self):
        # win_rate=0.3, payoff=1.0 -> kelly = 0.3 - 0.7/1.0 = -0.4
        sizer = KellyCriterionSizer(win_rate=0.3, payoff_ratio=1.0)
        qty = sizer.calculate(equity=Decimal("100000"), price=Decimal("100"))
        assert qty == Decimal("0")

    def test_zero_payoff_returns_zero(self):
        sizer = KellyCriterionSizer(win_rate=0.6, payoff_ratio=0.0)
        qty = sizer.calculate(equity=Decimal("100000"), price=Decimal("100"))
        assert qty == Decimal("0")

    def test_zero_price_returns_zero(self):
        sizer = KellyCriterionSizer(win_rate=0.6, payoff_ratio=2.0)
        qty = sizer.calculate(equity=Decimal("100000"), price=Decimal("0"))
        assert qty == Decimal("0")


# ---------------------------------------------------------------------------
# VolatilityTargetSizer
# ---------------------------------------------------------------------------


class TestVolatilityTargetSizer:
    def test_basic_calculation(self):
        sizer = VolatilityTargetSizer(target_risk=0.02, atr=Decimal("5"))
        # risk_amount = 0.02 * 100000 = 2000
        # divisor = 5 * 100 = 500
        # qty = 2000 / 500 = 4
        qty = sizer.calculate(equity=Decimal("100000"), price=Decimal("100"))
        assert qty == Decimal("4.00000000")

    def test_higher_atr_smaller_position(self):
        low_vol = VolatilityTargetSizer(target_risk=0.02, atr=Decimal("2"))
        high_vol = VolatilityTargetSizer(target_risk=0.02, atr=Decimal("10"))
        equity = Decimal("100000")
        price = Decimal("100")
        assert low_vol.calculate(equity, price) > high_vol.calculate(equity, price)

    def test_zero_atr_returns_zero(self):
        sizer = VolatilityTargetSizer(target_risk=0.02, atr=Decimal("0"))
        qty = sizer.calculate(equity=Decimal("100000"), price=Decimal("100"))
        assert qty == Decimal("0")

    def test_zero_price_returns_zero(self):
        sizer = VolatilityTargetSizer(target_risk=0.02, atr=Decimal("5"))
        qty = sizer.calculate(equity=Decimal("100000"), price=Decimal("0"))
        assert qty == Decimal("0")

    def test_zero_equity_returns_zero(self):
        sizer = VolatilityTargetSizer(target_risk=0.02, atr=Decimal("5"))
        qty = sizer.calculate(equity=Decimal("0"), price=Decimal("100"))
        assert qty == Decimal("0.00000000")
