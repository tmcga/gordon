"""Tests for gordon.core.models — all domain models."""

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from gordon.core.enums import (
    AssetClass,
    Interval,
    OrderStatus,
    OrderType,
    Side,
    TimeInForce,
)
from gordon.core.models import (
    Asset,
    Bar,
    Fill,
    Order,
    OrderUpdate,
    PortfolioSnapshot,
    Position,
    Signal,
    TradeRecord,
)

# ── Asset ──────────────────────────────────────────────────────────────


class TestAsset:
    def test_creation_with_exchange(self, sample_asset):
        assert sample_asset.symbol == "AAPL"
        assert sample_asset.asset_class == AssetClass.EQUITY
        assert sample_asset.exchange == "NASDAQ"

    def test_creation_without_exchange(self):
        asset = Asset(symbol="SPY", asset_class=AssetClass.EQUITY)
        assert asset.exchange is None

    def test_str_with_exchange(self, sample_asset):
        assert str(sample_asset) == "AAPL@NASDAQ"

    def test_str_without_exchange(self):
        asset = Asset(symbol="SPY", asset_class=AssetClass.EQUITY)
        assert str(asset) == "SPY"

    def test_crypto_asset(self, sample_crypto_asset):
        assert sample_crypto_asset.symbol == "BTC/USDT"
        assert sample_crypto_asset.asset_class == AssetClass.CRYPTO
        assert str(sample_crypto_asset) == "BTC/USDT@binance"

    def test_frozen(self, sample_asset):
        with pytest.raises(ValidationError):
            sample_asset.symbol = "MSFT"

    def test_equality(self):
        a1 = Asset(symbol="AAPL", asset_class=AssetClass.EQUITY, exchange="NASDAQ")
        a2 = Asset(symbol="AAPL", asset_class=AssetClass.EQUITY, exchange="NASDAQ")
        assert a1 == a2

    def test_hashable(self, sample_asset):
        """Frozen models should be hashable."""
        s = {sample_asset}
        assert sample_asset in s


# ── Bar ────────────────────────────────────────────────────────────────


class TestBar:
    def test_creation(self, sample_bar, sample_asset):
        assert sample_bar.asset == sample_asset
        assert sample_bar.open == Decimal("150.00")
        assert sample_bar.high == Decimal("155.00")
        assert sample_bar.low == Decimal("149.00")
        assert sample_bar.close == Decimal("153.00")
        assert sample_bar.volume == Decimal("1000000")
        assert sample_bar.interval == Interval.D1
        assert sample_bar.timestamp == datetime(2025, 1, 15, 16, 0, 0)

    def test_frozen(self, sample_bar):
        with pytest.raises(ValidationError):
            sample_bar.close = Decimal("999")

    def test_requires_asset(self):
        with pytest.raises(ValidationError):
            Bar(
                timestamp=datetime.now(),
                open=Decimal("1"),
                high=Decimal("1"),
                low=Decimal("1"),
                close=Decimal("1"),
                volume=Decimal("1"),
                interval=Interval.D1,
            )


# ── Order ──────────────────────────────────────────────────────────────


class TestOrder:
    def test_creation_with_defaults(self, sample_order):
        assert sample_order.side == Side.BUY
        assert sample_order.order_type == OrderType.MARKET
        assert sample_order.quantity == Decimal("10")
        assert sample_order.time_in_force == TimeInForce.GTC
        assert sample_order.limit_price is None
        assert sample_order.stop_price is None
        assert sample_order.metadata == {}

    def test_auto_generated_id(self, sample_order):
        assert sample_order.id is not None
        assert len(sample_order.id) == 12

    def test_unique_ids(self, sample_asset):
        kwargs = dict(
            asset=sample_asset,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
        )
        o1 = Order(**kwargs)
        o2 = Order(**kwargs)
        assert o1.id != o2.id

    def test_custom_id(self, sample_asset):
        order = Order(
            id="custom-id",
            asset=sample_asset,
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("5"),
            limit_price=Decimal("200.00"),
        )
        assert order.id == "custom-id"
        assert order.limit_price == Decimal("200.00")

    def test_limit_order_with_price(self, sample_asset):
        order = Order(
            asset=sample_asset,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("50"),
            limit_price=Decimal("148.00"),
            time_in_force=TimeInForce.DAY,
        )
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == Decimal("148.00")
        assert order.time_in_force == TimeInForce.DAY

    def test_frozen(self, sample_order):
        with pytest.raises(ValidationError):
            sample_order.quantity = Decimal("999")

    def test_strategy_id_default(self, sample_asset):
        order = Order(
            asset=sample_asset,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
        )
        assert order.strategy_id == ""


