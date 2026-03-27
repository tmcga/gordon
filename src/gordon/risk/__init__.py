"""Risk management — metrics, guards, position sizing, and limit tracking."""

from gordon.risk.guards import (
    CooldownGuard,
    DailyLossLimitGuard,
    MaxConcentrationGuard,
    MaxDrawdownGuard,
    MaxPositionSizeGuard,
    SymbolWhitelistGuard,
)
from gordon.risk.limits import DailyLossTracker, DrawdownTracker
from gordon.risk.manager import RiskManager
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
from gordon.risk.sizing import (
    FixedFractionalSizer,
    KellyCriterionSizer,
    PositionSizer,
    VolatilityTargetSizer,
)

__all__ = [
    "CooldownGuard",
    "DailyLossLimitGuard",
    "DailyLossTracker",
    "DrawdownTracker",
    "FixedFractionalSizer",
    "KellyCriterionSizer",
    "MaxConcentrationGuard",
    "MaxDrawdownGuard",
    "MaxPositionSizeGuard",
    "PositionSizer",
    "RiskManager",
    "SymbolWhitelistGuard",
    "VolatilityTargetSizer",
    "annualized_return",
    "calmar_ratio",
    "compute_metrics",
    "max_drawdown",
    "profit_factor",
    "sharpe_ratio",
    "sortino_ratio",
    "win_rate",
]
