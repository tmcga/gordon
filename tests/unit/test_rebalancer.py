"""Tests for the portfolio rebalancer."""

from __future__ import annotations

from decimal import Decimal

from gordon.core.enums import AssetClass, Side
from gordon.core.models import Asset, Position
from gordon.portfolio.rebalancer import Rebalancer


def _asset(symbol: str) -> Asset:
    return Asset(symbol=symbol, asset_class=AssetClass.EQUITY)


def _position(symbol: str, quantity: Decimal, avg_price: Decimal) -> Position:
    return Position(
        asset=_asset(symbol),
        quantity=quantity,
        avg_entry_price=avg_price,
    )


class TestRebalancer:
    def test_from_cash_to_target(self):
        """Starting from all cash, generate buy orders for target weights."""
        reb = Rebalancer()
        orders = reb.rebalance(
            current_positions={},
            target_weights={"AAPL": 0.5, "MSFT": 0.5},
            total_equity=Decimal("100000"),
            prices={"AAPL": Decimal("150"), "MSFT": Decimal("300")},
        )
        assert len(orders) == 2
        for o in orders:
            assert o.side == Side.BUY

        # Check order values
        by_symbol = {o.asset.symbol: o for o in orders}
        # AAPL: target = 50000, qty = 50000/150 = 333.33...
        assert by_symbol["AAPL"].quantity == Decimal("50000") / Decimal("150")
        # MSFT: target = 50000, qty = 50000/300 = 166.66...
        assert by_symbol["MSFT"].quantity == Decimal("50000") / Decimal("300")

    def test_reduces_overweight_positions(self):
        """Sell overweight positions."""
        reb = Rebalancer()
        # Position has 200 shares at $100 = $20000, but target is 10% of $100000 = $10000
        pos = _position("AAPL", Decimal("200"), Decimal("100"))
        orders = reb.rebalance(
            current_positions={"AAPL": pos},
            target_weights={"AAPL": 0.10},
            total_equity=Decimal("100000"),
            prices={"AAPL": Decimal("100")},
        )
        assert len(orders) == 1
        assert orders[0].side == Side.SELL
        # Should sell $10000 worth -> 100 shares
        assert orders[0].quantity == Decimal("10000") / Decimal("100")

    def test_skips_small_trades(self):
        """Trades below min_trade_value are skipped."""
        reb = Rebalancer()
        # Position is nearly at target
        pos = _position("AAPL", Decimal("100"), Decimal("100"))
        orders = reb.rebalance(
            current_positions={"AAPL": pos},
            target_weights={"AAPL": 0.1001},
            total_equity=Decimal("100000"),
            prices={"AAPL": Decimal("100")},
            min_trade_value=Decimal("50"),
        )
        # diff = 10010 - 10000 = 10 < 50 min_trade_value
        assert len(orders) == 0

    def test_empty_target_weights_sells_all(self):
        """Empty target weights with positions generates sell orders."""
        reb = Rebalancer()
        pos = _position("AAPL", Decimal("100"), Decimal("100"))
        orders = reb.rebalance(
            current_positions={"AAPL": pos},
            target_weights={},
            total_equity=Decimal("100000"),
            prices={"AAPL": Decimal("100")},
        )
        assert len(orders) == 1
        assert orders[0].side == Side.SELL

    def test_empty_target_and_no_positions(self):
        """No positions and no targets -> no orders."""
        reb = Rebalancer()
        orders = reb.rebalance(
            current_positions={},
            target_weights={},
            total_equity=Decimal("100000"),
            prices={},
        )
        assert len(orders) == 0

    def test_missing_price_skips_asset(self):
        """Assets without prices are skipped."""
        reb = Rebalancer()
        orders = reb.rebalance(
            current_positions={},
            target_weights={"AAPL": 0.5},
            total_equity=Decimal("100000"),
            prices={},  # no price for AAPL
        )
        assert len(orders) == 0

    def test_order_has_correct_asset_class(self):
        """Rebalance orders should have correct asset metadata."""
        reb = Rebalancer()
        orders = reb.rebalance(
            current_positions={},
            target_weights={"AAPL": 1.0},
            total_equity=Decimal("10000"),
            prices={"AAPL": Decimal("100")},
            asset_class=AssetClass.EQUITY,
        )
        assert len(orders) == 1
        assert orders[0].asset.asset_class == AssetClass.EQUITY
