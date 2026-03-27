"""Tests for the SimulatedBroker."""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal

import pytest

from gordon.broker.simulated import (
    FixedCommission,
    FixedSlippage,
    NoCommission,
    NoSlippage,
    PercentCommission,
    SimulatedBroker,
    VolumeSlippage,
)
from gordon.core.enums import AssetClass, OrderType, Side
from gordon.core.errors import BrokerError, OrderRejectedError
from gordon.core.models import Asset, Order

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ASSET = Asset(symbol="AAPL", asset_class=AssetClass.EQUITY, exchange="NASDAQ")


def _market_order(side: Side = Side.BUY, qty: Decimal = Decimal("10")) -> Order:
    return Order(
        asset=ASSET,
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        strategy_id="test",
    )


def _limit_order(
    side: Side = Side.BUY,
    qty: Decimal = Decimal("10"),
    limit: Decimal = Decimal("150"),
) -> Order:
    return Order(
        asset=ASSET,
        side=side,
        order_type=OrderType.LIMIT,
        quantity=qty,
        limit_price=limit,
        strategy_id="test",
    )


# ---------------------------------------------------------------------------
# Slippage model tests
# ---------------------------------------------------------------------------


class TestSlippageModels:
    def test_no_slippage(self):
        model = NoSlippage()
        price = Decimal("100")
        assert model.apply(price, Side.BUY, Decimal("10")) == price
        assert model.apply(price, Side.SELL, Decimal("10")) == price

    def test_fixed_slippage_buy(self):
        model = FixedSlippage(bps=Decimal("10"))  # 10 bps = 0.1%
        result = model.apply(Decimal("100"), Side.BUY, Decimal("10"))
        assert result == Decimal("100.10")  # 100 * 1.001

    def test_fixed_slippage_sell(self):
        model = FixedSlippage(bps=Decimal("10"))
        result = model.apply(Decimal("100"), Side.SELL, Decimal("10"))
        assert result == Decimal("99.90")  # 100 * 0.999

    def test_volume_slippage(self):
        model = VolumeSlippage(impact_factor=Decimal("0.1"))
        price = Decimal("100")
        qty = Decimal("10")
        # impact = 0.1 * 10 * 100 / 10000 = 0.01
        buy_price = model.apply(price, Side.BUY, qty)
        assert buy_price == Decimal("100.01")
        sell_price = model.apply(price, Side.SELL, qty)
        assert sell_price == Decimal("99.99")


# ---------------------------------------------------------------------------
# Commission model tests
# ---------------------------------------------------------------------------


class TestCommissionModels:
    def test_no_commission(self):
        model = NoCommission()
        assert model.calculate(Decimal("100"), Decimal("10")) == Decimal("0")

    def test_percent_commission(self):
        model = PercentCommission(rate=Decimal("0.001"))
        # 100 * 10 * 0.001 = 1.0
        assert model.calculate(Decimal("100"), Decimal("10")) == Decimal("1.000")

    def test_fixed_commission(self):
        model = FixedCommission(amount=Decimal("5.00"))
        assert model.calculate(Decimal("100"), Decimal("10")) == Decimal("5.00")


# ---------------------------------------------------------------------------
# SimulatedBroker tests
# ---------------------------------------------------------------------------


class TestSimulatedBroker:
    @pytest.mark.asyncio
    async def test_market_order_fills_at_current_price(self):
        broker = SimulatedBroker()
        broker.set_current_price(ASSET, Decimal("150"))
        order = _market_order()
        order_id = await broker.submit_order(order)
        assert isinstance(order_id, str)

        fills = broker.fill_history
        assert len(fills) == 1
        assert fills[0].price == Decimal("150")
        assert fills[0].quantity == Decimal("10")
        assert fills[0].side == Side.BUY

    @pytest.mark.asyncio
    async def test_no_price_raises_broker_error(self):
        broker = SimulatedBroker()
        with pytest.raises(BrokerError, match="No price"):
            await broker.submit_order(_market_order())

    @pytest.mark.asyncio
    async def test_slippage_applied(self):
        broker = SimulatedBroker(slippage=FixedSlippage(bps=Decimal("10")))
        broker.set_current_price(ASSET, Decimal("100"))
        await broker.submit_order(_market_order(Side.BUY))
        fill = broker.fill_history[0]
        # 10 bps on buy -> price should be 100.10
        assert fill.price == Decimal("100.10")

    @pytest.mark.asyncio
    async def test_commission_applied(self):
        broker = SimulatedBroker(commission=FixedCommission(amount=Decimal("5")))
        broker.set_current_price(ASSET, Decimal("100"))
        await broker.submit_order(_market_order())
        fill = broker.fill_history[0]
        assert fill.commission == Decimal("5")

    @pytest.mark.asyncio
    async def test_position_tracking_buy_then_sell(self):
        broker = SimulatedBroker()
        broker.set_current_price(ASSET, Decimal("100"))

        await broker.submit_order(_market_order(Side.BUY, Decimal("10")))
        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == Decimal("10")

        await broker.submit_order(_market_order(Side.SELL, Decimal("10")))
        positions = await broker.get_positions()
        assert len(positions) == 0  # fully closed, qty == 0 filtered out

    @pytest.mark.asyncio
    async def test_limit_order_buy_fills_when_achievable(self):
        broker = SimulatedBroker()
        broker.set_current_price(ASSET, Decimal("100"))
        order = _limit_order(Side.BUY, limit=Decimal("105"))  # limit above market
        await broker.submit_order(order)
        assert len(broker.fill_history) == 1

    @pytest.mark.asyncio
    async def test_limit_order_buy_rejected_when_unachievable(self):
        broker = SimulatedBroker()
        broker.set_current_price(ASSET, Decimal("100"))
        order = _limit_order(Side.BUY, limit=Decimal("95"))  # limit below market
        with pytest.raises(OrderRejectedError):
            await broker.submit_order(order)

    @pytest.mark.asyncio
    async def test_limit_order_sell_rejected_when_unachievable(self):
        broker = SimulatedBroker()
        broker.set_current_price(ASSET, Decimal("100"))
        order = _limit_order(Side.SELL, limit=Decimal("105"))  # limit above market
        with pytest.raises(OrderRejectedError):
            await broker.submit_order(order)

    @pytest.mark.asyncio
    async def test_cancel_order_returns_false(self):
        broker = SimulatedBroker()
        assert await broker.cancel_order("anything") is False

    @pytest.mark.asyncio
    async def test_get_fills_since(self):
        from datetime import datetime

        broker = SimulatedBroker()
        broker.set_current_price(ASSET, Decimal("100"))
        await broker.submit_order(_market_order())

        # All fills since epoch
        fills = await broker.get_fills(since=datetime(2000, 1, 1, tzinfo=UTC))
        assert len(fills) == 1

        # Fills since far future
        fills = await broker.get_fills(since=datetime(2099, 1, 1, tzinfo=UTC))
        assert len(fills) == 0
