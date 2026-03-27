"""Tests for engine helper functions (signal_to_order, close_positions)."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from gordon.core.enums import AssetClass, OrderType, Side
from gordon.core.models import (
    Asset,
    Fill,
    PortfolioSnapshot,
    Position,
    Signal,
)
from gordon.engine._helpers import close_positions, signal_to_order


@pytest.fixture()
def asset() -> Asset:
    return Asset(symbol="AAPL", asset_class=AssetClass.EQUITY, exchange="NASDAQ")


@pytest.fixture()
def portfolio_with_cash(asset: Asset) -> PortfolioSnapshot:
    """Portfolio with $100k cash, no positions."""
    return PortfolioSnapshot(
        timestamp=datetime(2025, 6, 1),
        cash=Decimal("100000"),
        positions=(),
        total_equity=Decimal("100000"),
    )


@pytest.fixture()
def portfolio_with_position(asset: Asset) -> PortfolioSnapshot:
    """Portfolio with a 100-share long position."""
    pos = Position(
        asset=asset,
        quantity=Decimal("100"),
        avg_entry_price=Decimal("150"),
    )
    return PortfolioSnapshot(
        timestamp=datetime(2025, 6, 1),
        cash=Decimal("85000"),
        positions=(pos,),
        total_equity=Decimal("100000"),
    )


class TestSignalToOrderBuy:
    def test_buy_creates_market_order(
        self, asset: Asset, portfolio_with_cash: PortfolioSnapshot
    ) -> None:
        sig = Signal(
            asset=asset,
            side=Side.BUY,
            strength=0.5,
            strategy_id="test",
        )
        order = signal_to_order(sig, portfolio_with_cash, Decimal("150"))
        assert order is not None
        assert order.side == Side.BUY
        assert order.order_type == OrderType.MARKET
        # 0.5 * 100000 / 150 = 333.3333 -> quantized
        expected = (Decimal("50000") / Decimal("150")).quantize(Decimal("0.0001"))
        assert order.quantity == expected

    def test_buy_strength_scales_quantity(
        self, asset: Asset, portfolio_with_cash: PortfolioSnapshot
    ) -> None:
        sig_half = Signal(asset=asset, side=Side.BUY, strength=0.5, strategy_id="t")
        sig_full = Signal(asset=asset, side=Side.BUY, strength=1.0, strategy_id="t")
        o_half = signal_to_order(sig_half, portfolio_with_cash, Decimal("100"))
        o_full = signal_to_order(sig_full, portfolio_with_cash, Decimal("100"))
        assert o_half is not None and o_full is not None
        assert o_full.quantity > o_half.quantity


class TestSignalToOrderSell:
    def test_sell_uses_held_quantity(
        self, asset: Asset, portfolio_with_position: PortfolioSnapshot
    ) -> None:
        sig = Signal(
            asset=asset,
            side=Side.SELL,
            strength=0.5,
            strategy_id="test",
        )
        order = signal_to_order(sig, portfolio_with_position, Decimal("150"))
        assert order is not None
        assert order.side == Side.SELL
        # 0.5 * 100 = 50
        expected = Decimal("50").quantize(Decimal("0.0001"))
        assert order.quantity == expected


class TestSignalToOrderReturnsNone:
    def test_zero_strength(self, asset: Asset, portfolio_with_cash: PortfolioSnapshot) -> None:
        sig = Signal(asset=asset, side=Side.BUY, strength=0.0, strategy_id="t")
        assert signal_to_order(sig, portfolio_with_cash, Decimal("150")) is None

    def test_zero_price(self, asset: Asset, portfolio_with_cash: PortfolioSnapshot) -> None:
        sig = Signal(asset=asset, side=Side.BUY, strength=0.5, strategy_id="t")
        assert signal_to_order(sig, portfolio_with_cash, Decimal("0")) is None


class TestClosePositions:
    @pytest.mark.asyncio()
    async def test_closes_long_position(self, asset: Asset) -> None:
        pos = MagicMock()
        pos.asset = asset
        pos.quantity = Decimal("100")

        fill = Fill(
            order_id="close-1",
            asset=asset,
            side=Side.SELL,
            price=Decimal("150"),
            quantity=Decimal("100"),
            timestamp=datetime(2025, 6, 1),
        )

        broker = MagicMock()
        broker.submit_order = AsyncMock(return_value=fill)

        tracker = MagicMock()
        tracker.positions = {"AAPL": pos}

        fills = await close_positions(broker, tracker)
        assert len(fills) == 1
        assert fills[0].side == Side.SELL
        tracker.on_fill.assert_called_once_with(fill)

    @pytest.mark.asyncio()
    async def test_closes_short_position(self, asset: Asset) -> None:
        pos = MagicMock()
        pos.asset = asset
        pos.quantity = Decimal("-50")

        fill = Fill(
            order_id="close-2",
            asset=asset,
            side=Side.BUY,
            price=Decimal("150"),
            quantity=Decimal("50"),
            timestamp=datetime(2025, 6, 1),
        )

        broker = MagicMock()
        broker.submit_order = AsyncMock(return_value=fill)

        tracker = MagicMock()
        tracker.positions = {"AAPL": pos}

        fills = await close_positions(broker, tracker)
        assert len(fills) == 1
        assert fills[0].side == Side.BUY

    @pytest.mark.asyncio()
    async def test_skips_zero_quantity(self, asset: Asset) -> None:
        pos = MagicMock()
        pos.asset = asset
        pos.quantity = Decimal("0")

        broker = MagicMock()
        broker.submit_order = AsyncMock()

        tracker = MagicMock()
        tracker.positions = {"AAPL": pos}

        fills = await close_positions(broker, tracker)
        assert len(fills) == 0
        broker.submit_order.assert_not_called()
