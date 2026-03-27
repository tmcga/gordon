"""Tests for portfolio optimization algorithms."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gordon.portfolio.optimizer import (
    BlackLittermanOptimizer,
    MeanVarianceOptimizer,
    OptimizationResult,
    RiskParityOptimizer,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def synthetic_returns() -> pd.DataFrame:
    """3-asset DataFrame with 100 rows of random daily returns (fixed seed)."""
    np.random.seed(42)
    return pd.DataFrame(np.random.randn(100, 3) * 0.02, columns=["A", "B", "C"])


@pytest.fixture()
def single_asset_returns() -> pd.DataFrame:
    np.random.seed(42)
    return pd.DataFrame(np.random.randn(100, 1) * 0.02, columns=["A"])


@pytest.fixture()
def empty_returns() -> pd.DataFrame:
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# MeanVarianceOptimizer
# ---------------------------------------------------------------------------


class TestMeanVarianceOptimizer:
    def test_weights_sum_to_one(self, synthetic_returns: pd.DataFrame):
        opt = MeanVarianceOptimizer()
        result = opt.optimize(synthetic_returns)
        assert sum(result.weights.values()) == pytest.approx(1.0, abs=1e-6)

    def test_all_weights_non_negative(self, synthetic_returns: pd.DataFrame):
        opt = MeanVarianceOptimizer()
        result = opt.optimize(synthetic_returns)
        for w in result.weights.values():
            assert w >= -1e-9  # allow tiny float noise

    def test_returns_all_symbols(self, synthetic_returns: pd.DataFrame):
        opt = MeanVarianceOptimizer()
        result = opt.optimize(synthetic_returns)
        assert set(result.weights.keys()) == {"A", "B", "C"}

    def test_result_has_expected_fields(self, synthetic_returns: pd.DataFrame):
        opt = MeanVarianceOptimizer()
        result = opt.optimize(synthetic_returns)
        assert isinstance(result, OptimizationResult)
        assert isinstance(result.expected_return, float)
        assert isinstance(result.expected_risk, float)
        assert isinstance(result.sharpe_ratio, float)

    def test_single_asset(self, single_asset_returns: pd.DataFrame):
        opt = MeanVarianceOptimizer()
        result = opt.optimize(single_asset_returns)
        assert result.weights == {"A": 1.0}

    def test_empty_returns(self, empty_returns: pd.DataFrame):
        opt = MeanVarianceOptimizer()
        result = opt.optimize(empty_returns)
        assert result.weights == {}
        assert result.expected_return == 0.0

    def test_risk_is_positive(self, synthetic_returns: pd.DataFrame):
        opt = MeanVarianceOptimizer()
        result = opt.optimize(synthetic_returns)
        assert result.expected_risk > 0


# ---------------------------------------------------------------------------
# RiskParityOptimizer
# ---------------------------------------------------------------------------


class TestRiskParityOptimizer:
    def test_weights_sum_to_one(self, synthetic_returns: pd.DataFrame):
        opt = RiskParityOptimizer()
        result = opt.optimize(synthetic_returns)
        assert sum(result.weights.values()) == pytest.approx(1.0, abs=1e-6)

    def test_all_weights_non_negative(self, synthetic_returns: pd.DataFrame):
        opt = RiskParityOptimizer()
        result = opt.optimize(synthetic_returns)
        for w in result.weights.values():
            assert w >= -1e-9

    def test_all_weights_strictly_positive(self, synthetic_returns: pd.DataFrame):
        """Risk parity should give every asset a non-zero allocation."""
        opt = RiskParityOptimizer()
        result = opt.optimize(synthetic_returns)
        for symbol, w in result.weights.items():
            assert w > 0, f"{symbol} weight should be positive, got {w}"

    def test_single_asset(self, single_asset_returns: pd.DataFrame):
        opt = RiskParityOptimizer()
        result = opt.optimize(single_asset_returns)
        assert result.weights == {"A": 1.0}

    def test_empty_returns(self, empty_returns: pd.DataFrame):
        opt = RiskParityOptimizer()
        result = opt.optimize(empty_returns)
        assert result.weights == {}


# ---------------------------------------------------------------------------
# BlackLittermanOptimizer
# ---------------------------------------------------------------------------


class TestBlackLittermanOptimizer:
    def test_weights_sum_to_one(self, synthetic_returns: pd.DataFrame):
        opt = BlackLittermanOptimizer()
        result = opt.optimize(synthetic_returns)
        assert sum(result.weights.values()) == pytest.approx(1.0, abs=1e-6)

    def test_all_weights_non_negative(self, synthetic_returns: pd.DataFrame):
        opt = BlackLittermanOptimizer()
        result = opt.optimize(synthetic_returns)
        for w in result.weights.values():
            assert w >= -1e-9

    def test_with_views(self, synthetic_returns: pd.DataFrame):
        opt = BlackLittermanOptimizer()
        # Strong bullish view on A
        views = {"A": 0.20}
        result = opt.optimize(synthetic_returns, views=views)
        assert sum(result.weights.values()) == pytest.approx(1.0, abs=1e-6)
        # With a very bullish view on A, it should tilt allocation toward A
        assert result.weights["A"] > 0.0

    def test_with_market_caps(self, synthetic_returns: pd.DataFrame):
        opt = BlackLittermanOptimizer()
        caps = {"A": 1000.0, "B": 500.0, "C": 200.0}
        result = opt.optimize(synthetic_returns, market_caps=caps)
        assert sum(result.weights.values()) == pytest.approx(1.0, abs=1e-6)

    def test_single_asset(self, single_asset_returns: pd.DataFrame):
        opt = BlackLittermanOptimizer()
        result = opt.optimize(single_asset_returns)
        assert result.weights == {"A": 1.0}

    def test_empty_returns(self, empty_returns: pd.DataFrame):
        opt = BlackLittermanOptimizer()
        result = opt.optimize(empty_returns)
        assert result.weights == {}
