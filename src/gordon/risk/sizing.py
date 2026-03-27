"""Position sizing algorithms for the Gordon trading agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import ROUND_DOWN, Decimal

import structlog

log = structlog.get_logger(__name__)


class PositionSizer(ABC):
    """Base class for position sizing strategies."""

    @abstractmethod
    def calculate(
        self,
        equity: Decimal,
        price: Decimal,
        risk_per_trade: float = 0.02,
    ) -> Decimal:
        """Return the position size (quantity) to trade."""


class FixedFractionalSizer(PositionSizer):
    """Risk a fixed fraction of equity per trade.

    quantity = (fraction * equity) / price
    """

    def __init__(self, fraction: float = 0.02) -> None:
        self.fraction = fraction

    def calculate(
        self,
        equity: Decimal,
        price: Decimal,
        risk_per_trade: float = 0.02,
    ) -> Decimal:
        """Return quantity based on fixed fraction of equity."""
        if price <= 0:
            log.warning("fixed_fractional.zero_price")
            return Decimal("0")
        notional = Decimal(str(self.fraction)) * equity
        qty = (notional / price).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        log.debug(
            "fixed_fractional.calculated",
            fraction=self.fraction,
            equity=str(equity),
            price=str(price),
            quantity=str(qty),
        )
        return qty


class KellyCriterionSizer(PositionSizer):
    """Optimal sizing from win rate and payoff ratio.

    Kelly fraction = win_rate - (1 - win_rate) / payoff_ratio
    Use half-Kelly for safety by default.
    """

    def __init__(
        self,
        win_rate: float,
        payoff_ratio: float,
        half_kelly: bool = True,
    ) -> None:
        self.win_rate = win_rate
        self.payoff_ratio = payoff_ratio
        self.half_kelly = half_kelly

    def calculate(
        self,
        equity: Decimal,
        price: Decimal,
        risk_per_trade: float = 0.02,
    ) -> Decimal:
        """Return quantity based on Kelly criterion."""
        if price <= 0 or self.payoff_ratio <= 0:
            log.warning("kelly.invalid_inputs", payoff_ratio=self.payoff_ratio)
            return Decimal("0")

        kelly_f = self.win_rate - (1.0 - self.win_rate) / self.payoff_ratio
        if kelly_f <= 0:
            log.info("kelly.negative_edge", kelly_fraction=kelly_f)
            return Decimal("0")

        if self.half_kelly:
            kelly_f *= 0.5

        notional = Decimal(str(kelly_f)) * equity
        qty = (notional / price).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        log.debug(
            "kelly.calculated",
            kelly_fraction=kelly_f,
            equity=str(equity),
            price=str(price),
            quantity=str(qty),
        )
        return qty


class VolatilityTargetSizer(PositionSizer):
    """Size inversely proportional to asset volatility (ATR).

    quantity = (target_risk * equity) / (atr * price)
    """

    def __init__(
        self,
        target_risk: float = 0.02,
        atr: Decimal = Decimal("1"),
    ) -> None:
        self.target_risk = target_risk
        self.atr = atr

    def calculate(
        self,
        equity: Decimal,
        price: Decimal,
        risk_per_trade: float = 0.02,
    ) -> Decimal:
        """Return quantity scaled inversely to volatility."""
        if price <= 0 or self.atr <= 0:
            log.warning("volatility_target.invalid_inputs", atr=str(self.atr))
            return Decimal("0")

        risk_amount = Decimal(str(self.target_risk)) * equity
        divisor = self.atr * price
        qty = (risk_amount / divisor).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        log.debug(
            "volatility_target.calculated",
            target_risk=self.target_risk,
            atr=str(self.atr),
            equity=str(equity),
            price=str(price),
            quantity=str(qty),
        )
        return qty
