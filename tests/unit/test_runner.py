"""Tests for EngineRunner."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from gordon.core.enums import AssetClass, Interval
from gordon.core.models import Asset
from gordon.engine.paper import PaperEngine
from gordon.engine.runner import EngineRunner


class TestEngineRunnerInstantiation:
    def test_can_create_with_paper_engine(self) -> None:
        asset = Asset(
            symbol="AAPL",
            asset_class=AssetClass.EQUITY,
            exchange="NASDAQ",
        )
        strategy = MagicMock()
        strategy.strategy_id = "test"
        strategy.on_bar = MagicMock(return_value=[])

        data_feed = MagicMock()
        data_feed.get_bars = AsyncMock(return_value=None)

        engine = PaperEngine(
            strategies=[strategy],
            assets=[asset],
            data_feed=data_feed,
            interval=Interval.M1,
            initial_cash=Decimal("100000"),
        )
        runner = EngineRunner(engine=engine)
        assert runner._engine is engine
