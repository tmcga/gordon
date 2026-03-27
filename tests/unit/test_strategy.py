"""Tests for the strategy layer: base class, SMA crossover, and registry."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from gordon.core.enums import AssetClass, Interval, Side
from gordon.core.models import Asset, Bar, PortfolioSnapshot, Signal
from gordon.strategy.base import Strategy
from gordon.strategy.registry import StrategyRegistry
from gordon.strategy.templates.sma_crossover import SmaCrossover

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ASSET = Asset(symbol="TEST", asset_class=AssetClass.EQUITY, exchange="TEST")


def _make_bar(close: float, idx: int = 0) -> Bar:
    return Bar(
        asset=ASSET,
        timestamp=datetime(2025, 1, 1 + idx),
        open=Decimal(str(close)),
        high=Decimal(str(close + 1)),
        low=Decimal(str(close - 1)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
        interval=Interval.D1,
    )


def _empty_snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime(2025, 1, 1),
        cash=Decimal("100000"),
        positions=(),
        total_equity=Decimal("100000"),
    )


# ---------------------------------------------------------------------------
# Strategy ABC
# ---------------------------------------------------------------------------


class TestStrategyABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Strategy(strategy_id="boom")  # type: ignore[abstract]

    def test_concrete_subclass_works(self):
        class Dummy(Strategy):
            def on_bar(self, asset, bar, portfolio):
                return []

        d = Dummy(strategy_id="dummy", params={"x": 1})
        assert d.strategy_id == "dummy"
        assert d.params == {"x": 1}
        assert "Dummy" in repr(d)

    def test_lifecycle_hooks_are_noop_by_default(self):
        class Dummy(Strategy):
            def on_bar(self, asset, bar, portfolio):
                return []

        d = Dummy(strategy_id="d")
        d.on_start()
        d.on_stop()


# ---------------------------------------------------------------------------
# SmaCrossover
# ---------------------------------------------------------------------------


class TestSmaCrossover:
    def test_no_signals_until_enough_bars(self):
        strat = SmaCrossover(
            strategy_id="sma_test",
            params={"fast_period": 3, "slow_period": 5},
        )
        strat.on_start()
        snap = _empty_snapshot()
        # Feed 5 bars (slow_period) -- not enough for crossover detection (need slow + 1)
        for i in range(5):
            sigs = strat.on_bar(ASSET, _make_bar(100.0, i), snap)
            assert sigs == []

    def test_golden_cross_produces_buy(self):
        """Feed a clear upward trend so fast SMA crosses above slow SMA."""
        strat = SmaCrossover(
            strategy_id="sma_test",
            params={"fast_period": 3, "slow_period": 5},
        )
        strat.on_start()
        snap = _empty_snapshot()

        # Start low, then trend up sharply to create a golden cross
        prices = [10, 10, 10, 10, 10, 10, 11, 13, 16, 20, 25]
        signals_collected: list[Signal] = []
        for i, p in enumerate(prices):
            sigs = strat.on_bar(ASSET, _make_bar(p, i), snap)
            signals_collected.extend(sigs)

        # We should get at least one BUY signal from the upward cross
        buy_signals = [s for s in signals_collected if s.side == Side.BUY]
        assert len(buy_signals) >= 1
        assert buy_signals[0].strength > 0

    def test_death_cross_produces_sell(self):
        """Feed an uptrend then a sharp downturn for a death cross."""
        strat = SmaCrossover(
            strategy_id="sma_test",
            params={"fast_period": 3, "slow_period": 5},
        )
        strat.on_start()
        snap = _empty_snapshot()

        # Uptrend first to set _was_above=True, then sharp reversal
        prices = [50, 52, 54, 56, 58, 60, 58, 52, 44, 34, 22, 15, 10]
        signals_collected: list[Signal] = []
        for i, p in enumerate(prices):
            sigs = strat.on_bar(ASSET, _make_bar(p, i), snap)
            signals_collected.extend(sigs)

        sell_signals = [s for s in signals_collected if s.side == Side.SELL]
        assert len(sell_signals) >= 1
        assert sell_signals[0].strength < 0

    def test_on_start_resets_state(self):
        strat = SmaCrossover(
            strategy_id="sma_test",
            params={"fast_period": 3, "slow_period": 5},
        )
        snap = _empty_snapshot()
        for i in range(10):
            strat.on_bar(ASSET, _make_bar(100.0 + i, i), snap)

        strat.on_start()
        # After reset, should need bars again
        assert strat._was_above is None
        assert len(strat._bars) == 0


# ---------------------------------------------------------------------------
# StrategyRegistry
# ---------------------------------------------------------------------------


class TestStrategyRegistry:
    def test_register_and_get(self):
        reg = StrategyRegistry()
        reg.register(SmaCrossover)
        strat = reg.get("sma_crossover", params={"fast_period": 5})
        assert isinstance(strat, SmaCrossover)
        assert strat.params["fast_period"] == 5

    def test_list_strategies(self):
        reg = StrategyRegistry()
        reg.register(SmaCrossover)
        names = reg.list_strategies()
        assert "sma_crossover" in names

    def test_unknown_strategy_raises(self):
        reg = StrategyRegistry()
        with pytest.raises(KeyError, match="Unknown strategy"):
            reg.get("nonexistent")

    def test_contains(self):
        reg = StrategyRegistry()
        assert "sma_crossover" not in reg
        reg.register(SmaCrossover)
        assert "sma_crossover" in reg

    def test_len(self):
        reg = StrategyRegistry()
        assert len(reg) == 0
        reg.register(SmaCrossover)
        assert len(reg) == 1

    def test_overwrite_logs_warning(self, caplog):
        import logging

        reg = StrategyRegistry()
        reg.register(SmaCrossover)
        with caplog.at_level(logging.WARNING):
            reg.register(SmaCrossover)
        assert "Overwriting" in caplog.text

    def test_discover_templates(self):
        from pathlib import Path

        reg = StrategyRegistry()
        templates_dir = (
            Path(__file__).resolve().parents[2] / "src" / "gordon" / "strategy" / "templates"
        )
        count = reg.discover(templates_dir)
        assert count >= 2  # sma_crossover and momentum at minimum
        assert "sma_crossover" in reg
        assert "momentum" in reg
