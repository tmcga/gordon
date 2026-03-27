"""Shared test fixtures for the Gordon test suite."""

from datetime import datetime
from decimal import Decimal

import pytest

from gordon.core.enums import (
    AssetClass,
    Interval,
    OrderType,
    Side,
)
from gordon.core.models import (
    Asset,
    Bar,
    Fill,
    Order,
    PortfolioSnapshot,
    Position,
)


@pytest.fixture()
def sample_asset() -> Asset:
    """AAPL equity asset."""
    return Asset(symbol="AAPL", asset_class=AssetClass.EQUITY, exchange="NASDAQ")


@pytest.fixture()
def sample_crypto_asset() -> Asset:
    """BTC/USDT crypto asset."""
    return Asset(symbol="BTC/USDT", asset_class=AssetClass.CRYPTO, exchange="binance")


@pytest.fixture()
def sample_bar(sample_asset: Asset) -> Bar:
    """A daily OHLCV bar for AAPL."""
    return Bar(
        asset=sample_asset,
        timestamp=datetime(2025, 1, 15, 16, 0, 0),
        open=Decimal("150.00"),
        high=Decimal("155.00"),
        low=Decimal("149.00"),
        close=Decimal("153.00"),
        volume=Decimal("1000000"),
        interval=Interval.D1,
    )


@pytest.fixture()
def sample_order(sample_asset: Asset) -> Order:
    """A market buy order for AAPL."""
    return Order(
        asset=sample_asset,
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
        strategy_id="test_strategy",
    )


@pytest.fixture()
def sample_fill(sample_asset: Asset) -> Fill:
    """A fill for an AAPL buy order."""
    return Fill(
        order_id="abc123",
        asset=sample_asset,
        side=Side.BUY,
        price=Decimal("152.50"),
        quantity=Decimal("10"),
        commission=Decimal("1.00"),
    )


@pytest.fixture()
def sample_position(sample_asset: Asset) -> Position:
    """A long AAPL position."""
    return Position(
        asset=sample_asset,
        quantity=Decimal("100"),
        avg_entry_price=Decimal("150.00"),
        unrealized_pnl=Decimal("300.00"),
        realized_pnl=Decimal("0"),
    )


@pytest.fixture()
def sample_portfolio_snapshot(sample_position: Position) -> PortfolioSnapshot:
    """A portfolio snapshot with one position."""
    return PortfolioSnapshot(
        timestamp=datetime(2025, 1, 15, 16, 0, 0),
        cash=Decimal("85000.00"),
        positions=(sample_position,),
        total_equity=Decimal("100000.00"),
        unrealized_pnl=Decimal("300.00"),
        realized_pnl=Decimal("0"),
    )
