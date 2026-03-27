"""Tests for the PortfolioTracker."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gordon.core.enums import AssetClass, Side
from gordon.core.models import Asset, Fill
from gordon.portfolio.tracker import PortfolioTracker

ASSET = Asset(symbol="AAPL", asset_class=AssetClass.EQUITY, exchange="NASDAQ")
NOW = datetime(2025, 6, 1)


def _fill(
    side: Side,
    price: float,
    qty: float,
    commission: float = 0.0,
) -> Fill:
    return Fill(
        order_id="test",
        asset=ASSET,
        side=side,
        price=Decimal(str(price)),
        quantity=Decimal(str(qty)),
        commission=Decimal(str(commission)),
        timestamp=NOW,
    )


class TestPortfolioTrackerInitialState:
    def test_initial_cash(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        assert tracker.cash == Decimal("100000")

    def test_no_positions(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        assert tracker.positions == {}

    def test_initial_equity_equals_cash(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        assert tracker.total_equity == Decimal("100000")

    def test_zero_pnl(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        assert tracker.realized_pnl == Decimal("0")
        assert tracker.unrealized_pnl == Decimal("0")


class TestPortfolioTrackerFills:
    def test_buy_fill_reduces_cash(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        tracker.on_fill(_fill(Side.BUY, 100.0, 10.0))
        # cash = 100000 - (100 * 10) - 0 commission = 99000
        assert tracker.cash == Decimal("99000")

    def test_buy_fill_creates_position(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        tracker.on_fill(_fill(Side.BUY, 100.0, 10.0))
        positions = tracker.positions
        assert "AAPL" in positions
        assert positions["AAPL"].quantity == Decimal("10")
        assert positions["AAPL"].avg_entry_price == Decimal("100")

    def test_sell_fill_increases_cash(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        tracker.on_fill(_fill(Side.BUY, 100.0, 10.0))
        tracker.on_fill(_fill(Side.SELL, 110.0, 10.0))
        # cash = 99000 + (110 * 10) - 0 = 100100
        assert tracker.cash == Decimal("100100")

    def test_sell_closes_position(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        tracker.on_fill(_fill(Side.BUY, 100.0, 10.0))
        tracker.on_fill(_fill(Side.SELL, 110.0, 10.0))
        # Position should be fully closed (qty=0), so filtered out
        assert tracker.positions == {}

    def test_realized_pnl_on_close(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        tracker.on_fill(_fill(Side.BUY, 100.0, 10.0))
        tracker.on_fill(_fill(Side.SELL, 110.0, 10.0))
        # PnL = (110 - 100) * 10 = 100
        assert tracker.realized_pnl == Decimal("100")

    def test_commission_deducted(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        tracker.on_fill(_fill(Side.BUY, 100.0, 10.0, commission=5.0))
        # cash = 100000 - 1000 - 5 = 98995
        assert tracker.cash == Decimal("98995")

    def test_unrealized_pnl(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        tracker.on_fill(_fill(Side.BUY, 100.0, 10.0))
        tracker.update_market_price(ASSET, Decimal("110"))
        # Unrealized = (110 - 100) * 10 = 100
        assert tracker.unrealized_pnl == Decimal("100")


class TestPortfolioTrackerSnapshot:
    def test_snapshot_structure(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        snap = tracker.snapshot(NOW)
        assert snap.timestamp == NOW
        assert snap.cash == Decimal("100000")
        assert snap.total_equity == Decimal("100000")
        assert snap.positions == ()

    def test_snapshot_includes_positions(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        tracker.on_fill(_fill(Side.BUY, 100.0, 10.0))
        snap = tracker.snapshot(NOW)
        assert len(snap.positions) == 1

    def test_total_equity_includes_market_value(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        tracker.on_fill(_fill(Side.BUY, 100.0, 10.0))
        tracker.update_market_price(ASSET, Decimal("110"))
        # equity = cash (99000) + market_value (110 * 10 = 1100) = 100100
        assert tracker.total_equity == Decimal("100100")


class TestPortfolioTrackerTradeRecords:
    def test_trade_record_on_close(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        tracker.on_fill(_fill(Side.BUY, 100.0, 10.0))
        tracker.on_fill(_fill(Side.SELL, 110.0, 10.0))
        records = tracker.trade_records
        assert len(records) == 1
        assert records[0].pnl == Decimal("100")
        assert records[0].entry_price == Decimal("100")
        assert records[0].exit_price == Decimal("110")

    def test_no_trade_record_while_open(self):
        tracker = PortfolioTracker(initial_cash=Decimal("100000"))
        tracker.on_fill(_fill(Side.BUY, 100.0, 10.0))
        assert tracker.trade_records == []
