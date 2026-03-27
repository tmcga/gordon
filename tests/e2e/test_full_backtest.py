"""End-to-end test: full backtest pipeline with synthetic data."""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from gordon.core.enums import AssetClass
from gordon.core.models import Asset
from gordon.engine.backtest import BacktestEngine, BacktestResult
from gordon.strategy.templates.sma_crossover import SmaCrossover

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mean_reverting_data(n: int = 200) -> pd.DataFrame:
    """Generate data that oscillates around a mean, producing crossovers."""
    np.random.seed(123)
    dates = pd.date_range(start="2024-01-01", periods=n, freq="B", tz=UTC)

    # Create oscillating prices that will trigger SMA crossovers
    t = np.arange(n)
    base = 100.0
    # Multiple sine waves to create clear crossover opportunities
    prices = base + 10 * np.sin(t * 2 * np.pi / 40) + np.random.normal(0, 0.5, n)
    prices = np.maximum(prices, 50.0)

    closes = prices
    opens = closes * (1 + np.random.normal(0, 0.001, n))
    highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.003, n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.003, n)))
    volumes = np.random.randint(500_000, 2_000_000, n).astype(float)

    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestFullBacktest:
    @pytest.mark.asyncio
    async def test_complete_pipeline(self):
        """Full end-to-end test: data -> strategy -> broker -> tracker -> metrics."""
        asset = Asset(symbol="WAVE", asset_class=AssetClass.EQUITY, exchange="TEST")
        data = _make_mean_reverting_data(200)

        strategy = SmaCrossover(
            strategy_id="sma_e2e",
            params={"fast_period": 5, "slow_period": 20},
        )

        engine = BacktestEngine(
            strategies=[strategy],
            data={asset: data},
            initial_cash=Decimal("100000"),
        )

        result = await engine.run()

        # Structural checks
        assert isinstance(result, BacktestResult)
        assert result.initial_cash == Decimal("100000")
        assert len(result.snapshots) > 0
        assert isinstance(result.final_equity, Decimal)
        assert result.final_equity > Decimal("0")

        # Metrics should be populated
        assert "total_return" in result.metrics
        assert "sharpe_ratio" in result.metrics
        assert "max_drawdown" in result.metrics
        assert result.metrics["max_drawdown"] >= 0.0

        # Date range check
        assert result.start_date < result.end_date
