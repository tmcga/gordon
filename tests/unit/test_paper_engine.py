"""Tests for PaperEngine."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from gordon.core.enums import AssetClass, Interval
from gordon.core.models import Asset
from gordon.engine.paper import PaperEngine


@pytest.fixture()
def asset() -> Asset:
    return Asset(symbol="AAPL", asset_class=AssetClass.EQUITY, exchange="NASDAQ")


@pytest.fixture()
def mock_strategy() -> MagicMock:
    strat = MagicMock()
    strat.strategy_id = "test_strat"
    strat.on_bar = MagicMock(return_value=[])
    strat.on_start = MagicMock()
    strat.on_stop = MagicMock()
    return strat


@pytest.fixture()
def mock_data_feed() -> MagicMock:
    feed = MagicMock()
    feed.get_bars = AsyncMock(return_value=None)
    return feed


class TestPaperEngineInstantiation:
    def test_can_create(
        self,
        asset: Asset,
        mock_strategy: MagicMock,
        mock_data_feed: MagicMock,
    ) -> None:
        engine = PaperEngine(
            strategies=[mock_strategy],
            assets=[asset],
            data_feed=mock_data_feed,
            interval=Interval.M1,
            initial_cash=Decimal("100000"),
        )
        assert engine._running is False

    def test_custom_params(
        self,
        asset: Asset,
        mock_strategy: MagicMock,
        mock_data_feed: MagicMock,
    ) -> None:
        engine = PaperEngine(
            strategies=[mock_strategy],
            assets=[asset],
            data_feed=mock_data_feed,
            interval=Interval.D1,
            initial_cash=Decimal("50000"),
            poll_interval=30.0,
        )
        assert engine._interval == Interval.D1
        assert engine._initial_cash == Decimal("50000")
        assert engine._poll_interval == 30.0


class TestPaperEngineStop:
    @pytest.mark.asyncio()
    async def test_stop_sets_running_false(
        self,
        asset: Asset,
        mock_strategy: MagicMock,
        mock_data_feed: MagicMock,
    ) -> None:
        engine = PaperEngine(
            strategies=[mock_strategy],
            assets=[asset],
            data_feed=mock_data_feed,
        )
        engine._running = True
        await engine.stop()
        assert engine._running is False
