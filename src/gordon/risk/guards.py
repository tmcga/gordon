"""Individual risk guard implementations for pre-trade checks."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from gordon.core.protocols import RiskVerdict
from gordon.risk.limits import DailyLossTracker, DrawdownTracker

if TYPE_CHECKING:
    from gordon.core.models import Order, PortfolioSnapshot

log = structlog.get_logger(__name__)


class MaxPositionSizeGuard:
    """Reject if the order would put more than *max_pct* of equity into one asset."""

    name: str = "max_position_size"

    def __init__(self, max_pct: float = 0.1) -> None:
        self.max_pct = max_pct

    def check(self, order: Order, portfolio: PortfolioSnapshot) -> RiskVerdict:
        equity = portfolio.total_equity
        if equity <= 0:
            return RiskVerdict(False, f"{self.name}: zero equity")

        order_value = order.quantity * (order.limit_price or Decimal("0"))
        if order.limit_price is None:
            # For market orders without a limit price we cannot compute
            # value precisely; approve and let downstream guards catch it.
            log.debug("max_position_size.no_limit_price", order_id=order.id)
            return RiskVerdict(True)

        pct = float(order_value / equity)
        if pct > self.max_pct:
            reason = f"{self.name}: order is {pct:.1%} of equity (limit {self.max_pct:.1%})"
            log.warning("max_position_size.rejected", reason=reason)
            return RiskVerdict(False, reason)

        log.debug("max_position_size.approved", pct=f"{pct:.2%}")
        return RiskVerdict(True)


class MaxConcentrationGuard:
    """Reject if any single position would exceed *max_pct* of total equity."""

    name: str = "max_concentration"

    def __init__(self, max_pct: float = 0.25) -> None:
        self.max_pct = max_pct

    def check(self, order: Order, portfolio: PortfolioSnapshot) -> RiskVerdict:
        equity = portfolio.total_equity
        if equity <= 0:
            return RiskVerdict(False, f"{self.name}: zero equity")

        # Find existing position value for this asset
        existing_value = Decimal("0")
        for pos in portfolio.positions:
            if pos.asset.symbol == order.asset.symbol:
                existing_value = pos.market_value
                break

        order_value = order.quantity * (order.limit_price or Decimal("0"))
        if order.limit_price is None:
            log.debug("max_concentration.no_limit_price", order_id=order.id)
            return RiskVerdict(True)

        projected = existing_value + order_value
        pct = float(projected / equity)
        if pct > self.max_pct:
            reason = (
                f"{self.name}: {order.asset.symbol} would be {pct:.1%} "
                f"of equity (limit {self.max_pct:.1%})"
            )
            log.warning("max_concentration.rejected", reason=reason)
            return RiskVerdict(False, reason)

        log.debug(
            "max_concentration.approved",
            symbol=order.asset.symbol,
            pct=f"{pct:.2%}",
        )
        return RiskVerdict(True)


class CooldownGuard:
    """Reject if the last trade in this asset was less than *seconds* ago."""

    name: str = "cooldown"

    def __init__(self, seconds: float = 300) -> None:
        self.seconds = seconds
        self._last_trade: dict[str, float] = {}

    def record_trade(self, symbol: str) -> None:
        """Record a trade timestamp for the given symbol."""
        self._last_trade[symbol] = time.monotonic()

    def check(self, order: Order, portfolio: PortfolioSnapshot) -> RiskVerdict:
        symbol = order.asset.symbol
        last = self._last_trade.get(symbol)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < self.seconds:
                remaining = self.seconds - elapsed
                reason = (
                    f"{self.name}: {symbol} traded {elapsed:.0f}s ago, "
                    f"cooldown {remaining:.0f}s remaining"
                )
                log.warning("cooldown.rejected", reason=reason)
                return RiskVerdict(False, reason)

        log.debug("cooldown.approved", symbol=symbol)
        return RiskVerdict(True)


class DailyLossLimitGuard:
    """Reject all orders if daily realized loss exceeds threshold."""

    name: str = "daily_loss_limit"

    def __init__(self, max_loss_pct: float = 0.02) -> None:
        self.max_loss_pct = max_loss_pct
        self.tracker = DailyLossTracker()

    def check(self, order: Order, portfolio: PortfolioSnapshot) -> RiskVerdict:
        equity = portfolio.total_equity
        if equity <= 0:
            return RiskVerdict(False, f"{self.name}: zero equity")

        loss_pct = float(self.tracker.daily_loss / equity)
        if loss_pct >= self.max_loss_pct:
            reason = (
                f"{self.name}: daily loss {loss_pct:.2%} exceeds limit {self.max_loss_pct:.2%}"
            )
            log.warning("daily_loss_limit.rejected", reason=reason)
            return RiskVerdict(False, reason)

        log.debug("daily_loss_limit.approved", daily_loss_pct=f"{loss_pct:.2%}")
        return RiskVerdict(True)


class MaxDrawdownGuard:
    """Reject if portfolio drawdown from peak exceeds threshold."""

    name: str = "max_drawdown"

    def __init__(self, max_drawdown: float = 0.10) -> None:
        self.max_drawdown = max_drawdown
        self.tracker = DrawdownTracker()

    def check(self, order: Order, portfolio: PortfolioSnapshot) -> RiskVerdict:
        self.tracker.update(portfolio.total_equity)
        dd = self.tracker.drawdown
        if dd >= self.max_drawdown:
            reason = f"{self.name}: drawdown {dd:.2%} exceeds limit {self.max_drawdown:.2%}"
            log.warning("max_drawdown.rejected", reason=reason)
            return RiskVerdict(False, reason)

        log.debug("max_drawdown.approved", drawdown=f"{dd:.2%}")
        return RiskVerdict(True)


class SymbolWhitelistGuard:
    """Reject if asset symbol is not in the whitelist."""

    name: str = "symbol_whitelist"

    def __init__(self, symbols: set[str]) -> None:
        self.symbols = symbols

    def check(self, order: Order, portfolio: PortfolioSnapshot) -> RiskVerdict:
        if order.asset.symbol not in self.symbols:
            reason = f"{self.name}: {order.asset.symbol} not in whitelist"
            log.warning("symbol_whitelist.rejected", reason=reason)
            return RiskVerdict(False, reason)

        log.debug("symbol_whitelist.approved", symbol=order.asset.symbol)
        return RiskVerdict(True)
