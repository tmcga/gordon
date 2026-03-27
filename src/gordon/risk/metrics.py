"""Performance and risk metrics computed from backtest results.

All metric functions are pure — they take arrays or lists and return floats.
The ``compute_metrics`` entry-point wires everything together.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from gordon.core.models import PortfolioSnapshot, TradeRecord


# ---------------------------------------------------------------------------
# Individual metric functions
# ---------------------------------------------------------------------------


def sharpe_ratio(
    returns: NDArray[np.float64],
    risk_free_rate: float,
    periods: int = 252,
) -> float:
    """Annualized Sharpe ratio.

    ``returns`` should be periodic (e.g. daily) log returns.
    """
    if len(returns) < 2:
        return 0.0
    excess = returns - risk_free_rate / periods
    std = float(np.std(excess, ddof=1))
    if std == 0.0:
        return 0.0
    return float(np.mean(excess)) / std * math.sqrt(periods)


def sortino_ratio(
    returns: NDArray[np.float64],
    risk_free_rate: float,
    periods: int = 252,
) -> float:
    """Annualized Sortino ratio — penalises only downside volatility."""
    if len(returns) < 2:
        return 0.0
    excess = returns - risk_free_rate / periods
    downside = excess[excess < 0]
    if len(downside) == 0:
        return 0.0
    downside_std = float(np.std(downside, ddof=1))
    if downside_std == 0.0:
        return 0.0
    return float(np.mean(excess)) / downside_std * math.sqrt(periods)


def max_drawdown(equity_curve: NDArray[np.float64]) -> float:
    """Maximum peak-to-trough decline as a positive fraction (0.15 = 15%)."""
    if len(equity_curve) < 2:
        return 0.0
    running_max = np.maximum.accumulate(equity_curve)
    drawdowns = (running_max - equity_curve) / running_max
    # Guard against NaN from zero peaks
    drawdowns = np.nan_to_num(drawdowns, nan=0.0)
    return float(np.max(drawdowns))


def calmar_ratio(annualized_ret: float, max_dd: float) -> float:
    """Calmar ratio = annualized return / max drawdown."""
    if max_dd == 0.0:
        return 0.0
    return annualized_ret / max_dd


def win_rate(trades: list[TradeRecord]) -> float:
    """Fraction of trades with positive P&L."""
    if not trades:
        return 0.0
    winners = sum(1 for t in trades if t.pnl > 0)
    return winners / len(trades)


def profit_factor(trades: list[TradeRecord]) -> float:
    """Gross profit divided by gross loss."""
    if not trades:
        return 0.0
    gross_profit = sum(float(t.pnl) for t in trades if t.pnl > 0)
    gross_loss = abs(sum(float(t.pnl) for t in trades if t.pnl < 0))
    if gross_loss == 0.0:
        return 0.0 if gross_profit == 0.0 else float("inf")
    return gross_profit / gross_loss


def annualized_return(total_return: float, days: int) -> float:
    """Convert a total return fraction to an annualized figure.

    Uses the formula: (1 + total_return)^(365 / days) - 1
    """
    if days <= 0:
        return 0.0
    return float((1.0 + total_return) ** (365.0 / days) - 1.0)


# ---------------------------------------------------------------------------
# Composite entry-point
# ---------------------------------------------------------------------------


def compute_metrics(
    snapshots: list[PortfolioSnapshot],
    trades: list[TradeRecord],
    risk_free_rate: float = 0.05,
) -> dict[str, float]:
    """Compute a full suite of performance and risk metrics.

    Parameters
    ----------
    snapshots:
        Periodic portfolio snapshots (one per bar, ordered by time).
    trades:
        Completed round-trip trade records.
    risk_free_rate:
        Annualized risk-free rate (default 5%).

    Returns
    -------
    dict with keys:
        total_return, annualized_return, sharpe_ratio, sortino_ratio,
        max_drawdown, calmar_ratio, win_rate, profit_factor,
        avg_trade_return, total_trades, avg_holding_period
    """
    if len(snapshots) < 2:
        return _empty_metrics()

    # Build equity curve from snapshots
    equity = np.array([float(s.total_equity) for s in snapshots])

    # Daily log returns (skip zero-equity entries)
    safe_equity = np.where(equity > 0, equity, 1e-10)
    log_returns = np.diff(np.log(safe_equity))

    # Total return
    initial_equity = float(snapshots[0].total_equity)
    final_equity = float(snapshots[-1].total_equity)
    total_ret = 0.0 if initial_equity == 0 else (final_equity - initial_equity) / initial_equity

    # Number of calendar days
    delta = snapshots[-1].timestamp - snapshots[0].timestamp
    days = max(delta.days, 1)

    ann_ret = annualized_return(total_ret, days)
    mdd = max_drawdown(equity)
    sr = sharpe_ratio(log_returns, risk_free_rate)
    so = sortino_ratio(log_returns, risk_free_rate)
    cr = calmar_ratio(ann_ret, mdd)
    wr = win_rate(trades)
    pf = profit_factor(trades)

    # Trade-level stats
    total_trades = len(trades)
    avg_trade_ret = 0.0
    avg_holding = 0.0
    if total_trades > 0:
        avg_trade_ret = sum(t.return_pct for t in trades) / total_trades
        avg_holding = sum(t.holding_period for t in trades) / total_trades

    return {
        "total_return": total_ret,
        "annualized_return": ann_ret,
        "sharpe_ratio": sr,
        "sortino_ratio": so,
        "max_drawdown": mdd,
        "calmar_ratio": cr,
        "win_rate": wr,
        "profit_factor": pf,
        "avg_trade_return": avg_trade_ret,
        "total_trades": float(total_trades),
        "avg_holding_period": avg_holding,
    }


def _empty_metrics() -> dict[str, float]:
    """Return zeroed-out metrics when there is insufficient data."""
    return {
        "total_return": 0.0,
        "annualized_return": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "max_drawdown": 0.0,
        "calmar_ratio": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "avg_trade_return": 0.0,
        "total_trades": 0.0,
        "avg_holding_period": 0.0,
    }
