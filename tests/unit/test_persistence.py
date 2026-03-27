"""Tests for TradeStore persistence layer."""

from datetime import datetime
from decimal import Decimal

import pytest

from gordon.core.enums import AssetClass, Side
from gordon.core.models import Asset, Fill, PortfolioSnapshot, TradeRecord
from gordon.persistence.store import TradeStore


@pytest.fixture()
def store() -> TradeStore:
    """In-memory SQLite store."""
    s = TradeStore(db_url="sqlite://")
    yield s
    s.close()


@pytest.fixture()
def asset() -> Asset:
    return Asset(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        exchange="NASDAQ",
    )


@pytest.fixture()
def fill(asset: Asset) -> Fill:
    return Fill(
        order_id="order-1",
        asset=asset,
        side=Side.BUY,
        price=Decimal("150.00"),
        quantity=Decimal("10"),
        commission=Decimal("1.00"),
        timestamp=datetime(2025, 6, 1, 12, 0, 0),
    )


@pytest.fixture()
def trade_record(asset: Asset) -> TradeRecord:
    return TradeRecord(
        asset=asset,
        side=Side.BUY,
        entry_price=Decimal("150.00"),
        exit_price=Decimal("160.00"),
        quantity=Decimal("10"),
        entry_time=datetime(2025, 6, 1, 12, 0, 0),
        exit_time=datetime(2025, 6, 2, 12, 0, 0),
        pnl=Decimal("100.00"),
        commission=Decimal("2.00"),
        strategy_id="test_strat",
    )


@pytest.fixture()
def snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime(2025, 6, 1, 16, 0, 0),
        cash=Decimal("50000.00"),
        total_equity=Decimal("100000.00"),
        unrealized_pnl=Decimal("500.00"),
        realized_pnl=Decimal("200.00"),
    )


class TestTradeStoreCreation:
    def test_creates_in_memory(self) -> None:
        s = TradeStore(db_url="sqlite://")
        s.close()


class TestRecordFillAndGetFills:
    def test_round_trip(self, store: TradeStore, fill: Fill) -> None:
        store.record_fill(fill, strategy_id="strat1")
        fills = store.get_fills()
        assert len(fills) == 1
        f = fills[0]
        assert f.order_id == "order-1"
        assert f.asset.symbol == "AAPL"
        assert f.side == Side.BUY
        assert f.price == Decimal("150.00")
        assert f.quantity == Decimal("10")
        assert f.commission == Decimal("1.00")

    def test_symbol_filter(self, store: TradeStore, asset: Asset) -> None:
        fill_aapl = Fill(
            order_id="o1",
            asset=asset,
            side=Side.BUY,
            price=Decimal("100"),
            quantity=Decimal("5"),
            timestamp=datetime(2025, 6, 1, 10, 0, 0),
        )
        btc = Asset(symbol="BTC", asset_class=AssetClass.CRYPTO, exchange="binance")
        fill_btc = Fill(
            order_id="o2",
            asset=btc,
            side=Side.SELL,
            price=Decimal("60000"),
            quantity=Decimal("1"),
            timestamp=datetime(2025, 6, 1, 11, 0, 0),
        )
        store.record_fill(fill_aapl)
        store.record_fill(fill_btc)

        aapl_fills = store.get_fills(symbol="AAPL")
        assert len(aapl_fills) == 1
        assert aapl_fills[0].asset.symbol == "AAPL"

        btc_fills = store.get_fills(symbol="BTC")
        assert len(btc_fills) == 1
        assert btc_fills[0].asset.symbol == "BTC"

    def test_since_filter(self, store: TradeStore, asset: Asset) -> None:
        early = Fill(
            order_id="o1",
            asset=asset,
            side=Side.BUY,
            price=Decimal("100"),
            quantity=Decimal("5"),
            timestamp=datetime(2025, 1, 1, 10, 0, 0),
        )
        late = Fill(
            order_id="o2",
            asset=asset,
            side=Side.SELL,
            price=Decimal("110"),
            quantity=Decimal("5"),
            timestamp=datetime(2025, 6, 1, 10, 0, 0),
        )
        store.record_fill(early)
        store.record_fill(late)

        cutoff = datetime(2025, 3, 1)
        fills = store.get_fills(since=cutoff)
        assert len(fills) == 1
        assert fills[0].order_id == "o2"


class TestRecordTradeAndGetTrades:
    def test_round_trip(self, store: TradeStore, trade_record: TradeRecord) -> None:
        store.record_trade(trade_record)
        trades = store.get_trades()
        assert len(trades) == 1
        t = trades[0]
        assert t.asset.symbol == "AAPL"
        assert t.side == Side.BUY
        assert t.entry_price == Decimal("150.00")
        assert t.exit_price == Decimal("160.00")
        assert t.pnl == Decimal("100.00")
        assert t.strategy_id == "test_strat"


class TestRecordSnapshot:
    def test_record_snapshot(self, store: TradeStore, snapshot: PortfolioSnapshot) -> None:
        # Should not raise
        store.record_snapshot(snapshot)


class TestClose:
    def test_close_does_not_error(self) -> None:
        s = TradeStore(db_url="sqlite://")
        s.close()
