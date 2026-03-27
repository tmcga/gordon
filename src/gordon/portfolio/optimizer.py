"""Portfolio optimization algorithms — mean-variance, risk parity, Black-Litterman."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import minimize

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class OptimizationResult:
    """Output of a portfolio optimization run."""

    weights: dict[str, float]  # symbol -> weight (0-1)
    expected_return: float
    expected_risk: float  # annualized volatility
    sharpe_ratio: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRADING_DAYS = 252


def _annualize_return(daily_mean: float) -> float:
    return daily_mean * _TRADING_DAYS


def _annualize_vol(daily_vol: float) -> float:
    return daily_vol * np.sqrt(_TRADING_DAYS)


def _portfolio_return(weights: np.ndarray, mean_returns: np.ndarray) -> float:
    return float(weights @ mean_returns)


def _portfolio_vol(weights: np.ndarray, cov: np.ndarray) -> float:
    return float(np.sqrt(weights @ cov @ weights))


def _clip_weights(weights: np.ndarray) -> np.ndarray:
    """Clip tiny negative values from numerical noise and re-normalize."""
    w = np.maximum(weights, 0.0)
    total = w.sum()
    if total > 0:
        w /= total
    return w


# ---------------------------------------------------------------------------
# Mean-Variance (Markowitz)
# ---------------------------------------------------------------------------


class MeanVarianceOptimizer:
    """Markowitz mean-variance optimization.

    Finds weights on the efficient frontier that maximize Sharpe ratio.
    """

    def optimize(
        self,
        returns: pd.DataFrame,
        risk_free_rate: float = 0.05,
        target_return: float | None = None,
    ) -> OptimizationResult:
        """Run mean-variance optimization.

        Parameters
        ----------
        returns:
            DataFrame with columns = symbols, rows = daily returns.
        risk_free_rate:
            Annualized risk-free rate (default 5 %).
        target_return:
            If given, minimize risk for this target annualized return.
            Otherwise maximize Sharpe ratio.
        """
        symbols = list(returns.columns)
        n = len(symbols)

        if n == 0:
            return OptimizationResult(
                weights={}, expected_return=0.0, expected_risk=0.0, sharpe_ratio=0.0
            )

        if n == 1:
            mu = _annualize_return(float(returns.iloc[:, 0].mean()))
            vol = _annualize_vol(float(returns.iloc[:, 0].std()))
            sr = (mu - risk_free_rate) / vol if vol > 0 else 0.0
            return OptimizationResult(
                weights={symbols[0]: 1.0},
                expected_return=mu,
                expected_risk=vol,
                sharpe_ratio=sr,
            )

        mean_ret = returns.mean().values
        cov = returns.cov().values
        daily_rf = risk_free_rate / _TRADING_DAYS

        x0 = np.ones(n) / n
        bounds = tuple((0.0, 1.0) for _ in range(n))
        constraints: list[dict] = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        ]

        if target_return is not None:
            daily_target = target_return / _TRADING_DAYS
            constraints.append(
                {
                    "type": "eq",
                    "fun": lambda w: _portfolio_return(w, mean_ret) - daily_target,
                }
            )

            def obj(w: np.ndarray) -> float:
                return _portfolio_vol(w, cov)

        else:

            def obj(w: np.ndarray) -> float:
                ret = _portfolio_return(w, mean_ret) - daily_rf
                vol = _portfolio_vol(w, cov)
                if vol < 1e-12:
                    return 0.0
                return -ret / vol  # negative Sharpe to minimize

        result = minimize(obj, x0, method="SLSQP", bounds=bounds, constraints=constraints)
        w = _clip_weights(result.x)

        ann_ret = _annualize_return(_portfolio_return(w, mean_ret))
        ann_vol = _annualize_vol(_portfolio_vol(w, cov))
        sr = (ann_ret - risk_free_rate) / ann_vol if ann_vol > 0 else 0.0

        return OptimizationResult(
            weights=dict(zip(symbols, w.tolist(), strict=True)),
            expected_return=ann_ret,
            expected_risk=ann_vol,
            sharpe_ratio=sr,
        )


# ---------------------------------------------------------------------------
# Risk Parity
# ---------------------------------------------------------------------------


class RiskParityOptimizer:
    """Equal risk contribution -- each asset contributes equally to portfolio risk."""

    def optimize(self, returns: pd.DataFrame) -> OptimizationResult:
        symbols = list(returns.columns)
        n = len(symbols)

        if n == 0:
            return OptimizationResult(
                weights={}, expected_return=0.0, expected_risk=0.0, sharpe_ratio=0.0
            )

        if n == 1:
            mu = _annualize_return(float(returns.iloc[:, 0].mean()))
            vol = _annualize_vol(float(returns.iloc[:, 0].std()))
            return OptimizationResult(
                weights={symbols[0]: 1.0},
                expected_return=mu,
                expected_risk=vol,
                sharpe_ratio=mu / vol if vol > 0 else 0.0,
            )

        cov = returns.cov().values
        mean_ret = returns.mean().values
        target_risk = 1.0 / n

        def obj(w: np.ndarray) -> float:
            port_vol = _portfolio_vol(w, cov)
            if port_vol < 1e-12:
                return 0.0
            marginal = cov @ w
            risk_contrib = w * marginal / port_vol
            return float(np.sum((risk_contrib - target_risk) ** 2))

        x0 = np.ones(n) / n
        bounds = tuple((1e-6, 1.0) for _ in range(n))
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

        result = minimize(obj, x0, method="SLSQP", bounds=bounds, constraints=constraints)
        w = _clip_weights(result.x)

        ann_ret = _annualize_return(_portfolio_return(w, mean_ret))
        ann_vol = _annualize_vol(_portfolio_vol(w, cov))
        sr = ann_ret / ann_vol if ann_vol > 0 else 0.0

        return OptimizationResult(
            weights=dict(zip(symbols, w.tolist(), strict=True)),
            expected_return=ann_ret,
            expected_risk=ann_vol,
            sharpe_ratio=sr,
        )


# ---------------------------------------------------------------------------
# Black-Litterman
# ---------------------------------------------------------------------------


class BlackLittermanOptimizer:
    """Black-Litterman: incorporate subjective views (from AI agent) as priors.

    Views are expressed as: ``{"AAPL": 0.10, "MSFT": 0.05}`` meaning
    "I expect AAPL to return 10 % and MSFT to return 5 %".
    """

    def optimize(
        self,
        returns: pd.DataFrame,
        market_caps: dict[str, float] | None = None,
        views: dict[str, float] | None = None,
        risk_free_rate: float = 0.05,
    ) -> OptimizationResult:
        symbols = list(returns.columns)
        n = len(symbols)

        if n == 0:
            return OptimizationResult(
                weights={}, expected_return=0.0, expected_risk=0.0, sharpe_ratio=0.0
            )

        if n == 1:
            mu = _annualize_return(float(returns.iloc[:, 0].mean()))
            vol = _annualize_vol(float(returns.iloc[:, 0].std()))
            sr = (mu - risk_free_rate) / vol if vol > 0 else 0.0
            return OptimizationResult(
                weights={symbols[0]: 1.0},
                expected_return=mu,
                expected_risk=vol,
                sharpe_ratio=sr,
            )

        cov_daily = returns.cov().values
        cov = cov_daily * _TRADING_DAYS  # annualized covariance

        # Market-cap weights (equilibrium) -- default to equal weight
        if market_caps is not None:
            cap_arr = np.array([market_caps.get(s, 1.0) for s in symbols])
        else:
            cap_arr = np.ones(n)
        w_mkt = cap_arr / cap_arr.sum()

        # Risk aversion parameter (delta)
        delta = 2.5

        # Implied equilibrium returns: Pi = delta * Sigma * w_mkt
        pi = delta * cov @ w_mkt

        # If no views, just use equilibrium returns
        if not views:
            adjusted_returns = pi
        else:
            # Build pick matrix P and view vector Q
            view_symbols = [s for s in views if s in symbols]
            k = len(view_symbols)
            if k == 0:
                adjusted_returns = pi
            else:
                pick = np.zeros((k, n))
                q_vec = np.zeros(k)
                for i, s in enumerate(view_symbols):
                    idx = symbols.index(s)
                    pick[i, idx] = 1.0
                    q_vec[i] = views[s]

                # Uncertainty in views: tau * Sigma
                tau = 0.05
                omega = np.diag(np.diag(pick @ (tau * cov) @ pick.T))

                # BL formula:
                #   adj = inv(inv(tau*Sigma) + P'*inv(Omega)*P)
                #       * (inv(tau*Sigma)*Pi + P'*inv(Omega)*Q)
                tau_cov_inv = np.linalg.inv(tau * cov)
                omega_inv = np.linalg.inv(omega)
                blend = np.linalg.inv(tau_cov_inv + pick.T @ omega_inv @ pick)
                adjusted_returns = blend @ (tau_cov_inv @ pi + pick.T @ omega_inv @ q_vec)

        # Run mean-variance on adjusted returns (already annualized)
        daily_adj = adjusted_returns / _TRADING_DAYS
        daily_rf = risk_free_rate / _TRADING_DAYS

        def neg_sharpe(w: np.ndarray) -> float:
            ret = float(w @ daily_adj) - daily_rf
            vol = _portfolio_vol(w, cov_daily)
            if vol < 1e-12:
                return 0.0
            return -ret / vol

        x0 = np.ones(n) / n
        bounds = tuple((0.0, 1.0) for _ in range(n))
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

        result = minimize(neg_sharpe, x0, method="SLSQP", bounds=bounds, constraints=constraints)
        w = _clip_weights(result.x)

        ann_ret = float(w @ adjusted_returns)
        ann_vol = _annualize_vol(_portfolio_vol(w, cov_daily))
        sr = (ann_ret - risk_free_rate) / ann_vol if ann_vol > 0 else 0.0

        return OptimizationResult(
            weights=dict(zip(symbols, w.tolist(), strict=True)),
            expected_return=ann_ret,
            expected_risk=ann_vol,
            sharpe_ratio=sr,
        )
