"""Tests for individual risk guard implementations."""

from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from gordon.core.enums import AssetClass, OrderType, Side
from gordon.core.models import Asset, Order, PortfolioSnapshot, Position
from gordon.risk.guards import (
    CooldownGuard,
    DailyLossLimitGuard,
    MaxConcentrationGuard,
    MaxDrawdownGuard,
    MaxPositionSizeGuard,
    SymbolWhitelistGuard,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _asset(symbol: str = "AAPL") -> Asset:
    return Asset(symbol=symbol, asset_class=AssetClass.EQUITY)


def _order(
    symbol: str = "AAPL",
    quantity: Decimal = Decimal("10"),
    limit_price: Decimal | None = Decimal("150"),
    side: Side = Side.BUY,
) -> Order:
    return Order(
        asset=_asset(symbol),
        side=side,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        limit_price=limit_price,
        strategy_id="test",
    )


def _portfolio(
    total_equity: Decimal = Decimal("100000"),
    positions: tuple[Position, ...] = (),
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime(2025, 1, 15),
        cash=total_equity,
        positions=positions,
        total_equity=total_equity,
    )


def _position(
    symbol: str = "AAPL",
    quantity: Decimal = Decimal("100"),
    avg_price: Decimal = Decimal("150"),
) -> Position:
    return Position(
        asset=_asset(symbol),
        quantity=quantity,
        avg_entry_price=avg_price,
    )


# ---------------------------------------------------------------------------
# MaxPositionSizeGuard
# ---------------------------------------------------------------------------


class TestMaxPositionSizeGuard:
    def test_approve_under_limit(self):
        guard = MaxPositionSizeGuard(max_pct=0.10)
        # order value = 10 * 150 = 1500, equity = 100000 -> 1.5%
        order = _order(quantity=Decimal("10"), limit_price=Decimal("150"))
        verdict = guard.check(order, _portfolio())
        assert verdict.approved is True

    def test_reject_over_limit(self):
        guard = MaxPositionSizeGuard(max_pct=0.10)
        # order value = 100 * 150 = 15000 -> 15% > 10%
        order = _order(quantity=Decimal("100"), limit_price=Decimal("150"))
        verdict = guard.check(order, _portfolio())
        assert verdict.approved is False
        assert "max_position_size" in verdict.reason

    def test_approve_market_order_no_limit_price(self):
        guard = MaxPositionSizeGuard(max_pct=0.10)
        order = _order(limit_price=None)
        verdict = guard.check(order, _portfolio())
        assert verdict.approved is True

    def test_reject_zero_equity(self):
        guard = MaxPositionSizeGuard(max_pct=0.10)
        order = _order()
        verdict = guard.check(order, _portfolio(total_equity=Decimal("0")))
        assert verdict.approved is False


# ---------------------------------------------------------------------------
# MaxConcentrationGuard
# ---------------------------------------------------------------------------


class TestMaxConcentrationGuard:
    def test_approve_below_concentration(self):
        guard = MaxConcentrationGuard(max_pct=0.25)
        # existing = 0, order value = 10 * 150 = 1500 -> 1.5%
        order = _order()
        verdict = guard.check(order, _portfolio())
        assert verdict.approved is True

    def test_reject_exceeds_concentration(self):
        guard = MaxConcentrationGuard(max_pct=0.25)
        # existing position: 100 * 200 = 20000
        # order value: 100 * 150 = 15000
        # projected: 35000 / 100000 = 35% > 25%
        pos = _position(quantity=Decimal("100"), avg_price=Decimal("200"))
        order = _order(quantity=Decimal("100"), limit_price=Decimal("150"))
        portfolio = _portfolio(positions=(pos,))
        verdict = guard.check(order, portfolio)
        assert verdict.approved is False
        assert "max_concentration" in verdict.reason

    def test_approve_with_existing_position_under_limit(self):
        guard = MaxConcentrationGuard(max_pct=0.25)
        pos = _position(quantity=Decimal("10"), avg_price=Decimal("150"))
        # existing = 1500, order = 10 * 150 = 1500, projected = 3000 -> 3%
        order = _order(quantity=Decimal("10"), limit_price=Decimal("150"))
        portfolio = _portfolio(positions=(pos,))
        verdict = guard.check(order, portfolio)
        assert verdict.approved is True

    def test_reject_zero_equity(self):
        guard = MaxConcentrationGuard(max_pct=0.25)
        order = _order()
        verdict = guard.check(order, _portfolio(total_equity=Decimal("0")))
        assert verdict.approved is False


# ---------------------------------------------------------------------------
# CooldownGuard
# ---------------------------------------------------------------------------


class TestCooldownGuard:
    def test_approve_no_recent_trade(self):
        guard = CooldownGuard(seconds=300)
        order = _order()
        verdict = guard.check(order, _portfolio())
        assert verdict.approved is True

    def test_reject_during_cooldown(self):
        guard = CooldownGuard(seconds=300)
        guard.record_trade("AAPL")
        order = _order()
        verdict = guard.check(order, _portfolio())
        assert verdict.approved is False
        assert "cooldown" in verdict.reason

    def test_approve_after_cooldown_expires(self):
        guard = CooldownGuard(seconds=1)
        guard.record_trade("AAPL")
        # Patch time.monotonic to simulate elapsed time
        original_time = time.monotonic()
        with patch("time.monotonic", return_value=original_time + 2):
            guard._last_trade["AAPL"] = original_time - 2
            verdict = guard.check(_order(), _portfolio())
        assert verdict.approved is True

    def test_different_symbols_independent(self):
        guard = CooldownGuard(seconds=300)
        guard.record_trade("MSFT")
        # AAPL should still be approved
        order = _order(symbol="AAPL")
        verdict = guard.check(order, _portfolio())
        assert verdict.approved is True


# ---------------------------------------------------------------------------
# DailyLossLimitGuard
# ---------------------------------------------------------------------------


class TestDailyLossLimitGuard:
    def test_approve_no_losses(self):
        guard = DailyLossLimitGuard(max_loss_pct=0.02)
        verdict = guard.check(_order(), _portfolio())
        assert verdict.approved is True

    def test_reject_when_loss_exceeds_threshold(self):
        guard = DailyLossLimitGuard(max_loss_pct=0.02)
        # Record losses totaling 2500 -> 2.5% of 100000
        guard.tracker.record_loss(Decimal("2500"))
        verdict = guard.check(_order(), _portfolio())
        assert verdict.approved is False
        assert "daily_loss_limit" in verdict.reason

    def test_approve_after_day_reset(self):
        guard = DailyLossLimitGuard(max_loss_pct=0.02)
        guard.tracker.record_loss(Decimal("5000"))
        guard.tracker.reset_day()
        verdict = guard.check(_order(), _portfolio())
        assert verdict.approved is True


# ---------------------------------------------------------------------------
# MaxDrawdownGuard
# ---------------------------------------------------------------------------


class TestMaxDrawdownGuard:
    def test_approve_no_drawdown(self):
        guard = MaxDrawdownGuard(max_drawdown=0.10)
        portfolio = _portfolio(total_equity=Decimal("100000"))
        verdict = guard.check(_order(), portfolio)
        assert verdict.approved is True

    def test_reject_when_drawdown_exceeded(self):
        guard = MaxDrawdownGuard(max_drawdown=0.10)
        # Set peak high, then check with lower equity
        guard.tracker.update(Decimal("100000"))
        portfolio = _portfolio(total_equity=Decimal("85000"))
        verdict = guard.check(_order(), portfolio)
        assert verdict.approved is False
        assert "max_drawdown" in verdict.reason

    def test_approve_when_drawdown_within_limit(self):
        guard = MaxDrawdownGuard(max_drawdown=0.10)
        guard.tracker.update(Decimal("100000"))
        portfolio = _portfolio(total_equity=Decimal("95000"))
        verdict = guard.check(_order(), portfolio)
        assert verdict.approved is True


# ---------------------------------------------------------------------------
# SymbolWhitelistGuard
# ---------------------------------------------------------------------------


class TestSymbolWhitelistGuard:
    def test_approve_whitelisted_symbol(self):
        guard = SymbolWhitelistGuard(symbols={"AAPL", "MSFT", "GOOG"})
        verdict = guard.check(_order(symbol="AAPL"), _portfolio())
        assert verdict.approved is True

    def test_reject_non_whitelisted_symbol(self):
        guard = SymbolWhitelistGuard(symbols={"AAPL", "MSFT"})
        verdict = guard.check(_order(symbol="TSLA"), _portfolio())
        assert verdict.approved is False
        assert "symbol_whitelist" in verdict.reason
        assert "TSLA" in verdict.reason