# ── Fill ───────────────────────────────────────────────────────────────


class TestFill:
    def test_creation(self, sample_fill):
        assert sample_fill.order_id == "abc123"
        assert sample_fill.side == Side.BUY
        assert sample_fill.price == Decimal("152.50")
        assert sample_fill.quantity == Decimal("10")
        assert sample_fill.commission == Decimal("1.00")

    def test_default_commission(self, sample_asset):
        fill = Fill(
            order_id="x",
            asset=sample_asset,
            side=Side.SELL,
            price=Decimal("100"),
            quantity=Decimal("5"),
        )
        assert fill.commission == Decimal("0")

    def test_default_timestamp(self, sample_asset):
        fill = Fill(
            order_id="x",
            asset=sample_asset,
            side=Side.BUY,
            price=Decimal("100"),
            quantity=Decimal("1"),
        )
        assert isinstance(fill.timestamp, datetime)

    def test_frozen(self, sample_fill):
        with pytest.raises(ValidationError):
            sample_fill.price = Decimal("0")


# ── Position ───────────────────────────────────────────────────────────


class TestPosition:
    def test_long_position(self, sample_position):
        assert sample_position.is_long is True
        assert sample_position.is_short is False

    def test_short_position(self, sample_asset):
        pos = Position(
            asset=sample_asset,
            quantity=Decimal("-50"),
            avg_entry_price=Decimal("150.00"),
        )
        assert pos.is_long is False
        assert pos.is_short is True

    def test_flat_position(self, sample_asset):
        pos = Position(
            asset=sample_asset,
            quantity=Decimal("0"),
            avg_entry_price=Decimal("150.00"),
        )
        assert pos.is_long is False
        assert pos.is_short is False

    def test_market_value_long(self, sample_position):
        # 100 * 150.00 = 15000.00
        assert sample_position.market_value == Decimal("15000.00")

    def test_market_value_short(self, sample_asset):
        pos = Position(
            asset=sample_asset,
            quantity=Decimal("-50"),
            avg_entry_price=Decimal("200.00"),
        )
        # abs(-50) * 200 = 10000
        assert pos.market_value == Decimal("10000.00")

    def test_defaults(self, sample_asset):
        pos = Position(
            asset=sample_asset,
            quantity=Decimal("10"),
            avg_entry_price=Decimal("100"),
        )
        assert pos.unrealized_pnl == Decimal("0")
        assert pos.realized_pnl == Decimal("0")

    def test_frozen(self, sample_position):
        with pytest.raises(ValidationError):
            sample_position.quantity = Decimal("999")


# ── Signal ─────────────────────────────────────────────────────────────


class TestSignal:
    def test_creation(self, sample_asset):
        sig = Signal(
            asset=sample_asset,
            side=Side.BUY,
            strength=0.8,
            strategy_id="momentum",
            reason="breakout detected",
        )
        assert sig.strength == 0.8
        assert sig.strategy_id == "momentum"
        assert sig.reason == "breakout detected"
        assert sig.metadata == {}

    def test_strength_max(self, sample_asset):
        sig = Signal(asset=sample_asset, side=Side.BUY, strength=1.0, strategy_id="s")
        assert sig.strength == 1.0

    def test_strength_min(self, sample_asset):
        sig = Signal(asset=sample_asset, side=Side.SELL, strength=-1.0, strategy_id="s")
        assert sig.strength == -1.0

    def test_strength_too_high(self, sample_asset):
        with pytest.raises(ValidationError):
            Signal(asset=sample_asset, side=Side.BUY, strength=1.1, strategy_id="s")

    def test_strength_too_low(self, sample_asset):
        with pytest.raises(ValidationError):
            Signal(asset=sample_asset, side=Side.SELL, strength=-1.1, strategy_id="s")

    def test_frozen(self, sample_asset):
        sig = Signal(asset=sample_asset, side=Side.BUY, strength=0.5, strategy_id="s")
        with pytest.raises(ValidationError):
            sig.strength = 0.9

    def test_default_reason(self, sample_asset):
        sig = Signal(asset=sample_asset, side=Side.BUY, strength=0.5, strategy_id="s")
        assert sig.reason == ""


