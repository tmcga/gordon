"""Tests for risk/performance metrics."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import numpy as np

from gordon.core.enums import AssetClass, Side
from gordon.core.models import Asset, PortfolioSnapshot, TradeRecord
from gordon.risk.metrics import (
    annualized_return,
    calmar_ratio,
    compute_metrics,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    sortino_ratio,
    win_rate,
)

ASSET = Asset(symbol="TEST", asset_class=AssetClass.EQUITY)


# ---------------------------------------------------------------------------
# sharpe_ratio
# ---------------------------------------------------------------------------


class TestSharpeRatio:
    def test_zero_with_single_return(self):
        assert sharpe_ratio(np.array([0.01]), risk_free_rate=0.0) == 0.0

    def test_positive_for_positive_returns(self):
        returns = np.array([0.01, 0.02, 0.015, 0.01, 0.02])
        sr = sharpe_ratio(returns, risk_free_rate=0.0)
        assert sr > 0

    def test_zero_std_returns_zero(self):
        returns = np.array([0.01, 0.01, 0.01, 0.01])
        sr = sharpe_ratio(returns, risk_free_rate=0.0)
        assert sr == 0.0

    def test_risk_free_rate_reduces_sharpe(self):
        returns = np.array([0.01, 0.02, 0.015, 0.01, 0.02])
        sr_no_rf = sharpe_ratio(returns, risk_free_rate=0.0)
        sr_with_rf = sharpe_ratio(returns, risk_free_rate=0.05)
        assert sr_with_rf < sr_no_rf


# ---------------------------------------------------------------------------
# sortino_ratio
# ---------------------------------------------------------------------------


class TestSortinoRatio:
    def test_zero_with_single_return(self):
        assert sortino_ratio(np.array([0.01]), risk_free_rate=0.0) == 0.0

    def test_zero_when_no_downside(self):
        returns = np.array([0.01, 0.02, 0.03, 0.04])
        # All returns positive, risk_free_rate=0 -> excess all positive -> no downside
        so = sortino_ratio(returns, risk_free_rate=0.0)
        assert so == 0.0

    def test_positive_with_mixed_returns(self):
        returns = np.array([0.02, -0.01, 0.03, -0.005, 0.02])
        so = sortino_ratio(returns, risk_free_rate=0.0)
        assert so > 0


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------


class TestMaxDrawdown:
    def test_no_drawdown_for_monotonic_increase(self):
        equity = np.array([100.0, 101.0, 102.0, 103.0])
        assert max_drawdown(equity) == 0.0

    def test_known_drawdown(self):
        equity = np.array([100.0, 110.0, 88.0, 95.0])
        # Peak = 110, trough = 88, dd = (110 - 88) / 110 = 0.2
        dd = max_drawdown(equity)
        assert abs(dd - 0.2) < 1e-9

    def test_single_element(self):
        assert max_drawdown(np.array([100.0])) == 0.0

    def test_full_drawdown(self):
        equity = np.array([100.0, 50.0])
        assert abs(max_drawdown(equity) - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# calmar_ratio
# ---------------------------------------------------------------------------


class TestCalmarRatio:
    def test_zero_drawdown_returns_zero(self):
        assert calmar_ratio(0.10, 0.0) == 0.0

    def test_known_value(self):
        assert abs(calmar_ratio(0.20, 0.10) - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# win_rate
# ---------------------------------------------------------------------------


class TestWinRate:
    def test_empty_trades(self):
        assert win_rate([]) == 0.0

    def test_all_winners(self):
        trades = [
            _trade(pnl=Decimal("10")),
            _trade(pnl=Decimal("20")),
        ]
        assert win_rate(trades) == 1.0

    def test_mixed(self):
        trades = [
            _trade(pnl=Decimal("10")),
            _trade(pnl=Decimal("-5")),
        ]
        assert win_rate(trades) == 0.5


# ---------------------------------------------------------------------------
# profit_factor
# ---------------------------------------------------------------------------


class TestProfitFactor:
    def test_empty_trades(self):
        assert profit_factor([]) == 0.0

    def test_no_losses(self):
        trades = [_trade(pnl=Decimal("10"))]
        assert profit_factor(trades) == float("inf")

    def test_known_value(self):
        trades = [
            _trade(pnl=Decimal("20")),
            _trade(pnl=Decimal("-10")),
        ]
        assert abs(profit_factor(trades) - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# annualized_return
# ---------------------------------------------------------------------------


class TestAnnualizedReturn:
    def test_zero_days(self):
        assert annualized_return(0.1, 0) == 0.0

    def test_one_year(self):
        # Over 365 days, annualized == total
        assert abs(annualized_return(0.10, 365) - 0.10) < 1e-9


# ---------------------------------------------------------------------------
# compute_metrics
# ---------------------------------------------------------------------------


class TestComputeMetrics:
    def test_empty_snapshots(self):
        result = compute_metrics([], [])
        assert result["total_return"] == 0.0

    def test_single_snapshot(self):
        snaps = [_snapshot(Decimal("100000"), datetime(2025, 1, 1))]
        result = compute_metrics(snaps, [])
        assert result["total_return"] == 0.0

    def test_positive_return(self):
        snaps = [
            _snapshot(Decimal("100000"), datetime(2025, 1, 1)),
            _snapshot(Decimal("110000"), datetime(2025, 7, 1)),
        ]
        result = compute_metrics(snaps, [])
        assert abs(result["total_return"] - 0.1) < 1e-9

    def test_all_keys_present(self):
        snaps = [
            _snapshot(Decimal("100000"), datetime(2025, 1, 1)),
            _snapshot(Decimal("110000"), datetime(2025, 7, 1)),
        ]
        result = compute_metrics(snaps, [])
        expected_keys = {
            "total_return",
            "annualized_return",
            "sharpe_ratio",
            "sortino_ratio",
            "max_drawdown",
            "calmar_ratio",
            "win_rate",
            "profit_factor",
            "avg_trade_return",
            "total_trades",
            "avg_holding_period",
        }
        assert set(result.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trade(pnl: Decimal) -> TradeRecord:
    return TradeRecord(
        asset=ASSET,
        side=Side.BUY,
        entry_price=Decimal("100"),
        exit_price=Decimal("100") + pnl / Decimal("10"),
        quantity=Decimal("10"),
        entry_time=datetime(2025, 1, 1),
        exit_time=datetime(2025, 1, 2),
        pnl=pnl,
    )


def _snapshot(equity: Decimal, ts: datetime) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=ts,
        cash=equity,
        positions=(),
        total_equity=equity,
    )