# ── PortfolioSnapshot ──────────────────────────────────────────────────


class TestPortfolioSnapshot:
    def test_creation(self, sample_portfolio_snapshot, sample_position):
        snap = sample_portfolio_snapshot
        assert snap.cash == Decimal("85000.00")
        assert snap.total_equity == Decimal("100000.00")
        assert snap.positions == (sample_position,)
        assert len(snap.positions) == 1

    def test_empty_positions_default(self):
        snap = PortfolioSnapshot(
            timestamp=datetime(2025, 1, 1),
            cash=Decimal("100000"),
        )
        assert snap.positions == ()
        assert snap.total_equity == Decimal("0")
        assert snap.unrealized_pnl == Decimal("0")
        assert snap.realized_pnl == Decimal("0")

    def test_frozen(self, sample_portfolio_snapshot):
        with pytest.raises(ValidationError):
            sample_portfolio_snapshot.cash = Decimal("0")


# ── TradeRecord ────────────────────────────────────────────────────────


class TestTradeRecord:
    def _make_trade(self, asset, side=Side.BUY, entry=Decimal("100"), exit_=Decimal("110")):
        return TradeRecord(
            asset=asset,
            side=side,
            entry_price=entry,
            exit_price=exit_,
            quantity=Decimal("10"),
            entry_time=datetime(2025, 1, 1, 10, 0, 0),
            exit_time=datetime(2025, 1, 1, 14, 0, 0),
            pnl=Decimal("100"),
        )

    def test_return_pct_long(self, sample_asset):
        trade = self._make_trade(sample_asset, Side.BUY, Decimal("100"), Decimal("110"))
        # (110 - 100) / 100 = 0.1
        assert trade.return_pct == pytest.approx(0.1)

    def test_return_pct_short(self, sample_asset):
        trade = self._make_trade(sample_asset, Side.SELL, Decimal("100"), Decimal("90"))
        # raw = (90 - 100) / 100 = -0.1; short negates => 0.1
        assert trade.return_pct == pytest.approx(0.1)

    def test_return_pct_short_loss(self, sample_asset):
        trade = self._make_trade(sample_asset, Side.SELL, Decimal("100"), Decimal("110"))
        # raw = (110 - 100) / 100 = 0.1; short negates => -0.1
        assert trade.return_pct == pytest.approx(-0.1)

    def test_return_pct_zero_entry(self, sample_asset):
        trade = self._make_trade(sample_asset, Side.BUY, Decimal("0"), Decimal("10"))
        assert trade.return_pct == 0.0

    def test_holding_period(self, sample_asset):
        trade = self._make_trade(sample_asset)
        # 4 hours = 14400 seconds
        assert trade.holding_period == 14400.0

    def test_holding_period_days(self, sample_asset):
        trade = TradeRecord(
            asset=sample_asset,
            side=Side.BUY,
            entry_price=Decimal("100"),
            exit_price=Decimal("110"),
            quantity=Decimal("10"),
            entry_time=datetime(2025, 1, 1),
            exit_time=datetime(2025, 1, 3),
            pnl=Decimal("100"),
        )
        assert trade.holding_period == 2 * 86400.0

    def test_defaults(self, sample_asset):
        trade = self._make_trade(sample_asset)
        assert trade.commission == Decimal("0")
        assert trade.strategy_id == ""

    def test_frozen(self, sample_asset):
        trade = self._make_trade(sample_asset)
        with pytest.raises(ValidationError):
            trade.pnl = Decimal("0")


# ── OrderUpdate ────────────────────────────────────────────────────────


class TestOrderUpdate:
    def test_creation(self):
        update = OrderUpdate(
            order_id="order123",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("10"),
            avg_fill_price=Decimal("150.00"),
            message="fully filled",
        )
        assert update.order_id == "order123"
        assert update.status == OrderStatus.FILLED
        assert update.filled_quantity == Decimal("10")
        assert update.avg_fill_price == Decimal("150.00")
        assert update.message == "fully filled"

    def test_defaults(self):
        update = OrderUpdate(order_id="x", status=OrderStatus.PENDING)
        assert update.filled_quantity == Decimal("0")
        assert update.avg_fill_price is None
        assert update.message == ""
        assert isinstance(update.timestamp, datetime)

    def test_frozen(self):
        update = OrderUpdate(order_id="x", status=OrderStatus.PENDING)
        with pytest.raises(ValidationError):
            update.status = OrderStatus.FILLED
